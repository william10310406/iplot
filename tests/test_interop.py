"""工作坊模組「互通」（modules/互通）：面板外的入口、彈出式視窗、那一小段、捷徑、同步、狀態頁。
模組裡的檔用 load("名字") 當一般模組 import（不寫 .pyc）。絕不真的開程式、不碰真的家目錄與 repo 的 modules/互通：
會開程式的呼叫一律換成記錄，要寫的資料夾一律在 tmp_path。"""

import ast
import dataclasses
import importlib
import importlib.util
import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest
from conftest import make_module, until

from core.types import DEFAULT_CONFIG

INTEROP = Path(__file__).resolve().parents[1] / "modules" / "互通"
NAMES = ("boot", "popup", "snippet", "shortcut", "sync", "run")


@pytest.fixture
def load(monkeypatch):
    """load("boot")：把 modules/互通/boot.py 當一般模組 import（不寫 .pyc）；結束時從 sys.modules 拿掉。"""
    monkeypatch.syspath_prepend(str(INTEROP))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    for n in NAMES:
        monkeypatch.delitem(sys.modules, n, raising=False)
    yield importlib.import_module
    for n in NAMES:
        sys.modules.pop(n, None)


def fake_iplot(root):
    """root 底下一個看起來像 iPLoT 的資料夾（有 main.py、core/app.py、modules/互通/），回 (home, run_file)。"""
    (root / "core").mkdir(parents=True)
    (root / "core" / "app.py").write_text("", encoding="utf-8")
    (root / "main.py").write_text("", encoding="utf-8")
    (root / "modules" / "互通").mkdir(parents=True)
    return root, str(root / "modules" / "互通" / "run.py")


def fake_framework(root):
    """root 底下一個 python.org 樣子的 Python.framework：回 (bin/python3, Python.app, Python.app 裡的執行檔)。"""
    version = root / "Python.framework" / "Versions" / "3.14"
    exe, app = version / "bin" / "python3", version / "Resources" / "Python.app"
    inner = app / "Contents" / "MacOS" / "Python"
    for f in (exe, inner):
        f.parent.mkdir(parents=True)
        f.write_text("", encoding="utf-8")
    return str(exe), app, str(inner)


def never(*args, **kw):
    pytest.fail(f"不該被呼叫：{args} {kw}")


# ── boot：找 iPLoT、用對的 Python、核對核心版本、提示框（D86） ──

def test_iplot_home_is_two_levels_up(load, tmp_path):
    home, run_file = fake_iplot(tmp_path / "iPLoT")
    assert load("boot").iplot_home(run_file) == home


def test_iplot_home_with_spaces_and_chinese(load, tmp_path):           # Review Focus 3
    home, run_file = fake_iplot(tmp_path / "我的 iPLoT")
    assert load("boot").iplot_home(run_file) == home


def test_iplot_home_none_when_not_in_modules(load, tmp_path):
    assert load("boot").iplot_home(str(tmp_path / "x" / "run.py")) is None


