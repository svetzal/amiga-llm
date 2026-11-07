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

### 2026-11-07: the Installer's install, attributes, a 68060 machine and an HDF (Amiberry 8.5.0, macOS)

Goal set by Stacey: make the 3.2 installation correct for her real A3000,
which runs a Z3660 accelerator (68060 at 50 MHz) on the same 3.2 A3000
Kickstart. The reference is a read-only export of her real Workbench
partition (`wb.hdf`, FFS DOS3) and the whole RDB image it came from. Neither
is in the repository.

#### Where the 3.2 Installer gets each piece

The recipe's OS layers now follow `Install3.2:Install/Install`, the
hard-disk branch ("FULL INSTALL"), in its order, then its "Install CPU
Support Libraries" branch, each read from the script:

| Installer step | From | To | Layer |
| --- | --- | --- | --- |
| make some new drawers | (makedir list) | Prefs, Locale, Classes, Devs, Storage drawers | `dirs` |
| needed stuff from the Install disk | `HDTools/(hd\|bru)#?`, `Installer`, `Libs/workbench.library`, `Libs/icon.library` | `Tools`, `System`, `Libs` | `copy` |
| copy the Workbench disk | Workbench3.2, all but `Locale` and `Disk.info` | root | `unpack` |
| copy the DiskDoctor disk | `C/DAControl`, `C/DiskDoctor`, `Devs/trackfile.device` | same | `copy` (new medium) |
| DOLOCALE | `Locale:Countries`; Locale-EN `Catalogs/english/Sys`, `Help/english/Sys` (UNCOMPRESS) | `Locale/...` | `copy`, `decompress` |
| copy the Extras disk | all but `Disk.info`; `S/User-startup` only if none | root | `unpack` |
| copy the Classes disk | all but `Disk.info` | root | `unpack` |
| copy the Fonts disk | all but `Disk.info` | `Fonts` | `unpack` |
| Storage disk | the five drawer icons, `Classes/DataTypes`, `C`, `DefIcons/#?.info`, `Presets/Pointers`, `Monitors`, `DOSDrivers`, `WBStartup`, `Env-Archive/deficons.prefs`, `Env-Archive/Pointer.prefs` | `Storage`, `Classes`, `C`, `Prefs/Env-Archive(/Sys)`, `Prefs/Presets`, `WBStartup` | `copy` |
| printer and keymap "schtick" | every driver and keymap (the default below expert level) | `Devs/Printers`, `Devs/Keymaps` | same `copy` |
| copy old intuition V40 | Storage `LIBS` | `Libs` | same `copy` |
| copy Backdrops | Backdrops3.2, all but `Disk.info` | `Prefs/Presets/Backdrops` | `unpack` (new medium) |
| Modules disk | only when the ROM's expansion.library is below V47 | not used: the 3.2 ROM's is V47 | none |
| defaults for HD-User | `Update/disk.info`, `Update/Startup-HardDrive`, `Update/Release` | root, `S/Startup-Sequence`, `Prefs/Env-Archive/Versions` | `copy` |
| reorganise, 60 Hz | `Storage/Monitors/NTSC` moved | `Devs/Monitors/NTSC` | `copy` with `exclude` |
| UpdateWBFiles, IconPos | Install `C/` | run on the machine | `amiga` layer `finish-install` |
| CPU support libraries (manufacturer "Other") | MMULibs all but `Configs` and `Locale`; `Locale/Help/MMULib` (UNCOMPRESS); `Configs/MMU-Configuration` | root (`C`, `Libs`, `Libs/MMU`), `MuTools`, `Prefs/Env-Archive` | `dirs`, `unpack`, `copy` |

ENVARC: is `SYS:Prefs/Env-Archive`, so MMU-Configuration lands in ENVARC:.
The CPU libraries go in before the first boot: the HD startup-sequence's
CPU CHECKINSTALL stops at an `ASK` without them.

The `.Z` files are Unix `compress` (LZW, magic `1F 9D`). The Installer's
`(copyfiles ... (compression) (newname NAME))` writes them decompressed
without the suffix. Evidence: her `Workbench.guide` is byte-identical to
`uncompress` of `Workbench.guide.Z` from Locale-EN.adf.
`tools/amiga_env/compress.py` decodes them; it matched `uncompress` on all
227 `.Z` files on the 3.2 floppies, and on 90 KB streams with 9, 12 and 16
bit codes, two of which hold CLEAR codes.

