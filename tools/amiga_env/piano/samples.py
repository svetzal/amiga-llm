"""Turn a multisampled piano into 8-bit Paula samples with loops.

Each chosen root note becomes one signed 8-bit sample: the recorded attack,
then a short loop that Paula repeats while the player's software decay
lowers the volume. The sample is stored at the rate Paula plays it for the
root at an integer period, so the root is in tune by construction and the
keys around it are a period lookup away.

Everything here is pure: arrays in, arrays and numbers out. read_wav is the
only function that touches a file.
"""

import math
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .sfz import Region

NTSC_CLOCK = 3_579_545  # Paula's clock on an NTSC machine, Hz
MIN_PERIOD = 124  # the shortest period Paula's DMA can feed (about 28.9 kHz)
LOWEST_KEY, HIGHEST_KEY = 21, 108  # A0 and C8, as MIDI notes


@dataclass(frozen=True)
class SampleSpec:
    """The choices that trade sound against chip RAM."""

    spacing: int = 3  # semitones between root notes
    min_rate: float = 11025.0  # Hz; no root is stored below this
    max_rate: float = 27000.0  # Hz; leaves the key above a root at period >= 124
    harmonics: float = 4.0  # stored rate is at least 2 * harmonics * the root's pitch
    attack_bass_s: float = 0.8  # recorded attack kept at A0 ...
    attack_treble_s: float = 0.25  # ... and at C8, interpolated by key between them
    loop_s: float = 0.1  # loop length aimed for; the search moves it +-25%
    fade_s: float = 0.01  # crossfade at the loop's seam
    seed: int = 4  # the dither's random generator
    peak: int = 126  # largest sample value after normalising, below 127 for the dither


@dataclass(frozen=True)
class PaulaSample:
    root: int  # MIDI note
    keys: tuple[int, ...]  # the MIDI notes it plays
    data: bytes  # signed 8-bit, even length
    loop_start: int  # bytes; even; the loop runs to the end
    period: int  # Paula period that plays the root at its recorded pitch (before tune)
    periods: dict[int, int]  # Paula period for each key it plays
    rate: float  # Hz, NTSC_CLOCK / period
    level: float  # peak before normalising, relative to the loudest root (with volume)
    decay_db_per_s: float  # how fast the recording fades after the attack
    loop_similarity: float  # 1.0 when the loop's seam matches the signal perfectly
    max_cents_error: float  # worst pitch error of a key, from rounding its period

    @property
    def loop_length(self) -> int:
        return len(self.data) - self.loop_start


def pitch_hz(note: int) -> float:
    return 440.0 * 2.0 ** ((note - 69) / 12)


def choose_layer(regions: list[Region], velocity: int) -> tuple[int, int]:
    """The velocity range of the layer that holds velocity, else the nearest one."""
    ranges = sorted({(r.lovel, r.hivel) for r in note_regions(regions)})
    for low, high in ranges:
        if low <= velocity <= high:
            return low, high
    return min(ranges, key=lambda r: abs((r[0] + r[1]) / 2 - velocity))


def note_regions(regions: list[Region]) -> list[Region]:
    """Regions a key press plays (not release, pedal or noise regions)."""
    return [r for r in regions if r.trigger == "attack" and r.lokey >= 0 and r.sample]


def layer_regions(regions: list[Region], layer: tuple[int, int]) -> dict[int, Region]:
    """Each root note of a layer and its region."""
    chosen = [r for r in note_regions(regions) if (r.lovel, r.hivel) == layer]
    return {r.pitch_keycenter: r for r in sorted(chosen, key=lambda r: r.pitch_keycenter)}


def choose_roots(
    available: list[int], spacing: int, low: int = LOWEST_KEY, high: int = HIGHEST_KEY
) -> list[int]:
    """Root notes about `spacing` semitones apart from low to high, each one a note that
    was sampled: evenly spaced targets, each moved to the nearest sampled note."""
    available = sorted(set(available))
    count = round((high - low) / spacing) + 1
    targets = [low + (high - low) * i / max(count - 1, 1) for i in range(count)]
    chosen = {min(available, key=lambda a, t=t: (abs(a - t), a)) for t in targets}
    return sorted(chosen)


def key_map(roots: list[int], low: int = LOWEST_KEY, high: int = HIGHEST_KEY) -> dict[int, int]:
    """The root each key plays from: the nearest, and the lower one on a tie."""
    return {key: min(roots, key=lambda r, k=key: (abs(r - k), r)) for key in range(low, high + 1)}


def cents(ratio: float) -> float:
    return 1200.0 * math.log2(ratio)


