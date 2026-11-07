"""Run the 68000 piano player on the emulated A500 and check it against the model.

One run boots the piano floppy (see disk.py) on a machine from amiga.toml
with no window and uses its screen as a person would: it presses a piece's
key (Amiberry's SEND_KEY, with Amiga raw key codes) or clicks its line
(SEND_MOUSE, steered by the pointer position the player's window holds),
waits for the piece to end or chooses the next one while it plays, and so
on, then presses Q. It watches the status block the player
keeps at $100 through Amiberry's control socket (READ_MEM). With the test
build it reads each piece's voice log back the same way and compares it
byte for byte with the model's (`<out>/m68k/<piece>.log`). With `audio`,
Amiberry runs at the emulated machine's own speed and SDL's disk audio
driver writes what Amiberry plays (16-bit stereo at 44.1 kHz), which
becomes a WAV; without it the run goes as fast as the host allows (warp).

Everything a run finds goes to `<out>/<name>.json`, with screenshots and
the WAV beside it.
"""

import json
import struct
import time
import wave
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

import numpy as np

from .. import profile, session
from . import m68k
from .disk import RAW_KEYS

STATUS = 0x100
MAGIC = 0x5049414E  # 'PIAN'
STATUS_FIELDS = (
    "magic",
    "state",
    "log_base",
    "log_bytes",
    "samples",
    "copied",
    "total_e",
    "ms",
    "max_frame_e",
    "frames",
    "max_ms_e",
    "piece",
    "entry_e",
    "played",
    "stopped",
    "pieces",
    "score",
    "score_bytes",
    "chip_free",
    "other_free",
    "key",
    "keys",
    "window",
    "clicks",
    "click_xy",
    "scope_frames",
    "scope_e",
    "scope_max_e",
    "highlight",
    "screen_chip",
    "draw_e",
    "draw_max_e",
)
# Window fields (struct Window): the pointer's position in the window.
WINDOW_MOUSE_Y, WINDOW_MOUSE_X = 12, 14
MOUSE_GAIN = 4  # SEND_MOUSE counts a pixel of pointer movement takes (about 4.2 measured)
MOUSE_STEP = 120  # the largest SEND_MOUSE move sent at once
PLAYING, ENDED, MENU, FAILED = 1, 2, 3, 0xFFFFFFFF
E_CLOCK_HZ = 715_909  # NTSC
TIMER_PERIOD = 716  # E-clock ticks between the player's interrupts
AUDIO_RATE = 44_100
# What a real A500 does and Amiberry does not by default: full stereo separation.
AUDIO_SETTINGS = ("sound_stereo_separation=10", "floppy0sound=0")
# SDL's disk driver file trails the emulation: a run that quit as soon as the
# player finished lost the last 5 s of the nocturne. Keep playing silence a while.
AUDIO_TAIL_S = 15.0


class Status(NamedTuple):
    magic: int
    state: int
    log_base: int
    log_bytes: int
    samples: int
    copied: int
    total_e: int
    ms: int
    max_frame_e: int
    frames: int
    max_ms_e: int
    piece: int
    entry_e: int
    played: int
    stopped: int
    pieces: int
    score: int
    score_bytes: int
    chip_free: int
    other_free: int
    key: int
    keys: int
    window: int
    clicks: int
    click_xy: int
    scope_frames: int
    scope_e: int
    scope_max_e: int
    highlight: int
    screen_chip: int
    draw_e: int
    draw_max_e: int


def parse_status(longs: Sequence[int]) -> Status:
    return Status(*longs[: len(STATUS_FIELDS)])


def cpu_report(status: Status) -> dict:
    """The player's share of the 68000, from its own E-clock measurements.

    Every figure counts from the CIA timer running out, so it includes how
    long exec and ciab.resource took to call the player.
    """
    elapsed_e = max(status.ms, 1) * TIMER_PERIOD
    frame_e = E_CLOCK_HZ / 60
    return {
        "frames": status.frames,
        "milliseconds": status.ms,
        "percent_of_cpu": round(100 * status.total_e / elapsed_e, 1),
        "average_e_per_frame": round(status.total_e / max(status.frames, 1)),
        "worst_e_in_a_frame": status.max_frame_e,
        "worst_frame_percent": round(100 * status.max_frame_e / frame_e, 1),
        "worst_e_in_a_millisecond": status.max_ms_e,
        "dispatch_percent_of_cpu": round(100 * status.entry_e / elapsed_e, 1),
        "dispatch_e_per_interrupt": round(status.entry_e / max(status.ms, 1), 1),
    }


