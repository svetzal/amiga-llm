import pytest
from amiga_env import project
from amiga_env.project import ENV_VAR, find_root


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "proj" / "src" / "deep").mkdir(parents=True)
    (tmp_path / "proj" / "amiga.toml").write_text("")
    return tmp_path


def test_the_root_is_the_nearest_directory_with_amiga_toml(tree):
    assert find_root(tree / "proj" / "src" / "deep", {}) == (tree / "proj").resolve()


def test_the_start_directory_itself_can_be_the_root(tree):
    assert find_root(tree / "proj", {}) == (tree / "proj").resolve()


def test_there_is_no_root_above_every_amiga_toml(tree):
    assert find_root(tree, {}) is None


def test_the_variable_overrides_discovery(tree):
    (tree / "other").mkdir()
    (tree / "other" / "amiga.toml").write_text("")

    assert find_root(tree / "proj", {ENV_VAR: str(tree / "other")}) == (tree / "other").resolve()


def test_a_variable_naming_a_directory_without_amiga_toml_is_an_error(tree):
    with pytest.raises(SystemExit, match="has no amiga.toml"):
        find_root(tree / "proj", {ENV_VAR: str(tree)})


def test_commands_outside_a_project_tell_the_user_to_run_init(tree, monkeypatch):
    monkeypatch.delenv(ENV_VAR)
    monkeypatch.chdir(tree)

    with pytest.raises(SystemExit, match="amiga-env init"):
        project.root()


def test_the_working_directories_hang_off_the_root(tree, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tree / "proj"))
    root = (tree / "proj").resolve()

    assert project.media_dir() == root / "media"
    assert project.tools_dir() == root / ".tools"
    assert project.runs_dir() == root / "runs"
    assert project.build_dir() == root / "build"
