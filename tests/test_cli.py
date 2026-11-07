from pathlib import Path

import pytest
from amiga_env import cli
from amiga_env.cli import paths_outside
from amiga_env.media import Manifest, Source
from amiga_env.profile import Machine

ROOT = Path("/work/amiga-llm")


def test_paths_under_the_project_pass():
    dump = "home_dir=/work/amiga-llm/runs/home\nrom_path=/work/amiga-llm/media/rom/\n"

    assert paths_outside(dump, ROOT) == []


def test_a_sibling_directory_sharing_the_prefix_is_outside():
    dump = "rom_path=/work/amiga-llm-old/rom/\n"

    assert paths_outside(dump, ROOT) == ["rom_path=/work/amiga-llm-old/rom/"]


def test_build_defaults_and_non_path_lines_are_ignored():
    dump = "Amiberry paths:\ncompiled_data_dir=/usr/share/amiberry\nportable=no\n"

    assert paths_outside(dump, ROOT) == []


def test_source_overrides_are_name_equals_path():
    assert cli.parse_overrides(["forever=~/AF"]) == {"forever": Path("~/AF").expanduser()}


@pytest.mark.parametrize("pair", ["forever", "=x", "forever="])
def test_a_malformed_override_is_refused(pair):
    with pytest.raises(SystemExit, match="NAME=PATH"):
        cli.parse_overrides([pair])


def test_doctor_says_whether_each_source_names_a_folder(tmp_path):
    manifest = Manifest(
        {
            "a": Source("a", "A_DIR", "d"),
            "b": Source("b", "B_DIR", "d"),
            "c": Source("c", "C", "d"),
        },
        [],
    )

    lines = cli.source_lines(manifest, {"a": tmp_path, "b": None, "c": tmp_path / "gone"})

    assert lines[0].startswith("sources   a")
    assert lines[0].endswith(f"A_DIR = {tmp_path} (found)")
    assert lines[1].endswith("B_DIR is not set (see .env.example)")
    assert lines[2].endswith("(NOT A FOLDER)")


def test_doctor_checks_each_machines_kickstart_and_disk(tmp_path):
    (tmp_path / "rom").mkdir()
    (tmp_path / "rom" / "k.rom").write_bytes(b"k")
    machine = Machine("A500", Path("rom/k.rom"), Path("adf/wb.adf"), (), "")

    lines, ok = cli.machine_media_lines({"a500": machine}, tmp_path)

    assert not ok
    assert lines == [
        "a500      kickstart rom/k.rom present",
        "a500      disk      adf/wb.adf MISSING",
    ]


def test_help_works_outside_a_project(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("AMIGA_ENV_ROOT")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as exit_:
        cli.main(["--help"])

    assert exit_.value.code == 0
    assert "init" in capsys.readouterr().out


def test_help_lists_the_projects_machines(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])

    out = capsys.readouterr().out
    assert "a500" in out and "a3000" in out


def test_a_machine_name_boots_that_machine(monkeypatch):
    calls = []
    monkeypatch.setattr(cli.home, "run", lambda args: calls.append(args) or 0)

    assert cli.main(["a500", "-G"]) == 0

    assert calls[0][:2] == ["--model", "A500"]
    assert calls[0][-1] == "-G"


def test_init_scaffolds_the_current_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("AMIGA_ENV_ROOT")
    monkeypatch.chdir(tmp_path)

    assert cli.main(["init"]) == 0

    assert (tmp_path / "amiga.toml").is_file()
