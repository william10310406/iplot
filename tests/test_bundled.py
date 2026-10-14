"""隨附的七個模組：靜態讀得到，用假的 Core 跑得通，不真的開檔案總管、編輯器、終端機，也不連網。
modules/作業系統 的後端（mac、win、linux）直接 import 進來驗參數，不真的啟動任何程式。"""

import contextlib
import ctypes
import importlib.util
import inspect
import os
import re
import shutil
import subprocess
import sys
import types
import urllib.parse
from pathlib import Path

import pytest

from core.app import App
from core.meta import read_meta
from core.runner import run_module
from core.scan import module_info

MODULES = Path(__file__).resolve().parents[1] / "modules"
NAMES = ("open", "edit", "reveal", "terminal", "trash", "requirements", "webview_ready")
OS_DIR = MODULES / "作業系統"


def bundled(name):
    return module_info(MODULES / name, MODULES, "here")


def run_bundled(name, fake_core):
    info = bundled(name)
    return run_module(info, App(fake_core, info))


def backend(name):
    """直接 import modules/作業系統/<name>.py，不經過 runner。不寫 .pyc：模組資料夾裡不留 __pycache__。"""
    spec = importlib.util.spec_from_file_location(name, OS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


@pytest.fixture
def launches(monkeypatch):
    """後端啟動外部程式都走 subprocess.Popen：換成記錄（argv, 其他參數）。"""
    seen = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: seen.append((argv, kw)))
    return seen


@pytest.fixture
def quiet(monkeypatch):
    """把會開視窗、會換掉程序的動作換成記錄。"""
    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: calls.append(("Popen", argv)))
    monkeypatch.setattr(os, "execv", lambda exe, argv: calls.append(("execv", argv)))
    return calls


@pytest.mark.parametrize("name", ["開工", "打開核心原始碼", "開Terminal", "重新啟動", "作業系統", "更新", "工作坊",
                                  "互通", "主控面板", "行事曆"])
def test_bundled_meta(name):
    m = read_meta(MODULES / name / "iplot.py")
    assert (m.error, m.has_run) == (None, True) and m.description


def test_mac_argv(launches):
    m, p = backend("mac"), Path("/x/a.txt")
    m.open(None, p)
    m.reveal(None, p)
    m.terminal(None, p)
    m.edit(None, p, None, 7)
    m.edit(None, p, ("code", "-g", "{file}:{line}"), 7)
    m.edit(None, p, ("code", "-g", "{file}:{line}"), None)
    s = str(p)  # 不寫死 "/x/a.txt"：在 Windows 的 runner 上 str(Path) 是反斜線
    assert [a for a, _ in launches] == [
        ["open", s], ["open", "-R", s], ["open", "-a", "Terminal", s],
        ["open", "-t", s], ["code", "-g", f"{s}:7"], ["code", "-g", f"{s}:1"]]


def test_mac_edit_folder_falls_back_to_open(launches, tmp_path):
    backend("mac").edit(None, tmp_path, ("code", "{file}"), 3)
    assert launches == [(["open", str(tmp_path)], {})]


