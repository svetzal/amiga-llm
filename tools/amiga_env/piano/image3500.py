"""A hard-disk image of the A3500 piano for Stacey's BlueSCSI: it boots Kickstart 2.04
straight into the piano's screen.

The image has a Rigid Disk Block and one bootable partition, DH0, labelled
Piano3500. It is the Fast File System without international mode (DOS1), the
one the A3000's Kickstart 2.04 has in ROM, so the RDB stores no filesystem
and nothing else is needed: no Workbench, no L:FastFileSystem. The partition
holds what the player runs from (run3500.write_files, the player Stacey
boots, not the test build): S/Startup-Sequence (`player`), the player,
piano.tab, samples.bin, title.ilbm, scores/ and Credits with the full
notices. The geometry is export.py's: 32 heads of 63 sectors, the RDB in
cylinders 0 and 1.

The image holds the samples (Salamander, CC BY 3.0) and the scores (MAESTRO,
CC BY-NC-SA 4.0): it goes under build/, and is never committed.
"""

import math
import shutil
import tempfile
from pathlib import Path

from amitools.fs.DosType import DOS1
from amitools.tools import rdbtool

from .. import amigafs, export, project
from . import build3500, run3500

LABEL = "Piano3500"
SPARE_MIB = 2  # free space left on the partition


def cylinders_for(tree_bytes: int, spare_mib: int = SPARE_MIB) -> int:
    """Cylinders for a partition holding `tree_bytes` with room to spare: the files,
    a block of headers per 72 data blocks, and spare_mib more."""
    blocks = math.ceil(tree_bytes / export.BLOCK)
    blocks += math.ceil(blocks / 72) + 64
    needed = blocks * export.BLOCK + spare_mib * export.MIB
    return math.ceil(needed / export.CYLINDER_BYTES)


def rdb_commands(image: Path, partition_cylinders: int) -> list[str]:
    """rdbtool arguments: the RDB and one bootable FFS partition, no filesystem stored."""
    first = export.RDB_CYLINDERS
    last = first + partition_cylinders - 1
    commands = [
        ["create", f"chs={last + 1},{export.HEADS},{export.SECTORS}"],
        ["init", f"rdb_cyls={export.RDB_CYLINDERS}"],
        [
            "add",
            f"start={first}",
            f"end={last}",
            "name=DH0",
            "fs=DOS1",
            "bootable=1",
            "pri=0",
            *export.DOS_ENV,
        ],
    ]
    args = ["-f", "--disk-vendor", "AMIGAENV", str(image)]
    for index, command in enumerate(commands):
        args += (["+"] if index else []) + command
    return args


def tree_bytes(tree: Path) -> int:
    return sum(p.stat().st_size for p in tree.rglob("*") if p.is_file())


def build(recipe_path: Path, image: Path | None = None) -> Path:
    """Write the image (build/piano3500/piano3500.hdf unless told) and return it."""
    recipe = build3500.load_recipe(recipe_path)
    image = image or project.build_dir() / "piano3500" / "piano3500.hdf"
    image.parent.mkdir(parents=True, exist_ok=True)
    piano = build3500.make_piano(recipe)
    with tempfile.TemporaryDirectory(prefix="image-", dir=image.parent) as work:
        tree = Path(work) / LABEL
        run3500.write_files(recipe, piano, tree, "player\n", log=False)
        image.unlink(missing_ok=True)
        if rdbtool.main(rdb_commands(image, cylinders_for(tree_bytes(tree)))) != 0:
            raise SystemExit(f"rdbtool could not write the RDB of {image}")
        amigafs.format_partition(image, "DH0", LABEL, tree, DOS1)
        shutil.copyfile(tree / run3500.CREDITS, image.with_name("Credits"))
    return image


A3000_SCSI = "scsi0_a3000"  # Amiberry's A3000 SCSI controller, which the ROM's scsi.device drives


def hardfile_setting(image: Path, controller: str = A3000_SCSI) -> str:
    """The Amiberry setting that attaches the image to the A3000's own SCSI controller."""
    path = str(image)
    if "," in path:
        raise SystemExit(f"Amiberry cannot attach an image whose path has a comma: {path}")
    return f"hardfile2=rw,DH0:{path},0,0,0,512,0,,{controller}"


def boot(machine, image: Path, out: Path, timeout: float = 120.0) -> dict:
    """Boot the image on `machine` with no window and no floppy, wait for the piano's
    screen, take a screenshot and stop the emulator."""
    import time

    from .. import profile

    out.mkdir(parents=True, exist_ok=True)
    image = image.resolve()
    args = [*profile.base_args(machine), "-s", hardfile_setting(image)]
    amiga = run3500.Machine(args, out / "image-boot.amiberry.log")
    began = time.monotonic()
    try:
        amiga.connect(image, timeout=60)
        while True:
            status = amiga.status()
            if status.magic == run3500.MAGIC and status.state == 3:
                break
            if status.magic == run3500.MAGIC and status.state == run3500.FAILED:
                raise SystemExit(f"the player failed on the image: {status}")
            if time.monotonic() - began > timeout:
                raise SystemExit(f"no piano screen within {timeout:g} s: {status}")
            time.sleep(0.5)
        shot = out / "image-boot.png"
        amiga._emulator.send("SCREENSHOT", str(shot))
    finally:
        amiga.stop()
    hz = status.vblank_hz or 60
    return {
        "controller": A3000_SCSI,
        "wall_s_to_screen": round(time.monotonic() - began, 1),
        "samples_loaded_s": round(status.loaded_at / hz, 2),
        "screen_up_s": round(status.screen_at / hz, 2),
        "screenshot": str(shot),
    }
