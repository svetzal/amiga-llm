from amiga_env.piano.clips import cause, release_ms, report
from amiga_env.piano.player import Ending
from amiga_env.piano.score import Event


def on(ms, key):
    return Event(ms, "on", key, 64)


def off(ms, key):
    return Event(ms, "off", key)


class TestReleaseTimes:
    def test_a_key_released_with_the_pedal_up_is_released_at_its_note_off(self):
        assert release_ms([on(0, 5), off(100, 5)]) == [100]

    def test_the_pedal_holds_a_released_key_until_the_pedal_comes_up(self):
        events = [Event(0, "down"), on(10, 5), off(100, 5), Event(300, "up")]

        assert release_ms(events) == [300]

    def test_a_key_still_down_when_the_pedal_comes_up_waits_for_its_note_off(self):
        events = [Event(0, "down"), on(10, 5), Event(50, "up"), off(80, 5)]

        assert release_ms(events) == [80]

    def test_a_note_never_released_is_released_at_the_end(self):
        assert release_ms([on(0, 5), on(40, 6), off(90, 6)]) == [90, 90]


class TestCauses:
    def test_a_steal_while_held_names_what_held_it(self):
        assert cause(Ending(0, 50, "steal", 9, True), released=100) == "steal-key"
        assert cause(Ending(0, 50, "steal", 9, False), released=100) == "steal-pedal"

    def test_an_ending_after_release_is_not_a_cut(self):
        assert cause(Ending(0, 150, "steal", 9, False), released=100) == "steal-released"
        assert cause(Ending(0, 50, "end", 9, True), released=100) == "end-released"


def test_the_report_counts_audible_cuts_while_held_per_minute():
    events = [Event(0, "down"), on(0, 1), on(0, 2), on(0, 3), off(10, 3), Event(60_000, "up")]
    endings = [
        Ending(0, 100, "steal", 9, False),
        Ending(1, 200, "restrike", 2, True),
        Ending(2, 300, "faded", 0, False),
    ]

    found = report(events, endings, length_ms=30_000)

    assert found["endings"] == {"faded-held": 1, "restrike-held": 1, "steal-pedal": 1}
    assert found["cut_while_held"] == 2
    assert found["cut_while_held_per_minute"] == 4.0
    assert found["cut_while_held_at_volume_4_up"] == 1
