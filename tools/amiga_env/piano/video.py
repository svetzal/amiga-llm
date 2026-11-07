"""A video of the piano disk playing by itself: the decisions, with no I/O.

`amiga-env piano-video` (recording.py) boots the disk in Amiberry's libretro
core, keeps every emulated frame and every sample, and stops a few seconds
after the rotation's tenth piece ends. Nothing is sent to the machine.

This module holds what can be decided without the emulator or ffmpeg:

- the core's options, all given explicitly, so that its command line
  resolves to the same configuration as the app's machine profile;
- when the run is over, from the player's status block;
- each frame on a canvas of one size;
- which line of the list is gold in a picture of the 320x200 screen, and
  so where each piece starts in the video;
- the YouTube chapter lines and description;
- the ffmpeg command lines for the lossless capture and the masters;
- measurements of the recorded sound.
"""

import bisect
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path
from typing import NamedTuple

import numpy as np

from .. import profile
from . import machine

SAMPLE_RATE = 48_000
# An NTSC A500 frame: 263 lines of 227.5 colour clocks at 3,579,545 Hz.
NTSC_FPS = Fraction(3_579_545 * 2, 455 * 263)
# The frame Amiberry 8.5.0 hands over for an NTSC A500, and where the 320x200
# screen is in it (each lowres pixel 2x2), as its SCREENSHOT shows it.
FRAME_WIDTH, FRAME_HEIGHT = 752, 486
SCREEN_LEFT, SCREEN_TOP, SCREEN_SCALE = 60, 48, 2
SCREEN_WIDTH, SCREEN_HEIGHT = 320, 200
TAIL_S = 5.0  # kept after the last piece ends

# The machine profile's settings the core can reproduce, as core options.
SETTING_OPTIONS = {"ntsc=true": ("amiberry_video_standard", "ntsc")}
# Every core option that reaches Amiberry's command line, set to what puts the
# profile's machine there and nothing else. Leaving one to the core is not
# safe: its v0 list gives floppy speed 0 (turbo) first, though 100 is its default.
CORE_OPTIONS = {
    "amiberry_cpu_model": "auto",
    "amiberry_chipset": "auto",
    "amiberry_chipset_aga": "auto",
    "amiberry_floppy_speed": "100",
    "amiberry_audio_interpolation": "auto",
    "amiberry_crop_overscan": "disabled",
    "amiberry_statusline": "disabled",
    "amiberry_on_screen_keyboard": "disabled",
    "amiberry_input_log": "disabled",
    "amiberry_midi_output": "disabled",
}
# The sound: what a real A500 does (full stereo, the filter as the LED says),
# at YouTube's rate, so nothing resamples it.
SOUND_OPTIONS = {
    "amiberry_audio_rate": str(SAMPLE_RATE),
    "amiberry_stereo_separation": "10",
    "amiberry_sound_filter": "emulated",
}
SOUND_SETTINGS = (
    f"sound_frequency={SAMPLE_RATE}",
    "sound_filter=emulated",
    "sound_stereo_separation=10",
)


def core_options(machine_: profile.Machine, kickstart: Path) -> dict[str, str]:
    """The core's options for `machine_`; SystemExit for a setting the core cannot take."""
    options = {"amiberry_model": machine_.model, "amiberry_kickstart": str(kickstart)}
    for setting in machine_.settings:
        if setting not in SETTING_OPTIONS:
            raise SystemExit(f"the libretro core cannot set {setting!r} from {machine_.model}")
        key, value = SETTING_OPTIONS[setting]
        options[key] = value
    return CORE_OPTIONS | SOUND_OPTIONS | options


def app_arguments(core_argv: Sequence[str]) -> list[str]:
    """The core's Amiberry command line without its frontend's paths, to compare
    with the app's (`amiberry.rom_path=` and `statefile_path=` name the core's folders)."""
    kept, skip = [], False
    for index, arg in enumerate(core_argv[1:], 1):
        if skip:
            skip = False
            continue
        following = core_argv[index + 1] if index + 1 < len(core_argv) else ""
        if arg == "-s" and following.startswith(("amiberry.rom_path=", "statefile_path=")):
            skip = True
            continue
        kept.append(arg)
    return kept


