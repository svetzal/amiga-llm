"""Unix compress (.Z) decompression, as the 3.2 Installer's UNCOMPRESS does it."""

import base64
import random

import pytest

from amiga_env import compress

# `compress -b 9` (macOS) of the text from text_1500() below. Its table fills
# up, so the stream grows from 9-bit to 10-bit codes past the header's limit.
NINE_BIT = base64.b64decode(
    "H52JZsacCSMGhBgzYUCQIXjmjBgyBQc+DDNwIYgxZc6MMVjm4kMzBcWEIYMGxBkzaNCYKUNmDMSO"
    "KtGUERNxTEA0EkGY2ZmSZhk0In9mRKhyjBg0I8u4bAh0DE4QSs9APXmmpZgxLheiwVgmjECdAUGE"
    "Kdmw4dGKD7ceJOjVIMKHGsvwpJky5UyjK7eKJaNzY8KZHQOa4QtCJ5nDVfmqDBNGKBmUOx+mfUxy"
    "LEgxVbeexIzzKlavW4sWHsO4oMDDjcl0fNxRYxiUJi/KFrvVK1agYs0UBoF7pGqCvMUe1a3wZ+GS"
    "fFdr5gySjEPVVwMqRQPxzNaWUqk+BolQd0qKujvShCimTFeMAjNu5A3yvMOu5SXPRKr7jNKEEDF6"
    "Vb3aOEaEXTFWmGIkcRYbS5QJhBBp5bmGGVS/bYURUnLpNlhqAb3mkEwK8UXQXQMNZB5EF5201X2x"
    "rTeSSF6BZJ1Y+Mk0VkEGGSRTeYeR1JlMI0VnHmlIyZRWRz/1VNxRjeEmU2I0bSTXRjMNltJApKVk"
    "n0BmbNadGc81JhdmDplhX2NBuZSRYWYMJJVCIlmHEVIXOXWSeeZVZZxDWD0UHEkoaaRQfrodxNpC"
    "ZSlkH1FyrfeSc9bZ5xVF32HGG3UPYWVQb/s1hpFJNJWnkH0L/SXTYMgpRFFXI3XG0kmVmaFdYwaR"
    "pNph1Jl3lEs4eVWRVwN5Zd1lNrXEW2MnoWQUQTOZ4ZBCJ2UkEnXebYdUVQMNBFRqB62EkFzmsQVR"
    "SvZZ5xRpSm2nUkHOLSVSSX05FF91KbkkEHUcmSeXeSS1dBhGj2HGUmEQISUSdYuxJNJhB10kE0GD"
    "vRZQUiO9dhJGE5UElENSbXSVffZl1JgZDb3mXFUUCUTTSVuRlpBAB11kk1IecaYaaYs5tBRJLlF0"
    "0WZZJfQaZ1Ox1BBstY1FXUpOORTdZiWJ5dVBBiXk2nhOKQXRSjb9hBFvqim000gC/RdXQa+VxJFJ"
    "K51kE0jUkdaReQiNhFFDOoG2EGOvzaSTQva5hNJnLQF1VUZdJQQbdaQxJpZGLbGl0GmFaQRVeWOJ"
    "xdRRLpW30EFdtQYVSwV5xVJLg53kHG8lMVYVSw59RlB0pDFGmkgH8YXZQ4eJRNBPVz0klxn2vWbe"
    "a951NZBUByGlUHkC4dfVa0CFFh5Gh6l1lFsgmTXQYOZJdVFmfu10ERo="
)


def text_1500() -> bytes:
    rng = random.Random(7)
    return "".join(rng.choice("abcdefgh ") for _ in range(1500)).encode()


def pack(codes: list[tuple[int, int, int]], max_bits: int = 9) -> bytes:
    """A .Z stream from (bit position after the header, width, code) triples."""
    bits = 0
    for position, width, code in codes:
        bits |= code << position
    end = max(position + width for position, width, _ in codes)
    body = bits.to_bytes(-(-end // 8), "little")
    return compress.MAGIC + bytes([compress.BLOCK_MODE | max_bits]) + body


def test_matches_compress_for_a_stream_whose_table_fills():
    assert compress.uncompress(NINE_BIT) == text_1500()


def test_decodes_a_code_it_has_not_yet_stored():
    # a, then 257 ("aa"), which the decoder builds from the previous string
    assert compress.uncompress(pack([(0, 9, 97), (9, 9, 257)])) == b"aaa"


def test_skips_the_rest_of_the_code_group_after_a_clear():
    # a, CLEAR, then b at the start of the next group of eight 9-bit codes
    stream = pack([(0, 9, 97), (9, 9, 256), (72, 9, 98)])

    assert compress.uncompress(stream) == b"ab"


def test_rejects_data_that_is_not_compressed():
    with pytest.raises(ValueError):
        compress.uncompress(b"plain text")


def test_rejects_a_code_beyond_the_table():
    with pytest.raises(ValueError):
        compress.uncompress(pack([(0, 9, 97), (9, 9, 300)]))


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Workbench.guide.Z", "Workbench.guide"), ("monitors.catalog", None), (".Z", None)],
)
def test_drops_the_suffix_the_installer_drops(name, expected):
    assert compress.uncompressed_name(name) == expected
