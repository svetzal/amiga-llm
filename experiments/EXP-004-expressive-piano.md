---
id: EXP-004
gloss: the expressive piano
status: running
---

# EXP-004: Play a human piano performance on the A500 with its dynamics

## Question

How much of a real pianist's expression (the velocity of every note and the
sustain pedal) can a stock 1 MB A500 reproduce through Paula, with sampled
piano notes, so that a listener hears the performance and not a sequence?

The A500 keyboard has no velocity, so the first source is a recorded
performance, not live playing.

## Sources

- **Performance:** MAESTRO v3.0.0 (Google Magenta), MIDI recorded on
  Yamaha Disklaviers at the International Piano-e-Competition: key strike
  velocity and sustain, sostenuto and soft pedals for every note.
  Licence: CC BY-NC-SA 4.0. Archive `maestro-v3.0.0-midi.zip`, SHA-256
  `70470ee253295c8d2c71e6d9d4a815189e35c89624b76d22fce5a019d5dde12c`,
  from `https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/`.
- **Samples:** Salamander Grand Piano v3 (Alexander Holm, Yamaha C5),
  CC BY 3.0, through its SFZ, which gives each sample's root note, key range
  and velocity layer.

Neither is committed. Both are fetched and checked against recorded
checksums.

## Pieces

Measured on 2026-11-07 (host tier; "ringing" counts keys held plus strings
the sustain pedal keeps sounding):

| Piece (MAESTRO performance) | Length | Velocity range | Pedal down | Keys held, 95% / max | Ringing, 95% / max |
| --- | --- | --- | --- | --- | --- |
| Chopin, Nocturne Op. 9 No. 2 (2011) | 225 s | 3 to 100 | 93% | 4 / 6 | 21 / 43 |
| Chopin, Nocturne Op. 15 No. 2 (2008) | 232 s | 3 to 99 | 88% | 5 / 7 | 13 / 22 |
| Chopin, Nocturne in C-sharp minor, Op. posth. (2014) | 244 s | 11 to 97 | 82% | 4 / 7 | 14 / 23 |
| Bach, Prelude and Fugue in C major, BWV 846 (2014) | 240 s | 3 to 104 | 10% | 5 / 8 | 5 / 11 |
| Chopin, Preludes Op. 28 Nos. 15 and 24 (2011) | 117 s | 3 to 118 | 95% | 4 / 7 | 35 / 49 |

Target: the Nocturne Op. 9 No. 2. Control: BWV 846, which has almost no
pedal and fits four voices most of the time.

## Constraints

- Paula: four 8-bit voices, a volume of 0 to 64 per voice, about 28 kHz at
  most per voice. Samples must be in chip RAM: 512 KB on the baseline A500,
  shared with the program and the score.
- One velocity layer per note may be all the memory allows; velocity then
  maps to volume (and later, if memory allows, to a choice of two layers).
- Pitch comes from Paula's period, so a sample stretched over many
  semitones changes its attack and tone. Root notes every few semitones.

## Hypotheses

1. With samples every 3 semitones, one velocity layer, an attack plus a
   short loop and a software decay, the piano fits in chip RAM with room for
   the player and the score.
2. Four voices with a software decay per voice and quietest-voice stealing
   play the pedalled nocturne without audible gaps: the notes that are
   stolen are the ones already faded.
3. A host model of Paula and the player, fed the same samples and score,
   gives the same voice, period and volume sequence as the A500 player, so
   the host can render a WAV to judge by ear before the 68000 code exists,
   and the emulator run can be checked against it.

Refuted, for 2, if Stacey hears notes cut off or missing in the nocturne
that she does not hear in the control.

## Procedure

1. Fetch MAESTRO and Salamander reproducibly, with checksums.
2. Host: convert the score to a compact event stream (time, note, velocity,
   pedal) and the samples to 8-bit with loops and a memory report.
3. Host: a Paula model that plays the event stream and writes a WAV. Stacey
   listens.
4. A500: the 68000 player, booted from a floppy built by `amiga-env`.
5. Compare the emulator's voice log with the host model; record audio from
   Amiberry; Stacey listens; later, the real A500.

## Evidence tier

Host for steps 1 to 3, machine level for 4 and 5, physical at the end.

## Results

### 2026-11-07: procedure steps 1 to 3 (host tier, macOS)

All numbers here are host tier: the reference implementation in
`tools/amiga_env/piano/`, run by `make piano` (`amiga-env piano
examples/piano/piano.toml`). Nothing has run on a 68000 yet. Outputs are in
`runs/exp004/` (not tracked): `report.json` has every number below.

#### Step 1: the sources, fetched reproducibly

`media/manifest.toml` now has `[[download]]` entries: a pinned https URL,
the download's size and SHA-256, its licence, and `unpack = "zip"` or
`"tar"`. `amiga-env media` fetches each into a fresh directory beside its
destination, refuses it unless size and checksum match, unpacks only
regular files and directories that stay inside the destination, clears
execute bits, and locks the unpacked tree beside the URL. Nothing from a
download is run. Both are optional, so the project still works without
them.

| Download | Size | SHA-256 | Licence |
| --- | --- | --- | --- |
| MAESTRO v3.0.0 MIDI, `maestro-v3.0.0-midi.zip` | 58,416,533 bytes | `70470ee2...5dde12c` | CC BY-NC-SA 4.0 |
| Salamander Grand Piano V3, `SalamanderGrandPianoV3+20161209_44khz16bit.tar.xz` from freepats.zenvoid.org | 412,313,804 bytes (1.1 GB unpacked, 644 files) | `58750eb1...4c819936` | CC BY 3.0, Alexander Holm |

The sfzinstruments GitHub repository for Salamander has no releases or
tags, only a branch of 48 kHz 24-bit FLAC, so it cannot be pinned. The
sfzinstruments page links the freepats archives; the 44.1 kHz 16-bit one
is the smallest package with the SFZ and WAV samples (the 48 kHz 24-bit
one is 1.18 GB, the SFZ+FLAC one 742 MB). Its date, 2016-12-09, names the
edition.

#### Step 2: the score

Decisions:

- **Time in milliseconds.** A 60 Hz frame (16.7 ms) would flatten chord
  spreads and rubato that a listener hears; 1 ms is below that. The player
  can count it with a CIA timer (716 ticks a millisecond on NTSC), as a
  1 kHz interrupt or a one-shot per wait. The 68000 player decides which.
- **A byte stream read one byte at a time**: note on is the key (0 to 87)
  and a velocity byte; note off is one byte; waits of 1 to 40 ms are one
  byte, up to 255 ms two, up to 65,535 ms three; pedal down and up and the
  end are one byte each. The format is in `score.py`'s docstring, and
  `decode` is the reference for the 68000 reader.
- **Sustain pedal down at CC64 >= 64**, the usual threshold, keeping only
  changes. Sostenuto (CC66) and soft (CC67) are counted and left out.

| Piece | Length | Notes | Pedal changes | CC64 messages | Ignored CC66 / CC67 | Velocity min / median / max | Stream |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Nocturne Op. 9 No. 2 | 220.7 s | 1,498 | 269 | 2,901 | 1 / 129 | 3 / 55 / 100 | 9,689 bytes |
| BWV 846 | 239.9 s | 1,925 | 160 | 746 | 0 / 781 | 3 / 69 / 104 | 11,573 bytes |

No note fell outside the 88 keys.

#### Step 2: the samples

Decisions:

- **Which SFZ.** `SalamanderGrandPianoV3.sfz`, Alexander Holm's own
  mapping. The package also has `SalamanderGrandPianoV3Retuned.sfz` (Markus
  Fiedler), whose `tune` opcodes pull the samples towards equal temperament
  (+10 cents at A0 to -38 cents at C8); the reader handles `tune`, so the
  retuned file is one line in the recipe if Stacey prefers it.
- **Roots.** Salamander sampled every minor third from A0: roots 21, 24,
  ..., 108, 30 of them. Choosing every 3 semitones (evenly spaced targets
  from A0 to C8, each moved to the nearest sampled note) therefore takes
  every sampled note, and each key plays its nearest root, never more than
  one semitone away. This is the same key mapping as the SFZ's own
  `lokey`/`hikey`.
- **Velocity layer.** The median of both pieces' 3,423 velocities is 64,
  which is in layer v8 (velocity 57 to 64). The pieces' own medians are 55
  and 69.
- **Rate and period.** Each root is stored at the rate Paula plays it at an
  integer period, so the root is exact and the keys around it are a period
  lookup. The rate aimed for is at least 11,025 Hz and at least eight times
  the root's pitch (four harmonics), at most 27,000 Hz so the key above the
  top root keeps a period of 124 or more. A search near that rate takes the
  period whose neighbouring keys round closest to pitch. Below F#6 every
  root is at period 320 or 321 (about 11.2 kHz), which with the A500's
  fixed filter at about 4.4 kHz loses little; the treble rises to
  26,515 Hz (period 135) at C8. The worst key is 3.1 cents off pitch.
- **Attack and loop.** Each sample keeps the recording from its first
  sound, 1.4 s at A0 down to 0.4 s at C8 (linear in key), then a loop of
  about 100 ms (the search moves it within 75 to 125 ms) whose start best
  matches the samples around its end (cosine similarity over up to two
  fundamental periods either side, at most a quarter of the loop). The loop is flattened against the recording's own
  decay, so its level holds, and its last 10 ms are crossfaded into the
  samples before its start so the seam continues the signal. Lengths and
  the loop start are even, as Paula needs.
- **Decay.** Each root's decay rate is fitted to the RMS of the recording
  in 50 ms frames over 3 s from the loop start: 1.0 to 7.5 dB/s.
- **Normalising and dither.** Each sample is normalised to a peak of 126
  and quantised with triangular dither of one step. Its level before
  normalising (relative to the loudest root, 0.25 to 1.0) goes to the
  player, which multiplies it into the volume. Paula's volume scales the
  quantisation noise down with the note, so this keeps the recording's
  balance between registers with the most bits in every sample.

Chip RAM, against a 380 KB budget (389,120 bytes) for samples, score,
tables and program:

