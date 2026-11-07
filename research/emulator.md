# Amiberry as the machine-level emulator

Amiberry (BlitterStudio, a WinUAE-derived emulator) is the whole-machine
emulator for this project. This note records what is verified about it and
what is still a hypothesis.

## Installation (verified 2026-11-07)

`make tools` asks the GitHub API for the latest release of
`BlitterStudio/amiberry`, downloads the asset for this host, and checks it
against the release's `SHA256SUMS` before unpacking. Each version gets its own
directory under `.tools/amiberry/`; `.tools/amiberry/current` links to the one
in use. `amiga-env amiberry --tag vX.Y.Z` installs a specific release, which
is how to roll back.

| Host | Asset |
| --- | --- |
| macOS (Apple silicon or Intel) | `Amiberry-<v>-macOS-universal.dmg` |
| Linux x86_64 (mojility-ops-01) | `Amiberry-<v>-x86_64.AppImage` |
| Linux aarch64 | `Amiberry-<v>-aarch64.AppImage` |

On 2026-11-07 the latest release was v8.5.0 (published 2026-10-27). The copy
in `/Applications` on the Mac was 8.3.0, and nothing here uses it.

The Linux path is written but not yet run.

## Isolation (verified 2026-11-07 on macOS)

Amiberry reads `~/Library/Application Support/Amiberry/amiberry.conf` on
macOS. On the Mac that global file sets `base_content_path` and `rom_path`
inside the OneDrive "Amiga Retro" folder, so an unmodified run reads ROMs and
writes save states there.

Two ways to stop that were tried:

