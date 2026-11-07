"""The player's screen, made on the host: the title picture with the list drawn in.

`amiga-env piano-disk` makes it from the recipe's `[screen]` table:

- the picture (picture.py) takes colour registers 0 to 12;
- the song list, one line a piece, is drawn into it in the project font
  (font.py) in register 13; the attribution lines and a signature in the
  lower right corner are drawn in colours of the picture itself, so the
  copper list that turns register 13 gold never touches them;
- registers 14 and 15 are the scopes' traces (the player draws them);
- the result is an uncompressed IFF ILBM for the disk, a preview PNG, and
  an include file (`screen.i`) that tells the player where each line is,
  which colours to use and where the scopes go.

Each piece's line has a fixed top row; the player highlights the line of
the piece playing (register 13 turns gold on its rows, by a user copper
list) and takes a click on those rows as a choice of that piece.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import numpy as np
from PIL import Image

from . import font as font_mod
from . import picture

TEXT_REGISTER = 13
VOICE_TRACE_REGISTER = 14
MIX_TRACE_REGISTER = 15
DEPTH = 4
# The brightest picture colour text may sit on: the wall and floor are dark,
# with faint blue speckles ($136 is about 46); the piano's highlights are not.
DARK_LUMINANCE = 50.0


class Box(NamedTuple):
    left: int
    top: int
    right: int  # exclusive
    bottom: int  # exclusive


class ScreenSpec(NamedTuple):
    master: str  # the master image, under the project
    font: str  # the font file, under the project
    picture: picture.PictureSpec
    list_box: Box  # where the song list and the attribution may go
    line_pitch: int
    attribution: tuple[str, ...]
    attribution_gap: int  # blank rows between the list and the attribution
    text: str  # register 13, OCS hex: ivory
    highlight: str  # register 13 on the playing piece's line: gold
    voice_trace: str  # register 14
    mix_trace: str  # register 15
    scope_band: Box  # rows the scopes may draw in; restored from a copy each frame
    voice_scopes: tuple[int, ...]  # the left column of each voice's scope
    voice_scope_width: int
    mix_scope: tuple[int, int]  # the mixed scope's left column and width
    scope_centre: int  # the row of the traces' zero
    attribution_colour: str = ""  # one of the picture's colours, OCS hex; "" for register 13
    signature: str = ""  # drawn in the lower right corner; "" for none
    signature_colour: str = ""  # one of the picture's colours, OCS hex


def load_spec(table: dict) -> ScreenSpec:
    return ScreenSpec(
        master=table["master"],
        font=table["font"],
        picture=picture.PictureSpec(**table.get("picture", {})),
        list_box=Box(*table["list_box"]),
        line_pitch=table["line_pitch"],
        attribution=tuple(table["attribution"]),
        attribution_gap=table["attribution_gap"],
        text=table["text"],
        highlight=table["highlight"],
        voice_trace=table["voice_trace"],
        mix_trace=table["mix_trace"],
        scope_band=Box(*table["scope_band"]),
        voice_scopes=tuple(table["voice_scopes"]),
        voice_scope_width=table["voice_scope_width"],
        mix_scope=tuple(table["mix_scope"]),
        scope_centre=table["scope_centre"],
        attribution_colour=table.get("attribution_colour", ""),
        signature=table.get("signature", ""),
        signature_colour=table.get("signature_colour", ""),
    )


class Line(NamedTuple):
    text: str
    left: int
    top: int


class Layout(NamedTuple):
    pieces: list[Line]  # one a piece, in menu order
    attribution: list[Line]
    signature: Line | None = None


def layout(titles: Sequence[str], spec: ScreenSpec, font: font_mod.Font) -> Layout:
    """Where each line goes; SystemExit when a line does not fit the list's box."""
    box = spec.list_box
    pieces = [Line(t, box.left, box.top + i * spec.line_pitch) for i, t in enumerate(titles)]
    first = box.top + len(titles) * spec.line_pitch + spec.attribution_gap
    attribution = [
        Line(t, box.left, first + i * spec.line_pitch) for i, t in enumerate(spec.attribution)
    ]
    for line in pieces + attribution:
        right = line.left + font.width(line.text)
        if right > box.right:
            raise SystemExit(
                f"{line.text!r} is {font.width(line.text)} pixels wide; "
                f"the list has {box.right - box.left}"
            )
        if line.top + font.height > box.bottom:
            raise SystemExit(f"{line.text!r} at row {line.top} runs below row {box.bottom}")
    return Layout(pieces, attribution)


