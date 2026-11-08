# Project guidance

**Agent**: uv-python-craftsperson for the host tooling in `tools/` and
`tests/`.

## Purpose

An environment in which agents develop software for the Commodore Amiga: build
on the Mac, run on Amiberry, and check on Stacey's real machines. The loop is
the product: an agent writes a program, puts it on an emulated Amiga, runs it
and reads back what happened, with no person at the keyboard.

Three kinds of work use the loop:

- **Hardware programs** (demos, games, anything that drives the custom chips
  directly), in 68000 assembly, for the A500.
- **Desktop applications** in C with MUI, for the A3000.
- **Language-model experiments**, the project this repository started as
  (hence its name), following coco-llm. Timing claims are checked on the A500.

Reusable knowledge goes into the agent skills this repository publishes (see
"Skills" below), so it serves other Amiga projects too.

## Target machines

Each target is a `[machines.NAME]` profile in `amiga.toml`, booted with
`make a500` / `make a3000` or `amiga-env <machine> [DISK.adf]`. A profile
starts from Amiberry's quick-start model and sets only what differs on the
real machine. When a fact is read off a real machine, record it here with its
source and date, update the profile and its test (`tests/test_profile.py`),
and move it out of the "not yet read" table.

### A500: hardware programs and the performance contract

**Stacey's Amiga 500 with 1 MB of memory, at its normal clock rate.** That is a
68000 at 7.16 MHz (NTSC) or 7.09 MHz (PAL), OCS or ECS chips, no accelerator
and no hard drive. It was her first Amiga. Every timing claim is checked on
it. A result that needs a faster or larger machine is reported as a labelled
option, never in place of a miss on the A500.

| Fact | Value | Source |
| --- | --- | --- |
| Kickstart | 1.2 (`media/rom/forever/amiga-os-120.rom`) | Stacey, 2026-11-07 |
| Workbench | 1.2 (`media/adf/1.2/workbench.adf`) | follows the Kickstart |

Not yet read off the machine; the profile uses Amiberry's A500 defaults:

| Fact | Default until read |
| --- | --- |
| Memory layout | 512 KB chip plus 512 KB "slow" trapdoor RAM |
| Agnus (OCS or ECS) | OCS |
| Video standard | NTSC (the machine is in Canada) |

Kickstart 1.2 constrains the tools: OFS floppies with the 1.x bootblock,
executables in the 1.x hunk format (`vasm -kick1hunks`), and only the library
calls that exist in V33. See `research/toolchain.md`.

### A3000: desktop applications

**Stacey's Amiga 3000.** MUI needs Kickstart 2.04 or later, so desktop
applications target this machine, not the A500.

| Fact | Value | Source |
| --- | --- | --- |
| CPU and FPU | 68030 and 68882 | `media/reference/stock-a3000.uae` |
| Chipset | ECS, 2 MB chip RAM | same |
| Motherboard fast RAM | 8 MB | same |
| Video standard | NTSC | same |
| Kickstart (profile) | 3.2 (`media/rom/3.2/kick-a3000.rom`) | chosen 2026-11-07 |
| Boot floppy (profile) | `media/adf/3.2/Install3.2.adf` | `Workbench3.2.adf` does not boot alone |
| Kickstart (machine) | 3.2 A3000 ROM, checksum identical to `media/rom/3.2/kick-a3000.rom` | Stacey, 2026-11-07 |
| Accelerator | Z3660: 68060 at 50 MHz (its `z3660cfg.txt`), with the 68060's FPU and MMU | Stacey, 2026-11-07 |
| Hard disk | RDB image, 32 heads, 63 sectors; FFS 47.4 in the RDB; `Workbench` (49 MiB, DOS3, boots) and `Work` (748 MiB, DOS3) | her `A3000Current.hdf`, read 2026-11-07 |
| Workbench install | the 3.2 Installer's full install and MMULibs 46.21 (68060.library 46.4); Z3660, Picasso96, AHI and Roadshow drivers | her Workbench partition, 2026-11-07 (EXP-003) |

Not yet known: the Z3660's fast RAM size. Stacey's MUI licence is a 3.8
registration (`media/mui/README.txt`).

### A3500: the big-memory machine

**Stacey's Amiga 3500**, a Commodore prototype that came before the A3000T.
She rescued it from Commodore Canada, where she worked in the 1990s. It is
the target for programs that need more memory than the A3000 has, such as a
piano with several velocity layers and software-mixed voices. Boot it with
`make a3500`. The profile is Amiberry's A3000 model, the same design.

