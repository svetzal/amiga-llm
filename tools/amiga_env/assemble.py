"""Assemble 68000 source into an AmigaDOS executable, and into a boot disk.

vasm writes the hunk executable directly (-Fhunkexe), so a one-file program
needs no link step. `-kick1hunks` is required on Kickstart 1.2: without it
vasm stores relocations as HUNK_DREL32 (RELOC32SHORT), a hunk type that only
the 2.0 and later loader reads.
"""

import subprocess
from pathlib import Path

from . import adf, project, toolchain

VASM = "vasmm68k_mot"


def vasm_args(vasm: Path, source: Path, out: Path) -> list[str]:
    return [
        str(vasm),
        "-quiet",
        "-m68000",
        "-Fhunkexe",
        "-kick1hunks",
        "-nosym",
        "-o",
        str(out),
        str(source),
    ]


def outputs(source: Path, build_dir: Path | None = None) -> tuple[Path, Path]:
    """`hello.s` -> `build/hello` and `build/hello.adf`."""
    build_dir = build_dir or project.build_dir()
    return build_dir / source.stem, build_dir / f"{source.stem}.adf"


def assemble(source: Path, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    args = vasm_args(toolchain.binary(VASM), source, out)
    if subprocess.run(args, check=False).returncode != 0:
        raise SystemExit(f"vasm failed on {source}")
    print(f"Wrote {out}")
    return out


def bootdisk(source: Path, build_dir: Path | None = None) -> Path:
    """Assemble `source` and put it on a floppy whose startup-sequence runs it."""
    program, image = outputs(source, build_dir)
    assemble(source, program)
    return adf.make_adf(image, [program], startup=[program.name])
