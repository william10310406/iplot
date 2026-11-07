"""tests/acceptance_coursework.py（N1–N3，自己跑、要網路）裡不連網、不開視窗就測得到的事：
從 README 讀指令、學生用的環境、掃 zip、各步的判斷（shell 用假的）。"""

import importlib.util
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TYPE_DIR = ROOT / "modules" / "課程作業" / "作業類型" / "算完畫圖"
SYSTEM = "/系統/python3"  # n1 量 pip list --user 用的 python；不是 argv[0] == "python3"，這樣好分辨


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("acceptance_coursework", ROOT / "tests" / "acceptance_coursework.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def shell(monkeypatch):
    spec = importlib.util.spec_from_file_location("cw_shell_for_script_test", TYPE_DIR / "coursework.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)  # dataclass 要在 sys.modules 裡找得到自己
    spec.loader.exec_module(module)
    return module


def result(script, code=0, out=""):
    return script.Result(code, out)


class FakeShell:
    """sh 的替身：照 answers(argv) 回；記下每一次的 (argv, cwd, env)。"""

    def __init__(self, script, answers=None):
        self.script, self.answers, self.calls = script, answers or (lambda argv: (0, "")), []

    def __call__(self, argv, cwd=None, env=None):
        self.calls.append((list(argv), cwd, env))
        code, out = self.answers(list(argv))
        return self.script.Result(code, out)


# ---------- 從 README 讀指令 ----------

def test_readme_commands_are_only_the_four_space_python3_lines(script):
    text = "\n".join([
        "第 3 步：確認 Python 版本",
        "",
        "    python3 --version",
        "",
        "    python3 -m venv .venv",
        "      python3 -m venv --clear .venv",  # 縮六格的重建指令不算
        "    py --version",  # Windows 的不算
        "python3 HK1.py 不縮排的不算",
        "    `python3` 這種說明文字不算",
        "    python3 HK1.py",
    ])
    assert script.readme_commands(text) == ["python3 --version", "python3 -m venv .venv", "python3 HK1.py"]


def test_readme_commands_of_the_real_student_readme_are_the_shell_constants(script, shell, tmp_path):
    zip_path = script.pack_example(tmp_path)
    folder = script.unpack(zip_path, tmp_path / "學生")
    commands = script.readme_commands((folder / "README.txt").read_text(encoding="utf-8"))
    assert commands == [shell.VERSION, shell.MAKE_VENV, shell.RUN.format(file="HK2.py")]


def test_the_last_step_gets_the_case_and_the_others_are_untouched(script):
    steps = script.student_steps(["python3 --version", "python3 -m venv .venv", "python3 HK2.py"])
    assert steps == [["python3", "--version"], ["python3", "-m", "venv", ".venv"], ["python3", "HK2.py", "--case", "case-1"]]


def test_readme_without_python3_lines_is_an_error(script):
    with pytest.raises(ValueError, match="沒有"):
        script.student_steps([])


# ---------- 學生用的環境 ----------

def test_student_env_hides_user_site_and_keeps_every_cache_in_the_work_folder(script, tmp_path):
    env = script.student_env({"PATH": "/usr/bin", "VIRTUAL_ENV": "/x", "PYTHONPATH": "/y", "PYTHONHOME": "/z", "HOME": "/h"}, tmp_path)
    assert env["PYTHONNOUSERSITE"] == "1" and env["MPLBACKEND"] == "Agg"
    assert not {"VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME"} & set(env)
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/h"
    for key in ("PIP_CACHE_DIR", "MPLCONFIGDIR"):
        assert Path(env[key]).is_relative_to(tmp_path)


# ---------- 掃 zip（N3） ----------

def make_zip(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return path


def test_scan_zip_finds_home_user_volumes_and_the_work_folder(script, tmp_path):
    needles = {"家目錄": "/Users/某人", "帳號名": "某人", "外接硬碟": "/Volumes", "暫存資料夾": str(tmp_path)}
    zip_path = make_zip(tmp_path / "a.zip", {
        "HK1/HK1.py": "print('/Users/某人/x')\n",
        "HK1/README.txt": "在 /Volumes/硬碟 打開\n",
        "HK1/coursework.py": f"# {tmp_path}\n",
        "HK1/備份_某人/a.txt": "乾淨",  # 名字裡有
    })
    found = script.scan_zip(zip_path, needles)
    assert {(m, k) for m, k in found} >= {("HK1/HK1.py", "家目錄"), ("HK1/HK1.py", "帳號名"), ("HK1/README.txt", "外接硬碟"),
                                           ("HK1/coursework.py", "暫存資料夾"), ("HK1/備份_某人/a.txt", "帳號名")}


def test_scan_zip_of_a_clean_zip_is_empty(script, tmp_path):
    zip_path = make_zip(tmp_path / "a.zip", {"HK1/HK1.py": "print(1)\n", "HK1/README.txt": "hello\n"})
    assert script.scan_zip(zip_path, {"家目錄": "/Users/某人", "帳號名": "某人"}) == []


def test_scan_needles_never_include_an_empty_string(script, tmp_path):
    assert all(script.scan_needles(tmp_path).values())


def test_n3_on_the_real_pack_is_clean(script, tmp_path):
    zip_path = script.pack_example(tmp_path)
    assert script.scan_zip(zip_path, script.scan_needles(tmp_path)) == []


def test_pack_example_is_the_hk2_student_pack(script, tmp_path):
    with zipfile.ZipFile(script.pack_example(tmp_path)) as z:
        names = z.namelist()
    assert "HK2/HK2.py" in names and "HK2/coursework.py" in names and "HK2/README.txt" in names
    assert "HK2/HK2Space/" in names


# ---------- N1 ----------

def n1_answers(user_packages=("[]", "[]"), venv_ok=True):
    pips = iter(user_packages)

    def answers(argv):
        if argv == ["python3", "--version"]:
            return 0, "Python 3.14.7"
        if argv[1:3] == ["-m", "pip"]:
            return 0, next(pips)
        if "import numpy, matplotlib" in argv:
            return (0 if venv_ok else 1), ""
        return 0, ""
    return answers


def test_n1_runs_the_readme_steps_in_order_in_the_unpacked_folder_with_a_clean_env(script, tmp_path):
    folder = script.unpack(script.pack_example(tmp_path), tmp_path / "學生")
    sh = FakeShell(script, n1_answers())
    ok = script.n1(folder, tmp_path, system_python=SYSTEM, sh=sh)
    assert ok is True
    steps = [argv for argv, _, _ in sh.calls if argv[0] == "python3"]
    assert steps == [["python3", "--version"], ["python3", "-m", "venv", ".venv"], ["python3", "HK2.py", "--case", "case-1"]]
    for argv, cwd, env in sh.calls:
        if argv[0] == "python3":
            assert Path(cwd) == folder
            assert env["PYTHONNOUSERSITE"] == "1" and env["MPLBACKEND"] == "Agg"
    venv_check = [argv for argv, _, _ in sh.calls if "import numpy, matplotlib" in argv]
    assert venv_check == [[str(folder / ".venv" / "bin" / "python"), "-c", "import numpy, matplotlib"]]


def test_n1_compares_the_systems_user_packages_before_and_after(script, tmp_path):
    folder = script.unpack(script.pack_example(tmp_path), tmp_path / "學生")
    assert script.n1(folder, tmp_path, system_python=SYSTEM, sh=FakeShell(script, n1_answers(("[1]", "[1]")))) is True
    assert script.n1(folder, tmp_path, system_python=SYSTEM, sh=FakeShell(script, n1_answers(("[1]", "[1, 2]")))) is False


def test_n1_stops_at_the_first_failing_step(script, tmp_path):
    folder = script.unpack(script.pack_example(tmp_path), tmp_path / "學生")

    def answers(argv):
        return (1, "boom") if argv[:3] == ["python3", "-m", "venv"] else (0, "Python 3.14.7" if argv[1:] == ["--version"] else "[]")
    sh = FakeShell(script, answers)
    assert script.n1(folder, tmp_path, system_python=SYSTEM, sh=sh) is False
    assert not any(argv[0] == "python3" and argv[1] == "HK2.py" for argv, _, _ in sh.calls)


def test_n1_fails_when_the_venv_lacks_the_packages(script, tmp_path):
    folder = script.unpack(script.pack_example(tmp_path), tmp_path / "學生")
    assert script.n1(folder, tmp_path, system_python=SYSTEM, sh=FakeShell(script, n1_answers(venv_ok=False))) is False


def test_n1_asks_python3_for_a_new_enough_python(script, tmp_path):
    """README 第 3 步要看到 3.10 以上；這台的 python3 太舊就不是 N1 能驗的情況。"""
    folder = script.unpack(script.pack_example(tmp_path), tmp_path / "學生")

    def answers(argv):
        return (0, "Python 3.9.6") if argv == ["python3", "--version"] else (0, "[]")
    assert script.n1(folder, tmp_path, system_python=SYSTEM, sh=FakeShell(script, answers)) is False


# ---------- N2 ----------

def test_n2_wants_the_version_sentence_exit_1_and_no_traceback(script, shell, tmp_path):
    folder = script.unpack(script.pack_example(tmp_path), tmp_path / "舊")
    sentence = shell.TOO_OLD.format(have="3.9.6")
    assert script.n2(folder, sh=FakeShell(script, lambda argv: (1, sentence + "\n")), python="/usr/bin/python3") is True
    assert script.n2(folder, sh=FakeShell(script, lambda argv: (0, sentence + "\n")), python="/usr/bin/python3") is False
    assert script.n2(folder, sh=FakeShell(script, lambda argv: (1, "Traceback (most recent call last):\n" + sentence)),
                     python="/usr/bin/python3") is False
    assert script.n2(folder, sh=FakeShell(script, lambda argv: (1, "別的話\n")), python="/usr/bin/python3") is False


def test_n2_runs_the_old_python_on_hk2_in_the_unpacked_folder(script, shell, tmp_path):
    folder = script.unpack(script.pack_example(tmp_path), tmp_path / "舊")
    sh = FakeShell(script, lambda argv: (1, shell.TOO_OLD.format(have="3.9.6")))
    script.n2(folder, sh=sh, python="/usr/bin/python3")
    argv, cwd, env = sh.calls[0]
    assert argv == ["/usr/bin/python3", "HK2.py"] and Path(cwd) == folder and env["PYTHONNOUSERSITE"] == "1"


# ---------- main ----------

def test_main_without_network_says_so_and_fails_but_still_does_n2_and_n3(script, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(script, "online", lambda *a, **k: False)
    monkeypatch.setattr(script, "n1", lambda *a, **k: pytest.fail("沒網路不該跑 N1"))
    monkeypatch.setattr(script, "n2", lambda *a, **k: True)
    assert script.main(["--keep", str(tmp_path / "留")]) != 0
    out = capsys.readouterr().out
    assert "沒網路，N1 沒跑" in out and "N2" in out and "N3" in out


def test_main_passes_when_every_item_passes(script, tmp_path, monkeypatch):
    monkeypatch.setattr(script, "online", lambda *a, **k: True)
    monkeypatch.setattr(script, "n1", lambda *a, **k: True)
    monkeypatch.setattr(script, "n2", lambda *a, **k: True)
    assert script.main(["--keep", str(tmp_path / "留")]) == 0
    assert (tmp_path / "留").is_dir()


def test_main_fails_when_n3_finds_something(script, tmp_path, monkeypatch):
    monkeypatch.setattr(script, "online", lambda *a, **k: True)
    monkeypatch.setattr(script, "n1", lambda *a, **k: True)
    monkeypatch.setattr(script, "n2", lambda *a, **k: True)
    monkeypatch.setattr(script, "scan_zip", lambda *a, **k: [("HK2/HK2.py", "家目錄")])
    assert script.main(["--keep", str(tmp_path / "留")]) == 1


def test_keep_refuses_a_folder_that_already_has_something_in_it(script, tmp_path, monkeypatch):
    victim = tmp_path / "桌面"
    victim.mkdir()
    (victim / "important.txt").write_text("不能刪", encoding="utf-8")
    monkeypatch.setattr(script, "online", lambda *a, **k: pytest.fail("不該走到網路"))
    assert script.main(["--keep", str(victim)]) == 1
    assert (victim / "important.txt").read_text(encoding="utf-8") == "不能刪"


def test_without_keep_the_work_folder_is_deleted_afterwards(script, monkeypatch):
    seen = []
    monkeypatch.setattr(script, "online", lambda *a, **k: True)
    monkeypatch.setattr(script, "n1", lambda folder, work, **k: seen.append(Path(work)) or True)
    monkeypatch.setattr(script, "n2", lambda *a, **k: True)
    assert script.main([]) == 0
    assert seen and not seen[0].exists()

