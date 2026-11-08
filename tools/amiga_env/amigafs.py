"""Gateway to amitools for Amiga filesystems: unpack a disk to a host folder
with a `.uaem` sidecar per entry, and pack a host folder into a partition.

Attributes go through uaem.py, not amitools' own `.uaem` code, which
shifts dates by the host's daylight-saving hour and drops sub-second ticks
when packing.
"""

from pathlib import Path

from amitools.fs.ADFSVolume import ADFSVolume
from amitools.fs.blkdev.BlkDevFactory import BlkDevFactory
from amitools.fs.DosType import DOS3
from amitools.fs.FSString import FSString
from amitools.fs.MetaInfo import MetaInfo
from amitools.fs.TimeStamp import TimeStamp

from . import uaem

SIDECAR = ".uaem"


def sidecar(path: Path) -> Path:
    return path.with_name(path.name + SIDECAR)


def unpack_adf(adf: Path, dest: Path) -> str:
    """Write the files of an ADF into dest, which must not exist; return its label."""
    blkdev = BlkDevFactory().open(str(adf), read_only=True)
    try:
        volume = ADFSVolume(blkdev)
        volume.open()
        try:
            dest.mkdir()
            _unpack_dir(volume.get_root_dir(), dest)
            return volume.get_volume_name().get_unicode()
        finally:
            volume.close()
    finally:
        blkdev.close()


def format_partition(
    image: Path, partition: str, label: str, tree: Path | None, dos_type: int = DOS3
) -> None:
    """Format one partition of an RDB image FFS (DOS3 unless told), then pack tree
    into it."""
    blkdev = BlkDevFactory().open(str(image), options={"part": partition})
    try:
        volume = ADFSVolume(blkdev)
        volume.create(FSString(label), dos_type=dos_type)
        if tree is not None:
            _pack_dir(tree, volume.get_root_dir())
        volume.close()
    finally:
        blkdev.close()


def _unpack_dir(node, path: Path) -> None:
    for entry in node.get_entries():
        target = path / entry.name.get_unicode_name()
        sidecar(target).write_text(uaem.format_line(_attributes(entry.meta_info)))
        if entry.is_dir():
            target.mkdir()
            _unpack_dir(entry, target)
        else:
            target.write_bytes(entry.get_file_data())


def _pack_dir(path: Path, node) -> None:
    for entry in sorted(path.iterdir()):
        if entry.name.lower().endswith(SIDECAR):
            continue
        meta = _meta_info(sidecar(entry))
        name = FSString(entry.name)
        if entry.is_dir():
            child = node.create_dir(name, meta, False)
            _pack_dir(entry, child)
        else:
            child = node.create_file(name, entry.read_bytes(), meta, False)
        child.flush()


def _attributes(meta) -> uaem.Attributes:
    stamp = meta.get_mod_ts()
    comment = meta.get_comment()
    return uaem.Attributes(
        protect=uaem.protect_text(meta.get_protect()),
        days=stamp.days,
        minutes=stamp.mins,
        ticks=stamp.ticks,
        comment=comment.get_unicode() if comment is not None else "",
    )


def _meta_info(found: Path) -> MetaInfo | None:
    if not found.is_file():
        return None
    attrs = uaem.parse_line(found.read_text())
    return MetaInfo(
        uaem.protect_mask(attrs.protect),
        TimeStamp(attrs.days, attrs.minutes, attrs.ticks),
        FSString(attrs.comment) if attrs.comment else None,
    )
