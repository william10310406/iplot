from pathlib import Path

import pytest

from core import actions


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(actions.subprocess, "run", lambda argv, **kw: seen.append((argv, kw)))
    return seen


def test_open_argv(calls):
    actions.open(Path("/x/a.txt"))
    assert calls == [(["open", "/x/a.txt"], {"check": False})]


def test_edit_default_uses_open_t(calls):
    actions.edit(Path("/x/iplot.py"), None, 7)
    assert calls[0][0] == ["open", "-t", "/x/iplot.py"]


def test_edit_template_formats_file_and_line(calls):
    actions.edit(Path("/x/iplot.py"), ("code", "-g", "{file}:{line}"), 7)
    assert calls[0][0] == ["code", "-g", "/x/iplot.py:7"]


def test_edit_template_line_none_becomes_1(calls):
    actions.edit(Path("/x/iplot.py"), ("code", "-g", "{file}:{line}"))
    assert calls[0][0] == ["code", "-g", "/x/iplot.py:1"]


def test_reveal_argv(calls):
    actions.reveal(Path("/x/a"))
    assert calls[0][0] == ["open", "-R", "/x/a"]


def test_terminal_argv(calls):
    actions.terminal(Path("/x/a"))
    assert calls[0][0] == ["open", "-a", "Terminal", "/x/a"]


def test_trash_moves_and_suffixes(tmp_path):
    trash = tmp_path / "Trash"
    trash.mkdir()
    for _ in range(2):
        (tmp_path / "x").mkdir()
        dest = actions.trash(tmp_path / "x", trash)
    assert dest == trash / "x 2"
    assert sorted(p.name for p in trash.iterdir()) == ["x", "x 2"]
    assert not (tmp_path / "x").exists()


def test_no_string_commands():
    src = Path(actions.__file__).read_text(encoding="utf-8")
    assert "os.system" not in src and "shell=True" not in src


def test_edit_folder_falls_back_to_open(calls, tmp_path):
    actions.edit(tmp_path, None)
    actions.edit(tmp_path, ("code", "-g", "{file}:{line}"))
    assert [argv for argv, _ in calls] == [["open", str(tmp_path)]] * 2
