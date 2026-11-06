"""課的 .venv：建、列已裝、缺的問一次、一個一個裝（從科學計算的 hk_tk 複製來改，不 import 它）；
課那一格 course_button：PACKAGES 分批問，沒有就裝每份作業 REQUIRES 的聯集，ONLY_ON 的套件在不對的機器上不裝。"""

import json

import pytest
from cw_support import FRAMEWORK, HOMEWORK_SRC, CwApp, FakePopen, load, make_course, make_homework


@pytest.fixture(autouse=True)
def _no_install(monkeypatch):
    monkeypatch.setenv("CW_NO_INSTALL", "1")


@pytest.fixture
def course_mod():
    return load(FRAMEWORK, "course")


@pytest.fixture
def installing(monkeypatch):
    """真的要裝的測試：拿掉 CW_NO_INSTALL（popen 一律是假的，不會有東西真的被裝）。"""
    monkeypatch.delenv("CW_NO_INSTALL")


def have(*names):
    """假的 popen 對「列出已裝」的回答：一行 JSON。"""
    return FakePopen(lines=[json.dumps(list(names))])


def src(*requires):
    return HOMEWORK_SRC.replace('["numpy", "matplotlib"]', repr(list(requires)))


def venv_of(course):
    """假裝課的 .venv 已經建好：放一個 bin/python。"""
    python = course / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return python


def argvs(popen):
    return [argv for argv, _ in popen.calls]


def pips(popen):
    return [argv[-1] for argv in argvs(popen) if argv[1:3] == ["-m", "pip"]]


# ── 零件 ──

def test_python_in_and_venv_python(course_mod, tmp_path):
    assert course_mod.python_in(tmp_path / ".venv").parts[-2:] == ("bin", "python")
    assert course_mod.venv_python(None) is None
    assert course_mod.venv_python(tmp_path) is None  # 還沒建
    python = venv_of(tmp_path)
    assert course_mod.venv_python(tmp_path) == python


def test_ensure_venv_builds_with_python_m_venv(course_mod, tmp_path, installing):
    popen, said = FakePopen(), []
    python = course_mod.ensure_venv(tmp_path / ".venv", said.append, popen=popen, python="/x/python3")
    assert argvs(popen) == [["/x/python3", "-m", "venv", str(tmp_path / ".venv")]]
    assert python == course_mod.python_in(tmp_path / ".venv")
    assert any(".venv" in s for s in said)


def test_ensure_venv_leaves_an_existing_one(course_mod, tmp_path, installing):
    python = venv_of(tmp_path)
    popen = FakePopen()
    assert course_mod.ensure_venv(tmp_path / ".venv", print, popen=popen) == python
    assert popen.calls == []


def test_ensure_venv_failure_and_no_install(course_mod, tmp_path, installing, monkeypatch):
    with pytest.raises(RuntimeError, match="代碼 1"):
        course_mod.ensure_venv(tmp_path / ".venv", print, popen=FakePopen(fail=lambda a: True))
    monkeypatch.setenv("CW_NO_INSTALL", "1")
    popen = FakePopen()
    with pytest.raises(RuntimeError, match="CW_NO_INSTALL"):
        course_mod.ensure_venv(tmp_path / ".venv", print, popen=popen)
    assert popen.calls == []


def test_installed_and_missing(course_mod, tmp_path):
    popen = have("NumPy", "matplotlib", "typing_extensions")
    assert course_mod.installed(tmp_path / "python", popen=popen) == {"numpy", "matplotlib", "typing-extensions"}
    assert course_mod.missing(tmp_path / "python", ["numpy", "scipy", "SciPy", "typing_extensions"], popen=popen) == ["scipy"]
    garbage = FakePopen(lines=["不是 JSON"])
    assert course_mod.installed(tmp_path / "python", popen=garbage) == set()


def test_install_runs_pip_one_by_one_in_that_python(course_mod, tmp_path, installing):
    popen, said = FakePopen(lines=["Collecting x"]), []
    python = tmp_path / "py"
    ok, failed = course_mod.install(python, ["numpy", "matplotlib"], said.append, popen=popen)
    assert (ok, failed) == (["numpy", "matplotlib"], [])
    assert len(popen.calls) == 2
    for argv, pkg in zip(argvs(popen), ["numpy", "matplotlib"], strict=True):
        assert argv == [str(python), "-m", "pip", "install", "--no-input", "--disable-pip-version-check", pkg]
        assert "--user" not in argv


def test_install_one_failing_does_not_stop_the_rest(course_mod, tmp_path, installing):
    popen = FakePopen(fail=lambda a: a[-1] == "scipy", lines=["ERROR: no matching distribution"])
    ok, failed = course_mod.install(tmp_path / "py", ["numpy", "scipy", "pandas"], print, popen=popen)
    assert ok == ["numpy", "pandas"]
    assert failed == [("scipy", "ERROR: no matching distribution")]


def test_install_refuses_names_that_are_not_pip_names(course_mod, tmp_path, installing):
    popen = FakePopen()
    ok, failed = course_mod.install(tmp_path / "py", ["numpy; rm -rf ~", "-e", "numpy\n"], print, popen=popen)
    assert ok == [] and [p for p, _ in failed] == ["numpy; rm -rf ~", "-e", "numpy\n"]
    assert popen.calls == []


