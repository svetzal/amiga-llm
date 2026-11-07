"""Give Amiberry a private home directory inside the project.

Amiberry reads its settings from ~/Library/Application Support/Amiberry
(macOS) and stores content under a base path named there. A personal setup
can point that global file anywhere. Running the emulator with HOME set to
runs/home/ moves every one of those paths into the project, so a run never
reads or writes anything outside it. The marker-file portable mode is not an
option on macOS: the system refuses writes inside the app bundle.
"""

import os
import platform
import subprocess
from pathlib import Path

from . import amiberry, project


def home_dir() -> Path:
    return project.runs_dir() / "home"


def settings_dir(home: Path) -> Path:
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "Amiberry"
    return home / ".config" / "amiberry"


def content_dir(home: Path) -> Path:
    return home / "Amiberry"


def render_conf(home: Path, media: Path | None = None) -> str:
    """The path settings this project owns. Amiberry fills in the rest."""
    media = media or project.media_dir()
    content = content_dir(home)
    return (
        f"base_content_path={content}/\n"
        f"rom_path={media / 'rom'}/\n"
        f"saveimage_dir={content / 'SaveImages'}/\n"
        f"plugins_dir={content / 'Plugins'}/\n"
        f"floppy_sounds_dir={content / 'Data' / 'Floppy_Sounds'}/\n"
    )


def merge_conf(existing: str, owned: str) -> str:
    """Set the keys this project owns; keep every other line Amiberry has saved.

    Amiberry rewrites amiberry.conf when its settings change, so the file cannot
    simply be replaced. An owned key takes its rendered value in place, any
    repeat of it is dropped, and an owned key the file lacks is appended.
    """
    wanted = {line.split("=", 1)[0]: line for line in owned.splitlines()}
    placed: set[str] = set()
    merged = []
    for line in existing.splitlines():
        key = line.split("=", 1)[0]
        if key in wanted:
            if key not in placed:
                merged.append(wanted[key])
                placed.add(key)
        else:
            merged.append(line)
    merged.extend(line for key, line in wanted.items() if key not in placed)
    return "\n".join(merged) + "\n"


def prepare(home: Path | None = None, media: Path | None = None) -> Path:
    home = home or home_dir()
    conf = settings_dir(home) / "amiberry.conf"
    conf.parent.mkdir(parents=True, exist_ok=True)
    content_dir(home).mkdir(parents=True, exist_ok=True)
    existing = conf.read_text() if conf.exists() else ""
    wanted = merge_conf(existing, render_conf(home, media))
    if wanted != existing:
        conf.write_text(wanted)
    return conf


def environment(home: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["HOME"] = str(home or home_dir())
    return env


def run(args: list[str], home: Path | None = None) -> int:
    home = home or home_dir()
    binary = amiberry.installed_binary()
    prepare(home)
    return subprocess.run([str(binary), *args], env=environment(home), check=False).returncode
