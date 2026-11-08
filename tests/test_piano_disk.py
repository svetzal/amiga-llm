from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from amiga_env.piano import build, disk, font, picture
from amiga_env.piano.build import Piece, Recipe
from amiga_env.piano.samples import SampleSpec
from PIL import Image

PLAYER = Path(__file__).parents[1] / "examples" / "piano" / "player.s"
RECIPE = PLAYER.parent / "piano.toml"


class TestMenu:
    def test_pieces_take_keys_1_to_9_then_letters(self):
        pieces = [(f"p{n}", f"Title {n}") for n in range(11)]

        keys = [e.key for e in disk.menu(pieces)]

        assert keys == list("123456789AB")

    def test_q_is_left_for_quit(self):
        assert "Q" not in disk.MENU_KEYS
        assert disk.MENU_KEYS[23:25] == "PR"

    def test_f_is_left_for_the_filter(self):
        assert "F" not in disk.MENU_KEYS
        assert disk.MENU_KEYS[12:15] == "DEG"

    def test_each_score_is_numbered_in_menu_order_in_the_scores_folder(self):
        entries = disk.menu([("nocturne", "Chopin: N"), ("bwv846", "Bach: P")])

        assert [e.path for e in entries] == ["scores/01-nocturne.score", "scores/02-bwv846.score"]

    def test_more_pieces_than_keys_are_refused(self):
        with pytest.raises(SystemExit, match="33 keys"):
            disk.menu([(f"p{n}", "T") for n in range(34)])

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


class TestMenuInclude:
    def test_each_piece_gets_its_keys_raw_code_in_order(self):
        assert "piece_keys: dc.b $01,$02,$03,$04,$05,$06,$07,$08,$09,$20,$35" in (
            disk.menu_include(11, 15).splitlines()
        )

    def test_the_rotation_gap_is_given_in_seconds(self):
        assert "ROTATE_S        equ 5" in disk.menu_include(3, 5).splitlines()

    @pytest.mark.parametrize("seconds", [0, -1, 601, 1.5])
    def test_a_gap_outside_1_to_600_whole_seconds_is_refused(self, seconds):
        with pytest.raises(SystemExit, match="rotate_s"):
            disk.menu_include(3, seconds)

    def test_the_recipe_rotates_after_15_seconds(self):
        assert build.load_recipe(RECIPE).rotate_s == 15

    def test_every_menu_key_has_a_raw_code(self):
        assert set(disk.MENU_KEYS) <= disk.RAW_KEYS.keys()

    def test_q_is_left_for_quit(self):
        assert disk.RAW_KEYS["Q"] == 0x10
        assert "Q" not in disk.MENU_KEYS

    def test_f_has_its_raw_code_for_the_filter_key(self):
        assert disk.RAW_KEYS["F"] == 0x23


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


class TestScreen:
    def test_a_click_point_is_on_each_pieces_line(self):
        from amiga_env.piano import build

        recipe = build.load_recipe(PLAYER.parent / "piano.toml")

        points = disk.click_points(recipe, PLAYER.parents[2])

        assert points["nocturne-op9-2"] == (202, 12)
        assert points["bwv846"] == (202, 23)
        assert len(points) == len(recipe.pieces)

    def test_the_player_takes_its_rows_and_keys_from_the_made_includes(self):
        source = PLAYER.read_text()

        assert 'include "screen.i"' in source and "SCREEN_TABLES" in source
        assert 'include "menu.i"' in source
        assert f'menu_keys:      dc.b "{disk.MENU_KEYS}"' in source
        assert 'include "light.i"' in source


FONT_PATH = PLAYER.parent / "font.txt"


class TestScreenData:
    def test_a_recipe_without_a_filter_light_is_refused(self, tmp_path):
        bare = replace(build.load_recipe(RECIPE), filter_light=None, out=str(tmp_path))

        with pytest.raises(SystemExit, match=r"no \[filter_light\]"):
            disk.screen_data(bare, PLAYER.parents[2], tmp_path / "m68k")

    def test_a_recipe_without_a_screen_is_refused(self, tmp_path):
        bare = replace(build.load_recipe(RECIPE), screen=None, out=str(tmp_path))

        with pytest.raises(SystemExit, match=r"no \[screen\]"):
            disk.screen_data(bare, PLAYER.parents[2], tmp_path / "m68k")


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    """The A500 screen data, as `piano-disk` writes it: the include folder and `out`."""
    out = tmp_path_factory.mktemp("exp004")
    recipe = replace(build.load_recipe(RECIPE), out=str(out))
    disk.screen_data(recipe, PLAYER.parents[2], out / "m68k")
    return out


class TestWrittenScreen:
    def test_the_picture_has_the_light_in_the_lower_left_in_register_14(self, written):
        indices, colours = picture.read_ilbm((written / "m68k" / "title.ilbm").read_bytes())

        assert (indices[192:199, 1:8] == 14).all()
        brown = colours.index(0x654)
        rows, cols = np.nonzero(font.load(FONT_PATH).render("filter"))
        assert (indices[rows + 192, cols + 11] == brown).all()

    def test_register_14_stays_the_voice_trace_colour(self, written):
        _, colours = picture.read_ilbm((written / "m68k" / "title.ilbm").read_bytes())

        assert colours[14] == 0x5BC

    def test_light_i_is_written_beside_screen_i_and_menu_i(self, written):
        data = written / "m68k"

        assert (data / "light.i").read_text(encoding="ascii") == (
            "; light.i: made by `amiga-env piano-disk` or `piano3500-run` (light.py); "
            "do not edit.\n"
            "FILTER_LIGHT_REGISTER equ 14\n"
            "FILTER_LIGHT_ON equ $F42\n"
            "FILTER_LIGHT_OFF equ $311\n"
            "FILTER_LIGHT_TOP equ 192\n"
            "FILTER_LIGHT_END equ 199\n"
            "FILTER_LIGHT_BACK equ $5BC\n"
        )
        assert {"title.ilbm", "screen.i", "menu.i", "light.i"} <= {p.name for p in data.iterdir()}

    def test_the_preview_shows_the_light(self, written):
        preview = np.asarray(Image.open(written / "title-preview.png").convert("RGB"))

        box = preview[693:716, 3:24]  # rows 192 to 198 and columns 1 to 7, enlarged 3.6 and 3 times
        assert (box == picture.rgb_of(0x5BC)).all()
