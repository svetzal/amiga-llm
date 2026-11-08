"""The A3500 piano's software mixer, as the 68030 runs it: integer arithmetic only.

EXP-005, software mixing on the A3500, chose this design (its way B).

Paula plays the mix at period 128 on NTSC, 3,579,545 / 128 = 27,965.2 Hz,
in blocks of BLOCK samples from two buffers in chip RAM. The channel 0
audio interrupt mixes the next block.

Samples are signed 16-bit, in fast RAM. A voice reads its sample at a
16.16 phase: the integer part is the sample's index, the fraction f is 16
bits. Each output sample is the linear interpolation between the sample at
the integer part, s0, and the next one, s1 (`interpolate`):

    v = s0 + (((s1 - s0) * (f >> 1)) >> 15)

The fraction is taken as 15 bits so that MULS.W, which is signed, sees it
as positive. s1 - s0 must fit a signed word; the build checks every sample
(`largest_difference`). The result lies between s0 and s1, so it fits a
word too. For each output sample and each voice, the 68030 does, with d0
the phase's integer part, d2 its fraction, d1 and d3 the step's fraction
and integer part, d7 the two multipliers (left in the low word, right in
the high word), a0 the sample, a2 and a3 the left and right sums:

    move.l  (a0,d0.l*2),d4   ; s0 in the high word, s1 in the low word
    move.l  d4,d6
    swap    d6               ; d6.w = s0
    sub.w   d6,d4            ; d4.w = s1 - s0
    move.w  d2,d5
    lsr.w   #1,d5            ; f >> 1
    muls.w  d5,d4            ; (s1 - s0) * (f >> 1)
    add.l   d4,d4
    swap    d4               ; >> 15: the high word of twice the product
    add.w   d6,d4            ; v
    move.w  d4,d6
    muls.w  d7,d4            ; v * left multiplier
    add.l   d4,(a2)+         ; to the left sum, 32 bits
    swap    d7
    muls.w  d7,d6            ; v * right multiplier
    add.l   d6,(a3)+         ; to the right sum
    add.w   d1,d2            ; the step: fraction, then integer part
    addx.l  d3,d0

18 instructions a voice-sample with a pan. The next sample does the right
side first, so one SWAP of d7 a sample keeps the multipliers in step; the
loop is unrolled by an even number and ends on a compare of a2 with the
end of the sums (CMPA.L and BNE), which frees d7 from counting. In mono
(pan width 0) one multiplier serves both sides: the MOVE.W copy, the second
MULS.W, its ADD.L and the SWAP go, and 14 instructions remain.

A voice's multipliers are `volume * gain >> 16` for each side (one MULU.W a
side), set once a block. With a pan width of 0 the two gains are equal, so
the 68030 can do one MULS and one sum for both sides; the result is the
same.

The phase is checked against the loop only at the start of a block: while
its integer part is at or past the sample's end, the loop's length is
subtracted. Every step is below MAX_STEP, so in one block s0 is read less
than PAD - 1 samples past the end, and s1 less than PAD. The 68030 copies PAD samples of the loop after each
sample's end (going round the loop again when it is shorter than PAD), so
the inner loop never checks a bound.

Once a block, each side's 32-bit sums become 16-bit values: shifted right
by OUTPUT_SHIFT (arithmetic, so rounded down) and clamped to -32,768 to
32,767 (`output16`). A multiplier is a signed word, so a voice can add at
most 32767 * 32767 to a sum; the shift of 14, two less than taking the high
word, lets a piece reach full scale. A sum wraps at 32 bits only above four
times full scale.

Output is 14-bit stereo. Each side's 16-bit value S goes out on two Paula
channels: its high byte (S >> 8) on a channel at volume 64, and its bits 7
to 2 ((S >> 2) & 63) on a channel at volume 1. Paula adds them: 64 * high
+ low = S >> 2. Left is channels 0 and 3, right is channels 1 and 2.
"""

import math

import numpy as np

from .samples import NTSC_CLOCK

MIX_PERIOD = 128
MIX_RATE = NTSC_CLOCK / MIX_PERIOD  # 27,965.2 Hz
BLOCK = 512  # samples a block
BLOCK_HZ = MIX_RATE / BLOCK  # 54.6 blocks a second
ONE = 1 << 16  # 1.0 in 16.16
MAX_STEP = 2 * ONE  # every key's step is below this
PAD = BLOCK * MAX_STEP // ONE  # samples the 68030 copies after each sample's end
OUTPUT_SHIFT = 14  # a 32-bit sum's shift to a 16-bit output value
GAIN_ONE = 65535  # a pan gain of 1.0
LEFT_CHANNELS, RIGHT_CHANNELS = (0, 3), (1, 2)  # (volume 64, volume 1) a side


def sample_of_ms(ms: int) -> int:
    """The output sample a score millisecond falls on: ms * 3,579,545 // 128,000.

    The 68030 does it with MULU.L into 64 bits and DIVU.L.
    """
    return ms * NTSC_CLOCK // (MIX_PERIOD * 1000)


