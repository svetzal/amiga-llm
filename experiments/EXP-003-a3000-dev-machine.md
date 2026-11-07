---
id: EXP-003
gloss: the A3000 dev machine
status: running
---

# EXP-003: Build an A3000 development machine from the host, reproducibly

## Question

Can the tools assemble a complete Amiga development system (AmigaOS 3.2,
MUI, and native compilers, assemblers and editors) for the emulated A3000
from the project's licensed media, with no Installer run by hand, so that
anyone with the same media can rebuild the same machine?

People want an authentic retro development experience: write, compile and
debug on the Amiga itself. Cross-compiling on the host stays the agent's
main loop; this machine is the period environment beside it.

## Hypothesis

The system can live in a host directory that Amiberry mounts as a bootable
`DH0:`. The tools fill that directory by unpacking the 3.2 floppies with
xdftool and adding the files the 3.2 Installer would add, then the archives
for MUI and the native tools. A rebuild from the same media gives the same
tree.

Refuted if 3.2 needs the Installer to produce a working system, or if a
host directory loses something the system needs (protection bits, comments,
links).

## Procedure

1. Unpack `Workbench3.2.adf` into a directory and boot the A3000 profile
   from it as `DH0:` (`filesystem2=rw,DH0:System:<dir>,0`), with no floppy.
2. Add what the boot asks for, one step at a time, and record each.
3. Add the rest of the 3.2 set (Extras, Classes, Fonts, Storage, Locale).
4. Add MUI 3.8 (user archive, keyfile) and its developer files.
5. Add native development tools (to be chosen with Stacey).
6. Rebuild from scratch and compare the trees.
7. Export the tree to an HDF for the real A3000 (BlueSCSI).

## Evidence tier

Machine level (Amiberry). Step 7 reaches physical.

## Results

### 2026-11-07: steps 1 and 2 (Amiberry 8.5.0, macOS)

- Workbench3.2.adf unpacked with xdftool (130 files) and mounted as a
  bootable `DH0:` booted Kickstart 3.2 into its startup-sequence from the
  host directory. `LIST_HARDDRIVES` on the control socket reported
  `unit0=dir:<path>`.
- The boot stopped at two points, each fixed by copying files from another
  3.2 floppy:
  - "Please insert a volume containing LIBS/icon.library": copied
    `icon.library` and `workbench.library` from `ModulesA3000_3.2.adf`
    (`LIBS/`) to `Libs/`.
  - `CPU CHECKINSTALL` reported that the 68030's MMU was not set up: copied
    `mmu.library`, `680x0.library`, `68030.library`, `memory.library` and
    `disassembler.library` from `MMULibs.adf` (`Libs/`) to `Libs/`.
- With both, the machine reached the 3.2 Workbench screen with a `System`
  volume and the RAM disk, about 25 seconds after launch.

Still to check: what else the Installer does (`MMU-Configuration` in
ENVARC:, locale, fonts, Prefs), whether protection bits survive (Amiberry
keeps them in `_UAEFSDB.___` files beside the host files), and the rest of
the procedure.
