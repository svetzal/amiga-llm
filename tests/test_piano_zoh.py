import numpy as np
import pytest
from amiga_env.piano import zoh
from amiga_env.piano.mixer import MIX_RATE

RATE = 44100


def tone(hz, seconds=1.0, amplitude=4000):
    t = np.arange(int(seconds * MIX_RATE)) / MIX_RATE
    return np.round(amplitude * np.sin(2 * np.pi * hz * t))


def level(y, hz, rate=RATE):
    """The amplitude of y at hz, by projection, away from the ends."""
    y = y[2000:-2000]
    t = np.arange(len(y)) / rate
    return 2 * abs(np.mean(y * np.exp(-2j * np.pi * hz * t)))


def test_a_constant_comes_out_unchanged():
    y = zoh.render(np.full(10000, 1234), RATE)

    assert y[100:-100] == pytest.approx(1234, abs=0.05)


def test_the_output_lasts_as_long_as_the_input():
    assert len(zoh.render(np.zeros(27965), RATE)) == 27965 * 128 * RATE // 3_579_545


@pytest.mark.parametrize("hz", [1000, 6000, 10000])
def test_a_tone_droops_as_a_hold_does(hz):
    y = zoh.render(tone(hz), RATE)

    assert level(y, hz) / 4000 == pytest.approx(np.sinc(hz / MIX_RATE), abs=0.003)


def test_the_holds_image_below_the_cutoff_stays():
    y = zoh.render(tone(10000), RATE)

    image = MIX_RATE - 10000
    assert level(y, image) / 4000 == pytest.approx(np.sinc(image / MIX_RATE), abs=0.01)


def test_an_image_above_the_wav_rates_half_is_removed_not_folded_back():
    y = zoh.render(tone(3000), RATE)

    folded = RATE - (MIX_RATE - 3000)  # where the 24,965 Hz image would alias to
    assert 20 * np.log10(level(y, folded) / 4000 + 1e-12) < -60


def test_stereo_frames_are_16_bit_at_four_times_the_14_bit_values():
    frames = zoh.stereo_wav_frames(np.full(5000, 1000), np.full(5000, -1000), RATE)

    assert frames.dtype == np.int16
    assert frames[100:-100].tolist() == [[4000, -4000]] * (len(frames) - 200)
