---
name: amiberry
description: Install, isolate, launch, drive and observe the Amiberry Amiga emulator from scripts and agents. Use when booting an emulated Amiga (A500, A1200, A3000 and so on) from the command line, choosing Kickstart ROMs and floppies, checking a configuration before boot, taking screenshots, sending keys or mouse input, reading emulator status, quitting a run cleanly, or keeping Amiberry away from a personal setup. Also use when the user mentions Amiberry, WinUAE-style .uae configurations, amiberry.conf, /tmp/amiberry.sock, Amiga Forever ROMs with rom.key, or wants to test an Amiga program without a person at the keyboard.
---

# Amiberry for agents

Amiberry (BlitterStudio) is a WinUAE-derived Amiga emulator for macOS, Linux
and Windows. With no GUI, a command-line configuration and a control socket,
an agent can boot a machine, run a program, see the screen and stop the
machine.

Facts here were verified with Amiberry 8.5.0 (2026-10-27) on macOS unless
marked otherwise. Check `amiberry --help` and the socket's `HELP` reply when
the version differs.

## Install a pinned release

Take releases from the GitHub API (`BlitterStudio/amiberry`) and check each
download against the release's `SHA256SUMS` asset before unpacking.

| Host | Asset |
| --- | --- |
| macOS | `Amiberry-<v>-macOS-universal.dmg`. Mount it, `ditto` the app out, detach. |
| Linux x86_64 or aarch64 | `Amiberry-<v>-<arch>.AppImage` (not yet verified) |

The binary on macOS is `Amiberry.app/Contents/MacOS/Amiberry`. Do not copy
the app with `cp -R`: it breaks the signature. Install each version in its
own directory with a `current` link, so a rollback is one link change.

## Keep it away from the user's own setup

Amiberry reads a global `amiberry.conf` (macOS:
`~/Library/Application Support/Amiberry/`, Linux: `~/.config/amiberry/`).
That file sets `rom_path` and `base_content_path`, so an unmodified run reads
the user's ROMs and writes save states and screenshots into their folders.

- **Works:** run Amiberry with `HOME` set to a private directory, and write
  that directory's `amiberry.conf` with your own `rom_path`,
  `base_content_path`, `saveimage_dir`, `plugins_dir` and
  `floppy_sounds_dir`. Amiberry rewrites the file when settings change, so
  set your keys and keep its other lines rather than replacing the file.
- **Fails on macOS:** portable mode (an `amiberry.portable` file beside the
  binary). The system refuses writes inside the app bundle.
- **Did not work:** `AMIBERRY_HOME_DIR` did not move the global settings
  file.
- **Check it:** `amiberry --dump-paths` under the private `HOME` prints
  every resolved path and exits. Fail if any is outside your directory.
  `compiled_data_dir` is a compiled-in fallback and can be ignored on macOS.

## Boot a stock machine from the command line

Start from a quick-start model, then set only what differs:

```sh
amiberry --model A500 -r <kick.rom> -0 <disk.adf> -s ntsc=true -G
```

| Option | Meaning |
| --- | --- |
| `--model A500` (A1200, A3000, ...) | Quick-start preset: CPU, chipset, memory, compatibility |
| `-r` / `-K` | Main and extended Kickstart ROM |
| `-0` to `-3` | Floppy images in DF0: to DF3: |
| `-s key=value` | Any `.uae` configuration key |
| `-f file.uae` | Load a full configuration |
| `-m VOL:path` | Mount a host directory as an Amiga volume (not yet verified) |
| `-G` | Start emulating with no settings window |
| `-w 0` / `-w -1` | Cycle-exact or maximum CPU speed |
| `--dump-config` | Print the resolved configuration and exit |
| `--dump-paths` | Print resolved paths and exit |

Run the same arguments with `--dump-config` before booting and assert on
`cpu_model`, `chipset`, `chipmem_size` (units of 512 KB), `bogomem_size`
(units of 256 KB), `fastmem_size`, `a3000mem_size` (MB), `ntsc` and
`kickstart_rom_file`. It is cheap and catches a wrong preset before a slow
boot.

Verified recipes:

| Machine | Arguments | Result |
| --- | --- | --- |
| A500, 1 MB, Kickstart 1.2 | `--model A500 -r amiga-os-120.rom -0 <WB 1.2 adf> -s ntsc=true` | 68000, OCS, 512 KB chip plus 512 KB slow, cycle-exact; Workbench 1.2 with "890424 free memory" |
| A3000, Kickstart 3.2 | `--model A3000 -r <3.2 A3000 ROM> -0 Install3.2.adf -s ntsc=true -s a3000mem_size=8` | 68030 and 68882, ECS, 2 MB chip, 8 MB fast; 3.2 Workbench from the Install floppy |
| A3000 with a 68060 | as above plus `cpu_model=68060 fpu_model=68060 mmu_model=68060 cpu_24bit_addressing=false cycle_exact=false cpu_cycle_exact=false cpu_memory_cycle_exact=false cpu_compatible=false z3mem_size=256` (each with `-s`) | 68060 with FPU and MMU, 256 MB Zorro III RAM; `cpu_compatible=false` holds only with cycle-exact off |

