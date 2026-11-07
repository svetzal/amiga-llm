"""Find the project amiga-env is working in, and the directories it uses.

A project is a directory holding `amiga.toml`. amiga-env looks for it in the
current directory and then in each parent, the way git finds `.git`. Setting
AMIGA_ENV_ROOT names the project directly. Nothing is looked up at import
time, so commands that need no project (`init`, `--help`) work anywhere.
"""

import os
from collections.abc import Mapping
from pathlib import Path

CONFIG = "amiga.toml"
ENV_VAR = "AMIGA_ENV_ROOT"


def find_root(start: Path, env: Mapping[str, str]) -> Path | None:
    """The project directory for `start`, or None when there is none."""
    named = env.get(ENV_VAR)
    if named:
        root = Path(named).expanduser().resolve()
        if not (root / CONFIG).is_file():
            raise SystemExit(f"{ENV_VAR} is {named}, which has no {CONFIG}")
        return root
    start = start.resolve()
    return next((d for d in (start, *start.parents) if (d / CONFIG).is_file()), None)


def current_root() -> Path | None:
    return find_root(Path.cwd(), os.environ)


def root() -> Path:
    found = current_root()
    if found is None:
        raise SystemExit(
            f"No {CONFIG} in {Path.cwd()} or any directory above it.\n"
            "Run `amiga-env init` to make this directory an amiga-env project,\n"
            f"or set {ENV_VAR} to a project directory."
        )
    return found


def config_path() -> Path:
    return root() / CONFIG


def media_dir() -> Path:
    return root() / "media"


def tools_dir() -> Path:
    return root() / ".tools"


def runs_dir() -> Path:
    return root() / "runs"


def build_dir() -> Path:
    return root() / "build"


def system_tree(name: str, root_dir: Path | None = None) -> Path:
    """Where `amiga-env system build NAME` builds the tree that boots as DH0:."""
    return (root_dir or root()) / "runs" / "systems" / name
