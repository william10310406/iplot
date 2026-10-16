"""作業的殼 v0（modules/科學計算/hk_page.py，docs/09_作業規範.md）：ensure、自動補 REQUIRES、--check、main、show、collect。

跟 test_homework 一樣：HK_NO_INSTALL=1、Popen 一律假的、不連網。
"""

import re
import sys
import types
from pathlib import Path

import pytest
from test_homework import FakePopen, loader

SPEC = Path(__file__).resolve().parents[1] / "docs" / "09_作業規範.md"


@pytest.fixture(autouse=True)
def no_install(monkeypatch):
    monkeypatch.setenv("HK_NO_INSTALL", "1")


@pytest.fixture(autouse=True)
def keep_cwd(monkeypatch):
    monkeypatch.chdir(Path.cwd())


@pytest.fixture
def load(monkeypatch):
    """load("hk_page")：同 test_homework 的 load。"""
    yield from loader(monkeypatch)


def spec_example() -> str:
    """docs/09 第 1 節那個檔的原文（規範與殼對不上時以殼為準，所以測試直接拿規範的範例）。"""
    text = SPEC.read_text(encoding="utf-8")
    return re.search(r"## 1\..*?```python\n(.*?)```", text, re.S).group(1)


@pytest.fixture
def standalone(monkeypatch):
    """像學生自己 python3 HKn.py 那樣：不在 iPLoT 的面板程序裡（別的測試可能已經 import 過 core.runner）。"""
    monkeypatch.delitem(sys.modules, "core.runner", raising=False)


@pytest.fixture
def in_panel(monkeypatch):
    """像在 iPLoT 的面板程序裡：core.runner 在 sys.modules。"""
    monkeypatch.setitem(sys.modules, "core.runner", types.ModuleType("core.runner"))


def homework(folder, src=None, name="HK0.py"):
    """在 folder 寫一份作業檔（預設是規範的範例），回那個檔。"""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / name
    file.write_text(spec_example() if src is None else src, encoding="utf-8")
    return file


# ── Task 8：ensure、自動補 REQUIRES、--check ──


def test_ensure_all_present_does_not_call_pip(tmp_path, load, standalone):
    hp = load("hk_page")
    popen = FakePopen()
    hp.ensure(["pytest", "numpy"], str(homework(tmp_path)), popen=popen, argv=["別的.py"])
    assert popen.calls == []


def test_ensure_installs_missing_with_user_flag_outside_venv(tmp_path, load, standalone, monkeypatch, capsys):
    hp = load("hk_page")
    monkeypatch.delenv("HK_NO_INSTALL")
    added = []
    monkeypatch.setattr(hp.site, "addsitedir", added.append)
    file = str(homework(tmp_path))
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)  # 不在 venv 裡
    popen = FakePopen()
    hp.ensure(["numpy", "no-such-pkg-m6"], file, popen=popen, argv=["別的.py"])
    assert popen.argvs == [[sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
                            "--user", "no-such-pkg-m6"]]
    assert "shell" not in popen.calls[0][1]
    assert added == [hp.site.getusersitepackages()]  # 剛建好的 user site 也進 sys.path
    assert "no-such-pkg-m6" in capsys.readouterr().out
    monkeypatch.setattr(sys, "base_prefix", "/某個/別的/prefix")  # 在 venv 裡：不加 --user
    popen = FakePopen()
    hp.ensure(["no-such-pkg-m6"], file, popen=popen, argv=["別的.py"])
    assert "--user" not in popen.argvs[0]


def test_ensure_failed_pip_says_the_command(tmp_path, load, standalone, monkeypatch):
    hp = load("hk_page")
    monkeypatch.delenv("HK_NO_INSTALL")
    with pytest.raises(RuntimeError, match=r"裝不了 no-such-pkg-m6：在終端機 .* -m pip install no-such-pkg-m6"):
        hp.ensure(["no-such-pkg-m6"], str(homework(tmp_path)), popen=FakePopen(fail=lambda argv: True),
                  argv=["別的.py"])


def test_ensure_no_install_env_raises_with_names(tmp_path, load, standalone):
    hp = load("hk_page")
    popen = FakePopen()
    with pytest.raises(RuntimeError, match="缺 no-such-a、no-such-b；HK_NO_INSTALL 設著，不裝"):
        hp.ensure(["numpy", "no-such-a", "no-such-b"], str(homework(tmp_path)), popen=popen, argv=["x"])
    assert popen.calls == []


def test_ensure_rejects_bad_names(tmp_path, load, standalone, monkeypatch):
    hp = load("hk_page")
    monkeypatch.delenv("HK_NO_INSTALL")
    popen = FakePopen()
    with pytest.raises(RuntimeError, match="名字不合法"):
        hp.ensure(["-x"], str(homework(tmp_path)), popen=popen, argv=["x"])
    assert popen.calls == []


