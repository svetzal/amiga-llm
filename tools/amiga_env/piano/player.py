"""The player, as the 68000 will run it: integer arithmetic only.

Four voices. A note on takes the voice already sounding its key (the string
is struck again), else the lowest-numbered free voice, else steals the
quietest voice (the oldest note on a tie). Its volume comes from a velocity
table and the root sample's level.

Volume is kept in 8.8 fixed point (64.0 is 16384); Paula gets the integer
part, 0 to 64. On every frame tick (60 Hz, the NTSC vertical blank) each
voice's volume is multiplied by a 16-bit factor, `(volume * factor) >> 16`,
which is one MULU and a SWAP on the 68000: the key's held factor while its
key or the sustain pedal is down, its release factor otherwise. While the
recorded attack plays (the key's attack_ticks from the note on) a held note
is not decayed, because the recording already fades. A voice whose Paula
volume reaches 0 stops.

Events at the same millisecond as a tick are handled before the tick. Tick k
falls at millisecond k * 1000 // 60.

The output is the list of Paula register writes (what the renderer plays),
a per-tick voice log (what the 68000 player's log is compared with), and
counts of what happened.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from .score import KEYS, Event

VOICES = 4
TICK_HZ = 60
FULL_VOLUME = 64 << 8
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
class LogRow:
    tick: int
    ms: int
    voice: int
    key: int  # -1 when silent
    sample: int
    period: int
    volume: int


@dataclass
class Voice:
    key: int = -1
    sample: int = -1
    period: int = 0
    volume: int = 0  # 8.8
    serial: int = 0
    key_down: bool = False
    ticks: int = 0  # ticks since the note on

    @property
    def active(self) -> bool:
        return self.key >= 0


@dataclass
class Result:
    writes: list[Write] = field(default_factory=list)
    log: list[LogRow] = field(default_factory=list)
    steals: list[Steal] = field(default_factory=list)
    notes: int = 0
    restrikes: int = 0
    dropped: int = 0
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
    """Run the player over a performance."""
    if len(keys) != KEYS:
        raise ValueError(f"need a sound for each of {KEYS} keys")
    state = _State(keys, table)
    for event in events:
        while tick_ms(state.tick) < event.ms:
            state.run_tick()
        state.handle(event)
    for _ in range(LIMIT_TICKS):
        if not any(v.active for v in state.voices):
            break
        state.run_tick()
    state.result.end_ms = tick_ms(state.tick)
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
        self.now = event.ms
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
        sound = self.keys[key]
        if sound is None:
            self.result.dropped += 1
            return
        self.result.notes += 1
        index = self.choose_voice(key)
        voice = self.voices[index]
        volume = max(256, self.table[velocity] * sound.level >> 8)
        self.serial += 1
        voice.key, voice.sample, voice.period = key, sound.sample, sound.period
        voice.volume, voice.serial, voice.key_down = volume, self.serial, True
        voice.ticks = 0
        self.result.writes.append(
            Write(self.now, index, "start", sound.sample, sound.period, volume >> 8)
        )

    def choose_voice(self, key: int) -> int:
        for index, voice in enumerate(self.voices):
            if voice.key == key:
                self.result.restrikes += 1
                return index
        for index, voice in enumerate(self.voices):
            if not voice.active:
                return index
        index = min(range(VOICES), key=lambda i: (self.voices[i].volume, self.voices[i].serial))
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
        return index

    def run_tick(self) -> None:
        now = tick_ms(self.tick)
        for index, voice in enumerate(self.voices):
            if voice.active:
                self.decay(index, voice, now)
            self.result.log.append(
                LogRow(
                    self.tick,
                    now,
                    index,
                    voice.key,
                    voice.sample,
                    voice.period,
                    voice.volume >> 8,
                )
            )
        self.tick += 1

    def decay(self, index: int, voice: Voice, now: int) -> None:
        sound = self.keys[voice.key]
        held = voice.key_down or self.pedal
        voice.ticks += 1
        if held and voice.ticks <= sound.attack_ticks:
            return
        factor = sound.held if held else sound.release
        before = voice.volume >> 8
        voice.volume = voice.volume * factor >> 16
        after = voice.volume >> 8
        if after == 0:
            self.result.writes.append(Write(now, index, "stop"))
            voice.key, voice.sample, voice.period, voice.volume = -1, -1, 0, 0
            voice.key_down = False
        elif after != before:
            self.result.writes.append(Write(now, index, "volume", volume=after))
