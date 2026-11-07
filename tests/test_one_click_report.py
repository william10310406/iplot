"""一鍵回報（M9、D150）：面板記最近的訊息與最近一次的錯誤（ui/errlog.py → logs/last-error.json）、自動問「出錯了，要回報嗎？」
（同一種錯誤只問一次、「這次執行期間不要再問」）、全域的例外處理，與「回報與討論」0.2.0 把它們放進回報（最近的訊息、
「回報問題」附上最近一次的錯誤、「我當時在做什麼」、網址放不下時先拿掉最近的訊息）。不開瀏覽器、不連網。"""
# ruff: noqa: F811  load、opened、web 是從 test_report 匯進來的 fixture，測試的參數同名是 pytest 的用法

import getpass
import importlib.util
import json
import shutil
import sys
import threading
from pathlib import Path

import pytest
from conftest import FakeApp, FakeView, FakeWebview, make_module, until
from test_report import (  # noqa: F401
    MODULE,
    load,
    make_api,
    make_app,
    opened,
    page_data,
    press,
    query,
    web,
)

from core.core import Core
from core.text import REPORT_MODULE, T
from core.types import DEFAULT_CONFIG, ErrorInfo
from ui import errlog

ERR = ErrorInfo("KeyError", "'score'", Path("/x/科學計算/hk.py"), 2, "Traceback …\nKeyError: 'score'\n", "module", "科學計算")


def other(**kw):
    import dataclasses
    return dataclasses.replace(ERR, **kw)


# ── 同一種錯誤只問一次（errlog.Offer）──

class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_offer_asks_once_for_the_same_kind_and_place():
    offer = errlog.Offer(clock=Clock())
    assert offer.due(ERR)
    assert not offer.due(ERR)
    assert not offer.due(other(message="'name'", traceback_text="另一段"))  # 類型、檔案、行號一樣就是同一種


def test_offer_asks_again_for_a_different_kind_file_or_line():
    offer = errlog.Offer(clock=Clock())
    assert offer.due(ERR)
    assert offer.due(other(kind="ValueError"))
    assert offer.due(other(line=3))
    assert offer.due(other(file=None))


def test_offer_asks_again_after_the_window():
    clock = Clock()
    offer = errlog.Offer(window=600, clock=clock)
    assert offer.due(ERR)
    clock.now += 599
    assert not offer.due(ERR)
    clock.now += 2
    assert offer.due(ERR)


def test_offer_muted_never_asks():
    offer = errlog.Offer(clock=Clock())
    offer.muted = True
    assert not offer.due(ERR) and not offer.due(other(kind="ValueError"))


def test_offer_skips_config_errors_and_the_reporters_own_errors():
    offer = errlog.Offer(clock=Clock())
    assert not offer.due(other(source="config", module=None))
    assert not offer.due(other(module=REPORT_MODULE))
    assert offer.due(other(source="core", module=None))


# ── 最近的訊息與 logs/last-error.json（errlog.Recent、errlog.write）──

def test_recent_keeps_the_last_lines_and_splits_multiline_text():
    recent = errlog.Recent()
    for i in range(errlog.RECENT + 5):
        recent.add(f"第 {i} 行")
    recent.add("甲\n乙")
    lines = recent.lines()
    assert len(lines) == errlog.RECENT and lines[-2:] == ["甲", "乙"]


def test_write_puts_the_error_and_recent_lines_in_last_error_json(home):
    errlog.write(home, ERR, ["a", "b"])
    data = json.loads((home / "logs" / "last-error.json").read_text(encoding="utf-8"))
    assert data["kind"] == "KeyError" and data["file"] == str(ERR.file) and data["line"] == 2
    assert data["recent"] == ["a", "b"] and data["sentence"] and data["time"]
    assert not (home / "logs" / "last-error.json.tmp").exists()


def test_write_skips_the_reporters_own_errors(home):
    errlog.write(home, ERR, ["原本那一筆"])
    errlog.write(home, other(module=REPORT_MODULE, kind="TypeError"), ["回報與討論自己壞了"])
    assert json.loads((home / "logs" / "last-error.json").read_text(encoding="utf-8"))["kind"] == "KeyError"


