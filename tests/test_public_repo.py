"""The repository is public. Licensed media, and .env, must never be tracked.

The rules are `amiga-env guard`'s (see amiga_env/guard.py); this test runs
them on this repository so `make test` enforces them. Never weaken them to
make a commit pass.
"""

import pytest
from amiga_env.guard import check
from conftest import REPO


def test_git_tracks_no_licensed_media_and_no_env_file():
    offences = check(REPO)
    if offences is None:
        pytest.skip("not a git checkout")

    assert offences == []
