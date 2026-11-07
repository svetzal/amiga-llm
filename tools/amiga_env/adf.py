"""Make bootable floppy images for the baseline A500 with amitools' xdftool.

Kickstart 1.2 reads only the original file system (OFS, `DOS\\0`) and runs the
1.x bootblock. xdftool's `boot install` writes its 2.x/3.x boot code unless it
is told `boot1x`; the `boot1x` code is byte for byte the boot code on the
Workbench 1.2 disk (see research/toolchain.md).
"""

import tempfile
from pathlib import Path

from amitools.tools import xdftool

DD_SIZE = "880Ki"  # 80 cylinders x 2 heads x 11 sectors x 512 bytes
BOOT_CODE = "boot1x"
STARTUP = "s/startup-sequence"
MAX_NAME = 30  # OFS file and volume names
SEPARATOR = "+"  # xdftool's command separator


def amiga_name(path: Path) -> str:
    """The name a host file takes in the root of the disk."""
    name = path.name
    _check_name(name, f"file name {name!r}")
    return name


def check_label(label: str) -> str:
    _check_name(label, f"volume label {label!r}")
    return label


def startup_sequence(commands: list[str]) -> str:
    """One AmigaDOS command per line, LF endings, as the 1.2 shell reads it."""
    for command in commands:
        if "\n" in command or "\r" in command:
            raise SystemExit(f"a startup command must be one line: {command!r}")
    return "".join(f"{command}\n" for command in commands)


def xdftool_args(
    image: Path, files: list[Path], label: str, startup_file: Path | None = None
) -> list[str]:
    """xdftool arguments that build the whole disk in one pass."""
    names = [amiga_name(f) for f in files]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise SystemExit(f"two files would share the name {duplicates[0]} on the disk")
    steps = [
        ["create", f"size={DD_SIZE}"],
        ["format", check_label(label), "ofs"],
        ["boot", "install", BOOT_CODE],
        *(["write", str(f), n] for f, n in zip(files, names, strict=True)),
    ]
    if startup_file is not None:
        steps += [["makedir", "s"], ["write", str(startup_file), STARTUP]]
    args = ["-f", "-s", SEPARATOR, str(image)]
    for index, step in enumerate(steps):
        args += ([SEPARATOR] if index else []) + step
    return args


def make_adf(
    image: Path, files: list[Path], startup: list[str] | None = None, label: str | None = None
) -> Path:
    """Write a bootable OFS floppy holding `files` in its root."""
    for f in files:
        if not f.is_file():
            raise SystemExit(f"not a file: {f}")
    image.parent.mkdir(parents=True, exist_ok=True)
    # xdftool picks the image type from the suffix, so the partial keeps `.adf`.
    partial = image.with_name(f".{image.stem}.partial.adf")
    with tempfile.TemporaryDirectory(prefix="amiga-adf-") as scratch:
        startup_file = None
        if startup:
            startup_file = Path(scratch) / "startup-sequence"
            startup_file.write_text(startup_sequence(startup))
        args = xdftool_args(partial, files, label or image.stem, startup_file)
        code = xdftool.main(args)
    if code != 0:
        partial.unlink(missing_ok=True)
        raise SystemExit(f"xdftool failed with exit code {code}")
    partial.replace(image)
    print(f"Wrote {image}")
    return image


def _check_name(name: str, what: str) -> None:
    if not name or len(name) > MAX_NAME:
        raise SystemExit(f"{what} must be 1 to {MAX_NAME} characters")
    if any(c in name for c in ":/") or name == SEPARATOR:
        raise SystemExit(f"{what} may not contain ':' or '/', or be {SEPARATOR!r}")
