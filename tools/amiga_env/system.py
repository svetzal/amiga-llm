"""Build a system recipe (see recipe.py) into runs/systems/NAME/.

The tree is the directory a machine with `system = "NAME"` boots as DH0:.
Beside it, runs/systems/NAME.build/ keeps what the build knows:

    state.json      the fingerprint of every layer applied to the tree
    snapshots/FP/   a copy of the tree after each `amiga` layer
    exchange/       the AmigaEnv: folder of the last `amiga` layer run
    tree.txt        SHA-256, size and path of every file, for comparing builds

A rebuild applies only what changed: an unchanged recipe does nothing, new
layers at the end are added to the tree, and any other change starts again
from the latest snapshot still on the recipe's chain, or from nothing. Disks
and archives are opened once into runs/systems/.cache/, keyed by checksum.
"""

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from amitools.tools import xdftool

from . import media, profile, project, recipe, session
from .recipe import Amiga, Copy, File, Layer, MediaRef, Recipe, Unpack

SYSTEMS = "systems"
FSDB = "_UAEFSDB.___"  # Amiberry's per-folder record of Amiga file attributes
IGNORED = {FSDB, ".DS_Store"}


def recipes_dir() -> Path:
    return project.root() / SYSTEMS


def recipe_path(name: str) -> Path:
    return recipes_dir() / f"{name}.toml"


def load(name: str) -> Recipe:
    path = recipe_path(name)
    if not path.is_file():
        known = ", ".join(names()) or "none"
        raise SystemExit(f"no system recipe {path} (recipes: {known})")
    return recipe.parse(name, path.read_text())


def names() -> list[str]:
    folder = recipes_dir()
    return sorted(p.stem for p in folder.glob("*.toml")) if folder.is_dir() else []


def tree_dir(name: str) -> Path:
    return project.system_tree(name)


def build_dir(name: str) -> Path:
    return project.runs_dir() / "systems" / f"{name}.build"


def cache_dir() -> Path:
    return project.runs_dir() / "systems" / ".cache"


def built_layers(name: str) -> list[str]:
    state = build_dir(name) / "state.json"
    return json.loads(state.read_text())["layers"] if state.is_file() else []


def list_systems() -> None:
    found = names()
    if not found:
        print(f"no recipes in {recipes_dir()}")
    for name in found:
        wanted = fingerprints(load(name))
        built = built_layers(name)
        state = "built" if built == wanted else ("partly built" if built else "not built")
        print(f"{name:<14} {state:<13} {load(name).description}")


def fingerprints(rec: Recipe) -> list[str]:
    return recipe.fingerprints(rec.layers, [_input_digests(layer) for layer in rec.layers])


def build(name: str, force: bool = False) -> Path:
    rec = load(name)
    tree, state = tree_dir(name), build_dir(name)
    wanted = fingerprints(rec)
    snapshots = state / "snapshots"
    known = [p.name for p in snapshots.iterdir()] if snapshots.is_dir() else []
    step = recipe.plan(wanted, [] if force else built_layers(name), [] if force else known)
    if step.up_to_date:
        print(f"{name} is up to date ({tree})")
        return tree
    if step.fresh:
        shutil.rmtree(tree, ignore_errors=True)
        tree.mkdir(parents=True)
        _save_state(state, [])
    if step.restore is not None:
        print(f"restore  the tree after layer {step.restore} from its snapshot")
        _replace_tree(snapshots / wanted[step.restore - 1], tree)
        _save_state(state, wanted[: step.restore])
    for index in range(step.start, len(rec.layers)):
        layer = rec.layers[index]
        began = time.monotonic()
        print(f"layer {index + 1:>2} {recipe.describe(layer)}", flush=True)
        _apply(layer, rec, tree, state)
        if isinstance(layer, Amiga):
            _replace_tree(tree, snapshots / wanted[index])
        _save_state(state, wanted[: index + 1])
        print(f"         {time.monotonic() - began:.1f} s", flush=True)
    _ensure_hook(tree)
    _drop_stale_snapshots(snapshots, set(wanted))
    count = write_tree_listing(tree, state / "tree.txt")
    print(f"built    {name}: {count} files in {tree}; listing in {state / 'tree.txt'}")
    return tree


def tree_listing(tree: Path) -> list[str]:
    """`sha256  size  path` for every file, sorted; Amiberry's records left out."""
    lines = []
    for path in sorted(tree.rglob("*")):
        if path.is_file() and path.name not in IGNORED:
            rel = path.relative_to(tree).as_posix()
            lines.append(f"{media.file_digest(path)}  {path.stat().st_size:>8}  {rel}")
    return lines


