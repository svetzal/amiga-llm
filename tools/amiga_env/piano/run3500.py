"""Run the A3500 piano's 68030 player on the emulated A3500 and check it against the model.

A run builds a volume (a host folder booted as DH0: through Amiberry's
filesystem2): `S/Startup-Sequence`, the player's test build (`player`, LOG=1),
`piano.tab` and `samples.bin` (m68k3500.py), `scores/` and an empty `logs/`.
Its Startup-Sequence plays the chosen pieces one after another:

    player 1 nocturne-op9-2
    player 2 bwv846

The player writes each piece's voice log to `logs/NAME.log` as it plays and,
when it ends, its status block to `logs/NAME.stat`. The host boots the
machine with no window, waits for each `.stat` file, compares each log with
the model's byte for byte, and stops the emulator it started. The player's
status block at $100 is read through the control socket (READ_MEM) only to
show progress.

The player is assembled with the model's constants (`defines`), so the two
cannot drift apart.
"""

import json
import shutil
import struct
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from .. import assemble, profile, project, session
from . import build3500, disk, m68k3500, mixer, picture, player3500, score
from . import font as font_mod
from . import light as light_mod
from . import screen as screen_mod

PROGRAM = "player"
VOLUME_LABEL = "Piano3500"
QUEUE = 32  # changes a voice can hold queued (the player's own limit)
STATUS = 0x100
MAGIC = 0x50333550  # 'P35P'
DONE, FAILED = 2, 0xFFFFFFFF
STATUS_FIELDS = (
    "magic",
    "state",
    "error",
    "run",
    "blocks",
    "total_e",
    "worst_e",
    "overruns",
    "notes",
    "steals",
    "restrikes",
    "clamped",
    "log_bytes",
    "log_overruns",
    "queue_full",
    "e_freq",
    "cacr",
    "samples",
    "mode",
    "piece",
    "pieces",
    "played",
    "stopped",
    "starts",
    "rotated",
    "next",
    "rotate_at",
    "highlight",
    "window",
    "key",
    "keys",
    "clicks",
    "click_xy",
    "filter_keys",
    "vblanks",
    "vblank_hz",
    "loaded_at",
    "preload_frames",
    "screen_at",
    "chosen_at",
    "gold_at",
    "playing_at",
    "first_note_at",
    "ended_at",
    "worst_total_e",
    "task_e",
    "units",
    "unit_max_e",
    "fast_free_before",
    "fast_largest_before",
    "fast_free_after",
    "fast_largest_after",
)
STATUS_BYTES = 4 * len(STATUS_FIELDS)
BLOCK_E = mixer.BLOCK * mixer.MIX_PERIOD / 5  # E-clock ticks a block lasts: Paula's clock / 5


class Status(NamedTuple):
    magic: int
    state: int
    error: int
    run: int
    blocks: int
    total_e: int
    worst_e: int
    overruns: int
    notes: int
    steals: int
    restrikes: int
    clamped: int
    log_bytes: int
    log_overruns: int
    queue_full: int
    e_freq: int
    cacr: int
    samples: int
    mode: int
    piece: int
    pieces: int
    played: int
    stopped: int
    starts: int
    rotated: int
    next: int
    rotate_at: int
    highlight: int
    window: int
    key: int
    keys: int
    clicks: int
    click_xy: int
    filter_keys: int
    vblanks: int
    vblank_hz: int
    loaded_at: int
    preload_frames: int
    screen_at: int
    chosen_at: int
    gold_at: int
    playing_at: int
    first_note_at: int
    ended_at: int
    worst_total_e: int
    task_e: int
    units: int
    unit_max_e: int
    fast_free_before: int  # fast RAM free just before samples.bin's AllocMem
    fast_largest_before: int  # its largest block, which samples.bin must fit in
    fast_free_after: int  # once every allocation for the screen is done
    fast_largest_after: int


def defines(log: bool = True) -> dict[str, int]:
    """The model's constants, as the player is assembled with them."""
    return {
        "VOICES": player3500.VOICES,
        "BLOCK": mixer.BLOCK,
        "PERIOD": mixer.MIX_PERIOD,
        "FADE_STEP": player3500.FADE_STEP,
        "STOP_VOLUME": player3500.STOP_VOLUME,
        "LIMIT_BLOCKS": player3500.LIMIT_BLOCKS,
        "OUTPUT_SHIFT": mixer.OUTPUT_SHIFT,
        "QUEUE": QUEUE,
        "LOG": int(log),
    }