def test_write_never_raises_when_logs_cannot_be_written(home):
    (home / "logs").write_text("不是資料夾", encoding="utf-8")  # logs 是一個檔：mkdir、寫檔都失敗
    errlog.write(home, ERR, [])
    errlog.write(home, other(message="\udce9"), ["\udce9"])  # 孤立的代理字元也不丟


# ── 全域的例外處理（errlog.install）──

def test_thread_exception_goes_to_iplot_log_and_the_sink(home, monkeypatch):
    got, default = [], []
    monkeypatch.setattr(errlog, "sink", got.append)
    monkeypatch.setattr(threading, "excepthook", default.append)  # 原本的那一個（印在終端機）：記下來看有沒有叫到
    errlog.install(home)

    def boom():
        raise RuntimeError("執行緒裡炸了")

    t = threading.Thread(target=boom)
    t.start()
    t.join()
    assert "RuntimeError: 執行緒裡炸了" in (home / "logs" / "iplot.log").read_text(encoding="utf-8")
    assert len(got) == 1 and isinstance(got[0], RuntimeError)
    assert len(default) == 1  # 照樣交給原本的，印在終端機


def test_main_thread_hook_logs_then_calls_the_default(home, monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: seen.append(a))
    errlog.install(home)
    try:
        raise ValueError("主執行緒")
    except ValueError as exc:
        sys.excepthook(type(exc), exc, exc.__traceback__)
    assert seen and "ValueError: 主執行緒" in (home / "logs" / "iplot.log").read_text(encoding="utf-8")


def test_hooks_survive_an_unwritable_logs_folder(home, monkeypatch):
    (home / "logs").write_text("不是資料夾", encoding="utf-8")
    monkeypatch.setattr(sys, "excepthook", lambda *a: None)
    errlog.install(home)
    try:
        raise ValueError("x")
    except ValueError as exc:
        sys.excepthook(type(exc), exc, exc.__traceback__)  # 不丟


# ── 網頁面板：自動問一次 ──

def install_reporter(home, src):
    """modules/回報與討論 換成一個假的：on_error 把收到的錯誤寫進 got.txt（或照 src 做別的）。"""
    return make_module(home / "modules", REPORT_MODULE, src)


ON_ERROR = ("from pathlib import Path\n\ndef run(app):\n    pass\n\n"
            "def on_error(app, error):\n    Path(app.home, 'got.txt').open('a').write(error.kind + '\\n')\n")
BAD = "def run(app):\n    1 / 0\n"


@pytest.fixture
def live(home):
    """跑過 run() 的 WebPanel，自動問「要回報嗎？」是開著的。回 (panel, window)。"""
    from ui.web import WebPanel

    p = WebPanel(home, "0.6.2", False, webview=FakeWebview())
    p.attach(Core(home, DEFAULT_CONFIG, p))
    p.run()
    p.wait()
    return p, p.webview.windows[0]


def offers(window):
    return window.calls("offer")


def crash(panel, home, name="壞掉"):
    """按一個模組（沒有就先建一個會丟 ZeroDivisionError 的），等它跑完；自動問的那一件排在後面。"""
    if not (home / "modules" / name).exists():
        make_module(home / "modules", name, BAD)
    panel.submit(panel.core.rescan)
    panel.wait()
    info = next(m for m in panel.core.all_modules() if m.name == name)
    before = len(panel.webview.windows[0].calls("report"))
    panel.submit(lambda: panel.press(panel.core, info))
    until(lambda: len(panel.webview.windows[0].calls("report")) > before)


def answer_offer(panel, window, value, n=1):
    until(lambda: len(offers(window)) >= n)
    panel.answer(offers(window)[n - 1][0], value)
    panel.wait()


def test_web_offer_asks_and_report_runs_on_error(live, home):
    panel, window = live
    install_reporter(home, ON_ERROR)
    crash(panel, home)
    answer_offer(panel, window, {"report": True, "mute": False})
    assert (home / "got.txt").read_text() == "ZeroDivisionError\n"
    assert T["offer_report"].split("\n")[0] in offers(window)[0][1]


