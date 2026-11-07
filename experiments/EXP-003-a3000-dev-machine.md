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

### 2026-11-07: the a3000-dev recipe, steps 3 to 6 (Amiberry 8.5.0, macOS)

Stacey chose the tools: AmigaOS 3.2, MUI 3.8, SAS/C 6.50 and Commodore's
Amiga Developer Update 3.1 (NDU 3.1). The procedure is now a recipe,
`systems/a3000-dev.toml`, built by `amiga-env system build a3000-dev`
(`make system`) into `runs/systems/a3000-dev/`. The `a3000-dev` machine in
`amiga.toml` boots it as `DH0:` (`System:`) with the project's `work/`
folder as `Work:`.

What each layer does:

| Layers | What | Where it runs |
| --- | --- | --- |
| 1 to 7 | 3.2: the Workbench floppy, the two A3000 module libraries, the five MMU libraries, the Extras, Classes and Fonts floppies, `Locale/Countries` | host |
| 8 | SAS/C 6.50 into `SYS:SC` from its first five disks | emulated A3000 |
| 9 to 13 | NDU 3.1: `include_h.lha` and `include_i.lha` into `Developer/NDU3.1/Include`, `fd.lha`, `linker_libs.lha`, `autodocs.lha` | host |
| 14 to 16 | MUI 3.8: the `MUI` drawer from `mui38usr.lha` (installers left out), `mui.key` into `S:`, `MUI/Developer` from `mui38dev.lha` into `Developer/MUI` | host |
| 17 | `S:User-Startup`: SAS/C's assigns and path, `INCLUDE:` and `LIB:` with NDU 3.1 and MUI first, MUI's own block | host |

amiga-env adds one block at the end of `S:User-Startup` that runs
`AmigaEnv:boot` when a volume named AmigaEnv is mounted, and does nothing
otherwise. That is how a layer, or `amiga-env exec`, runs a script on the
machine with no person present.

SAS/C cannot be installed on the host. Its disks keep files in SAS's own
compressed `*_files` format, which only its Amiga `decompress` program
unpacks. The Installer was tried first:

- `Installer Install_SASC_6.50 MINUSER NOVICE DEFUSER NOVICE` (Installer
  2.15, 1992) stopped at its welcome dialog ("Set Installation Mode",
  "Proceed With Install") and waited there until the 45 s timeout. Screenshot:
  `runs/exp003/sasc-installer-welcome.png`. Clicking through it with the
  socket's mouse commands would depend on timing and on what NOVICE picks.
- `systems/a3000-dev/install-sasc` makes the Installer script's calls
  itself: every `MakeDir` and `decompress` of its hard-disk branch, in the
  same order (derived mechanically from `Install_SASC_6.50` on disk 1). It
  installs the C compiler and headers, optimizers, assembler, debugger,
  extra utilities, examples and source, and the standard, IEEE and 68881
  libraries. It leaves out C++, the cross debugger, the extras, and the
  on-line help (which would put a 1993 `amigaguide.library` over the 3.2
  one). It ends by checking `Version SC:c/sc` (SAS/C_Driver 6.50,
  07/08/1994) and `SC:c/slink` (6.50, 08/26/1993).
- The six disks mount at once, each as a host folder under its own volume
  name (`SASC_6.50_Disk_1:` to `_6:`), so the script never asks for a disk.
  Disk 6 is used only by the floppy install and is not mounted. The plain
  disk 1 was enough; the `[a]` alternate was not needed.
- 868 files were decompressed, and `SC/` holds 868 files.

Running a script on the machine. The first version ran it with `Execute`
in the boot shell under `FailAt 21`. A failing command then did not stop
the script; with `FailAt 10` it stopped the script and the boot shell too,
so the done marker was never written (a test script with a failing `Copy`
timed out). The script now runs through ARexx: `boot` starts `RexxMast`,
and `run.rexx` runs `address command 'Execute AmigaEnv:script'`, which
gets a shell of its own, then writes the return code to `AmigaEnv:done`.
The same failing script now ends with return code 20 after 6.2 s.

Verified, headless (SDL's dummy video and audio drivers), through the
control socket:

- Boot: Workbench 3.2 with `System`, `Work` and `AmigaEnv` volumes
  (`runs/exp003/probe.png`).
- C: `work/hello/test.amigados` runs `sc LINK hello.c` in `Work:hello`,
  runs the program, and the host reads `work/hello/output.txt`: "Hello from
  SAS/C 6.50 on the A3000". `Search INCLUDE:exec/types.h` finds "Includes
  Release 40.15", the NDU 3.1 headers (SAS/C's own say 40.13).
- MUI: `work/muihello/test.amigados` compiles `muihello.c` with SAS/C
  against the NDU 3.1 and MUI 3.8 includes and starts it. Its output says
  "window open: yes", and `runs/exp003/muihello.png` shows a window titled
  "Hello from MUI" with the text "Hello from SAS/C 6.50 and MUI 3.8" and a
  Quit button on the 3.2 Workbench. No MUI registration nag showed.
  Whether MUI reads the keyfile as registered was not checked.

Timings (Apple silicon Mac):

| Step | Time |
| --- | --- |
| Full build from nothing | 57 to 58 s, of which the SAS/C layer is about 56 s |
| Rebuild with nothing changed | under 1 s |
| Rebuild after adding layers after SAS/C | under 1 s (only the new layers) |
| `exec` of the C hello (boot, compile, link, run, quit) | 6.2 s |
| `exec` of the MUI hello (includes a 6 s wait for the window) | 16.3 s |

Reproducibility (step 6). Two builds with `--force` from the same media
gave the same 2,297 files with the same SHA-256 each
(`runs/systems/a3000-dev.build/tree.txt`, both listings
`1ff6c131...e46666d`). A run of the C hello afterwards left the tree's
listing unchanged. What varies between builds is file dates: every host
file has the time it was written, and the Amiga shows that date. Amiberry
wrote no `_UAEFSDB.___` files.

Refuted or not, so far: the hypothesis holds for steps 1 to 6 with one
change. One part of the system (SAS/C) has to be installed on the
emulated machine, by a script, not on the host. Nothing needed a person.

Still open:

- Protection bits are not kept. Every file shows `----rwed`; the `p` and
  `s` bits on the floppies (recorded in xdftool's `.xdfmeta`) are gone. The
  3.2 startup-sequence still works (`Resident ... PURE`), and scripts are
  run with `Execute`. Writing them into `_UAEFSDB.___` files is the likely
  fix; not tried.
- File dates are build times, not the floppies' dates.
- Not done from the 3.2 Installer: Storage, the Locale-EN catalogs and help
  (`.Z`-compressed), `MMU-Configuration` in ENVARC:, Prefs presets, the HD
  startup-sequence (the system boots the floppy's).
- Step 7 (an HDF for the real A3000) is not started. The tree holds
  `S:mui.key`, which must not leave Stacey's machines.
