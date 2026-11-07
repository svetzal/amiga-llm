from pathlib import Path

import pytest
from amiga_env.adf import folders, startup_sequence, xdftool_args
from amiga_env.assemble import outputs, vasm_args


def _steps(args):
    """Split xdftool arguments into the option prefix and the '+'-separated steps."""
    prefix, commands = args[:4], args[4:]
    steps, step = [], []
    for token in commands:
        if token == "+":
            steps.append(step)
            step = []
        else:
            step.append(token)
    return prefix, steps + [step]


def test_the_disk_is_an_ofs_dd_floppy_with_the_1x_bootblock():
    prefix, steps = _steps(xdftool_args(Path("/b/hello.adf"), [Path("/b/hello")], "hello"))

    assert prefix == ["-f", "-s", "+", "/b/hello.adf"]
    assert steps[:3] == [
        ["create", "size=880Ki"],
        ["format", "hello", "ofs"],
        ["boot", "install", "boot1x"],
    ]


def test_files_go_in_the_root_under_their_own_names():
    _, steps = _steps(xdftool_args(Path("o.adf"), [Path("/b/hello"), Path("/x/data.bin")], "v"))

    assert ["write", "/b/hello", "hello"] in steps
    assert ["write", "/x/data.bin", "data.bin"] in steps


def test_a_startup_file_lands_in_s():
    _, steps = _steps(xdftool_args(Path("o.adf"), [Path("hello")], "v", Path("/tmp/ss")))

    assert steps[-2:] == [["makedir", "s"], ["write", "/tmp/ss", "s/startup-sequence"]]


def test_without_a_startup_file_there_is_no_s_directory():
    _, steps = _steps(xdftool_args(Path("o.adf"), [Path("hello")], "v"))

    assert ["makedir", "s"] not in steps


def test_two_files_with_the_same_name_are_refused():
    with pytest.raises(SystemExit, match="share the name"):
        xdftool_args(Path("o.adf"), [Path("a/hello"), Path("b/hello")], "v")


@pytest.mark.parametrize("label", ["", "x" * 31, "bad:name", "a/b"])
def test_labels_must_suit_ofs(label):
    with pytest.raises(SystemExit):
        xdftool_args(Path("o.adf"), [Path("hello")], label)


def test_a_name_longer_than_ofs_allows_is_refused():
    with pytest.raises(SystemExit, match="30 characters"):
        xdftool_args(Path("o.adf"), [Path("a" * 31)], "v")


def test_the_startup_sequence_is_one_command_per_line():
    assert startup_sequence(["hello", "hello again"]) == "hello\nhello again\n"


def test_a_startup_command_spanning_lines_is_refused():
    with pytest.raises(SystemExit):
        startup_sequence(["hello\nformat df0:"])


def test_vasm_writes_a_kickstart_1x_hunk_executable_for_a_68000():
    args = vasm_args(Path("/t/vasmm68k_mot"), Path("hello.s"), Path("build/hello"))

    assert args[0] == "/t/vasmm68k_mot"
    assert {"-m68000", "-Fhunkexe", "-kick1hunks"} <= set(args)
    assert args[-3:] == ["-o", "build/hello", "hello.s"]


def test_a_source_builds_an_executable_and_a_disk_named_after_it():
    assert outputs(Path("examples/hello/hello.s"), Path("/b")) == (
        Path("/b/hello"),
        Path("/b/hello.adf"),
    )


def test_include_folders_and_defines_come_before_the_output():
    args = vasm_args(Path("/t/vasmm68k_mot"), Path("p.s"), Path("b/p"), [Path("data")], {"LOG": 1})

    assert args[-5:] == ["-Idata", "-DLOG=1", "-o", "b/p", "p.s"]


def test_a_file_can_go_to_a_path_in_a_folder_made_before_it():
    files = [Path("/b/piano"), (Path("/r/one.score"), "scores/01-one.score")]

    _, steps = _steps(xdftool_args(Path("o.adf"), files, "v"))

    assert steps.index(["makedir", "scores"]) < steps.index(
        ["write", "/r/one.score", "scores/01-one.score"]
    )
    assert ["write", "/b/piano", "piano"] in steps


def test_each_folder_is_made_once_and_parents_first():
    assert folders(["a/b/x", "a/y", "a/b/z", "top"]) == ["a", "a/b"]


@pytest.mark.parametrize("path", ["scores/" + "x" * 31, "scores//x", "a:b/x"])
def test_every_part_of_a_disk_path_must_suit_ofs(path):
    with pytest.raises(SystemExit):
        xdftool_args(Path("o.adf"), [(Path("/r/x"), path)], "v")
