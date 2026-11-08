import struct

import numpy as np
import pytest
from amiga_env.piano import harness3500, player3500, run3500


def status(**fields):
    values = dict.fromkeys(run3500.STATUS_FIELDS, 0) | {"vblank_hz": 60} | fields
    return run3500.Status(*(values[name] for name in run3500.STATUS_FIELDS))


class TestSteering:
    def test_within_a_pixel_it_stops(self):
        assert harness3500.steer_move((100, 50), (101, 49), [4.0, 4.0]) is None

    def test_a_move_goes_most_of_the_way_at_the_learnt_gain(self):
        assert harness3500.steer_move((100, 50), (110, 40), [2.0, 3.0]) == (14, -21)

    def test_a_far_target_is_approached_in_limited_moves(self):
        move = harness3500.steer_move((0, 0), (300, 0), [4.0, 4.0])

        assert move == (harness3500.STEER_LIMIT, 0)

    def test_a_small_distance_still_moves_a_count(self):
        assert harness3500.steer_move((100, 50), (102, 50), [0.5, 0.5]) == (1, 0)

    def test_the_gain_is_counts_per_pixel_moved(self):
        gain = harness3500.learn_gain([4.0, 4.0], (20, -12), (100, 50), (110, 46))

        assert gain == [2.0, 3.0]

    def test_a_move_that_went_nowhere_or_backwards_teaches_nothing(self):
        assert harness3500.learn_gain([4.0, 4.0], (20, 12), (100, 50), (100, 45)) == [4.0, 4.0]


class TestLogs:
    def log(self, blocks):
        body = bytes((i * 5 + 1) % 256 for i in range(blocks * player3500.LOG_BLOCK_BYTES))
        return player3500.log_header(blocks) + body

    def test_a_stopped_pieces_log_matches_the_models_first_blocks(self):
        model, machine = self.log(5), self.log(5)
        machine = player3500.log_header(2) + machine[16 : 16 + 2 * player3500.LOG_BLOCK_BYTES]

        found = harness3500.compare_prefix(model, machine)

        assert found == {"machine_blocks": 2, "same_header": True, "same_blocks": True}

    def test_a_changed_byte_is_found(self):
        model = self.log(3)
        machine = bytearray(player3500.log_header(1) + model[16 : 16 + 232])
        machine[30] ^= 1

        assert not harness3500.compare_prefix(model, bytes(machine))["same_blocks"]


class TestLatency:
    def test_steps_are_milliseconds_after_the_choice(self):
        found = harness3500.latency(
            status(chosen_at=600, gold_at=601, playing_at=602, first_note_at=660)
        )

        assert found == {"line_gold_ms": 17, "first_block_made_ms": 33, "first_note_ms": 1000}

    def test_a_step_before_the_choice_is_left_out(self):
        found = harness3500.latency(status(chosen_at=600, gold_at=601, first_note_at=10))

        assert "first_note_ms" not in found


class TestScreenshot:
    def test_the_screen_is_found_where_the_doubled_picture_fits(self):
        rng = np.random.default_rng(2)
        picture = rng.integers(0, 255, (20, 30, 3), dtype=np.uint8)
        shot = np.zeros((60, 90, 3), dtype=np.uint8)
        shot[8:48, 12:72] = picture.repeat(2, axis=0).repeat(2, axis=1)

        origin = harness3500.find_origin(shot, picture, range(0, 30, 2), range(0, 20, 2))

        assert (origin.x, origin.y, origin.difference) == (12, 8, 0.0)

    def test_a_shot_smaller_than_the_screen_is_refused(self):
        with pytest.raises(SystemExit):
            harness3500.find_origin(
                np.zeros((10, 10, 3)), np.zeros((20, 20, 3)), range(1), range(1)
            )


class TestIndex:
    def test_one_line_a_piece_its_name_then_its_title(self):
        text = run3500.index_text([("bwv846", "Bach  Prelude & Fugue in C")])

        assert text == "bwv846 Bach  Prelude & Fugue in C\n"

    def test_a_name_with_a_space_is_refused(self):
        with pytest.raises(SystemExit):
            run3500.index_text([("two words", "Title")])


def test_the_status_file_holds_every_field_the_player_writes():
    assert run3500.STATUS_BYTES == 192
    assert len(struct.pack(f">{len(run3500.STATUS_FIELDS)}L", *[0] * 48)) == 192