| Fact | Value | Source |
| --- | --- | --- |
| CPU and FPU | 68030 at 25 MHz and 68882 | Stacey, 2026-11-07 |
| Chipset | ECS | Stacey, 2026-11-07 |
| Chip RAM | 2 MB | Stacey, 2026-11-07 |
| Fast RAM | 16 MB, on the motherboard | Stacey, 2026-11-07 |
| Video standard | NTSC | Stacey, 2026-11-07 |
| Kickstart | 2.04 in ROM (`media/rom/forever/amiga-os-204-a3000.rom`, 37.175) | Stacey, 2026-11-07 |
| Drives | a floppy drive, and a BlueSCSI (SD card disk images) on the built-in SCSI port; no working SCSI hard disk | Stacey, 2026-11-07 |
| Workbench (profile) | 2.1 (`media/adf/2.1/`: Workbench, Extras, Fonts, Install, Locale), the last release for Kickstart 2.04 | Stacey's choice, 2026-11-07 |

Programs for it are prototyped as if they boot from the BlueSCSI: a hard
disk image in the emulator, which an RDB image (`amiga-env system export`)
can become on its SD card. No system for it is built yet. Amiberry's
68030 timing, with its caches, is approximate: timing claims for this
machine are checked on the real one. The profile runs the CPU at 25.06 MHz
(`cpu_multiplier=7`) with the data cache emulated; see EXP-005.

