"""A picture for an OCS lowres screen: palette, dither, bitplanes and IFF ILBM.

The title picture of EXP-004's player is made on the host from a large
master image, in these steps (Stacey's design, 2026-11-07):

1. crop the master to its left 4:3 area (x from 0 to h * 4 / 3);
2. resize it to 320x200 with Lanczos. NTSC lowres pixels are taller than
   wide, so squashing a 4:3 area into 320x200 keeps its proportions;
3. apply a gamma of 0.8 (brightens the dark midtones);
4. choose colours by k-means, weighting each pixel by 1 + 6 * luminance /
   255 so that the few bright pixels (keys, gold) get colours of their own;
5. snap each colour to OCS 12-bit (multiples of 17 per channel), keep the
   distinct ones and sort them by luminance;
6. Floyd-Steinberg dither the whole picture to that palette.

Everything is deterministic: the k-means starts from a seeded generator.
"""

import struct
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image

WIDTH, HEIGHT = 320, 200
LUMINANCE = np.array([0.299, 0.587, 0.114])
OCS_STEP = 17  # 255 / 15: one step of an OCS colour channel in 8 bits


class PictureSpec(NamedTuple):
    colours: int = 13
    gamma: float = 0.8
    bright_weight: float = 6.0  # weight = 1 + bright_weight * luminance / 255
    seed: int = 1
    iterations: int = 40


