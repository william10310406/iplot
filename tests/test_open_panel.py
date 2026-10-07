"""工作坊模組「主控面板」（modules/主控面板）：app.run("主控面板") 打開面板，已經開著就叫到最前面（D82）。
ps、lsof、Popen、叫到最前面都換成假的：絕不真的開面板、不真的動別的程序。"""

import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest
from conftest import FakeApp

MODULE = Path(__file__).resolve().parents[1] / "modules" / "主控面板" / "iplot.py"
PS = "  101 /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 main.py\n  202 /usr/bin/python3 {home}/main.py\n"


@pytest.fixture
def panel_mod():
    spec = importlib.util.spec_from_file_location("open_panel_module", MODULE)
    mod = importlib.util.module_from_spec(spec)
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = old
    return mod


def nothing(*a, **k):
    pytest.fail(f"不該被呼叫：{a} {k}")


def go(mod, home, **kw):
    """open_panel 用假的 ps、lsof、Popen、activate；回 (app, 叫到前面的 pid 們, Popen 的呼叫)。"""
    app, activated, launched = FakeApp(home), [], []
    kw.setdefault("modules", {})
    kw.setdefault("ps", lambda: "")
    kw.setdefault("lsof", lambda pid: "")
    kw.setdefault("activate", lambda pid, platform: activated.append(pid) or True)
    kw.setdefault("popen", lambda argv, **k: launched.append((argv, k)))
    kw.setdefault("platform", "darwin")
    kw.setdefault("me", 999)
    mod.open_panel(app, home, **kw)
    return app, activated, launched


def test_in_panel_brings_itself_forward(panel_mod, home):
    app, activated, launched = go(panel_mod, home, modules={"ui.web": object()}, ps=nothing)
    assert activated == [None] and launched == [] and app.logs == ["主控面板已經開著"]


def test_in_the_safe_mode_panel_too(panel_mod, home):
    assert panel_mod.in_panel({"ui.tk": object()}) and not panel_mod.in_panel({"core.runner": object()})


def test_find_panel_by_absolute_path(panel_mod, home):
    assert panel_mod.find_panel(home, ps=lambda: PS.format(home=home), lsof=lambda pid: "", me=999) == 202


def test_find_panel_by_relative_main_py_and_cwd(panel_mod, home):
    first = PS.splitlines()[0] + "\n"
    found = panel_mod.find_panel(home, ps=lambda: first, lsof=lambda pid: f"p{pid}\nfcwd\nn{home}\n", me=999)
    assert found == 101


def test_find_panel_with_spaces_in_the_path(panel_mod, tmp_path):        # Review Focus 3
    home = tmp_path / "我的 iPLoT"
    home.mkdir()
    assert panel_mod.find_panel(home, ps=lambda: PS.format(home=home), lsof=lambda pid: "", me=999) == 202
    first = PS.splitlines()[0] + "\n"
    assert panel_mod.find_panel(home, ps=lambda: first, lsof=lambda pid: f"p{pid}\nfcwd\nn{home}\n", me=999) == 101


def test_find_panel_ignores_itself_and_other_iplots(panel_mod, home, tmp_path):
    other = tmp_path / "別的 iPLoT"
    other.mkdir()
    assert panel_mod.find_panel(home, ps=lambda: PS.format(home=home), lsof=lambda pid: "", me=202) is None
    assert panel_mod.find_panel(home, ps=lambda: PS.format(home=other), lsof=lambda pid: f"n{other}\n", me=999) is None
    assert panel_mod.find_panel(home, ps=lambda: "  7 /bin/zsh main.py\n  8 vim /x/main.py\n", lsof=nothing, me=1) is None


def test_open_panel_brings_the_running_one_forward(panel_mod, home):
    app, activated, launched = go(panel_mod, home, ps=lambda: PS.format(home=home))
    assert activated == [202] and launched == [] and app.logs == ["主控面板已經開著，叫到最前面了"]


def test_not_running_launches_detached(panel_mod, home):
    app, activated, launched = go(panel_mod, home)
    [(argv, kw)] = launched
    assert argv == [sys.executable, str(home / "main.py")] and kw["cwd"] == str(home)
    assert kw["start_new_session"] is True
    assert (kw["stdin"], kw["stdout"], kw["stderr"]) == (subprocess.DEVNULL,) * 3
    assert app.logs == ["打開主控面板"] and activated == []


