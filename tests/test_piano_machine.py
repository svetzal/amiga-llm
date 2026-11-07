import struct
import wave

from amiga_env.piano import disk, m68k, machine
from amiga_env.piano.player import LogRow


def status(**fields):
    values = dict.fromkeys(machine.STATUS_FIELDS, 0) | fields
    return machine.parse_status([values[name] for name in machine.STATUS_FIELDS])


class TestStatus:
    def test_the_status_block_is_read_in_order(self):
        found = machine.parse_status(list(range(len(machine.STATUS_FIELDS))))

        assert (found.magic, found.state, found.entry_e, found.keys) == (0, 1, 12, 21)

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
    assert not found["same_ticks"]
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


def test_a_log_cut_short_matches_over_the_ticks_it_has():
    rows = [LogRow(t, 0, v, v, v, 300, 10, 10) for t in range(3) for v in range(4)]
    model = m68k.log_bytes(rows)

    found = machine.compare_logs(model, model[: 2 * m68k.LOG_BYTES_PER_TICK])

    assert (found["identical"], found["same_ticks"], found["machine_ticks"]) == (False, True, 2)


class TestKeys:
    def test_menu_keys_are_amiga_raw_key_codes(self):
        assert [machine.raw_key(k) for k in "19AQZ"] == [0x01, 0x09, 0x20, 0x10, 0x31]

    def test_lower_case_presses_the_same_key(self):
        assert machine.raw_key("a") == machine.raw_key("A")

    def test_every_menu_key_has_a_code(self):
        assert all(machine.raw_key(k) for k in disk.MENU_KEYS)


class TestDisks:
    def test_ofs_blocks_count_headers_and_extension_blocks(self):
        assert disk.ofs_blocks(488) == 2
        assert disk.ofs_blocks(72 * 488) == 73
        assert disk.ofs_blocks(73 * 488) == 75


def test_the_boot_silence_is_dropped_up_to_a_lead():
    silence = struct.pack("<2h", 3, -3) * 44100 * 3
    music = struct.pack("<2h", 1000, -1000) * 10

    trimmed, dropped = machine.trim_lead(silence + music, lead_s=1.0)

    assert dropped == 2.0
    assert trimmed == silence[: 4 * 44100] + music
