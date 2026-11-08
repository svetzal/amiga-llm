"""The A3500 piano's player, as the 68030 runs it: integer arithmetic only.

Time runs in output samples at 27,965.2 Hz (see mixer.py), in blocks of
512. A score millisecond falls on output sample `ms * 3,579,545 //
128,000` (mixer.sample_of_ms). For each block, in this order, the player:

1. decays every voice whose note started before the block (see "Volume");
2. handles the score's events that fall in the block, in score order, each
   at its own sample;
3. mixes the block, voice by voice (mixer.py), splitting a voice's block
   where a note starts or a cut's fade steps, into a 32-bit sum per side
   and output sample; then shifts and clamps the sums to 16-bit output
   values (mixer.output16);
4. writes the block's record to the voice log (see "The voice log").

So nothing is quantised to blocks except volume changes: a note starts at
its exact sample.

Sixteen voices. A note on takes the voice already sounding its key (the
string is struck again), else the lowest-numbered free voice, else steals a
voice: the quietest one whose key is up (held only by the pedal, or
released), and only when every key is down the quietest of all; the oldest
note on a tie. These are player.py's rules.

What a note plays. Its velocity picks a layer (the instrument's 128-byte
layer table); its key and layer pick a sound: a sample, a 16.16 step, a
held and a release decay factor, and the blocks its recorded attack lasts.
Its volume comes from its root's 128-word volume table (layers.py gives
the rule), and its pan from its key's two 16-bit gains.

Cutting a note. A note that takes a voice which is still sounding does not
start at once: the old note fades out. Its multipliers go to 3/4, 2/4 and
1/4 of what they were, for FADE_STEP samples each, then it stops and the
new note starts, 3 * FADE_STEP samples (3.4 ms) after its time in the
score. A note on for a voice already waiting replaces the waiting note and
the fade carries on. A waiting voice belongs to its new note for every
other purpose (its key, its volume for stealing), but it is not decayed
until it starts.

Volume. A voice's volume is 16 bits, at most 32,767. Once a block, each
voice whose note started before the block is multiplied by a 16-bit factor,
`(volume * factor) >> 16` (MULU.W and SWAP): the sound's held factor while
its key or the sustain pedal is down, its release factor otherwise. While
the recorded attack plays (the sound's attack blocks from the start) a held
note is not decayed, because the recording already fades. A voice whose
volume falls below STOP_VOLUME stops. After the decay, its multipliers are
set again from its volume and pan gains.

The voice log (`log_bytes`), big-endian as the 68030 writes it. A header of
LOG_HEADER_BYTES: the four bytes "P35L", version (word, 1), voices (word,
16), samples a block (word, 512), a zero word, and the number of blocks
(long). Then one record a block, of LOG_BLOCK_BYTES: the checksum of the
block's 16-bit output values (two longs, mixer.checksum) and one record of LOG_VOICE_BYTES for each
voice in order, as the voice is at the end of the block:

    key (byte, 0-87, 0xFF when free), sample (byte, 0xFF when silent),
    volume (word), left and right multipliers (words, as the last run of
    the block used them), phase integer part (long), phase fraction (word).
"""

import struct
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from . import mixer
from .player import Ending, Steal
from .score import KEYS, Event

VOICES = 16
FADE_STEP = 32  # samples at each of a cut's three fade levels
FADE_QUARTERS = (3, 2, 1)
STOP_VOLUME = 8  # a voice stops below this volume
# After the last event, blocks until every voice is silent.
LIMIT_BLOCKS = round(60 * mixer.BLOCK_HZ)
SILENT = 0xFF
LOG_MAGIC = b"P35L"
LOG_VERSION = 1
LOG_HEADER = ">4sHHHHL"
LOG_HEADER_BYTES = struct.calcsize(LOG_HEADER)
LOG_VOICE = ">BBHHHLH"
LOG_VOICE_BYTES = struct.calcsize(LOG_VOICE)
LOG_BLOCK_BYTES = 8 + VOICES * LOG_VOICE_BYTES