def parse_argv_log(line: str) -> list[str]:
    """The arguments in the core's debug log line `core_entry argv: [a] [b] ...`."""
    _, _, rest = line.partition("argv:")
    return [part.strip()[1:] for part in rest.strip().split("]") if part.strip()]


def config_differences(app: str, core: str, ignore: Sequence[str] = ("use_gui",)) -> list[str]:
    """The `key=value` lines of two `amiberry --dump-config` outputs that differ, as
    "key: app -> core", leaving out `ignore` (the core's frontend starts with no GUI)."""

    def settings(text: str) -> dict[str, str]:
        pairs = (line.split("=", 1) for line in text.splitlines() if "=" in line)
        return {key: value for key, value in pairs if key not in ignore}

    a, b = settings(app), settings(core)
    return [
        f"{k}: {a.get(k)} -> {b.get(k)}"
        for k in sorted(a.keys() | b.keys())
        if a.get(k) != b.get(k)
    ]


def status_of(block: bytes) -> machine.Status | None:
    """The player's status block from chip RAM, or None before the player has written it."""
    count = len(machine.STATUS_FIELDS)
    if len(block) < 4 * count:
        return None
    status = machine.parse_status(np.frombuffer(block[: 4 * count], ">u4").tolist())
    return status if status.magic == machine.MAGIC else None


def finished(status: machine.Status | None, pieces: int) -> bool:
    """Whether the rotation has started and ended every piece once."""
    return status is not None and status.starts >= pieces and status.played >= pieces


def canvas(pixels: bytes, width: int, height: int, pitch: int) -> tuple[bytes, bool]:
    """A frame as FRAME_WIDTH x FRAME_HEIGHT XRGB8888, and whether it had to be fitted.

    A frame of another size (Amiberry hands over a few 484-line frames) is
    put at the top left of a black canvas, or cut to it.
    """
    rows = np.frombuffer(pixels, np.uint8).reshape(height, pitch)[:, : width * 4]
    if (width, height) == (FRAME_WIDTH, FRAME_HEIGHT):
        return rows.tobytes(), False
    out = np.zeros((FRAME_HEIGHT, FRAME_WIDTH * 4), np.uint8)
    h, w = min(height, FRAME_HEIGHT), min(width, FRAME_WIDTH) * 4
    out[:h, :w] = rows[:h, :w]
    return out.tobytes(), True


def screen_of(frame: bytes) -> np.ndarray:
    """The 320x200 screen (rows x columns x RGB) in a canvas frame."""
    pixels = np.frombuffer(frame, np.uint8).reshape(FRAME_HEIGHT, FRAME_WIDTH, 4)
    top, left, scale = SCREEN_TOP, SCREEN_LEFT, SCREEN_SCALE
    screen = pixels[
        top : top + SCREEN_HEIGHT * scale : scale, left : left + SCREEN_WIDTH * scale : scale
    ]
    return screen[:, :, 2::-1]  # B, G, R, X in memory


def ocs_rgb(colour: str) -> tuple[int, int, int]:
    """An OCS colour ('B95') as 8-bit RGB."""
    return tuple(int(digit, 16) * 17 for digit in colour)  # type: ignore[return-value]


class ListLayout(NamedTuple):
    """Where the list's lines are on the 320x200 screen, and their two colours."""

    left: int
    right: int
    top: int
    line_pitch: int
    lines: int
    text: tuple[int, int, int]
    highlight: tuple[int, int, int]


