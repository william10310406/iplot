"""模組導覽列（D153、D159、D161）：「導覽列」模組（提供 page.top）算要列的格子、它的 nav.js 畫那一排；
「頁面」模組（提供 app.page，在模組自己的程序裡開視窗）問它、掛上載入後的注入與 _iplot_nav，按了一格就 app.start 那個模組。
這裡的「導覽列」是一份拷貝，放在 iPLoT 的上一層（ROOTS 的 ".."）：面板找得到它，但它不是 modules/ 裡那些模組的同一層。
Python 這一頭用假的 webview；JS 那一頭用 node 跑一個假的 DOM（沒有 node 就跳過），畫得對不對在 Mac 上真的看一次（人工驗收）。"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import FakeView, FakeWebview, make_module

from core.core import Core
from core.scan import module_info
from core.types import DEFAULT_CONFIG

NAV = Path(__file__).resolve().parents[1] / "modules" / "導覽列"
SOURCE = (NAV / "nav.js").read_text(encoding="utf-8")
PANEL = {"k": "panel", "t": "主控面板", "i": "", "d": ""}
_spec = importlib.util.spec_from_file_location("iplot_page_module", NAV.parent / "頁面" / "iplot.py")
PAGE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(PAGE)


@pytest.fixture(autouse=True)
def provider(home):
    shutil.copytree(NAV, home.parent / "導覽列")


def tree(home):
    """課程（有說明）底下兩個子模組：HK1（有圖示、底下還有 G）與 HK2。"""
    top = make_module(home / "modules", "課程", '"""作業"""\nTITLE = "課程作業"\n')
    make_module(top, "HK2", 'TITLE = "第二份"\n')
    hk1 = make_module(top, "HK1", '"""說明一"""\nICON = "📄"\nTITLE = "第一份"\n')
    make_module(hk1, "G")
    return top


def info_of(home, *names):
    root = (home / "modules").resolve()
    folder = root.joinpath(*names)
    level = "here" if len(names) == 1 else "child"
    return module_info(folder, root, level)


def bar_for(home, *names):
    """導覽列給 names 那個模組的一排：(格子, 目標的名字)。"""
    got = Core(home, DEFAULT_CONFIG, FakeView()).call("page.top", info_of(home, *names))
    return got["cells"], [t and t.name for t in got["targets"]]


class StubApp:
    """頁面模組拿到的 app：call 交給真的核心（找得到導覽列），start 只記下來。"""

    def __init__(self, home):
        self.core, self.started, self.logs = Core(home, DEFAULT_CONFIG, FakeView()), [], []

    def call(self, role, *args):
        return self.core.call(role, *args)

    def start(self, info):
        self.started.append(info)

    def log(self, text):
        self.logs.append(text)


def open_page(monkeypatch, home, owner, during=lambda window: None, api=None):
    """用假的 webview 開一頁；during(視窗) 在視窗開著的期間做（按格子、觸發 loaded）。回 (視窗, app)。"""
    fake = FakeWebview()
    fake.start = lambda: during(fake.windows[0])
    monkeypatch.setitem(sys.modules, "webview", fake)
    app = StubApp(home)
    PAGE.page(app, "頁", "<p>hi</p>", api, owner)
    return fake.windows[0], app


def test_cells_for_a_top_level_module_are_the_panel_then_its_children(home):
    tree(home)
    cells, targets = bar_for(home, "課程")
    assert cells == [PANEL, {"k": "child", "t": "第一份", "i": "📄", "d": "說明一"},
                     {"k": "child", "t": "第二份", "i": "", "d": ""}]
    assert targets == [None, "HK1", "HK2"]


def test_cells_for_a_child_add_the_parent_in_the_middle(home):
    tree(home)
    cells, targets = bar_for(home, "課程", "HK1")
    assert cells == [PANEL, {"k": "parent", "t": "↑ 課程作業", "i": "", "d": "作業"},
                     {"k": "sibling", "t": "第二份", "i": "", "d": ""}, {"k": "child", "t": "G", "i": "", "d": ""}]
    assert targets == [None, "課程", "HK2", "G"]


def test_a_top_level_module_lists_the_other_top_level_modules_of_its_folder(home):
    """Discussion #9：最上層的模組沒有上一層、多半也沒有下一層，以前那一排只剩主控面板；現在有同一層。"""
    tree(home)
    make_module(home / "modules", "行事曆", 'ICON = "📅"\n')
    assert bar_for(home, "行事曆")[0] == [PANEL, {"k": "sibling", "t": "課程作業", "i": "", "d": "作業"}]


