"""amiga-env: set up, check and run an Amiga development environment in this project."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import (
    adf,
    amiberry,
    assemble,
    export,
    guard,
    home,
    init,
    media,
    profile,
    project,
    session,
    system,
    toolchain,
)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        # Everything after `run` belongs to Amiberry, including its own flags.
        return home.run(argv[1:])
    parser, sub = build_parser()
    machines = _machines(set(sub.choices))
    if argv[:1] and argv[0] in machines:
        _ready(machines[argv[0]])
        return home.run(boot_command(machines[argv[0]], argv[1:]))
    for name, machine in machines.items():
        # Listed for --help only; machines are dispatched above, like `run`.
        sub.add_parser(name, help=f"{machine.purpose}; or boot DISK.adf; more args go to Amiberry")
    return dispatch(parser.parse_args(argv))


def build_parser() -> tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    parser = argparse.ArgumentParser(prog="amiga-env", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    scaffold = sub.add_parser("init", help="make this directory an amiga-env project")
    scaffold.add_argument(
        "--force",
        action="store_true",
        help="rewrite amiga.toml, .env.example and the hello example; never media or .env",
    )

    fetch = sub.add_parser("amiberry", help="install the latest (or a named) Amiberry release")
    fetch.add_argument("--tag", help="release tag, for example v8.5.0; default is latest")
    fetch.add_argument("--force", action="store_true", help="reinstall even if present")

    sub.add_parser("amiberry-path", help="print the path of the installed Amiberry binary")

    migrate = sub.add_parser("media", help="copy licensed media in from the sources in .env")
    migrate.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="NAME=PATH",
        dest="source_overrides",
        help="use PATH for source NAME this time, instead of its variable; repeatable",
    )
    edit = migrate.add_subparsers(dest="media_command")
    item = edit.add_parser("add", help="add one item to media/manifest.toml")
    item.add_argument("source", metavar="SOURCE", help="a source name from the manifest")
    item.add_argument("origin", metavar="ORIGIN", help="path in that source, or absolute under it")
    item.add_argument("dest", metavar="DEST", help="path under media/")
    item.add_argument("--licence", required=True, help="what entitles this copy")
    item.add_argument("--optional", action="store_true", help="the project works without it")
    origin = edit.add_parser("source", help="add a named source to media/manifest.toml")
    origin.add_argument("name", metavar="NAME", help="lower case letters, digits and _")
    origin.add_argument("--env", required=True, help="the variable naming its folder")
    origin.add_argument("--description", required=True, help="what folder the variable names")

    sub.add_parser("media-verify", help="check media/ against manifest.lock.json")
    sub.add_parser("doctor", help="report what is installed and what is missing")
    sub.add_parser("guard", help="fail if git tracks licensed media or .env")

    build = sub.add_parser("toolchain", help="build the pinned vasm and vlink into .tools/")
    build.add_argument("--force", action="store_true", help="rebuild even if present")

    asm = sub.add_parser("asm", help="assemble 68000 source into a Kickstart 1.2 executable")
    asm.add_argument("source", type=Path)
    asm.add_argument("-o", "--output", type=Path, help="default: build/<source name>")

    disk = sub.add_parser("adf", help="write a bootable Kickstart 1.2 floppy holding FILEs")
    disk.add_argument("image", type=Path, metavar="OUT.adf")
    disk.add_argument("files", type=Path, nargs="+", metavar="FILE")
    disk.add_argument(
        "--startup",
        action="append",
        metavar="COMMAND",
        help="a line of s/startup-sequence; repeat for more lines",
    )
    disk.add_argument("--label", help="volume name; default is the image name")

    boot = sub.add_parser(
        "bootdisk", help="assemble SOURCE.s and write build/<name>.adf that runs it at boot"
    )
    boot.add_argument("source", type=Path, metavar="SOURCE.s")

    systems = sub.add_parser("system", help="build and list systems from systems/NAME.toml")
    act = systems.add_subparsers(dest="system_command", required=True)
    make = act.add_parser("build", help="build runs/systems/NAME, applying only what changed")
    make.add_argument("name", metavar="NAME")
    make.add_argument("--force", action="store_true", help="rebuild every layer from nothing")
    act.add_parser("list", help="list the recipes and whether each is built")
    out = act.add_parser(
        "export", help="write a built system to an RDB hard-disk image for a real Amiga"
    )
    out.add_argument("name", metavar="NAME")
    out.add_argument("image", type=Path, metavar="OUT.hdf")
    out.add_argument(
        "--include-personal",
        action="store_true",
        help="keep paths the recipe marks personal, such as a keyfile",
    )
    out.add_argument("--system-size", type=int, default=49, metavar="MIB", help="DH0; 49")
    out.add_argument("--work-size", type=int, default=748, metavar="MIB", help="DH1 Work; 748")

    once = sub.add_parser(
        "exec", help="boot MACHINE with no window, run an AmigaDOS SCRIPT once, then quit"
    )
    once.add_argument("machine", metavar="MACHINE", help="a machine with a built system")
    once.add_argument("script", type=Path, metavar="SCRIPT", help="AmigaDOS script on the host")
    once.add_argument("--timeout", type=float, default=300, help="seconds to wait; default 300")
    once.add_argument("--screenshot", type=Path, metavar="PNG", help="screenshot when it ends")
    once.add_argument(
        "--image",
        type=Path,
        metavar="HDF",
        help="boot an exported image (`system export`) in place of the system folder",
    )

    piano = sub.add_parser(
        "piano", help="build a Paula piano from RECIPE.toml: samples, scores, voice logs, WAVs"
    )
    piano.add_argument("recipe", type=Path, metavar="RECIPE.toml")
    piano3500 = sub.add_parser(
        "piano3500",
        help="model the A3500's 68030 piano from RECIPE.toml: 16 mixed voices, voice logs, WAVs",
    )
    piano3500.add_argument("recipe", type=Path, metavar="RECIPE.toml")
    image3500 = sub.add_parser(
        "piano3500-image",
        help="write the A3500 piano's RDB hard-disk image (BlueSCSI): it boots to the screen",
    )
    image3500.add_argument("recipe", type=Path, metavar="RECIPE.toml")
    image3500.add_argument(
        "--out", type=Path, metavar="HDF", help="the image; build/piano3500/piano3500.hdf"
    )
    image3500.add_argument(
        "--boot", action="store_true", help="then boot it headless and screenshot the screen"
    )
    run3500 = sub.add_parser(
        "piano3500-run",
        help="boot the A3500 with the 68030 piano player, play PIECEs, "
        "compare their voice logs with the model's",
    )
    run3500.add_argument("recipe", type=Path, metavar="RECIPE.toml")
    run3500.add_argument("pieces", nargs="*", metavar="PIECE")
    run3500.add_argument(
        "--screen",
        action="store_true",
        help="boot the screen and play through its checks (rotation, click, keys, F, Space, Q)",
    )
    run3500.add_argument(
        "--realtime", action="store_true", help="run at the machine's own speed, not in warp"
    )
    run3500.add_argument("--timeout", type=float, default=1800, help="seconds for the run; 1800")
    disks = sub.add_parser(
        "piano-disk", help="assemble the recipe's 68000 player onto a boot floppy per piece"
    )
    disks.add_argument("recipe", type=Path, metavar="RECIPE.toml")
    disks.add_argument("--out", type=Path, metavar="DIR", help="where the disks go; build/piano")
    survey = sub.add_parser(
        "piano-survey",
        help="measure every MAESTRO performance of a length for the recipe's four voices",
    )
    survey.add_argument("recipe", type=Path, metavar="RECIPE.toml")
    survey.add_argument("--min-s", type=float, default=120, help="shortest, seconds; 120")
    survey.add_argument("--max-s", type=float, default=360, help="longest, seconds; 360")
    check = sub.add_parser(
        "piano-run",
        help="boot the piano floppy headless and choose pieces on its screen; "
        "compare their logs, record audio",
    )
    check.add_argument("recipe", type=Path, metavar="RECIPE.toml")
    check.add_argument(
        "pieces", nargs="+", metavar="PIECE", help="piece names from the recipe, played in order"
    )
    check.add_argument("--machine", default="a500", help="a machine from amiga.toml; a500")
    check.add_argument(
        "--switch-after-s",
        type=float,
        metavar="S",
        help="choose the next piece S seconds into each piece but the last, while it plays",
    )
    check.add_argument(
        "--click", action="store_true", help="choose by clicking each piece's line, not its key"
    )
    check.add_argument(
        "--scope-shots",
        type=int,
        default=0,
        metavar="N",
        help="take N more screenshots while each piece plays and count scopes caught half drawn",
    )
    check.add_argument("--name", help="what the run's files are called; emulator-screen[-log]")
    check.add_argument(
        "--floppy",
        type=Path,
        metavar="ADF",
        help="the disk to boot; build/piano/piano-log.adf with --log, else build/piano/piano.adf",
    )
    mode = check.add_mutually_exclusive_group(required=True)
    mode.add_argument("--log", action="store_true", help="the test build: compare the voice log")
    mode.add_argument("--audio", action="store_true", help="the player, in real time, to a WAV")
    mode.add_argument(
        "--realtime", action="store_true", help="the player, in real time, with no recording"
    )

    rotation = sub.add_parser(
        "piano-rotation",
        help="boot the piano test floppy and check that it plays by itself: "
        "the quiet start, the gaps, a click, the wrap, Space, a key",
    )
    rotation.add_argument("recipe", type=Path, metavar="RECIPE.toml")
    rotation.add_argument("--machine", default="a500", help="a machine from amiga.toml; a500")
    rotation.add_argument(
        "--floppy", type=Path, metavar="ADF", help="the test build; build/piano/piano-log.adf"
    )
    rotation.add_argument("--name", default="emulator-rotation", help="the run's files' name")

    film = sub.add_parser(
        "piano-video",
        help="record the piano floppy playing by itself, frame by frame, and make a 4K YouTube "
        "master, chapters and a description in runs/video",
    )
    film.add_argument("recipe", type=Path, metavar="RECIPE.toml")
    film.add_argument("--machine", default="a500", help="a machine from amiga.toml; a500")
    film.add_argument(
        "--floppy", type=Path, metavar="ADF", help="the player's disk; build/piano/piano.adf"
    )
    film.add_argument("--out", type=Path, metavar="DIR", help="where it all goes; runs/video")
    film.add_argument(
        "--seconds", type=float, metavar="S", help="stop after S seconds of emulated time (a test)"
    )
    film.add_argument(
        "--steps",
        default="record,master,measure",
        help="which of record, master, measure to do; all three",
    )
    film.add_argument(
        "--description",
        type=Path,
        metavar="TXT",
        help="the description with {chapters}; video-description.txt beside the recipe",
    )

    # Listed for --help only; `run` is dispatched in main, before argparse sees it.
    sub.add_parser("run", help="run Amiberry with the project's private home directory")
    return parser, sub


def command_names() -> set[str]:
    """Every amiga-env command; no machine may take one of these names."""
    return set(build_parser()[1].choices)


def dispatch(args: argparse.Namespace) -> int:
    """Run a parsed command. A handler's int result is the exit status; anything else is 0."""
    status = COMMANDS[args.command](args)
    return status if type(status) is int else 0


