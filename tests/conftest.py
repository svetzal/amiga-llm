"""Tests run against this repository as the project, wherever pytest starts.

A test that needs another project sets AMIGA_ENV_ROOT itself, or passes paths.
"""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _this_repository_is_the_project(monkeypatch):
    monkeypatch.setenv("AMIGA_ENV_ROOT", str(REPO))
