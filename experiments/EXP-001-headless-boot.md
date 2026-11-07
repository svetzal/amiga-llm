---
id: EXP-001
gloss: the headless boot
status: planned
---

# EXP-001: Boot an emulated Amiga with no person present

## Question

Can the tools start Amiberry from a generated configuration, with no GUI,
boot AmigaOS 3.2 from the project's own media, run a command, and stop, with
every path inside the project?

## Hypothesis

`amiga-env run -G -f <generated.uae>` boots Workbench 3.2 from
`media/adf/3.2/Workbench3.2.adf` on the 3.2 Kickstart for the chosen machine,
and a `S:User-Startup` on a host directory mounted with `-m` runs a command
whose output appears in that directory on the host within 60 seconds of
launch at maximum emulation speed.

Refuted if any of these fails: the boot needs a GUI step, a path resolves
outside the project, or no output appears in the mounted directory.

## Procedure

1. `make doctor` passes.
2. Generate a configuration for the contract machine (see the open decision
   in `README.md`; until it is made, use an A1200 with 2 MB chip RAM, the
   Amiberry quick-start default).
3. Mount `runs/exp-001/exchange/` as `EXCHANGE:`.
4. Boot, run `Echo >EXCHANGE:result.txt "booted"` and `UAEQuit` (or the
   nearest equivalent; finding it is part of the experiment).
5. Record wall-clock time to the result file, emulation speed setting, and
   Amiberry version.

## Evidence tier

Machine level (Amiberry).

## Results

None yet.
