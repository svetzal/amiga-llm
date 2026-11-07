"""System recipes: how to build an Amiga system disk as a host directory.

A recipe is `systems/NAME.toml` in the project. It names the machine profile
that runs its `amiga` layers and lists ordered layers, each applied to the
system tree (the directory that boots as DH0:):

    description = "AmigaOS 3.2 for development"
    machine = "a3000"          # profile in amiga.toml that runs `amiga` layers

    [[layer]]                  # a whole disk or archive, merged into a path
    type = "unpack"
    media = "adf/3.2/Workbench3.2.adf"
    into = ""                  # path in the system; "" is its root (default)
    exclude = ["Disk.info"]    # paths in the disk to leave out, optional
    decompress = false         # unpack NAME.Z files as NAME, optional

    [[layer]]                  # named files or drawers from a disk or archive
    type = "copy"
    media = "adf/3.2/Install3.2.adf"
    files = { "Libs/icon.library" = "Libs/icon.library" }
    exclude = []               # paths in the disk to leave out, optional
    decompress = false         # as for unpack, optional
    personal = false           # true: export leaves these out, optional

    [[layer]]                  # empty drawers, as the Installer's makedir
    type = "dirs"
    paths = ["Expansion", "Libs/MMU"]

    [[layer]]                  # a text file, written with LF line endings
    type = "file"
    path = "S/User-Startup"
    text = "Assign SC: SYS:SC\\n"
    append = false             # true: add to the end of the file, optional

    [[layer]]                  # an AmigaDOS script run once on the machine
    type = "amiga"
    name = "sasc"
    script = "systems/a3000-dev/install-sasc"   # relative to the project
    disks = ["dev/sasc-6.50/disk1.7z"]  # mounted under their own volume names
    timeout = 1800             # seconds, optional

`media` is a path under media/: an ADF, an archive (.lha, .lzh, .7z, .zip),
an archive that holds exactly one ADF, or any other file, which opens as a
folder holding just that file. `member` names a disk or archive inside it,
which is opened the same way. Files keep the Amiga attributes their disk
gave them (see system.py). Everything here is pure: parsing, checking,
fingerprints and the rebuild plan. system.py does the work.
"""

import hashlib
import json
import re
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
TOP_KEYS = {"description", "machine", "layer"}
DEFAULT_TIMEOUT = 600
# Bump when the meaning of a layer changes, so every system is rebuilt.
FORMAT = 3
ARCHIVE_SUFFIXES = (".lha", ".lzh", ".7z", ".zip")
CONTAINER_SUFFIXES = (".adf", *ARCHIVE_SUFFIXES)


@dataclass(frozen=True)
class MediaRef:
    media: str
    member: str | None = None


@dataclass(frozen=True)
class Unpack:
    source: MediaRef
    into: str
    exclude: tuple[str, ...]
    decompress: bool = False


@dataclass(frozen=True)
class Copy:
    source: MediaRef
    files: tuple[tuple[str, str], ...]
    exclude: tuple[str, ...] = ()
    decompress: bool = False
    personal: bool = False


@dataclass(frozen=True)
class Dirs:
    paths: tuple[str, ...]


@dataclass(frozen=True)
class File:
    path: str
    text: str
    append: bool = False


@dataclass(frozen=True)
class Amiga:
    name: str
    script: str
    disks: tuple[MediaRef, ...]
    timeout: int


Layer = Unpack | Copy | Dirs | File | Amiga


@dataclass(frozen=True)
class Recipe:
    name: str
    description: str
    machine: str | None
    layers: tuple[Layer, ...]


@dataclass(frozen=True)
class Plan:
    """What a build does. When `fresh`, it empties the tree, then restores the
    snapshot taken after `restore` layers if that is set. It applies the
    layers from `start` on. An up-to-date tree needs nothing."""

    start: int
    restore: int | None = None
    fresh: bool = False
    up_to_date: bool = False


