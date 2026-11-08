from pathlib import Path

import pytest
from amiga_env.cli import boot_command
from amiga_env.profile import load_machines, machine_args, media_paths, parse_config
from conftest import REPO

MEDIA = Path("/project/media")
# amiga-llm's own machines, as AGENTS.md records them.
MACHINES = load_machines(REPO / "amiga.toml")


def _value(args, flag):
    return args[args.index(flag) + 1]


def _settings(args):
    return [args[i + 1] for i, a in enumerate(args) if a == "-s"]


def test_the_a500_is_an_ntsc_a500_on_kickstart_and_workbench_1_2():
    args = machine_args(MACHINES["a500"], media=MEDIA)

    assert _value(args, "--model") == "A500"
    assert _value(args, "-r") == "/project/media/rom/forever/amiga-os-120.rom"
    assert _value(args, "-0") == "/project/media/adf/1.2/workbench.adf"
    assert _settings(args) == ["ntsc=true"]


def test_the_a3000_is_an_ntsc_a3000_on_3_2_with_8_mb_of_motherboard_fast_ram():
    args = machine_args(MACHINES["a3000"], media=MEDIA)

    assert _value(args, "--model") == "A3000"
    assert _value(args, "-r") == "/project/media/rom/3.2/kick-a3000.rom"
    assert _value(args, "-0") == "/project/media/adf/3.2/Install3.2.adf"
    assert _settings(args) == ["ntsc=true", "a3000mem_size=8"]


def test_the_a3500_is_an_ntsc_a3000_at_25_mhz_on_kickstart_2_04_and_workbench_2_1_with_16_mb_fast():
    args = machine_args(MACHINES["a3500"], media=MEDIA)

    assert _value(args, "--model") == "A3000"
    assert _value(args, "-r") == "/project/media/rom/forever/amiga-os-204-a3000.rom"
    assert _value(args, "-0") == "/project/media/adf/2.1/workbench.adf"
    assert _settings(args) == [
        "ntsc=true",
        "a3000mem_size=16",
        "cpu_speed=real",
        "cpu_multiplier=7",
        "cpu_data_cache=true",
        "sound_max_buff=8192",
    ]


def test_the_a3000_dev_boots_its_built_system_as_dh0_and_work_as_dh1():
    args = machine_args(MACHINES["a3000-dev"], media=MEDIA, root=Path("/project"))

    assert _value(args, "--model") == "A3000"
    assert _value(args, "-r") == "/project/media/rom/3.2/kick-a3000.rom"
    assert "-0" not in args
    assert _settings(args) == [
        "ntsc=true",
        "a3000mem_size=8",
        "filesystem2=rw,DH0:System:/project/runs/systems/a3000-dev,0",
        "filesystem2=rw,DH1:Work:/project/work,-128",
    ]


def test_the_a3000_dev_060_runs_the_same_system_on_a_68060_with_its_fpu_and_mmu():
    args = machine_args(MACHINES["a3000-dev-060"], media=MEDIA, root=Path("/project"))
    settings = _settings(args)

    assert _value(args, "--model") == "A3000"
    assert _value(args, "-r") == "/project/media/rom/3.2/kick-a3000.rom"
    for wanted in ("cpu_model=68060", "fpu_model=68060", "mmu_model=68060"):
        assert wanted in settings
    assert "cpu_24bit_addressing=false" in settings
    assert "cpu_compatible=false" in settings
    assert "z3mem_size=256" in settings
    assert "filesystem2=rw,DH0:System:/project/runs/systems/a3000-dev,0" in settings


def test_amiga_llm_defines_its_five_machines():
    assert list(MACHINES) == ["a500", "a3000", "a3500", "a3000-dev", "a3000-dev-060"]


@pytest.mark.parametrize("name", MACHINES)
def test_a_disk_replaces_workbench_in_drive_0(name):
    args = machine_args(MACHINES[name], Path("/build/hello.adf"), MEDIA)

    assert _value(args, "-0") == "/build/hello.adf"


def test_the_command_takes_an_optional_disk_then_amiberry_options():
    with_disk = boot_command(MACHINES["a500"], ["hello.adf", "-G"], MEDIA)
    without = boot_command(MACHINES["a3000"], ["-G"], MEDIA)

    assert _value(with_disk, "-0") == str(Path("hello.adf").resolve())
    assert with_disk[-1] == "-G"
    assert _value(without, "-0") == "/project/media/adf/3.2/Install3.2.adf"
    assert without[-1] == "-G"


