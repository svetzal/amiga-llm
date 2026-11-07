"""Assemble the 68000 piano player and put it on boot floppies, one per piece.

The player (the recipe's `player` source) is assembled twice from the data
`amiga-env piano` wrote to `<out>/m68k/`: the player Stacey boots, and a
test build (`LOG=1`) that also writes the voice log. Each piece gets a
floppy of each, whose startup-sequence runs `piano <piece name>`; the
player plays BWV 846 when its argument starts with b, else the nocturne.

    build/piano/<piece>.adf        the player
    build/piano/<piece>-log.adf    the test build
"""

from pathlib import Path

from .. import adf, assemble, project
from .build import Recipe

PROGRAM = "piano"
FLOPPY_BYTES = 901_120
OFS_DATA_BYTES = 488  # of each 512-byte block of an OFS file


def disk_names(piece: str) -> tuple[str, str]:
    """The player's floppy and the test build's floppy for a piece."""
    return f"{piece}.adf", f"{piece}-log.adf"


def startup(piece: str) -> list[str]:
    return [f"{PROGRAM} {piece}"]


def ofs_blocks(size: int) -> int:
    """Blocks an OFS file of `size` bytes takes: its data blocks, one header block,
    and one extension block for every 72 data blocks after the first 72."""
    data = -(-size // OFS_DATA_BYTES)
    return data + 1 + max(0, -(-(data - 72) // 72))


def build_disks(recipe: Recipe, root: Path | None = None) -> list[Path]:
    root = root or project.root()
    data = root / recipe.out / "m68k"
    if not (data / "samples.bin").is_file():
        raise SystemExit(f"no player data in {data}; run `amiga-env piano` first")
    out = project.build_dir() / "piano"
    source = root / recipe.player
    builds = {
        False: assemble.assemble(source, out / "player" / PROGRAM, [data], {"LOG": 0}),
        True: assemble.assemble(source, out / "player-log" / PROGRAM, [data], {"LOG": 1}),
    }
    for program in builds.values():
        size = program.stat().st_size
        print(f"{program}: {size} bytes, {ofs_blocks(size)} of the 1756 a floppy has free")
    images = []
    for piece in recipe.pieces:
        for log, name in zip((False, True), disk_names(piece.name), strict=True):
            label = f"EXP004 {piece.name}"[:30]
            images.append(adf.make_adf(out / name, [builds[log]], startup(piece.name), label))
    return images
