"""The piano's tables and voice log in the byte layout the 68000 player uses.

Everything is big-endian, as the 68000 reads it. `examples/piano/player.s`
includes the tables with INCBIN; its log build writes the voice log in the
same layout as `log_bytes`, so the two can be compared byte for byte.

Key table, KEY_BYTES per key, keys 0 to 87 from A0:
    sample index, period, level (0-256), held factor, release factor,
    attack ticks: six words.

Sample table, SAMPLE_BYTES per sample, offsets from the start of the
samples' chip RAM block:
    offset (long), length in words (word), loop offset (long), loop length
    in words (word).

Velocity table: 128 words, the 8.8 volume of each MIDI velocity.

Voice log, LOG_BYTES_PER_TICK per tick, one record of LOG_RECORD_BYTES for
each of the four voices in order:
    key (byte, 0-87, 0xFF when silent), sample (byte, 0xFF when silent),
    period (word), volume (byte, 0-64), Paula volume (byte, 0-64).
"""

import struct
from collections.abc import Sequence
from typing import NamedTuple

from .player import VOICES, KeySound, LogRow
from .samples import PaulaSample

KEY_BYTES = 12
SAMPLE_BYTES = 12
LOG_RECORD_BYTES = 6
LOG_BYTES_PER_TICK = LOG_RECORD_BYTES * VOICES
LOG_FIELDS = ("key", "sample", "period", "volume", "out")


def key_table(sounds: Sequence[KeySound | None]) -> bytes:
    out = bytearray()
    for sound in sounds:
        if sound is None:
            raise ValueError("the 68000 player needs a sound for every key")
        out += struct.pack(
            ">6H",
            sound.sample,
            sound.period,
            sound.level,
            sound.held,
            sound.release,
            sound.attack_ticks,
        )
    return bytes(out)


def sample_table(made: Sequence[PaulaSample]) -> bytes:
    out, offset = bytearray(), 0
    for sample in made:
        if len(sample.data) % 2 or sample.loop_start % 2:
            raise ValueError(f"sample {sample.root}: Paula needs even lengths and loop starts")
        out += struct.pack(
            ">LHLH",
            offset,
            len(sample.data) // 2,
            offset + sample.loop_start,
            sample.loop_length // 2,
        )
        offset += len(sample.data)
    return bytes(out)


def velocity_bytes(table: Sequence[int]) -> bytes:
    if len(table) != 128:
        raise ValueError("the velocity table has one entry for each of 128 velocities")
    return struct.pack(">128H", *table)


def log_bytes(log: Sequence[LogRow]) -> bytes:
    """The model's voice log in the 68000 player's layout."""
    return b"".join(
        struct.pack(">BBHBB", row.key & 0xFF, row.sample & 0xFF, row.period, row.volume, row.out)
        for row in log
    )


class Difference(NamedTuple):
    tick: int
    voice: int
    field: str
    model: int
    machine: int


def first_difference(model: bytes, machine: bytes) -> Difference | None:
    """Where the machine's log first differs from the model's, over the ticks both have."""
    ticks = min(len(model), len(machine)) // LOG_BYTES_PER_TICK
    for tick in range(ticks):
        start = tick * LOG_BYTES_PER_TICK
        a = model[start : start + LOG_BYTES_PER_TICK]
        b = machine[start : start + LOG_BYTES_PER_TICK]
        if a == b:
            continue
        for voice in range(VOICES):
            ra = _record(a, voice)
            rb = _record(b, voice)
            for name, x, y in zip(LOG_FIELDS, ra, rb, strict=True):
                if x != y:
                    return Difference(tick, voice, name, x, y)
    return None


def _record(tick: bytes, voice: int) -> tuple[int, ...]:
    return struct.unpack_from(">BBHBB", tick, voice * LOG_RECORD_BYTES)
