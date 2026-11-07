"""Run an AmigaDOS script once on an emulated machine, with no person present.

The machine boots from a system directory (see system.py). Its
S:User-Startup ends with a block amiga-env owns:

    ;BEGIN amiga-env
    Assign >NIL: AmigaEnv: EXISTS
    If NOT WARN
      Run >NIL: Execute AmigaEnv:boot
    EndIf
    ;END amiga-env

so it does nothing unless a volume named AmigaEnv is mounted. For a run,
amiga-env mounts a fresh host folder as AmigaEnv: holding the script. The
`boot` wrapper starts ARexx, whose `run.rexx` runs the script in a shell of
its own with its output in AmigaEnv:script.log, then writes the script's
return code to AmigaEnv:done. As in any shell script, a command that fails
(return code 10 or more) stops the script. The host waits for `done`,
can take a screenshot through the control socket, and sends QUIT.

Amiberry falls back to another socket when /tmp/amiberry.sock is taken, and
prints the one it chose ("IPC: Listening on PATH") when run with --log, so a
run talks only to the emulator it started, and never to one a person has
open.
"""

import re
import socket
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from . import amiberry, home

EXCHANGE_VOLUME = "AmigaEnv"
EXCHANGE_DEVICE = "AENV"
HOOK_BEGIN = ";BEGIN amiga-env"
HOOK_END = ";END amiga-env"
HOOK = f"""{HOOK_BEGIN}
Assign >NIL: {EXCHANGE_VOLUME}: EXISTS
If NOT WARN
  Run >NIL: Execute {EXCHANGE_VOLUME}:boot
EndIf
{HOOK_END}
"""
USER_STARTUP = "S/User-Startup"

NOT_BOOTABLE = -128
LISTENING = re.compile(r"IPC: Listening on (\S+)")


@dataclass(frozen=True)
class Volume:
    device: str
    label: str
    path: Path
    bootpri: int = NOT_BOOTABLE


@dataclass(frozen=True)
class Outcome:
    return_code: int
    log: str
    seconds: float


def with_hook(user_startup: str) -> str:
    """S:User-Startup text that ends with the amiga-env block, exactly once."""
    lines, kept, inside = user_startup.splitlines(keepends=True), [], False
    for line in lines:
        if line.rstrip() == HOOK_BEGIN:
            inside = True
        elif inside and line.rstrip() == HOOK_END:
            inside = False
        elif not inside:
            kept.append(line)
    body = "".join(kept)
    if body and not body.endswith("\n"):
        body += "\n"
    return body + HOOK


def boot_script() -> str:
    """AmigaEnv:boot: start ARexx and hand over to AmigaEnv:run.rexx."""
    return (
        "; Written by amiga-env for one run.\n"
        "FailAt 21\n"
        "RexxMast >NIL:\n"
        "WaitForPort REXX\n"
        f"rx {EXCHANGE_VOLUME}:run.rexx\n"
    )


def run_rexx() -> str:
    """Run the script in a shell of its own, then write its return code.

    A script Executed in the boot shell would share its FailAt, and a
    failing command ends every script that shell is running, so the done
    marker would never be written. ARexx's `address command` runs the script
    in a new shell and returns its code.
    """
    return (
        "/* Written by amiga-env for one run. */\n"
        f"address command 'Execute {EXCHANGE_VOLUME}:script >{EXCHANGE_VOLUME}:script.log'\n"
        "code = rc\n"
        f"if open(done, '{EXCHANGE_VOLUME}:done', 'W') then do\n"
        "  call writeln(done, code)\n"
        "  call close(done)\n"
        "end\n"
    )


def filesystem_setting(volume: Volume) -> str:
    """The Amiberry setting that mounts a host folder as an Amiga volume."""
    path = str(volume.path)
    if "," in path:
        raise SystemExit(f"Amiberry cannot mount a folder whose path has a comma: {path}")
    return f"filesystem2=rw,{volume.device}:{volume.label}:{path},{volume.bootpri}"


def volume_args(volumes: Sequence[Volume]) -> list[str]:
    args = []
    for volume in volumes:
        args += ["-s", filesystem_setting(volume)]
    return args


def socket_path(log: str) -> str | None:
    """The control socket Amiberry chose, from its --log output."""
    found = LISTENING.search(log)
    return found.group(1) if found else None


def headless(env: dict[str, str]) -> dict[str, str]:
    """No window and no sound, unless the caller's environment chooses SDL drivers.

    With SDL's dummy drivers Amiberry still emulates the display, so the
    socket's SCREENSHOT works.
    """
    return {"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"} | env


