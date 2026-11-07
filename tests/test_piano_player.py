from itertools import pairwise

import pytest
from amiga_env.piano.player import (
    FULL_VOLUME,
    KeySound,
    LogRow,
    Write,
    decay_factor,
    play,
    tick_ms,
    velocity_table,
)
from amiga_env.piano.score import KEYS, Event

NO_DECAY = 0xFFFF
HALF = 0x8000


def keys(held=NO_DECAY, release=HALF, level=256, attack_ticks=0):
    return [KeySound(key % 3, 200 + key, level, held, release, attack_ticks) for key in range(KEYS)]


def table(volume):
    """Every velocity plays at this Paula volume."""
    return (0,) + (volume << 8,) * 127


def on(ms, key, velocity=100):
    return Event(ms, "on", key, velocity)


def starts(result):
    return [(w.ms, w.voice) for w in result.writes if w.kind == "start"]


class TestTables:
    def test_velocity_table_spans_1_to_64_and_rises(self):
        t = velocity_table(1.5)

        assert t[0] == 0
        assert t[1] == 256 and t[127] == FULL_VOLUME
        assert all(a <= b for a, b in pairwise(t[1:]))
        assert t[64] >> 8 == 22

    @pytest.mark.parametrize(("db", "factor"), [(0, 0xFFFF), (6.0206 * 60, 0x8000)])
    def test_decay_factor(self, db, factor):
        assert decay_factor(db) == pytest.approx(factor, abs=1)

    def test_ticks_fall_on_whole_milliseconds_at_60_hz(self):
        assert [tick_ms(k) for k in range(5)] == [0, 16, 33, 50, 66]
        assert tick_ms(60) == 1000


class TestChoosingAVoice:
    def test_free_voices_are_taken_lowest_first(self):
        result = play([on(0, 1), on(0, 2), on(0, 3)], keys(), table(40))

        assert starts(result) == [(0, 0), (0, 1), (0, 2)]

    def test_striking_a_sounding_key_again_reuses_its_voice(self):
        result = play([on(0, 5), on(0, 6), on(10, 5)], keys(), table(40))

        assert starts(result) == [(0, 0), (0, 1), (10, 0)]
        assert result.restrikes == 1
        assert result.steals == []

    def test_with_every_voice_busy_the_quietest_is_stolen(self):
        quiet = (0,) + tuple((v << 8) for v in range(1, 128))
        events = [on(0, 1, 50), on(0, 2, 9), on(0, 3, 70), on(0, 4, 60), on(0, 9, 100)]

        result = play(events, keys(), quiet)

        assert starts(result)[-1] == (0, 1)
        steal = result.steals[0]
        assert (steal.voice, steal.volume, steal.old_key, steal.new_key) == (1, 9, 2, 9)
        assert steal.held

    def test_on_a_tie_the_oldest_note_is_stolen(self):
        events = [on(0, 1), on(1, 2), on(2, 3), on(3, 4), on(4, 9)]

        result = play(events, keys(), table(30))

        assert starts(result)[-1] == (4, 0)

    def test_a_key_with_no_sound_is_dropped(self):
        sounds = keys()
        sounds[0] = None

        result = play([on(0, 0)], sounds, table(30))

        assert result.dropped == 1
        assert result.writes == []

    def test_volume_is_velocity_times_the_samples_level(self):
        result = play([on(0, 1)], keys(level=128), table(40))

        assert result.writes[0] == Write(0, 0, "start", sample=1, period=201, volume=20)


class TestDecay:
    def test_a_released_key_fades_at_its_release_factor_and_stops(self):
        result = play([on(0, 1), Event(0, "off", 1)], keys(), table(64))

        volumes = [w.volume for w in result.writes if w.kind == "volume"]
        assert volumes == [32, 16, 8, 4, 2, 1]
        assert result.writes[-1].kind == "stop"

    def test_a_held_key_fades_at_its_held_factor(self):
        result = play([on(0, 1), Event(100, "off", 1)], keys(held=HALF, release=0), table(64))

        assert [w.volume for w in result.writes[1:4]] == [32, 16, 8]

    def test_the_sustain_pedal_holds_a_released_key(self):
        events = [Event(0, "down"), on(0, 1), Event(1, "off", 1), Event(100, "up")]

        result = play(events, keys(held=NO_DECAY, release=HALF), table(64))

        before_up = [w.volume for w in result.writes if w.kind == "volume" and w.ms < 100]
        after_up = [w.volume for w in result.writes if w.kind == "volume" and w.ms >= 100]
        assert min(before_up) >= 60
        assert after_up[:2] == [31, 15]

    def test_a_held_note_does_not_decay_during_its_recorded_attack(self):
        result = play([on(0, 1)], keys(held=HALF, attack_ticks=3), table(64))

        first = next(w for w in result.writes if w.kind == "volume")
        assert first.ms == tick_ms(3)

    def test_the_release_applies_during_the_attack(self):
        events = [on(0, 1), Event(0, "off", 1)]

        result = play(events, keys(release=HALF, attack_ticks=50), table(64))

        assert next(w for w in result.writes if w.kind == "volume").ms == 0

    def test_events_at_a_ticks_millisecond_come_before_the_tick(self):
        result = play([on(16, 1), Event(16, "off", 1)], keys(), table(64))

        assert next(w for w in result.writes if w.kind == "volume").ms == 16


def test_the_log_has_every_voice_on_every_tick():
    result = play([on(0, 1), Event(0, "off", 1)], keys(), table(64))

    ticks = {row.tick for row in result.log}
    assert len(result.log) == 4 * len(ticks)
    assert result.log[0] == LogRow(0, 0, 0, 1, 1, 201, 32)
    assert result.log[1] == LogRow(0, 0, 1, -1, -1, 0, 0)
