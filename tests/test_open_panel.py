"""工作坊模組「主控面板」（modules/主控面板）：app.run("主控面板") 打開面板，已經開著就叫到最前面（D82）。
ps、lsof、Popen、叫到最前面都換成假的：絕不真的開面板、不真的動別的程序。"""

import errno
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import FakeApp

MODULE = Path(__file__).resolve().parents[1] / "modules" / "主控面板" / "iplot.py"
PS = "  101 /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 main.py\n  202 /usr/bin/python3 {main}\n"


def ps_for(home):
    """假的 ps 輸出：202 是開著 home 那一份 iPLoT 的面板。main.py 的路徑用這個平台的分隔符組。"""
    return PS.format(main=home / "main.py")


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
    """open_panel 用假的 ps、lsof、Popen 與 app.call("os.activate")；回 (app, 問了 os.activate 的, Popen 的呼叫)。
    panel= 是 app.panel（開它的面板是哪一種），answer= 是 os.activate 回的。"""
    app, activated, launched = FakeApp(home), [], []
    app.panel, answer = kw.pop("panel", None), kw.pop("answer", True)
    app.call = lambda role, pid: (activated.append((role, pid)), answer)[1]  # 只有 os.activate 會被問
    kw.setdefault("ps", lambda: "")
    kw.setdefault("lsof", lambda pid: "")
    kw.setdefault("popen", lambda argv, **k: launched.append((argv, k)))
    kw.setdefault("platform", "darwin")
    kw.setdefault("me", 999)
    mod.open_panel(app, home, **kw)
    return app, activated, launched


@pytest.mark.parametrize("kind", ["網頁", "tkinter"])
def test_opened_by_a_panel_only_says_so(panel_mod, home, kind):
    """1.0 起每按一次都在面板開的工作程序裡跑（D161）：app.panel 有值，面板就是開這個程序的那一個，本來就在最前面。
    以前用 sys.modules 猜（R3），在工作程序裡猜不到，就去叫面板到最前面而失敗（2026-11-24 Mac 驗收）。"""
    app, activated, launched = go(panel_mod, home, panel=kind, ps=nothing)
    assert activated == [] and launched == [] and app.logs == ["主控面板已經開著"]


def test_find_panel_by_absolute_path(panel_mod, home):
    assert panel_mod.find_panel(home, ps=lambda: ps_for(home), lsof=lambda pid: "", me=999) == 202


def test_find_panel_by_relative_main_py_and_cwd(panel_mod, home):
    first = PS.splitlines()[0] + "\n"
    found = panel_mod.find_panel(home, ps=lambda: first, lsof=lambda pid: f"p{pid}\nfcwd\nn{home}\n", me=999)
    assert found == 101


def test_find_panel_with_spaces_in_the_path(panel_mod, tmp_path):        # Review Focus 3
    home = tmp_path / "我的 iPLoT"
    home.mkdir()
    assert panel_mod.find_panel(home, ps=lambda: ps_for(home), lsof=lambda pid: "", me=999) == 202
    first = PS.splitlines()[0] + "\n"
    assert panel_mod.find_panel(home, ps=lambda: first, lsof=lambda pid: f"p{pid}\nfcwd\nn{home}\n", me=999) == 101


def test_find_panel_ignores_itself_and_other_iplots(panel_mod, home, tmp_path):
    other = tmp_path / "別的 iPLoT"
    other.mkdir()
    assert panel_mod.find_panel(home, ps=lambda: ps_for(home), lsof=lambda pid: "", me=202) is None
    assert panel_mod.find_panel(home, ps=lambda: ps_for(other), lsof=lambda pid: f"n{other}\n", me=999) is None
    assert panel_mod.find_panel(home, ps=lambda: "  7 /bin/zsh main.py\n  8 vim /x/main.py\n", lsof=nothing, me=1) is None


def test_open_panel_brings_the_running_one_forward(panel_mod, home):
    app, activated, launched = go(panel_mod, home, ps=lambda: ps_for(home))
    assert activated == [("os.activate", 202)] and launched == [] and app.logs == ["主控面板已經開著，叫到最前面了"]


def test_not_running_launches_detached(panel_mod, home):
    app, activated, launched = go(panel_mod, home)
    [(argv, kw)] = launched
    assert argv == [sys.executable, str(home / "main.py")] and kw["cwd"] == str(home)
    assert kw["start_new_session"] is True
    assert (kw["stdin"], kw["stdout"]) == (subprocess.DEVNULL,) * 2 and kw["stderr"].name.endswith("separate.log")  # D160 第 3 條
    assert app.logs == ["打開主控面板"] and activated == []


def test_launch_failure_is_one_sentence(panel_mod, home):
    def broken(argv, **kw):
        raise OSError(errno.ENOENT, "No such file or directory")

    app, _, _ = go(panel_mod, home, popen=broken)
    assert app.logs == ["打不開主控面板：找不到 Python 或 iPLoT 的 main.py。確認 iPLoT 資料夾還在，再雙擊一次"]  # 體驗 7-08：中文原因、有下一步


def test_appkit_missing_still_logs(panel_mod, home):
    app, _, _ = go(panel_mod, home, ps=lambda: ps_for(home), answer=False)
    assert app.logs == ["主控面板已經開著，但沒辦法把它叫到最前面。到 Dock 點一下 Python 的圖示"]


def test_elsewhere_launches_and_says_it_cannot_bring_forward(panel_mod, home):
    app, activated, launched = go(panel_mod, home, platform="linux", ps=nothing)
    assert len(launched) == 1 and activated == []
    assert app.logs == ["打開主控面板", "這個系統還不會把開著的面板叫到最前面"]


def test_elsewhere_in_the_panel_only_logs(panel_mod, home):
    app, activated, launched = go(panel_mod, home, platform="linux", panel="tkinter")
    assert (activated, launched, app.logs) == ([], [], ["主控面板已經開著"])


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
    line = f"  5 python3 {unicodedata.normalize('NFD', str(home / 'main.py'))}\n"
    assert panel_mod.find_panel(home, ps=lambda: line, lsof=nothing, me=1) == 5
