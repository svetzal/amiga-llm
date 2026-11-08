"""Which notes the player cuts short, and why.

A note is released when its key is up and the sustain pedal is up: at its
note off if the pedal is up then, else at the next pedal up. A note whose
sound ends before it is released was cut short if the player ended it (a
steal or a restrike); one that faded to silence while held followed its
recording's decay. Notes cut during their release fade are counted apart:
the damper is already stopping them.
"""

from collections import Counter
from collections.abc import Sequence

from .player import Ending
from .score import NOTE_OFF, NOTE_ON, PEDAL_DOWN, PEDAL_UP, Event

AUDIBLE_VOLUME = 4  # Paula volume (of 64) from which a cut is counted as audible
CUTS = ("steal-key", "steal-pedal", "restrike-held")  # ended by the player while held


def release_ms(events: Sequence[Event]) -> list[int]:
    """For each note on, in order, the millisecond its key and the pedal let it go.

    A note still held when the score ends is released at the score's end.
    """
    released: list[int | None] = []
    down: dict[int, list[int]] = {}
    sustained: list[int] = []
    pedal = False
    for event in events:
        if event.kind == NOTE_ON:
            down.setdefault(event.key, []).append(len(released))
            released.append(None)
        elif event.kind == NOTE_OFF:
            for note in down.pop(event.key, []):
                if pedal:
                    sustained.append(note)
                else:
                    released[note] = event.ms
        elif event.kind == PEDAL_DOWN:
            pedal = True
        elif event.kind == PEDAL_UP:
            pedal = False
            for note in sustained:
                released[note] = event.ms
            sustained = []
    end = events[-1].ms if events else 0
    return [end if ms is None else ms for ms in released]


def cause(ending: Ending, released: int) -> str:
    """`steal-key`, `steal-pedal`, `restrike-held`, `faded-held`, or `<cause>-released`."""
    if ending.ms >= released or ending.cause == "end":
        return f"{ending.cause}-released"
    if ending.cause == "steal":
        return "steal-key" if ending.key_down else "steal-pedal"
    return f"{ending.cause}-held"


def report(
    events: Sequence[Event],
    endings: Sequence[Ending],
    length_ms: int,
    audible: int = AUDIBLE_VOLUME,
) -> dict:
    """Counts of note endings by cause, per piece and per minute.

    A cut counts as audible from `audible` up, in the units of Ending.volume
    (Paula volume for the A500 player).
    """
    released = release_ms(events)
    minutes = max(length_ms, 1) / 60000
    counts: Counter[str] = Counter()
    loud = 0
    for ending in endings:
        name = cause(ending, released[ending.note])
        counts[name] += 1
        loud += name in CUTS and ending.volume >= audible
    held = sum(counts[name] for name in CUTS)
    return {
        "endings": dict(sorted(counts.items())),
        "endings_per_minute": {k: round(v / minutes, 1) for k, v in sorted(counts.items())},
        "cut_while_held": held,
        "cut_while_held_per_minute": round(held / minutes, 1),
        "cut_while_held_at_volume_4_up": loud,
        "cut_while_held_at_volume_4_up_per_minute": round(loud / minutes, 1),
    }
