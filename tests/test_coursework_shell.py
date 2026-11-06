"""殼 coursework.py（學生拿到、跟作業檔放在一起的那個檔）：3.10 檢查、ensure、作業旁邊的 .venv、
自動補 REQUIRES；main（Task 5）。CW_NO_INSTALL=1、Popen 一律假的、不連網。"""

import ast
import sys
from pathlib import Path

import pytest
from cw_support import TYPE_DIR, FakePopen, load, make_course

SHELL = TYPE_DIR / "coursework.py"
VENV_PY = Path("Scripts/python.exe") if sys.platform == "win32" else Path("bin/python")


@pytest.fixture(autouse=True)
def _no_install(monkeypatch):
    monkeypatch.setenv("CW_NO_INSTALL", "1")
    monkeypatch.delenv("CW_FROM_IPLOT", raising=False)


@pytest.fixture
def cw():
    return load(SHELL, "coursework")


@pytest.fixture
def outside_venv(monkeypatch):
    """像學生用系統的 Python 跑：sys.prefix == sys.base_prefix。"""
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)


@pytest.fixture
def in_venv(monkeypatch):
    monkeypatch.setattr(sys, "base_prefix", "/某個/別的/prefix")


def homework(folder, src="x = 1\n", name="HK1.py"):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / name
    file.write_text(src, encoding="utf-8", newline="\n")
    return file


def fake_venv(folder):
    python = Path(folder) / ".venv" / VENV_PY
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return python


# ── A12：3.9 讀得懂、頂層只 import 標準庫 ──

def test_shell_parses_as_python_3_9():
    ast.parse(SHELL.read_text(encoding="utf-8"), feature_version=(3, 9))


def test_shell_imports_only_the_standard_library_at_top_level():
    tree = ast.parse(SHELL.read_text(encoding="utf-8"))
    names = {a.name.split(".")[0] for n in tree.body if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in tree.body if isinstance(n, ast.ImportFrom) and n.module}
    assert names <= set(sys.stdlib_module_names) | {"__future__"}, names
    assert tree.body[1].module == "__future__"  # docstring 之後第一行


def test_shell_never_installs_into_the_users_python():
    source = SHELL.read_text(encoding="utf-8")
    assert "--user" not in source and "getusersitepackages" not in source


# ── A11：版本 ──

def test_too_old_python_says_one_sentence_and_exits_1(cw, tmp_path, capsys):
    popen = FakePopen()
    file = homework(tmp_path)
    with pytest.raises(SystemExit) as done:
        cw.ensure(["numpy"], str(file), popen=popen, argv=[str(file)], version=(3, 9, 6))
    assert done.value.code == 1
    assert capsys.readouterr().out == cw.TOO_OLD.format(have="3.9.6") + "\n"
    assert popen.calls == []
    assert "3.10" in cw.TOO_OLD and "python3" in cw.TOO_OLD


# ── A11：不在 venv 裡 ──

def test_outside_venv_reruns_with_the_venv_next_to_the_file(cw, tmp_path, outside_venv):
    file = homework(tmp_path / "HK1")
    python = fake_venv(tmp_path / "HK1")
    popen = FakePopen()
    with pytest.raises(SystemExit) as done:
        cw.ensure([], str(file), popen=popen, argv=[str(file), "--case", "case-2"])  # 先重跑，不先查缺什麼
    assert done.value.code == 0
    assert popen.calls == [([str(python), str(file.resolve()), "--case", "case-2"], {"cwd": str(file.resolve().parent)})]


def test_outside_venv_passes_the_rerun_exit_code_on(cw, tmp_path, outside_venv):
    file = homework(tmp_path / "HK1")
    fake_venv(tmp_path / "HK1")
    with pytest.raises(SystemExit) as done:
        cw.ensure(["numpy"], str(file), popen=FakePopen(fail=lambda argv: True), argv=[str(file)])
    assert done.value.code == 1


def test_outside_venv_finds_the_course_venv_but_prefers_the_one_next_to_the_file(cw, tmp_path, outside_venv):
    course = make_course(tmp_path, "課")
    course_python = fake_venv(course)
    file = homework(course / "HK01")
    popen = FakePopen()
    with pytest.raises(SystemExit):
        cw.ensure(["numpy"], str(file), popen=popen, argv=[str(file)])
    assert popen.calls[0][0][0] == str(course_python)
    own = fake_venv(course / "HK01")
    with pytest.raises(SystemExit):
        cw.ensure(["numpy"], str(file), popen=popen, argv=[str(file)])
    assert popen.calls[1][0][0] == str(own)


