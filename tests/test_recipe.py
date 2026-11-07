import pytest
from amiga_env.recipe import (
    Amiga,
    Copy,
    File,
    MediaRef,
    Plan,
    Unpack,
    describe,
    fingerprints,
    media_refs,
    parse,
    plan,
)
from conftest import REPO

EVERY_LAYER = """
description = "test system"
machine = "a3000"

[[layer]]
type = "unpack"
media = "adf/wb.adf"
exclude = ["Disk.info"]

[[layer]]
type = "copy"
media = "dev/disk3.7z"
member = "include_h.lha"
files = { "include" = "Developer/Include" }

[[layer]]
type = "file"
path = "S/User-Startup"
text = "Assign SC: SYS:SC\\n"

[[layer]]
type = "amiga"
name = "sasc"
script = "systems/x/install"
disks = ["dev/sasc/disk1.7z"]
timeout = 90
"""


def _one_layer(body: str) -> str:
    return f'machine = "m"\n[[layer]]\n{body}\n'


class TestParsing:
    def test_each_layer_type_is_read_in_order(self):
        recipe = parse("x", EVERY_LAYER)

        assert recipe.description == "test system"
        assert recipe.machine == "a3000"
        assert recipe.layers == (
            Unpack(MediaRef("adf/wb.adf"), "", ("Disk.info",)),
            Copy(
                MediaRef("dev/disk3.7z", "include_h.lha"),
                (("include", "Developer/Include"),),
            ),
            File("S/User-Startup", "Assign SC: SYS:SC\n"),
            Amiga("sasc", "systems/x/install", (MediaRef("dev/sasc/disk1.7z"),), 90),
        )

    def test_an_amiga_layer_waits_ten_minutes_unless_told(self):
        recipe = parse("x", _one_layer('type = "amiga"\nname = "a"\nscript = "s"'))

        assert recipe.layers[0].timeout == 600

    def test_a_plain_file_can_be_media_for_a_copy(self):
        recipe = parse("x", _one_layer('type = "copy"\nmedia = "mui/mui.key"\nfiles = {k = "S/k"}'))

        assert recipe.layers[0].source == MediaRef("mui/mui.key")

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ('machine = "m"\n', "no \\[\\[layer\\]\\]"),
            (_one_layer('type = "move"'), "type is one of"),
            (_one_layer('type = "file"\npath = "S/x"\ntext = "a"\nmode = 1'), "unknown key mode"),
            (_one_layer('type = "file"\npath = "/S/x"\ntext = "a"'), "relative path"),
            (_one_layer('type = "file"\npath = "../x"\ntext = "a"'), "relative path"),
            (_one_layer('type = "file"\npath = "SYS:x"\ntext = "a"'), "relative path"),
            (_one_layer('type = "file"\npath = "x"\ntext = "a\\r\\n"'), "LF line endings"),
            (_one_layer('type = "copy"\nmedia = "a.adf"\nfiles = {}'), "files is a table"),
            (_one_layer('type = "copy"\nmedia = "a"\nmember = "b.txt"\nfiles = {a = "b"}'), "ADF"),
            (_one_layer('type = "amiga"\nname = "A B"\nscript = "s"'), "name is lower case"),
            (_one_layer('type = "amiga"\nname = "a"\nscript = "s"\ntimeout = 0'), "whole number"),
            (_one_layer('type = "amiga"\nname = "a"\nscript = "s"\ndisks = ["d.txt"]'), "ADF"),
            ('[[layer]]\ntype = "amiga"\nname = "a"\nscript = "s"\n', "needs `machine`"),
            (
                _one_layer('type = "amiga"\nname = "a"\nscript = "s"')
                + '[[layer]]\ntype = "amiga"\nname = "a"\nscript = "t"\n',
                "share a name",
            ),
            ("[[layer]\n", "not valid TOML"),
        ],
    )
    def test_mistakes_are_refused_clearly(self, text, message):
        with pytest.raises(SystemExit, match=message):
            parse("x", text)

    def test_a_system_name_is_lower_case(self):
        with pytest.raises(SystemExit, match="lower case"):
            parse("A3000", EVERY_LAYER)

    def test_media_refs_and_descriptions_cover_every_layer(self):
        layers = parse("x", EVERY_LAYER).layers

        assert [len(media_refs(layer)) for layer in layers] == [1, 1, 0, 1]
        assert describe(layers[1]) == ("copy 1 path(s) from dev/disk3.7z!include_h.lha")
        assert describe(layers[3]) == "amiga  sasc (systems/x/install)"


