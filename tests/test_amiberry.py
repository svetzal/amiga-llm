import pytest
from amiga_env.amiberry import Release, asset_name, core_asset_name, core_path, parse_sha256sums

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


CORES = Release(
    tag="v8.5.0",
    assets={
        name: f"https://example.invalid/{name}"
        for name in [
            "amiberry-libretro-macOS-arm64.dylib",
            "amiberry-libretro-linux-x86_64.so",
            "amiberry-libretro-linux-aarch64.so",
        ]
    },
)


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Darwin", "arm64", "amiberry-libretro-macOS-arm64.dylib"),
        ("Linux", "x86_64", "amiberry-libretro-linux-x86_64.so"),
        ("Linux", "amd64", "amiberry-libretro-linux-x86_64.so"),
        ("Linux", "aarch64", "amiberry-libretro-linux-aarch64.so"),
    ],
)
def test_libretro_core_for_host(system, machine, expected):
    assert core_asset_name(CORES, system, machine) == expected


def test_no_libretro_core_for_an_intel_mac():
    with pytest.raises(SystemExit, match="no libretro core"):
        core_asset_name(CORES, "Darwin", "x86_64")


def test_core_path_finds_the_core_beside_the_app(tmp_path):
    (tmp_path / "amiberry-libretro-macOS-arm64.dylib").write_bytes(b"")
    assert core_path(tmp_path) == tmp_path / "amiberry-libretro-macOS-arm64.dylib"


def test_core_path_says_how_to_get_the_core(tmp_path):
    with pytest.raises(SystemExit, match="amiga-env amiberry"):
        core_path(tmp_path)