The FastFileSystem in her RDB (`rdbtool fsget`) is byte-identical to
`L/FastFileSystem` on Install3.2, Extras3.2 and HDSetup3.2 (`$VER: fs 47.4
(16.6.2020)`, 30,532 bytes).

Result against her disk (unpacked read-only into the session scratchpad):
the 3.2 part of the built tree has no file hers lacks. Of 844 files in
both, the only content differences are S:User-Startup and 23 icons that
IconPos or she has changed since. The CPU libraries, MMU-Configuration and
the startup-sequence are identical.

Machine steps. `finish-install` runs `UpdateWBFiles` with NEWWB: assigned
(it returns 20 on a new system; the Installer ignores its return code),
the Installer's IconPos calls, and `Copy Devs.info Storage.info`. The
Installer itself cannot run these headless: a one-line `makedir` script
under `Installer ... MINUSER EXPERT DEFUSER EXPERT NOPRETEND NOLOG` still
stopped at the welcome dialog (`runs/exec/a3000-dev/timeout.png` at the
time).

#### Protection bits, dates and comments (step 2)

Amiberry 8.5.0 keeps Amiga attributes in FS-UAE `.uaem` sidecar files, not
`_UAEFSDB.___` (the binary has both strings; only `.uaem` was written). A
probe on the AmigaEnv: host folder:

- `Protect +s` and `FileNote` each wrote `NAME.uaem`, one line:
  `-s--rwed 2026-11-07 09:34:48.70` and `----rwed ... a comment`. The flags
  are `hsparwed` with `-` for a clear flag; the date is the Amiga's wall
  clock with hundredths.
- `Protect +p` showed `--p-rwed` but wrote no sidecar, and after a reboot
  the file showed `----rwed`: a `p` set on the Amiga is lost. `Protect -wd`
  became host mode `r--r--r--` and read back as `----r-ed`.
- Sidecars written on the host are read at boot: `--p-rwed`, `-s--rw-d`
  with a comment, and a date of 13-Apr-21 03:43:13 all showed in `List`,
  with or without a trailing newline.

So the build writes a sidecar for every file and drawer it takes from a
floppy, and every copy takes the sidecar along under the file's new name
(`.Z` files included). A file from an archive has none, so it gets the
defaults. amitools 0.9.0 can unpack to sidecars itself (`unpack DIR
fsuae`), but it converts datestamps through the host's local time: the
floppy's C:Assign is days 15808, minute 163, tick 684 (02:43:13.68), which
amitools writes as 03:43:13 in summer, and packing drops the ticks.
`tools/amiga_env/uaem.py` converts with naive dates instead.

Verified inside the emulator with `List` (`runs/exp003/cpucheck-*.txt`):
`C:Assign` shows `--p-rwed 13-Apr-21 02:43:13`, `S:Startup-sequence`
`-s--rw-d 13-Apr-21 02:42:22`. Against her disk, read the same way, 900
files and drawers are in both trees; none differs in protection bits, and
the only files whose dates differ are the 23 icons above and
S:User-Startup.

#### The 68060 machine (step 3)

