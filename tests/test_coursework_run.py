"""作業那一格（A7、A8、A18 的 .py 那一半）：選 case、用課的 .venv 另開程序、--check 只警告、留作業檔的版本；
type.argv。Popen 一律是假的，不真的開程序；.venv 是 tmp 裡假的 bin/python（Windows 是 Scripts/python.exe）。"""

import json
import os
import shutil
import subprocess
import sys
import sysconfig
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cw_support import (
    CW,
    FRAMEWORK,
    TYPE_DIR,
    VENV_PY,
    CwApp,
    FakePopen,
    load,
    make_course,
    make_homework,
)

from core.runner import run_module
from core.scan import find_children, module_info

HAVE = ["numpy", "matplotlib"]  # 假的 .venv 裡「裝了」的
ROOT_SCI = CW.parent / "科學計算"  # 凍結的科學計算：只讀它的 v0 範例


@pytest.fixture(autouse=True)
def _no_install(monkeypatch):
    monkeypatch.setenv("CW_NO_INSTALL", "1")
    monkeypatch.delenv("CW_FROM_IPLOT", raising=False)


@pytest.fixture
def course_mod():
    return load(FRAMEWORK, "course")


@pytest.fixture
def kind():
    return load(TYPE_DIR / "type.py", "cw_type_算完畫圖")


def fake_venv(course):
    python = course / ".venv" / VENV_PY
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_text("", encoding="utf-8")
    return python


def popen_with(installed=HAVE, **kw):
    return FakePopen(lines=[json.dumps(installed)], **kw)


def template_homework(course, n=1):
    """照範本建第 n 份作業（跟「新增作業」一樣用 type.new），回傳作業檔。"""
    return load(TYPE_DIR / "type.py", "cw_type_算完畫圖").new(course / f"HK{n:02d}", f"HK{n}")


@pytest.fixture
def hw(tmp_path):
    """一門有 .venv 的課，一份照範本的 HK1（case-1、case-2）。回 (課, 作業檔, .venv 的 python)。"""
    course = make_course(tmp_path)
    file = template_homework(course)
    return course, file, fake_venv(course)


def press(course_mod, file, *answers, popen=None, now=None, confirms=(), **kw):
    app = CwApp(file.parent)
    app.answers_ask, app.answers = list(answers), list(confirms)
    popen = popen if popen is not None else popen_with()
    course_mod.homework_button(app, file.parent, popen=popen, now=now or datetime.now,
                               background=lambda job: job(), **kw)
    return app, popen


def windows(popen):
    """框架為了「開始跑之前就出錯」另開的文字視窗：coursework.py --show-text <標題> <文字>。"""
    return [argv for argv, _ in popen.calls if "--show-text" in argv]


def runs(popen, file):
    """真的跑作業的那幾次（不算問「裝了什麼」、建 venv、pip）。"""
    return [(argv, kw) for argv, kw in popen.calls if len(argv) > 1 and argv[1] == str(file)]


# ── 選 case 與另開程序（A7）──

def test_answer_2_runs_case_2_with_the_course_python(course_mod, hw):
    course, file, python = hw
    app, popen = press(course_mod, file, "2")
    [(argv, kw)] = runs(popen, file)
    assert argv == [str(python), str(file), "--case", "case-2"]
    assert kw["cwd"] == str(file.parent)
    assert kw["env"]["PYTHONPATH"] == str(TYPE_DIR) and kw["env"]["CW_FROM_IPLOT"] == "1"
    assert kw["env"]["PATH"] == os.environ["PATH"]  # 其他環境變數照帶
    assert kw["env"]["PYTHONIOENCODING"] == "utf-8"  # stderr 要讀回來給老師看（D142）
    assert kw["stderr"] == subprocess.PIPE
    assert app.logs[-1] == "HK1：case-2 的視窗開了（在 Dock 上找 Python）"


def test_answer_0_runs_all(course_mod, hw):
    _, file, python = hw
    app, popen = press(course_mod, file, "0")
    assert [argv for argv, _ in runs(popen, file)] == [[str(python), str(file), "--all"]]
    assert app.logs[-1] == "HK1：全部 的視窗開了（在 Dock 上找 Python）"


def test_the_prompt_lists_cases_and_ends_with_what_to_type(course_mod, hw):
    _, file, _ = hw
    app, _ = press(course_mod, file, None)
    [(prompt, default)] = app.asks
    assert default == "1"
    lines = prompt.splitlines()
    assert lines == ["HK1 要跑哪一個？", "1) case-1  半徑 1、角速度 1", "2) case-2  半徑 2、角速度 0.5", "0) 全部",
                     "打 1–2 跑一個 case，打 0 全部跑："]