| Part | Bytes |
| --- | --- |
| 30 samples | 328,794 |
| Largest score (BWV 846) | 11,573 |
| Player tables (88 keys, 30 samples, velocity) | 1,200 |
| Program (an estimate; the player does not exist yet) | 8,192 |
| Total | 349,759 (341.6 KB) |
| Headroom under the budget | 39,361 |

Per sample: 7,170 bytes (F#6) to 15,612 bytes (A0). Loop similarity
before the crossfade is 0.67 at worst (C1), median 0.96.

Trade-offs measured on the way (samples only differ):

| Setting | Total bytes | Note |
| --- | --- | --- |
| Attack 0.8 s to 0.25 s | 213,619 | first run; leaves 175 KB unused |
| Attack 1.4 s to 0.4 s (chosen) | 349,759 | longer recorded attack before the loop |
| Same, minimum rate 14,000 Hz | 401,767 | over the budget by 12,647 bytes |
| Same, roots every 6 semitones | 186,269 | keys up to 3 semitones from a root |

So the budget buys a longer recorded attack at every 3 semitones, not a
higher rate.

Known weakness, and a cost of that choice: the loop is cut from the
recording where the attack ends, after the note has faded, and shares the
attack's normalisation. In the bass the loop is 2 to 5 dB below the attack;
from middle C up it is 11 to 21 dB below, with an RMS of 2 to 6 steps of
the 8-bit range, so sustained treble notes play from very few bits. The
longer attack made this worse: root 75's loop RMS fell from 26 steps (first
run) to 15. One way out for step 4: normalise the loop on its own and lower
the voice's volume by the same factor in the audio interrupt Paula raises
when it starts the loop, which is exact to the sample where a frame tick is
not. That is a choice for the 68000 player, not made here.

#### Step 3: the player model and Paula

Decisions:

- **Voices.** A note on takes the voice already sounding its key (the
  string is struck again, as on a piano), else the lowest free voice, else
  the quietest voice (the oldest on a tie).
- **Volume from velocity.** `64 * (v / 127) ** 1.5`, at least 1: about 9 dB
  per doubling of velocity, 22 at velocity 64, 64 at 127. One velocity
  layer means loudness alone carries the dynamics; a square law (30 dB over
  velocity 20 to 110) would push quiet notes to volumes of 1 to 3, where
  Paula's steps are 3 to 6 dB.
- **Decay.** Volume is 8.8 fixed point; each 60 Hz tick multiplies it by a
  16-bit factor (`(v * f) >> 16`, a MULU on the 68000). Held (key or pedal
  down): the root's measured decay, not applied while the recorded attack
  is still playing because the recording already fades. Released: the SFZ's
  `ampeg_release` read as a 60 dB fade (1 s, 60 dB/s, where the key has a
  damper; 5 s for keys 89 and up, which Salamander marks as having none),
  never slower than the held decay. A voice stops when its volume reaches
  0.
- **Order.** Events at the same millisecond as a tick go first; tick k is
  at `k * 1000 // 60` ms.
- **Rendering.** Each voice holds each 8-bit value for its period of the
  3,579,545 Hz clock and multiplies it by its 6-bit volume, with no
  interpolation, read at 44.1 kHz. Voices 0 and 3 are left, 1 and 2 right,
  so the WAVs are stereo as an Amiga is. Paula full scale is WAV full scale,
  so the files are quiet (RMS -29.7 dBFS and peak -9.7 dBFS for the
  nocturne; -26.9 and -7.0 for the Bach): that is the level the Amiga
  would put out, relative to its maximum. Simplification: a
  register write takes effect at once.

| Piece | Steals a minute | Steals of notes still held (key or pedal) | Stolen volume median / max | Stolen volume 1 / 2-3 / 4-7 / 8-15 / 16-31 / 32-64 | Restrikes | Dropped |
| --- | --- | --- | --- | --- | --- | --- |
| Nocturne Op. 9 No. 2 | 307.8 | 1,024 of 1,132 | 8 / 25 | 9 / 85 / 449 / 499 / 90 / 0 | 362 | 0 |
| BWV 846 | 355.7 | 249 of 1,422 | 5 / 25 | 137 / 356 / 509 / 389 / 31 / 0 | 349 | 0 |

No note was dropped: every key has a sound, and the volume floor of 1 keeps
every note audible.

Stacey listens to these (A500 filter: one pole at about 4.4 kHz, the
360 ohm and 0.1 uF RC usually given for the A500; an approximation, not
measured, and not the switchable LED filter):

- `runs/exp004/nocturne-op9-2.wav` and `runs/exp004/nocturne-op9-2-a500-filter.wav`
- `runs/exp004/bwv846.wav` and `runs/exp004/bwv846-a500-filter.wav`

The voice logs (`runs/exp004/*.voices.csv`, one row per voice per tick:
tick, ms, voice, MIDI key, sample, period, volume) are what the 68000
player's log will be compared with for hypothesis 3. `runs/exp004/samples.bin`
and `samples.json` hold the samples end to end with their offsets and loops.

#### Where the hypotheses stand

- Hypothesis 1 holds at the host tier: every 3 semitones, one layer, an
  attack and a short loop fit in 349,759 bytes with an estimated 8 KB
  program, 39 KB under 380 KB. The program size is a guess until step 4.
- Hypothesis 2 waits for Stacey's ears. The numbers: the nocturne steals a
  voice about five times a second, and 90% of those notes are still held
  by the key or the pedal; half of the stolen notes are at volume 8 or more
  (of 64). The control steals more often (BWV 846's notes are denser) but
  mostly notes already released, at a median volume of 5.
- Hypothesis 3 is untested: there is no 68000 player yet.

### 2026-11-07: Stacey listens to the host renders

Stacey listened to the step 3 renders (`runs/exp004/*.wav`) on 2026-11-07.
Her words: "I am noticing some notes clipped early, it's a little jarring,
but in general it sounds quite nice."

Against hypothesis 2: refuted as stated. Four voices with quietest-voice
stealing do not play the pedalled nocturne without audible gaps; the notes
that are stolen are not all already faded. She did not say whether she
heard the clipping in the control as well.

### 2026-11-07: the clipped notes, found and changed (host tier)

How each note's sound ends, from the model's own record (`clips.py`, now in
`report.json` under `clips`). A note is released when its key and the
sustain pedal are both up: at its note off if the pedal is up, else at the
next pedal up. A note the player ends before that was cut while held.
Notes ended during their release fade are not counted as cut: the damper is
already stopping them. "Before" is the step 3 model; "after" is the changed
one. Counts per minute of the performance:

| Cause | Nocturne before | Nocturne after | BWV 846 before | BWV 846 after |
| --- | --- | --- | --- | --- |
| Stolen while its key was down | 87.5 | 7.3 | 45.8 | 29.0 |
| Stolen while only the pedal held it | 127.0 | 219.1 | 4.8 | 9.8 |
| Its key struck again while held (restrike) | 84.8 | 74.2 | 0.3 | 0.3 |
| All cut while held | 299.3 | 300.7 | 50.8 | 39.0 |
| Cut while held at Paula volume 4 or more | 282.5 | 281.9 | 48.3 | 37.3 |
| Faded to silence while held | 0 | 0 | 1.3 | 2.0 |
| Stolen during its release fade | 93.2 | 92.4 | 305.1 | 331.6 |

Causes, in order of size:

1. **Steals of held notes**, the cause. The pedalled nocturne keeps 21
   strings ringing at its 95th percentile, and four voices cannot hold
   them. Under the old rule (quietest first) the melody, held under the
   finger while it decays, was stolen 87.5 times a minute by fresh, louder
   accompaniment notes.
2. **Restrikes**, a second, smaller source. In the changed model, 137 of
   the nocturne's 315 restrikes replace a sound louder than the new note's start, 21 of
   them by a factor of two or more. On a piano the string struck again
   keeps ringing. Not changed: it is the same key sounding again, not a
   note that stops.
3. **The 1 s release on key-up**: not a cause. A note ended in its release
   is already being damped.
4. **The attack-to-loop join**: not a cause. The loop starts where the
   attack ends in the recording, so the level is continuous there.
5. **Fading to silence while held**: rare (0 and 5 to 8 notes a piece), and
   it follows each root's measured decay.

What changed in the model (`player.py`), and why it suits a 68000:

- **Steal a key-up note first.** The voice stolen is the quietest whose key
  is up (held by the pedal only, or released); only when every key is down
  is it the quietest of all. On the 68000 that is one more word compare in
  the steal loop. It cuts melody steals in the nocturne from 87.5 to 7.3 a
  minute, and in BWV 846 from 45.8 to 29.0. The total cut while held does
  not fall: the nocturne loses pedal-held notes instead (127.0 to 219.1),
  which are mostly the inner notes of the accompaniment, and some of them
  are louder than the old rule's choice (the loudest stolen note is now
  volume 32 of 64, from 25).
- **Fade a cut note out instead of cutting it.** A note that takes a
  sounding voice waits while the old one fades: Paula volume 3/4, 2/4 and
  1/4 of what it was, one step a millisecond, then the channel stops, and
  the new note starts a millisecond later, 5 ms after its time in the
  score. The largest step in the old note's signal is a quarter of a cut's
  (12 dB smaller). Only notes that take a sounding voice are delayed; a
  free voice starts at once. It costs no extra interrupt (the player already runs every
  millisecond), and it gives Paula a stopped millisecond before the
  channel restarts, which a 68000 player needs anyway.

Rejected, with the numbers that decided it:

- **Eight voices mixed in software into four channels.** Run with eight
  voices (same rules otherwise), the nocturne still cuts 116.6 restrikes and
  75.8 steals a minute while held: it rings beyond eight voices too.
  BWV 846 would fall to 1.4 a minute. Mixing two voices into each channel
  at about 11 kHz, with a resampling step and a volume table per output
  sample, is about 88,000 voice samples a second, of the order of a third
  of the 68000, with nearest-neighbour resampling in place of Paula's
  exact periods. The nocturne does not repay that.