def test_web_offer_same_error_twice_asks_once(live, home):
    panel, window = live
    install_reporter(home, ON_ERROR)
    crash(panel, home)
    answer_offer(panel, window, {"report": False, "mute": False})
    crash(panel, home)
    panel.wait()
    assert len(offers(window)) == 1 and len(window.calls("report")) == 2  # 第二次照樣進訊息區，只是不再問
    assert not (home / "got.txt").exists()


def test_web_offer_mute_stops_asking_for_other_errors_too(live, home):
    panel, window = live
    install_reporter(home, ON_ERROR)
    make_module(home / "modules", "另一個", "def run(app):\n    {}['x']\n")
    crash(panel, home)
    answer_offer(panel, window, {"report": False, "mute": True})
    crash(panel, home, "另一個")
    panel.wait()
    assert len(offers(window)) == 1 and panel.offer.muted


@pytest.mark.parametrize("value", [None, "亂來", 1, {"report": "yes"}])
def test_web_offer_odd_answers_count_as_no(live, home, value):
    panel, window = live
    install_reporter(home, ON_ERROR)
    crash(panel, home)
    answer_offer(panel, window, value)
    assert not (home / "got.txt").exists() and not panel.offer.muted


def test_web_no_offer_without_the_report_module(live, home):
    panel, window = live
    crash(panel, home)
    panel.wait()
    assert window.calls("report") and not offers(window)


def test_web_reporter_crashing_does_not_ask_again_or_kill_the_panel(live, home):
    panel, window = live
    install_reporter(home, "def run(app):\n    pass\n\ndef on_error(app, error):\n    raise RuntimeError('回報壞了')\n")
    crash(panel, home)
    answer_offer(panel, window, {"report": True, "mute": False})
    reports = window.calls("report")
    assert [r[0]["kind"] for r in reports] == ["ZeroDivisionError", "RuntimeError"]
    assert len(offers(window)) == 1  # 回報與討論自己的錯誤不再問
    make_module(home / "modules", "還能跑")  # 面板照常
    panel.submit(panel.core.rescan)
    panel.wait()
    info = next(m for m in panel.core.all_modules() if m.name == "還能跑")
    panel.submit(lambda: panel.press(panel.core, info))
    panel.wait()
    assert ["ok"] in window.calls("log")


def test_web_closing_the_window_while_asking_is_a_no(live, home):
    panel, window = live
    install_reporter(home, ON_ERROR)
    crash(panel, home)
    until(lambda: offers(window))
    window.fire("closing")
    panel.wait()
    assert not (home / "got.txt").exists()


def test_web_report_writes_last_error_with_recent_messages(live, home):
    panel, window = live
    make_module(home / "modules", "吵", "def run(app):\n    print('先印一行')\n    1 / 0\n")
    crash(panel, home, "吵")
    panel.wait()
    data = json.loads((home / "logs" / "last-error.json").read_text(encoding="utf-8"))
    assert data["kind"] == "ZeroDivisionError" and "先印一行" in data["recent"]
    assert data["recent"][-1] == data["sentence"]


def test_bridge_thread_errors_reach_the_panel_through_the_sink(live, home, monkeypatch):
    panel, window = live
    monkeypatch.setattr(errlog, "sink", lambda exc: panel.submit(
        lambda: panel.core.report_internal(type(exc), exc, exc.__traceback__)))
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    errlog.install(home)
    t = threading.Thread(target=lambda: 1 / 0)
    t.start()
    t.join()
    panel.wait()
    assert window.calls("report")[-1][0]["source"] == "core"


# ── tkinter 面板 ──

