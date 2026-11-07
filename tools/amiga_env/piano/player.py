"""The player, as the 68000 runs it: integer arithmetic only.

Time runs in milliseconds, as the 68000 player's 1 kHz CIA interrupt does.
Each millisecond, in this order:

1. every voice that is fading out steps its fade (see "Cutting a note");
2. the score's events for that millisecond are handled;
3. if a frame tick falls on that millisecond (tick k falls at
   k * 1000 // 60), every voice decays and the log gets one row per voice.

Four voices. A note on takes the voice already sounding its key (the string
is struck again), else the lowest-numbered free voice, else steals a voice:
the quietest one whose key is up (held only by the pedal, or released), and
only when every key is down the quietest of all; the oldest note on a tie.
Its volume comes from a velocity table and the root sample's level.

Cutting a note. A note that takes a voice which is still sounding does not
start at once: the old note fades out over FADE_MS milliseconds and the new
one starts after it. The voice's Paula volume goes to 3/4, 2/4 and 1/4 of
what it was, then 0, when the voice's DMA stops; the new note starts one
millisecond later, so Paula has a millisecond with the channel stopped
before it restarts. A note on for a voice already waiting replaces the
waiting note and the fade carries on. A waiting voice belongs to its new
note for every other purpose (its key, its volume for stealing), but it is
not decayed until it starts.

Volume is kept in 8.8 fixed point (64.0 is 16384); Paula gets the integer
part, 0 to 64. On every frame tick each sounding voice's volume is
multiplied by a 16-bit factor, `(volume * factor) >> 16`, one MULU and a
SWAP on the 68000: the key's held factor while its key or the sustain pedal
is down, its release factor otherwise. While the recorded attack plays (the
key's attack_ticks from the start) a held note is not decayed, because the
recording already fades. A voice whose Paula volume reaches 0 stops.

The output is the list of Paula register writes (what the renderer plays),
a per-tick voice log (what the 68000 player's log is compared with), and
what happened to every note.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from .score import KEYS, Event

VOICES = 4
TICK_HZ = 60
FULL_VOLUME = 64 << 8
FADE_MS = 5  # from the cut to the new note's start
LIMIT_TICKS = 60 * TICK_HZ  # after the last event, ticks until every voice is silent


@dataclass(frozen=True)
class KeySound:
    """What one key plays."""

    sample: int  # index of its root's sample
    period: int
    level: int  # 0-256: the root sample's level, 256 is 1.0
    held: int  # 16-bit decay factor per tick while the key or pedal holds it
    release: int  # 16-bit decay factor per tick otherwise
    attack_ticks: int = 0  # ticks the recorded attack lasts at this key's period


@dataclass(frozen=True)
class Write:
    """A change to one Paula voice: start a sample, set its volume, or stop it."""

    ms: int
    voice: int
    kind: str  # "start", "volume" or "stop"
    sample: int = -1
    period: int = 0
    volume: int = 0


@dataclass(frozen=True)
class Steal:
    ms: int
    voice: int
    volume: int  # Paula volume of the stolen note when it was stolen
    held: bool  # whether its key or the pedal still held it
    old_key: int
    new_key: int


@dataclass(frozen=True)
class Ending:
    """How one note's sound ended."""

    note: int  # the note's index among the score's note ons, from 0
    ms: int
    cause: str  # "steal", "restrike", "faded" or "end" (still sounding when play stopped)
    volume: int  # Paula volume when it ended
    key_down: bool


@dataclass(frozen=True)
class LogRow:
    tick: int
    ms: int
    voice: int
    key: int  # -1 when silent
    sample: int
    period: int
    volume: int  # the note's volume, 0-64
    out: int  # Paula's volume register: differs from volume while a cut fades


@dataclass
class Voice:
    key: int = -1
    sample: int = -1
    period: int = 0
    volume: int = 0  # 8.8
    serial: int = 0  # the note's index among the note ons, from 1
    key_down: bool = False
    ticks: int = 0  # ticks since the note started
    out: int = 0  # Paula volume register
    fade: int = 0  # milliseconds until the waiting note starts; 0 when none waits
    fade_from: int = 0  # Paula volume when the fade began
    cut: int = 0  # serial of the note being faded out

    @property
    def active(self) -> bool:
        return self.key >= 0


@dataclass
class Result:
    writes: list[Write] = field(default_factory=list)
    log: list[LogRow] = field(default_factory=list)
    steals: list[Steal] = field(default_factory=list)
    endings: list[Ending] = field(default_factory=list)
    notes: int = 0
    restrikes: int = 0
    dropped: int = 0  # no sound for the key
    superseded: int = 0  # replaced while waiting for a fade, so never sounded
    end_ms: int = 0


def velocity_table(exponent: float = 1.5) -> tuple[int, ...]:
    """8.8 volume for each MIDI velocity: 64 * (v / 127) ** exponent, at least 1.0."""
    return (0,) + tuple(max(256, round(FULL_VOLUME * (v / 127) ** exponent)) for v in range(1, 128))


def decay_factor(db_per_s: float, tick_hz: int = TICK_HZ) -> int:
    """The 16-bit per-tick factor that fades db_per_s decibels a second."""
    return max(0, min(0xFFFF, round(65536 * 10 ** (-db_per_s / (20 * tick_hz)))))


