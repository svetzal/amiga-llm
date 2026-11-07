"""Export a built system as a hard-disk image for a real Amiga.

`amiga-env system export NAME OUT.hdf` writes an RDB image: a Rigid Disk
Block holding the Fast File System, a bootable partition DH0 holding the
system tree, and an empty partition DH1 named Work, both FFS (DOS3). The
files keep their Amiga attributes: each is packed with the protection
bits, date and comment in its `.uaem` sidecar (see system.py, amigafs.py).

The filesystem stored in the RDB is the system's own `L:FastFileSystem`,
the one HDToolBox would add from L:. Paths a recipe marks `personal` (a
keyfile, say) are left out unless the caller asks for them, so an image is
safe to hand to another machine of one's own; it is still licensed media,
and never committed or published.

The geometry is 32 heads of 63 sectors (2016 blocks, 1,032,192 bytes, a
cylinder), as HDToolBox and many SCSI emulators present a disk, with the
RDB in cylinders 0 and 1 and the partitions after it.
"""

import math
import os
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from amitools.tools import rdbtool

from . import amigafs, recipe, system

HEADS = 32
SECTORS = 63
BLOCK = 512
CYLINDER_BYTES = HEADS * SECTORS * BLOCK
RDB_CYLINDERS = 2
MIB = 1024 * 1024
FILESYSTEM = "L/FastFileSystem"
SYSTEM_LABEL = "Workbench"
WORK_LABEL = "Work"
# The partition settings of the A3000 image this export copies: buffers,
# memory type, the largest transfer and the DMA address mask.
DOS_ENV = ("num_buffer=30", "buf_mem_type=1", "max_transfer=0xffffff", "mask=0x7ffffffe")


@dataclass(frozen=True)
class Layout:
    cylinders: int
    system: tuple[int, int]
    work: tuple[int, int]


def layout(system_mib: int, work_mib: int) -> Layout:
    """Cylinder ranges for partitions of at least the given sizes."""
    if system_mib < 1 or work_mib < 1:
        raise SystemExit("partition sizes are whole MiB, at least 1")
    system_cyls = math.ceil(system_mib * MIB / CYLINDER_BYTES)
    work_cyls = math.ceil(work_mib * MIB / CYLINDER_BYTES)
    first = RDB_CYLINDERS
    system = (first, first + system_cyls - 1)
    work = (system[1] + 1, system[1] + work_cyls)
    return Layout(work[1] + 1, system, work)


def left_out(personal: Iterable[str], include_personal: bool) -> set[str]:
    """Lower-case paths in the system an export leaves out."""
    return set() if include_personal else {p.lower() for p in personal}


def rdb_commands(image: Path, plan: Layout, filesystem: Path) -> list[str]:
    """rdbtool arguments that write the RDB, both partitions and the filesystem."""
    (s_lo, s_hi), (w_lo, w_hi) = plan.system, plan.work
    commands = [
        ["create", f"chs={plan.cylinders},{HEADS},{SECTORS}"],
        ["init", f"rdb_cyls={RDB_CYLINDERS}"],
        [
            "add",
            f"start={s_lo}",
            f"end={s_hi}",
            "name=DH0",
            "fs=DOS3",
            "bootable=1",
            "pri=0",
            *DOS_ENV,
        ],
        ["add", f"start={w_lo}", f"end={w_hi}", "name=DH1", "fs=DOS3", "bootable=0", *DOS_ENV],
        ["fsadd", str(filesystem), "fs=DOS3"],
    ]
    args = ["-f", "--disk-vendor", "AMIGAENV", str(image)]
    for index, command in enumerate(commands):
        args += (["+"] if index else []) + command
    return args


def export(
    name: str,
    image: Path,
    include_personal: bool = False,
    system_mib: int = 49,
    work_mib: int = 748,
) -> Path:
    """Write the built system NAME to an RDB image; see the module notes."""
    rec = system.load(name)
    tree = system.tree_dir(name)
    if not system.built_layers(name):
        raise SystemExit(f"run `amiga-env system build {name}` first")
    if system.built_layers(name) != system.fingerprints(rec):
        raise SystemExit(f"{name} is not up to date; run `amiga-env system build {name}`")
    filesystem = system.resolve(tree, FILESYSTEM)
    if not filesystem.is_file():
        raise SystemExit(f"{name} has no {FILESYSTEM} to store in the RDB")
    plan = layout(system_mib, work_mib)
    leave_out = left_out(recipe.personal_paths(rec), include_personal)
    image.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="export-", dir=system.build_dir(name)) as work:
        staged = Path(work) / SYSTEM_LABEL
        skipped = stage(tree, staged, leave_out)
        if rdbtool.main(rdb_commands(image, plan, filesystem)) != 0:
            raise SystemExit(f"rdbtool could not write the RDB of {image}")
        amigafs.format_partition(image, "DH0", SYSTEM_LABEL, staged)
        amigafs.format_partition(image, "DH1", WORK_LABEL, None)
    for path in skipped:
        print(f"left out {path} (personal; --include-personal keeps it)")
    print(
        f"exported {name} to {image}: DH0 {SYSTEM_LABEL} cylinders {plan.system[0]}-"
        f"{plan.system[1]}, DH1 {WORK_LABEL} {plan.work[0]}-{plan.work[1]}, FFS from L:"
    )
    return image


def stage(tree: Path, dest: Path, leave_out: set[str]) -> list[str]:
    """Link the tree into dest without the paths left out (and their sidecars).

    Returns the paths left out that were there.
    """
    skipped = []
    for source in sorted(tree.rglob("*")):
        rel = source.relative_to(tree).as_posix()
        owner = rel[: -len(system.SIDECAR)] if system.is_sidecar(rel) else rel
        if owner.lower() in leave_out:
            if owner == rel:
                skipped.append(rel)
            continue
        if source.name in system.IGNORED:
            continue
        target = dest / rel
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source, target)
            except OSError:
                shutil.copyfile(source, target)
    dest.mkdir(parents=True, exist_ok=True)
    return skipped
