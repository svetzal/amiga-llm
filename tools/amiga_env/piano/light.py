"""The audio filter's light on the piano's screen, for the A500 and A3500 players.

The recipe's `[filter_light]` table (EXP-004's recipe; the A3500 recipe
takes it through `pieces`) names a label and two colours. The host draws
the light into the screen (screen.py) in the lower left corner, the mirror
of the signature: a small box in colour register 14 and the label beside it
in the attribution's colour. The player changes register 14 as the filter
changes:

- the A3500 player draws no voice trace, so it sets the whole register
  (its picture holds `off` in register 14);
- the A500 player's voice traces are register 14, so its user copper list
  changes the register on the light's rows only (FILTER_LIGHT_TOP up to
  FILTER_LIGHT_END) and puts back FILTER_LIGHT_BACK, the traces' colour,
  after them. Its picture keeps the trace colour in register 14.

Both players include `light.i` (include()).
"""

import string
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np

from . import font as font_mod
from . import picture
from . import screen as screen_mod

REGISTER = screen_mod.VOICE_TRACE_REGISTER  # 14
GAP = 3  # blank columns between the light's box and its label


@dataclass(frozen=True)
class FilterLight:
    """The light: a box in register 14, which the player sets to `on` or `off`
    (OCS hex) as the filter changes, and a label beside it."""

    label: str
    on: str  # register 14 on the light while the filter is on
    off: str  # register 14 on the light while the filter is off


def load(table: dict) -> FilterLight:
    """The recipe's [filter_light] table; SystemExit when a key is missing or a
    colour is not three hex digits."""
    try:
        light = FilterLight(label=table["label"], on=table["on"], off=table["off"])
    except KeyError as missing:
        raise SystemExit(f"[filter_light]: no {missing.args[0]}") from None
    if not isinstance(light.label, str) or not light.label.strip():
        raise SystemExit("[filter_light]: the label is a word of text")
    for name in ("on", "off"):
        colour = getattr(light, name)
        try:
            picture.parse_ocs(colour)
            if not all(c in string.hexdigits for c in colour):
                raise ValueError(colour)
        except (TypeError, ValueError):
            raise SystemExit(
                f"[filter_light]: {name} = {colour!r} is not an OCS colour (three hex digits)"
            ) from None
    return light


def include(light: FilterLight, box: screen_mod.Box, back: int) -> str:
    """`light.i` for either player: the light's register, its two colours, its
    rows (TOP, and END, the first row after it) and `back`, register 14's colour
    in the picture's palette (the voice traces')."""
    return (
        "; light.i: made by `amiga-env piano-disk` or `piano3500-run` (light.py); "
        "do not edit.\n"
        f"FILTER_LIGHT_REGISTER equ {REGISTER}\n"
        f"FILTER_LIGHT_ON equ ${picture.parse_ocs(light.on):03X}\n"
        f"FILTER_LIGHT_OFF equ ${picture.parse_ocs(light.off):03X}\n"
        f"FILTER_LIGHT_TOP equ {box.top}\n"
        f"FILTER_LIGHT_END equ {box.bottom}\n"
        f"FILTER_LIGHT_BACK equ ${back:03X}\n"
    )


class Place(NamedTuple):
    box: screen_mod.Box  # the light itself, filled in register 14
    label: screen_mod.Line


def place(label: str, font: font_mod.Font, top: int) -> Place:
    """The light in the lower left corner, the mirror of the signature: the box's
    left column 1 pixel in from the screen's left edge, the label's line at row
    `top` (the signature's), and the box (font height - 2 square) centred on
    the label's ink rows with GAP blank columns before the label's ink."""
    rows, cols = np.nonzero(font.render(label))
    size = font.height - 2
    ink_top, ink_rows = top + int(rows.min()), int(rows.max() - rows.min()) + 1
    box_top = ink_top + (ink_rows - size) // 2
    box = screen_mod.Box(1, box_top, 1 + size, box_top + size)
    return Place(box, screen_mod.Line(label, box.right + GAP - int(cols.min()), top))


def _meets(a: screen_mod.Box, b: screen_mod.Box) -> bool:
    return a.left < b.right and b.left < a.right and a.top < b.bottom and b.top < a.bottom


def check(
    parts: Mapping[str, screen_mod.Box],
    made: screen_mod.Screen,
    band: screen_mod.Box,
    scopes: Sequence[tuple[int, int]],
    signature: screen_mod.Box | None,
) -> None:
    """SystemExit when a part of the light (`parts`, by name) sits on a bright part
    of the screen, meets a scope's columns (`scopes`: left and right, exclusive)
    on the band's rows, or meets the signature."""
    palette = np.array([picture.rgb_of(w) for w in made.colours], dtype=float)
    spans = [screen_mod.Box(left, band.top, right, band.bottom) for left, right in scopes]
    for name, box in parts.items():
        brightest = screen_mod.brightest_under(made.indices, palette, box)
        if brightest > screen_mod.DARK_LUMINANCE:
            raise SystemExit(
                f"the filter light's {name} would sit on the picture (luminance {brightest:.0f})"
            )
        for span in spans:
            if _meets(box, span):
                raise SystemExit(
                    f"a scope (columns {span.left} to {span.right - 1}) would draw over the "
                    f"filter light's {name} (columns {box.left} to {box.right - 1})"
                )
        if signature and _meets(box, signature):
            raise SystemExit(f"the filter light's {name} would overlap the signature")


def draw(
    made: screen_mod.Screen,
    spec: screen_mod.ScreenSpec,
    scopes: Sequence[tuple[int, int]],
    light: FilterLight,
    font: font_mod.Font,
) -> tuple[screen_mod.Screen, Place]:
    """`made` with the light drawn in, after check(): the box in register 14 and
    the label in the attribution's colour. The colour registers are unchanged."""
    if not spec.attribution_colour:
        raise SystemExit("[screen] names no attribution_colour for the filter light's label")
    signature = made.layout.signature
    top = signature.top if signature else screen_mod.signature_line(light.label, font).top
    where = place(light.label, font, top)
    check(
        {"box": where.box, "label": screen_mod.text_box(where.label, font)},
        made,
        spec.scope_band,
        scopes,
        screen_mod.text_box(signature, font) if signature else None,
    )
    pictures = np.array([picture.rgb_of(w) for w in made.colours[: made.picture_colours]])
    label_register = screen_mod.register_of(pictures, spec.attribution_colour)
    indices = made.indices.copy()
    box = where.box
    indices[box.top : box.bottom, box.left : box.right] = REGISTER
    indices = screen_mod.draw(indices, [where.label], font, label_register)
    return made._replace(indices=indices), where
