"""Exporting a built system as an RDB hard-disk image."""

import zipfile

import pytest
from amiga_env import export, system, uaem
from amitools.fs.ADFSVolume import ADFSVolume
from amitools.fs.blkdev.BlkDevFactory import BlkDevFactory
from amitools.fs.blkdev.RawBlockDevice import RawBlockDevice
from amitools.fs.block.rdb.PartitionBlock import PartitionBlock
from amitools.fs.FSString import FSString
from amitools.fs.rdb.RDisk import RDisk


def test_partitions_follow_the_rdb_in_whole_cylinders_of_at_least_the_size_asked():
    plan = export.layout(49, 748)

    assert plan == export.Layout(cylinders=812, system=(2, 51), work=(52, 811))


def test_a_size_below_one_mib_is_refused():
    with pytest.raises(SystemExit):
        export.layout(0, 10)


def test_personal_paths_are_left_out_unless_asked_for():
    assert export.left_out(["S/mui.key"], include_personal=False) == {"s/mui.key"}
    assert export.left_out(["S/mui.key"], include_personal=True) == set()


def test_rdbtool_gets_a_bootable_dh0_a_work_dh1_and_the_filesystem(tmp_path):
    args = export.rdb_commands(tmp_path / "a.hdf", export.layout(49, 748), tmp_path / "FFS")
    commands = " ".join(args).split(" + ")

    assert commands[0].endswith("create chs=812,32,63")
    assert "start=2 end=51 name=DH0 fs=DOS3 bootable=1 pri=0" in commands[2]
    assert "start=52 end=811 name=DH1 fs=DOS3 bootable=0" in commands[3]
    assert commands[4] == f"fsadd {tmp_path / 'FFS'} fs=DOS3"


def test_staging_leaves_out_a_personal_file_and_its_sidecar(tmp_path):
    tree, staged = tmp_path / "tree", tmp_path / "staged"
    (tree / "S").mkdir(parents=True)
    (tree / "S" / "mui.key").write_bytes(b"key")
    (tree / "S" / "mui.key.uaem").write_text("----rwed 2021-04-13 02:43:13.00\n")
    (tree / "S" / "Startup-sequence").write_text("LoadWB\n")

    skipped = export.stage(tree, staged, {"s/mui.key"})

    assert skipped == ["S/mui.key"]
    assert sorted(p.name for p in (staged / "S").iterdir()) == ["Startup-sequence"]


@pytest.fixture
def built(tmp_path, monkeypatch):
    """A built system with a script, a pure command, a keyfile and a filesystem."""
    (tmp_path / "amiga.toml").write_text("")
    monkeypatch.setenv("AMIGA_ENV_ROOT", str(tmp_path))
    (tmp_path / "media").mkdir()
    with zipfile.ZipFile(tmp_path / "media" / "sys.zip", "w") as archive:
        archive.writestr("S/Startup-sequence", "LoadWB\n")
        archive.writestr("C/Assign", "pure")
        archive.writestr("L/FastFileSystem", "$VER: fs 47.4 (16.6.2020)\n")
        archive.writestr("mui.key", "key")
    (tmp_path / "systems").mkdir()
    (tmp_path / "systems" / "t.toml").write_text(
        '[[layer]]\ntype = "copy"\nmedia = "sys.zip"\n'
        'files = { "S" = "S", "C" = "C", "L" = "L" }\n\n'
        '[[layer]]\ntype = "copy"\nmedia = "sys.zip"\n'
        'files = { "mui.key" = "S/mui.key" }\npersonal = true\n'
    )
    tree = system.build("t")
    script = uaem.Attributes("-s--rw-d", 15808, 162, 1111, "the boot script")
    (tree / "S" / "Startup-sequence.uaem").write_text(uaem.format_line(script))
    (tree / "C" / "Assign.uaem").write_text(uaem.format_line(uaem.Attributes("--p-rwed")))
    return tmp_path


def _volume(image, part):
    blkdev = BlkDevFactory().open(str(image), read_only=True, options={"part": part})
    volume = ADFSVolume(blkdev)
    volume.open()
    return blkdev, volume


def test_an_export_keeps_attributes_and_leaves_out_the_keyfile(built):
    image = export.export("t", built / "out" / "t.hdf", system_mib=1, work_mib=1)
    blkdev, volume = _volume(image, "DH0")

    script = volume.get_path_name(FSString("S/Startup-sequence")).meta_info
    pure = volume.get_path_name(FSString("C/Assign")).meta_info
    names = [e.name.get_unicode_name() for e in volume.get_path_name(FSString("S")).get_entries()]
    label = volume.get_volume_name().get_unicode()
    volume.close()
    blkdev.close()

    assert label == "Workbench"
    assert uaem.protect_text(script.get_protect()) == "-s--rw-d"
    stamp = script.get_mod_ts()
    assert (stamp.days, stamp.mins, stamp.ticks) == (15808, 162, 1111)
    assert script.get_comment().get_unicode() == "the boot script"
    assert uaem.protect_text(pure.get_protect()) == "--p-rwed"
    assert "mui.key" not in [n.lower() for n in names]


def test_the_rdb_holds_the_systems_filesystem_and_a_bootable_dh0(built):
    image = export.export("t", built / "t.hdf", system_mib=1, work_mib=1)
    blkdev = RawBlockDevice(str(image), read_only=True)
    blkdev.open()
    rdisk = RDisk(blkdev)
    rdisk.open()

    names = [p.get_drive_name().get_unicode() for p in rdisk.parts]
    bootable = rdisk.parts[0].get_flags() & PartitionBlock.FLAG_BOOTABLE
    (filesystem,) = rdisk.fs
    version = filesystem.fshd.version
    rdisk.close()
    blkdev.close()

    assert names == ["DH0", "DH1"]
    assert bootable
    assert version == 47 << 16 | 4


def test_include_personal_keeps_the_keyfile(built):
    image = export.export("t", built / "t.hdf", include_personal=True, system_mib=1, work_mib=1)
    blkdev, volume = _volume(image, "DH0")

    found = volume.get_path_name(FSString("S/mui.key"))
    volume.close()
    blkdev.close()

    assert found is not None
