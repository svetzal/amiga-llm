import pytest
from amiga_env.piano.sfz import Region, expand, parse, parse_key

SALAMANDER_LIKE = r"""
//Notes
<group> amp_veltrack=73 ampeg_release=1

<region> sample=44.1khz16bit\A0v8.wav lokey=21 hikey=22 lovel=57 hivel=64 pitch_keycenter=21
<region> sample=44.1khz16bit\C4v8.wav lokey=59 hikey=61 lovel=57 hivel=64

//Notes without dampers
<group> amp_veltrack=73 ampeg_release=5
<region> sample=44.1khz16bit\F#6v8.wav lokey=89 hikey=91 lovel=57 hivel=64 pitch_keycenter=90 tune=-13

<group> trigger=release volume=-4
<region> sample=44.1khz16bit\harmLA0.wav lokey=20 hikey=22 lovel=45 pitch_keycenter=21
"""


class TestParse:
    def test_reads_regions_and_what_they_inherit_from_their_group(self):
        regions = parse(SALAMANDER_LIKE)

        assert regions[0] == Region(
            sample="44.1khz16bit/A0v8.wav",
            lokey=21,
            hikey=22,
            pitch_keycenter=21,
            lovel=57,
            hivel=64,
            ampeg_release=1.0,
        )
        assert regions[2].ampeg_release == 5.0
        assert regions[2].tune == -13
        assert (regions[3].trigger, regions[3].volume) == ("release", -4.0)

    def test_a_missing_keycenter_is_60(self):
        assert parse(SALAMANDER_LIKE)[1].pitch_keycenter == 60

    def test_a_new_group_forgets_the_last_ones_opcodes(self):
        regions = parse("<group> tune=5\n<region> sample=a.wav\n<group>\n<region> sample=b.wav")

        assert [r.tune for r in regions] == [5, 0]

    def test_a_region_overrides_its_group(self):
        regions = parse("<group> lovel=10 hivel=20\n<region> sample=a.wav hivel=30")

        assert (regions[0].lovel, regions[0].hivel) == (10, 30)

    def test_key_sets_the_range_and_the_centre(self):
        region = parse("<region> sample=a.wav key=c#4")[0]

        assert (region.lokey, region.hikey, region.pitch_keycenter) == (61, 61, 61)

    def test_a_sample_path_may_hold_spaces_and_takes_the_default_path(self):
        text = "<control> default_path=Samples\\\n<region> sample=Grand A0 v8.wav lokey=21"

        region = parse(text)[0]

        assert region.sample == "Samples/Grand A0 v8.wav"
        assert region.lokey == 21

    def test_ignores_headers_and_opcodes_it_does_not_use(self):
        text = "<curve> curve_index=7 v000=0\n<region> sample=a.wav amp_veltrack=73 offset=12"

        regions = parse(text)

        assert len(regions) == 1
        assert regions[0].offset == 12

    def test_reads_define_and_include(self):
        files = {"keys.sfz": "<region> sample=$NAME.wav lokey=$LOW"}
        text = '#define $NAME A0v8\n#define $LOW 21\n#include "keys.sfz"\n'

        region = parse(text, files.__getitem__)[0]

        assert (region.sample, region.lokey) == ("A0v8.wav", 21)


def test_expand_drops_line_and_block_comments():
    assert expand("a // b\n/* c\nd */ e", lambda n: "").split() == ["a", "e"]


@pytest.mark.parametrize(
    ("name", "note"), [("60", 60), ("c4", 60), ("C4", 60), ("a0", 21), ("eb3", 51), ("c-1", 0)]
)
def test_parse_key(name, note):
    assert parse_key(name) == note


def test_region_plays_its_keys_and_velocities():
    region = Region("a.wav", lokey=21, hikey=22, lovel=57, hivel=64)

    assert region.plays(22, 57)
    assert not region.plays(23, 60)
    assert not region.plays(21, 65)
