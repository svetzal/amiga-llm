import json

import pytest
from amiga_env.media import (
    Item,
    Source,
    add,
    add_source,
    check_new_dest,
    describe,
    load_manifest,
    manifest_path,
    migrate,
    parse_manifest,
    relative_origin,
    tree_digest,
    verify,
    with_item,
    with_source,
)
from conftest import REPO

SOURCES = """\
[sources.forever]
env = "FOREVER_DIR"
description = "an Amiga Forever folder"

[sources.extra]
env = "EXTRA_DIR"
description = "other things"
"""


def test_amiga_llms_manifest_names_its_three_sources_and_no_paths():
    loaded = load_manifest()

    assert manifest_path() == REPO / "media" / "manifest.toml"
    assert set(loaded.sources) == {"amiga_forever", "amigaos32", "collection"}
    assert loaded.items
    assert all(not item.origin.startswith(("/", "~")) for item in loaded.items)


def test_amiga_llms_personal_collection_items_are_all_optional():
    # Someone without Stacey's personal collection can still run the project:
    # only Amiga Forever and AmigaOS 3.2 media are required.
    items = load_manifest().items

    assert all(i.optional for i in items if i.source == "collection")
    assert all(not i.optional for i in items if i.source != "collection")


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


def _manifest(media, items):
    """items: (dest, source, origin, optional)"""
    media.mkdir(exist_ok=True)
    entries = "".join(
        f'[[item]]\ndest = "{dest}"\nsource = "{source}"\norigin = "{origin}"\n'
        f'licence = "test"\n{"optional = true" if optional else ""}\n\n'
        for dest, source, origin, optional in items
    )
    (media / "manifest.toml").write_text(f"# a comment to keep\n\n{SOURCES}\n{entries}")
    return media / "manifest.toml"


def _lock(media):
    return json.loads((media / "manifest.lock.json").read_text())


@pytest.fixture
def origin(tmp_path):
    origin = tmp_path / "forever"
    (origin / "ndk" / "include").mkdir(parents=True)
    (origin / "ndk" / "include" / "exec.h").write_text("struct ExecBase;")
    (origin / "kick.rom").write_bytes(b"\x11\x14\x4e\xf9")
    return origin


@pytest.fixture
def env(origin):
    return {"FOREVER_DIR": str(origin)}


@pytest.fixture
def manifest(tmp_path):
    items = [("rom/kick.rom", "forever", "kick.rom", False), ("ndk", "forever", "ndk", False)]
    return _manifest(tmp_path / "media", items)


class TestTheManifest:
    @pytest.mark.parametrize("dest", ["/etc/kick.rom", "../outside.rom", "rom/../../x", ""])
    def test_rejects_a_dest_outside_media(self, tmp_path, dest):
        path = _manifest(tmp_path / "media", [(dest, "forever", "kick.rom", False)])

        with pytest.raises(SystemExit, match="inside media"):
            load_manifest(path)

    def test_rejects_a_dest_that_would_replace_the_lock(self, tmp_path):
        path = _manifest(tmp_path / "media", [("manifest.lock.json", "forever", "k", False)])

        with pytest.raises(SystemExit, match="would replace"):
            load_manifest(path)

    def test_rejects_an_item_from_an_unknown_source(self, tmp_path):
        path = _manifest(tmp_path / "media", [("k.rom", "hyperion", "k.rom", False)])

        with pytest.raises(SystemExit, match="no source named hyperion"):
            load_manifest(path)

    @pytest.mark.parametrize("origin", ["/abs/kick.rom", "../kick.rom"])
    def test_rejects_an_origin_outside_its_source(self, tmp_path, origin):
        path = _manifest(tmp_path / "media", [("k.rom", "forever", origin, False)])

        with pytest.raises(SystemExit, match="relative to its source"):
            load_manifest(path)

    def test_says_origin_root_is_gone(self):
        with pytest.raises(SystemExit, match="origin_root is no longer used"):
            parse_manifest('origin_root = "~/Amiga"\n')

    def test_rejects_unknown_keys(self):
        with pytest.raises(SystemExit, match="unknown key path"):
            parse_manifest('[sources.a]\nenv = "A"\ndescription = "d"\npath = "/x"\n')

    def test_rejects_two_sources_sharing_a_variable(self):
        text = (
            '[sources.a]\nenv = "A"\ndescription = "d"\n[sources.b]\nenv = "A"\ndescription = "e"\n'
        )

        with pytest.raises(SystemExit, match="same environment variable"):
            parse_manifest(text)

    def test_with_nothing_in_it_is_empty(self):
        assert parse_manifest("").items == []


