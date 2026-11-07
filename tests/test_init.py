import pytest
from amiga_env.dotenv import parse
from amiga_env.init import init, missing_ignore_lines, template, with_ignore_lines
from amiga_env.media import load_manifest
from amiga_env.profile import parse_config

FILES = [
    "amiga.toml",
    "media/manifest.toml",
    "examples/hello/hello.s",
    "Makefile",
    ".env.example",
    ".env",
    ".gitignore",
]


def _actions(report):
    return {path: action for action, path in report}


def test_a_fresh_directory_gets_every_file(tmp_path):
    report = _actions(init(tmp_path))

    assert report == dict.fromkeys(FILES, "created")
    assert all((tmp_path / f).is_file() for f in FILES)


def test_the_scaffold_is_valid_and_empty(tmp_path):
    init(tmp_path)

    assert parse_config((tmp_path / "amiga.toml").read_text()) == {}
    manifest = load_manifest(tmp_path / "media" / "manifest.toml")
    assert manifest.items == []
    assert set(manifest.sources) == {"amiga_forever", "amigaos32", "collection"}
    variables = {"AMIGA_FOREVER_DIR": "", "AMIGAOS32_DIR": "", "AMIGA_COLLECTION_DIR": ""}
    assert parse((tmp_path / ".env.example").read_text()) == variables
    assert parse((tmp_path / ".env").read_text()) == variables
    assert (tmp_path / "examples/hello/hello.s").read_text() == template("hello.s")


def test_the_example_machine_parses_once_uncommented():
    text = template("amiga.toml")
    example = text[text.index("# [machines.") :]

    uncommented = "\n".join(line.removeprefix("# ") for line in example.splitlines())

    assert list(parse_config(uncommented)) == ["a500"]


def test_running_twice_keeps_everything(tmp_path):
    init(tmp_path)
    before = {f: (tmp_path / f).read_text() for f in FILES}

    report = _actions(init(tmp_path))

    assert report == dict.fromkeys(FILES, "kept")
    assert {f: (tmp_path / f).read_text() for f in FILES} == before


def test_existing_files_are_kept(tmp_path):
    (tmp_path / "Makefile").write_text("all:\n\techo mine\n")
    (tmp_path / "amiga.toml").write_text("# mine\n")

    report = _actions(init(tmp_path))

    assert report["Makefile"] == report["amiga.toml"] == "kept"
    assert (tmp_path / "Makefile").read_text() == "all:\n\techo mine\n"


def test_force_replaces_only_inits_own_files(tmp_path):
    init(tmp_path)
    for name in FILES:
        (tmp_path / name).write_text((tmp_path / name).read_text() + "# edited\n")
    (tmp_path / "media" / "kick.rom").write_bytes(b"licensed")

    report = _actions(init(tmp_path, force=True))

    replaced = {"amiga.toml", "examples/hello/hello.s", ".env.example"}
    assert {f for f, a in report.items() if a == "replaced"} == replaced
    for name in set(FILES) - replaced:
        assert (tmp_path / name).read_text().endswith("# edited\n")
    assert (tmp_path / "media" / "kick.rom").read_bytes() == b"licensed"


def test_gitignore_gains_only_the_missing_rules(tmp_path):
    (tmp_path / ".gitignore").write_text("__pycache__/\nbuild/\n")

    assert _actions(init(tmp_path))[".gitignore"] == "updated"

    lines = (tmp_path / ".gitignore").read_text().splitlines()
    assert lines[:2] == ["__pycache__/", "build/"]
    assert lines.count("build/") == 1
    assert {"media/*", "!media/manifest.toml", "!media/manifest.lock.json", ".env"} <= set(lines)


@pytest.mark.parametrize("existing", ["", "x\n"])
def test_nothing_missing_means_no_change(existing):
    assert with_ignore_lines(existing, []) == existing


def test_comments_are_not_rules():
    assert missing_ignore_lines("", "# note\n.env\n") == [".env"]