def test_install_under_no_install_runs_nothing(course_mod, tmp_path):
    popen = FakePopen()
    ok, failed = course_mod.install(tmp_path / "py", ["numpy"], print, popen=popen)
    assert ok == [] and failed == [("numpy", "CW_NO_INSTALL")]
    assert popen.calls == []


def test_install_reports_progress_every_five_seconds(course_mod, tmp_path, installing):
    ticks = iter([0, 1, 6, 7, 12])  # 第一次是 last 的起點
    said = []
    popen = FakePopen(lines=["a", "b", "c", "d"])
    course_mod.install(tmp_path / "py", ["numpy"], said.append, popen=popen, clock=lambda: next(ticks))
    assert said == ["numpy：b", "numpy：d"]


def test_summary_of_install(course_mod):
    assert course_mod.summary_of_install([], []) == ""
    assert course_mod.summary_of_install(["a", "b"], []) == "已裝 a、b"
    assert course_mod.summary_of_install(["a"], [("c", "網路")]) == "已裝 a；裝不了 c（網路）"


# ── 這門課有哪些作業 ──

def test_homeworks_are_found_in_number_order(course_mod, tmp_path):
    course = make_course(tmp_path)
    for n in (10, 2, 1):
        make_homework(course, n)
    (course / ".版本").mkdir()
    (course / ".版本" / "HK3.py").write_text("x = 1\n", encoding="utf-8")
    (course / "發出去的").mkdir()
    (course / "HK07").mkdir()  # 資料夾在、檔不在
    assert [code for code, _ in course_mod.homeworks(course_mod.read_course(course))] == ["HK1", "HK2", "HK10"]


# ── 課那一格 ──

def test_button_without_venv_asks_for_the_union_then_builds_and_installs(course_mod, tmp_path, installing):
    course = make_course(tmp_path)
    make_homework(course, 1, src("numpy", "matplotlib"))
    make_homework(course, 2, src("numpy", "scipy"))
    app, popen = CwApp(tmp_path), FakePopen()
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert len(app.confirms) == 1
    for name in ("matplotlib", "numpy", "scipy"):
        assert name in app.confirms[0]
    assert argvs(popen)[0][1:] == ["-m", "venv", str(course / ".venv")]
    python = str(course_mod.python_in(course / ".venv"))
    assert pips(popen) == ["matplotlib", "numpy", "scipy"]
    assert all(argv[0] == python for argv in argvs(popen)[1:])
    assert "已裝 matplotlib、numpy、scipy" in app.logs[-1]


def test_button_cancel_runs_nothing_and_says_so(course_mod, tmp_path, installing):
    course = make_course(tmp_path)
    make_homework(course, 1)
    app, popen = CwApp(tmp_path), FakePopen()
    app.answers = [False]
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert popen.calls == [] and not (course / ".venv").exists()
    assert app.logs[-1] == "沒裝"


def test_button_with_venv_asks_only_for_what_is_missing(course_mod, tmp_path, installing):
    course = make_course(tmp_path)
    make_homework(course, 1, src("numpy", "scipy"))
    venv_of(course)
    app, popen = CwApp(tmp_path), have("numpy")
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert "scipy" in app.confirms[0] and "numpy" not in app.confirms[0]
    assert pips(popen) == ["scipy"]


def test_button_with_everything_installed_says_so(course_mod, tmp_path, installing):
    course = make_course(tmp_path)
    make_homework(course, 1, src("numpy"))
    venv_of(course)
    app, popen = CwApp(tmp_path), have("numpy", "pip")
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert app.confirms == [] and pips(popen) == []
    assert "都在" in app.logs[-1]


def test_button_packages_ask_one_batch_at_a_time(course_mod, tmp_path, installing):
    batches = [(["numpy", "matplotlib"], "HK1–HK8 用的", "約 480 MB"), (["torch"], "HK9 用的", "約 1.1 GB")]
    course = make_course(tmp_path, PACKAGES=batches)
    make_homework(course, 1)
    app, popen = CwApp(tmp_path), FakePopen()
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert len(app.confirms) == 1
    assert "HK1–HK8 用的" in app.confirms[0] and "約 480 MB" in app.confirms[0] and "torch" not in app.confirms[0]
    assert pips(popen) == ["numpy", "matplotlib"]
    assert "HK9 用的" in app.logs[-1] and "約 1.1 GB" in app.logs[-1] and "再按一次" in app.logs[-1]


def test_button_packages_second_batch_comes_after_the_first_is_there(course_mod, tmp_path, installing):
    batches = [(["numpy"], "第一批", "約 1 MB"), (["torch"], "第二批", "約 2 MB")]
    course = make_course(tmp_path, PACKAGES=batches)
    venv_of(course)
    app, popen = CwApp(tmp_path), have("numpy")
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert "第二批" in app.confirms[0] and "torch" in app.confirms[0]
    assert pips(popen) == ["torch"]
    assert "再按一次" not in app.logs[-1]