def test_ensure_says_mlx_needs_apple_silicon(tmp_path, load, standalone, monkeypatch):
    hp = load("hk_page")
    monkeypatch.delenv("HK_NO_INSTALL")
    monkeypatch.setattr(hp.platform, "machine", lambda: "x86_64")
    popen = FakePopen()
    with pytest.raises(RuntimeError, match="Apple Silicon"):
        hp.ensure(["mlx-lm"], str(homework(tmp_path)), popen=popen, argv=["x"])
    assert popen.calls == []


AUTOFILL = '''REQUIRES = ["numpy"]   # 用了別的套件就加在這
import hk_page; hk_page.ensure(REQUIRES, __file__)
import numpy as np
import json
import helper


def compute(case):
    import scipy.signal
    from sklearn.cluster import KMeans
    import yaml
    return {}
'''


def test_ensure_autofills_only_when_running_own_file(tmp_path, load, standalone, capsys):
    hp = load("hk_page")
    (tmp_path / "helper.py").write_text("", encoding="utf-8")
    file = homework(tmp_path, AUTOFILL.replace("\n", "\r\n"), name="HK7.py")  # Windows 的換行也只動那一行
    before = file.read_bytes()
    with pytest.raises(RuntimeError, match="HK_NO_INSTALL"):  # 補完之後缺的照報（測試不裝）
        hp.ensure(["numpy"], str(file), popen=FakePopen(), argv=[str(file)])
    after = file.read_bytes()
    first, rest = after.split(b"\r\n", 1)
    assert first.decode("utf-8") == 'REQUIRES = ["numpy", "scipy", "scikit-learn", "PyYAML"]   # 用了別的套件就加在這'
    assert rest == before.split(b"\r\n", 1)[1]  # 其他行一個 byte 都沒動
    assert "已把 scipy、scikit-learn、PyYAML 加進 REQUIRES" in capsys.readouterr().out
    other = homework(tmp_path / "b", AUTOFILL, name="HK7.py")
    hp.ensure(["numpy"], str(other), popen=FakePopen(), argv=[str(tmp_path / "別的.py")])  # numpy 在：照常回來
    assert other.read_text(encoding="utf-8") == AUTOFILL  # 不是自己跑自己：不改


def test_ensure_in_panel_never_installs_or_edits(tmp_path, load, in_panel, monkeypatch, capsys):
    hp = load("hk_page")
    monkeypatch.delenv("HK_NO_INSTALL")
    course = tmp_path / "科學計算"
    (course / "HK13" / "B1").mkdir(parents=True)
    (course / "hk_tk.py").write_text("", encoding="utf-8")
    file = homework(course / "HK13" / "B1", AUTOFILL, name="iplot.py")
    popen = FakePopen()
    with pytest.raises(SystemExit) as stop:  # 沒有 .venv：說一句、正常結束（runner 當作完成），不裝
        hp.ensure(["no-such-pkg-m6"], str(file), popen=popen, argv=[str(file)])
    assert stop.value.code == 0 and popen.calls == []
    assert "先按「科學計算」裝課程套件" in capsys.readouterr().out
    vpy = course / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    vpy.parent.mkdir(parents=True)
    vpy.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as stop:  # 有 .venv：交給它另開程序跑這個檔
        hp.ensure(["no-such-pkg-m6"], str(file), popen=popen, argv=[str(file)])
    assert stop.value.code == 0
    [(argv, kw)] = popen.calls
    assert argv == [str(vpy), str(file)] and kw["cwd"] == str(file.parent)
    assert kw["env"]["HK_NO_AUTOFILL"] == "1"  # 交出去的子程序也不准改學生的檔
    assert "改用課程的 .venv 另開視窗跑" in capsys.readouterr().out
    assert file.read_text(encoding="utf-8") == AUTOFILL  # 面板裡絕不改檔
    fine = homework(course / "HK13" / "B2", name="iplot.py")  # 只用 numpy、matplotlib
    hp.ensure(["numpy", "matplotlib"], str(fine), popen=popen, argv=[str(fine)])  # 都在：照常回來
    assert len(popen.calls) == 1


def test_ensure_in_panel_hands_off_for_imports_missing_from_requires(tmp_path, load, in_panel, capsys):
    hp = load("hk_page")
    course = tmp_path / "科學計算"
    (course / "HK13" / "B1").mkdir(parents=True)
    (course / "hk_tk.py").write_text("", encoding="utf-8")
    file = homework(course / "HK13" / "B1", "REQUIRES = ['numpy']\nimport numpy\nimport no_such_mod_m6\n", name="iplot.py")
    with pytest.raises(SystemExit):  # REQUIRES 漏寫、面板的 Python 也沒有：一樣交給 .venv（這裡沒有 .venv，只說一句）
        hp.ensure(["numpy"], str(file), popen=FakePopen(), argv=[str(file)])
    assert "no_such_mod_m6" in capsys.readouterr().out
    assert "no_such_mod_m6" not in file.read_text(encoding="utf-8").splitlines()[0]


