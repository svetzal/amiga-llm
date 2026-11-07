"""Amiga attributes as .uaem sidecar lines, with no time zone."""

import pytest
from amiga_env.uaem import Attributes, format_line, parse_line, protect_mask, protect_text

# C:Assign on the 3.2 Workbench floppy: 13 April 2021, 02:43:13 and 34 ticks.
ASSIGN = Attributes("--p-rwed", days=15808, minutes=163, ticks=684)


@pytest.mark.parametrize(
    ("mask", "text"),
    [
        (0x00, "----rwed"),
        (0x20, "--p-rwed"),  # a pure command
        (0x42, "-s--rw-d"),  # a script, not executable
        (0x07, "----r---"),
        (0xF0, "hsparwed"),
        (0x0F, "--------"),
    ],
)
def test_protection_masks_read_as_list_shows_them(mask, text):
    assert protect_text(mask) == text
    assert protect_mask(text) == mask


def test_a_datestamp_is_written_as_the_amiga_shows_it_whatever_the_host_zone():
    assert format_line(ASSIGN) == "--p-rwed 2021-04-13 02:43:13.68\n"


def test_a_comment_follows_the_date():
    line = format_line(Attributes("----rwed", 15808, 163, 0, "a comment"))

    assert line == "----rwed 2021-04-13 02:43:00.00 a comment\n"


def test_lines_read_back_to_the_same_attributes():
    assert parse_line(format_line(ASSIGN)) == ASSIGN
    with_comment = Attributes("-s--rw-d", 100, 1439, 2999, "two words")
    assert parse_line(format_line(with_comment)) == with_comment


def test_a_line_amiberry_wrote_without_a_newline_reads():
    assert parse_line("-s--rwed 2026-11-07 09:34:48.70").ticks == 48 * 50 + 35


@pytest.mark.parametrize("bad", ["", "rwed", "xs--rwed 2021-04-13 02:43:13.00", "----rwed today"])
def test_anything_else_is_refused(bad):
    with pytest.raises(ValueError):
        parse_line(bad)