class TestAmigaToml:
    def test_a_minimal_machine_needs_only_a_model_and_a_kickstart(self):
        machines = parse_config('[machines.a1200]\nmodel = "A1200"\nkickstart = "rom/k.rom"\n')

        machine = machines["a1200"]
        assert machine.disk is None
        assert machine.settings == ()
        assert machine_args(machine, media=MEDIA) == [
            "--model",
            "A1200",
            "-r",
            "/project/media/rom/k.rom",
        ]

    def test_volumes_without_a_system_start_at_dh0(self):
        machines = parse_config(
            '[machines.a]\nmodel = "A"\nkickstart = "k"\nvolumes = { Work = "w", Data = "d" }\n'
        )

        args = machine_args(machines["a"], media=MEDIA, root=Path("/p"))

        assert _settings(args) == [
            "filesystem2=rw,DH0:Work:/p/w,-128",
            "filesystem2=rw,DH1:Data:/p/d,-128",
        ]

    def test_no_machines_is_valid(self):
        assert parse_config("# nothing yet\n") == {}

    @pytest.mark.parametrize(
        ("text", "message"),
        [
            ('[machines.a]\nmodel = "A500"\n', "has no kickstart"),
            ('[machines.a]\nkickstart = "k.rom"\n', "has no model"),
            ('[machines.a]\nmodel = "A500"\nkickstart = "k"\nram = 1\n', "unknown key ram"),
            ('[machine.a]\nmodel = "A500"\n', "unknown key machine"),
            ('[machines.a]\nmodel = "A500"\nkickstart = "/abs/k.rom"\n', "inside media"),
            ('[machines.a]\nmodel = "A500"\nkickstart = "../k.rom"\n', "inside media"),
            ('[machines.a]\nmodel = "A500"\nkickstart = "k"\ndisk = "../d.adf"\n', "inside media"),
            ('[machines.a]\nmodel = "A500"\nkickstart = "k"\nsettings = ["ntsc"]\n', "key=value"),
            ('[machines.A5]\nmodel = "A500"\nkickstart = "k"\n', "lower case"),
            ('[machines.a]\nmodel = ""\nkickstart = "k"\n', "non-empty"),
            ('[machines.a]\nmodel = "A"\nkickstart = "k"\nsystem = "A B"\n', "names a recipe"),
            ('[machines.a]\nmodel = "A"\nkickstart = "k"\nvolumes = ["w"]\n', "table of Label"),
            ('[machines.a]\nmodel = "A"\nkickstart = "k"\nvolumes = { "W:x" = "w" }\n', "volume"),
            ('[machines.a]\nmodel = "A"\nkickstart = "k"\nvolumes = { System = "w" }\n', "volume"),
            ('[machines.a]\nmodel = "A"\nkickstart = "k"\nvolumes = { W = "../w" }\n', "inside"),
            ("[machines\n", "not valid TOML"),
        ],
    )
    def test_mistakes_are_refused_clearly(self, text, message):
        with pytest.raises(SystemExit, match=message):
            parse_config(text)

    def test_a_machine_may_not_take_a_command_name(self):
        with pytest.raises(SystemExit, match="is an amiga-env command"):
            parse_config('[machines.doctor]\nmodel = "A500"\nkickstart = "k"\n', {"doctor"})

    def test_media_paths_list_what_the_machine_boots(self):
        assert media_paths(MACHINES["a500"]) == {
            "kickstart": Path("rom/forever/amiga-os-120.rom"),
            "disk": Path("adf/1.2/workbench.adf"),
        }


def test_an_exported_image_replaces_the_system_folder_and_the_volumes():
    image = Path("/project/runs/export/a3000-dev.hdf")
    args = machine_args(MACHINES["a3000-dev-060"], media=MEDIA, image=image)
    settings = _settings(args)

    assert "hardfile2=rw,DH0:/project/runs/export/a3000-dev.hdf,0,0,0,512,0,,uaehf0" in settings
    assert not [s for s in settings if s.startswith("filesystem2=")]
