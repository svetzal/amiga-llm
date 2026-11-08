---
id: EXP-006
gloss: the A3500 piano
status: running
---

# EXP-006: Play EXP-004's pieces on the A3500 with 16 mixed voices and 8 layers

## Question

EXP-004, the expressive piano, plays ten MAESTRO performances on the A500
with four Paula voices and one 8-bit velocity layer. Stacey heard notes
clipped early. The player model shows why: four voices cannot hold a
pedalled piece, so it steals notes that still sound.

The A3500 (68030 at 25 MHz, 68882, ECS, 2 MB chip RAM, 16 MB fast RAM,
Kickstart 2.04) has the speed to mix voices in software and the memory for
more samples. EXP-005, software mixing on the A3500, measured 16 voices of
16-bit samples at 22 to 31% of the CPU in the emulator.

With 16 mixed voices, 8 velocity layers of 16-bit samples and attacks twice
as long, how close does the same score come to a piano? Does the clipping
go, does it fit in memory, and does the 14-bit output have the headroom?

This file is the host tier: a model of the 68030 player, written as the
68030 will run it. The 68030 player is the next milestone. Its voice log
must match this model's byte for byte, as EXP-004's 68000 player's log
matches `player.py`'s.

## Hypotheses

Written 2026-11-07, before the recorded host run in "Results". Trial runs of
the model while it was built had already shown some numbers (the clip counts
and the peak levels), so these are not blind.

1. 8 of Salamander's 16 layers, 30 roots a layer, as 16-bit samples with
   about twice EXP-004's attack, fit in 12 MB of the A3500's 16 MB fast RAM
   with the player's tables and the largest score.
2. 16 voices and 8 layers remove the audible clipping of EXP-004. Refuted
   if Stacey hears notes cut off in the nocturne (Op. 9 No. 2) or the
   Beethoven, the two pieces that cut most in EXP-004. Restrikes (a key
   struck again while it sounds) are a separate category.
3. A 16-bit sum per side with no saturation has the headroom: no piece
   overflows, at a volume scale where a worst case (16 adjacent keys at
   velocity 127 struck at once) does not overflow either.
4. With the volume rule below, loudness follows velocity with no step where
   one layer gives way to the next, and the tone changes by layer. The host
   tier shows the first part by construction. The second is for the ear.

## Procedure

1. Host: choose the layers and the roots from the SFZ, make the 16-bit
   samples and the player's tables (`tools/amiga_env/piano/layers.py`,
   `samples.py`, `build3500.py`).
2. Host: a model of the 68030 player and mixer, integer arithmetic only
   (`player3500.py`, `mixer.py`), run over the ten pieces of EXP-004 with
   the same score conversion (`score.py`) and the same clip measure
   (`clips.py`).
3. Host: render each piece from the model's 14-bit Paula output to a WAV.
   Stacey listens and compares with EXP-004's renders (`runs/exp004/*.wav`).
4. Machine: write the 68030 player. Compare its voice log with the model's,
   byte for byte, on the `a3500` machine in Amiberry.
5. Physical: run it on the A3500.

The command is `make piano3500` (`amiga-env piano3500
examples/piano3500/piano.toml`). It writes to `runs/exp006/`.

## Evidence tier

Steps 1 to 3 are host tier. Steps 4 and 5 are not done. Nothing here makes
a timing claim.

## Results

### 2026-11-07: procedure steps 1 to 3 (host tier, macOS)

#### The layers

Salamander's SFZ has 16 velocity layers, narrow in the middle (v3 is 35 to
36) and wide at the ends (v1 is 1 to 26). Eight are kept, with their centre
velocities spread evenly from the softest layer's (13.5) to the loudest's
(124): evenly spaced targets, each taking the nearest layer not yet taken
(`layers.choose_layers`). The softest and the loudest recordings are always
kept, so the piano keeps its whole dynamic range. A velocity plays the kept
layer whose SFZ range holds it, else the kept layer with the nearest centre.

| Kept layer | SFZ velocities | Velocities it plays | Median recorded level |
| --- | --- | --- | --- |
| v1 | 1-26 | 1-26 | 0.064 |
| v2 | 27-34 | 27-37 | 0.101 |
| v5 | 44-46 | 38-52 | 0.187 |
| v8 | 57-64 | 53-68 | 0.274 |
| v10 | 73-80 | 69-84 | 0.331 |
| v12 | 89-96 | 85-100 | 0.404 |
| v14 | 105-112 | 101-116 | 0.550 |
| v16 | 121-127 | 117-127 | 0.756 |

"Recorded level" is the sample's peak relative to the loudest of the 240.
From velocity 38 up each layer plays 11 to 16 velocities. Below 38 the SFZ
itself has only v1 and v2 as wide layers.

#### The volume rule

Each sample is normalised to full scale (peak 32,700), so a note's loudness
is its voice volume alone. The SFZ gives a note the recording's own level
times a velocity gain, `1 - t * (1 - (v / 127)^2)`, for its region's
amp_veltrack t (73% for every Salamander note), as sfizz reads it. Used
as it stands, the level would jump at every layer boundary, more so with
half the layers. So:

- for each root, the recorded level of each kept layer goes at that
  layer's centre velocity, and the level between centres is interpolated
  in decibels (flat below the softest centre and above the loudest).
- a note's volume is `full_volume * level(v) * gain(v)`, rounded, from 1
  to 32,767.

At a layer's centre the volume is the SFZ's own loudness. Between centres it
changes smoothly, and where the layer changes only the tone changes. The
68030 reads it from a table: 30 roots by 128 velocities, one word each.
`full_volume` (14,336) is the volume of the loudest sample at velocity 127.

#### The samples

Roots every minor third (30 a layer, 240 in all), the same roots and the
same loop search as EXP-004, with these changes:

