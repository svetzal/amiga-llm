from dataclasses import replace

import numpy as np
import pytest
from amiga_env.piano import build3500, font, picture, run3500
from amiga_env.piano import screen as screen_mod
from amiga_env.piano.build3500 import (
    FilterLight,
    Scopes,
    check_scopes,
    load_filter_light,
    load_scopes,
)
from conftest import REPO

RECIPE = REPO / "examples" / "piano3500" / "piano.toml"


class TestScopes:
    def test_the_projects_recipe_has_two_quarter_screen_scopes_side_by_side_in_the_middle(self):
        recipe = build3500.load_recipe(RECIPE)

        assert recipe.scopes == Scopes(left=(80, 160), width=80)

    def test_a_recipe_without_scopes_loads_with_none(self, tmp_path):
        path = tmp_path / "r.toml"
        path.write_text(
            'sfz = "a.sfz"\nout = "o"\nfull_volume = 1\nbudget_bytes = 1\n'
            '[[piece]]\nname = "p"\nmidi = "p.mid"\n'
        )

        assert build3500.load_recipe(path).scopes is None

    def test_a_table_without_a_width_is_refused(self):
        with pytest.raises(SystemExit, match="no width"):
            load_scopes({"left": [80, 160]})

    @pytest.mark.parametrize(
        ("left", "width", "message"),
        [
            ((80,), 80, "two lefts"),
            ((80, 160, 240), 16, "two lefts"),
            ((84, 160), 64, "column 84 does not start on a byte"),
            ((80, 160), 72, "not a multiple of 16"),
            ((80, 160), 0, "not a multiple of 16"),
            ((-16, 160), 80, "leaves the screen"),
            ((80, 256), 80, "from column 256 to 336 leaves the screen"),
            ((80, 144), 80, "overlap"),
            ((160, 80), 96, "overlap"),
        ],
    )
    def test_scopes_that_the_player_cannot_draw_are_refused(self, left, width, message):
        with pytest.raises(SystemExit, match=message):
            check_scopes(Scopes(left=left, width=width))

    def test_scopes_that_touch_are_allowed(self):
        check_scopes(Scopes(left=(0, 160), width=160))


class TestScopesInclude:
    def test_the_include_names_each_scopes_first_column_and_their_width(self):
        text = run3500.scopes_include(Scopes(left=(80, 160), width=80))

        assert text == (
            "; scopes.i: made by `amiga-env piano3500-run` (run3500.py); do not edit.\n"
            "STEREO_LEFT_L   equ 80\n"
            "STEREO_LEFT_R   equ 160\n"
            "STEREO_WIDTH    equ 80\n"
        )

    def test_screen_data_refuses_a_recipe_without_scopes(self, tmp_path):
        recipe = build3500.load_recipe(RECIPE)
        bare = replace(recipe, scopes=None)

        with pytest.raises(SystemExit, match=r"no \[scopes\]"):
            run3500.screen_data(bare, tmp_path)


FONT = font.load(REPO / "examples" / "piano" / "font.txt")
LIGHT = FilterLight(label="filter", on="F42", off="311")
BROWN = 2  # the attribution colour's register in the screens below


def dark_screen(signature=None):
    """A black 320 x 200 screen whose picture has 13 colours, $654 in register 2."""
    colours = [0] * 16
    colours[BROWN] = 0x654
    layout = screen_mod.Layout([], [], signature)
    return screen_mod.Screen(np.zeros((200, 320), dtype=np.uint8), colours, layout, 13)


class TestFilterLight:
    def test_the_projects_recipe_has_a_filter_light_lit_red_and_unlit_dark(self):
        recipe = build3500.load_recipe(RECIPE)

        assert recipe.filter_light == LIGHT

    def test_a_recipe_without_one_loads_with_none(self, tmp_path):
        path = tmp_path / "r.toml"
        path.write_text(
            'sfz = "a.sfz"\nout = "o"\nfull_volume = 1\nbudget_bytes = 1\n'
            '[[piece]]\nname = "p"\nmidi = "p.mid"\n'
        )

        assert build3500.load_recipe(path).filter_light is None

    def test_a_table_without_an_off_colour_is_refused(self):
        with pytest.raises(SystemExit, match="no off"):
            load_filter_light({"label": "filter", "on": "F42"})

    @pytest.mark.parametrize("colour", ["F4", "F421", "F4G", "-1F", "0x1", 42])
    def test_a_colour_that_is_not_three_hex_digits_is_refused(self, colour):
        with pytest.raises(SystemExit, match="not an OCS colour"):
            load_filter_light({"label": "filter", "on": colour, "off": "311"})

    def test_an_empty_label_is_refused(self):
        with pytest.raises(SystemExit, match="label"):
            load_filter_light({"label": " ", "on": "F42", "off": "311"})

    def test_lower_case_hex_is_allowed(self):
        assert load_filter_light({"label": "f", "on": "f42", "off": "311"}).on == "f42"


