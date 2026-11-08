import math
from itertools import pairwise

import pytest
from amiga_env.piano import layers

SALAMANDER = [
    (1, 26),
    (27, 34),
    (35, 36),
    (37, 43),
    (44, 46),
    (47, 50),
    (51, 56),
    (57, 64),
    (65, 72),
    (73, 80),
    (81, 88),
    (89, 96),
    (97, 104),
    (105, 112),
    (113, 120),
    (121, 127),
]


class TestChoosingLayers:
    def test_eight_of_salamanders_sixteen_spread_by_centre_velocity(self):
        chosen = layers.choose_layers(SALAMANDER, 8)

        assert chosen == [
            (1, 26),
            (27, 34),
            (44, 46),
            (57, 64),
            (73, 80),
            (89, 96),
            (105, 112),
            (121, 127),
        ]

    def test_the_softest_and_loudest_layers_are_always_kept(self):
        chosen = layers.choose_layers(SALAMANDER, 3)

        assert chosen[0] == (1, 26) and chosen[-1] == (121, 127)

    def test_asking_for_more_layers_than_there_are_fails(self):
        with pytest.raises(ValueError):
            layers.choose_layers(SALAMANDER[:2], 3)


class TestLayerForVelocity:
    def test_a_velocity_plays_the_kept_layer_that_holds_it(self):
        table = layers.velocity_layers([(1, 26), (44, 46), (121, 127)])

        assert (table[1], table[26], table[45], table[127]) == (0, 0, 1, 2)

    def test_a_velocity_between_kept_layers_plays_the_nearest_centre(self):
        table = layers.velocity_layers([(1, 26), (44, 46), (121, 127)])

        assert table[30] == 1  # centre 45 is 15 away, centre 13.5 is 16.5 away
        assert table[29] == 0
        assert table[84] == 1 and table[85] == 2

    def test_the_table_has_an_entry_for_every_midi_velocity(self):
        assert len(layers.velocity_layers(SALAMANDER)) == 128


class TestVolumes:
    CHOSEN = ((1, 41), (42, 80), (81, 127))  # centres 21, 61 and 104
    LAYER_OF = layers.velocity_layers(CHOSEN)
    LEVELS = (0.05, 0.3, 1.0)  # each layer's recording is louder than the last

    def volumes(self, full=8192, veltrack=73.0):
        return layers.velocity_volumes(
            self.LEVELS, self.CHOSEN, self.LAYER_OF, [veltrack] * 3, full
        )

    def test_at_a_layers_centre_the_volume_is_the_sfzs_own_loudness(self):
        v = self.volumes()

        assert v[104] == round(8192 * 1.0 * layers.sfz_gain(104, 73))
        assert v[61] == pytest.approx(8192 * 0.3 * layers.sfz_gain(61, 73), abs=1)

    def test_loudness_rises_smoothly_across_layer_boundaries(self):
        v = self.volumes()
        steps = [20 * math.log10(b / a) for a, b in pairwise(v[1:])]

        boundary = [steps[40], steps[79]]  # 41 to 42 and 80 to 81
        within = steps[45:75]
        assert all(s > 0 for s in steps[20:])
        assert max(boundary) <= max(within) * 1.1

    def test_the_sfz_gain_follows_amp_veltrack(self):
        assert layers.sfz_gain(127, 73) == 1.0
        assert layers.sfz_gain(1, 100) == pytest.approx(1 / 127**2)
        assert layers.sfz_gain(1, 73) == pytest.approx(0.27, abs=1e-3)
        assert layers.sfz_gain(64, 0) == 1.0

    def test_volumes_fit_a_signed_word_and_never_reach_0(self):
        v = layers.velocity_volumes([1.0] * 3, self.CHOSEN, self.LAYER_OF, [73] * 3, 40000)

        assert v[0] == 0
        assert max(v) == layers.MAX_VOLUME
        assert min(v[1:]) >= 1