def test_outside_venv_without_a_venv_says_the_readme_lines_and_never_calls_pip(cw, tmp_path, outside_venv):
    file = homework(tmp_path / "HK1")
    popen = FakePopen()
    with pytest.raises(RuntimeError) as err:
        cw.ensure(["numpy", "no-such-pkg-cw"], str(file), popen=popen, argv=[str(file)])
    said = str(err.value)
    assert "no-such-pkg-cw" in said and "numpy" not in said.split("\n")[0].replace("no-such-pkg-cw", "")
    lines = [ln.strip() for ln in said.split("\n") if ln.startswith("    ")]  # 四個空格的是要打的指令
    assert lines == [cw.MAKE_VENV, cw.RUN.format(file="HK1.py"), cw.WIN_MAKE_VENV, cw.WIN_RUN.format(file="HK1.py")]
    assert (cw.MAKE_VENV, cw.RUN.format(file="HK1.py")) == ("python3 -m venv .venv", "python3 HK1.py")
    assert "py -m venv .venv" in said and "Windows（未經實機驗證）" in said and "--user" not in said
    assert popen.calls == []


def test_outside_venv_without_a_venv_runs_on_when_nothing_is_missing(cw, tmp_path, outside_venv):
    popen = FakePopen()
    file = homework(tmp_path)
    assert cw.ensure(["pytest"], str(file), popen=popen, argv=[str(file)]) is None  # 系統的 Python 剛好有
    assert popen.calls == []


# ── A11：在 venv 裡 ──

def test_in_venv_installs_with_sys_executable(cw, tmp_path, in_venv, monkeypatch, capsys):
    monkeypatch.delenv("CW_NO_INSTALL")
    popen = FakePopen()
    cw.ensure(["pytest", "no-such-pkg-cw"], str(homework(tmp_path)), popen=popen, argv=["別的.py"])
    assert popen.calls == [([sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
                             "no-such-pkg-cw"], {})]
    assert "--user" not in popen.calls[0][0]
    assert "no-such-pkg-cw" in capsys.readouterr().out


def test_in_venv_failed_pip_says_the_command(cw, tmp_path, in_venv, monkeypatch):
    monkeypatch.delenv("CW_NO_INSTALL")
    with pytest.raises(RuntimeError, match=r"裝不了 no-such-pkg-cw：在終端機 .* -m pip install no-such-pkg-cw"):
        cw.ensure(["no-such-pkg-cw"], str(homework(tmp_path)), popen=FakePopen(fail=lambda argv: True),
                  argv=["別的.py"])


def test_in_venv_no_install_only_reports(cw, tmp_path, in_venv):
    popen = FakePopen()
    with pytest.raises(RuntimeError, match="缺 no-such-a、no-such-b；CW_NO_INSTALL 設著，不裝"):
        cw.ensure(["pytest", "no-such-a", "no-such-b"], str(homework(tmp_path)), popen=popen, argv=["x"])
    assert popen.calls == []


@pytest.mark.parametrize("name", ["-x", "a b", "numpy\n", "x;rm"])
def test_in_venv_rejects_bad_names(cw, tmp_path, in_venv, monkeypatch, name):
    monkeypatch.delenv("CW_NO_INSTALL")
    popen = FakePopen()
    with pytest.raises(RuntimeError, match="名字不合法"):
        cw.ensure([name], str(homework(tmp_path)), popen=popen, argv=["x"])
    assert popen.calls == []


@pytest.mark.parametrize("name", ["mlx-lm", "mlx_lm", "MLX-LM"])
def test_in_venv_mlx_needs_apple_silicon(cw, tmp_path, in_venv, monkeypatch, name):
    monkeypatch.delenv("CW_NO_INSTALL")
    monkeypatch.setattr(cw.platform, "machine", lambda: "x86_64")
    popen = FakePopen()
    with pytest.raises(RuntimeError, match="Apple Silicon"):
        cw.ensure([name], str(homework(tmp_path)), popen=popen, argv=["x"])
    assert popen.calls == []


def test_a_string_requires_is_one_name(cw, tmp_path, in_venv):
    popen = FakePopen()
    cw.ensure("pytest", str(homework(tmp_path)), popen=popen, argv=["x"])  # 不是一個字一個字裝
    assert popen.calls == []