1. **Portable mode.** Amiberry enters portable mode when an
   `amiberry.portable` marker sits beside its executable, which on macOS is
   `Amiberry.app/Contents/MacOS/`. macOS refuses the write ("Operation not
   permitted") because the bundle is protected, and modifying a signed bundle
   would break its signature in any case. Rejected.
2. **A private HOME.** Running Amiberry with `HOME=<project>/runs/home` moves
   the settings directory, content directory, ROM path, configurations, save
   states and screenshots under the project. `amiga-env run` does this. Before
   each run it sets the path keys in that `amiberry.conf` (`rom_path` is
   `media/rom/`) and keeps the settings Amiberry saved there. Adopted.

`make doctor` runs `amiberry --dump-paths` under the private HOME and fails if
any resolved path is outside the project. The one exception is
`compiled_data_dir`, a compiled-in fallback that the macOS build does not use
because its data directory is inside the bundle.

`AMIBERRY_HOME_DIR` exists in the binary but did not override the global
settings file when tried.

## Driving Amiberry: see the skill

How to boot a machine from the command line, check the resolved
configuration, and drive and observe a run through the control socket is in
the `amiberry` skill (`plugins/amiga-dev/skills/amiberry/SKILL.md`). That is
the one place for reusable Amiberry knowledge. This note keeps the evidence
specific to this repository.

## Booting the baseline A500 (verified 2026-11-07 on macOS)

`amiga-env a500` runs Amiberry's A500 quick-start model with Kickstart 1.2,
Workbench 1.2 in drive 0, and `ntsc=true`. `--dump-config` shows a 68000,
OCS, 512 KB chip plus 512 KB slow RAM, and cycle-exact emulation. It reached
the Workbench 1.2 screen showing "890424 free memory". The Amiga Forever ROM
is encrypted; Amiberry decrypts it with `rom.key` from the same directory.

## Booting the A3000 (verified 2026-11-07 on macOS)

`amiga-env a3000` runs Amiberry's A3000 model with the 3.2 A3000 Kickstart,
`ntsc=true` and `a3000mem_size=8` (the preset has no fast RAM).
`--dump-config` shows a 68030 and 68882, ECS, 2 MB chip and 8 MB motherboard
RAM. With `Workbench3.2.adf` in drive 0 it stayed at the 3.2 insert-disk
screen ("3.2 ROM (Kickstart Version 47.96)") after 45 seconds, so the profile
boots `Install3.2.adf`, which reached a 3.2 Workbench screen.

## Control socket evidence (2026-11-07 on macOS)

- `SCREENSHOT` wrote the screenshots for the A500 hello boot and both A3000
  boots, where macOS `screencapture` failed in the same session.
- `QUIT` ended the hello run cleanly; the log shows `IPC: Received QUIT`.
- `HELP` returned the full command list, now in the skill's
  `references/ipc-commands.md`. Its "prefer MCP/HTTP" heading refers to an
  MCP or HTTP surface that is not in the 8.5.0 macOS binary as far as
  `strings` shows. Not yet investigated.

## Hypotheses to test

These are the questions the first experiments answer. None is established.

- A host directory mounted with `-m` gives the host and the Amiga a shared
  folder that an agent can write a program into and read results back from,
  without driving the GUI.
- The emulated serial port can be bridged to a TCP socket on the host, giving
  a text console the agent can read and write.
- Amiberry can produce screenshots on demand without the window-finding and
  retry logic coco-llm needed for XRoar. (One screenshot taken; see "Control
  socket". Repeatability is still EXP-002's question.)
- The release also ships a libretro core
  (`amiberry-libretro-macOS-arm64.dylib`). A small libretro host could step
  frames, inject keys and read the frame buffer directly. That would make
  observation deterministic. It is a larger build, so it waits until the
  simpler routes above are measured.
- Amiberry runs headless on mojility-ops-01 from the AppImage, so long runs
  can move off the Mac.

## Host folders as volumes, and headless script runs (verified 2026-11-07, Amiberry 8.5.0, macOS)

From EXP-003, the A3000 dev machine:

- **A bootable host folder.** `-s filesystem2=rw,DH0:System:<dir>,0` boots
  Kickstart 3.2 from a host directory holding an unpacked Workbench 3.2
  floppy. The last field is the boot priority; `-128` mounts a folder that
  is not bootable.
- **Many folders at once.** Repeating `-s filesystem2=...` mounts each one.
  Eight at once worked: System, AmigaEnv, and the six SAS/C disks as
  `SASC_6.50_Disk_1:` to `_6:` (a volume name with `.` in it works).
  `Info` lists each with its device name (`DH0`, `DH1`, `AENV`).
- **Attributes.** A host file with no sidecar shows `----rwed` on the
  Amiga. See "Amiga attributes in host folders" below for how to keep `p`,
  `s`, dates and comments.
- **No window.** With `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy`
  Amiberry runs with no window and no sound, and the socket's `SCREENSHOT`
  still writes the emulated display. `amiga-env exec` sets both unless the
  caller's environment chooses drivers.
- **A second emulator gets its own socket.** When `/tmp/amiberry.sock` is
  taken, Amiberry logs "Default socket in use, using instance N" and uses
  another path. With `--log` it prints "IPC: Listening on PATH", so a
  script can find the socket of the emulator it started and leave a
  person's emulator alone. `amiga-env exec` does this, then checks that
  `LIST_HARDDRIVES` reports its own exchange folder before sending
  anything else.
- **`Assign NAME: EXISTS`** returns 5 (WARN) for a name that is not
  mounted, with no requester. The amiga-env hook in `S:User-Startup` uses
  it to do nothing unless the AmigaEnv volume is mounted.
- **A missing assign target asks a person.** `assign add LOCALE: MUI:Locale`
  in MUI's `User-Startup` block opened "Please insert volume LOCALE" when
  `SYS:Locale` did not exist (the 3.2 startup-sequence assigns `LOCALE:` to
  it only then). A headless run then waits until its timeout; take a
  screenshot at the timeout to see why.

## Amiga attributes in host folders (verified 2026-11-07, Amiberry 8.5.0, macOS)

From EXP-003, the A3000 dev machine. Amiberry 8.5.0 keeps what a host file
cannot hold in an FS-UAE sidecar, `NAME.uaem` beside `NAME`, not in
`_UAEFSDB.___` (both strings are in the binary; only `.uaem` was seen):

```text
-s--rw-d 2021-04-13 02:42:22.10 an optional comment
```

- The flags are `hsparwed`, a letter when set and `-` when clear. The date
  is the Amiga's wall clock, with hundredths of a second, and Amiberry
  shows it as written: no time zone is applied.
- Amiberry writes a sidecar when the Amiga sets `s`, `h`, `a` or a comment
  (`Protect +s`, `FileNote`). It does not write one for `Protect +p`: the
  `p` shows until the emulator stops and is gone after the next boot.
  Clearing `w` changes the host mode to read-only instead.
- Sidecars written on the host before boot are read: protection, date and
  comment all show in `List`. A trailing newline is optional.
- A drawer can have one too (`Drawer.uaem`).

amitools 0.9.0 reads and writes the same format (`xdftool IMAGE unpack DIR
fsuae`, and `pack` reads `.uaem` files), but it converts Amiga datestamps
through the host's local time: in summer its sidecars read an hour later
than the Amiga shows, and `pack` drops the 1/50 s ticks. amiga-env writes
sidecars itself (`tools/amiga_env/uaem.py`).

## The 68060 with its FPU and MMU (verified 2026-11-07, Amiberry 8.5.0, macOS)

On the A3000 model, `-s cpu_model=68060 -s fpu_model=68060 -s
mmu_model=68060 -s cpu_24bit_addressing=false -s z3mem_size=256` gives a
68060 with its own FPU and MMU and 256 MB of Zorro III RAM (at 0x40000000 on
the 3.2 A3000 ROM). `cpu_compatible=false` takes effect only with
`cycle_exact`, `cpu_cycle_exact` and `cpu_memory_cycle_exact` all false;
with the preset's cycle-exact on, `--dump-config` showed
`cpu_compatible=true` whatever was set. `--dump-config` also prints a
`cpu_type=68040` line for this configuration; `cpu_model` is the one that
counts (the 3.2 `CPU` command reports a 68060 Rev6).

With MMULibs installed, 3.2's `CPU` showed `68060 68882 68060-MMU ...
(DATA: Cache CopyBack)` and `Superscalar` dispatch; MMULibs' `FPU` showed
`68060`, and `MuScan` printed mmu.library's table with 4 KB pages.

## Booting an RDB hard-disk image (verified 2026-11-07, Amiberry 8.5.0, macOS)

`-s hardfile2=rw,DH0:/abs/path/disk.hdf,0,0,0,512,0,,uaehf0` attaches an RDB
image to UAE's hard-disk controller. With sectors, surfaces and reserved
blocks 0, Amiberry reads the geometry and the partitions from the RDB; the
`DH0` in the setting is not used, and the partitions keep their RDB names.
The log shows each `PART` block and "RDB filesystem 444F5303 (DOS\3)
version 47.4" when the RDB carries a filesystem. An image from `amiga-env
system export` (built with amitools' rdbtool) booted the 3.2 A3000 ROM to
Workbench on the 68060 machine. A host-folder volume (`filesystem2`) can be
mounted beside it; do not give it a device or volume name the RDB uses.

## Recording a run (verified 2026-11-07, Amiberry 8.5.0, macOS)

For EXP-004's video of the piano disk. The reusable facts are in the
`amiberry` skill's `references/recording.md`; this is the evidence.

**The built-in recorder.** Amiberry's input events include
`SPC_VIDEORECORD` and `SPC_VIDEORECORDFILE` (WinUAE's), but in the v8.5.0
source `AVIOUTPUT` is commented out in `src/osdep/sysconfig.h` (line 129),
there is no `avioutput.cpp`, and the record handler in `inputdevice.cpp` is
under `#ifdef AVIOUTPUT`. The bundled libavcodec serves `VIDEOGRAB` (genlock
input). On a running A500, the socket's `SETTINGS_INPUT_EVENTS` did not list
"Audio/Video recording", and binding it replied `ERROR  Unknown input
event: Audio/Video recording`. `HOST_SETTINGS_GET video_dir` names a
`Videos/` folder in the private home; nothing writes there.

**`FRAME_ADVANCE`.** After `PAUSE`, 120 rounds of `FRAME_ADVANCE 1` plus
`SCREENSHOT` took 2.75 s and the player's vertical blank count (its status
block at `$100`) stayed at 1217 throughout; `FRAME_ADVANCE 600` returned in
0.01 s and the count was still 1217. The handler (`HandleFrameAdvance` in
`amiberry_ipc_socket.cpp`) calls `resumepaused(3)` and `setpaused(3)` back
to back and caps the count at 100. Not usable for a capture.

