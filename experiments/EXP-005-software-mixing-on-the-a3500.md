---
id: EXP-005
gloss: software mixing on the A3500
status: running
---

# EXP-005: What 16 software-mixed voices cost a 25 MHz 68030

## Question

EXP-004's A500 piano has four voices, one per Paula channel, and they cannot
hold a pedalled piece: the player model steals 49 still-sounding notes a
minute across the ten pieces. With 16 voices it steals 1.3 a minute. Paula
has four channels, so 16 voices means mixing in software.

The A3500 (68030 at 25 MHz, 68882, 2 MB chip and 16 MB fast RAM, Kickstart
2.04) has the speed and the memory for it, with 16-bit samples in fast RAM
and 14-bit stereo out (two channels a side, at volumes 64 and 1). How much
of the CPU does the mixing take?

## Hypothesis

Written before any measurement (2026-11-07): 16 voices mixed at about 28
kHz into 14-bit stereo take roughly 30% of a 25 MHz 68030, from an estimate
of 12 to 20 cycles for each voice's sample. The design is affordable if the
real machine's worst block takes under 50%, which leaves the rest for the
player, the screen and the operating system.

## Procedure

`examples/mixbench/mixbench.s`, a floppy program for Kickstart 2.04 or
later (`make mixbench` builds `build/mixbench.adf`; `amiga-env a3500
build/mixbench.adf` boots it, as does the floppy on the real machine). Its header gives the details:

- Paula plays 512-sample blocks at period 128 (27,965 Hz, 18.3 ms) from two
  buffers in chip RAM. Channel 0's audio interrupt mixes the next block, so
  a block's mixing has one block's time.
- Each voice reads its own 32,768-sample waveform in fast RAM at its own
  16.16 pitch step, no interpolation; half the voices go left, half right.
- Way A: 8-bit samples and a 256-word volume table per level (the voice
  keeps 8 bits of detail at any volume). Way B: 16-bit samples, MULS.W and
  SWAP.
- The handler times each block with timer.device's ReadEClock. A block is
  13,107.2 E-clock ticks. The share printed is mixing time over block time.
- Six tests of 218 blocks (4 s): A and B with 8 and 16 voices with the data
  cache off, then A and B with 16 voices and the data cache on. The first
  line reports the cache bits the program found and the ticks for 1,000,000
  turns of SUBQ.L and BNE, which compares CPU speeds.

The same numbers go to a status block at $100, read through Amiberry's
control socket.

## Results

### 2026-11-07: emulator tier (Amiberry 8.5.0, approximate)

Profile `a3500`: `cpu_speed=real`, `cpu_multiplier=7` (7 x 3.58 MHz = 25.06
MHz), `cpu_data_cache=true`, approximate cycle-exact 68030. The loop line
confirms the clock: 57,437 E-clock ticks at multiplier 7 against 50,415 at
the default 8, a ratio of 1.139 for an expected 8/7 = 1.143.

| Test | Mean | Worst |
| --- | --- | --- |
| A, 8 voices, data cache off | 19.8% | 20.1% |
| A, 16 voices, data cache off | 31.0% | 31.2% |
| B, 8 voices, data cache off | 17.4% | 17.6% |
| B, 16 voices, data cache off | 26.2% | 26.4% |
| A, 16 voices, data cache on | 24.8% | 25.1% |
| B, 16 voices, data cache on | 21.6% | 21.8% |

The program found the instruction cache on and the data cache off
(`cache $00002001`). From the 8- and 16-voice rows, each voice costs 1.4%
(way A) and 1.1% (way B) of the CPU with the data cache off, about 12 and 10
cycles a sample; the rest, about 8.6%, is fixed per block, mostly writing
four 512-byte buffers to chip RAM a byte at a time.

The sound was checked from Amiberry's audio output: all 16 voices at their
expected pitches (within the 0.5 Hz resolution of the measurement), eight a
side, and the 16-voice level √2 times the 8-voice level, as for independent
voices.