@dataclass(frozen=True)
class Sound:
    """What one key plays in one layer."""

    sample: int  # index into the instrument's samples
    step: int  # 16.16
    held: int  # 16-bit decay factor per block while the key or pedal holds it
    release: int  # 16-bit decay factor per block otherwise
    attack_blocks: int = 0


@dataclass(frozen=True)
class MixSample:
    """A sample as the mixer reads it."""

    data: np.ndarray  # signed 16-bit, padded (mixer.padded)
    length: int  # samples before the pad
    loop_start: int


@dataclass(frozen=True)
class Instrument:
    sounds: tuple[tuple[Sound, ...], ...]  # [key][layer]
    pans: tuple[tuple[int, int], ...]  # [key]: left and right gains
    roots: tuple[int, ...]  # [key]: index of the root it plays from
    volumes: tuple[tuple[int, ...], ...]  # [root][velocity]
    layer_of: tuple[int, ...]  # [velocity]


@dataclass
class Tone:
    """What the mixer plays on a voice."""

    sample: int
    phase: int  # 16.16
    step: int
    left: int
    right: int
    quarters: int = 4  # 4 except while a cut fades it

    @property
    def multipliers(self) -> tuple[int, int]:
        return mixer.faded(self.left, self.quarters), mixer.faded(self.right, self.quarters)


@dataclass
class Change:
    """Something that happens to a voice's tone at an output sample."""

    at: int
    quarters: int = 0  # a fade level, or 0 when a new tone starts
    tone: Tone | None = None


@dataclass
class Voice:
    key: int = -1  # the note the voice belongs to; -1 when free
    sound: Sound | None = None
    volume: int = 0
    pan: tuple[int, int] = (0, 0)
    serial: int = 0  # the note's index among the note ons, from 1
    key_down: bool = False
    start: int = 0  # output sample its note starts on (later than now while waiting)
    blocks: int = 0  # blocks decayed since the note started
    tone: Tone | None = None
    changes: list[Change] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.key >= 0

    def multipliers(self) -> tuple[int, int]:
        return mixer.multiplier(self.volume, self.pan[0]), mixer.multiplier(
            self.volume, self.pan[1]
        )


@dataclass
class Result:
    left: np.ndarray  # int16 output values, as the 68030's out step makes them
    right: np.ndarray
    log: bytes
    blocks: int
    steals: list[Steal] = field(default_factory=list)
    endings: list[Ending] = field(default_factory=list)
    notes: int = 0
    restrikes: int = 0
    superseded: int = 0  # replaced while waiting for a fade, so never sounded
    peak: int = 0  # largest true sum on either side, shifted to output units, before clamping
    clamped: int = 0  # output values (both sides) the out step clamps
    wraps: int = 0  # 32-bit sums whose true value does not fit 32 bits


def decay_factor(db_per_s: float, block_hz: float = mixer.BLOCK_HZ) -> int:
    """The 16-bit per-block factor that fades db_per_s decibels a second."""
    return max(0, min(0xFFFF, round(65536 * 10 ** (-db_per_s / (20 * block_hz)))))


def play(events: Sequence[Event], instrument: Instrument, samples: Sequence[MixSample]) -> Result:
    """Run the player over a performance, one block at a time."""
    if len(instrument.sounds) != KEYS:
        raise ValueError(f"need sounds for each of {KEYS} keys")
    state = _State(instrument, samples)
    timed = [(mixer.sample_of_ms(e.ms), e) for e in events]
    index, last = 0, timed[-1][0] // mixer.BLOCK if timed else 0
    block = 0
    while index < len(timed) or (block <= last + LIMIT_BLOCKS and state.sounding()):
        begin = block * mixer.BLOCK
        state.decay(begin)
        while index < len(timed) and timed[index][0] < begin + mixer.BLOCK:
            state.handle(*timed[index])
            index += 1
        state.mix(begin)
        block += 1
    end = block * mixer.BLOCK
    for voice in state.voices:
        if voice.active:
            state.ended(voice, "end", mixer.ms_of_sample(end), end)
    return state.result(block)


def log_header(blocks: int) -> bytes:
    return struct.pack(LOG_HEADER, LOG_MAGIC, LOG_VERSION, VOICES, mixer.BLOCK, 0, blocks)


