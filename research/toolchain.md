# Toolchain

coco-llm used three evidence tiers: CPU-level tests in a fast simulator,
machine-level checks in a whole-machine emulator, and physical hardware. This
project keeps the same tiers. The machine-level tier (Amiberry) and the
assemble-to-boot-disk loop are decided. The rest are candidates.

## Decided: vasm, xdftool, Amiberry (verified 2026-11-07 on macOS)

One command assembles a program and writes a floppy that runs it at boot;
another boots the baseline A500 on it:

```sh
make toolchain                          # once: build vasm and vlink into .tools/
make hello                              # = amiga-env bootdisk examples/hello/hello.s
uv run amiga-env a500 build/hello.adf   # boot it
```

The pieces can be used apart:

```sh
uv run amiga-env asm prog.s -o build/prog
uv run amiga-env adf build/disk.adf build/prog data.bin --startup prog
```

### vasm and vlink

| Tool | Version | Archive | SHA-256 |
| --- | --- | --- | --- |
| vasm (m68k, Motorola syntax) | 2.0f | `vasm2_0f.tar.gz` | `c84b2de1cbb87831795fe64a85c5d9a7002a766e3a7c30b0a2d7d5e99d878f49` |
| vlink | 0.18a | `vlink0_18a.tar.gz` | `8d151cdd30a4feb575a364e68810c2bc300fe1a7c074dbbee6fd1175a6c5bfae` |

Both were the newest versioned archives in `http://phoenix.owl.de/tags/` on
2026-11-07. The version and checksum are pinned in
`tools/amiga_env/toolchain.py`; `make doctor` says when the listing has a
newer one.

What the pin can and cannot prove. The authors serve these files over plain
HTTP only (port 443 is refused on both `phoenix.owl.de` and
`sun.hasenbraten.de`) and publish no checksums. The pin is therefore trust on
first use: it guarantees every later build uses the same bytes as the first,
not that the first download was genuine. One cross-check was available: the
unversioned `vlink.tar.gz` on the same server had the same SHA-256 as
`vlink0_18a.tar.gz`.

`amiga-env toolchain` checks the SHA-256 before unpacking, refuses an archive
with members outside its `vasm/` or `vlink/` directory, extracts into a fresh
empty directory with Python's `data` tar filter (no links out, no device
files, no absolute paths), and runs only the archive's own Makefile:
`make CC=cc CPU=m68k SYNTAX=mot` for vasm and `make CC=cc` for vlink. The
products (`vasmm68k_mot`, `vobjdump`, `vlink`) are copied into
`.tools/<tool>/<version>/`, and `.tools/<tool>/current` links to it. Both
build with Apple clang with warnings only.

### Hunk format for Kickstart 1.2

`amiga-env asm` runs `vasmm68k_mot -m68000 -Fhunkexe -kick1hunks -nosym`.
vasm writes the executable itself, so a one-file program needs no linker.

`-kick1hunks` is required. Without it, vasm writes absolute relocations as
`HUNK_DREL32` (`0x3F7`), which vasm's own source calls "RELOC32SHORT for
OS2.0" (`output_hunk.c`). The 1.x loader predates that hunk type. With the
flag, the same `hello.s` carries `HUNK_RELOC32` (`0x3EC`), checked in the
built file. `examples/hello/hello.s` uses an absolute `move.l #message,d2`
on purpose so that the boot test covers a relocation.

vlink has the matching `-kick1` option ("ensure Kickstart 1.x compatibility"
in `vlink -h`). It is built but nothing uses it yet; it is needed when a
program is assembled to objects (`-Fhunk`) and linked with `-bamigahunk`.

The example writes its library vector offsets as constants. They come from
the NDK 3.2 FD files (`exec_lib.fd`, `dos_lib.fd`): OpenLibrary -552,
CloseLibrary -414, Output -60, Write -48. That keeps the example free of
licensed includes. A larger program will want the NDK includes from
`media/ndk/3.2/`, passed with `-I`; whether the 3.2 includes are clean for a
1.2 target is not yet checked.

### Boot floppies: amitools xdftool

