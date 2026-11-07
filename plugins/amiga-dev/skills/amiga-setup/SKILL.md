---
name: amiga-setup
description: Set up a project for agent-driven Commodore Amiga development, the way amiga-llm is set up. A pinned Amiberry kept apart from the user's own emulator settings, the user's licensed Kickstart ROMs and floppies copied in once with a checksum lock, a pinned 68000 cross-assembler and linker, boot floppies that work on Kickstart 1.x, one-command boots of the user's real machines, and a guard that keeps licensed media out of git. Use when the user wants to start an Amiga project, build or test Amiga software from a modern computer, set up Amiberry for a repository, bring their ROMs or Workbench disks into a project, or reproduce amiga-llm's environment elsewhere.
---

# Set up an Amiga development project

The result is a project where an agent can write a program, build a bootable
floppy, boot an emulated copy of the user's real Amiga on it, see the screen,
and stop the emulator, with no person at the keyboard. The `amiga-env` tool
does the work; this skill is the order of steps and the questions to ask.

Use the `amiberry` skill for anything about running or driving the emulator
itself.

## Rules that do not bend

- **Only the user's own licensed media.** Kickstart ROMs, Workbench floppies
  and SDKs are copyrighted. Copy them only from a collection the user owns
  (Amiga Forever, an AmigaOS 3.2 or 3.1.4 purchase, dumps of their own
  chips). Never download ROMs or disk images from the internet, and never
  suggest a site that offers them.
- **Never commit media.** Only `media/manifest.toml` and
  `media/manifest.lock.json` are tracked. Run `amiga-env guard` before every
  push, and put it in the project's test or CI gate.
- **Copy once, then stand alone.** After `amiga-env media`, nothing reads the
  user's collection again. Do not point the emulator at the collection.
- **Do not touch the user's own Amiberry setup.** The project runs its own
  pinned Amiberry with a private `HOME`. Never launch an Amiberry the user
  installed themselves for project work.

## Before you start

Check, and install what is missing through the host's package manager:

- `uv` (Python tool and project manager)
- `git`
- a C compiler and `make` (`xcode-select --install` on macOS), to build vasm
  and vlink
- macOS or Linux. Windows is not covered.

Ask the user, and write the answers down before acting:

1. Which real Amigas do they want to target, and what does each have:
   model, Kickstart version, memory (chip, slow or "trapdoor", fast), NTSC or
   PAL, accelerator, hard drive? Unknown facts are fine; record them as
   unknown and use Amiberry's quick-start defaults for that model.
2. Where is each distribution they own? Typically an Amiga Forever
   installation (its "Amiga Files" folder) and an AmigaOS 3.2 CD or
   download, plus any personal folder of manuals or configurations. See
   `references/media-sources.md`.
3. What will the project build: hardware programs in assembly, OS-friendly
   applications, or both? This decides which machines matter first.

## Steps

### 1. Install the tool and scaffold the project

```sh
uv tool install git+https://github.com/svetzal/amiga-llm@v0.1.0
cd <project> && git init      # if it is not a repository yet
amiga-env init
```

`init` creates `amiga.toml`, `media/manifest.toml`, `.env.example`, an
empty `.env`, `.gitignore` entries, `examples/hello/hello.s` and, if there is
none, a `Makefile`. It keeps any file that already exists.

### 2. Install Amiberry

```sh
amiga-env amiberry          # latest release, checked against SHA256SUMS
```

It installs under `.tools/amiberry/<version>/`. `--tag vX.Y.Z` pins or rolls
back.

### 3. Bring in the media, once

Tracked files never hold a path on the user's computer. The manifest names
**sources** (Amiga Forever, AmigaOS 3.2, a personal collection), each tied to
an environment variable, and every item's path is relative to its source.
Where each source lives on this computer goes in `.env`, which git ignores.
`.env.example` documents every variable and is tracked.

Fill in `.env` with the folders the user named:

```sh
AMIGA_FOREVER_DIR="~/Amiga Forever/Amiga Files"
AMIGAOS32_DIR="~/Downloads/AmigaOS3.2CD"
AMIGA_COLLECTION_DIR="~/Documents/Amiga"
```

An environment variable of the same name overrides `.env`. Then add one item
per file the project needs, by source:

```sh
amiga-env media add amiga_forever Shared/rom/amiga-os-130.rom rom/forever/amiga-os-130.rom --licence "Amiga Forever"
amiga-env media add amiga_forever Shared/rom/rom.key rom/forever/rom.key --licence "Amiga Forever"
amiga-env media add amiga_forever Shared/adf/amiga-os-134-workbench.adf adf/1.3/workbench.adf --licence "Amiga Forever"
amiga-env media add collection manuals/M68000PRM.pdf docs/M68000PRM.pdf --licence "Freely distributed" --optional
amiga-env media           # copy everything in and write the checksum lock
amiga-env media-verify
```

