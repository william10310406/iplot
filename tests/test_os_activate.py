"""作業系統模組的 os.activate（D164）：把另一個程序的視窗叫到最前面。原本主控面板、行事曆各抄一份，1.0 收到這裡。
AppKit 與子程序都換成假的：絕不真的動別的程序。"""

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest

FOLDER = Path(__file__).resolve().parents[1] / "modules" / "作業系統"


def load(name):
    spec = importlib.util.spec_from_file_location(f"os_activate_{name}", FOLDER / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def nothing(*a, **k):
    pytest.fail(f"不該被呼叫：{a} {k}")


def fake_appkit(answer):
    """假的 AppKit：NSRunningApplication 的 activateWithOptions_ 回 answer。"""
    target = types.SimpleNamespace(activateWithOptions_=lambda options: answer)
    running = types.SimpleNamespace(runningApplicationWithProcessIdentifier_=lambda pid: target)
    return types.SimpleNamespace(NSRunningApplication=running, NSApplicationActivateIgnoringOtherApps=2,
                                 __file__="/lib/AppKit/__init__.py")


@pytest.mark.parametrize("name", ["win", "linux"])
def test_other_systems_say_they_cannot(name):
    assert load(name).activate(None, 123) is False


def test_without_appkit_it_says_it_cannot(monkeypatch):
    monkeypatch.setitem(sys.modules, "AppKit", None)  # import AppKit 會丟 ImportError
    assert load("mac").activate(None, 123, run=nothing) is False


def test_directly_when_macos_allows_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit(True))
    assert load("mac").activate(None, 123, run=nothing) is True


def test_hands_over_to_a_plain_helper_when_refused(monkeypatch):
    """macOS 14 起，自己不在前面的 App 叫別人到前面會被拒絕；一般的 python 子程序叫就可以（2026-10-07 量過）。
    子程序的錯誤輸出不丟掉（R11）：沒有 stderr=，留在這個程序的錯誤輸出。"""
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit(False))
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        return subprocess.CompletedProcess(argv, 0)

    mac = load("mac")
    assert mac.activate(None, 123, run=run) is True
    [(argv, kw)] = calls
    assert argv[0] == sys.executable and argv[1] == "-c" and argv[-2:] == [str(Path("/lib")), "123"]
    assert "stderr" not in kw
    assert mac.activate(None, 123, run=lambda argv, **kw: subprocess.CompletedProcess(argv, 1)) is False
    assert mac.activate(None, 123, run=lambda argv, **kw: (_ for _ in ()).throw(OSError("x"))) is False


def test_the_module_provides_it():
    from core.meta import read_meta
    assert ("os.activate", "activate") in read_meta(FOLDER / "iplot.py").provides


# ── os.app_name（D166）：Dock 上的名字不是「Python」 ──

@pytest.mark.parametrize("name", ["win", "linux"])
def test_other_systems_leave_the_name_alone(name):
    assert load(name).app_name(None, "行事曆") is False


def test_app_name_sets_the_bundle_name_before_the_first_window(monkeypatch):
    info = {"CFBundleName": "Python"}
    bundle = types.SimpleNamespace(localizedInfoDictionary=lambda: None, infoDictionary=lambda: info)
    monkeypatch.setitem(sys.modules, "Foundation", types.SimpleNamespace(NSBundle=types.SimpleNamespace(
        mainBundle=lambda: bundle)))
    assert load("mac").app_name(None, "行事曆") is True and info["CFBundleName"] == "行事曆"


def test_app_name_without_pyobjc_says_it_cannot(monkeypatch):
    monkeypatch.setitem(sys.modules, "Foundation", None)
    assert load("mac").app_name(None, "行事曆") is False


def test_the_os_module_provides_app_name():
    from core.meta import read_meta
    meta = read_meta(FOLDER / "iplot.py")
    assert ("os.app_name", "app_name") in meta.provides and "os.app_name" in dict(meta.role_names)
