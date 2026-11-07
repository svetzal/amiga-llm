"""Amiga file attributes as FS-UAE `.uaem` sidecar lines.

Amiberry keeps the attributes a host file cannot hold in `NAME.uaem` beside
it, one line:

    -s--rw-d 2021-04-13 02:42:22.10 an optional comment

the protection flags in `hsparwed` order (a letter when the flag is set,
`-` when not), the date as the Amiga shows it, with hundredths of a second,
and the comment. Amiberry reads the date as written: an Amiga datestamp is
a wall-clock time with no time zone (days, minutes and 1/50 s ticks since
1 January 1978), so it is converted here with no time zone either.

amitools 0.9.0 converts datestamps through the host's local time, so in
summer its `.uaem` and listings show an hour later than the Amiga does.
This module stands in for its conversions.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

FLAGS = "hsparwed"
# h, s, p and a are set when their bit is 1; r, w, e and d are allowed when
# their bit is 0 (bits 3 to 0).
INVERTED = "rwed"
EPOCH = datetime(1978, 1, 1)
TICKS_PER_SECOND = 50
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_PROTECT = "----rwed"


@dataclass(frozen=True)
class Attributes:
    protect: str = DEFAULT_PROTECT
    days: int = 0
    minutes: int = 0
    ticks: int = 0
    comment: str = ""


def protect_text(mask: int) -> str:
    """`hsparwed` text for an Amiga protection mask."""
    text = []
    for bit, flag in zip(range(7, -1, -1), FLAGS, strict=True):
        is_set = bool(mask & (1 << bit))
        shown = (not is_set) if flag in INVERTED else is_set
        text.append(flag if shown else "-")
    return "".join(text)


def protect_mask(text: str) -> int:
    """The Amiga protection mask for `hsparwed` text."""
    if len(text) != len(FLAGS) or any(c not in (f, "-") for c, f in zip(text, FLAGS, strict=True)):
        raise ValueError(f"not hsparwed protection flags: {text!r}")
    mask = 0
    for bit, (char, flag) in zip(range(7, -1, -1), zip(text, FLAGS, strict=True), strict=True):
        shown = char == flag
        if shown != (flag in INVERTED):
            mask |= 1 << bit
    return mask


def format_line(attrs: Attributes) -> str:
    when = EPOCH + timedelta(
        days=attrs.days, minutes=attrs.minutes, seconds=attrs.ticks // TICKS_PER_SECOND
    )
    hundredths = (attrs.ticks % TICKS_PER_SECOND) * 100 // TICKS_PER_SECOND
    line = f"{attrs.protect} {when.strftime(DATE_FORMAT)}.{hundredths:02d}"
    return f"{line} {attrs.comment}\n" if attrs.comment else f"{line}\n"


def parse_line(text: str) -> Attributes:
    """Attributes from a sidecar's text, as Amiberry or format_line() wrote it."""
    line = text.rstrip("\n")
    protect, date, clock, comment = (line.split(" ", 3) + ["", "", ""])[:4]
    if not date or "." not in clock:
        raise ValueError(f"not a .uaem line: {text!r}")
    seconds, hundredths = clock.split(".", 1)
    when = datetime.strptime(f"{date} {seconds}", DATE_FORMAT)
    since = when - EPOCH
    ticks = since.seconds % 60 * TICKS_PER_SECOND + int(hundredths) * TICKS_PER_SECOND // 100
    protect_mask(protect)
    return Attributes(protect, since.days, since.seconds // 60, ticks, comment)