def test_tk_offer_once_and_mute(home, monkeypatch):
    tkinter = pytest.importorskip("tkinter")
    from conftest import new_tk
    probe = new_tk()  # 只有 Linux 沒有顯示器才跳過
    probe.update()  # macOS 的 Tk 9.0：沒跑過事件迴圈就 destroy，之後的事件迴圈會當掉（test_tk_smoke 的 _probe）
    probe.destroy()
    from ui.tk import Panel

    install_reporter(home, ON_ERROR)
    p = Panel("0.6.2", safe=True)
    try:
        core = Core(home, DEFAULT_CONFIG, p)
        p.attach(core)
        asked = []
        monkeypatch.setattr(p, "ask_offer", lambda prompt: asked.append(prompt) or {"report": True, "mute": True})
        p.report(ERR)
        p.report(ERR)
        p.root.update()
        assert len(asked) == 1 and p.offer.muted
        assert (home / "got.txt").read_text() == "KeyError\n"
        p.report(other(kind="ValueError"))
        p.root.update()
        assert len(asked) == 1
        assert json.loads((home / "logs" / "last-error.json").read_text(encoding="utf-8"))["kind"] == "ValueError"
    finally:
        p.root.update()
        p.root.destroy()
    assert tkinter


# ── 「回報與討論」0.2.0：報告內容 ──

MAC_HOME = str(Path.home())


def recent_lines():
    user = getpass.getuser()
    return [f"讀 {MAC_HOME}/Desktop/成績/王小明.csv", f"使用者 {user} 按了批改", "寄給 a.b@example.com"]


def test_body_has_recent_messages_after_the_error(load):
    report = load("report")
    text = report.body("x", ["- iPLoT：0.6.2"], "一句話", "Traceback\nKeyError\n", ["第一行", "第二行"])
    assert text.index("### 錯誤") < text.index(report.LOG_HEAD) < text.index("<!-- iPLoT 回報")
    assert "第一行\n第二行" in text


def test_body_without_recent_messages_has_no_section(load):
    report = load("report")
    assert report.LOG_HEAD not in report.body("x", [], "一句話", "tb", [])
    assert report.LOG_HEAD not in report.body("x", [], "一句話", "tb", ["", "  "])


def test_recent_text_limits_lines_and_characters(load):
    report = load("report")
    many = [f"行 {i}" for i in range(100)]
    text = report.recent_text(many)
    assert text.split("\n") == many[-report.LOG_LINES:]
    long = ["x" * 500 for _ in range(30)]
    cut = report.recent_text(long)
    assert len(cut) <= report.LOG_CHARS and set(cut.split("\n")) == {"x" * 500}  # 截在行首，不留半行


def test_recent_messages_are_redacted_home_user_and_email(load, tmp_path, web):
    report = load("report")
    app = make_app(tmp_path / "iPLoT")
    rep = report.from_error(ERR, app, recent_lines())
    assert report.LOG_HEAD in rep.body
    for leak in (MAC_HOME, "王小明", "a.b@example.com"):
        assert leak not in rep.body
    user = getpass.getuser()
    if len(user) >= 3:  # 太短的名字 redact 不自動遮（SHORT_USER）
        assert user not in rep.body.replace("<USER>", "")


def test_report_contains_error_traceback_version_os_python_and_module(load, tmp_path, web):
    report = load("report")
    home = tmp_path / "iPLoT"
    app = make_app(home)
    folder = make_module(home / "modules", "科學計算")
    error = other(file=folder / "iplot.py", traceback_text=f'Traceback\n  File "{folder / "iplot.py"}", line 2\nKeyError\n')
    rep = report.from_error(error, app, ["按了第二個作業"])
    for part in ("### 錯誤", "KeyError", f"- iPLoT：{app.version}", "- 作業系統：", "- Python：", "- 模組：科學計算",
                 report.LOG_HEAD, "按了第二個作業"):
        assert part in rep.body, part


def test_with_doing_replaces_the_placeholder(load):
    report = load("report")
    text = report.body(report.WHAT_ERROR, [], "s", "tb")
    done = report.with_doing(text, "  按了   批改 ")
    assert f"{report.WHAT_HEAD}\n{report.DOING_HEAD}按了 批改" in done and report.WHAT_ERROR not in done
    assert report.with_doing(text, "   ") == text