def scope_report(status: Status) -> dict:
    """The scopes' rate and share of the 68000, from the player's own measurements.

    A scope frame is two parts: drawing the last traces (taking back the
    old points and plotting the new, `draw_e`) and making the next
    (`scope_e`). Neither counts the player's interrupts (measured
    separately) or the waits for the beam, but both include the system's
    own interrupts (VBlank, keyboard).
    """
    elapsed_e = max(status.ms, 1) * TIMER_PERIOD
    frame_e = E_CLOCK_HZ / 60
    frames = max(status.scope_frames, 1)
    work_e = status.scope_e + status.draw_e
    scope_share = work_e / elapsed_e
    player_share = status.total_e / elapsed_e
    return {
        "scope_frames": status.scope_frames,
        "scope_frames_per_second": round(status.scope_frames * 1000 / max(status.ms, 1), 1),
        "average_e_per_scope_frame": round(work_e / frames),
        "average_e_drawing": round(status.draw_e / frames),
        "worst_e_drawing": status.draw_max_e,
        "average_e_making_traces": round(status.scope_e / frames),
        "worst_e_making_traces": status.scope_max_e,
        "scope_percent_of_cpu": round(100 * scope_share, 1),
        "player_e_per_frame": round(player_share * frame_e),
        "scope_e_per_frame": round(scope_share * frame_e),
        "player_and_scopes_percent_of_cpu": round(100 * (player_share + scope_share), 1),
    }


class Scope(NamedTuple):
    left: int  # screen columns
    width: int
    colour: tuple[int, int, int]  # 8-bit RGB of its trace


# Where Amiberry 8.5.0's SCREENSHOT puts the A500's 320x200 NTSC screen with
# the default window: each lowres pixel is 2x2, the first at (60, 48).
SHOT_ORIGIN = (60, 48)
SHOT_SCALE = 2


def scope_coverage(shot: np.ndarray, scopes: Sequence[Scope], rows: tuple[int, int]) -> list[float]:
    """For each scope, the share of its columns that show a trace pixel within `rows`
    (screen rows, end exclusive) in a screenshot (height x width x 3). A scope the
    beam caught half drawn has columns with none."""
    x0, y0 = SHOT_ORIGIN
    band = shot[y0 + SHOT_SCALE * rows[0] : y0 + SHOT_SCALE * rows[1]].astype(int)
    found = []
    for scope in scopes:
        columns = [x0 + SHOT_SCALE * x for x in range(scope.left, scope.left + scope.width)]
        near = np.abs(band[:, columns] - np.array(scope.colour)).sum(axis=2) < 30
        found.append(round(float(near.any(axis=0).mean()), 2))
    return found


def pointer_move(at: tuple[int, int], target: tuple[int, int]) -> tuple[int, int] | None:
    """The SEND_MOUSE move that brings the pointer from `at` towards `target`,
    or None when it is within a pixel of it."""
    dx, dy = target[0] - at[0], target[1] - at[1]
    if abs(dx) <= 1 and abs(dy) <= 1:
        return None
    return (
        max(-MOUSE_STEP, min(MOUSE_STEP, dx * MOUSE_GAIN)),
        max(-MOUSE_STEP, min(MOUSE_STEP, dy * MOUSE_GAIN)),
    )


def raw_key(key: str) -> int:
    """The Amiga raw key code of a menu key."""
    try:
        return RAW_KEYS[key.upper()]
    except KeyError:
        raise SystemExit(f"no raw key code for {key!r}") from None


def compare_logs(model: bytes, machine: bytes) -> dict:
    """Whether the machine's log is the model's; `same_ticks` compares the ticks both have
    (the player's log holds 277 s, so a longer piece's is the model's first 277 s)."""
    ticks = len(machine) // m68k.LOG_BYTES_PER_TICK
    difference = m68k.first_difference(model, machine)
    return {
        "model_ticks": len(model) // m68k.LOG_BYTES_PER_TICK,
        "machine_ticks": ticks,
        "identical": model == machine,
        "same_ticks": difference is None,
        "first_difference": difference._asdict() if difference else None,
    }


