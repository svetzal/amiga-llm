"""The baseline machine: Stacey's Amiga 500, as Amiberry arguments.

AGENTS.md records the machine. Amiberry's A500 quick-start model already
matches the facts not yet read off it (68000, OCS, 512 KB chip plus 512 KB
slow RAM, cycle-exact), so the profile adds only what is known: Kickstart 1.2,
Workbench 1.2 in drive 0, NTSC.
"""

from pathlib import Path

from . import MEDIA_DIR

KICKSTART = Path("rom/forever/amiga-os-120.rom")
WORKBENCH = Path("adf/1.2/workbench.adf")


def a500_args(disk: Path | None = None, media: Path = MEDIA_DIR) -> list[str]:
    """Arguments that boot the baseline A500 from `disk`, or Workbench 1.2."""
    return [
        "--model",
        "A500",
        "-r",
        str(media / KICKSTART),
        "-0",
        str(disk or media / WORKBENCH),
        "-s",
        "ntsc=true",
    ]