def gold_line(screen: np.ndarray, layout: ListLayout, min_pixels: int = 8) -> int | None:
    """The line (from 0) whose text is in the highlight colour, or None.

    A pixel counts as gold or ivory when it is nearer that colour than the
    other, and near enough to it to survive a lossy encode. A line is gold
    when it has `min_pixels` gold pixels and the other lines have ivory text:
    a frame without the player's palette (the screen opening, in the
    Workbench's colours) has none, whatever its picture's pixels look like.
    """
    rows = layout.top + layout.lines * layout.line_pitch
    band = screen[layout.top : rows, layout.left : layout.right].astype(int)
    to_text = np.abs(band - np.array(layout.text)).sum(axis=2)
    to_gold = np.abs(band - np.array(layout.highlight)).sum(axis=2)
    gold = (to_gold < to_text) & (to_gold < 60)
    ivory = (to_text < to_gold) & (to_text < 60)
    shape = (layout.lines, layout.line_pitch, -1)
    gold_per_line = gold.reshape(shape).sum(axis=(1, 2))
    ivory_per_line = ivory.reshape(shape).sum(axis=(1, 2))
    best = int(gold_per_line.argmax())
    others = np.delete(ivory_per_line, best)
    if gold_per_line[best] < min_pixels or (others < min_pixels).any():
        return None
    return best


class Onset(NamedTuple):
    frame: int
    line: int


def gold_onsets(lines: Sequence[int | None]) -> list[Onset]:
    """Each frame where a line turns gold that was not gold in the frame before."""
    onsets, before = [], None
    for frame, line in enumerate(lines):
        if line is not None and line != before:
            onsets.append(Onset(frame, line))
        before = line
    return onsets


def timestamp(seconds: float) -> str:
    """YouTube's form: m:ss under an hour, h:mm:ss from an hour; whole seconds, rounded down."""
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def chapter_label(title: str) -> str:
    """A list title ("Chopin  Nocturne Op. 9 No. 2") as "Composer: Title"."""
    composer, _, work = title.partition("  ")
    if not work:
        raise SystemExit(f"a title is 'Composer  Work', with two spaces: {title!r}")
    return f"{composer}: {work.strip()}"


class Chapter(NamedTuple):
    seconds: float
    label: str


MIN_CHAPTER_S = 10


def chapters(first: str, starts: Sequence[tuple[float, str]], length_s: float) -> list[Chapter]:
    """The chapters: `first` at 0:00, then each (seconds, label) in order.

    SystemExit unless each chapter, the last included, is at least 10 s long
    as YouTube shows it (whole seconds), as YouTube requires.
    """
    found = [Chapter(0.0, first), *(Chapter(s, label) for s, label in starts)]
    ends = [*(c.seconds for c in found[1:]), length_s]
    for chapter, end in zip(found, ends, strict=True):
        if int(end) - int(chapter.seconds) < MIN_CHAPTER_S:
            raise SystemExit(f"chapter {chapter.label!r} is under {MIN_CHAPTER_S} s")
    return found


def chapter_lines(found: Sequence[Chapter]) -> list[str]:
    return [f"{timestamp(c.seconds)} {c.label}" for c in found]


def description(template: str, found: Sequence[Chapter]) -> str:
    """The template with `{chapters}` replaced by the chapter lines."""
    if "{chapters}" not in template:
        raise SystemExit("the description template has no {chapters}")
    return template.replace("{chapters}", "\n".join(chapter_lines(found)))


def capture_command(ffmpeg: str, fps: Fraction, out: Path) -> list[str]:
    """ffmpeg reading canvas frames from stdin into a lossless FFV1 file."""
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr0",
        "-video_size",
        f"{FRAME_WIDTH}x{FRAME_HEIGHT}",
        "-framerate",
        f"{fps.numerator}/{fps.denominator}",
        "-i",
        "-",
        "-c:v",
        "ffv1",
        "-level",
        "3",
        "-slices",
        "16",
        "-slicecrc",
        "1",
        str(out),
    ]


class Master(NamedTuple):
    width: int  # the frame
    height: int
    picture_width: int  # the 4:3 picture inside it
    path: Path


