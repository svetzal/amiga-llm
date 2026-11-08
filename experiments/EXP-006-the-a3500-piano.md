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
   end). Then each voice in runs, split where a change falls.
4. The output: the high byte of each sum to channels 0 (left) and 1 (right)
   at volume 64, bits 7 to 2 to channels 3 (left) and 2 (right) at volume 1.

Its data, in `runs/exp006/`:

- `samples.bin`: the 240 samples, 16-bit big-endian, layer by layer, without
  pads. `samples.json` gives each one's offset, length and loop start.
- `instrument.json`: the layer of each velocity, the volume table, and for
  each key its root, pan gains and, per layer, sample, step, held and
  release factors and attack blocks.
- `<piece>.score`: EXP-004's score stream, unchanged.

CPU: EXP-005 measured about 1.1% of the CPU a voice with one MULS and one
sum. The pan adds a MULS, a SWAP and an ADD a voice-sample. If that doubles
the per-voice cost, 16 voices and EXP-005's fixed 8.6% come to about 44%.
That is an estimate, not a measurement. `pan_width = 0` is the fallback.

## Not done

- Steps 4 and 5: the 68030 player, and the real machine.
- Stacey's listening (hypotheses 2 and 4).
- The binary tables for the 68030 (`instrument.json` holds their contents).