def startup_sequence(pieces: Sequence[str]) -> str:
    """Play each piece in turn; a failed one does not stop the rest."""
    lines = ["; Written by amiga-env piano3500-run.", "FailAt 21"]
    lines += [f"{PROGRAM} {run} {name}" for run, name in enumerate(pieces, 1)]
    return "\n".join(lines) + "\n"


def parse_status(data: bytes) -> Status:
    return Status(*struct.unpack(f">{len(STATUS_FIELDS)}L", data[:STATUS_BYTES]))


def cpu_report(status: Status) -> dict:
    """The mixing's share of the 68030, from the player's own E-clock readings.

    Each figure counts from the handler's first ReadEClock to its last, so
    it leaves out the time exec takes to call it.
    """
    blocks = max(status.blocks, 1)
    mean_e = status.total_e / blocks
    return {
        "blocks": status.blocks,
        "mean_e_per_block": round(mean_e),
        "worst_e_in_a_block": status.worst_e,
        "mean_percent": round(100 * mean_e / BLOCK_E, 1),
        "worst_percent": round(100 * status.worst_e / BLOCK_E, 1),
        "overruns": status.overruns,
    }


class Difference(NamedTuple):
    offset: int
    block: int  # -1 in the header
    voice: int  # -1 in the block's checksum or the header
    field: str
    model: int
    machine: int


VOICE_FIELDS = (
    ("key", 0, 1),
    ("sample", 1, 1),
    ("volume", 2, 2),
    ("left", 4, 2),
    ("right", 6, 2),
    ("phase", 8, 4),
    ("fraction", 12, 2),
)


def first_difference(model: bytes, machine: bytes) -> Difference | None:
    """Where two voice logs first differ, named by block, voice and field."""
    limit = min(len(model), len(machine))
    offset = next((i for i in range(limit) if model[i] != machine[i]), None)
    if offset is None:
        if len(model) == len(machine):
            return None
        offset = limit
    header = player3500.LOG_HEADER_BYTES
    if offset < header:
        return Difference(offset, -1, -1, "header", _byte(model, offset), _byte(machine, offset))
    block, within = divmod(offset - header, player3500.LOG_BLOCK_BYTES)
    start = header + block * player3500.LOG_BLOCK_BYTES
    if within < 8:
        name, at, size = ("checksum_a", 0, 4) if within < 4 else ("checksum_b", 4, 4)
        return Difference(
            offset,
            block,
            -1,
            name,
            _field(model, start + at, size),
            _field(machine, start + at, size),
        )
    voice, inner = divmod(within - 8, player3500.LOG_VOICE_BYTES)
    name, at, size = next(f for f in VOICE_FIELDS if f[1] <= inner < f[1] + f[2])
    base = start + 8 + voice * player3500.LOG_VOICE_BYTES + at
    return Difference(
        offset, block, voice, name, _field(model, base, size), _field(machine, base, size)
    )


def _byte(data: bytes, offset: int) -> int:
    return data[offset] if offset < len(data) else -1


def _field(data: bytes, offset: int, size: int) -> int:
    if offset + size > len(data):
        return -1
    return int.from_bytes(data[offset : offset + size], "big")


def compare_logs(model: bytes, machine: bytes) -> dict:
    blocks = player3500.LOG_BLOCK_BYTES
    difference = first_difference(model, machine)
    return {
        "model_bytes": len(model),
        "machine_bytes": len(machine),
        "model_blocks": (len(model) - player3500.LOG_HEADER_BYTES) // blocks,
        "machine_blocks": max(0, len(machine) - player3500.LOG_HEADER_BYTES) // blocks,
        "identical": model == machine,
        "first_difference": difference._asdict() if difference else None,
    }


INDEX = "scores/index"
PICTURE = "title.ilbm"
CREDITS = "Credits"


def index_text(pieces: Sequence[tuple[str, str]]) -> str:
    """scores/index: one line a piece, its name, a space and its title."""
    for name, title in pieces:
        if " " in name or not title.isascii() or "\n" in title:
            raise SystemExit(f"{name}: a name has no spaces and a title is one line of ASCII")
    return "".join(f"{name} {title}\n" for name, title in pieces)