class TestLightInclude:
    def test_the_include_names_register_14_and_both_colours(self):
        assert run3500.light_include(LIGHT) == (
            "; light.i: made by `amiga-env piano3500-run` (run3500.py); do not edit.\n"
            "FILTER_LIGHT_REGISTER equ 14\n"
            "FILTER_LIGHT_ON equ $F42\n"
            "FILTER_LIGHT_OFF equ $311\n"
        )

    def test_screen_data_refuses_a_recipe_without_a_filter_light(self, tmp_path):
        bare = replace(build3500.load_recipe(RECIPE), filter_light=None)

        with pytest.raises(SystemExit, match=r"no \[filter_light\]"):
            run3500.screen_data(bare, tmp_path)


class TestPlaceFilterLight:
    def test_the_box_is_one_pixel_in_from_the_left_and_the_label_three_columns_after(self):
        place = run3500.place_filter_light("filter", FONT, 192)

        assert place.box == screen_mod.Box(1, 192, 8, 199)  # 7 square: font height 9 - 2
        assert place.label == screen_mod.Line("filter", 11, 192)

    def test_the_box_is_centred_on_the_labels_ink_rows(self):
        place = run3500.place_filter_light("ace", FONT, 100)  # lower case: ink rows 102 to 106

        assert (place.box.top, place.box.bottom) == (101, 108)


class TestDrawFilterLight:
    @pytest.fixture
    def spec(self):
        return build3500.load_recipe(RECIPE).screen

    @pytest.fixture
    def scopes(self):
        return Scopes(left=(80, 160), width=80)

    def test_the_box_is_register_14_and_the_label_the_attribution_colour(self, spec, scopes):
        made, place = run3500.draw_filter_light(dark_screen(), spec, scopes, LIGHT, FONT)

        box = place.box
        assert (made.indices[box.top : box.bottom, box.left : box.right] == 14).all()
        assert (made.indices == 14).sum() == 7 * 7
        rows, cols = np.nonzero(FONT.render("filter"))
        assert (made.indices[rows + place.label.top, cols + place.label.left] == BROWN).all()
        assert (made.indices == BROWN).sum() == len(rows)
        assert made.colours[14] == 0x311

    def test_a_bright_picture_under_the_label_is_refused(self, spec, scopes):
        bright = dark_screen()
        bright.indices[192:200, 11:32] = 1
        bright.colours[1] = 0xFFF

        with pytest.raises(SystemExit, match="label would sit on the picture"):
            run3500.draw_filter_light(bright, spec, scopes, LIGHT, FONT)

    def test_a_scope_over_the_box_is_refused(self, spec):
        with pytest.raises(SystemExit, match="would draw over the filter light's box"):
            run3500.draw_filter_light(
                dark_screen(), spec, Scopes(left=(0, 160), width=80), LIGHT, FONT
            )

    def test_a_scope_over_the_label_is_refused(self, spec):
        with pytest.raises(SystemExit, match="would draw over the filter light's label"):
            run3500.draw_filter_light(
                dark_screen(), spec, Scopes(left=(16, 160), width=64), LIGHT, FONT
            )

    def test_a_signature_it_would_meet_is_refused(self, spec, scopes):
        crowded = dark_screen(signature=screen_mod.Line("svetzal", 20, 192))

        with pytest.raises(SystemExit, match="overlap the signature"):
            run3500.draw_filter_light(crowded, spec, scopes, LIGHT, FONT)

    def test_a_screen_without_an_attribution_colour_is_refused(self, spec, scopes):
        with pytest.raises(SystemExit, match="attribution_colour"):
            run3500.draw_filter_light(
                dark_screen(), spec._replace(attribution_colour=""), scopes, LIGHT, FONT
            )


@pytest.fixture(scope="module")
def written(tmp_path_factory):
    """The A3500 screen data, as `piano3500-run` writes it."""
    data = tmp_path_factory.mktemp("m68030")
    run3500.screen_data(build3500.load_recipe(RECIPE), data)
    return data


class TestWrittenScreen:
    def test_the_picture_has_the_light_in_the_lower_left_and_register_14_unlit(self, written):
        indices, colours = picture.read_ilbm((written / "title.ilbm").read_bytes())

        assert colours[14] == 0x311
        assert (indices[192:199, 1:8] == 14).all()
        assert (indices == 14).sum() == 7 * 7
        brown = colours.index(0x654)
        rows, cols = np.nonzero(FONT.render("filter"))
        assert (indices[rows + 192, cols + 11] == brown).all()

    def test_light_i_is_written_beside_the_other_includes(self, written):
        text = (written / "light.i").read_text(encoding="ascii")

        assert text == run3500.light_include(LIGHT)
        assert {"screen.i", "scopes.i", "menu.i", "title-preview.png"} <= {
            p.name for p in written.iterdir()
        }
