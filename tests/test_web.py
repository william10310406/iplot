"""ui/web.py：WebPanel 把 show／log／report／ask 翻成對頁面的呼叫，Bridge 把頁面的動作排進單一工作執行緒。
全部用假的 webview（conftest.FakeWebview），不開視窗、不需要顯示器。"""

import base64
import dataclasses
import shutil
import threading
import time
from pathlib import Path

import pytest
from conftest import FakeWebview, make_module, until

from core.core import Core
from core.text import T
from core.types import DEFAULT_CONFIG, ErrorInfo
from ui.web import Bridge, WebPanel, error_json, icon_for, scope_json

SLOW = ("import time\ndef run(app):\n    app.log(f'start {time.monotonic()}')\n    time.sleep(0.2)\n"
        "    app.log(f'end {time.monotonic()}')\n")
ASK = "def run(app):\n    app.log('got ' + repr(app.ask('q', 'd')))\n"
MODULE_KEYS = {"id", "name", "title", "description", "icon", "has_children", "error"}
GROUP_KEYS = {"label", "level", "path", "root", "note", "modules"}
ERROR_KEYS = {"kind", "message", "file", "line", "traceback", "source", "module", "sentence"}


@pytest.fixture
def window(panel):
    return panel.window


@pytest.fixture
def bridge(window):
    return window.kw["js_api"]


def rescan(panel):
    panel.window.kw["js_api"].rescan()
    panel.wait()
    return panel.window.calls("show")[-1][0]


def modules(scope):
    return {m["name"]: m for g in scope["groups"] for m in g["modules"]}


def in_thread(fn):
    """在另一條執行緒呼叫 fn，回傳（執行緒, 放結果的 list）。"""
    box = []
    t = threading.Thread(target=lambda: box.append(fn()), daemon=True)
    t.start()
    return t, box


# 視窗與啟動

def test_window_is_created_from_a_file_url(panel, window, home):
    """給 file:// 網址，pywebview 才不會自己起一個 HTTP server（規格：沒有 server、沒有 port）。"""
    assert window.kw["url"] == (home / "ui" / "index.html").as_uri() and window.kw["url"].startswith("file://")
    assert (window.kw["width"], window.kw["height"], window.kw["min_size"]) == (820, 620, (480, 420))
    assert window.title == "iPLoT v0.4.0" and isinstance(window.kw["js_api"], Bridge)


def test_safe_mode_is_in_the_title(home):
    p = WebPanel(home, "0.4.0", True, webview=FakeWebview())
    p.attach(Core(home, DEFAULT_CONFIG, p, safe=True))
    p.run()
    p.wait()
    assert p.window.title == "iPLoT v0.4.0" + T["safe_mode"]
    assert p.window.calls("init")[0][0]["safe"] is True


def test_init_sends_text_then_rescans(panel, window):
    assert window.js[0].startswith("iplot.init(")
    [[init]] = window.calls("init")
    assert init == {"text": T, "version": "0.4.0", "safe": False}
    assert len(window.calls("show")) == 1 and window.js.index(next(j for j in window.js if "iplot.show(" in j)) > 0


def test_startup_logs_what_was_scanned(home):
    make_module(home / "modules", "A")
    p = WebPanel(home, "0.4.0", False, webview=FakeWebview())
    p.attach(Core(home, DEFAULT_CONFIG, p))
    p.run()
    p.wait()
    assert p.window.calls("log")[-1] == [T["scanned"].format(roots="modules/" + T["list_sep"] + "../", count=1)]


def test_reports_made_before_the_page_is_ready_arrive_after_init(home):
    """config.py 壞掉的回報在 run() 之前就交給面板：要等頁面拿到文字（init）之後才送。"""
    p = WebPanel(home, "0.4.0", False, webview=FakeWebview())
    p.attach(Core(home, DEFAULT_CONFIG, p))
    p.submit(lambda: p.report(ErrorInfo("SyntaxError", "x", home / "config.py", 1, "tb", "config", None)))
    p.run()
    p.wait()
    kinds = [j.split("(")[0] for j in p.window.js]
    assert kinds[0] == "iplot.init" and kinds[1] == "iplot.report"