def test_ensure_never_autofills_a_collected_or_marked_file(tmp_path, load, standalone, monkeypatch):
    hp = load("hk_page")
    course = tmp_path / "科學計算"
    (course / "HK13" / "B1").mkdir(parents=True)
    (course / "hk_tk.py").write_text("", encoding="utf-8")
    inside = homework(course / "HK13" / "B1", AUTOFILL, name="iplot.py")  # 課程資料夾裡（收進來的、老師的）
    hp.ensure(["numpy"], str(inside), popen=FakePopen(), argv=[str(inside)])
    assert inside.read_text(encoding="utf-8") == AUTOFILL
    outside = homework(tmp_path / "批次" / "HK13_收件" / "B1", AUTOFILL, name="iplot.py")
    monkeypatch.setenv("HK_NO_AUTOFILL", "1")  # 批次名單、面板交出去的子程序都帶這個
    hp.ensure(["numpy"], str(outside), popen=FakePopen(), argv=[str(outside)])
    assert outside.read_text(encoding="utf-8") == AUTOFILL


def test_ensure_treats_a_string_requires_as_one_name(tmp_path, load, standalone):
    hp = load("hk_page")
    popen = FakePopen()
    hp.ensure("numpy", str(homework(tmp_path)), popen=popen, argv=["x"])  # 不是一個字一個字裝
    assert popen.calls == []


def test_mpl_toolkits_and_pylab_count_as_matplotlib(tmp_path, load, monkeypatch):
    hp = load("hk_page")
    monkeypatch.setattr(hp.importlib.metadata, "packages_distributions", lambda: {})  # 全新的 Python：什麼都沒裝
    file = homework(tmp_path, "REQUIRES = ['numpy', 'matplotlib']\nfrom mpl_toolkits.mplot3d import Axes3D\n"
                              "from pylab import plot\nimport numpy\n")
    assert hp._forgotten(file, ["numpy", "matplotlib"]) == []
    assert hp._forgotten(file, ["numpy"]) == ["matplotlib"]
    hk = load("hk_tk")
    assert hk.pip_name("mpl_toolkits") == "matplotlib" and hk.pip_name("pylab") == "matplotlib"


def test_requires_line_counts_lines_like_ast(tmp_path, load):
    hp = load("hk_page")
    src = "# 學號\x0c姓名 貼上來的\nREQUIRES = ['numpy']  # 註解\nimport scipy\n"
    assert hp.requires_line(src) == (2, 2, "  # 註解")
    file = tmp_path / "HK1.py"
    file.write_bytes(src.encode("utf-8"))
    assert hp.fill_requires(file, ["scipy"]) is True
    assert file.read_bytes() == src.replace("['numpy']", '["numpy", "scipy"]').encode("utf-8")


def test_fill_requires_on_a_read_only_file_says_so(tmp_path, load, capsys):
    hp = load("hk_page")
    file = homework(tmp_path, "REQUIRES = ['numpy']\nimport scipy\n")
    file.chmod(0o444)
    try:
        assert hp.fill_requires(file, ["scipy"]) is False
    finally:
        file.chmod(0o644)
    assert "手動" in capsys.readouterr().out
    assert file.read_text(encoding="utf-8") == "REQUIRES = ['numpy']\nimport scipy\n"


def test_ensure_mlx_spellings_all_need_apple_silicon(tmp_path, load, standalone, monkeypatch):
    hp = load("hk_page")
    monkeypatch.delenv("HK_NO_INSTALL")
    monkeypatch.setattr(hp.platform, "machine", lambda: "x86_64")
    for name in ("mlx_lm", "MLX-LM"):
        with pytest.raises(RuntimeError, match="Apple Silicon"):
            hp.ensure([name], str(homework(tmp_path)), popen=FakePopen(), argv=["x"])


@pytest.mark.parametrize("value", ["None", "3", "'numpy'", "[1, 2]"])
def test_check_requires_must_be_a_list_of_names(tmp_path, load, value):
    hp = load("hk_page")
    src = spec_example().replace('REQUIRES = ["numpy", "matplotlib"]', f"REQUIRES = {value}")
    (tmp_path / "HK0Space").mkdir()
    problems = hp.check(homework(tmp_path, src))
    assert any("REQUIRES 要是一個 list" in p for p in problems)