# ── 自動補 REQUIRES（照 test_hk_page.py 那幾個 case 改成 coursework）──

AUTOFILL = '''REQUIRES = ["numpy"]   # 用了別的套件就加在這
import coursework; coursework.ensure(REQUIRES, __file__)
import numpy as np
import json
import helper


def compute(case):
    import scipy.signal
    from sklearn.cluster import KMeans
    import yaml
    return {}
'''


def test_autofill_only_the_requires_line_when_running_own_file(cw, tmp_path, in_venv, capsys):
    (tmp_path / "helper.py").write_text("", encoding="utf-8")
    file = homework(tmp_path, AUTOFILL.replace("\n", "\r\n"), name="HK7.py")  # Windows 的換行也只動那一行
    before = file.read_bytes()
    with pytest.raises(RuntimeError, match="CW_NO_INSTALL"):  # 補完之後缺的照報（測試不裝）
        cw.ensure(["numpy"], str(file), popen=FakePopen(), argv=[str(file)])
    first, rest = file.read_bytes().split(b"\r\n", 1)
    assert first.decode("utf-8") == 'REQUIRES = ["numpy", "scipy", "scikit-learn", "PyYAML"]   # 用了別的套件就加在這'
    assert rest == before.split(b"\r\n", 1)[1]  # 其他行一個 byte 都沒動
    assert "已把 scipy、scikit-learn、PyYAML 加進 REQUIRES" in capsys.readouterr().out


def test_autofill_never_when_not_running_own_file(cw, tmp_path, in_venv):
    file = homework(tmp_path, AUTOFILL, name="HK7.py")
    cw.ensure(["numpy"], str(file), popen=FakePopen(), argv=[str(tmp_path / "別的.py")])  # numpy 在：照常回來
    assert file.read_text(encoding="utf-8") == AUTOFILL


def test_autofill_never_when_iplot_started_it(cw, tmp_path, in_venv, monkeypatch):
    monkeypatch.setenv("CW_FROM_IPLOT", "1")
    file = homework(tmp_path, AUTOFILL, name="HK7.py")
    cw.ensure(["numpy"], str(file), popen=FakePopen(), argv=[str(file)])
    assert file.read_text(encoding="utf-8") == AUTOFILL


def test_coursework_itself_is_not_a_package(cw, tmp_path):
    file = homework(tmp_path, 'REQUIRES = ["numpy"]\nimport coursework\nimport numpy\n')
    assert cw._forgotten(file, ["numpy"]) == []


def test_requires_line_counts_lines_like_ast(cw, tmp_path):
    src = "# 學號\x0c姓名 貼上來的\nREQUIRES = ['numpy']  # 註解\nimport scipy\n"
    assert cw.requires_line(src) == (2, 2, "  # 註解")
    file = tmp_path / "HK1.py"
    file.write_bytes(src.encode("utf-8"))
    assert cw.fill_requires(file, ["scipy"]) is True
    assert file.read_bytes() == src.replace("['numpy']", '["numpy", "scipy"]').encode("utf-8")


def test_fill_requires_on_a_read_only_file_says_so(cw, tmp_path, capsys):
    file = homework(tmp_path, "REQUIRES = ['numpy']\nimport scipy\n")
    file.chmod(0o444)
    try:
        assert cw.fill_requires(file, ["scipy"]) is False
    finally:
        file.chmod(0o644)
    assert "手動" in capsys.readouterr().out


def test_fill_requires_leaves_multiline_alone(cw, tmp_path, capsys):
    src = 'REQUIRES = [\n    "numpy",\n]\nimport scipy\n'
    file = homework(tmp_path, src)
    assert cw.requires_line(src) is None
    assert cw.fill_requires(file, ["scipy"]) is False
    assert file.read_text(encoding="utf-8") == src
    assert "手動" in capsys.readouterr().out


def test_fill_requires_keeps_a_bom_and_dedupes(cw, tmp_path):
    file = tmp_path / "HK1.py"
    file.write_bytes(b"\xef\xbb\xbfREQUIRES = ['numpy']  # x\nimport scipy\n")
    assert cw.fill_requires(file, ["scipy", "numpy", "scipy"]) is True
    assert file.read_bytes() == b'\xef\xbb\xbfREQUIRES = ["numpy", "scipy"]  # x\nimport scipy\n'
    assert cw.fill_requires(file, []) is False
