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