class TestMigrate:
    def test_copies_items_and_locks_them_with_their_source(self, manifest, env):
        migrate(manifest=manifest, environ=env)

        media = manifest.parent
        assert (media / "rom" / "kick.rom").read_bytes() == b"\x11\x14\x4e\xf9"
        lock = _lock(media)
        assert set(lock) == {"rom/kick.rom", "ndk"}
        assert lock["rom/kick.rom"]["source"] == "forever"
        assert lock["rom/kick.rom"]["origin"] == "kick.rom"
        assert verify(manifest)
        assert not list(media.rglob("*.partial"))

    def test_reads_the_source_folder_from_the_projects_env_file(self, manifest, origin):
        (manifest.parent.parent / ".env").write_text(f'FOREVER_DIR="{origin}"\n')

        migrate(manifest=manifest, environ={})

        assert verify(manifest)

    def test_a_real_variable_overrides_the_env_file(self, manifest, env):
        (manifest.parent.parent / ".env").write_text("FOREVER_DIR=/nowhere\n")

        migrate(manifest=manifest, environ=env)

        assert verify(manifest)

    def test_an_override_names_a_source_folder_for_one_run(self, manifest, origin):
        migrate({"forever": origin}, manifest=manifest, environ={})

        assert verify(manifest)

    def test_does_not_need_the_source_for_media_already_present(self, manifest, env):
        migrate(manifest=manifest, environ=env)

        migrate(manifest=manifest, environ={})

        assert verify(manifest)

    def test_refreshes_where_present_media_came_from_without_touching_checksums(
        self, manifest, env
    ):
        migrate(manifest=manifest, environ=env)
        lock_path = manifest.parent / "manifest.lock.json"
        old = _lock(manifest.parent)
        stale = {k: v | {"origin": "Old/Full/Path"} for k, v in old.items()}
        stale["ndk"].pop("source")
        lock_path.write_text(json.dumps(stale))

        migrate(manifest=manifest, environ={})

        assert _lock(manifest.parent) == old

    def test_names_the_variable_when_a_required_source_is_unset(self, manifest):
        with pytest.raises(SystemExit, match="FOREVER_DIR is not set") as error:
            migrate(manifest=manifest, environ={})

        assert ".env.example" in str(error.value)

    def test_names_the_variable_when_it_is_not_a_folder(self, manifest, tmp_path):
        with pytest.raises(SystemExit, match="which is not a folder"):
            migrate(manifest=manifest, environ={"FOREVER_DIR": str(tmp_path / "gone")})

    def test_skips_an_optional_item_whose_source_is_unset(self, tmp_path, env, capsys):
        items = [("rom/kick.rom", "forever", "kick.rom", False), ("m.pdf", "extra", "m.pdf", True)]
        manifest = _manifest(tmp_path / "media", items)

        migrate(manifest=manifest, environ=env)

        assert "skipped m.pdf (optional; EXTRA_DIR is not set" in capsys.readouterr().out
        assert set(_lock(manifest.parent)) == {"rom/kick.rom"}
        assert verify(manifest)

    def test_skips_an_optional_item_missing_from_its_source(self, tmp_path, env, capsys):
        items = [("gone.pdf", "forever", "gone.pdf", True)]
        manifest = _manifest(tmp_path / "media", items)

        migrate(manifest=manifest, environ=env)

        assert "not found in forever" in capsys.readouterr().out

    def test_refuses_an_origin_that_does_not_match_the_lock(self, manifest, origin, env):
        migrate(manifest=manifest, environ=env)
        kick = manifest.parent / "rom" / "kick.rom"
        kick.unlink()
        (origin / "kick.rom").write_bytes(b"not the same rom")

        with pytest.raises(SystemExit, match="does not match") as error:
            migrate(manifest=manifest, environ=env)

        message = str(error.value)
        assert "source forever (FOREVER_DIR)" in message
        assert "different edition or dump" in message
        assert not kick.exists()
        assert not list(manifest.parent.rglob("*.partial"))

    def test_an_interrupted_migrate_keeps_what_it_finished(self, tmp_path, env):
        items = [("rom/kick.rom", "forever", "kick.rom", False), ("g.adf", "forever", "g", False)]
        manifest = _manifest(tmp_path / "media", items)

        with pytest.raises(SystemExit, match="Missing in origin"):
            migrate(manifest=manifest, environ=env)

        assert set(_lock(manifest.parent)) == {"rom/kick.rom"}

    def test_replaces_a_directory_rather_than_merging_into_it(self, manifest, env):
        stale = manifest.parent / "ndk" / "include" / "left-over.h"
        stale.parent.mkdir(parents=True)
        stale.write_text("from an earlier copy")

        migrate(manifest=manifest, environ=env)

        assert not stale.exists()
        assert _lock(manifest.parent)["ndk"]["files"] == 1

    def test_drops_lock_entries_the_manifest_no_longer_lists(self, manifest, env):
        (manifest.parent / "manifest.lock.json").write_text(json.dumps({"retired.rom": {}}))

        migrate(manifest=manifest, environ=env)

        assert "retired.rom" not in _lock(manifest.parent)


