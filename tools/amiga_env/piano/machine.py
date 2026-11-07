"""Run the 68000 piano player on the emulated A500 and check it against the model.

One run boots a piece's floppy (see disk.py) on a machine from amiga.toml
with no window, and watches the status block the player keeps at $100
through Amiberry's control socket (READ_MEM). With the test build it reads
the voice log back the same way and compares it byte for byte with the
model's (`<out>/m68k/<piece>.log`). With `audio`, Amiberry runs at the
emulated machine's own speed and SDL's disk audio driver writes what
Amiberry plays (16-bit stereo at 44.1 kHz), which becomes a WAV; without
it the run goes as fast as the host allows (warp).

Everything a run finds goes to `<out>/emulator-<piece>[-log].json`, with
screenshots and the WAV beside it.
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
)
PLAYING, DONE, FAILED = 1, 2, 0xFFFFFFFF
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


def compare_logs(model: bytes, machine: bytes) -> dict:
    ticks = len(machine) // m68k.LOG_BYTES_PER_TICK
    difference = m68k.first_difference(model, machine)
    return {
        "model_ticks": len(model) // m68k.LOG_BYTES_PER_TICK,
        "machine_ticks": ticks,
        "identical": model == machine,
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

    def screenshot(self, path: Path) -> None:
        reply = self.send("SCREENSHOT", str(path.resolve()))
        if reply[0] != "OK":
            raise SystemExit(f"SCREENSHOT failed: {' '.join(reply)}")

    def stop(self) -> None:
        self._emulator.stop()


def run_piece(
    machine: profile.Machine,
    floppy: Path,
    model_log: Path,
    out: Path,
    name: str,
    log: bool,
    audio: bool,
    timeout: float = 600.0,
) -> dict:
    """Boot `floppy`, wait for the player to finish, and record what it did."""
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
    found: dict = {"floppy": str(floppy), "audio": audio, "warp": not audio}
    try:
        amiga.connect(floppy.resolve())
        if not audio:
            amiga.send("SET_WARP", "1")
        status = _wait(amiga, out / f"{name}-playing.png", timeout)
        amiga.screenshot(out / f"{name}-done.png")
        if audio:
            time.sleep(AUDIO_TAIL_S)
        found["status"] = status._asdict()
        if status.state == FAILED:
            raise SystemExit(f"the player failed; see {out / f'{name}-done.png'}")
        found["cpu"] = cpu_report(status)
        found["samples_in_chip"] = {
            "address": hex(status.samples),
            "how": "copied with AllocMem" if status.copied else "LoadSeg's chip hunk",
        }
        if log:
            machine_log = read_block(amiga.read_long, status.log_base, status.log_bytes)
            (out / f"{name}.log").write_bytes(machine_log)
            found["log"] = compare_logs(model_log.read_bytes(), machine_log)
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


def _wait(amiga: Amiga, playing_shot: Path, timeout: float) -> Status:
    started, shot = time.monotonic(), False
    while True:
        time.sleep(1.0)
        status = parse_status([amiga.read_long(STATUS + 4 * i) for i in range(13)])
        if status.magic == MAGIC and status.state == PLAYING and not shot and status.ms > 5000:
            amiga.screenshot(playing_shot)
            shot = True
        if status.magic == MAGIC and status.state in (DONE, FAILED):
            return status
        if time.monotonic() - started > timeout:
            raise SystemExit(f"the player did not finish within {timeout:g} s")