def scopes_include(scopes: build3500.Scopes) -> str:
    """`scopes.i` for the player: where its two scopes start, and their width."""
    left, right = scopes.left
    return (
        "; scopes.i: made by `amiga-env piano3500-run` (run3500.py); do not edit.\n"
        f"STEREO_LEFT_L   equ {left}\n"
        f"STEREO_LEFT_R   equ {right}\n"
        f"STEREO_WIDTH    equ {scopes.width}\n"
    )


def unlit(made: screen_mod.Screen, light: light_mod.FilterLight) -> screen_mod.Screen:
    """`made` with register 14 (the light's) holding the light's `off` colour, as
    the player starts: the A3500 player draws no voice trace, so it sets the
    whole register as the filter changes."""
    colours = list(made.colours)
    colours[light_mod.REGISTER] = picture.parse_ocs(light.off)
    return made._replace(colours=colours)


def screen_data(recipe: build3500.Recipe, data: Path) -> Path:
    """title.ilbm, screen.i and menu.i (EXP-004's screen and keys), scopes.i
    (the two channels' scopes) and light.i (the filter light) into `data`;
    returns the picture."""
    if recipe.screen is None:
        raise SystemExit("the recipe shares no [screen] table (pieces = ...)")
    if recipe.scopes is None:
        raise SystemExit("the recipe has no [scopes] table")
    if recipe.filter_light is None:
        raise SystemExit("the recipe has no [filter_light] table")
    data.mkdir(parents=True, exist_ok=True)
    root = project.root()
    names = disk.titles(recipe)
    made = screen_mod.make(names, recipe.screen, root)
    font = font_mod.load(root / recipe.screen.font)
    spans = [(left, left + recipe.scopes.width) for left in recipe.scopes.left]
    made, place = light_mod.draw(made, recipe.screen, spans, recipe.filter_light, font)
    back = made.colours[light_mod.REGISTER]
    title = screen_mod.write(unlit(made, recipe.filter_light), recipe.screen, root, data, data)
    (data / "menu.i").write_text(disk.menu_include(len(names), recipe.rotate_s), encoding="ascii")
    (data / "scopes.i").write_text(scopes_include(recipe.scopes), encoding="ascii")
    light_i = light_mod.include(recipe.filter_light, place.box, back)
    (data / "light.i").write_text(light_i, encoding="ascii")
    return title


def write_files(
    recipe: build3500.Recipe, piano: build3500.Piano, folder: Path, startup: str, log: bool
) -> None:
    """Everything the player needs, in a folder it runs from (and boots from)."""
    if not recipe.player:
        raise SystemExit("the recipe names no player (player = ...)")
    if folder.exists():
        shutil.rmtree(folder)
    for sub in ("S", "scores", *(["logs"] if log else [])):
        (folder / sub).mkdir(parents=True)
    mixing = piano.mix_samples()
    (folder / "S" / "Startup-Sequence").write_text(startup, encoding="ascii")
    (folder / "piano.tab").write_bytes(m68k3500.tables_bytes(piano.instrument, mixing))
    (folder / "samples.bin").write_bytes(m68k3500.samples_bytes(mixing))
    data = project.root() / recipe.out / "m68030"
    shutil.copyfile(screen_data(recipe, data), folder / PICTURE)
    if recipe.credits:
        credits = (project.root() / recipe.credits).read_text(encoding="ascii")
        disk.check_credits(credits)
        (folder / CREDITS).write_text(credits, encoding="ascii")
    media = project.media_dir()
    (folder / INDEX).write_text(
        index_text([(p.name, p.title) for p in recipe.pieces]), encoding="ascii"
    )
    for piece in recipe.pieces:
        perf = score.performance(score.read_midi(media / piece.midi))
        (folder / "scores" / f"{piece.name}.score").write_bytes(score.encode(perf.events))
    assemble.assemble(project.root() / recipe.player, folder / PROGRAM, [data], defines(log=log))


