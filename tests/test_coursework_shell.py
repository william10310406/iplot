"""殼 coursework.py（學生拿到、跟作業檔放在一起的那個檔）：3.10 檢查、ensure、作業旁邊的 .venv、
自動補 REQUIRES；main（Task 5）。CW_NO_INSTALL=1、Popen 一律假的、不連網。"""

import ast
import contextlib
import io
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from cw_support import TYPE_DIR, VENV_PY, FakePopen, load, make_course

SHELL = TYPE_DIR / "coursework.py"


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
    [(argv, kwargs)] = popen.calls
    assert argv == [str(python), str(file.resolve()), "--case", "case-2"]
    assert kwargs["cwd"] == str(file.resolve().parent)
    assert kwargs["env"] == {**os.environ, cw.REEXEC: "1"}  # D144：重跑的那一個知道自己是重跑的


def test_rerun_that_is_still_outside_a_venv_stops_with_one_sentence(cw, tmp_path, outside_venv, monkeypatch, capsys):
    """D144：重跑過一次還是不在 venv 裡（.venv 少了 pyvenv.cfg 這種）→ 不再重跑，印一句、結束碼 1。"""
    file = homework(tmp_path / "HK1")
    fake_venv(tmp_path / "HK1")
    monkeypatch.setenv(cw.REEXEC, "1")
    popen = FakePopen()
    with pytest.raises(SystemExit) as done:
        cw.ensure(["numpy"], str(file), popen=popen, argv=[str(file)])
    assert done.value.code == 1 and popen.calls == []
    out = capsys.readouterr()
    assert out.err == "" and out.out == cw.BROKEN_VENV + "\n"
    assert out.out.startswith("這個資料夾的 .venv 壞了")
    assert cw.REMAKE_VENV in out.out and cw.WIN_REMAKE_VENV in out.out and "Traceback" not in out.out


