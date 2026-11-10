"""工作坊模組「Lean」（modules/Lean）：按下去打開 Lean 實數遊戲。
不連網（urlopen 換成替身）、不開瀏覽器（webbrowser.open 換成替身）。"""

import http.client
import importlib.util
import re
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import pytest
from conftest import FakeApp

from core.meta import read_meta

MODULE = Path(__file__).resolve().parents[1] / "modules" / "Lean"
GAME = "https://adam.math.hhu.de/#/g/william10310406/reals-game"


@pytest.fixture
def lean(monkeypatch):
    """把 modules/Lean/iplot.py 當一般模組載入（不寫 .pyc）。"""
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    spec = importlib.util.spec_from_file_location("lean_iplot", MODULE / "iplot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        return b"<"


@pytest.fixture
def online(monkeypatch):
    """連得上：urlopen 回一個假的回應，記下開過的網址。"""
    urls = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, **k: urls.append(url) or _Response())
    return urls


@pytest.fixture(autouse=True)
def opened(monkeypatch):
    """不開真的瀏覽器：記下網址、回 True。"""
    calls = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: calls.append(url) or True)
    return calls


class PageApp(FakeApp):
    """網頁面板的替身：頁面「開出來」時，那一頁的 JS 會叫 api.shown()。"""

    def page(self, title, html, api=None):
        super().page(title, html, api)
        api.shown()


def test_meta_is_chinese_with_an_icon():
    m = read_meta(MODULE / "iplot.py")
    assert m.icon == "📐"
    assert m.description.startswith("Lean 實數遊戲") and "不用安裝" in m.description


def test_changelog_top_section_is_0_1_0_with_a_first_paragraph():
    text = (MODULE / "CHANGELOG.md").read_text(encoding="utf-8")
    top = text[text.index("## ["):]
    assert top.startswith("## [0.1.0] - 2026-11-10\n\n")
    first = top.split("\n\n")[1]
    assert "Lean 實數遊戲" in first and "需要網路" in first


def test_web_panel_opens_the_page_and_does_not_open_a_browser(lean, online, opened, tmp_path):
    app = PageApp(tmp_path)
    lean.run(app)
    assert online == [lean.CHECK_URL]
    [(title, html, api)] = app.pages
    assert title == "Lean 實數遊戲" and isinstance(api, lean.Api)
    assert opened == []
    assert app.logs[0] == lean.INTRO and "需要網路" in app.logs[0] and "不用安裝" in app.logs[0]
    assert app.logs[-1] == lean.CLOSED


def test_panel_without_pages_falls_back_to_the_browser(lean, online, opened, tmp_path):
    app = FakeApp(tmp_path)  # tkinter 面板：page 只記一行就回來，那一頁的 JS 從沒跑過
    lean.run(app)
    assert len(app.pages) == 1
    assert opened == [GAME]
    assert app.logs == [lean.INTRO, lean.NO_PAGE, lean.OPENED]


@pytest.mark.parametrize("trouble", [
    urllib.error.URLError("nodename nor servname provided"),
    TimeoutError("timed out"),
    ConnectionResetError(54, "Connection reset by peer"),
    http.client.RemoteDisconnected("Remote end closed connection without response"),
])
def test_unreachable_server_is_one_sentence_and_opens_nothing(lean, opened, monkeypatch, tmp_path, trouble):
    def boom(url, **k):
        raise trouble
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    app = PageApp(tmp_path)
    lean.run(app)  # 不丟例外
    assert app.pages == [] and opened == []
    assert app.logs[0] == lean.INTRO
    assert len(app.logs) == 2 and app.logs[1].startswith("連不上 adam.math.hhu.de（") and "再按一次" in app.logs[1]
    assert "Traceback" not in app.logs[1]


def test_browser_that_cannot_open_gives_the_url_to_copy(lean, monkeypatch):
    def fail(url, *a, **k):
        raise webbrowser.Error("could not locate runnable browser")
    monkeypatch.setattr(webbrowser, "open", fail)
    assert lean.open_browser() == lean.NOT_OPENED.format(url=GAME)
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: False)
    assert GAME in lean.open_browser()


def test_page_button_opens_the_browser_and_returns_a_sentence(lean, opened):
    api = lean.Api()
    assert api.browser() == lean.OPENED and opened == [GAME]


def test_api_exposes_only_shown_and_browser_and_takes_no_app(lean):
    api = lean.Api()
    public = sorted(n for n in dir(api) if not n.startswith("_"))
    assert public == ["browser", "shown"]
    assert all(n.startswith("_") for n in vars(api))


def test_page_loads_no_external_resources_and_navigates_only_to_the_game(lean):
    html = lean.page()
    assert re.findall(r"https?://[^\s\"'<>]+", html) == [GAME]
    assert not re.search(r"""(src|href)\s*=\s*["']?https?:""", html, re.I)
    assert "<link" not in html and "@import" not in html
    assert f"const GAME = \"{GAME}\";" in html


def test_page_without_pywebview_api_is_reported_by_flag_only(lean):
    api = lean.Api()
    assert api._shown is False
    api.shown()
    assert api._shown is True
