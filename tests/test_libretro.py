import pytest
from amiga_env.libretro import option_default


def test_an_option_defaults_to_its_first_value():
    assert option_default("Crop Overscan; disabled|enabled|small") == "disabled"


def test_a_path_value_is_kept_whole():
    assert option_default("Kickstart ROM; auto|kick.rom") == "auto"


def test_a_description_without_values_is_refused():
    with pytest.raises(ValueError, match="not a libretro option"):
        option_default("Crop Overscan")
