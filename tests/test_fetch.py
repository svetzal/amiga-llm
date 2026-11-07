import hashlib
import io
import json
import stat
import tarfile
import zipfile

import pytest
from amiga_env.fetch import fetch, member_path, unpack_tar, unpack_zip
from amiga_env.media import load_manifest, migrate, verify


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def _getter(payload: bytes, calls: list | None = None):
    def get(url, out, max_bytes):
        if calls is not None:
            calls.append(url)
        out.write_bytes(payload)

    return get


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class TestFetch:
    def test_returns_the_checked_file_when_nothing_is_unpacked(self, tmp_path):
        data = b"MThd"

        got = fetch("https://x/a.mid", _sha(data), len(data), tmp_path, None, _getter(data))

        assert got.read_bytes() == data

    def test_refuses_a_download_whose_checksum_differs(self, tmp_path):
        with pytest.raises(SystemExit, match="SHA-256"):
            fetch("https://x/a", "0" * 64, 4, tmp_path, None, _getter(b"evil"))

    def test_refuses_a_download_whose_size_differs(self, tmp_path):
        with pytest.raises(SystemExit, match="bytes, but the manifest says 9"):
            fetch("https://x/a", _sha(b"evil"), 9, tmp_path, None, _getter(b"evil"))

    def test_needs_an_empty_directory(self, tmp_path):
        (tmp_path / "left-over").write_text("x")

        with pytest.raises(SystemExit, match="must be empty"):
            fetch("https://x/a", "0" * 64, 1, tmp_path, None, _getter(b"x"))

    def test_unpacks_a_zip_and_drops_the_archive(self, tmp_path):
        data = _zip({"top/2011/a.midi": b"MThd", "top/LICENSE": b"cc"})

        got = fetch("https://x/a.zip", _sha(data), len(data), tmp_path, "zip", _getter(data))

        assert (got / "top" / "2011" / "a.midi").read_bytes() == b"MThd"
        assert not (tmp_path / "download").exists()


