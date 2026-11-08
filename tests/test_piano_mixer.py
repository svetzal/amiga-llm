import numpy as np
import pytest
from amiga_env.piano import mixer


class TestTime:
    @pytest.mark.parametrize(
        ("ms", "sample"), [(0, 0), (1, 27), (18, 503), (19, 531), (1000, 27965)]
    )
    def test_a_millisecond_falls_on_its_output_sample(self, ms, sample):
        assert mixer.sample_of_ms(ms) == sample

    def test_a_note_starts_inside_its_block_at_its_own_offset(self):
        sample = mixer.sample_of_ms(19)

        assert divmod(sample, mixer.BLOCK) == (1, 19)

    def test_ms_of_sample_comes_back_within_a_millisecond(self):
        for ms in range(0, 5000, 7):
            assert ms - 1 <= mixer.ms_of_sample(mixer.sample_of_ms(ms)) <= ms


class TestStep:
    def test_a_sample_at_the_mix_rate_played_at_pitch_steps_one(self):
        assert mixer.step(mixer.MIX_RATE, 1.0) == mixer.ONE

    def test_half_the_rate_steps_a_half(self):
        assert mixer.step(mixer.MIX_RATE / 2, 1.0) == mixer.ONE // 2

    def test_a_step_of_two_or_more_is_refused(self):
        with pytest.raises(ValueError):
            mixer.step(mixer.MIX_RATE, 2.0)

    def test_the_pad_covers_a_block_at_the_largest_step(self):
        assert mixer.PAD >= mixer.BLOCK * mixer.MAX_STEP // mixer.ONE


class TestPan:
    def test_width_0_puts_every_key_in_the_middle(self):
        assert {mixer.pan_gains(k, 0.0) for k in (0, 40, 87)} == {(46340, 46340)}

    def test_bass_goes_left_and_treble_right(self):
        bass, treble = mixer.pan_gains(0, 0.5), mixer.pan_gains(87, 0.5)

        assert bass[0] > bass[1]
        assert treble[1] > treble[0]
        assert bass == treble[::-1]

    def test_width_1_puts_the_end_keys_hard_over(self):
        assert mixer.pan_gains(0, 1.0) == (65535, 0)
        assert mixer.pan_gains(87, 1.0) == (0, 65535)

    def test_gains_keep_constant_power(self):
        for key in range(88):
            left, right = mixer.pan_gains(key, 0.7)

            assert (left**2 + right**2) / 65535**2 == pytest.approx(1, abs=1e-4)

    def test_multipliers_are_volume_times_gain_over_65536(self):
        assert mixer.multiplier(8192, 46340) == 5792
        assert [mixer.faded(5792, q) for q in (4, 3, 2, 1)] == [5792, 4344, 2896, 1448]


class TestMixRun:
    DATA = np.array([100, -100, 32767, -32768, 7, -7], dtype=np.int16)

    def test_a_run_gives_each_samples_full_32_bit_product(self):
        left, right, _ = mixer.mix_run(self.DATA, 0, mixer.ONE, 0x4000, 0x7FFF, 6)

        assert left.tolist() == [v * 0x4000 for v in self.DATA.tolist()]
        assert right.tolist() == [v * 0x7FFF for v in self.DATA.tolist()]

    def test_the_phase_fraction_carries_into_the_index(self):
        left, _, phase = mixer.mix_run(self.DATA, 0, 0xC000, 1, 0, 4)

        assert left.tolist() == [100, 100, -100, 32767]  # phases 0, 0.75, 1.5 and 2.25
        assert phase == 4 * 0xC000

    def test_a_run_reads_past_the_end_into_the_pad(self):
        data = mixer.padded(np.arange(10, dtype=np.int16), loop_start=6)

        assert data[10:18].tolist() == [6, 7, 8, 9, 6, 7, 8, 9]
        assert len(data) == 10 + mixer.PAD

    def test_the_phase_goes_back_round_the_loop_at_a_block_start(self):
        assert mixer.wrap_phase(9 << 16, 10, 6) == 9 << 16
        assert mixer.wrap_phase((10 << 16) + 5, 10, 6) == (6 << 16) + 5
        assert mixer.wrap_phase(17 << 16, 10, 6) == 9 << 16  # more than one loop past

    def test_sums_wrap_as_32_bit_longwords_do(self):
        sums = np.array([2**31 - 1, 2**31, -(2**31) - 1, 2**32 + 5])

        assert mixer.wrap32(sums).tolist() == [2**31 - 1, -(2**31), 2**31 - 1, 5]


class TestOutput:
    def test_a_sum_is_shifted_right_by_14_rounding_down(self):
        sums = np.array([0, 1 << 14, (1 << 14) - 1, -1, -(1 << 14) - 1])

        assert mixer.output16(sums).tolist() == [0, 1, 0, -1, -2]

    def test_a_sum_past_full_scale_is_clamped_and_counted(self):
        sums = np.array([32767 << 14, 32768 << 14, -(32768 << 14), (-32769) << 14, 2**31 - 1])

        assert mixer.output16(sums).tolist() == [32767, 32767, -32768, -32768, 32767]
        assert mixer.clamped(sums) == 3


class TestFourteenBits:
    @pytest.mark.parametrize("value", [-32768, -257, -256, -5, -1, 0, 3, 4, 255, 256, 32767])
    def test_paula_puts_the_two_channels_back_together_as_the_top_14_bits(self, value):
        high, low = mixer.split14(np.array([value], dtype=np.int16))

        assert 0 <= int(low[0]) <= 63
        assert mixer.paula_output(high, low).tolist() == [value >> 2]

    def test_the_render_holds_each_mixed_sample_and_scales_to_16_bits(self):
        output = np.array([1000, -1000] * 50, dtype=np.int32)

        frames = mixer.stereo_wav_frames(output, -output, 44100)

        assert frames.shape == (len(output) * 44100 * 128 // 3_579_545, 2)
        assert frames[0].tolist() == [4000, -4000]
        assert frames[1].tolist() == [4000, -4000]  # 44.1 kHz reads each sample 1.6 times
        assert frames[2].tolist() == [-4000, 4000]


class TestChecksum:
    def test_it_sums_the_words_and_their_running_totals(self):
        a, b = mixer.checksum(np.array([1, -1]), np.array([2, 3]))

        assert a == 1 + 2 + 0xFFFF + 3
        assert b == 1 + 3 + (3 + 0xFFFF) + (6 + 0xFFFF)

    def test_it_sees_a_swap_of_left_and_right(self):
        left, right = np.array([1, 2, 3]), np.array([4, 5, 6])

        assert mixer.checksum(left, right) != mixer.checksum(right, left)
