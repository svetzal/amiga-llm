"""The repository is public. Licensed media must never be tracked.

These tests look at what git tracks, so they also catch a ROM or disk image
committed outside media/ or under another name.
"""

import hashlib
import json
import shutil
import subprocess

import pytest
from amiga_env import MEDIA_DIR, ROOT

MEDIA_SUFFIXES = {
    ".rom", ".key", ".adf", ".adz", ".dms", ".hdf", ".hdz", ".ipf", ".lha", ".lzx",
    ".uae", ".uss", ".iso", ".cue", ".bin", ".pdf", ".zip", ".7z", ".dmg",
}  # fmt: skip
TRACKED_IN_MEDIA = {"media/manifest.toml", "media/manifest.lock.json"}


def _tracked() -> list[str]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    return [p for p in out.decode().split("\0") if p]


def test_only_the_manifest_and_lock_are_tracked_under_media():
    tracked = {p for p in _tracked() if p.startswith("media/")}

    assert tracked <= TRACKED_IN_MEDIA


def test_no_tracked_file_has_a_media_suffix():
    found = [p for p in _tracked() if any(p.lower().endswith(s) for s in MEDIA_SUFFIXES)]

    assert found == []


def test_no_tracked_file_is_a_copy_of_locked_media():
    lock = json.loads((MEDIA_DIR / "manifest.lock.json").read_text())
    locked = {e["sha256"] for e in lock.values() if e.get("kind") == "file"}
    copies = [
        p
        for p in _tracked()
        if (ROOT / p).is_file() and hashlib.sha256((ROOT / p).read_bytes()).hexdigest() in locked
    ]

    assert copies == []
