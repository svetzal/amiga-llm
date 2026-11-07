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
    "vblanks",
    "vblank_hz",
    "screen_at",
    "chosen_at",
    "ended_at",
    "loaded_at",
    "gold_at",
    "playing_at",
    "first_note_at",
    "first_note_ms",
    "starts",
    "rotated",
    "next",
    "rotate_at",
    "preload_frames",
    "scores_bytes",
    "filter_keys",
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
    vblanks: int  # vertical blanks since the program started; the times below are counts of it
    vblank_hz: int
    screen_at: int
    chosen_at: int  # the task took the choice (or the rotation's alarm)
    ended_at: int  # the piece before was ended and given back
    loaded_at: int  # the chosen score was ready
    gold_at: int  # its line was gold
    playing_at: int  # its timer started: the piece's millisecond 0
    first_note_at: int
    first_note_ms: int  # the piece's millisecond of its first note
    starts: int
    rotated: int  # pieces the rotation started
    next: int  # the piece the rotation plays next
    rotate_at: int  # when, 0xFFFFFFFF while it waits for a choice
    preload_frames: int  # vertical blanks loading every score at the start
    scores_bytes: int
    filter_keys: int  # presses of F, each switching the A500's audio filter


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


def latency_report(status: Status) -> dict:
    """Milliseconds from the task taking a choice to each step of the piece starting.

    The player stamps each step with its vertical blank count, so a figure
    is good to one frame (1/60 s on NTSC). A step that happened before the
    choice was taken (none in a run that waited for it) is left out.
    """
    hz = status.vblank_hz or 60
    steps = {
        "previous_piece_ended": status.ended_at,
        "score_ready": status.loaded_at,
        "line_gold": status.gold_at,
        "timer_started": status.playing_at,
        "first_note": status.first_note_at,
    }
    found: dict = {
        f"{step}_ms": round((at - status.chosen_at) * 1000 / hz)
        for step, at in steps.items()
        if at and at >= status.chosen_at
    }
    if status.ended_at > status.playing_at:  # that was this piece's own end
        found.pop("previous_piece_ended_ms", None)
    return found | {
        "first_note_in_the_score_ms": status.first_note_ms,
        "frame_ms": round(1000 / hz, 1),
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
    (the test build's log holds 251 s, so a longer piece's is the model's first 251 s)."""
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


def require_floppy(floppy: Path) -> None:
    """SystemExit unless the disk exists: Amiberry starts without a missing floppy, and
    the run then fails late, at the socket's floppy check."""
    if not floppy.is_file():
        raise SystemExit(f"no floppy at {floppy}; run `amiga-env piano-disk` first")


class Choice(NamedTuple):
    """A piece to choose on the player's screen."""

    name: str
    key: str  # its key
    model_log: Path  # the model's voice log in the player's layout
    line: tuple[int, int]  # a point on its line, to click
    index: int = 0  # its place in the list, from 0


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
    realtime: bool = False,
) -> dict:
    """Boot `floppy`, choose each piece in turn, then quit; record each.

    Without `audio` or `realtime` the emulator runs in warp. With `click` a
    piece is chosen by clicking its line, else by its key.
    With `switch_after_ms` each piece but the last is played only that long,
    and the next is chosen while it plays. With `scopes`, screenshots taken
    while a piece plays are checked for scopes caught half drawn.
    """
    require_floppy(floppy)
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
        "warp": not (audio or realtime),
        "chosen_by": "click" if click else "key",
        "pieces": {},
    }
    try:
        amiga.connect(floppy.resolve())
        found["floppy_speed"] = " ".join(amiga.send("GET_FLOPPY_SPEED")[1:])
        if found["warp"]:
            amiga.send("SET_WARP", "1")
        status = _wait_for(amiga, lambda s: s.state in (MENU, PLAYING, ENDED, FAILED), timeout)
        if status.state not in (MENU, PLAYING):  # the rotation may have started piece 1
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
                out / f"{name}-{choice.name}",
                _Options(log, switch, click, scopes, timeout, found["warp"]),
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
    warp: bool = False


def started(status: Status, starts_before: int, index: int) -> bool:
    """Whether piece `index` has started since `starts_before` pieces had."""
    return status.starts > starts_before and status.piece == index


def has_ended(status: Status, serial: int) -> bool:
    """Whether the piece that was the `serial`th to start (from 1) has ended."""
    return status.played >= serial