COMMANDS = {
    "init": lambda args: init.init(Path.cwd(), args.force),
    "amiberry": lambda args: amiberry.install(args.tag, args.force),
    "amiberry-path": lambda args: print(amiberry.installed_binary()),
    "media": lambda args: _media(args),
    "media-verify": lambda args: 0 if media.verify() else 1,
    "doctor": lambda args: _doctor(),
    "guard": lambda args: guard.run(project.root()),
    "toolchain": lambda args: toolchain.install_all(args.force),
    "asm": lambda args: assemble.assemble(
        args.source, args.output or assemble.outputs(args.source)[0]
    ),
    "adf": lambda args: adf.make_adf(args.image, args.files, args.startup, args.label),
    "bootdisk": lambda args: assemble.bootdisk(args.source),
    "system": lambda args: _system(args),
    "exec": lambda args: _exec(args),
    "piano": lambda args: _piano(args.recipe),
    "piano3500": lambda args: _piano3500(args.recipe),
    "piano3500-run": lambda args: _piano3500_run(args),
    "piano3500-image": lambda args: _piano3500_image(args),
    "piano-disk": lambda args: _piano_disk(args.recipe, args.out),
    "piano-survey": lambda args: _piano_survey(args),
    "piano-run": lambda args: _piano_run(args),
    "piano-rotation": lambda args: _piano_rotation(args),
    "piano-video": lambda args: _piano_video(args),
}


