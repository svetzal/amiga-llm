"""Keep licensed media, and the paths to it, out of git.

Media is copyrighted and lives only in media/, which git ignores except for
the manifest and its lock. .env holds where each source is on one person's
disk, so it is never tracked either. The guard looks at what git tracks (the
index, so staged files count), which also catches a ROM or disk image
committed outside media/ or under another name.
"""

import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .dotenv import ENV_FILE
from .media import LOCK_NAME, MANIFEST_NAME

MEDIA_SUFFIXES = {
    ".rom", ".key", ".adf", ".adz", ".dms", ".hdf", ".hdz", ".ipf", ".lha", ".lzx",
    ".uae", ".uss", ".iso", ".cue", ".bin", ".pdf", ".zip", ".7z", ".dmg",
}  # fmt: skip
TRACKED_IN_MEDIA = {f"media/{MANIFEST_NAME}", f"media/{LOCK_NAME}"}


@dataclass(frozen=True)
class Offence:
    path: str
    reason: str


def find_offences(
    tracked: Iterable[str], locked: set[str], digest_of: Callable[[str], str | None]
) -> list[Offence]:
    """Tracked paths that are, or may be, licensed media.

    `locked` holds the SHA-256 of every file in manifest.lock.json; `digest_of`
    gives a tracked path's SHA-256, or None when it is not a regular file.
    """
    offences = []
    for path in tracked:
        if path == ENV_FILE or path.endswith(f"/{ENV_FILE}"):
            offences.append(Offence(path, "is a local .env"))
        elif path.startswith("media/") and path not in TRACKED_IN_MEDIA:
            offences.append(Offence(path, "under media/"))
        elif any(path.lower().endswith(suffix) for suffix in MEDIA_SUFFIXES):
            offences.append(Offence(path, "has a media suffix"))
        elif locked and digest_of(path) in locked:
            offences.append(Offence(path, "is a copy of locked media"))
    return offences


def locked_digests(lock_text: str) -> set[str]:
    return {e["sha256"] for e in json.loads(lock_text).values() if e.get("kind") == "file"}


def tracked_files(root: Path) -> list[str] | None:
    """Paths git tracks under root, relative to it; None when root is not in a checkout."""
    if shutil.which("git") is None:
        return None
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [p for p in out.stdout.decode().split("\0") if p]


def check(root: Path) -> list[Offence] | None:
    """Offences in the checkout at root; None when root is not in a git checkout."""
    tracked = tracked_files(root)
    if tracked is None:
        return None
    lock = root / "media" / LOCK_NAME
    locked = locked_digests(lock.read_text()) if lock.is_file() else set()
    return find_offences(tracked, locked, lambda p: _digest(root / p))


def run(root: Path) -> int:
    offences = check(root)
    if offences is None:
        print(f"guard     {root} is not in a git checkout; nothing is tracked")
        return 0
    if offences:
        print("guard     git tracks files that must stay local:")
        for offence in offences:
            print(f"          {offence.path} ({offence.reason})")
        print("          remove it with `git rm --cached PATH` before committing")
        return 1
    print("guard     no licensed media is tracked")
    return 0


def _digest(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()