**The libretro core.** `amiga-env amiberry` now installs the release's core
beside the app (`amiberry-libretro-macOS-arm64.dylib`, SHA-256 checked:
`5e8da355...d626c`). `amiga-env piano-video` hosts it with ctypes
(`tools/amiga_env/libretro.py`). Measured on the piano disk:

| Check | Found |
| --- | --- |
| The core's command line, from its debug log | `--model A500 -s sound_frequency=48000 -s sound_filter=emulated -s sound_stereo_separation=10 -s ntsc=true -G -s amiberry.rom_path=... -r <Kickstart 1.2> -s statefile_path=... <disk>` |
| The app's `--dump-config` for that line against the a500 profile's own arguments plus the three sound settings | identical except `use_gui` (and `amiga-env piano-video` repeats this check on every recording) |
| With floppy speed left to the core's v0 list (0, turbo) | the player's preload took 199 vertical blanks and its screen opened at 330; the app: 504 and 788 |
| With floppy speed 100 | screen at 789 (the app: 788) |
| Frame | 752x486 XRGB8888; the screen at (60, 48), each lowres pixel exactly 2x2 (rows and columns compared); frames 0 to 133 were 752x484 |
| Samples | 802.325 a frame (fit over frames 1000 to 4487), so 59.8262 frames a second at 48 kHz: the NTSC rate, 3,579,545 / 227.5 / 263 |
| Frames 0 and 1 | no samples; after that every frame gave some |
| Text colours on the piano screen | ivory (238, 221, 187), gold (187, 153, 85): `$EDB` and `$B95` |
| Speed | about 60 frames a second wall clock; the core paces itself |
| Two boots of the same disk | the screen opened 4 frames apart (frames 2951 and about 2947) |

A/V sync, from the 75 s test (`runs/video/test`): the player stamped piece
1's first note in frame 3909 (65.340 s from the first frame); the
recording's sound passed -42 dBFS 8.6 ms after that frame began. A note
written inside a 16.7 ms frame puts the offset of sound against picture
between -8.1 ms and +8.6 ms. The MP4's AAC, decoded, gave the same onset
to 0.1 ms. The ten pieces of the full run narrow this (EXP-004).
