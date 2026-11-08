---
name: piano-video
description: Record one of this repository's piano disks playing by itself and prepare it for Stacey to publish on YouTube. Use when Stacey asks for a video, a recording, a playthrough or a YouTube upload of the A500 piano (EXP-004, the floppy) or the A3500 piano (EXP-006, the BlueSCSI image), when she asks to free disk space for a recording, or when she says an upload is done and the recording's files can go.
---

# Piano videos for YouTube

An occasional job: one unattended run of a piano disk, from the boot to 5 s
after its tenth piece, every emulated frame and every sample, mastered to
4K with chapters. Stacey uploads it herself. Never upload, and never use a
YouTube API.

| Disk | Command | Out folder | Master | Description template |
| --- | --- | --- | --- | --- |
| A500 floppy (EXP-004) | `make piano-video` | `runs/video/` | `piano-playthrough-4k.mp4` | `examples/piano/video-description.txt` |
| A3500 image (EXP-006) | `make piano3500-video` | `runs/video3500/` | `piano3500-playthrough-4k.mp4` | `examples/piano3500/video-description.txt` |

The make targets take `SECONDS=`, `STEPS=` and `OUT=`. The A500 command
boots a copy of the floppy (`--floppy`); the A3500 one boots a copy of the
image (`--image`) through `machine.uae`, the app's own resolved
configuration, because the core has no A3000 model of its own.

How the recorder works, and what failed before it worked (the app has no
recorder; the libretro core gives frames and samples in emulated time):
`plugins/amiga-dev/skills/amiberry/references/recording.md`. The evidence
from each run goes in its experiment (EXP-004, "A video of the disk playing
by itself"; EXP-006 for the A3500).

## 1. Make room

A run needs about 0.56 GB a minute of recording for the lossless capture
(24.6 GB for the A500's 43 minutes) plus about 1 GB for the 4K master. The
command estimates the run and refuses to start without room for it. Check
the free space on the Data volume (`df -h /System/Volumes/Data`). If it is
short, local Time Machine snapshots are usually what fills it: list them
with `tmutil listlocalsnapshots /` and, with Stacey's go-ahead, delete each
with `tmutil deletelocalsnapshots <date>`. Delete nothing else to make
room without asking.

## 2. Build what is recorded

Record the disk as it is on `main`, built fresh: `make piano-disk` or `make
piano3500-image`. Gate first (`set -o pipefail; make test`, `uv run
amiga-env guard`). Close any emulator window of yours that has the image
open; the recorder works on a copy.

## 3. Record

Run the command in the background; recording takes about as long as what
it records (about 43 minutes; the core paces even the cycle-exact 68030 at
real time), then the master and measure steps take about half as long
again. It needs no input. Nothing is sent to the machine. A
test run first is cheap: `--seconds 40 --out runs/<name>-test` shows the
screen and the first piece's start; delete its `capture.mkv` afterwards.
`--steps master,measure` redoes the later steps without recording again.

## 4. Check before handing over

From `video.json` and the master itself (extract a few frames with ffmpeg
and look at them):

- frames and samples: none missing, the sound's rate steady;
- the sound offset measured from the master's own audio, within a frame;
- each piece's gold line found, ten chapters, the first at 0:00;
- levels and digital silence within pieces (silence at a rest is fine);
- the picture: the screen's own colours, nearest neighbour, 3840x2160.

Write the results as a dated section of the experiment.

## 5. The description

The command writes `youtube-description.generated.txt` from the template
with the chapters filled in. Stacey edits a copy,
`youtube-description.txt`, by hand. Never write or overwrite that file: if
it exists, show her what changed in the generated draft and let her merge
it. Give her the master's path and the draft's.

## 6. After the upload

When Stacey says the video is up, delete the run's large temporary files
(`capture.mkv`, `audio.wav`, the disk copy) and keep the small ones (`video.json`,
`record.json`, `frames.csv`, the descriptions). Delete the 4K master only
when she says so.
