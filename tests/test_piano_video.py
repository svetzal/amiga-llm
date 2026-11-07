from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest
from amiga_env.piano import machine, video
from amiga_env.profile import Machine

A500 = Machine("A500", Path("rom/kick.rom"), None, ("ntsc=true",), "")
LAYOUT = video.ListLayout(
    left=190,
    right=318,
    top=8,
    line_pitch=11,
    lines=10,
    text=(238, 221, 187),
    highlight=(187, 153, 85),
)
DARK = (0, 17, 51)


def screen_with(gold: int | None, text=LAYOUT.text, highlight=LAYOUT.highlight) -> np.ndarray:
    """A 320x200 screen: the dark wall, a few text pixels on every line, one line gold."""
    screen = np.zeros((200, 320, 3), np.uint8)
    screen[:, :] = DARK
    for line in range(LAYOUT.lines):
        row = LAYOUT.top + line * LAYOUT.line_pitch + 3
        screen[row : row + 5, 200:220:2] = highlight if line == gold else text
    return screen


def status(**fields) -> machine.Status:
    values = dict.fromkeys(machine.STATUS_FIELDS, 0) | {"magic": machine.MAGIC} | fields
    return machine.Status(**values)


class TestCoreOptions:
    def test_the_profile_becomes_options(self):
        options = video.core_options(A500, Path("/m/rom/kick.rom"))
        assert options["amiberry_model"] == "A500"
        assert options["amiberry_kickstart"] == "/m/rom/kick.rom"
        assert options["amiberry_video_standard"] == "ntsc"

    def test_floppy_speed_is_never_left_to_the_core(self):
        assert video.core_options(A500, Path("/k"))["amiberry_floppy_speed"] == "100"

    def test_the_sound_is_a_real_a500s_at_48_khz(self):
        options = video.core_options(A500, Path("/k"))
        assert options["amiberry_stereo_separation"] == "10"
        assert options["amiberry_audio_rate"] == "48000"
        assert options["amiberry_sound_filter"] == "emulated"

    def test_a_setting_the_core_cannot_take_is_refused(self):
        odd = Machine("A500", Path("k"), None, ("ntsc=true", "chipmem_size=4"), "")
        with pytest.raises(SystemExit, match="chipmem_size=4"):
            video.core_options(odd, Path("/k"))


class TestCoreCommandLine:
    LINE = (
        "core_entry argv: [amiberry] [--model] [A500] [-s] [sound_frequency=48000] [-s] "
        "[ntsc=true] [-G] [-s] [amiberry.rom_path=/x/system] [-r] [/m/kick.rom] [-s] "
        "[statefile_path=/x/save] [/x/piano.adf]"
    )

    def test_the_log_line_becomes_arguments(self):
        argv = video.parse_argv_log(self.LINE)
        assert argv[:3] == ["amiberry", "--model", "A500"]
        assert argv[-1] == "/x/piano.adf"

    def test_the_frontends_paths_are_left_out(self):
        assert video.app_arguments(video.parse_argv_log(self.LINE)) == [
            "--model",
            "A500",
            "-s",
            "sound_frequency=48000",
            "-s",
            "ntsc=true",
            "-G",
            "-r",
            "/m/kick.rom",
            "/x/piano.adf",
        ]


class TestConfigDifferences:
    def test_identical_configurations_differ_in_nothing(self):
        assert video.config_differences("a=1\nuse_gui=yes\n", "use_gui=no\na=1\n") == []

    def test_a_changed_or_missing_setting_is_named(self):
        app = "floppy_speed=100\nntsc=true\n"
        core = "floppy_speed=0\n"
        assert video.config_differences(app, core) == [
            "floppy_speed: 100 -> 0",
            "ntsc: true -> None",
        ]


class TestStatus:
    def test_no_block_before_the_player_writes_it(self):
        assert video.status_of(bytes(4 * len(machine.STATUS_FIELDS))) is None

    def test_a_short_read_is_no_block(self):
        assert video.status_of(b"") is None

    def test_the_block_is_read_big_endian(self):
        longs = [0] * len(machine.STATUS_FIELDS)
        longs[0], longs[machine.STATUS_FIELDS.index("vblanks")] = machine.MAGIC, 1234
        block = b"".join(n.to_bytes(4, "big") for n in longs)
        assert video.status_of(block).vblanks == 1234

    @pytest.mark.parametrize(
        ("starts", "played", "done"),
        [(10, 9, False), (9, 9, False), (10, 10, True), (11, 10, True)],
    )
    def test_the_run_ends_when_every_piece_has_played(self, starts, played, done):
        assert video.finished(status(starts=starts, played=played), 10) is done

    def test_nothing_is_finished_before_the_player_runs(self):
        assert not video.finished(None, 10)