def _system(args: argparse.Namespace) -> None:
    if args.system_command == "list":
        system.list_systems()
    elif args.system_command == "export":
        export.export(
            args.name, args.image, args.include_personal, args.system_size, args.work_size
        )
    else:
        system.build(args.name, args.force)


def _exec(args: argparse.Namespace) -> int:
    machines = profile.load_machines(reserved=command_names())
    if args.machine not in machines:
        raise SystemExit(f"no machine {args.machine} in {project.CONFIG}")
    machine = machines[args.machine]
    if machine.system is None:
        raise SystemExit(f"{args.machine} boots no system, so it has no amiga-env startup hook")
    _ready(machine)
    exchange = project.runs_dir() / "exec" / args.machine
    outcome = session.run_script(
        profile.machine_args(machine, image=args.image.resolve() if args.image else None),
        exchange,
        args.script.read_text(),
        args.timeout,
        args.screenshot,
    )
    sys.stdout.write(outcome.log)
    print(f"exec      return code {outcome.return_code} after {outcome.seconds:.1f} s")
    return 0 if outcome.return_code == 0 else 1


def _piano(recipe: Path) -> None:
    from .piano import build  # numpy and mido load only for this command

    report = build.build(recipe)
    memory = report["memory"]
    print(f"piano     {len(report['samples'])} samples, layer {report['layer']}")
    print(
        f"memory    {memory['total_bytes']} of {memory['budget_bytes']} bytes "
        f"(samples {memory['samples_bytes']}, headroom {memory['headroom_bytes']})"
    )
    for name, piece in report["pieces"].items():
        print(
            f"{name:<16} {piece['bytes']} score bytes, {piece['steals_per_minute']} steals/min, "
            f"stolen volume median {piece['stolen_volume_median']}"
        )


