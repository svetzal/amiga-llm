"""Put the 68000 piano player, its screen and its pieces on one boot floppy.

The player (the recipe's `player` source) is assembled twice from the data
`amiga-env piano` wrote to `<out>/m68k/` and the screen made here
(screen.py): the player Stacey boots, and a test build (`LOG=1`) that also
writes the voice log. The program holds the samples and tables; the
picture, the credits and each piece's score are files, so a piece is added
by rebuilding the disk:

    piano                          the program
    title.ilbm                     the screen: picture, song list, attribution
    Credits                        the full notices (the recipe's `credits`)
    scores/index                   one line a piece: its score's path, a space, its title
    scores/NN-<piece>.score        the score byte stream (see score.py)
    s/startup-sequence             `piano`

    build/piano/piano.adf          the player
    build/piano/piano-log.adf      the test build

Pieces take keys 1 to 9, then the letters without Q (MENU_KEYS); Q and Esc
quit. The player gets Amiga raw key codes, so `keys.i` gives it each
piece's code (RAW_KEYS).
"""

from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from .. import adf, assemble, project
from . import screen as screen_mod
from .build import Recipe

PROGRAM = "piano"
DISK_NAMES = ("piano.adf", "piano-log.adf")
LABEL = "Piano"
INDEX = "scores/index"
PICTURE = "title.ilbm"
CREDITS = "Credits"
MENU_KEYS = "123456789ABCDEFGHIJKLMNOPRSTUVWXYZ"
OFS_DATA_BYTES = 488  # of each 512-byte block of an OFS file
CREDITS_WIDTH = 60  # characters a line: the 1.2 boot CLI window wraps after 61
# Amiga raw key codes (the A500 keyboard's matrix). Each row of letters and
# digits runs on from its first code.
RAW_KEYS = {
    key: first + offset
    for row, first in (
        ("1234567890", 0x01),
        ("QWERTYUIOP", 0x10),
        ("ASDFGHJKL", 0x20),
        ("ZXCVBNM", 0x31),
    )
    for offset, key in enumerate(row)
}


class MenuPiece(NamedTuple):
    key: str  # its key
    path: str  # the score's path on the disk
    title: str  # ASCII


def menu(pieces: Sequence[tuple[str, str]]) -> list[MenuPiece]:
    """Each piece's key, score path and title, in list order, from (name, title) pairs."""
    if len(pieces) > len(MENU_KEYS):
        raise SystemExit(f"the menu has {len(MENU_KEYS)} keys; {len(pieces)} pieces given")
    entries = []
    for number, (key, (name, title)) in enumerate(zip(MENU_KEYS, pieces, strict=False), 1):
        path = f"scores/{number:02d}-{name}.score"
        if not title or not title.isascii() or "\n" in title:
            raise SystemExit(f"{name}: a title is one line of ASCII, not {title!r}")
        adf.disk_path((Path(), path))  # an OFS name, or SystemExit
        entries.append(MenuPiece(key, path, title))
    return entries


def index_text(entries: Sequence[MenuPiece]) -> str:
    """The index file: one line a piece, `<score path> <title>`, LF endings."""
    return "".join(f"{e.path} {e.title}\n" for e in entries)


def keys_include(count: int) -> str:
    """`keys.i`: the raw key code of each piece's key, in list order."""
    codes = ",".join(f"${RAW_KEYS[k]:02x}" for k in MENU_KEYS[:count])
    return f"; keys.i: made by `amiga-env piano-disk` (disk.py); do not edit.\npiece_keys: dc.b {codes}\n"


def check_credits(text: str) -> None:
    """The credits are ASCII, with lines a 1.2 CLI window shows whole; SystemExit if not."""
    if not text.isascii():
        raise SystemExit("the credits are ASCII, for the Amiga's own text")
    long = [line for line in text.splitlines() if len(line) > CREDITS_WIDTH]
    if long:
        raise SystemExit(f"a credits line is over {CREDITS_WIDTH} characters: {long[0]!r}")


def ofs_blocks(size: int) -> int:
    """Blocks an OFS file of `size` bytes takes: its data blocks, one header block,
    and one extension block for every 72 data blocks after the first 72."""
    data = -(-size // OFS_DATA_BYTES)
    return data + 1 + max(0, -(-(data - 72) // 72))


def titles(recipe: Recipe) -> list[str]:
    """Each piece's title from the recipe; SystemExit when one has none."""
    missing = [p.name for p in recipe.pieces if not p.title]
    if missing:
        raise SystemExit(f"{missing[0]}: the recipe gives it no title")
    return [p.title for p in recipe.pieces]


def build_disks(recipe: Recipe, root: Path | None = None) -> list[Path]:
    root = root or project.root()
    data = root / recipe.out / "m68k"
    if not (data / "samples.bin").is_file():
        raise SystemExit(f"no player data in {data}; run `amiga-env piano` first")
    if recipe.screen is None or not recipe.credits:
        raise SystemExit("the recipe needs a [screen] table and `credits`")
    names = titles(recipe)
    entries = menu([(p.name, t) for p, t in zip(recipe.pieces, names, strict=True)])
    out = project.build_dir() / "piano"
    out.mkdir(parents=True, exist_ok=True)
    made = screen_mod.make(names, recipe.screen, root)
    picture = screen_mod.write(made, recipe.screen, root, data, root / recipe.out)
    (data / "keys.i").write_text(keys_include(len(entries)), encoding="ascii")
    credits = root / recipe.credits
    check_credits(credits.read_text(encoding="ascii"))
    index = out / "index"
    index.write_text(index_text(entries), encoding="ascii")
    files: list[adf.DiskFile] = [(picture, PICTURE), (credits, CREDITS), (index, INDEX)]
    files += [(data / f"{p.name}.score", e.path) for p, e in zip(recipe.pieces, entries)]
    source = root / recipe.player
    images = []
    for log, name in zip((0, 1), DISK_NAMES, strict=True):
        folder = out / ("player-log" if log else "player")
        program = assemble.assemble(source, folder / PROGRAM, [data], {"LOG": log})
        image = adf.make_adf(out / name, [program, *files], [PROGRAM], LABEL)
        used, free = adf.blocks(image)
        print(
            f"{image}: program {ofs_blocks(program.stat().st_size)} blocks; "
            f"disk {used} used, {free} free"
        )
        images.append(image)
    print(f"screen: {made.picture_colours} picture colours; {root / recipe.out}/title-preview.png")
    for entry, line in zip(entries, made.layout.pieces, strict=True):
        print(f" {entry.key}  row {line.top:3}  {entry.title}")
    return images