def test_button_packages_ignore_what_homeworks_require(course_mod, tmp_path, installing):
    course = make_course(tmp_path, PACKAGES=[(["numpy"], "全部", "約 1 MB")])
    make_homework(course, 1, src("scipy"))
    app, popen = CwApp(tmp_path), FakePopen()
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert pips(popen) == ["numpy"]


MLX = [(["numpy", "mlx-lm"], "全部", "約 1 MB")]


def test_button_only_on_skips_the_package_off_that_machine(course_mod, tmp_path, installing):
    course = make_course(tmp_path, PACKAGES=MLX, ONLY_ON={"mlx-lm": "apple-silicon"})
    make_homework(course, 1)
    make_homework(course, 9, src("numpy", "mlx-lm"))
    app, popen = CwApp(tmp_path), FakePopen()
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert pips(popen) == ["numpy"]
    assert "mlx-lm" in app.confirms[0] and "HK9" in app.confirms[0]  # 先說，再問
    assert "mlx-lm" in app.logs[-1] and "HK9" in app.logs[-1] and "看不了" in app.logs[-1]


def test_button_only_on_installs_it_on_that_machine(course_mod, tmp_path, installing):
    course = make_course(tmp_path, PACKAGES=MLX, ONLY_ON={"mlx-lm": "apple-silicon"})
    make_homework(course, 9, src("numpy", "mlx-lm"))
    app, popen = CwApp(tmp_path), FakePopen()
    course_mod.course_button(app, course, popen=popen, apple_silicon=True)
    assert pips(popen) == ["numpy", "mlx-lm"]
    assert "看不了" not in app.confirms[0] + app.logs[-1]


def test_button_only_on_union_mode_when_nothing_else_is_left(course_mod, tmp_path, installing):
    course = make_course(tmp_path, ONLY_ON={"mlx-lm": "apple-silicon"})
    make_homework(course, 9, src("mlx-lm"))
    app, popen = CwApp(tmp_path), FakePopen()
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert popen.calls == [] and app.confirms == []
    assert "mlx-lm" in app.logs[-1] and "HK9" in app.logs[-1] and "看不了" in app.logs[-1]


def test_button_default_machine_check_is_the_real_one(course_mod, tmp_path, monkeypatch):
    monkeypatch.setattr(course_mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(course_mod.sys, "platform", "darwin")
    assert course_mod._apple_silicon() is False
    monkeypatch.setattr(course_mod.platform, "machine", lambda: "arm64")
    assert course_mod._apple_silicon() is True
    monkeypatch.setattr(course_mod.sys, "platform", "linux")
    assert course_mod._apple_silicon() is False


def test_button_no_install_builds_nothing_and_installs_nothing(course_mod, tmp_path):
    course = make_course(tmp_path)
    make_homework(course, 1)
    app, popen = CwApp(tmp_path), FakePopen()
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert popen.calls == [] and app.confirms == [] and not (course / ".venv").exists()
    assert len(app.logs) == 1 and "CW_NO_INSTALL" in app.logs[0]


def test_button_with_nothing_to_install(course_mod, tmp_path, installing):
    course = make_course(tmp_path)
    app, popen = CwApp(tmp_path), FakePopen()
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert popen.calls == [] and app.confirms == [] and not (course / ".venv").exists()
    assert "還沒有需要裝的套件" in app.logs[-1]


def test_button_reports_a_broken_course_file(course_mod, tmp_path, installing):
    course = make_course(tmp_path)
    (course / "課程.py").write_text("NAME = 'x'\nimport os\n", encoding="utf-8")
    app, popen = CwApp(tmp_path), FakePopen()
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert popen.calls == [] and "第 2 行" in app.logs[-1]


def test_button_failed_install_is_in_the_last_line(course_mod, tmp_path, installing):
    course = make_course(tmp_path)
    make_homework(course, 1, src("numpy", "scipy"))
    app = CwApp(tmp_path)
    popen = FakePopen(fail=lambda a: a[-1] == "scipy", lines=["ERROR: 沒有網路"])
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert "已裝 numpy" in app.logs[-1] and "裝不了 scipy（ERROR: 沒有網路）" in app.logs[-1]


def test_button_venv_build_failure_is_one_sentence(course_mod, tmp_path, installing):
    course = make_course(tmp_path)
    make_homework(course, 1)
    app = CwApp(tmp_path)
    popen = FakePopen(fail=lambda a: "venv" in a)
    course_mod.course_button(app, course, popen=popen, apple_silicon=False)
    assert "建不了" in app.logs[-1] and pips(popen) == []


def test_button_never_runs_the_homework_file(course_mod, tmp_path, installing):
    course = make_course(tmp_path)
    file = make_homework(course, 1, "import zz_不存在\nopen('寫了.txt', 'w')\n" + HOMEWORK_SRC)
    app = CwApp(tmp_path)
    course_mod.course_button(app, course, popen=FakePopen(), apple_silicon=False)
    assert not (file.parent / "寫了.txt").exists() and not (tmp_path / "寫了.txt").exists()
