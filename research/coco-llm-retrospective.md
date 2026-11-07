# What coco-llm teaches this project

coco-llm (`~/Work/Projects/Personal/coco-llm`, public at `svetzal/coco-llm`)
ran from 2026-07-30 to 2026-10-19: 380 commits, 19 experiments, five
published blog posts, a talk and an exhibit table. Its question was whether a
stock 1981 Color Computer could train a language model in front of an
audience. It answered that question in the emulator in its first week. This
note records what to keep and what to do differently here.

Commit cadence by month: July 53, August 173, September 128, October 26.

## Keep

**The evidence loop.** Every material decision started as a falsifiable
hypothesis in `experiments/`, was tested in the smallest reference
implementation first, and was ported only when the evidence supported it. Null
results were kept and stated plainly: the adaptive opponent (EXP-008) lost to
a ninety-byte frequency table, the register-resident loop (EXP-016) was
rejected by arithmetic before anyone built it, and the game opponent
(EXP-013) recorded that its 80% synthetic score fell to 52.8% against a real
person. That honesty is the most valuable thing in the repository.

**Evidence tiers.** coco-llm kept three levels apart: CPU-level tests in a
pinned 6809 simulator (fast, deterministic, no ROMs), machine-level checks in
XRoar with real ROMs, and physical hardware as the timing authority. Claims
named their tier. `make test` needed no ROMs and finished in about twenty
seconds.

**Bit-exact parity.** The Python reference and the 6809 assembly were checked
against each other byte for byte. That is what made it safe to change the
assembly.

**Pinning and checksums.** The simulator was pinned to a git revision. ROM
checksums were verified before every emulator run.

**A stated performance contract.** "CoCo 1 at its normal clock rate" was
written down on day one. A faster mode was allowed only as a labelled option,
never to hide a miss.

**Writing rules.** No anthropomorphising the model; every experiment number
carries a short gloss. The published posts are clearer for both.

## Change

**Scope had no boundary, so it grew.** Of 19 experiments, about eight are
about language models. The rest became a four-voice software synthesizer
(EXP-009, EXP-015 to EXP-018), a hand game (EXP-013, EXP-019), a Star Trek
title generator, a Raspberry Pi signage image (`signage/`, 501 MB on disk), a
WiFi bridge and printable cards. Each was interesting. Together they meant the
headline claim, timing on a physical CoCo 1, was still unmade at the end,
while the CoCo 3 got several hardware sessions for sound work. amiga-llm
writes its scope boundary into `AGENTS.md` before the first experiment, and
work outside it goes to a different repository.

**The Makefile became the program.** 1,324 lines and 119 targets. `tools/`
holds 72 flat scripts, ten of them near-copies named `make_*_parity_test.py`.
The pattern repeated without being factored. Here the Makefile stays a thin
index of one-line targets, and logic lives in one tested Python package
(`tools/amiga_env/`) with subcommands.

**It did not stand alone.** The ROM archive default was hard-coded to
`~/OneDrive/CoCo/MAME/roms/`. XRoar came from Homebrew, unpinned, and one day
in October saw "use the Applications XRoar app" committed and reverted. Here,
licensed media is copied into `media/` once, checked against a committed lock
file, and never read from OneDrive again. Amiberry is downloaded by
`make tools`, checked against the release's `SHA256SUMS`, and run with a
private `HOME` so it cannot read the global settings that point into OneDrive.

**Observing the machine was the weakest link.** Machine-level checks went as
far as "the program reaches its keyboard prompt". Captures meant finding the
XRoar window by process id, cropping its corners, and retrying stills when the
display had gone to sleep. An agent could not see the machine reliably, so it
could not iterate against it. amiga-llm treats driving and observing the
emulator as the first experiments, before any model work.

**One index, not three.** The experiment list lived in `AGENTS.md`,
`README.md` and `experiments/README.md`, and they drifted: the README says
eighteen experiments where nineteen exist, and two different files are both
numbered EXP-014 (`EXP-014-6309-multiplier.md`, `EXP-014-hardware-session.md`).
Here, each experiment file carries its number and gloss in front matter, and
the index is generated from the files.

**Research and presentation share one repository.** Deck, posts, fonts, card
art and signage sit beside the code. That kept the claims and the code
aligned, which mattered. It also put 37 MB of presentation and 173 MB of
ignored artifacts in the working tree. If amiga-llm reaches a talk, the
presentation lives in `presentation/` with the same alignment rule, and the
heavy binaries stay out of git from the start.
