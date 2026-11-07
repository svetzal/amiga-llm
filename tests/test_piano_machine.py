import struct
import wave

from amiga_env.piano import disk, m68k, machine
from amiga_env.piano.player import LogRow


def status(**fields):
    values = dict.fromkeys(machine.STATUS_FIELDS, 0) | fields
    return machine.parse_status([values[name] for name in machine.STATUS_FIELDS])


class TestStatus:
    def test_the_status_block_is_read_in_order(self):
        found = machine.parse_status(list(range(13)))

        assert (found.magic, found.state, found.entry_e) == (0, 1, 12)

    def test_cpu_shares_are_of_the_e_clock_ticks_played(self):
        # 1000 ms of 716 ticks; 71,600 ticks used is 10%; dispatch 35,800 is 5%.
        found = machine.cpu_report(
            status(ms=1000, frames=60, total_e=71_600, entry_e=35_800, max_frame_e=1193)
        )

        assert found["percent_of_cpu"] == 10.0
        assert found["dispatch_percent_of_cpu"] == 5.0
        assert found["average_e_per_frame"] == 1193
        assert found["worst_frame_percent"] == 10.0


def test_a_block_is_read_a_long_at_a_time():
    memory = bytes(range(16))

    def read_long(address):
        return struct.unpack_from(">L", memory, address)[0]

    assert machine.read_block(read_long, 4, 6) == memory[4:10]


def test_logs_compare_with_the_first_difference():
    rows = [LogRow(0, 0, v, v, v, 300, 10, 10) for v in range(4)]
    model = m68k.log_bytes(rows)
    other = m68k.log_bytes([*rows[:3], LogRow(0, 0, 3, 3, 3, 300, 10, 9)])

    assert machine.compare_logs(model, model)["identical"]
    found = machine.compare_logs(model, other)
    assert found["first_difference"] == {
        "tick": 0,
        "voice": 3,
        "field": "out",
        "model": 10,
        "machine": 9,
    }


def test_disk_audio_becomes_a_stereo_wav(tmp_path):
    path = tmp_path / "a.wav"

    machine.wav_from_raw(bytes(4 * 10 + 2), path)

    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (
            2,
            2,
            44100,
            10,
        )


class TestDisks:
    def test_each_piece_has_a_player_floppy_and_a_test_floppy(self):
        assert disk.disk_names("bwv846") == ("bwv846.adf", "bwv846-log.adf")
        assert disk.startup("bwv846") == ["piano bwv846"]

    def test_ofs_blocks_count_headers_and_extension_blocks(self):
        assert disk.ofs_blocks(488) == 2
        assert disk.ofs_blocks(72 * 488) == 73
        assert disk.ofs_blocks(73 * 488) == 75
