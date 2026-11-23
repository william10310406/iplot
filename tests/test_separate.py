"""「互通」的 separate.py：有頁面的模組在網頁面板裡按下時，經 run.py 另開一個程序開頁面，面板不會被卡住
（2026-11-18 研究助理回報：開著工作坊時回主控面板按別的都沒反應，關掉之後才一次跳出來）。
已經開著就叫到最前面；另開的程序、tkinter 面板、沒有 run.py、另開失敗時，照舊在這個程序裡開。"""

import ast
import errno
import importlib.util
import os
import subprocess
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEPARATE = ROOT / "modules" / "互通" / "separate.py"
WEB = {"ui.web": types.ModuleType("ui.web")}
TK = {"ui.web": types.ModuleType("ui.web"), "ui.tk": types.ModuleType("ui.tk")}
OUTSIDE: dict = {}
PS = "  101 /usr/bin/python3 {run} {folder}\n  202 /usr/bin/python3 /x/main.py\n"


def load_separate():
    """跟頁面模組一樣用檔案路徑載入（不靠 sys.path：別的模組的 sys.path[0] 是它自己的資料夾）。"""
    spec = importlib.util.spec_from_file_location("iplot_interop_separate_test", SEPARATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def never(*args, **kw):
    pytest.fail(f"不該被呼叫：{args} {kw}")


class Info:
    def __init__(self, folder, title):
        self.folder, self.title, self.name = folder, title, folder.name


class FakeApp:
    def __init__(self, home, folder, title="工作坊"):
        self.home, self.module, self.logs = home, Info(folder, title), []

    def log(self, text):
        self.logs.append(text)


class Child:
    """假的另開程序：poll() 是 None 表示還活著。"""

    def __init__(self, exited=None):
        self.pid, self.exited, self.terminated = 303, exited, False

    def poll(self):
        return self.exited

    def terminate(self):
        self.terminated = True


def launcher(folder, run_py, launched, up=True, child=None):
    """回 (popen, ps)：popen 記下參數；up 的話，另開的程序像真的一樣把 pid 寫進 .pid，ps 也看得到它。"""
    child = child or Child()

    def popen(argv, **kw):
        launched.append((argv, kw))
        if up:
            (folder / ".pid").write_text(str(child.pid), encoding="utf-8")
        return child

    def ps():
        return f"  {child.pid} /usr/bin/python3 {run_py} {folder}\n" if launched and up else ""

    return popen, ps


@pytest.fixture
def sep():
    return load_separate()


@pytest.fixture
def setup(tmp_path):
    home = tmp_path / "iPLoT"
    folder = home / "modules" / "工作坊"
    folder.mkdir(parents=True)
    run_py = home / "modules" / "互通" / "run.py"
    run_py.parent.mkdir(parents=True)
    run_py.write_text("", encoding="utf-8")
    return home, folder, run_py


def test_in_the_web_panel_it_launches_run_py_detached_and_says_so(sep, setup):
    home, folder, run_py = setup
    app, launched = FakeApp(home, folder), []
    popen, ps = launcher(folder, run_py, launched)
    here = sep.here(app, modules=WEB, ps=ps, popen=popen, activate=never, me=999, python="/py")
    [(argv, kw)] = launched
    assert here is False and argv == ["/py", str(run_py), str(folder)]
    assert kw["start_new_session"] is True and (kw["stdin"], kw["stdout"]) == (subprocess.DEVNULL,) * 2
    assert kw["stderr"].name == str(home / "logs" / "separate.log") and kw["stderr"].closed  # 交給 Popen 之後就關
    assert app.logs == ["在另一個視窗打開「工作坊」"]


@pytest.mark.parametrize("exited", [None, 1], ids=["一直沒起來", "先結束了"])
def test_when_the_separate_window_does_not_come_up_it_says_so_and_opens_here(sep, setup, exited):
    """D160 第 3 條：另開了不等於開起來了。等不到 .pid、或它先結束了，就停掉它、說一句、在這裡開。"""
    home, folder, run_py = setup
    app, launched, child, naps = FakeApp(home, folder), [], Child(exited), []
    popen, ps = launcher(folder, run_py, launched, up=False, child=child)
    here = sep.here(app, modules=WEB, ps=ps, popen=popen, activate=never, me=999, wait=0.3, sleep=naps.append)
    assert here is True and len(launched) == 1 and child.terminated
    assert app.logs == ["另開的視窗沒有開起來（原因記在 logs/separate.log），改在這裡打開「工作坊」；開著的期間，面板上按別的模組會等它關掉才跑"]
    assert (naps == []) if exited else naps  # 先結束了就不用等


def test_without_run_py_it_opens_here_as_before(sep, setup):
    home, folder, run_py = setup
    run_py.unlink()
    app = FakeApp(home, folder)
    assert sep.here(app, modules=WEB, ps=lambda: "", popen=never, activate=never, me=999) is True
    assert app.logs == []


def test_a_launch_that_fails_opens_here_and_says_why_in_chinese(sep, setup):
    home, folder, _ = setup
    app = FakeApp(home, folder)

    def popen(argv, **kw):
        raise OSError(errno.ENOENT, "No such file or directory")

    assert sep.here(app, modules=WEB, ps=lambda: "", popen=popen, activate=never, me=999) is True
    [line] = app.logs
    assert line.startswith("沒辦法另開視窗（找不到檔案或資料夾），改在這裡打開「工作坊」") and "No such" not in line


def test_in_its_own_process_it_claims_the_pid_and_opens_here(sep, setup):
    home, folder, _ = setup
    app, registered = FakeApp(home, folder), []
    assert sep.here(app, modules=OUTSIDE, ps=lambda: "", popen=never, activate=never, me=999,
                    at_exit=registered.append) is True
    assert (folder / ".pid").read_text(encoding="utf-8") == str(os.getpid()) and app.logs == []
    [cleanup] = registered
    cleanup()
    assert not (folder / ".pid").exists()


def test_a_pid_that_cannot_be_written_still_opens_here(sep, setup):
    home, folder, _ = setup
    (folder / ".pid").mkdir()  # 寫不進去（是個資料夾）
    app = FakeApp(home, folder)
    assert sep.here(app, modules=OUTSIDE, ps=lambda: "", popen=never, activate=never, me=999,
                    at_exit=never) is True


def test_the_tkinter_panel_opens_here_without_a_pid(sep, setup):
    home, folder, _ = setup
    app = FakeApp(home, folder)
    assert sep.here(app, modules=TK, ps=lambda: "", popen=never, activate=never, me=999, at_exit=never) is True
    assert not (folder / ".pid").exists()


@pytest.mark.parametrize("modules", [WEB, OUTSIDE], ids=["panel", "shortcut"])
def test_one_already_open_is_brought_forward_and_nothing_new_opens(sep, setup, modules):
    home, folder, run_py = setup
    (folder / ".pid").write_text("101", encoding="utf-8")
    app, activated = FakeApp(home, folder), []
    here = sep.here(app, modules=modules, ps=lambda: PS.format(run=run_py, folder=folder), popen=never,
                    activate=lambda pid, platform: activated.append(pid) or True, platform="darwin", me=999)
    assert here is False and activated == [101] and app.logs == ["「工作坊」已經開著"]


def test_one_already_open_that_will_not_come_forward_says_where_to_look(sep, setup):
    home, folder, run_py = setup
    (folder / ".pid").write_text("101", encoding="utf-8")
    app = FakeApp(home, folder)
    here = sep.here(app, modules=WEB, ps=lambda: PS.format(run=run_py, folder=folder), popen=never,
                    activate=lambda pid, platform: False, platform="darwin", me=999)
    assert here is False and app.logs == ["「工作坊」已經開著（在 Dock 上找 Python 的圖示）"]


def test_a_stale_or_reused_pid_counts_as_closed(sep, setup):
    home, folder, run_py = setup
    (folder / ".pid").write_text("202", encoding="utf-8")  # 202 還活著，但它是 main.py，不是這個模組的 run.py
    app, launched = FakeApp(home, folder), []
    popen, ps = launcher(folder, run_py, launched)
    here = sep.here(app, modules=WEB, ps=lambda: PS.format(run=run_py, folder=folder) + ps(), popen=popen,
                    activate=never, me=999)
    assert here is False and len(launched) == 1


def test_a_folder_whose_path_is_a_prefix_of_another_is_not_confused(sep, setup):
    home, folder, run_py = setup
    (folder / ".pid").write_text("101", encoding="utf-8")
    other = folder.with_name(folder.name + " 2")  # 「工作坊」是「工作坊 2」的前綴（行事曆 2 碰過，D89 的修訂）
    app, launched = FakeApp(home, folder), []
    popen, ps = launcher(folder, run_py, launched)
    sep.here(app, modules=WEB, ps=lambda: PS.format(run=run_py, folder=other) + ps(), popen=popen, activate=never, me=999)
    assert len(launched) == 1


def test_its_own_pid_is_not_already_open(sep, setup):
    home, folder, run_py = setup
    (folder / ".pid").write_text("101", encoding="utf-8")
    app = FakeApp(home, folder)
    assert sep.here(app, modules=OUTSIDE, ps=lambda: PS.format(run=run_py, folder=folder), popen=never,
                    activate=never, me=101, at_exit=lambda f: None) is True


def test_separate_reads_on_python_3_8_like_the_rest_of_interop():
    ast.parse(SEPARATE.read_text(encoding="utf-8"), feature_version=(3, 8))


def test_without_ps_a_fresh_pid_file_counts_as_up(sep, setup):
    """Windows 沒有 ps、venv 的 python.exe 又多一層程序（pid 對不上）：.pid 換成新的內容就算起來了。"""
    home, folder, run_py = setup
    (folder / ".pid").write_text("111", encoding="utf-8")  # 上一次留下的
    app, launched = FakeApp(home, folder), []
    popen, _ = launcher(folder, run_py, launched)
    assert sep.here(app, modules=WEB, ps=lambda: "", popen=popen, activate=never, me=999, wait=0.3) is False