# show 的 JSON（規格附錄 A）

def test_show_json_shape(panel, home):
    folder = make_module(home / "modules", "A", '"""說明。"""\nTITLE = "甲"\ndef run(app):\n    pass\n')
    make_module(folder, "kid")
    scope = rescan(panel)
    assert set(scope) == {"crumbs", "groups"} and scope["crumbs"] == ["iPLoT"]
    here, parent = scope["groups"]
    assert set(here) == GROUP_KEYS
    assert (here["label"], here["level"], here["path"], here["note"]) == (T["here"], "here", "modules/", None)
    assert here["root"] == str((home / "modules").resolve()) and parent["path"] == "../"
    [m] = here["modules"]
    assert set(m) == MODULE_KEYS
    assert m == {"id": str(folder.resolve()), "name": "A", "title": "甲", "description": "說明。", "icon": None,
                 "has_children": True, "error": None}


def test_nested_scope_is_one_child_group(panel, bridge, window, home):
    folder = make_module(home / "modules", "A")
    make_module(folder, "kid")
    rescan(panel)
    bridge.enter(str(folder.resolve()))
    panel.wait()
    scope = window.calls("show")[-1][0]
    assert scope["crumbs"] == ["iPLoT", "A"]
    [g] = scope["groups"]
    assert (g["label"], g["level"], g["path"], g["root"]) == ("A", "child", "A/", str(folder.resolve()))
    assert [m["name"] for m in g["modules"]] == ["kid"]
    bridge.back(0)
    panel.wait()
    assert window.calls("show")[-1][0]["crumbs"] == ["iPLoT"]


def test_extra_root_shows_the_config_string_and_missing_root_has_note(home, tmp_path):
    p = WebPanel(home, "0.4.0", False, webview=FakeWebview())
    p.attach(Core(home, dataclasses.replace(DEFAULT_CONFIG, roots=("modules", "/nonexistent/x")), p))
    p.run()
    p.wait()
    extra = p.window.calls("show")[-1][0]["groups"][1]
    assert (extra["level"], extra["path"]) == ("extra", "/nonexistent/x") and extra["note"]


def test_syntax_error_module_carries_error_string(panel, home):
    make_module(home / "modules", "壞", "def run(app)\n")
    assert modules(rescan(panel))["壞"]["error"].startswith(T["syntax_error"].split("{")[0])


def test_show_escapes_names_for_js(panel, window, home):
    """審查焦點：名稱含單引號、反斜線、雙引號、換行、U+2028 時，送出去的仍是合法的 JS 字面值。"""
    nasty = "a\\b \"q\" it's \u2028 \U0001f9e9 中"
    make_module(home / "modules", "it's", f"TITLE = {nasty!r}\ndef run(app):\n    pass\n")
    scope = rescan(panel)  # calls() 用 json.loads 解得回來
    assert modules(scope)["it's"]["title"] == nasty
    assert window.js[-1].isascii(), "非 ASCII 字元一律 \\uXXXX，經過 pywebview 的轉義與 eval 也不會壞"


def test_state_returns_current_scope(panel, bridge, home):
    make_module(home / "modules", "A")
    scope = rescan(panel)
    assert bridge.state() == scope and modules(scope).keys() == {"A"}


# 圖示（D65）

