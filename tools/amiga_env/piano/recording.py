"""Record, master and measure the piano disk playing by itself (the I/O around video.py).

1. `record`: boot a copy of the disk in Amiberry's libretro core and keep every
   emulated frame (`capture.mkv`, FFV1, lossless) and every sample
   (`audio.wav`, 48 kHz), and the player's status block after each frame
   (`frames.csv`). Nothing is sent to the machine. The run stops `TAIL_S`
   after the rotation's last piece ends. The core runs at its own pace, but
   the files are in emulated time: frame n is the machine's frame n, and
   sample k was made 1/48,000 s of emulated time after sample k-1.
2. `master`: one ffmpeg pass from the capture to each master.
3. `measure`: where each piece's line turns gold, read from a video's own
   frames; where the first notes are; the sound's levels and continuity.
"""

import csv
import hashlib
import json
import os
import shutil
import subprocess
import time
import wave
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

import numpy as np

from .. import amiberry, home, libretro, profile, project
from . import machine, video

CSV_FIELDS = (
    "frame",
    "samples",
    "vblanks",
    "state",
    "piece",
    "starts",
    "played",
    "highlight",
    "screen_at",
    "chosen_at",
    "gold_at",
    "playing_at",
    "first_note_at",
    "first_note_ms",
)
DEBUG_LOG = "amiberry_libretro_debug.log"
PROBE_ENTRIES = (
    "stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_read_packets,"
    "sample_rate,channels,duration,pix_fmt,color_space"
)
ARGV_MARK = "core_entry argv:"


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise SystemExit("ffmpeg is not on PATH (on a Mac: brew install ffmpeg)")
    return found


