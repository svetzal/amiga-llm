import numpy as np
import pytest
from amiga_env.piano import picture
from PIL import Image


def gradient(width=32, height=20):
    x = np.linspace(0, 255, width)
    rgb = np.stack([np.tile(x, (height, 1))] * 3, axis=2)
    rgb[..., 2] = 40.0
    return rgb


class TestCrop:
    def test_the_left_four_by_three_area_is_kept_and_squashed_to_320_by_200(self):
        master = np.zeros((300, 600, 3), dtype=np.uint8)
        master[:, :400] = 200  # the left 4:3 area is bright, the rest black

        found = picture.crop_and_resize(Image.fromarray(master))

        assert found.shape == (200, 320, 3)
        assert found.min() > 190


class TestPalette:
    def test_colours_snap_to_ocs_steps_of_17(self):
        found = picture.ocs_palette(np.array([[10.0, 30.0, 250.0]]))

        assert found.tolist() == [[17.0, 34.0, 255.0]]

    def test_duplicates_after_snapping_are_merged_and_the_darkest_comes_first(self):
        centres = np.array([[250.0, 250.0, 250.0], [1.0, 2.0, 3.0], [0.0, 0.0, 5.0]])

        found = picture.ocs_palette(centres)

        assert found.tolist() == [[0.0, 0.0, 0.0], [255.0, 255.0, 255.0]]

    def test_kmeans_is_the_same_for_the_same_seed(self):
        pixels = gradient().reshape(-1, 3)
        weights = np.ones(len(pixels))

        first = picture.weighted_kmeans(pixels, 4, weights, seed=1, iterations=5)
        again = picture.weighted_kmeans(pixels, 4, weights, seed=1, iterations=5)

        assert np.array_equal(first, again)

    def test_bright_pixels_weigh_more(self):
        # 90 dark pixels and 10 bright ones: one centre each way when the
        # bright are weighted, the bright one sits on them.
        pixels = np.array([[10.0, 10.0, 10.0]] * 90 + [[250.0, 250.0, 250.0]] * 10)
        weights = 1 + picture.luminance(pixels) / 255 * 6

        centres = picture.weighted_kmeans(pixels, 2, weights, seed=3, iterations=10)

        assert sorted(c[0] for c in centres) == pytest.approx([10.0, 250.0])

    @pytest.mark.parametrize(("rgb", "word"), [((255, 0, 0), 0xF00), ((187, 153, 85), 0xB95)])
    def test_an_ocs_colour_is_a_register_word(self, rgb, word):
        assert picture.ocs_word(rgb) == word
        assert picture.rgb_of(word) == rgb

    @pytest.mark.parametrize("text", ["B9", "B955", "XYZ"])
    def test_a_written_colour_is_three_hex_digits(self, text):
        with pytest.raises(ValueError):
            picture.parse_ocs(text)


class TestDither:
    def test_a_colour_in_the_palette_needs_no_dither(self):
        palette = np.array([[0.0, 0.0, 0.0], [255.0, 255.0, 255.0]])
        rgb = np.full((4, 8, 3), 255.0)

        assert (picture.floyd_steinberg(rgb, palette) == 1).all()

    def test_a_half_grey_dithers_to_half_of_each(self):
        palette = np.array([[0.0, 0.0, 0.0], [255.0, 255.0, 255.0]])
        rgb = np.full((16, 16, 3), 127.5)

        found = picture.floyd_steinberg(rgb, palette)

        assert found.mean() == pytest.approx(0.5, abs=0.05)

    def test_the_whole_conversion_is_deterministic(self):
        master = Image.fromarray(gradient(400, 300).astype(np.uint8))
        spec = picture.PictureSpec(colours=4, iterations=5)

        first = picture.convert(master, spec)
        again = picture.convert(master, spec)

        assert np.array_equal(first.indices, again.indices)
        assert np.array_equal(first.palette, again.palette)
        assert first.indices.shape == (200, 320)


class TestPlanes:
    def test_each_plane_holds_one_bit_of_the_index(self):
        indices = np.zeros((1, 16), dtype=np.uint8)
        indices[0, 0] = 0b0101
        indices[0, 15] = 0b1000

        planes = picture.bitplanes(indices, 4)

        assert planes == [b"\x80\x00", b"\x00\x00", b"\x80\x00", b"\x00\x01"]

    def test_a_row_is_a_whole_number_of_words(self):
        with pytest.raises(ValueError, match="words"):
            picture.bitplanes(np.zeros((1, 8), dtype=np.uint8), 4)

    def test_an_index_must_fit_the_planes(self):
        with pytest.raises(ValueError, match="fit"):
            picture.bitplanes(np.full((1, 16), 16, dtype=np.uint8), 4)


class TestIlbm:
    def test_an_ilbm_reads_back_as_written(self):
        rng = np.random.default_rng(0)
        indices = rng.integers(0, 16, (200, 320), dtype=np.uint8)
        colours = [n * 0x111 for n in range(16)]

        found, read_colours = picture.read_ilbm(picture.ilbm(indices, colours))

        assert np.array_equal(found, indices)
        assert read_colours == colours

    def test_the_header_says_320_by_200_four_planes_uncompressed(self):
        data = picture.ilbm(np.zeros((200, 320), dtype=np.uint8), [0] * 16)

        assert data[:4] == b"FORM" and data[8:16] == b"ILBMBMHD"
        assert data[20:24] == bytes([1, 64, 0, 200])  # 320, 200
        assert data[28:31] == bytes([4, 0, 0])  # planes, no mask, no compression
        assert len(data) == 8 + int.from_bytes(data[4:8], "big")

    def test_the_body_interleaves_each_rows_planes(self):
        indices = np.zeros((2, 16), dtype=np.uint8)
        indices[1, 0] = 0b0010

        data = picture.ilbm(indices, [0] * 16)

        body = data[data.index(b"BODY") + 8 :]
        assert body == bytes(8) + b"\x00\x00" + b"\x80\x00" + bytes(4)

    def test_sixteen_colours_for_four_planes(self):
        with pytest.raises(ValueError, match="16 colours"):
            picture.ilbm(np.zeros((1, 16), dtype=np.uint8), [0] * 13)