`amiga-env adf` uses `xdftool` from amitools 0.9.0 (PyPI, a project
dependency without the `vamos` extra, so it pulls no native code). It runs in
one pass: create an 880 KB image, format it OFS (`DOS\0`), install the
bootblock, write each file to the root, and write `s/startup-sequence`.

Kickstart 1.2 has no fast file system in ROM, so the disk must be OFS.

The bootblock must be named. `xdftool boot install` with no name writes
`boot2x3x`, which opens `expansion.library` first. `boot install boot1x`
writes 38 bytes that are identical to the boot code on the Workbench 1.2 disk
(`media/adf/1.2/workbench.adf`, offset 12 on: `lea dosname(pc),a1`,
`jsr FindResident(a6)`, return the dos init vector). The first 64 bytes of a
built disk, checksum `0xC0200F19` and root block 880 included, match the
Workbench 1.2 disk exactly.

### Running a program from the root on 1.2

The disk has no `C:` directory, so no `Echo`, `Wait` or `EndCLI`. A
startup-sequence line that names a program in the root runs it, because the
boot CLI's current directory is the boot volume. Verified at the machine
tier: `amiga-env a500 build/hello.adf -G` reached the initial CLI window,
which showed the Release 1.2 banner, then "Hello from 68000 assembly on
Kickstart 1.2", then a `1>` prompt. The boot printed no error for the missing
`C:`. Screenshot taken through the control socket, about 25 seconds after
launch (`runs/hello/hello-boot.png`, not tracked).

## Kickstart 1.2 findings from the piano player (verified 2026-11-07, machine tier)

From EXP-004, the expressive piano (`examples/piano/player.s`), on Amiberry
8.5.0's A500 model (Kickstart 1.2, 512 KB chip plus 512 KB slow RAM, NTSC):

- **LoadSeg honours the chip flag.** `section samples,data_c` makes vasm
  (with `-kick1hunks`) set bit 30 of that hunk's size in the header
  (`0x40014117`) and write a plain `HUNK_DATA` (`0x3EA`) in the body. The
  1.2 loader put the 328,796-byte hunk at `$12920`, and `TypeOfMem` reported
  `MEMF_CHIP`, so the player's fallback (AllocMem `MEMF_CHIP` and a copy)
  did not run. The program checks at run time all the same, since a loader
  that ignored the flag would load the samples into slow RAM, where Paula
  cannot read them.
- **CIA-B timer A is free on 1.2.** `AddICRVector(ciab.resource, 0, ...)`
  returned 0 with the boot CLI running. The player loads its latch with 715
  (716 E-clock ticks, 1.000127 ms on NTSC) and runs it continuously.
- **Interrupt dispatch costs.** From the timer running out to the player's
  handler, exec's level 6 dispatch and ciab.resource took 67 E-clock ticks
  on average (about 670 CPU cycles), so a 1 kHz interrupt through the OS
  costs 9.4% of the 68000 before the handler does anything.
- **Attack then loop with the audio interrupt.** Write AUDxLC and AUDxLEN for
  the whole sample, clear the channel's INTREQ bit, enable its INTENA bit,
  and set its DMACON bit. Paula raises the channel's interrupt once it has
  taken the start and length; the handler (installed with `SetIntVector` on
  `INTB_AUD0` to `INTB_AUD3`, called with the custom chips in a0 and is_Data
  in a1) writes the loop's start and length, which Paula takes when the
  sample ends, then clears the channel's INTENA and INTREQ bits. The voice
  logs match the host model to the byte, which says the loop timing is as
  modelled only indirectly: the log records register writes, not Paula's
  output.
- **Restarting a channel.** The player always leaves at least a millisecond
  between clearing a channel's DMACON bit and setting it again (a cut note
  fades for 4 ms, its channel stops, and the next note starts 1 ms later),
  so it never needs the busy-wait that restarting a playing channel
  otherwise takes.
- **Where things went.** ExecBase was at `$C00276` (in the slow RAM) and the
  player's AllocMem without `MEMF_CHIP` returned slow RAM (`$C0FC98`).
- **Unused 68000 vectors as a mailbox.** The player keeps its status at
  `$100` (the user interrupt vectors from 64 on, which the Amiga does not
  use), where the host reads it with Amiberry's `READ_MEM` without knowing
  where LoadSeg put the program.

