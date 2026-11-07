from pathlib import Path

import pytest
from amiga_env.piano import disk
from amiga_env.piano.build import Piece, Recipe
from amiga_env.piano.samples import SampleSpec

PLAYER = Path(__file__).parents[1] / "examples" / "piano" / "player.s"


class TestMenu:
    def test_pieces_take_keys_1_to_9_then_letters(self):
        pieces = [(f"p{n}", f"Title {n}") for n in range(11)]

        keys = [e.key for e in disk.menu(pieces)]

        assert keys == list("123456789AB")

    def test_q_is_left_for_quit(self):
        assert "Q" not in disk.MENU_KEYS
        assert disk.MENU_KEYS[24:26] == "PR"

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


def test_the_index_has_a_line_a_piece_path_space_title():
    entries = disk.menu([("a", "Bach: Duet in E Minor, BWV 802"), ("b", "Haydn: Sonata")])

    assert disk.index_text(entries) == (
        "scores/01-a.score Bach: Duet in E Minor, BWV 802\nscores/02-b.score Haydn: Sonata\n"
    )


def recipe(*titles):
    return Recipe(
        sfz="s.sfz",
        out="runs/x",
        pieces=tuple(Piece(f"p{n}", "m.midi", t) for n, t in enumerate(titles)),
        spec=SampleSpec(),
        budget_bytes=1,
        program_bytes=1,
        velocity_exponent=1.5,
        layer_velocity=64,
    )


class TestTitles:
    def test_titles_come_from_the_recipe(self):
        assert disk.titles(recipe("Bach  Duet", "Haydn  Sonata")) == ["Bach  Duet", "Haydn  Sonata"]

    def test_a_piece_without_a_title_is_refused(self):
        with pytest.raises(SystemExit, match="p1: the recipe gives it no title"):
            disk.titles(recipe("Bach  Duet", ""))


class TestKeys:
    def test_each_piece_gets_its_keys_raw_code_in_order(self):
        assert disk.keys_include(11).splitlines()[1] == (
            "piece_keys: dc.b $01,$02,$03,$04,$05,$06,$07,$08,$09,$20,$35"
        )

    def test_every_menu_key_has_a_raw_code(self):
        assert set(disk.MENU_KEYS) <= disk.RAW_KEYS.keys()

    def test_q_is_left_for_quit(self):
        assert disk.RAW_KEYS["Q"] == 0x10
        assert "Q" not in disk.MENU_KEYS


class TestCredits:
    def test_the_disks_credits_name_each_source_its_licence_and_the_changes(self):
        text = (PLAYER.parent / "Credits").read_text(encoding="ascii")

        disk.check_credits(text)
        for needed in (
            "Alexander Holm",
            "https://creativecommons.org/licenses/by/3.0/",
            "freepats.zenvoid.org",
            "8 bits",
            "Google LLC (Magenta)",
            "International Piano-e-Competition",
            "https://creativecommons.org/licenses/by-nc-sa/4.0/",
            "Not for commercial use",
            "OpenAI",
            "font",
        ):
            assert needed in text

    def test_a_long_line_is_refused(self):
        with pytest.raises(SystemExit, match="over 60"):
            disk.check_credits("x" * 61)

    def test_non_ascii_is_refused(self):
        with pytest.raises(SystemExit, match="ASCII"):
            disk.check_credits("Frédéric")