def test_verify_reports_changed_media(manifest, env):
    migrate(manifest=manifest, environ=env)
    (manifest.parent / "ndk" / "include" / "exec.h").write_text("edited")

    assert not verify(manifest)


def test_verify_fails_on_required_media_never_copied(manifest):
    assert not verify(manifest)


class TestAdd:
    def test_appends_an_item_and_keeps_the_comments(self, manifest, origin, env):
        add("forever", "kick.rom", "rom/copy.rom", "mine", manifest=manifest, environ=env)

        text = manifest.read_text()
        assert text.startswith("# a comment to keep\n")
        assert load_manifest(manifest).items[-1] == Item(
            "rom/copy.rom", "forever", "kick.rom", "mine"
        )

    def test_makes_an_absolute_origin_under_the_source_relative(self, manifest, origin, env):
        item = add("forever", str(origin / "ndk"), "ndk2", "mine", True, manifest, env)

        assert item.origin == "ndk"
        assert item.optional

    def test_refuses_an_absolute_origin_outside_the_source(self, manifest, tmp_path, env):
        (tmp_path / "elsewhere.rom").write_bytes(b"x")

        with pytest.raises(SystemExit, match="is not inside"):
            add("forever", str(tmp_path / "elsewhere.rom"), "x.rom", "l", False, manifest, env)

    def test_refuses_an_origin_that_does_not_exist(self, manifest, env):
        with pytest.raises(SystemExit, match="Not found in forever"):
            add("forever", "nope.rom", "x.rom", "l", False, manifest, env)

    def test_refuses_an_unknown_source(self, manifest, env):
        with pytest.raises(SystemExit, match="No source named hyperion"):
            add("hyperion", "kick.rom", "x.rom", "l", False, manifest, env)

    def test_refuses_a_source_whose_folder_is_not_set(self, manifest):
        with pytest.raises(SystemExit, match="FOREVER_DIR must name"):
            add("forever", "kick.rom", "x.rom", "l", False, manifest, {})

    def test_refuses_a_duplicate_dest(self, manifest, env):
        with pytest.raises(SystemExit, match="already in the manifest"):
            add("forever", "kick.rom", "rom/kick.rom", "l", False, manifest, env)

    def test_refuses_a_dest_escaping_media(self, manifest, env):
        with pytest.raises(SystemExit, match="inside media"):
            add("forever", "kick.rom", "../kick.rom", "l", False, manifest, env)

    def test_refuses_an_empty_licence(self, manifest, env):
        with pytest.raises(SystemExit, match="licence"):
            add("forever", "kick.rom", "x.rom", " ", False, manifest, env)


