from pathlib import Path

from amiga_env.cli import a500_command
from amiga_env.profile import a500_args

MEDIA = Path("/project/media")


def _value(args, flag):
    return args[args.index(flag) + 1]


def test_the_baseline_is_an_ntsc_a500_on_kickstart_and_workbench_1_2():
    args = a500_args(media=MEDIA)

    assert _value(args, "--model") == "A500"
    assert _value(args, "-r") == "/project/media/rom/forever/amiga-os-120.rom"
    assert _value(args, "-0") == "/project/media/adf/1.2/workbench.adf"
    assert _value(args, "-s") == "ntsc=true"


def test_a_disk_replaces_workbench_in_drive_0():
    assert _value(a500_args(Path("/build/hello.adf"), MEDIA), "-0") == "/build/hello.adf"


def test_the_command_takes_an_optional_disk_then_amiberry_options():
    with_disk = a500_command(["hello.adf", "-G"])
    without = a500_command(["-G"])

    assert _value(with_disk, "-0") == str(Path("hello.adf").resolve())
    assert with_disk[-1] == "-G"
    assert _value(without, "-0").endswith("adf/1.2/workbench.adf")
    assert without[-1] == "-G"
