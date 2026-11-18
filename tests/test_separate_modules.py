"""有頁面的模組改用「互通」的 separate.py：在網頁面板裡按下時不開頁面、交給另一個程序（面板不會被卡住）。"""

import ast
import runpy
import subprocess
import sys
import types
from pathlib import Path

import pytest
from test_separate import SEPARATE, WEB, Info

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    home = tmp_path / "iPLoT"
    (home / "modules" / "工作坊").mkdir(parents=True)
    run_py = home / "modules" / "互通" / "run.py"
    run_py.parent.mkdir(parents=True)
    run_py.write_text("", encoding="utf-8")
    return home, home / "modules" / "工作坊", run_py


# ── 用它的模組：在面板裡按下時不開頁面、交給另一個程序 ──

PAGE_MODULES = {"工作坊": "run", "回報與討論": "run", "互通": "run"}


@pytest.mark.parametrize("name", PAGE_MODULES)
def test_page_modules_ask_separate_before_their_page(name):
    """run 裡第一個 app.page 之前，要先問過另開（_separate(app) 或 separate.here(app)），問了是 False 就 return。"""
    tree = ast.parse((ROOT / "modules" / name / "iplot.py").read_text(encoding="utf-8"))
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == PAGE_MODULES[name])
    calls = [n for n in ast.walk(run) if isinstance(n, ast.Call)]
    asked = [c.lineno for c in calls if ast.unparse(c.func) in ("_separate", "separate.here")]
    pages = [c.lineno for c in calls if ast.unparse(c.func) == "app.page"]
    assert asked and pages and min(asked) < min(pages)


def test_report_on_error_stays_in_the_panel():
    """「回報這個問題」拿的是面板上的那一個錯誤，不能交給別的程序：on_error 不問另開。"""
    tree = ast.parse((ROOT / "modules" / "回報與討論" / "iplot.py").read_text(encoding="utf-8"))
    on_error = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "on_error")
    assert "_separate" not in ast.unparse(on_error)


class WorkshopApp:
    def __init__(self, home, folder):
        self.home, self.module, self.logs, self.pages, self.rescans = home, Info(folder, "工作坊"), [], [], 0
        self.config = types.SimpleNamespace(workshop_url="https://example.invalid/index.json")

    def log(self, text):
        self.logs.append(text)

    def page(self, *args):
        self.pages.append(args)

    def rescan(self):
        self.rescans += 1


def run_workshop(app, monkeypatch, listing, popen=None):
    """照 runner 的樣子跑「工作坊」的 run：sys.path[0] 是它的資料夾、面板是網頁面板；listing 代替真的抓清單。"""
    folder = ROOT / "modules" / "工作坊"
    monkeypatch.syspath_prepend(str(folder))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.delitem(sys.modules, "workshop", raising=False)
    monkeypatch.setitem(sys.modules, "ui.web", WEB["ui.web"])
    if popen is not None:
        monkeypatch.setattr(subprocess, "Popen", popen)
    ns = runpy.run_path(str(folder / "iplot.py"))
    monkeypatch.setattr(sys.modules["workshop"], "read_listing", listing)
    try:
        ns["run"](app)
    finally:
        sys.modules.pop("workshop", None)


def test_workshop_in_the_web_panel_hands_off_without_fetching_or_opening_a_page(setup, monkeypatch):
    home, folder, run_py = setup
    (home / "modules" / "互通" / "separate.py").write_bytes(SEPARATE.read_bytes())
    app, launched = WorkshopApp(home, folder), []
    run_workshop(app, monkeypatch, lambda url: pytest.fail("在面板裡不該先抓清單"),
                 popen=lambda argv, **kw: launched.append(argv))
    assert [a[1:] for a in launched] == [[str(run_py), str(folder)]]
    assert app.pages == [] and app.logs == ["在另一個視窗打開「工作坊」"]


def test_workshop_without_interop_opens_its_page_here_as_before(setup, monkeypatch):
    home, folder, run_py = setup
    run_py.unlink()  # 沒有 separate.py、也沒有 run.py：舊的互通，或沒裝
    app = WorkshopApp(home, folder)
    run_workshop(app, monkeypatch, lambda url: ([], None))
    assert len(app.pages) == 1 and app.pages[0][0] == "工作坊" and app.rescans == 1