The piano for it is EXP-006, the A3500 piano: 16 voices mixed in software
and 8 velocity layers of 16-bit samples. `make piano3500` builds its host
model (`tools/amiga_env/piano/player3500.py` and `mixer.py`) and renders
EXP-004's pieces to `runs/exp006/`. The 68030 player,
`examples/piano3500/player.s`, matches that model's voice log byte for
byte: `make piano3500-run` boots it on this machine from a host folder
(DH0:), plays `PIECES` and compares the logs (emulator tier), and
`amiga-env piano3500-run examples/piano3500/piano.toml --screen` drives
its screen (EXP-004's, with the rotation, keys and filter key).
`make piano3500-image` writes `build/piano3500/piano3500.hdf`, an RDB
image for the BlueSCSI that boots Kickstart 2.04 straight into the piano
(DOS1, the ROM's FFS; no Workbench), and boots it through Amiberry's A3000
SCSI controller to check it. The image holds the samples and scores:
keep it out of git.

### a3000-dev: the A3000 as a development machine

The same A3000 profile, booting a system built from
`systems/a3000-dev.toml` (`make system`) as `DH0:` instead of a floppy,
with the project's `work/` folder as `Work:`. Boot it with `make a3000-dev`;
run a script on it with no person present with `amiga-env exec a3000-dev
SCRIPT`. `a3000-dev-060` runs the same system on a 68060 with its FPU and
MMU and Zorro III RAM, as the Z3660 does; check either with
`work/cpucheck/test.amigados`. The OS is installed as the 3.2 Installer's
full install and its CPU support libraries install would install it, with
the floppies' protection bits and dates (EXP-003).
`amiga-env system export a3000-dev OUT.hdf` writes an RDB image for the
real machine; `exec --image OUT.hdf` boots one. The tools are Stacey's
choice (2026-11-07):

| Part | Version | From |
| --- | --- | --- |
| OS | AmigaOS 3.2 | the 3.2 floppies |
| C compiler | SAS/C 6.50 (`SYS:SC`, `SC:`) | `media/dev/sasc-6.50/`, installed on the emulated machine |
| Includes, FD, linker libraries, autodocs | Amiga Developer Update 3.1 (`Developer:NDU3.1`) | `media/dev/ndu-3.1/` |
| GUI | MUI 3.8 (`SYS:MUI`, `S:mui.key`, `Developer:MUI`) | `media/mui/` |

`INCLUDE:` and `LIB:` search NDU 3.1 first, then MUI, then SAS/C's own.
The built tree holds `S:mui.key`, which must not leave Stacey's machines;
the recipe marks it personal, so an export leaves it out unless
`--include-personal` is given. An exported image is licensed media: keep
it out of git and never publish it. The Z3660 drivers are not in the
system yet. See EXP-003, the A3000 dev machine.

## Scope boundary

In scope:

- the host tooling that installs Amiberry, manages licensed media, generates
  emulator configurations, and drives and observes runs;
- the cross-toolchains (assembly now; C next) and the test tiers;
- hardware programs for the A500 and desktop applications for the A3000;
- language-model experiments, and their reference implementations on the
  host;
- the agent skills and the plugin marketplace in `plugins/`.

Out of scope here. Start a separate repository if one of these becomes a goal:

- hardware projects (PiStorm, Z3660, BlueSCSI, Gotek, KiCad boards);
- exhibit signage, Raspberry Pi images and printed material;
- a finished product (a game, an application) once it outgrows being an
  example. Give it its own repository and use this environment's tools and
  skills from there.

coco-llm had no boundary and grew without one. See
`research/coco-llm-retrospective.md`.

## Working principles

- When a literal phrase is available, use it. Don't use mannered prose.
- Optimise for learning value before novelty or benchmark performance.
- Prefer deterministic seeds, fixed inputs, checksums and test vectors.
- Use physical hardware to validate timing before making public claims.
- Record uncertain ideas as experiments rather than quietly turning them into
  architecture.
- Record what you verify, where it belongs, when you verify it (see
  "Where knowledge goes").

For language-model experiments:

- Keep the model mathematically honest. Name and explain every simplification.
- Never hide training or inference on modern hardware during a demonstration.
- Keep the computational core bit-exact across the host reference, the
  emulator and the hardware.
- Keep platform display and I/O code outside the learning engine.
- Do not anthropomorphise algorithms. The model does not read, learn about,
  understand or meet anything; it is arithmetic over the training data.

## Where knowledge goes

| Kind of knowledge | Home |
| --- | --- |
| Reusable and true for anyone (Amiberry behaviour, Kickstart 1.x rules, toolchain flags) | a skill in `plugins/amiga-dev/skills/` |
| Facts about Stacey's machines and media | this file, "Target machines" |
| Evidence and dated findings for this repository | `research/` |
| A question being tested | `experiments/` |
| An occasional workflow for this repository only (the piano videos for YouTube) | a project skill in `.claude/skills/` |

A skill states the version and host each fact was verified on, and separates
verified behaviour from behaviour that is only listed or documented. When a
skill and `research/` disagree, re-verify and fix both. Never put Stacey's
paths, machines or media in a skill.

## Skills

This repository is a Claude Code plugin marketplace
(`.claude-plugin/marketplace.json`) with one plugin, `amiga-dev`
(`plugins/amiga-dev/`). Skills so far:

- `amiberry`: install, isolate, boot, drive and observe Amiberry.
- `amiga-setup`: set up a new project like this one with the `amiga-env`
  tool: media from the user's own collection, machines, the build loop.

Project skills, for this repository only and not published, are in
`.claude/skills/`:

- `piano-video`: record a piano disk playing by itself and prepare the 4K
  master and description for Stacey to upload to YouTube.

Candidates to extract next, when their knowledge is verified: the 68000
cross-toolchain and boot floppies for Kickstart 1.x, OS-version headers and
library calls, and C with MUI.

Each skill is `plugins/amiga-dev/skills/<name>/SKILL.md`, with long material
in `references/` and helper scripts in `scripts/` (standard library only, so
they run anywhere). Keep `SKILL.md` short; its description says when to use
it. Run `claude plugin validate .` and `claude plugin validate
plugins/amiga-dev` after changing either. Bump the plugin `version` in both
manifests when a skill changes in a way users should pull.

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
  `media/manifest.lock.json`. To add media, run `amiga-env media add` and
  then `make media`. Never copy files into `media/` by hand.
- Tracked files never hold a path on one person's disk. Each manifest item
  names a source (`amiga_forever`, `amigaos32`, `collection`); where a source
  is comes from its variable in `.env`, which git ignores. `.env.example`
  lists every variable. Stacey's `.env` points into the OneDrive "Amiga
  Retro" folder; that is read only by `make media`, and only for media not
  yet copied.
- Media is copyrighted and never committed. Only the manifest and its lock are
  tracked. The repository is public (`github.com/svetzal/amiga-llm`), so
  `amiga-env guard` (`make guard`, and `tests/test_public_repo.py` in `make
  test`) fails if git tracks `.env`, anything else under `media/`, a file
  with a media suffix (`.rom`, `.adf`, `.key` and so on), or a file whose
  checksum matches locked media. Never weaken those rules to make a commit
  pass.
- Amiberry comes from `make tools` and runs through `amiga-env run`, which
  gives it a private HOME under `runs/home/`. Never launch
  `/Applications/Amiberry.app` or the bundled binary directly for project
  work; the global settings file points into OneDrive.
- `make doctor` must pass before an emulator run is reported as evidence.

## Repository practice

- Work directly on `main`. Small, scoped commits.
- The Makefile is a thin index: one line per target that calls
  `amiga-env` or another tool. Logic goes in `tools/amiga_env/` with tests.
- `amiga-env` is a public tool that other projects install
  (`uv tool install git+https://github.com/svetzal/amiga-llm@vX.Y.Z`) and set
  up with `amiga-env init`. Nothing in `tools/amiga_env/` may name Stacey's
  machines, paths or media; those belong in `amiga.toml`,
  `media/manifest.toml` and `.env`. It finds its project from `amiga.toml`,
  never from where the package is installed.
- What `amiga-env init` writes comes from `tools/amiga_env/templates/`.
  `examples/hello/hello.s` is a link to the template, so there is one copy.
- The command surface is a contract with the `amiga-dev` skills. Change it
  only with a matching skill change, and release by bumping `version` in
  `pyproject.toml` and pushing an annotated tag `vX.Y.Z`.
- Before adding a script, check whether it is a subcommand of an existing
  one. coco-llm accumulated ten near-identical generator scripts.
- Keep generated products (`build/`, `runs/`, `.tools/`) out of git.
- Cite primary sources where available.
