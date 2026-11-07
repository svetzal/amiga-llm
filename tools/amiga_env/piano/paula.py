"""Render the player's Paula writes to audio the way Paula makes it.

Each voice holds each 8-bit sample value for `period` clock cycles and
multiplies it by its 6-bit volume; there is no interpolation. Voices 0 and 3
are the left channel and voices 1 and 2 the right, as on every Amiga. The
held signal is read at the output rate (point sampling), so the render keeps
Paula's stair steps and the aliasing they bring.

Simplifications: a start or volume write takes effect at once (Paula waits
for the current sample period to end), and DMA timing is not modelled.

`a500_filter` approximates the A500's fixed low-pass: one pole at about
4.4 kHz, the 360 ohm and 0.1 uF RC usually given for it. It is not the
switchable "LED" filter, and it has not been measured on Stacey's machine.
"""

import math
import wave
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np

from .player import VOICES, Write
from .samples import NTSC_CLOCK

OUTPUT_RATE = 44_100
LEFT_VOICES = (0, 3)
A500_CUTOFF_HZ = 1 / (2 * math.pi * 360 * 0.1e-6)  # about 4421 Hz


class Sample(Protocol):
    data: bytes
    loop_start: int


def sample_index(elapsed: np.ndarray, period: int, length: int, loop_start: int, rate: int):
    """Which byte of a sample Paula plays `elapsed` output samples after it started:
    through the whole sample once, then round the loop."""
    played = elapsed * NTSC_CLOCK // (rate * period)
    loop = length - loop_start
    return np.where(played < length, played, loop_start + (played - length) % loop)


def render_voice(
    writes: Sequence[Write], samples: Sequence[Sample], frames: int, rate: int = OUTPUT_RATE
) -> np.ndarray:
    """One voice's output, sample value times volume (-8192 to 8128), as int32."""
    out = np.zeros(frames, dtype=np.int32)
    data = [np.frombuffer(s.data, dtype=np.int8).astype(np.int32) for s in samples]
    note = None  # (start frame, sample, period)
    volume = 0
    if not writes:
        return out
    for write, following in zip(writes, [*writes[1:], None], strict=True):
        if write.kind == "start":
            note, volume = (_frame(write.ms, rate), write.sample, write.period), write.volume
        elif write.kind == "volume":
            volume = write.volume
        else:
            note, volume = None, 0
        begin = _frame(write.ms, rate)
        end = frames if following is None else _frame(following.ms, rate)
        if note is None or volume == 0 or end <= begin:
            continue
        start, sample, period = note
        elapsed = np.arange(begin - start, end - start, dtype=np.int64)
        values = data[sample]
        index = sample_index(elapsed, period, len(values), samples[sample].loop_start, rate)
        out[begin:end] = values[index] * volume
    return out


def render(
    writes: Sequence[Write], samples: Sequence[Sample], end_ms: int, rate: int = OUTPUT_RATE
) -> np.ndarray:
    """Stereo int16 frames. Two voices at full scale on one side reach full scale."""
    frames = _frame(end_ms, rate) + 1
    channels = np.zeros((frames, 2), dtype=np.int32)
    for voice in range(VOICES):
        mine = [w for w in writes if w.voice == voice]
        side = 0 if voice in LEFT_VOICES else 1
        channels[:, side] += render_voice(mine, samples, frames, rate)
    return np.clip(channels * 2, -32768, 32767).astype(np.int16)


def a500_filter(frames: np.ndarray, rate: int = OUTPUT_RATE) -> np.ndarray:
    """The one-pole low-pass, as its impulse response truncated where it is below 1e-9."""
    a = 1 - math.exp(-2 * math.pi * A500_CUTOFF_HZ / rate)
    taps = math.ceil(math.log(1e-9) / math.log(1 - a))
    response = a * (1 - a) ** np.arange(taps)
    filtered = np.stack(
        [np.convolve(frames[:, c].astype(np.float64), response)[: len(frames)] for c in (0, 1)],
        axis=1,
    )
    return np.clip(np.round(filtered), -32768, 32767).astype(np.int16)


def write_wav(path: Path, frames: np.ndarray, rate: int = OUTPUT_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames.astype("<i2").tobytes())


def _frame(ms: int, rate: int) -> int:
    return ms * rate // 1000
