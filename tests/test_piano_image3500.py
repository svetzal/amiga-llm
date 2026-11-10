import pytest
from amiga_env import export
from amiga_env.piano import image3500


def test_a_partition_has_room_for_the_files_and_the_spare():
    cylinders = image3500.cylinders_for(11_200_000)

    assert cylinders * export.CYLINDER_BYTES >= 11_200_000 + image3500.SPARE_MIB * export.MIB
    assert (cylinders - 1) * export.CYLINDER_BYTES < 11_200_000 + 4 * export.MIB


def test_the_rdb_has_one_bootable_ffs_partition_and_no_filesystem():
    args = image3500.rdb_commands(image3500.Path("x.hdf"), 13)

    assert args[: args.index("+")] == [
        "-f",
        "--disk-vendor",
        "AMIGAENV",
        "x.hdf",
        "create",
        "chs=15,32,63",
    ]
    assert "fs=DOS1" in args and "bootable=1" in args and "name=DH0" in args
    assert "end=14" in args
    assert "fsadd" not in args


def test_the_image_goes_on_the_a3000s_own_scsi_controller():
    setting = image3500.hardfile_setting(image3500.Path("/work/piano.hdf"))

    assert setting == "hardfile2=rw,DH0:/work/piano.hdf,0,0,0,512,0,,scsi0_a3000"


def test_a_path_with_a_comma_is_refused():
    with pytest.raises(SystemExit):
        image3500.hardfile_setting(image3500.Path("/a,b/piano.hdf"))


def test_the_boot_reports_the_players_fast_ram_figures():
    from amiga_env.piano import run3500

    values = dict.fromkeys(run3500.STATUS_FIELDS, 0) | {
        "fast_free_before": 15_100_000,
        "fast_largest_before": 15_000_000,
        "fast_free_after": 3_900_000,
        "fast_largest_after": 3_800_000,
    }

    figures = image3500.fast_ram(run3500.Status(**values))

    assert figures == {
        "fast_free_before": 15_100_000,
        "fast_largest_before": 15_000_000,
        "fast_free_after": 3_900_000,
        "fast_largest_after": 3_800_000,
    }