- **The treble-loop fix from step 3** (normalise each loop on its own and
  lower the voice's volume at the loop start). The loops would gain 6 to
  28 dB (x2 to x25), so a note's Paula volume would fall by the same factor
  at its loop: 564 of the nocturne's 1,498 notes and 303 of BWV 846's 1,925
  would go to Paula volume 0 at their loop start, and 842 and 1,079 more to
  volume 1 or 2. That would cut notes short, the problem being fixed. Not
  applied.

The model now runs a millisecond at a time, in the order the 68000 player
does (fades, then the score's events, then the frame tick), and its voice
log has one more column, `out`, Paula's volume register, which differs from
the note's volume while a cut fades.

Re-rendered for Stacey (host tier, same settings as step 3):

- after: `runs/exp004/nocturne-op9-2.wav`, `runs/exp004/bwv846.wav` and
  their `-a500-filter` versions;
- before, for comparison: the same names in `runs/exp004/before/`.

### 2026-11-07: procedure steps 4 and 5, the 68000 player (machine tier)

Everything here ran on Amiberry 8.5.0 on the Mac, on the `a500` machine:
Kickstart 1.2, a 68000 at the NTSC clock, OCS, 512 KB chip plus 512 KB
slow RAM, cycle-exact. Nothing has run on the real A500 yet.

#### The player

`examples/piano/player.s`, 68000 assembly for vasm (Motorola syntax),
built by `make piano-disk` (`amiga-env piano-disk
examples/piano/piano.toml`) from the data `make piano` writes to
`runs/exp004/m68k/`: the key table (88 keys, 12 bytes each: sample, period,
level, held and release factors, attack ticks), the sample table, the
velocity table, the samples and both scores, all INCBINed, big-endian
(`m68k.py`). It implements the changed model in integer arithmetic:

- **Timing.** CIA-B timer A, taken through `ciab.resource`
  (`AddICRVector` returned 0: the timer is free on 1.2), runs continuously
  with a latch of 715, an interrupt every 716 E-clock ticks (1.000127 ms).
  Each interrupt is one millisecond of the model: fades, then the score's
  events due, then the frame tick if one falls on it.
- **Frame ticks are counted in milliseconds, not taken from VBlank.** Tick
  k falls at k * 1000 // 60 ms, as in the model, kept with a 16-or-17
  counter and a remainder. The NTSC VBlank is not locked to the CIA timer
  (Amiberry reports 59.83 Hz), so a VBlank tick would fall a millisecond
  earlier or later than the model's now and then, and the logs could not
  match. The decay runs 0.3% faster than it would at 59.83 Hz.
- **Score reader, voice choice, volumes, decay, fades.** As the model:
  the same byte stream, the steal order (key down, volume, note number),
  `max(256, velocity[v] * level >> 8)`, `(volume * factor) >> 16` with one
  MULU and a SWAP, and the 3/4, 2/4, 1/4, stop, start fade.
- **Paula.** A start writes AUDxLC and AUDxLEN for the whole sample, the
  period and volume, clears and enables the channel's audio interrupt and
  sets its DMA bit. The audio interrupt (taken with `SetIntVector`) writes
  the loop's start and length, which Paula takes when the sample ends, and
  turns that channel's interrupt off until its next note. A stop clears the
  DMA bit and sets volume 0.
- **The system.** The player stays inside the OS. It Forbid()s task
  switching, takes CIA-B timer A and the four audio interrupt vectors,
  drives Paula directly, and busy-waits for the end. At the end it stops
  the timer, gives back the vector and the interrupts, silences Paula,
  Permit()s and prints its measurements to the CLI. It does not disable
  interrupts, so the system's own (VBlank, keyboard, disk) still run.
- **Samples in chip RAM.** The samples are a `data_c` section. Kickstart
  1.2's LoadSeg honoured the chip flag in the hunk header: the samples
  loaded at `$12920` and `TypeOfMem` reported chip memory. The player
  checks this at run time and would copy them into chip RAM from
  `AllocMem(MEMF_CHIP)` otherwise; that path did not run.
- **The piece.** One program holds both scores; its argument chooses (a
  first letter b is BWV 846). Each floppy's startup-sequence runs `piano
  <piece>`: `build/piano/nocturne-op9-2.adf` and `build/piano/bwv846.adf`,
  and the test builds `...-log.adf`. Each OFS floppy holds the program in
  738 of its 1,756 free blocks.
- **Status for the host.** The player keeps a status block at `$100`
  (unused 68000 vectors): a magic word, its state, where its log is, where
  the samples are, and its measurements. The host polls it with `READ_MEM`.

#### Memory

| Part | Bytes | Where it loaded |
| --- | --- | --- |
| Samples (chip hunk) | 328,796 | chip RAM, `$12920` |
| Tables, both scores, interrupt structures (data hunk) | 23,044 | anywhere |
| Code | 2,548 (2,696 in the test build) | anywhere |
| Variables (BSS) | 732 | anywhere |
| Voice log, test build only (AllocMem) | 400,000 | slow RAM, `$C0FC98` |

Chip RAM holds only the samples: 328,796 bytes, against the 389,120-byte
budget of step 2, which also counted the score, tables and program.

#### The voice logs: identical

The test build (`LOG=1`) writes, on every frame tick, the same record the
model writes for each voice: key, sample, period, volume and Paula volume,
6 bytes, 24 a tick. `amiga-env piano-run examples/piano/piano.toml PIECE
--log` boots it headless with warp on, waits for the status to say done,
reads the log back with `READ_MEM` a long at a time (350 KB in 2.5 s), and
compares it with the model's `runs/exp004/m68k/PIECE.log`.

| Piece | Model ticks | Emulator ticks | Result |
| --- | --- | --- | --- |
| Nocturne Op. 9 No. 2 | 13,380 | 13,380 | identical, every byte, the whole piece |
| BWV 846 | 14,420 | 14,420 | identical, every byte, the whole piece |

The first run matched; no difference had to be fixed. The log records
what the player wrote to Paula's registers and when, at frame resolution,
not Paula's output.

#### CPU time

Measured by the player itself with CIA-B timer A's count: at the end of
each interrupt, the E-clock ticks since the timer ran out (which includes
exec's and ciab.resource's dispatch before the handler starts), and the
time spent in each audio interrupt. A frame here is a model tick, 16 or 17
ms; 11,932 E-clock ticks is 1/60 s.

| Build, piece | Player share of the 68000 | Average per frame | Worst frame | Worst millisecond | Of which dispatch |
| --- | --- | --- | --- | --- | --- |
| Player, nocturne | 17.3% | 2,069 ticks | 4,450 (37%) | 556 of 716 | 9.4% |
| Player, BWV 846 | 17.5% | 2,085 ticks | 3,904 (33%) | 571 of 716 | 9.4% |
| Test build, nocturne | 18.1% | 2,158 ticks | 4,523 (38%) | 639 of 716 | 9.4% |
| Test build, BWV 846 | 18.2% | 2,174 ticks | 3,995 (33%) | 660 of 716 | 9.4% |

The player rows come from the real-time audio runs, the test build rows
from the warp runs. The worst frame moves by a few ticks between runs of
the same build (4,443 and 4,450 for the nocturne) as the system's own
interrupts fall differently; the logs do not change.

More than half the cost is getting called: 67 E-clock ticks (about 670
CPU cycles) from the timer running out to the handler, a thousand times a
second, 9.4% of the CPU. Most milliseconds have nothing to do, and the
handler returns at once on those. Only about 100 milliseconds a second
have work (events, ticks or fade steps: 21,454 of the nocturne's 222,984).
A one-shot timer set to the next millisecond with work would take that to
about 1% of the CPU, with the same log; not done, because 17% leaves the
68000 most of its time. The worst millisecond used 660 of its 716 ticks:
one that overran would delay the next interrupt, not lose it, unless it
overran by a whole period.

#### What the screen shows

The player prints to the boot CLI window: the experiment, the piece,
where the samples are, "Playing...", and at the end the frame count and
its CPU figures (`runs/exp004/emulator-*-playing.png` and `-done.png`,
looked at). There is no other display while it plays.

#### Audio from the emulator

Amiberry has no sound recording command, but its SDL 3 has the disk audio
driver: with `SDL_AUDIODRIVER=disk` and `SDL_AUDIO_DISK_OUTPUT_FILE`, it
writes what Amiberry plays as 16-bit stereo at 44.1 kHz, in real time.
`amiga-env piano-run examples/piano/piano.toml PIECE --audio` runs the
player that way, with `sound_stereo_separation=10` (the A500 model's
default is 7; a real Amiga separates fully), and drops the 37 s of boot
before the music, less 1 s. The first try quit as soon as the player
finished and lost the nocturne's last 5 s, so a run now plays 15 s of
silence before it quits.

- `runs/exp004/emulator-nocturne-op9-2.wav` (232 s)
- `runs/exp004/emulator-bwv846.wav` (250 s)

They include Amiberry's A500 filter emulation (`sound_filter=emulated`,
`standard`) and `sound_interpol=anti`. The power LED is on while the
player runs (CIA-A port A read `$FC`: bit 1 low), and on an A500 that also
switches on the LED low-pass filter; the player leaves it as the system set
it. Against the host render without a filter, the emulator's level is
within 0.5 dB (RMS -30.0 and -29.5 dBFS for the nocturne, -27.3 and -26.9
for BWV 846), and the two loudness envelopes, in 10 ms frames, correlate at
0.98 and 0.99 over 10 s near the start once aligned. That says the notes are at
the same times and levels, not that the sound is the same; Stacey judges.

To listen on the emulated A500 in a window, from the project folder:

```sh
uv run amiga-env a500 build/piano/nocturne-op9-2.adf
uv run amiga-env a500 build/piano/bwv846.adf
```

The music starts about 37 s after the boot (the floppy loads 355 KB).
`make piano piano-disk` rebuilds the floppies from the media.

#### Where the hypotheses stand

- Hypothesis 1 holds at the machine tier: the samples take 328,796 bytes
  of chip RAM, and the program, tables and scores another 26,324 bytes
  outside it.
- Hypothesis 2 is refuted as stated (Stacey, above). The changed stealing
  moves the cuts from the melody to the pedalled accompaniment and fades
  them; whether that is acceptable is for her ears.
- Hypothesis 3 holds at the machine tier: the 68000 player's voice log is
  the model's to the byte, for the whole of both pieces. The host model's
  WAV is therefore a fair preview of the register writes; whether it is a
  fair preview of Paula's sound (filters, the hold between samples) is what
  the emulator WAVs and then the real A500 answer.

Next: Stacey listens to the host renders before and after the change and
to the emulator WAVs; then the floppies on her A500, where the CPU figures
are printed on the screen at the end of each piece.

### 2026-11-07: one floppy, ten pieces and a menu (host and machine tier)

Stacey asked for one floppy with both pieces, more if they fit, and a very
simple way to choose. Machine-tier runs here are Amiberry 8.5.0 on the Mac,
the `a500` machine as in steps 4 and 5. Nothing has run on the real A500
yet.

#### More pieces: the survey (host tier)

`amiga-env piano-survey examples/piano/piano.toml` (`build.survey`,
`survey.py`) takes every MAESTRO performance of 2 to 6 minutes (501 of
1,276), measures keys held and strings ringing, and runs the player model
over it with this piano to count the notes it cuts while their key or the
pedal still holds them (`clips.report`). Its table is
`runs/exp004/survey.csv`. The Salamander layer is now fixed at velocity 64
in the recipe (it was the median of the pieces' velocities, which was 64),
so a new piece does not change the samples; the two original pieces'
clipping numbers below are the ones recorded above.

"Ringing" counts the distinct keys held or kept sounding by the pedal; the
percentiles are weighted by time. The survey reproduces the table at the
top of this file for keys held, the ringing maximum and the pedal share,
but gives the nocturne's ringing 95th percentile as 31, not 21. The script
behind that first table was not kept, so I cannot say which is the
earlier method's slip; the survey's is in code, with tests. (Later: the
script was kept after all; see "the first polyphony table's method"
below.)

The ten pieces, in menu order. "Cut" is notes cut while held at Paula
volume 4 or more, a minute; "melody" is the part of those stolen while
their key was down.

| Key | Piece (MAESTRO performance) | Length | Held 95% / max | Ringing 95% / max | Pedal | Cut a minute | Melody a minute | Why |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Chopin, Nocturne Op. 9 No. 2 (2011) | 221 s | 4 / 6 | 31 / 43 | 93% | 281.9 | 7.3 | the target, kept |
| 2 | Bach, Prelude and Fugue in C major, BWV 846 (2014) | 240 s | 5 / 8 | 5 / 11 | 10% | 37.3 | 29.0 | the control, kept |
| 3 | Bach, Duet in E minor, BWV 802 (2009) | 132 s | 2 / 4 | 2 / 4 | 1% | 0.0 | 0.0 | the lowest of all 501: two voices, nothing cut |
| 4 | Scarlatti, Sonata in D major, K. 145 (2014) | 206 s | 3 / 5 | 3 / 8 | 18% | 16.3 | 1.5 | Scarlatti's lowest; clear two-part writing |
| 5 | Haydn, Sonata in F major, Hob. XVI:23, I (2015) | 208 s | 3 / 5 | 3 / 7 | 5% | 11.8 | 2.0 | Haydn's lowest |
| 6 | Mozart, Sonata in B-flat major, K. 333, I (2017) | 302 s | 3 / 6 | 4 / 8 | 7% | 14.5 | 1.6 | Mozart's lowest; lyrical |
| 7 | Beethoven, Sonata No. 18, Op. 31 No. 3, I (2008) | 352 s | 5 / 7 | 7 / 11 | 26% | 78.0 | 21.6 | Beethoven's lowest; no Beethoven under 78 |
| 8 | Schubert, Sonata in B-flat major "D. 962" (2009) | 216 s | 4 / 7 | 4 / 7 | 4% | 31.3 | 24.7 | Schubert's lowest by three times |
| 9 | Chopin, Nocturne in C-sharp minor, Op. posth. (2014) | 243 s | 4 / 7 | 14 / 23 | 82% | 136.3 | 6.7 | lyrical; half the target's cuts, and the melody is rarely stolen |
| A | Debussy, Prelude, Book I No. 6, "Des pas sur la neige" (2018) | 251 s | 5 / 8 | 9 / 14 | 80% | 26.3 | 13.9 | Debussy's lowest by 3.6 times; slow and sparse |

Considered and left out: Schumann's lowest, the Romances Op. 28 Nos. 2 and
3 (2011), cuts 153.5 a minute with 46.8 of them melody; Brahms's Intermezzo
Op. 118 No. 6 (171.4), Rachmaninoff's Moment Musical Op. 16 No. 3 (180.6),
Liszt's lowest, "Feux Follets" (189.0), and Mendelssohn's Rondo Capriccioso
(323.8). Bach had 103 candidates and filled the 27 lowest places; I kept
to two Bach pieces so the other composers have room. A second Chopin went
in over Schumann because its melody survives (6.7 against 46.8 a minute).

The menu text is MAESTRO's composer (the surname) and title, in ASCII, as
the catalogue has them, including three of its slips: BWV 846 is in the
first book of the Well-Tempered Clavier, not "WTC II"; Haydn's title says
"Sonata in in F Major"; and D. 962 is not a Schubert sonata number (D. 960
is his B-flat sonata), so which piece that performance is, I cannot say
without listening. A title that does not fit 56 characters loses its last
clauses: Haydn's and Beethoven's lose the movement.

#### The floppy

`make piano-disk` (`disk.py`) writes `build/piano/piano.adf` and the test
build `build/piano/piano-log.adf`. Both are OFS with the 1.x bootblock,
labelled `Piano`:

| Path | What | Blocks |
| --- | --- | --- |
| `piano` | the program: code, tables, and the samples as a chip hunk (335,328 bytes) | 698 |
| `scores/index` | one line a piece: the score's path, a space, its title (748 bytes) | 2 |
| `scores/01-nocturne-op9-2.score` to `scores/10-debussy-neige.score` | the ten scores, 3,031 to 19,058 bytes, 113,609 in all | 248 |
| `s/startup-sequence` | `piano` | |
| All, with the root, bitmap and folders | | 955 used, 803 free of 1,758 |

The 803 free blocks hold about 391,000 bytes of scores. These ten average
2,875 bytes a minute of music, so about 136 minutes more would fit, some
32 more pieces of this length. The menu has keys for 34 pieces (1 to 9
and the letters without Q), 24 more than now, so the keys run out before
the disk does. Only one score is in memory at a time.

Adding a piece is a line in `examples/piano/piano.toml`, `make piano`
(which converts it and runs the model) and `make piano-disk`. The program
is reassembled by that command but does not change.

#### The player's menu

The program (`examples/piano/player.s`) now holds only the samples and
tables. At the start it loads `scores/index` and splits it into titles.
`piano` with no argument shows the menu in the boot CLI window; `piano 9
a` plays pieces 9 and A and ends, with no menu.

- **Single keys on 1.2.** `SetMode` is a 2.0 call. The menu opens `*`, the
  CLI's window, and puts its console handler in raw mode with an
  `ACTION_SCREEN_MODE` packet (-1 raw, 0 cooked), sent from the process's
  own message port. `Read` of one byte then returns each key with no echo
  and no Return. The details are in `research/toolchain.md`.
- **Choosing.** 1 to 9 and A play pieces 1 to 10 (a or A); Q quits and
  puts the console back in cooked mode. Other keys are ignored: a space and
  a z were, in the test below.
- **Loading.** The chosen score is read with `Open`, `Seek` to the end and
  back (which gives its size), `AllocMem(size + 1, MEMF_PUBLIC |
  MEMF_CLEAR)` and one `Read`, played from there, and freed with `FreeMem`
  when the piece ends or stops. With slow RAM fitted it loads at
  `$C0xxxx`.
- **Playing and stopping.** Each piece starts from a cleared state (voices,
  time, score, log and the status block's measurements). The interrupts
  are the same code as before. The task no longer `Forbid()`s and spins:
  it sleeps in `WaitForChar` on the raw window for 20 ms at a time and
  checks whether the interrupts have finished the piece. Any key stops the
  piece (CTRL-C too), and the result line says "Stopped after N frames".
- **What it prints.** Each piece's title, where its score loaded, free
  memory while it plays, then the frame count and CPU figures as before,
  then the menu again. The boot CLI window wraps after 61 characters, so
  every line is at most 60, and the menu and the last piece's figures fit
  in the window together.

| Screenshot (looked at) | Shows |
| --- | --- |
| `runs/exp004/emulator-menu-menu.png` | the Release 1.2 banner, the player's banner, the ten titles, Q Quit and "Press a key:" |
| `runs/exp004/emulator-menu-log-scarlatti-k145-playing.png` | Scarlatti chosen with 4: title, score at `$C6CEB8`, free memory, "Playing; press any key to stop." |
| `runs/exp004/emulator-menu-debussy-neige-done.png` | Debussy chosen with A, finished: its figures above the menu, shown again |
| `runs/exp004/emulator-menu-stop-nocturne-op9-2-done.png` | the nocturne stopped with Return: "Stopped after 873 frames" and the menu |

#### The voice logs through the menu

`amiga-env piano-run examples/piano/piano.toml PIECE... --log` now boots
the one test floppy, waits for the menu, presses each piece's key with
Amiberry's `SEND_KEY` (Amiga raw key codes; verified here, see the
amiberry skill), waits for the piece to end and the menu to return, reads
the piece's log, and compares it with the model's. At the end it presses
Q. One boot played all ten in menu order:

| Key | Piece | Model ticks | Emulator ticks | Result | Player share of the 68000 | Free while playing: chip / other |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Nocturne Op. 9 No. 2 | 13,380 | 13,380 | identical, every byte | 18.5% | 119,496 / 63,440 |
| 2 | BWV 846 | 14,420 | 14,420 | identical, every byte | 18.6% | 119,496 / 61,560 |
| 3 | BWV 802 | 7,918 | 7,918 | identical | 18.3% | 119,496 / 67,088 |
| 4 | Scarlatti K. 145 | 12,408 | 12,408 | identical | 18.7% | 119,496 / 61,512 |
| 5 | Haydn Hob. XVI:23 | 12,517 | 12,517 | identical | 18.8% | 119,496 / 60,800 |
| 6 | Mozart K. 333 | 18,133 | 16,666 | identical for the 16,666 ticks the log holds | 18.6% | 119,496 / 56,616 |
| 7 | Beethoven Op. 31 No. 3 | 21,179 | 16,666 | identical for the 16,666 ticks the log holds | 18.6% | 119,496 / 54,072 |
| 8 | Schubert "D. 962" | 13,073 | 13,073 | identical | 19.3% | 119,496 / 56,040 |
| 9 | Nocturne in C-sharp minor | 14,558 | 14,558 | identical | 18.0% | 119,496 / 66,480 |
| A | Debussy, "Des pas sur la neige" | 15,041 | 15,041 | identical | 17.8% | 119,496 / 70,104 |

The test build's log is 400,000 bytes (277 s), so the two pieces longer
than that were compared over their first 277 s. Making it longer needs
more than the slow RAM has left: "other" free memory in the test build is
about 60 KB with the log allocated.

A second boot (`--stop-after-s 10`, name `emulator-menu-stop`) chose
BWV 802 and then the nocturne and pressed Return about 15 s into each (the
host polls once a second in warp): both stopped ("stopped by a key" in the
status), their logs matched the model's for the 906 and 873 ticks they
played, and the nocturne, started after a stopped piece, began from a
clean state.

Without the menu: at the CLI after Q, typing `piano a` (with `SEND_KEY`)
played Debussy and ended. Its log matched the model's except for its first
6 bytes, because the host read it after the program had ended and freed it:
the first 8 bytes held exec's free-memory header (next 0, size 473,440).
An earlier try, `piano 9 a`, played only A: the player read the first
argument to decide between the menu and the arguments and then lost it.
Fixed, and the nocturne and BWV 846 were played again through the menu
with the fixed build (`emulator-menu-final-log`): both identical, every
byte.

#### Memory at run time

From the status block while a piece plays (`AvailMem` after the score is
loaded):

| Build | Chip RAM free | Other memory free |
| --- | --- | --- |
| Player, Debussy playing (`emulator-menu.json`) | 119,496 bytes | 470,272 bytes |
| Test build, with its 400,000-byte log | 119,496 bytes | 54,072 to 70,104 bytes, by score |

Chip RAM holds the samples, 328,794 bytes at `$12920`, where LoadSeg put
the chip hunk; the score, the index and the program's other hunks are in
slow RAM. The largest score is 19,058 bytes.

#### CPU, with the task asleep

The share of the 68000 used by the player's interrupts rose a little: the
nocturne's test build was 18.1% in step 4 and is 18.5% now, BWV 846's
18.2% and 18.6%. The worst frame is about the same (BWV 846: 3,995 and
3,999 E-clock ticks). The difference is in when the handlers get called,
not what they do, since the logs are identical: with the task asleep in
`WaitForChar` instead of spinning in `Forbid`, other tasks and the
console's timer requests run during the piece, and the dispatch to the
CIA handler is measured from the timer running out. That is a guess; I
have not measured it further.

#### Audio through the menu

`amiga-env piano-run examples/piano/piano.toml debussy-neige --audio` boots
the player floppy in real time, presses A, records the piece, presses Q,
and writes `runs/exp004/emulator-menu.wav` (262 s; the 39.7 s before the
music are dropped). Against the host render `runs/exp004/debussy-neige.wav`
(no filter): RMS -38.7 and -38.3 dBFS, peak -12.6 and -12.3 dBFS, and the
loudness envelopes in 10 ms frames correlate at 0.996 over the first 30 s
once aligned and 0.963 over the whole piece. As before, that says the
notes are at the same times and levels, not that the sound is the same.

#### To play it in a window

From the project folder:

```sh
uv run amiga-env a500 build/piano/piano.adf
```

The menu appears about 37 s after the boot. `make piano piano-disk`
rebuilds the floppy from the media. The two one-piece floppies of step 4
are gone; this floppy replaces them.

#### Where the hypotheses stand

Unchanged from step 5. Hypothesis 3 holds through the menu path for all
ten pieces (eight in full, two over their first 277 s): loading a score
from the floppy at run time, raw console input and a sleeping task changed
nothing in the register writes.

Next: Stacey chooses pieces from the menu in the emulator, and then boots
the floppy on her A500, where each piece's CPU figures and free memory are
printed when it ends.

### 2026-11-07: the first polyphony table's method (host tier)

The polyphony columns of the table at the top of this file came from
`runs/exp004/scripts/first-table-poly.py` (not tracked; Stacey kept it).
It takes the counts after every MIDI message, so its percentiles are
weighted by events, and the events include the pedal and other control
messages: the nocturne has 2,901 sustain messages against 1,498 notes, and
most of them fall while the pedal is changing. The survey
(`survey.polyphony`) weights each count by how long it lasts. That is why
the nocturne's ringing 95th percentile is 21 in the first table and 31 in
the survey. The survey's measure, weighted by time, is the one this
experiment uses from "More pieces" on.

### 2026-11-07: the player's own screen (host and machine tier)

Stacey's design (2026-11-07): replace the CLI menu with a screen. The
title picture with the song list drawn into it, the playing piece's line
in gold, five scopes on the floor, a click or a key to choose, and full
credits on the disk. Machine-tier runs are Amiberry 8.5.0 on the Mac, the
`a500` machine as before (Kickstart 1.2, 68000 at the NTSC clock, OCS,
512 KB chip plus 512 KB slow RAM, cycle-exact). Nothing has run on the real
A500 yet.

#### The picture (host tier)

`examples/piano/art/piano-title-master.png` (1536x1024, generated with
OpenAI's image API from `piano-title.json`, Stacey's files) becomes the
screen in `tools/amiga_env/piano/picture.py`, as Stacey specified: the
left 4:3 area (x 0 to 1365), Lanczos to 320x200, gamma 0.8, k-means of 13
colours weighted by 1 + 6 x luminance / 255 (seed 1, 40 iterations), each
colour snapped to OCS 12-bit (multiples of 17), the distinct ones sorted by
luminance, and Floyd-Steinberg over the whole picture. Its pixels are
identical to the prototype's `runs/exp004/art/p3-fs.png` (mode `all`):
none of the 64,000 differ. It takes about 1 s on the Mac. The recipe's
`[screen.picture]` table holds the settings.

| Registers | Colours |
| --- | --- |
| 0 to 12, the picture | `$001 $012 $013 $112 $211 $223 $421 $136 $333 $654 $864 $B95 $EDB` |
| 13, all list text | `$EDB`, the picture's ivory; `$B95`, the picture's gold, on the playing line |
| 14, the four voice traces | `$5BC`, a soft cyan |
| 15, the mixed trace | `$DB8`, a pale gold |

All 13 colours survived the snapping, so registers 0 to 12 are full.

#### The list and the attribution (host tier)

`screen.py` draws the text into the picture before it is written, in
register 13. The font is drawn for this project as text,
`examples/piano/font.txt` (`font.py` reads it): 78 glyphs, 9 rows (capitals
7, lower case 5, descenders 2), proportional, letters 1 to 5 pixels wide
(3.9 on average) plus a 1-pixel gap. Not Topaz. Its licence: it is part of
this repository, which has no licence file yet, and the disk's `Credits`
shares it on the disk's terms (CC BY-NC-SA 4.0). Choosing the repository's
licence is Stacey's decision.

The titles are written in the recipe (`title` in each `[[piece]]`), no
longer taken from MAESTRO's catalogue. The rows are the lines' tops on the
screen; the player gets them in `screen.i` (`line_tops`).

| Key | Row | Title on the screen | Width (pixels of 128) | MAESTRO's title |
| --- | --- | --- | --- | --- |
| 1 | 8 | Chopin  Nocturne Op. 9 No. 2 | 123 | Nocturne Op. 9 No. 2 in E-flat Major |
| 2 | 19 | Bach  Prelude & Fugue in C | 117 | Prelude and Fugue in C Major, WTC II, BWV 846 (wrong book: BWV 846 is Book I) |
| 3 | 30 | Bach  Duet in E minor | 91 | Duet in E Minor, BWV 802 |
| 4 | 41 | Scarlatti  Sonata K. 145 | 101 | Sonata in D Major, K. 145 |
| 5 | 52 | Haydn  Sonata Hob. XVI:23, I | 125 | Sonata in in F Major, Hob. XVI: 23, I. Allegro moderato ("in in") |
| 6 | 63 | Mozart  Sonata K. 333, I | 106 | Sonata in B-flat Major, K. 333, I. Allegro |
| 7 | 74 | Beethoven  Op. 31 No. 3, I | 112 | Sonata No. 18 in E-flat Major, Op. 31 No. 3, First Movement |
| 8 | 85 | Schubert  Sonata D. 962 | 103 | Sonata in B-flat Major D. 962 |
| 9 | 96 | Chopin  Nocturne in C# minor | 124 | Nocturne in C-Sharp Minor, Op. Posth. |
| A | 107 | Debussy  Des pas sur la neige | 127 | Prelude No. 6, Book I, "Des pas sur la neige" |

**Schubert "D. 962" is not verified.** D. 962 is not a Schubert sonata in
the Deutsch catalogue as I know it (his B-flat sonata is D. 960), and the
performance is 216 s, much shorter than any movement of D. 960 would
suggest. The screen shows MAESTRO's label, shortened; which piece the
recording is needs someone to listen to it. I have not guessed a title.

Two lines of attribution follow the list, in the same font and register:
"Piano: A. Holm, CC BY 3.0" at row 132 and "MAESTRO, CC BY-NC-SA 4.0" at
row 143. Stacey's longer examples (160 and 140 pixels) did not fit the 128
pixels right of the piano.

Checked against the picture: the list sits on the dark wall right of the
piano (columns 190 to 318; the piano's edge is at column 186) and the
attribution on the dark floor. `screen.make` refuses text over any picture
pixel brighter than luminance 50 (the wall's blue speckles, `$136`, are 46;
the piano's highlights are far brighter). That check moved the attribution
down: at rows 126 to 130 the floor meets the wall in a line of `$333`.
`runs/exp004/title-preview.png` shows the result at 4:3 (looked at).

#### The disk

`make piano-disk` now also writes the picture as `title.ilbm` and copies
`examples/piano/Credits` to the disk as `Credits` (lines of at most 60
characters, so `type Credits` reads in the boot CLI window). `Credits`
has the full notices: Salamander Grand Piano V3 by Alexander Holm, CC BY
3.0, the source and licence URLs and what was changed; MAESTRO v3.0.0 by
Google LLC (Magenta), recorded at the International Piano-e-Competition,
CC BY-NC-SA 4.0 with its URL, changed into our score format, so the disk
and its scores are shared under CC BY-NC-SA 4.0 and not for commercial
use; the picture, generated with OpenAI's image model from the project's
own description; and the font.

**The picture's format: an uncompressed IFF ILBM** (`BMHD` 320x200, 4
planes, no masking, no compression, aspect 10:11; `CAMG` 0; `CMAP` of 16;
`BODY` with each row's four planes interleaved), 32,116 bytes. Chosen over
raw planes because other Amiga programs can open it, at the cost of a
short chunk walk in the player; uncompressed, so the player copies rows and
does not need a ByteRun1 decoder. `picture.read_ilbm` reads it back in the
tests.

| Path | Bytes | |
| --- | --- | --- |
| `piano` | 338,572 (704 blocks) | the program, 3,244 bytes more than the menu's |
| `title.ilbm` | 32,116 | |
| `Credits` | 1,721 | |
| `scores/...` | as before | |
| Disk | 1,033 blocks used, 725 free | the test build's disk: 1,034 and 724 |

#### The player (machine tier)

`examples/piano/player.s` keeps the interrupts as they were (one
millisecond of the model each, the same log) and replaces the CLI menu:

- **The screen.** `OpenScreen` with a `NewScreen` of 320x200, 4 planes,
  lowres, `CUSTOMSCREEN | SCREENQUIET`; a full-screen `BACKDROP |
  BORDERLESS | ACTIVATE | RMBTRAP` window with IDCMP `MOUSEBUTTONS |
  RAWKEY`; `ShowTitle(FALSE)`. The program reads `title.ilbm` with dos,
  finds `BMHD`, `CMAP` and `BODY`, refuses anything but 320x200, 4 planes
  and no compression, copies the rows into the screen's planes and loads
  the 16 colours with `LoadRGB4`. The planes are Intuition's, in chip RAM.
- **Choosing.** A left click (`SELECTDOWN`) at x 186 or more, on a line's
  11 rows, chooses that piece; its key does too (1 to 9, then the
  letters without Q, as many as there are pieces: A for the tenth; raw
  codes from `keys.i`, which `piano-disk` writes); Esc or Q quits. A
  choice while a piece plays stops it (its interrupts, Paula and score
  given back, "stopped" in the status) and starts the new one. After Esc
  or Q the player closes its window and screen and the boot CLI is back
  with its prompt (screenshots `emulator-screen-*-end.png`).
- **The gold line: a user copper list, verified on 1.2.** `UCopperListInit`
  for 5 instructions: WAIT the line's first row, MOVE `COLOR13` `$B95`,
  WAIT 9 rows on, MOVE `COLOR13` `$EDB`, CEND; set into the screen
  viewport's `UCopIns` under `Forbid`, then `MakeScreen` and
  `RethinkDisplay`; the old list is freed after a `WaitTOF`. How it was
  verified: the copper list at `COP2LC` (read with Amiberry's
  `GET_COPPER_STATE` and `READ_MEM`, decoded on the host) held `WAIT
  74,0`, `MOVE $19A=$0B95`, `WAIT 83,0`, `MOVE $19A=$0EDB` for line 3 (row
  30; the display starts at line 44), and every screenshot of a piece
  playing shows its line in gold and the others ivory. Details in
  `research/toolchain.md`.
- **The scopes.** Four voice scopes, 36 columns each, at columns 8, 50, 92
  and 134, and the mix, 132 columns from column 180, all centred on row
  174 in the floor band (rows 152 to 196, checked against the picture:
  dark floor, the golden reflection under the left ones). Paula cannot be
  read, so the player now records, when it starts a channel, what Paula
  plays: the sample, its period and the millisecond (`V_PSAMPLE`,
  `V_PPERIOD`, `V_PSTART`), and clears the sample when it stops one. The
  task copies those and each voice's Paula volume, and works out where
  Paula is the tracker way: the timer's period is exactly 3,580 Paula
  clocks, so (ms since the start) x 3,580 / period is the samples played,
  through the whole sample once and then round its loop. A column is 960
  Paula clocks (3 samples at period 320); a voice's trace is sample x
  volume >> 7, clamped to 16 rows; the mix is half the four voices' sum,
  clamped to 21. Silent voices draw a flat line.
- **The picture under the scopes stays intact.** Decided: keep a copy of
  the band (all four planes, 7,200 bytes, in slow RAM) and put back from
  it. A pixel in register 14 or 15 must set all four planes, so drawing
  over the picture cannot leave it as it was. Copying the whole band back
  (with the blitter, and then with the CPU) and plotting after each
  `WaitTOF` ran at 30 frames a second but tore: screenshots caught the
  mixed scope half drawn (7 of 20 with the CPU version). Now each scope is a unit
  that puts back its own last points (four bytes each, one per plane) and
  plots its new ones; no unit starts while the beam is on the band or
  within 64 lines above it; and the next traces are made, into a second
  buffer, while the beam holds the drawing up. In the audio run 30
  screenshots taken 0.3 s apart all showed every scope whole (`piano-run
  --scope-shots 30`); the cost is the rate, about 20 frames a second.
  The task draws; the interrupts never wait for it.

#### The voice logs through the new screen

| Run | How chosen | Piece | Model ticks | Emulator ticks | Result |
| --- | --- | --- | --- | --- | --- |
| `emulator-screen-log` | keys 1, 2 | Nocturne Op. 9 No. 2 | 13,380 | 13,380 | identical, every byte |
| | | BWV 846 | 14,420 | 14,420 | identical, every byte |
| `emulator-screen-switch` | clicks; the second click 20 s into the nocturne | Nocturne Op. 9 No. 2 | 13,380 | 1,290 (switched) | identical for the 1,290 ticks played |
| | | BWV 846, after the switch | 14,420 | 14,420 | identical, every byte |

So the screen, the copper list, the scopes and the switch did not change
the music's register writes. Both runs used warp; the audio run below is
in real time.

#### The mouse through Amiberry's socket

`SEND_MOUSE dx dy buttons` works: it is relative, and 50 counts moved the
pointer 12 lowres pixels. `piano-run --click` steers by reading the
pointer's position from the player's window (`wd_MouseX`, `wd_MouseY`; the
status block gives the window's address), moving, and reading again, then
presses and releases button 1. It clicked at (202, 12), (202, 23) and
(202, 34), each a line's middle row, and the status counted each click.
`SEND_MOUSE_ABS` replied "Absolute mouse input rejected (check
coordinates, focus, and active tablet_mode)"; I did not pursue it. Recorded
in the amiberry skill (plugin 0.6.0).

#### CPU and the scope rate

From the player's own E-clock counts (the scopes' time leaves out the
player's interrupts and the waits for the beam, but includes the system's
other interrupts). A frame is 1/60 s, 11,932 E-clock ticks.

| Run, piece | Player | Scopes | Player and scopes | Scope frames a second | Scope frame: drawing / making traces (average E-clock ticks) | Worst millisecond of the player (of 716) |
| --- | --- | --- | --- | --- | --- | --- |
| log, nocturne | 18.3% | 54.5% | 72.8% | 19.9 | 11,881 / 7,743 | 708 |
| log, BWV 846 | 18.4% | 54.5% | 73.0% | 20.0 | 11,663 / 7,842 | 662 |
| switch, BWV 846 | 18.4% | 54.1% | 72.5% | 19.9 | 12,267 / 7,157 | 664 |
| audio (real time), BWV 802 | 17.4% | 51.8% | 69.2% | 20.1 | 11,751 / 6,695 | 568 |

Per 1/60 s frame that is about 2,200 E-clock ticks for the player and
6,500 for the scopes. The scopes' work for one of their frames is about
19,500 ticks (27 ms), over two frames of the display with the player's
share added, so they come every third frame: 20 a second. The menu's
player took 18.5% (nocturne, test build); with the screen it takes 18.3%.

The worst millisecond is the one figure that rose: 639 and 660 E-clock
ticks of 716 in step 4's test builds, 662 to 708 with the screen. It is measured from
the timer running out, so it includes how late the interrupt was
dispatched. A millisecond that ran over 716 would delay the next
interrupt, not lose it, and the logs stayed identical; but the margin in
the nocturne is now 8 ticks. Restoring the band with the blitter gave 711
in the one nocturne run with it, against 663 in one run with the CPU, so I
dropped the blitter, but two runs do not show that it was the cause. On the
real A500 this is the number to watch.

#### Memory

| Chip RAM (512 KB, 524,288 bytes) | Bytes |
| --- | --- |
| Samples (the program's chip hunk, at `$12920`) | 328,796 |
| The screen's four planes (Intuition's) | 32,000 |
| Free while a piece plays (`AvailMem(MEMF_CHIP)`, with the screen open) | 87,296 |
| Everything else: Kickstart 1.2's own use, the Workbench screen and CLI window, copper lists, the screen's other chip allocations | 76,196 |

With the menu, 119,496 bytes of chip RAM were free while a piece played;
opening the screen took 32,200 of them. The band copy (7,200), the trace
table (16,640) and the score are in slow RAM; other memory free while a
piece plays: 436,392 bytes in the player (BWV 802), about 31,000 in the
test build with its 400,000-byte log.

#### Audio through the screen

`amiga-env piano-run examples/piano/piano.toml bwv802 --audio --click
--scope-shots 30` clicked BWV 802's line, recorded the piece in real time
and pressed Q: `runs/exp004/emulator-screen-audio.wav` (145.5 s; the 44.3 s
of boot are dropped). Against the host render `runs/exp004/bwv802.wav`:
RMS -34.0 and -33.4 dBFS, peak -17.1 and -16.6 dBFS, loudness envelopes
in 10 ms frames correlated at 0.992 over the first 30 s once aligned and
0.948 over the whole piece.

#### Screenshots looked at

| Screenshot | Shows |
| --- | --- |
| `runs/exp004/emulator-screen-switch-idle.png` | the picture, the ten titles and the attribution, all ivory; no scopes; the pointer top left |
| `...-switch-nocturne-op9-2-clicked.png`, `-playing.png`, `-playing-2.png` | the nocturne's line in gold under the pointer; five scopes, different in the two shots taken a moment apart |
| `...-switch-bwv846-clicked.png`, `-playing.png` | after a click on the second line while the nocturne played: Bach's line gold, the nocturne's ivory again |
| `...-switch-bwv846-done.png` | BWV 846 ended: no gold line, no traces, the floor as in the picture |
| `...-switch-end.png` | after Q: the boot CLI with both pieces' figures and the prompt |
| `...-audio-bwv802-playing.png`, `-playing-2.png` | the same in real time |
| `runs/exp004/title-preview.png` | the host's preview of `title.ilbm` |

#### To play it in a window

From the project folder:

```sh
uv run amiga-env a500 build/piano/piano.adf
```

The screen appears about 37 s after the boot. Click a title (or press its
key); Esc or Q quits. `make piano piano-disk` rebuilds the floppy.

#### Where the hypotheses stand

Hypothesis 3 holds through the new screen for both original pieces, in
full, and through a switch: the screen, the user copper list and the
scopes do not change the register writes. Hypotheses 1 and 2 are
unchanged.

Open:

- Schubert "D. 962": Stacey decided on 2026-11-07 to keep MAESTRO's label
  until someone identifies the recording.
- Licence: settled on 2026-11-07. The repository, the player and the font
  are MIT, Copyright (c) 2026 Stacey Vetzal; `Credits` says so.
- The worst millisecond, 708 of 716 in the nocturne: watch it on the real
  A500.
- The scopes run at 20 frames a second. Drawing is about 60% of their
  work; fewer points (a narrower mix) or putting back a scope's bytes once
  instead of once a point would buy 30.

### Stacey's trial of the disk: the lag, unattended play, the filter key (2026-11-07)

Stacey played `build/piano/piano.adf` in an Amiberry window and reported:

> There's considerable lag between clicking a title, and it turning gold
> and starting playing.

> after a period of 15s of inactivity, unless stopped, it plays the next
> tune (starting from the first) - it would be nice if someone could put
> in the disk and it would just play and rotate the music unattended.

She also asked for a key to switch the A500's audio filter, and for two
picture changes: the credits in a dimmer colour of their own, and a
signature.

#### The lag, measured (machine tier, normal speed)

The player now stamps each step of a choice with its vertical blank count
(`ST_CHOSEN_AT` to `ST_FIRST_NOTE_AT`, 1/60 s each), and `amiga-env
piano-run ... --realtime` reports them. Both runs: the A500 profile at its
own speed (no warp), floppy speed 100 (`GET_FLOPPY_SPEED`), choices by
click, the first while nothing played and the others 8 s into the piece
before. Times are milliseconds after the task took the click.

| Piece (score bytes) | Before: line gold | Before: timer starts | Before: first note | After: line gold | After: timer starts | After: first note |
| --- | --- | --- | --- | --- | --- | --- |
| Nocturne Op. 9 No. 2 (9,689), nothing playing | 1,567 | 1,567 | 2,583 | 33 | 33 | 1,050 |
| Schubert (17,093), a switch | 2,933 | 2,933 | 3,917 | 17 | 33 | 1,033 |
| Debussy (3,031), a switch | 1,483 | 1,483 | 2,450 | 33 | 50 | 1,017 |
| BWV 802 (6,047), a switch | 2,367 | 2,367 | 3,333 | 33 | 50 | 1,017 |

Runs `runs/exp004/latency-before.json` (the old player with the stamps
added) and `latency-final.json` (the disk below).

Where the old player's time went:

- **Reading the score from the floppy: 1.35 to 2.87 s**, longer for longer
  scores. The old player loaded each score when it was chosen, then put the
  line in gold. Stacey's hypothesis held.
- **The gold line itself: 67 to 133 ms** after the load (`MakeScreen` 1 to 2
  frames, `RethinkDisplay` under one, then a `WaitTOF`).
- **Stopping the piece before: 117 to 150 ms**, most of it writing the
  stopped piece's results to the boot CLI's window behind the screen.
- **About 1 s from the timer to the first note, in every piece.** That is
  the recordings' own lead-in: each score's first note is at 908 to 1,029
  ms. It is in the MAESTRO data, not in the player, and it remains. Taking
  it out is a change to the score format's input (trim the leading silence
  in `score.py`), which changes every score and model log; I have not
  made it. It is a decision for Stacey.

What changed:

- **Every score loaded at the start** (113,609 bytes, into slow RAM), so a
  choice switches pointers. The line turns gold first, before anything else
  is touched.
- **File sizes from `Examine`.** The first preload, sizing each file with
  `Seek` to its end, took 827 vertical blanks (13.8 s); with `Lock` and
  `Examine` it takes 502 (8.4 s).
- **A switch puts the next line in gold as it stops the old piece**, and the
  stopped piece's results are formatted then but written to the CLI after
  the next piece's timer starts. A click mid-piece went from 250 ms to the
  timer to 33 to 50 ms.
- **A bug found on the way:** `end_piece` kept the line to show in d2, which
  `give_audio` uses, so for a moment after each piece Haydn's line (line 5)
  went gold. Fixed.

Startup: the screen now appears 787 vertical blanks (13.1 s) after the
program starts, against 283 (4.7 s) before: the preload adds 8.4 s to the
boot (the screen came about 37 s after the boot; now about 45 s).

Memory while a piece plays, the player: 87,272 bytes of chip RAM free (as
before: 87,296) and 326,960 of other memory (before: 425,176 to 439,240,
with one score loaded). The test build's voice log is now 362,400 bytes
(15,100 ticks, 251 s, was 400,000) to leave room for the scores; about 35
KB of them go to chip RAM there (52,384 bytes of chip RAM free). Every
log that fitted in 400,000 bytes still fits (the longest, Debussy's, is
360,984). Mozart's and Beethoven's never fitted, and are now cut at 251 s,
not 277 s.

#### Playing unattended

After the screen appears, `rotate_s` seconds (15, in the recipe; written
into the player's `menu.i`) with no input start piece 1; that long after
each piece ends, the next plays, the first after the last. A click or a
piece's key plays that piece now, and the rotation goes on from it. Space
stops the piece and holds the rotation until the next choice. Any other key
press or click restarts the quiet. Esc and Q quit as before. The task waits
in `Wait` on the window's port and an alarm signal sent by a vertical blank
server; nothing spins (research/toolchain.md has the calls).

`amiga-env piano-rotation examples/piano/piano.toml` checked it on the test
build (`runs/exp004/emulator-rotation.json`, the final build):

| Step | Warp | Found |
| --- | --- | --- |
| Boot, touch nothing | off | piece 1 chosen 15.00 s (emulated) after the screen appeared; the host saw it start 15.1 s (wall clock) after it saw the screen |
| Nocturne to its end | on | voice log identical, 13,380 ticks |
| The gap | on | BWV 846 started by the rotation 15.00 s after the nocturne ended, its line gold |
| 20 s into BWV 846, click Debussy (line A) | off | BWV 846 stopped (its 1,309 ticks matched the model); Debussy's line gold in 33 ms, its timer at 50 ms; the rotation's next is piece 1 |
| Debussy to its end | on | voice log identical, 15,041 ticks |
| The wrap | on | piece 1 started by the rotation 15.00 s later |
| 10 s in, Space | off | the nocturne stopped (627 ticks matched); no line gold; the rotation held |
| 60 s of quiet | on | nothing started |
| Key 3 | off | BWV 802 gold and its timer in 17 ms; the rotation's next is Scarlatti |
| BWV 802 to its end, the gap | on | log identical, 7,918 ticks; Scarlatti started 15.00 s after |
| Q | off | the boot CLI with the results |

Warp changes none of these figures: the gaps and latencies are counted in
the emulated machine's vertical blanks. I used warp only after piece 1 had
started by itself, and turned it off for every click, key and log read. No
piece was shortened.

Screenshots looked at (`runs/exp004/emulator-rotation-*.png`): `quiet-01s`,
`-08s` and `-14s` show the list with no gold line and no traces;
`piece-1-by-itself` the nocturne's line gold with five scopes;
`piece-2-by-rotation` Bach's; `clicked-last` Debussy's; `wrap-to-1` the
nocturne's again; `space` and `held-60s` no gold line and an empty floor;
`after-key` Scarlatti's; `end` the CLI.

`piano-run` now follows each piece by its own start (the player's
`ST_STARTS` and the piece number), so a piece the rotation starts by
itself while the host is slow is never taken for the one it chose.

#### The filter key

F switches the A500's audio filter: the task flips CIA-A PRA (`$BFE001`)
bit 1 with one `bchg` (bit clear: filter on, power LED bright; set: filter
off, LED dim), nothing else, never in an interrupt. The player keeps the
bit as it was at the start and puts it back when it quits. F is no longer
a piece key (the piece keys are 1 to 9, then A to Z without F and Q, 33 in
all). The screen does not show the state; the power LED does. A marker on
the screen would need a copper change on rows of its own, and I left that
out.

| Check (machine tier) | Found |
| --- | --- |
| `READ_MEM $BFE001 1` at the start, after F, after F again | 252, 254, 252 (bit 1: 0, 1, 0) |
| After three presses, then Q | 254, then 252: put back |
| BWV 802 with F pressed 20 s in (test build, warp) | voice log identical, 7,918 ticks |
| BWV 802 recorded in real time, F at 10.8 s and 21.3 s: energy at 5 to 12 kHz, as a share of 50 Hz to 12 kHz, 3 s before and after each press | -50.2 dB, then -34.9 dB with the filter off; -33.3 dB, then -52.4 dB with it on again |

`runs/exp004/emulator-filter.wav` is that recording. Amiberry's socket does
not know `sound_filter` as a `GET_CONFIG` key, but the 15 to 19 dB steps
show that its A500 emulates the filter.

#### The picture

The two credit lines are now drawn in `$654`, one of the picture's own
colours (register 9), not register 13, so the copper list that turns
register 13 gold never touches them. `$333` was nearly invisible on the
floor (`runs/exp004/credit-signature-options.png` compares them).
"svetzal" is in the lower right corner in `$136` (register 7), the
picture's lightest blue, its ink one pixel in from the right and bottom
edges (columns 290 to 318, rows 192 to 198); `$223` was too faint. The
scope band reaches row 196, so the mixed scope now ends at column 287 (108
columns, was 132) rather than losing height; `screen.py` refuses a scope
whose columns meet the signature's in the band. Host preview:
`runs/exp004/title-preview.png`; on the emulator, the screenshots above.

#### The disk

`build/piano/piano-new.adf` is the player with all of this. It was written
beside `piano.adf`, not over it, because Stacey's emulator had that one
open.

#### Where the hypotheses stand

Hypothesis 3 holds through the preload, the rotation and the filter key:
every complete log above is identical to the model's, and every cut-short
one matches over the ticks it has. Hypotheses 1 and 2 are unchanged.

Open:

- The recordings' 1 s lead-in: trim it in the scores, or keep it? Stacey's
  decision.
- The preload adds 8.4 s to the boot. Loading the scores after the screen
  appears, during the first quiet, would hide it, at the cost of a slow
  first choice in those seconds.

### A video of the disk playing by itself (2026-11-07)

Stacey asked for one raw, unattended playthrough of `build/piano/piano.adf`
(SHA-1 `8a630dc5...`) for YouTube, with chapters. `amiga-env piano-video
examples/piano/piano.toml` makes it (commands and evidence for the recorder
in `research/emulator.md`, "Recording a run").

#### How it was recorded (machine tier)

Amiberry 8.5.0's own recorder is not compiled in, and the socket's
`FRAME_ADVANCE` runs no frame, so the run went through the release's
libretro core: every emulated frame and every sample, in emulated time. The
core's command line resolves to the same configuration as the a500
profile's (`--dump-config`, differing only in `use_gui`), with full stereo
separation, the emulated filter and 48 kHz sound. Nothing was sent to the
machine. The run was not warped; the core paces itself at about real time
(43.3 min wall for 43.0 min recorded), and the files do not depend on it.

| Check | Found |
| --- | --- |
| Recording | 154,517 frames at 59.826 frames a second (NTSC), 43:02.77, boot to 5 s after piece 10 ended |
| Frames | 752x486, every one emulated and kept; none repeated by the core; frames 0 to 134 (the first 2.2 s) were 752x484 and put on the canvas with 2 black rows |
| Sound | 123,969,930 samples at 48 kHz, 802.325 a frame, steady; no frame without sound after the start |
| 4K master (`runs/video/piano-playthrough-4k.mp4`) | 154,517 frames, H.264 High CRF 16, BT.709, AAC 256 kb/s 48 kHz stereo; 1.05 GB |
| Picture | the 320x200 screen cut from its 640x400 area (the border is the screen's colour 0) and widened with nearest neighbour to 2880x2160 in a 3840x2160 frame |
| Levels | the whole run RMS -29.5 dBFS, peak -7.0; the pieces from -38.6 (Debussy) to -27.0 RMS, peaks -12.5 to -7.0 |
| Digital silence of 20 ms or more within pieces | 14 runs, all at rests: the host model is silent at 10 of them, and quiet (-29 to -53 dBFS) within tens of milliseconds of a rest at the other 4 |

The picture choice: nearest neighbour gives each Amiga pixel exactly 9
columns and 10 or 11 rows and adds no colours; an integer x11 then one area
resample made even rows but blended one row in five; Lanczos softened and
rang. At this size the first two look the same, so the master keeps only
the screen's own colours. Intuition's pointer stays top left, as on the
machine.

#### Sound against picture

Each piece's first note, as sound, measured from the start of the frame in
which the player wrote it, bounds the offset to one frame. In the capture
the ten notes put the sound 20.1 to 21.8 ms early; a 75 s test run gave
-8.1 to +8.6 ms, so the offset comes from the core's start and varies by
run. The master delays the sound by 21 ms; measured again from its own
AAC, the ten notes put it at -0.8 to +0.9 ms. The picture is unchanged.

#### Where each piece starts

Read from the 4K master's own frames (the frame its line turns gold), the
same frame in the lossless capture and in the player's own stamp for all
ten. Times from piece 1's first note (65.339 s into the video).

| Piece | Gold at (video) | Chapter | From the first note |
| --- | --- | --- | --- |
| Chopin: Nocturne Op. 9 No. 2 | 64.320 s (frame 3848) | 1:04 | -1.019 s |
| Bach: Prelude & Fugue in C | 302.477 s | 5:02 | 237.138 s |
| Bach: Duet in E minor | 557.950 s | 9:17 | 492.611 s |
| Scarlatti: Sonata K. 145 | 705.027 s | 11:45 | 639.688 s |
| Haydn: Sonata Hob. XVI:23, I | 926.953 s | 15:26 | 861.614 s |
| Mozart: Sonata K. 333, I | 1150.719 s | 19:10 | 1085.380 s |
| Beethoven: Op. 31 No. 3, I | 1468.088 s | 24:28 | 1402.749 s |
| Schubert: Sonata D. 962 | 1836.239 s | 30:36 | 1770.900 s |
| Chopin: Nocturne in C# minor | 2069.247 s | 34:29 | 2003.908 s |
| Debussy: Des pas sur la neige | 2327.011 s | 38:47 | 2261.672 s |

The screen opened at frame 2951 (49.3 s); the player's screen stamp was 789
vertical blanks, as in the app (788). The first chapter is "Boot and title
screen" at 0:00. Chapters round down, so each begins at or before its gold
line; each first note follows its gold line by 0.7 to 1.1 s, the
recordings' own lead-in.

`runs/video/youtube-description.generated.txt` is the generated draft;
Stacey edits `youtube-description.txt`, which the command never writes.

Open:

- Two boots of the same disk opened the screen 4 frames apart. Each
  recording is measured on its own; why the boot varies is not known.
- The lossless capture is 24.6 GB (FFV1 codes every frame whole). An
  encoder that codes the differences between frames losslessly would be far
  smaller; not tried.

### 2026-11-08: a filter light on the screen (host and machine tier)

Stacey could not tell from the screen whether the audio filter was on, so
the A500 disk now has the light the A3500 piano got the same day (EXP-006):
a 7 by 7 light at columns 1 to 7, rows 192 to 198, and the word "filter" in
the attribution's brown beside it, on the signature's row. The host draws
both (`light.py`, the recipe's `[filter_light]`, now shared with the A3500
recipe, and `light.i`).

All 16 registers are taken here, so the light is drawn in register 14, the
voice traces' colour, and the user copper list changes that register on
the light's rows only: $F42 (lit) while the filter is on, $311 while it is
off, and the trace colour ($5BC) again from row 199. The copper list that
turned the playing piece's line gold now always exists and carries both;
F remakes it. The voice traces reach rows 158 to 190 and the light starts
on row 192; the player fails to assemble if a trace could reach the light,
so the host checks only the mix scope's columns against it.

Checked on the `a500` machine (`runs/exp004/light/`): with piece 1 playing,
three screenshots with F pressed between them showed the light lit, unlit,
lit, with the CIA bit 0, 1, 0, and the voice traces still cyan above it
(looked at). `amiga-env piano-run ... bwv846 debussy-neige --log --click
--switch-after-s 10`: Debussy's voice log identical, BWV 846's identical
tick for tick up to the switch, each line gold in 17 to 33 ms; the player
17.6 to 17.8% of the CPU, 65.7 to 66.0% with the scopes.

### 2026-11-08: a listener's notes, the Schubert, and the attacks (host tier)

A listener wrote to Stacey after the videos: "Some work better than
others." The Haydn and Mozart were the most successful, the Debussy a
surprise, the Chopin lacking, and "is it the attack on the sound that
causes runs to 'stumble' in places?" The listener also named the Schubert:
"the third movement of the B-flat D. 960."

**The Schubert.** MAESTRO's catalogue gives the 2009 recital
`MIDI-Unprocessed_21_R2_2009_01_ORIG` four tracks, labelled "D. 960",
"D. 961", "D. 962" and "D. 963" (tracks 01 to 04). They are the four
movements of D. 960, numbered as if each were its own work. This disk plays
track 03, the third movement (Scherzo), 216 s. The title is now "Schubert
Sonata D. 960, III" in `examples/piano/piano.toml`, for both disks. Its
name (`schubert-d962`) stays, so the run files keep theirs. Both videos
recorded so far show the old label.

**The attacks.** Each sample starts 32 samples before the recording first
passes 1% of its peak (`samples.trim_silence`). That threshold finds the
start of the sound, not the hammer's moment, and the rise after it differs
from recording to recording. Measured over each sample's first 0.3 s (2 ms
envelope; the time to half the attack's peak):

| Samples | Time to half the peak, C4 to C6 (roots 60 to 84) | Whole keyboard |
| --- | --- | --- |
| EXP-004, layer v8 | 2.5 to 11.2 ms; neighbouring roots differ by up to 7.7 ms | 2.5 to 34.3 ms |
| EXP-006, 8 layers | 1.8 to 20.1 ms; at one root the layers differ by up to 18.3 ms (C6) | 1.8 to 34.7 ms |

So a run that crosses from one root's sample to the next (every 3
semitones), or on the A3500 from one layer to the next, starts its notes
unevenly by several milliseconds that the pianist did not play. On the A500
a note that takes a sounding voice is also 5 ms late (the fade), and the
Chopin nocturnes take the most voices. That these are the stumble the
listener hears is inferred, not tested. A test: trim every sample so its
attack reaches half its peak at the same time, render a run both ways, and
listen.
