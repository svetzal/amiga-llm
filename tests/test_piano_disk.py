from pathlib import Path

import pytest
from amiga_env.piano import disk
from amiga_env.piano.build import Piece, Recipe
from amiga_env.piano.samples import SampleSpec
from amiga_env.piano.survey import Entry

PLAYER = Path(__file__).parents[1] / "examples" / "piano" / "player.s"


class TestMenu:
    def test_pieces_take_keys_1_to_9_then_letters(self):
        pieces = [(f"p{n}", f"Title {n}") for n in range(11)]

        keys = [e.key for e in disk.menu(pieces)]

        assert keys == list("123456789AB")

    def test_q_is_left_for_quit(self):
        assert "Q" not in disk.MENU_KEYS
        assert disk.MENU_KEYS[24:26] == "PR"

    def test_the_player_has_the_same_keys(self):
        assert f'menu_keys:      dc.b "{disk.MENU_KEYS}"' in PLAYER.read_text()

    def test_each_score_is_numbered_in_menu_order_in_the_scores_folder(self):
        entries = disk.menu([("nocturne", "Chopin: N"), ("bwv846", "Bach: P")])

        assert [e.path for e in entries] == ["scores/01-nocturne.score", "scores/02-bwv846.score"]

    def test_more_pieces_than_keys_are_refused(self):
        with pytest.raises(SystemExit, match="34 keys"):
            disk.menu([(f"p{n}", "T") for n in range(35)])

    @pytest.mark.parametrize("title", ["", "Chopin: Nocturne\nOp. 9", "Frédéric"])
    def test_a_title_is_one_line_of_ascii(self, title):
        with pytest.raises(SystemExit, match="ASCII"):
            disk.menu([("p", title)])

    def test_a_score_name_must_suit_ofs(self):
        with pytest.raises(SystemExit):
            disk.menu([("x" * 22, "T")])

    def test_the_menu_lists_keys_titles_and_quit(self):
        entries = disk.menu([("a", "Bach: Duet"), ("b", "Haydn: Sonata")])

        assert disk.menu_lines(entries) == [
            " 1  Bach: Duet",
            " 2  Haydn: Sonata",
            " Q  Quit",
            "Press a key: ",
        ]


def test_the_index_has_a_line_a_piece_path_space_title():
    entries = disk.menu([("a", "Bach: Duet in E Minor, BWV 802"), ("b", "Haydn: Sonata")])

    assert disk.index_text(entries) == (
        "scores/01-a.score Bach: Duet in E Minor, BWV 802\nscores/02-b.score Haydn: Sonata\n"
    )


def recipe(*midis):
    return Recipe(
        sfz="s.sfz",
        out="runs/x",
        pieces=tuple(Piece(f"p{n}", m) for n, m in enumerate(midis)),
        spec=SampleSpec(),
        budget_bytes=1,
        program_bytes=1,
        velocity_exponent=1.5,
        layer_velocity=64,
        catalogue="maestro/v3/maestro.csv",
    )


class TestTitles:
    def test_titles_come_from_the_catalogue_entry_for_each_midi_file(self):
        catalogue = [
            Entry("Frédéric Chopin", "Nocturne Op. 9 No. 2", 2011, "2011/a.midi", 220.0),
            Entry("Claude Debussy", "Prelude No. 6", 2018, "2018/b.midi", 250.0),
        ]

        found = disk.titles(recipe("maestro/v3/2018/b.midi", "maestro/v3/2011/a.midi"), catalogue)

        assert found == ["Debussy: Prelude No. 6", "Chopin: Nocturne Op. 9 No. 2"]

    def test_a_piece_missing_from_the_catalogue_is_refused(self):
        with pytest.raises(SystemExit, match="not in"):
            disk.titles(recipe("maestro/v3/2018/c.midi"), [])