def test_a_module_with_no_parent_and_no_children_only_has_the_panel_cell(home):
    make_module(home / "modules", "孤")
    assert bar_for(home, "孤") == ([PANEL], [None])


def test_without_a_provider_the_page_opens_with_no_bar(home, monkeypatch):
    shutil.rmtree(home.parent / "導覽列")
    tree(home)
    window, app = open_page(monkeypatch, home, info_of(home, "課程"), lambda w: w.fire("loaded"))
    assert window.exposed == {} and window.js == [] and app.started == []


def test_a_page_with_no_owner_has_no_bar(home, monkeypatch):
    tree(home)
    window, _ = open_page(monkeypatch, home, None)
    assert window.exposed == {}


def test_names_go_in_as_data_never_markup(home, monkeypatch):
    make_module(home / "modules", "孤", 'TITLE = "<b>x</b>"\n')
    make_module(home / "modules" / "孤", "子", 'TITLE = "</script>\\"\'"\n')
    window, _ = open_page(monkeypatch, home, info_of(home, "孤"), lambda w: w.fire("loaded"))
    [script] = window.js
    assert json.loads(script.removeprefix(f"({SOURCE})(").removesuffix(")"))[1]["t"] == "</script>\"'"


def test_the_bar_is_injected_after_the_page_loads_and_again_after_every_load(home, monkeypatch):
    tree(home)
    cells, _ = bar_for(home, "課程")
    window, _ = open_page(monkeypatch, home, info_of(home, "課程"), lambda w: (w.fire("loaded"), w.fire("loaded")))
    assert window.js == [f"({SOURCE})({json.dumps(cells)})"] * 2


def test_iplot_nav_is_exposed_under_that_exact_name_and_the_module_api_is_untouched(home, monkeypatch):
    class Api:
        def hi(self):
            return 1

    tree(home)
    window, _ = open_page(monkeypatch, home, info_of(home, "課程"), api=Api())
    assert list(window.exposed) == ["_iplot_nav"]  # 底線開頭：pywebview 攤開模組的 api 時略過，撞不到
    assert [n for n in dir(window.kw["js_api"]) if not n.startswith("_")] == ["hi"]


@pytest.mark.parametrize("bad", ["1", 1.0, True, None, -1, 3, 99, [1], {"i": 1}])
def test_iplot_nav_only_accepts_an_index_on_the_bar(home, monkeypatch, bad):
    tree(home)
    window, app = open_page(monkeypatch, home, info_of(home, "課程"), lambda w: w.exposed["_iplot_nav"](bad))
    assert not window.destroyed and app.started == []


def test_choosing_closes_the_page_and_starts_that_module_keeping_the_first_choice(home, monkeypatch):
    tree(home)

    def choose(window):
        window.exposed["_iplot_nav"](2)
        window.exposed["_iplot_nav"](1)

    window, app = open_page(monkeypatch, home, info_of(home, "課程"), choose)
    assert window.destroyed and [i.name for i in app.started] == ["HK2"]  # 另開程序跑，不等它（D161）


def test_choosing_the_panel_only_closes_the_page(home, monkeypatch):
    tree(home)
    window, app = open_page(monkeypatch, home, info_of(home, "課程"), lambda w: w.exposed["_iplot_nav"](0))
    assert window.destroyed and app.started == []


def test_closing_without_choosing_starts_nothing(home, monkeypatch):
    tree(home)
    _, app = open_page(monkeypatch, home, info_of(home, "課程"))
    assert app.started == []


