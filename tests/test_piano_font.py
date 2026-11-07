from pathlib import Path

import pytest
from amiga_env.piano import font

FONT = Path(__file__).parents[1] / "examples" / "piano" / "font.txt"
RECIPE = Path(__file__).parents[1] / "examples" / "piano" / "piano.toml"

TINY = """# a comment
height 3
baseline 2
gap 1

char space
..

char I
#
#
#

char T
###
.#.
"""


@pytest.fixture
def tiny():
    return font.parse(TINY.splitlines())


class TestParse:
    def test_the_header_and_glyphs_are_read(self, tiny):
        assert (tiny.height, tiny.baseline, tiny.gap) == (3, 2, 1)
        assert sorted(tiny.glyphs) == [" ", "I", "T"]

    def test_a_short_glyph_is_blank_below_its_rows(self, tiny):
        assert tiny.glyph("T").tolist() == [
            [True, True, True],
            [False, True, False],
            [False, False, False],
        ]

    def test_a_glyph_row_of_one_ink_pixel_is_not_a_comment(self, tiny):
        assert tiny.glyph("I").all()

    def test_rows_of_different_widths_are_refused(self):
        with pytest.raises(ValueError, match="one width"):
            font.parse(["height 2", "baseline 1", "gap 1", "", "char A", "##", "#"])

    def test_a_character_twice_is_refused(self):
        with pytest.raises(ValueError, match="new character"):
            font.parse(["height 1", "baseline 0", "gap 1", "char A", "#", "", "char A", "#"])

    def test_the_header_is_required(self):
        with pytest.raises(ValueError, match="gap"):
            font.parse(["height 1", "baseline 0", "char A", "#"])

    def test_anything_else_is_refused(self):
        with pytest.raises(ValueError, match="cannot read"):
            font.parse(["height 1", "baseline 0", "gap 1", "char A", "#x"])


class TestText:
    def test_the_width_counts_gaps_between_glyphs_only(self, tiny):
        assert tiny.width("IT") == 1 + 1 + 3
        assert tiny.width("") == 0

    def test_text_renders_glyph_by_glyph(self, tiny):
        assert tiny.render("I T").astype(int).tolist() == [
            [1, 0, 0, 0, 0, 1, 1, 1],
            [1, 0, 0, 0, 0, 0, 1, 0],
            [1, 0, 0, 0, 0, 0, 0, 0],
        ]

    def test_a_missing_glyph_is_named(self, tiny):
        with pytest.raises(ValueError, match="'Z'"):
            tiny.width("Z")


class TestTheProjectFont:
    def test_it_is_narrow_and_nine_rows_high(self):
        project = font.load(FONT)

        widths = [g.shape[1] for c, g in project.glyphs.items() if c.isalpha()]
        assert project.height == 9
        assert max(widths) == 5 and sum(widths) / len(widths) < 4

    def test_it_has_every_printable_character_the_titles_use(self):
        import tomllib

        recipe = tomllib.loads(RECIPE.read_text())
        text = "".join(p["title"] for p in recipe["piece"])
        text += "".join(recipe["screen"]["attribution"])

        project = font.load(FONT)

        assert set(text) <= project.glyphs.keys()
        assert set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") <= (
            project.glyphs.keys()
        )