def wav_from_raw(raw: bytes, path: Path, rate: int = AUDIO_RATE) -> None:
    """SDL's disk driver output (signed 16-bit little-endian stereo) as a WAV."""
    usable = len(raw) - len(raw) % 4
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(raw[:usable])


def trim_lead(raw: bytes, lead_s: float = 1.0, threshold: int = 64) -> tuple[bytes, float]:
    """Drop the silence of the boot before the music, keeping `lead_s` of it.

    Returns the audio and the seconds dropped. A frame is silent when both
    channels are within `threshold` of zero.
    """
    usable = len(raw) - len(raw) % 4
    frames = np.abs(np.frombuffer(raw[:usable], dtype="<i2").reshape(-1, 2)).max(axis=1)
    loud = np.flatnonzero(frames > threshold)
    first = int(loud[0]) if len(loud) else len(frames)
    start = max(0, first - round(lead_s * AUDIO_RATE))
    return raw[start * 4 : usable], start / AUDIO_RATE


def read_block(read_long: Callable[[int], int], address: int, size: int) -> bytes:
    """`size` bytes from the Amiga's memory, a long at a time."""
    longs = [read_long(address + offset) for offset in range(0, size + 3 & ~3, 4)]
    return struct.pack(f">{len(longs)}L", *longs)[:size]


class Amiga:
    """Gateway: an emulator this run started, driven through its control socket."""

    def __init__(self, args: Sequence[str], log_path: Path, env: dict[str, str]):
        self._emulator = session.Emulator([*args, "-G"], log_path, env)

    def connect(self, floppy: Path, timeout: float = 60.0) -> None:
        """Find this emulator's socket and check that it booted our floppy."""
        emulator, deadline = self._emulator, time.monotonic() + timeout
        while emulator.socket is None:
            if time.monotonic() > deadline or not emulator.running():
                raise SystemExit(f"Amiberry opened no control socket; see {emulator.log_path}")
            emulator.socket = session.socket_path(emulator.log())
            time.sleep(0.5)
        while True:
            try:
                reply = emulator.send("GET_STATUS")
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        if f"Floppy0={floppy}" not in reply:
            theirs, emulator.socket = emulator.socket, None
            raise SystemExit(f"the emulator on {theirs} is not this run's: {reply}")

    def send(self, *fields: str) -> list[str]:
        return self._emulator.send(*fields)

    def read_long(self, address: int) -> int:
        reply = self.send("READ_MEM", hex(address), "4")
        if reply[0] != "OK":
            raise SystemExit(f"READ_MEM {address:#x} failed: {' '.join(reply)}")
        return int(reply[1])

    def press(self, code: int) -> None:
        """Press and release a key, by its Amiga raw key code."""
        for state in ("1", "0"):
            reply = self.send("SEND_KEY", str(code), state)
            if reply[0] != "OK":
                raise SystemExit(f"SEND_KEY {code:#x} failed: {' '.join(reply)}")
            time.sleep(0.1)

    def read_word(self, address: int) -> int:
        reply = self.send("READ_MEM", hex(address), "2")
        if reply[0] != "OK":
            raise SystemExit(f"READ_MEM {address:#x} failed: {' '.join(reply)}")
        return int(reply[1])

    def mouse(self, dx: int, dy: int, buttons: int) -> None:
        reply = self.send("SEND_MOUSE", str(dx), str(dy), str(buttons))
        if reply[0] != "OK":
            raise SystemExit(f"SEND_MOUSE failed: {' '.join(reply)}")

    def click(self, window: int, target: tuple[int, int], tries: int = 30) -> tuple[int, int]:
        """Move the pointer to `target` (screen pixels) and press the left button.

        Amiberry's SEND_MOUSE moves are relative and Intuition scales them, so
        the pointer is steered by reading where it is (the window's MouseX
        and MouseY) after each move. Returns where it clicked.
        """
        for _ in range(tries):
            at = (
                self.read_word(window + WINDOW_MOUSE_X),
                self.read_word(window + WINDOW_MOUSE_Y),
            )
            move = pointer_move(at, target)
            if move is None:
                break
            self.mouse(*move, 0)
            time.sleep(0.2)
        else:
            raise SystemExit(f"the pointer did not reach {target}; it is at {at}")
        self.mouse(0, 0, 1)
        time.sleep(0.1)
        self.mouse(0, 0, 0)
        return at

    def screenshot_pixels(self, path: Path) -> np.ndarray:
        """A screenshot as RGB pixels (the PNG is kept at `path`)."""
        from PIL import Image

        self.screenshot(path)
        return np.asarray(Image.open(path).convert("RGB"))

    def screenshot(self, path: Path) -> None:
        reply = self.send("SCREENSHOT", str(path.resolve()))
        if reply[0] != "OK":
            raise SystemExit(f"SCREENSHOT failed: {' '.join(reply)}")

    def stop(self) -> None:
        self._emulator.stop()


