"""Stacey's two target machines, as Amiberry arguments.

AGENTS.md records both machines. Each profile starts from Amiberry's
quick-start model and sets only what differs on the real machine.

- a500: demos, games and code that drives the hardware directly, and the
  performance contract. Amiberry's A500 model already matches the facts not
  yet read off it (68000, OCS, 512 KB chip plus 512 KB slow RAM,
  cycle-exact).
- a3000: desktop applications (C, MUI). Amiberry's A3000 model has no fast
  RAM; the real machine has 8 MB on the motherboard, per the configuration
  Stacey kept for it (media/reference/stock-a3000.uae).
"""

from dataclasses import dataclass
from pathlib import Path

from . import MEDIA_DIR


@dataclass(frozen=True)
class Machine:
    model: str
    kickstart: Path
    disk: Path
    settings: tuple[str, ...]
    purpose: str


MACHINES = {
    "a500": Machine(
        model="A500",
        kickstart=Path("rom/forever/amiga-os-120.rom"),
        disk=Path("adf/1.2/workbench.adf"),
        settings=("ntsc=true",),
        purpose="boot the A500 (Kickstart 1.2, Workbench 1.2): demos, games, hardware",
    ),
    "a3000": Machine(
        model="A3000",
        kickstart=Path("rom/3.2/kick-a3000.rom"),
        disk=Path("adf/3.2/Install3.2.adf"),
        settings=("ntsc=true", "a3000mem_size=8"),
        purpose="boot the A3000 (Kickstart 3.2, Workbench 3.2): desktop applications",
    ),
}


def machine_args(name: str, disk: Path | None = None, media: Path = MEDIA_DIR) -> list[str]:
    """Arguments that boot machine `name` from `disk`, or its Workbench floppy."""
    machine = MACHINES[name]
    args = ["--model", machine.model, "-r", str(media / machine.kickstart)]
    args += ["-0", str(disk or media / machine.disk)]
    for setting in machine.settings:
        args += ["-s", setting]
    return args