def test_wrong_python_reexecs_once_with_the_recorded_one(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    folder, env, calls = Path(run_file).parent, {}, []
    (folder / ".python").write_text(sys.executable, encoding="utf-8")

    def importer(name):
        raise ImportError("compiled for another Python")

    boot.ensure_python(home, folder, run_file, ["開工"], importer=importer, environ=env,
                       execv=lambda exe, argv: calls.append((exe, argv)), exe="/usr/bin/python3")
    assert calls == [(sys.executable, [sys.executable, run_file, "開工"])] and env[boot.REEXEC] == "1"


def test_after_one_reexec_it_says_one_sentence_instead_of_looping(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    folder = Path(run_file).parent
    (folder / ".python").write_text(sys.executable, encoding="utf-8")

    def importer(name):
        raise ImportError("compiled for another Python")

    said = boot.ensure_python(home, folder, run_file, [], importer=importer, environ={boot.REEXEC: "1"},
                              execv=never, exe="/usr/bin/python3")
    assert said == (f"換成記下的 Python（{sys.executable}）還是開不起來：compiled for another Python。"
                    "在面板按一次「互通」重新記下。")


def test_old_python_without_record_says_one_sentence(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    said = boot.ensure_python(home, Path(run_file).parent, run_file, [], version=(3, 9, 6), importer=never,
                              environ={}, execv=never, exe="/usr/bin/python3")
    assert said == "互通需要 Python 3.10 以上，這個是 3.9.6。先在面板按一次「互通」，讓它記下面板用的 Python。"


def test_lib_that_does_not_load_without_record_says_one_sentence(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")

    def importer(name):
        if name == "webview":
            raise ImportError("bad magic number")

    said = boot.ensure_python(home, Path(run_file).parent, run_file, [], importer=importer, environ={},
                              execv=never, exe="/x/python3")
    assert said == ("這個 Python（/x/python3）載不進 iPLoT 的介面套件（lib/ 是給別的 Python 裝的）。"
                    "先在面板按一次「互通」，讓它記下面板用的 Python。")


def test_a_record_that_is_gone_or_is_this_python_is_not_tried(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    folder = Path(run_file).parent

    def importer(name):
        raise ImportError("x")

    for rec in (str(tmp_path / "gone" / "python3"), sys.executable):
        (folder / ".python").write_text(rec, encoding="utf-8")
        said = boot.ensure_python(home, folder, run_file, [], importer=importer, environ={}, execv=never,
                                  exe=sys.executable)
        assert said.startswith("這個 Python（")


def test_ensure_python_ok_puts_home_and_lib_first(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    env = {"IPLOT_INTEROP_REEXEC": "1"}
    assert boot.ensure_python(home, Path(run_file).parent, run_file, [], importer=lambda name: None,
                              environ=env, execv=never) is None
    assert sys.path[:2] == [str(home), str(home / "lib")]
    assert env == {}  # 換過、成功了：之後這個程序開的程式不再帶著這個記號


def test_check_version(load):
    b = load("boot")
    assert b.check_version("0.5.1", 3, "0.1.0") is None and b.check_version("0.5.0", 3, "0.1.0") is None
    assert b.check_version("0.6.0", 3, "0.1.0") == "互通 0.1.0 支援 iPLoT 0.5，這台是 0.6.0。到工作坊看看互通有沒有新版。"
    assert b.check_version("0.5.1", 2, "0.1.0") is not None


def test_alert_passes_text_as_arguments(load, capsys):
    calls = []
    load("boot").alert("互通", "這是 \" 與 ' 與 end tell", platform="darwin", call=calls.append)
    assert calls[0][-2:] == ["互通", "這是 \" 與 ' 與 end tell"] and "end tell" in capsys.readouterr().err
    assert calls[0][:2] == ["osascript", "-e"] and "on run argv" in calls[0]


def test_alert_elsewhere_only_writes_stderr(load, capsys):
    load("boot").alert("互通", "只寫 stderr", platform="linux", call=never)
    assert "只寫 stderr" in capsys.readouterr().err


def test_remember_python_only_when_changed(load, tmp_path):
    boot, record = load("boot"), tmp_path / ".python"
    assert boot.recorded_python(tmp_path) is None
    boot.remember_python(tmp_path, "/a/python3")
    os.utime(record, ns=(1, 1))
    boot.remember_python(tmp_path, "/a/python3")
    assert record.stat().st_mtime_ns == 1 and boot.recorded_python(tmp_path) == "/a/python3"
    boot.remember_python(tmp_path, "/b/python3")
    assert boot.recorded_python(tmp_path) == "/b/python3" and not list(tmp_path.glob(".python.*"))


def test_python_app_from_bin_and_from_the_app_itself(load, tmp_path):
    boot = load("boot")
    exe, app, inner = fake_framework(tmp_path / "fw")
    assert boot.python_app(exe) == app and boot.python_app(inner) == app
    lone = tmp_path / "venv" / "bin" / "python3"
    lone.parent.mkdir(parents=True)
    lone.write_text("", encoding="utf-8")
    assert boot.python_app(str(lone)) is None


def test_the_app_binary_counts_as_the_same_python(load, tmp_path):
    """從捷徑開時 sys.executable 是 Python.app 裡的執行檔，面板記下的是 bin/python3：是同一個，不重寫紀錄。"""
    boot = load("boot")
    exe, _, inner = fake_framework(tmp_path / "fw")
    boot.remember_python(tmp_path, exe)
    os.utime(tmp_path / ".python", ns=(1, 1))
    boot.remember_python(tmp_path, inner)
    assert boot.recorded_python(tmp_path) == exe and (tmp_path / ".python").stat().st_mtime_ns == 1
    assert boot.same_python(exe, inner) and not boot.same_python(exe, "/usr/bin/python3")


def test_own_version(load, tmp_path):
    boot = load("boot")
    assert boot.own_version(tmp_path) == "?"
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [0.2.0] - 2026-10-08\n\nx\n\n## [0.1.0]\n",
                                           encoding="utf-8")
    assert boot.own_version(tmp_path) == "0.2.0" and boot.own_version(INTEROP) == "0.1.0"


def test_boot_and_run_read_on_python_3_8():
    for name in ("boot.py", "run.py"):
        if (INTEROP / name).exists():
            ast.parse((INTEROP / name).read_text(encoding="utf-8"), feature_version=(3, 8))


# ── popup：彈出式視窗，平常藏著，有話才出來（D81） ──

@pytest.fixture
def popup(load, home):
    """接好 Core 的 Popup：假的 webview，不開視窗；busy_after 縮短成 0.05 秒，exit 只記結束碼。"""
    from conftest import FakeWebview

    from core.core import Core
    from core.types import DEFAULT_CONFIG

    wv, exits, dock = FakeWebview(), [], []
    p = load("popup").Popup(home, wv, "測試", busy_after=0.05, exit=exits.append, dock=dock.append)
    p.attach(Core(home, DEFAULT_CONFIG, p))
    return types.SimpleNamespace(p=p, wv=wv, exits=exits, dock=dock)


def in_thread(fn):
    """在另一條執行緒跑 fn，回那條執行緒與裝結果的盒子。"""
    box = []
    t = threading.Thread(target=lambda: box.append(fn()), daemon=True)
    t.start()
    return t, box


def bridge(t):
    return t.wv.windows[0].kw["js_api"]


def test_popup_starts_hidden_and_a_silent_job_never_shows_it(popup):
    p = popup.p
    assert p.run(lambda: (p.done("ok", 0.0), 0)[1]) == 0
    w = popup.wv.windows[0]
    assert w.kw["hidden"] is True and not w.shown and w.destroyed and not w.calls("done")
    assert (w.kw["width"], w.kw["height"], w.kw["min_size"]) == (460, 320, (360, 220))
    assert w.kw["url"].startswith("file://") and w.kw["url"].endswith("popup.html")


def test_dock_icon_only_while_shown(popup, load, home):
    """藏著的期間不在 Dock（accessory），顯示時才回到一般的 App（Task 0 Step 5 的退路）。"""
    from conftest import FakeWebview

    p = popup.p
    p.run(lambda: (p.done("ok", 0.0), 0)[1])
    assert popup.dock == [False]
    dock = []
    q = load("popup").Popup(home, FakeWebview(), "測試", exit=popup.exits.append, dock=dock.append)
    q.run(lambda: (q.log("x"), q.log("y"), 0)[2])
    assert dock == [False, True]


def test_log_shows_the_window_and_sends_text(popup):
    p = popup.p
    p.run(lambda: (p.log("<b>hi</b>"), 0)[1])
    w = popup.wv.windows[0]
    assert w.shown and w.calls("log") == [["<b>hi</b>"]]


def test_init_tells_the_page_the_title(popup):
    popup.p.run(lambda: 0)
    assert popup.wv.windows[0].calls("init") == [[{"title": "測試"}]]


def test_ask_roundtrip_shows_the_window(popup):
    p, got = popup.p, []
    t, box = in_thread(lambda: p.run(lambda: (got.append(p.ask("q", "d")), 0)[1]))
    until(lambda: popup.wv.windows and popup.wv.windows[0].calls("ask"))
    w = popup.wv.windows[0]
    [[ask_id, prompt, default]] = w.calls("ask")
    assert (prompt, default, w.shown) == ("q", "d", True)
    bridge(popup).answer(ask_id, "yes")
    t.join(3)
    assert (got, box) == (["yes"], [0])


@pytest.mark.parametrize(("value", "expected"), [(True, True), (False, False), (None, False)])
def test_confirm_roundtrip(popup, value, expected):
    p, got = popup.p, []
    t, _ = in_thread(lambda: p.run(lambda: (got.append(p.confirm("要嗎？")), 0)[1]))
    until(lambda: popup.wv.windows and popup.wv.windows[0].calls("confirm"))
    [[ask_id, prompt]] = popup.wv.windows[0].calls("confirm")
    bridge(popup).answer(ask_id, value)
    t.join(3)
    assert prompt == "要嗎？" and got == [expected]


def test_closing_cancels_pending_dialog_and_stops_a_running_job(popup):
    p, got = popup.p, []
    t, _ = in_thread(lambda: p.run(lambda: (got.append(p.ask("q")), 0)[1]))
    until(lambda: popup.wv.windows and popup.wv.windows[0].calls("ask"))
    popup.wv.windows[0].fire("closing")
    t.join(3)
    assert got == [None] and popup.exits == [1]


def test_closing_after_the_module_is_done_is_not_a_stop(popup):
    p = popup.p
    p.run(lambda: (p.log("x"), p.done("ok", 0.1), 0)[2])
    popup.wv.windows[0].fire("closing")
    assert popup.exits == []


def test_page_opens_a_second_window_and_does_not_show_the_popup(popup):
    p = popup.p
    t, _ = in_thread(lambda: p.run(lambda: (p.page("頁", "<p>x</p>", None), 0)[1]))
    until(lambda: len(popup.wv.windows) == 2)
    second = popup.wv.windows[1]
    assert (second.title, second.kw["html"], second.kw["width"], second.kw["height"]) == ("頁", "<p>x</p>", 640, 520)
    second.fire("closed")
    t.join(3)
    assert not t.is_alive() and popup.wv.windows[0].shown is False


def test_choose_files_shows_the_window_first(popup):
    p, seen = popup.p, []

    def job():
        w = popup.wv.windows[0]
        w.dialog_result = ["/a"]
        original = w.create_file_dialog
        w.create_file_dialog = lambda *a, **k: (seen.append(w.shown), original(*a, **k))[1]
        return p.choose_files()

    assert p.run(job) == [Path("/a")] and seen == [True]


def test_choose_folder(popup):
    p = popup.p

    def job():
        popup.wv.windows[0].dialog_result = ["/d"]
        return p.choose_folder()

    assert p.run(job) == Path("/d") and popup.wv.windows[0].shown


def test_done_after_showing_tells_the_page(popup):
    p = popup.p
    p.run(lambda: (p.log("x"), p.done("ok", 1.2), 0)[2])
    w = popup.wv.windows[0]
    assert w.calls("done") == [["ok", 1.2]] and not w.destroyed


def test_done_error_tells_the_page(popup):
    p = popup.p
    p.run(lambda: (p.done("error", 0.1), 0)[1])
    w = popup.wv.windows[0]
    assert w.calls("done") == [["error", 0.1]] and w.shown and not w.destroyed


def test_a_slow_job_shows_busy(popup):
    p = popup.p
    p.run(lambda: (time.sleep(0.3), 0)[1])
    w = popup.wv.windows[0]
    assert w.calls("busy") == [["測試"]] and w.shown


def test_a_quick_job_never_shows_busy(popup):
    p = popup.p
    p.run(lambda: 0)
    time.sleep(0.1)
    w = popup.wv.windows[0]
    assert not w.calls("busy") and not w.shown


def test_stop_exits_with_1(popup):
    popup.p.run(lambda: 0)
    bridge(popup).stop()
    assert popup.exits == [1]


def test_close_destroys_the_window(popup):
    popup.p.run(lambda: 0)
    bridge(popup).close()
    assert popup.wv.windows[0].destroyed


def test_report_sends_the_sentence_file_line_and_details(popup):
    from core.types import ErrorInfo

    p = popup.p
    err = ErrorInfo("NameError", "name 'x' is not defined", Path("/m/iplot.py"), 7, "Traceback…", "module", "M")
    p.run(lambda: (p.report(err), 0)[1])
    [[sent]] = popup.wv.windows[0].calls("report")
    assert sent == {"kind": "NameError", "message": "name 'x' is not defined", "file": "/m/iplot.py", "line": 7,
                    "traceback": "Traceback…", "sentence": "模組『M』第 7 行出錯：NameError，name 'x' is not defined",
                    "id": 0}


def test_open_error_edits_at_the_line(popup, monkeypatch):
    from core.types import ErrorInfo

    p, calls = popup.p, []
    monkeypatch.setattr(p.core, "action", lambda *a: calls.append(a))
    err = ErrorInfo("E", "m", Path("/m/iplot.py"), 7, "", "module", "M")
    p.run(lambda: (p.report(err), 0)[1])
    bridge(popup).open_error(0)
    bridge(popup).open_error(5)  # 不認得的編號不理
    until(lambda: calls)
    time.sleep(0.05)
    assert calls == [("edit", Path("/m/iplot.py"), None, 7)]


def test_bridge_exposes_only_its_methods(load):
    bridge_cls = load("popup").Bridge
    assert {n for n in vars(bridge_cls) if not n.startswith("_")} == {"answer", "open_error", "stop", "close"}


def test_popup_html_is_self_contained_and_never_uses_inner_html():
    html = (INTEROP / "popup.html").read_text(encoding="utf-8")
    assert not any(w in html for w in ("http://", "https://", "innerHTML", "style.css"))
    assert "prefers-color-scheme: dark" in html


def test_popup_html_defines_every_entry_python_calls():
    defined = set(re.findall(r"^iplot\.(\w+) = ", (INTEROP / "popup.html").read_text(encoding="utf-8"), re.M))
    assert defined == {"init", "log", "report", "ask", "confirm", "busy", "done"}


# ── snippet：把那一小段補進現有的模組（每個模組一次，先存快照） ──

def test_snippet_text_is_the_core_template_block(load):
    from core.text import TEMPLATE
    text = load("snippet").TEXT
    assert text in TEMPLATE and text.startswith("# ── 互通 ──") and text.endswith("# ── 互通 ──\n")
    end = "# ── 互通 ──\n"
    assert TEMPLATE[TEMPLATE.index(end[:-1]):TEMPLATE.rindex(end) + len(end)] == text


def test_where_goes_after_docstring_future_and_leading_imports(load):
    src = '"""說明。"""\nfrom __future__ import annotations\nimport os\nimport sys\n\nICON = "x"\nprint(1)\n'
    assert load("snippet").where(src) == 4


def test_where_without_docstring_is_the_top(load):
    assert load("snippet").where("print(1)\n") == 0


def test_where_stops_at_the_first_other_statement(load):
    src = '"""說明。"""\nimport os\nx = 1\nimport sys\n'
    assert load("snippet").where(src) == 2


def test_has_only_counts_the_mark_at_the_start_of_a_line(load):
    s = load("snippet")
    assert s.has("x = 1\n# ── 互通 ── 說明\n") and not s.has('print("# ── 互通 ──")\n')


def test_add_inserts_once_and_snapshots_first(load, tmp_path):
    f = make_module(tmp_path, "A", '"""說明。"""\ndef run(app):\n    pass\n') / "iplot.py"
    s = load("snippet")
    assert s.add(f, 20) is True and s.add(f, 20) is False
    [snap] = (f.parent / ".history").glob("*.py")
    assert s.MARK not in snap.read_text(encoding="utf-8") and f.read_text(encoding="utf-8").count(s.MARK) == 2
    assert f.read_text(encoding="utf-8") == '"""說明。"""\n' + s.TEXT + "def run(app):\n    pass\n"


def test_add_keeps_bom_and_crlf(load, tmp_path):
    f = tmp_path / "iplot.py"
    f.write_bytes(b"\xef\xbb\xbf" + '"""說明。"""\r\ndef run(app):\r\n    pass\r\n'.encode())
    assert load("snippet").add(f, 20)
    data = f.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf") and b"\n" not in data.replace(b"\r\n", b"")
    assert data.count("# ── 互通 ──".encode()) == 2


def test_add_to_a_file_without_a_trailing_newline(load, tmp_path):
    f = tmp_path / "iplot.py"
    f.write_text('"""說明。"""', encoding="utf-8")
    s = load("snippet")
    assert s.add(f, 20) and f.read_text(encoding="utf-8") == '"""說明。"""\n' + s.TEXT
    ast.parse(f.read_text(encoding="utf-8"))


def test_add_raises_on_syntax_error(load, tmp_path):
    f = make_module(tmp_path, "A", "def run(app)\n    pass\n") / "iplot.py"
    with pytest.raises(SyntaxError):
        load("snippet").add(f, 20)
    assert f.read_text(encoding="utf-8") == "def run(app)\n    pass\n" and not (f.parent / ".history").exists()


def test_patched_module_still_reads_meta(load, tmp_path):
    from core.meta import read_meta
    f = make_module(tmp_path, "A", '"""說明。\n\n第二段。"""\nICON = "🧭"\ndef run(app):\n    pass\n') / "iplot.py"
    load("snippet").add(f, 20)
    m = read_meta(f)
    assert (m.description, m.icon, m.has_run, m.error) == ("說明。", "🧭", True, None)


def test_script_module_runs_top_level_only_once(load, tmp_path):
    """沒有 run 的模組（D47）：直接執行時，最外層在交出去之前一行都不跑。"""
    home, _ = fake_iplot(tmp_path / "iPLoT")
    (home / "modules" / "互通" / "run.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    f = make_module(home / "modules", "S", 'print("最外層")\n') / "iplot.py"
    load("snippet").add(f, 20)
    r = subprocess.run([sys.executable, str(f)], capture_output=True, text=True)
    assert r.returncode == 0 and "最外層" not in r.stdout


@pytest.mark.parametrize("odd", ["\x0c", " ", "\x85"])
def test_add_counts_lines_like_python_does(load, tmp_path, odd):
    """換頁字元、\\u2028 這類字 str.splitlines 當成換行，Python 不當：行號要照 Python 算，那一小段才不會插進 docstring 裡。"""
    f = tmp_path / "iplot.py"
    f.write_text(f'"""說明{odd}"""\ndef run(app):\n    pass\n', encoding="utf-8")
    load("snippet").add(f, 20)
    tree = ast.parse(f.read_text(encoding="utf-8"))
    assert ast.get_docstring(tree) == f"說明{odd}" and isinstance(tree.body[2], ast.If)


# ── shortcut：macOS 的 .app 捷徑，交給 Python.app 開（D86） ──

def test_plist_keys_and_executable(load, tmp_path):
    sc, mod = load("shortcut"), make_module(tmp_path, "開工")
    b = sc.write(tmp_path / "捷徑", "開工", mod, "/py/python3", tmp_path / "run.py", sips=pytest.fail)
    info = plistlib.loads((b / "Contents" / "Info.plist").read_bytes())
    assert (info["CFBundleExecutable"], info["CFBundlePackageType"], info["IPLoTInterop"]) == ("iplot-run", "APPL", 1)
    assert (info["IPLoTModule"], info["IPLoTPython"], info["IPLoTIcon"]) == (str(mod), "/py/python3", "")
    assert (b / "Contents" / "MacOS" / "iplot-run").stat().st_mode & 0o777 == 0o755
    assert (info["CFBundleName"], info["CFBundleDisplayName"], info["CFBundleVersion"]) == ("開工", "開工", "1")
    assert re.fullmatch(r"local\.iplot\.interop\.[0-9a-f]{12}", info["CFBundleIdentifier"])
    assert info["IPLoTRun"] == str(tmp_path / "run.py") and "CFBundleIconFile" not in info
    assert b == tmp_path / "捷徑" / "開工.app" and not list((tmp_path / "捷徑").glob(".tmp-*"))


def test_script_quotes_every_path(load, tmp_path):                       # Review Focus 3
    sc = load("shortcut")
    text = sc.script("/我的 py/python3", tmp_path / "我的 iPLoT" / "run.py", tmp_path / "a 'b' $c", "a 'b' $c")
    assert shlex.quote(str(tmp_path / "a 'b' $c")) in text and shlex.quote("/我的 py/python3") in text


def test_script_alerts_when_python_or_run_py_is_missing(load, tmp_path):  # Review Focus 1
    text = load("shortcut").script("/py", tmp_path / "run.py", tmp_path / "m", "m")
    assert '[ ! -x "$py" ] || [ ! -f "$run" ]' in text and "/usr/bin/osascript" in text and "on run argv" in text
    assert "這個捷徑找不到記下的 Python 或 iPLoT。在面板按一次「互通」，捷徑會重新整理。" in text


def test_script_hands_over_to_the_python_app(load, tmp_path):
    """有 Python.app 的 Python：交給它開（TCC 算在 Python 頭上，所有捷徑共用一次允許）。"""
    exe, app, _ = fake_framework(tmp_path / "我的 fw")
    text = load("shortcut").script(exe, tmp_path / "run.py", tmp_path / "模組 A", "模組 A")
    assert f'exec /usr/bin/open -n -a "$app" --args "$run" {shlex.quote(str(tmp_path / "模組 A"))}' in text
    assert f"app={shlex.quote(str(app))}" in text and '[ ! -d "$app" ]' in text


def test_script_really_runs_in_sh_with_odd_paths(load, tmp_path):
    """沒有 Python.app 的 Python：真的用 /bin/sh 跑產生的指令稿，假的 Python 把收到的參數寫出來。"""
    py = tmp_path / "我的 py" / "python3"
    py.parent.mkdir()
    out = tmp_path / "argv.txt"
    py.write_text(f'#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done > {shlex.quote(str(out))}\n',
                  encoding="utf-8")
    py.chmod(0o755)
    run, module = tmp_path / "我的 iPLoT" / "run.py", tmp_path / "a 'b' $c `d` \"e\""
    run.parent.mkdir()
    run.write_text("", encoding="utf-8")
    script = tmp_path / "iplot-run"
    script.write_text(load("shortcut").script(str(py), run, module, "名稱\n換行"), encoding="utf-8")
    assert subprocess.run(["/bin/sh", str(script)], capture_output=True).returncode == 0
    assert out.read_text(encoding="utf-8").splitlines() == [str(run), str(module)]


def test_names_nested_sanitized_and_deduplicated(load, tmp_path):
    sc, a, b, c = load("shortcut"), tmp_path / "a", tmp_path / "b", tmp_path / "c"
    assert sc.names([(["父", "子"], a), (["x/y:z"], b), (["父", "子"], c)]) == {"父 › 子": a, "x／y：z": b, "父 › 子 2": c}


def test_bundle_name_drops_control_characters_and_leading_dots(load):
    assert load("shortcut").bundle_name(["..隱\t藏\n"]) == "隱藏"


def test_long_names_are_cut_and_stay_unique(load, tmp_path):            # Review Focus 4
    got = load("shortcut").names([(["很長" * 80, "一"], tmp_path / "a"), (["很長" * 80, "二"], tmp_path / "b")])
    assert len(got) == 2 and all(len(n.encode()) <= 200 and n.endswith(("…", "… 2")) for n in got)


def test_names_differing_only_in_case_do_not_collide(load, tmp_path):
    """APFS 預設不分大小寫：Abc.app 與 abc.app 是同一個檔名。"""
    got = load("shortcut").names([(["Abc"], tmp_path / "a"), (["abc"], tmp_path / "b")])
    assert list(got) == ["Abc", "abc 2"]


def _shortcuts(base):
    return sorted(p.name for p in base.iterdir())


def test_sync_adds_renames_removes_and_leaves_foreign_things(load, tmp_path):
    sc, base, run = load("shortcut"), tmp_path / "捷徑", tmp_path / "run.py"
    a, b = make_module(tmp_path, "a"), make_module(tmp_path, "b")
    (base / "別人的.app" / "Contents").mkdir(parents=True)
    (base / "別人的.app" / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName": "x"}))
    assert sc.sync(base, {"A": a, "B": b}, "/py", run, sips=pytest.fail) == []
    assert _shortcuts(base) == ["A.app", "B.app", "別人的.app"]
    assert sc.sync(base, {"A2": a}, "/py", run, sips=pytest.fail) == []
    assert _shortcuts(base) == ["A2.app", "別人的.app"]
    assert plistlib.loads((base / "別人的.app" / "Contents" / "Info.plist").read_bytes()) == {"CFBundleName": "x"}


def test_sync_rewrites_when_python_or_run_or_icon_changes(load, tmp_path):
    sc, base, run = load("shortcut"), tmp_path / "捷徑", tmp_path / "run.py"
    a, calls = make_module(tmp_path, "a"), []
    plist = base / "A.app" / "Contents" / "Info.plist"
    sc.sync(base, {"A": a}, "/py1", run, sips=pytest.fail)
    sc.sync(base, {"A": a}, "/py2", run, sips=pytest.fail)
    assert plistlib.loads(plist.read_bytes())["IPLoTPython"] == "/py2"
    sc.sync(base, {"A": a}, "/py2", tmp_path / "moved" / "run.py", sips=pytest.fail)
    assert plistlib.loads(plist.read_bytes())["IPLoTRun"] == str(tmp_path / "moved" / "run.py")
    (a / "icon.png").write_bytes(b"png")

    def sips(argv):
        calls.append(argv)
        Path(argv[-1]).write_bytes(b"icns")
        return 0

    sc.sync(base, {"A": a}, "/py2", tmp_path / "moved" / "run.py", sips=sips)
    info = plistlib.loads(plist.read_bytes())
    assert len(calls) == 1 and calls[0][:4] == ["sips", "-s", "format", "icns"] and info["IPLoTIcon"] != ""
    assert info["CFBundleIconFile"] == "icon" and (base / "A.app" / "Contents" / "Resources" / "icon.icns").exists()


def test_sync_leaves_up_to_date_shortcuts_alone(load, tmp_path):
    sc, base, run = load("shortcut"), tmp_path / "捷徑", tmp_path / "run.py"
    a = make_module(tmp_path, "a")
    sc.sync(base, {"A": a}, "/py", run, sips=pytest.fail)
    plist = base / "A.app" / "Contents" / "Info.plist"
    os.utime(plist, ns=(1, 1))
    sc.sync(base, {"A": a}, "/py", run, sips=pytest.fail)
    assert plist.stat().st_mtime_ns == 1


def test_a_failed_icon_conversion_means_no_icon(load, tmp_path):
    sc, a = load("shortcut"), make_module(tmp_path, "a")
    (a / "icon.png").write_bytes(b"not a png")
    b = sc.write(tmp_path / "捷徑", "A", a, "/py", tmp_path / "run.py", sips=lambda argv: 1)
    assert "CFBundleIconFile" not in plistlib.loads((b / "Contents" / "Info.plist").read_bytes())


def test_sync_clears_its_own_leftover_temporaries(load, tmp_path):
    sc, base = load("shortcut"), tmp_path / "捷徑"
    (base / ".tmp-A.app" / "Contents").mkdir(parents=True)
    sc.sync(base, {}, "/py", tmp_path / "run.py", sips=pytest.fail)
    assert _shortcuts(base) == []


# ── sync：補那一小段、捷徑、紀錄，同一時間只做一個 ──

@pytest.fixture
def interop(home):
    """home/modules/互通（假的「互通」資料夾：同步把紀錄寫在這裡）。"""
    return make_module(home / "modules", "互通")


def do_sync(load, home, interop, config=None, **kw):
    kw.setdefault("platform", "linux")
    return load("sync").sync(home, config or DEFAULT_CONFIG, sys.executable, interop, **kw)


def patched(interop):
    return json.loads((interop / ".patched").read_text(encoding="utf-8"))


def test_sync_patches_each_module_once(load, home, interop):
    a = make_module(home / "modules", "A", '"""a"""\ndef run(app):\n    pass\n')
    already = '"""b"""\n# ── 互通 ── 自己加的\ndef run(app):\n    pass\n'
    b = make_module(home / "modules", "B", already)
    assert do_sync(load, home, interop) == []
    assert "# ── 互通 ──" in (a / "iplot.py").read_text(encoding="utf-8")
    assert (b / "iplot.py").read_bytes() == already.encode() and not (b / ".history").exists()
    assert {str(a), str(b)} <= set(patched(interop))
    (a / "iplot.py").write_text('"""a"""\ndef run(app):\n    pass\n', encoding="utf-8")  # 不要那一段：刪掉
    do_sync(load, home, interop)
    assert "# ── 互通 ──" not in (a / "iplot.py").read_text(encoding="utf-8")


def test_sync_walks_into_child_modules(load, home, interop):
    p = make_module(home / "modules", "P")
    c = make_module(p, "C", '"""c"""\ndef run(app):\n    pass\n')
    do_sync(load, home, interop)
    assert "# ── 互通 ──" in (c / "iplot.py").read_text(encoding="utf-8") and str(c) in patched(interop)


def test_sync_skips_workshop_bundled_and_extra_roots(load, home, interop, tmp_path):
    b = make_module(home / "modules", "B")
    (b / ".origin").write_text("{}", encoding="utf-8")
    up = make_module(home / "modules", "更新")
    e = make_module(tmp_path / "extra", "E")
    config = dataclasses.replace(DEFAULT_CONFIG, roots=("modules", "..", str(tmp_path / "extra")))
    do_sync(load, home, interop, config)
    for m in (b, up, e):
        assert "互通" not in (m / "iplot.py").read_text(encoding="utf-8"), m


def test_sync_does_not_patch_through_a_symlink(load, home, tmp_path, interop):    # Review Focus 2
    real = make_module(tmp_path / "別處", "R", '"""r"""\n')
    (home / "modules" / "L").symlink_to(real, target_is_directory=True)
    problems = load("sync").sync(home, DEFAULT_CONFIG, sys.executable, home / "modules" / "互通", platform="linux")
    assert "L：是符號連結，沒補" in problems and "互通" not in (real / "iplot.py").read_text(encoding="utf-8")


def test_sync_does_not_patch_a_symlinked_iplot_py_but_still_makes_its_shortcut(load, home, tmp_path, interop,
                                                                                monkeypatch):
    target = tmp_path / "別處" / "f.py"  # 別處 不是模組（ROOTS 的 ".." 就是 tmp_path）
    target.parent.mkdir()
    target.write_text('"""f"""\n', encoding="utf-8")
    (home / "modules" / "F").mkdir()
    (home / "modules" / "F" / "iplot.py").symlink_to(target)
    wanted = []
    monkeypatch.setattr(load("shortcut"), "sync", lambda base, w, *a, **k: wanted.append(w) or [])
    problems = do_sync(load, home, interop, platform="darwin")
    assert "F：是符號連結，沒補" in problems and "互通" not in target.read_text(encoding="utf-8")
    assert "F" in wanted[0]


def test_sync_reports_a_syntax_error_and_writes_the_record(load, home, interop):
    a = make_module(home / "modules", "A", "def run(app)\n")
    assert do_sync(load, home, interop) == ["A：有語法錯誤，沒補"]
    assert (interop / ".sync-error").read_text(encoding="utf-8") == "A：有語法錯誤，沒補\n"
    (a / "iplot.py").write_text("def run(app):\n    pass\n", encoding="utf-8")
    assert do_sync(load, home, interop) == [] and not (interop / ".sync-error").exists()


def test_a_fresh_lock_skips_and_a_stale_lock_is_taken(load, home, interop):
    a = make_module(home / "modules", "A", '"""a"""\n')
    (interop / ".lock").write_text("", encoding="utf-8")
    assert do_sync(load, home, interop) == [] and "互通" not in (a / "iplot.py").read_text(encoding="utf-8")
    do_sync(load, home, interop, now=lambda: time.time() + 121)
    assert "互通" in (a / "iplot.py").read_text(encoding="utf-8") and not (interop / ".lock").exists()


def test_records_are_replaced_atomically(load, home, interop, monkeypatch):      # Review Focus 5
    make_module(home / "modules", "A", '"""a"""\n')
    do_sync(load, home, interop)
    before = (interop / ".patched").read_bytes()
    make_module(home / "modules", "B", '"""b"""\n')

    def boom(*a, **k):
        raise OSError("磁碟滿了")

    monkeypatch.setattr(os, "replace", boom)
    problems = do_sync(load, home, interop)
    monkeypatch.undo()
    assert (interop / ".patched").read_bytes() == before and json.loads(before)
    assert any("磁碟滿了" in p for p in problems) and not list(interop.glob(".*.tmp"))
    assert not (interop / ".lock").exists()


def test_shortcuts_only_on_macos_and_never_for_the_os_module(load, home, interop, monkeypatch):
    make_module(home / "modules", "作業系統")
    make_module(home / "modules", "A")
    do_sync(load, home, interop, platform="linux")
    assert not (interop / "捷徑").exists()
    calls = []
    monkeypatch.setattr(load("shortcut"), "sync", lambda base, wanted, python, run, **k: calls.append(
        (base, wanted, python, run)) or [])
    do_sync(load, home, interop, platform="darwin")
    [(base, wanted, python, run)] = calls
    assert base == interop / "捷徑" and run == interop / "run.py" and python == sys.executable
    assert "作業系統" not in wanted and wanted["A"] == home / "modules" / "A"


def test_why_not_names_the_reason(load, home, tmp_path):
    from core import scan
    sync = load("sync")
    b = make_module(home / "modules", "B")
    (b / ".origin").write_text("{}", encoding="utf-8")
    make_module(home / "modules", "工作坊")
    make_module(home / "modules", "A")
    make_module(tmp_path / "extra", "E")
    config = dataclasses.replace(DEFAULT_CONFIG, roots=("modules", "..", str(tmp_path / "extra")))
    roots = scan.roots_from_config(home, config.roots)
    got = {info.name: sync.why_not(info, roots) for info, _ in sync.modules(home, config)}
    assert got == {"A": None, "B": "工作坊裝來的", "工作坊": "隨附模組", "E": "在 ROOTS 另外加的資料夾裡"}


# ── run：面板外的入口 ──

@pytest.fixture
def entry(load, home, monkeypatch):
    """run.main 的測試環境：Python 一律算對、同步與提示框只記錄、webview 是假的；互通的紀錄寫在 home/modules/互通。"""
    from conftest import FakeWebview

    run, boot, sync = load("run"), load("boot"), load("sync")
    synced, alerts, wv = [], [], FakeWebview()
    monkeypatch.setattr(boot, "ensure_python", lambda *a, **k: None)
    monkeypatch.setattr(sync, "sync", lambda *a, **k: synced.append(a) or [])
    monkeypatch.setattr(boot, "alert", lambda title, message, **k: alerts.append((title, message)))
    folder = home / "modules" / "互通"
    folder.mkdir()

    def go(argv, cwd=None, **kw):
        kw.setdefault("home", home)
        return run.main(argv, folder=folder, webview=wv, cwd=cwd or home, **kw)

    return types.SimpleNamespace(run=run, go=go, wv=wv, synced=synced, alerts=alerts, folder=folder)


def started_core(home, config=DEFAULT_CONFIG):
    from conftest import FakeView

    from core.core import Core
    c = Core(home, config, FakeView())
    c.rescan()
    return c


def test_resolve_by_folder_iplot_py_nested_path_and_name(load, home):
    from core import scan
    run = load("run")
    a = make_module(home / "modules", "A")
    p = make_module(home / "modules", "P")
    c = make_module(p, "C")
    core = started_core(home)
    top = scan.module_info(a, (home / "modules").resolve(), "here")
    child = scan.module_info(c, (home / "modules").resolve(), "child")
    assert run.resolve(core, str(a), home) == (top, None)
    assert run.resolve(core, str(a / "iplot.py"), home) == (top, None)
    assert run.resolve(core, "modules/P/C", home) == (child, None)
    assert run.resolve(core, "A", home) == (top, None)


def test_resolve_outside_every_root_is_extra(load, home, tmp_path):
    run = load("run")
    m = make_module(tmp_path / "遠方" / "更遠", "M")  # ROOTS 只有 modules：tmp_path 不是根目錄
    core = started_core(home, dataclasses.replace(DEFAULT_CONFIG, roots=("modules",)))
    info, problem = run.resolve(core, str(m), home)
    assert problem is None and (info.level, info.root, info.folder) == ("extra", m.parent, m)


def test_resolve_problems(load, home):
    from core.text import T
    run = load("run")
    (home / "modules" / "空的").mkdir()
    make_module(home / "modules", "A")
    make_module(home.parent, "A")
    core = started_core(home)
    empty = home / "modules" / "空的"
    assert run.resolve(core, str(empty), home) == (None, run.NOT_A_MODULE.format(path=empty))
    assert run.resolve(core, "/x/y", home) == (None, run.GONE.format(path="/x/y"))
    assert run.resolve(core, "nope", home) == (None, T["not_found"].format(name="nope"))
    info, problem = run.resolve(core, "A", home)
    assert info is None and problem.startswith(T["ambiguous"].split("：")[0].format(name="A"))


def test_main_runs_a_module_quietly_and_returns_0(entry, home):
    make_module(home / "modules", "A", "def run(app):\n    app.log('hi')\n")
    assert entry.go(["A"]) == 0
    w = entry.wv.windows[0]
    assert ["hi"] in w.calls("log") and not any("完成（" in c[0] for c in w.calls("log"))
    assert len(entry.synced) == 1 and w.title == "A"


def test_main_module_error_returns_1(entry, home):
    make_module(home / "modules", "A", "def run(app):\n    1/0\n")
    assert entry.go(["A"]) == 1
    w = entry.wv.windows[0]
    assert w.calls("report")[0][0]["kind"] == "ZeroDivisionError" and w.calls("done") == [["error", pytest.approx(
        w.calls("done")[0][1])]]


def test_main_files_go_to_on_files_relative_to_cwd(entry, home, tmp_path):
    make_module(home / "modules", "A", "def on_files(app, paths):\n    app.log(repr(paths))\n")
    assert entry.go(["A", "x.txt", "/abs/y.txt"], cwd=tmp_path) == 0
    assert [repr([tmp_path / "x.txt", Path("/abs/y.txt")])] in entry.wv.windows[0].calls("log")


def test_main_unconfirmed_cancel_returns_1(entry, home, load, monkeypatch):
    from core.text import T
    a = make_module(home / "modules", "A")
    (a / ".unconfirmed").write_text("", encoding="utf-8")
    monkeypatch.setattr(load("popup").Popup, "confirm", lambda self, prompt: False)
    assert entry.go(["A"]) == 1
    assert [T["cancelled"].format(title="A")] in entry.wv.windows[0].calls("log")


def test_main_not_found_returns_1_and_still_syncs(entry):
    from core.text import T
    assert entry.go(["nope"]) == 1
    w = entry.wv.windows[0]
    assert [T["not_found"].format(name="nope")] in w.calls("log") and w.calls("done")[0][0] == "error"
    assert len(entry.synced) == 1


def test_main_wrong_version_alerts_and_returns_2(entry, load, monkeypatch):
    monkeypatch.setattr(load("boot"), "check_version", lambda *a: "版本不合的那一句")
    assert entry.go(["A"]) == 2
    assert entry.alerts == [("互通", "版本不合的那一句")] and entry.wv.windows == []


def test_main_wrong_python_alerts_and_returns_2(entry, load, monkeypatch):
    monkeypatch.setattr(load("boot"), "ensure_python", lambda *a, **k: "Python 不對的那一句")
    assert entry.go(["A"]) == 2
    assert entry.alerts == [("互通", "Python 不對的那一句")] and entry.wv.windows == []


def test_main_remembers_the_python(entry, home):
    make_module(home / "modules", "A")
    entry.go(["A"])
    assert (entry.folder / ".python").read_text(encoding="utf-8") == sys.executable


def test_main_syncs_with_the_recorded_python(entry, home):
    make_module(home / "modules", "A")
    entry.go(["A"])
    [(h, config, python, folder)] = entry.synced
    assert (h, python, folder) == (home, sys.executable, entry.folder)


def test_main_reports_a_broken_config_and_still_runs(entry, home):
    (home / "config.py").write_text("ROOTS = 1\n", encoding="utf-8")
    make_module(home / "modules", "A", "def run(app):\n    app.log('跑了')\n")
    assert entry.go(["A"]) == 0
    w = entry.wv.windows[0]
    assert len(w.calls("report")) == 1 and w.calls("report")[0][0]["kind"] == "TypeError" and ["跑了"] in w.calls("log")


def test_main_outside_modules_alerts_and_returns_2(entry, load, monkeypatch):
    monkeypatch.setattr(load("boot"), "iplot_home", lambda run_file: None)
    assert entry.go(["A"], home=None) == 2
    assert entry.alerts[0][1].startswith("「互通」要放在 iPLoT 的 modules/ 裡才能用：")


def test_main_popup_cannot_start_alerts_and_returns_2(entry, home):
    make_module(home / "modules", "A")

    def broken():
        raise entry.wv.WebViewException("沒有 WebKit")

    entry.wv.start = broken
    assert entry.go(["A"]) == 2 and entry.alerts == [("互通", "彈出式視窗開不起來：沒有 WebKit")]


def test_a_module_importing_tkinter_gets_the_sentence(entry, home, monkeypatch):
    for name in ("tkinter", "_tkinter"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    make_module(home / "modules", "T", "import tkinter\n")
    assert entry.go(["T"]) == 1
    assert entry.wv.windows[0].calls("report")[0][0]["message"] == entry.run.NO_TK
    assert not any(type(f).__name__ == "NoTk" for f in sys.meta_path)


def test_a_module_with_a_helper_named_like_ours_gets_its_own(entry, home):
    """run.py 自己的 sync.py、popup.py……不能蓋掉模組自己同名的 helper。"""
    m = make_module(home / "modules", "A", "import sync\nprint(sync.VALUE)\n")
    (m / "sync.py").write_text("VALUE = 42\n", encoding="utf-8")
    assert entry.go(["A"]) == 0 and ["42"] in entry.wv.windows[0].calls("log")


def test_main_without_a_target_says_how_to_use(entry, capsys):
    assert entry.go([]) == 1 and entry.wv.windows == []
    assert "run.py <模組資料夾或名稱>" in capsys.readouterr().err


# ── 在面板按「互通」：同步一次，看狀態、捷徑與指令 ──

def load_button():
    """modules/互通/iplot.py 當一般模組 import（同一個資料夾的 boot、sync 由 load 的 sys.path 找到）。"""
    spec = importlib.util.spec_from_file_location("interop_button", INTEROP / "iplot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_button_remembers_python_syncs_and_opens_the_page(load, home, monkeypatch):
    from conftest import FakeApp

    from core.runner import run_module
    from core.scan import module_info
    copy = home / "modules" / "互通"
    shutil.copytree(INTEROP, copy, ignore=shutil.ignore_patterns("__pycache__", ".*", "捷徑"))
    before = {n: (INTEROP / n).stat().st_mtime_ns if (INTEROP / n).exists() else None for n in (".python", ".patched")}
    app, revealed = FakeApp(home), []
    app.reveal = revealed.append
    monkeypatch.setattr(sys, "platform", "linux")  # 這個測試不做捷徑
    result = run_module(module_info(copy, home / "modules", "here"), app)
    assert result.ok, result.error
    assert app.pages[0][0] == "互通" and (copy / ".python").read_text(encoding="utf-8") == sys.executable
    after = {n: (INTEROP / n).stat().st_mtime_ns if (INTEROP / n).exists() else None for n in (".python", ".patched")}
    assert (copy / ".patched").exists() and after == before  # repo 裡的 modules/互通 一個檔都沒動


def _status_tree(home, tmp_path):
    a = make_module(home / "modules", "A", '"""a"""\n')
    b = make_module(home / "modules", "B", 'TITLE = "<b>x</b>"\n')
    (b / ".origin").write_text("{}", encoding="utf-8")
    make_module(home / "modules", "更新")
    make_module(home / "modules", "S", "def run(app)\n")
    make_module(tmp_path / "extra", "E")
    target = tmp_path / "別處" / "f.py"
    target.parent.mkdir()
    target.write_text('"""f"""\n', encoding="utf-8")
    (home / "modules" / "F").mkdir()
    (home / "modules" / "F" / "iplot.py").symlink_to(target)
    interop = make_module(home / "modules", "互通")
    config = dataclasses.replace(DEFAULT_CONFIG, roots=("modules", "..", str(tmp_path / "extra")))
    return a, interop, config


def test_status_counts_and_reasons(load, home, tmp_path):
    a, interop, config = _status_tree(home, tmp_path)
    load("sync").sync(home, config, "/py/python3", interop, platform="linux")
    button = load_button()
    (a / "iplot.py").write_text('"""a"""\n', encoding="utf-8")  # 自己把那一段拿掉了
    got = button.status(home, config, "/py/python3", interop)
    reasons = {s["name"]: s["reason"] for s in got["skipped"]}
    assert reasons == {"<b>x</b>": "工作坊裝來的", "更新": "隨附模組", "S": "有語法錯誤", "E": "在 ROOTS 另外加的資料夾裡",
                       "F": "是符號連結", "A": "拿掉了那一小段（不會再補）"}
    assert (got["total"], got["direct"]) == (7, 1)  # 七個模組都能從面板外打開；直接執行的只有互通自己
    assert got["shortcuts"] == str(interop / "捷徑") and got["python"] == "/py/python3"
    assert got["problems"] == ["F：是符號連結，沒補", "S：有語法錯誤，沒補"]  # 照名稱的順序
    assert got["command"] == shlex.join(["/py/python3", str(interop / "run.py"), "A"])


def test_the_example_command_prefers_kaigong(load, home):
    interop = make_module(home / "modules", "互通")
    make_module(home / "modules", "A")
    make_module(home / "modules", "開工")
    got = load_button().status(home, DEFAULT_CONFIG, "/py", interop)
    assert got["command"] == shlex.join(["/py", str(interop / "run.py"), "開工"])


def test_api_exposes_only_three_methods(load):
    api = load_button().Api
    assert {n for n in vars(api) if not n.startswith("_")} == {"reveal", "copy", "resync"}


def test_api_reveal_copy_and_resync(load, home, monkeypatch):
    from conftest import FakeApp
    button, interop = load_button(), make_module(home / "modules", "互通")
    app, revealed, runs = FakeApp(home), [], []
    app.reveal = revealed.append
    api = button.Api(app, home, DEFAULT_CONFIG, "/py", interop)
    api.reveal()
    assert revealed == [interop / "捷徑"]
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: runs.append((argv, kw)))
    monkeypatch.setattr(sys, "platform", "linux")
    assert api.copy("x") is False and runs == []
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(load("sync"), "sync", lambda *a, **k: [])
    assert api.copy("指令") is True and runs == [(["pbcopy"], {"input": "指令".encode(), "check": False})]
    assert api.resync()["shortcuts"] == str(interop / "捷徑")


def test_names_reach_the_page_as_data_not_markup(load, home, tmp_path, monkeypatch):
    _, interop, config = _status_tree(home, tmp_path)
    button = load_button()
    html = button.render(button.status(home, config, "/py", interop))
    assert "<b>x</b>" not in html and "\\u003cb>x\\u003c/b>" in html and "__STATUS__" not in html
    monkeypatch.setattr(load("sync"), "sync", lambda *a, **k: [])
    data = button.Api(None, home, config, "/py", interop).resync()
    assert {"name": "<b>x</b>", "reason": "工作坊裝來的"} in data["skipped"]


def test_page_html_is_self_contained_and_never_uses_inner_html():
    html = (INTEROP / "page.html").read_text(encoding="utf-8")
    assert not any(w in html for w in ("http://", "https://", "innerHTML", "style.css"))
    assert "prefers-color-scheme: dark" in html and html.count("__STATUS__") == 1


def test_add_after_imports_leaves_a_blank_line_so_ruff_is_happy(load, tmp_path):
    """接在開頭的 import 後面時空一行：ruff 的 I001 要那一行（tests/test_create.py 的範本也過 ruff）。"""
    pytest.importorskip("ruff")
    f = tmp_path / "iplot.py"
    f.write_text('"""說明。"""\nimport os\n\n\ndef run(app):\n    app.log(os.getcwd())\n', encoding="utf-8")
    s = load("snippet")
    s.add(f, 20)
    assert f.read_text(encoding="utf-8").startswith('"""說明。"""\nimport os\n\n' + s.TEXT)
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "--config", str(root / "pyproject.toml"), str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_sync_rewrites_when_only_the_python_app_moves(load, tmp_path, monkeypatch):
    """Homebrew 的 Python 升小版本：python 的路徑不變（opt/…/python3.14），Python.app 換到新的 Cellar 資料夾。"""
    sc, base, run = load("shortcut"), tmp_path / "捷徑", tmp_path / "run.py"
    a, apps = make_module(tmp_path, "a"), iter([tmp_path / "Cellar" / "3.14.7" / "Python.app",
                                                tmp_path / "Cellar" / "3.14.8" / "Python.app"])
    current = [next(apps)]
    monkeypatch.setattr(sc, "python_app", lambda python: current[0])
    sc.sync(base, {"A": a}, "/opt/py", run, sips=pytest.fail)
    current[0] = next(apps)
    sc.sync(base, {"A": a}, "/opt/py", run, sips=pytest.fail)
    script = (base / "A.app" / "Contents" / "MacOS" / "iplot-run").read_text(encoding="utf-8")
    assert "3.14.8" in script and "3.14.7" not in script
    assert plistlib.loads((base / "A.app" / "Contents" / "Info.plist").read_bytes())["IPLoTApp"] == str(current[0])


@pytest.mark.parametrize("src", ["import turtle\nturtle.forward(10)\n", "from tkinter import messagebox\n",
                                 "import tkinter.ttk as ttk\n", "def run(app):\n    import turtle\n"])
def test_sync_leaves_tkinter_and_turtle_modules_alone(load, home, interop, src):
    """用 tkinter／turtle 的模組在面板外開不了視窗（run.py 擋著）；補了那一小段，原本能直接 python3 iplot.py 的就不能了。"""
    t = make_module(home / "modules", "T", src)
    do_sync(load, home, interop)
    assert (t / "iplot.py").read_text(encoding="utf-8") == src
    from core import scan
    sync = load("sync")
    [info] = [i for i, _ in sync.modules(home, DEFAULT_CONFIG) if i.name == "T"]
    assert sync.why_not(info, scan.roots_from_config(home, DEFAULT_CONFIG.roots)) == "用了 tkinter 或 turtle"


def test_an_unknown_tilde_user_is_one_sentence_not_a_traceback(load, home, entry, tmp_path):
    """「~打錯/x」：pathlib 找不到那個使用者會丟 RuntimeError；這裡要的是一句話。"""
    run = load("run")
    assert run.resolve(started_core(home), "~沒有這個人/x", home) == (None, run.GONE.format(path="~沒有這個人/x"))
    make_module(home / "modules", "A", "def on_files(app, paths):\n    app.log(repr(paths))\n")
    assert entry.go(["A", "~沒有這個人/f.txt"], cwd=tmp_path) == 0
    assert [repr([tmp_path / "~沒有這個人/f.txt"])] in entry.wv.windows[0].calls("log")


def test_a_page_window_gets_a_dock_icon_without_showing_the_popup(popup):
    """藏著的小視窗是 accessory（不在 Dock、不在 ⌘-Tab）；app.page 開的視窗要找得回來，所以開之前回到一般的 App。"""
    p = popup.p
    t, _ = in_thread(lambda: p.run(lambda: (p.page("頁", "<p>x</p>", None), 0)[1]))
    until(lambda: len(popup.wv.windows) == 2)
    assert popup.dock == [False, True] and popup.wv.windows[0].shown is False
    popup.wv.windows[1].fire("closed")
    t.join(3)


def test_a_foreign_app_with_a_wanted_name_is_left_alone(load, tmp_path):
    """別人放在 捷徑/ 裡、剛好跟模組同名的 .app（沒有 IPLoTInterop）：不刪、不蓋，說一句。"""
    sc, base, a = load("shortcut"), tmp_path / "捷徑", make_module(tmp_path, "a")
    foreign = base / "A.app" / "Contents"
    foreign.mkdir(parents=True)
    (foreign / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName": "別人的"}))
    problems = sc.sync(base, {"A": a}, "/py", tmp_path / "run.py", sips=pytest.fail)
    assert plistlib.loads((foreign / "Info.plist").read_bytes()) == {"CFBundleName": "別人的"}
    assert len(problems) == 1 and problems[0].startswith("捷徑「A」：") and not list(base.glob(".tmp-*"))