def _piano3500(recipe: Path) -> None:
    from .piano import build3500  # numpy and mido load only for this command

    report = build3500.build(recipe)
    memory = report["memory"]
    print(f"piano3500 {len(report['samples'])} samples in {len(report['layers'])} layers")
    print(
        f"memory    {memory['total_bytes']} of {memory['budget_bytes']} bytes "
        f"(samples {memory['samples_bytes_padded']}, headroom {memory['headroom_bytes']})"
    )
    for name, piece in report["pieces"].items():
        print(
            f"{name:<18} {piece['clips']['cut_while_held_per_minute']} cut while held/min, "
            f"peak {piece['peak_dbfs']} dBFS, {piece['clamped']} clamped, "
            f"{piece['seconds_to_render']} s"
        )
    worst = report["worst_case"]
    print(
        f"worst     keys {worst['keys']} at velocity 127: {worst['peak_dbfs']} dBFS, "
        f"{worst['clamped']} clamped, {worst['wraps']} wrapped"
    )
    print(f"done      in {report['seconds_total']} s")


def _piano3500_image(args: argparse.Namespace) -> None:
    from .piano import build3500, image3500

    image = image3500.build(args.recipe, args.out)
    print(f"image     {image} ({image.stat().st_size} bytes); Credits beside it")
    if args.boot:
        recipe = build3500.load_recipe(args.recipe)
        machines = profile.load_machines(reserved=command_names())
        if recipe.machine not in machines:
            raise SystemExit(f"{args.recipe}: no machine {recipe.machine!r} in {project.CONFIG}")
        _ready(machines[recipe.machine])
        found = image3500.boot(
            machines[recipe.machine], image, project.root() / recipe.out / "machine"
        )
        print(
            f"booted    through {found['controller']}: screen up {found['screen_up_s']} s "
            f"after the player started ({found['wall_s_to_screen']} s wall); "
            f"{found['screenshot']}"
        )