def test_a_venv_without_pyvenv_cfg_reruns_at_most_once(tmp_path):
    """真的子程序：.venv/bin/python 是指到基底 Python 的連結、沒有 pyvenv.cfg（重跑的那個 Python 不認得自己在 venv 裡）。
    以前會一直重跑下去；現在第二次就停、結束碼 1。整個程序組在 finally 裡殺掉，萬一又無限重跑也不留下來。"""
    if sys.platform == "win32":
        pytest.skip("連結與程序組只在 macOS／Linux 這樣做")
    base = Path(sys._base_executable).resolve()
    file = homework(tmp_path / "HK1", 'REQUIRES = []\nimport coursework; coursework.ensure(REQUIRES, __file__)\nprint("跑了")\n')
    python = tmp_path / "HK1" / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(base)
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONHOME", "CW_REEXEC")}
    env["PYTHONPATH"] = str(TYPE_DIR)
    proc = subprocess.Popen([str(base), str(file)], cwd=str(file.parent), env=env, start_new_session=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    try:
        out, err = proc.communicate(timeout=30)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    assert proc.returncode == 1, (out, err)
    assert out.count("這個資料夾的 .venv 壞了") == 1 and "跑了" not in out and "Traceback" not in err


def cfg(python, **keys):
    """像 python -m venv 寫的 pyvenv.cfg（在 .venv/ 底下，python 在 .venv/bin/python）。"""
    lines = ["home = /某處/bin", "include-system-site-packages = false", *(f"{k} = {v}" for k, v in keys.items())]
    (python.parents[1] / "pyvenv.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_old_venv_next_to_the_file_is_not_switched_into(cw, tmp_path, outside_venv, capsys):
    """D143：.venv 是 3.10 以前的 Python 建的 → 不切進去、不重跑，印白話、結束碼 1。"""
    file = homework(tmp_path / "HK1")
    cfg(fake_venv(tmp_path / "HK1"), version="3.9.6")
    popen = FakePopen()
    with pytest.raises(SystemExit) as done:
        cw.ensure(["numpy"], str(file), popen=popen, argv=[str(file)])
    assert done.value.code == 1 and popen.calls == []
    out = capsys.readouterr()
    assert out.err == "" and out.out == cw.OLD_VENV + "\n"
    assert out.out.startswith("這個資料夾的 .venv 是用舊的 Python 建的。先照 README 第 3 步確認版本，再打 ")
    assert "python3 -m venv --clear .venv" in out.out and "py -m venv --clear .venv" in out.out
    assert out.out.endswith("然後重跑。\n") and "Traceback" not in out.out


def test_old_venv_sentence_uses_the_shell_constants(cw):
    assert cw.OLD_VENV == ("這個資料夾的 .venv 是用舊的 Python 建的。先照 README 第 3 步確認版本，"
                           "再打 python3 -m venv --clear .venv 重建（Windows 是 py -m venv --clear .venv），然後重跑。")
    assert (cw.REMAKE_VENV, cw.WIN_REMAKE_VENV) == ("python3 -m venv --clear .venv", "py -m venv --clear .venv")


@pytest.mark.parametrize("keys", [{"version": "3.9.6"}, {"version_info": "3.9.6.final.0"}, {"version": "3.9"}])
def test_old_venv_is_read_from_pyvenv_cfg_in_either_spelling(cw, tmp_path, outside_venv, keys):
    file = homework(tmp_path / "HK1")
    cfg(fake_venv(tmp_path / "HK1"), **keys)
    with pytest.raises(SystemExit) as done:
        cw.ensure([], str(file), popen=FakePopen(), argv=[str(file)])
    assert done.value.code == 1


@pytest.mark.parametrize("keys", [{"version": "3.10.0"}, {"version": "3.14.7"}, {"version_info": "3.12.1.final.0"}])
def test_venv_made_by_3_10_or_newer_is_switched_into_as_before(cw, tmp_path, outside_venv, keys):
    file = homework(tmp_path / "HK1")
    python = fake_venv(tmp_path / "HK1")
    cfg(python, **keys)
    popen = FakePopen()
    with pytest.raises(SystemExit) as done:
        cw.ensure([], str(file), popen=popen, argv=[str(file), "--all"])
    assert done.value.code == 0 and popen.calls[0][0] == [str(python), str(file.resolve()), "--all"]


@pytest.mark.parametrize("text", ["", "version = abc\n", "home = /x\n", "\x00\x01"])
def test_venv_whose_version_cannot_be_read_is_switched_into(cw, tmp_path, outside_venv, text):
    file = homework(tmp_path / "HK1")
    python = fake_venv(tmp_path / "HK1")
    (python.parents[1] / "pyvenv.cfg").write_text(text, encoding="utf-8")
    popen = FakePopen()
    with pytest.raises(SystemExit):
        cw.ensure([], str(file), popen=popen, argv=[str(file)])
    assert len(popen.calls) == 1  # 讀不出來就照舊：不為了猜不準的事擋學生


def test_old_course_venv_is_not_switched_into_either(cw, tmp_path, outside_venv, capsys):
    course = make_course(tmp_path, "課")
    cfg(fake_venv(course), version="3.9.6")
    file = homework(course / "HK01")
    popen = FakePopen()
    with pytest.raises(SystemExit) as done:
        cw.ensure([], str(file), popen=popen, argv=[str(file)])
    assert done.value.code == 1 and popen.calls == [] and capsys.readouterr().out == cw.OLD_VENV + "\n"


def test_old_venv_next_to_the_file_wins_over_a_new_course_venv(cw, tmp_path, outside_venv, capsys):
    course = make_course(tmp_path, "課")
    cfg(fake_venv(course), version="3.14.0")
    file = homework(course / "HK01")
    cfg(fake_venv(course / "HK01"), version="3.9.6")  # 旁邊那個優先，它舊就是舊
    popen = FakePopen()
    with pytest.raises(SystemExit) as done:
        cw.ensure([], str(file), popen=popen, argv=[str(file)])
    assert done.value.code == 1 and popen.calls == []


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


def test_outside_venv_without_a_venv_says_the_readme_lines_and_never_calls_pip(cw, tmp_path, outside_venv, capsys):
    """D138：跟版本那句一樣，印白話、結束碼 1，不丟例外（學生看不到 traceback）。"""
    file = homework(tmp_path / "HK1")
    popen = FakePopen()
    with pytest.raises(SystemExit) as done:
        cw.ensure(["numpy", "no-such-pkg-cw"], str(file), popen=popen, argv=[str(file)])
    assert done.value.code == 1
    captured = capsys.readouterr()
    said = captured.out.rstrip("\n")
    assert captured.err == "" and said == cw._no_venv(["no-such-pkg-cw"], file)
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


# ── A10：main ──

@pytest.fixture
def agg():
    """main 會 import matplotlib.pyplot：測試用 Agg，不開視窗；rcParams 用完還原；沒有 matplotlib 的機器跳過。"""
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with matplotlib.rc_context():
        yield plt
    plt.close("all")


def make_hw(calls, draw=True, text=None, fail=(), stats=True):
    """兩個 case 的作業 dict（規範 v2 的 HOMEWORK）；calls 記下 compute／draw 被怎麼叫。"""
    def compute(case):
        calls.append(("compute", case))
        if case in fail:
            raise ValueError(f"{case} 算壞了")
        run = {"case": case, "x": [0, 1, 2]}
        if text:
            run["text"] = text
        return run

    def draw_fn(fig, run):
        from matplotlib.animation import FuncAnimation

        calls.append(("draw", type(fig).__name__, run["case"]))
        (line,) = fig.add_subplot(111).plot(run["x"], run["x"])
        return FuncAnimation(fig, lambda i: (line,), frames=3, interval=10)

    return dict(name="HK1 範例", note="筆記寫這裡。\n第二行。",
                docs=[("Circular motion", "https://example.invalid/circle"), ("角速度", "https://example.invalid/w")],
                cases={"case-1": dict(label="第一個"), "case-2": dict(label="第二個")},
                compute=compute, draw=draw_fn if draw else None,
                stats=(lambda run: [("點數", str(len(run["x"])))]) if stats else None, file=__file__)


def drawn(plt, then=None):
    """假的 plt.show：把現在的圖畫一次（動畫才算有畫過），再做 then。"""
    def show_fn():
        plt.gcf().canvas.draw()
        if then:
            then()
    return show_fn


def no_ask(prompt):
    raise AssertionError("有 --case、--all 就不問")


def test_main_prints_name_note_docs_first(cw, agg):
    out = io.StringIO()
    assert cw.main(make_hw([]), argv=["--case", "case-1"], ask=no_ask, out=out, show_fn=drawn(agg)) == 0
    lines = out.getvalue().splitlines()
    assert lines[:5] == ["HK1 範例", "筆記寫這裡。", "第二行。", "Circular motion：https://example.invalid/circle",
                         "角速度：https://example.invalid/w"]


def test_main_without_note_or_docs_prints_only_the_name(cw, agg):
    hw = make_hw([])
    hw.update(note="", docs=[])
    out = io.StringIO()
    cw.main(hw, argv=["--case", "case-1"], ask=no_ask, out=out, show_fn=drawn(agg))
    assert out.getvalue().splitlines()[0] == "HK1 範例" and "：https" not in out.getvalue()
    assert out.getvalue().splitlines()[1].startswith("── case-1")


def test_main_case_flag_runs_only_that_one(cw, agg):
    calls, out = [], io.StringIO()
    assert cw.main(make_hw(calls), argv=["--case", "case-2"], ask=no_ask, out=out, show_fn=drawn(agg)) == 0
    assert calls == [("compute", "case-2"), ("draw", "Figure", "case-2")]
    assert cw.main(make_hw(calls), argv=["--case", "case-9"], ask=no_ask, out=out, show_fn=drawn(agg)) == 2
    assert "沒有 case-9" in out.getvalue()


def test_main_all_flag_runs_every_case_without_asking(cw, agg):
    calls = []
    assert cw.main(make_hw(calls), argv=["--all"], ask=no_ask, out=io.StringIO(), show_fn=drawn(agg)) == 0
    assert [c for c in calls if c[0] == "compute"] == [("compute", "case-1"), ("compute", "case-2")]


def test_main_asks_for_a_number(cw, agg):
    calls, out, asked = [], io.StringIO(), []
    assert cw.main(make_hw(calls), argv=[], ask=lambda p: asked.append(p) or "2", out=out, show_fn=drawn(agg)) == 0
    assert calls == [("compute", "case-2"), ("draw", "Figure", "case-2")]
    text = out.getvalue()
    assert "1) case-1  第一個" in text and "2) case-2  第二個" in text and "0) 全部" in text
    assert text.index("Circular motion") < text.index("1) case-1")  # 先 NAME、NOTE、DOCS，再列 case
    calls.clear()
    assert cw.main(make_hw(calls), argv=[], ask=lambda p: "0", out=io.StringIO(), show_fn=drawn(agg)) == 0
    assert [c[1] for c in calls if c[0] == "compute"] == ["case-1", "case-2"]


@pytest.mark.parametrize("answer", ["x", "", "9", "①", "²", EOFError])
def test_main_bad_number_returns_2(cw, agg, answer):
    def ask(prompt):
        if answer is EOFError:
            raise EOFError
        return answer

    calls, out = [], io.StringIO()
    assert cw.main(make_hw(calls), argv=[], ask=ask, out=out, show_fn=drawn(agg)) == 2
    assert calls == [] and "選" in out.getvalue().splitlines()[-1]


def test_main_continues_after_an_exception_and_returns_1(cw, agg):
    calls, out = [], io.StringIO()
    assert cw.main(make_hw(calls, fail={"case-1"}), argv=["--all"], ask=no_ask, out=out, show_fn=drawn(agg)) == 1
    assert "Traceback" in out.getvalue() and "ValueError: case-1 算壞了" in out.getvalue()
    assert ("compute", "case-2") in calls and ("draw", "Figure", "case-2") in calls


def test_main_text_only_homework_opens_no_figure(cw, agg):
    shown, out = [], io.StringIO()
    hw = make_hw([], draw=False, text="hi there", stats=False)
    assert cw.main(hw, argv=["--all"], ask=no_ask, out=out, show_fn=drawn(agg, lambda: shown.append(1))) == 0
    assert "hi there" in out.getvalue() and shown == []


def test_main_prints_text_and_stats(cw, agg):
    out = io.StringIO()
    cw.main(make_hw([], text="結果是 3"), argv=["--case", "case-1"], ask=no_ask, out=out, show_fn=drawn(agg))
    assert "結果是 3" in out.getvalue() and "點數：3" in out.getvalue()


def test_main_from_iplot_opens_text_then_figure_per_case(cw, agg, monkeypatch):
    monkeypatch.setenv("CW_FROM_IPLOT", "1")
    shown = []
    assert cw.main(make_hw([], text="t"), argv=["--all"], ask=no_ask, out=io.StringIO(),
                   show_fn=drawn(agg, lambda: shown.append(agg.gcf().canvas.manager.get_window_title()))) == 0
    assert shown == ["HK1 範例 — case-1（文字）", "HK1 範例 — case-1", "HK1 範例 — case-2（文字）", "HK1 範例 — case-2"]


def test_main_from_iplot_first_text_window_has_name_note_and_every_doc(cw, agg, monkeypatch):
    monkeypatch.setenv("CW_FROM_IPLOT", "1")
    texts = []
    monkeypatch.setattr(cw, "_show_text", lambda title, text, show_fn=None: texts.append(text))
    cw.main(make_hw([], text="結果"), argv=["--all"], ask=no_ask, out=io.StringIO(), show_fn=drawn(agg))
    first, second = texts
    assert first.startswith("HK1 範例\n筆記寫這裡。\n第二行。")
    assert "https://example.invalid/circle" in first and "https://example.invalid/w" in first and "結果" in first
    assert "筆記" not in second and "https://" not in second and "結果" in second


def test_main_from_iplot_opens_the_first_text_window_even_without_text(cw, agg, monkeypatch):
    monkeypatch.setenv("CW_FROM_IPLOT", "1")
    texts = []
    monkeypatch.setattr(cw, "_show_text", lambda title, text, show_fn=None: texts.append(text))
    cw.main(make_hw([], stats=False), argv=["--all"], ask=no_ask, out=io.StringIO(), show_fn=drawn(agg))
    assert len(texts) == 1 and "筆記寫這裡" in texts[0]  # 第二個 case 沒有字：不開空的文字視窗


def test_main_from_iplot_shows_the_traceback_of_a_failed_case_in_a_text_window(cw, agg, monkeypatch):
    monkeypatch.setenv("CW_FROM_IPLOT", "1")
    texts = []
    monkeypatch.setattr(cw, "_show_text", lambda title, text, show_fn=None: texts.append((title, text)))
    out = io.StringIO()
    assert cw.main(make_hw([], text="結果", fail={"case-1", "case-2"}), argv=["--all"], ask=no_ask, out=out,
                   show_fn=drawn(agg)) == 1
    (t1, first), (t2, second) = texts
    assert t1 == "HK1 範例 — case-1" and t2 == "HK1 範例 — case-2"
    assert first.startswith("HK1 範例\n筆記寫這裡。") and "https://example.invalid/w" in first  # 第一個視窗照樣有 NAME、NOTE、DOCS
    assert "case-1 出錯了" in first and "Traceback" in first and "ValueError: case-1 算壞了" in first
    assert "筆記" not in second and "ValueError: case-2 算壞了" in second
    assert out.getvalue().count("Traceback") == 2  # 輸出照樣印


def test_main_from_iplot_draw_failure_after_the_header_window_does_not_repeat_it(cw, agg, monkeypatch):
    monkeypatch.setenv("CW_FROM_IPLOT", "1")
    texts = []
    monkeypatch.setattr(cw, "_show_text", lambda title, text, show_fn=None: texts.append(text))
    hw = make_hw([], text="結果")
    hw["draw"] = lambda fig, run: 1 / 0
    assert cw.main(hw, argv=["--case", "case-1"], ask=no_ask, out=io.StringIO(), show_fn=drawn(agg)) == 1
    header, error = texts
    assert "筆記" in header and "筆記" not in error and "ZeroDivisionError" in error


def test_main_outside_iplot_opens_no_window_for_a_traceback(cw, agg, monkeypatch):
    texts = []
    monkeypatch.setattr(cw, "_show_text", lambda title, text, show_fn=None: texts.append(text))
    cw.main(make_hw([], fail={"case-1"}), argv=["--case", "case-1"], ask=no_ask, out=io.StringIO(), show_fn=drawn(agg))
    assert texts == []


def test_main_from_iplot_says_on_stderr_that_it_opened_an_error_window(cw, agg, monkeypatch, capsys):
    monkeypatch.setenv("CW_FROM_IPLOT", "1")
    monkeypatch.setattr(cw, "_show_text", lambda title, text, show_fn=None: None)
    cw.main(make_hw([], fail={"case-1"}), argv=["--all"], ask=no_ask, out=io.StringIO(), show_fn=drawn(agg))
    assert capsys.readouterr().err.splitlines() == [cw.SHOWN_MARK]  # 兩個 case 只壞一個：一行


def test_main_outside_iplot_never_prints_the_mark(cw, agg, capsys):
    cw.main(make_hw([], fail={"case-1"}), argv=["--all"], ask=no_ask, out=io.StringIO(), show_fn=drawn(agg))
    assert cw.SHOWN_MARK not in capsys.readouterr().err


def test_cli_show_text_opens_a_text_window(cw, monkeypatch):
    texts = []
    monkeypatch.setattr(cw, "_show_text", lambda title, text, show_fn=None: texts.append((title, text)))
    assert cw.cli(["--show-text", "HK6", "第一行\n第二行"]) == 0
    assert texts == [("HK6", "第一行\n第二行")]


def test_main_sets_installed_chinese_fonts_before_drawing(cw, agg):
    import matplotlib

    seen = []
    hw = make_hw([])
    hw["draw"] = lambda fig, run: seen.append(list(matplotlib.rcParams["font.sans-serif"]))
    cw.main(hw, argv=["--case", "case-1"], ask=no_ask, out=io.StringIO(), show_fn=drawn(agg))
    [fonts] = seen
    assert fonts[-1] == "DejaVu Sans" and set(fonts[:-1]) <= set(cw.TEXT_FONTS)


# ── D145：iPLoT 另開的程序開不了視窗（matplotlib 沒裝、壞了）→ 同一段文字夾在兩行記號之間印到 stderr，給框架放進訊息區 ──

def no_window(*args, **kwargs):
    raise ModuleNotFoundError("No module named 'matplotlib'")


def handed(cw, err):
    """stderr 裡殼交給 iPLoT 的每一段（記號之間的行）。"""
    blocks, block = [], None
    for line in err.splitlines():
        if line == cw.HANDED_OVER:
            block = []
        elif line == cw.HANDED_OVER_END and block is not None:
            blocks.append(block)
            block = None
        elif block is not None:
            block.append(line)
    return blocks


def test_main_from_iplot_hands_the_text_over_when_no_window_opens(cw, monkeypatch, capsys):
    monkeypatch.setenv("CW_FROM_IPLOT", "1")
    monkeypatch.setattr(cw, "_show_text", no_window)
    out = io.StringIO()
    assert cw.main(make_hw([], draw=False, text="結果是 3"), argv=["--all"], ask=no_ask, out=out) == 0
    first, second = handed(cw, capsys.readouterr().err)
    assert first[0] == "HK1 範例 — case-1：視窗開不了（No module named 'matplotlib'），內容放在這裡："
    assert first[1:4] == ["HK1 範例", "筆記寫這裡。", "第二行。"] and "結果是 3" in first and "點數：3" in first
    assert second[0].startswith("HK1 範例 — case-2：視窗開不了") and "結果是 3" in second and "筆記寫這裡。" not in second
    assert "結果是 3" in out.getvalue()  # stdout 照樣印


def test_main_from_iplot_hands_a_failed_case_over_and_says_it_was_shown(cw, monkeypatch, capsys):
    monkeypatch.setenv("CW_FROM_IPLOT", "1")
    monkeypatch.setattr(cw, "_show_text", no_window)
    assert cw.main(make_hw([], draw=False, fail={"case-1"}), argv=["--case", "case-1"], ask=no_ask, out=io.StringIO()) == 1
    err = capsys.readouterr().err
    [block] = handed(cw, err)
    assert "case-1 出錯了：" in block and "ValueError: case-1 算壞了" in block
    assert err.splitlines().count(cw.SHOWN_MARK) == 1  # 給人看了：框架不再開錯誤視窗


def test_main_outside_iplot_never_hands_anything_over(cw, monkeypatch, capsys):
    monkeypatch.setattr(cw, "_show_text", no_window)
    cw.main(make_hw([], draw=False, text="t"), argv=["--all"], ask=no_ask, out=io.StringIO())
    assert cw.HANDED_OVER not in capsys.readouterr().err


def test_cli_show_text_hands_the_text_over_when_no_window_opens(cw, monkeypatch, capsys):
    monkeypatch.setattr(cw, "_show_text", no_window)
    assert cw.cli(["--show-text", "HK1", "第一行\n第二行"]) == 0
    assert handed(cw, capsys.readouterr().err) == [["HK1：視窗開不了（No module named 'matplotlib'），內容放在這裡：",
                                                     "第一行", "第二行"]]
