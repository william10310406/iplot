"""開機程式 main.py 的版本防線（D167）與核心的啟動流程 modules/核心/ui/start.py（規格 §3），都用檔案路徑載入。
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
from core.text import T

SYSTEM_MODULE = "作業系統"  # 隨附的作業系統模組（提供 os.*）；1.0 起核心不知道這個名字（D164）

ROOT = Path(__file__).resolve().parent.parent
KERNEL = ROOT / "modules" / "核心"
PRE_GATE = ["main.py"]  # 版本防線之前就會被讀的檔案：只有凍結的開機程式（D167）


@pytest.fixture(autouse=True)
def bundled_panel(home):
    """網頁面板是隨附的「主控面板」提供的 main（D162）：每個 iPLoT 資料夾都有一份。"""
    from conftest import PANEL_DIR
    shutil.copytree(PANEL_DIR, home / "modules" / "主控面板", ignore=shutil.ignore_patterns("__pycache__"))


def load_boot():
    spec = importlib.util.spec_from_file_location("iplot_boot", ROOT / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_main():
    """核心的啟動（ui/start.py）。測試用的 home 是假的 iPLoT 資料夾；核心照種子的情形當成就在 home（不記 .good）。"""
    spec = importlib.util.spec_from_file_location("iplot_start_under_test", KERNEL / "ui" / "start.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_old_python_exits_with_message(monkeypatch):
    main = load_boot()
    monkeypatch.setattr(sys, "version_info", (3, 9, 6, "final", 0))
    with pytest.raises(SystemExit) as ei:
        main.main()
    assert "3.10" in str(ei.value) and "3.9.6" in str(ei.value)


def test_need_python_text_is_in_the_boot_program():
    assert "{found}" in load_boot().NEED


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
    b = types.SimpleNamespace(main=main, home=home, calls=[], web=None, tk=None, pip=None, notes=[], quick=[],
                              req=home / "requirements" / "web-mac.txt")

    def run_web(home, config, err, note=None):
        b.calls.append(("web",))
        b.notes.append(note)
        if b.web is not None:
            raise b.web

    def run_tk(home, config, err, safe, note=None):
        b.calls.append(("tk", safe, note))
        if b.tk is not None:
            raise b.tk

    def install(home, req, say, quick=False):
        b.calls.append(("pip", req, (home / "lib" / ".installed").exists()))
        b.quick.append(quick)
        say("Collecting pywebview")
        return b.pip

    def execv(exe, argv):
        b.calls.append(("execv", exe, argv, os.environ.get("IPLOT_BOOT")))
        raise Exec

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
    boot.main.main(boot.home, boot.home)
    assert boot.calls == [("tk", True, None)]


def test_safe_without_tkinter_exits_1(boot, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["main.py", "--safe"])
    boot.tk = ImportError("No module named '_tkinter'")
    with pytest.raises(SystemExit) as ei:
        boot.main.main(boot.home, boot.home)
    assert ei.value.code == 1 and T["no_tk"] in capsys.readouterr().out


def test_web_when_importable(boot, capsys):
    boot.main.main(boot.home, boot.home)
    assert boot.calls == [("web",)] and capsys.readouterr().out == ""


def test_lib_is_on_sys_path_behind_the_program_itself(boot):
    boot.main.main(boot.home, boot.home)
    assert sys.path.index(str(boot.home / "lib")) == 1, "lib/ 排在 iPLoT 自己的資料夾後面、系統的套件前面"


def test_missing_lib_installs_then_execv(boot, capsys):
    boot.web = ImportError("No module named 'webview'")
    with pytest.raises(Exec):
        boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["web", "pip", "execv"] and boot.calls[1][1] == boot.req
    _, exe, argv, flag = boot.calls[2]
    assert (exe, argv, flag) == (sys.executable, [sys.executable, str(boot.home / "main.py")], "1")
    out = capsys.readouterr().out
    assert out.index(T["installing"].split("{")[0]) < out.index("Collecting pywebview") < out.index(T["install_done"])


def test_execv_keeps_the_arguments(boot, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--whatever"])
    boot.web = ImportError("x")
    with pytest.raises(Exec):
        boot.main.main(boot.home, boot.home)
    assert boot.calls[-1][2] == [sys.executable, str(boot.home / "main.py"), "--whatever"]


def test_install_failure_falls_back_to_tk_with_note(boot, capsys):
    """裝不起來（例如沒有網路）：主控台與 tk 面板的訊息區都說原因與怎麼再試。
    後備面板不是安全模式：掃完整範圍（上一層與 ROOTS），只有 --safe 才只掃 modules/。"""
    boot.web, boot.pip = ImportError("No module named 'webview'"), "ERROR: Could not fetch URL x"
    boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["web", "pip", "tk"]
    _, safe, note = boot.calls[-1]
    assert safe is False and note == T["install_failed"].format(message="ERROR: Could not fetch URL x")
    out = capsys.readouterr().out
    assert note in out and "Traceback" not in out


def test_install_failure_without_tk_exits_1(boot, capsys):
    """審查焦點 1：第一次啟動沒網路、也沒有 tkinter：白話說明，代碼 1，沒有 traceback。"""
    boot.web, boot.pip, boot.tk = ImportError("x"), "ERROR: no network", ImportError("No module named '_tkinter'")
    with pytest.raises(SystemExit) as ei:
        boot.main.main(boot.home, boot.home)
    out = capsys.readouterr().out
    assert ei.value.code == 1 and T["no_tk"] in out and "ERROR: no network" in out and "Traceback" not in out


def test_broken_lib_reinstalls_then_falls_back(boot, capsys):
    """審查焦點 2：lib/ 在、.installed 對得上，但 import 壞掉：重裝一次；重啟後還是壞，就退到 tk 並說原因。"""
    (boot.home / "lib").mkdir()
    (boot.home / "lib" / ".installed").write_text(hashlib.sha256(boot.req.read_bytes()).hexdigest(), encoding="utf-8")
    boot.web = ImportError("cannot import name 'AppKit'")
    with pytest.raises(Exec):
        boot.main.main(boot.home, boot.home)  # 第一次啟動：重裝，重啟
    assert kinds(boot) == ["web", "pip", "execv"]
    assert boot.calls[1][2] is False, "重裝之前先拿掉 .installed：裝到一半又中斷的話，下次還會再裝"
    boot.main.main(boot.home, boot.home)  # 重啟後的那一次：還是壞
    assert kinds(boot) == ["web", "pip", "execv", "web", "tk"], "只重裝一次"
    _, safe, note = boot.calls[-1]
    assert safe is False and note == T["web_failed"].format(message="cannot import name 'AppKit'")
    assert note in capsys.readouterr().out


def test_reinstall_happens_once(boot, monkeypatch):
    """計畫的審查焦點 1：這次啟動就是剛裝完重啟的那一次（IPLOT_BOOT=1），不再裝、不再 execv。"""
    monkeypatch.setenv("IPLOT_BOOT", "1")
    boot.web = ImportError("still broken")
    boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["web", "tk"] and "IPLOT_BOOT" not in os.environ


def test_boot_flag_does_not_leak_into_later_restarts(boot, monkeypatch):
    """重啟後開得起來：旗標拿掉，之後「重新啟動」模組再 execv 時，壞了仍然可以重裝一次。"""
    monkeypatch.setenv("IPLOT_BOOT", "1")
    boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["web"] and "IPLOT_BOOT" not in os.environ


def test_platform_without_web_panel_falls_back_without_pip(boot, monkeypatch, capsys):
    """Linux 這一版沒有網頁面板：不跑 pip，主控台與訊息區說明，開後備的 tk 面板（完整範圍）。"""
    monkeypatch.setattr(sys, "platform", "linux")
    boot.web = ImportError("No module named 'webview'")
    boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["web", "tk"]
    assert "Linux" in boot.calls[-1][2] and boot.calls[-1][2].startswith(T["web_failed"].split("{")[0])
    assert boot.calls[-1][1] is False


def test_missing_system_module_falls_back_without_pip(boot, capsys):
    """作業系統模組不在：不知道要裝哪一份，不跑 pip；主控台有 no_system 那一句，然後開安全模式。"""
    shutil.rmtree(boot.home / "modules" / SYSTEM_MODULE)
    boot.web = ImportError("No module named 'webview'")
    boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["web", "tk"] and boot.calls[-1][1] is False
    assert T["no_system"].format(role="os.requirements") in capsys.readouterr().out


def test_config_error_reaches_the_panel(boot, monkeypatch):
    (boot.home / "config.py").write_text("ROOTS = [\n", encoding="utf-8")
    seen = []
    monkeypatch.setattr(boot.main, "run_web", lambda home, config, err, note=None: seen.append(err))
    boot.main.main(boot.home, boot.home)
    assert seen[0].source == "config"


# run_web 本身（上面的測試把它換掉了）：用假的 webview 套件，不開視窗

def test_run_web_opens_the_panel_and_reports_config_error_after_init(home, monkeypatch):
    from core.core import load_config
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    (home / "config.py").write_text("ROOTS = [\n", encoding="utf-8")
    config, err = load_config(home / "config.py")
    load_main().run_web(home, config, err)
    [window] = fake.windows
    until(lambda: window.calls("show"))
    order = [j.split("(")[0] for j in window.js]
    assert window.title == f"iPLoT v{__version__}" and order[:2] == ["iplot.init", "iplot.report"]
    assert window.calls("report")[0][0]["source"] == "config"


def test_run_web_turns_a_webview_that_cannot_start_into_import_error(home, monkeypatch):
    """lib/ 裝壞了：pywebview import 得到，但找不到能用的視窗套件。當成「開不起來」，交給安裝流程處理。"""
    from core.types import DEFAULT_CONFIG

    class Broken(FakeWebview):
        def start(self):
            raise self.WebViewException("You must have either PyObjC or Qt installed")

    monkeypatch.setitem(sys.modules, "webview", Broken())
    with pytest.raises(ImportError, match="PyObjC"):
        load_main().run_web(home, DEFAULT_CONFIG, None)


def test_run_web_without_a_panel_module_opens_the_rescue_panel_and_says_why(home, monkeypatch):
    from core.types import DEFAULT_CONFIG
    shutil.rmtree(home / "modules" / "主控面板")
    main, seen = load_main(), []
    monkeypatch.setattr(main, "tk_or_exit", lambda home, config, err, safe, note=None: seen.append((safe, note)))
    main.run_web(home, DEFAULT_CONFIG, None)
    assert seen == [(False, T["no_panel"])]


def test_run_web_with_a_broken_panel_module_opens_the_rescue_panel_and_logs_it(home, monkeypatch):
    from core.types import DEFAULT_CONFIG
    (home / "modules" / "主控面板" / "iplot.py").write_text('PROVIDES = {"main": "start"}\ndef start(app, core, note, err):\n'
                                                       '    raise RuntimeError("面板壞了")\n', encoding="utf-8")
    main, seen = load_main(), []
    monkeypatch.setattr(main, "tk_or_exit", lambda home, config, err, safe, note=None: seen.append((safe, note)))
    main.run_web(home, DEFAULT_CONFIG, None)
    assert seen == [(False, T["panel_broken"].format(message="面板壞了"))]
    assert "RuntimeError: 面板壞了" in (home / "logs" / "iplot.log").read_text(encoding="utf-8")


def test_run_web_without_pywebview_is_import_error(home, monkeypatch):
    from core.types import DEFAULT_CONFIG
    monkeypatch.setitem(sys.modules, "webview", None)  # import webview → ImportError
    with pytest.raises(ImportError):
        load_main().run_web(home, DEFAULT_CONFIG, None)


def test_a_module_using_tkinter_under_the_web_panel_runs_in_its_own_process(home, monkeypatch):
    """以前網頁面板的程序裡一開 tkinter 視窗整個程序就被系統中止（實測結束碼 133），只好擋住 import tkinter。
    每按一次另開程序之後（D161），模組在自己的程序的主執行緒上跑，turtle、tkinter 照常 import，面板的程序不受影響。"""
    pytest.importorskip("tkinter")  # 這個 Python 沒有 tkinter：模組本來就 import 不到，跟面板無關
    from core.types import DEFAULT_CONFIG
    closed = threading.Event()

    class Open(FakeWebview):
        def start(self):
            super().start()
            closed.wait(20)  # 視窗開著

    fake = Open()
    monkeypatch.setitem(sys.modules, "webview", fake)
    folder = make_module(home / "modules", "海龜", "import tkinter\nprint('reached')\n").resolve()
    main = load_main()
    runner = threading.Thread(target=lambda: main.run_web(home, DEFAULT_CONFIG, None), daemon=True)
    runner.start()
    until(lambda: fake.windows and fake.windows[0].calls("show"))
    window = fake.windows[0]
    window.kw["js_api"].press(str(folder))
    until(lambda: ["reached"] in window.calls("log") or window.calls("report"), 20)
    closed.set()
    runner.join(5)
    assert ["reached"] in window.calls("log"), window.calls("report")
    assert not any(type(f).__name__ == "NoTk" for f in sys.meta_path)


# 需求檔變了（「更新」換了 requirements/）→ 下次啟動重裝 lib/；沒有網路就先用現有的

def mark_installed(b, text=None):
    (b.home / "lib").mkdir(exist_ok=True)
    digest = hashlib.sha256(b.req.read_bytes()).hexdigest() if text is None else text
    (b.home / "lib" / ".installed").write_text(digest, encoding="utf-8")


def test_up_to_date_lib_is_not_reinstalled(boot, capsys):
    mark_installed(boot)
    boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["web"] and boot.notes == [None] and capsys.readouterr().out == ""


def test_changed_requirements_reinstall_before_the_panel_opens(boot, capsys):
    """lib/ 是照舊的需求檔裝的：開面板之前先重裝（求快），裝好直接開，不用重啟——這時候還沒 import 任何 lib/ 的東西。"""
    mark_installed(boot, "digest of the old requirements file")
    boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["pip", "web"] and boot.quick == [True] and boot.notes == [None]
    assert boot.calls[0][2] is True, "重裝之前不拿掉記號：沒裝成的話下次還要再試"
    out = capsys.readouterr().out
    assert T["refreshing"] in out and "Collecting pywebview" in out


def test_changed_requirements_offline_opens_the_old_panel_and_keeps_trying(boot, capsys):
    """更新之後沒有網路：重裝失敗就說明原因、先用現有的 lib/ 開網頁面板（訊息區也說一次）；
    記號沒動，所以下次啟動會再試。"""
    mark_installed(boot, "digest of the old requirements file")
    boot.pip = "ERROR: Could not find a version"
    boot.main.main(boot.home, boot.home)
    note = T["refresh_failed"].format(message="ERROR: Could not find a version")
    assert kinds(boot) == ["pip", "web"] and boot.notes == [note]
    out = capsys.readouterr().out
    assert note in out and "Traceback" not in out
    assert (boot.home / "lib" / ".installed").read_text(encoding="utf-8") == "digest of the old requirements file"
    boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["pip", "web", "pip", "web"], "下次啟動再試一次"


def test_changed_requirements_on_a_platform_without_web_panel_does_nothing(boot, monkeypatch):
    mark_installed(boot, "digest of the old requirements file")
    monkeypatch.setattr(sys, "platform", "linux")
    boot.web = ImportError("No module named 'webview'")
    boot.main.main(boot.home, boot.home)
    assert "pip" not in kinds(boot)


def test_safe_mode_never_touches_lib(boot, monkeypatch):
    mark_installed(boot, "digest of the old requirements file")
    monkeypatch.setattr(sys, "argv", ["main.py", "--safe"])
    boot.main.main(boot.home, boot.home)
    assert kinds(boot) == ["tk"]


def test_unexpected_startup_error_is_a_plain_sentence_and_the_traceback_goes_to_the_log(home, monkeypatch, capsys):
    """體驗 1-02：啟動途中出了沒預料到的例外，終端機是一句人話；traceback 寫進 logs/iplot.log，不印在使用者眼前。"""
    main = load_main()

    def boom(home, kernel):
        raise RuntimeError("secret detail 123")

    monkeypatch.setattr(main, "main", boom)
    with pytest.raises(SystemExit) as ei:
        main.run(home, home)
    out = capsys.readouterr()
    assert ei.value.code == 1
    assert out.out.strip() == T["start_failed"] and "logs/iplot.log" in T["start_failed"] and "--safe" in T["start_failed"]
    assert "Traceback" not in out.out + out.err and "RuntimeError" not in out.out + out.err
    log = (home / "logs" / "iplot.log").read_text(encoding="utf-8")
    assert "RuntimeError: secret detail 123" in log and "Traceback" in log


def test_a_normal_exit_is_not_touched_by_the_startup_catch(home, monkeypatch):
    main = load_main()
    monkeypatch.setattr(main, "main", lambda home, kernel: (_ for _ in ()).throw(SystemExit("bye")))
    with pytest.raises(SystemExit) as ei:
        main.run(home, home)
    assert ei.value.code == "bye"