The A3000 preset has no fast RAM; add `a3000mem_size` for the motherboard
RAM. The AmigaOS 3.2 `Workbench3.2.adf` does not boot on its own (the machine
stops at the insert-disk screen); `Install3.2.adf` does.

### Hard disks: host folders and RDB images

- `-s filesystem2=rw,DH0:Label:/abs/dir,0` mounts a host folder as a
  volume; the last field is the boot priority (`-128` for not bootable).
- `-s hardfile2=rw,DH0:/abs/disk.hdf,0,0,0,512,0,,uaehf0` attaches an RDB
  image. Zeros for sectors, surfaces and reserved blocks make Amiberry read
  the geometry, partitions and any filesystem from the RDB; the partitions
  keep their RDB names. Kickstart 3.2 booted one to Workbench.
- **Amiga attributes in a host folder** live in FS-UAE sidecars,
  `NAME.uaem` beside `NAME`: one line, `-s--rw-d 2021-04-13 02:42:22.10
  comment`, flags in `hsparwed` order (`-` when clear), the date as the
  Amiga shows it, with no time zone. Write sidecars on the host before boot
  to give files their protection bits, dates and comments. Amiberry writes
  one when the Amiga sets `s`, `h`, `a` or a comment, but not for
  `Protect +p`, which is lost at the next boot.
- amitools (`xdftool unpack DIR fsuae`, `pack`) uses the same sidecars but,
  in 0.9.0, converts dates through the host's time zone (an hour off in
  summer) and drops sub-second ticks when packing.

### ROMs

- `-r` takes a path. In the resolved configuration it shows relative to
  `rom_path`.
- Amiga Forever ROMs are encrypted (they start with `AMIROMTYPE1`). Amiberry
  decrypts them when `rom.key` from the same Amiga Forever installation is in
  the same directory as the ROM.
- Never commit ROMs, disk images or `rom.key`; they are copyrighted.

## Drive and observe a running machine

A running Amiberry listens on the Unix socket `/tmp/amiberry.sock`. A
command is one line of tab-separated fields; the reply is one line of
tab-separated fields starting with `OK` or an error.

`scripts/amiberry_ipc.py` (standard library only) sends one command and
prints the reply fields:

```sh
python3 scripts/amiberry_ipc.py --wait 60 GET_STATUS
python3 scripts/amiberry_ipc.py SCREENSHOT /abs/path/boot.png
python3 scripts/amiberry_ipc.py QUIT
```

Verified commands:

| Command | Reply or effect |
| --- | --- |
| `GET_STATUS` | `OK  Paused=false  Config=...  Floppy0=<path>` |
| `SCREENSHOT <path>` | Writes a PNG of the emulated display to an absolute path |
| `QUIT` | `OK`; the emulator exits and removes the socket file |
| `GET_VERSION` | `OK  version=Amiberry 8.5.0 (2026.10.27)  sdl=SDL 3.4.18` |
| `HELP` | The full command list, in `references/ipc-commands.md` |

The list also has keyboard and mouse input (`SEND_KEY`, `SEND_MOUSE`),
memory access (`READ_MEM`, `WRITE_MEM`), floppy changes (`INSERTFLOPPY`,
`EJECT_FLOPPY`), save states, `FRAME_ADVANCE`, warp mode and a debugger
(`DEBUG_STEP`, `GET_CPU_REGS`, `DISASSEMBLE`, breakpoints). These are listed
by Amiberry but not yet verified here. Avoid `CHOOSE_MEDIA`: it opens a
system file dialog and blocks the socket until a person answers it.

A scripted run is: launch in the background with `-G`, wait for the socket,
act, take a screenshot and look at it, then send `QUIT`. Do not kill the
process unless `QUIT` fails.

## Gotchas

- **A second emulator gets another socket.** When `/tmp/amiberry.sock` is
  taken, Amiberry logs "Default socket in use, using instance N" and
  listens elsewhere; with `--log` it prints "IPC: Listening on PATH". Read
  that line to find your emulator's socket, check that `GET_STATUS` or
  `LIST_HARDDRIVES` names the disk you booted, and never quit an emulator
  you did not start.
- **`ps` is misleading.** Amiberry rewrites its argument strings after
  parsing: a run started with `-s ntsc=true -G` shows `-s ntsc true` and no
  `-G`. Use `GET_STATUS` or `--dump-config` instead.
- **Host screen capture can fail.** macOS `screencapture` failed ("could not
  create image from display") where the socket's `SCREENSHOT` worked. Use
  the socket.
- **A GDB stub exists.** The binary has a WinUAE GDB server on `127.0.0.1`.
  How to enable it is not yet verified.
- **The libretro core.** Releases also ship a libretro core, which a small
  host could step frame by frame. Not yet tried.

## Keep this skill current

When you verify a new Amiberry behaviour, add it here with the version and
host, and move it out of "not yet verified". When a release changes a
behaviour, update the fact rather than adding a second one.
