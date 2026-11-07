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

Pieces take keys 1 to 9, then the letters without F and Q (MENU_KEYS); Q
and Esc quit, F switches the A500's audio filter, Space stops. The player gets Amiga raw key codes, so `menu.i` gives it each
piece's code (RAW_KEYS), and the recipe's `rotate_s`: the seconds of quiet
after which the player plays the next piece by itself.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from .. import adf, assemble, project
from . import font as font_mod
from . import picture
from . import screen as screen_mod
from .build import Recipe

PROGRAM = "piano"
DISK_NAMES = ("piano.adf", "piano-log.adf")
LABEL = "Piano"
INDEX = "scores/index"
PICTURE = "title.ilbm"
CREDITS = "Credits"
MENU_KEYS = "123456789ABCDEGHIJKLMNOPRSTUVWXYZ"  # not F (the filter) or Q (quit)
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


ROTATE_RANGE_S = (1, 600)


def menu_include(count: int, rotate_s: int) -> str:
    """`menu.i`: the raw key code of each piece's key, in list order, and the
    rotation's gap in seconds; SystemExit for a gap that is not 1 to 600 whole seconds."""
    low, high = ROTATE_RANGE_S
    if type(rotate_s) is not int or not low <= rotate_s <= high:
        raise SystemExit(f"rotate_s is whole seconds from {low} to {high}, not {rotate_s!r}")
    codes = ",".join(f"${RAW_KEYS[k]:02x}" for k in MENU_KEYS[:count])
    return (
        "; menu.i: made by `amiga-env piano-disk` (disk.py); do not edit.\n"
        f"ROTATE_S        equ {rotate_s}\n"
        f"piece_keys: dc.b {codes}\n"
    )


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


def click_points(recipe: Recipe, root: Path | None = None) -> dict[str, tuple[int, int]]:
    """A point on each piece's line of the screen, by piece name: its middle row,
    a little in from the line's left."""
    root = root or project.root()
    if recipe.screen is None:
        raise SystemExit("the recipe has no [screen] table")
    font = font_mod.load(root / recipe.screen.font)
    lines = screen_mod.layout(titles(recipe), recipe.screen, font).pieces
    return {
        p.name: (line.left + 12, line.top + font.height // 2)
        for p, line in zip(recipe.pieces, lines, strict=True)
    }


def scope_regions(recipe: Recipe) -> tuple[tuple, tuple[int, int]]:
    """The scopes (as machine.Scope fields: left, width, trace colour) and the band's
    rows, from the recipe's screen, for checking screenshots."""
    spec = recipe.screen
    if spec is None:
        raise SystemExit("the recipe has no [screen] table")
    from .machine import Scope

    voice = picture.rgb_of(picture.parse_ocs(spec.voice_trace))
    mix = picture.rgb_of(picture.parse_ocs(spec.mix_trace))
    scopes = tuple(Scope(x, spec.voice_scope_width, voice) for x in spec.voice_scopes)
    scopes += (Scope(spec.mix_scope[0], spec.mix_scope[1], mix),)
    return scopes, (spec.scope_band.top, spec.scope_band.bottom)


def build_disks(recipe: Recipe, root: Path | None = None, out: Path | None = None) -> list[Path]:
    """Assemble both builds and write both disks into `out` (build/piano)."""
    root = root or project.root()
    data = root / recipe.out / "m68k"
    if not (data / "samples.bin").is_file():
        raise SystemExit(f"no player data in {data}; run `amiga-env piano` first")
    if recipe.screen is None or not recipe.credits:
        raise SystemExit("the recipe needs a [screen] table and `credits`")
    names = titles(recipe)
    entries = menu([(p.name, t) for p, t in zip(recipe.pieces, names, strict=True)])
    out = out or project.build_dir() / "piano"
    out.mkdir(parents=True, exist_ok=True)
    made = screen_mod.make(names, recipe.screen, root)
    picture = screen_mod.write(made, recipe.screen, root, data, root / recipe.out)
    (data / "menu.i").write_text(menu_include(len(entries), recipe.rotate_s), encoding="ascii")
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
