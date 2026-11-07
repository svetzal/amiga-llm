from pathlib import Path
from unittest.mock import Mock

import pytest
from amiga_env import session
from amiga_env.session import (
    HOOK,
    Emulator,
    Volume,
    boot_script,
    filesystem_setting,
    headless,
    read_done,
    run_rexx,
    run_script,
    socket_path,
    with_hook,
)


class TestTheStartupHook:
    def test_it_is_added_at_the_end_of_user_startup(self):
        assert with_hook("Assign SC: SYS:SC\n") == "Assign SC: SYS:SC\n" + HOOK

    def test_adding_it_twice_leaves_one_copy(self):
        once = with_hook("Path SC:c ADD\n")

        assert with_hook(once) == once

    def test_a_hook_in_the_middle_moves_to_the_end(self):
        text = "a\n" + HOOK + "b\n"

        assert with_hook(text) == "a\nb\n" + HOOK

    def test_a_last_line_without_a_newline_keeps_its_own_line(self):
        assert with_hook("EndIf") == "EndIf\n" + HOOK

    def test_it_runs_the_boot_script_only_when_amigaenv_is_mounted(self):
        assert "Assign >NIL: AmigaEnv: EXISTS\nIf NOT WARN\n" in HOOK
        assert "Run >NIL: Execute AmigaEnv:boot\n" in HOOK


class TestTheRunScripts:
    def test_boot_starts_arexx_and_hands_over(self):
        assert boot_script().splitlines()[-3:] == [
            "RexxMast >NIL:",
            "WaitForPort REXX",
            "rx AmigaEnv:run.rexx",
        ]

    def test_the_script_runs_in_a_shell_of_its_own_with_its_output_kept(self):
        assert "address command 'Execute AmigaEnv:script >AmigaEnv:script.log'" in run_rexx()

    def test_the_return_code_goes_to_done(self):
        assert "open(done, 'AmigaEnv:done', 'W')" in run_rexx()
        assert "call writeln(done, code)" in run_rexx()

    def test_a_fresh_exchange_holds_only_the_new_run(self, tmp_path):
        (tmp_path / "done").write_text("0\n")

        session.prepare_exchange(tmp_path, "Echo hi\n")

        assert sorted(p.name for p in tmp_path.iterdir()) == ["boot", "run.rexx", "script"]
        assert (tmp_path / "script").read_text() == "Echo hi\n"

    @pytest.mark.parametrize(
        ("content", "code"), [(None, None), ("", None), ("0\n", 0), ("20\n", 20), ("x", None)]
    )
    def test_done_holds_the_return_code_once_written(self, tmp_path, content, code):
        if content is not None:
            (tmp_path / "done").write_text(content)

        assert read_done(tmp_path) == code


class TestAmiberryArguments:
    def test_a_folder_mounts_read_write_with_its_boot_priority(self):
        volume = Volume("DH0", "System", Path("/p/runs/systems/x"), 0)

        assert filesystem_setting(volume) == "filesystem2=rw,DH0:System:/p/runs/systems/x,0"

    def test_volumes_are_not_bootable_unless_asked(self):
        assert filesystem_setting(Volume("DH1", "Work", Path("/w"))).endswith(",-128")

    def test_a_path_with_a_comma_is_refused(self):
        with pytest.raises(SystemExit, match="comma"):
            filesystem_setting(Volume("DH1", "Work", Path("/a,b")))

    def test_the_socket_amiberry_chose_is_read_from_its_log(self):
        log = "Amiberry v8.5.0\nIPC: Default socket in use, using instance 1\n"
        log += "IPC: Listening on /tmp/amiberry_1.sock\n"

        assert socket_path(log) == "/tmp/amiberry_1.sock"
        assert socket_path("starting\n") is None

    def test_runs_have_no_window_or_sound_unless_the_caller_chooses(self):
        assert headless({"HOME": "/h"}) == {
            "SDL_VIDEODRIVER": "dummy",
            "SDL_AUDIODRIVER": "dummy",
            "HOME": "/h",
        }
        assert headless({"SDL_VIDEODRIVER": "cocoa"})["SDL_VIDEODRIVER"] == "cocoa"