def text_box(line: Line, font: font_mod.Font) -> Box:
    return Box(line.left, line.top, line.left + font.width(line.text), line.top + font.height)


def brightest_under(indices: np.ndarray, palette: np.ndarray, box: Box) -> float:
    """The luminance of the brightest picture pixel in `box`."""
    area = indices[box.top : box.bottom, box.left : box.right]
    return float(picture.luminance(palette[np.unique(area)]).max())


def draw(
    indices: np.ndarray,
    lines: Sequence[Line],
    font: font_mod.Font,
    register: int = TEXT_REGISTER,
) -> np.ndarray:
    """`indices` with every line's ink set to `register`."""
    out = indices.copy()
    for line in lines:
        ink = font.render(line.text)
        rows, cols = ink.shape
        area = out[line.top : line.top + rows, line.left : line.left + cols]
        if ink[area.shape[0] :].any() or ink[:, area.shape[1] :].any():
            raise SystemExit(f"{line.text!r} runs off the screen")
        area[ink[: area.shape[0], : area.shape[1]]] = register
    return out


def register_of(palette: np.ndarray, colour: str) -> int:
    """The picture's register that holds `colour` (OCS hex); SystemExit when none does."""
    words = [picture.ocs_word(c) for c in palette]
    try:
        return words.index(picture.parse_ocs(colour))
    except ValueError:
        raise SystemExit(f"${colour} is not one of the picture's colours") from None


def signature_line(text: str, font: font_mod.Font) -> Line:
    """`text` placed with its ink one pixel from the screen's right and bottom edges."""
    rows, cols = np.nonzero(font.render(text))
    return Line(text, picture.WIDTH - 2 - int(cols.max()), picture.HEIGHT - 2 - int(rows.max()))


def check_signature(box: Box, spec: ScreenSpec) -> None:
    """No scope may draw where the signature is: SystemExit when a scope's columns
    meet the signature's on rows of the scope band."""
    band = spec.scope_band
    if box.bottom <= band.top or box.top >= band.bottom:
        return
    spans = [(x, x + spec.voice_scope_width) for x in spec.voice_scopes]
    spans.append((spec.mix_scope[0], spec.mix_scope[0] + spec.mix_scope[1]))
    for left, right in spans:
        if left < box.right and box.left < right:
            raise SystemExit(
                f"a scope (columns {left} to {right - 1}) would draw over the signature "
                f"(columns {box.left} to {box.right - 1})"
            )


def colours(palette: np.ndarray, spec: ScreenSpec) -> list[int]:
    """The 16 colour registers: the picture's, black up to 12, then text and traces."""
    words = [picture.ocs_word(c) for c in palette]
    if len(words) > TEXT_REGISTER:
        raise SystemExit(f"the picture has {len(words)} colours; registers 0 to 12 hold 13")
    words += [0] * (TEXT_REGISTER - len(words))
    return words + [picture.parse_ocs(c) for c in (spec.text, spec.voice_trace, spec.mix_trace)]


class Screen(NamedTuple):
    indices: np.ndarray
    colours: list[int]
    layout: Layout
    picture_colours: int


