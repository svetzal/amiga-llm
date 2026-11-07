"""Put the 68000 piano player and its pieces on one boot floppy.

The player (the recipe's `player` source) is assembled twice from the data
`amiga-env piano` wrote to `<out>/m68k/`: the player Stacey boots, and a
test build (`LOG=1`) that also writes the voice log. The program holds the
samples and tables; each piece is its own score file, listed in an index in
menu order, so a piece is added by rebuilding the disk, not the program:

    piano                          the program
    scores/index                   one line a piece: its score's path, a space, its title
    scores/NN-<piece>.score        the score byte stream (see score.py)
    s/startup-sequence             `piano`: the menu

    build/piano/piano.adf          the player
    build/piano/piano-log.adf      the test build

The menu shows the pieces under keys 1 to 9, then the letters without Q,
which quits (MENU_KEYS, the same string as `menu_keys` in the player).
"""

from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from .. import adf, assemble, project
from . import survey
from .build import Recipe

PROGRAM = "piano"
DISK_NAMES = ("piano.adf", "piano-log.adf")
LABEL = "Piano"
INDEX = "scores/index"
MENU_KEYS = "123456789ABCDEFGHIJKLMNOPRSTUVWXYZ"
OFS_DATA_BYTES = 488  # of each 512-byte block of an OFS file


class MenuPiece(NamedTuple):
    key: str  # the menu key
    path: str  # the score's path on the disk
    title: str  # ASCII


def menu(pieces: Sequence[tuple[str, str]]) -> list[MenuPiece]:
    """Each piece's key, score path and title, in menu order, from (name, title) pairs."""
    if len(pieces) > len(MENU_KEYS):
        raise SystemExit(f"the menu has {len(MENU_KEYS)} keys; {len(pieces)} pieces given")
    entries = []
    for number, (key, (name, title)) in enumerate(zip(MENU_KEYS, pieces, strict=False), 1):
        path = f"scores/{number:02d}-{name}.score"
        if not title or not title.isascii() or "\n" in title:
            raise SystemExit(f"{name}: a menu title is one line of ASCII, not {title!r}")
        adf.disk_path((Path(), path))  # an OFS name, or SystemExit
        entries.append(MenuPiece(key, path, title))
    return entries


def index_text(entries: Sequence[MenuPiece]) -> str:
    """The index file: one line a piece, `<score path> <title>`, LF endings."""
    return "".join(f"{e.path} {e.title}\n" for e in entries)


def menu_lines(entries: Sequence[MenuPiece]) -> list[str]:
    """The lines the player prints for its menu (see `menu_line` in the player)."""
    return [f" {e.key}  {e.title}" for e in entries] + [" Q  Quit", "Press a key: "]


def ofs_blocks(size: int) -> int:
    """Blocks an OFS file of `size` bytes takes: its data blocks, one header block,
    and one extension block for every 72 data blocks after the first 72."""
    data = -(-size // OFS_DATA_BYTES)
    return data + 1 + max(0, -(-(data - 72) // 72))


def titles(recipe: Recipe, catalogue: Sequence[survey.Entry]) -> list[str]:
    """Each piece's menu title from MAESTRO's composer and title for its MIDI file."""
    folder = Path(recipe.catalogue).parent
    by_midi = {e.midi: e for e in catalogue}
    found = []
    for piece in recipe.pieces:
        entry = by_midi.get(Path(piece.midi).relative_to(folder).as_posix())
        if entry is None:
            raise SystemExit(f"{piece.name}: {piece.midi} is not in {recipe.catalogue}")
        found.append(survey.menu_title(entry.composer, entry.title))
    return found


def build_disks(recipe: Recipe, root: Path | None = None) -> list[Path]:
    root = root or project.root()
    data = root / recipe.out / "m68k"
    if not (data / "samples.bin").is_file():
        raise SystemExit(f"no player data in {data}; run `amiga-env piano` first")
    if not recipe.catalogue:
        raise SystemExit("the recipe names no MAESTRO catalogue, so the menu has no titles")
    catalogue = survey.read_catalogue(project.media_dir() / recipe.catalogue)
    entries = menu([(p.name, t) for p, t in zip(recipe.pieces, titles(recipe, catalogue))])
    out = project.build_dir() / "piano"
    out.mkdir(parents=True, exist_ok=True)
    index = out / "index"
    index.write_text(index_text(entries), encoding="ascii")
    scores: list[adf.DiskFile] = [(index, INDEX)]
    scores += [(data / f"{p.name}.score", e.path) for p, e in zip(recipe.pieces, entries)]
    source = root / recipe.player
    images = []
    for log, name in zip((0, 1), DISK_NAMES, strict=True):
        folder = out / ("player-log" if log else "player")
        program = assemble.assemble(source, folder / PROGRAM, [data], {"LOG": log})
        image = adf.make_adf(out / name, [program, *scores], [PROGRAM], LABEL)
        used, free = adf.blocks(image)
        print(
            f"{image}: program {ofs_blocks(program.stat().st_size)} blocks; "
            f"disk {used} used, {free} free"
        )
        images.append(image)
    for line in menu_lines(entries):
        print(line)
    return images