def parse(name: str, text: str) -> Recipe:
    """A recipe from its TOML text, checked."""
    where = f"systems/{name}.toml"
    if not NAME.fullmatch(name):
        raise SystemExit(f"{where}: a system name is lower case letters, digits, - and _")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise SystemExit(f"{where} is not valid TOML: {error}") from error
    _no_unknown_keys(data, TOP_KEYS, where)
    tables = data.get("layer", [])
    if not isinstance(tables, list) or not tables:
        raise SystemExit(f"{where} has no [[layer]] tables")
    layers = tuple(_layer(table, f"{where} layer {i + 1}") for i, table in enumerate(tables))
    machine = data.get("machine")
    if any(isinstance(layer, Amiga) for layer in layers) and machine is None:
        raise SystemExit(f"{where}: an amiga layer needs `machine`, the profile that runs it")
    names = [layer.name for layer in layers if isinstance(layer, Amiga)]
    if len(names) != len(set(names)):
        raise SystemExit(f"{where}: two amiga layers share a name")
    return Recipe(
        name=name,
        description=_text(data.get("description", f"the {name} system"), f"{where} description"),
        machine=_text(machine, f"{where} machine") if machine is not None else None,
        layers=layers,
    )


def personal_paths(rec: Recipe) -> tuple[str, ...]:
    """Paths in the system that hold something personal, such as a keyfile,
    which an exported image leaves out unless asked."""
    return tuple(
        dst
        for layer in rec.layers
        if isinstance(layer, Copy) and layer.personal
        for _, dst in layer.files
    )


def media_refs(layer: Layer) -> tuple[MediaRef, ...]:
    """The media a layer reads."""
    match layer:
        case Unpack(source=source) | Copy(source=source):
            return (source,)
        case Amiga(disks=disks):
            return disks
    return ()


def describe(layer: Layer) -> str:
    """One line for the build log."""
    match layer:
        case Unpack(source=s, into=into):
            return f"unpack {_ref(s)} into {into or 'the root'}"
        case Copy(source=s, files=files):
            return f"copy {len(files)} path(s) from {_ref(s)}"
        case Dirs(paths=paths):
            return f"dirs   {len(paths)} drawer(s)"
        case File(path=path, append=append):
            return f"file   {path}{' (append)' if append else ''}"
        case Amiga(name=name, script=script):
            return f"amiga  {name} ({script})"
    raise TypeError(layer)


def fingerprints(layers: Sequence[Layer], inputs: Sequence[Iterable[str]]) -> list[str]:
    """One fingerprint per layer, each covering every layer before it.

    `inputs[i]` holds the content digests of what layer i reads (media, the
    script), so changing a file changes its layer and every later one.
    """
    previous, chain = f"amiga-env system format {FORMAT}", []
    for layer, digests in zip(layers, inputs, strict=True):
        spec = json.dumps(
            {"type": type(layer).__name__, **asdict(layer)}, sort_keys=True, default=list
        )
        h = hashlib.sha256(previous.encode())
        h.update(spec.encode())
        for digest in digests:
            h.update(digest.encode())
        previous = h.hexdigest()
        chain.append(previous)
    return chain


def plan(wanted: Sequence[str], built: Sequence[str], snapshots: Iterable[str]) -> Plan:
    """How to reach `wanted` from a tree that has `built` applied.

    A tree is only ever added to, so it can continue only when what it holds
    is a prefix of what is wanted. Otherwise the build restores the latest
    snapshot on the wanted chain (snapshots are taken after `amiga` layers,
    the slow ones), or starts from an empty tree.
    """
    wanted, built = list(wanted), list(built)
    if built == wanted:
        return Plan(len(wanted), up_to_date=True)
    if built and wanted[: len(built)] == built:
        return Plan(len(built))
    saved = set(snapshots)
    for count in range(len(wanted), 0, -1):
        if wanted[count - 1] in saved:
            return Plan(count, restore=count, fresh=True)
    return Plan(0, fresh=True)


def system_path(value: object, what: str, allow_root: bool = False) -> str:
    """A path inside the system tree, in Amiga spelling ("Libs/icon.library")."""
    if not isinstance(value, str):
        raise SystemExit(f"{what} must be a string")
    if value in ("", ".") and allow_root:
        return ""
    path = PurePosixPath(value)
    if not value or value.startswith("/") or ":" in value or ".." in path.parts:
        raise SystemExit(f"{what} must be a relative path with no ':' or '..': {value!r}")
    return path.as_posix()


