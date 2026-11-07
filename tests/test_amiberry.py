import pytest
from amiga_env.amiberry import Release, asset_name, parse_sha256sums

RELEASE = Release(
    tag="v8.5.0",
    assets={
        name: f"https://example.invalid/{name}"
        for name in [
            "Amiberry-8.5.0-macOS-universal.dmg",
            "Amiberry-8.5.0-x86_64.AppImage",
            "Amiberry-8.5.0-aarch64.AppImage",
            "SHA256SUMS",
        ]
    },
)


def test_version_drops_the_v():
    assert RELEASE.version == "8.5.0"


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", "Amiberry-8.5.0-macOS-universal.dmg"),
        ("Darwin", "x86_64", "Amiberry-8.5.0-macOS-universal.dmg"),
        ("Linux", "x86_64", "Amiberry-8.5.0-x86_64.AppImage"),
        ("Linux", "aarch64", "Amiberry-8.5.0-aarch64.AppImage"),
    ],
)
def test_asset_for_host(system, machine, expected):
    assert asset_name(RELEASE, system, machine) == expected


def test_missing_asset_is_an_error():
    sparse = Release(tag="v9.0.0", assets={"SHA256SUMS": "x"})
    with pytest.raises(SystemExit):
        asset_name(sparse, "Darwin", "arm64")


def test_sha256sums_accepts_text_and_binary_markers():
    text = "ABC123  Amiberry.dmg\ndef456 *amiberry.AppImage\n\nnot a sum line here\n"
    assert parse_sha256sums(text) == {"Amiberry.dmg": "abc123", "amiberry.AppImage": "def456"}


@pytest.mark.parametrize(("system", "machine"), [("Linux", "riscv64"), ("Windows", "AMD64")])
def test_unsupported_host_is_an_error(system, machine):
    with pytest.raises(SystemExit, match="No Amiberry asset rule"):
        asset_name(RELEASE, system, machine)
