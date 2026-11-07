import struct

import pytest
from amiga_env.piano import m68k
from amiga_env.piano.player import KeySound, LogRow
from amiga_env.piano.samples import NTSC_CLOCK, PaulaSample


def made(root, length, loop_start):
    return PaulaSample(
        root=root,
        keys=(root,),
        data=bytes(length),
        loop_start=loop_start,
        period=320,
        periods={root: 320},
        rate=NTSC_CLOCK / 320,
        level=1.0,
        decay_db_per_s=1.0,
        loop_similarity=1.0,
        max_cents_error=0.0,
    )


def test_each_key_is_six_big_endian_words():
    sounds = [KeySound(2, 320, 200, 0xFF00, 0x8000, 59)] * 88

    table = m68k.key_table(sounds)

    assert len(table) == 88 * m68k.KEY_BYTES
    assert table[:12] == bytes.fromhex("0002 0140 00c8 ff00 8000 003b".replace(" ", ""))


def test_a_key_without_a_sound_is_refused():
    with pytest.raises(ValueError, match="every key"):
        m68k.key_table([None])


def test_samples_follow_each_other_and_loops_are_offsets_into_the_block():
    table = m68k.sample_table([made(21, 100, 60), made(24, 40, 10)])

    assert struct.unpack(">LHLH", table[:12]) == (0, 50, 60, 20)
    assert struct.unpack(">LHLH", table[12:]) == (100, 20, 110, 15)


def test_an_odd_loop_start_is_refused():
    with pytest.raises(ValueError, match="even"):
        m68k.sample_table([made(21, 100, 61)])


def test_the_velocity_table_is_128_words():
    assert m68k.velocity_bytes(list(range(128)))[254:] == b"\x00\x7f"
    with pytest.raises(ValueError):
        m68k.velocity_bytes([0])


def row(tick, voice, key=-1, sample=-1, period=0, volume=0, out=0):
    return LogRow(tick, 0, voice, key, sample, period, volume, out)


def test_a_silent_voice_logs_ff_for_its_key_and_sample():
    log = [row(0, 0, 39, 12, 321, 22, 20), row(0, 1), row(0, 2), row(0, 3)]

    data = m68k.log_bytes(log)

    assert len(data) == m68k.LOG_BYTES_PER_TICK
    assert data[:12] == bytes.fromhex("270c01411614ffff00000000")


class TestComparingLogs:
    model = m68k.log_bytes([row(t, v, key=v, period=300 + t) for t in range(3) for v in range(4)])

    def test_identical_logs_have_no_difference(self):
        assert m68k.first_difference(self.model, self.model) is None

    def test_the_first_differing_field_is_named(self):
        machine = bytearray(self.model)
        machine[1 * 24 + 2 * 6 + 3] ^= 1  # tick 1, voice 2, low byte of the period

        found = m68k.first_difference(self.model, bytes(machine))

        assert found == m68k.Difference(1, 2, "period", 301, 300)

    def test_only_the_ticks_both_logs_have_are_compared(self):
        assert m68k.first_difference(self.model, self.model[:24]) is None
