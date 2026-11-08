"""The A3500 piano's data in the byte layout its 68030 player loads.

Everything is big-endian, as the 68030 reads it. The player
(`examples/piano3500/player.s`) loads two files whole into fast RAM, and a
piece's score (score.py's stream, unchanged).

`samples.bin`: every sample end to end as signed 16-bit words, each with
its pad already in place (mixer.padded: PAD more samples round its loop),
so the player only loads it. Sample i starts at the byte offset its table
entry gives.

`piano.tab`: a header of TABLE_HEADER_BYTES, then five sections, one after
the other, each an even number of bytes:

    header   "P35T", version (word, 1), keys, layers, roots, samples (words),
             a zero word
    layers   128 bytes: the kept layer each MIDI velocity plays (0 for 0)
    volumes  roots * 128 words: each root's voice volume for each velocity
    samples  samples * SAMPLE_BYTES: byte offset in samples.bin (long),
             length before the pad, loop start and loop length, in samples
             (longs)
    keys     keys * KEY_BYTES: root index, left gain, right gain (words),
             a zero word
    sounds   keys * layers * SOUND_BYTES, key by key, layer by layer:
             sample index (word), 16.16 step (long), held factor, release
             factor and attack blocks (words)
"""

import struct
from collections.abc import Sequence
from typing import NamedTuple

import numpy as np

from .player3500 import Instrument, MixSample, Sound

TABLE_MAGIC = b"P35T"
TABLE_VERSION = 1
TABLE_HEADER = ">4sHHHHHH"
TABLE_HEADER_BYTES = struct.calcsize(TABLE_HEADER)
VELOCITIES = 128
SAMPLE_ENTRY = ">LLLL"
SAMPLE_BYTES = struct.calcsize(SAMPLE_ENTRY)
KEY_ENTRY = ">HHHH"
KEY_BYTES = struct.calcsize(KEY_ENTRY)
SOUND_ENTRY = ">HLHHH"
SOUND_BYTES = struct.calcsize(SOUND_ENTRY)


class Tables(NamedTuple):
    """piano.tab read back: the reference for the player's reader."""

    layer_of: tuple[int, ...]
    volumes: tuple[tuple[int, ...], ...]
    samples: tuple[tuple[int, int, int, int], ...]  # offset, length, loop start, loop length
    keys: tuple[tuple[int, int, int], ...]  # root, left gain, right gain
    sounds: tuple[tuple[Sound, ...], ...]


def samples_bytes(samples: Sequence[MixSample]) -> bytes:
    """samples.bin: the padded samples end to end, big-endian."""
    return b"".join(np.asarray(s.data, dtype=">i2").tobytes() for s in samples)


def sample_entries(samples: Sequence[MixSample]) -> list[tuple[int, int, int, int]]:
    entries, offset = [], 0
    for s in samples:
        entries.append((offset, s.length, s.loop_start, s.length - s.loop_start))
        offset += 2 * len(s.data)
    return entries


def tables_bytes(instrument: Instrument, samples: Sequence[MixSample]) -> bytes:
    """piano.tab for an instrument and its samples."""
    keys, layers = len(instrument.sounds), len(instrument.sounds[0])
    roots = len(instrument.volumes)
    if len(instrument.layer_of) != VELOCITIES:
        raise ValueError("the layer table has one entry for each of 128 velocities")
    out = bytearray(
        struct.pack(TABLE_HEADER, TABLE_MAGIC, TABLE_VERSION, keys, layers, roots, len(samples), 0)
    )
    out += bytes(instrument.layer_of)
    for volumes in instrument.volumes:
        out += struct.pack(f">{VELOCITIES}H", *volumes)
    for entry in sample_entries(samples):
        out += struct.pack(SAMPLE_ENTRY, *entry)
    for root, (left, right) in zip(instrument.roots, instrument.pans, strict=True):
        out += struct.pack(KEY_ENTRY, root, left, right, 0)
    for per_key in instrument.sounds:
        for s in per_key:
            out += struct.pack(SOUND_ENTRY, s.sample, s.step, s.held, s.release, s.attack_blocks)
    return bytes(out)


def read_tables(data: bytes) -> Tables:
    magic, version, keys, layers, roots, count, _ = struct.unpack_from(TABLE_HEADER, data)
    if (magic, version) != (TABLE_MAGIC, TABLE_VERSION):
        raise ValueError("not a version 1 A3500 piano table")
    at = TABLE_HEADER_BYTES
    layer_of = tuple(data[at : at + VELOCITIES])
    at += VELOCITIES
    volumes = []
    for _ in range(roots):
        volumes.append(struct.unpack_from(f">{VELOCITIES}H", data, at))
        at += 2 * VELOCITIES
    entries = []
    for _ in range(count):
        entries.append(struct.unpack_from(SAMPLE_ENTRY, data, at))
        at += SAMPLE_BYTES
    key_rows = []
    for _ in range(keys):
        key_rows.append(struct.unpack_from(KEY_ENTRY, data, at)[:3])
        at += KEY_BYTES
    sounds = []
    for _ in range(keys):
        row = []
        for _ in range(layers):
            row.append(Sound(*struct.unpack_from(SOUND_ENTRY, data, at)))
            at += SOUND_BYTES
        sounds.append(tuple(row))
    if at != len(data):
        raise ValueError(f"{len(data) - at} bytes after the tables")
    return Tables(layer_of, tuple(volumes), tuple(entries), tuple(key_rows), tuple(sounds))
