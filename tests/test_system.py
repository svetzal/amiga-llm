"""Building systems on the host. Only `amiga` layers need the emulator, and
these tests use none: they build small trees from disks and archives made
here, in a throwaway project."""

import zipfile

import pytest
from amiga_env import adf, compress, session, system
from amiga_env.recipe import parse, personal_paths
from amitools.fs.ADFSVolume import ADFSVolume
from amitools.fs.blkdev.BlkDevFactory import BlkDevFactory
from amitools.fs.FSString import FSString
from amitools.fs.TimeStamp import TimeStamp
from amitools.tools import xdftool


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An empty amiga-env project with a disk and an archive in media/."""
    (tmp_path / "amiga.toml").write_text("")
    monkeypatch.setenv("AMIGA_ENV_ROOT", str(tmp_path))
    media = tmp_path / "media"
    (media / "adf").mkdir(parents=True)
    content = tmp_path / "content"
    content.mkdir()
    (content / "hello").write_text("hello\n")
    adf.make_adf(media / "adf" / "wb.adf", [content / "hello"], ["hello"], "Workbench")
    with zipfile.ZipFile(media / "dev.zip", "w") as archive:
        archive.writestr("Dev/include/exec/types.h", "/* types */\n")
        archive.writestr("Dev/lib/amiga.lib", "lib")
    (tmp_path / "systems").mkdir()
    return tmp_path


def _recipe(project, text):
    (project / "systems" / "t.toml").write_text(text)


BASE = """
[[layer]]
type = "unpack"
media = "adf/wb.adf"

[[layer]]
type = "copy"
media = "dev.zip"
files = { "Dev/include" = "Developer/Include" }
"""

STARTUP = """
[[layer]]
type = "file"
path = "s/user-startup"
text = "Assign SC: SYS:SC\\n"
"""


class TestBuild:
    def test_layers_fill_the_tree_from_disks_and_archives(self, project):
        _recipe(project, BASE)

        tree = system.build("t")

        assert (tree / "hello").read_text() == "hello\n"
        assert (tree / "s" / "startup-sequence").read_text() == "hello\n"
        assert (tree / "Developer" / "Include" / "exec" / "types.h").is_file()
        assert not (tree / "Developer" / "Include" / "lib").exists()

    def test_every_system_ends_with_the_amiga_env_startup_hook(self, project):
        _recipe(project, BASE + STARTUP)

        tree = system.build("t")

        startup = (tree / "s" / "user-startup").read_text()
        assert startup == "Assign SC: SYS:SC\n" + session.HOOK

    def test_an_unchanged_recipe_builds_nothing(self, project, capsys):
        _recipe(project, BASE)
        system.build("t")
        capsys.readouterr()

        system.build("t")

        assert "up to date" in capsys.readouterr().out

    def test_a_new_layer_at_the_end_is_the_only_one_applied(self, project, capsys):
        _recipe(project, BASE)
        system.build("t")
        capsys.readouterr()
        _recipe(project, BASE + STARTUP)

        system.build("t")

        out = capsys.readouterr().out
        assert "layer  3 file   s/user-startup" in out
        assert "layer  1" not in out

    def test_a_changed_layer_rebuilds_from_nothing_without_a_snapshot(self, project, capsys):
        _recipe(project, BASE + STARTUP)
        tree = system.build("t")
        (tree / "stray").write_text("left by a person")
        capsys.readouterr()
        _recipe(project, BASE.replace("Dev/include", "Dev/lib") + STARTUP)

        system.build("t")

        assert "layer  1" in capsys.readouterr().out
        assert not (tree / "stray").exists()
        assert (tree / "Developer" / "Include" / "amiga.lib").is_file()

    def test_two_builds_give_the_same_listing(self, project):
        _recipe(project, BASE + STARTUP)
        system.build("t", force=True)
        first = system.tree_listing(system.tree_dir("t"))

        system.build("t", force=True)

        assert system.tree_listing(system.tree_dir("t")) == first
        files = [line for line in first if not line.endswith(system.SIDECAR)]
        assert len(files) == 4

    def test_list_reports_whether_each_recipe_is_built(self, project, capsys):
        _recipe(project, BASE)
        system.list_systems()
        assert "not built" in capsys.readouterr().out

        system.build("t")
        system.list_systems()

        assert "t              built" in capsys.readouterr().out

    def test_an_unknown_recipe_names_the_ones_there_are(self, project):
        _recipe(project, BASE)

        with pytest.raises(SystemExit, match="recipes: t"):
            system.load("nope")


# "aaa" as compress writes it: the code for a, then 257 (aa), in 9 bits.
AAA_Z = compress.MAGIC + bytes([compress.BLOCK_MODE | 9]) + (97 | 257 << 9).to_bytes(3, "little")


def _sidecar(path):
    return (path.parent / (path.name + system.SIDECAR)).read_text()


def _stamp(adf, path, days, minutes, ticks):
    """Set a file's raw Amiga datestamp, which has no time zone."""
    blkdev = BlkDevFactory().open(str(adf))
    volume = ADFSVolume(blkdev)
    volume.open()
    volume.get_path_name(FSString(path)).change_mod_ts(TimeStamp(days, minutes, ticks))
    volume.close()
    blkdev.close()


