import dataclasses
import struct

import numpy as np
import pytest
from amiga_env.piano import m68k3500, mixer
from amiga_env.piano.player3500 import Instrument, MixSample, Sound


def tiny():
    """Two keys, two layers, one root, two samples."""
    data = [np.arange(10, dtype=np.int16), np.array([-1, 2, -3, 4], dtype=np.int16)]
    samples = [MixSample(mixer.padded(d, 2), len(d), 2) for d in data]
    sounds = (
        (Sound(0, 0x10000, 0xFFF0, 0x8000, 7), Sound(1, 0x8000, 0xFFE0, 0x4000, 3)),
        (Sound(1, 0x12345, 0xFFFF, 0x1234, 0), Sound(0, 0x1FFFF, 1, 2, 65535)),
    )
    instrument = Instrument(
        sounds=sounds,
        pans=((46340, 46340), (65535, 0)),
        roots=(0, 0),
        volumes=(tuple(range(128)),),
        layer_of=tuple(0 if v < 64 else 1 for v in range(128)),
    )
    return instrument, samples


class TestSamples:
    def test_samples_go_end_to_end_padded_and_big_endian(self):
        _, samples = tiny()

        data = m68k3500.samples_bytes(samples)

        assert len(data) == 2 * (10 + 4 + 2 * mixer.PAD)
        assert struct.unpack_from(">3h", data, 0) == (0, 1, 2)
        second = 2 * (10 + mixer.PAD)
        assert struct.unpack_from(">4h", data, second) == (-1, 2, -3, 4)

    def test_each_entry_gives_offset_length_loop_start_and_loop_length(self):
        _, samples = tiny()

        assert m68k3500.sample_entries(samples) == [(0, 10, 2, 8), (2 * (10 + mixer.PAD), 4, 2, 2)]


class TestTables:
    def test_the_tables_read_back_as_they_were_written(self):
        instrument, samples = tiny()

        tables = m68k3500.read_tables(m68k3500.tables_bytes(instrument, samples))

        assert tables.layer_of == instrument.layer_of
        assert tables.volumes == instrument.volumes
        assert tables.samples == tuple(m68k3500.sample_entries(samples))
        assert tables.keys == ((0, 46340, 46340), (0, 65535, 0))
        assert tables.sounds == instrument.sounds

    def test_the_layout_is_header_layers_volumes_samples_keys_sounds(self):
        instrument, samples = tiny()

        data = m68k3500.tables_bytes(instrument, samples)

        assert data[:4] == b"P35T"
        assert struct.unpack_from(">HHHHHH", data, 4) == (1, 2, 2, 1, 2, 0)
        assert len(data) == 16 + 128 + 1 * 256 + 2 * 16 + 2 * 8 + 2 * 2 * 12
        first_sound = 16 + 128 + 256 + 32 + 16
        assert struct.unpack_from(">HLHHH", data, first_sound) == (0, 0x10000, 0xFFF0, 0x8000, 7)

    def test_a_short_layer_table_is_refused(self):
        instrument, samples = tiny()

        with pytest.raises(ValueError):
            m68k3500.tables_bytes(dataclasses.replace(instrument, layer_of=(0,) * 10), samples)