def make(titles: Sequence[str], spec: ScreenSpec, root: Path) -> Screen:
    font = font_mod.load(root / spec.font)
    lines = layout(titles, spec, font)
    made = picture.convert(Image.open(root / spec.master), spec.picture)
    signature = signature_line(spec.signature, font) if spec.signature else None
    if signature:
        check_signature(text_box(signature, font), spec)
    for line in [*lines.pieces, *lines.attribution, *([signature] if signature else [])]:
        brightest = brightest_under(made.indices, made.palette, text_box(line, font))
        if brightest > DARK_LUMINANCE:
            raise SystemExit(f"{line.text!r} would sit on the picture (luminance {brightest:.0f})")
    credits = TEXT_REGISTER
    if spec.attribution_colour:
        credits = register_of(made.palette, spec.attribution_colour)
    indices = draw(made.indices, lines.pieces, font)
    indices = draw(indices, lines.attribution, font, credits)
    if signature:
        indices = draw(indices, [signature], font, register_of(made.palette, spec.signature_colour))
    return Screen(
        indices, colours(made.palette, spec), lines._replace(signature=signature), len(made.palette)
    )


def include(screen: Screen, spec: ScreenSpec, font: font_mod.Font) -> str:
    """`screen.i` for the player: the list's rows, the colours and the scopes."""
    band, (mix_left, mix_width) = spec.scope_band, spec.mix_scope
    lines = [
        "; screen.i: made by `amiga-env piano-disk` (screen.py); do not edit.",
        f"LIST_LEFT       equ {spec.list_box.left}",
        f"LIST_LINES      equ {len(screen.layout.pieces)}",
        f"LINE_PITCH      equ {spec.line_pitch}",
        f"LINE_ROWS       equ {font.height}",
        f"TEXT_COLOUR     equ ${picture.parse_ocs(spec.text):03X}",
        f"HIGHLIGHT_COLOUR equ ${picture.parse_ocs(spec.highlight):03X}",
        f"SCOPE_TOP       equ {band.top}",
        f"SCOPE_ROWS      equ {band.bottom - band.top}",
        f"SCOPE_CENTRE    equ {spec.scope_centre}",
        f"VOICE_SCOPE_WIDTH equ {spec.voice_scope_width}",
        f"MIX_SCOPE_LEFT  equ {mix_left}",
        f"MIX_SCOPE_WIDTH equ {mix_width}",
        "; The tables, placed where the player invokes the macro.",
        "SCREEN_TABLES   macro",
        "line_tops:      dc.w " + ",".join(str(line.top) for line in screen.layout.pieces),
        "voice_scope_left: dc.w " + ",".join(str(x) for x in spec.voice_scopes),
        "                endm",
        "",
    ]
    return "\n".join(lines)


def check_scopes(spec: ScreenSpec) -> None:
    """The scopes fit the band and the screen, and no two share a byte of a row
    (the player takes back and redraws each on its own); SystemExit otherwise."""
    band = spec.scope_band
    spans = [(x, x + spec.voice_scope_width) for x in spec.voice_scopes]
    spans.append((spec.mix_scope[0], spec.mix_scope[0] + spec.mix_scope[1]))
    for left, right in spans:
        if left < 0 or right > picture.WIDTH:
            raise SystemExit(f"a scope from column {left} to {right} leaves the screen")
    for (_, right), (left, _) in zip(sorted(spans), sorted(spans)[1:], strict=False):
        if left < right:
            raise SystemExit("two scopes overlap")
        if left // 8 <= (right - 1) // 8:
            raise SystemExit("two scopes share a byte of the screen; the player draws each alone")
    if not band.top < spec.scope_centre < band.bottom or band.bottom > picture.HEIGHT:
        raise SystemExit("the scopes' centre row must be inside their band, on the screen")
    if (band.right - band.left) != picture.WIDTH:
        raise SystemExit("the scope band is whole rows, so it is restored as one block")


def write(screen: Screen, spec: ScreenSpec, root: Path, data: Path, out: Path) -> Path:
    """The ILBM and screen.i into `data` (the player's folder), a preview into `out`."""
    check_scopes(spec)
    font = font_mod.load(root / spec.font)
    ilbm = data / "title.ilbm"
    ilbm.write_bytes(picture.ilbm(screen.indices, screen.colours, DEPTH))
    (data / "screen.i").write_text(include(screen, spec, font), encoding="ascii")
    picture.preview(screen.indices, screen.colours, out / "title-preview.png")
    return ilbm
