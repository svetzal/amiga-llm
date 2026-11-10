from dataclasses import replace

import numpy as np
import pytest
from amiga_env.piano import build3500, font, light, picture, run3500
from amiga_env.piano import screen as screen_mod
from amiga_env.piano.build3500 import Scopes, check_scopes, load_scopes
from amiga_env.piano.light import FilterLight
from conftest import REPO

RECIPE = REPO / "examples" / "piano3500" / "piano.toml"
RECIPE_16K = REPO / "examples" / "piano3500-16k" / "piano.toml"
MADE = build3500.Made(
    root=21,
    layer=0,
    region=None,
    keys=(21,),
    data=np.zeros(0, dtype=np.int16),
    loop_start=0,
    rate=11025.0,
    level=1.0,
    decay_db_per_s=0.0,
    loop_similarity=1.0,
)


class TestSamplesBudget:
    def made(self, lengths):
        return [replace(MADE, data=np.zeros(n, dtype=np.int16)) for n in lengths]

    def test_samples_that_fit_the_budget_pass(self):
        made = self.made([1000, 2000])
        size = sum(m.padded_bytes for m in made)

        build3500.check_samples_budget(made, size)

    def test_samples_over_the_budget_stop_the_build(self):
        made = self.made([1000, 2000])
        size = sum(m.padded_bytes for m in made)

        with pytest.raises(SystemExit, match="1 over samples_budget_bytes"):
            build3500.check_samples_budget(made, size - 1)

    def test_the_projects_recipes_keep_the_measured_limit(self):
        for path in (RECIPE, RECIPE_16K):
            assert build3500.load_recipe(path).samples_budget_bytes == 15_409_032


class TestEditions:
    def test_the_16k_edition_differs_only_in_its_rate_floor_and_output(self):
        a3000, edition = build3500.load_recipe(RECIPE), build3500.load_recipe(RECIPE_16K)

        assert (a3000.spec.min_rate, edition.spec.min_rate) == (11025.0, 16000.0)
        assert a3000.out != edition.out
        assert replace(edition, spec=a3000.spec, out=a3000.out) == a3000


class TestScopes:
    def test_the_projects_recipe_has_two_quarter_screen_scopes_side_by_side_in_the_middle(self):
        recipe = build3500.load_recipe(RECIPE)

        assert recipe.scopes == Scopes(left=(80, 160), width=80)

    def test_a_recipe_without_scopes_loads_with_none(self, tmp_path):
        path = tmp_path / "r.toml"
        path.write_text(
            'sfz = "a.sfz"\nout = "o"\nfull_volume = 1\nsamples_budget_bytes = 1\n'
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


class TestFilterLight:
    def test_the_recipe_takes_the_shared_recipes_filter_light_through_pieces(self):
        recipe = build3500.load_recipe(RECIPE)

        assert recipe.filter_light == LIGHT

    def test_a_recipe_without_one_loads_with_none(self, tmp_path):
        path = tmp_path / "r.toml"
        path.write_text(
            'sfz = "a.sfz"\nout = "o"\nfull_volume = 1\nsamples_budget_bytes = 1\n'
            '[[piece]]\nname = "p"\nmidi = "p.mid"\n'
        )

        assert build3500.load_recipe(path).filter_light is None

    def test_screen_data_refuses_a_recipe_without_a_filter_light(self, tmp_path):
        bare = replace(build3500.load_recipe(RECIPE), filter_light=None)

        with pytest.raises(SystemExit, match=r"no \[filter_light\]"):
            run3500.screen_data(bare, tmp_path)

    def test_unlit_puts_the_off_colour_in_register_14_only(self):
        colours = list(range(16))
        made = screen_mod.Screen(np.zeros((200, 320), np.uint8), colours, None, 13)

        assert run3500.unlit(made, LIGHT).colours == [*range(14), 0x311, 15]
        assert made.colours == list(range(16))


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

        assert text == light.include(LIGHT, screen_mod.Box(1, 192, 8, 199), 0x5BC)
        assert {"screen.i", "scopes.i", "menu.i", "title-preview.png"} <= {
            p.name for p in written.iterdir()
        }
