import hashlib
import subprocess

import pytest
from amiga_env.guard import check, find_offences, locked_digests

ROM = hashlib.sha256(b"kickstart").hexdigest()


def _offences(tracked, locked=frozenset(), digests=None):
    digests = digests or {}
    return {(o.path, o.reason) for o in find_offences(tracked, set(locked), digests.get)}


def test_the_manifest_and_lock_may_be_tracked():
    assert _offences(["media/manifest.toml", "media/manifest.lock.json", "README.md"]) == set()


def test_anything_else_under_media_is_an_offence():
    assert _offences(["media/notes.txt"]) == {("media/notes.txt", "under media/")}


@pytest.mark.parametrize("path", ["roms/Kick13.ROM", "x/disk.adf", "a.uae", "manual.pdf"])
def test_a_media_suffix_anywhere_is_an_offence(path):
    assert _offences([path]) == {(path, "has a media suffix")}


def test_a_renamed_copy_of_locked_media_is_an_offence():
    assert _offences(["src/data.s"], {ROM}, {"src/data.s": ROM}) == {
        ("src/data.s", "is a copy of locked media")
    }


@pytest.mark.parametrize("path", [".env", "sub/.env"])
def test_a_local_env_file_is_an_offence(path):
    assert _offences([path]) == {(path, "is a local .env")}


def test_the_env_example_may_be_tracked():
    assert _offences([".env.example"]) == set()


def test_locked_digests_are_the_files_not_the_trees():
    lock = '{"a.rom": {"kind": "file", "sha256": "aa"}, "ndk": {"kind": "tree", "sha256": "bb"}}'

    assert locked_digests(lock) == {"aa"}


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_a_directory_outside_git_has_nothing_to_check(tmp_path):
    assert check(tmp_path) is None


def test_check_sees_staged_files(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / ".env").write_text("A_DIR=/x\n")
    (tmp_path / "ok.s").write_text("rts\n")
    _git(tmp_path, "add", "-f", ".env", "ok.s")

    assert [o.path for o in check(tmp_path)] == [".env"]
