"""Copy licensed media into media/ once, and verify it against recorded checksums.

media/manifest.toml says what is needed and where it comes from: named
sources (an Amiga Forever installation, an AmigaOS 3.2 CD, a personal
folder), and items, each a file or folder in one source. A source's location
is never written in a tracked file. It comes from the environment variable
the source names, usually set in the project's .env (see dotenv.py).
media/manifest.lock.json records what was copied: size and SHA-256 for each
file, and a tree digest for each directory. Both are checked in; the media is
not.

Each item is copied to a hidden `.partial` sibling and moved into place only
when complete, and the lock is rewritten after every item, so an interrupted
migration leaves no half-copied media and keeps what it finished. An item
already present and matching its lock is not copied again, so its source need
not be set. A copy that does not match its locked checksum is refused, so a
different origin cannot silently replace the media the lock describes.

Freely licensed material from the internet is a [[download]]: a pinned URL,
its size and SHA-256, and its licence. `migrate` fetches it into a fresh
directory, checks it, unpacks it when it is an archive (see fetch.py), and
locks what landed in media/ beside the URL and the download's checksum.
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from . import dotenv, fetch, project

MANIFEST_NAME = "manifest.toml"
LOCK_NAME = "manifest.lock.json"
SOURCE_NAME = re.compile(r"[a-z0-9_]+")
ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
SOURCE_KEYS = {"env", "description"}
ITEM_REQUIRED = {"dest", "source", "origin", "licence"}
ITEM_KEYS = ITEM_REQUIRED | {"optional"}
DOWNLOAD_REQUIRED = {"dest", "url", "sha256", "size", "licence"}
DOWNLOAD_KEYS = DOWNLOAD_REQUIRED | {"unpack", "optional"}
SHA256 = re.compile(r"[0-9a-f]{64}")
DIGEST_KEYS = ("kind", "sha256", "size", "files")


@dataclass(frozen=True)
class Source:
    name: str
    env: str
    description: str


@dataclass(frozen=True)
class Item:
    dest: str
    source: str
    origin: str
    licence: str
    optional: bool = False


@dataclass(frozen=True)
class Download:
    dest: str
    url: str
    sha256: str
    size: int
    licence: str
    unpack: str | None = None
    optional: bool = False


@dataclass(frozen=True)
class Manifest:
    sources: dict[str, Source]
    items: list[Item]
    downloads: tuple[Download, ...] = ()

    @property
    def entries(self) -> list[Item | Download]:
        """Everything with a dest in media/: copied items, then downloads."""
        return [*self.items, *self.downloads]


def manifest_path() -> Path:
    return project.media_dir() / MANIFEST_NAME


def parse_manifest(text: str) -> Manifest:
    """The sources and items in manifest.toml text, checked."""
    data = tomllib.loads(text)
    if "origin_root" in data:
        raise SystemExit(
            "manifest.toml: origin_root is no longer used; name [sources] and give each "
            "[[item]] a source (see the comment at the top of a fresh `amiga-env init` manifest)"
        )
    _no_unknown_keys(data, {"sources", "item", "download"}, "manifest.toml")
    sources = {name: _source(name, table) for name, table in data.get("sources", {}).items()}
    envs = [s.env for s in sources.values()]
    if len(set(envs)) != len(envs):
        raise SystemExit("manifest.toml: two sources use the same environment variable")
    items = [_item(table, sources) for table in data.get("item", [])]
    downloads = [_download(table) for table in data.get("download", [])]
    dests = [e.dest for e in [*items, *downloads]]
    if len(set(dests)) != len(dests):
        raise SystemExit("manifest.toml lists the same dest twice")
    return Manifest(sources, items, tuple(downloads))


def load_manifest(path: Path | None = None) -> Manifest:
    path = path or manifest_path()
    if not path.is_file():
        raise SystemExit(f"No {path}; run `amiga-env init`")
    return parse_manifest(path.read_text())


def check_dest(dest: str) -> str:
    """A dest names a path inside media/ that is not the manifest or its lock."""
    path = Path(dest)
    if not dest or path.is_absolute() or ".." in path.parts or path.parts[:1] == (".",):
        raise SystemExit(f"manifest.toml dest must stay inside media/: {dest!r}")
    if path.parts[0] in (MANIFEST_NAME, LOCK_NAME):
        raise SystemExit(f"dest {dest!r} would replace media/{path.parts[0]}")
    return path.as_posix()


def source_folders(manifest: Manifest, values: Mapping[str, str]) -> dict[str, Path | None]:
    """Each source's folder from the variable it names; None when the variable is unset."""
    return {name: dotenv.folder(values.get(s.env)) for name, s in manifest.sources.items()}


