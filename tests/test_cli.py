from pathlib import Path

from amiga_env.cli import paths_outside

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