def prepare_exchange(folder: Path, script: str) -> None:
    """An empty AmigaEnv folder holding the script and its wrapper."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.iterdir():
        if old.is_file():
            old.unlink()
    (folder / "script").write_text(script)
    (folder / "boot").write_text(boot_script())
    (folder / "run.rexx").write_text(run_rexx())


def read_done(folder: Path) -> int | None:
    """The script's return code once AmigaEnv:done is complete, else None."""
    done = folder / "done"
    if not done.is_file():
        return None
    text = done.read_text(errors="replace").strip()
    return int(text) if text.lstrip("-").isdigit() else None


class Emulator:
    """Gateway: one Amiberry process this run started, and its control socket."""

    def __init__(self, args: Sequence[str], log_path: Path):
        home.prepare()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path = log_path
        self._log = log_path.open("w")
        self._process = subprocess.Popen(
            [str(amiberry.installed_binary()), "--log", *args],
            env=headless(home.environment()),
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        self.socket: str | None = None

    def running(self) -> bool:
        return self._process.poll() is None

    def log(self) -> str:
        return self.log_path.read_text(errors="replace")

    def send(self, *fields: str, timeout: float = 10.0) -> list[str]:
        if self.socket is None:
            raise SystemExit("the emulator has no control socket yet")
        with socket.socket(socket.AF_UNIX) as conn:
            conn.settimeout(timeout)
            conn.connect(self.socket)
            conn.sendall(("\t".join(fields) + "\n").encode())
            reply = b""
            while not reply.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                reply += chunk
        return reply.decode(errors="replace").rstrip("\n").split("\t")

    def stop(self, wait: float = 30.0) -> None:
        """QUIT through the socket; end the process only if that fails."""
        if self.running() and self.socket is not None:
            try:
                self.send("QUIT")
            except OSError:
                pass
        try:
            self._process.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            self._process.wait(timeout=wait)
        self._log.close()


def run_script(
    args: Sequence[str],
    exchange: Path,
    script: str,
    timeout: float,
    screenshot: Path | None = None,
    launch: Callable[[Sequence[str], Path], Emulator] = Emulator,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Outcome:
    """Boot with `args` plus AmigaEnv:, run `script` once, and quit.

    `args` must boot a system whose S:User-Startup holds the amiga-env block.
    Raises SystemExit when the script does not finish within `timeout`; a
    screenshot of that moment is left in the exchange folder.
    """
    prepare_exchange(exchange, script)
    mount = Volume(EXCHANGE_DEVICE, EXCHANGE_VOLUME, exchange.resolve())
    started = now()
    emulator = launch([*args, *volume_args([mount]), "-G"], exchange / "amiberry.log")
    try:
        _find_socket(emulator, exchange, started + 60, now, sleep)
        while (code := read_done(exchange)) is None:
            if not emulator.running():
                raise SystemExit(
                    f"Amiberry exited before the script finished; see {emulator.log_path}"
                )
            if now() - started > timeout:
                emulator.send("SCREENSHOT", str((exchange / "timeout.png").resolve()))
                raise SystemExit(
                    f"the script did not finish within {timeout:g} s; "
                    f"see {exchange / 'timeout.png'} and {exchange / 'script.log'}"
                )
            sleep(1.0)
        if screenshot is not None:
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            reply = emulator.send("SCREENSHOT", str(screenshot.resolve()))
            if reply[0] != "OK":
                raise SystemExit(f"SCREENSHOT failed: {' '.join(reply)}")
    finally:
        emulator.stop()
    log = exchange / "script.log"
    return Outcome(code, log.read_text(errors="replace") if log.exists() else "", now() - started)


def _find_socket(
    emulator: Emulator,
    exchange: Path,
    deadline: float,
    now: Callable[[], float],
    sleep: Callable[[float], None],
) -> None:
    """Wait for this emulator's socket, and check it reports our AmigaEnv folder."""
    while emulator.socket is None:
        if now() > deadline or not emulator.running():
            raise SystemExit(f"Amiberry opened no control socket; see {emulator.log_path}")
        emulator.socket = socket_path(emulator.log())
        sleep(0.5)
    while True:
        try:
            reply = emulator.send("LIST_HARDDRIVES")
            break
        except OSError:
            if now() > deadline:
                raise
            sleep(0.5)
    if str(exchange.resolve()) not in "\t".join(reply):
        # Never QUIT an emulator this run did not start: forget the socket,
        # so stop() ends only the process this run launched.
        theirs, emulator.socket = emulator.socket, None
        raise SystemExit(f"the emulator on {theirs} is not this run's: {reply}")
