from pathlib import Path

import pytest
from amiga_env.cli import boot_command
from amiga_env.profile import MACHINES, machine_args

MEDIA = Path("/project/media")


def _value(args, flag):
    return args[args.index(flag) + 1]


def _settings(args):
    return [args[i + 1] for i, a in enumerate(args) if a == "-s"]


def test_the_a500_is_an_ntsc_a500_on_kickstart_and_workbench_1_2():
    args = machine_args("a500", media=MEDIA)

    assert _value(args, "--model") == "A500"
    assert _value(args, "-r") == "/project/media/rom/forever/amiga-os-120.rom"
    assert _value(args, "-0") == "/project/media/adf/1.2/workbench.adf"
    assert _settings(args) == ["ntsc=true"]


def test_the_a3000_is_an_ntsc_a3000_on_3_2_with_8_mb_of_motherboard_fast_ram():
    args = machine_args("a3000", media=MEDIA)

    assert _value(args, "--model") == "A3000"
    assert _value(args, "-r") == "/project/media/rom/3.2/kick-a3000.rom"
    assert _value(args, "-0") == "/project/media/adf/3.2/Install3.2.adf"
    assert _settings(args) == ["ntsc=true", "a3000mem_size=8"]


@pytest.mark.parametrize("name", MACHINES)
def test_a_disk_replaces_workbench_in_drive_0(name):
    assert _value(machine_args(name, Path("/build/hello.adf"), MEDIA), "-0") == "/build/hello.adf"


def test_the_command_takes_an_optional_disk_then_amiberry_options():
    with_disk = boot_command("a500", ["hello.adf", "-G"])
    without = boot_command("a3000", ["-G"])

    assert _value(with_disk, "-0") == str(Path("hello.adf").resolve())
    assert with_disk[-1] == "-G"
    assert _value(without, "-0").endswith("adf/3.2/Install3.2.adf")
    assert without[-1] == "-G"