def test_check_says_one_sentence_for_unreadable_files(tmp_path, load, capsys):
    hp = load("hk_page")
    assert hp.check(tmp_path / "沒有.py") == [f"讀不到這個檔：{tmp_path / '沒有.py'}"]
    assert hp.cli(["--check", str(tmp_path / "沒有.py")]) == 1
    nul = tmp_path / "nul.py"
    nul.write_bytes(b"x = 1\x00\n")
    [problem] = hp.check(nul)
    assert problem.startswith("語法錯誤") and "None" not in problem


def test_fill_requires_leaves_multiline_alone(tmp_path, load, capsys):
    hp = load("hk_page")
    src = 'REQUIRES = [\n    "numpy",\n]\nimport scipy\n'
    file = homework(tmp_path, src)
    assert hp.requires_line(src) is None
    assert hp.fill_requires(file, ["scipy"]) is False
    assert file.read_text(encoding="utf-8") == src
    assert "手動" in capsys.readouterr().out


def test_requires_line_finds_the_comment(load):
    hp = load("hk_page")
    assert hp.requires_line(spec_example()) == (1, 1, "              # 用了別的套件就加在這；自己跑一次會自動補")
    assert hp.requires_line("x = 1\n") is None
    assert hp.requires_line("REQUIRES = ['a']\n") == (1, 1, "")


def test_fill_requires_keeps_a_bom_and_dedupes(tmp_path, load):
    hp = load("hk_page")
    file = tmp_path / "HK1.py"
    file.write_bytes(b"\xef\xbb\xbfREQUIRES = ['numpy']  # x\nimport scipy\n")
    assert hp.fill_requires(file, ["scipy", "numpy", "scipy"]) is True
    assert file.read_bytes() == b'\xef\xbb\xbfREQUIRES = ["numpy", "scipy"]  # x\nimport scipy\n'
    assert hp.fill_requires(file, []) is False


def test_dist_for_uses_installed_mapping_then_table(load, monkeypatch):
    hp = load("hk_page")
    monkeypatch.setattr(hp.importlib.metadata, "packages_distributions",
                        lambda: {"yaml": ["PyYAML"], "mylib": ["my-dist"]})
    assert hp.dist_for("mylib") == "my-dist"  # 裝了的：照它自己的 metadata
    assert hp.dist_for("cv2") == "opencv-python"  # 沒裝的：對照表
    assert hp.dist_for("whatever") == "whatever"


def test_check_passes_spec_example(tmp_path, load):
    hp = load("hk_page")
    file = homework(tmp_path)
    (tmp_path / "HK0Space").mkdir()
    assert hp.check(file) == []


def test_check_reports_each_rule(tmp_path, load):
    hp = load("hk_page")
    src = spec_example()
    src = src.replace("import numpy as np\n", "import numpy as np\nimport tkinter\nimport scipy\n")
    src = src.replace("def on_files(app, paths): hk_page.collect(app, paths)",
                      "def on_files(app, paths): print(paths)")
    src = src.replace('    return FuncAnimation(', '    plt.show()\n    open("/Users/x/data.txt")\n    return FuncAnimation(')
    file = homework(tmp_path, src)
    problems = hp.check(file)
    expect = ["tkinter", "def on_files(app, paths): hk_page.collect(app, paths)", "REQUIRES 漏了 scipy",
              "plt.show", "/Users/x/data.txt", "HK0Space"]
    for word in expect:
        assert sum(word in p for p in problems) == 1, (word, problems)
    assert len(problems) == len(expect)


def test_check_reports_missing_names_and_homework_keys(tmp_path, load):
    hp = load("hk_page")
    src = spec_example().replace('NAME = "HK0 範例：一顆球繞圓"', 'TITLE2 = "x"')
    src = src.replace("compute=compute, draw=draw", "draw=draw").replace("file=__file__", "file=None")
    src = src.replace('DATA = Path(__file__).resolve().parent / "HK0Space"', "")
    problems = hp.check(homework(tmp_path, src))
    assert any("少了 NAME" in p for p in problems)
    assert any("compute=" in p for p in problems)
    assert any("file=__file__" in p for p in problems)
    assert hp.check(homework(tmp_path, "def x(:\n", name="壞.py")) == ["語法錯誤：第 1 行"]


def test_check_cli_exit_code(load, tmp_path, capsys):
    hp = load("hk_page")
    good = homework(tmp_path)
    (tmp_path / "HK0Space").mkdir()
    assert hp.cli(["--check", str(good)]) == 0
    assert "通過" in capsys.readouterr().out
    bad = homework(tmp_path, spec_example().replace("import numpy as np", "import turtle"), name="壞.py")
    assert hp.cli(["--check", str(bad)]) == 1
    out = capsys.readouterr().out
    assert "turtle" in out and "通過" not in out
    assert hp.cli([]) == 2
