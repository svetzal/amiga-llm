"""amiga-env: set up and check the amiga-llm environment."""

import argparse
import subprocess
import sys
from pathlib import Path

from . import amiberry, home, media


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        # Everything after `run` belongs to Amiberry, including its own flags.
        return home.run(argv[1:])

    parser = argparse.ArgumentParser(prog="amiga-env", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("amiberry", help="install the latest (or a named) Amiberry release")
    fetch.add_argument("--tag", help="release tag, for example v8.5.0; default is latest")
    fetch.add_argument("--force", action="store_true", help="reinstall even if present")

    sub.add_parser("amiberry-path", help="print the path of the installed Amiberry binary")

    migrate = sub.add_parser("media", help="copy licensed media in from the origin collection")
    migrate.add_argument("--origin-root", type=Path, help="override origin_root in the manifest")

    sub.add_parser("media-verify", help="check media/ against manifest.lock.json")
    sub.add_parser("doctor", help="report what is installed and what is missing")

    # Listed for --help only; `run` is dispatched above, before argparse sees it.
    sub.add_parser("run", help="run Amiberry with the project's private home directory")

    args = parser.parse_args(argv)
    if args.command == "amiberry":
        amiberry.install(args.tag, args.force)
    elif args.command == "amiberry-path":
        print(amiberry.installed_binary())
    elif args.command == "media":
        media.migrate(args.origin_root)
    elif args.command == "media-verify":
        return 0 if media.verify() else 1
    elif args.command == "doctor":
        return _doctor()
    return 0


def _doctor() -> int:
    ok = True
    version = amiberry.installed_version()
    if version:
        print(f"amiberry  {version}{_latest_note(version)}")
        out = subprocess.run(
            [str(amiberry.installed_binary()), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        banner = (out.stdout or out.stderr).splitlines()
        print(f"          {banner[0] if banner else '(no --help output)'}")
        ok = _paths_stay_inside_project() and ok
    else:
        print("amiberry  not installed; run `make tools`")
        ok = False
    ok = media.verify() and ok
    return 0 if ok else 1


def _latest_note(version: str) -> str:
    try:
        latest = amiberry.fetch_release().version
    except OSError as error:  # offline, DNS, GitHub rate limit
        return f" (could not check for a newer release: {error})"
    return "" if latest == version else f" (latest is {latest}; run `make tools`)"


# Compiled-in fallbacks Amiberry reports but does not use when its bundled
# data directory exists.
BUILD_DEFAULTS = ("compiled_data_dir=",)


def paths_outside(dump: str, root: Path) -> list[str]:
    """Lines of `amiberry --dump-paths` whose absolute path is not under root."""
    return [
        line
        for line in dump.splitlines()
        if "=/" in line
        and not line.startswith(BUILD_DEFAULTS)
        and not Path(line.split("=", 1)[1]).is_relative_to(root)
    ]


def _paths_stay_inside_project() -> bool:
    """Every path Amiberry resolves must be inside the project (the app bundle is too)."""
    home.prepare()
    out = subprocess.run(
        [str(amiberry.installed_binary()), "--dump-paths"],
        env=home.environment(),
        check=False,
        capture_output=True,
        text=True,
    )
    outside = paths_outside(out.stdout, home.ROOT)
    if outside:
        print("paths     OUTSIDE the project:")
        for line in outside:
            print(f"          {line}")
        return False
    print("paths     all inside the project")
    return True


if __name__ == "__main__":
    sys.exit(main())
