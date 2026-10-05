"""有顯示器才跑：真的建 Panel，按按鈕，看訊息區。"""

import dataclasses
import gc
import os
import subprocess
import sys
import types
from pathlib import Path

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
from core.types import DEFAULT_CONFIG, ErrorInfo  # noqa: E402
from ui.tk import Panel  # noqa: E402


def close(root):
    """先跑一次事件迴圈再 destroy，理由同上面的 _probe。"""
    root.update()
    root.destroy()


@pytest.fixture
def panel():
    p = Panel("9.9", safe=False)
    yield p
    close(p.root)


def started(home, panel, config=DEFAULT_CONFIG):
    core = Core(home, config, panel)
    panel.attach(core)
    core.rescan()
    panel.root.update()
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
    panel.root.update()
    assert "第 3 行" in messages(panel)
    assert button(panel.messages, T["open_file"]).winfo_ismapped()


def test_panel_title_safe_mode():
    p = Panel("9.9", safe=True)
    try:
        assert p.root.title() == "iPLoT v9.9（安全模式）"
    finally:
        close(p.root)


def test_dnd_skipped_in_safe_mode_and_failure_falls_back(monkeypatch):
    half_built = []

    class BrokenDnDTk(tkinter.Tk):
        def __init__(self):
            super().__init__()
            half_built.append(self)
            raise RuntimeError("Unable to load tkdnd library.")

    monkeypatch.setitem(sys.modules, "tkinterdnd2", types.SimpleNamespace(
        TkinterDnD=types.SimpleNamespace(Tk=BrokenDnDTk)))
    close(Panel("9.9", safe=True).root)
    assert half_built == []  # 安全模式連 import 都不做
    p = Panel("9.9", safe=False)
    try:
        assert len(half_built) == 1 and p.root.winfo_exists()
        assert half_built[0].winfo_exists()  # 建到一半的視窗不能被 destroy（見檔頭）
    finally:
        for root in {p.root, half_built[0]}:
            close(root)


def test_unreadable_root_has_note_and_no_plus(home, panel):
    started(home, panel, dataclasses.replace(DEFAULT_CONFIG, roots=("modules", "/nonexistent")))
    labels = [w.cget("text") for w in widgets(panel.body, tkinter.Label)]
    assert T["empty_group"] in labels and any("/nonexistent" in t for t in labels)
    assert [b.cget("text") for b in widgets(panel.body, tkinter.Button)].count("＋") == 1


def test_report_keeps_plain_sentence_at_the_end(home, panel):
    make_module(home / "modules", "A", "def run(app):\n    x = 1\n    1/0\n")
    started(home, panel)
    button(panel.body, "A").invoke()
    panel.root.update()
    tail = panel.messages.get("end-3l", "end")  # see("end") 之後看得到的是最後幾行
    assert "模組『A』第 3 行出錯" in tail
    assert "Traceback" not in tail


def test_enter_child_breadcrumb_and_warning_mark(home, panel):
    make_module(make_module(home / "modules", "A"), "C")
    make_module(home / "modules", "Bad", "def run(app)\n    pass\n")
    started(home, panel)
    assert button(panel.body, "⚠ Bad")
    button(panel.body, "▸").invoke()
    panel.root.update()
    assert [b.cget("text") for b in widgets(panel.crumbs, tkinter.Button)] == ["iPLoT", "A"]
    assert button(panel.body, "C")
    button(panel.crumbs, "iPLoT").invoke()
    panel.root.update()
    assert [b.cget("text") for b in widgets(panel.crumbs, tkinter.Button)] == ["iPLoT"]
    assert button(panel.body, "A") and button(panel.body, "⚠ Bad")


def test_open_file_button_uses_core_action(home, panel, monkeypatch):
    started(home, panel)
    seen = []
    monkeypatch.setattr(panel.core, "action", lambda name, *a: seen.append((name, *a)))
    panel.report(ErrorInfo("NameError", "x", Path("/m/iplot.py"), 7, "", "module", "m"))
    [opener] = [panel.messages.nametowidget(n) for n in panel.messages.window_names()]
    opener.invoke()
    assert seen == [("edit", Path("/m/iplot.py"), panel.core.config.editor, 7)]


def test_right_click_menu_uses_core_action(home, panel, monkeypatch):
    make_module(home / "modules", "A")
    core = started(home, panel)
    seen = []
    monkeypatch.setattr(core, "action", lambda name, *a: seen.append((name, *a)))
    [menu] = widgets(button(panel.body, "A"), tkinter.Menu)
    assert [menu.entrycget(i, "label") for i in range(3)] == ["打開程式碼", "在資料夾中顯示", "在終端機打開"]
    for i in range(3):
        menu.invoke(i)
    [info] = core.scope.groups[0].modules
    assert seen == [("edit", info.file, None, None), ("reveal", info.folder), ("terminal", info.folder)]


