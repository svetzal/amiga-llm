from itertools import pairwise

import numpy as np
import pytest
from amiga_env.piano.samples import (
    MIN_PERIOD,
    NTSC_CLOCK,
    SampleSpec,
    cents,
    choose_layer,
    choose_period,
    choose_roots,
    crossfade_seam,
    decay_rate,
    find_loop,
    finish,
    key_map,
    layer_regions,
    prepare,
    quantise,
    resample,
    trim_silence,
)
from amiga_env.piano.sfz import Region

SALAMANDER_ROOTS = list(range(21, 109, 3))  # minor thirds from A0 to C8


def sine(freq, rate, seconds, decay_db_per_s=0.0):
    t = np.arange(int(rate * seconds)) / rate
    return np.sin(2 * np.pi * freq * t) * 10 ** (-decay_db_per_s * t / 20)


class TestChoosingLayersAndRoots:
    def test_the_layer_is_the_one_holding_the_velocity(self):
        regions = [Region("a", lovel=1, hivel=56), Region("b", lovel=57, hivel=64)]

        assert choose_layer(regions, 62) == (57, 64)

    def test_release_regions_do_not_count_as_a_layer(self):
        regions = [Region("a", lovel=1, hivel=40), Region("r", lovel=45, trigger="release")]

        assert choose_layer(regions, 60) == (1, 40)

    def test_layer_regions_are_keyed_by_root(self):
        regions = [Region("a", pitch_keycenter=24), Region("b", pitch_keycenter=21)]

        assert list(layer_regions(regions, (1, 127))) == [21, 24]

    def test_every_three_semitones_takes_every_salamander_root(self):
        assert choose_roots(SALAMANDER_ROOTS, 3) == SALAMANDER_ROOTS

    def test_every_six_semitones_takes_every_other_root_and_both_ends(self):
        roots = choose_roots(SALAMANDER_ROOTS, 6)

        assert roots[0] == 21 and roots[-1] == 108
        assert all(b - a in (6, 9) for a, b in pairwise(roots))

    def test_roots_are_always_notes_that_were_sampled(self):
        assert set(choose_roots([21, 30, 60, 108], 3)) <= {21, 30, 60, 108}

    def test_each_key_plays_its_nearest_root_and_the_lower_on_a_tie(self):
        mapping = key_map([21, 24, 108], low=21, high=25)

        assert mapping == {21: 21, 22: 21, 23: 24, 24: 24, 25: 24}
        assert key_map([21, 23], low=22, high=22) == {22: 21}


class TestChoosingAPeriod:
    def test_the_root_is_exact_and_neighbours_are_close(self):
        ratios = [2 ** (-1 / 12), 1.0, 2 ** (1 / 12)]

        period, periods, error = choose_period(ratios, 320.0)

        assert periods[1] == period
        assert error < 1.0
        assert periods[2] < period < periods[0]

    def test_no_key_goes_below_the_shortest_period(self):
        _, periods, _ = choose_period([1.0, 2 ** (1 / 12)], MIN_PERIOD)

        assert min(periods.values()) >= MIN_PERIOD

    def test_says_when_no_period_fits(self):
        with pytest.raises(ValueError, match="no period"):
            choose_period([1.0, 1.5], 100.0)

    def test_cents(self):
        assert cents(2.0) == pytest.approx(1200)


class TestSignals:
    def test_resampling_keeps_a_tone_and_its_level(self):
        y = resample(sine(440, 44100, 0.5), 44100, 11025)

        middle = y[1000:4000]
        spectrum = np.abs(np.fft.rfft(middle * np.hanning(len(middle))))
        peak_hz = np.argmax(spectrum) * 11025 / len(middle)
        assert peak_hz == pytest.approx(440, abs=5)
        assert np.max(np.abs(middle)) == pytest.approx(1.0, abs=0.02)

    def test_resampling_removes_what_the_new_rate_cannot_hold(self):
        y = resample(sine(9000, 44100, 0.2), 44100, 11025)

        assert np.max(np.abs(y[200:-200])) < 0.01

    def test_decay_rate_of_an_exponential_fade(self):
        x = sine(220, 8000, 4.0, decay_db_per_s=6.0)

        assert decay_rate(x, 8000, 0.5) == pytest.approx(6.0, abs=0.3)

    def test_a_loop_of_a_steady_tone_is_whole_cycles(self):
        y = sine(100, 10000, 1.0)  # 100 samples a cycle

        length = find_loop(y, end=8000, shortest=150, longest=260, window=50)

        assert length == 200

    def test_the_crossfade_makes_the_seam_continue_the_signal(self):
        y = np.arange(100, dtype=float)

        out = crossfade_seam(y, start=40, end=80, fade=10)

        assert out[79] == y[39]
        assert np.array_equal(out[:70], y[:70])

    def test_quantising_is_signed_8_bit_and_repeatable(self):
        y = sine(50, 1000, 1.0)

        a = quantise(y, 126, np.random.default_rng(1))
        b = quantise(y, 126, np.random.default_rng(1))

        assert a.dtype == np.int8
        assert np.array_equal(a, b)
        assert a.max() <= 127 and a.min() >= -128
        assert np.abs(a.astype(float) - y * 126).max() <= 2

    def test_trim_silence_keeps_a_short_lead_in(self):
        x = np.concatenate([np.zeros(1000), np.ones(10)])

        assert len(trim_silence(x, lead=32)) == 42


class TestPrepareAndFinish:
    @pytest.fixture
    def made(self):
        spec = SampleSpec(attack_bass_s=0.4, attack_treble_s=0.4, loop_s=0.05)
        recording = sine(220.0, 44100, 3.0, decay_db_per_s=8.0)
        region = Region("a3.wav", lokey=56, hikey=58, pitch_keycenter=57)
        return finish([prepare(region, recording, 44100.0, [56, 57, 58], spec)], spec)[0]

    def test_lengths_are_whole_words_for_paula(self, made):
        assert len(made.data) % 2 == 0
        assert made.loop_start % 2 == 0
        assert 0 < made.loop_start < len(made.data)

    def test_the_root_plays_at_its_period_and_the_rate_follows(self, made):
        assert made.periods[57] == made.period
        assert made.rate == pytest.approx(NTSC_CLOCK / made.period)
        assert made.rate >= 11025 * 0.94

    def test_the_decay_and_loop_are_measured(self, made):
        assert made.decay_db_per_s == pytest.approx(8.0, abs=0.5)
        assert made.loop_similarity > 0.99
        assert made.level == 1.0

    def test_the_loop_holds_its_level(self, made):
        data = np.frombuffer(made.data, dtype=np.int8).astype(float)
        loop = data[made.loop_start :]
        half = len(loop) // 2
        first, second = np.abs(loop[:half]).max(), np.abs(loop[half:]).max()
        assert first == pytest.approx(second, rel=0.1)
