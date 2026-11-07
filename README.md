# amiga-llm

An environment for agent-driven development on the Commodore Amiga: write a
program on the Mac, build it, boot it on Amiberry with no person at the
keyboard, and read back what happened. It targets two real machines: a 1 MB
Amiga 500 on Kickstart 1.2 for demos, games and hardware programs, and an
Amiga 3000 for desktop applications in C and MUI.

It started as a place for language-model experiments, following
[coco-llm](https://github.com/svetzal/coco-llm), which trained a small
language model on a 1981 Tandy Color Computer. Those experiments are still
one of its uses. [`research/coco-llm-retrospective.md`](research/coco-llm-retrospective.md)
records what that project showed needed changing.

## Agent skills

This repository is also a Claude Code plugin marketplace. The `amiga-dev`
plugin holds skills that work in any Amiga project: `amiberry` (installing,
isolating, booting, driving and observing the emulator) and `amiga-setup`
(setting up a new project like this one from your own licensed media).

```text
/plugin marketplace add svetzal/amiga-llm
/plugin install amiga-dev@amiga-llm
```

Status: skeleton. Amiberry installs and runs isolated from the host's own
settings, licensed media migrates into the project, and a 68000 program
assembled on the Mac boots on the emulated A500 from a floppy built here.
The `amiga-env` tool installs on its own and sets up the same environment in
any project (see "Using amiga-env in another project").
EXP-001, the headless boot, is still to be run as an experiment.

## Repository map

- `tools/amiga_env/`: the host tooling, one Python package with the
  `amiga-env` command. Installable on its own for other projects.
- `tests/`: tests for the host tooling. No licensed media needed.
- `amiga.toml`: this project's machine profiles, the A500 and the A3000.
- `media/`: licensed ROMs, OS floppies, the NDK and reference manuals.
  Only `manifest.toml` and `manifest.lock.json` are tracked.
- `.env.example`: the variables that say where each media source is. Your
  values go in `.env`, which git ignores.
- `experiments/`: hypotheses, procedures, measurements and conclusions.
- `research/`: durable findings: the emulator, the toolchain, the
  retrospective.
- `examples/`: small programs for the Amiga, each a known-good boot test.
- `plugins/amiga-dev/`: the published agent skills.
- `.tools/` (ignored): downloaded and built tools: Amiberry, vasm, vlink.
- `runs/` (ignored): emulator state, including Amiberry's private home.

## Getting started

Needs [uv](https://docs.astral.sh/uv/) and macOS. Linux support is written
for the build host and not yet run.

```sh
cp .env.example .env   # then fill in where your media sources are
make tools             # download the latest Amiberry and check its SHA-256
make toolchain         # build the pinned vasm and vlink into .tools/ (needs cc, make)
make media             # copy licensed media in from those sources, once
make doctor            # project, Amiberry, paths, sources, media, machines
make guard             # fail if git tracks licensed media or .env
make test              # lint and host tests
```

`make media` reads `media/manifest.toml`. Each item there names a source
(`amiga_forever`, `amigaos32` or `collection`) and a path inside it. Where a
source is on your disk comes from its variable in `.env`, or from the real
environment, which overrides `.env`. Your copies must match the checksums in
`manifest.lock.json`; a different edition of Amiga Forever, for example, is
refused rather than silently used. The manuals and the reference
configuration are optional, so `collection` can stay unset. For one run,
`uv run amiga-env media --source NAME=PATH` names a source's folder directly.

Run Amiberry for this project with:

```sh
uv run amiga-env run [amiberry options]
```

To boot one of the target machines in a window:

```sh
make a500     # Kickstart 1.2, Workbench 1.2, NTSC
make a3000    # Kickstart 3.2, the 3.2 Install floppy, 8 MB fast RAM
```

The machines are defined in `amiga.toml`; `uv run amiga-env <machine>
[DISK.adf] [amiberry options]` boots any of them.

To write a program in 68000 assembly and boot it:

```sh
make hello                                 # assemble examples/hello/hello.s into build/hello.adf
uv run amiga-env a500 build/hello.adf -G   # boot it, no GUI
```

`uv run amiga-env bootdisk prog.s` does the same for any one-file program:
it writes `build/prog` and a bootable `build/prog.adf` whose
startup-sequence runs it. `amiga-env asm` and `amiga-env adf` are the two
halves. The disk is OFS with the Kickstart 1.x bootblock. See
[`research/toolchain.md`](research/toolchain.md).

`amiga-env run` and the machine commands set `HOME` to `runs/home/` so
Amiberry's settings, ROM path, save states and screenshots stay inside the
project. See [`research/emulator.md`](research/emulator.md).

## Using amiga-env in another project

`amiga-env` works in any directory that has an `amiga.toml`. It looks for
the file in the current directory and then in each parent; `AMIGA_ENV_ROOT`
names a project directly. Install it as a tool, then make a project:

```sh
uv tool install git+https://github.com/svetzal/amiga-llm@v0.1.0
cd my-amiga-project && git init
amiga-env init
```

`init` writes `amiga.toml` (no machines yet), `media/manifest.toml` (the
three usual sources, no items), `.env.example` and an empty `.env`,
`examples/hello/hello.s`, a `Makefile` if there is none, and the ignore lines
in `.gitignore`. It keeps any file that exists. Then:

```sh
$EDITOR .env                                    # where your Amiga Forever and AmigaOS 3.2 copies are
amiga-env media add amiga_forever Shared/rom/amiga-os-130.rom rom/kick13.rom --licence "Amiga Forever"
amiga-env media add amiga_forever Shared/adf/amiga-os-134-workbench.adf adf/wb13.adf --licence "Amiga Forever"
amiga-env media                                 # copy them in and lock their checksums
$EDITOR amiga.toml                              # add a [machines.NAME] table using those files
amiga-env amiberry && amiga-env toolchain
amiga-env doctor
amiga-env <machine>                             # boot it
```

`amiga-env media source NAME --env VAR --description TEXT` adds a source of
your own. Run `amiga-env guard` (or `make guard`) before you push: it fails
if git tracks licensed media or `.env`.

## Performance contract

Stacey's Amiga 500 with 1 MB of memory, at its normal clock rate. It is the
physical machine timing claims are checked on. The emulated baseline matches
it. It runs Kickstart 1.2. Its memory layout, Agnus and video standard are
still to be read off the machine. See `AGENTS.md`.

## Open decisions

- **Purpose beyond the environment.** Whether the first model experiment
  repeats coco-llm's live-training thesis at Amiga scale or asks a question
  only the larger machine can answer.
