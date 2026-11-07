"""How well a performance suits four Paula voices: the numbers for choosing pieces.

For a performance's events (see score.py) this measures, over its length,
how many keys are held down and how many strings ring (keys held plus keys
the sustain pedal keeps sounding), as the share of time at or under each
count: the 95th percentile and the maximum. The player model's cuts come
from clips.report. Everything here is pure except `read_catalogue`, which
reads MAESTRO's catalogue.

Menu text is the composer's surname and the title, in ASCII for the Amiga's
topaz font: accents are dropped (é becomes e), curly quotes become straight
ones, and anything else outside ASCII is removed.
"""

import csv
import math
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from . import clips, player, score
from .score import Event

MENU_WIDTH = 56  # a title's characters: " N  " and the title fit the 60-column boot CLI


@dataclass(frozen=True)
class Entry:
    """One MAESTRO performance."""

    composer: str
    title: str
    year: int
    midi: str  # relative to the dataset folder
    duration_s: float


@dataclass(frozen=True)
class Polyphony:
    held_p95: int
    held_max: int
    ringing_p95: int
    ringing_max: int
    pedal_share: float  # of the performance's length, 0 to 1


def read_catalogue(path: Path) -> list[Entry]:
    """MAESTRO's CSV: composer, title, year, MIDI file and duration of each performance."""
    with path.open(newline="", encoding="utf-8") as f:
        return [
            Entry(
                row["canonical_composer"],
                row["canonical_title"],
                int(row["year"]),
                row["midi_filename"],
                float(row["duration"]),
            )
            for row in csv.DictReader(f)
        ]


def polyphony(events: Sequence[Event]) -> Polyphony:
    """Keys held and strings ringing, weighted by how long each count lasts."""
    held: set[int] = set()
    ringing: set[int] = set()
    pedal = False
    held_time: dict[int, int] = {}
    ringing_time: dict[int, int] = {}
    pedal_ms = 0
    last = events[0].ms if events else 0
    for event in events:
        span = event.ms - last
        if span:
            held_time[len(held)] = held_time.get(len(held), 0) + span
            ringing_time[len(ringing)] = ringing_time.get(len(ringing), 0) + span
            pedal_ms += span * pedal
            last = event.ms
        match event.kind:
            case "on":
                held.add(event.key)
                ringing.add(event.key)
            case "off":
                held.discard(event.key)
                if not pedal:
                    ringing.discard(event.key)
            case "down":
                pedal = True
            case "up":
                pedal = False
                ringing = set(held)
    length = (events[-1].ms - events[0].ms) if events else 0
    return Polyphony(
        held_p95=percentile(held_time, 0.95),
        held_max=max(held_time, default=0),
        ringing_p95=percentile(ringing_time, 0.95),
        ringing_max=max(ringing_time, default=0),
        pedal_share=pedal_ms / length if length else 0.0,
    )


def percentile(weights: dict[int, int], share: float) -> int:
    """The smallest count that the given share of the time is at or under."""
    total = sum(weights.values())
    if not total:
        return 0
    running = 0
    for count in sorted(weights):
        running += weights[count]
        if running >= math.ceil(share * total):
            return count
    return max(weights)


QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def ascii_text(text: str) -> str:
    """Text the Amiga's topaz font shows: accents dropped, the rest of non-ASCII removed."""
    decomposed = unicodedata.normalize("NFKD", text.translate(QUOTES))
    return "".join(c for c in decomposed if c.isascii() and (c.isprintable() or c == " "))


def surnames(composer: str) -> str:
    """The last word of each composer's name: "Bach", "Schubert / Liszt"."""
    return " / ".join(name.split()[-1] for name in composer.split("/") if name.strip())


def menu_title(composer: str, title: str, width: int = MENU_WIDTH) -> str:
    """`Surname: Title` in ASCII, at most `width` characters.

    A longer one loses its last comma-separated clauses (often the movement)
    until it fits; failing that, it is cut after a word and ends with "...".
    """
    text = f"{ascii_text(surnames(composer))}: {ascii_text(title)}"
    while len(text) > width and ", " in text:
        text = text.rsplit(", ", 1)[0]
    if len(text) <= width:
        return text
    head = text[: width - 3]
    if text[width - 3] != " ":
        head = head.rsplit(" ", 1)[0]  # the last word did not fit whole
    return head.rstrip() + "..."


def measure(
    entry: Entry,
    events: Sequence[Event],
    sounds: list[player.KeySound | None],
    table: tuple[int, ...],
) -> dict:
    """One candidate's row: its polyphony and the notes the player model cuts."""
    length_ms = events[-1].ms if events else 0
    cuts = clips.report(events, player.play(events, sounds, table).endings, length_ms)
    per_minute = cuts["endings_per_minute"]
    return {
        "composer": entry.composer,
        "title": entry.title,
        "year": entry.year,
        "midi": entry.midi,
        "length_s": round(length_ms / 1000, 1),
        "notes": sum(e.kind == score.NOTE_ON for e in events),
        **asdict(polyphony(events)),
        "cut_per_minute": cuts["cut_while_held_per_minute"],
        "cut_audible_per_minute": cuts["cut_while_held_at_volume_4_up_per_minute"],
        "melody_steals_per_minute": per_minute.get("steal-key", 0.0),
    }


def measure_catalogue(
    entries: Sequence[Entry],
    read_events: Callable[[str], list[Event]],
    sounds: list[player.KeySound | None],
    table: tuple[int, ...],
) -> list[dict]:
    """A row for each entry, fewest audible cuts a minute first."""
    rows = [measure(e, read_events(e.midi), sounds, table) for e in entries]
    return sorted(rows, key=lambda r: (r["cut_audible_per_minute"], r["ringing_p95"]))