def test_with_doing_keeps_what_the_user_already_wrote(load):
    report = load("report")
    text = f"{report.WHAT_HEAD}\n我自己寫的\n\n### 環境\n"
    done = report.with_doing(text, "按了批改")
    assert done.startswith(f"{report.WHAT_HEAD}\n{report.DOING_HEAD}按了批改\n我自己寫的")
    assert report.with_doing("沒有標題", "x").startswith(report.WHAT_HEAD)


def test_fit_drops_recent_messages_before_cutting_the_traceback(load):
    report = load("report")
    tb = "Traceback\n" + "\n".join(f"  frame {i}" for i in range(6)) + "\nKeyError\n"
    text = report.body("x", [], "一句話", tb, ["很長的一行 " * 30] * 20)
    u, cut = report.fit("BUG", "[回報] t", text, report.MAX_URL)
    sent = query(u)["body"]
    assert cut and report.LOG_DROPPED in sent
    assert "frame 0" in sent and "frame 5" in sent  # traceback 沒被截
    assert len(u) <= report.MAX_URL


def test_last_error_reads_what_the_panel_wrote(load, home):
    report = load("report")
    errlog.write(home, ERR, ["一", "二"])
    error, recent, when = report.last_error(home)
    assert error == ERR and recent == ["一", "二"] and when


@pytest.mark.parametrize("content", ["", "不是 JSON", "[]", '{"kind": 1}', json.dumps({
    "kind": "K", "message": "m", "file": None, "line": "7", "traceback_text": "", "source": "module", "module": None}),
    json.dumps({"kind": "K", "message": "m", "file": None, "line": None, "traceback_text": "", "source": "亂來",
                "module": None})])
def test_last_error_broken_file_is_none(load, home, content):
    report = load("report")
    (home / "logs").mkdir()
    (home / "logs" / "last-error.json").write_text(content, encoding="utf-8")
    assert report.last_error(home) is None


def test_last_error_missing_is_none(load, home):
    assert load("report").last_error(home) is None


def test_recent_for_only_attaches_the_matching_error(load, home):
    report = load("report")
    errlog.write(home, ERR, ["那時候的訊息"])
    assert report.recent_for(home, ERR) == ["那時候的訊息"]
    assert report.recent_for(home, other(kind="ValueError")) == []


# ── 「回報與討論」0.2.0：入口 ──

def test_menu_report_attaches_the_last_error(tmp_path, web):
    home = tmp_path / "iPLoT"
    home.mkdir()
    errlog.write(home, ERR, ["那時候的訊息"])
    view = FakeView()
    result, _ = press(home, view, "run")
    assert result.ok, result.error
    title, html, api = next(e[1] for e in view.events if e[0] == "page")
    data = page_data(html)
    assert data["last"].startswith("會附上最近一次的錯誤")
    got = api.start("")
    assert "KeyError" in got["title"] and "那時候的訊息" in got["body"] and "### 錯誤" in got["body"]


def test_menu_report_without_a_last_error_only_has_the_environment(tmp_path, web):
    home = tmp_path / "iPLoT"
    view = FakeView()
    result, _ = press(home, view, "run")
    assert result.ok, result.error
    _, html, api = next(e[1] for e in view.events if e[0] == "page")
    assert page_data(html)["last"] == ""
    got = api.start("")
    assert "### 錯誤" not in got["body"] and "- iPLoT：" in got["body"]


def test_menu_report_survives_a_broken_last_error_file(tmp_path, web):
    home = tmp_path / "iPLoT"
    (home / "logs").mkdir(parents=True)
    (home / "logs" / "last-error.json").write_bytes(b"\xff\xfe\x00")
    view = FakeView()
    result, _ = press(home, view, "run")
    assert result.ok, result.error


def test_on_error_attaches_recent_messages_of_that_error(tmp_path, web):
    home = tmp_path / "iPLoT"
    home.mkdir()
    errlog.write(home, ERR, ["那時候的訊息"])
    view = FakeView()
    result, _ = press(home, view, "on_error", ERR)
    assert result.ok, result.error
    _, html, _ = next(e[1] for e in view.events if e[0] == "page")
    assert "那時候的訊息" in page_data(html)["body"]


