import pytest
from amiga_env.piano.score import (
    Event,
    MidiMessage,
    decode,
    encode,
    performance,
    report,
    wait_bytes,
)


def on(seconds, note, velocity):
    return MidiMessage(seconds, "note_on", note, velocity)


def cc(seconds, number, value):
    return MidiMessage(seconds, "control_change", number, value)


class TestPerformance:
    def test_keys_count_from_a0_and_times_round_to_the_millisecond(self):
        perf = performance([on(0.0014, 21, 40), on(1.0006, 108, 90)])

        assert perf.events == [Event(1, "on", 0, 40), Event(1001, "on", 87, 90)]

    def test_a_note_on_with_velocity_zero_is_a_note_off(self):
        perf = performance([on(0, 60, 50), on(0.5, 60, 0), MidiMessage(0.6, "note_off", 61, 0)])

        assert [e.kind for e in perf.events] == ["on", "off", "off"]
        assert perf.notes == 1

    def test_the_sustain_pedal_is_down_from_64_and_only_changes_are_kept(self):
        perf = performance([cc(0, 64, 10), cc(0.1, 64, 64), cc(0.2, 64, 120), cc(0.3, 64, 63)])

        assert [(e.ms, e.kind) for e in perf.events] == [(100, "down"), (300, "up")]
        assert perf.sustain_messages == 4

    def test_sostenuto_and_soft_pedals_are_counted_and_left_out(self):
        perf = performance([cc(0, 66, 127), cc(0, 67, 127), cc(0.1, 67, 0)])

        assert perf.events == []
        assert (perf.sostenuto_messages, perf.soft_messages) == (1, 2)

    def test_notes_outside_the_88_keys_are_dropped_and_counted(self):
        perf = performance([on(0, 20, 50), on(0, 109, 50), MidiMessage(1, "note_off", 20, 0)])

        assert perf.events == []
        assert perf.dropped_notes == 2

    def test_events_keep_their_order_within_a_millisecond(self):
        perf = performance([on(0.0101, 60, 0), on(0.0102, 60, 70)])

        assert [e.kind for e in perf.events] == ["off", "on"]


class TestTheStream:
    @pytest.mark.parametrize(
        ("ms", "expected"),
        [
            (0, b""),
            (1, b"\x58"),
            (40, b"\x7f"),
            (41, b"\xe0\x29"),
            (255, b"\xe0\xff"),
            (256, b"\xe1\x01\x00"),
            (65535, b"\xe1\xff\xff"),
            (65536, b"\xe1\xff\xff\x58"),
        ],
    )
    def test_waits_take_the_shortest_form(self, ms, expected):
        assert wait_bytes(ms) == expected

    def test_a_chord_needs_no_wait_between_its_notes(self):
        stream = encode([Event(0, "on", 39, 64), Event(0, "on", 43, 60), Event(5, "off", 39)])

        assert stream == bytes([39, 64, 43, 60, 0x57 + 5, 0x80 + 39, 0xFF])

    def test_pedal_bytes(self):
        assert encode([Event(0, "down"), Event(0, "up")]) == b"\xf0\xf1\xff"

    def test_decoding_gives_back_the_events(self):
        events = [
            Event(0, "down"),
            Event(3, "on", 0, 1),
            Event(3, "on", 87, 127),
            Event(300, "off", 87),
            Event(70_000, "up"),
            Event(70_041, "off", 0),
        ]

        assert decode(encode(events)) == events

    def test_refuses_an_event_out_of_range(self):
        with pytest.raises(ValueError, match="out of range"):
            encode([Event(0, "on", 88, 64)])

    def test_refuses_events_out_of_order(self):
        with pytest.raises(ValueError, match="back in time"):
            encode([Event(5, "down"), Event(4, "up")])

    def test_decode_refuses_an_unknown_byte(self):
        with pytest.raises(ValueError, match="not an event"):
            decode(b"\xe5\xff")


def test_the_report_gives_size_velocities_and_what_was_ignored():
    perf = performance([on(0, 60, 30), on(0, 64, 70), cc(0, 67, 127), on(1, 64, 0)])

    found = report(perf, encode(perf.events))

    assert found["bytes"] == 2 + 2 + 3 + 1 + 1  # two notes, a 1000 ms wait, an off, the end
    assert found["velocity_median"] == 50
    assert found["soft_messages_ignored"] == 1
    assert found["length_s"] == 1.0