class SteppedClock:
    """Simulated time: each sleep advances it."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class TestRunScript:
    @pytest.fixture
    def clock(self):
        return SteppedClock()

    @pytest.fixture
    def exchange(self, tmp_path):
        return tmp_path / "exchange"

    def _emulator(self, exchange: Path, finish_after: int | None, code: int = 0):
        """A fake emulator that writes `done` after some LIST/poll calls."""
        emulator = Mock(spec=Emulator)
        emulator.socket = None
        emulator.log_path = exchange / "amiberry.log"
        emulator.log.return_value = "IPC: Listening on /tmp/amiberry_2.sock\n"
        emulator.running.return_value = True
        polls = {"count": 0}

        def send(*fields, **_):
            if fields[0] == "LIST_HARDDRIVES":
                return ["OK", f"unit0=dir:{exchange.resolve()}"]
            return ["OK"]

        def running():
            polls["count"] += 1
            if finish_after is not None and polls["count"] >= finish_after:
                (exchange / "done").write_text(f"{code}\n")
                (exchange / "script.log").write_text("hello\n")
            return True

        emulator.send.side_effect = send
        emulator.running.side_effect = running
        return emulator

    def test_it_returns_the_scripts_code_and_output_then_quits(self, clock, exchange):
        emulator = self._emulator(exchange, finish_after=3, code=5)

        outcome = run_script(
            ["--model", "A3000"],
            exchange,
            "Echo hello\n",
            timeout=60,
            launch=lambda args, log: emulator,
            now=clock,
            sleep=clock.sleep,
        )

        assert outcome.return_code == 5
        assert outcome.log == "hello\n"
        assert emulator.socket == "/tmp/amiberry_2.sock"
        emulator.stop.assert_called_once()

    def test_it_mounts_the_exchange_folder_and_starts_without_the_gui(self, clock, exchange):
        emulator = self._emulator(exchange, finish_after=1)
        launched = {}

        def launch(args, log):
            launched["args"] = args
            return emulator

        run_script(["--model", "A3000"], exchange, "", 60, None, launch, clock, clock.sleep)

        assert launched["args"][-3:] == [
            "-s",
            f"filesystem2=rw,AENV:AmigaEnv:{exchange.resolve()},-128",
            "-G",
        ]

    def test_a_screenshot_is_taken_through_the_socket_when_it_ends(self, clock, exchange):
        emulator = self._emulator(exchange, finish_after=2)
        shot = exchange.parent / "shots" / "end.png"

        run_script([], exchange, "", 60, shot, lambda a, log: emulator, clock, clock.sleep)

        emulator.send.assert_any_call("SCREENSHOT", str(shot.resolve()))

    def test_a_script_that_never_ends_times_out_with_a_screenshot(self, clock, exchange):
        emulator = self._emulator(exchange, finish_after=None)

        with pytest.raises(SystemExit, match="did not finish within 30 s"):
            run_script([], exchange, "", 30, None, lambda a, log: emulator, clock, clock.sleep)

        emulator.send.assert_any_call("SCREENSHOT", str((exchange / "timeout.png").resolve()))
        emulator.stop.assert_called_once()

    def test_an_emulator_that_is_not_this_runs_is_refused(self, clock, exchange):
        emulator = self._emulator(exchange, finish_after=1)
        emulator.send.side_effect = lambda *f, **k: ["OK", "unit0=dir:/somewhere/else"]

        with pytest.raises(SystemExit, match="is not this run's"):
            run_script([], exchange, "", 30, None, lambda a, log: emulator, clock, clock.sleep)

        assert emulator.socket is None  # so stop() sends it no QUIT
        emulator.stop.assert_called_once()