def test_mac_trash_moves_and_suffixes(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    m = backend("mac")
    a = tmp_path / "x"
    a.write_text("1")
    dest1 = m.trash(None, a)
    b = tmp_path / "x"
    b.write_text("2")
    dest2 = m.trash(None, b)
    assert (dest1, dest2) == (tmp_path / ".Trash" / "x", tmp_path / ".Trash" / "x 2")
    assert dest2.read_text() == "2" and not (tmp_path / "x").exists()


def test_win_argv(launches, monkeypatch):
    w, p = backend("win"), "C:\\x\\a.txt"
    opened = []
    monkeypatch.setattr(os, "startfile", lambda path: opened.append(path), raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: {"wt": "C:\\wt.exe", "code": "C:\\code.cmd"}.get(name))
    w.open(None, Path(p))
    w.reveal(None, Path(p))
    w.terminal(None, Path(p))
    w.edit(None, Path(p), None, 1)
    w.edit(None, Path(p), ("code", "-g", "{file}:{line}"), 7)
    assert opened == [p]
    assert launches == [(["explorer", f"/select,{p}"], {}), (["wt", "-d", p], {}),
                        (["notepad", p], {}), (["C:\\code.cmd", "-g", f"{p}:7"], {})]


def test_win_terminal_without_wt_uses_cmd_new_console(launches, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    backend("win").terminal(None, Path("C:\\x"))
    assert launches == [(["cmd"], {"cwd": "C:\\x", "creationflags": 0x10})]


def test_win_edit_folder_falls_back_to_open(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(os, "startfile", lambda path: opened.append(path), raising=False)
    backend("win").edit(None, tmp_path, None, None)
    assert opened == [str(tmp_path)]


def test_win_trash_calls_shfileoperation(monkeypatch):
    seen = []

    class Shell32:
        def SHFileOperationW(self, ref):
            seen.append(ref._obj)
            return 0

    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(shell32=Shell32()), raising=False)
    assert backend("win").trash(None, Path("C:\\x\\y")) is None
    [op] = seen
    # c_wchar_p 讀回來到第一個 NUL 為止；雙 NUL 由 str(path) + "\0" 保證
    assert (op.wFunc, op.fFlags, op.pFrom) == (3, 0x454, "C:\\x\\y")


def test_win_trash_nonzero_is_oserror(monkeypatch):
    class Shell32:
        def SHFileOperationW(self, ref):
            return 2

    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(shell32=Shell32()), raising=False)
    with pytest.raises(OSError, match="資源回收筒拒絕：2"):
        backend("win").trash(None, Path("C:\\x\\y"))


def test_linux_argv(launches, monkeypatch):
    lx, p = backend("linux"), Path("/x/a.txt")
    monkeypatch.setattr(shutil, "which",
                        lambda name: "/usr/bin/gnome-terminal" if name == "gnome-terminal" else None)
    lx.open(None, p)
    lx.reveal(None, p)
    lx.edit(None, p, None, 1)
    lx.edit(None, p, ("code", "-g", "{file}:{line}"), 7)
    lx.terminal(None, p.parent)
    s, d = str(p), str(p.parent)
    assert launches == [(["xdg-open", s], {}), (["xdg-open", d], {}),
                        (["xdg-open", s], {}), (["code", "-g", f"{s}:7"], {}),
                        (["gnome-terminal", f"--working-directory={d}"], {"cwd": d})]


def test_linux_edit_folder_falls_back_to_open(launches, tmp_path):
    backend("linux").edit(None, tmp_path, ("code", "{file}"), 3)
    assert launches == [(["xdg-open", str(tmp_path)], {})]


def test_linux_no_terminal_is_oserror(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(OSError, match="xterm"):
        backend("linux").terminal(None, Path("/x"))


def test_linux_trash_writes_files_and_info(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    lx = backend("linux")
    trash = tmp_path / ".local" / "share" / "Trash"
    a = tmp_path / "x"
    a.write_text("1")
    d1 = lx.trash(None, a)
    b = tmp_path / "x"
    b.write_text("2")
    d2 = lx.trash(None, b)
    assert (d1, d2) == (trash / "files" / "x", trash / "files" / "x 2")
    info = (trash / "info" / "x.trashinfo").read_text(encoding="utf-8").splitlines()
    assert info[0] == "[Trash Info]" and info[1] == f"Path={urllib.parse.quote(str(tmp_path / 'x'))}"
    assert re.fullmatch(r"DeletionDate=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", info[2])
    assert (trash / "info" / "x 2.trashinfo").exists() and d2.read_text() == "2"


def test_backends_have_same_seven_functions():
    sigs = [{n: str(inspect.signature(getattr(backend(b), n))) for n in NAMES}
            for b in ("mac", "win", "linux")]
    assert sigs[0] == sigs[1] == sigs[2]
    assert all(isinstance(backend(b).NAME, str) for b in ("mac", "win", "linux"))


def test_backend_error_points_into_backend_file(fake_core, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    def boom(argv, **kw):
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    monkeypatch.setattr(subprocess, "Popen", boom)
    info = bundled("作業系統")
    r = run_module(info, App(fake_core, info), "open", (Path("/x"),))
    assert not r.ok and r.error.kind == "FileNotFoundError"
    assert r.error.file.name == "linux.py" and r.error.line and "xdg-open" in r.error.message


def test_selector_picks_backend_by_platform(fake_core, monkeypatch):
    for platform, expected in [("darwin", "macOS"), ("win32", "Windows"), ("linux", "Linux")]:
        monkeypatch.setattr(sys, "platform", platform)
        fake_core.view.events.clear()
        r = run_bundled("作業系統", fake_core)
        assert r.ok, r.error
        assert f"作業系統：{expected}" in fake_core.view.logs[-1]


def test_kaigong_runs_with_fake_core(fake_core, quiet):
    assert run_bundled("開工", fake_core).ok
    assert sum(1 for c in fake_core.calls if c[:2] == ("action", "open")) >= 2
    assert ("action", "terminal", fake_core.home) in fake_core.calls and fake_core.view.logs


def test_restart_calls_execv(fake_core, quiet):
    assert run_bundled("重新啟動", fake_core).ok
    [(kind, argv)] = [c for c in quiet if c[0] == "execv"]
    assert argv[-1] == str(fake_core.home / "main.py")


def test_open_core_and_terminal(fake_core, quiet):
    assert run_bundled("打開核心原始碼", fake_core).ok
    assert ("action", "open", fake_core.home / "core") in fake_core.calls
    assert run_bundled("開Terminal", fake_core).ok
    assert ("action", "terminal", fake_core.home) in fake_core.calls


def test_restart_execs_from_home_not_module_folder(fake_core, monkeypatch):
    # 腳本語意（D47）下執行期間的工作目錄是模組資料夾；execv 換掉程序前要先回 iPLoT 資料夾
    seen = []
    monkeypatch.setattr(os, "execv", lambda exe, argv: seen.append(os.getcwd()))
    assert run_bundled("重新啟動", fake_core).ok
    assert seen == [str(fake_core.home)]


def test_bundled_modules_have_icons():
    icons = {name: bundled(name).icon for name in ("開工", "打開核心原始碼", "開Terminal", "重新啟動", "作業系統",
                                                   "更新", "工作坊")}
    assert icons == {"開工": "🧭", "打開核心原始碼": "🧬", "開Terminal": "⌨️", "重新啟動": "🔄", "作業系統": "🖥️",
                     "更新": "⬆️", "工作坊": "🧰"}


@pytest.mark.parametrize("name, setting", [("更新", "UPDATE_URL"), ("工作坊", "WORKSHOP_URL")])
def test_update_and_workshop_do_nothing_until_a_url_is_set(name, setting, home, monkeypatch):
    """平常使用不需要網路：來源網址沒設定時，按下去只說一句怎麼設定，不連網、不開頁面、不寫任何檔案。"""
    import urllib.request

    from conftest import FakeApp

    def no_network(*args, **kwargs):
        raise AssertionError("沒設定網址卻去連網了")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    app = FakeApp(home)
    info = bundled(name)
    result = run_module(info, app)
    assert result.ok, result.error
    assert len(app.logs) == 1 and setting in app.logs[0] and "config.py" in app.logs[0]
    assert app.pages == [] and app.confirms == [] and list(home.rglob("*")) == [home / "modules"]


def test_shipped_config_points_at_the_workshop_site():
    """D71 修訂（D-d）：隨附的 config.py 直接帶正式網址（GitHub Pages 上的 iplot-workshop），剛拿到的 iPLoT 按「更新」
    「工作坊」就有東西；Config 的預設值仍是 None（上面那個測試），改回 None 就不連網。"""
    from core.core import load_config

    config, err = load_config(MODULES.parent / "config.py")
    base = "https://william10310406.github.io/iplot-workshop/"
    assert err is None
    assert (config.update_url, config.workshop_url) == (base + "update.json", base + "index.json")


def test_update_and_workshop_keep_their_logic_beside_iplot_py():
    """兩個模組都是「iplot.py 只串起來，做法在旁邊的檔」；工作坊的頁面零外部資源。"""
    assert (MODULES / "更新" / "update.py").is_file() and (MODULES / "工作坊" / "workshop.py").is_file()
    page = (MODULES / "工作坊" / "page.html").read_text(encoding="utf-8")
    assert "{rows}" in page and "http://" not in page and "https://" not in page


class FakeWinreg(types.ModuleType):
    """假的 winreg：present 是存在的（hive, 路徑）→ pv 的值；其餘 OpenKey 丟 OSError。"""

    HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER = "HKLM", "HKCU"

    def __init__(self, present):
        super().__init__("winreg")
        self.present, self.opened = present, []

    def OpenKey(self, hive, path):  # noqa: N802  真的 winreg 就叫這個名字
        self.opened.append((hive, path))
        if (hive, path) not in self.present:
            raise FileNotFoundError(2, "找不到機碼")
        return contextlib.nullcontext((hive, path))

    def QueryValueEx(self, key, name):  # noqa: N802
        return (self.present[key], 1)


WEBVIEW2 = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def test_requirements_and_ready_per_backend(monkeypatch):
    assert (backend("mac").requirements(None), backend("mac").webview_ready(None)) == ("web-mac.txt", None)
    assert backend("linux").requirements(None) == "" and "Linux" in backend("linux").webview_ready(None)
    assert "安全模式" not in backend("linux").webview_ready(None), "這句話後面接的是「已改用備用面板」"
    assert backend("win").requirements(None) == "web-win.txt"
    for present in ({("HKLM", "SOFTWARE\\WOW6432Node\\" + WEBVIEW2): "120.0.1"},
                    {("HKLM", "SOFTWARE\\" + WEBVIEW2): "120.0.1"},
                    {("HKCU", "Software\\" + WEBVIEW2): "120.0.1"}):
        monkeypatch.setitem(sys.modules, "winreg", FakeWinreg(present))
        assert backend("win").webview_ready(None) is None, present
    for missing in ({}, {("HKCU", "Software\\" + WEBVIEW2): "0.0.0.0"}, {("HKCU", "Software\\" + WEBVIEW2): ""}):
        monkeypatch.setitem(sys.modules, "winreg", FakeWinreg(missing))
        reason = backend("win").webview_ready(None)
        assert isinstance(reason, str) and "WebView2" in reason and "安全模式" not in reason, missing


def test_system_module_answers_through_core_action(fake_core, monkeypatch):
    """ui/install.py 用 core.action 問；這裡直接用 runner 跑那兩個名字，確認 iplot.py 有把它們接出來。"""
    monkeypatch.setattr(sys, "platform", "darwin")
    info = bundled("作業系統")
    assert run_module(info, App(fake_core, info), "requirements").value == "web-mac.txt"
    r = run_module(info, App(fake_core, info), "webview_ready")
    assert r.ok and r.value is None


CARRY = ("開工", "打開核心原始碼", "重新啟動", "開Terminal", "互通", "主控面板", "行事曆")


@pytest.mark.parametrize("name", CARRY)
def test_repo_modules_carry_the_interop_snippet(name):
    from core.text import TEMPLATE
    block = TEMPLATE[TEMPLATE.index("# ── 互通 ──"):TEMPLATE.rindex("# ── 互通 ──\n") + len("# ── 互通 ──\n")]
    assert block in (MODULES / name / "iplot.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["作業系統", "更新", "工作坊"])
def test_iplots_own_modules_stay_untouched(name):
    assert "# ── 互通 ──" not in (MODULES / name / "iplot.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["開工", "打開核心原始碼"])
def test_changed_workshop_modules_say_so_in_their_changelog(name):
    text = (MODULES / name / "CHANGELOG.md").read_text(encoding="utf-8")
    top = text[text.index("## ["):]
    assert top.startswith("## [0.5.1] - ") and "加上「互通」的那一小段：可以直接 python3 iplot.py。" in top.split("## [0.5.0]")[0]
