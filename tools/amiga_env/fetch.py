"""Download a pinned file, check it, and unpack it when it is an archive.

A download is untrusted data. It goes into a fresh directory of its own,
its size and SHA-256 must match the manifest before anything reads it, and
an archive is unpacked by reading its members as data: only regular files
and directories, every path inside the destination, and no execute bits.
Nothing from a download is ever run.
"""

import hashlib
import shutil
import stat
import tarfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

USER_AGENT = "amiga-env"
UNPACK_FORMATS = ("zip", "tar")
CHUNK = 1 << 20

Getter = Callable[[str, Path, int], None]


def http_get(url: str, out: Path, max_bytes: int) -> None:
    """Stream url into out, stopping if it grows past max_bytes."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    written = 0
    with urllib.request.urlopen(request, timeout=120) as response, out.open("wb") as f:
        for chunk in iter(lambda: response.read(CHUNK), b""):
            written += len(chunk)
            if written > max_bytes:
                raise SystemExit(f"{url} is larger than the {max_bytes} bytes the manifest says")
            f.write(chunk)


def fetch(
    url: str, sha256: str, size: int, work: Path, unpack: str | None, get: Getter = http_get
) -> Path:
    """Download url into the empty directory work and return what to install.

    That is the checked file itself, or, for an archive, a directory holding
    its unpacked members.
    """
    if any(work.iterdir()):
        raise SystemExit(f"{work} must be empty before a download")
    archive = work / "download"
    get(url, archive, size)
    found_size = archive.stat().st_size
    if found_size != size:
        raise SystemExit(f"{url}: {found_size} bytes, but the manifest says {size}")
    found = file_sha256(archive)
    if found != sha256:
        raise SystemExit(f"{url}: SHA-256 {found}, but the manifest says {sha256}")
    if unpack is None:
        return archive
    tree = work / "unpacked"
    tree.mkdir()
    UNPACKERS[unpack](archive, tree)
    archive.unlink()
    return tree


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def member_path(name: str, into: Path) -> Path:
    """Where an archive member goes under into; refuses any path that leaves it."""
    pure = PurePosixPath(name.replace("\\", "/"))
    if pure.is_absolute() or ".." in pure.parts or not pure.parts or ":" in pure.parts[0]:
        raise SystemExit(f"archive member {name!r} would land outside the destination")
    return into.joinpath(*pure.parts)


def unpack_zip(archive: Path, into: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            kind = stat.S_IFMT(info.external_attr >> 16)  # 0 when the zip records no type
            if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise SystemExit(f"archive member {info.filename!r} is not a file or directory")
            target = member_path(info.filename, into)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
            target.chmod(0o644)


def unpack_tar(archive: Path, into: Path) -> None:
    with tarfile.open(archive) as tf:
        for member in tf:
            if not (member.isfile() or member.isdir()):
                raise SystemExit(f"archive member {member.name!r} is not a file or directory")
            target = member_path(member.name, into)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            src = tf.extractfile(member)
            with src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, CHUNK)
            target.chmod(0o644)


UNPACKERS = {"zip": unpack_zip, "tar": unpack_tar}
