import numpy as np
import pytest
from amiga_env.piano import build, font, light
from amiga_env.piano import screen as screen_mod
from amiga_env.piano.light import FilterLight
from conftest import REPO

RECIPE = REPO / "examples" / "piano" / "piano.toml"
FONT = font.load(REPO / "examples" / "piano" / "font.txt")
LIGHT = FilterLight(label="filter", on="F42", off="311")
BROWN = 2  # the attribution colour's register in the screens below
CLEAR = [(80, 160), (160, 240)]  # scopes well away from the light


def dark_screen(signature=None):
    """A black 320 x 200 screen whose picture has 13 colours, $654 in register 2
    and the voice traces' $5BC in register 14."""
    colours = [0] * 16
    colours[BROWN] = 0x654
    colours[14] = 0x5BC
    layout = screen_mod.Layout([], [], signature)
    return screen_mod.Screen(np.zeros((200, 320), dtype=np.uint8), colours, layout, 13)


@pytest.fixture
def spec():
    return build.load_recipe(RECIPE).screen


class TestLoad:
    def test_the_shared_recipe_has_a_filter_light_lit_red_and_unlit_dark(self):
        assert build.load_recipe(RECIPE).filter_light == LIGHT

    def test_a_recipe_without_one_loads_with_none(self, tmp_path):
        path = tmp_path / "r.toml"
        path.write_text(
            'sfz = "a.sfz"\nout = "o"\nbudget_bytes = 1\nprogram_bytes = 1\n'
            '[[piece]]\nname = "p"\nmidi = "p.mid"\n'
        )

        assert build.load_recipe(path).filter_light is None

    def test_a_table_without_an_off_colour_is_refused(self):
        with pytest.raises(SystemExit, match="no off"):
            light.load({"label": "filter", "on": "F42"})

    @pytest.mark.parametrize("colour", ["F4", "F421", "F4G", "-1F", "0x1", 42])
    def test_a_colour_that_is_not_three_hex_digits_is_refused(self, colour):
        with pytest.raises(SystemExit, match="not an OCS colour"):
            light.load({"label": "filter", "on": colour, "off": "311"})

    def test_an_empty_label_is_refused(self):
        with pytest.raises(SystemExit, match="label"):
            light.load({"label": " ", "on": "F42", "off": "311"})

    def test_lower_case_hex_is_allowed(self):
        assert light.load({"label": "f", "on": "f42", "off": "311"}).on == "f42"


class TestInclude:
    def test_the_include_names_the_register_colours_rows_and_the_traces_colour(self):
        text = light.include(LIGHT, screen_mod.Box(1, 192, 8, 199), 0x5BC)

        assert text == (
            "; light.i: made by `amiga-env piano-disk` or `piano3500-run` (light.py); "
            "do not edit.\n"
            "FILTER_LIGHT_REGISTER equ 14\n"
            "FILTER_LIGHT_ON equ $F42\n"
            "FILTER_LIGHT_OFF equ $311\n"
            "FILTER_LIGHT_TOP equ 192\n"
            "FILTER_LIGHT_END equ 199\n"
            "FILTER_LIGHT_BACK equ $5BC\n"
        )

    def test_colours_are_written_in_upper_case_with_three_digits(self):
        text = light.include(FilterLight("f", "f42", "011"), screen_mod.Box(1, 10, 8, 17), 0x5)

        assert "FILTER_LIGHT_ON equ $F42\n" in text
        assert "FILTER_LIGHT_OFF equ $011\n" in text
        assert "FILTER_LIGHT_BACK equ $005\n" in text


class TestPlace:
    def test_the_box_is_one_pixel_in_from_the_left_and_the_label_three_columns_after(self):
        place = light.place("filter", FONT, 192)

        assert place.box == screen_mod.Box(1, 192, 8, 199)  # 7 square: font height 9 - 2
        assert place.label == screen_mod.Line("filter", 11, 192)

    def test_the_box_is_centred_on_the_labels_ink_rows(self):
        place = light.place("ace", FONT, 100)  # lower case: ink rows 102 to 106

        assert (place.box.top, place.box.bottom) == (101, 108)


class TestDraw:
    def test_the_box_is_register_14_and_the_label_the_attribution_colour(self, spec):
        made, place = light.draw(dark_screen(), spec, CLEAR, LIGHT, FONT)

        box = place.box
        assert (made.indices[box.top : box.bottom, box.left : box.right] == 14).all()
        assert (made.indices == 14).sum() == 7 * 7
        rows, cols = np.nonzero(FONT.render("filter"))
        assert (made.indices[rows + place.label.top, cols + place.label.left] == BROWN).all()
        assert (made.indices == BROWN).sum() == len(rows)

    def test_the_colour_registers_are_left_as_they_were(self, spec):
        before = dark_screen()

        made, _ = light.draw(before, spec, CLEAR, LIGHT, FONT)

        assert made.colours == before.colours

    def test_without_a_signature_the_light_takes_the_row_a_signature_would(self, spec):
        made, place = light.draw(dark_screen(), spec, CLEAR, LIGHT, FONT)

        assert place.label.top == screen_mod.signature_line("filter", FONT).top
        assert made.layout.signature is None

    def test_a_bright_picture_under_the_label_is_refused(self, spec):
        bright = dark_screen()
        bright.indices[192:200, 11:32] = 1
        bright.colours[1] = 0xFFF

        with pytest.raises(SystemExit, match="label would sit on the picture"):
            light.draw(bright, spec, CLEAR, LIGHT, FONT)

    def test_a_bright_picture_under_the_box_is_refused(self, spec):
        bright = dark_screen()
        bright.indices[195, 4] = 1
        bright.colours[1] = 0xFFF

        with pytest.raises(SystemExit, match="box would sit on the picture"):
            light.draw(bright, spec, CLEAR, LIGHT, FONT)

    def test_a_scope_over_the_box_is_refused(self, spec):
        with pytest.raises(SystemExit, match="would draw over the filter light's box"):
            light.draw(dark_screen(), spec, [(0, 80)], LIGHT, FONT)

    def test_a_scope_over_the_label_is_refused(self, spec):
        with pytest.raises(SystemExit, match=r"columns 8 to 43\) would draw over .* label"):
            light.draw(dark_screen(), spec, [(8, 44)], LIGHT, FONT)

    def test_a_scope_that_ends_where_the_box_begins_is_allowed(self, spec):
        light.draw(dark_screen(), spec, [(0, 1), *CLEAR], LIGHT, FONT)

    def test_a_scope_band_that_ends_above_the_light_lets_a_scope_share_its_columns(self, spec):
        above = spec._replace(scope_band=screen_mod.Box(0, 150, 320, 190))

        light.draw(dark_screen(), above, [(8, 44)], LIGHT, FONT)

    def test_a_signature_it_would_meet_is_refused(self, spec):
        crowded = dark_screen(signature=screen_mod.Line("svetzal", 20, 192))

        with pytest.raises(SystemExit, match="overlap the signature"):
            light.draw(crowded, spec, CLEAR, LIGHT, FONT)

    def test_a_screen_without_an_attribution_colour_is_refused(self, spec):
        with pytest.raises(SystemExit, match="attribution_colour"):
            light.draw(dark_screen(), spec._replace(attribution_colour=""), CLEAR, LIGHT, FONT)


class TestScopeSpans:
    def test_the_voice_scopes_then_the_mixed_scope(self, spec):
        assert screen_mod.scope_spans(spec) == [
            (8, 44),
            (50, 86),
            (92, 128),
            (134, 170),
            (180, 288),
        ]