def write_tree_listing(tree: Path, out: Path) -> int:
    lines = tree_listing(tree)
    out.write_text("".join(f"{line}\n" for line in lines))
    return len(lines)


# ---- layers ----------------------------------------------------------------


def _apply(layer: Layer, rec: Recipe, tree: Path, state: Path) -> None:
    match layer:
        case Unpack(source=source, into=into, exclude=exclude):
            opened, _ = open_ref(source)
            dest = _resolve(tree, into, create=True)
            dest.mkdir(parents=True, exist_ok=True)
            merge(opened, dest, {e.lower() for e in exclude})
        case Copy(source=source, files=files):
            opened, _ = open_ref(source)
            for src, dst in files:
                _copy_path(_existing(opened, src, source.media), tree, dst)
        case File(path=path, text=text):
            target = _resolve(tree, path, create=True)
            target.write_text(text)
        case Amiga():
            _run_amiga(layer, rec, tree, state)


def _run_amiga(layer: Amiga, rec: Recipe, tree: Path, state: Path) -> None:
    _ensure_hook(tree)
    machines = profile.load_machines()
    if rec.machine not in machines:
        raise SystemExit(f"systems/{rec.name}.toml: no machine {rec.machine} in amiga.toml")
    volumes = [session.Volume(profile.SYSTEM_DEVICE, profile.SYSTEM_VOLUME, tree.resolve(), 0)]
    for index, disk in enumerate(layer.disks):
        opened, label = open_ref(disk)
        if label is None:
            raise SystemExit(f"{disk.media} is not a disk, so it has no volume name to mount")
        volumes.append(session.Volume(f"BLD{index}", label, opened.resolve()))
    args = profile.base_args(machines[rec.machine]) + session.volume_args(volumes)
    script = (project.root() / layer.script).read_text()
    exchange = state / "exchange" / layer.name
    outcome = session.run_script(args, exchange, script, layer.timeout)
    print(f"         script ended with return code {outcome.return_code}")
    if outcome.return_code != 0:
        raise SystemExit(f"{layer.name} failed; see {exchange / 'script.log'}")


def _ensure_hook(tree: Path) -> None:
    startup = _resolve(tree, session.USER_STARTUP, create=True)
    existing = startup.read_text() if startup.exists() else ""
    wanted = session.with_hook(existing)
    if wanted != existing:
        startup.write_text(wanted)


# ---- opening media -----------------------------------------------------------


def open_ref(ref: MediaRef) -> tuple[Path, str | None]:
    """The opened contents of a media reference, and its volume name if a disk."""
    path = project.media_dir() / ref.media
    if not path.is_file():
        raise SystemExit(f"media/{ref.media} is missing; run `amiga-env media`")
    opened, label = open_file(path)
    if ref.member is None:
        return opened, label
    return open_file(_existing(opened, ref.member, ref.media))


def open_file(path: Path) -> tuple[Path, str | None]:
    """Unpack an ADF or extract an archive once, into the cache, by checksum.

    An archive whose only content is one ADF opens as that disk.
    """
    slot = cache_dir() / media.file_digest(path)
    tree = slot / "tree"
    if not tree.is_dir():
        shutil.rmtree(slot, ignore_errors=True)
        slot.parent.mkdir(parents=True, exist_ok=True)
        partial = Path(tempfile.mkdtemp(prefix=".open-", dir=slot.parent))
        try:
            label = None
            if _is_adf(path):
                label = _unpack_adf(path, partial)
            elif path.name.lower().endswith(recipe.ARCHIVE_SUFFIXES):
                _extract(path, partial)
            else:
                (partial / "tree").mkdir()
                shutil.copyfile(path, partial / "tree" / path.name)
            (partial / "label").write_text(label or "")
            partial.rename(slot)
        except BaseException:
            shutil.rmtree(partial, ignore_errors=True)
            raise
    label = (slot / "label").read_text() or None
    inner = [p for p in tree.iterdir() if p.name not in IGNORED]
    if label is None and len(inner) == 1 and _is_adf(inner[0]):
        return open_file(inner[0])
    return tree, label