def row_menu(panel, text):
    """某一列按鈕的右鍵選單，和它每一項的標籤。"""
    [menu] = widgets(button(panel.body, text), tkinter.Menu)
    return menu, [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]


def lone_module(home, panel, monkeypatch, answer=None):
    """模組 A（沒有子模組）。會碰到外面的全部換成只記進 seen：core.action、啟動外部程式（Popen、execv）；ask 回固定答案。
    記錄而不是丟例外：Tk 回呼裡丟的例外會被 tkinter 吞掉，測試不會紅；seen 多一筆，比對 seen 的測試才會紅。"""
    seen = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: seen.append(("Popen", *a)))
    monkeypatch.setattr(os, "execv", lambda *a: seen.append(("execv", *a)))
    make_module(home / "modules", "A")
    core = started(home, panel)
    monkeypatch.setattr(core, "action", lambda name, *a: seen.append((name, *a)))
    monkeypatch.setattr(panel, "ask", lambda prompt, default="": answer)
    return core, seen


def add_child(panel, text):
    """按某一列右鍵選單的第四項。先確認它在：索引超出範圍時 Tk 可能改按最後一項（在終端機打開）。"""
    menu, labels = row_menu(panel, text)
    assert labels[3:] == ["在這裡新增下一層模組…"]
    menu.invoke(3)
    panel.root.update()


def test_right_click_menu_has_add_child(home, panel, monkeypatch):
    lone_module(home, panel, monkeypatch)
    _, labels = row_menu(panel, "A")
    assert labels == ["打開程式碼", "在資料夾中顯示", "在終端機打開", "在這裡新增下一層模組…"]
    assert labels[3] == T["menu_add_child"]


def test_add_child_creates_under_module_and_shows_arrow(home, panel, monkeypatch):
    core, seen = lone_module(home, panel, monkeypatch, answer="子")
    assert "▸" not in [b.cget("text") for b in widgets(panel.body, tkinter.Button)]
    add_child(panel, "A")
    child = home / "modules" / "A" / "子" / "iplot.py"
    assert child.is_file()
    assert seen == [("edit", child, core.config.editor, None)]  # 建好照舊交給編輯器
    assert row_menu(panel, "A")[1][3:] == [T["menu_add_child"]]  # 有了子模組，這一項還在
    button(panel.body, "▸").invoke()
    panel.root.update()
    assert [b.cget("text") for b in widgets(panel.crumbs, tkinter.Button)] == ["iPLoT", "A"]
    assert button(panel.body, "子")


def test_add_child_bad_name_does_not_create(home, panel, monkeypatch):
    _, seen = lone_module(home, panel, monkeypatch, answer="a/b")
    add_child(panel, "A")
    assert [p.name for p in (home / "modules" / "A").rglob("*")] == ["iplot.py"]
    assert T["bad_name"] in messages(panel)
    assert seen == []


def test_confirm_uses_messagebox(panel, monkeypatch):
    seen = []
    monkeypatch.setattr("tkinter.messagebox.askokcancel",
                        lambda title, prompt, **kw: seen.append((title, prompt, kw)) or False)
    assert panel.confirm("q") is False
    assert seen == [("iPLoT v9.9", "q", {"parent": panel.root})]


def test_attach_sends_callback_errors_to_core(home, panel):
    core = started(home, panel)
    assert panel.root.report_callback_exception == core.report_internal


def test_panel_has_no_window_attribute(panel):
    assert not hasattr(panel, "window") and panel.root.winfo_exists()


def test_run_tk_writes_note_then_config_error(home, monkeypatch):
    """main.run_tk：後備面板先把「為什麼是這個面板」寫進訊息區，再回報 config.py 的錯。"""
    from test_main import load_main

    made = []
    monkeypatch.setattr(Panel, "mainloop", lambda self: made.append(self))
    error = ErrorInfo("SyntaxError", "x", home / "config.py", 1, "", "config", None)
    load_main().run_tk(home, DEFAULT_CONFIG, error, True, note="先說原因")
    [p] = made
    try:
        text = messages(p)
        assert text.index("先說原因") < text.index(T["config_error"].format(message="x"))
        assert p.root.title().endswith(T["safe_mode"]) and p.core.safe
    finally:
        close(p.root)
        del made[:], p
        gc.collect()  # 面板有循環參照：在這條執行緒收掉，不要留到別的測試的工作執行緒才收（Tcl 會抱怨）


def test_page_logs_unsupported(home, panel):
    """安全模式的 tk 面板沒有頁面：page 在訊息區記一行就回來，不開視窗、不丟例外。"""
    started(home, panel)
    assert panel.page("工作坊", "<p>hi</p>", object()) is None
    assert T["page_unsupported"] in messages(panel)
