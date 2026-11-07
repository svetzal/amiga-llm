from amiga_env.home import merge_conf, prepare, render_conf, settings_dir

OWNED = "rom_path=/project/media/rom/\nbase_content_path=/project/runs/home/Amiberry/\n"


def test_merge_into_nothing_is_the_owned_settings():
    assert merge_conf("", OWNED) == OWNED


def test_merge_replaces_owned_keys_in_place_and_keeps_amiberrys_own():
    saved = "gfx_width=720\nrom_path=/old/rom/\nsound_output=normal\n"

    merged = merge_conf(saved, OWNED)

    assert merged == (
        "gfx_width=720\n"
        "rom_path=/project/media/rom/\n"
        "sound_output=normal\n"
        "base_content_path=/project/runs/home/Amiberry/\n"
    )


def test_merge_drops_repeats_of_an_owned_key():
    saved = "rom_path=/old/rom/\nrom_path=/older/rom/\n"

    assert merge_conf(saved, OWNED).count("rom_path=") == 1


def test_merge_is_stable():
    once = merge_conf("gfx_width=720\n", OWNED)

    assert merge_conf(once, OWNED) == once


def test_prepare_updates_a_stale_conf(tmp_path):
    conf = settings_dir(tmp_path) / "amiberry.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("rom_path=/Users/someone/OneDrive/rom/\ngfx_width=720\n")

    prepare(tmp_path)

    text = conf.read_text()
    assert "OneDrive" not in text
    assert "gfx_width=720" in text
    assert all(line in text.splitlines() for line in render_conf(tmp_path).splitlines())
