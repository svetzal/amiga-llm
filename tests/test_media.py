import json

import pytest
from amiga_env import MEDIA_DIR
from amiga_env.media import describe, load_manifest, migrate, tree_digest, verify


def test_manifest_loads_and_has_unique_destinations():
    root, items = load_manifest()
    assert root.is_absolute()
    assert items


def test_manifest_lives_in_media_dir():
    assert (MEDIA_DIR / "manifest.toml").exists()


def test_tree_digest_ignores_finder_litter_and_sees_content(tmp_path):
    (tmp_path / "a.txt").write_text("one")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("two")
    before, count = tree_digest(tmp_path)
    (tmp_path / ".DS_Store").write_text("noise")
    assert tree_digest(tmp_path) == (before, count)
    assert count == 2
    (tmp_path / "sub" / "b.txt").write_text("changed")
    assert tree_digest(tmp_path)[0] != before


def test_describe_file(tmp_path):
    f = tmp_path / "k.rom"
    f.write_bytes(b"\x11\x14")
    info = describe(f)
    assert info["kind"] == "file"
    assert info["size"] == 2


def _manifest(media, origin, items):
    media.mkdir(exist_ok=True)
    entries = "".join(
        f'[[item]]\ndest = "{dest}"\norigin = "{src}"\nlicence = "test"\n\n' for dest, src in items
    )
    (media / "manifest.toml").write_text(f'origin_root = "{origin}"\n\n{entries}')
    return media / "manifest.toml"


def _lock(media):
    return json.loads((media / "manifest.lock.json").read_text())


@pytest.fixture
def origin(tmp_path):
    origin = tmp_path / "origin"
    (origin / "ndk" / "include").mkdir(parents=True)
    (origin / "ndk" / "include" / "exec.h").write_text("struct ExecBase;")
    (origin / "kick.rom").write_bytes(b"\x11\x14\x4e\xf9")
    return origin


@pytest.fixture
def manifest(tmp_path, origin):
    return _manifest(tmp_path / "media", origin, [("rom/kick.rom", "kick.rom"), ("ndk", "ndk")])


@pytest.mark.parametrize("dest", ["/etc/kick.rom", "../outside.rom", "rom/../../x"])
def test_manifest_rejects_a_dest_outside_media(tmp_path, dest):
    path = _manifest(tmp_path / "media", tmp_path, [(dest, "kick.rom")])

    with pytest.raises(SystemExit, match="inside media"):
        load_manifest(path)


def test_migrate_copies_items_and_locks_them(manifest):
    migrate(manifest=manifest)

    media = manifest.parent
    assert (media / "rom" / "kick.rom").read_bytes() == b"\x11\x14\x4e\xf9"
    assert set(_lock(media)) == {"rom/kick.rom", "ndk"}
    assert verify(manifest)
    assert not list(media.rglob("*.partial"))


def test_migrate_does_not_reread_the_origin_for_media_already_present(manifest, origin):
    migrate(manifest=manifest)
    (origin / "kick.rom").unlink()

    migrate(manifest=manifest)

    assert verify(manifest)


def test_migrate_refuses_an_origin_that_does_not_match_the_lock(manifest, origin):
    migrate(manifest=manifest)
    kick = manifest.parent / "rom" / "kick.rom"
    kick.unlink()
    (origin / "kick.rom").write_bytes(b"not the same rom")

    with pytest.raises(SystemExit, match="does not match"):
        migrate(manifest=manifest)

    assert not kick.exists()
    assert not list(manifest.parent.rglob("*.partial"))


def test_an_interrupted_migrate_keeps_what_it_finished(tmp_path, origin):
    manifest = _manifest(
        tmp_path / "media", origin, [("rom/kick.rom", "kick.rom"), ("gone.adf", "gone.adf")]
    )

    with pytest.raises(SystemExit, match="Missing in origin"):
        migrate(manifest=manifest)

    assert set(_lock(manifest.parent)) == {"rom/kick.rom"}


def test_migrate_replaces_a_directory_rather_than_merging_into_it(manifest):
    stale = manifest.parent / "ndk" / "include" / "left-over.h"
    stale.parent.mkdir(parents=True)
    stale.write_text("from an earlier copy")

    migrate(manifest=manifest)

    assert not stale.exists()
    assert _lock(manifest.parent)["ndk"]["files"] == 1


def test_migrate_drops_lock_entries_the_manifest_no_longer_lists(manifest):
    (manifest.parent / "manifest.lock.json").write_text(json.dumps({"retired.rom": {}}))

    migrate(manifest=manifest)

    assert "retired.rom" not in _lock(manifest.parent)


def test_verify_reports_changed_media(manifest):
    migrate(manifest=manifest)
    (manifest.parent / "ndk" / "include" / "exec.h").write_text("edited")

    assert not verify(manifest)
