"""Read the project's .env: where each media source lives on this machine.

Tracked files never hold a path on one person's disk. A source names an
environment variable; its value comes from the real environment or, failing
that, from .env at the project root, which git ignores. .env.example, which
git tracks, lists every variable.

The format is the common subset: `KEY=VALUE` lines, an optional `export `,
blank lines and `#` comment lines, values optionally in single or double
quotes. An unquoted value ends at ` #`. No variable substitution.
"""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

ENV_FILE = ".env"
EXAMPLE_FILE = ".env.example"
KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

EXAMPLE_HEADER = """\
# Where your own copies of the licensed Amiga media are, one variable per
# source in media/manifest.toml. Copy this file to .env and fill in the
# folders; .env is ignored by git. Real environment variables override .env.
# `~` at the start of a path means your home directory.
"""


def parse(text: str) -> dict[str, str]:
    values = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not KEY.fullmatch(key):
            raise SystemExit(f"{ENV_FILE} line {number} is not KEY=VALUE: {raw!r}")
        values[key] = _value(value.strip())
    return values


def load(path: Path) -> dict[str, str]:
    return parse(path.read_text()) if path.is_file() else {}


def merged(file_values: Mapping[str, str], environ: Mapping[str, str]) -> dict[str, str]:
    """Real environment variables override .env."""
    return {**file_values, **environ}


def folder(value: str | None) -> Path | None:
    """A variable's value as a folder path, or None when it is unset or empty."""
    return Path(value).expanduser() if value else None


def example_entry(env: str, description: str) -> str:
    return f"\n# {description}\n{env}=\n"


def render_example(entries: Iterable[tuple[str, str]]) -> str:
    return EXAMPLE_HEADER + "".join(example_entry(env, desc) for env, desc in entries)


def render_empty(names: Iterable[str]) -> str:
    return "".join(f"{name}=\n" for name in names)


def _value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    comment = value.find(" #")
    return value[:comment].rstrip() if comment >= 0 else value
