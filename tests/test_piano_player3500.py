import numpy as np
import pytest
from amiga_env.piano import mixer
from amiga_env.piano.player3500 import (
    FADE_STEP,
    LIMIT_BLOCKS,
    LOG_BLOCK_BYTES,
    LOG_HEADER_BYTES,
    SILENT,
    STOP_VOLUME,
    VOICES,
    Instrument,
    MixSample,
    Sound,
    decay_factor,
    play,
    read_log,
)
from amiga_env.piano.score import KEYS, Event

LEVEL = 4000  # every sample holds this value
LENGTH, LOOP_START = 30000, 20000
NO_DECAY = 0xFFFF  # still takes 1 off a volume each block
FOREVER = 1 << 20  # attack blocks: a held note never decays
HALF_GAIN = 32768


def samples(count=2, level=LEVEL):
    data = np.full(LENGTH, level, dtype=np.int16)
    return [MixSample(mixer.padded(data, LOOP_START), LENGTH, LOOP_START)] * count


def instrument(volume=8000, held=NO_DECAY, release=NO_DECAY, attack_blocks=0, pan=None):
    """Two layers: velocity 1-63 plays sample 0, 64-127 sample 1. One root."""
    sounds = tuple(
        tuple(Sound(layer, mixer.ONE, held, release, attack_blocks) for layer in (0, 1))
        for _ in range(KEYS)
    )
    pans = tuple(pan or (HALF_GAIN, HALF_GAIN) for _ in range(KEYS))
    volumes = ((0,) + (volume,) * 127,)
    layer_of = tuple(0 if v < 64 else 1 for v in range(128))
    return Instrument(sounds, pans, (0,) * KEYS, volumes, layer_of)


def on(ms, key, velocity=100):
    return Event(ms, "on", key, velocity)


def off(ms, key):
    return Event(ms, "off", key)


def contribution(volume=8000, gain=HALF_GAIN):
    """What one voice adds to a side for each output sample."""
    return LEVEL * mixer.multiplier(volume, gain) >> 16


def blocks(result):
    return read_log(result.log)


def voice_record(result, block, voice):
    return blocks(result)[block][1][voice]


class TestTiming:
    def test_a_note_starts_at_its_own_sample_inside_a_block(self):
        result = play([on(19, 5)], instrument(), samples())

        start = mixer.sample_of_ms(19)
        assert start == 531
        assert result.left[start - 1] == 0
        assert result.left[start] == contribution()

    def test_play_goes_on_until_every_voice_is_silent(self):
        result = play([on(0, 5)], instrument(release=0), samples())

        assert result.endings[0].cause == "end"  # held with no decay: still sounding
        assert result.blocks > LIMIT_BLOCKS


class TestChoosingAVoice:
    def test_free_voices_are_taken_lowest_first(self):
        result = play([on(0, 1), on(0, 2), on(0, 3)], instrument(), samples())

        assert [voice_record(result, 0, v)[0] for v in range(4)] == [1, 2, 3, SILENT]

    def test_sixteen_notes_sound_at_once(self):
        result = play([on(0, k) for k in range(VOICES)], instrument(), samples())

        assert result.steals == []
        assert result.left[0] == VOICES * contribution()

    def test_a_seventeenth_note_steals_a_key_up_voice_before_a_quieter_held_one(self):
        events = [on(0, k, 100) for k in range(VOICES)]
        events.append(off(10, 7))
        events.append(on(20, 40))

        result = play(events, instrument(), samples())

        assert [(s.voice, s.old_key) for s in result.steals] == [(7, 7)]

    def test_with_every_key_down_the_quietest_is_stolen_then_the_oldest(self):
        ins = instrument()
        volumes = list(ins.volumes[0])
        volumes[30] = 100
        quiet = Instrument(ins.sounds, ins.pans, ins.roots, (tuple(volumes),), ins.layer_of)
        events = [on(0, k, 100) for k in range(VOICES - 1)] + [on(5, 50, 30), on(20, 60)]

        result = play(events, quiet, samples())

        assert [(s.voice, s.old_key, s.held) for s in result.steals] == [(15, 50, True)]

    def test_a_restrike_takes_its_keys_own_voice(self):
        result = play([on(0, 1), on(0, 2), on(100, 1)], instrument(), samples())

        assert result.restrikes == 1
        assert result.endings[0].cause == "restrike"
        assert result.steals == []