def _piano3500_run(args: argparse.Namespace) -> int:
    from .piano import build3500, run3500

    recipe = build3500.load_recipe(args.recipe)
    machines = profile.load_machines(reserved=command_names())
    if recipe.machine not in machines:
        raise SystemExit(f"{args.recipe}: no machine {recipe.machine!r} in {project.CONFIG}")
    machine = machines[recipe.machine]
    _ready(machine)
    out = project.root() / recipe.out / "machine"
    if args.screen:
        from .piano import harness3500

        found = harness3500.run(machine, recipe, out / "screen")
        print(json.dumps(found, indent=2))
        return 0
    if not args.pieces:
        raise SystemExit("name the pieces to play, or give --screen")
    found = run3500.run(machine, recipe, args.pieces, out, not args.realtime, args.timeout)
    good = True
    for name, piece in found["pieces"].items():
        cpu, log = piece["cpu"], piece["log"]
        same = "identical" if log["identical"] else f"differs: {log['first_difference']}"
        good &= log["identical"] and piece["done"] and cpu["overruns"] == 0
        print(
            f"{name:<18} log {same}, CPU {cpu['mean_percent']}% mean, "
            f"{cpu['worst_percent']}% worst, {cpu['overruns']} overruns, "
            f"{piece['wall_seconds']} s"
        )
    print(f"done      in {found['wall_seconds']} s; {out / 'piano3500-run.json'}")
    return 0 if good else 1


def _piano_disk(recipe: Path, out: Path | None) -> None:
    from .piano import build, disk

    disk.build_disks(build.load_recipe(recipe), out=out)


def _piano_survey(args: argparse.Namespace) -> None:
    from .piano import build

    rows = build.survey(args.recipe, args.min_s, args.max_s)
    print(f"survey    {len(rows)} performances; fewest audible cuts a minute first:")
    for row in rows[:20]:
        print(
            f"{row['cut_audible_per_minute']:6.1f}/min  ringing {row['ringing_p95']:>2}  "
            f"{row['length_s']:5.0f} s  {row['composer']}: {row['title']} ({row['year']})"
        )


def _piano_run(args: argparse.Namespace) -> int:
    from .piano import build, disk, machine

    recipe = build.load_recipe(args.recipe)
    keys = {p.name: key for p, key in zip(recipe.pieces, disk.MENU_KEYS)}
    order = {p.name: i for i, p in enumerate(recipe.pieces)}
    unknown = [name for name in args.pieces if name not in keys]
    if unknown:
        raise SystemExit(f"no piece {unknown[0]} in {args.recipe}")
    machines = profile.load_machines(reserved=command_names())
    out = project.root() / recipe.out
    player, test = disk.DISK_NAMES
    name = args.name or ("emulator-screen-log" if args.log else "emulator-screen")
    switch_ms = round(args.switch_after_s * 1000) if args.switch_after_s is not None else None
    lines = disk.click_points(recipe)
    scopes = machine.ScopeCheck(*disk.scope_regions(recipe), args.scope_shots)
    found = machine.run_menu(
        machines[args.machine],
        args.floppy or project.build_dir() / "piano" / (test if args.log else player),
        [
            machine.Choice(n, keys[n], out / "m68k" / f"{n}.log", lines[n], order[n])
            for n in args.pieces
        ],
        out,
        name,
        log=args.log,
        audio=args.audio,
        switch_after_ms=switch_ms,
        click=args.click,
        scopes=scopes,
        realtime=args.realtime,
    )
    print(f"samples in chip RAM at {found['samples_in_chip']['address']}")
    print(f"chip RAM free with the screen open: {found['chip_free_with_the_screen_open']}")
    matched = True
    for piece, result in found["pieces"].items():
        cpu, free, scopes = result["cpu"], result["memory_free_while_playing"], result["scopes"]
        left = (
            ", left playing for the next choice"
            if result["left_playing_for_the_next_choice"]
            else ""
        )
        print(
            f"{piece} (key {result['key']}): {cpu['frames']} frames{left}, player "
            f"{cpu['percent_of_cpu']}%, with scopes {scopes['player_and_scopes_percent_of_cpu']}% "
            f"of the CPU, scopes {scopes['scope_frames_per_second']}/s; "
            f"free {free['chip']} chip, {free['other']} other"
        )
        if result.get("scope_shots", {}).get("shots"):
            shots = result["scope_shots"]
            print(f"  scopes whole in {shots['every_scope_whole']} of {shots['shots']} screenshots")
        if args.log:
            print(f"  voice log: {json.dumps(result['log'])}")
            matched &= result["log"]["same_ticks"]
    if args.audio:
        print(f"audio: {found.get('wav')}")
    return 0 if matched and found["ended"] else 1