def test_measure_and_send_put_doing_into_the_report(load, tmp_path, monkeypatch, opened):
    report = load("report")
    rep = report.from_error(ERR, make_app(tmp_path / "iPLoT"))
    api, _ = make_api(load, tmp_path, monkeypatch, rep)
    m = api.measure(rep.title, rep.body, f"讀 {MAC_HOME}/私人/a.txt 的時候")
    assert f"{report.DOING_HEAD}讀 " in m["full"] and MAC_HOME not in m["full"]
    r = api.send(rep.title, rep.body, True, "按了批改")
    assert r["ok"] and f"{report.DOING_HEAD}按了批改" in query(opened[-1])["body"]
    assert api.send(rep.title, rep.body, True, None)["ok"]  # 頁面送來的不是字串：當作沒寫


def test_page_has_doing_copy_and_last(load):
    html = (MODULE / "page.html").read_text(encoding="utf-8")
    for needle in ('id="doing"', 'id="copy"', 'id="last"', '$("doing").value', "複製整份報告"):
        assert needle in html, needle


def test_reporter_version_is_0_2_0(load):
    assert load("report").REPORTER == "0.2.0"
    assert "## [0.2.0]" in (MODULE / "CHANGELOG.md").read_text(encoding="utf-8")


def test_core_logic_is_untouched_by_m9():
    """D150：這一版不動核心邏輯（core/ 除了 text.py），只動 ui/、main.py 與模組；核心邏輯的行數不變。"""
    from test_budget import core_logic
    assert sum(core_logic().values()) == 501



# ── 學生作業的錯誤不自動問（D150 修訂）──

HK_TK = MODULE.parent / "科學計算" / "hk_tk.py"


def course_tree(home, student_src="import hk_page\nscore = 1 / 0\n"):
    """照「科學計算」收作業放出來的樣子：<課程>/HK5/<學生>/ 裡是學生的 iplot.py 與殼 hk_page.py（新格式），
    課程資料夾有 hk_tk.py（用真的那一份）。回 (課程, 學生資料夾)。"""
    course = home / "modules" / "科學計算"
    course.mkdir(parents=True)
    shutil.copy2(HK_TK, course / "hk_tk.py")
    make_module(course, "HK5", "def run(app):\n    pass\n")
    student = make_module(course / "HK5", "王小明_B11201234", student_src)
    (student / "hk_page.py").write_text("def boom():\n    raise RuntimeError('殼壞了')\n", encoding="utf-8")
    return course, student


def run_error(home, folder, level="child"):
    from core.runner import run_module
    from core.scan import module_info

    error = run_module(module_info(folder, (home / "modules").resolve(), level), FakeApp(home)).error
    assert error is not None
    return error


def test_student_homework_error_is_not_offered(home):
    _, student = course_tree(home)
    error = run_error(home, student)
    assert error.kind == "ZeroDivisionError" and error.file == student / "iplot.py"
    assert errlog.student_homework(error)
    assert not errlog.Offer(clock=Clock()).due(error)


def test_student_syntax_error_is_not_offered(home):
    _, student = course_tree(home, "import hk_page\ndef compute(case:\n")
    error = run_error(home, student)
    assert error.kind == "SyntaxError" and errlog.student_homework(error)


def test_student_error_in_a_library_call_is_still_the_students(home):
    # 學生把 json.loads 用錯：traceback 最後一格在標準庫裡，模組資料夾裡最內層的那一格是學生的檔
    _, student = course_tree(home, "import hk_page\nimport json\njson.loads('{')\n")
    error = run_error(home, student)
    assert error.kind == "JSONDecodeError" and errlog.student_homework(error)


def test_error_in_the_shell_next_to_the_student_is_offered(home):
    # 殼 hk_page.py 是 iPLoT 這邊的程式：它壞了照常問
    _, student = course_tree(home, "import hk_page\nhk_page.boom()\n")
    error = run_error(home, student)
    assert error.file == student / "hk_page.py"
    assert not errlog.student_homework(error) and errlog.Offer(clock=Clock()).due(error)