class Choice(NamedTuple):
    """A piece to choose on the player's screen."""

    name: str
    key: str  # its key
    model_log: Path  # the model's voice log in the player's layout
    line: tuple[int, int]  # a point on its line, to click


def run_menu(
    machine: profile.Machine,
    floppy: Path,
    choices: Sequence[Choice],
    out: Path,
    name: str,
    log: bool,
    audio: bool,
    switch_after_ms: int | None = None,
    click: bool = False,
    scopes: "ScopeCheck | None" = None,
    timeout: float = 900.0,
) -> dict:
    """Boot `floppy`, choose each piece in turn, then quit; record each.

    With `click` a piece is chosen by clicking its line, else by its key.
    With `switch_after_ms` each piece but the last is played only that long,
    and the next is chosen while it plays. With `scopes`, screenshots taken
    while a piece plays are checked for scopes caught half drawn.
    """
    out.mkdir(parents=True, exist_ok=True)
    raw = out / f"{name}.raw"
    env = {"SDL_AUDIODRIVER": "dummy"}
    settings: list[str] = []
    if audio:
        raw.unlink(missing_ok=True)
        env = {"SDL_AUDIODRIVER": "disk", "SDL_AUDIO_DISK_OUTPUT_FILE": str(raw)}
        settings = [arg for setting in AUDIO_SETTINGS for arg in ("-s", setting)]
    amiga = Amiga(
        [*profile.machine_args(machine, floppy.resolve()), *settings],
        out / f"{name}.amiberry.log",
        env,
    )
    found: dict = {
        "floppy": str(floppy),
        "audio": audio,
        "warp": not audio,
        "chosen_by": "click" if click else "key",
        "pieces": {},
    }
    try:
        amiga.connect(floppy.resolve())
        if not audio:
            amiga.send("SET_WARP", "1")
        status = _wait_for(amiga, lambda s: s.state in (MENU, ENDED, FAILED), timeout)
        if status.state != MENU:
            raise SystemExit(f"the player did not reach its menu: {status}")
        amiga.screenshot(out / f"{name}-idle.png")
        found["menu_pieces"] = status.pieces
        found["chip_free_with_the_screen_open"] = status.screen_chip
        found["samples_in_chip"] = {
            "address": hex(status.samples),
            "how": "copied with AllocMem" if status.copied else "LoadSeg's chip hunk",
        }
        for number, choice in enumerate(choices, 1):
            switch = switch_after_ms if number < len(choices) else None
            found["pieces"][choice.name] = _play(
                amiga,
                choice,
                number,
                out / f"{name}-{choice.name}",
                _Options(log, switch, click, scopes, timeout),
            )
        amiga.press(raw_key("Q"))
        status = _wait_for(amiga, lambda s: s.state in (ENDED, FAILED), 60)
        amiga.screenshot(out / f"{name}-end.png")
        found["ended"] = status.state == ENDED
        if audio:
            time.sleep(AUDIO_TAIL_S)
    finally:
        amiga.stop()
    if audio and raw.exists():
        music, dropped = trim_lead(raw.read_bytes())
        wav_from_raw(music, out / f"{name}.wav")
        raw.unlink()
        found["wav"] = str(out / f"{name}.wav")
        found["wav_starts_after_s"] = round(dropped, 2)
    (out / f"{name}.json").write_text(json.dumps(found, indent=2) + "\n")
    return found


class ScopeCheck(NamedTuple):
    """Screenshots to check while a piece plays, and what to look for."""

    scopes: tuple[Scope, ...]
    rows: tuple[int, int]  # the band's screen rows, end exclusive
    extra_shots: int = 0  # more screenshots, 0.3 s apart, after the first


