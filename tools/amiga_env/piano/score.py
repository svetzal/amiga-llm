"""A piano performance as a compact event stream for a 68000 player.

Time is in milliseconds. A 1 ms grid keeps the timing of a recorded
performance (chord spreads, rubato, pedal changes) to well under what a
listener can hear, where the 60 Hz frame (16.7 ms) would not. The player can
keep that time with a CIA timer (715909 Hz on NTSC, 716 ticks a millisecond),
either as a 1 kHz interrupt or as a one-shot set to each wait.

Keys are numbered 0 to 87 from A0 (MIDI note 21). The stream is bytes, read
one at a time:

    0x00-0x57  note on, key 0-87; the next byte is the velocity, 1-127
    0x58-0x7F  wait 1-40 ms (the byte minus 0x57)
    0x80-0xD7  note off, key 0-87 (the byte minus 0x80)
    0xE0 n     wait n ms, 1-255
    0xE1 h l   wait h*256+l ms, 1-65535 (big-endian, as the 68000 reads it)
    0xF0       sustain pedal down
    0xF1       sustain pedal up
    0xFF       end

Events that share a millisecond follow each other with no wait between them.
"""

import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

LOWEST_NOTE = 21  # MIDI note of A0, key 0
KEYS = 88
PEDAL_THRESHOLD = 64  # MIDI CC64 at or above this is "down", the usual reading
SUSTAIN, SOSTENUTO, SOFT = 64, 66, 67

NOTE_ON, NOTE_OFF, PEDAL_DOWN, PEDAL_UP = "on", "off", "down", "up"
SHORT_WAIT_BASE = 0x57
SHORT_WAIT_MAX = 0x7F - SHORT_WAIT_BASE  # 40 ms
OFF_BASE = 0x80
WAIT_BYTE, WAIT_WORD = 0xE0, 0xE1
DOWN_BYTE, UP_BYTE, END_BYTE = 0xF0, 0xF1, 0xFF


class MidiMessage(NamedTuple):
    """One channel message of a MIDI file, at its time in seconds from the start."""

    seconds: float
    kind: str  # "note_on", "note_off" or "control_change"
    number: int  # note or controller number
    value: int  # velocity or controller value


@dataclass(frozen=True)
class Event:
    ms: int
    kind: str
    key: int = 0
    velocity: int = 0


@dataclass(frozen=True)
class Performance:
    events: list[Event]
    notes: int
    dropped_notes: int  # outside the 88 keys
    sostenuto_messages: int
    soft_messages: int
    sustain_messages: int

    @property
    def velocities(self) -> list[int]:
        return [e.velocity for e in self.events if e.kind == NOTE_ON]

    @property
    def length_ms(self) -> int:
        return self.events[-1].ms if self.events else 0


def performance(messages: Iterable[MidiMessage]) -> Performance:
    """The player's events for a performance, in time order, with what was left out."""
    timed: list[Event] = []
    counts = {SUSTAIN: 0, SOSTENUTO: 0, SOFT: 0}
    dropped = notes = 0
    pedal_down = False
    for message in messages:
        ms = round(message.seconds * 1000)
        if message.kind == "control_change":
            if message.number in counts:
                counts[message.number] += 1
            if message.number == SUSTAIN:
                down = message.value >= PEDAL_THRESHOLD
                if down != pedal_down:
                    pedal_down = down
                    timed.append(Event(ms, PEDAL_DOWN if down else PEDAL_UP))
            continue
        key = message.number - LOWEST_NOTE
        is_on = message.kind == "note_on" and message.value > 0
        if not 0 <= key < KEYS:
            dropped += is_on
            continue
        if is_on:
            notes += 1
            timed.append(Event(ms, NOTE_ON, key, min(message.value, 127)))
        elif message.kind in ("note_on", "note_off"):
            timed.append(Event(ms, NOTE_OFF, key))
    timed.sort(key=lambda e: e.ms)  # stable: events in one millisecond keep their order
    return Performance(timed, notes, dropped, counts[SOSTENUTO], counts[SOFT], counts[SUSTAIN])


