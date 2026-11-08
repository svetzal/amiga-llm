from dataclasses import replace

import pytest
from amiga_env.piano import build3500, run3500
from amiga_env.piano.build3500 import Scopes, check_scopes, load_scopes
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
