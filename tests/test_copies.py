"""抄本要登記（D160 第 2 條，AGENTS.md）：tools/check_copies.py 找到的每一組逐字一樣的函式，都要在 tools/copies.json；
登記成 same 的那一組不准分家；已經不是抄本的登記要刪掉。"""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("iplot_check_copies", ROOT / "tools" / "check_copies.py")
copies = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copies)


@pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(), reason="要 git 才列得出檔案")
def test_every_copy_is_registered_and_kept_in_step():
    assert copies.problems() == []


def test_registry_entries_say_why():
    for entry in json.loads(copies.COPIES.read_text(encoding="utf-8")):
        assert entry["why"] and entry["why"] != "待補" and isinstance(entry["same"], bool) and len(entry["places"]) > 1, entry


def test_finds_copies_and_ignores_docstrings(tmp_path, monkeypatch):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text('def f(x):\n    """一。"""\n    y = x + 1\n    z = y * 2\n    return z\n', encoding="utf-8")
    b.write_text('def g(x):\n    """二，說明不一樣。"""\n    y = x + 1\n    z = y * 2\n    return z\n', encoding="utf-8")
    monkeypatch.setattr(copies, "ROOT", tmp_path)
    monkeypatch.setattr(copies, "tracked", lambda: [a, b])
    assert copies.groups(copies.bodies()) == [["a.py:f", "b.py:g"]]
