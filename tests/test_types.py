import dataclasses
from pathlib import Path

import pytest

from core.text import T
from core.types import DEFAULT_CONFIG, Group, ModuleInfo, Result


def test_moduleinfo_is_frozen():
    m = ModuleInfo("a", "a", "", Path("a"), Path("a/iplot.py"), Path("."), "here", True, False, False, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.name = "b"


def test_group_note_defaults_none():
    assert Group("這一層", "here", Path("."), ()).note is None


def test_result_has_output():
    assert Result(True, None, 0.0, "").output == ""


def test_default_config():
    assert DEFAULT_CONFIG.roots == ("modules", "..") and DEFAULT_CONFIG.history_keep == 20


def test_text_keys():
    for k in ["here", "parent", "empty_group", "done", "error_at_line", "missing_handler", "title"]:
        assert k in T
