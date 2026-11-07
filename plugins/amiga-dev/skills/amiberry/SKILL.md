---
name: amiberry
description: Install, isolate, launch, drive and observe the Amiberry Amiga emulator from scripts and agents. Use when booting an emulated Amiga (A500, A1200, A3000 and so on) from the command line, choosing Kickstart ROMs and floppies, checking a configuration before boot, taking screenshots, recording video and sound frame by frame, sending keys or mouse input, reading emulator status, quitting a run cleanly, or keeping Amiberry away from a personal setup. Also use when the user mentions Amiberry, WinUAE-style .uae configurations, amiberry.conf, /tmp/amiberry.sock, Amiga Forever ROMs with rom.key, or wants to test an Amiga program without a person at the keyboard.
---

# Amiberry for agents

Amiberry (BlitterStudio) is a WinUAE-derived Amiga emulator for macOS, Linux
and Windows. With no GUI, a command-line configuration and a control socket,
an agent can boot a machine, run a program, see the screen and stop the
machine.

Facts here were verified with Amiberry 8.5.0 (2026-10-27) on macOS unless
marked otherwise (mouse input, the copper state and recording on
2026-11-07). Check `amiberry --help` and the socket's `HELP` reply when
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
| `READ_MEM <addr> <width>` | `OK  <value>`, the value in decimal; width 4 reads a big-endian long. About 0.09 ms a call on an Apple silicon Mac, so 350 KB read a long at a time takes under 3 s |
| `SET_WARP 1` | Runs as fast as the host can; a cycle-exact A500 did 223 s of emulated time in about 30 s |
| `GET_CONFIG <key>` | `OK  <value>` for some keys (`sound_output`), `ERROR  Unknown option` for others (`sound_frequency`); `--dump-config` shows them all |
| `SEND_KEY <code> <state>` | Presses (`1`) or releases (`0`) a key; the code is the Amiga raw key code in decimal (`64` is space, `2` is the 2 key, `49` is Z, `68` is Return). Send both states, a tenth of a second apart. Works with warp on (Amiberry 8.5.0, A500 on Kickstart 1.2, read by a program from a console in raw mode) |
| `READ_MEM <addr> 2` | `OK  <value>`, a big-endian word (verified for words in a program's own structures) |
| `SEND_MOUSE <dx> <dy> <buttons>` | Moves the Amiga's mouse by counts, not pixels: on an A500 with Kickstart 1.2 and `GET_MOUSE_SPEED` 100, 50 counts moved Intuition's pointer 12 lowres pixels. `buttons` 1 presses the left button, 0 releases it; Intuition delivered `MOUSEBUTTONS` `SELECTDOWN` at the pointer. Works with warp on. To hit a point, read where the pointer is (a program's window keeps it in `wd_MouseX` and `wd_MouseY`, offsets 14 and 12) and move again until it is there |
| `SEND_MOUSE_ABS <x> <y> <buttons>` | `ERROR  Absolute mouse input rejected (check coordinates, focus, and active tablet_mode)` with the A500 model's defaults; not pursued |
| `GET_COPPER_STATE` | `OK  COP1LC=00000420  COP2LC=0006C810  enabled=1`; read the list at `COP2LC` with `READ_MEM` (WAIT when the first word is odd) to check what a program's copper list does |
| `GET_CPU_REGS` | `OK  D0=...  A7=...  PC=...  SR=...  USP=...  ISP=...` in hex. Sampled a few times, with the program's load address known (have it write `lea start(pc)` somewhere the host reads), the PC says where a program is stuck |

`SCREENSHOT` captures one emulated frame as the beam drew it: a program that
draws while the beam passes shows half-drawn graphics in some screenshots,
which makes many screenshots a cheap check for flicker. With the default
window an NTSC A500's 320x200 lowres screen is at (60, 48) in the 752x486
PNG, each pixel 2x2 (Amiberry 8.5.0, macOS).

The list also has `WRITE_MEM`, floppy changes (`INSERTFLOPPY`,
`EJECT_FLOPPY`), save states and a debugger
(`DEBUG_STEP`, `DISASSEMBLE`, breakpoints). These are listed
by Amiberry but not yet verified here. Avoid `CHOOSE_MEDIA`: it opens a
system file dialog and blocks the socket until a person answers it.

A scripted run is: launch in the background with `-G`, wait for the socket,
act, take a screenshot and look at it, then send `QUIT`. Do not kill the
process unless `QUIT` fails.

### Hand results to the host through memory

`MONITOR` passes GDB monitor commands, not the UAE debugger's, so it cannot
dump memory to a file. A program can leave a status block at a fixed
address (the unused 68000 vectors from `$100` work on any Amiga) holding a
magic word, a state and the address of a buffer; the host polls it with
`READ_MEM` and then reads the buffer.

### Record what Amiberry plays

Amiberry has no command for sound recording, but its SDL 3 has the disk
audio driver. Launch it with:

```sh
SDL_AUDIODRIVER=disk SDL_AUDIO_DISK_OUTPUT_FILE=/abs/out.raw amiberry ...
```

The log says `Writing to file [...], format=S16LE channels=2 freq=44100`:
raw signed 16-bit little-endian stereo, which needs only a WAV header. The
driver plays in real time, so the run takes as long as the music; do not
use warp. The A500 model's defaults are `sound_stereo_separation=7` (a real
Amiga is 10, full separation), `sound_filter=emulated`,
`sound_filter_type=standard` and `sound_interpol=anti`; pass `-s
sound_stereo_separation=10` for the real machine's stereo.

### Record a video, frame by frame

Amiberry 8.5.0's audio/video recorder is not compiled in, and the socket's
`FRAME_ADVANCE` replies `OK` but runs no frame. The release's libretro core
records exactly: each `retro_run()` gives one emulated frame (752x486
XRGB8888 for an NTSC A500, the screen at (60, 48), 2x2) and the samples
made in it, at 59.826 frames a second (NTSC). Give it every option
yourself; its v0 list puts floppy speed 0 (turbo) first. Details, and how
to check that its machine is the app's, are in `references/recording.md`.

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
- **`FRAME_ADVANCE` does nothing.** It needs `PAUSE` first and then replies
  `OK  n frame(s) advanced`, but no frame runs (see
  `references/recording.md`). Step frames with the libretro core instead.

## Keep this skill current

When you verify a new Amiberry behaviour, add it here with the version and
host, and move it out of "not yet verified". When a release changes a
behaviour, update the fact rather than adding a second one.