def test_the_prompt_with_one_case_and_no_label(course_mod, tmp_path):
    course = make_course(tmp_path)
    fake_venv(course)
    file = make_homework(course, 1)  # CASES = {"case-1": dict(label="第一個")}
    file.write_text(file.read_text(encoding="utf-8").replace('dict(label="第一個")', "dict()"), encoding="utf-8")
    app, _ = press(course_mod, file, None)
    assert app.asks[0][0].splitlines()[1:] == ["1) case-1", "0) 全部", "打 1 跑這個 case，打 0 全部跑："]
    assert "1–1" not in app.asks[0][0]


def test_cancel_runs_nothing(course_mod, hw):
    _, file, _ = hw
    app, popen = press(course_mod, file, None)
    assert runs(popen, file) == [] and app.logs[-1] == "沒跑"


@pytest.mark.parametrize("answer", ["x", "", "3", "-1", "①", "²", "1.0"])
def test_not_a_number_in_range_says_so_and_runs_nothing(course_mod, hw, answer):
    _, file, _ = hw
    app, popen = press(course_mod, file, answer)
    assert runs(popen, file) == []
    assert "0 到 2" in app.logs[-1] and "沒跑" in app.logs[-1]


def test_spaces_around_the_number_are_fine(course_mod, hw):
    _, file, _ = hw
    _, popen = press(course_mod, file, " 1 ")
    assert runs(popen, file)[0][0][-2:] == ["--case", "case-1"]


def test_unreadable_cases_say_r7_and_run_nothing(course_mod, hw):
    _, file, _ = hw
    file.write_text(file.read_text(encoding="utf-8").replace('"case-2": dict', "CASE_2: dict", 1),  # 鍵是變數
                    encoding="utf-8")
    app, popen = press(course_mod, file)
    assert app.asks == [] and runs(popen, file) == []
    assert any(line.startswith("R7") for line in app.logs) and "沒跑" in app.logs[-1]


def test_no_cases_runs_straight_away_without_asking(course_mod, hw):
    _, file, python = hw
    text = file.read_text(encoding="utf-8")
    start = text.index("CASES = {")
    end = text.index("}\n", start) + 2
    file.write_text(text[:start] + "CASES = {}\n" + text[end:], encoding="utf-8")
    app, popen = press(course_mod, file)
    assert app.asks == []
    assert [argv for argv, _ in runs(popen, file)] == [[str(python), str(file), "--all"]]


# ── --check 在 iPLoT 裡只警告（D131、D141）──

def test_check_problems_are_logged_and_it_still_runs(course_mod, hw):
    _, file, _ = hw
    text = file.read_text(encoding="utf-8")
    text = text.replace("def stats(run):", "import scipy\n\n\ndef stats(run):", 1)  # R12：不在對照表，只警告
    text = text.replace("def stats(run):", "def stats(run):\n    open(\"out.txt\", \"w\")", 1)  # R23：擋
    file.write_text(text, encoding="utf-8")
    app, popen = press(course_mod, file, "1")
    assert len(runs(popen, file)) == 1
    blocked = [line for line in app.logs if line.startswith("✗ R23 第 ")]
    warned = [line for line in app.logs if line.startswith("⚠ R12 第 ")]
    assert len(blocked) == 1 and len(warned) == 1 and "scipy" in warned[0]
    note = app.logs[max(app.logs.index(warned[0]), app.logs.index(blocked[0])) + 1]  # 問題都列完之後的那一句
    assert "照跑" in note and "檢查與打包" in note


def test_only_warnings_say_packing_is_not_blocked_either(course_mod, hw):
    _, file, _ = hw
    file.write_text(file.read_text(encoding="utf-8").replace("def stats(run):", "import scipy\n\n\ndef stats(run):", 1),
                    encoding="utf-8")
    app, _ = press(course_mod, file, "1")
    i = next(i for i, line in enumerate(app.logs) if line.startswith("⚠ R12"))
    assert "打包也不擋" in app.logs[i + 1]


def test_a_clean_homework_logs_no_check_lines(course_mod, hw):
    _, file, _ = hw
    app, _ = press(course_mod, file, "1")
    assert not [line for line in app.logs if line[:1] in "✗⚠"]


# ── 不是 v2 的作業檔：列問題、不跑 ──

def test_syntax_error_lists_r27_and_runs_nothing(course_mod, hw):
    _, file, _ = hw
    file.write_text(file.read_text(encoding="utf-8").replace("def compute(case):", "def compute(case:", 1),
                    encoding="utf-8")
    app, popen = press(course_mod, file)
    assert app.asks == [] and app.confirms == [] and popen.calls == []
    assert any(line.startswith("✗ R27 第 ") for line in app.logs)
    assert "沒跑" in app.logs[-1] and "v2" in app.logs[-1]


def test_v0_file_says_how_to_turn_it_into_v2(course_mod, hw):
    _, file, _ = hw
    v0 = (ROOT_SCI / "examples" / "HK2.py").read_text(encoding="utf-8")
    file.write_text(v0, encoding="utf-8")
    app, popen = press(course_mod, file)
    assert popen.calls == [] and app.asks == []
    assert "沒跑" in app.logs[-1] and "hk_page" in app.logs[-1] and "coursework" in app.logs[-1]