def _piano_rotation(args: argparse.Namespace) -> int:
    from .piano import build, disk, machine

    recipe = build.load_recipe(args.recipe)
    out = project.root() / recipe.out
    lines = disk.click_points(recipe)
    choices = [
        machine.Choice(p.name, key, out / "m68k" / f"{p.name}.log", lines[p.name], i)
        for i, (p, key) in enumerate(zip(recipe.pieces, disk.MENU_KEYS))
    ]
    floppy = args.floppy or project.build_dir() / "piano" / disk.DISK_NAMES[1]
    found = machine.run_rotation(
        profile.load_machines(reserved=command_names())[args.machine],
        floppy,
        choices,
        out,
        args.name,
    )
    for step, result in found["steps"].items():
        print(f"{step}: {json.dumps(result)}")
    logs = [r for step, r in found["steps"].items() if step.endswith("_log") or "_log_" in step]
    return 0 if all(r["same_ticks"] for r in logs) and found["steps"]["quit"]["ended"] else 1


def _piano_video(args: argparse.Namespace) -> int:
    from .piano import build, disk, recording

    recipe = build.load_recipe(args.recipe)
    if recipe.screen is None:
        raise SystemExit(f"{args.recipe} has no [screen] table")
    out = args.out or project.root() / "runs" / "video"
    found = recording.make_video(
        profile.load_machines(reserved=command_names())[args.machine],
        args.floppy or project.build_dir() / "piano" / disk.DISK_NAMES[0],
        out,
        disk.titles(recipe),
        recipe.screen,
        args.description or args.recipe.parent / "video-description.txt",
        steps=[step.strip() for step in args.steps.split(",") if step.strip()],
        max_seconds=args.seconds,
    )
    if "record" in found:
        made = found["record"]
        print(
            f"recorded {made['frames']} frames ({made['seconds']} s) and {made['samples']} "
            f"samples ({made['samples_off_by']} off the frame rate's count)"
        )
    if "chapters" in found:
        print("\n".join(found["chapters"]["lines"]))
    print(f"results: {out / 'video.json'}")
    return 0


def _ready(machine: profile.Machine) -> None:
    """A machine's system must be built and its volume folders must exist."""
    if machine.system is not None and not system.built_layers(machine.system):
        raise SystemExit(f"run `amiga-env system build {machine.system}` first")
    for volume in profile.volumes(machine)[1 if machine.system else 0 :]:
        volume.path.mkdir(parents=True, exist_ok=True)


def parse_overrides(pairs: list[str]) -> dict[str, Path]:
    """`--source NAME=PATH` values as a mapping."""
    overrides = {}
    for pair in pairs:
        name, sep, path = pair.partition("=")
        if not sep or not name or not path:
            raise SystemExit(f"--source takes NAME=PATH, not {pair!r}")
        overrides[name] = Path(path).expanduser()
    return overrides


def boot_command(machine: profile.Machine, rest: list[str], media_dir: Path | None = None):
    """Amiberry arguments for `amiga-env MACHINE [DISK.adf] [amiberry options]`."""
    if rest and not rest[0].startswith("-"):
        return profile.machine_args(machine, Path(rest[0]).resolve(), media_dir) + rest[1:]
    return profile.machine_args(machine, media=media_dir) + rest


def _machines(commands: set[str]) -> dict[str, profile.Machine]:
    """The machines of the project here, or none when there is no project."""
    if project.current_root() is None:
        return {}
    return profile.load_machines(reserved=commands)


def _media(args: argparse.Namespace) -> None:
    if args.media_command == "add":
        media.add(args.source, args.origin, args.dest, args.licence, args.optional)
    elif args.media_command == "source":
        media.add_source(args.name, args.env, args.description)
    else:
        overrides = parse_overrides(args.source_overrides)
        known = media.load_manifest().sources
        unknown = sorted(overrides.keys() - known.keys())
        if unknown:
            raise SystemExit(f"--source names no source in the manifest: {', '.join(unknown)}")
        media.migrate(overrides)


