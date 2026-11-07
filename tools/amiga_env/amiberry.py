"""Fetch the latest Amiberry release into .tools/amiberry/ and resolve its binary.

The download is checked against the release's SHA256SUMS before anything is
unpacked. Each version gets its own directory; `current` is a symlink to the
one in use, so an upgrade is reversible by pointing the link back.

The release's libretro core (the same emulator as a library, see libretro.py)
goes beside the app, checked the same way, on hosts that have one.
"""

import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import project

REPO = "BlitterStudio/amiberry"
API = f"https://api.github.com/repos/{REPO}/releases"
USER_AGENT = "amiga-llm-tools"
# platform.machine() spelling -> the spelling in Amiberry's AppImage names
LINUX_ARCHES = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}
CORE_GLOB = "amiberry-libretro-*"


@dataclass(frozen=True)
class Release:
    tag: str
    assets: dict[str, str]  # asset name -> download URL

    @property
    def version(self) -> str:
        return self.tag.removeprefix("v")


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fetch_release(tag: str | None = None) -> Release:
    url = f"{API}/tags/{tag}" if tag else f"{API}/latest"
    data = json.loads(_get(url))
    return Release(
        tag=data["tag_name"],
        assets={a["name"]: a["browser_download_url"] for a in data["assets"]},
    )


def asset_name(release: Release, system: str, machine: str) -> str:
    """Pick the release asset for this host. Pure, so it is testable."""
    version = release.version
    if system == "Darwin":
        name = f"Amiberry-{version}-macOS-universal.dmg"
    elif system == "Linux" and machine in LINUX_ARCHES:
        name = f"Amiberry-{version}-{LINUX_ARCHES[machine]}.AppImage"
    else:
        raise SystemExit(f"No Amiberry asset rule for {system} {machine}")
    if name not in release.assets:
        raise SystemExit(f"Release {release.tag} has no asset named {name}")
    return name


def core_asset_name(release: Release, system: str, machine: str) -> str:
    """Pick the release's libretro core for this host. Pure, so it is testable."""
    if system == "Darwin" and machine == "arm64":
        name = "amiberry-libretro-macOS-arm64.dylib"
    elif system == "Linux" and machine in LINUX_ARCHES:
        name = f"amiberry-libretro-linux-{LINUX_ARCHES[machine]}.so"
    else:
        raise SystemExit(f"Amiberry has no libretro core for {system} {machine}")
    if name not in release.assets:
        raise SystemExit(f"Release {release.tag} has no asset named {name}")
    return name


def parse_sha256sums(text: str) -> dict[str, str]:
    sums = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            digest, name = parts
            sums[name.lstrip("*")] = digest.lower()
    return sums


def binary_path(version_dir: Path) -> Path:
    app = version_dir / "Amiberry.app" / "Contents" / "MacOS" / "Amiberry"
    if app.exists():
        return app
    images = sorted(version_dir.glob("*.AppImage"))
    if images:
        return images[0]
    raise SystemExit(f"No Amiberry binary in {version_dir}")


def core_path(version_dir: Path) -> Path:
    cores = sorted(version_dir.glob(CORE_GLOB))
    if not cores:
        raise SystemExit(f"No libretro core in {version_dir}; run `amiga-env amiberry --force`")
    return cores[0]


def installed_core() -> Path:
    current = amiberry_dir() / "current"
    if not current.exists():
        raise SystemExit("Amiberry is not installed; run `amiga-env amiberry`")
    return core_path(current.resolve())


def amiberry_dir() -> Path:
    return project.tools_dir() / "amiberry"


def installed_version() -> str | None:
    current = amiberry_dir() / "current"
    return current.resolve().name if current.exists() else None


def installed_binary() -> Path:
    current = amiberry_dir() / "current"
    if not current.exists():
        raise SystemExit("Amiberry is not installed; run `amiga-env amiberry`")
    return binary_path(current.resolve())


def install(tag: str | None = None, force: bool = False) -> Path:
    release = fetch_release(tag)
    base = amiberry_dir()
    target = base / release.version
    sums = parse_sha256sums(_get(release.assets["SHA256SUMS"]).decode())
    if target.exists() and not force:
        _point_current(target)
        _install_core(release, sums, target)
        print(f"Amiberry {release.version} already installed at {target}")
        return binary_path(target)

    name = asset_name(release, platform.system(), platform.machine())
    print(f"Downloading {name}")
    payload = _download(release, sums, name)
    digest = hashlib.sha256(payload).hexdigest()

    base.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=base))
    try:
        download = staging / name
        download.write_bytes(payload)
        unpacked = staging / release.version
        unpacked.mkdir()
        if name.endswith(".dmg"):
            _unpack_dmg(download, unpacked)
        else:
            image = unpacked / name
            shutil.move(download, image)
            image.chmod(0o755)
        (unpacked / "SHA256").write_text(f"{digest}  {name}\n")
        if target.exists():
            shutil.rmtree(target)
        shutil.move(unpacked, target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    _point_current(target)
    _install_core(release, sums, target)
    print(f"Installed Amiberry {release.version} at {target}")
    return binary_path(target)


def _download(release: Release, sums: dict[str, str], name: str) -> bytes:
    """An asset's bytes, checked against SHA256SUMS."""
    if name not in sums:
        raise SystemExit(f"SHA256SUMS for {release.tag} does not list {name}")
    payload = _get(release.assets[name])
    digest = hashlib.sha256(payload).hexdigest()
    if digest != sums[name]:
        raise SystemExit(f"Checksum mismatch for {name}: got {digest}, expected {sums[name]}")
    return payload


def _install_core(release: Release, sums: dict[str, str], target: Path) -> None:
    """Put the release's libretro core beside the app, if the host has one and it is missing."""
    try:
        name = core_asset_name(release, platform.system(), platform.machine())
    except SystemExit as reason:
        print(f"No libretro core installed: {reason}")
        return
    if (target / name).is_file():
        return
    print(f"Downloading {name}")
    payload = _download(release, sums, name)
    (target / name).write_bytes(payload)
    with (target / "SHA256").open("a") as record:
        record.write(f"{hashlib.sha256(payload).hexdigest()}  {name}\n")


def _unpack_dmg(dmg: Path, dest: Path) -> None:
    mount = Path(tempfile.mkdtemp(prefix="amiberry-mnt-"))
    try:
        subprocess.run(
            ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mount), str(dmg)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        apps = list(mount.glob("*.app"))
        if len(apps) != 1:
            raise SystemExit(f"Expected one .app in {dmg.name}, found {len(apps)}")
        # ditto keeps the bundle's signature and extended attributes intact.
        subprocess.run(["ditto", str(apps[0]), str(dest / "Amiberry.app")], check=True)
    finally:
        subprocess.run(["hdiutil", "detach", str(mount)], check=False, stdout=subprocess.DEVNULL)
        mount.rmdir()


def _point_current(target: Path) -> None:
    current = target.parent / "current"
    if current.is_symlink() or current.exists():
        current.unlink()
    current.symlink_to(target.name)
