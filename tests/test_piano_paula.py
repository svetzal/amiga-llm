import wave
from dataclasses import dataclass

import numpy as np
import pytest
from amiga_env.piano import build
from amiga_env.piano.paula import (
    a500_filter,
    render,
    render_voice,
    sample_index,
    write_wav,
)
from amiga_env.piano.player import Result, Steal, Write, decay_factor
from amiga_env.piano.samples import NTSC_CLOCK, PaulaSample
from amiga_env.piano.sfz import Region

# With this output rate one output frame is exactly one Paula sample at period 100.
RATE = NTSC_CLOCK // 100


@dataclass(frozen=True)
class Tiny:
    data: bytes
    loop_start: int


RAMP = Tiny(bytes([1, 2, 3, 4, 5, 6]), loop_start=4)  # plays 1 2 3 4 5 6 5 6 5 6 ...


class TestSampleIndex:
    def test_plays_through_once_then_round_the_loop(self):
        elapsed = np.arange(10)

        index = sample_index(elapsed, period=100, length=6, loop_start=4, rate=RATE)

        assert index.tolist() == [0, 1, 2, 3, 4, 5, 4, 5, 4, 5]

    def test_a_longer_period_holds_each_value_longer(self):
        index = sample_index(np.arange(6), period=200, length=6, loop_start=4, rate=RATE)

        assert index.tolist() == [0, 0, 1, 1, 2, 2]


class TestRenderVoice:
    def test_values_times_volume_with_no_interpolation(self):
        writes = [Write(0, 0, "start", sample=0, period=100, volume=2)]

        out = render_voice(writes, [RAMP], frames=8, rate=RATE)

        assert out.tolist() == [2, 4, 6, 8, 10, 12, 10, 12]

    def test_a_volume_write_changes_the_level_without_restarting(self):
        writes = [
            Write(0, 0, "start", sample=0, period=100, volume=1),
            Write(1, 0, "volume", volume=10),  # 1 ms is frame 35
        ]

        out = render_voice(writes, [RAMP], frames=40, rate=RATE)

        assert out[33:37].tolist() == [6, 5, 60, 50]

    def test_a_stop_silences_the_voice(self):
        writes = [Write(0, 0, "start", sample=0, period=100, volume=1), Write(1, 0, "stop")]

        out = render_voice(writes, [RAMP], frames=200, rate=RATE)

        stop = RATE // 1000
        assert out[stop - 1] != 0
        assert not out[stop:].any()


def test_voices_0_and_3_are_left_and_1_and_2_are_right():
    writes = [
        Write(0, 0, "start", sample=0, period=100, volume=64),
        Write(0, 1, "start", sample=1, period=100, volume=1),
    ]
    samples = [Tiny(bytes([0x80, 0x80]), 0), Tiny(bytes([1, 1]), 0)]

    frames = render(writes, samples, end_ms=0, rate=RATE)

    assert frames[0].tolist() == [-128 * 64 * 2, 2]


def test_the_a500_filter_passes_low_tones_and_cuts_high_ones():
    t = np.arange(44100) / 44100
    low = np.round(10000 * np.sin(2 * np.pi * 100 * t)).astype(np.int16)
    high = np.round(10000 * np.sin(2 * np.pi * 15000 * t)).astype(np.int16)

    for tone, low_gain in ((low, True), (high, False)):
        out = a500_filter(np.stack([tone, tone], axis=1))
        ratio = np.abs(out[1000:, 0]).max() / 10000
        assert (ratio > 0.98) if low_gain else (ratio < 0.35)


def test_write_wav_is_stereo_16_bit(tmp_path):
    path = tmp_path / "out" / "a.wav"

    write_wav(path, np.zeros((10, 2), dtype=np.int16))

    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (
            2,
            2,
            44100,
            10,
        )


class TestBuildHelpers:
    def test_attack_ticks_follow_the_keys_period(self):
        # 3579545 / 320 is about 11186 bytes a second; 11186 bytes is one second.
        assert build.attack_ticks(11186, 320) == 59
        assert build.attack_ticks(11186, 160) == 29

    def test_stolen_volumes_fall_in_doubling_bands(self):
        bands = build.volume_histogram([1, 2, 3, 4, 7, 8, 31, 32, 64])

        assert bands == {"1": 1, "2-3": 2, "4-7": 2, "8-15": 1, "16-31": 1, "32-64": 2}

    def test_a_recipe_with_an_unknown_sample_choice_is_refused(self, tmp_path):
        recipe = tmp_path / "r.toml"
        recipe.write_text(
            'sfz = "a.sfz"\nout = "o"\nbudget_bytes = 1\nprogram_bytes = 1\n'
            "[samples]\nspaceing = 3\n"
            '[[piece]]\nname = "p"\nmidi = "p.mid"\n'
        )

        with pytest.raises(SystemExit, match="unknown key spaceing"):
            build.load_recipe(recipe)

    def test_the_projects_recipe_loads(self):
        from conftest import REPO

        recipe = build.load_recipe(REPO / "examples" / "piano" / "piano.toml")

        assert [p.name for p in recipe.pieces][:2] == ["nocturne-op9-2", "bwv846"]
        assert len(recipe.pieces) == 10
        assert recipe.spec.spacing == 3
        assert recipe.layer_velocity == 64  # adding a piece must not change the samples


def _made(root, keys, decay_db):
    return PaulaSample(
        root=root,
        keys=tuple(keys),
        data=bytes(100),
        loop_start=60,
        period=320,
        periods={k: 320 - (k - root) * 18 for k in keys},
        rate=NTSC_CLOCK / 320,
        level=0.5,
        decay_db_per_s=decay_db,
        loop_similarity=1.0,
        max_cents_error=0.0,
    )


class TestKeySounds:
    def test_damped_keys_release_by_the_sfz_and_undamped_ones_never_faster_than_held(self):
        made = [_made(21, range(21, 65), 3.0), _made(108, range(65, 109), 20.0)]
        mapping = {k: 21 if k < 65 else 108 for k in range(21, 109)}
        regions = [
            Region("low.wav", lokey=21, hikey=64, lovel=57, hivel=64, ampeg_release=1.0),
            Region("high.wav", lokey=65, hikey=108, lovel=57, hivel=64, ampeg_release=5.0),
        ]

        sounds = build.key_sounds(made, mapping, regions, (57, 64))

        low, high = sounds[0], sounds[87]
        assert (low.sample, low.period, low.level) == (0, 320, 128)
        assert low.held == decay_factor(3.0)
        assert low.release == decay_factor(60.0)
        assert high.release == decay_factor(20.0)  # 60 dB / 5 s is slower than its 20 dB/s
        assert low.attack_ticks == build.attack_ticks(60, 320)


def test_play_report_counts_steals_per_minute_and_their_volumes():
    result = Result(steals=[Steal(0, 0, 3, True, 1, 2), Steal(5, 1, 9, False, 3, 4)], notes=5)

    found = build.play_report(result, length_ms=30_000)

    assert found["steals_per_minute"] == 4.0
    assert found["steals_of_held_notes"] == 1
    assert (found["stolen_volume_median"], found["stolen_volume_max"]) == (6.0, 9)