def picture_filter(masters: Sequence[Master]) -> str:
    """The filter graph from the capture to each master's picture.

    The screen is cut out of the capture (640x400, each lowres pixel 2x2),
    widened with nearest neighbour to the largest master's 4:3 picture (each
    lowres pixel exactly 9 wide at 2880; 10 or 11 tall at 2160, as 400 lines
    do not divide 2160), and averaged down for a smaller master (2880x2160 to
    1440x1080 is exactly half each way). Black bars fill each frame.
    """
    largest = max(masters, key=lambda m: m.height)
    crop = (
        f"crop={SCREEN_WIDTH * SCREEN_SCALE}:{SCREEN_HEIGHT * SCREEN_SCALE}:"
        f"{SCREEN_LEFT}:{SCREEN_TOP}"
    )
    parts = [
        f"[0:v]{crop},scale={largest.picture_width}:{largest.height}:flags=neighbor,"
        f"split={len(masters)}" + "".join(f"[p{i}]" for i in range(len(masters)))
    ]
    for i, master in enumerate(masters):
        scale = (
            "" if master is largest else f"scale={master.picture_width}:{master.height}:flags=area,"
        )
        pad = (master.width - master.picture_width) // 2
        parts.append(
            f"[p{i}]{scale}pad={master.width}:{master.height}:{pad}:0:black,"
            "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"
            f"[v{i}]"
        )
    return ";".join(parts)


def master_command(
    ffmpeg: str, capture: Path, audio: Path, masters: Sequence[Master], crf: int = 16
) -> list[str]:
    """ffmpeg making every master in one pass: H.264 High, CRF `crf`, the capture's
    frames one for one, AAC at 256 kb/s, 48 kHz stereo; tagged BT.709."""
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    command += ["-i", str(capture), "-i", str(audio), "-filter_complex", picture_filter(masters)]
    for i, master in enumerate(masters):
        command += [
            "-map",
            f"[v{i}]",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            str(crf),
            "-profile:v",
            "high",
            "-fps_mode",
            "passthrough",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-c:a",
            "aac",
            "-b:a",
            "256k",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(master.path),
        ]
    return command


def list_command(ffmpeg: str, video: Path, layout: ListLayout, picture: tuple[int, int, int, int]):
    """ffmpeg decoding `video` to the list's lines at the screen's own size: the
    picture (left, top, width, height in the video) cut out, averaged down to
    320x200, then cut to the list, as RGB24 frames on stdout."""
    left, top, width, height = picture
    rows = layout.lines * layout.line_pitch
    # in_color_matrix applies to a YUV master; swscale ignores it for the RGB capture.
    chain = (
        f"crop={width}:{height}:{left}:{top},"
        f"scale={SCREEN_WIDTH}:{SCREEN_HEIGHT}:flags=area:in_color_matrix=bt709:in_range=tv,"
        f"crop={layout.right - layout.left}:{rows}:{layout.left}:{layout.top},format=rgb24"
    )
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-vf",
        chain,
        "-f",
        "rawvideo",
        "-",
    ]


def first_sound(samples: np.ndarray, start: int, threshold: int = 256) -> int | None:
    """The first sample at or after `start` where either channel's size reaches `threshold`."""
    loud = np.flatnonzero(np.abs(samples[start:]).max(axis=1) >= threshold)
    return start + int(loud[0]) if len(loud) else None


def silent_runs(samples: np.ndarray, min_samples: int) -> list[tuple[int, int]]:
    """(start, length) of each run of exact digital zero in both channels at least
    `min_samples` long: what a dropout in the recording would look like."""
    zero = ~samples.any(axis=1)
    edges = np.flatnonzero(np.diff(np.concatenate(([0], zero.astype(np.int8), [0]))))
    return [(int(a), int(b - a)) for a, b in zip(edges[0::2], edges[1::2]) if b - a >= min_samples]


def levels(samples: np.ndarray) -> dict:
    """RMS and peak of `samples` in dBFS (16-bit full scale)."""
    if not len(samples):
        return {"rms_dbfs": None, "peak_dbfs": None}
    as_float = samples.astype(float) / 32768
    rms = float(np.sqrt((as_float**2).mean()))
    peak = float(np.abs(as_float).max())
    return {
        "rms_dbfs": round(20 * np.log10(max(rms, 1e-10)), 1),
        "peak_dbfs": round(20 * np.log10(max(peak, 1e-10)), 1),
    }


def frame_of(vblank: int, counts: Sequence[int]) -> int | None:
    """The first frame after which the player's vertical blank count had reached
    `vblank`; `counts` holds the count after each frame (0 before the player ran)."""
    frame = bisect.bisect_left(counts, vblank)
    return frame if frame < len(counts) else None
