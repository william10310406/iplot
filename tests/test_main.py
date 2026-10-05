"""main.py 的入口防線與啟動流程（規格 §3）。main.py 在 repo 根目錄，不在套件裡，用檔案路徑載入。
啟動流程的測試全部用替身：不開視窗、不真的跑 pip、不真的 execv，home 是 tmp 裡的假 iPLoT。"""

import ast
import hashlib
import importlib.util
import os
import shutil
import sys
import threading
import types
from pathlib import Path

import pytest
from conftest import FakeWebview, make_module, until

from core import __version__
from core.text import SYSTEM_MODULE, T

ROOT = Path(__file__).resolve().parent.parent
PRE_GATE = ["main.py", "core/__init__.py", "core/text.py"]  # 版本防線之前就會被 import 的檔案


def load_main():
    spec = importlib.util.spec_from_file_location("iplot_main", ROOT / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_old_python_exits_with_message(monkeypatch):
    main = load_main()
    monkeypatch.setattr(sys, "version_info", (3, 9, 6, "final", 0))
    with pytest.raises(SystemExit) as ei:
        main.main()
    assert "3.10" in str(ei.value) and "3.9.6" in str(ei.value)


def test_need_python_text_in_t():
    assert "{found}" in T["need_python"]


def _annotations(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from (a.annotation for a in node.args.args + node.args.kwonlyargs if a.annotation)
            if node.returns:
                yield node.returns


def test_pre_gate_files_import_on_old_python():
    """D46：防線之前 import 的檔案不能用 3.10 才有的語法，型別註記也不能在 import 時求值（3.8 沒有 dict[str, str]）。"""
    for name in PRE_GATE:
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"), feature_version=(3, 7))
        lazy = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                   and any(a.name == "annotations" for a in n.names) for n in tree.body)
        evaluated = [ast.unparse(a) for a in _annotations(tree)
                     if any(isinstance(x, (ast.Subscript, ast.BinOp)) for x in ast.walk(a))]
        assert lazy or not evaluated, f"{name} 的型別註記 {evaluated} 會在舊版 Python import 時炸"


class Exec(Exception):
    """真的 os.execv 不會回來；替身用丟例外來模擬。"""


@pytest.fixture
def boot(home, monkeypatch):
    """tmp 裡的假 iPLoT（有作業系統模組與 requirements/），main 的四個出口都換成記錄。
    knobs：web 是 run_web 要丟的例外（None＝開得起來）、tk 同理、pip 是 install 的回傳值。"""
    main = load_main()
    shutil.copytree(ROOT / "modules" / SYSTEM_MODULE, home / "modules" / SYSTEM_MODULE,
                    ignore=shutil.ignore_patterns("__pycache__", ".history"))
    shutil.copytree(ROOT / "requirements", home / "requirements")
    b = types.SimpleNamespace(main=main, home=home, calls=[], web=None, tk=None, pip=None,
                              req=home / "requirements" / "web-mac.txt")

    def run_web(home, config, err, version):
        b.calls.append(("web", version))
        if b.web is not None:
            raise b.web

    def run_tk(home, config, err, safe, note=None):
        b.calls.append(("tk", safe, note))
        if b.tk is not None:
            raise b.tk

    def install(home, req, say):
        b.calls.append(("pip", req, (home / "lib" / ".installed").exists()))
        say("Collecting pywebview")
        return b.pip

    def execv(exe, argv):
        b.calls.append(("execv", exe, argv, os.environ.get("IPLOT_BOOT")))
        raise Exec

    monkeypatch.setattr(main, "__file__", str(home / "main.py"))
    monkeypatch.setattr(main, "run_web", run_web)
    monkeypatch.setattr(main, "run_tk", run_tk)
    monkeypatch.setattr("ui.install.install", install)
    monkeypatch.setattr(os, "execv", execv)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv("IPLOT_BOOT", raising=False)
    return b


def kinds(b):
    return [c[0] for c in b.calls]


def test_safe_uses_tk(boot, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--safe"])
    boot.main.main()
    assert boot.calls == [("tk", True, None)]


def test_safe_without_tkinter_exits_1(boot, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "--safe"])
    boot.tk = ImportError("No module named '_tkinter'")
    with pytest.raises(SystemExit) as ei:
        boot.main.main()
    assert ei.value.code == 1 and T["no_tk"] in capsys.readouterr().out


def test_web_when_importable(boot, capsys):
    boot.main.main()
    assert boot.calls == [("web", __version__)] and capsys.readouterr().out == ""


def test_lib_is_on_sys_path_behind_the_program_itself(boot):
    boot.main.main()
    assert sys.path.index(str(boot.home / "lib")) == 1, "lib/ 排在 iPLoT 自己的資料夾後面、系統的套件前面"


def test_missing_lib_installs_then_execv(boot, capsys):
    boot.web = ImportError("No module named 'webview'")
    with pytest.raises(Exec):
        boot.main.main()
    assert kinds(boot) == ["web", "pip", "execv"] and boot.calls[1][1] == boot.req
    _, exe, argv, flag = boot.calls[2]
    assert (exe, argv, flag) == (sys.executable, [sys.executable, str(boot.home / "main.py")], "1")
    out = capsys.readouterr().out
    assert out.index(T["installing"].split("{")[0]) < out.index("Collecting pywebview") < out.index(T["install_done"])


def test_execv_keeps_the_arguments(boot, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--whatever"])
    boot.web = ImportError("x")
    with pytest.raises(Exec):
        boot.main.main()
    assert boot.calls[-1][2] == [sys.executable, str(boot.home / "main.py"), "--whatever"]


def test_install_failure_falls_back_to_tk_with_note(boot, capsys):
    """裝不起來（例如沒有網路）：主控台與 tk 面板的訊息區都說原因與怎麼再試。
    後備面板不是安全模式：掃完整範圍（上一層與 ROOTS），只有 --safe 才只掃 modules/。"""
    boot.web, boot.pip = ImportError("No module named 'webview'"), "ERROR: Could not fetch URL x"
    boot.main.main()
    assert kinds(boot) == ["web", "pip", "tk"]
    _, safe, note = boot.calls[-1]
    assert safe is False and note == T["install_failed"].format(message="ERROR: Could not fetch URL x")
    out = capsys.readouterr().out
    assert note in out and "Traceback" not in out


def test_install_failure_without_tk_exits_1(boot, capsys):
    """審查焦點 1：第一次啟動沒網路、也沒有 tkinter：白話說明，代碼 1，沒有 traceback。"""
    boot.web, boot.pip, boot.tk = ImportError("x"), "ERROR: no network", ImportError("No module named '_tkinter'")
    with pytest.raises(SystemExit) as ei:
        boot.main.main()
    out = capsys.readouterr().out
    assert ei.value.code == 1 and T["no_tk"] in out and "ERROR: no network" in out and "Traceback" not in out


def test_broken_lib_reinstalls_then_falls_back(boot, capsys):
    """審查焦點 2：lib/ 在、.installed 對得上，但 import 壞掉：重裝一次；重啟後還是壞，就退到 tk 並說原因。"""
    (boot.home / "lib").mkdir()
    (boot.home / "lib" / ".installed").write_text(hashlib.sha256(boot.req.read_bytes()).hexdigest(), encoding="utf-8")
    boot.web = ImportError("cannot import name 'AppKit'")
    with pytest.raises(Exec):
        boot.main.main()  # 第一次啟動：重裝，重啟
    assert kinds(boot) == ["web", "pip", "execv"]
    assert boot.calls[1][2] is False, "重裝之前先拿掉 .installed：裝到一半又中斷的話，下次還會再裝"
    boot.main.main()  # 重啟後的那一次：還是壞
    assert kinds(boot) == ["web", "pip", "execv", "web", "tk"], "只重裝一次"
    _, safe, note = boot.calls[-1]
    assert safe is False and note == T["web_failed"].format(message="cannot import name 'AppKit'")
    assert note in capsys.readouterr().out


def test_reinstall_happens_once(boot, monkeypatch):
    """計畫的審查焦點 1：這次啟動就是剛裝完重啟的那一次（IPLOT_BOOT=1），不再裝、不再 execv。"""
    monkeypatch.setenv("IPLOT_BOOT", "1")
    boot.web = ImportError("still broken")
    boot.main.main()
    assert kinds(boot) == ["web", "tk"] and "IPLOT_BOOT" not in os.environ


def test_boot_flag_does_not_leak_into_later_restarts(boot, monkeypatch):
    """重啟後開得起來：旗標拿掉，之後「重新啟動」模組再 execv 時，壞了仍然可以重裝一次。"""
    monkeypatch.setenv("IPLOT_BOOT", "1")
    boot.main.main()
    assert kinds(boot) == ["web"] and "IPLOT_BOOT" not in os.environ


def test_platform_without_web_panel_falls_back_without_pip(boot, monkeypatch, capsys):
    """Linux 這一版沒有網頁面板：不跑 pip，主控台與訊息區說明，開後備的 tk 面板（完整範圍）。"""
    monkeypatch.setattr(sys, "platform", "linux")
    boot.web = ImportError("No module named 'webview'")
    boot.main.main()
    assert kinds(boot) == ["web", "tk"]
    assert "Linux" in boot.calls[-1][2] and boot.calls[-1][2].startswith(T["web_failed"].split("{")[0])
    assert boot.calls[-1][1] is False


def test_missing_system_module_falls_back_without_pip(boot, capsys):
    """作業系統模組不在：不知道要裝哪一份，不跑 pip；主控台有 no_system 那一句，然後開安全模式。"""
    shutil.rmtree(boot.home / "modules" / SYSTEM_MODULE)
    boot.web = ImportError("No module named 'webview'")
    boot.main.main()
    assert kinds(boot) == ["web", "tk"] and boot.calls[-1][1] is False
    assert T["no_system"].format(module=SYSTEM_MODULE, name="requirements") in capsys.readouterr().out


def test_config_error_reaches_the_panel(boot, monkeypatch):
    (boot.home / "config.py").write_text("ROOTS = [\n", encoding="utf-8")
    seen = []
    monkeypatch.setattr(boot.main, "run_web", lambda home, config, err, version: seen.append(err))
    boot.main.main()
    assert seen[0].source == "config"


# run_web 本身（上面的測試把它換掉了）：用假的 webview 套件，不開視窗

def test_run_web_opens_the_panel_and_reports_config_error_after_init(home, monkeypatch):
    from core.core import load_config
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    (home / "config.py").write_text("ROOTS = [\n", encoding="utf-8")
    config, err = load_config(home / "config.py")
    load_main().run_web(home, config, err, "9.9")
    [window] = fake.windows
    until(lambda: window.calls("show"))
    order = [j.split("(")[0] for j in window.js]
    assert window.title == "iPLoT v9.9" and order[:2] == ["iplot.init", "iplot.report"]
    assert window.calls("report")[0][0]["source"] == "config"


def test_run_web_turns_a_webview_that_cannot_start_into_import_error(home, monkeypatch):
    """lib/ 裝壞了：pywebview import 得到，但找不到能用的視窗套件。當成「開不起來」，交給安裝流程處理。"""
    from core.types import DEFAULT_CONFIG

    class Broken(FakeWebview):
        def start(self):
            raise self.WebViewException("You must have either PyObjC or Qt installed")

    monkeypatch.setitem(sys.modules, "webview", Broken())
    with pytest.raises(ImportError, match="PyObjC"):
        load_main().run_web(home, DEFAULT_CONFIG, None, "9.9")


def test_run_web_without_pywebview_is_import_error(home, monkeypatch):
    from core.types import DEFAULT_CONFIG
    monkeypatch.setitem(sys.modules, "webview", None)  # import webview → ImportError
    with pytest.raises(ImportError):
        load_main().run_web(home, DEFAULT_CONFIG, None, "9.9")


def test_module_using_tkinter_under_the_web_panel_gets_a_plain_error(home, monkeypatch):
    """網頁面板的程序裡，tkinter（turtle 也是）一開視窗整個程序就被系統中止，沒有任何訊息（實測結束碼 133）。
    面板開著的期間 import tkinter 要變成一般的模組錯誤，用白話說怎麼辦；面板關掉之後不再擋（後備面板要用）。"""
    from core.types import DEFAULT_CONFIG
    for name in [n for n in sys.modules if n.split(".")[0] in ("tkinter", "_tkinter", "turtle")]:
        monkeypatch.delitem(sys.modules, name)
    closed = threading.Event()

    class Open(FakeWebview):
        def start(self):
            super().start()
            closed.wait(5)  # 視窗開著

    fake = Open()
    monkeypatch.setitem(sys.modules, "webview", fake)
    folder = make_module(home / "modules", "海龜", "import turtle\nprint('reached')\n").resolve()
    main = load_main()
    runner = threading.Thread(target=lambda: main.run_web(home, DEFAULT_CONFIG, None, "9.9"), daemon=True)
    runner.start()
    until(lambda: fake.windows and fake.windows[0].calls("show"))
    window = fake.windows[0]
    window.kw["js_api"].press(str(folder))
    until(lambda: window.calls("report"))
    closed.set()
    runner.join(5)
    [error] = window.calls("report")[-1]
    assert error["kind"] == "ImportError" and error["message"] == T["tk_in_web"] and error["module"] == "海龜"
    assert ["reached"] not in window.calls("log")
    import tkinter  # noqa: F401  面板關掉之後擋就拿掉了
