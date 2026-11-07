import pytest
from amiga_env.piano.score import Event
from amiga_env.piano.survey import (
    ascii_text,
    menu_title,
    percentile,
    polyphony,
    read_catalogue,
    surnames,
)


def on(ms, key):
    return Event(ms, "on", key, 64)


def off(ms, key):
    return Event(ms, "off", key)


class TestPolyphony:
    def test_keys_held_are_weighted_by_how_long_they_last(self):
        # one key for 900 ms, then three keys for 100 ms
        events = [on(0, 1), on(900, 2), on(900, 3), off(1000, 1), off(1000, 2), off(1000, 3)]

        found = polyphony(events)

        assert (found.held_p95, found.held_max) == (3, 3)
        assert found.ringing_max == 3

    def test_the_pedal_keeps_released_keys_ringing_until_it_comes_up(self):
        events = [
            Event(0, "down"),
            on(0, 1),
            off(100, 1),
            on(100, 2),
            off(200, 2),
            on(200, 3),
            Event(300, "up"),
            off(400, 3),
        ]

        found = polyphony(events)

        assert found.held_max == 1
        assert found.ringing_max == 3
        assert found.pedal_share == pytest.approx(0.75)

    def test_a_key_struck_again_under_the_pedal_is_one_string(self):
        events = [Event(0, "down"), on(0, 1), off(10, 1), on(20, 1), off(30, 1), Event(40, "up")]

        assert polyphony(events).ringing_max == 1

    def test_no_events_is_silence(self):
        assert polyphony([]).ringing_max == 0


class TestPercentile:
    def test_the_count_that_the_share_of_time_is_at_or_under(self):
        assert percentile({1: 90, 5: 10}, 0.95) == 5
        assert percentile({1: 95, 5: 5}, 0.95) == 1

    def test_no_time_is_zero(self):
        assert percentile({}, 0.95) == 0


class TestMenuText:
    def test_accents_are_dropped_and_curly_quotes_made_straight(self):
        assert ascii_text("Frédéric Chopin, “Voiles” Leoš Janáček") == (
            'Frederic Chopin, "Voiles" Leos Janacek'
        )

    def test_a_composer_is_their_surname_and_arrangers_keep_theirs(self):
        assert surnames("Johann Sebastian Bach") == "Bach"
        assert surnames("Franz Schubert / Franz Liszt") == "Schubert / Liszt"

    def test_a_title_that_fits_is_kept_whole(self):
        assert menu_title("Frédéric Chopin", "Nocturne Op. 9 No. 2 in E-flat Major") == (
            "Chopin: Nocturne Op. 9 No. 2 in E-flat Major"
        )

    def test_a_long_title_loses_its_last_clauses_first(self):
        title = "Sonata No. 18 in E-flat Major, Op. 31 No. 3, First Movement"

        assert menu_title("Ludwig van Beethoven", title) == (
            "Beethoven: Sonata No. 18 in E-flat Major, Op. 31 No. 3"
        )

    def test_a_long_title_without_clauses_is_cut_after_a_word(self):
        found = menu_title("A B", "word " * 20, width=20)

        assert found == "B: word word word..."
        assert len(found) <= 20


def test_the_catalogue_is_read_from_maestros_csv(tmp_path):
    path = tmp_path / "maestro.csv"
    path.write_text(
        "canonical_composer,canonical_title,split,year,midi_filename,audio_filename,duration\n"
        'Frédéric Chopin,"Nocturne, Op. 9",train,2011,2011/a.midi,2011/a.wav,220.5\n',
        encoding="utf-8",
    )

    [entry] = read_catalogue(path)

    assert (entry.composer, entry.title, entry.year, entry.midi, entry.duration_s) == (
        "Frédéric Chopin",
        "Nocturne, Op. 9",
        2011,
        "2011/a.midi",
        220.5,
    )