def choose_period(
    ratios: list[float], target: float, clock: int = NTSC_CLOCK
) -> tuple[int, dict[int, int], float]:
    """The root's period near target that keeps every key closest to pitch.

    ratios[i] is how much faster than the root key i must play. Returns the
    root period, each key's rounded period (by index) and the worst error in
    cents. Every key's period is at least MIN_PERIOD.
    """
    best = None
    for p0 in range(max(MIN_PERIOD, math.floor(target * 0.94)), math.ceil(target * 1.06) + 1):
        periods = {i: round(p0 / r) for i, r in enumerate(ratios)}
        if min(periods.values()) < MIN_PERIOD:
            continue
        error = max(abs(cents((p0 / r) / periods[i])) for i, r in enumerate(ratios))
        score = (round(error, 6), abs(p0 - target))
        if best is None or score < best[0]:
            best = (score, p0, periods, error)
    if best is None:
        raise ValueError(f"no period near {target:.1f} keeps every key at {MIN_PERIOD} or more")
    _, p0, periods, error = best
    return p0, periods, error


def resample(x: np.ndarray, rate_in: float, rate_out: float, taps: int = 32) -> np.ndarray:
    """Band-limited resampling with a Blackman-windowed sinc."""
    cutoff = 0.95 * min(rate_in, rate_out) / 2 / rate_in  # cycles per input sample
    count = int(len(x) * rate_out / rate_in)
    t = np.arange(count) * (rate_in / rate_out)
    base = np.floor(t).astype(np.int64)
    out = np.zeros(count)
    padded = np.concatenate([np.zeros(taps), x, np.zeros(taps + 1)])
    for j in range(-taps + 1, taps + 1):
        d = t - (base + j)
        window = 0.42 + 0.5 * np.cos(np.pi * d / taps) + 0.08 * np.cos(2 * np.pi * d / taps)
        kernel = 2 * cutoff * np.sinc(2 * cutoff * d) * window
        out += padded[base + j + taps] * kernel
    return out


def decay_rate(x: np.ndarray, rate: float, start: float, span: float = 3.0) -> float:
    """dB per second the signal falls from start (s) over span seconds, fitted to its
    RMS in 50 ms frames, ignoring frames within 60 dB of silence."""
    frame = int(rate * 0.05)
    segment = x[int(start * rate) : int((start + span) * rate)]
    count = len(segment) // frame
    if count < 3:
        return 0.0
    rms = np.sqrt(np.mean(segment[: count * frame].reshape(count, frame) ** 2, axis=1))
    peak = np.max(np.abs(x)) or 1.0
    db = 20 * np.log10(np.maximum(rms, 1e-12) / peak)
    keep = db > -60
    if keep.sum() < 3:
        return 0.0
    times = np.arange(count)[keep] * 0.05
    slope = np.polyfit(times, db[keep], 1)[0]
    return float(max(0.0, -slope))


def find_loop(y: np.ndarray, end: int, shortest: int, longest: int, window: int) -> int:
    """The even loop length L in [shortest, longest] for a loop ending at end whose
    start looks most like end does: the cosine similarity of the `window` samples
    either side of end - L and of end."""
    target = y[end - window : end + window]
    best_length, best_score = shortest, -2.0
    for length in range(shortest + shortest % 2, longest + 1, 2):
        start = end - length
        candidate = y[start - window : start + window]
        norm = np.linalg.norm(candidate) * np.linalg.norm(target)
        score = float(np.dot(candidate, target) / norm) if norm else -1.0
        if score > best_score:
            best_length, best_score = length, score
    return best_length


def similarity(y: np.ndarray, start: int, end: int, window: int) -> float:
    a, b = y[start - window : start + window], y[end - window : end + window]
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / norm) if norm else 0.0


def flatten_loop(y: np.ndarray, start: int, rate: float, db_per_s: float) -> np.ndarray:
    """Undo the recording's own decay from start on, so the loop holds its level and
    the player's software decay alone fades it."""
    out = y.copy()
    seconds = np.arange(len(y) - start) / rate
    out[start:] *= 10 ** (db_per_s * seconds / 20)
    return out


def crossfade_seam(y: np.ndarray, start: int, end: int, fade: int) -> np.ndarray:
    """Blend the loop's last `fade` samples into the samples before its start, so the
    jump from end - 1 back to start continues the signal."""
    out = y.copy()
    t = np.arange(1, fade + 1) / fade
    out[end - fade : end] = (1 - t) * y[end - fade : end] + t * y[start - fade : start]
    return out


def quantise(y: np.ndarray, scale: float, rng: np.random.Generator) -> np.ndarray:
    """Signed 8-bit with triangular (TPDF) dither of one step either way."""
    noise = rng.random(len(y)) - rng.random(len(y))
    return np.clip(np.round(y * scale + noise), -128, 127).astype(np.int8)


def quantise16(y: np.ndarray, scale: float, rng: np.random.Generator) -> np.ndarray:
    """Signed 16-bit with triangular (TPDF) dither of one step either way."""
    noise = rng.random(len(y)) - rng.random(len(y))
    return np.clip(np.round(y * scale + noise), -32768, 32767).astype(np.int16)


def attack_seconds(root: int, spec: SampleSpec) -> float:
    position = (root - LOWEST_KEY) / (HIGHEST_KEY - LOWEST_KEY)
    return spec.attack_bass_s + (spec.attack_treble_s - spec.attack_bass_s) * position


