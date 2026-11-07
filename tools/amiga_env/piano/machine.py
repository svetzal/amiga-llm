"""Run the 68000 piano player on the emulated A500 and check it against the model.

One run boots the piano floppy (see disk.py) on a machine from amiga.toml
with no window and uses its menu as a person would: it presses a piece's
key (Amiberry's SEND_KEY, with Amiga raw key codes), waits for the piece to
end, and so on, then presses Q. It watches the status block the player
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
)
PLAYING, ENDED, MENU, FAILED = 1, 2, 3, 0xFFFFFFFF
# Amiga raw key codes (the A500 keyboard's matrix), which SEND_KEY takes.
# Each row of letters and digits runs on from its first code.
RAW_KEYS = {
    key: first + offset
    for row, first in (
        ("1234567890", 0x01),
        ("QWERTYUIOP", 0x10),
        ("ASDFGHJKL", 0x20),
        ("ZXCVBNM", 0x31),
    )
    for offset, key in enumerate(row)
}
RETURN_KEY = 0x44
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

    def screenshot(self, path: Path) -> None:
        reply = self.send("SCREENSHOT", str(path.resolve()))
        if reply[0] != "OK":
            raise SystemExit(f"SCREENSHOT failed: {' '.join(reply)}")

    def stop(self) -> None:
        self._emulator.stop()


class Choice(NamedTuple):
    """A piece to choose from the menu."""

    name: str
    key: str  # its menu key
    model_log: Path  # the model's voice log in the player's layout


def run_menu(
    machine: profile.Machine,
    floppy: Path,
    choices: Sequence[Choice],
    out: Path,
    name: str,
    log: bool,
    audio: bool,
    stop_after_ms: int | None = None,
    timeout: float = 900.0,
) -> dict:
    """Boot `floppy`, choose each piece from the menu in turn, then quit; record each."""
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
    found: dict = {"floppy": str(floppy), "audio": audio, "warp": not audio, "pieces": {}}
    try:
        amiga.connect(floppy.resolve())
        if not audio:
            amiga.send("SET_WARP", "1")
        status = _wait_for(amiga, lambda s: s.state in (MENU, ENDED, FAILED), timeout)
        if status.state != MENU:
            raise SystemExit(f"the player did not reach its menu: {status}")
        amiga.screenshot(out / f"{name}-menu.png")
        found["menu_pieces"] = status.pieces
        found["samples_in_chip"] = {
            "address": hex(status.samples),
            "how": "copied with AllocMem" if status.copied else "LoadSeg's chip hunk",
        }
        for number, choice in enumerate(choices, 1):
            found["pieces"][choice.name] = _play(
                amiga, choice, number, out / f"{name}-{choice.name}", log, stop_after_ms, timeout
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


def _play(
    amiga: Amiga,
    choice: Choice,
    number: int,
    stem: Path,
    log: bool,
    stop_after_ms: int | None,
    timeout: float,
) -> dict:
    """Press a piece's key, watch it play, and record it when the menu is back."""
    amiga.press(raw_key(choice.key))
    status = _wait_for(amiga, lambda s: s.state in (PLAYING, FAILED) or s.played >= number, 120)
    shot = Path(f"{stem}-playing.png")
    while status.played < number:
        if status.state == FAILED:
            raise SystemExit(f"the player failed during {choice.name}")
        if status.ms > 5000 and not shot.exists():
            amiga.screenshot(shot)
        if stop_after_ms is not None and status.ms >= stop_after_ms:
            amiga.press(RETURN_KEY)
            stop_after_ms = None
        status = _wait_for(amiga, lambda s: True, timeout)
    status = _wait_for(amiga, lambda s: s.state in (MENU, ENDED, FAILED), 60)
    amiga.screenshot(Path(f"{stem}-done.png"))
    found = {
        "key": choice.key,
        "status": status._asdict(),
        "stopped_by_key": bool(status.stopped),
        "cpu": cpu_report(status),
        "memory_free_while_playing": {"chip": status.chip_free, "other": status.other_free},
        "score": {"address": hex(status.score), "bytes": status.score_bytes},
    }
    if log:
        machine_log = read_block(amiga.read_long, status.log_base, status.log_bytes)
        Path(f"{stem}.log").write_bytes(machine_log)
        found["log"] = compare_logs(choice.model_log.read_bytes(), machine_log)
    return found


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