def test_old_format_student_folder_is_offered(home):
    # 舊格式的學生資料夾：iplot.py 是 iPLoT 寫的墊片（學生的 HKn.txt 在另開的程序裡跑），墊片壞了是 iPLoT 的事
    course, student = course_tree(home, "raise RuntimeError('墊片壞了')\n")
    (student / "hk_page.py").unlink()
    (student / "t2026fscSpace").mkdir()
    (student / "t2026fscSpace" / "HK5.txt").write_text("def HK5():\n    LF_subWIN\n", encoding="utf-8")
    error = run_error(home, student)
    assert not errlog.student_homework(error) and errlog.Offer(clock=Clock()).due(error)


def test_same_shape_outside_a_course_is_offered(home):
    # 沒有 hk_tk.py 的上上層：不是科學計算的課，只是長得像
    folder = make_module(make_module(home / "modules", "別的", "def run(app):\n    pass\n"), "子", "x = 1 / 0\n")
    (folder / "hk_page.py").write_text("", encoding="utf-8")
    assert not errlog.student_homework(run_error(home, folder))


def test_course_and_hk_level_errors_are_offered(home):
    course, _ = course_tree(home)
    (course / "HK5" / "iplot.py").write_text("x = 1 / 0\n", encoding="utf-8")  # 老師那一層（HKn 的墊片）
    assert not errlog.student_homework(run_error(home, course / "HK5"))
    (course / "iplot.py").write_text("x = 1 / 0\n", encoding="utf-8")
    assert not errlog.student_homework(run_error(home, course, "here"))


def test_core_and_config_errors_are_never_student_homework():
    assert not errlog.student_homework(other(source="core", module=None))
    assert not errlog.student_homework(other(file=None))


def test_symlinked_student_folder_is_offered(home, tmp_path):
    _, student = course_tree(home)
    link = student.parent / "連結"
    try:
        link.symlink_to(student, target_is_directory=True)
    except OSError:
        pytest.skip("這台不能建符號連結")
    error = other(file=link / "iplot.py", module="連結")
    assert not errlog.student_homework(error)


def test_student_rule_matches_science_courses_own(home, load):
    """照「科學計算」自己的判斷（hk_tk._is_student、_is_new_folder、course_root）：同一棵樹上說法一樣。"""
    course, student = course_tree(home)
    spec = importlib.util.spec_from_file_location("hk_tk_for_test", HK_TK)
    hk_tk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hk_tk)
    assert hk_tk._is_student(student, "HK5") and hk_tk._is_new_folder(student)
    assert hk_tk.course_root(student) == course.resolve()
    assert errlog.student_homework(run_error(home, student))


def test_student_error_is_not_written_as_the_last_error(home):
    errlog.write(home, ERR, ["原本那一筆"])
    _, student = course_tree(home)
    errlog.write(home, run_error(home, student), ["學生的"])
    assert json.loads((home / "logs" / "last-error.json").read_text(encoding="utf-8"))["recent"] == ["原本那一筆"]


def test_web_student_error_keeps_the_button_but_does_not_ask(live, home):
    from core.scan import module_info

    panel, window = live
    install_reporter(home, ON_ERROR)
    _, student = course_tree(home)
    info = module_info(student, (home / "modules").resolve(), "child")
    panel.submit(lambda: panel.press(panel.core, info))
    panel.wait()
    row = window.calls("report")[-1][0]
    assert row["kind"] == "ZeroDivisionError" and row["reportable"]  # 「回報這個問題」照樣在
    assert not offers(window)
    bridge = window.kw["js_api"]
    bridge.report_error(row["id"])  # 按那一列的鈕：照樣交給 on_error
    panel.wait()
    assert (home / "got.txt").read_text() == "ZeroDivisionError\n"
    crash(panel, home)  # iPLoT 這邊的模組出錯：照常問
    answer_offer(panel, window, {"report": False, "mute": False})
    assert len(offers(window)) == 1