def model_logs(
    recipe: build3500.Recipe, piano: build3500.Piano, pieces: Sequence[str]
) -> dict[str, bytes]:
    """The model's voice log of each named piece."""
    chosen = {p.name: p for p in recipe.pieces}
    unknown = [name for name in pieces if name not in chosen]
    if unknown:
        raise SystemExit(f"no piece {', '.join(unknown)} in the recipe")
    mixing = piano.mix_samples()
    media = project.media_dir()
    logs = {}
    for name in dict.fromkeys(pieces):
        perf = score.performance(score.read_midi(media / chosen[name].midi))
        logs[name] = player3500.play(perf.events, piano.instrument, mixing).log
    return logs


def build_volume(recipe: build3500.Recipe, pieces: Sequence[str], folder: Path) -> dict[str, bytes]:
    """The log run's volume (one line a piece), and each piece's model voice log."""
    piano = build3500.make_piano(recipe)
    models = model_logs(recipe, piano, pieces)
    write_files(recipe, piano, folder, startup_sequence(pieces), log=True)
    return models


class Machine:
    """Gateway: an emulator this run started, booting the volume as DH0:."""

    def __init__(self, args: Sequence[str], log_path: Path):
        self._emulator = session.Emulator([*args, "-G"], log_path, {"SDL_AUDIODRIVER": "dummy"})

    def connect(self, volume: Path, timeout: float = 60.0) -> None:
        """Find this emulator's socket, and check it is the one booting our volume."""
        emulator, deadline = self._emulator, time.monotonic() + timeout
        while emulator.socket is None:
            if time.monotonic() > deadline or not emulator.running():
                raise SystemExit(f"Amiberry opened no control socket; see {emulator.log_path}")
            emulator.socket = session.socket_path(emulator.log())
            time.sleep(0.5)
        while True:
            try:
                reply = emulator.send("LIST_HARDDRIVES")
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        if str(volume) not in "\t".join(reply):
            theirs, emulator.socket = emulator.socket, None
            raise SystemExit(f"the emulator on {theirs} is not this run's: {reply}")

    def running(self) -> bool:
        return self._emulator.running()

    def warp(self, on: bool) -> None:
        self._emulator.send("SET_WARP", "1" if on else "0")

    def status(self) -> Status:
        longs = []
        for i in range(len(STATUS_FIELDS)):
            reply = self._emulator.send("READ_MEM", hex(STATUS + 4 * i), "4")
            longs.append(int(reply[1]) if reply[0] == "OK" else 0)
        return Status(*longs)

    def stop(self) -> None:
        self._emulator.stop()


def run(
    machine: profile.Machine,
    recipe: build3500.Recipe,
    pieces: Sequence[str],
    out: Path,
    warp: bool = True,
    timeout: float = 1800.0,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Play `pieces` on the machine with logging and compare each with the model."""
    volume = (out / "volume").resolve()
    models = build_volume(recipe, pieces, volume)
    args = [
        *profile.base_args(machine),
        *session.volume_args([session.Volume("DH0", VOLUME_LABEL, volume, 0)]),
    ]
    found: dict = {"machine": recipe.machine, "warp": warp, "pieces": {}}
    began = now()
    amiga = Machine(args, out / "piano3500-run.amiberry.log")
    try:
        amiga.connect(volume)
        if warp:
            amiga.warp(True)
        for name in pieces:
            start = now()
            stat = volume / "logs" / f"{name}.stat"
            while not (stat.exists() and stat.stat().st_size == STATUS_BYTES):
                if not amiga.running():
                    raise SystemExit("Amiberry stopped before the pieces were played")
                if now() - began > timeout:
                    raise SystemExit(
                        f"{name} did not finish within {timeout:g} s: {amiga.status()}"
                    )
                sleep(1.0)
            status = parse_status(stat.read_bytes())
            machine_log = (volume / "logs" / f"{name}.log").read_bytes()
            (out / f"{name}.machine.voices.bin").write_bytes(machine_log)
            found["pieces"][name] = {
                "status": status._asdict(),
                "done": status.state == DONE,
                "cpu": cpu_report(status),
                "log": compare_logs(models[name], machine_log),
                "wall_seconds": round(now() - start, 1),
            }
    finally:
        amiga.stop()
    found["wall_seconds"] = round(now() - began, 1)
    (out / "piano3500-run.json").write_text(json.dumps(found, indent=2) + "\n")
    return found
