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

None yet.