class TestCutting:
    def test_a_cut_note_fades_in_quarters_and_the_new_note_starts_after_it(self):
        result = play([on(0, 1), on(100, 1)], instrument(attack_blocks=FOREVER), samples())

        cut = mixer.sample_of_ms(100)
        full = mixer.multiplier(8000, HALF_GAIN)
        expected = [LEVEL * mixer.faded(full, q) >> 16 for q in (4, 3, 2, 1)]
        heard = [result.left[cut - 1]] + [result.left[cut + i * FADE_STEP] for i in (0, 1, 2)]
        assert heard == expected
        assert result.left[cut + 3 * FADE_STEP] == contribution()

    def test_a_fade_carries_across_a_block_boundary(self):
        cut_ms = 18  # sample 503: the fade ends in the next block
        result = play([on(0, 1), on(cut_ms, 1)], instrument(attack_blocks=FOREVER), samples())

        cut = mixer.sample_of_ms(cut_ms)
        assert cut + 3 * FADE_STEP > mixer.BLOCK
        assert result.left[cut + 2 * FADE_STEP] == LEVEL * mixer.faded(4000, 1) >> 16
        assert result.left[cut + 3 * FADE_STEP] == contribution()

    def test_a_note_for_a_waiting_voice_replaces_the_waiting_note(self):
        events = [on(0, 1), on(100, 1, 100), on(101, 1, 30)]

        result = play(events, instrument(), samples())

        assert result.superseded == 1
        start = mixer.sample_of_ms(100) + 3 * FADE_STEP
        block = start // mixer.BLOCK
        assert voice_record(result, block, 0)[1] == 0  # the new note plays layer 0
        assert result.left[start] == contribution()


class TestLayers:
    def test_velocity_picks_the_layer_and_so_the_sample(self):
        result = play([on(0, 1, 63), on(0, 2, 64)], instrument(), samples())

        assert voice_record(result, 0, 0)[1] == 0
        assert voice_record(result, 0, 1)[1] == 1


class TestVolume:
    def test_a_held_note_is_not_decayed_while_its_attack_plays(self):
        result = play([on(0, 1)], instrument(held=0x8000, attack_blocks=3), samples())

        volumes = [voice_record(result, b, 0)[2] for b in range(6)]
        assert volumes == [8000, 8000, 8000, 8000, 4000, 2000]

    def test_a_released_note_decays_by_its_release_factor_and_stops(self):
        result = play([on(0, 1), off(10, 1)], instrument(release=0x4000), samples())

        volumes = [voice_record(result, b, 0)[2] for b in range(5)]
        assert volumes == [8000, 2000, 500, 125, 31]
        assert result.endings[0].cause == "faded"
        assert 31 * 0x4000 >> 16 < STOP_VOLUME
        assert voice_record(result, 5, 0)[:2] == (SILENT, SILENT)  # stopped at block 5

    def test_the_pedal_holds_a_released_note(self):
        events = [Event(0, "down"), on(0, 1), off(10, 1)]

        result = play(events, instrument(held=0x8000, release=0x1000), samples())

        assert voice_record(result, 1, 0)[2] == 4000

    def test_decay_factor_fades_db_per_second(self):
        assert decay_factor(0) == 0xFFFF
        factor = decay_factor(60)
        assert (factor / 65536) ** mixer.BLOCK_HZ == pytest.approx(0.001, rel=0.01)


class TestPanAndSums:
    def test_width_0_gives_the_same_sum_on_both_sides(self):
        result = play([on(0, 1), on(5, 80)], instrument(pan=(46340, 46340)), samples())

        assert np.array_equal(result.left, result.right)

    def test_a_sum_that_does_not_fit_16_bits_wraps_and_is_counted(self):
        events = [on(0, k) for k in range(VOICES)]

        loud = instrument(volume=32767, pan=(65535, 65535), attack_blocks=FOREVER)

        result = play(events, loud, samples(level=32767))

        true_sum = VOICES * (32767 * mixer.multiplier(32767, 65535) >> 16)
        assert result.peak == true_sum
        assert result.overflows > 0
        assert int(result.left[0]) == (true_sum + 32768) % 65536 - 32768


class TestLog:
    def test_the_log_has_a_header_and_a_record_per_block(self):
        result = play([on(0, 1), off(30, 1)], instrument(release=0x4000), samples())

        assert result.log[:4] == b"P35L"
        assert len(result.log) == LOG_HEADER_BYTES + result.blocks * LOG_BLOCK_BYTES

    def test_each_block_carries_the_checksum_of_its_sums(self):
        result = play([on(3, 1), on(40, 9)], instrument(), samples())

        for block, (checksum, _) in enumerate(blocks(result)[:4]):
            span = slice(block * mixer.BLOCK, (block + 1) * mixer.BLOCK)
            assert checksum == mixer.checksum(result.left[span], result.right[span])

    def test_a_voice_record_shows_key_sample_volume_multipliers_and_phase(self):
        result = play([on(0, 1)], instrument(), samples())

        key, sample, volume, left, right, whole, fraction = voice_record(result, 1, 0)
        full = mixer.multiplier(8000, HALF_GAIN)
        assert (key, sample, volume, left, right) == (1, 1, 7999, full - 1, full - 1)
        assert (whole, fraction) == (2 * mixer.BLOCK, 0)