def _play(amiga: Amiga, choice: Choice, stem: Path, options: _Options) -> dict:
    """Choose a piece, watch it play, and record it when it ends.

    The piece is followed by its place among the pieces started, so a piece
    the rotation starts by itself before or after it is not taken for it.
    With `switch_after_ms` it is left playing after that long: the next
    choice stops it. Its log is then read as far as it has got. In warp, a
    piece that ends is read with warp off, so the rotation's next piece
    cannot overwrite its log first.
    """
    log, switch_after_ms, click, scopes, timeout, _ = options
    found: dict = {"key": choice.key}
    before = read_status(amiga).starts
    if click:
        window = read_status(amiga).window
        found["clicked_at"] = amiga.click(window, choice.line)
        time.sleep(1.0)
        amiga.screenshot(Path(f"{stem}-clicked.png"))
    else:
        amiga.press(raw_key(choice.key))
    status = _wait_for(amiga, lambda s: s.state == FAILED or started(s, before, choice.index), 120)
    serial = status.starts
    first = Path(f"{stem}-playing.png")
    second = Path(f"{stem}-playing-2.png")
    first_ms = None
    while not has_ended(status, serial):
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
    switched = not has_ended(status, serial)
    warp = options.warp and not switched
    if warp:
        amiga.send("SET_WARP", "0")
    if not switched:
        status = read_status(amiga)
        if status.starts != serial:
            raise SystemExit(f"the next piece started before {choice.name}'s log was read")
        amiga.screenshot(Path(f"{stem}-done.png"))
    found |= {
        "status": status._asdict(),
        "left_playing_for_the_next_choice": switched,
        "highlighted_line": status.highlight if switched else None,
        "latency": latency_report(status),
        "cpu": cpu_report(status),
        "scopes": scope_report(status),
        "memory_free_while_playing": {"chip": status.chip_free, "other": status.other_free},
        "score": {"address": hex(status.score), "bytes": status.score_bytes},
    }
    if log:
        machine_log = read_block(amiga.read_long, status.log_base, status.log_bytes)
        Path(f"{stem}.log").write_bytes(machine_log)
        found["log"] = compare_logs(choice.model_log.read_bytes(), machine_log)
    if warp:
        amiga.send("SET_WARP", "1")
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


def seconds(frames: int, hz: int) -> float:
    """Vertical blanks as seconds, to the hundredth."""
    return round(frames / (hz or 60), 2)


SPACE_KEY = 0x40  # Amiga raw key code: stops the piece and holds the rotation
HELD = 0xFFFFFFFF  # rotate_at while the rotation waits for a choice; highlight with no line


class _Rotation:
    """One run of the unattended screen: the emulator, what it found, its screenshots."""

    def __init__(self, amiga: Amiga, choices: Sequence[Choice], out: Path, name: str):
        self.amiga, self.choices, self.out, self.name = amiga, choices, out, name
        self.screen_wall = 0.0
        self.found: dict = {"steps": {}, "screenshots": []}

    def status(self) -> Status:
        return read_status(self.amiga)

    def wait(self, ready: Callable[[Status], bool], timeout: float) -> Status:
        """Poll four times a second until `ready`."""
        deadline = time.monotonic() + timeout
        while True:
            status = self.status()
            if status.magic == MAGIC and ready(status):
                return status
            if status.state == FAILED:
                raise SystemExit(f"the player failed: {status}")
            if time.monotonic() > deadline:
                raise SystemExit(f"not there within {timeout:g} s: {status}")
            time.sleep(0.25)

    def warp(self, on: bool) -> None:
        self.amiga.send("SET_WARP", "1" if on else "0")

    def shot(self, label: str) -> None:
        status = self.status()
        path = self.out / f"{self.name}-{label}.png"
        self.amiga.screenshot(path)
        self.found["screenshots"].append(
            {
                "file": path.name,
                "wall_s_after_screen": round(time.monotonic() - self.screen_wall, 1),
                "emulated_s_after_screen": seconds(
                    status.vblanks - status.screen_at, status.vblank_hz
                ),
                "piece": status.piece if status.state == PLAYING else None,
                "highlight": None if status.highlight == HELD else status.highlight,
            }
        )

    def read_log(self, label: str) -> dict:
        """The playing (or just ended) piece's voice log against the model's."""
        status = self.status()
        choice = self.choices[status.piece]
        machine_log = read_block(self.amiga.read_long, status.log_base, status.log_bytes)
        (self.out / f"{self.name}-{label}.log").write_bytes(machine_log)
        return {"piece": choice.name, **compare_logs(choice.model_log.read_bytes(), machine_log)}

    def after_end(self, serial: int, label: str) -> tuple[Status, dict]:
        """Warp until the `serial`th piece ends, then read its log with warp off."""
        self.warp(True)
        # The player counts the end first and stamps it last, then waits (MENU).
        self.wait(lambda s: has_ended(s, serial) and (s.state == MENU or s.starts > serial), 900)
        self.warp(False)
        ended = self.status()
        if ended.starts != serial:
            raise SystemExit("the rotation started the next piece before the log was read")
        return ended, self.read_log(label)

    def next_by_rotation(self, ended: Status) -> dict:
        """Warp through the gap until the rotation starts the next piece; what it did."""
        self.warp(True)
        status = self.wait(lambda s: s.starts > ended.starts, 120)
        self.warp(False)
        hz = status.vblank_hz
        return {
            "piece": self.choices[status.piece].name,
            "started_by_rotation": status.rotated > ended.rotated,
            "gap_s": seconds(status.chosen_at - ended.ended_at, hz),
            "line_gold": status.highlight == status.piece,
            "latency": latency_report(status),
        }