def test_launch_failure_is_one_sentence(panel_mod, home):
    def broken(argv, **kw):
        raise OSError("x")

    app, _, _ = go(panel_mod, home, popen=broken)
    assert app.logs == ["打不開主控面板：x"]


def test_appkit_missing_still_logs(panel_mod, home):
    app, _, _ = go(panel_mod, home, ps=lambda: PS.format(home=home), activate=lambda pid, platform: False)
    assert app.logs == ["主控面板已經開著，但沒辦法把它叫到最前面"]


def test_elsewhere_launches_and_says_it_cannot_bring_forward(panel_mod, home):
    app, activated, launched = go(panel_mod, home, platform="linux", ps=nothing)
    assert len(launched) == 1 and activated == []
    assert app.logs == ["打開主控面板", "這個系統還不會把開著的面板叫到最前面"]


def test_elsewhere_in_the_panel_only_logs(panel_mod, home):
    app, activated, launched = go(panel_mod, home, platform="linux", modules={"ui.tk": object()})
    assert (activated, launched, app.logs) == ([], [], ["主控面板已經開著"])


def test_activate_is_false_elsewhere_or_without_appkit(panel_mod, monkeypatch):
    assert panel_mod.activate(123, platform="linux") is False
    monkeypatch.setitem(sys.modules, "AppKit", None)  # import AppKit 會丟 ImportError
    assert panel_mod.activate(123, platform="darwin", run=nothing) is False


def fake_appkit(answer):
    """假的 AppKit：NSRunningApplication 的 activateWithOptions_ 回 answer。"""
    target = types.SimpleNamespace(activateWithOptions_=lambda options: answer)
    running = types.SimpleNamespace(runningApplicationWithProcessIdentifier_=lambda pid: target,
                                    currentApplication=lambda: target)
    return types.SimpleNamespace(NSRunningApplication=running, NSApplicationActivateIgnoringOtherApps=2,
                                 __file__="/lib/AppKit/__init__.py")


def test_activate_directly_when_macos_allows_it(panel_mod, monkeypatch):
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit(True))
    assert panel_mod.activate(123, platform="darwin", run=nothing) is True
    assert panel_mod.activate(None, platform="darwin", run=nothing) is True


def test_activate_hands_over_to_a_plain_helper_when_refused(panel_mod, monkeypatch):
    """macOS 14 起，自己不在前面的 App 叫別人到前面會被拒絕；一般的 python 子程序叫就可以（Task 0 量過）。"""
    monkeypatch.setitem(sys.modules, "AppKit", fake_appkit(False))
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    assert panel_mod.activate(123, platform="darwin", run=run) is True
    [argv] = calls
    assert argv[0] == sys.executable and argv[1] == "-c" and argv[-2:] == ["/lib", "123"]
    assert panel_mod.activate(None, platform="darwin", run=lambda argv, **kw: subprocess.CompletedProcess(argv, 1)) \
        is False


def test_ps_is_called_with_a_utf8_locale(panel_mod, monkeypatch):
    """ps 在沒有設定 locale 的環境（從 Spotlight、Dock 開的程式就是）會把中文路徑寫成 M-fM^H…，
    <iPLoT>/main.py 永遠比不到（2026-10-07 在 Mac 上看到的）。"""
    seen = []

    def fake_run(argv, **kw):
        seen.append((argv, kw))
        return subprocess.CompletedProcess(argv, 0, "  1 python3 /我的 iPLoT/main.py\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert "我的" in panel_mod._ps()
    [(argv, kw)] = seen
    assert argv == ["ps", "-axww", "-o", "pid=,command="] and kw["env"]["LC_ALL"] == "en_US.UTF-8"
    assert kw["encoding"] == "utf-8"


def test_find_panel_matches_however_the_path_is_normalized(panel_mod, tmp_path):
    import unicodedata
    home = tmp_path / unicodedata.normalize("NFC", "ガイド iPLoT")
    home.mkdir()
    line = f"  5 python3 {unicodedata.normalize('NFD', str(home))}/main.py\n"
    assert panel_mod.find_panel(home, ps=lambda: line, lsof=nothing, me=1) == 5
