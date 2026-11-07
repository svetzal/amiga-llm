from pathlib import Path

import numpy as np
import pytest
from amiga_env.piano import build, font, picture, screen

REPO = Path(__file__).parents[1]
RECIPE = REPO / "examples" / "piano" / "piano.toml"

TINY = font.parse(
    ["height 3", "baseline 2", "gap 1", "", "char A", "##", "##", "", "char space", "."]
)


def spec(**changes):
    base = screen.ScreenSpec(
        master="m.png",
        font="f.txt",
        picture=picture.PictureSpec(),
        list_box=screen.Box(190, 8, 318, 152),
        line_pitch=11,
        attribution=("A A",),
        attribution_gap=14,
        text="EDB",
        highlight="B95",
        voice_trace="5BC",
        mix_trace="DB8",
        scope_band=screen.Box(0, 152, 320, 197),
        voice_scopes=(8, 50, 92, 134),
        voice_scope_width=36,
        mix_scope=(180, 132),
        scope_centre=174,
    )
    return base._replace(**changes)


class TestLayout:
    def test_each_piece_has_a_line_at_a_fixed_pitch(self):
        found = screen.layout(["A", "AA", "A"], spec(), TINY)

        assert [line.top for line in found.pieces] == [8, 19, 30]
        assert {line.left for line in found.pieces} == {190}

    def test_the_attribution_follows_the_list_after_its_gap(self):
        found = screen.layout(["A", "A"], spec(), TINY)

        assert [line.top for line in found.attribution] == [8 + 22 + 14]

    def test_a_line_too_wide_for_the_list_is_refused(self):
        with pytest.raises(SystemExit, match="pixels wide"):
            screen.layout(["A" * 50], spec(), TINY)

    def test_too_many_lines_are_refused(self):
        with pytest.raises(SystemExit, match="below row"):
            screen.layout(["A"] * 14, spec(), TINY)


class TestDrawing:
    def test_only_ink_takes_the_text_register(self):
        indices = np.full((20, 320), 3, dtype=np.uint8)
        line = screen.Line("A A", 4, 2)

        found = screen.draw(indices, [line], TINY)

        assert found[2:4, 4:6].tolist() == [[13, 13], [13, 13]]
        assert found[2, 6:9].tolist() == [3, 3, 3]  # the gap and the space
        assert found[4, 4] == 3  # the glyph's blank last row
        assert (indices == 3).all()  # the picture given is not changed

    def test_the_brightest_pixel_under_a_box_is_found(self):
        indices = np.zeros((10, 10), dtype=np.uint8)
        indices[5, 5] = 1
        palette = np.array([[0.0, 0.0, 0.0], [255.0, 255.0, 255.0]])

        assert screen.brightest_under(indices, palette, screen.Box(0, 0, 5, 5)) == 0.0
        assert screen.brightest_under(indices, palette, screen.Box(0, 0, 6, 6)) == 255.0


class TestColours:
    def test_the_picture_takes_up_to_13_and_then_text_and_traces(self):
        palette = np.array([[0.0, 0.0, 17.0], [187.0, 153.0, 85.0]])

        found = screen.colours(palette, spec())

        assert found[:2] == [0x001, 0xB95]
        assert found[2:13] == [0] * 11
        assert found[13:] == [0xEDB, 0x5BC, 0xDB8]

    def test_more_than_13_picture_colours_are_refused(self):
        with pytest.raises(SystemExit, match="13"):
            screen.colours(np.zeros((14, 3)), spec())


class TestScopes:
    def test_the_recipes_scopes_fit(self):
        screen.check_scopes(spec())

    def test_overlapping_scopes_are_refused(self):
        with pytest.raises(SystemExit, match="overlap"):
            screen.check_scopes(spec(voice_scopes=(8, 30, 92, 134)))

    def test_scopes_sharing_a_byte_are_refused(self):
        with pytest.raises(SystemExit, match="share a byte"):
            screen.check_scopes(spec(voice_scopes=(8, 46, 92, 134)))

    def test_a_scope_off_the_screen_is_refused(self):
        with pytest.raises(SystemExit, match="leaves"):
            screen.check_scopes(spec(mix_scope=(200, 132)))

    def test_the_band_is_whole_rows(self):
        with pytest.raises(SystemExit, match="whole rows"):
            screen.check_scopes(spec(scope_band=screen.Box(4, 152, 320, 197)))


