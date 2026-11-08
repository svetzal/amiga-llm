"""Paula's held output, made band-limited at a WAV's rate, for listening on the host.

Paula holds each output value for one period (a zero-order hold). The
continuous signal is `y(t) = sum x[n] * r(t - n T)`, with r a rectangle one
period T long. Its spectrum is the mix's own, times the hold's sinc droop,
with images of it above 13,983 Hz (the mix rate's half): those images are
in Paula's real output. To write it at 44.1 kHz without aliasing, y is
passed through a low-pass kernel k (CUTOFF_HZ, a Blackman-windowed sinc)
and sampled at the WAV's rate:

    z(t) = sum x[n] * G(t - n T),    G(tau) = integral of k over [tau - T, tau]

G is tabulated for PHASES positions within a period and read with linear
interpolation between them. The images up to CUTOFF_HZ stay in, as they are
in Paula's output; the rest go.

Not modelled: the A3000's (and so the A3500's) fixed output filter, whose
corner frequency is not known, and the analogue stages after it. The A500
renders of EXP-004 (paula.py) are not changed by this module.
"""

import numpy as np

from .mixer import MIX_PERIOD
from .samples import NTSC_CLOCK

CUTOFF_HZ = 20_000.0
HALF_WIDTH = 16  # periods either side of the output time the kernel reaches
PHASES = 2048  # table positions within a period
STEPS_PER_PERIOD = 64  # integration steps of k within a period


def _table(cutoff: float, period_s: float) -> np.ndarray:
    """G(phase + j T) for j = -HALF_WIDTH .. HALF_WIDTH, PHASES + 1 phases of T.

    Row p, column j is G at tau = (p / PHASES + j) * T.
    """
    width = HALF_WIDTH * period_s
    dt = period_s / STEPS_PER_PERIOD
    u = np.arange(-width - period_s, width + 2 * period_s + dt, dt)
    window = np.where(
        np.abs(u) <= width,
        0.42 + 0.5 * np.cos(np.pi * u / width) + 0.08 * np.cos(2 * np.pi * u / width),
        0.0,
    )
    k = 2 * cutoff * np.sinc(2 * cutoff * u) * window
    k /= k.sum() * dt  # so the kernel's integral is exactly 1
    integral = np.concatenate([[0.0], np.cumsum(k) * dt])
    edges = np.concatenate([[u[0]], u + dt])

    def big_k(tau: np.ndarray) -> np.ndarray:
        return np.interp(tau, edges, integral)

    phase = np.arange(PHASES + 1) / PHASES
    j = np.arange(-HALF_WIDTH, HALF_WIDTH + 1)
    tau = (phase[:, None] + j[None, :]) * period_s
    return big_k(tau) - big_k(tau - period_s)


def render(values: np.ndarray, rate: int, cutoff: float = CUTOFF_HZ) -> np.ndarray:
    """Held values (one per mix period, either side's output) at `rate`, as floats."""
    period_s = MIX_PERIOD / NTSC_CLOCK
    table = _table(cutoff, period_s).astype(np.float32)
    count = len(values) * MIX_PERIOD * rate // NTSC_CLOCK
    m = np.arange(count, dtype=np.int64)
    # Output time t = m / rate, in periods: n0 = floor, phase = the rest.
    scaled = m * NTSC_CLOCK  # t * NTSC_CLOCK * rate
    n0 = scaled // (MIX_PERIOD * rate)
    phase = (scaled % (MIX_PERIOD * rate)).astype(np.float64) / (MIX_PERIOD * rate)
    position = phase * PHASES
    row = np.minimum(position.astype(np.int64), PHASES - 1)
    weight = (position - row).astype(np.float32)
    x = np.concatenate(
        [np.zeros(HALF_WIDTH + 1), np.asarray(values, dtype=np.float32), np.zeros(HALF_WIDTH + 1)]
    ).astype(np.float32)
    out = np.zeros(count, dtype=np.float32)
    for column, j in enumerate(range(-HALF_WIDTH, HALF_WIDTH + 1)):
        g = table[row, column] * (1 - weight) + table[row + 1, column] * weight
        out += x[n0 - j + HALF_WIDTH + 1] * g
    return out


def stereo_wav_frames(left: np.ndarray, right: np.ndarray, rate: int) -> np.ndarray:
    """16-bit stereo frames at `rate` from the two sides' 14-bit Paula output."""
    frames = np.stack([render(left, rate), render(right, rate)], axis=1) * 4
    return np.clip(np.round(frames), -32768, 32767).astype(np.int16)