def test_unreadable_homework_file_is_one_sentence(course_mod, hw, monkeypatch, kind):
    _, file, _ = hw

    def boom(path):
        raise PermissionError(13, "Permission denied")

    app = CwApp(file.parent)
    real = course_mod.load_type
    monkeypatch.setattr(course_mod, "load_type", lambda name, fw: _with(real(name, fw), classify=boom))
    course_mod.homework_button(app, file.parent, popen=popen_with())
    assert len(app.logs) == 1 and "讀不了 HK1.py" in app.logs[0] and "Traceback" not in app.logs[0]


def _with(module, **attrs):
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def test_course_button_also_catches_unreadable_files(course_mod, hw, monkeypatch):
    course, file, _ = hw

    def boom(path):
        raise PermissionError(13, "Permission denied")

    real = course_mod.load_type
    monkeypatch.setattr(course_mod, "load_type", lambda name, fw: _with(real(name, fw), classify=boom))
    app = CwApp(course)
    course_mod.course_button(app, course, popen=popen_with())
    assert any("讀不了 HK1.py" in line for line in app.logs)


def test_folder_without_a_homework_file(course_mod, tmp_path):
    course = make_course(tmp_path)
    (course / "HK01").mkdir()
    app = CwApp(course)
    course_mod.homework_button(app, course / "HK01", popen=popen_with())
    assert len(app.logs) == 1 and "HK01" in app.logs[0] and "作業檔" in app.logs[0]


def test_folder_outside_a_course(course_mod, tmp_path):
    (tmp_path / "HK01").mkdir()
    app = CwApp(tmp_path)
    course_mod.homework_button(app, tmp_path / "HK01", popen=popen_with())
    assert len(app.logs) == 1 and "課程.py" in app.logs[0]


# ── 套件與 .venv ──

