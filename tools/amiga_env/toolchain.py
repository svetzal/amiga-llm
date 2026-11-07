"""Build the pinned vasm and vlink into .tools/ from their source tarballs.

The authors publish versioned tarballs at http://phoenix.owl.de/tags/ over
plain HTTP, with no checksums of their own, so each archive's SHA-256 is pinned
here and checked before anything is unpacked. The archive is untrusted: it is
unpacked into a fresh empty directory, its members must all sit under the one
top-level directory the tool is known to use, and the only thing run from it
is its Makefile. Each version gets its own directory under .tools/<tool>/ with
a `current` link, the same layout as Amiberry.

To move to a newer release, change the version and SHA-256 below. `amiga-env
doctor` says when the listing has a newer one.
"""

import hashlib
import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import project

BASE_URL = "http://phoenix.owl.de/tags/"
USER_AGENT = "amiga-llm-tools"


@dataclass(frozen=True)
class Source:
    name: str  # also the archive's top-level directory
    version: str  # as the authors write it, for example "2.0f"
    sha256: str
    make_args: tuple[str, ...]
    products: tuple[str, ...]  # files the build leaves in the top-level directory

    @property
    def archive(self) -> str:
        return archive_name(self.name, self.version)

    @property
    def url(self) -> str:
        return BASE_URL + self.archive

    @property
    def tool_dir(self) -> Path:
        return project.tools_dir() / self.name


VASM = Source(
    name="vasm",
    version="2.0f",
    sha256="c84b2de1cbb87831795fe64a85c5d9a7002a766e3a7c30b0a2d7d5e99d878f49",
    make_args=("CPU=m68k", "SYNTAX=mot"),
    products=("vasmm68k_mot", "vobjdump"),
)
VLINK = Source(
    name="vlink",
    version="0.18a",
    sha256="8d151cdd30a4feb575a364e68810c2bc300fe1a7c074dbbee6fd1175a6c5bfae",
    make_args=(),
    products=("vlink",),
)
SOURCES = (VASM, VLINK)


def archive_name(name: str, version: str) -> str:
    """`vasm`, `2.0f` -> `vasm2_0f.tar.gz`, the authors' naming."""
    return f"{name}{version.replace('.', '_')}.tar.gz"


def listed_versions(listing: str, name: str) -> list[str]:
    """Versions of `name` that a directory listing links to, oldest first."""
    found = set(re.findall(rf'href="{name}(\d+)_(\d+)([a-z]?)\.tar\.gz"', listing))
    return sorted((f"{major}.{minor}{letter}" for major, minor, letter in found), key=version_key)


def version_key(version: str) -> tuple[int, int, str]:
    """Order `1.9f` < `2.0` < `2.0a`. Minor numbers compare as numbers: 0.9 < 0.16."""
    match = re.fullmatch(r"(\d+)\.(\d+)([a-z]?)", version)
    if match is None:
        raise ValueError(f"not a vasm/vlink version: {version}")
    major, minor, letter = match.groups()
    return int(major), int(minor), letter


def check_digest(payload: bytes, source: Source) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    if digest != source.sha256:
        raise SystemExit(
            f"Checksum mismatch for {source.archive}: got {digest}, pinned {source.sha256}"
        )
    return digest


def stray_members(names: list[str], top: str) -> list[str]:
    """Archive members that are not `top` or inside it."""
    return [n for n in names if n != top and not n.startswith(f"{top}/")]


def make_command(source: Source, jobs: int) -> list[str]:
    """The build: the archive's own Makefile, with the host C compiler."""
    return ["make", f"-j{jobs}", "CC=cc", *source.make_args]


def installed_version(source: Source) -> str | None:
    current = source.tool_dir / "current"
    return current.resolve().name if current.exists() else None


def binary(product: str) -> Path:
    """Path of an installed tool, for example `vasmm68k_mot`."""
    for source in SOURCES:
        if product in source.products:
            path = source.tool_dir / "current" / product
            if not path.exists():
                raise SystemExit(f"{product} is not installed; run `amiga-env toolchain`")
            return path
    raise SystemExit(f"{product} is not part of the toolchain")


def fetch_listing() -> str:
    return _get(BASE_URL).decode("latin-1")


def install_all(force: bool = False) -> None:
    for source in SOURCES:
        install(source, force)


def install(source: Source, force: bool = False) -> Path:
    target = source.tool_dir / source.version
    if not force and all((target / p).exists() for p in source.products):
        _point_current(source.tool_dir, target)
        print(f"{source.name} {source.version} already installed at {target}")
        return target

    print(f"Downloading {source.url}")
    payload = _get(source.url)
    digest = check_digest(payload, source)

    source.tool_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=source.tool_dir))
    try:
        unpacked = staging / "src"
        unpacked.mkdir()  # fresh and empty: the archive is the only thing in it
        _unpack(payload, unpacked, source)
        build_dir = unpacked / source.name
        _build(source, build_dir)
        out = staging / source.version
        out.mkdir()
        for product in source.products:
            shutil.copy2(build_dir / product, out / product)
        (out / "SHA256").write_text(f"{digest}  {source.archive}\n")
        if target.exists():
            shutil.rmtree(target)
        shutil.move(out, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    _point_current(source.tool_dir, target)
    print(f"Installed {source.name} {source.version} at {target}")
    return target


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def _unpack(payload: bytes, dest: Path, source: Source) -> None:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        stray = stray_members(archive.getnames(), source.name)
        if stray:
            raise SystemExit(f"{source.archive} has members outside {source.name}/: {stray[:5]}")
        # The "data" filter refuses links out of dest, device files and absolute paths.
        archive.extractall(dest, filter="data")


def _build(source: Source, build_dir: Path) -> None:
    print(f"Building {source.name} {source.version}")
    result = subprocess.run(
        make_command(source, os.cpu_count() or 1),
        cwd=build_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout[-4000:], result.stderr[-4000:], sep="\n")
        raise SystemExit(f"Building {source.name} failed with exit code {result.returncode}")


def _point_current(tool_dir: Path, target: Path) -> None:
    current = tool_dir / "current"
    if current.is_symlink() or current.exists():
        current.unlink()
    current.symlink_to(target.name)