class _Options(NamedTuple):
    log: bool
    switch_after_ms: int | None
    click: bool
    scopes: ScopeCheck | None
    timeout: float


def _play(amiga: Amiga, choice: Choice, number: int, stem: Path, options: _Options) -> dict:
    """Choose a piece, watch it play, and record it when it ends.

    With `switch_after_ms` it is left playing after that long: the next
    choice stops it. Its log is then read as far as it has got.
    """
    log, switch_after_ms, click, scopes, timeout = options
    found: dict = {"key": choice.key}
    if click:
        window = read_status(amiga).window
        found["clicked_at"] = amiga.click(window, choice.line)
        time.sleep(1.0)
        amiga.screenshot(Path(f"{stem}-clicked.png"))
    else:
        amiga.press(raw_key(choice.key))
    status = _wait_for(
        amiga,
        lambda s: (
            s.state == FAILED
            or s.played >= number
            or (s.state == PLAYING and s.played == number - 1)
        ),
        120,
    )
    first = Path(f"{stem}-playing.png")
    second = Path(f"{stem}-playing-2.png")
    first_ms = None
    while status.played < number:
        if status.state == FAILED:
            raise SystemExit(f"the player failed during {choice.name}")
        if status.ms > 5000 and first_ms is None:
            shot = amiga.screenshot_pixels(first)
            first_ms = status.ms
            if scopes:
                found["scope_coverage"] = [scope_coverage(shot, scopes.scopes, scopes.rows)]
                found["scope_shots"] = _check_shots(amiga, stem, scopes)
        elif first_ms is not None and status.ms > first_ms + 1000 and not second.exists():
            shot = amiga.screenshot_pixels(second)
            if scopes:
                found["scope_coverage"].append(scope_coverage(shot, scopes.scopes, scopes.rows))
        if switch_after_ms is not None and status.ms >= switch_after_ms:
            break
        status = _wait_for(amiga, lambda s: True, timeout)
    switched = status.played < number
    if not switched:
        status = _wait_for(amiga, lambda s: s.state in (MENU, ENDED, FAILED), 60)
        amiga.screenshot(Path(f"{stem}-done.png"))
    found |= {
        "status": status._asdict(),
        "left_playing_for_the_next_choice": switched,
        "highlighted_line": status.highlight if switched else None,
        "cpu": cpu_report(status),
        "scopes": scope_report(status),
        "memory_free_while_playing": {"chip": status.chip_free, "other": status.other_free},
        "score": {"address": hex(status.score), "bytes": status.score_bytes},
    }
    if log:
        machine_log = read_block(amiga.read_long, status.log_base, status.log_bytes)
        Path(f"{stem}.log").write_bytes(machine_log)
        found["log"] = compare_logs(choice.model_log.read_bytes(), machine_log)
    return found


def _check_shots(amiga: Amiga, stem: Path, check: ScopeCheck) -> dict:
    """Take `extra_shots` screenshots and count those with every scope drawn whole
    (a trace pixel in 90% of its columns); keep the others' PNGs."""
    whole, kept = 0, []
    for n in range(check.extra_shots):
        path = Path(f"{stem}-scopes-{n:02d}.png")
        coverage = scope_coverage(amiga.screenshot_pixels(path), check.scopes, check.rows)
        if min(coverage) >= 0.9:
            whole += 1
            path.unlink()
        else:
            kept.append({"file": path.name, "coverage": coverage})
        time.sleep(0.3)
    return {"shots": check.extra_shots, "every_scope_whole": whole, "partial": kept}


def _wait_for(amiga: Amiga, ready: Callable[[Status], bool], timeout: float) -> Status:
    """Poll the status block once a second until `ready` says so."""
    started = time.monotonic()
    while True:
        time.sleep(1.0)
        status = read_status(amiga)
        if status.magic == MAGIC and ready(status):
            return status
        if time.monotonic() - started > timeout:
            raise SystemExit(f"the player did not get there within {timeout:g} s: {status}")


def read_status(amiga: Amiga) -> Status:
    return parse_status([amiga.read_long(STATUS + 4 * i) for i in range(len(STATUS_FIELDS))])
