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
- **Attributes.** Files in a host folder show `----rwed` on the Amiga. The
  `p` and `s` bits of the original disk are not kept, and Amiberry wrote no
  `_UAEFSDB.___` files during these runs. Commands without `p` still run,
  and `Resident ... PURE` still works.
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