class TestAddSource:
    def test_adds_the_table_after_the_last_source_and_documents_the_variable(self, manifest):
        add_source("hyperion", "HYPERION_DIR", "a Hyperion download", manifest)

        text = manifest.read_text()
        assert text.index("[sources.hyperion]") < text.index("[[item]]")
        assert load_manifest(manifest).sources["hyperion"].env == "HYPERION_DIR"
        example = (manifest.parent.parent / ".env.example").read_text()
        assert "\nFOREVER_DIR=\n" in example
        assert "# a Hyperion download\nHYPERION_DIR=\n" in example

    def test_appends_to_an_existing_env_example(self, manifest):
        example = manifest.parent.parent / ".env.example"
        example.write_text("# mine\nFOREVER_DIR=\n")

        add_source("hyperion", "HYPERION_DIR", "a Hyperion download", manifest)

        assert example.read_text().startswith("# mine\nFOREVER_DIR=\n")
        assert example.read_text().endswith("HYPERION_DIR=\n")

    def test_refuses_a_name_already_used(self, manifest):
        with pytest.raises(SystemExit, match="already has a source"):
            add_source("forever", "OTHER_DIR", "d", manifest)

    def test_refuses_a_variable_already_used(self, manifest):
        with pytest.raises(SystemExit, match="already uses FOREVER_DIR"):
            add_source("other", "FOREVER_DIR", "d", manifest)

    @pytest.mark.parametrize(("name", "env"), [("Bad Name", "OK_DIR"), ("ok", "lower")])
    def test_refuses_malformed_names(self, manifest, name, env):
        with pytest.raises(SystemExit):
            add_source(name, env, "d", manifest)


@pytest.mark.parametrize(
    ("dest", "existing", "message"),
    [("ndk/3.2", ["ndk"], "overlaps"), ("ndk", ["ndk/3.2"], "overlaps"), ("a", ["a"], "already")],
)
def test_a_new_dest_may_not_overlap_another(dest, existing, message):
    with pytest.raises(SystemExit, match=message):
        check_new_dest(dest, existing)


def test_a_dest_sharing_only_a_prefix_is_fine():
    assert check_new_dest("ndk2", ["ndk"]) == "ndk2"


def test_relative_origin_normalises_and_refuses_escapes(tmp_path):
    assert relative_origin("a/./b/../c.rom", tmp_path) == "a/c.rom"
    with pytest.raises(SystemExit):
        relative_origin("a/../../c.rom", tmp_path)


def test_a_new_item_escapes_quotes_and_backslashes():
    item = Item('d "q".rom', "s", "a\\b.rom", 'it\'s "mine"')
    text = with_item('[sources.s]\nenv = "S"\ndescription = "d"\n', item)

    assert parse_manifest(text).items == [item]


def test_the_first_source_goes_above_the_items_and_their_heading():
    text = (
        '# head\n\n# ---- ROMs\n[[item]]\ndest = "a"\nsource = "s"\norigin = "a"\nlicence = "l"\n'
    )

    updated = with_source(text, Source("s", "S", "d"))

    assert updated.index("# head") < updated.index("[sources.s]") < updated.index("# ---- ROMs")
    assert parse_manifest(updated).sources["s"] == Source("s", "S", "d")