How the emulator's speed settings behave, for later work: with
`cpu_speed=max` (the A3000 model's default) the CPU loop runs about eight
times faster, but the mixing times hardly change, because they depend on
memory timing; `cpu_frequency` does not set a cycle-exact 68030's clock and
gives meaningless times; `cpu_multiplier` does.

Against the hypothesis: supported at the emulator tier (16 voices take 22
to 31%). The emulator's 68030 timing is approximate, so this does not
settle it.

### 2026-11-07: way B with 32-bit sums, emulator tier

Way B rerun after the change for EXP-006 (MULS.W, then ADD.L into a
longword sum, no SWAP; shift and clamp once per output sample). Same
profile and loop count (57,436).

| Test | Mean | Worst |
| --- | --- | --- |
| B, 8 voices, data cache off | 17.8% | 18.1% |
| B, 16 voices, data cache off | 26.6% | 26.9% |
| B, 16 voices, data cache on | 25.1% | 25.4% |

With the data cache off the change costs 0.4 points. With it on, way B
loses most of its gain from the cache (21.6% before), probably because the
sums now take 4 KB instead of 2 KB against a 256-byte data cache. The test
mixes each voice to one side; the A3500 piano pans each voice to both sides,
a second MULS.W and ADD.L per voice-sample, which this test does not yet
measure.

### 2026-11-07: way C, the A3500 piano's loop, emulator tier

Way C is the loop EXP-006's player will run: linear interpolation (one
MOVE.L fetches both samples), then a volume MULS.W and ADD.L for each side,
18 instructions a voice-sample. Same profile; loop count 57,434.

| Test | Mean | Worst |
| --- | --- | --- |
| C, 16 voices, data cache off | 41.2% | 41.5% |
| C, 16 voices, data cache on | 37.9% | 38.3% |

Ways A and B gave the same numbers as before, within 0.1 points. Way C
costs about 2.0% of the CPU a voice (data cache off) against B's 1.1%, and
the fixed part per block is unchanged. 16 voices fit under the 50% limit
at the emulator tier, with 8 to 12 points to spare for the player's own
work, the screen and the operating system.

### Real machine tier

Not yet run. Stacey boots `build/mixbench.adf` on the A3500 from a floppy
and reads the six lines off the screen.

## Decision

2026-11-07: the A3500 is off the bench. Stacey chose to build the A3500
piano on the emulator's numbers and run this test on the real machine when
it is back (tracked in her Operations to-do list). Way B (16-bit samples
and MULS.W) is the design: it is cheaper than way A on the 68030 and keeps
16 bits of detail. The rest of this section stands until the real run.

Pending the real machine. If its worst 16-voice block is under 50%, the
A3500 piano is built on software mixing. The chip RAM writes (the fixed
8.6%) can be cut by writing words or longwords instead of bytes.

### 2026-11-07: way B changed after these runs

EXP-006, the A3500 piano, needs more headroom than a 16-bit sum gives, so
way B in `mixbench.s` changed to the piano's mixer: MULS.W, then ADD.L of
the 32-bit product to a longword sum (no SWAP), and an out step that shifts
each sum right by 14 and clamps it to 16 bits before the 14-bit split. The
instruction count per voice-sample is the same. The sums buffer is twice
the size, and the out step does more work per output sample. Way A is
unchanged.

The emulator numbers above were measured before this change. They are not
yet measured again; the real machine run will measure the changed program.

### 2026-11-07: way C added

`mixbench.s` has a third way, C: the A3500 piano's inner loop from EXP-006,
the A3500 piano. It does linear interpolation between the sample at the
phase and the next, one MOVE.L fetching both, and puts every voice on both
sides, with two MULS.W and two ADD.L into longword sums: 18 instructions a
voice-sample. It runs with 16 voices, data cache off and then on, after the
six tests of ways A and B, so the program now prints eight lines. It is
assembled but not yet run.

