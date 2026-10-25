"""隨附模組「回報與討論」（modules/回報與討論）：遮蔽、內文、網址、截斷、預覽頁與面板的流程（M8、D110–D116）。
不開瀏覽器（autouse 的替身）、不連網、不寫進 repo（跑模組的流程先複製到 tmp）；遮蔽的表用假的 Ctx，只有端對端的兩個用這台機器。"""

import importlib
import sys
import types
import webbrowser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules" / "回報與討論"
NAMES = ("forum", "redact", "report", "iplot")


@pytest.fixture
def load(monkeypatch):
    """load("forum")：把 modules/回報與討論/forum.py 當一般模組 import（不寫 .pyc）——跟 runner 一樣走 sys.path；
    結束時從 sys.modules 拿掉。"""
    monkeypatch.syspath_prepend(str(MODULE))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    for n in NAMES:
        monkeypatch.delitem(sys.modules, n, raising=False)
    yield importlib.import_module
    for n in NAMES:
        sys.modules.pop(n, None)


@pytest.fixture(autouse=True)
def opened(monkeypatch):
    """每一個測試都不開真的瀏覽器：webbrowser.open 換成記下網址、回 True 的替身；回那一串網址。
    有 tkinter 的話，tkinter 自己的那個 Tk 先當作沒有：tkinter 的流程不碰真的剪貼簿，不靠測試的順序。"""
    calls = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: calls.append(url) or True)
    try:
        import tkinter
    except ImportError:  # 沒有 tkinter 的 Python：tkinter 的流程本來就跑不到
        return calls
    monkeypatch.setattr(tkinter, "_default_root", None, raising=False)
    return calls


@pytest.fixture
def web(monkeypatch):
    """網頁面板的樣子：只有 ui.web。"""
    monkeypatch.delitem(sys.modules, "ui.tk", raising=False)
    monkeypatch.setitem(sys.modules, "ui.web", types.ModuleType("ui.web"))


@pytest.fixture
def tk(monkeypatch):
    """後備的 tkinter 面板的樣子：網頁面板開不起來之後 ui.web 還在，兩個都在。"""
    monkeypatch.setitem(sys.modules, "ui.tk", types.ModuleType("ui.tk"))
    monkeypatch.setitem(sys.modules, "ui.web", types.ModuleType("ui.web"))


def test_helper_names_are_not_stdlib():
    assert not {"forum", "redact", "report"} & set(sys.stdlib_module_names)


def test_forum_points_at_this_repo(load):
    forum = load("forum")
    assert forum.REPO == "william10310406/iplot"
    assert forum.FORUM == "https://github.com/william10310406/iplot/discussions"


def test_forum_has_four_categories(load):
    # 整份測試只有這裡寫死 slug（Task 0 Step 1 照實測改的就是這一行）；其他測試一律從 forum.CATEGORIES 查
    forum = load("forum")
    assert forum.CATEGORIES == {"BUG": "問題回報", "IDEA": "功能建議", "QA": "問答", "NEWS": "公告"}
    assert not any("%" in slug for slug in forum.CATEGORIES.values())  # 存解開 %XX 之後的樣子


def test_report_folder_is_ignored_by_git():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "modules/回報與討論/回報/" in lines
