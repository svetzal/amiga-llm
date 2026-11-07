"""Machine profiles from the project's amiga.toml, as Amiberry arguments.

Each `[machines.NAME]` table starts from one of Amiberry's quick-start models
and names the Kickstart ROM and floppy in media/ that it boots:

    [machines.a500]
    model = "A500"                               # Amiberry --model
    kickstart = "rom/forever/amiga-os-120.rom"   # relative to media/, required
    disk = "adf/1.2/workbench.adf"               # relative to media/, optional
    settings = ["ntsc=true"]                     # each becomes -s, optional
    purpose = "what this machine is for"         # shown in --help, optional

A machine can also boot a system built from `systems/NAME.toml` (see
system.py) as DH0:, and mount project folders as further volumes:

    system = "a3000-dev"                         # boots runs/systems/a3000-dev
    volumes = { Work = "work" }                  # label = folder in the project
"""

import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from . import project, session

SYSTEM_VOLUME = "System"
SYSTEM_DEVICE = "DH0"

TOP_LEVEL_KEYS = {"machines"}
REQUIRED_KEYS = {"model", "kickstart"}
OPTIONAL_KEYS = {"disk", "settings", "purpose", "system", "volumes"}
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,29}")
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")


@dataclass(frozen=True)
class Machine:
    model: str
    kickstart: Path
    disk: Path | None
    settings: tuple[str, ...]
    purpose: str
    system: str | None = None
    volumes: tuple[tuple[str, Path], ...] = ()


def parse_config(text: str, reserved: Iterable[str] = ()) -> dict[str, Machine]:
    """Machines in amiga.toml text, checked. `reserved` names may not be machines."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise SystemExit(f"amiga.toml is not valid TOML: {error}") from error
    _no_unknown_keys(data, TOP_LEVEL_KEYS, "amiga.toml")
    tables = data.get("machines", {})
    if not isinstance(tables, dict):
        raise SystemExit("amiga.toml: `machines` must be a table of [machines.NAME] tables")
    reserved = set(reserved)
    return {name: _machine(name, table, reserved) for name, table in tables.items()}


def load_machines(path: Path | None = None, reserved: Iterable[str] = ()) -> dict[str, Machine]:
    path = path or project.config_path()
    return parse_config(path.read_text(), reserved)


def machine_args(
    machine: Machine, disk: Path | None = None, media: Path | None = None, root: Path | None = None
) -> list[str]:
    """Arguments that boot `machine` from `disk`, or from its own floppy if it names one,
    with its system as DH0: and its volumes after it."""
    args = base_args(machine, media)
    floppy = disk or ((media or project.media_dir()) / machine.disk if machine.disk else None)
    if floppy is not None:
        args[4:4] = ["-0", str(floppy)]
    return args + session.volume_args(volumes(machine, root))


def base_args(machine: Machine, media: Path | None = None) -> list[str]:
    """The model, Kickstart and settings of a machine, with no disks or volumes."""
    media = media or project.media_dir()
    args = ["--model", machine.model, "-r", str(media / machine.kickstart)]
    for setting in machine.settings:
        args += ["-s", setting]
    return args


def volumes(machine: Machine, root: Path | None = None) -> list[session.Volume]:
    """DH0: for the machine's built system, then DH1: and on for its project folders."""
    root = root or project.root()
    mounted = []
    if machine.system is not None:
        tree = project.system_tree(machine.system, root)
        mounted.append(session.Volume(SYSTEM_DEVICE, SYSTEM_VOLUME, tree, 0))
    first = len(mounted)
    for index, (label, folder) in enumerate(machine.volumes, start=first):
        mounted.append(session.Volume(f"DH{index}", label, root / folder))
    return mounted


def media_paths(machine: Machine) -> dict[str, Path]:
    """The files a machine needs in media/, by role."""
    paths = {"kickstart": machine.kickstart}
    if machine.disk is not None:
        paths["disk"] = machine.disk
    return paths


def _machine(name: str, table: object, reserved: set[str]) -> Machine:
    where = f"amiga.toml [machines.{name}]"
    if not NAME.fullmatch(name):
        raise SystemExit(f"{where}: a machine name is lower case letters, digits, - and _")
    if name in reserved:
        raise SystemExit(f"{where}: {name} is an amiga-env command; choose another name")
    if not isinstance(table, dict):
        raise SystemExit(f"{where} must be a table")
    _no_unknown_keys(table, REQUIRED_KEYS | OPTIONAL_KEYS, where)
    missing = sorted(REQUIRED_KEYS - table.keys())
    if missing:
        raise SystemExit(f"{where} has no {', '.join(missing)}")
    settings = table.get("settings", [])
    if not isinstance(settings, list) or not all(_is_setting(s) for s in settings):
        raise SystemExit(f'{where}: settings is a list of "key=value" strings')
    return Machine(
        model=_text(table["model"], f"{where} model"),
        kickstart=_media_path(table["kickstart"], f"{where} kickstart"),
        disk=_media_path(table["disk"], f"{where} disk") if "disk" in table else None,
        settings=tuple(settings),
        purpose=_text(table.get("purpose", f"boot the {name}"), f"{where} purpose"),
        system=_system(table.get("system"), where),
        volumes=_volumes(table.get("volumes", {}), where),
    )


def _system(value: object, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise SystemExit(f'{where}: system names a recipe in systems/, such as "a3000-dev"')
    return value


def _volumes(value: object, where: str) -> tuple[tuple[str, Path], ...]:
    if not isinstance(value, dict):
        raise SystemExit(f'{where}: volumes is a table of Label = "folder in the project"')
    mounted = []
    for label, folder in value.items():
        if not LABEL.fullmatch(label) or label.lower() == SYSTEM_VOLUME.lower():
            raise SystemExit(f"{where}: {label!r} is not a usable volume name")
        path = Path(_text(folder, f"{where} volumes.{label}"))
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"{where}: volumes.{label} must be a folder inside the project")
        mounted.append((label, path))
    return tuple(mounted)


def _no_unknown_keys(table: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(table.keys() - allowed)
    if unknown:
        raise SystemExit(
            f"{where}: unknown key {', '.join(unknown)} (allowed: {', '.join(sorted(allowed))})"
        )


def _text(value: object, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"{what} must be a non-empty string")
    return value


def _media_path(value: object, what: str) -> Path:
    path = Path(_text(value, what))
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"{what} must be a path inside media/: {value}")
    return path


def _is_setting(value: object) -> bool:
    return isinstance(value, str) and "=" in value and not value.startswith("=")
