"""模組導覽列（D153）：ui/nav.py 算要列的格子、掛上載入後的注入與 _iplot_nav，ui/nav.js 畫那一排。
Python 這一頭用假的 webview；JS 那一頭用 node 跑一個假的 DOM（沒有 node 就跳過），畫得對不對在 Mac 上真的看一次（人工驗收）。"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import FakeWebview, FakeWindow, make_module, until
from test_web import in_thread

from core.core import Core
from core.scan import module_info
from core.text import T
from core.types import DEFAULT_CONFIG
from ui import nav
from ui.web import WebPanel

UI = Path(__file__).resolve().parents[1] / "ui"
PAGE = 'def run(app):\n    app.page("頁", "<p>hi</p>")\n    app.log("頁關了")\n'
PANEL = {"k": "panel", "t": "主控面板", "i": "", "d": ""}


def tree(home):
    """課程（有說明）底下兩個子模組：HK1（有圖示、底下還有 G）與 HK2。"""
    top = make_module(home / "modules", "課程", '"""作業"""\nTITLE = "課程作業"\n')
    make_module(top, "HK2", 'TITLE = "第二份"\n')
    hk1 = make_module(top, "HK1", '"""說明一"""\nICON = "📄"\nTITLE = "第一份"\n')
    make_module(hk1, "G")
    return top


def core_with(home, info):
    core = Core(home, DEFAULT_CONFIG, None)
    core.running.append(info)
    return core


def info_of(home, *names):
    root = (home / "modules").resolve()
    folder = root.joinpath(*names)
    level = "here" if len(names) == 1 else "child"
    return module_info(folder, root, level)


def test_cells_for_a_top_level_module_are_the_panel_then_its_children(home):
    tree(home)
    bar = nav.Nav(FakeWindow("頁", {}), core_with(home, info_of(home, "課程")))
    assert bar.cells == [PANEL, {"k": "child", "t": "第一份", "i": "📄", "d": "說明一"},
                         {"k": "child", "t": "第二份", "i": "", "d": ""}]
    assert [t and t.name for t in bar.targets] == [None, "HK1", "HK2"]


def test_cells_for_a_child_add_the_parent_in_the_middle(home):
    tree(home)
    bar = nav.Nav(FakeWindow("頁", {}), core_with(home, info_of(home, "課程", "HK1")))
    assert bar.cells == [PANEL, {"k": "parent", "t": "↑ 課程作業", "i": "", "d": "作業"},
                         {"k": "child", "t": "G", "i": "", "d": ""}]
    assert [t and t.name for t in bar.targets] == [None, "課程", "G"]


def test_a_module_with_no_parent_and_no_children_only_has_the_panel_cell(home):
    make_module(home / "modules", "孤")
    bar = nav.Nav(FakeWindow("頁", {}), core_with(home, info_of(home, "孤")))
    assert bar.cells == [PANEL] and bar.targets == [None]


def test_names_go_in_as_data_never_markup(home):
    make_module(home / "modules", "孤", 'TITLE = "<b>x</b>"\n')
    make_module(home / "modules" / "孤", "子", 'TITLE = "</script>\\"\'"\n')
    window = FakeWindow("頁", {})
    nav.Nav(window, core_with(home, info_of(home, "孤")))
    window.fire("loaded")
    [script] = window.js
    assert json.loads(script.removeprefix(f"({nav.source()})(").removesuffix(")"))[1]["t"] == "</script>\"'"


def test_the_bar_is_injected_after_the_page_loads_and_again_after_every_load(home):
    tree(home)
    window = FakeWindow("頁", {})
    bar = nav.Nav(window, core_with(home, info_of(home, "課程")))
    assert window.js == []
    window.fire("loaded")
    window.fire("loaded")
    assert window.js == [f"({nav.source()})({json.dumps(bar.cells)})"] * 2


def test_iplot_nav_is_exposed_under_that_exact_name(home):
    tree(home)
    window = FakeWindow("頁", {})
    nav.Nav(window, core_with(home, info_of(home, "課程")))
    assert list(window.exposed) == ["_iplot_nav"]  # 底線開頭：pywebview 攤開模組的 api 時略過，撞不到


@pytest.mark.parametrize("bad", ["1", 1.0, True, None, -1, 3, 99, [1], {"i": 1}])
def test_iplot_nav_only_accepts_an_index_on_the_bar(home, bad):
    tree(home)
    window = FakeWindow("頁", {})
    bar = nav.Nav(window, core_with(home, info_of(home, "課程")))
    window.exposed["_iplot_nav"](bad)
    assert not window.destroyed and bar.choice is None


def test_choosing_twice_keeps_the_first_choice(home):
    tree(home)
    window = FakeWindow("頁", {})
    bar = nav.Nav(window, core_with(home, info_of(home, "課程")))
    window.exposed["_iplot_nav"](1)
    window.exposed["_iplot_nav"](2)
    assert bar.choice == 1


def test_choosing_closes_the_page_and_remembers_which(home):
    tree(home)
    window = FakeWindow("頁", {})
    bar = nav.Nav(window, core_with(home, info_of(home, "課程")))
    window.exposed["_iplot_nav"](2)
    assert window.destroyed and bar.choice == 2 and bar.targets[2].name == "HK2"


def test_jump_runs_the_chosen_module_with_the_given_press(home):
    tree(home)
    window, calls = FakeWindow("頁", {}), []
    bar = nav.Nav(window, core := core_with(home, info_of(home, "課程")))
    window.exposed["_iplot_nav"](1)
    bar.jump(lambda c, info: calls.append((c, info.name)))
    assert calls == [(core, "HK1")]


def test_jump_to_the_panel_runs_nothing(home):
    tree(home)
    window, calls = FakeWindow("頁", {}), []
    bar = nav.Nav(window, core_with(home, info_of(home, "課程")))
    window.exposed["_iplot_nav"](0)
    bar.jump(lambda *a: calls.append(a))
    assert window.destroyed and calls == []


def test_jump_with_no_choice_runs_nothing(home):
    tree(home)
    bar = nav.Nav(FakeWindow("頁", {}), core_with(home, info_of(home, "課程")))
    bar.jump(lambda *a: pytest.fail("不該跑"))


def test_jump_to_a_module_that_is_gone_says_so_and_rescans(home, view):
    top = tree(home)
    window = FakeWindow("頁", {})
    core = Core(home, DEFAULT_CONFIG, view)
    core.running.append(info_of(home, "課程"))
    bar = nav.Nav(window, core)
    window.exposed["_iplot_nav"](1)
    core.running.clear()  # 真正跳的時候，頁面所屬的那次執行已經結束了
    shutil.rmtree(top / "HK1")
    bar.jump(lambda *a: pytest.fail("不該跑"))
    assert view.logs[-1] == T["nav_gone"].format(title="第一份") and len(view.shows) == 1


# ── 在面板裡：ui/web.py 的 page ──

@pytest.fixture
def panel(home):
    p = WebPanel(home, "0.7.0", False, webview=FakeWebview())
    p.offer.muted = True
    p.attach(Core(home, DEFAULT_CONFIG, p))
    p.run()
    return p


def open_page(panel, folder):
    """按下 folder 這個模組，等它開出頁面視窗；回那個視窗（工作執行緒停在 app.page 裡）。"""
    count = len(panel.webview.windows)
    panel.window.kw["js_api"].rescan()
    panel.wait()
    panel.window.kw["js_api"].press(str(folder.resolve()))
    until(lambda: len(panel.webview.windows) == count + 1)
    page = panel.webview.windows[-1]
    until(lambda: page in panel._pages)  # 導覽列在登記之前就裝好了：不等的話，視窗剛建好、expose 還沒做
    return page


def test_a_module_page_gets_the_bar_and_jumping_runs_the_child_after_the_module_finishes(panel, home):
    top = make_module(home / "modules", "P", PAGE)
    make_module(top, "K", 'def run(app):\n    app.log("K 跑了")\n')
    page = open_page(panel, top)
    assert list(page.exposed) == ["_iplot_nav"]
    page.fire("loaded")
    assert '"t": "K"' in page.js[-1]
    page.exposed["_iplot_nav"](1)
    assert page.destroyed
    page.fire("closed")
    panel.wait()
    logs = [c[0] for c in panel.window.calls("log")]
    assert logs.index("頁關了") < logs.index("K 跑了")  # 排在這次執行之後
    assert panel.window.calls("busy")[-2:] == [["K"], [None]]


def test_jumping_to_the_panel_only_closes_the_page(panel, home):
    top = make_module(home / "modules", "P", PAGE)
    make_module(top, "K", 'def run(app):\n    app.log("K 跑了")\n')
    page = open_page(panel, top)
    page.exposed["_iplot_nav"](0)
    page.fire("closed")
    panel.wait()
    logs = [c[0] for c in panel.window.calls("log")]
    assert "頁關了" in logs and "K 跑了" not in logs
    assert panel.core.scope.crumbs == ("iPLoT",)  # 面板停在原本的地方


def test_the_panel_stays_where_it_was_after_jumping_to_a_child(panel, home):
    top = make_module(home / "modules", "P", PAGE)
    make_module(top, "K", "def run(app):\n    pass\n")
    page = open_page(panel, top)
    page.exposed["_iplot_nav"](1)
    page.fire("closed")
    panel.wait()
    assert panel.core.scope.crumbs == ("iPLoT",)


def test_a_page_opened_while_another_is_open_gets_no_bar(panel, home):
    make_module(home / "modules", "X")
    panel.core.running.append(info_of(home, "X"))
    t1, _ = in_thread(lambda: panel.page("一", "<p>1</p>", None))
    until(lambda: panel._pages)  # 第一頁已經登記
    t2, _ = in_thread(lambda: panel.page("二", "<p>2</p>", None))
    until(lambda: len(panel.webview.windows) == 3)
    first, second = panel.webview.windows[1:]
    assert list(first.exposed) == ["_iplot_nav"] and second.exposed == {}
    second.fire("loaded")
    assert second.js == []
    for w, t in ((second, t2), (first, t1)):
        w.fire("closed")
        t.join(3)
    assert panel._pages == []
    again, _ = in_thread(lambda: panel.page("三", "<p>3</p>", None))  # 都關掉之後又有導覽列
    until(lambda: len(panel.webview.windows) == 4 and panel.webview.windows[3].exposed)
    assert list(panel.webview.windows[3].exposed) == ["_iplot_nav"]
    panel.webview.windows[3].fire("closed")
    again.join(3)


def test_a_page_opened_outside_any_module_run_has_no_bar(panel):
    t, _ = in_thread(lambda: panel.page("頁", "<p>hi</p>", None))
    until(lambda: len(panel.webview.windows) == 2)
    assert panel.webview.windows[1].exposed == {}
    panel.webview.windows[1].fire("closed")
    t.join(3)


def test_the_module_api_still_reaches_the_page(panel, home):
    """_iplot_nav 是另外 expose 的：模組自己的 js_api 原封不動地交給視窗。"""
    top = make_module(home / "modules", "P", 'class Api:\n    def hi(self):\n        return 1\n\n'
                      'def run(app):\n    app.page("頁", "<p>x</p>", Api())\n')
    page = open_page(panel, top)
    assert [n for n in dir(page.kw["js_api"]) if not n.startswith("_")] == ["hi"]
    assert "_iplot_nav" not in dir(page.kw["js_api"])
    page.fire("closed")
    panel.wait()


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
    out = subprocess.run([NODE, "-e", HARNESS, str(UI / "nav.js"), json.dumps(cells)],
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
    text = (UI / "nav.js").read_text(encoding="utf-8")
    assert text.lstrip().startswith(("//", "(")) and "innerHTML" not in text and "outerHTML" not in text
    assert "document.write" not in text and "eval(" not in text


def test_a_module_made_with_the_plus_button_gets_the_bar_after_one_app_page_line(panel, home):
    """＋ 新建的模組（範本只有 app.log）加一行 app.page 就有導覽列：模組什麼都不用多寫（D153，範本不改）。"""
    bridge = panel.window.kw["js_api"]
    bridge.rescan()
    panel.wait()
    [root] = [g["root"] for g in panel.window.calls("show")[-1][0]["groups"] if g["level"] == "here"]
    bridge.create(root, "新的")
    panel.wait()
    folder = (home / "modules" / "新的").resolve()
    source = (folder / "iplot.py").read_text(encoding="utf-8")
    assert "iplot-nav" not in source and "_iplot_nav" not in source  # 範本沒有導覽列的任何東西
    (folder / "iplot.py").write_text(source + '    app.page("新的", "<p>hi</p>")\n', encoding="utf-8")
    page = open_page(panel, folder)
    assert list(page.exposed) == ["_iplot_nav"]
    page.fire("loaded")
    assert json.loads(page.js[-1].removeprefix(f"({nav.source()})(").removesuffix(")")) == [PANEL]
    page.fire("closed")
    panel.wait()