def test_without_pywebview_it_says_so_and_returns(home, monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)  # import webview 丟 ImportError
    app = StubApp(home)
    PAGE.page(app, "頁", "<p>hi</p>", None, None)
    assert app.logs and "開不了頁面視窗" in app.logs[0]


# ── nav.js：用 node 跑一個假的 DOM ──

NODE = shutil.which("node")
HARNESS = r"""
const fs = require("fs");
const make = (tag) => ({tag, style: {}, children: [], on: {}, textContent: "",
  append(...c) { this.children.push(...c); }, prepend(...c) { this.children.unshift(...c); },
  addEventListener(t, f) { this.on[t] = f; }, attachShadow(o) { this.mode = o.mode; return (this.shadow = make("#shadow")); },
  set innerHTML(v) { throw new Error("innerHTML"); }});
const run = (cells, meta, twice) => {
  const body = make("body"), calls = [];
  global.document = {body, createElement: make,
    querySelector: (s) => s.startsWith("meta") ? (meta && s === 'meta[name="iplot-nav"][content="off"]' ? {} : null) : body.children.find((c) => c.tag === "iplot-nav") || null};
  global.window = {pywebview: {api: {_iplot_nav: (i) => calls.push(i)}}};
  const fn = eval(fs.readFileSync(process.argv[1], "utf8"));
  fn(cells);
  if (twice) fn(cells);
  const bar = body.children.find((c) => c.tag === "iplot-nav");
  const walk = (n) => [n, ...n.children.flatMap(walk)];
  const buttons = bar ? walk(bar.shadow).filter((n) => n.on.click) : [];
  buttons.forEach((b) => b.on.click());
  const seps = bar ? walk(bar.shadow).filter((n) => n.tag === "i").length : 0;
  return {count: body.children.length, mode: bar && bar.mode, style: bar && bar.style.cssText, seps,
          texts: buttons.map((b) => b.textContent), titles: buttons.map((b) => b.title), calls};
};
const cells = JSON.parse(process.argv[2]);
console.log(JSON.stringify({plain: run(cells, false, false), off: run(cells, true, false), twice: run(cells, false, true),
  separators: run(cells, false, false).seps, without_panel_separators: run(cells.slice(1), false, false).seps,
  empty: run([], false, false)}));
"""


@pytest.mark.skipif(NODE is None, reason="沒有 node")
def test_nav_js_draws_one_closed_shadow_bar_with_text_only_and_calls_the_index(home):
    cells = [PANEL, {"k": "parent", "t": "↑ 上", "i": "", "d": "說明"}, {"k": "child", "t": "<b>x</b>", "i": "📄", "d": ""}]
    out = subprocess.run([NODE, "-e", HARNESS, str(NAV / "nav.js"), json.dumps(cells)],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    got = json.loads(out)
    plain = got["plain"]
    assert plain["count"] == 1 and plain["mode"] == "closed"
    for part in ("all: initial", "position: sticky", "top: 0", "z-index: 2147483647", "flex: none", "display: block"):
        assert part in plain["style"]
    assert plain["texts"] == ["主控面板", "↑ 上", "📄 <b>x</b>"] and plain["titles"] == ["", "說明", ""]
    assert plain["calls"] == [0, 1, 2]
    assert got["separators"] == 2  # 主控面板 | 父層 | 子模組：兩條，最前面沒有
    assert got["without_panel_separators"] == 1 and got["empty"]["count"] == 0  # 沒有任何格子就不畫
    assert got["off"]["count"] == 0  # <meta name="iplot-nav" content="off">
    assert got["twice"]["count"] == 1  # 同一頁載入兩次也只有一排


def test_nav_js_has_no_globals_and_no_inner_html():
    text = (NAV / "nav.js").read_text(encoding="utf-8")
    assert text.lstrip().startswith(("//", "(")) and "innerHTML" not in text and "outerHTML" not in text
    assert "document.write" not in text and "eval(" not in text
