---
id: EXP-001
gloss: the headless boot
status: planned
---

# EXP-001: Boot an emulated Amiga with no person present

## Question

Can the tools start Amiberry from a generated configuration, with no GUI,
boot the baseline A500 from the project's own media, run a command, and stop,
with every path inside the project?

## Hypothesis

`amiga-env run -G -f <generated.uae>` boots the baseline A500 profile in
`AGENTS.md` (Kickstart 1.2, 512 KB chip plus 512 KB slow RAM, OCS) from
`media/adf/1.2/workbench.adf`, and a command added to the boot sequence
writes to a host directory mounted with `-m`
whose output appears in that directory on the host within 60 seconds of
launch at maximum emulation speed.

Refuted if any of these fails: the boot needs a GUI step, a path resolves
outside the project, or no output appears in the mounted directory.

## Procedure

1. `make doctor` passes.
2. Generate a configuration for the baseline A500 profile in `AGENTS.md`.
   If the facts read off the physical A500 differ from the defaults by then,
   use the facts and record which were used.

   Risk: Kickstart 1.2 cannot boot from or automount a device the way 1.3
   can, so Amiberry's mounted directory may not appear on its own. Finding
   out is part of the question. If it does not, try a `Mount` from the
   floppy's startup sequence. If nothing works on 1.2, record that, and run
   the same procedure on 1.3 as a labelled variant.
3. Mount `runs/exp-001/exchange/` as `EXCHANGE:`.
4. Boot, run `Echo >EXCHANGE:result.txt "booted"` and `UAEQuit` (or the
   nearest equivalent; finding it is part of the experiment).
5. Record wall-clock time to the result file, emulation speed setting, and
   Amiberry version.

## Evidence tier

Machine level (Amiberry).

## Results

None yet.
