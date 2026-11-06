"""課程作業的骨架：模組掃得到、課程用的東西不進 git、不進核心的包、按下去列出這台電腦上的課，
以及 cw_support 的共用工具。"""

import shutil
import subprocess

import pytest
from cw_support import CW, ROOT, CwApp, FakePopen, load, make_course

from core.runner import run_module
from core.scan import module_info


@pytest.fixture(autouse=True)
def _no_install(monkeypatch):
    monkeypatch.setenv("CW_NO_INSTALL", "1")


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)


def _module_copy(tmp_path):
    """把 iplot.py 與框架複製到 tmp 的模組資料夾（不連同使用的時候長出來的東西）。"""
    mod = tmp_path / "modules" / "課程作業"
    mod.mkdir(parents=True)
    shutil.copy(CW / "iplot.py", mod / "iplot.py")
    shutil.copytree(CW / "框架", mod / "框架", ignore=shutil.ignore_patterns("__pycache__"))
    return mod


def _run(mod, tmp_path):
    app = CwApp(tmp_path)
    result = run_module(module_info(mod, mod.parent, "here"), app)
    assert result.error is None, result.error
    return app


def test_module_scans_with_icon():
    info = module_info(CW, CW.parent, "here")
    assert info.icon == "📚"
    assert info.error is None


@pytest.mark.parametrize("path", [
    "modules/課程作業/測試課/課程.py",
    "modules/課程作業/測試課/HK01/HK1.py",
])
def test_generated_things_are_ignored(path):
    assert _git("check-ignore", "-q", path).returncode == 0


@pytest.mark.parametrize("path", [
    "modules/課程作業/iplot.py",
    "modules/課程作業/框架/course.py",
    "modules/課程作業/作業類型/算完畫圖/coursework.py",
    "modules/課程作業/範例課程/科學計算/課程.py",
    "modules/課程作業/新增一門課/iplot.py",
    "modules/課程作業/加入範例課程/iplot.py",
])
def test_shipped_things_are_not_ignored(path):
    assert _git("check-ignore", "-q", path).returncode == 1


def test_export_ignored():
    # 目錄的規則（結尾斜線）只對目錄自己顯示 set，不會算到裡面的檔；git archive 看的也是目錄
    out = _git("check-attr", "export-ignore", "--", "modules/課程作業/").stdout
    assert out.strip().endswith("export-ignore: set")


def test_run_lists_courses(tmp_path):
    mod = _module_copy(tmp_path)
    make_course(mod, "課甲")
    make_course(mod, "課乙")
    app = _run(mod, tmp_path)
    assert len(app.logs) == 2
    assert all("還沒建" in line for line in app.logs)
    assert sorted(line.split("：")[0] for line in app.logs) == ["課乙", "課甲"]


def test_run_without_courses_says_how_to_start(tmp_path):
    app = _run(_module_copy(tmp_path), tmp_path)
    assert len(app.logs) == 1
    assert "新增一門課" in app.logs[0]


def test_run_shows_name_homework_count_and_venv(tmp_path):
    mod = _module_copy(tmp_path)
    course = make_course(mod, "資料夾名", NAME="顯示名")
    (course / ".venv").mkdir()
    for folder, code in (("HK01", "HK1"), ("HK02", "HK2")):
        (course / folder).mkdir()
        (course / folder / f"{code}.py").write_text("x = 1\n", encoding="utf-8")
    (course / "新增作業").mkdir()  # 按鈕的資料夾裡只有 iplot.py，不算作業
    (course / "新增作業" / "iplot.py").write_text("def run(app): pass\n", encoding="utf-8")
    app = _run(mod, tmp_path)
    assert app.logs == ["顯示名：2 份作業；.venv 已建"]


def test_run_ignores_folders_without_course_file(tmp_path):
    mod = _module_copy(tmp_path)
    (mod / "框架" / "不是課").mkdir()
    (mod / "亂放的").mkdir()
    app = _run(mod, tmp_path)
    assert "新增一門課" in app.logs[0]


def test_support_cwapp_answers_in_order_then_default(tmp_path):
    app = CwApp(tmp_path)
    app.answers_ask = ["甲", None]
    assert [app.ask("一", "d"), app.ask("二", "d"), app.ask("三", "d")] == ["甲", None, "d"]
    assert app.asks == [("一", "d"), ("二", "d"), ("三", "d")]
    app.edit(tmp_path / "a.py", 3)
    app.reveal(tmp_path)
    app.open(tmp_path / "b")
    assert (app.edits, app.revealed, app.opened) == (
        [(tmp_path / "a.py", 3)], [tmp_path], [tmp_path / "b"])
    assert app.choose_files() == [] and app.choose_folder() is None
    assert app.module.folder == tmp_path


def test_support_fake_popen_records_and_fails_on_demand():
    popen = FakePopen(fail=lambda argv: "bad" in argv, lines=["一行\n"])
    good = popen(["py", "ok"], cwd="x")
    bad = popen(["py", "bad"])
    assert (good.wait(), bad.wait()) == (0, 1)
    assert popen.calls == [(["py", "ok"], {"cwd": "x"}), (["py", "bad"], {})]
    assert list(good.stdout) == ["一行\n"]


def test_support_make_course_writes_literals_the_framework_can_read(tmp_path):
    folder = make_course(tmp_path, "課", CODE="Lab{n}", TYPES=["算完畫圖"])
    text = (folder / "課程.py").read_text(encoding="utf-8")
    assert "NAME = '課'" in text and "CODE = 'Lab{n}'" in text and "TYPES = ['算完畫圖']" in text


def test_support_load_leaves_no_trace(tmp_path):
    src = tmp_path / "m.py"
    src.write_text("X = 7\n", encoding="utf-8")
    import sys
    module = load(src, "cw_probe_module")
    assert module.X == 7
    assert "cw_probe_module" not in sys.modules
    assert not (tmp_path / "__pycache__").exists()