def run_rotation(
    machine: profile.Machine, floppy: Path, choices: Sequence[Choice], out: Path, name: str
) -> dict:
    """Boot the test build and check the rotation as someone who walks away would see it.

    Real time until piece 1 starts by itself; warp after that, off whenever a
    log is read or a key or click is sent. The steps: piece 1 after the quiet
    start; piece 2 after the gap; a click on the last piece mid-piece; the
    wrap to piece 1 after the last; Space; quiet held; a key; the next by
    rotation from that key's piece; Q.
    """
    require_floppy(floppy)
    out.mkdir(parents=True, exist_ok=True)
    amiga = Amiga(
        profile.machine_args(machine, floppy.resolve()),
        out / f"{name}.amiberry.log",
        {"SDL_AUDIODRIVER": "dummy"},
    )
    run = _Rotation(amiga, choices, out, name)
    steps = run.found["steps"]
    try:
        amiga.connect(floppy.resolve())
        _rotation_steps(run, steps)
    finally:
        amiga.stop()
    run.found["floppy"] = str(floppy)
    (out / f"{name}.json").write_text(json.dumps(run.found, indent=2) + "\n")
    return run.found


def _rotation_steps(run: _Rotation, steps: dict) -> None:
    last = len(run.choices) - 1
    menu = run.wait(lambda s: s.state in (MENU, PLAYING), 300)
    run.screen_wall = time.monotonic()
    hz = menu.vblank_hz
    for at in (1, 8, 14):
        time.sleep(max(0.0, run.screen_wall + at - time.monotonic()))
        run.shot(f"quiet-{at:02d}s")
    first = run.wait(lambda s: s.starts >= 1, 60)
    wall = round(time.monotonic() - run.screen_wall, 1)
    time.sleep(2)
    run.shot("piece-1-by-itself")
    steps["first_by_itself"] = {
        "piece": run.choices[first.piece].name,
        "started_by_rotation": first.rotated == 1,
        "emulated_s_from_screen_to_choice": seconds(first.chosen_at - first.screen_at, hz),
        "emulated_s_from_screen_to_timer": seconds(first.playing_at - first.screen_at, hz),
        "wall_s_seen_by_the_host": wall,
        "warp": False,
    }
    ended, steps["first_log"] = run.after_end(1, "1-rotation")
    steps["second_by_rotation"] = run.next_by_rotation(ended)
    run.shot("piece-2-by-rotation")

    run.warp(True)
    run.wait(lambda s: s.ms >= 20_000, 300)
    run.warp(False)
    steps["second_log_before_the_click"] = run.read_log("2-rotation")
    before = run.status()
    run.amiga.click(before.window, run.choices[last].line)
    clicked = run.wait(lambda s: started(s, before.starts, last), 30)
    run.shot("clicked-last")
    steps["click_mid_piece"] = {
        "piece": run.choices[clicked.piece].name,
        "previous_stopped": clicked.played == before.starts,
        "line_gold": clicked.highlight == last,
        "rotation_next": run.choices[clicked.next].name,
        "latency": latency_report(clicked),
    }
    ended, steps["last_log"] = run.after_end(clicked.starts, "last-chosen")
    steps["wrap_to_first"] = run.next_by_rotation(ended)
    run.shot("wrap-to-1")

    run.warp(True)
    run.wait(lambda s: s.ms >= 10_000, 300)
    run.warp(False)
    steps["wrap_log_before_space"] = run.read_log("1-wrapped")
    before = run.status()
    run.amiga.press(SPACE_KEY)
    held = run.wait(lambda s: s.state == MENU and s.played == before.starts, 30)
    run.shot("space")
    run.warp(True)
    quiet = run.wait(lambda s: s.vblanks >= held.vblanks + 60 * hz, 120)
    run.warp(False)
    run.shot("held-60s")
    steps["space"] = {
        "piece_stopped": held.stopped == 1,
        "rotation_held": held.rotate_at == HELD,
        "no_line_gold": held.highlight == HELD,
        "starts_after_60_quiet_s": quiet.starts - held.starts,
    }

    choice = run.choices[2]
    run.amiga.press(raw_key(choice.key))
    chosen = run.wait(lambda s: started(s, held.starts, choice.index), 30)
    steps["key_after_space"] = {
        "piece": choice.name,
        "rotation_next": run.choices[chosen.next].name,
        "latency": latency_report(chosen),
    }
    ended, steps["key_log"] = run.after_end(chosen.starts, "3-chosen")
    steps["next_after_the_key"] = run.next_by_rotation(ended)
    run.shot("after-key")
    run.amiga.press(raw_key("Q"))
    end = run.wait(lambda s: s.state in (ENDED, FAILED), 60)
    run.shot("end")
    steps["quit"] = {"ended": end.state == ENDED}
