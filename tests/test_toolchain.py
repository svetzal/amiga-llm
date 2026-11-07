import hashlib

import pytest
from amiga_env.toolchain import (
    VASM,
    VLINK,
    Source,
    archive_name,
    check_digest,
    listed_versions,
    make_command,
    stray_members,
    version_key,
)

LISTING = """
<a href="vasm1_9f.tar.gz">vasm1_9f.tar.gz</a>
<a href="vasm2_0.tar.gz">vasm2_0.tar.gz</a>
<a href="vasm2_0f.tar.gz">vasm2_0f.tar.gz</a>
<a href="vasm.tar.gz">vasm.tar.gz</a>
<a href="vlink0_9.tar.gz">vlink0_9.tar.gz</a>
<a href="vlink0_18a.tar.gz">vlink0_18a.tar.gz</a>
<a href="vlink0_16h.tar.gz">vlink0_16h.tar.gz</a>
"""


@pytest.mark.parametrize(
    ("name", "version", "expected"),
    [("vasm", "2.0f", "vasm2_0f.tar.gz"), ("vlink", "0.18a", "vlink0_18a.tar.gz")],
)
def test_archive_name_follows_the_authors_naming(name, version, expected):
    assert archive_name(name, version) == expected


def test_the_pins_download_from_the_versioned_tags_directory():
    assert VASM.url == "http://phoenix.owl.de/tags/vasm2_0f.tar.gz"
    assert VLINK.url == "http://phoenix.owl.de/tags/vlink0_18a.tar.gz"


def test_listed_versions_are_ordered_and_skip_the_unversioned_archive():
    assert listed_versions(LISTING, "vasm") == ["1.9f", "2.0", "2.0f"]


def test_minor_versions_compare_as_numbers():
    assert listed_versions(LISTING, "vlink") == ["0.9", "0.16h", "0.18a"]


def test_a_letter_release_follows_its_base_release():
    assert version_key("2.0") < version_key("2.0a") < version_key("2.1")


def test_a_malformed_version_is_an_error():
    with pytest.raises(ValueError):
        version_key("2.0-beta")


def test_a_payload_matching_the_pin_passes():
    payload = b"vasm source"
    source = Source("vasm", "9.9", hashlib.sha256(payload).hexdigest(), (), ())

    assert check_digest(payload, source) == source.sha256


def test_a_payload_not_matching_the_pin_is_refused():
    with pytest.raises(SystemExit, match="Checksum mismatch"):
        check_digest(b"something else", VASM)


def test_members_outside_the_top_directory_are_reported():
    names = ["vasm", "vasm/Makefile", "vasm/cpus/m68k/cpu.c", "vasmevil/x", "../etc/passwd"]

    assert stray_members(names, "vasm") == ["vasmevil/x", "../etc/passwd"]


def test_vasm_builds_the_m68k_cpu_with_motorola_syntax_using_the_host_compiler():
    command = make_command(VASM, jobs=4)

    assert command == ["make", "-j4", "CC=cc", "CPU=m68k", "SYNTAX=mot"]
    assert "vasmm68k_mot" in VASM.products