def record(
    machine_: profile.Machine,
    floppy: Path,
    out: Path,
    pieces: int,
    max_seconds: float | None = None,
    fps: Fraction = video.NTSC_FPS,
) -> dict:
    """Boot `floppy` (a copy is made in `out`) and record until the rotation is done."""
    out.mkdir(parents=True, exist_ok=True)
    disk = out / "piano.adf"
    shutil.copyfile(floppy, disk)
    core_dir = out / "core"
    (core_dir / "save" / DEBUG_LOG).unlink(missing_ok=True)
    os.environ["AMIBERRY_LIBRETRO_DEBUG"] = "1"  # the core logs its command line
    kickstart = project.media_dir() / machine_.kickstart
    core = libretro.Core(
        amiberry.installed_core(),
        video.core_options(machine_, kickstart),
        core_dir / "system",
        core_dir / "save",
    )
    core.load(disk.resolve())
    started = time.monotonic()
    tally = _Tally()
    with (
        subprocess.Popen(
            video.capture_command(ffmpeg(), fps, out / "capture.mkv"), stdin=subprocess.PIPE
        ) as encoder,
        wave.open(str(out / "audio.wav"), "wb") as audio,
        (out / "frames.csv").open("w", newline="") as rows,
    ):
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(video.SAMPLE_RATE)
        log = csv.writer(rows)
        log.writerow(CSV_FIELDS)
        limit = round(max_seconds * fps) if max_seconds else None
        stop_at = None
        while (stop_at is None or tally.frames < stop_at) and (
            limit is None or tally.frames < limit
        ):
            status = _frame(core, encoder, audio, log, tally)
            if stop_at is None and video.finished(status, pieces):
                stop_at = tally.frames + round(video.TAIL_S * fps)
            if tally.frames % (60 * 60) == 0:
                _progress(tally, status, fps, started)
        encoder.stdin.close()
    core.close()
    if encoder.returncode:
        raise SystemExit(f"ffmpeg stopped with {encoder.returncode} while capturing")
    core_argv = _core_argv(core_dir / "save" / DEBUG_LOG)
    app_argv = profile.base_args(machine_) + ["-0", str(disk.resolve())]
    app_argv += [arg for setting in video.SOUND_SETTINGS for arg in ("-s", setting)]
    report = tally.report(fps) | {
        "floppy": str(floppy),
        "floppy_sha1": _sha1(floppy),
        "copy_booted": str(disk),
        "finished": stop_at is not None,
        "wall_s": round(time.monotonic() - started, 1),
        "core_timing": core.timing(),
        "core_events": core.events,
        "core_argv": core_argv,
        "app_argv": app_argv,
        "config_differences_from_the_app": _compare_configs(core_argv, app_argv),
    }
    (out / "record.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


class _Tally:
    """What the recording loop counts."""

    def __init__(self):
        self.frames = 0
        self.samples = 0
        self.fitted: list[int] = []  # frames of another size, put on the canvas
        self.repeated = 0  # frames the core did not draw; the last one is kept
        self.quiet = []  # frames, after the first with sound, that gave no samples
        self.sizes: dict[str, int] = {}
        self.last: bytes = bytes(video.FRAME_WIDTH * video.FRAME_HEIGHT * 4)

    def report(self, fps: Fraction) -> dict:
        expected = self.frames * video.SAMPLE_RATE / fps
        return {
            "frames": self.frames,
            "fps": f"{fps.numerator}/{fps.denominator}",
            "seconds": round(float(self.frames / fps), 3),
            "samples": self.samples,
            "samples_per_frame": round(self.samples / max(self.frames, 1), 3),
            "samples_expected_at_fps": round(float(expected)),
            "samples_off_by": round(self.samples - float(expected)),
            "frame_sizes": self.sizes,
            "frames_fitted_to_the_canvas": len(self.fitted),
            "fitted_frame_ranges": _ranges(self.fitted),
            "frames_repeated_by_the_core": self.repeated,
            "frames_without_samples_after_the_first_sound": self.quiet[:20],
        }


def _ranges(frames: Sequence[int]) -> list[list[int]]:
    """Consecutive frame numbers as [first, last] pairs."""
    found: list[list[int]] = []
    for frame in frames:
        if found and frame == found[-1][1] + 1:
            found[-1][1] = frame
        else:
            found.append([frame, frame])
    return found


def _frame(core: libretro.Core, encoder, audio, log, tally: _Tally) -> machine.Status | None:
    frame = core.run()
    if frame.pixels is None:
        tally.repeated += 1
    else:
        size = f"{frame.width}x{frame.height}"
        tally.sizes[size] = tally.sizes.get(size, 0) + 1
        tally.last, fitted = video.canvas(frame.pixels, frame.width, frame.height, frame.pitch)
        if fitted:
            tally.fitted.append(tally.frames)
    encoder.stdin.write(tally.last)
    audio.writeframesraw(frame.audio)
    count = len(frame.audio) // 4
    if not count and tally.samples:
        tally.quiet.append(tally.frames)
    tally.samples += count
    status = video.status_of(core.read(machine.STATUS, 4 * len(machine.STATUS_FIELDS)))
    values = [getattr(status, field) for field in CSV_FIELDS[2:]] if status else []
    log.writerow([tally.frames, count, *values])
    tally.frames += 1
    return status


def _progress(tally: _Tally, status: machine.Status | None, fps: Fraction, started: float) -> None:
    where = (
        f"piece {status.piece + 1}, {status.played} ended" if status and status.starts else "boot"
    )
    print(
        f"{tally.frames / fps / 60:5.1f} min emulated, {(time.monotonic() - started) / 60:5.1f} "
        f"min wall: {where}",
        flush=True,
    )


def _core_argv(log: Path) -> list[str]:
    if not log.is_file():
        return []
    lines = [line for line in log.read_text(errors="replace").splitlines() if ARGV_MARK in line]
    return video.parse_argv_log(lines[-1]) if lines else []


def _compare_configs(core_argv: Sequence[str], app_argv: Sequence[str]) -> list[str]:
    """How the configuration the core's command line resolves to differs from the app's
    for its machine profile with the same sound settings, by the app's --dump-config."""
    if not core_argv:
        raise SystemExit("the core logged no command line; see its debug log")
    dumps = [
        subprocess.run(
            [str(amiberry.installed_binary()), *args, "--dump-config"],
            env=home.environment(),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for args in (app_argv, video.app_arguments(core_argv))
    ]
    return video.config_differences(*dumps)


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def master(out: Path, masters: Sequence[video.Master], delay_ms: int = 0) -> dict:
    """Every master from the capture and the sound, in one ffmpeg pass."""
    started = time.monotonic()
    command = video.master_command(
        ffmpeg(), out / "capture.mkv", out / "audio.wav", masters, delay_ms=delay_ms
    )
    subprocess.run(command, check=True)
    return {
        "masters": [str(m.path) for m in masters],
        "sound_delayed_ms": delay_ms,
        "wall_s": round(time.monotonic() - started),
    }


def sound_offset(found: dict, fps: Fraction) -> dict:
    """The sound's offset against the picture from a measure's first notes."""
    lags = [
        p["first_sound_after_the_players_note_ms"]
        for p in found["pieces"]
        if p["first_sound_after_the_players_note_ms"] is not None
    ]
    low, high = video.sound_offset_ms(lags, 1000 / float(fps))
    return {"lags_ms": lags, "offset_ms": [low, high]}


def probe(path: Path) -> dict:
    """ffprobe's streams of a file: codec, size, rate, packets (a video's frames), duration."""
    reply = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-count_packets",
            "-show_entries",
            PROBE_ENTRIES,
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(reply.stdout)


def gold_lines(source: Path, layout: video.ListLayout, picture: tuple[int, int, int, int]) -> list:
    """The gold line (or None) in each frame of `source`, read from its own pixels."""
    width, rows = layout.right - layout.left, layout.lines * layout.line_pitch
    size = width * rows * 3
    shifted = layout._replace(left=0, right=width, top=0)
    found = []
    with subprocess.Popen(
        video.list_command(ffmpeg(), source, layout, picture), stdout=subprocess.PIPE
    ) as decoder:
        while chunk := decoder.stdout.read(size):
            if len(chunk) < size:
                break
            found.append(
                video.gold_line(np.frombuffer(chunk, np.uint8).reshape(rows, width, 3), shifted)
            )
    return found


def read_frames_csv(path: Path) -> list[dict]:
    with path.open(newline="") as rows:
        return [
            {key: int(value) for key, value in row.items() if value not in ("", None)}
            for row in csv.DictReader(rows)
        ]


def read_sound(path: Path) -> np.ndarray:
    """A file's sound as 48 kHz 16-bit stereo, decoded by ffmpeg (an MP4's AAC included)."""
    decoded = subprocess.run(
        [ffmpeg(), "-v", "error", "-i", str(path), "-vn", "-f", "s16le", "-ac", "2", "-ar"]
        + [str(video.SAMPLE_RATE), "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(decoded, "<i2").reshape(-1, 2)


def _has_audio(path: Path) -> bool:
    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0"]
        + [str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return "audio" in streams


def measure(
    out: Path,
    source: Path,
    picture: tuple[int, int, int, int],
    layout: video.ListLayout,
    titles: Sequence[str],
    fps: Fraction,
) -> dict:
    """Where each piece starts in `source` (its line turning gold, from the video's own
    frames), the player's own stamps for the same moments, the first notes in the
    sound, and the sound's levels and continuity."""
    rows = read_frames_csv(out / "frames.csv")
    sound = read_sound(source if _has_audio(source) else out / "audio.wav")
    lines = gold_lines(source, layout, picture)
    onsets = video.gold_onsets(lines)
    player = _player_starts(rows)
    per_frame = video.SAMPLE_RATE / fps
    pieces = []
    for number, onset in enumerate(onsets):
        stamps = player[number] if number < len(player) else {}
        first_note = stamps.get("first_note_frame")
        heard = video.first_sound(sound, round(onset.frame * per_frame))
        ends = (
            round(onsets[number + 1].frame * per_frame) if number + 1 < len(onsets) else len(sound)
        )
        body = sound[heard:ends] if heard is not None else sound[:0]
        pieces.append(
            {
                "line": onset.line,
                "title": titles[onset.line],
                "gold_frame": onset.frame,
                "gold_s": round(float(onset.frame / fps), 3),
                "player_gold_frame": stamps.get("gold_frame"),
                "player_first_note_frame": first_note,
                "player_first_note_s": round(float(first_note / fps), 3) if first_note else None,
                "first_sound_s": round(heard / video.SAMPLE_RATE, 4) if heard is not None else None,
                "first_sound_after_the_players_note_ms": (
                    round((heard / video.SAMPLE_RATE - float(first_note / fps)) * 1000, 1)
                    if first_note and heard is not None
                    else None
                ),
                "levels": video.levels(body),
                "digital_silences_over_20_ms": len(
                    video.silent_runs(body, video.SAMPLE_RATE // 50)
                ),
            }
        )
    return {
        "source": str(source),
        "frames_read": len(lines),
        "onsets": [o._asdict() for o in onsets],
        "pieces": pieces,
        "sound_s": round(len(sound) / video.SAMPLE_RATE, 3),
        "sound_levels": video.levels(sound),
    }


def _player_starts(rows: Sequence[dict]) -> list[dict]:
    """For each piece the player started, in order: the frames of its gold stamp and
    its first note, from the player's own vertical blank counts."""
    counts = [row.get("vblanks", 0) for row in rows]
    found: list[dict] = []
    for row in rows:
        starts = row.get("starts", 0)
        if starts > len(found):
            found.append({"gold_at": row["gold_at"]})
        if found and starts == len(found) and row.get("first_note_at", 0) >= found[-1]["gold_at"]:
            found[-1].setdefault("first_note_at", row["first_note_at"])
    for piece in found:
        piece["gold_frame"] = video.frame_of(piece["gold_at"], counts)
        if "first_note_at" in piece:
            piece["first_note_frame"] = video.frame_of(piece["first_note_at"], counts)
    return found


STEPS = ("record", "master", "measure")
GENERATED_DESCRIPTION = "youtube-description.generated.txt"
FIRST_CHAPTER = "Boot and title screen"
CAPTURE_PICTURE = (
    video.SCREEN_LEFT,
    video.SCREEN_TOP,
    video.SCREEN_WIDTH * video.SCREEN_SCALE,
    video.SCREEN_HEIGHT * video.SCREEN_SCALE,
)


def masters(out: Path) -> list[video.Master]:
    """The YouTube master: 4K, the 4:3 picture in black bars. YouTube makes the
    smaller sizes itself."""
    return [video.Master(3840, 2160, 2880, out / "piano-playthrough-4k.mp4")]


def layout_of(spec, lines: int) -> video.ListLayout:
    """Where the list is on the screen, from the recipe's [screen] table."""
    box = spec.list_box
    return video.ListLayout(
        left=box.left,
        right=box.right,
        top=box.top,
        line_pitch=spec.line_pitch,
        lines=lines,
        text=video.ocs_rgb(spec.text),
        highlight=video.ocs_rgb(spec.highlight),
    )


def make_video(
    machine_: profile.Machine,
    floppy: Path,
    out: Path,
    titles: Sequence[str],
    spec,
    template: Path,
    steps: Sequence[str] = STEPS,
    max_seconds: float | None = None,
) -> dict:
    """Record, master and measure; write the description with the chapters.

    The chapters come from the 4K master's own frames; the capture's are read
    too, and must put every piece on the same frame. The capture's first notes
    give the sound's offset against the picture, which the masters correct;
    the master's own sound is measured again.
    """
    unknown = sorted(set(steps) - set(STEPS))
    if unknown:
        raise SystemExit(f"no step {unknown[0]}; the steps are {', '.join(STEPS)}")
    fps = video.NTSC_FPS
    found: dict = {}
    if "record" in steps:
        found["record"] = record(machine_, floppy, out, len(titles), max_seconds, fps)
    targets = masters(out)
    layout = layout_of(spec, len(titles))
    if "master" in steps or "measure" in steps:
        found["capture"] = measure(out, out / "capture.mkv", CAPTURE_PICTURE, layout, titles, fps)
        found["capture_sound_offset"] = sound_offset(found["capture"], fps)
    if "master" in steps:
        delay = video.audio_delay_ms(tuple(found["capture_sound_offset"]["offset_ms"]))
        found["master"] = master(out, targets, delay) | {"probe": [probe(m.path) for m in targets]}
    if "measure" in steps:
        largest = targets[0]
        in_master = (
            (largest.width - largest.picture_width) // 2,
            0,
            largest.picture_width,
            largest.height,
        )
        found["video"] = measure(out, largest.path, in_master, layout, titles, fps)
        found["video_sound_offset"] = sound_offset(found["video"], fps)
        found["chapters"] = _chapters(found, template, out, fps)
    (out / "video.json").write_text(json.dumps(found, indent=2) + "\n")
    return found


def _chapters(found: dict, template: Path, out: Path, fps: Fraction) -> dict:
    in_capture = [p["gold_frame"] for p in found["capture"]["pieces"]]
    pieces = found["video"]["pieces"]
    in_video = [p["gold_frame"] for p in pieces]
    if in_capture != in_video:
        raise SystemExit(f"the master's gold lines {in_video} are not the capture's {in_capture}")
    length = found["video"]["frames_read"] / fps
    starts = [(p["gold_s"], video.chapter_label(p["title"])) for p in pieces]
    chapters = video.chapters(FIRST_CHAPTER, starts, float(length))
    text = video.description(template.read_text(), chapters)
    # A draft only: the description that is uploaded is edited by hand in
    # youtube-description.txt, which this never writes.
    (out / GENERATED_DESCRIPTION).write_text(text)
    first_note = pieces[0]["player_first_note_s"] if pieces else None
    return {
        "lines": video.chapter_lines(chapters),
        "video_s": round(float(length), 3),
        "from_the_first_note_s": [
            round(p["gold_s"] - first_note, 3) if first_note else None for p in pieces
        ],
        "description": str(out / GENERATED_DESCRIPTION),
    }