- 16-bit, with triangular dither of one step either way.
- attack 2.8 s at A0 down to 0.8 s at C8, twice EXP-004's 1.4 s to 0.4 s,
  then a loop of about 0.1 s.
- stored at `2 * 4 * pitch` within 11,025 Hz and 27,965 Hz (the mix rate),
  as EXP-004 but with the mix rate as the ceiling: roots up to D#6 at
  11,025 Hz, then 11,840 Hz (F#6) up to 27,965 Hz (A7 and C8).

A key plays its root at a 16.16 step, `rate * 2^(semitones / 12) / 27,965.2`.
The largest step of any key in any layer is 1.059 (a semitone above a root
stored at the mix rate). The bound is a step below 2.0: then one 512-sample
block reads less than 1,024 samples past a sample's end, and the 68030 pads
each sample with 1,024 samples of its loop (round the loop again where the
loop is shorter, as the shortest, 826 samples, is). The model reads the
padded copy and raises an error if it ever reads past it.

Memory (fast RAM, the samples with their pads):

| Part | Bytes |
| --- | --- |
| Samples of one layer | 1,371,600 (each of the 8 is the same size) |
| Samples, all 8 layers | 10,972,800, of which pads 491,520 |
| Tables (layers, volumes, keys, samples) | 19,696 |
| Largest score (Beethoven) | 19,058 |
| Total | 11,011,554 of a 12,582,912 budget; 1,571,358 spare |

The rates are a choice against memory. At 11,025 Hz most of the keyboard
keeps nothing above 5.5 kHz. Raising the floor to 16 kHz would need about
14.8 MB, and 22,050 Hz about 19.7 MB, with these attacks. Not done.

The loops are the weak point. Before their 10 ms crossfade, 22 of the 240
seams match the signal at under 0.8 (cosine similarity), against 3 of
EXP-004's 30. The worst is C8 in layer v8, at -0.65. The loop search is
EXP-004's, unchanged.

#### The mixer and the headroom

As EXP-005's way B, with a pan. Per voice and output sample: fetch the
sample at the phase's integer part. MULS.W by the left multiplier, SWAP,
ADD.W to the left sum. The same for the right. ADD.W and ADDX.L the step.
The multipliers are `volume * gain >> 16`, set once a block. The pan gains
are constant power, bass left and treble right. `pan_width = 0.5` puts A0
at 22.5 degrees and C8 at 67.5. With `pan_width = 0` the two gains are
equal and one MULS serves both sides.

The sums are 16-bit and the 68030 does not clamp: an ADD.W that overflows
wraps. The model keeps the true sums as well, and counts the samples where
they do not fit.

- The build strikes every run of 16 adjacent keys at velocity 127 at once.
  The worst run is MIDI 77 to 92: a peak sum of 30,548, -0.6 dBFS. The
  build refuses a recipe where any run overflows. At the first scale tried
  (8,192), this run peaked at 17,454. 14,336 is 1.75 times that.
- No piece overflows. The loudest, BWV 846, peaks at 5,181 (-16.0 dBFS).
  The quietest, Debussy, at 1,621 (-26.1 dBFS).

So clamping is not needed. The price is level: at their loudest the pieces
reach about 10 to 11.5 of the 14 output bits.

#### The clipping

Counts per minute of performance, from `clips.py`. "Cut while held" is a
note the player ended (a steal or a restrike) before its key and the pedal
let it go. "Audible" counts only cuts at volume 4/64 of full or more, as in
EXP-004. EXP-004's numbers are its four-voice model.

| Piece | Minutes | Cut while held, EXP-004 | Cut while held, EXP-006 | Restrikes, EXP-006 | Steals, EXP-006 | Audible, EXP-004 | Audible, EXP-006 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Nocturne Op. 9 No. 2 | 3.7 | 300.7 | 154.4 | 127.8 | 26.6 | 281.9 | 97.1 |
| BWV 846 | 4.0 | 39.0 | 0.3 | 0.3 | 0 | 37.3 | 0.3 |
| BWV 802 | 2.2 | 0 | 0 | 0 | 0 | 0 | 0 |
| Scarlatti K. 145 | 3.4 | 16.3 | 8.7 | 8.7 | 0 | 16.3 | 8.4 |
| Haydn Hob. XVI:23 | 3.5 | 12.4 | 6.6 | 6.6 | 0 | 11.8 | 6.3 |
| Mozart K. 333 | 5.0 | 15.3 | 5.0 | 5.0 | 0 | 14.5 | 3.8 |
| Beethoven Op. 31 No. 3 | 5.9 | 87.7 | 51.4 | 51.4 | 0 | 78.0 | 32.7 |
| Schubert D. 962 | 3.6 | 34.1 | 5.5 | 5.5 | 0 | 31.3 | 3.9 |
| Nocturne in C# minor | 4.0 | 161.0 | 73.4 | 67.0 | 6.4 | 136.3 | 43.3 |
| Debussy, Des pas sur la neige | 4.2 | 51.2 | 15.3 | 15.3 | 0 | 26.3 | 3.1 |
| All ten | 39.5 | 74.4 | 33.7 | 30.5 | 3.1 | 65.5 | 20.8 |

Steals of notes that still sound fall from 56.2 a minute to 3.1 (0.8 a
minute at volume 4/64 or more). They happen only in the two Chopin
nocturnes, and the stolen notes are quiet: their median volume is about
1.5% of full (-37 dB). What remains is restrikes: the nocturne's restrikes of held
notes rise from 273 to 470, because with four voices many of those notes had
been stolen before their key was struck again. In this model a restruck
note fades out in 3.4 ms, as any cut does. On a piano the string goes on
sounding and is struck again. Letting the old sound ring on in a second
voice is an option for later. This model does not do it.

The conversation's voice-count sweep gave 49.0 a minute at 4 voices and 1.3
at 16. Its method is not recorded. With `clips.py` over the ten pieces,
`player.py`'s rules on EXP-004's samples give 56.2 a minute at 4 voices and
2.4 at 16. This model's 3.1 is close to that 2.4. I tested two causes, and
both are small. Notes here ring down to -65 dB, where `player.py` stops at
Paula volume 0: stopping at -36 dB gives 2.8. The longer undecayed attack:
halving it gives 3.1.

#### The renders

Each piece's WAV is made from the model's own output: each side's 16-bit
sum split into the bytes of its two channels, put back together as Paula
does (64 times the high byte plus the low bits), held for each mix period
and read at 44.1 kHz, as EXP-004's renders read Paula. The A3500's own
output filter is not modelled.

`runs/exp006/<piece>.wav`, for the ten pieces: `nocturne-op9-2`, `bwv846`,
`bwv802`, `scarlatti-k145`, `haydn-hob16-23`, `mozart-k333`,
`beethoven-op31-3`, `schubert-d962`, `nocturne-cs-minor`, `debussy-neige`.
Compare with `runs/exp004/<piece>.wav`. The EXP-006 renders are quieter
(see the headroom).

The whole build, from the SFZ to the ten WAVs, took 15.8 s on the Mac: 5.1
s for the 240 samples, then 0.4 to 1.4 s a piece.

#### Where the hypotheses stand

1. Supported: 11.0 MB of a 12 MB budget.
2. Not yet tested: it needs Stacey's ear. At the host tier, cuts while held
   fall from 74.4 to 33.7 a minute, audible ones from 65.5 to 20.8, and 90%
   of what remains is restrikes.
3. Supported at the host tier: no piece overflows, and neither does the
   worst run of 16 keys.
4. The first part holds by construction (`tests/test_piano_layers.py`). The
   tone is for the ear.

### 2026-11-07: more headroom, 32-bit sums (host tier)

The first results left the pieces at -16 to -26 dBFS, about 10 to 11.5 of
the 14 output bits, because `full_volume` was sized for 16 adjacent keys at
velocity 127. The coordinator asked for this change, which costs the 68030
nothing per voice-sample:

- The mixer has no SWAP. Each MULS.W product is added with ADD.L to a
  32-bit sum per output sample and side. With the pan it is still two MULS
  and two adds a voice-sample.
- Once per output sample and side, the out step shifts the sum right by 14
  and clamps it to 16 bits, then makes the 14-bit split as before. The model
  does exactly that and counts the clamped values (`mixer.output16`).

Two facts changed the request a little:

- It asked for the sum's high word (a shift of 16). A MULS.W multiplier is
  a signed word, at most 32,767, so a voice adds at most 16,383 to the high
  word. BWV 846 needed about 5.6 times its old level, which is a
  `full_volume` of about 80,000. That is not possible. A shift of 14 gives
  the two bits of gain that are missing.
- It said a 32-bit sum cannot overflow with 16 voices. It can: one product
  is up to 2^30, and 16 of them come to 2^34. A sum wraps only above four
  times full scale (+12 dB). No piece comes near that, but the worst case
  does. The model counts wraps as well.

How `full_volume` was chosen: a render at 14,336 with the new mixer peaked at
20,737 (BWV 846, -4.0 dBFS). For a peak of -1 dBFS (29,205):
14,336 * 29,205 / 20,737 = 20,190. At 20,190 BWV 846 peaks at 29,204.

| Piece | Peak | Peak, dBFS | Clamped | Wrapped | Cut while held a minute | Render, s |
| --- | --- | --- | --- | --- | --- | --- |
| Nocturne Op. 9 No. 2 | 22,302 | -3.3 | 0 | 0 | 154.4 | 1.4 |
| BWV 846 | 29,204 | -1.0 | 0 | 0 | 0.3 | 1.0 |
| BWV 802 | 11,630 | -9.0 | 0 | 0 | 0.0 | 0.5 |
| Scarlatti K. 145 | 28,815 | -1.1 | 0 | 0 | 8.7 | 0.9 |
| Haydn Hob. XVI:23 | 21,239 | -3.8 | 0 | 0 | 6.6 | 0.8 |
| Mozart K. 333 | 16,607 | -5.9 | 0 | 0 | 5.0 | 1.3 |
| Beethoven Op. 31 No. 3 | 28,156 | -1.3 | 0 | 0 | 51.4 | 1.5 |
| Schubert D. 962 | 28,196 | -1.3 | 0 | 0 | 5.5 | 1.0 |
| Nocturne in C# minor | 18,244 | -5.1 | 0 | 0 | 73.9 | 1.2 |
| Debussy, Des pas sur la neige | 9,157 | -11.1 | 0 | 0 | 15.3 | 0.9 |

No piece clamps. The worst case is now a report, not a refusal. The 16 keys
MIDI 77 to 92 struck at velocity 127 at once would reach 172,144, 14.4 dB
over full scale. The out step clamps 1,879 values, and 4 sums wrap at 32
bits. A wrapped sum comes out with the wrong sign: a click. No performance
in MAESTRO is likely to do this, but it is possible.

The clip counts hardly change. The volume scale changed and the stop level
(volume 8) did not, so notes ring a little longer relative to full: the
C-sharp minor nocturne goes from 73.4 to 73.9 cuts a minute. All ten pieces
together: 33.7 cut while held a minute, 30.5 of them restrikes and 3.2
steals, 20.8 audible.

Which measure. The counts in these tables are `clips.py`'s: every steal and
restrike of a note its key or the pedal still held, at any volume ("cut
while held"), and the same at volume 4/64 of full or more ("audible"). The
conversation's sweep (49.0 a minute at 4 voices to 1.3 at 16) counted only
steal-key and steal-pedal endings at Paula volume 4 or more, with
`player.py`'s rules and EXP-004's samples. On that measure this model gives
0.8 a minute (31 steals in 39.5 minutes).

The renders in `runs/exp006/` are this version, louder than the first by
the change in level. The build took 16.5 s: 5.1 s for the samples, then 0.5
to 1.5 s a piece.

EXP-005's `mixbench.s` way B now runs the same inner loop and out step, so
its timing test measures what the piano will run (see EXP-005).

#### Where the hypotheses stand

3. Changed design, supported at the host tier: the sums are 32-bit, and the
   out step clamps. No piece clamps or wraps. A worst case far louder than
   any piece clamps, and wraps only at the extreme.

### 2026-11-07: linear interpolation, and a band-limited render (host tier)

Stacey heard a metallic overtone, like aliasing, in the renders. The
coordinator measured it: the mixer read the sample at the integer phase
only, and against an ideal band-limited resample that gives an error of -7
to -20 dB, worst in the treble and where the step is near 1. A/B clips in
`runs/exp006/ab/` (1 the render as it was, 2 the same mix written at
27,965 Hz, 3 with linear interpolation at 27,965 Hz): Stacey heard clip 3 as
much better.

What changed:

- The mixer interpolates between the sample at the phase and the next:
  `v = s0 + (((s1 - s0) * (f >> 1)) >> 15)`, with f the 16-bit fraction
  taken as 15 bits so MULS.W, which is signed, sees it as positive. One
  MOVE.L fetches s0 and s1 together. SUB.W makes s1 - s0, so neighbouring
  samples must differ by less than 32,768: the build checks every sample.
  The largest difference is 29,624 (C8 in layer v16). The pad still covers
  the next sample: in one block s0 is read less than 1,023 samples past a
  sample's end, so s1 is within the 1,024. The inner loop is in "What the
  68030 player must match".
- The host render no longer reads Paula's output at the nearest instant at
  44.1 kHz, which added aliasing of its own. `zoh.py` models Paula's hold
  (each value held for one period) and passes it through a 20 kHz low-pass
  kernel, a Blackman-windowed sinc 16 periods either side, before it
  samples at 44.1 kHz. The hold's images below 20 kHz stay in, as they are
  in Paula's output. Above that they are removed, not folded back: an image
  at 24,965 Hz comes out below -60 dB at its alias frequency (a unit test).
  The A3000's fixed output filter is not modelled, because its corner
  frequency is not known. EXP-004's renders and `paula.py` do not change.

The error now goes in `report.json` (`interpolation_error_db`) so a
regression shows. For each kept layer and the roots C2 to A7, the root's
highest key plays the first 0.6 s of the sample. The error is the energy
of the difference from an ideal resample (the sample upsampled 16 times
through its FFT, read at the same positions) over the ideal's energy. This
is the coordinator's method, with the mixer's own integer arithmetic. The
range is over the 8 layers:

| Root | Key | Step | Nearest sample, dB | Linear, dB |
| --- | --- | --- | --- | --- |
| C2 (36) | 37 | 0.418 | -25.8 to -16.9 | -58.6 to -33.8 |
| C3 (48) | 49 | 0.418 | -25.1 to -20.9 | -56.4 to -38.1 |
| C4 (60) | 61 | 0.418 | -17.2 to -14.1 | -44.0 to -30.3 |
| C5 (72) | 73 | 0.418 | -15.0 to -8.7 | -40.1 to -21.6 |
| C6 (84) | 85 | 0.418 | -10.0 to -6.7 | -30.3 to -21.8 |
| C7 (96) | 97 | 0.634 | -7.9 to -7.0 | -26.0 to -24.9 |
| A7 (105) | 106 | 1.059 | -17.8 to -6.8 | -37.5 to -24.5 |

The worst is -6.7 dB with the nearest sample and -21.6 dB with linear
interpolation. Linear interpolation is weakest where the stored rate is low
for the pitch (C5 and C6 at 11,025 Hz). A higher stored rate there, or a
better interpolator, would help, and both cost memory or CPU.

Peaks fall a little, because interpolation smooths the samples' extremes.
`full_volume` stays 20,190:

| Piece | Peak | Peak, dBFS | Clamped | Wrapped | Render, s |
| --- | --- | --- | --- | --- | --- |
| Nocturne Op. 9 No. 2 | 21,793 | -3.5 | 0 | 0 | 4.4 |
| BWV 846 | 28,707 | -1.1 | 0 | 0 | 3.8 |
| BWV 802 | 11,095 | -9.4 | 0 | 0 | 2.0 |
| Scarlatti K. 145 | 27,142 | -1.6 | 0 | 0 | 3.2 |
| Haydn Hob. XVI:23 | 21,307 | -3.7 | 0 | 0 | 3.2 |
| Mozart K. 333 | 15,944 | -6.3 | 0 | 0 | 4.7 |
| Beethoven Op. 31 No. 3 | 27,453 | -1.5 | 0 | 0 | 5.5 |
| Schubert D. 962 | 27,279 | -1.6 | 0 | 0 | 3.5 |
| Nocturne in C# minor | 17,534 | -5.4 | 0 | 0 | 4.0 |
| Debussy, Des pas sur la neige | 9,086 | -11.1 | 0 | 0 | 3.7 |

The 16-key worst case now goes 13.8 dB over full scale: 1,743 clamped
values and 4 wraps. The clip counts do not change. The whole build took 44.8
s, 5.1 s of it for the samples; most of a piece's time is now the render.

The cost on the 68030. The inner loop goes from 7 instructions a
voice-sample (with the pan) to 18, or from 5 to 14 in mono. EXP-005's
`mixbench.s` has a way C with this loop, 16 voices, data cache off and on,
for the coordinator to run. Until then, whether 16 voices fit in the
CPU's time with interpolation is not known.

### 2026-11-07: procedure step 4, the 68030 player (machine tier)

Everything here ran on Amiberry 8.5.0 on the Mac, on the `a3500` machine:
Kickstart 2.04, a cycle-exact 68030 at 25.06 MHz (`cpu_multiplier=7`) with
its data cache emulated, ECS, NTSC, 16 MB of fast RAM. Amiberry's 68030
timing is approximate (EXP-005), so the CPU figures are the emulator's, not
the A3500's. The real A3500 is off the bench.

#### The player

`examples/piano3500/player.s`, 68030 assembly for vasm. It has no screen:
sound and the voice log only. `player RUN NAME` loads `piano.tab` and
`samples.bin` whole into fast RAM, and `scores/NAME.score` (score.py's
stream, unchanged). It takes channel 0's audio interrupt with SetIntVector,
as mixbench does, and makes each block in that interrupt in the model's
order: decay, the block's events at their own samples, the mix into 32-bit
sums in runs split at queued changes, the shift by 14 and clamp, the 14-bit
split and the checksum, then the log record and the decision whether there
is another block. The data cache is on while it plays.

The model's constants (voices, block, period, fade step, stop volume, the
blocks after the last event, the output shift) are not written in the
source. The host passes them to vasm with -D from `player3500.py` and
`mixer.py`, and the source refuses to assemble without them. A test checks
that every constant passed is one the source uses and does not define
itself.

- The inner loop is mixer.py's, 18 instructions a voice-sample. A run of an
  odd length is pairs of samples (left first, then right first, so one SWAP
  a sample keeps the multipliers in step) and one sample more.
- Each voice has a queue of up to 32 changes (a fade level or a new tone,
  each at its sample). A full queue loses the change and is counted; none
  was lost.
- The test build (LOG=1) fills a 14,848-byte buffer (64 blocks) in the
  interrupt while the task writes the other to `logs/NAME.log`. At the end
  it writes the rest, then seeks back and writes the header with the block
  count. No log block was lost in any run.
- At the end the player writes its status block (72 bytes) to
  `logs/NAME.stat`, so the host has each piece's figures after the next
  piece has started.

The data files (`m68k3500.py`, which documents and tests them):
`samples.bin` holds the 240 samples with their pads in place, 16-bit
big-endian, 10,972,800 bytes; `piano.tab` holds the layer of each velocity,
the volume table, the sample table, each key's root and pan gains, and each
key's sound in each layer, 20,816 bytes. The player is 3,568 bytes.

#### The run

`amiga-env piano3500-run examples/piano3500/piano.toml PIECE...` (`make
piano3500-run`, with `PIECES=` to choose) builds a volume in
`runs/exp006/machine/volume/` (`S/Startup-Sequence`, the player's test
build, the data, the scores), boots it as DH0: with no floppy and no
window, waits for each piece's `.stat` file, compares each log with the
model's, and stops the emulator it started. Kickstart 2.04 boots the host
folder through Amiberry's filesystem2 in about 4 s. The Startup-Sequence
holds one line a piece (`player 1 nocturne-op9-2`) after `FailAt 21`, so a
piece that fails does not stop the rest.

#### Results

| Piece | Blocks | Log | CPU, mean | CPU, worst block | Overruns | Wall time (warp) |
| --- | --- | --- | --- | --- | --- | --- |
| Nocturne Op. 9 No. 2 | 12,566 | identical | 39.5% | 44.3% | 0 | 67.3 s |
| BWV 846 | 13,151 | identical | 24.8% | 43.1% | 0 | 57.3 s |
| BWV 802 | 7,235 | identical | 21.0% | 37.6% | 0 | 31.1 s |

"CPU" is E-clock ticks from the handler's first ReadEClock to its last, over
the 13,107 ticks a block lasts; it leaves out the time exec takes to call
the handler. An overrun is a block that took longer than a block lasts.
The player's counts of notes, steals and restrikes are the model's (the
nocturne 1,498, 508 and 861; BWV 846 1,925, 9 and 938), and it clamped no
output value.

The logs are identical byte for byte: 2,915,328 bytes for the nocturne and
3,051,048 for BWV 846, every voice's key, sample, volume, multipliers and
phase in every block, and the checksum of every block's output. They were
identical in the first run; nothing had to be corrected in the player
after it first assembled.

Warp. The runs above went in warp. BWV 802 was also run at the machine's
own speed (138.5 s): 2,748 E-clock ticks a block on average in both, and
4,931 against 4,932 for the worst block. In warp Amiberry keeps the
emulated CPU's time against the E-clock, so warp is good for the CPU share.
Between two warp runs BWV 846's worst block was 5,636 and 5,644 ticks: the
worst case moves by a few ticks from run to run, the mean does not.

The make target took 2 min 14 s for the two pieces, of which about 8 s
builds the volume (the samples, the model's logs and the player).

Against EXP-005's 50% bar: the densest piece takes 39.5% on average and
44.3% in its worst block on the emulator, close to mixbench's way C (38 to
41% for 16 voices). There is room, but not much, and the real 68030 may
differ.

Not done: audio from the emulator (SDL's disk driver), which the brief made
optional. The logs, with each block's output checksum, show the mix is the
model's.

### 2026-11-07: the screen, the rotation and the BlueSCSI image (machine tier)

Amiberry 8.5.0 on the Mac, the `a3500` machine as before. The CPU figures
are the emulator's approximate 68030.

#### Aligning the samples

The MOVE.L that fetches a sample and the next reads at the sample's base
plus twice the phase's integer part. That index runs through odd and even
values, so whatever the base, about half the fetches cross a long boundary.
To make every fetch long-aligned, each sample would have to be stored twice
(each long holding a sample and the next), about 22 MB, which does not fit
the 16 MB of fast RAM. `samples.bin` now starts every sample on a multiple
of 4 bytes, so the even indexes are aligned. Every padded sample already
had an even length, so the file did not change.

Measured in the emulator with the nocturne (log run): all bases long-aligned,
5,179 E-clock ticks a block on average and 5,806 at worst; all bases moved
to 2 mod 4 (an experiment, not kept), 5,179 and 5,817. The emulator does
not charge for the misaligned half, or the two halves balance. Only the
real 68030 can say which.

#### The player's screen

`player` with no arguments opens EXP-004's screen: the same title picture
with the song list composited on the host (`screen.py`, from EXP-004's
recipe, which the A3500 recipe now shares with its `rotate_s`), the pixel
font, the gold user copper line on the playing piece, the dim attribution,
the "svetzal" signature and five scopes in the floor band (two since
2026-11-08, below). The screen code
(the ILBM reader, Intuition's screen and backdrop window, the copper list,
the choices, the rotation, the vertical blank server and the filter key)
is EXP-004's, copied into the A3500 player and adapted to it; the two
players do not share a source file. The behaviour is EXP-004's: a click or
a piece's key plays it or switches to it; 15 s after the screen appears,
and 15 s after each piece ends, the next piece plays by itself; Space stops
and holds the rotation; F switches the audio filter and the power LED
(CIA-A PRA bit 1, by the task); Esc or Q quits. Every score is loaded at
the start. `player RUN NAME` still plays one piece with no screen.

The scopes. Sixteen voices do not fit five 36-column scopes, so the four
small scopes show the four loudest voices sounding (by voice volume, in
voice order), each traced from its own sample at its own phase and step, a
column every 7.5 output samples (960 Paula clocks, as on the A500), times
the mean of its two multipliers. The large scope shows what is heard: the
left plus the right high bytes of the block Paula is playing, read from
chip RAM, a column every 4 output samples. The four loudest are what a
listener hears most; the output is the mix itself, not a model of it.

The cost. The first version drew one of six units (four small scopes and
the large one in two halves) after every vertical blank. The nocturne's
worst block then took 50.4% with the screen's work added, over the 50%
bar: a block (18.3 ms) can hold two vertical blanks, and the large
scope's halves were 60 and 48 points. What changed: the scopes go in a
cycle of eight steps (make the traces, then draw each of seven units: the
four small scopes and the large one in three parts of 36, 40 and 32
points), and at most one step a block. Each scope is redrawn about 6.8
times a second (EXP-004's A500 scopes: 20). The handler adds the screen's
E-clock ticks since the last block, less its own, to its own count, so
"worst total" is the most mixing and screen work in one block's time.

#### Results with the screen

`amiga-env piano3500-run examples/piano3500/piano.toml --screen` boots the
test build (LOG=1) on the screen and plays through the checks, touching
nothing until the rotation starts piece 1. Warp is on between the steps
and off for every key, click and screenshot; the times are the player's
own (vertical blanks). Run `runs/exp006/machine/screen/screen-run.json`:

| Step | Found |
| --- | --- |
| Boot, touch nothing | piece 1 (the nocturne) chosen by the rotation 15.00 s (emulated) after the screen appeared; its line gold in 17 ms and its first block made in 17 ms |
| The nocturne to its end | voice log identical, 12,566 blocks |
| The gap | BWV 846 started by the rotation 15.03 s after the nocturne ended |
| 20 s into BWV 846, a click on Debussy's line | gold in 17 ms, first block in 33 ms; BWV 846 stopped, its 1,246 blocks identical to the model's first 1,246 |
| F, twice | CIA-A bit 1: 0, 1, 0; two presses counted |
| Key 3 | BWV 802 gold in 17 ms, first block in 33 ms; Debussy stopped, its 251 blocks identical to the model's |
| BWV 802 to its end | voice log identical, 7,235 blocks |
| The next by the rotation, Space 5 s in | Scarlatti stopped, the rotation held, no line gold; nothing started in 30 s of quiet |
| Q | the player ended; the filter bit as it was at the start |

The screenshots (`runs/exp006/machine/screen/screen-*.png`) were checked by
the run against `title.ilbm` itself (the screen found at (76, 48) in the
screenshot, a mean difference of 0.08 of 255 when idle), for the gold line
(none idle, the playing piece's line otherwise) and for the scopes (every
one of the five with a trace in all its columns). I looked at the idle,
playing and clicked shots: the picture, the list, Debussy's line gold
under the pointer, the traces on the floor.

CPU with the screen up and the scopes drawing (test build, which also logs):

| Piece | Mixing, mean | Mixing, worst block | Mixing and screen, worst block | Screen, mean | Most for one screen step |
| --- | --- | --- | --- | --- | --- |
| Nocturne Op. 9 No. 2 | 40.4% | 45.5% | 47.1% | 1.72% | 464 E-clock ticks (3.5%) |
| BWV 802 | 21.8% | 38.7% | 40.5% | 1.69% | 443 ticks |

With the screen open the mixing itself costs about 1% more than without it
(the nocturne's log run: 39.5% and 44.3%), most likely the display's DMA on
the chip RAM writes. The test build's log record is part of these figures;
Stacey's build does not log.

Latency, from the task taking a click or a key: the line gold in 17 ms (one
frame), the first block made in 17 to 33 ms, and Paula plays it from the
next block, 18.3 ms later: about 50 ms from the click to the piece's start.
Its first note follows by the recording's own lead-in (BWV 846: 967 ms),
as on the A500.

Start-up, from the player starting: the samples (10,972,800 bytes) in 1.37
s, every score 4 vertical blanks later, the screen up at 1.48 s. That is
the emulator's SCSI, which reads the image at host speed; how long the
BlueSCSI takes for 11 MB on the A3500 is not measured.

#### The BlueSCSI image

`amiga-env piano3500-image examples/piano3500/piano.toml --boot` (`make
piano3500-image`) writes `build/piano3500/piano3500.hdf`, 16,515,072 bytes:
a Rigid Disk Block (32 heads, 63 sectors, export.py's geometry) and one
bootable partition, DH0 `Piano3500`, 13 MiB of the Fast File System
without international mode (DOS1), which Kickstart 2.04 has in ROM, so the
RDB stores no filesystem and the image needs no Workbench. It holds
`S/Startup-Sequence` (`player`), Stacey's build of the player (7,724
bytes), `piano.tab`, `samples.bin`, `title.ilbm`, `scores/` and `Credits`,
the A3500 edition's full notices (`examples/piano3500/Credits`, also
written beside the image). It is under `build/` and never committed.

Booted on the `a3500` machine with no floppy, the image attached to the
A3000's own SCSI controller (Amiberry's `scsi0_a3000`, which the ROM's
scsi.device drives, as on the real machine): Amiberry reported "Adding
SCSI HD 'scsi_a3000' unit 0", Kickstart 2.04 booted the partition, and
the piano's screen was up 1.48 s after the player started, 2.7 s after
Amiberry did. `runs/exp006/machine/image-boot.png` shows it (looked at).

Not done: the image on the real A3500 and its BlueSCSI; audio from the
emulator.

### 2026-11-08: two stereo scopes, and the emulator's glitches (machine tier)

Stacey's listening, from the image in a window: the five scopes made no
sense, and she heard audio glitches she put down to the emulator's timing.

#### Two scopes

The player now draws two scopes, the left output channel and the right,
each a quarter of the screen wide (80 columns), side by side in the middle
(columns 80 to 239), in register 15. Each traces its channel's high bytes
from the block Paula is playing, a column every 6 output samples (480 of
the block's 512), shifted right by 2 and held to 21 rows from the centre.
The columns come from the A3500 recipe's `[scopes]` table (`scopes.i`);
the rows are still EXP-004's band. The four loudest voices' traces are
gone. The cycle is five steps (make the traces, then draw each scope in two
halves of 40 points), so each scope is redrawn about 11 times a second
instead of 6.8. `runs/exp006/glitch/stereo.png` shows them under the
nocturne (looked at).

The screen run again (`amiga-env piano3500-run ... --screen`, test build):
every step as on 2026-11-07, the nocturne's and BWV 802's voice logs
identical to the model's, both scopes traced in every column in each
screenshot checked. The nocturne's worst block, mixing and screen, 47.5%
(47.1% with five scopes); BWV 802's 40.7%; the screen 1.7% on average, at
most 467 E-clock ticks for one step.

#### The glitches

Three measurements, with the image playing the nocturne (Stacey's build,
no log):

- The emulator keeps time: 0.99 emulated seconds a wall second, sampled
  each second for 25 s, on about half of one host core.
- The player keeps time: no block overran, the worst took 38.3% of a block
  with the screen up.
- Amiberry's output has no gaps: 30 s captured through SDL's disk driver
  had no runs of silence, no held samples and no clicks
  (second-difference spikes).

So the Amiga side is clean, and the glitches come after it, between
Amiberry and the Mac's audio device. Amiberry ran with its default buffer,
768 frames at 44.1 kHz (17 ms), in push mode; the cycle-exact 68030 makes
the emulator's frames uneven enough to miss that now and then. The `a3500`
profile now sets `sound_max_buff=8192`, a 2048-frame buffer (46 ms; 16384
gives 4096 frames). This is a host setting, not the real machine. It adds
about 30 ms between a click and the sound in the emulator only. Whether it
cures what Stacey heard is for her ears; the capture cannot show a device
underrun.

### 2026-11-08: a filter light (machine tier)

Stacey could not tell from the screen whether the audio filter was on. The
power LED shows it on the real machine, but not where she looks. The host
now draws a 7 by 7 light in register 14 (free since the scopes became one
colour) and the word "filter" in the attribution's brown, in the lower left
corner on the signature's row (light at columns 1 to 7, label at 11 to 31,
rows 192 to 198; `[filter_light]`, since moved to EXP-004's shared recipe
when the A500 disk got the same light, and `light.i`). The player sets
register 14 with SetRGB4 from CIA-A bit 1 when the screen opens and after
each F: $F42 (lit) while the filter is on, $311 (unlit) while it is off.

Checked on the image: three screenshots with F pressed between them showed
the light lit, unlit, lit, with the CIA bit 0, 1, 0
(`runs/exp006/glitch/lightcrop*.png`, looked at). The screen run passed
again with the same figures (voice logs identical, the nocturne's worst
block 47.5%).

### 2026-11-08: a video of the image playing by itself (machine tier)

Stacey asked for the same unattended playthrough as EXP-004's A500 video,
of the A3500 image (`build/piano3500/piano3500.hdf`, SHA-1 `185efdfb...`,
built from `main` just before). `amiga-env piano3500-video
examples/piano3500/piano.toml` (`make piano3500-video`) records it through
Amiberry 8.5.0's libretro core into `runs/video3500/`; the workflow is the
project skill `.claude/skills/piano-video`. The core has no A3000 model, so
it boots the app's own resolved configuration of the `a3500` profile and
the image on `scsi0_a3000` as a `.uae`; the core's configuration showed no
differences from the app's. Nothing was sent to the machine.

| Check | Found |
| --- | --- |
| Recording | 152,741 frames at 59.826 a second (NTSC), 42:33.08, boot to 5 s after piece 10 ended; 42:40.5 wall (the core paces the cycle-exact 68030 at real time) |
| Frames | 756x486, every one kept, none repeated; frames 0 to 24 were 756x484 and put on the canvas with 2 black rows |
| Sound | 122,545,728 samples at 48 kHz, 802.311 a frame, 2,261 short of the frame count (from the core's start); no frame without sound after the first |
| Capture | 25.1 GB lossless (FFV1), 0.49 GB WAV |
| 4K master (`runs/video3500/piano3500-playthrough-4k.mp4`) | 152,741 frames, 3840x2160 H.264 CRF 16, BT.709, AAC 48 kHz stereo; 0.80 GB; made in 23 min |
| Gold lines | all ten found in the master's own frames, each the frame after the player's own stamp, the same in the capture |
| Levels | the whole run RMS -31.7 dBFS, peak -7.4; the pieces from -41.5 (Debussy) to -29.1 RMS, peaks -17.4 to -7.4 |
| Digital silence of 20 ms or more within pieces | every one is in the host model's render of that piece at the same time (Beethoven's six, Schubert's three, the eight short ones near the end of the C# minor nocturne, and the rest): rests, not dropouts |

Sound against picture. The player stamps a piece's first note while it
mixes the block the note falls in, and Paula plays that block one block
later, so each note's own delay (19.0 to 33.7 ms here) comes off the
measured lag first. The ten first notes then bound the core's offset to
+12.6 to +15.4 ms, the sound late by under a frame. They agree with each
other, so the delay model holds; the master is not shifted.

Chapters (rounded down, each at or before its gold line): 0:00 boot and
title screen, then 0:17, 4:22, 8:38, 11:05, 14:48, 18:32, 23:50, 29:58,
33:59 and 38:16. `runs/video3500/youtube-description.generated.txt` is the
draft from `examples/piano3500/video-description.txt`; Stacey edits a copy
named `youtube-description.txt`, which the command never writes. I looked
at master frames at 0:30, 10:00, 25:00 and 40:50.

## What the 68030 player must match

The voice log, byte for byte (`player3500.py`'s docstring has the format):
a 16-byte header ("P35L", version 1, 16 voices, 512 samples a block, the
number of blocks), then per block the checksum of its sums and a 14-byte
record for each voice. 232 bytes a block, 12.7 KB a second of music: 4.5 MB
for the Beethoven, more than the fast RAM the samples leave free. The log
build must write the log to disk as it goes, or log part of a piece.

For each block, in this order:

1. Decay. For each voice whose note started before the block, count the
   block. Unless its key or the pedal holds it within its attack blocks,
   multiply its volume by the held or release factor (`volume * factor >>
   16`). Below 8 the voice stops. Else set its multipliers again.
2. The score's events in the block, each at its sample (`ms * 3,579,545 //
   128,000`). Voice choice, cuts and waiting as in the docstring. A cut
   fades the old tone's multipliers to 3/4, 2/4 and 1/4 for 32 samples each
   (`m * q >> 2`), then the new tone starts at phase 0.
3. Mixing. At the block's start, bring each tone's phase back round its
   loop (subtract the loop length while the integer part is at or past the
   end). Then each voice in runs, split where a change falls. Each output
   sample of a voice is `s0 + (((s1 - s0) * (f >> 1)) >> 15)`, the sample at
   the phase's integer part and the next, with f the phase's 16-bit
   fraction (`mixer.interpolate`). It is multiplied by each side's
   multiplier and goes into a 32-bit sum (ADD.L, which wraps).
4. The output: each sum shifted right by 14 and clamped to 16 bits. Its high
   byte goes to channels 0 (left) and 1 (right) at volume 64, its bits 7 to
   2 to channels 3 (left) and 2 (right) at volume 1. The log's checksum is
   of these 16-bit values.

Its data, in `runs/exp006/`:

- `samples.bin`: the 240 samples, 16-bit big-endian, layer by layer, without
  pads. `samples.json` gives each one's offset, length and loop start.
- `instrument.json`: the layer of each velocity, the volume table, and for
  each key its root, pan gains and, per layer, sample, step, held and
  release factors and attack blocks.
- `<piece>.score`: EXP-004's score stream, unchanged.

The inner loop, as `mixer.py`'s docstring gives it, with d0 and d2 the
phase's integer part and fraction, d1 and d3 the step's, d7 the left
multiplier in the low word and the right in the high word, a0 the sample,
a2 and a3 the left and right sums:

```text
move.l  (a0,d0.l*2),d4   ; s0 in the high word, s1 in the low word
move.l  d4,d6
swap    d6               ; s0
sub.w   d6,d4            ; s1 - s0
move.w  d2,d5
lsr.w   #1,d5            ; f >> 1
muls.w  d5,d4
add.l   d4,d4
swap    d4               ; >> 15
add.w   d6,d4            ; v
move.w  d4,d6
muls.w  d7,d4
add.l   d4,(a2)+         ; left
swap    d7
muls.w  d7,d6
add.l   d6,(a3)+         ; right
add.w   d1,d2
addx.l  d3,d0
```

18 instructions a voice-sample. The next sample does the right side first,
so one SWAP of d7 a sample keeps the multipliers in step. The loop is
unrolled by four and ends on CMPA.L and BLO.W against the end of the sums,
which leaves d7 free for the multipliers. In mono, 14 instructions (no copy,
no second MULS.W and ADD.L, no SWAP). A run that is not a multiple of four
samples needs its own entry into the unrolled loop; that is the 68030
player's to solve, and the model does not depend on it.

CPU: EXP-005 measured about 1.1% of the CPU a voice for the old 5- to
6-instruction loop. This one is about three times as long. `mixbench.s` way
C will measure it. `pan_width = 0` (14 instructions) is a fallback.

## Not done

- Steps 4 and 5: the 68030 player, and the real machine.
- Stacey's listening (hypotheses 2 and 4).
- The binary tables for the 68030 (`instrument.json` holds their contents).