## Kickstart 1.2 findings from the piano menu (verified 2026-11-07, machine tier)

From EXP-004, the expressive piano, when the player gained a menu and
loaded its scores from the floppy (`examples/piano/player.s`), on the same
Amiberry 8.5.0 A500 model:

- **Single key presses without SetMode.** `SetMode` is a 2.0 call. On 1.2
  the console handler takes the packet `ACTION_SCREEN_MODE` (994) with
  `dp_Arg1` -1 for raw mode and 0 for cooked mode. The player builds a
  `StandardPacket` (a `Message` of 20 bytes, its `ln_Name` pointing at the
  `DosPacket` of 48 bytes after it), sets `dp_Link` to the message, `dp_Port`
  and `mn_ReplyPort` to its own process's `pr_MsgPort` (`FindTask(0)` plus
  `$5C`), `PutMsg`s it to the handler's port (`fh_Type`, offset 8 of the
  `FileHandle` that the file's BPTR shifted left by 2 points at), then
  `WaitPort` and `GetMsg` on its own port. After that, `Read(fh, buf, 1)`
  returns each key at once with no echo: space came as `$20`, z as `$7A`,
  2 as `$32`. The player sends 0 before it exits, or the CLI is left raw.
- **Read the keyboard from `*`, not `Input()`.** The player opens `*`
  (`Open("*", MODE_OLDFILE)`), the CLI's own window, and sends the packet to
  that handle's handler; that worked from the startup-sequence. It does not
  use `Input()`, because a program that a script runs gets the script as its
  input (documented AmigaDOS behaviour; not tried here).
- **Waiting for a key without spinning.** `WaitForChar(fh, 20000)` (dos
  offset -204) on the raw `*` handle returns nonzero when a key is
  waiting and 0 after 20 ms. The player's task sleeps in it while its interrupts play,
  with no `Forbid`; the voice logs match the model as they did with the
  task in `Forbid` and spinning.
- **Loading a whole file.** `Open`, `Seek(fh, 0, OFFSET_END)`, then
  `Seek(fh, 0, OFFSET_BEGINNING)`, which returns the old position, so the
  file's size; then `AllocMem(size + 1, MEMF_PUBLIC | MEMF_CLEAR)`, one
  `Read` of the size, `Close`. With slow RAM fitted, `MEMF_PUBLIC` memory
  came from it (`$C0xxxx`), leaving chip RAM to the samples.
- **The boot CLI window is 60 columns.** With no `devs/system-configuration`
  on the floppy, Kickstart 1.2's own preferences apply, and the boot CLI's
  text wrapped after 61 characters (screenshot). Lines the player prints
  are kept to 60.

## Candidates

| Candidate | What it is | Notes |
| --- | --- | --- |
| vbcc | ISO C compiler with an AmigaOS target, same authors | Pairs with vasm and vlink; needs the NDK includes and a 1.x-safe startup |
| amiga-gcc (bebbo) | GCC 6 cross toolchain for m68k-amigaos | Better optimiser, heavy build; a Docker image exists |

The NDK 3.2 (includes, autodocs, FD files) is in `media/ndk/3.2/` after
`make media`.

## CPU-level and OS-level tests without the whole machine

| Candidate | What it is |
| --- | --- |
| vamos (amitools) | Runs AmigaOS 68k CLI programs on the host with an emulated exec and dos. It is amitools' `vamos` extra, which needs the native `machine68k` CPU core, so it is not installed yet. If it runs our binaries it is the counterpart of the gorsat/6809 simulator: fast, scriptable, no Kickstart needed. It emulates a later OS than 1.2, so a pass there is not evidence for the A500. |
| Musashi or Moira | 68000-family CPU cores, for pure-arithmetic kernels with no OS calls |

## Physical hardware

Stacey's 1 MB Amiga 500 is the physical authority and the performance
contract (see `AGENTS.md`). A 68000 build target with no FPU and no
32-bit-only instructions follows from that, which is why `asm` passes
`-m68000`. Getting a program onto the real machine (floppy written from an
ADF, or a serial transfer) is still to be worked out. `build/hello.adf` is a
standard OFS image and should write to a real floppy, but that is untested.