def test_missing_package_asks_once_and_cancel_runs_nothing(course_mod, hw, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    _, file, _ = hw
    app, popen = press(course_mod, file, "1", popen=popen_with(["numpy"]), confirms=[False])
    assert len(app.confirms) == 1 and "matplotlib" in app.confirms[0] and "numpy" not in app.confirms[0]
    assert runs(popen, file) == [] and app.asks == [] and "沒跑" in app.logs[-1]
    assert not [argv for argv, _ in popen.calls if "pip" in argv]


def test_missing_package_installs_then_runs(course_mod, hw, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    _, file, python = hw
    app, popen = press(course_mod, file, "1", popen=popen_with(["numpy"]))
    pips = [argv for argv, _ in popen.calls if "pip" in argv]
    assert pips == [[str(python), "-m", "pip", "install", "--no-input", "--disable-pip-version-check", "matplotlib"]]
    assert len(runs(popen, file)) == 1 and any("已裝 matplotlib" in line for line in app.logs)


def test_failed_install_runs_nothing(course_mod, hw, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    _, file, _ = hw
    popen = FakePopen(fail=lambda argv: "pip" in argv, lines=[json.dumps(["numpy"])])
    app, _ = press(course_mod, file, "1", popen=popen)
    assert runs(popen, file) == [] and "裝不了 matplotlib" in "".join(app.logs) and "沒跑" in app.logs[-1]


def test_no_venv_asks_builds_it_and_installs(course_mod, tmp_path, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    course = make_course(tmp_path)
    file = template_homework(course)

    def popen(argv, **kw):  # 建 venv 那一次真的放一個假的 python，後面才找得到
        if argv[1:3] == ["-m", "venv"]:
            fake_venv(course)
        return fake(argv, **kw)

    fake = popen_with([])
    app = CwApp(file.parent)
    app.answers_ask = ["1"]
    course_mod.homework_button(app, file.parent, popen=popen)
    assert len(app.confirms) == 1 and "還沒建" in app.confirms[0] and "matplotlib、numpy" in app.confirms[0]  # requires 是集合：照字母排
    venv = [argv for argv, _ in fake.calls if argv[1:3] == ["-m", "venv"]]
    assert venv == [[venv[0][0], "-m", "venv", str(course / ".venv")]]
    assert [argv[-1] for argv, _ in fake.calls if "pip" in argv] == ["matplotlib", "numpy"]
    assert len(runs(fake, file)) == 1


def test_no_venv_and_nothing_to_install_still_asks_to_build_it(course_mod, tmp_path, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    course = make_course(tmp_path)
    file = template_homework(course)
    file.write_text(file.read_text(encoding="utf-8").replace('REQUIRES = ["numpy", "matplotlib"]', "REQUIRES = []", 1),
                    encoding="utf-8")
    app, popen = press(course_mod, file, "1", confirms=[False])
    assert len(app.confirms) == 1 and "還沒建" in app.confirms[0]
    assert "並裝 matplotlib 嗎？" in app.confirms[0] and "開視窗用的" in app.confirms[0]  # D145：殼開視窗要它
    assert popen.calls == [] and "沒跑" in app.logs[-1]


def text_only(file):
    """把照範本的作業改成 REQUIRES = []（純文字作業：只用標準庫）。"""
    file.write_text(file.read_text(encoding="utf-8").replace('REQUIRES = ["numpy", "matplotlib"]', "REQUIRES = []", 1),
                    encoding="utf-8")
    return file


def test_text_only_homework_still_gets_matplotlib_into_the_course_venv(course_mod, hw, monkeypatch):
    """D145：課的 .venv 一律裝 matplotlib（殼在 iPLoT 裡用它開文字視窗），不管 REQUIRES 有沒有寫。"""
    monkeypatch.delenv("CW_NO_INSTALL")
    _, file, python = hw
    text_only(file)
    app, popen = press(course_mod, file, "1", popen=popen_with(["numpy"]))
    assert len(app.confirms) == 1 and "matplotlib" in app.confirms[0] and "開視窗用的" in app.confirms[0]
    assert [argv[-1] for argv, _ in popen.calls if "pip" in argv] == ["matplotlib"]
    assert len(runs(popen, file)) == 1


def test_text_only_homework_with_matplotlib_there_asks_nothing(course_mod, hw, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    _, file, _ = hw
    app, popen = press(course_mod, text_only(file), "1")
    assert app.confirms == [] and len(runs(popen, file)) == 1


def test_no_install_with_something_missing_says_so_and_runs_nothing(course_mod, hw):
    _, file, _ = hw
    app, popen = press(course_mod, file, "1", popen=popen_with(["numpy"]))
    assert app.confirms == [] and runs(popen, file) == []
    assert "CW_NO_INSTALL" in app.logs[-1] and "matplotlib" in app.logs[-1]


def test_no_install_without_a_venv_runs_nothing(course_mod, tmp_path):
    course = make_course(tmp_path)
    file = template_homework(course)
    app, popen = press(course_mod, file, "1")
    assert popen.calls == [] and app.confirms == [] and "CW_NO_INSTALL" in app.logs[-1]


def test_only_on_package_on_the_wrong_machine_runs_nothing(course_mod, tmp_path):
    course = make_course(tmp_path, ONLY_ON={"mlx-lm": "apple-silicon"})
    fake_venv(course)
    file = template_homework(course)
    file.write_text(file.read_text(encoding="utf-8").replace('"matplotlib"]', '"matplotlib", "mlx-lm"]', 1),
                    encoding="utf-8")
    app, popen = press(course_mod, file, "1", apple_silicon=False)
    assert runs(popen, file) == [] and app.confirms == [] and app.asks == []
    assert "mlx-lm" in app.logs[-1] and "Apple Silicon" in app.logs[-1] and "HK1" in app.logs[-1]
    app, popen = press(course_mod, file, "1", popen=popen_with(HAVE + ["mlx-lm"]), apple_silicon=True)
    assert len(runs(popen, file)) == 1


# ── 面板程序不執行作業檔（A8）──

@pytest.fixture
def mod(tmp_path):
    root = tmp_path / "modules" / "課程作業"
    root.mkdir(parents=True)
    for name in ("框架", "作業類型", "範例課程", "新增一門課", "加入範例課程"):
        shutil.copytree(CW / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def test_pressing_the_stub_never_executes_the_homework(course_mod, mod, tmp_path, monkeypatch):
    app = CwApp(tmp_path)
    app.answers_ask = ["測試課"]
    course_mod.new_course(app, mod)
    course = mod / "測試課"
    course_mod.new_homework(CwApp(tmp_path), course)
    fake_venv(course)
    file = course / "HK01" / "HK1.py"
    text = file.read_text(encoding="utf-8").replace("# ── 從這裡開始是作業 ──",
                                                    "# ── 從這裡開始是作業 ──\nimport zz_不存在\nopen(\"寫了.txt\", \"w\")", 1)
    file.write_text(text, encoding="utf-8")
    fake = popen_with()
    monkeypatch.setattr(subprocess, "Popen", fake)  # 墊片每次重讀框架，預設的 popen 在那時才取
    monkeypatch.chdir(file.parent)
    app = CwApp(tmp_path)
    app.answers_ask = ["1"]
    result = run_module(module_info(file.parent, mod, "child"), app)
    assert result.error is None, result.error
    assert not (file.parent / "寫了.txt").exists() and not (tmp_path / "寫了.txt").exists()
    assert len(runs(fake, file)) == 1
    assert any(line.startswith("⚠ R12") and "zz_不存在" in line for line in app.logs)


def test_example_hk6_stub_runs_case_1(course_mod, mod, tmp_path, monkeypatch):
    course_mod.add_example(CwApp(tmp_path), mod)
    course = mod / "科學計算"
    python = fake_venv(course)
    fake = popen_with()
    monkeypatch.setattr(subprocess, "Popen", fake)
    app = CwApp(tmp_path)
    app.answers_ask = ["1"]
    result = run_module(module_info(course / "HK06", mod, "child"), app)
    assert result.error is None, result.error
    file = course / "HK06" / "HK6.py"
    assert [argv for argv, _ in runs(fake, file)] == [[str(python), str(file), "--case", "case-1"]]
    assert app.asks[0][0].splitlines()[0] == "HK6 要跑哪一個？"


# ── 作業檔的版本（D135，A18 的 .py 那一半）──

def clock(start=datetime(2026, 11, 6, 9, 0, 0)):
    ticks = iter(start + timedelta(minutes=i) for i in range(1000))
    return lambda: next(ticks)


def test_snapshot_saves_once_until_the_file_changes(course_mod, hw):
    _, file, _ = hw
    now = clock()
    first = course_mod.snapshot_homework(file, now=now)
    assert first == file.parent / ".版本" / "HK1_2026-11-06_090000.py" and first.read_bytes() == file.read_bytes()
    assert course_mod.snapshot_homework(file, now=now) is None
    file.write_text(file.read_text(encoding="utf-8") + "# 改了\n", encoding="utf-8")
    second = course_mod.snapshot_homework(file, now=now)
    assert second is not None and second.read_bytes() == file.read_bytes()


def test_snapshot_same_second_gets_a_number(course_mod, hw):
    _, file, _ = hw
    stamp = datetime(2026, 11, 6, 9, 0, 0)
    course_mod.snapshot_homework(file, now=lambda: stamp)
    file.write_text("# 改了\n", encoding="utf-8")
    again = course_mod.snapshot_homework(file, now=lambda: stamp)
    assert again.name == "HK1_2026-11-06_090000_1.py"
    file.write_text("# 又改了\n", encoding="utf-8")
    assert course_mod.snapshot_homework(file, now=lambda: stamp).name == "HK1_2026-11-06_090000_2.py"
    assert course_mod.snapshot_homework(file, now=lambda: stamp) is None  # 跟最新的（_2）一樣


def test_snapshot_keeps_the_newest_20_and_leaves_other_files_alone(course_mod, hw):
    _, file, _ = hw
    versions = file.parent / ".版本"
    versions.mkdir()
    others = [versions / "HK1_2026-01-01_000000_學生包.zip", versions / "我的筆記.py", versions / "HK2_2020-01-01_000000.py",
              versions / "HK1_舊的.py"]
    for other in others:
        other.write_bytes(b"keep")
    now = clock()
    made = []
    for i in range(21):
        file.write_text(f"# 第 {i} 版\n", encoding="utf-8")
        made.append(course_mod.snapshot_homework(file, now=now))
    left = sorted(p for p in versions.glob("HK1_????-??-??_??????.py"))
    assert len(left) == 20 and made[0] not in left and made[-1] in left
    assert all(other.read_bytes() == b"keep" for other in others)


def test_pressing_the_button_snapshots_before_anything_else(course_mod, hw):
    _, file, _ = hw
    now = clock()
    press(course_mod, file, None, now=now)
    press(course_mod, file, None, now=now)
    assert len(list((file.parent / ".版本").glob("*.py"))) == 1
    file.write_text(file.read_text(encoding="utf-8") + "# 改了\n", encoding="utf-8")
    press(course_mod, file, None, now=now)
    assert len(list((file.parent / ".版本").glob("*.py"))) == 2


def test_versions_folder_is_not_a_panel_child(course_mod, mod, tmp_path):
    course_mod.add_example(CwApp(tmp_path), mod)
    folder = mod / "科學計算" / "HK06"
    course_mod.snapshot_homework(folder / "HK6.py")
    assert (folder / ".版本").is_dir()
    assert all(".版本" not in str(child.folder) for child in find_children(folder, mod))


# ── type.argv ──

def test_type_argv(kind, tmp_path):
    file, python = tmp_path / "HK1.py", tmp_path / ".venv" / VENV_PY
    env = {"PYTHONPATH": str(TYPE_DIR), "CW_FROM_IPLOT": "1", "PYTHONIOENCODING": "utf-8"}
    assert kind.argv(file, python, "case-2") == ([str(python), str(file), "--case", "case-2"], env)
    assert kind.argv(file, python, None) == ([str(python), str(file), "--all"], env)



# ── 開始跑之前就出錯（D142）：框架讀子程序的 stderr，結束碼不是 0、殼又沒開過錯誤視窗時，開一個文字視窗 ──

def test_failure_before_main_opens_a_window_with_the_last_40_lines(course_mod, hw):
    _, file, python = hw
    err = [f"雜訊 {i}\n" for i in range(60)] + ["Traceback (most recent call last):\n", "ZeroDivisionError: division by zero\n"]
    popen = popen_with(fail=lambda argv: argv[1:2] == [str(file)], stderr=err)
    press(course_mod, file, "1", popen=popen)
    [argv] = windows(popen)
    assert argv[:3] == [str(python), str(TYPE_DIR / "coursework.py"), "--show-text"] and argv[3] == "HK1"
    text = argv[4]
    lines = text.splitlines()
    assert lines[0] == "HK1 在開始跑之前就出錯了，下面是 Python 的錯誤訊息："
    assert lines[1] == "" and lines[2:] == [line.rstrip("\n") for line in err[-40:]]


def test_a_clean_exit_opens_no_window(course_mod, hw):
    _, file, _ = hw
    popen = popen_with(stderr=["UserWarning: 只是警告\n"])
    press(course_mod, file, "1", popen=popen)
    assert windows(popen) == []


def test_no_window_when_the_shell_already_opened_one(course_mod, hw, kind):
    _, file, _ = hw
    mark = kind.shell().SHOWN_MARK
    popen = popen_with(fail=lambda argv: argv[1:2] == [str(file)], stderr=["前面\n", mark + "\n", "後面\n"] + ["x\n"] * 50)
    press(course_mod, file, "1", popen=popen)
    assert windows(popen) == []  # 記號在最後 40 行之外也算


def test_failure_without_any_stderr_still_says_so(course_mod, hw):
    _, file, _ = hw
    popen = popen_with(fail=lambda argv: argv[1:2] == [str(file)])
    press(course_mod, file, "1", popen=popen)
    [argv] = windows(popen)
    assert argv[4].splitlines()[0].startswith("HK1 在開始跑之前就出錯了") and "結束碼 1" in argv[4]


def test_the_watch_runs_in_the_background_by_default(course_mod, hw, monkeypatch):
    _, file, _ = hw
    started = []

    class Thread:
        def __init__(self, target, daemon):
            started.append(daemon)

        def start(self):
            pass

    monkeypatch.setattr(course_mod.threading, "Thread", Thread)
    app = CwApp(file.parent)
    app.answers_ask = ["1"]
    popen = popen_with(fail=lambda argv: argv[1:2] == [str(file)], stderr=["boom\n"])
    course_mod.homework_button(app, file.parent, popen=popen)
    assert started == [True] and windows(popen) == []  # 沒有等子程序：面板馬上回來


# ── D145：殼開不了視窗時交過來的段落，框架放進面板的訊息區 ──

def block(kind, *lines):
    shell = kind.shell()
    return [shell.HANDED_OVER + "\n", *(line + "\n" for line in lines), shell.HANDED_OVER_END + "\n"]


def test_text_the_shell_hands_over_goes_to_the_message_area(course_mod, hw, kind):
    _, file, _ = hw
    popen = popen_with(stderr=["雜訊\n", *block(kind, "HK1 — case-1：視窗開不了（x），內容放在這裡：", "HK1 範例", "結果是 3")])
    app, _ = press(course_mod, file, "1", popen=popen)
    assert app.logs[-3:] == ["HK1 — case-1：視窗開不了（x），內容放在這裡：", "HK1 範例", "結果是 3"]
    assert windows(popen) == []


def test_a_handed_over_error_is_logged_and_no_error_window_opens(course_mod, hw, kind):
    _, file, _ = hw
    mark = kind.shell().SHOWN_MARK
    popen = popen_with(fail=lambda argv: argv[1:2] == [str(file)],
                       stderr=[*block(kind, "標題：視窗開不了（x），內容放在這裡：", "case-1 出錯了：", "ValueError: 壞"), mark + "\n"])
    app, _ = press(course_mod, file, "1", popen=popen)
    assert app.logs[-1] == "ValueError: 壞" and windows(popen) == []


def test_when_the_error_window_cannot_open_either_its_text_goes_to_the_message_area(course_mod, hw, kind):
    _, file, _ = hw
    fake = popen_with(fail=lambda argv: argv[1:2] == [str(file)], stderr=["ZeroDivisionError: division by zero\n"])

    def popen(argv, **kw):
        if "--show-text" in argv:  # 錯誤視窗的那個程序也開不了視窗：它把同一段交過來
            fake.calls.append((list(argv), kw))
            return FakePopen(stderr=block(kind, "HK1：視窗開不了（x），內容放在這裡：", *argv[4].splitlines()))(argv, **kw)
        return fake(argv, **kw)

    app, _ = press(course_mod, file, "1", popen=popen)
    assert app.logs[-1] == "ZeroDivisionError: division by zero" and len(windows(fake)) == 1
    assert "HK1 在開始跑之前就出錯了，下面是 Python 的錯誤訊息：" in app.logs


def test_when_the_error_window_cannot_even_start_the_error_goes_to_the_message_area(course_mod, hw):
    _, file, _ = hw
    fake = popen_with(fail=lambda argv: argv[1:2] == [str(file)], stderr=["NameError: x\n"])

    def popen(argv, **kw):
        if "--show-text" in argv:
            raise FileNotFoundError(2, "No such file or directory", argv[0])
        return fake(argv, **kw)

    app, _ = press(course_mod, file, "1", popen=popen)
    assert app.logs[-2:] == ["HK1：錯誤視窗開不了，Python 的錯誤訊息：", "NameError: x"]


def test_review_case_a_venv_without_matplotlib_still_shows_hk8_in_the_message_area(course_mod, kind, tmp_path):
    """最終審查 2.1 的情境，用真的子程序：一個沒裝任何東西的 venv 跑範例 HK8（純文字）。以前印完就
    ModuleNotFoundError、結束碼 1、什麼都看不到；現在結束碼 0，結果在訊息區。"""
    venv = tmp_path / "v"
    subprocess.run([str(Path(sys._base_executable).resolve()), "-m", "venv", "--without-pip", str(venv)], check=True)
    python = course_mod.python_in(venv)
    src = CW / "範例課程" / "科學計算" / "HK08"
    shutil.copytree(src, tmp_path / "HK08")
    file = tmp_path / "HK08" / "HK8.py"
    argv, env = kind.argv(file, python, "case-1")
    env = {**{k: v for k, v in os.environ.items() if k not in ("MPLBACKEND", "VIRTUAL_ENV")}, **env}
    proc = subprocess.Popen(argv, cwd=str(file.parent), env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    logs = []
    course_mod._watch(proc, kind, file, python, subprocess.Popen, logs.append)
    proc.stdout.close()
    assert proc.returncode == 0
    assert logs[0] == "HK8 n-gram 語言模型：n-gram language model — case-1：視窗開不了（No module named 'matplotlib'），內容放在這裡："
    assert logs[1] == "HK8 n-gram 語言模型：n-gram language model" and len(logs) > 4


# 真的開子程序（用一個真的 venv 當課的 .venv）；文字視窗那一次不真的開，只記下來

@pytest.fixture(scope="session")
def real_venv(tmp_path_factory):
    """一個真的 venv（python -m venv，跟框架建課的 .venv 一樣），回它的 Python。
    跑測試的 Python 不一定在 venv 裡（CI 不在）：直接拿它當課的 .venv，框架問「裝了什麼」時它會說自己不在 venv 裡，
    課就被當成 .venv 壞了（D146），作業根本沒跑。套件（numpy、matplotlib）用 .pth 指到跑測試的這個 Python 的 site-packages。"""
    venv = tmp_path_factory.mktemp("real") / ".venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    python = venv / VENV_PY
    site = subprocess.run([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                          capture_output=True, text=True, check=True).stdout.strip()
    outer = {p for p in (sysconfig.get_paths()["purelib"], sysconfig.get_paths()["platlib"], *sys.path)
             if p and p.endswith("site-packages")}
    Path(site, "_outer.pth").write_text("".join(f"{p}\n" for p in sorted(outer)), encoding="utf-8")
    return python


@pytest.fixture
def real(hw, real_venv, monkeypatch):
    monkeypatch.setenv("MPLBACKEND", "Agg")
    course, file, python = hw
    shown, ran = [], []  # ran：真的跑作業的那幾個程序（看得到結束碼）

    def popen(argv, **kw):
        if "--show-text" in argv:
            shown.append(argv)
            return FakePopen()(argv, **kw)
        if argv[:1] == [str(python)]:
            argv = [str(real_venv), *argv[1:]]
        proc = subprocess.Popen(argv, **kw)
        if argv[1:2] == [str(file)]:
            ran.append(proc)
        return proc

    return file, popen, shown, ran


def put_after_marker(file, code):
    text = file.read_text(encoding="utf-8")
    file.write_text(text.replace("# ── 從這裡開始是作業 ──", f"# ── 從這裡開始是作業 ──\n{code}", 1), encoding="utf-8")
    return file.read_text(encoding="utf-8").splitlines().index(code) + 1


def test_real_top_level_error_shows_zero_division_and_the_line(course_mod, real):
    file, popen, shown, ran = real
    line = put_after_marker(file, "1 / 0")
    press(course_mod, file, "1", popen=popen)
    assert len(ran) == 1 and ran[0].returncode != 0
    [argv] = shown
    text = argv[4]
    assert text.startswith("HK1 在開始跑之前就出錯了，下面是 Python 的錯誤訊息：\n")
    assert "ZeroDivisionError" in text and f"line {line}" in text and "HK1.py" in text


def test_real_clean_run_opens_no_error_window(course_mod, real):
    file, popen, shown, ran = real
    app, _ = press(course_mod, file, "1", popen=popen)
    assert len(ran) == 1 and ran[0].returncode == 0, app.logs  # 真的跑完了，不是沒跑所以沒視窗
    assert shown == []


def test_real_case_error_is_shown_by_the_shell_not_again(course_mod, real):
    file, popen, shown, ran = real
    text = file.read_text(encoding="utf-8")
    file.write_text(text.replace("def compute(case):", "def compute(case):\n    raise ValueError(\"算壞了\")", 1),
                    encoding="utf-8")
    app, _ = press(course_mod, file, "1", popen=popen)
    assert len(ran) == 1 and ran[0].returncode not in (None, 0), app.logs  # 真的跑了、算壞了
    assert shown == []  # 殼自己開了錯誤視窗（Agg 下 show 不開東西），框架不再開


# ── D146：課的 .venv 壞了：作業那一格問要不要重建，不說成「讀不了 HK1.py」 ──

def broken_course(tmp_path):
    course = make_course(tmp_path)
    file = template_homework(course)
    python = course / ".venv" / VENV_PY
    python.parent.mkdir(parents=True)
    python.symlink_to(tmp_path / "已經不在的" / "python3.13")
    return course, file, python


def broken_popen(python, installed=HAVE):
    fake = popen_with(installed)

    def popen(argv, **kw):
        if argv[0] == str(python) and not python.exists():
            raise FileNotFoundError(2, "No such file or directory", str(python))
        if argv[1:3] == ["-m", "venv"]:
            python.unlink()
            python.write_text("", encoding="utf-8")
        return fake(argv, **kw)

    return popen, fake


def test_broken_venv_asks_to_rebuild_then_installs_and_runs(course_mod, tmp_path, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    _, file, python = broken_course(tmp_path)
    popen, fake = broken_popen(python, installed=[])
    app, _ = press(course_mod, file, "1", popen=popen)
    [ask] = app.confirms
    assert ask.startswith("測試課/.venv 壞了（建它的 Python 已經不在、或換了版本）：要清掉重建，並裝 matplotlib、numpy 嗎？")
    assert [argv[1:4] for argv, _ in fake.calls if argv[1:3] == ["-m", "venv"]] == [["-m", "venv", "--clear"]]
    assert [argv[-1] for argv, _ in fake.calls if "pip" in argv] == ["matplotlib", "numpy"]
    assert len(runs(fake, file)) == 1
    assert not any("讀不了" in line or "Traceback" in line for line in app.logs)


def test_broken_venv_cancel_rebuilds_nothing_and_runs_nothing(course_mod, tmp_path, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    _, file, python = broken_course(tmp_path)
    popen, fake = broken_popen(python)
    app, _ = press(course_mod, file, "1", popen=popen, confirms=[False])
    assert len(app.confirms) == 1 and runs(fake, file) == [] and python.is_symlink()
    assert app.logs[-1] == "沒重建，沒跑"


def test_broken_venv_under_no_install_says_so(course_mod, tmp_path):
    _, file, python = broken_course(tmp_path)
    popen, fake = broken_popen(python)
    app, _ = press(course_mod, file, "1", popen=popen)
    assert app.confirms == [] and runs(fake, file) == []
    assert "CW_NO_INSTALL" in app.logs[-1] and "壞了" in app.logs[-1] and "讀不了" not in app.logs[-1]


def test_venv_python_that_runs_but_fails_counts_as_broken(course_mod, hw, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    _, file, _ = hw
    popen = popen_with(fail=lambda argv: argv[1:2] == ["-c"])
    app, _ = press(course_mod, file, "1", popen=popen, confirms=[False])
    assert len(app.confirms) == 1 and "壞了" in app.confirms[0]


# ── D147：OSError 的句子指到真正出錯的路徑 ──

def test_versions_being_a_file_is_named_not_the_homework(course_mod, hw):
    _, file, _ = hw
    (file.parent / ".版本").write_text("", encoding="utf-8")
    app, popen = press(course_mod, file, "1")
    assert app.logs[-1].startswith("HK1：測試課/HK01/.版本 有問題（") and app.logs[-1].endswith("），沒跑")
    assert "HK1.py" not in app.logs[-1] and runs(popen, file) == []


def test_a_course_python_that_cannot_start_is_named(course_mod, hw):
    course, file, python = hw
    fake = popen_with()

    def popen(argv, **kw):
        if argv[1:2] == [str(file)]:  # 問得到裝了什麼，真的跑的時候卻叫不起來
            raise FileNotFoundError(2, "No such file or directory", str(python))
        return fake(argv, **kw)

    app, _ = press(course_mod, file, "1", popen=popen)
    assert app.logs[-1] == f"HK1：測試課/.venv/{VENV_PY.as_posix()} 有問題（No such file or directory），沒跑"


def test_course_button_names_the_path_of_an_os_error_instead_of_a_traceback(course_mod, hw, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    course, file, python = hw
    fake = popen_with(["numpy"])

    def popen(argv, **kw):
        if "pip" in argv:
            raise PermissionError(13, "Permission denied", str(python))
        return fake(argv, **kw)

    app = CwApp(course)
    course_mod.course_button(app, course, popen=popen)
    assert app.logs[-1] == f"測試課：測試課/.venv/{VENV_PY.as_posix()} 有問題（Permission denied），沒裝"
