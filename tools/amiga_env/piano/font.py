"""A proportional pixel font kept as text, and text set in it.

The font file has a header and then one block a glyph:

    height 9        rows in every glyph
    baseline 6      the row the capitals stand on
    gap 1           blank columns after every glyph

    char A          the glyph's character; `char space` is the space
    .##.            its rows, top first: '#' ink, '.' paper; all one width
    #..#

A line starting with '# ', or a lone '#' outside a glyph, is a comment; a
blank line ends a glyph. A glyph with fewer rows than `height` is blank below them.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import numpy as np


class Font(NamedTuple):
    height: int
    baseline: int
    gap: int
    glyphs: dict[str, np.ndarray]  # each `height` x width, bool

    def advance(self, char: str) -> int:
        return self.glyph(char).shape[1] + self.gap

    def width(self, text: str) -> int:
        """Pixels from the first column of `text` to its last ink, without the last gap."""
        return sum(self.advance(c) for c in text) - self.gap if text else 0

    def glyph(self, char: str) -> np.ndarray:
        try:
            return self.glyphs[char]
        except KeyError:
            raise ValueError(f"the font has no glyph for {char!r}") from None

    def render(self, text: str) -> np.ndarray:
        """`text` as a `height` x width bool array."""
        out = np.zeros((self.height, max(self.width(text), 0)), dtype=bool)
        x = 0
        for char in text:
            glyph = self.glyph(char)
            out[:, x : x + glyph.shape[1]] = glyph
            x += glyph.shape[1] + self.gap
        return out


def parse(lines: Iterable[str]) -> Font:
    header: dict[str, int] = {}
    glyphs: dict[str, list[str]] = {}
    current: list[str] | None = None
    for number, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if not line.strip():
            current = None  # a blank line ends a glyph
            continue
        if line.startswith("# ") or (line == "#" and current is None):
            continue
        words = line.split()
        if words[0] == "char" and len(words) == 2:
            char = " " if words[1] == "space" else words[1]
            if len(char) != 1 or char in glyphs:
                raise ValueError(f"line {number}: a glyph is one new character, not {words[1]!r}")
            current = glyphs.setdefault(char, [])
        elif current is None and len(words) == 2 and words[0] in ("height", "baseline", "gap"):
            header[words[0]] = int(words[1])
        elif current is not None and set(line) <= {"#", "."}:
            current.append(line)
        else:
            raise ValueError(f"line {number}: cannot read {line!r}")
    missing = {"height", "baseline", "gap"} - header.keys()
    if missing:
        raise ValueError(f"the font has no {', '.join(sorted(missing))}")
    height = header["height"]
    return Font(
        height,
        header["baseline"],
        header["gap"],
        {char: _glyph(char, rows, height) for char, rows in glyphs.items()},
    )


def _glyph(char: str, rows: list[str], height: int) -> np.ndarray:
    if not rows or len(rows) > height or len({len(r) for r in rows}) != 1:
        raise ValueError(f"glyph {char!r}: 1 to {height} rows, all one width")
    out = np.zeros((height, len(rows[0])), dtype=bool)
    out[: len(rows)] = [[c == "#" for c in row] for row in rows]
    return out


def load(path: Path) -> Font:
    return parse(path.read_text(encoding="ascii").splitlines())
