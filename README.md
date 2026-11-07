# amiga-llm

An environment for agent-driven language-model experiments on the Commodore
Amiga. It follows [coco-llm](https://github.com/svetzal/coco-llm), which
trained a small language model on a 1981 Tandy Color Computer, and changes
what that project showed needed changing
([`research/coco-llm-retrospective.md`](research/coco-llm-retrospective.md)).

Status: skeleton. Amiberry installs and runs isolated from the host's own
settings, licensed media migrates into the project, and a 68000 program
assembled on the Mac boots on the emulated A500 from a floppy built here.
EXP-001, the headless boot, is still to be run as an experiment.

## Repository map

- `tools/amiga_env/`: the host tooling, one Python package with the
  `amiga-env` command.
- `tests/`: tests for the host tooling. No licensed media needed.
- `media/`: licensed ROMs, OS floppies, the NDK and reference manuals.
  Only `manifest.toml` and `manifest.lock.json` are tracked.
- `experiments/`: hypotheses, procedures, measurements and conclusions.
- `research/`: durable findings: the emulator, the toolchain, the
  retrospective.
- `examples/`: small programs for the Amiga, each a known-good boot test.
- `.tools/` (ignored): downloaded and built tools: Amiberry, vasm, vlink.
- `runs/` (ignored): emulator state, including Amiberry's private home.

## Getting started

Needs [uv](https://docs.astral.sh/uv/) and macOS. Linux support is written
for the build host and not yet run.

```sh
make tools         # download the latest Amiberry and check its SHA-256
make toolchain     # build the pinned vasm and vlink into .tools/ (needs cc, make)
make media         # copy licensed media in from the origin collection, once
make doctor        # Amiberry version, isolated paths, media checksums
make test          # lint and host tests
```

`make media` reads `media/manifest.toml`. Its `origin_root` is Stacey's
"Amiga Retro" OneDrive folder. Someone else can point it at their own copies
with `uv run amiga-env media --origin-root <dir>`, provided their files match
the checksums in `manifest.lock.json`.

Run Amiberry for this project with:

```sh
uv run amiga-env run [amiberry options]
```

To boot the baseline A500 (Kickstart 1.2, Workbench 1.2, NTSC) in a window:

```sh
make a500
```

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

That sets `HOME` to `runs/home/` so Amiberry's settings, ROM path, save
states and screenshots stay inside the project. See
[`research/emulator.md`](research/emulator.md).

## Performance contract

Stacey's Amiga 500 with 1 MB of memory, at its normal clock rate. It is the
physical machine timing claims are checked on. The emulated baseline matches
it. It runs Kickstart 1.2. Its memory layout, Agnus and video standard are
still to be read off the machine. See `AGENTS.md`.

## Open decisions

- **Purpose beyond the environment.** Whether the first model experiment
  repeats coco-llm's live-training thesis at Amiga scale or asks a question
  only the larger machine can answer.