def test_icon_three_ways(panel, home):
    png = b"\x89PNG\r\n\x1a\n" + b"x" * 10
    (make_module(home / "modules", "A") / "icon.png").write_bytes(png)
    (make_module(home / "modules", "B") / "icon.svg").write_text("<svg/>", encoding="utf-8")
    make_module(home / "modules", "C", 'ICON = "🧩"\ndef run(app):\n    pass\n')
    make_module(home / "modules", "D")
    icons = {name: m["icon"] for name, m in modules(rescan(panel)).items()}
    assert icons["A"] == {"file": "data:image/png;base64," + base64.b64encode(png).decode()}
    assert icons["B"] == {"file": "data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode()}
    assert icons["C"] == {"text": "🧩"} and icons["D"] is None


def test_icon_file_wins_over_constant_and_is_reread_when_changed(panel, home):
    folder = make_module(home / "modules", "A", 'ICON = "🧩"\ndef run(app):\n    pass\n')
    (folder / "icon.png").write_bytes(b"one")
    assert modules(rescan(panel))["A"]["icon"]["file"].endswith(base64.b64encode(b"one").decode())
    (folder / "icon.png").write_bytes(b"three")
    assert modules(rescan(panel))["A"]["icon"]["file"].endswith(base64.b64encode(b"three").decode())
    (folder / "icon.png").unlink()
    assert modules(rescan(panel))["A"]["icon"] == {"text": "🧩"}


def test_bad_icon_falls_back(panel, window, home):
    """審查焦點 5：超過 1 MB 的 icon.png 當作沒有，訊息區記一行，而且只記一次；不影響別的模組。"""
    (make_module(home / "modules", "大") / "icon.png").write_bytes(b"x" * (1024 * 1024 + 1))
    big = make_module(home / "modules", "大有字", 'ICON = "🧩"\ndef run(app):\n    pass\n')
    (big / "icon.png").write_bytes(b"x" * (1024 * 1024 + 1))
    (make_module(home / "modules", "好") / "icon.png").write_bytes(b"ok")
    icons = {name: m["icon"] for name, m in modules(rescan(panel)).items()}
    assert icons["大"] is None and icons["大有字"] == {"text": "🧩"} and "file" in icons["好"]
    warned = [T["icon_unusable"].format(title=t) for t in ("大", "大有字")]
    assert [c[0] for c in window.calls("log") if c[0] in warned] == warned
    rescan(panel)
    assert [c[0] for c in window.calls("log") if c[0] in warned] == warned


def test_icon_exactly_one_megabyte_is_used(home):
    folder = make_module(home / "modules", "A")
    (folder / "icon.png").write_bytes(b"x" * (1024 * 1024))
    info = dataclasses.replace(DEFAULT_INFO(folder), icon_file=folder / "icon.png")
    logs = []
    assert "file" in icon_for(info, set(), logs.append) and logs == []


def test_unreadable_icon_falls_back(home):
    folder = make_module(home / "modules", "A")
    info = dataclasses.replace(DEFAULT_INFO(folder), icon_file=folder / "icon.png")  # 掃描之後被刪掉
    logs, warned = [], set()
    assert icon_for(info, warned, logs.append) is None and icon_for(info, warned, logs.append) is None
    assert logs == [T["icon_unusable"].format(title="A")]


def DEFAULT_INFO(folder):
    from core.scan import module_info
    return module_info(folder, folder.parent, "here")


def test_scope_json_takes_any_icon_function(panel):
    scope = dataclasses.replace(panel.core.scope)
    assert scope_json(scope, lambda info: {"text": "x"})["crumbs"] == ["iPLoT"]


# 工作執行緒

def test_jobs_run_one_at_a_time(panel, bridge, window, home):
    """審查焦點 3：連按兩個模組，Bridge 立刻回來；工作一次只做一件，第二件排在第一件後面。"""
    a, b = (str(make_module(home / "modules", n, SLOW).resolve()) for n in ("A", "B"))
    rescan(panel)
    before = time.monotonic()
    assert bridge.press(a) is None and bridge.press(b) is None and bridge.press(a) is None
    assert time.monotonic() - before < 0.15, "press 不能等模組跑完"
    panel.wait()
    marks = [c[0].split() for c in window.calls("log") if c[0].startswith(("start", "end"))]
    assert [m[0] for m in marks] == ["start", "end"] * 3
    times = [float(m[1]) for m in marks]
    # 0.19 再扣一格時鐘：Windows 上 Python 3.10 的 time.monotonic 約 15.6 ms 才跳一格，sleep(0.2) 可能只量到 0.188
    assert times == sorted(times) and all(times[i + 1] - times[i] >= 0.19 - 0.016 for i in (0, 2, 4))


def test_job_exception_goes_to_report_internal(panel, window, home):
    panel.submit(lambda: 1 / 0)
    panel.wait()
    [error] = window.calls("report")[-1]
    assert error["source"] == "core" and error["kind"] == "ZeroDivisionError"
    assert "ZeroDivisionError" in (home / "logs" / "iplot.log").read_text(encoding="utf-8")
    make_module(home / "modules", "A")
    assert "A" in modules(rescan(panel)), "工作迴圈還活著"


def test_worker_survives_a_page_that_cannot_show_reports(panel, window, home):
    """頁面的 JS 壞到連 iplot.report 都丟例外：回報寫進 logs/iplot.log，工作迴圈照樣繼續。"""
    window.js_error = "iplot.report("
    panel.submit(lambda: 1 / 0)
    panel.wait()
    assert "ZeroDivisionError" in (home / "logs" / "iplot.log").read_text(encoding="utf-8")
    window.js_error = None
    make_module(home / "modules", "A")
    assert "A" in modules(rescan(panel))


# 對話框：ask、confirm

def pending(window, name):
    until(lambda: window.calls(name))
    return window.calls(name)[-1]


def test_ask_roundtrip(panel, bridge, window):
    t, box = in_thread(lambda: panel.ask("q", "d"))
    ask_id, prompt, default = pending(window, "ask")
    assert (prompt, default) == ("q", "d") and t.is_alive()
    bridge.answer(ask_id, "yes")
    t.join(3)
    assert box == ["yes"]


def test_answer_null_is_none(panel, bridge, window):
    t, box = in_thread(lambda: panel.ask("q"))
    bridge.answer(pending(window, "ask")[0], None)
    t.join(3)
    assert box == [None]


def test_confirm_roundtrip(panel, bridge, window):
    for answer, expected in [(True, True), (False, False), (None, False)]:
        t, box = in_thread(lambda: panel.confirm("sure?"))
        ask_id, prompt = pending(window, "confirm")
        assert prompt == "sure?"
        bridge.answer(ask_id, answer)
        t.join(3)
        assert box == [expected]
        window.js.clear()


def test_answer_for_unknown_id_is_ignored(bridge):
    assert bridge.answer(999, "x") is None


def test_close_window_cancels_pending_ask(panel, bridge, window, home):
    """審查焦點 4：模組在 input() 等回答時關掉視窗，ask 收到 None，工作結束，之後的 ask 不再等。"""
    a = str(make_module(home / "modules", "A", ASK).resolve())
    rescan(panel)
    bridge.press(a)
    pending(window, "ask")
    window.fire("closing")
    panel.wait()
    assert panel.ask("again") is None and panel.confirm("again") is False
    assert not any("got" in j for j in window.js), "視窗關了之後不再對頁面說話"


def test_module_input_becomes_a_dialog(panel, bridge, window, home):
    a = str(make_module(home / "modules", "A", "name = input('你是誰？')\nprint('你好，' + name)\n").resolve())
    rescan(panel)
    bridge.press(a)
    ask_id, prompt, _ = pending(window, "ask")
    assert prompt == "你是誰？"
    bridge.answer(ask_id, "小明")
    panel.wait()
    assert ["你好，小明"] in window.calls("log")


def test_page_reload_cancels_pending_ask(panel, window):
    t, box = in_thread(lambda: panel.ask("q"))
    pending(window, "ask")
    window.fire("loaded")  # 頁面重新載入：舊頁面的對話框不在了
    t.join(3)
    assert box == [None]


# Bridge 的動作

def test_bridge_exposes_only_its_methods(bridge):
    """pywebview 會把 js_api 的公開屬性一路攤開給 pywebview.api：Bridge 攤出去的只有這些方法。
    這是整潔，不是安全邊界——pywebview 用名字一路 getattr，知道名字的頁面程式碼叫得到底線後面的東西；
    真正的邊界是頁面零外部資源、模組的輸出一律當文字（tests/test_boundaries.py）。"""
    public = {n for n in dir(bridge) if not n.startswith("_")}
    assert public == {"state", "press", "enter", "back", "create", "add_child", "action", "open_error",
                      "report_error", "rescan", "answer"}
    assert all(callable(getattr(bridge, n)) for n in public)


def test_press_runs_module_and_logs_done(panel, bridge, window, home):
    a = str(make_module(home / "modules", "A").resolve())
    rescan(panel)
    bridge.press(a)
    panel.wait()
    logs = [c[0] for c in window.calls("log")]
    assert "ok" in logs and logs[-1].startswith("A ")


def test_press_missing_module_rescans(panel, bridge, window, home):
    """審查焦點 6：面板上的模組在檔案總管被刪掉後雙擊，不是 traceback，重掃、圖示消失。"""
    folder = make_module(home / "modules", "A")
    assert "A" in modules(rescan(panel))
    shutil.rmtree(folder)
    bridge.press(str(folder.resolve()))
    panel.wait()
    assert window.calls("report") == [] and window.js[-1].startswith("iplot.show(")
    assert modules(window.calls("show")[-1][0]) == {}


def test_unknown_id_rescans(panel, bridge, window):
    shows = len(window.calls("show"))
    for call in (bridge.press, bridge.enter, lambda i: bridge.add_child(i, "x"), lambda i: bridge.action("edit", i)):
        call("/no/such/module")
    panel.wait()
    assert len(window.calls("show")) == shows + 4 and window.calls("report") == []


def test_action_edit_passes_editor(panel, bridge, home, monkeypatch):
    folder = make_module(home / "modules", "A").resolve()
    rescan(panel)
    seen = []
    panel.core.config = dataclasses.replace(panel.core.config, editor=("code", "{file}"))
    monkeypatch.setattr(panel.core, "action", lambda *a: seen.append(a))
    for name in ("edit", "reveal", "terminal"):
        bridge.action(name, str(folder))
    panel.wait()
    assert seen == [("edit", folder / "iplot.py", ("code", "{file}"), None), ("reveal", folder),
                    ("terminal", folder)]


def test_action_rejects_names_the_page_has_no_business_calling(panel, bridge, home, monkeypatch):
    """頁面只能要求打開程式碼、在資料夾中顯示、在終端機打開；trash 這類動作不能從 JS 叫。"""
    folder = make_module(home / "modules", "A").resolve()
    rescan(panel)
    seen = []
    monkeypatch.setattr(panel.core, "action", lambda *a: seen.append(a))
    for name in ("trash", "open", "requirements", ""):
        bridge.action(name, str(folder))
    panel.wait()
    assert seen == [] and folder.exists()


def test_create_in_a_shown_root(panel, bridge, home, monkeypatch):
    monkeypatch.setattr(panel.core, "action", lambda *a: None)  # 不真的開編輯器
    bridge.create(str((home / "modules").resolve()), "新的")
    panel.wait()
    assert (home / "modules" / "新的" / "iplot.py").is_file()
    assert "新的" in modules(panel.window.calls("show")[-1][0])


def test_create_outside_shown_roots_does_nothing(panel, bridge, tmp_path, monkeypatch):
    monkeypatch.setattr(panel.core, "action", lambda *a: None)
    (tmp_path / "elsewhere").mkdir()
    bridge.create(str(tmp_path / "elsewhere"), "x")
    panel.wait()
    assert not (tmp_path / "elsewhere" / "x").exists()


def test_create_bad_name_logs_the_rule(panel, bridge, window, home):
    bridge.create(str((home / "modules").resolve()), "a/b")
    panel.wait()
    assert window.calls("log")[-1] == [T["bad_name"]]


def test_add_child_creates_under_module(panel, bridge, home, monkeypatch):
    monkeypatch.setattr(panel.core, "action", lambda *a: None)
    folder = make_module(home / "modules", "A").resolve()
    rescan(panel)
    bridge.add_child(str(folder), "子")
    panel.wait()
    assert (folder / "子" / "iplot.py").is_file()
    assert modules(panel.window.calls("show")[-1][0])["A"]["has_children"] is True


# 回報與「打開檔案」

def test_report_has_sentence_and_open_error_edits_at_the_line(panel, bridge, window, home, monkeypatch):
    a = make_module(home / "modules", "A", "def run(app):\n    1 / 0\n").resolve()
    rescan(panel)
    bridge.press(str(a))
    panel.wait()
    [error] = window.calls("report")[-1]
    assert set(error) == ERROR_KEYS | {"id", "reportable"}
    assert error["sentence"] == T["error_at_line"].format(module="A", line=2, kind="ZeroDivisionError",
                                                           message="division by zero")
    assert (error["file"], error["line"], error["source"]) == (str(a / "iplot.py"), 2, "module")
    assert "Traceback" in error["traceback"]
    seen = []
    monkeypatch.setattr(panel.core, "action", lambda *a: seen.append(a))
    bridge.open_error(error["id"])
    bridge.open_error(999)  # 不認得的編號：什麼都不做
    panel.wait()
    assert seen == [("edit", a / "iplot.py", None, 2)]


def test_error_json_without_file(home):
    error = ErrorInfo("TypeError", "m", None, None, "", "config", None)
    assert error_json(error) == {"kind": "TypeError", "message": "m", "file": None, "line": None, "traceback": "",
                                 "source": "config", "module": None,
                                 "sentence": T["config_error"].format(message="m")}


REPORTER_SRC = "def on_error(app, error):\n    app.log('got ' + error.kind)\n"
NAME_ERROR = ErrorInfo("NameError", "x", None, None, "", "module", "A")


def test_reportable_follows_the_report_module(panel, home, window):
    """D110：modules/回報與討論 是模組時，錯誤那一列才有「回報這個問題」；每一筆在回報的當下各算各的。"""
    panel.report(NAME_ERROR)
    first = window.calls("report")[-1][0]
    assert first["reportable"] is False
    make_module(home / "modules", "回報與討論", REPORTER_SRC)
    panel.report(NAME_ERROR)
    assert window.calls("report")[-1][0]["reportable"] is True
    assert window.calls("report")[0][0] == first


def test_report_error_hands_the_same_error_to_on_error(panel, home, bridge, monkeypatch):
    """「回報這個問題」把面板上那一筆 ErrorInfo 原封不動交給「回報與討論」的 on_error，而且 quiet（設計第 17 節第 6 條）。"""
    make_module(home / "modules", "回報與討論", REPORTER_SRC)
    seen = []
    monkeypatch.setattr(panel.core, "press", lambda info, handler="run", args=(), quiet=False:
                        seen.append((info, handler, args, quiet)))
    panel.report(NAME_ERROR)
    bridge.report_error(0)
    panel.wait()
    [(info, handler, args, quiet)] = seen
    assert info.folder == home / "modules" / "回報與討論"
    assert (handler, quiet) == ("on_error", True)
    assert len(args) == 1 and args[0] is panel.errors[0]


def test_report_error_runs_on_error_quietly_with_busy(panel, home, bridge, window):
    """真的跑一次：on_error 的輸出進訊息區、沒有「完成」那一行；執行中照樣告訴頁面（經過 WebPanel.press）。"""
    make_module(home / "modules", "回報與討論", REPORTER_SRC)
    panel.report(NAME_ERROR)
    bridge.report_error(0)
    panel.wait()
    logs = [c[0] for c in window.calls("log")]
    done = T["done"].split("{seconds")[0].format(title="回報與討論")
    assert "got NameError" in logs and not any(line.startswith(done) for line in logs)
    assert window.calls("busy") == [["回報與討論"], [None]]


@pytest.mark.parametrize("bad", [999, -1, "0", None, 1.5])
def test_report_error_ignores_bad_ids(panel, home, bridge, window, monkeypatch, bad):
    """頁面傳來的編號只認回報過的那幾筆（照 open_error）：其餘什麼都不做，也不重掃。"""
    make_module(home / "modules", "回報與討論", REPORTER_SRC)
    seen = []
    monkeypatch.setattr(panel.core, "press", lambda *a: seen.append(a))
    panel.report(NAME_ERROR)
    shows = len(window.calls("show"))
    bridge.report_error(bad)
    panel.wait()
    assert seen == [] and len(window.calls("show")) == shows


def test_report_error_without_the_module_rescans(panel, bridge, window):
    """「回報與討論」不在（回報之後被刪掉，或從來沒有）：按了就重掃，不報錯、不記任何一行。"""
    panel.report(NAME_ERROR)
    shows, logs = len(window.calls("show")), len(window.calls("log"))
    bridge.report_error(0)
    panel.wait()
    assert len(window.calls("show")) == shows + 1
    assert len(window.calls("log")) == logs and len(window.calls("report")) == 1


def test_report_error_works_from_a_child_level(panel, home, bridge, window):
    """面板停在下一層時 modules/回報與討論 不在畫面上：照樣找得到（用路徑找，不用 WebPanel.find；設計第 17 節第 5 條）。"""
    a = make_module(home / "modules", "A").resolve()
    make_module(a, "B")
    make_module(home / "modules", "回報與討論", REPORTER_SRC)
    rescan(panel)
    bridge.enter(str(a))
    panel.wait()
    assert "回報與討論" not in modules(window.calls("show")[-1][0])
    panel.report(NAME_ERROR)
    bridge.report_error(0)
    panel.wait()
    assert "got NameError" in [c[0] for c in window.calls("log")]


# 選檔案、選資料夾（D67）

def test_file_dialog_cancel(panel, window):
    window.dialog_result = None
    assert panel.choose_files() == [] and panel.choose_folder() is None


def test_file_dialog_returns_paths(panel, window):
    window.dialog_result = ("/a/b.txt", "/c d/e.txt")
    assert panel.choose_files() == [Path("/a/b.txt"), Path("/c d/e.txt")]
    assert window.dialogs[-1] == ((FakeWebview.FileDialog.OPEN,), {"allow_multiple": True})
    window.dialog_result = ("/a",)
    assert panel.choose_folder() == Path("/a") and window.dialogs[-1] == ((FakeWebview.FileDialog.FOLDER,), {})


# 最終審查的修正

def test_jobs_queued_behind_a_dialog_do_not_run_after_the_window_closes(panel, bridge, window, home):
    """A 在等回答、B 排在後面，這時關掉視窗：A 以取消結束，B 不能在使用者已經離開之後才開始跑。"""
    a = str(make_module(home / "modules", "A", ASK).resolve())
    b = make_module(home / "modules", "B", "open('ran.txt', 'w').close()\n").resolve()
    rescan(panel)
    bridge.press(a)
    pending(window, "ask")
    bridge.press(str(b))
    window.fire("closing")
    panel.wait()
    assert not (b / "ran.txt").exists()


def test_press_tells_the_page_while_a_module_is_running(panel, bridge, window, home):
    """模組的輸出要等它結束才進訊息區：執行期間頁面要看得出「還在跑」，不然使用者會以為沒按到、再按一次。"""
    a = str(make_module(home / "modules", "A", 'TITLE = "甲"\ndef run(app):\n    app.log("mid")\n    1 / 0\n').resolve())
    rescan(panel)
    window.js.clear()
    bridge.press(a)
    panel.wait()
    assert window.calls("busy") == [["甲"], [None]]
    kinds = [j.split("(")[0] for j in window.js]
    assert kinds == ["iplot.busy", "iplot.log", "iplot.report", "iplot.busy"]


def test_empty_icon_file_falls_back(home):
    """0 位元組的 icon.png（下載到一半、touch 出來的）當作沒有，記一行。"""
    folder = make_module(home / "modules", "A")
    (folder / "icon.png").write_bytes(b"")
    logs = []
    assert icon_for(DEFAULT_INFO(folder), set(), logs.append) is None
    assert logs == [T["icon_unusable"].format(title="A")]


# M3：app.page

def test_page_blocks_until_closed(panel):
    """app.page 開第二個視窗顯示一頁 HTML，視窗關掉才回來（像對話框）；api 的方法給那一頁的 JS 呼叫。"""
    api = object()
    t, box = in_thread(lambda: panel.page("工作坊", "<p>hi</p>", api))
    until(lambda: len(panel.webview.windows) == 2)
    page = panel.webview.windows[1]
    assert (page.title, page.kw["html"], page.kw["js_api"]) == ("工作坊", "<p>hi</p>", api)
    assert "url" not in page.kw and t.is_alive()
    page.fire("closed")
    t.join(3)
    assert box == [None] and not t.is_alive()