def _is_adf(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".adf"


def _unpack_adf(adf: Path, slot: Path) -> str:
    out = slot / "unpacked"
    out.mkdir()
    if xdftool.main([str(adf), "unpack", str(out)]) != 0:
        raise SystemExit(f"xdftool could not unpack {adf}")
    disks = [p for p in out.iterdir() if p.is_dir()]
    if len(disks) != 1:
        raise SystemExit(f"xdftool unpacked {len(disks)} volumes from {adf}")
    disks[0].rename(slot / "tree")
    shutil.rmtree(out)
    return disks[0].name


def _extract(archive: Path, slot: Path) -> None:
    """Extract with bsdtar, and check every listed file arrived.

    bsdtar reports errors on some Amiga LhA archives yet extracts every
    member, so its exit status alone is not the test.
    """
    tree = slot / "tree"
    tree.mkdir()
    try:
        listing = subprocess.run(
            ["bsdtar", "-tf", str(archive)], capture_output=True, text=True, check=False
        )
        result = subprocess.run(
            ["bsdtar", "-xf", str(archive), "-C", str(tree)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as error:
        raise SystemExit("bsdtar is needed to open archives (libarchive-tools on Linux)") from error
    missing = missing_members(listing.stdout.splitlines(), tree)
    if missing or not listing.stdout.strip():
        raise SystemExit(
            f"bsdtar did not extract {len(missing)} member(s) of {archive.name}, "
            f"for example {missing[:3]}: {result.stderr.strip()}"
        )


def missing_members(listed: list[str], tree: Path) -> list[str]:
    """Listed archive members (directories end in /) not present under tree."""
    return [m for m in listed if m and not m.endswith("/") and not (tree / m).exists()]


# ---- copying into the tree -----------------------------------------------------


def merge(source: Path, dest: Path, exclude: set[str], prefix: str = "") -> None:
    """Copy a folder's contents into dest, matching names as AmigaDOS does
    (ignoring case), so `LIBS` from one disk lands in `Libs` from another."""
    for entry in sorted(source.iterdir()):
        rel = f"{prefix}{entry.name}"
        if entry.name in IGNORED or rel.lower() in exclude:
            continue
        target = _child(dest, entry.name)
        if entry.is_dir():
            target.mkdir(exist_ok=True)
            merge(entry, target, exclude, f"{rel}/")
        else:
            shutil.copyfile(entry, target)


def _copy_path(source: Path, tree: Path, dst: str) -> None:
    target = _resolve(tree, dst, create=True)
    if source.is_dir():
        target.mkdir(exist_ok=True)
        merge(source, target, set())
    else:
        shutil.copyfile(source, target)


def _resolve(tree: Path, rel: str, create: bool = False) -> Path:
    """tree/rel, using existing folders whose names differ only in case."""
    path = tree
    parts = [p for p in rel.split("/") if p]
    for index, part in enumerate(parts):
        path = _child(path, part)
        if create and index < len(parts) - 1:
            path.mkdir(exist_ok=True)
    return path


def _child(folder: Path, name: str) -> Path:
    if folder.is_dir():
        for entry in folder.iterdir():
            if entry.name.lower() == name.lower():
                return entry
    return folder / name


def _existing(tree: Path, rel: str, what: str) -> Path:
    path = _resolve(tree, rel)
    if not path.exists():
        raise SystemExit(f"{what} has no {rel}")
    return path


# ---- state -----------------------------------------------------------------------


def _input_digests(layer: Layer) -> list[str]:
    digests = [_media_digest(ref.media) for ref in recipe.media_refs(layer)]
    if isinstance(layer, Amiga):
        script = project.root() / layer.script
        if not script.is_file():
            raise SystemExit(f"amiga layer {layer.name}: no script {layer.script}")
        digests.append(media.file_digest(script))
    return digests


def _media_digest(rel: str) -> str:
    lock = media.manifest_path().with_name(media.LOCK_NAME)
    entry = json.loads(lock.read_text()).get(rel) if lock.is_file() else None
    if entry:
        return entry["sha256"]
    path = project.media_dir() / rel
    if not path.is_file():
        raise SystemExit(f"media/{rel} is not in the media lock; add it with `amiga-env media add`")
    return media.file_digest(path)


def _save_state(state: Path, layers: list[str]) -> None:
    state.mkdir(parents=True, exist_ok=True)
    (state / "state.json").write_text(json.dumps({"layers": layers}, indent=2) + "\n")


def _replace_tree(source: Path, dest: Path) -> None:
    shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest, symlinks=True)


def _drop_stale_snapshots(snapshots: Path, wanted: set[str]) -> None:
    if snapshots.is_dir():
        for snap in snapshots.iterdir():
            if snap.name not in wanted:
                shutil.rmtree(snap)
