# Toolchain: candidates, not decisions

coco-llm used three evidence tiers: CPU-level tests in a fast simulator,
machine-level checks in a whole-machine emulator, and physical hardware. This
project keeps the same tiers. Only the machine-level tier (Amiberry) is
decided. The rest are candidates to evaluate in experiments.

## Cross-compilation

| Candidate | What it is | Notes |
| --- | --- | --- |
| vasm + vlink | 68k assembler and linker by Volker Barthelmann and Frank Wille | Small C sources, builds anywhere; pin a release and build into `.tools/` |
| vbcc | ISO C compiler with an AmigaOS target, same authors | Pairs with vasm and vlink; needs the NDK includes |
| amiga-gcc (bebbo) | GCC 6 cross toolchain for m68k-amigaos | Better optimiser, heavy build; a Docker image exists |

The NDK 3.2 (includes, autodocs, FD files) is in `media/ndk/3.2/` after
`make media`.

## CPU-level and OS-level tests without the whole machine

| Candidate | What it is |
| --- | --- |
| vamos (amitools) | Runs AmigaOS 68k CLI programs on the host with an emulated exec and dos. A Python package, so it fits `uv`. If it works for our binaries it is the counterpart of the gorsat/6809 simulator: fast, scriptable, no Kickstart needed. |
| Musashi or Moira | 68000-family CPU cores, for pure-arithmetic kernels with no OS calls |

amitools also provides `xdftool`, which creates and edits ADF and HDF images
from the host. That may be how the environment builds bootable disks
reproducibly instead of keeping hand-made hard-drive images.

## Physical hardware

Stacey's Amiga 3000 (with a Z3660 accelerator, PiStorm and BlueSCSI material
in the origin collection) is the likely physical authority. Which machine is
the performance contract is an open decision, recorded in `README.md`.