def project_values(root: Path, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Variables from root/.env, overridden by the real environment."""
    environ = os.environ if environ is None else environ
    return dotenv.merged(dotenv.load(root / dotenv.ENV_FILE), environ)


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


def lock_entry(digest: dict, item: Item | Download) -> dict:
    """What the lock records for an entry: its checksum, and where it came from."""
    entry = {k: digest[k] for k in DIGEST_KEYS if k in digest}
    if isinstance(item, Download):
        entry |= {"url": item.url, "download_sha256": item.sha256, "licence": item.licence}
    else:
        entry |= {"source": item.source, "origin": item.origin, "licence": item.licence}
    return entry | ({"optional": True} if item.optional else {})


def migrate(
    overrides: Mapping[str, Path] | None = None,
    manifest: Path | None = None,
    environ: Mapping[str, str] | None = None,
    get: fetch.Getter = fetch.http_get,
) -> None:
    """Copy every item and fetch every download not already present.

    `overrides` maps source names to folders; `get` fetches a URL into a file.
    """
    manifest = manifest or manifest_path()
    loaded = load_manifest(manifest)
    media_dir = manifest.parent
    folders = source_folders(loaded, project_values(media_dir.parent, environ))
    folders |= dict(overrides or {})
    lock_path = media_dir / LOCK_NAME
    previous = _read_lock(lock_path)
    lock = {e.dest: previous[e.dest] for e in loaded.entries if e.dest in previous}
    present = {
        e.dest for e in loaded.entries if _matches_lock(media_dir / e.dest, lock.get(e.dest))
    }
    pending = [i for i in loaded.items if i.dest not in present]
    _require_sources(loaded, pending, folders)
    for item in loaded.items:
        if item.dest in present:
            lock[item.dest] = lock_entry(lock[item.dest], item)
            print(f"present {item.dest}")
            continue
        found = _copy_item(item, loaded.sources[item.source], folders, media_dir, lock)
        if found is not None:
            lock[item.dest] = lock_entry(found, item)
            _write_lock(lock_path, lock)
            print(f"copied  {item.dest}")
    for download in loaded.downloads:
        if download.dest in present:
            lock[download.dest] = lock_entry(lock[download.dest], download)
            print(f"present {download.dest}")
            continue
        found = _fetch_download(download, media_dir, lock, get)
        if found is not None:
            lock[download.dest] = lock_entry(found, download)
            _write_lock(lock_path, lock)
            print(f"fetched {download.dest}")
    _write_lock(lock_path, lock)
    print(f"Recorded {len(lock)} items in {lock_path.relative_to(media_dir.parent)}")


def verify(manifest: Path | None = None) -> bool:
    manifest = manifest or manifest_path()
    loaded = load_manifest(manifest)
    media_dir = manifest.parent
    lock = _read_lock(media_dir / LOCK_NAME)
    ok = True
    for item in loaded.entries:
        dest = media_dir / item.dest
        expected = lock.get(item.dest)
        if not dest.exists() and item.optional:
            print(f"optional {item.dest} not copied")
        elif expected is None:
            print(f"UNLOCKED {item.dest} (run `amiga-env media`)")
            ok = False
        elif not dest.exists():
            print(f"MISSING  {item.dest}")
            ok = False
        elif describe(dest)["sha256"] != expected.get("sha256"):
            print(f"CHANGED  {item.dest}")
            ok = False
    print("media verified" if ok else "media verification FAILED")
    return ok


def add(
    source: str,
    origin: str,
    dest: str,
    licence: str,
    optional: bool = False,
    manifest: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Item:
    """Append one item to the manifest. The media is copied by `migrate`."""
    manifest = manifest or manifest_path()
    loaded = load_manifest(manifest)
    if source not in loaded.sources:
        known = ", ".join(loaded.sources) or "none yet; add one with `amiga-env media source`"
        raise SystemExit(f"No source named {source} in manifest.toml (sources: {known})")
    env = loaded.sources[source].env
    folder = source_folders(loaded, project_values(manifest.parent.parent, environ))[source]
    if folder is None or not folder.is_dir():
        raise SystemExit(f"{env} must name the {source} folder to add from it; set it in .env")
    relative = relative_origin(origin, folder)
    if not (folder / relative).exists():
        raise SystemExit(f"Not found in {source} ({env}): {relative}")
    if not licence.strip():
        raise SystemExit("--licence must say what entitles this copy")
    dest = check_new_dest(dest, [e.dest for e in loaded.entries])
    item = Item(dest, source, relative, licence, optional)
    _write_text(manifest, with_item(manifest.read_text(), item))
    print(f"added   {item.dest} <- {source}:{relative}; run `amiga-env media` to copy it in")
    return item


def add_source(name: str, env: str, description: str, manifest: Path | None = None) -> Source:
    """Add a named source to the manifest, and its variable to .env.example."""
    manifest = manifest or manifest_path()
    loaded = load_manifest(manifest)
    source = _source(name, {"env": env, "description": description})
    if name in loaded.sources:
        raise SystemExit(f"manifest.toml already has a source named {name}")
    if env in {s.env for s in loaded.sources.values()}:
        raise SystemExit(f"another source already uses {env}")
    _write_text(manifest, with_source(manifest.read_text(), source))
    example = manifest.parent.parent / dotenv.EXAMPLE_FILE
    _document_variable(example, source, loaded)
    print(f"added   source {name}; set {env} in .env to the folder")
    return source


def relative_origin(origin: str, folder: Path) -> str:
    """An origin as a path under its source folder. An absolute one must already be under it."""
    path = Path(origin).expanduser()
    if path.is_absolute():
        for base, full in ((folder, path), (folder.resolve(), path.resolve())):
            if full.is_relative_to(base) and full != base:
                path = full.relative_to(base)
                break
        else:
            raise SystemExit(f"{origin} is not inside {folder}")
    relative = Path(os.path.normpath(path))
    if relative.parts[:1] in (("..",), (".",)):
        raise SystemExit(f"{origin} is not inside {folder}")
    return relative.as_posix()


def check_new_dest(dest: str, existing: list[str]) -> str:
    """A dest for a new item: inside media/, not taken, not inside or around another."""
    dest = check_dest(dest)
    for other in existing:
        if dest == other:
            raise SystemExit(f"media/{dest} is already in the manifest")
        if dest.startswith(f"{other}/") or other.startswith(f"{dest}/"):
            raise SystemExit(f"media/{dest} overlaps media/{other}, already in the manifest")
    return dest


def with_item(text: str, item: Item) -> str:
    """The manifest text with one [[item]] appended. Comments are kept as written."""
    block = (
        "[[item]]\n"
        f"dest = {_toml_string(item.dest)}\n"
        f"source = {_toml_string(item.source)}\n"
        f"origin = {_toml_string(item.origin)}\n"
        f"licence = {_toml_string(item.licence)}\n"
    ) + ("optional = true\n" if item.optional else "")
    updated = f"{text.rstrip()}\n\n{block}" if text.strip() else block
    if parse_manifest(updated).items[-1] != item:
        raise SystemExit("could not append the item to manifest.toml")
    return updated


def with_source(text: str, source: Source) -> str:
    """The manifest text with a [sources.NAME] table after the last one. Comments are kept."""
    block = (
        f"[sources.{source.name}]\n"
        f"env = {_toml_string(source.env)}\n"
        f"description = {_toml_string(source.description)}\n"
    )
    headers = list(re.finditer(r"^\[sources\.[^\]]+\][ \t]*$", text, re.MULTILINE))
    if headers:
        end = re.compile(r"^(?:[ \t]*$|\[)", re.MULTILINE).search(text, headers[-1].end() + 1)
        pos = end.start() if end else len(text)
        head = text[:pos] if text[:pos].endswith("\n") else text[:pos] + "\n"
        updated = f"{head}\n{block}{text[pos:]}"
    else:
        first = re.search(r"^\[", text, re.MULTILINE)
        if first is None:
            updated = f"{text.rstrip()}\n\n{block}" if text.strip() else block
        else:
            start = text.rfind("\n\n", 0, first.start())
            pos = start + 2 if start >= 0 else 0
            updated = f"{text[:pos]}{block}\n{text[pos:]}"
    if parse_manifest(updated).sources.get(source.name) != source:
        raise SystemExit("could not add the source to manifest.toml")
    return updated


def _source(name: str, table: object) -> Source:
    where = f"manifest.toml [sources.{name}]"
    if not SOURCE_NAME.fullmatch(name):
        raise SystemExit(f"{where}: a source name is lower case letters, digits and _")
    if not isinstance(table, dict):
        raise SystemExit(f"{where} must be a table")
    _no_unknown_keys(table, SOURCE_KEYS, where)
    env, description = table.get("env"), table.get("description")
    if not isinstance(env, str) or not ENV_NAME.fullmatch(env):
        raise SystemExit(f"{where}: env must be a variable name like AMIGA_FOREVER_DIR")
    if not isinstance(description, str) or not description.strip():
        raise SystemExit(f"{where}: description must say what folder the variable names")
    return Source(name, env, description)


def _item(table: object, sources: dict[str, Source]) -> Item:
    if not isinstance(table, dict):
        raise SystemExit("manifest.toml: each [[item]] must be a table")
    where = f"manifest.toml [[item]] {table.get('dest', '(no dest)')}"
    _no_unknown_keys(table, ITEM_KEYS, where)
    missing = sorted(ITEM_REQUIRED - table.keys())
    if missing:
        raise SystemExit(f"{where} has no {', '.join(missing)}")
    if table["source"] not in sources:
        raise SystemExit(f"{where}: no source named {table['source']} in [sources]")
    origin = Path(table["origin"])
    if origin.is_absolute() or os.path.normpath(origin).startswith(".."):
        raise SystemExit(f"{where}: origin must be relative to its source folder")
    if not isinstance(table.get("optional", False), bool):
        raise SystemExit(f"{where}: optional is true or false")
    return Item(
        dest=check_dest(table["dest"]),
        source=table["source"],
        origin=origin.as_posix(),
        licence=table["licence"],
        optional=table.get("optional", False),
    )


def _download(table: object) -> Download:
    if not isinstance(table, dict):
        raise SystemExit("manifest.toml: each [[download]] must be a table")
    where = f"manifest.toml [[download]] {table.get('dest', '(no dest)')}"
    _no_unknown_keys(table, DOWNLOAD_KEYS, where)
    missing = sorted(DOWNLOAD_REQUIRED - table.keys())
    if missing:
        raise SystemExit(f"{where} has no {', '.join(missing)}")
    url, sha256, size = table["url"], table["sha256"], table["size"]
    if not isinstance(url, str) or not url.startswith("https://"):
        raise SystemExit(f"{where}: url must be an https:// address")
    if not isinstance(sha256, str) or not SHA256.fullmatch(sha256):
        raise SystemExit(f"{where}: sha256 must be 64 lower-case hex digits")
    if type(size) is not int or size <= 0:
        raise SystemExit(f"{where}: size is the download's length in bytes")
    unpack = table.get("unpack")
    if unpack is not None and unpack not in fetch.UNPACK_FORMATS:
        raise SystemExit(f"{where}: unpack is one of {', '.join(fetch.UNPACK_FORMATS)}")
    if not isinstance(table.get("optional", False), bool):
        raise SystemExit(f"{where}: optional is true or false")
    if not isinstance(table["licence"], str) or not table["licence"].strip():
        raise SystemExit(f"{where}: licence must name the licence the material is under")
    return Download(
        dest=check_dest(table["dest"]),
        url=url,
        sha256=sha256,
        size=size,
        licence=table["licence"],
        unpack=unpack,
        optional=table.get("optional", False),
    )


def _fetch_download(
    download: Download, media_dir: Path, lock: dict, get: fetch.Getter
) -> dict | None:
    """Fetch one download into media/ and return its description; None when an optional
    download could not be fetched."""
    dest = media_dir / download.dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{dest.name}.download-", dir=dest.parent))
    try:
        try:
            fetched = fetch.fetch(
                download.url, download.sha256, download.size, work, download.unpack, get
            )
        except OSError as error:
            if not download.optional:
                raise SystemExit(f"could not fetch {download.url}: {error}") from error
            print(f"skipped {download.dest} (optional; could not fetch it: {error})")
            return None
        found = describe(fetched)
        expected = lock.get(download.dest)
        if expected and found["sha256"] != expected.get("sha256"):
            raise SystemExit(
                f"{download.url} unpacked to something other than the lock records for "
                f"{download.dest}. Nothing was installed."
            )
        _remove(dest)
        fetched.replace(dest)
        return found
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _no_unknown_keys(table: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(table.keys() - allowed)
    if unknown:
        raise SystemExit(
            f"{where}: unknown key {', '.join(unknown)} (allowed: {', '.join(sorted(allowed))})"
        )


def _matches_lock(dest: Path, expected: dict | None) -> bool:
    return bool(expected) and dest.exists() and describe(dest)["sha256"] == expected.get("sha256")


def _require_sources(
    manifest: Manifest, pending: list[Item], folders: Mapping[str, Path | None]
) -> None:
    """Refuse to start when a required item still to copy has no usable source."""
    problems = {}
    for item in pending:
        source = manifest.sources[item.source]
        folder = folders.get(item.source)
        if item.optional or (folder is not None and folder.is_dir()):
            continue
        problems[source.name] = (
            f"{source.env} is not set"
            if folder is None
            else f"{source.env} is {folder}, which is not a folder"
        )
    if problems:
        lines = "".join(f"\n  {name}: {why}" for name, why in problems.items())
        raise SystemExit(
            f"Media still to copy needs these sources:{lines}\n"
            "Set each variable in .env (.env.example lists them) or in the environment."
        )


def _copy_item(
    item: Item,
    source: Source,
    folders: Mapping[str, Path | None],
    media_dir: Path,
    lock: dict,
) -> dict | None:
    """Copy one item into media/ and return its description; None when an optional item is
    skipped."""
    folder = folders.get(item.source)
    if folder is None or not folder.is_dir():
        print(f"skipped {item.dest} (optional; {source.env} is not set to a folder)")
        return None
    origin = folder / item.origin
    if not origin.exists():
        if item.optional:
            print(f"skipped {item.dest} (optional; not found in {item.source})")
            return None
        raise SystemExit(f"Missing in origin: {item.origin} (source {item.source}, {source.env})")
    dest = media_dir / item.dest
    partial = _copy_beside(origin, dest)
    found = describe(partial)
    expected = lock.get(item.dest)
    if expected and found["sha256"] != expected.get("sha256"):
        _remove(partial)
        raise SystemExit(
            f"{item.origin} in source {item.source} ({source.env}) does not match the checksum "
            f"locked for {item.dest}.\nA different edition or dump of the same file is the "
            "likely cause. Nothing was copied."
        )
    if dest.is_dir():
        shutil.rmtree(dest)
    partial.replace(dest)
    return found


def _document_variable(example: Path, source: Source, before: Manifest) -> None:
    if not example.exists():
        entries = [(s.env, s.description) for s in [*before.sources.values(), source]]
        example.write_text(dotenv.render_example(entries))
    elif not re.search(rf"^{source.env}=", example.read_text(), re.MULTILINE):
        with example.open("a") as f:
            f.write(dotenv.example_entry(source.env, source.description))


def _toml_string(value: str) -> str:
    # A JSON string is a valid TOML basic string.
    return json.dumps(value, ensure_ascii=False)


def _write_text(path: Path, text: str) -> None:
    partial = path.with_name(f".{path.name}.partial")
    partial.write_text(text)
    partial.replace(path)


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