class TestCanvas:
    def test_a_full_frame_loses_only_its_row_padding(self):
        pitch = video.FRAME_WIDTH * 4 + 8
        pixels = bytes(range(256)) * (pitch * video.FRAME_HEIGHT // 256 + 1)
        frame, fitted = video.canvas(pixels[: pitch * video.FRAME_HEIGHT], 752, 486, pitch)
        assert not fitted
        assert len(frame) == 752 * 486 * 4
        assert frame[: 752 * 4] == pixels[: 752 * 4]
        assert frame[752 * 4 : 752 * 8] == pixels[pitch : pitch + 752 * 4]

    def test_a_shorter_frame_sits_at_the_top_on_black(self):
        frame, fitted = video.canvas(b"\xff" * (752 * 4 * 484), 752, 484, 752 * 4)
        assert fitted
        rows = np.frombuffer(frame, np.uint8).reshape(486, -1)
        assert rows[:484].min() == 255 and rows[484:].max() == 0

    def test_the_screen_is_every_other_pixel_from_60_48_in_rgb(self):
        pixels = np.zeros((486, 752, 4), np.uint8)
        pixels[48, 60] = (1, 2, 3, 0)  # B, G, R, X
        pixels[49, 61] = (9, 9, 9, 0)  # the same lowres pixel's other half
        pixels[50, 62] = (4, 5, 6, 0)
        screen = video.screen_of(pixels.tobytes())
        assert screen.shape == (200, 320, 3)
        assert tuple(screen[0, 0]) == (3, 2, 1)
        assert tuple(screen[1, 1]) == (6, 5, 4)


class TestGoldLine:
    def test_ocs_colours_scale_to_8_bits(self):
        assert video.ocs_rgb("B95") == (187, 153, 85)

    @pytest.mark.parametrize("line", [0, 4, 9])
    def test_the_gold_line_is_found(self, line):
        assert video.gold_line(screen_with(line), LAYOUT) == line

    def test_no_line_is_gold_between_pieces(self):
        assert video.gold_line(screen_with(None), LAYOUT) is None

    def test_colours_drifted_by_an_encode_still_read(self):
        drifted = screen_with(3, text=(230, 214, 192), highlight=(180, 150, 92))
        assert video.gold_line(drifted, LAYOUT) == 3

    def test_a_few_stray_pixels_are_not_a_line(self):
        screen = screen_with(None)
        screen[50, 200:203] = LAYOUT.highlight
        assert video.gold_line(screen, LAYOUT) is None

    def test_a_screen_without_the_players_ivory_is_not_read(self):
        # The frame the screen opens in, before the player loads its palette:
        # the text in another colour, picture pixels near gold here and there.
        screen = screen_with(None, text=(153, 51, 238))
        screen[30:36, 230:250:2] = (190, 150, 80)
        assert video.gold_line(screen, LAYOUT) is None

    def test_onsets_are_where_a_line_turns_gold(self):
        lines = [None, None, 0, 0, 0, None, None, 1, 1, 2, None]
        assert video.gold_onsets(lines) == [
            video.Onset(2, 0),
            video.Onset(7, 1),
            video.Onset(9, 2),
        ]


class TestChapters:
    @pytest.mark.parametrize(
        ("seconds", "shown"),
        [(0, "0:00"), (61.9, "1:01"), (599.99, "9:59"), (754.2, "12:34"), (3725, "1:02:05")],
    )
    def test_timestamps_are_rounded_down(self, seconds, shown):
        assert video.timestamp(seconds) == shown

    def test_a_title_becomes_composer_and_work(self):
        assert video.chapter_label("Chopin  Nocturne Op. 9 No. 2") == "Chopin: Nocturne Op. 9 No. 2"

    def test_a_title_without_the_double_space_is_refused(self):
        with pytest.raises(SystemExit, match="two spaces"):
            video.chapter_label("Chopin Nocturne")

    def test_chapters_start_at_zero_with_the_boot(self):
        found = video.chapters("Boot", [(36.6, "A: a"), (300.2, "B: b")], 400)
        assert video.chapter_lines(found) == ["0:00 Boot", "0:36 A: a", "5:00 B: b"]

    @pytest.mark.parametrize(
        "starts, length",
        [([(9.5, "A: a")], 100), ([(30, "A: a"), (39.9, "B: b")], 100), ([(30, "A: a")], 39.5)],
    )
    def test_a_chapter_under_10_seconds_is_refused(self, starts, length):
        with pytest.raises(SystemExit, match="under 10 s"):
            video.chapters("Boot", starts, length)

    def test_the_description_takes_the_chapters(self):
        found = video.chapters("Boot", [(36.6, "A: a")], 100)
        assert (
            video.description("Hi\n\n{chapters}\n\nBye", found)
            == "Hi\n\n0:00 Boot\n0:36 A: a\n\nBye"
        )

    def test_a_template_without_chapters_is_refused(self):
        with pytest.raises(SystemExit, match="chapters"):
            video.description("Hi", [])


class TestCommands:
    def test_the_capture_is_lossless_at_the_ntsc_rate(self):
        command = video.capture_command("ffmpeg", video.NTSC_FPS, Path("c.mkv"))
        assert command[command.index("-framerate") + 1] == "1431818/23933"
        assert command[command.index("-c:v") + 1] == "ffv1"
        assert command[command.index("-video_size") + 1] == "752x486"

    def test_the_ntsc_frame_rate(self):
        assert float(video.NTSC_FPS) == pytest.approx(59.8261, abs=1e-4)
        assert video.NTSC_FPS == Fraction(3_579_545) / Fraction("227.5") / 263

    def test_the_masters_share_one_nearest_neighbour_widening(self):
        masters = [
            video.Master(3840, 2160, 2880, Path("4k.mp4")),
            video.Master(1920, 1080, 1440, Path("hd.mp4")),
        ]
        graph = video.picture_filter(masters)
        assert graph.startswith("[0:v]crop=640:400:60:48,scale=2880:2160:flags=neighbor,split=2")
        assert "[p0]pad=3840:2160:480:0:black" in graph
        assert "[p1]scale=1440:1080:flags=area,pad=1920:1080:240:0:black" in graph

    def test_each_master_keeps_every_frame_and_the_audio(self):
        masters = [video.Master(3840, 2160, 2880, Path("4k.mp4"))]
        command = video.master_command("ffmpeg", Path("c.mkv"), Path("a.wav"), masters)
        assert command[command.index("-fps_mode") + 1] == "passthrough"
        assert command[command.index("-b:a") + 1] == "256k"
        assert command[command.index("-ar") + 1] == "48000"
        assert command[-1] == "4k.mp4"

    def test_the_list_is_read_back_at_the_screens_size(self):
        command = video.list_command("ffmpeg", Path("v.mp4"), LAYOUT, (480, 0, 2880, 2160))
        assert "crop=2880:2160:480:0,scale=320:200:flags=area" in command[command.index("-vf") + 1]
        assert "crop=128:110:190:8" in command[command.index("-vf") + 1]


class TestSound:
    def test_the_first_sound_after_a_point(self):
        samples = np.zeros((100, 2), np.int16)
        samples[10, 0] = 1000
        samples[60, 1] = -300
        assert video.first_sound(samples, 0) == 10
        assert video.first_sound(samples, 11) == 60
        assert video.first_sound(samples, 61) is None

    def test_runs_of_digital_silence(self):
        samples = np.ones((100, 2), np.int16)
        samples[10:40] = 0
        samples[50:55] = 0
        samples[90:] = 0
        assert video.silent_runs(samples, 10) == [(10, 30), (90, 10)]

    def test_levels_in_dbfs(self):
        samples = np.full((100, 2), 16384, np.int16)
        assert video.levels(samples) == {"rms_dbfs": -6.0, "peak_dbfs": -6.0}

    def test_a_vblank_count_maps_to_a_frame(self):
        counts = [0, 0, 0, 1, 2, 3, 4]
        assert video.frame_of(1, counts) == 3
        assert video.frame_of(4, counts) == 6
        assert video.frame_of(5, counts) is None


class TestSoundOffset:
    def test_each_note_bounds_the_offset_by_one_frame(self):
        assert video.sound_offset_ms([-5.2, -20.1, -12.5], 16.7) == pytest.approx((-21.9, -20.1))

    def test_bounds_that_do_not_meet_are_refused(self):
        with pytest.raises(SystemExit, match="do not agree"):
            video.sound_offset_ms([0.0, -30.0], 16.7)

    def test_no_notes_no_bound(self):
        with pytest.raises(SystemExit, match="no first notes"):
            video.sound_offset_ms([], 16.7)

    def test_the_delay_puts_the_middle_of_the_bound_on_zero(self):
        assert video.audio_delay_ms((-21.9, -20.1)) == 21

    def test_sound_that_lags_is_left_alone(self):
        assert video.audio_delay_ms((-8.1, 8.6)) == 0

    def test_the_master_delays_the_sound(self):
        masters = [video.Master(1920, 1080, 1440, Path("hd.mp4"))]
        command = video.master_command("ffmpeg", Path("c.mkv"), Path("a.wav"), masters, delay_ms=21)
        assert command[command.index("-af") + 1] == "adelay=21:all=1"