class TestAttributes:
    def test_a_file_keeps_the_protection_bits_and_date_of_its_disk(self, project):
        image = project / "media" / "adf" / "wb.adf"
        xdftool.main([str(image), "protect", "hello", "srwd"])
        _stamp(image, "hello", days=15808, minutes=163, ticks=684)
        _recipe(project, BASE)

        tree = system.build("t")

        assert _sidecar(tree / "hello") == "-s--rw-d 2021-04-13 02:43:13.68\n"

    def test_a_copied_file_takes_its_attributes_under_its_new_name(self, project):
        xdftool.main([str(project / "media" / "adf" / "wb.adf"), "protect", "hello", "prwed"])
        _recipe(
            project,
            '[[layer]]\ntype = "copy"\nmedia = "adf/wb.adf"\nfiles = { "hello" = "C/Greet" }\n',
        )

        tree = system.build("t")

        assert _sidecar(tree / "C" / "Greet").startswith("--p-rwed ")

    def test_a_file_from_an_archive_replaces_attributes_as_well_as_content(self, tmp_path):
        source, dest = tmp_path / "archive", tmp_path / "tree"
        source.mkdir()
        dest.mkdir()
        (source / "Startup").write_text("new")
        (dest / "Startup").write_text("old")
        (dest / "Startup.uaem").write_text("-s--rwed 2021-04-13 03:43:13.00\n")

        system.merge(source, dest, set())

        assert sorted(p.name for p in dest.iterdir()) == ["Startup"]

    def test_sidecars_are_not_files_in_their_own_right(self, tmp_path):
        source, dest = tmp_path / "disk", tmp_path / "tree"
        source.mkdir()
        dest.mkdir()
        (source / "Disk.info").write_text("icon")
        (source / "Disk.info.uaem").write_text("----rw-d 2021-04-13 03:43:13.00\n")

        system.merge(source, dest, {"disk.info"})

        assert list(dest.iterdir()) == []


