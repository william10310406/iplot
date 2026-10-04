"""隨附的四個模組：靜態讀得到，用假的 Core 跑得通，不真的開 Finder、編輯器、Terminal。"""

import os
import subprocess
from pathlib import Path

import pytest

from core import actions
from core.app import App
from core.meta import read_meta
from core.runner import run_module
from core.scan import module_info

MODULES = Path(__file__).resolve().parents[1] / "modules"


def bundled(name):
    return module_info(MODULES / name, MODULES, "here")


def run_bundled(name, fake_core):
    info = bundled(name)
    return run_module(info, App(fake_core, info))


@pytest.fixture
def quiet(monkeypatch):
    """把會開視窗的動作全部換成記錄。"""
    calls = []
    for mod, fn in [(actions, "open"), (actions, "edit"), (actions, "reveal"), (actions, "terminal")]:
        monkeypatch.setattr(mod, fn, lambda *a, fn=fn: calls.append((fn, a)))
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: calls.append(("subprocess", argv)))
    monkeypatch.setattr(os, "execv", lambda exe, argv: calls.append(("execv", argv)))
    return calls


@pytest.mark.parametrize("name", ["開工", "打開核心原始碼", "開Terminal", "重新啟動"])
def test_bundled_meta(name):
    m = read_meta(MODULES / name / "iplot.py")
    assert (m.error, m.has_run) == (None, True) and m.description


def test_kaigong_runs_with_fake_core(fake_core, quiet):
    r = run_bundled("開工", fake_core)
    assert r.ok, r.error
    assert sum(1 for c in fake_core.calls if c[:2] == ("action", "open")) >= 2
    assert ("subprocess", ["open", "-a", "Terminal", str(fake_core.home)]) in quiet
    assert fake_core.view.logs


def test_restart_calls_execv(fake_core, quiet):
    assert run_bundled("重新啟動", fake_core).ok
    [(kind, argv)] = [c for c in quiet if c[0] == "execv"]
    assert argv[-1] == str(fake_core.home / "main.py")


def test_open_core_and_terminal_argv(fake_core, quiet):
    assert run_bundled("打開核心原始碼", fake_core).ok
    assert ("action", "open", fake_core.home / "core") in fake_core.calls
    assert run_bundled("開Terminal", fake_core).ok
    assert ("subprocess", ["open", "-a", "Terminal", str(fake_core.home)]) in quiet


def test_restart_execs_from_home_not_module_folder(fake_core, monkeypatch):
    # 腳本語意（D47）下執行期間的工作目錄是模組資料夾；execv 換掉程序前要先回 iPLoT 資料夾
    seen = []
    monkeypatch.setattr(os, "execv", lambda exe, argv: seen.append(os.getcwd()))
    assert run_bundled("重新啟動", fake_core).ok
    assert seen == [str(fake_core.home)]