def _doctor() -> int:
    root = project.root()
    print(f"project   {root}")
    ok = _amiberry_report()
    ok = _toolchain_report() and ok
    ok = _media_report(root) and ok
    ok = _machines_report() and ok
    return 0 if ok else 1


def _amiberry_report() -> bool:
    version = amiberry.installed_version()
    if not version:
        print("amiberry  not installed; run `amiga-env amiberry`")
        return False
    print(f"amiberry  {version}{_latest_note(version)}")
    out = subprocess.run(
        [str(amiberry.installed_binary()), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    banner = (out.stdout or out.stderr).splitlines()
    print(f"          {banner[0] if banner else '(no --help output)'}")
    return _paths_stay_inside_project()


def _media_report(root: Path) -> bool:
    try:
        manifest = media.load_manifest()
    except SystemExit as error:
        print(f"media     {error}")
        return False
    values = media.project_values(root, os.environ)
    folders = media.source_folders(manifest, values)
    for line in source_lines(manifest, folders):
        print(line)
    return media.verify()


def source_lines(manifest: media.Manifest, folders: dict[str, Path | None]) -> list[str]:
    """One doctor line per source: its variable, and whether it names a folder."""
    if not manifest.sources:
        return ["sources   none in media/manifest.toml"]
    lines = []
    for index, (name, source) in enumerate(manifest.sources.items()):
        folder = folders.get(name)
        if folder is None:
            state = f"{source.env} is not set (see .env.example)"
        else:
            found = "found" if folder.is_dir() else "NOT A FOLDER"
            state = f"{source.env} = {folder} ({found})"
        lines.append(f"{'sources' if index == 0 else '':<9} {name:<14} {state}")
    return lines


def _machines_report() -> bool:
    try:
        machines = profile.load_machines(reserved=command_names())
    except SystemExit as error:
        print(f"machines  {error}")
        return False
    if not machines:
        print(f"machines  none defined; add a [machines.NAME] table to {project.CONFIG}")
        return True
    print(f"machines  {', '.join(machines)}")
    lines, ok = machine_media_lines(machines, project.media_dir())
    for line in lines:
        print(line)
    for name, machine in machines.items():
        if machine.system is not None:
            built = system.built_layers(machine.system) == system.fingerprints(
                system.load(machine.system)
            )
            state = (
                "built" if built else f"NOT BUILT; run `amiga-env system build {machine.system}`"
            )
            print(f"{name:<9} {'system':<9} {machine.system} {state}")
    return ok


def machine_media_lines(
    machines: dict[str, profile.Machine], media_dir: Path
) -> tuple[list[str], bool]:
    """Whether each machine's Kickstart and floppy are in media/."""
    lines, ok = [], True
    for name, machine in machines.items():
        for role, path in profile.media_paths(machine).items():
            present = (media_dir / path).is_file()
            ok = ok and present
            lines.append(f"{name:<9} {role:<9} {path} {'present' if present else 'MISSING'}")
    return lines, ok


def _toolchain_report() -> bool:
    try:
        listing = toolchain.fetch_listing()
    except OSError as error:
        listing = None
        print(f"toolchain could not check for newer releases: {error}")
    ok = True
    for source in toolchain.SOURCES:
        version = toolchain.installed_version(source)
        if version is None:
            print(f"{source.name:<9} not installed; run `amiga-env toolchain`")
            ok = False
            continue
        note = "" if version == source.version else f" (pinned is {source.version})"
        if listing is not None:
            newest = toolchain.listed_versions(listing, source.name)[-1:]
            if newest and toolchain.version_key(newest[0]) > toolchain.version_key(source.version):
                note += f" ({newest[0]} is available; update the pin in toolchain.py)"
        print(f"{source.name:<9} {version}{note}")
    return ok


def _latest_note(version: str) -> str:
    try:
        latest = amiberry.fetch_release().version
    except OSError as error:  # offline, DNS, GitHub rate limit
        return f" (could not check for a newer release: {error})"
    return "" if latest == version else f" (latest is {latest}; run `amiga-env amiberry`)"


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
    outside = paths_outside(out.stdout, project.root())
    if outside:
        print("paths     OUTSIDE the project:")
        for line in outside:
            print(f"          {line}")
        return False
    print("paths     all inside the project")
    return True


if __name__ == "__main__":
    sys.exit(main())
