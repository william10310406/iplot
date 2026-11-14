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


def test_meta_is_chinese_with_an_icon():
    m = read_meta(MODULE / "iplot.py")
    assert m.icon == "📐"
    assert m.description.startswith("Lean 實數遊戲") and "不用安裝" in m.description


def test_changelog_top_section_is_0_1_0_with_a_first_paragraph():
    text = (MODULE / "CHANGELOG.md").read_text(encoding="utf-8")
    text = text.replace("## [Unreleased]", "## [-]")  # 體驗打磨加的「未發佈」不算版本（tools/publish.py 的 latest() 也略過它）
    top = text[text.index("## [0"):]
    assert top.startswith("## [0.1.0] - 2026-11-10\n\n")
    first = top.split("\n\n")[1]
    assert "Lean 實數遊戲" in first and "需要網路" in first and "瀏覽器" in first


def test_press_says_what_it_is_then_opens_the_browser_once(lean, online, opened, tmp_path):
    app = FakeApp(tmp_path)
    lean.run(app)
    assert online == [lean.CHECK_URL]
    assert opened == [GAME]
    assert app.logs == [lean.INTRO, lean.OPENED]
    intro = app.logs[0]
    assert "需要網路" in intro and "不用安裝" in intro and "進度存在" in intro and "瀏覽器" in intro


def test_never_opens_a_page_of_its_own(lean, online, tmp_path):
    app = FakeApp(tmp_path)
    lean.run(app)
    assert app.pages == []
    assert not hasattr(lean, "Api") and not hasattr(lean, "page")


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
    app = FakeApp(tmp_path)
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


def test_module_has_no_page_and_loads_nothing_external(lean):
    source = (MODULE / "iplot.py").read_text(encoding="utf-8")
    assert "app.page" not in source and "<html" not in source
    assert re.findall(r"https?://[^\s\"'<>]+", source).count(GAME) == 1


@pytest.mark.parametrize("trouble, plain", [
    (urllib.error.URLError("nodename nor servname provided"), "沒有網路"),
    (TimeoutError("timed out"), "逾時"),
    (urllib.error.URLError(TimeoutError("timed out")), "逾時"),
    (urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None), "503"),
    (__import__("ssl").SSLCertVerificationError("certificate verify failed"), "憑證"),
    (urllib.error.URLError(__import__("ssl").SSLError("bad")), "憑證"),
    (ConnectionResetError(54, "Connection reset by peer"), "沒有網路"),
    (http.client.RemoteDisconnected("Remote end closed connection without response"), "沒有網路"),
])
def test_the_reason_is_plain_chinese_never_pythons_english(lean, monkeypatch, tmp_path, trouble, plain):
    """體驗 8e-01：「連不上 adam.math.hhu.de（…）」括號裡是中文原因。"""
    def boom(url, **k):
        raise trouble
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    app = FakeApp(tmp_path)
    lean.run(app)
    reason = app.logs[1].split("（", 1)[1].split("），", 1)[0]
    assert plain in reason and not re.search("[A-Za-z]{4,}", reason) and "Error" not in app.logs[1]