def ms_of_sample(sample: int) -> int:
    """The millisecond an output sample falls in (for reports)."""
    return sample * MIX_PERIOD * 1000 // NTSC_CLOCK


def step(rate: float, ratio: float) -> int:
    """The 16.16 step that plays a sample stored at rate, `ratio` times faster."""
    value = round(rate * ratio / MIX_RATE * ONE)
    if not 0 < value < MAX_STEP:
        raise ValueError(f"step {value / ONE:.3f} is not between 0 and {MAX_STEP // ONE}")
    return value


def pan_gains(key: int, width: float, keys: int = 88) -> tuple[int, int]:
    """Left and right gains (0 to 65535) for a key, bass left and treble right.

    Constant power: the angle runs from 45 degrees (the middle) by width
    either way, so width 1 puts the lowest key hard left and the highest
    hard right, and width 0 puts every key in the middle.
    """
    position = key / (keys - 1)
    angle = math.pi / 4 * (1 + width * (2 * position - 1))
    return round(GAIN_ONE * math.cos(angle)), round(GAIN_ONE * math.sin(angle))


def multiplier(volume: int, gain: int) -> int:
    """A side's multiplier: volume * gain >> 16."""
    return volume * gain >> 16


def faded(value: int, quarters: int) -> int:
    """A multiplier during a cut's fade: value * quarters >> 2."""
    return value * quarters >> 2


def padded(data: np.ndarray, loop_start: int) -> np.ndarray:
    """A sample as the 68030 holds it: PAD more samples, going round the loop."""
    loop = np.arange(PAD) % (len(data) - loop_start) + loop_start
    return np.concatenate([data, data[loop]]).astype(np.int16)


def wrap_phase(phase: int, length: int, loop_start: int) -> int:
    """The phase at a block's start, brought back into the sample round its loop."""
    while phase >> 16 >= length:
        phase -= (length - loop_start) << 16
    return phase


def interpolate(data: np.ndarray, positions: np.ndarray) -> np.ndarray:
    """The interpolated sample at each 16.16 position, as the 68030 makes it."""
    index = positions >> 16
    s0 = data[index].astype(np.int64)
    difference = data[index + 1].astype(np.int64) - s0
    return s0 + ((difference * ((positions & 0xFFFF) >> 1)) >> 15)


def largest_difference(data: np.ndarray) -> int:
    """The largest step between neighbouring samples; SUB.W needs it below 32,768."""
    return int(np.abs(np.diff(data.astype(np.int64))).max(initial=0))


def mix_run(
    data: np.ndarray, phase: int, step_: int, left: int, right: int, count: int
) -> tuple[np.ndarray, np.ndarray, int]:
    """One voice's products for `count` output samples, and its phase after them.

    Products are int64 so the caller can see the true sums; `wrap32` gives
    what the 68030's ADD.L leaves.
    """
    values = interpolate(data, phase + step_ * np.arange(count, dtype=np.int64))
    return values * left, values * right, phase + step_ * count


def wrap32(values: np.ndarray) -> np.ndarray:
    """Sums as 32-bit longwords hold them: wrapped."""
    return (values + 2**31) % 2**32 - 2**31


def output16(sums: np.ndarray) -> np.ndarray:
    """A side's 32-bit sums as 16-bit output values: shifted, then clamped."""
    return np.clip(sums >> OUTPUT_SHIFT, -32768, 32767).astype(np.int16)


def clamped(sums: np.ndarray) -> int:
    """How many of a side's 32-bit sums `output16` clamps."""
    shifted = sums >> OUTPUT_SHIFT
    return int(np.count_nonzero((shifted < -32768) | (shifted > 32767)))


def split14(sums: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """A side's sums as the bytes of its two channels: (high byte, bits 7 to 2)."""
    wide = sums.astype(np.int32)
    return (wide >> 8).astype(np.int8), ((wide >> 2) & 63).astype(np.int8)


def paula_output(high: np.ndarray, low: np.ndarray) -> np.ndarray:
    """What Paula makes of a side's two channels: 64 * high + 1 * low."""
    return high.astype(np.int32) * 64 + low.astype(np.int32)


def checksum(left: np.ndarray, right: np.ndarray) -> tuple[int, int]:
    """A Fletcher-style checksum of a block's output values, for the voice log.

    The words are taken as unsigned, left then right for each sample in turn.
    a is their sum and b the sum of the running values of a, both modulo
    2^32: two ADD.L a word on the 68030.
    """
    words = np.empty(2 * len(left), dtype=np.int64)
    words[0::2] = left.astype(np.int64) & 0xFFFF
    words[1::2] = right.astype(np.int64) & 0xFFFF
    running = np.cumsum(words)
    return int(running[-1]) & 0xFFFFFFFF, int(running.sum()) & 0xFFFFFFFF
