import struct
import wave
from pathlib import Path

import numpy as np
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


class TestScopes:
    def test_scope_shares_are_of_the_e_clock_ticks_played(self):
        # 1000 ms of 716 ticks: scopes 358,000 ticks is 50%, player 71,600 is 10%.
        found = machine.scope_report(
            status(ms=1000, scope_frames=30, scope_e=158_000, draw_e=200_000, total_e=71_600)
        )

        assert found["scope_frames_per_second"] == 30.0
        assert found["average_e_per_scope_frame"] == 11_933
        assert found["average_e_drawing"] == 6667
        assert found["scope_percent_of_cpu"] == 50.0
        assert found["player_and_scopes_percent_of_cpu"] == 60.0
        assert found["player_e_per_frame"] == 1193

    def test_no_scope_frames_is_not_a_division_by_zero(self):
        assert machine.scope_report(status())["average_e_per_scope_frame"] == 0


class TestPointer:
    def test_a_move_is_the_distance_times_the_gain(self):
        assert machine.pointer_move((10, 10), (20, 5)) == (40, -20)

    def test_a_long_move_is_sent_in_steps(self):
        assert machine.pointer_move((0, 0), (300, -300)) == (120, -120)

    def test_within_a_pixel_is_there(self):
        assert machine.pointer_move((201, 12), (202, 13)) is None


def test_the_status_block_has_the_screens_fields_after_the_menus():
    found = machine.parse_status(list(range(len(machine.STATUS_FIELDS))))

    assert (found.window, found.scope_frames, found.highlight, found.screen_chip) == (
        22,
        25,
        28,
        29,
    )


class TestScopeCoverage:
    def shot(self):
        return np.zeros((486, 752, 3), dtype=np.uint8)

    def test_a_trace_in_every_column_is_whole(self):
        shot = self.shot()
        scope = machine.Scope(10, 4, (85, 187, 204))
        for x in range(10, 14):
            shot[48 + 2 * 170, 60 + 2 * x] = (85, 187, 204)

        assert machine.scope_coverage(shot, [scope], (152, 197)) == [1.0]

    def test_a_half_drawn_trace_is_seen(self):
        shot = self.shot()
        scope = machine.Scope(10, 4, (85, 187, 204))
        for x in range(10, 12):
            shot[48 + 2 * 170, 60 + 2 * x] = (85, 187, 204)

        assert machine.scope_coverage(shot, [scope], (152, 197)) == [0.5]

    def test_pixels_outside_the_band_do_not_count(self):
        shot = self.shot()
        shot[48 + 2 * 100, 60 + 2 * 10] = (85, 187, 204)

        found = machine.scope_coverage(shot, [machine.Scope(10, 1, (85, 187, 204))], (152, 197))

        assert found == [0.0]


def test_the_recipes_scopes_are_checked_with_their_trace_colours():
    from amiga_env.piano import build

    recipe = build.load_recipe(Path(__file__).parents[1] / "examples" / "piano" / "piano.toml")

    scopes, rows = disk.scope_regions(recipe)

    assert rows == (152, 197)
    assert [s.left for s in scopes] == [8, 50, 92, 134, 180]
    assert scopes[0].colour == (85, 187, 204) and scopes[4].colour == (221, 187, 136)


class TestLatency:
    def test_each_step_is_milliseconds_after_the_choice(self):
        found = machine.latency_report(
            status(
                vblank_hz=60,
                chosen_at=600,
                gold_at=601,
                loaded_at=601,
                playing_at=602,
                first_note_at=662,
                first_note_ms=1000,
            )
        )

        assert found == {
            "line_gold_ms": 17,
            "score_ready_ms": 17,
            "timer_started_ms": 33,
            "first_note_ms": 1033,
            "first_note_in_the_score_ms": 1000,
            "frame_ms": 16.7,
        }

    def test_the_piece_before_counts_only_when_it_ended_for_this_one(self):
        switched = status(vblank_hz=60, chosen_at=600, ended_at=606, playing_at=607)
        own_end = status(vblank_hz=60, chosen_at=600, ended_at=9000, playing_at=607)

        assert machine.latency_report(switched)["previous_piece_ended_ms"] == 100
        assert "previous_piece_ended_ms" not in machine.latency_report(own_end)
