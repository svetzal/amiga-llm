# Project guidance

**Agent**: uv-python-craftsperson for the host tooling in `tools/` and
`tests/`.

## Purpose

Build an environment in which agents can develop, run and measure small
language-model experiments on the Commodore Amiga, with Amiberry as the
whole-machine emulator and real Amiga hardware as the final authority.

The first product is the environment itself: an agent can build a program,
put it on an emulated Amiga, run it, and read back what happened, without a
person at the keyboard. Model work starts when that loop is measured.

## Performance contract

**Stacey's Amiga 500 with 1 MB of memory, at its normal clock rate.** That is a
68000 at 7.16 MHz (NTSC) or 7.09 MHz (PAL), OCS or ECS chips, no accelerator
and no hard drive. It was her first Amiga and it is the physical machine every
timing claim is checked on.

A result that needs a faster or larger machine is reported as a labelled
option, never in place of a miss on the A500. No fast mode is defined yet.

The emulated baseline profile matches that machine:

| Fact | Value | Source |
| --- | --- | --- |
| Kickstart version | 1.2 (`media/rom/forever/amiga-os-120.rom`) | Stacey, 2026-11-07 |
| Workbench | 1.2 (`media/adf/1.2/workbench.adf`) | follows the Kickstart |

These facts are not yet read off it, so the profile uses Amiberry's A500
defaults until they are:

| Fact | Default until read |
| --- | --- |
| Memory layout | 512 KB chip plus 512 KB "slow" trapdoor RAM |
| Agnus (OCS or ECS) | OCS |
| Video standard | NTSC (the machine is in Canada) |

## Scope boundary

In scope:

- the host tooling that installs Amiberry, manages licensed media, generates
  emulator configurations, and drives and observes runs;
- the cross-toolchain and the test tiers;
- language-model experiments that run on the Amiga, and their reference
  implementations on the host.

Out of scope here. Start a separate repository if one of these becomes a goal:

- sound synthesis, music players and trackers;
- games and game opponents;
- exhibit signage, Raspberry Pi images and printed material;
- hardware projects (PiStorm, Z3660, BlueSCSI, Gotek, KiCad boards).

coco-llm had no boundary and grew into all of these. See
`research/coco-llm-retrospective.md`.

## Working principles

- When a literal phrase is available, use it. Don't use mannered prose.
- Optimise for learning value before novelty or benchmark performance.
- Keep the model mathematically honest. Name and explain every simplification.
- Never hide training or inference on modern hardware during a demonstration.
- Keep the computational core bit-exact across the host reference, the
  emulator and the hardware.
- Prefer deterministic seeds, fixed corpora, checksums and test vectors.
- Use physical hardware to validate timing before making public claims.
- Keep platform display and I/O code outside the learning engine.
- Record uncertain ideas as experiments rather than quietly turning them into
  architecture.
- Do not anthropomorphise algorithms. The model does not read, learn about,
  understand or meet anything; it is arithmetic over the training data.

## Evidence tiers

Every claim names its tier:

1. **Host**: the reference implementation and unit tests on the Mac.
2. **CPU or OS level**: 68k code run without the whole machine (candidates in
   `research/toolchain.md`).
3. **Machine level**: Amiberry with real Kickstart ROMs.
4. **Physical**: a real Amiga. The only authority for timing.

`make test` covers tier 1 and must never need licensed media.

## Evidence loop

1. State a falsifiable hypothesis in `experiments/`.
2. Implement the smallest test that can refute it.
3. Record quality, memory, operation counts and timing, with their tier.
4. Build on only the parts the evidence supports.
5. Record the conclusion and update `research/`.

An experiment is complete only when its evidence and conclusion are recorded.
Do not rewrite a hypothesis after seeing the result; append.

## Experiments

Each file is `experiments/EXP-NNN-short-name.md` and starts with front matter:

```yaml
---
id: EXP-001
gloss: the headless boot
status: planned   # planned | running | supported | rejected | abandoned
---
```

Never write a bare experiment number. Every reference carries its gloss on
first use in a document, in every table row, and whenever it is the subject of
a claim: "EXP-001, the headless boot". The front matter is the only place a
gloss is defined. Do not copy the list into this file or the README.

Check that the number is unused before creating a file.

## Standalone rule

Nothing in this project reads the OneDrive "Amiga Retro" folder or any other
path outside the repository at run time.

- Licensed media enters through `make media`, which copies the items listed in
  `media/manifest.toml` and records their checksums in
  `media/manifest.lock.json`. To add media, add a manifest entry and rerun
  `make media`. Never copy files into `media/` by hand.
- Media is copyrighted and never committed. Only the manifest and its lock are
  tracked. The repository is public (`github.com/svetzal/amiga-llm`), so
  `tests/test_public_repo.py` fails if git tracks anything else under
  `media/`, a file with a media suffix (`.rom`, `.adf`, `.key` and so on), or
  a file whose checksum matches locked media. Never weaken those tests to
  make a commit pass.
- Amiberry comes from `make tools` and runs through `amiga-env run`, which
  gives it a private HOME under `runs/home/`. Never launch
  `/Applications/Amiberry.app` or the bundled binary directly for project
  work; the global settings file points into OneDrive.
- `make doctor` must pass before an emulator run is reported as evidence.

## Repository practice

- Work directly on `main`. Small, scoped commits.
- The Makefile is a thin index: one line per target that calls
  `amiga-env` or another tool. Logic goes in `tools/amiga_env/` with tests.
- Before adding a script, check whether it is a subcommand of an existing
  one. coco-llm accumulated ten near-identical generator scripts.
- Keep generated products (`build/`, `runs/`, `.tools/`) out of git.
- Cite primary sources where available.