def _layer(table: object, where: str) -> Layer:
    if not isinstance(table, dict):
        raise SystemExit(f"{where} must be a table")
    kind = table.get("type")
    builders = {"unpack": _unpack, "copy": _copy, "dirs": _dirs, "file": _file, "amiga": _amiga}
    if kind not in builders:
        raise SystemExit(f"{where}: type is one of {', '.join(builders)}, not {kind!r}")
    return builders[kind](table, f"{where} ({kind})")


def _unpack(table: dict, where: str) -> Unpack:
    _no_unknown_keys(table, {"type", "media", "member", "into", "exclude", "decompress"}, where)
    return Unpack(
        source=_media_ref(table, where),
        into=system_path(table.get("into", ""), f"{where} into", allow_root=True),
        exclude=_paths(table, "exclude", where),
        decompress=_flag(table, "decompress", where),
    )


def _copy(table: dict, where: str) -> Copy:
    allowed = {"type", "media", "member", "files", "exclude", "decompress", "personal"}
    _no_unknown_keys(table, allowed, where)
    files = table.get("files")
    if not isinstance(files, dict) or not files:
        raise SystemExit(f'{where}: files is a table of "path in media" = "path in system"')
    return Copy(
        source=_media_ref(table, where),
        files=tuple(
            (system_path(src, f"{where} files"), system_path(dst, f"{where} files"))
            for src, dst in files.items()
        ),
        exclude=_paths(table, "exclude", where),
        decompress=_flag(table, "decompress", where),
        personal=_flag(table, "personal", where),
    )


def _dirs(table: dict, where: str) -> Dirs:
    _no_unknown_keys(table, {"type", "paths"}, where)
    paths = _paths(table, "paths", where)
    if not paths:
        raise SystemExit(f"{where}: paths lists the drawers to make")
    return Dirs(paths=paths)


def _file(table: dict, where: str) -> File:
    _no_unknown_keys(table, {"type", "path", "text", "append"}, where)
    text = table.get("text")
    if not isinstance(text, str):
        raise SystemExit(f"{where}: text is the file's contents")
    if "\r" in text:
        raise SystemExit(f"{where}: text must use LF line endings")
    return File(
        path=system_path(table.get("path"), f"{where} path"),
        text=text,
        append=_flag(table, "append", where),
    )


def _paths(table: dict, key: str, where: str) -> tuple[str, ...]:
    value = table.get(key, [])
    if not isinstance(value, list):
        raise SystemExit(f"{where}: {key} is a list of paths")
    return tuple(system_path(v, f"{where} {key}") for v in value)


def _flag(table: dict, key: str, where: str) -> bool:
    value = table.get(key, False)
    if not isinstance(value, bool):
        raise SystemExit(f"{where}: {key} is true or false")
    return value


def _amiga(table: dict, where: str) -> Amiga:
    _no_unknown_keys(table, {"type", "name", "script", "disks", "timeout"}, where)
    name = table.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise SystemExit(f"{where}: name is lower case letters, digits, - and _")
    disks = table.get("disks", [])
    if not isinstance(disks, list):
        raise SystemExit(f"{where}: disks is a list of media paths")
    timeout = table.get("timeout", DEFAULT_TIMEOUT)
    if type(timeout) is not int or timeout <= 0:
        raise SystemExit(f"{where}: timeout is a whole number of seconds")
    return Amiga(
        name=name,
        script=system_path(table.get("script"), f"{where} script"),
        disks=tuple(MediaRef(_container(d, f"{where} disks")) for d in disks),
        timeout=timeout,
    )


def _media_ref(table: dict, where: str) -> MediaRef:
    member = table.get("member")
    return MediaRef(
        media=system_path(table.get("media"), f"{where} media"),
        member=_container(member, f"{where} member") if member is not None else None,
    )


def _container(value: object, what: str) -> str:
    path = system_path(value, what)
    if not path.lower().endswith(CONTAINER_SUFFIXES):
        raise SystemExit(f"{what} must be an ADF or an archive ({', '.join(CONTAINER_SUFFIXES)})")
    return path


def _ref(ref: MediaRef) -> str:
    return f"{ref.media}!{ref.member}" if ref.member else ref.media


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