def trim_silence(x: np.ndarray, threshold: float = 0.01, lead: int = 32) -> np.ndarray:
    """Drop what comes before the first sample above threshold of the peak, less lead."""
    peak = np.max(np.abs(x)) if len(x) else 0.0
    if peak == 0:
        return x
    first = int(np.argmax(np.abs(x) > threshold * peak))
    return x[max(0, first - lead) :]


@dataclass(frozen=True)
class Prepared:
    """A root's sample before normalising: in the stored rate, with its loop made."""

    root: int
    keys: tuple[int, ...]
    signal: np.ndarray  # float, the recording's scale
    loop_start: int
    period: int
    periods: dict[int, int]
    decay_db_per_s: float
    loop_similarity: float
    max_cents_error: float
    gain: float  # from the region's volume opcode


def prepare(
    region: Region, recording: np.ndarray, rate_in: float, keys: list[int], spec: SampleSpec
) -> Prepared:
    """Resample, cut and loop one root's recording (mono, floats)."""
    root = region.pitch_keycenter
    ratios = [2 ** ((k - root) / 12 + region.tune / 1200) for k in keys]
    period, by_index, error = choose_period(ratios, NTSC_CLOCK / wanted_rate(root, spec))
    looped = loop_recording(region, recording, rate_in, NTSC_CLOCK / period, spec)
    return Prepared(
        root=root,
        keys=tuple(keys),
        signal=looped.signal,
        loop_start=looped.loop_start,
        period=period,
        periods={keys[i]: p for i, p in by_index.items()},
        decay_db_per_s=looped.decay_db_per_s,
        loop_similarity=looped.loop_similarity,
        max_cents_error=error,
        gain=10 ** (region.volume / 20),
    )


def wanted_rate(root: int, spec: SampleSpec) -> float:
    """The rate a root is stored at: 2 * harmonics * its pitch, within the spec's bounds."""
    return min(max(2 * spec.harmonics * pitch_hz(root), spec.min_rate), spec.max_rate)


@dataclass(frozen=True)
class Looped:
    """A root's recording at its stored rate: the attack, then a loop to the end."""

    signal: np.ndarray  # float, the recording's scale
    loop_start: int
    decay_db_per_s: float
    loop_similarity: float


def loop_recording(
    region: Region, recording: np.ndarray, rate_in: float, rate: float, spec: SampleSpec
) -> Looped:
    """Resample one root's recording (mono, floats) to rate, cut it after its attack and
    make a loop that ends there."""
    root = region.pitch_keycenter
    x = trim_silence(recording[region.offset :])
    attack = attack_seconds(root, spec)
    end = 2 * round(attack * rate / 2)
    loop = spec.loop_s * rate
    window = max(16, min(int(loop / 4), round(2 * rate / pitch_hz(root))))
    needed_in = int((end + window + 2) * rate_in / rate) + 64
    y = resample(x[:needed_in], rate_in, rate)
    length = find_loop(y, end, int(loop * 0.75), int(loop * 1.25), window)
    start = end - length
    db_per_s = decay_rate(x, rate_in, start / rate)
    fade = min(length // 2, max(2, round(spec.fade_s * rate)), start)
    flat = flatten_loop(y, start, rate, db_per_s)
    seam = similarity(flat, start, end, window)
    looped = crossfade_seam(flat, start, end, fade)[:end]
    return Looped(looped, start, db_per_s, seam)


def finish(prepared: list[Prepared], spec: SampleSpec) -> list[PaulaSample]:
    """Normalise each sample to full scale and quantise it; its level keeps the
    roots' recorded balance for the player to apply as volume."""
    rng = np.random.default_rng(spec.seed)
    peaks = [float(np.max(np.abs(p.signal))) * p.gain for p in prepared]
    loudest = max(peaks) or 1.0
    out = []
    for p, peak in zip(prepared, peaks, strict=True):
        scale = spec.peak / (float(np.max(np.abs(p.signal))) or 1.0)
        data = quantise(p.signal, scale, rng).tobytes()
        out.append(
            PaulaSample(
                root=p.root,
                keys=p.keys,
                data=data,
                loop_start=p.loop_start,
                period=p.period,
                periods=p.periods,
                rate=NTSC_CLOCK / p.period,
                level=peak / loudest,
                decay_db_per_s=p.decay_db_per_s,
                loop_similarity=p.loop_similarity,
                max_cents_error=p.max_cents_error,
            )
        )
    return out


def read_wav(path: Path) -> tuple[float, np.ndarray]:
    """A 16-bit PCM WAV as its rate and the mean of its channels, scaled to +-1."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise SystemExit(f"{path}: only 16-bit WAV files are read")
        channels, rate = w.getnchannels(), w.getframerate()
        frames = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return float(rate), frames.reshape(-1, channels).mean(axis=1) / 32768.0
