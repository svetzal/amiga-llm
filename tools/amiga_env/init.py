"""Make a directory an amiga-env project, without overwriting anything there.

`amiga-env init` writes amiga.toml (no machines yet), an empty media manifest
with the usual sources, .env.example and an empty .env, the hello example,
and a Makefile when there is none, and adds the ignore lines to .gitignore.
A file that exists is kept. `--force` rewrites only the files that are
init's own (amiga.toml, the hello example, .env.example); it never touches
the media manifest, .env, the Makefile or anything in media/.
"""

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from . import dotenv, media, project

TEMPLATES = resources.files("amiga_env") / "templates"
GITIGNORE_HEADER = "# amiga-env: licensed media, local paths and generated files stay out of git"


@dataclass(frozen=True)
class Scaffold:
    path: str  # relative to the project directory
    template: str | None  # file in templates/, or None when rendered
    force_replaces: bool


SCAFFOLD = (
    Scaffold(project.CONFIG, "amiga.toml", force_replaces=True),
    Scaffold(f"media/{media.MANIFEST_NAME}", "manifest.toml", force_replaces=False),
    Scaffold("examples/hello/hello.s", "hello.s", force_replaces=True),
    Scaffold("Makefile", "Makefile", force_replaces=False),
    Scaffold(dotenv.EXAMPLE_FILE, None, force_replaces=True),
    Scaffold(dotenv.ENV_FILE, None, force_replaces=False),
)


def template(name: str) -> str:
    return (TEMPLATES / name).read_text()


def action_for(path: Path, force_replaces: bool, force: bool) -> str:
    """What init does with one file: create it, keep it, or replace it."""
    if path.is_symlink() or not path.exists():
        return "kept" if path.is_symlink() else "created"
    return "replaced" if force and force_replaces else "kept"


def missing_ignore_lines(existing: str, wanted: str) -> list[str]:
    """Rules from `wanted` that `existing` lacks. Comments are not rules."""
    have = {line.strip() for line in existing.splitlines()}
    rules = [line.strip() for line in wanted.splitlines()]
    return [rule for rule in rules if rule and not rule.startswith("#") and rule not in have]


def with_ignore_lines(existing: str, missing: list[str]) -> str:
    """`existing` with the missing rules appended under one comment."""
    if not missing:
        return existing
    block = "\n".join([GITIGNORE_HEADER, *missing]) + "\n"
    return f"{existing.rstrip()}\n\n{block}"


def init(directory: Path, force: bool = False) -> list[tuple[str, str]]:
    """Scaffold `directory`. Returns (action, path) for each file, in order."""
    report = []
    for entry in SCAFFOLD:
        path = directory / entry.path
        action = action_for(path, entry.force_replaces, force)
        if action != "kept":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_content(entry, directory))
        report.append((action, entry.path))
    report.append(_update_gitignore(directory))
    for action, path in report:
        print(f"{action:<9} {path}")
    return report


def _content(entry: Scaffold, directory: Path) -> str:
    if entry.template is not None:
        return template(entry.template)
    sources = media.load_manifest(directory / "media" / media.MANIFEST_NAME).sources.values()
    if entry.path == dotenv.EXAMPLE_FILE:
        return dotenv.render_example((s.env, s.description) for s in sources)
    return dotenv.render_empty(s.env for s in sources)


def _update_gitignore(directory: Path) -> tuple[str, str]:
    path = directory / ".gitignore"
    existing = path.read_text() if path.exists() else ""
    wanted = template("gitignore")
    missing = missing_ignore_lines(existing, wanted)
    if not missing:
        return "kept", ".gitignore"
    if not existing.strip():
        path.write_text(wanted)
        return "created", ".gitignore"
    path.write_text(with_ignore_lines(existing, missing))
    return "updated", ".gitignore"
