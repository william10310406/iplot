"""有顯示器才跑：真的建 Panel，按按鈕，看訊息區。"""

import dataclasses
import sys
import types

import pytest

tkinter = pytest.importorskip("tkinter")
try:
    _probe = tkinter.Tk()
    _probe.update()  # macOS 的 Tk 9.0：沒跑過事件迴圈就 destroy 的視窗，會讓之後的事件迴圈當掉（SIGTRAP）
    _probe.destroy()
except tkinter.TclError:
    pytest.skip("沒有顯示器", allow_module_level=True)

from conftest import make_module  # noqa: E402

from core.core import Core  # noqa: E402
from core.text import T  # noqa: E402
from core.types import DEFAULT_CONFIG  # noqa: E402
from core.ui import Panel  # noqa: E402


def close(root):
    """先跑一次事件迴圈再 destroy，理由同上面的 _probe。"""
    root.update()
    root.destroy()


@pytest.fixture
def panel():
    p = Panel("9.9", safe=False)
    yield p
    close(p.window)


def started(home, panel, config=DEFAULT_CONFIG):
    core = Core(home, config, panel)
    panel.attach(core)
    core.rescan()
    panel.window.update()
    return core


def widgets(parent, kind):
    for w in parent.winfo_children():
        if isinstance(w, kind):
            yield w
        yield from widgets(w, kind)


def button(parent, text):
    return next(b for b in widgets(parent, tkinter.Button) if b.cget("text") == text)


def messages(panel):
    return panel.messages.get("1.0", "end")


def test_panel_shows_buttons_and_runs(home, panel):
    make_module(home / "modules", "A", "def run(app):\n    print('hi')\n")
    started(home, panel)
    b = button(panel.body, "A")
    assert b.cget("fg") == "blue"
    b.invoke()
    assert "hi" in messages(panel) and "完成（" in messages(panel)


def test_panel_reports_error_with_open_button(home, panel):
    make_module(home / "modules", "A", "def run(app):\n    x = 1\n    1/0\n")
    started(home, panel)
    button(panel.body, "A").invoke()
    panel.window.update()
    assert "第 3 行" in messages(panel)
    assert button(panel.messages, T["open_file"]).winfo_ismapped()


def test_panel_title_safe_mode():
    p = Panel("9.9", safe=True)
    try:
        assert p.window.title() == "iPLoT v9.9（安全模式）"
    finally:
        close(p.window)


def test_dnd_skipped_in_safe_mode_and_failure_falls_back(monkeypatch):
    half_built = []

    class BrokenDnDTk(tkinter.Tk):
        def __init__(self):
            super().__init__()
            half_built.append(self)
            raise RuntimeError("Unable to load tkdnd library.")

    monkeypatch.setitem(sys.modules, "tkinterdnd2", types.SimpleNamespace(
        TkinterDnD=types.SimpleNamespace(Tk=BrokenDnDTk)))
    close(Panel("9.9", safe=True).window)
    assert half_built == []  # 安全模式連 import 都不做
    p = Panel("9.9", safe=False)
    try:
        assert len(half_built) == 1 and p.window.winfo_exists()
        assert half_built[0].winfo_exists()  # 建到一半的視窗不能被 destroy（見檔頭）
    finally:
        for root in {p.window, half_built[0]}:
            close(root)


def test_unreadable_root_has_note_and_no_plus(home, panel):
    started(home, panel, dataclasses.replace(DEFAULT_CONFIG, roots=("modules", "/nonexistent")))
    labels = [w.cget("text") for w in widgets(panel.body, tkinter.Label)]
    assert T["empty_group"] in labels and any("/nonexistent" in t for t in labels)
    assert [b.cget("text") for b in widgets(panel.body, tkinter.Button)].count("＋") == 1