class TestFingerprints:
    LAYERS = parse("x", EVERY_LAYER).layers
    INPUTS = (["a"], ["b"], [], ["c", "d"])

    def test_the_same_layers_and_inputs_give_the_same_chain(self):
        assert fingerprints(self.LAYERS, self.INPUTS) == fingerprints(self.LAYERS, self.INPUTS)

    def test_changed_media_changes_its_layer_and_every_later_one(self):
        before = fingerprints(self.LAYERS, self.INPUTS)
        after = fingerprints(self.LAYERS, [["a"], ["B"], [], ["c", "d"]])

        assert after[0] == before[0]
        assert all(a != b for a, b in zip(after[1:], before[1:], strict=True))

    def test_a_changed_layer_changes_its_fingerprint(self):
        edited = (*self.LAYERS[:2], File("S/User-Startup", "other\n"), self.LAYERS[3])

        before = fingerprints(self.LAYERS, self.INPUTS)
        after = fingerprints(edited, self.INPUTS)

        assert after[:2] == before[:2]
        assert after[2] != before[2]


class TestPlan:
    WANTED = ("f1", "f2", "f3", "f4")

    def test_a_tree_with_every_layer_is_up_to_date(self):
        assert plan(self.WANTED, self.WANTED, []).up_to_date

    def test_new_layers_at_the_end_are_added_to_the_tree(self):
        assert plan(self.WANTED, ["f1", "f2"], []) == Plan(2)

    def test_a_changed_layer_restores_the_latest_snapshot_before_it(self):
        assert plan(self.WANTED, ["f1", "x2", "x3"], ["f2", "x3", "f1"]) == Plan(
            2, restore=2, fresh=True
        )

    def test_with_no_usable_snapshot_the_build_starts_from_nothing(self):
        assert plan(self.WANTED, ["x1"], ["x1"]) == Plan(0, fresh=True)

    def test_a_tree_with_more_layers_than_wanted_is_rebuilt(self):
        assert plan(["f1"], ["f1", "f2"], []) == Plan(0, fresh=True)

    def test_an_empty_tree_starts_from_nothing(self):
        assert plan(self.WANTED, [], []) == Plan(0, fresh=True)


class TestTheA3000DevRecipe:
    RECIPE = parse("a3000-dev", (REPO / "systems" / "a3000-dev.toml").read_text())

    def _user_startup(self) -> str:
        files = [layer for layer in self.RECIPE.layers if isinstance(layer, File)]
        return next(f.text for f in files if f.path == "S/User-Startup")

    def test_it_starts_from_the_3_2_workbench_floppy(self):
        assert self.RECIPE.layers[0] == Unpack(MediaRef("adf/3.2/Workbench3.2.adf"), "", ())

    def test_sasc_installs_on_the_a3000_from_its_first_five_disks(self):
        (sasc,) = [layer for layer in self.RECIPE.layers if isinstance(layer, Amiga)]

        assert self.RECIPE.machine == "a3000"
        assert sasc.script == "systems/a3000-dev/install-sasc"
        assert [d.media for d in sasc.disks] == [f"dev/sasc-6.50/disk{n}.7z" for n in range(1, 6)]
        assert (REPO / sasc.script).is_file()

    def test_the_slow_sasc_layer_comes_before_the_developer_files(self):
        kinds = [type(layer).__name__ for layer in self.RECIPE.layers]

        assert kinds.index("Amiga") < min(
            i for i, layer in enumerate(self.RECIPE.layers) if "dev/ndu" in str(layer)
        )

    def test_user_startup_makes_the_assigns_sasc_needs(self):
        text = self._user_startup()

        assert "Assign SC: SYS:SC\n" in text
        assert "Path SC:c ADD\n" in text

    def test_ndu_3_1_and_mui_includes_and_libs_come_before_sascs_own(self):
        text = self._user_startup()

        assert (
            "Assign INCLUDE: Developer:NDU3.1/Include Developer:MUI/C/Include SC:include\n" in text
        )
        assert "Assign LIB: Developer:NDU3.1/Lib SC:lib\n" in text

    def test_user_startup_has_muis_own_block(self):
        text = self._user_startup()

        assert ';BEGIN MUI\nif exists "SYS:MUI"\n   assign MUI: "SYS:MUI"\n' in text
        assert "      assign add LIBS: MUI:Libs\n" in text
        assert text.rstrip().endswith(";END MUI")

    def test_the_mui_keyfile_goes_to_s(self):
        copies = [layer for layer in self.RECIPE.layers if isinstance(layer, Copy)]

        assert Copy(MediaRef("mui/mui.key"), (("mui.key", "S/mui.key"),)) in copies
