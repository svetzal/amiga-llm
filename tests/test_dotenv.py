from pathlib import Path

import pytest
from amiga_env.dotenv import folder, load, merged, parse, render_empty, render_example


def test_reads_key_value_lines_comments_and_quotes():
    text = """
# a comment
A=/plain/path
export B = "/quoted path/with # hash"
C='single'
D=/path # trailing note
E=
"""
    assert parse(text) == {
        "A": "/plain/path",
        "B": "/quoted path/with # hash",
        "C": "single",
        "D": "/path",
        "E": "",
    }


@pytest.mark.parametrize("line", ["no equals sign", "1BAD=x", "=value"])
def test_refuses_a_line_that_is_not_key_value(line):
    with pytest.raises(SystemExit, match="not KEY=VALUE"):
        parse(line)


def test_a_missing_file_has_no_values(tmp_path):
    assert load(tmp_path / ".env") == {}


def test_real_variables_override_the_file():
    assert merged({"A": "file", "B": "file"}, {"A": "real"}) == {"A": "real", "B": "file"}


def test_a_folder_expands_the_home_directory_and_an_empty_value_is_unset():
    assert folder("~/Amiga") == Path.home() / "Amiga"
    assert folder("") is None
    assert folder(None) is None


def test_the_example_documents_each_variable_with_an_empty_value():
    text = render_example([("A_DIR", "the a folder")])

    assert text.endswith("\n# the a folder\nA_DIR=\n")
    assert parse(text) == {"A_DIR": ""}
    assert parse(render_empty(["A_DIR", "B_DIR"])) == {"A_DIR": "", "B_DIR": ""}
