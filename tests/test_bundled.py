"""隨附的五個模組：靜態讀得到，用假的 Core 跑得通，不真的開檔案總管、編輯器、終端機。
modules/作業系統 的後端（mac、win、linux）直接 import 進來驗參數，不真的啟動任何程式。"""

import ctypes
import importlib.util
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

from core.app import App
from core.meta import read_meta
from core.runner import run_module
from core.scan import module_info

MODULES = Path(__file__).resolve().parents[1] / "modules"
NAMES = ("open", "edit", "reveal", "terminal", "trash")
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


@pytest.mark.parametrize("name", ["開工", "打開核心原始碼", "開Terminal", "重新啟動", "作業系統"])
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
    assert [a for a, _ in launches] == [
        ["open", "/x/a.txt"], ["open", "-R", "/x/a.txt"], ["open", "-a", "Terminal", "/x/a.txt"],
        ["open", "-t", "/x/a.txt"], ["code", "-g", "/x/a.txt:7"], ["code", "-g", "/x/a.txt:1"]]


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
