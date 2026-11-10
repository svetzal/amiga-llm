import re
import struct
from pathlib import Path

from amiga_env.piano import mixer, player3500, run3500

PLAYER = Path(__file__).parent.parent / "examples" / "piano3500" / "player.s"


def log(blocks):
    """A model-shaped log with `blocks` blocks of distinct bytes."""
    body = bytes((i * 7 + 3) % 256 for i in range(blocks * player3500.LOG_BLOCK_BYTES))
    return player3500.log_header(blocks) + body


class TestStartup:
    def test_each_piece_runs_with_its_number_and_a_failure_does_not_stop_the_rest(self):
        text = run3500.startup_sequence(["nocturne-op9-2", "bwv846"])

        assert text.splitlines()[1:] == ["FailAt 21", "player 1 nocturne-op9-2", "player 2 bwv846"]


class TestDefines:
    def test_the_player_is_assembled_with_the_models_constants(self):
        d = run3500.defines()

        assert d["VOICES"] == player3500.VOICES
        assert d["BLOCK"] == mixer.BLOCK
        assert d["OUTPUT_SHIFT"] == mixer.OUTPUT_SHIFT
        assert d["LIMIT_BLOCKS"] == player3500.LIMIT_BLOCKS
        assert d["LOG"] == 1 and run3500.defines(log=False)["LOG"] == 0

    def test_every_constant_passed_is_one_the_player_uses_and_it_defines_none_itself(self):
        source = PLAYER.read_text()

        for name in run3500.defines():
            assert re.search(rf"\b{name}\b", source), name
            assert not re.search(rf"^{name}\s+equ", source, re.MULTILINE), name


class TestStatus:
    def test_the_players_status_offsets_are_the_hosts_fields_in_order(self):
        offsets = {
            name: int(value)
            for name, value in re.findall(
                r"^ST_(\w+)\s+equ\s+(\d+)", PLAYER.read_text(), re.MULTILINE
            )
        }
        size = offsets.pop("SIZE")
        in_order = [name.lower().replace("_", "") for name in sorted(offsets, key=offsets.get)]

        assert size == run3500.STATUS_BYTES
        assert sorted(offsets.values()) == list(range(0, size, 4))
        assert in_order == [field.replace("_", "") for field in run3500.STATUS_FIELDS]

    def test_the_fast_ram_figures_are_the_last_four_longs(self):
        longs = [0] * len(run3500.STATUS_FIELDS)
        longs[-4:] = [15_000_000, 14_900_000, 3_000_000, 2_900_000]

        status = run3500.parse_status(struct.pack(f">{len(longs)}L", *longs))

        assert status.fast_largest_before == 14_900_000
        assert status.fast_free_after == 3_000_000

    def test_the_status_file_reads_as_its_fields(self):
        count = len(run3500.STATUS_FIELDS)
        data = struct.pack(
            f">{count}L", 0x50333550, 2, 0, 1, 100, 300000, 5000, 0, *range(count - 8)
        )

        status = run3500.parse_status(data)

        assert (status.state, status.run, status.blocks, status.worst_e) == (2, 1, 100, 5000)

    def test_the_cpu_share_is_e_clock_ticks_over_a_blocks_length(self):
        status = run3500.parse_status(
            struct.pack(
                f">{len(run3500.STATUS_FIELDS)}L",
                *(0, 2, 0, 1, 10, 10 * 6553, 13107, 1),
                *[0] * (len(run3500.STATUS_FIELDS) - 8),
            )
        )

        cpu = run3500.cpu_report(status)

        assert cpu["mean_percent"] == 50.0
        assert cpu["worst_percent"] == 100.0
        assert cpu["overruns"] == 1


class TestCompare:
    def test_identical_logs_have_no_difference(self):
        assert run3500.compare_logs(log(3), log(3))["identical"]

    def test_a_difference_is_named_by_block_voice_and_field(self):
        model = log(3)
        machine = bytearray(model)
        offset = player3500.LOG_HEADER_BYTES + 2 * player3500.LOG_BLOCK_BYTES + 8 + 5 * 14 + 8
        machine[offset + 1] ^= 1

        difference = run3500.first_difference(model, bytes(machine))

        assert (difference.block, difference.voice, difference.field) == (2, 5, "phase")
        assert difference.model != difference.machine

    def test_a_checksum_difference_has_no_voice(self):
        model = log(2)
        machine = bytearray(model)
        machine[player3500.LOG_HEADER_BYTES + player3500.LOG_BLOCK_BYTES + 5] ^= 1

        difference = run3500.first_difference(model, bytes(machine))

        assert (difference.block, difference.voice, difference.field) == (1, -1, "checksum_b")

    def test_a_short_log_differs_where_it_ends(self):
        model = log(3)

        found = run3500.compare_logs(model, model[: -player3500.LOG_BLOCK_BYTES])

        assert not found["identical"]
        assert found["machine_blocks"] == 2
        assert found["first_difference"]["block"] == 2
