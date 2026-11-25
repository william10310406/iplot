"""每按一次另開一個程序（D161）：頁面開著時按別的模組要馬上開始跑；模組改全域狀態不影響別人；程序死掉變成錯誤。

這是討論區 #8 與「開行事曆後主控面板卡住」的常駐測試：以前驗收只看「另開的視窗有沒有開」，從來沒有一項是
「它開著的時候，再按別的模組會不會馬上動」。B 是沒寫任何另開程式的模組（像車車），只能靠核心。"""

import os
import sys
import threading
import time
from pathlib import Path

from conftest import FakeView, make_module

from core.core import Core
from core.scan import module_info
from core.types import DEFAULT_CONFIG

# 假的頁面模組：提供 app.page，不開視窗，等到 release 檔出現才回來（就像使用者還沒關掉視窗）
FAKE_PAGE = '''PROVIDES = {"app.page": "page"}
import pathlib, time
def page(app, title, html, api=None, owner=None):
    here = pathlib.Path(__file__).parent
    (here / ("opened-" + title)).write_text(str(time.time()))
    while not (here / ("release-" + title)).exists():
        time.sleep(0.02)
'''

OPENS_PAGE = 'def run(app):\n    app.page("A", "<p>a</p>")\n    print("A 關了")\n'
STARTS = ('import time, pathlib\n'
          'def run(app):\n    pathlib.Path(app.home, "b-started").write_text(repr(time.time()))\n    print("B 跑完")\n')


def setup(tmp_path):
    home = tmp_path / "iplot"
    modules = home / "modules"
    make_module(modules, "頁面", FAKE_PAGE)
    make_module(modules, "A", OPENS_PAGE)
    make_module(modules, "B", STARTS)
    view = FakeView()
    core = Core(home, DEFAULT_CONFIG, view, separate=True)
    core.rescan()
    return home, core, view


def info(home, name):
    return module_info(home / "modules" / name, (home / "modules").resolve(), "here")


def wait_for(path: Path, seconds: float = 20.0) -> None:
    end = time.monotonic() + seconds
    while not path.exists():
        assert time.monotonic() < end, f"等不到 {path.name}"
        time.sleep(0.02)


def test_another_module_starts_within_a_second_while_a_page_is_open(tmp_path):
    home, core, view = setup(tmp_path)
    results = {}
    a = threading.Thread(target=lambda: results.setdefault("A", core.press(info(home, "A"))))
    a.start()
    wait_for(home / "modules" / "頁面" / "opened-A")  # A 的頁面開著了

    pressed = time.time()
    b = core.press(info(home, "B"))
    started = float((home / "b-started").read_text())

    assert b.ok, b.error
    assert started - pressed < 1.0  # 1 秒內開始跑，不用等 A 的頁面關掉
    assert a.is_alive()  # A 還開著
    assert "B 跑完" in view.logs

    (home / "modules" / "頁面" / "release-A").write_text("")
    a.join(20)
    assert results["A"].ok, results["A"].error
    assert "A 關了" in view.logs


def test_global_state_a_module_changes_stays_in_its_own_process(tmp_path):
    home, core, view = setup(tmp_path)
    make_module(home / "modules", "C", 'import os, sys, builtins\n'
                'def run(app):\n    os.chdir("/")\n    sys.argv[:] = ["x"]\n    sys.path.insert(0, "/nowhere")\n'
                '    builtins.input = None\n    print(os.getpid())\n')
    cwd, argv, path = os.getcwd(), list(sys.argv), list(sys.path)

    result = core.press(info(home, "C"))

    assert result.ok, result.error
    assert int(result.output.strip()) != os.getpid()  # 真的在另一個程序跑
    assert (os.getcwd(), sys.argv, sys.path) == (cwd, argv, path)


def test_a_process_that_dies_becomes_an_error_and_the_panel_goes_on(tmp_path):
    home, core, view = setup(tmp_path)
    make_module(home / "modules", "D", 'import os\ndef run(app):\n    os._exit(3)\n')

    result = core.press(info(home, "D"))

    assert not result.ok
    assert result.error.kind == "WorkerDied"
    assert "3" in result.error.message
    assert view.reports == [result.error]
    assert core.press(info(home, "B")).ok


def test_app_calls_reach_the_panel_through_the_pipe(tmp_path):
    home, core, view = setup(tmp_path)
    view.answer = "小明"
    make_module(home / "modules", "E", 'def run(app):\n    app.log("嗨")\n    name = input("名字？")\n'
                '    app.memory["n"] = app.memory.get("n", 0) + 1\n    ok = app.confirm("好嗎？")\n'
                '    app.log(f"{name} {app.memory[\'n\']} {ok} {app.module.name} {app.api_version}")\n'
                '    return app.run("B").ok\n')

    first = core.press(info(home, "E"))
    second = core.press(info(home, "E"))

    assert first.ok and second.ok, (first.error, second.error)
    assert first.value is True  # app.run 在同一個工作程序裡跑 B，回 Result
    assert view.asks == ["名字？", "名字？"]
    assert "嗨" in view.logs
    assert "小明 1 True E 7" in view.logs and "小明 2 True E 7" in view.logs  # memory 跨次保留


def test_role_calls_from_the_panel_get_the_return_value(tmp_path):
    home, core, view = setup(tmp_path)
    make_module(home / "modules", "選單", 'PROVIDES = {"menu.module": "items"}\n'
                'def items(app, info):\n    return [("改名…", info.name)]\n')

    assert core.call("menu.module", info(home, "B")) == [("改名…", "B")]


def test_min_api_higher_than_ours_does_not_start_a_process(tmp_path):
    home, core, view = setup(tmp_path)
    make_module(home / "modules", "F", 'MIN_API = 99\ndef run(app):\n    print("不該跑")\n')

    result = core.press(info(home, "F"))

    assert not result.ok
    assert result.error.kind == "NeedsNewerIPLoT"
    assert "99" in result.error.message and "7" in result.error.message