`amiga-env media source NAME --env VAR --description TEXT` adds a source the
scaffold lacks. An `--optional` item is skipped, with a note, when its source
is not set; a required item with an unset source stops with the variable's
name.

For each target machine add: its Kickstart ROM, a bootable Workbench or
Install floppy for that release, and, for encrypted Amiga Forever ROMs,
`rom.key` into the same `media/` folder as those ROMs. Add the OS developer
kit (NDK) if the project will call the OS. `references/media-sources.md`
says which file is which and which floppies boot.

Commit `media/manifest.toml`, `media/manifest.lock.json` and `.env.example`.
Never commit `.env`: it describes one person's computer.

**Running someone else's kit.** When the user clones a project that already
has a manifest and lock, they only fill in `.env` and run `amiga-env media`.
If a file's checksum differs from the lock, their edition or dump of that
file differs from the one the project was built with. Report which source
and file; do not edit the lock to make it pass. Ask whether the project
should accept their edition (a decision for the project's owner).

### 4. Describe the user's machines

Add one `[machines.<name>]` block to `amiga.toml` per real machine:

```toml
[machines.a500]
model = "A500"
kickstart = "rom/forever/amiga-os-120.rom"
disk = "adf/1.2/workbench.adf"
settings = ["ntsc=true"]
purpose = "boot the A500 (Kickstart 1.2): demos, games, hardware"
```

`model` is an Amiberry quick-start model. Add a `settings` entry only for a
fact that differs from that model's defaults. `references/machines.md`
lists the defaults and the settings verified so far. Check the result before
booting:

```sh
amiga-env a500 --dump-config | grep -E '^(cpu_model|chipset|chipmem_size|bogomem_size|fastmem_size|ntsc|kickstart_rom_file)='
```

Record each machine's facts, with the source of each (the user, a config
file, read off the machine), in the project's `AGENTS.md`, including the
facts still unknown.

### 5. Check the environment

```sh
amiga-env doctor
```

It must report the Amiberry version, that every path Amiberry resolves is
inside the project, that the media matches the lock, and that each machine's
Kickstart and disk exist. Fix anything it reports before going on.

### 6. Boot each machine and look at it

Boot with no settings window, wait for the control socket, take a
screenshot, look at it, then quit (the `amiberry` skill has
`scripts/amiberry_ipc.py`):

```sh
amiga-env a500 -G &
python3 <amiberry skill>/scripts/amiberry_ipc.py --wait 60 GET_STATUS
sleep 30   # booting from floppy takes this long at normal speed
python3 <amiberry skill>/scripts/amiberry_ipc.py SCREENSHOT "$PWD/runs/a500-boot.png"
python3 <amiberry skill>/scripts/amiberry_ipc.py QUIT
```

Look at the screenshot. A Workbench screen, or a CLI with the release
banner, is a pass. The insert-disk screen means the floppy does not boot on
that Kickstart (see `references/machines.md`). Show the user the
screenshot.

### 7. Prove the build loop

```sh
amiga-env toolchain                 # build pinned vasm and vlink into .tools/
amiga-env bootdisk examples/hello/hello.s
amiga-env a500 build/hello.adf -G &
```

Then screenshot as in step 6. The pass is the line "Hello from 68000
assembly" under the AmigaDOS banner. The example runs on Kickstart 1.2 and
later, so it fits any machine.

### 8. Close out

- Run `amiga-env guard`, then commit: `amiga.toml`, the manifest and lock,
  `.env.example`, `.gitignore`, the `Makefile`, `examples/`, `AGENTS.md`.
  Never `.env`.
- Tell the user what was verified (with the screenshots), which machine facts
  are still unknown, and how to boot each machine (`amiga-env <machine>`).

## When something fails

| Symptom | Cause and fix |
| --- | --- |
| `media` says a source variable is not set | Set it in `.env` (see `.env.example`), or mark the item `--optional` if the project can do without it. |
| `doctor` lists a path outside the project | Amiberry was run without the private `HOME`. Always launch through `amiga-env`. |
| Kickstart not found, or a ROM error at boot | Encrypted Amiga Forever ROM without `rom.key` in the same folder. Add `rom.key` to the manifest beside the ROMs. |
| Insert-disk screen | The floppy does not boot on this Kickstart. Use that release's Workbench or Install floppy. |
| `media` refuses an item: checksum differs from the lock | The collection's file changed or is a different dump. Ask the user which is right; do not delete the lock entry to make it pass. |
| A 1.x machine will not load the program | Built without `-kick1hunks`, or the floppy has a 2.x bootblock. Use `amiga-env bootdisk`, which sets both. |
| `QUIT` does nothing | Another Amiberry owns `/tmp/amiberry.sock`. Check `GET_STATUS` names your disk. |