class TestUnpackingTreatsArchivesAsData:
    @pytest.mark.parametrize("name", ["/etc/passwd", "../up.txt", "a/../../up.txt", "C:/x"])
    def test_member_path_refuses_paths_that_leave_the_destination(self, tmp_path, name):
        with pytest.raises(SystemExit, match="outside the destination"):
            member_path(name, tmp_path)

    def test_zip_members_lose_their_execute_bits(self, tmp_path):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            info = zipfile.ZipInfo("run.sh")
            info.external_attr = (stat.S_IFREG | 0o755) << 16
            zf.writestr(info, b"#!/bin/sh\n")
        archive = tmp_path / "a.zip"
        archive.write_bytes(buffer.getvalue())
        into = tmp_path / "into"
        into.mkdir()

        unpack_zip(archive, into)

        assert stat.S_IMODE((into / "run.sh").stat().st_mode) == 0o644

    def test_a_zip_symlink_is_refused(self, tmp_path):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            info = zipfile.ZipInfo("link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, b"/etc/passwd")
        archive = tmp_path / "a.zip"
        archive.write_bytes(buffer.getvalue())

        with pytest.raises(SystemExit, match="not a file or directory"):
            unpack_zip(archive, tmp_path)

    def test_a_tar_symlink_is_refused(self, tmp_path):
        archive = tmp_path / "a.tar.xz"
        with tarfile.open(archive, "w:xz") as tf:
            link = tarfile.TarInfo("link")
            link.type = tarfile.SYMTYPE
            link.linkname = "/etc/passwd"
            tf.addfile(link)

        with pytest.raises(SystemExit, match="not a file or directory"):
            unpack_tar(archive, tmp_path)

    def test_a_compressed_tar_unpacks(self, tmp_path):
        archive = tmp_path / "a.tar.xz"
        with tarfile.open(archive, "w:xz") as tf:
            data = b"<region> sample=a.wav"
            info = tarfile.TarInfo("piano/piano.sfz")
            info.size = len(data)
            info.mode = 0o755
            tf.addfile(info, io.BytesIO(data))
        into = tmp_path / "into"
        into.mkdir()

        unpack_tar(archive, into)

        unpacked = into / "piano" / "piano.sfz"
        assert unpacked.read_bytes() == b"<region> sample=a.wav"
        assert stat.S_IMODE(unpacked.stat().st_mode) == 0o644


DOWNLOAD = """\
[[download]]
dest = "{dest}"
url = "https://example.org/a.zip"
sha256 = "{sha}"
size = {size}
licence = "CC BY 3.0"
{extra}
"""


def _download_manifest(media, data, dest="piano/set", extra='unpack = "zip"'):
    media.mkdir(parents=True, exist_ok=True)
    text = DOWNLOAD.format(dest=dest, sha=_sha(data), size=len(data), extra=extra)
    (media / "manifest.toml").write_text(text)
    return media / "manifest.toml"


class TestDownloadsInTheManifest:
    def test_fetches_unpacks_and_locks_a_download_with_its_url(self, tmp_path):
        data = _zip({"a.sfz": b"<region>"})
        manifest = _download_manifest(tmp_path / "media", data)

        migrate(manifest=manifest, environ={}, get=_getter(data))

        media = manifest.parent
        assert (media / "piano" / "set" / "a.sfz").read_bytes() == b"<region>"
        entry = json.loads((media / "manifest.lock.json").read_text())["piano/set"]
        assert entry["kind"] == "tree"
        assert entry["url"] == "https://example.org/a.zip"
        assert entry["download_sha256"] == _sha(data)
        assert verify(manifest)
        assert [p.name for p in (media / "piano").iterdir()] == ["set"]

    def test_does_not_fetch_again_when_the_lock_matches(self, tmp_path):
        data = _zip({"a.sfz": b"<region>"})
        manifest = _download_manifest(tmp_path / "media", data)
        migrate(manifest=manifest, environ={}, get=_getter(data))
        calls = []

        migrate(manifest=manifest, environ={}, get=_getter(data, calls))

        assert calls == []

    def test_an_optional_download_that_cannot_be_fetched_is_skipped(self, tmp_path):
        data = b"x"
        manifest = _download_manifest(tmp_path / "media", data, extra="optional = true")

        def offline(url, out, max_bytes):
            raise OSError("no network")

        migrate(manifest=manifest, environ={}, get=offline)

        assert not (manifest.parent / "piano" / "set").exists()
        assert verify(manifest)

    def test_a_tampered_download_installs_nothing(self, tmp_path):
        manifest = _download_manifest(tmp_path / "media", b"good")

        with pytest.raises(SystemExit, match="SHA-256"):
            migrate(manifest=manifest, environ={}, get=_getter(b"evil"))

        assert not (manifest.parent / "piano" / "set").exists()
        assert not list((manifest.parent / "piano").iterdir())

    @pytest.mark.parametrize(
        ("field", "value", "message"),
        [
            ("url", '"http://example.org/a"', "https"),
            ("sha256", '"ABC"', "64 lower-case hex"),
            ("size", "0", "length in bytes"),
            ("unpack", '"rar"', "unpack is one of"),
        ],
    )
    def test_rejects_a_bad_field(self, tmp_path, field, value, message):
        manifest = _download_manifest(tmp_path / "media", b"x", extra="")
        text = manifest.read_text()
        lines = [f"{field} = {value}" if line.startswith(f"{field} =") else line
                 for line in text.splitlines()]  # fmt: skip
        if not any(line.startswith(f"{field} =") for line in text.splitlines()):
            lines.append(f"{field} = {value}")
        manifest.write_text("\n".join(lines) + "\n")

        with pytest.raises(SystemExit, match=message):
            load_manifest(manifest)

    def test_a_download_and_an_item_cannot_share_a_dest(self, tmp_path):
        manifest = _download_manifest(tmp_path / "media", b"x", dest="k.rom", extra="")
        manifest.write_text(
            '[sources.f]\nenv = "F"\ndescription = "d"\n'
            '[[item]]\ndest = "k.rom"\nsource = "f"\norigin = "k.rom"\nlicence = "t"\n'
            + manifest.read_text()
        )

        with pytest.raises(SystemExit, match="same dest twice"):
            load_manifest(manifest)