def tick_ms(tick: int) -> int:
    return tick * 1000 // TICK_HZ


def play(events: Iterable[Event], keys: list[KeySound | None], table: tuple[int, ...]) -> Result:
    """Run the player over a performance, one millisecond at a time."""
    if len(keys) != KEYS:
        raise ValueError(f"need a sound for each of {KEYS} keys")
    state = _State(keys, table)
    pending = list(events)
    index = 0
    while index < len(pending):
        state.step_fades()
        while index < len(pending) and pending[index].ms <= state.now:
            state.handle(pending[index])
            index += 1
        state.maybe_tick()
        state.now += 1
    for _ in range(LIMIT_TICKS * 17):
        if not any(v.active for v in state.voices):
            break
        state.step_fades()
        state.maybe_tick()
        state.now += 1
    for voice in state.voices:
        if voice.active:
            state.ended(voice, "end")
    state.result.end_ms = state.now
    return state.result


class _State:
    def __init__(self, keys: list[KeySound | None], table: tuple[int, ...]):
        self.keys = keys
        self.table = table
        self.voices = [Voice() for _ in range(VOICES)]
        self.pedal = False
        self.tick = 0
        self.serial = 0
        self.now = 0
        self.result = Result()

    def handle(self, event: Event) -> None:
        match event.kind:
            case "on":
                self.note_on(event.key, event.velocity)
            case "off":
                for voice in self.voices:
                    if voice.key == event.key:
                        voice.key_down = False
            case "down":
                self.pedal = True
            case "up":
                self.pedal = False

    def note_on(self, key: int, velocity: int) -> None:
        self.serial += 1
        sound = self.keys[key]
        if sound is None:
            self.result.dropped += 1
            return
        self.result.notes += 1
        index = self.choose_voice(key)
        voice = self.voices[index]
        volume = max(256, self.table[velocity] * sound.level >> 8)
        if voice.fade:
            pass  # the waiting note is replaced; the fade carries on
        elif voice.active:
            voice.fade, voice.fade_from, voice.cut = FADE_MS, voice.out, voice.serial
        voice.key, voice.sample, voice.period = key, sound.sample, sound.period
        voice.volume, voice.serial, voice.key_down = volume, self.serial, True
        voice.ticks = 0
        if not voice.fade:
            self.start(index, voice)

    def start(self, index: int, voice: Voice) -> None:
        voice.out = voice.volume >> 8
        self.result.writes.append(
            Write(self.now, index, "start", voice.sample, voice.period, voice.out)
        )

    def choose_voice(self, key: int) -> int:
        for index, voice in enumerate(self.voices):
            if voice.key == key:
                self.result.restrikes += 1
                self.ended(voice, "restrike")
                return index
        for index, voice in enumerate(self.voices):
            if not voice.active:
                return index
        index = min(range(VOICES), key=lambda i: self.steal_order(self.voices[i]))
        stolen = self.voices[index]
        self.result.steals.append(
            Steal(
                self.now,
                index,
                stolen.volume >> 8,
                stolen.key_down or self.pedal,
                stolen.key,
                key,
            )
        )
        self.ended(stolen, "steal")
        return index

    @staticmethod
    def steal_order(voice: Voice) -> tuple[bool, int, int]:
        """Lowest is stolen first: key up before key down, then quietest, then oldest."""
        return voice.key_down, voice.volume, voice.serial

    def ended(self, voice: Voice, cause: str) -> None:
        """Record the end of the note a voice sounds; a waiting note never sounded."""
        if voice.fade:
            self.result.superseded += 1
            return
        self.result.endings.append(
            Ending(voice.serial - 1, self.now, cause, voice.out, voice.key_down)
        )

    def step_fades(self) -> None:
        for index, voice in enumerate(self.voices):
            if not voice.fade:
                continue
            voice.fade -= 1
            if voice.fade >= 2:
                voice.out = voice.fade_from * (voice.fade - 1) >> 2
                self.result.writes.append(Write(self.now, index, "volume", volume=voice.out))
            elif voice.fade == 1:
                voice.out = 0
                self.result.writes.append(Write(self.now, index, "stop"))
            else:
                self.start(index, voice)

    def maybe_tick(self) -> None:
        if tick_ms(self.tick) != self.now:
            return
        for index, voice in enumerate(self.voices):
            if voice.active and not voice.fade:
                self.decay(index, voice)
            self.result.log.append(
                LogRow(
                    self.tick,
                    self.now,
                    index,
                    voice.key,
                    voice.sample,
                    voice.period,
                    voice.volume >> 8,
                    voice.out,
                )
            )
        self.tick += 1

    def decay(self, index: int, voice: Voice) -> None:
        sound = self.keys[voice.key]
        held = voice.key_down or self.pedal
        voice.ticks += 1
        if held and voice.ticks <= sound.attack_ticks:
            return
        factor = sound.held if held else sound.release
        voice.volume = voice.volume * factor >> 16
        after = voice.volume >> 8
        if after == 0:
            self.ended(voice, "faded")
            self.result.writes.append(Write(self.now, index, "stop"))
            voice.key, voice.sample, voice.period, voice.volume = -1, -1, 0, 0
            voice.key_down, voice.out = False, 0
        elif after != voice.out:
            voice.out = after
            self.result.writes.append(Write(self.now, index, "volume", volume=after))
