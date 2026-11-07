"""Copy licensed media into media/ once, and verify it against recorded checksums.

media/manifest.toml says what is needed and where it came from.
media/manifest.lock.json records what was copied: size and SHA-256 for each
file, and a tree digest for each directory. Both are checked in; the media is
not.

Each item is copied to a hidden `.partial` sibling and moved into place only
when complete, and the lock is rewritten after every item, so an interrupted
migration leaves no half-copied media and keeps what it finished. An item
already present and matching its lock is not copied again. A copy that does not
match its locked checksum is refused, so a different origin cannot silently
replace the media the lock describes.
"""

import hashlib
import json
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import MEDIA_DIR

MANIFEST = MEDIA_DIR / "manifest.toml"
LOCK = MEDIA_DIR / "manifest.lock.json"


@dataclass(frozen=True)
class Item:
    dest: str
    origin: str
    licence: str


def load_manifest(path: Path = MANIFEST) -> tuple[Path, list[Item]]:
    data = tomllib.loads(path.read_text())
    root = Path(data["origin_root"]).expanduser()
    items = [Item(i["dest"], i["origin"], i["licence"]) for i in data["item"]]
    for item in items:
        if Path(item.dest).is_absolute() or ".." in Path(item.dest).parts:
            raise SystemExit(f"manifest.toml dest must stay inside media/: {item.dest}")
    dests = [i.dest for i in items]
    if len(set(dests)) != len(dests):
        raise SystemExit("manifest.toml lists the same dest twice")
    return root, items


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_digest(path: Path) -> tuple[str, int]:
    """Digest of a directory: every relative path and file digest, sorted."""
    h = hashlib.sha256()
    count = 0
    for file in sorted(p for p in path.rglob("*") if p.is_file() and p.name != ".DS_Store"):
        rel = file.relative_to(path).as_posix()
        h.update(f"{rel}\0{file_digest(file)}\n".encode())
        count += 1
    return h.hexdigest(), count


def describe(path: Path) -> dict:
    if path.is_dir():
        digest, count = tree_digest(path)
        return {"kind": "tree", "sha256": digest, "files": count}
    return {"kind": "file", "sha256": file_digest(path), "size": path.stat().st_size}


def migrate(origin_root: Path | None = None, manifest: Path = MANIFEST) -> None:
    root, items = load_manifest(manifest)
    root = origin_root or root
    if not root.is_dir():
        raise SystemExit(f"Origin root not found: {root}")
    media_dir = manifest.parent
    lock_path = media_dir / LOCK.name
    previous = _read_lock(lock_path)
    lock = {item.dest: previous[item.dest] for item in items if item.dest in previous}
    for item in items:
        dest = media_dir / item.dest
        expected = lock.get(item.dest)
        if expected and dest.exists() and describe(dest)["sha256"] == expected["sha256"]:
            print(f"present {item.dest}")
            continue
        source = root / item.origin
        if not source.exists():
            raise SystemExit(f"Missing in origin: {item.origin}")
        partial = _copy_beside(source, dest)
        found = describe(partial)
        if expected and found["sha256"] != expected["sha256"]:
            _remove(partial)
            raise SystemExit(f"{item.origin} does not match the checksum locked for {item.dest}")
        if dest.is_dir():
            shutil.rmtree(dest)
        partial.replace(dest)
        lock[item.dest] = found | {"origin": item.origin, "licence": item.licence}
        _write_lock(lock_path, lock)
        print(f"copied  {item.dest}")
    _write_lock(lock_path, lock)
    print(f"Recorded {len(lock)} items in {lock_path.relative_to(media_dir.parent)}")


def verify(manifest: Path = MANIFEST) -> bool:
    _, items = load_manifest(manifest)
    media_dir = manifest.parent
    lock = _read_lock(media_dir / LOCK.name)
    ok = True
    for item in items:
        dest = media_dir / item.dest
        expected = lock.get(item.dest)
        if expected is None:
            print(f"UNLOCKED {item.dest} (run `make media`)")
            ok = False
        elif not dest.exists():
            print(f"MISSING  {item.dest}")
            ok = False
        elif describe(dest)["sha256"] != expected["sha256"]:
            print(f"CHANGED  {item.dest}")
            ok = False
    print("media verified" if ok else "media verification FAILED")
    return ok


def _copy_beside(source: Path, dest: Path) -> Path:
    """Copy source to a hidden sibling of dest and return its path."""
    partial = dest.with_name(f".{dest.name}.partial")
    _remove(partial)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, partial, ignore=shutil.ignore_patterns(".DS_Store"))
    else:
        shutil.copy2(source, partial)
    return partial


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _read_lock(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _write_lock(path: Path, lock: dict) -> None:
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(json.dumps(dict(sorted(lock.items())), indent=2) + "\n")
    partial.replace(path)