`a3000-dev-060` in `amiga.toml`: the same system with `cpu_model`,
`fpu_model` and `mmu_model` 68060, `cpu_24bit_addressing=false`,
`z3mem_size=256` (the Z3660's RAM size is not yet read off the board) and
cycle-exact off. With cycle-exact on (the A3000 preset), `--dump-config`
kept `cpu_compatible=true` whatever was asked.

`work/cpucheck/test.amigados` on both machines, headless:

| Check | a3000-dev (68030) | a3000-dev-060 |
| --- | --- | --- |
| CPU CHECKINSTALL | 0 | 0 |
| `CPU` | `68030 68882 68030-MMU ... (DATA: Cache NoBurst)` | `68060 68882 68060-MMU ... (DATA: Cache CopyBack)`, `Rev6 Superscalar Load/StoreBypass StoreBuffer BranchCache` |
| `FPU` (MMULibs) | 68882 | 68060 |
| `MuScan` | 68030 MMU, 1 KB pages, a full memory map | 68060 MMU, 4 KB pages, Zorro III RAM at 0x40000000 CopyBack |
| `Avail` fast | 8 MB | 8 MB plus 256 MB |
| Workbench | `runs/exp003/cpucheck-a3000-dev.png` | `runs/exp003/cpucheck-a3000-dev-060.png` |
| SAS/C hello | "Hello from SAS/C 6.50 on the A3000" (`runs/exp003/hello-a3000-dev.png`) | the same (`runs/exp003/hello-a3000-dev-060.png`) |

`CPU` reports the FPU flags exec sets, which name the 68882 on a 68060 as
well; `FPU` names the 68060's own. Superscalar dispatch and the CopyBack
data cache are what 68060.library switches on, and MuScan's table is the
one mmu.library built, so the libraries are in use, not only present.

#### The HDF export (step 7)

`amiga-env system export a3000-dev OUT.hdf` writes an RDB image shaped like
hers: 32 heads, 63 sectors, RDB in cylinders 0 and 1, DH0 "Workbench"
cylinders 2 to 51 (49 MiB, bootable, priority 0) and DH1 "Work" 52 to 811
(748 MiB), both DOS3, with her partitions' buffers, memory type, transfer
size and mask, and FFS 47.4 from the system's L: in the RDB. Her partitions
are named `Workbench` and `Work` in the RDB; the export names them DH0 and
DH1 and labels the volumes as hers are. Packing uses the sidecars, so the
image holds the floppies' bits and datestamps (ticks included). `S:mui.key`
(the recipe marks it `personal`) is left out unless `--include-personal`.

Verified: `exec --image` booted a copy of the export on `a3000-dev-060`.
Amiberry's log shows the RDB, both partitions and "RDB filesystem
444F5303 (DOS\3) version 47.4". `Info` listed DH0 Workbench 49M and DH1
Work 748M; CPU CHECKINSTALL returned 0; C:Assign and S:Startup-sequence
had their bits and dates; SAS/C compiled and ran hello in RAM:; `List
SYS:S/mui.key` found nothing (`runs/exp003/export-boot-060.png`,
`runs/exp003/export-cpucheck-060.txt`). The image is not yet tried on the
real machine.

#### What the Installer does that the recipe still does not

- `makedir ... (infos)` gives `Prefs/Presets/Backdrops` and
  `Prefs/Presets/Pointers` default drawer icons from icon.library. They are
  missing (her disk has both). The Installer cannot run headless (above).
- It stamps the icons IconPos rewrites with the install time; so does the
  `finish-install` layer. Two `--force` builds gave 3,643 files each, all
  identical except those 16 icons and their sidecars: the dates differ,
  and so do the icon bytes. Which bytes, and why (pointer values that
  icon.library writes into the gadget structure are a likely cause), is
  not yet checked (`runs/exp003/tree-3.txt`, `tree-4.txt`).
- Upgrade-only steps (moving old startup files aside, deleting obsolete
  files, keeping and restoring old icons and prefs, the UPDATE moves) do
  nothing on a new system. The UPDATE moves were checked: no WBStartup
  program also exists in Utilities, System, Tools or Commodities.
- WBPattern reset, LoadModule REMOVE and the reboot apply only when
  installing over the running system.
- S:User-Startup keeps the Extras disk's date after the recipe appends to
  it.

#### What her disk has that the recipe does not (from wb.hdf)

These are for a later Z3660 layer from her collection, or are her own:

- Z3660: `Devs/z3660_scsi.device`; RTG: `Devs/Monitors/Z3660` (and
  PicassoIV, Retina, uaegfx), `Devs/p96-z3660-hdmi`,
  `Devs/Picasso96Settings`, `Libs/Picasso96/` (rtg.library,
  emulation.library, fastlayers.library, z3660.card and four other cards
  and chips), `Libs/Picasso96API.library`, `Prefs/Picasso96Mode`,
  `ENVARC:Picasso96/` (12 settings); audio: `Devs/AHI/z3660ax.audio`,
  `Devs/AudioModes/z3660ax`; network: `Devs/Networks/z3660net.device`
  (and a2065, ppp-ethernet), `T/z3660net.bak`; `Tools/ZTop`.
- Roadshow: 26 commands in C: (AddNetInterface, ping, ftp, ipf, wget and
  so on), `Libs/bsdsocket.library`, `Libs/usergroup.library`,
  `Devs/Internet/`, `Devs/NetInterfaces/`, `Storage/NetInterfaces/` (47
  files), `S/Network-Startup`, the firewall scripts and `S/IPF/` (28),
  `S/PPP-Configurations/`, and five German Roadshow catalogs.
- Other software: `C/lha`, `C/axmp3`, `Prefs/PVS`, the napsa fonts (8).
- Her settings: `ENVARC:Sys/ScreenMode.prefs`, `.backdrop`, the
  Picasso96, AmiTCP and Roadshow blocks in S:User-Startup.
- SAS/C lives in `Work:sc` on hers (`SC: Work:sc`), in `SYS:SC` here.

Still open: the real-hardware boot of an exported image; the Z3660 layer;
the Z3660's fast RAM size.