def read_log(data: bytes) -> list[tuple[tuple[int, int], list[tuple[int, ...]]]]:
    """A voice log as (checksum, voice records) per block: the reference for reading
    the 68030 player's log."""
    magic, version, voices, block, _, blocks = struct.unpack_from(LOG_HEADER, data)
    if (magic, version, voices, block) != (LOG_MAGIC, LOG_VERSION, VOICES, mixer.BLOCK):
        raise ValueError("not a version 1 A3500 piano voice log")
    out, offset = [], LOG_HEADER_BYTES
    for _ in range(blocks):
        checksum = struct.unpack_from(">LL", data, offset)
        records = [
            struct.unpack_from(LOG_VOICE, data, offset + 8 + v * LOG_VOICE_BYTES)
            for v in range(VOICES)
        ]
        out.append((checksum, records))
        offset += LOG_BLOCK_BYTES
    return out


class _State:
    def __init__(self, instrument: Instrument, samples: Sequence[MixSample]):
        self.instrument = instrument
        self.samples = samples
        self.voices = [Voice() for _ in range(VOICES)]
        self.pedal = False
        self.serial = 0
        self.left: list[np.ndarray] = []
        self.right: list[np.ndarray] = []
        self.log = bytearray()
        self.steals: list[Steal] = []
        self.endings: list[Ending] = []
        self.notes = self.restrikes = self.superseded = 0
        self.peak = self.clamped = self.wraps = 0

    def sounding(self) -> bool:
        return any(v.active or v.tone is not None for v in self.voices)

    def result(self, blocks: int) -> Result:
        empty = np.zeros(0, dtype=np.int16)
        return Result(
            left=np.concatenate(self.left) if self.left else empty,
            right=np.concatenate(self.right) if self.right else empty,
            log=log_header(blocks) + bytes(self.log),
            blocks=blocks,
            steals=self.steals,
            endings=self.endings,
            notes=self.notes,
            restrikes=self.restrikes,
            superseded=self.superseded,
            peak=self.peak,
            clamped=self.clamped,
            wraps=self.wraps,
        )

    # 1. Decay

    def decay(self, begin: int) -> None:
        for voice in self.voices:
            if not voice.active or voice.start >= begin or voice.sound is None:
                continue
            voice.blocks += 1
            held = voice.key_down or self.pedal
            if held and voice.blocks <= voice.sound.attack_blocks:
                continue
            factor = voice.sound.held if held else voice.sound.release
            voice.volume = voice.volume * factor >> 16
            if voice.volume < STOP_VOLUME:
                self.ended(voice, "faded", mixer.ms_of_sample(begin), begin)
                self.free(voice)
            elif voice.tone is not None:
                voice.tone.left, voice.tone.right = voice.multipliers()

    @staticmethod
    def free(voice: Voice) -> None:
        voice.key, voice.sound, voice.volume, voice.key_down = -1, None, 0, False
        voice.tone, voice.changes = None, []

    # 2. Events

    def handle(self, at: int, event: Event) -> None:
        match event.kind:
            case "on":
                self.note_on(at, event)
            case "off":
                for voice in self.voices:
                    if voice.key == event.key:
                        voice.key_down = False
            case "down":
                self.pedal = True
            case "up":
                self.pedal = False

    def note_on(self, at: int, event: Event) -> None:
        self.serial += 1
        self.notes += 1
        ins = self.instrument
        sound = ins.sounds[event.key][ins.layer_of[event.velocity]]
        volume = ins.volumes[ins.roots[event.key]][event.velocity]
        index = self.choose_voice(event.key, at, event.ms)
        voice = self.voices[index]
        waiting = voice.active and voice.start > at
        sounding = voice.active and not waiting
        voice.key, voice.sound, voice.volume = event.key, sound, volume
        voice.pan, voice.serial, voice.key_down, voice.blocks = (
            ins.pans[event.key],
            self.serial,
            True,
            0,
        )
        tone = Tone(sound.sample, 0, sound.step, *voice.multipliers())
        if waiting:
            voice.changes[-1].tone = tone  # the fade carries on
        elif sounding:
            for step, quarters in enumerate(FADE_QUARTERS):
                voice.changes.append(Change(at + step * FADE_STEP, quarters))
            voice.start = at + len(FADE_QUARTERS) * FADE_STEP
            voice.changes.append(Change(voice.start, tone=tone))
        else:
            voice.start = at
            voice.changes.append(Change(at, tone=tone))

    def choose_voice(self, key: int, at: int, ms: int) -> int:
        for index, voice in enumerate(self.voices):
            if voice.key == key:
                self.restrikes += 1
                self.ended(voice, "restrike", ms, at)
                return index
        for index, voice in enumerate(self.voices):
            if not voice.active:
                return index
        index = min(range(VOICES), key=lambda i: self.steal_order(self.voices[i]))
        stolen = self.voices[index]
        self.steals.append(
            Steal(ms, index, stolen.volume, stolen.key_down or self.pedal, stolen.key, key)
        )
        self.ended(stolen, "steal", ms, at)
        return index

    @staticmethod
    def steal_order(voice: Voice) -> tuple[bool, int, int]:
        """Lowest is stolen first: key up before key down, then quietest, then oldest."""
        return voice.key_down, voice.volume, voice.serial

    def ended(self, voice: Voice, cause: str, ms: int, at: int) -> None:
        """Record the end of the note a voice sounds; a waiting note never sounded."""
        if voice.start > at:
            self.superseded += 1
            return
        self.endings.append(Ending(voice.serial - 1, ms, cause, voice.volume, voice.key_down))

    # 3. Mixing, and 4. the log

    def mix(self, begin: int) -> None:
        left = np.zeros(mixer.BLOCK, dtype=np.int64)
        right = np.zeros(mixer.BLOCK, dtype=np.int64)
        for voice in self.voices:
            self.mix_voice(voice, begin, left, right)
        for true in (left, right):
            self.peak = max(self.peak, int(np.abs(true >> mixer.OUTPUT_SHIFT).max()))
            self.wraps += int(np.count_nonzero(mixer.wrap32(true) != true))
        held_left, held_right = mixer.wrap32(left), mixer.wrap32(right)
        self.clamped += mixer.clamped(held_left) + mixer.clamped(held_right)
        left16, right16 = mixer.output16(held_left), mixer.output16(held_right)
        self.left.append(left16)
        self.right.append(right16)
        self.log += struct.pack(">LL", *mixer.checksum(left16, right16))
        for voice in self.voices:
            self.log += self.record(voice)

    def mix_voice(self, voice: Voice, begin: int, left: np.ndarray, right: np.ndarray) -> None:
        if voice.tone is not None:
            sample = self.samples[voice.tone.sample]
            voice.tone.phase = mixer.wrap_phase(voice.tone.phase, sample.length, sample.loop_start)
        end = begin + mixer.BLOCK
        due = [c for c in voice.changes if c.at < end]
        voice.changes = voice.changes[len(due) :]
        offset = 0
        for change in due:
            self.run(voice.tone, offset, change.at - begin, left, right)
            offset = change.at - begin
            if change.tone is not None:
                voice.tone = change.tone
            elif voice.tone is not None:
                voice.tone.quarters = change.quarters
        self.run(voice.tone, offset, mixer.BLOCK, left, right)

    def run(
        self, tone: Tone | None, begin: int, end: int, left: np.ndarray, right: np.ndarray
    ) -> None:
        if tone is None or end <= begin:
            return
        l_mul, r_mul = tone.multipliers
        data = self.samples[tone.sample].data
        l_part, r_part, tone.phase = mixer.mix_run(
            data, tone.phase, tone.step, l_mul, r_mul, end - begin
        )
        left[begin:end] += l_part
        right[begin:end] += r_part

    @staticmethod
    def record(voice: Voice) -> bytes:
        tone = voice.tone
        key = voice.key if voice.active else SILENT
        if tone is None:
            return struct.pack(LOG_VOICE, key, SILENT, voice.volume, 0, 0, 0, 0)
        l_mul, r_mul = tone.multipliers
        return struct.pack(
            LOG_VOICE,
            key,
            tone.sample,
            voice.volume,
            l_mul,
            r_mul,
            tone.phase >> 16,
            tone.phase & 0xFFFF,
        )
