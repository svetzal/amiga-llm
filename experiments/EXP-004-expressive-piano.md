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
