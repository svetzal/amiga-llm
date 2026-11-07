# Recording picture and sound

Verified with Amiberry 8.5.0 (2026-10-27) on macOS (Apple silicon),
2026-11-07, unless marked otherwise.

## What does not work

- **The built-in recorder is not compiled in.** The binary has the strings
  `SPC_VIDEORECORD`, `AKS_VIDEORECORD`, "Audio/Video recording" and
  "Include alpha channels in screenshots and video captures", but WinUAE's
  recorder (`avioutput.cpp`) is not in Amiberry's source, and `AVIOUTPUT`
  is commented out in `src/osdep/sysconfig.h`. The record action's handler
  in `inputdevice.cpp` is inside `#ifdef AVIOUTPUT`.
- **The socket cannot bind it.** `SETTINGS_INPUT_EVENTS` lists 206 events
  ("Screenshot (file)" among them) but not "Audio/Video recording";
  `SETTINGS_CUSTOM_CONTROL_SET 0 none a "Audio/Video recording"` replies
  `ERROR  Unknown input event: Audio/Video recording`. Custom controls are
  game controller buttons and axes, not keys.
- **The bundled FFmpeg libraries are for input.** `libavcodec` and
  `libavformat` serve the genlock video source (`VIDEOGRAB`, CMake option
  `USE_VIDEOGRAB`), which plays a video file into the Amiga's picture.
- **`FRAME_ADVANCE` runs no frame.** After `PAUSE` it replies `OK  1
  frame(s) advanced`, but the handler resumes and pauses again at once on
  the socket thread, so no frame is emulated: a program's vertical blank
  counter, read with `READ_MEM`, did not move over 780 "advanced" frames.
  It also caps `n` at 100.

So the app cannot make a frame-exact recording. `SCREENSHOT` in a loop gets
about 40 shots a second at best, at no known frame.

## What works: the release's libretro core

Each release has a libretro core beside the app
(`amiberry-libretro-macOS-arm64.dylib`, `amiberry-libretro-linux-*.so`,
listed in the release's `SHA256SUMS`). It is the same emulator built as a
library. A small host (about 150 lines of Python `ctypes`) loads it, and
each `retro_run()` emulates one frame and hands over:

- **the picture**, through the video callback, as XRGB8888 (bytes B, G, R,
  X; ffmpeg's `bgr0`). For an NTSC A500 the frame is 752x486, the same
  geometry as the app's `SCREENSHOT`: a 320x200 lowres screen at (60, 48),
  each pixel exactly 2x2. The first 134 frames of a boot (about 2.2 s) were
  752x484;
- **the sound made in that frame**, through the batch audio callback, as
  signed 16-bit stereo. The core passes the emulator's samples through a
  FIFO about 1.5 frames deep. It adds samples of its own only in a frame
  that gave none at all. At 48 kHz the stream ran at 802.325 samples a
  frame, steady from the first second, which is 48,000 / 59.8261: the NTSC
  frame rate (3,579,545 Hz / 227.5 / 263). So samples are in emulated time,
  and a host that keeps every one in order has sound locked to the frames;
- **chip RAM**, through `retro_get_memory_data(RETRO_MEMORY_SYSTEM_RAM)`, in
  the Amiga's (big-endian) byte order, for reading a program's state after
  each frame instead of `READ_MEM`.

The core paced itself at about 60 frames a second on an M-series Mac,
though the host asked for frames as fast as it could, so a recording takes
as long as what it records.

### Options decide the machine

The core builds an Amiberry command line from its options and calls
Amiberry's own `main`: `--model`, `-s` settings, `-G`, `-r KICKSTART`, the
content path. Content can be `.adf`, `.hdf`, `.uae`, `.lha` and others.

- **Answer every option yourself.** A frontend that answers
  `GET_CORE_OPTIONS_VERSION` with 0 gets the v0 list, whose first value is
  not always the real default: floppy speed is listed `0|100|...` (0 is
  turbo, the v2 default is 100), sound filter `off|emulated|on`, stereo
  separation `0|...|10`. Taking the first value made an A500 boot about 2.4
  times faster than the app did.
- Options used for a stock NTSC A500: `amiberry_model=A500`,
  `amiberry_kickstart=<absolute path>`, `amiberry_video_standard=ntsc`,
  `amiberry_floppy_speed=100`, `amiberry_cpu_model=auto`,
  `amiberry_chipset=auto`, `amiberry_audio_interpolation=auto`,
  `amiberry_crop_overscan=disabled`, `amiberry_statusline=disabled`, and for
  the sound `amiberry_audio_rate=48000`, `amiberry_stereo_separation=10`,
  `amiberry_sound_filter=emulated`.
- **Check the command line.** With `AMIBERRY_LIBRETRO_DEBUG=1` in the
  environment, the core writes `amiberry_libretro_debug.log` in its save
  directory, with a line `core_entry argv: [amiberry] [--model] [A500]
  ...`. Pass the same arguments, minus `amiberry.rom_path=` and
  `statefile_path=`, to the app with `--dump-config`, and compare with the
  app's own arguments: with the options above the two configurations
  differed only in `use_gui`.
- An encrypted Amiga Forever ROM works as `amiberry_kickstart` when
  `rom.key` is beside it, as in the app.
- The core makes its home (an `amiberry.conf` and the usual folders) in the
  save directory the frontend gives it, and wrote nothing to the user's
  global Amiberry folder.
- The core had no floppy drive sounds.

### Not repeatable to the frame

Two boots of the same disk with the same options opened a program's screen
4 frames apart. Measure each recording's own timings; do not reuse one
run's frame numbers for another.

### Making a video

Pipe the frames to ffmpeg as raw `bgr0` at the NTSC rate (`-framerate
1431818/23933`) into a lossless codec (FFV1), write the samples to a WAV,
and encode from those. A 320x200 lowres screen widened with nearest
neighbour from its 640x400 (2x2) area to 2880x2160 gives each Amiga pixel
exactly 9 columns and 10 or 11 rows; MP4's timescale stores the rate as
1376/23.