def crop_and_resize(image: Image.Image, width: int = WIDTH, height: int = HEIGHT) -> np.ndarray:
    """The left 4:3 area of `image`, resized to `width` x `height`, as float RGB 0-255."""
    rgb = image.convert("RGB")
    h = rgb.size[1]
    area = rgb.crop((0, 0, h * 4 // 3, h)).resize((width, height), Image.LANCZOS)
    return np.asarray(area, dtype=np.float64)


def apply_gamma(rgb: np.ndarray, gamma: float) -> np.ndarray:
    return (rgb / 255.0) ** gamma * 255.0


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb @ LUMINANCE


def weighted_kmeans(
    pixels: np.ndarray, k: int, weights: np.ndarray, seed: int, iterations: int
) -> np.ndarray:
    """`k` centres for `pixels` (N x 3), started from pixels drawn by weight."""
    rng = np.random.default_rng(seed)
    centres = pixels[rng.choice(len(pixels), k, replace=False, p=weights / weights.sum())]
    for _ in range(iterations):
        labels = ((pixels[:, None, :] - centres[None]) ** 2).sum(-1).argmin(1)
        for c in range(k):
            members = labels == c
            if members.any():
                centres[c] = np.average(pixels[members], axis=0, weights=weights[members])
    return centres


def ocs_palette(centres: np.ndarray) -> np.ndarray:
    """Centres snapped to OCS 12-bit colours, distinct, darkest first (8-bit values)."""
    snapped = np.unique(np.round(centres / OCS_STEP) * OCS_STEP, axis=0)
    return snapped[np.argsort(luminance(snapped), kind="stable")]


def floyd_steinberg(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Each pixel's palette index, diffusing the error 7/16, 3/16, 5/16, 1/16."""
    image = rgb.astype(np.float64).copy()
    height, width = image.shape[:2]
    indices = np.zeros((height, width), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            old = image[y, x]
            k = int(((palette - old) ** 2).sum(1).argmin())
            indices[y, x] = k
            error = old - palette[k]
            if x + 1 < width:
                image[y, x + 1] += error * 7 / 16
            if y + 1 < height:
                if x > 0:
                    image[y + 1, x - 1] += error * 3 / 16
                image[y + 1, x] += error * 5 / 16
                if x + 1 < width:
                    image[y + 1, x + 1] += error * 1 / 16
    return indices


class Picture(NamedTuple):
    indices: np.ndarray  # HEIGHT x WIDTH palette indices
    palette: np.ndarray  # the picture's colours, 8-bit RGB, darkest first


def convert(master: Image.Image, spec: PictureSpec) -> Picture:
    """The master as an OCS lowres picture of at most `spec.colours` colours."""
    rgb = apply_gamma(crop_and_resize(master), spec.gamma)
    pixels = rgb.reshape(-1, 3)
    weights = 1.0 + luminance(pixels) / 255.0 * spec.bright_weight
    centres = weighted_kmeans(pixels, spec.colours, weights, spec.seed, spec.iterations)
    palette = ocs_palette(centres)
    return Picture(floyd_steinberg(rgb, palette), palette)


def ocs_word(rgb: Sequence[float]) -> int:
    """An 8-bit RGB colour on the OCS 12-bit grid as a colour register word ($0RGB)."""
    r, g, b = (round(c / OCS_STEP) for c in rgb)
    return r << 8 | g << 4 | b


def parse_ocs(text: str) -> int:
    """A colour written as three hex digits, `B95`, as a colour register word."""
    if len(text) != 3:
        raise ValueError(f"an OCS colour is three hex digits, not {text!r}")
    return int(text, 16)


def rgb_of(word: int) -> tuple[int, int, int]:
    return ((word >> 8 & 15) * OCS_STEP, (word >> 4 & 15) * OCS_STEP, (word & 15) * OCS_STEP)


def bitplanes(indices: np.ndarray, depth: int) -> list[bytes]:
    """`depth` bitplanes of `indices`, each row a whole number of 16-bit words."""
    width = indices.shape[1]
    if width % 16:
        raise ValueError("an OCS bitplane row is a whole number of words")
    if int(indices.max(initial=0)) >= 1 << depth:
        raise ValueError(f"an index does not fit {depth} planes")
    return [np.packbits((indices >> p) & 1, axis=1).tobytes() for p in range(depth)]


def ilbm(indices: np.ndarray, colours: Sequence[int], depth: int = 4) -> bytes:
    """An uncompressed IFF ILBM: BMHD, CAMG (lowres, 0), CMAP and an interleaved BODY.

    `colours` are colour register words ($0RGB), 1 << depth of them.
    """
    if len(colours) != 1 << depth:
        raise ValueError(f"{depth} planes need {1 << depth} colours")
    height, width = indices.shape
    planes = bitplanes(indices, depth)
    row = width // 8
    body = b"".join(planes[p][y * row : (y + 1) * row] for y in range(height) for p in range(depth))
    # BMHD: width, height, x, y, planes, masking, compression, pad, transparent
    # colour, x aspect, y aspect (10:11 for NTSC lowres), page width and height.
    bmhd = struct.pack(
        ">HHhhBBBBHBBhh", width, height, 0, 0, depth, 0, 0, 0, 0, 10, 11, width, height
    )
    cmap = bytes(c for word in colours for c in rgb_of(word))
    chunks = _chunk(b"BMHD", bmhd) + _chunk(b"CAMG", struct.pack(">L", 0))
    chunks += _chunk(b"CMAP", cmap) + _chunk(b"BODY", body)
    return b"FORM" + struct.pack(">L", 4 + len(chunks)) + b"ILBM" + chunks


def _chunk(name: bytes, data: bytes) -> bytes:
    pad = b"\0" if len(data) % 2 else b""
    return name + struct.pack(">L", len(data)) + data + pad


def read_ilbm(data: bytes) -> tuple[np.ndarray, list[int]]:
    """The indices and colour words of an uncompressed ILBM that `ilbm` wrote."""
    if data[:4] != b"FORM" or data[8:12] != b"ILBM":
        raise ValueError("not an IFF ILBM")
    chunks, at = {}, 12
    while at < len(data):
        name, size = data[at : at + 4], struct.unpack_from(">L", data, at + 4)[0]
        chunks[name] = data[at + 8 : at + 8 + size]
        at += 8 + size + size % 2
    width, height, _, _, depth, _, compression = struct.unpack_from(">HHhhBBB", chunks[b"BMHD"])
    if compression:
        raise ValueError("compressed ILBM")
    cmap = chunks[b"CMAP"]
    colours = [
        (cmap[i] // OCS_STEP) << 8 | (cmap[i + 1] // OCS_STEP) << 4 | cmap[i + 2] // OCS_STEP
        for i in range(0, len(cmap), 3)
    ]
    row = width // 8
    body = np.frombuffer(chunks[b"BODY"], dtype=np.uint8).reshape(height, depth, row)
    bits = np.unpackbits(body, axis=2)  # height x depth x width
    indices = sum(bits[:, p, :].astype(np.uint8) << p for p in range(depth))
    return np.asarray(indices, dtype=np.uint8), colours


def preview(indices: np.ndarray, colours: Sequence[int], path: Path, scale: int = 3) -> None:
    """A PNG of the picture as the screen shows it, enlarged 3 times (4:3 at 960x720)."""
    lookup = np.array([rgb_of(w) for w in colours], dtype=np.uint8)
    image = Image.fromarray(lookup[indices])
    height, width = indices.shape
    image.resize((width * scale, round(height * scale * 1.2)), Image.NEAREST).save(path)