def test_the_include_gives_the_player_rows_colours_and_scopes():
    made = screen.Screen(
        np.zeros((200, 320), dtype=np.uint8),
        [0] * 16,
        screen.Layout([screen.Line("A", 190, 8), screen.Line("A", 190, 19)], []),
        13,
    )

    text = screen.include(made, spec(), TINY)

    assert "line_tops:      dc.w 8,19" in text
    assert "LIST_LINES      equ 2" in text
    assert "HIGHLIGHT_COLOUR equ $B95" in text
    assert "SCOPE_ROWS      equ 45" in text
    assert "voice_scope_left: dc.w 8,50,92,134" in text


def test_the_recipe_makes_a_screen_with_its_text_on_the_dark_wall_and_floor():
    recipe = build.load_recipe(RECIPE)

    made = screen.make([p.title for p in recipe.pieces], recipe.screen, REPO)

    assert made.picture_colours == 13
    assert made.colours[11:14] == [0xB95, 0xEDB, 0xEDB]  # gold, ivory, the text's ivory
    assert (made.indices == screen.TEXT_REGISTER).sum() > 1000
    rows = np.flatnonzero((made.indices == screen.TEXT_REGISTER).any(axis=1))
    assert rows.max() < recipe.screen.scope_band.top
    cols = np.flatnonzero((made.indices == screen.TEXT_REGISTER).any(axis=0))
    assert cols.min() >= recipe.screen.list_box.left


PALETTE = np.array([[0, 0, 17], [17, 51, 102], [102, 85, 68]])  # $001 $136 $654


class TestPictureRegisters:
    def test_a_colour_is_found_among_the_pictures_registers(self):
        assert screen.register_of(PALETTE, "654") == 2

    def test_a_colour_the_picture_lacks_is_refused(self):
        with pytest.raises(SystemExit, match="not one of the picture's"):
            screen.register_of(PALETTE, "EDB")

    def test_lines_are_drawn_in_the_register_given(self):
        indices = np.zeros((10, 10), dtype=np.uint8)

        found = screen.draw(indices, [screen.Line("A", 1, 1)], TINY, register=9)

        assert set(np.unique(found)) == {0, 9}


TALL_BAND = screen.Box(0, 152, 320, 200)


class TestSignature:
    def test_its_ink_is_one_pixel_from_the_right_and_bottom_edges(self):
        line = screen.signature_line("A", TINY)
        indices = screen.draw(np.zeros((200, 320), dtype=np.uint8), [line], TINY, register=7)

        rows, cols = np.nonzero(indices == 7)
        assert (rows.max(), cols.max()) == (198, 318)

    def test_a_scope_over_its_columns_in_the_band_is_refused(self):
        line = screen.signature_line("AAAA", TINY)

        with pytest.raises(SystemExit, match="signature"):
            screen.check_signature(screen.text_box(line, TINY), spec(scope_band=TALL_BAND))

    def test_a_scope_that_ends_left_of_it_is_allowed(self):
        line = screen.signature_line("AAAA", TINY)

        screen.check_signature(
            screen.text_box(line, TINY), spec(scope_band=TALL_BAND, mix_scope=(180, 120))
        )

    def test_rows_below_the_band_are_never_drawn_on(self):
        line = screen.signature_line("AAAA", TINY)  # rows 197 to 199; the band ends at 197

        screen.check_signature(screen.text_box(line, TINY), spec())


def test_the_recipes_credits_and_signature_are_in_picture_colours_off_register_13():
    recipe = build.load_recipe(RECIPE)
    spec_ = recipe.screen

    made = screen.make([p.title for p in recipe.pieces], spec_, REPO)

    credits_register = made.colours.index(picture.parse_ocs(spec_.attribution_colour))
    signature_register = made.colours.index(picture.parse_ocs(spec_.signature_colour))
    text_rows = np.flatnonzero((made.indices == screen.TEXT_REGISTER).any(axis=1))
    first_credit = made.layout.attribution[0].top
    assert text_rows.max() < first_credit  # register 13 is the list's alone
    signature = made.layout.signature
    ink = font.load(REPO / spec_.font).render(signature.text)
    rows, cols = np.nonzero(ink)
    rows, cols = rows + signature.top, cols + signature.left
    assert (rows.max(), cols.max()) == (198, 318)
    assert (made.indices[rows, cols] == signature_register).all()
    assert (made.indices[first_credit : first_credit + 9] == credits_register).sum() > 50