class TestLayerOptions:
    def test_decompress_writes_name_z_as_name_as_the_installer_does(self, tmp_path):
        source, dest = tmp_path / "disk", tmp_path / "tree"
        source.mkdir()
        dest.mkdir()
        (source / "Workbench.guide.Z").write_bytes(AAA_Z)
        (source / "Workbench.guide.Z.uaem").write_text("----rw-d 2021-04-13 03:44:03.46\n")

        system.merge(source, dest, set(), decompress=True)

        assert (dest / "Workbench.guide").read_bytes() == b"aaa"
        assert _sidecar(dest / "Workbench.guide").startswith("----rw-d 2021-04-13 03:44:03.46")
        assert not (dest / "Workbench.guide.Z").exists()

    def test_copy_leaves_out_excluded_paths_named_from_the_disk_root(self, project):
        _recipe(
            project,
            '[[layer]]\ntype = "copy"\nmedia = "dev.zip"\n'
            'files = { "Dev" = "Developer" }\nexclude = ["Dev/lib/amiga.lib"]\n',
        )

        tree = system.build("t")

        assert (tree / "Developer" / "include" / "exec" / "types.h").is_file()
        assert not (tree / "Developer" / "lib" / "amiga.lib").exists()

    def test_dirs_makes_empty_drawers(self, project):
        _recipe(project, BASE + '[[layer]]\ntype = "dirs"\npaths = ["Libs/MMU", "Expansion"]\n')

        tree = system.build("t")

        assert (tree / "Libs" / "MMU").is_dir()
        assert (tree / "Expansion").is_dir()

    def test_append_adds_to_the_file_a_disk_put_there(self, project):
        appended = STARTUP.replace("s/user-startup", "s/startup-sequence")
        _recipe(project, BASE + appended.replace('type = "file"', 'type = "file"\nappend = true'))

        tree = system.build("t")

        assert (tree / "s" / "startup-sequence").read_text() == "hello\nAssign SC: SYS:SC\n"

    def test_personal_layers_name_the_paths_an_export_leaves_out(self):
        rec = parse(
            "t",
            '[[layer]]\ntype = "copy"\nmedia = "mui/mui.key"\n'
            'files = { "mui.key" = "S/mui.key" }\npersonal = true\n',
        )

        assert personal_paths(rec) == ("S/mui.key",)


class TestOpeningMedia:
    def test_an_adf_opens_as_its_files_with_its_volume_name(self, project):
        tree, label = system.open_file(project / "media" / "adf" / "wb.adf")

        assert label == "Workbench"
        assert (tree / "hello").is_file()

    def test_an_archive_holding_one_adf_opens_as_that_disk(self, project):
        packed = project / "media" / "disk.zip"
        with zipfile.ZipFile(packed, "w") as archive:
            archive.write(project / "media" / "adf" / "wb.adf", "Workbench (1993).adf")

        tree, label = system.open_file(packed)

        assert label == "Workbench"
        assert (tree / "hello").is_file()

    def test_a_plain_file_opens_as_a_folder_holding_it(self, project):
        key = project / "media" / "mui.key"
        key.write_bytes(b"key")

        tree, label = system.open_file(key)

        assert label is None
        assert (tree / "mui.key").read_bytes() == b"key"

    def test_members_missing_after_extraction_are_named(self, tmp_path):
        (tmp_path / "MUI").mkdir()
        (tmp_path / "MUI" / "Libs").write_text("x")

        assert system.missing_members(["MUI/", "MUI/Libs", "MUI/Docs"], tmp_path) == ["MUI/Docs"]


class TestMerging:
    def test_drawers_are_matched_ignoring_case_as_amigados_does(self, tmp_path):
        source, dest = tmp_path / "disk", tmp_path / "tree"
        (source / "LIBS").mkdir(parents=True)
        (source / "LIBS" / "icon.library").write_text("icon")
        (dest / "Libs").mkdir(parents=True)

        system.merge(source, dest, set())

        assert sorted(p.name for p in dest.iterdir()) == ["Libs"]
        assert (dest / "Libs" / "icon.library").read_text() == "icon"

    def test_excluded_paths_are_left_out(self, tmp_path):
        source, dest = tmp_path / "disk", tmp_path / "tree"
        (source / "MUI").mkdir(parents=True)
        (source / "Disk.info").write_text("icon")
        (source / "MUI" / "Install-MUI").write_text("script")
        (source / "MUI" / "Libs").write_text("libs")
        dest.mkdir()

        system.merge(source, dest, {"disk.info", "mui/install-mui"})

        assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*")) == [
            "MUI",
            "MUI/Libs",
        ]

    def test_the_listing_leaves_out_amiberrys_attribute_records(self, tmp_path):
        (tmp_path / "C").mkdir()
        (tmp_path / "C" / "Dir").write_bytes(b"dir")
        (tmp_path / "C" / system.FSDB).write_bytes(b"attrs")

        (line,) = system.tree_listing(tmp_path)

        assert line.endswith("  C/Dir")