def encode(events: Iterable[Event]) -> bytes:
    out = bytearray()
    now = 0
    for event in events:
        if event.ms < now:
            raise ValueError(f"events go back in time at {event.ms} ms")
        out += wait_bytes(event.ms - now)
        now = event.ms
        out += event_bytes(event)
    out.append(END_BYTE)
    return bytes(out)


def wait_bytes(ms: int) -> bytes:
    out = bytearray()
    while ms > 0xFFFF:
        out += bytes((WAIT_WORD, 0xFF, 0xFF))
        ms -= 0xFFFF
    if ms == 0:
        pass
    elif ms <= SHORT_WAIT_MAX:
        out.append(SHORT_WAIT_BASE + ms)
    elif ms <= 0xFF:
        out += bytes((WAIT_BYTE, ms))
    else:
        out += bytes((WAIT_WORD, ms >> 8, ms & 0xFF))
    return bytes(out)


def event_bytes(event: Event) -> bytes:
    match event.kind:
        case "on":
            if not 0 <= event.key < KEYS or not 1 <= event.velocity <= 127:
                raise ValueError(f"note on out of range: {event}")
            return bytes((event.key, event.velocity))
        case "off":
            return bytes((OFF_BASE + event.key,))
        case "down":
            return bytes((DOWN_BYTE,))
        case "up":
            return bytes((UP_BYTE,))
    raise ValueError(f"unknown event {event.kind}")


def decode(stream: bytes) -> list[Event]:
    """The events in a stream: the reference for the 68000 player's reader."""
    events, now, i = [], 0, 0
    while True:
        byte = stream[i]
        i += 1
        if byte < 0x58:
            events.append(Event(now, NOTE_ON, byte, stream[i]))
            i += 1
        elif byte < 0x80:
            now += byte - SHORT_WAIT_BASE
        elif byte < 0xD8:
            events.append(Event(now, NOTE_OFF, byte - OFF_BASE))
        elif byte == WAIT_BYTE:
            now += stream[i]
            i += 1
        elif byte == WAIT_WORD:
            now += stream[i] << 8 | stream[i + 1]
            i += 2
        elif byte in (DOWN_BYTE, UP_BYTE):
            events.append(Event(now, PEDAL_DOWN if byte == DOWN_BYTE else PEDAL_UP))
        elif byte == END_BYTE:
            return events
        else:
            raise ValueError(f"byte {byte:#04x} at offset {i - 1} is not an event")


def report(perf: Performance, stream: bytes) -> dict:
    """What the conversion kept and left out, and how big the stream is."""
    velocities = perf.velocities
    return {
        "bytes": len(stream),
        "length_s": round(perf.length_ms / 1000, 1),
        "notes": perf.notes,
        "dropped_notes": perf.dropped_notes,
        "pedal_changes": sum(e.kind in (PEDAL_DOWN, PEDAL_UP) for e in perf.events),
        "sustain_messages": perf.sustain_messages,
        "sostenuto_messages_ignored": perf.sostenuto_messages,
        "soft_messages_ignored": perf.soft_messages,
        "velocity_min": min(velocities, default=0),
        "velocity_median": statistics.median(velocities) if velocities else 0,
        "velocity_max": max(velocities, default=0),
    }


def read_midi(path: Path) -> list[MidiMessage]:
    """The channel messages of a MIDI file, with times from its tempo map (mido)."""
    import mido

    messages, seconds = [], 0.0
    for message in mido.MidiFile(path):
        seconds += message.time
        if message.type in ("note_on", "note_off"):
            messages.append(MidiMessage(seconds, message.type, message.note, message.velocity))
        elif message.type == "control_change":
            messages.append(MidiMessage(seconds, message.type, message.control, message.value))
    return messages
