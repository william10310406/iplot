"""工作坊模組「科學計算」（M6）：舊格式執行器、墊片、匯入作業包、套件、收作業、批次模式。

不連網、不裝東西：每個測試都在 HK_NO_INSTALL=1 底下跑，Popen 一律是假的（FakePopen）。
Tk 的部分用藏起來的真 Tk（tests/test_tk_smoke.py 的做法：destroy 之前先 update）；沒有顯示器就跳過那幾個。
"""

import ast
import importlib
import importlib.util
import io
import os
import shutil
import sys
import types
import unicodedata
import zipfile
from pathlib import Path

import pytest
from conftest import FakeApp

COURSE = Path(__file__).resolve().parents[1] / "modules" / "科學計算"
NAMES = ("hk_tk", "hk_page")


@pytest.fixture(autouse=True)
def no_install(monkeypatch):
    """所有測試都不建 venv、不跑 pip（設計第 6 節）。"""
    monkeypatch.setenv("HK_NO_INSTALL", "1")


@pytest.fixture(autouse=True)
def keep_cwd(monkeypatch):
    """build、run_homework 會 os.chdir：測試結束放回原來的工作目錄。"""
    monkeypatch.chdir(Path.cwd())


def loader(monkeypatch):
    """load 的本體（test_hk_page 也用）：課程資料夾放到 sys.path 最前面、不寫 .pyc，給出 import_module；
    結束時把 hk_tk、hk_page 從 sys.modules 拿掉。"""
    monkeypatch.syspath_prepend(str(COURSE))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    for n in NAMES:
        monkeypatch.delitem(sys.modules, n, raising=False)
    yield importlib.import_module
    for n in NAMES:
        sys.modules.pop(n, None)


@pytest.fixture
def load(monkeypatch):
    """load("hk_tk")：把 modules/科學計算/hk_tk.py 當一般模組 import（不寫 .pyc），結束時從 sys.modules 拿掉。"""
    yield from loader(monkeypatch)


class HwApp(FakeApp):
    """FakeApp 再多 module.folder、ask（answers_ask 先放好；用完回 default）、reveal、choose_files、choose_folder。"""

    def __init__(self, home, folder):
        super().__init__(home)
        self.module = types.SimpleNamespace(folder=Path(folder))
        self.asks, self.answers_ask, self.revealed = [], [], []
        self.chosen_files, self.chosen_folder = [], None

    def ask(self, prompt, default=""):
        self.asks.append((prompt, default))
        return self.answers_ask.pop(0) if self.answers_ask else default

    def reveal(self, path):
        self.revealed.append(Path(path))

    def choose_files(self):
        return list(self.chosen_files)

    def choose_folder(self):
        return self.chosen_folder


class FakeProc:
    """假的子程序：stdout 是給好的那幾行（text），returncode 一開始就定好。"""

    def __init__(self, lines, returncode):
        self.stdout = io.StringIO("".join(lines))
        self.returncode = returncode

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def communicate(self, timeout=None):
        return self.stdout.read(), ""


class FakePopen:
    """當作 popen 傳進去：記下每次的 argv 與 kwargs；output(argv) 給那一次的輸出行，fail(argv) 為真就回非零。"""

    def __init__(self, output=lambda argv: [], fail=lambda argv: False):
        self.calls, self.output, self.fail = [], output, fail

    def __call__(self, argv, **kw):
        self.calls.append((list(argv), kw))
        return FakeProc(self.output(argv), 1 if self.fail(argv) else 0)

    @property
    def argvs(self):
        return [argv for argv, _ in self.calls]


OLD_HK = '''SEEN = set()
def cmd{hk}_SAVEB():
    pass
import tkinter as tk
def {hk}_RUN_CASE1(ich, LF_subWIN):
    import json
    from sklearn.cluster import KMeans
def cmdRUN(LF_subWIN):
    for w in LF_subWIN.winfo_children():
        if isinstance(w, tkinter.Button): pass
def {hk}():
    global LF_subWIN, optionValue
    SEEN.update(globals().keys())
    LF_subWIN.configure(text='Homework')
    tkinter.Button(LF_subWIN, text='RUN').place(relx=0, rely=0, relwidth=0.1, relheight=0.05)
'''


def old_hk(folder, hk="HK5", src=OLD_HK, encoding="utf-8"):
    """folder/t2026fscSpace/HK5.txt 寫入 src（{hk} 換成 hk），回那個檔。"""
    kit = Path(folder) / "t2026fscSpace"
    kit.mkdir(parents=True, exist_ok=True)
    file = kit / f"{hk}.txt"
    file.write_text(src.replace("{hk}", hk), encoding=encoding)
    return file


try:
    import tkinter
except ImportError:  # 沒有 tkinter 的 Python：Tk 的測試各自跳過
    tkinter = None


def _new_root(tk_class=None):
    if tkinter is None:
        pytest.skip("這個 Python 沒有 tkinter")
    try:
        root = (tk_class or tkinter.Tk)()
    except tkinter.TclError:
        pytest.skip("沒有顯示器")
    root.withdraw()
    return root


def _close(root):
    """先跑一次事件迴圈再 destroy（macOS 的 Tk 9.0，見 test_tk_smoke）。"""
    root.update()
    root.destroy()


@pytest.fixture
def tk_root():
    root = _new_root()
    yield root
    _close(root)


@pytest.fixture
def fake_tk(monkeypatch):
    """run_homework 自己建的 Tk：換成藏起來的真 Tk，mainloop 不跑；messagebox.showerror 換成記錄。
    回 namespace：roots（建過的 Tk）、errors（showerror 收到的 (title, message)）。"""
    if tkinter is None:
        pytest.skip("這個 Python 沒有 tkinter")
    from tkinter import messagebox
    rec = types.SimpleNamespace(roots=[], errors=[])
    real = tkinter.Tk

    def make(*a, **k):
        root = _new_root(real)
        root.mainloop = lambda *a: None
        rec.roots.append(root)
        return root

    monkeypatch.setattr(tkinter, "Tk", make)
    monkeypatch.setattr(messagebox, "showerror", lambda title, message, **k: rec.errors.append((title, message)))
    yield rec
    for root in rec.roots:
        _close(root)


# ── 頂層只 import 標準庫，而且不 import tkinter（課程模組與墊片在面板的程序裡 import hk_tk，面板擋 tkinter）──


@pytest.mark.parametrize("name", ["hk_tk", "hk_page"])
def test_top_level_imports_only_stdlib_and_no_tkinter(name):
    tree = ast.parse((COURSE / f"{name}.py").read_text(encoding="utf-8"))
    top = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            top.add(node.module.split(".")[0])
    assert top <= set(sys.stdlib_module_names) | {"__future__"}
    assert not top & {"tkinter", "_tkinter", "turtle"}


# ── Task 1：舊格式執行器 ──


def test_hk_of_finds_the_single_hk_file(tmp_path, load):
    hk = load("hk_tk")
    one = tmp_path / "one"
    old_hk(one, "HK5")
    (one / "t2026fscSpace" / "HK5_backup.txt").write_text("x", encoding="utf-8")  # 不符合 HK_RE，不算
    assert hk.hk_of(one) == "HK5"
    two = tmp_path / "two"
    old_hk(two, "HK5")
    old_hk(two, "HK6")
    assert hk.hk_of(two) is None
    assert hk.hk_of(tmp_path / "none") is None
    (tmp_path / "empty" / "t2026fscSpace").mkdir(parents=True)
    assert hk.hk_of(tmp_path / "empty") is None


def test_build_gives_the_seven_globals_and_calls_hk(tmp_path, load, tk_root):
    hk = load("hk_tk")
    folder = tmp_path / "B11234567_王小明"
    old_hk(folder)
    ns = hk.build(folder, "HK5", tk_root)
    assert ns["SEEN"] >= set(hk.GLOBALS)  # HK5() 被叫到，而且看得到這幾個全域
    assert ns["t2026fscHOMEDIR"] == str(folder)
    assert ns["LF"] is tk_root and ns["HAS_DND"] is False
    assert Path.cwd() == folder.resolve()
    assert tk_root.title() == "B11234567_王小明 — HK5"
    texts = [w.cget("text") for w in ns["LF_subWIN"].winfo_children()]
    assert texts == ["RUN"]


def test_build_reads_utf8_sig(tmp_path, load, tk_root):
    hk = load("hk_tk")
    old_hk(tmp_path, src="﻿" + OLD_HK + "# 中文註解\n")
    ns = hk.build(tmp_path, "HK5", tk_root)
    assert "LF" in ns["SEEN"]


def test_run_homework_shows_syntax_error_with_line(tmp_path, load, fake_tk):
    hk = load("hk_tk")
    old_hk(tmp_path, src="def HK5():\n    pass\nx = (\n")
    assert hk.run_homework(tmp_path, "HK5") == 0
    [(title, message)] = fake_tk.errors
    assert "語法錯誤：第 3 行" in message
    assert "HK5.txt" in message  # traceback 全文：看得出是哪個檔


def test_run_homework_reports_missing_module_with_pip_hint(tmp_path, load, fake_tk, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.setitem(sys.modules, "sklearn", None)  # 這台有沒有裝都一樣：import sklearn 一定丟 ModuleNotFoundError
    old_hk(tmp_path, src="import sklearn\ndef HK5():\n    pass\n")
    hk.run_homework(tmp_path, "HK5")
    [(_, message)] = fake_tk.errors
    assert "ModuleNotFoundError" in message
    assert f"缺 sklearn：{sys.executable} -m pip install scikit-learn" in message


@pytest.mark.parametrize("src", ["x = 1\nprint('hi')\n", OLD_HK.replace("{hk}", "HK3")])
def test_run_homework_says_when_it_is_not_this_homework(tmp_path, load, fake_tk, src):
    hk = load("hk_tk")
    old_hk(tmp_path, src=src)  # 檔名是 HK5.txt，裡面沒有 def HK5()（交錯份、或根本不是作業）
    hk.run_homework(tmp_path, "HK5")
    [(_, message)] = fake_tk.errors
    assert message.startswith("這份不是 HK5 的作業檔：檔裡沒有 def HK5()")


def test_run_homework_says_when_the_file_is_not_utf8(tmp_path, load, fake_tk):
    hk = load("hk_tk")
    old_hk(tmp_path, src="def HK5():\n    print('中文')\n", encoding="cp950")
    hk.run_homework(tmp_path, "HK5")
    [(_, message)] = fake_tk.errors
    assert message.startswith("這個檔不是 UTF-8")


def test_run_homework_writes_the_log_file(tmp_path, load, fake_tk, capsys):
    hk = load("hk_tk")
    old_hk(tmp_path, src="print('開始')\ndef HK5():\n    print('你好')\n")
    out_before = sys.stdout
    hk.run_homework(tmp_path, "HK5")
    assert sys.stdout is out_before  # 跑完放回去
    log = (tmp_path / hk.LOG).read_text(encoding="utf-8")
    assert "開始" in log and "你好" in log
    assert "你好" in capsys.readouterr().out  # 終端機也看得到
    assert fake_tk.errors == []


def test_callback_exception_goes_to_messagebox(tmp_path, load, fake_tk):
    hk = load("hk_tk")
    old_hk(tmp_path, src="def HK5():\n    pass\n")
    hk.run_homework(tmp_path, "HK5")
    [root] = fake_tk.roots
    try:
        raise TypeError("按了 RUN 之後炸了")
    except TypeError as exc:
        root.report_callback_exception(TypeError, exc, exc.__traceback__)
    [(title, message)] = fake_tk.errors
    assert title == "這份作業出錯了"
    assert "TypeError: 按了 RUN 之後炸了" in message


def test_main_usage(load, capsys):
    hk = load("hk_tk")
    assert hk.main([]) == 2
    assert "用法" in capsys.readouterr().err


def test_main_runs_the_homework(load, monkeypatch, tmp_path):
    hk = load("hk_tk")
    calls = []
    monkeypatch.setattr(hk, "run_homework", lambda folder, name: calls.append((folder, name)) or 0)
    assert hk.main([str(tmp_path), "HK5"]) == 0
    assert calls == [(tmp_path, "HK5")]


# ── Task 2：墊片與 launch、venv_python、course_root ──


def course_copy(tmp_path):
    """tmp_path/科學計算：放一份真的 hk_tk.py（墊片往上找的就是它）與 hk_page.py（新格式要複製的殼），回課程資料夾。"""
    course = tmp_path / "科學計算"
    course.mkdir(parents=True)
    for name in ("hk_tk.py", "hk_page.py"):
        (course / name).write_bytes((COURSE / name).read_bytes())
    return course


def test_course_root_walks_up_two_levels(tmp_path, load):
    hk = load("hk_tk")
    course = course_copy(tmp_path)
    (course / "HK5" / "B1").mkdir(parents=True)
    assert hk.course_root(course / "HK5" / "B1") == course
    assert hk.course_root(course / "HK5") == course
    assert hk.course_root(course) == course
    assert hk.course_root(tmp_path) is None


def test_venv_python_platform_path(tmp_path, load, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.setattr(sys, "platform", "darwin")
    assert hk.python_in(tmp_path / ".venv") == tmp_path / ".venv" / "bin" / "python"
    monkeypatch.setattr(sys, "platform", "win32")
    assert hk.python_in(tmp_path / ".venv") == tmp_path / ".venv" / "Scripts" / "python.exe"
    assert hk.venv_python(tmp_path) is None  # 不存在
    assert hk.venv_python(None) is None
    exe = tmp_path / ".venv" / "Scripts" / "python.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    assert hk.venv_python(tmp_path) == exe


def test_write_stub_is_idempotent(tmp_path, load):
    hk = load("hk_tk")
    stub = hk.write_stub(tmp_path)
    assert stub == tmp_path / "iplot.py" and stub.read_text(encoding="utf-8") == hk.STUB
    os.utime(stub, (1_000_000, 1_000_000))
    assert hk.write_stub(tmp_path) == stub
    assert stub.stat().st_mtime == 1_000_000  # 內容一樣就不碰
    assert hk.STUB.startswith('"""按下去用課程的 Python 另開視窗跑這個資料夾的 t2026fscSpace/HKn.txt（舊格式）')


def test_write_stub_leaves_a_real_module_alone(tmp_path, load):
    hk = load("hk_tk")
    mine = 'HOMEWORK = dict(name="HK13")\n'  # 新格式的作業本身，不是墊片
    (tmp_path / "iplot.py").write_text(mine, encoding="utf-8")
    hk.write_stub(tmp_path)
    assert (tmp_path / "iplot.py").read_text(encoding="utf-8") == mine
    (tmp_path / "iplot.py").write_text(hk.STUB.replace("（舊格式）", "（舊的墊片）"), encoding="utf-8")
    hk.write_stub(tmp_path)  # 舊版本的墊片：換成這一版
    assert (tmp_path / "iplot.py").read_text(encoding="utf-8") == hk.STUB


@pytest.mark.parametrize("level", [("HK5",), ("HK5", "B1")])
def test_stub_runs_through_the_real_runner(tmp_path, load, monkeypatch, level):
    from core.runner import run_module
    from core.scan import module_info

    hk = load("hk_tk")
    course = course_copy(tmp_path)
    folder = course.joinpath(*level)
    old_hk(folder)
    hk.write_stub(folder)
    popen = FakePopen()
    monkeypatch.setattr("subprocess.Popen", popen)
    app = HwApp(tmp_path, folder)
    result = run_module(module_info(folder, course, "here"), app)
    assert result.ok, result.error
    assert popen.argvs == [[sys.executable, str(course / "hk_tk.py"), str(folder), "HK5"]]
    assert popen.calls[0][1]["cwd"] == str(folder)
    assert str(course) not in sys.path  # 墊片 import 完就把課程資料夾從 sys.path 拿掉


def test_launch_argv_uses_venv_python(tmp_path, load):
    hk = load("hk_tk")
    course = course_copy(tmp_path)
    vpy = hk.python_in(course / ".venv")
    vpy.parent.mkdir(parents=True)
    vpy.write_text("", encoding="utf-8")
    folder = course / "HK5" / "B1"
    old_hk(folder)
    app, popen = HwApp(tmp_path, folder), FakePopen()
    hk.launch(app, folder, popen=popen)
    assert popen.argvs == [[str(vpy), str(course / "hk_tk.py"), str(folder), "HK5"]]
    assert popen.calls[0][1] == {"cwd": str(folder)}
    assert app.logs == ["B1：HK5 的視窗開了（在 Dock 上找 Python）"]


def test_launch_without_venv_falls_back_and_says_so(tmp_path, load):
    hk = load("hk_tk")
    course = course_copy(tmp_path)
    folder = course / "HK5"
    old_hk(folder)
    app, popen = HwApp(tmp_path, folder), FakePopen()
    hk.launch(app, folder, popen=popen)
    assert popen.argvs[0][0] == sys.executable
    assert any("先按「科學計算」裝課程套件" in line for line in app.logs)
    assert app.logs[-1] == "HK5：HK5 的視窗開了（在 Dock 上找 Python）"


def test_launch_without_hk_file_only_logs(tmp_path, load):
    hk = load("hk_tk")
    course = course_copy(tmp_path)
    (course / "HK5").mkdir()
    app, popen = HwApp(tmp_path, course / "HK5"), FakePopen()
    hk.launch(app, course / "HK5", popen=popen)
    assert popen.calls == []
    assert app.logs == ["HK5：這個資料夾裡沒有 t2026fscSpace/HK*.txt"]
    old_hk(tmp_path / "外面")
    hk.launch(app, tmp_path / "外面", popen=popen)
    assert popen.calls == []
    assert app.logs[-1] == "找不到課程資料夾（上層沒有 hk_tk.py）"


# ── Task 3：gather 與匯入老師的作業包 ──


class Cp950Name(zipfile.ZipInfo):
    """不設 UTF-8 旗標、檔名是 cp950 位元組的成員（Windows 上的中文壓縮程式常這樣做）。"""

    def _encodeFilenameFlags(self):
        return self.filename.encode("cp950"), self.flag_bits & ~0x800


def make_zip(path, members):
    """members：{名字: bytes 或 str}；名字是 Cp950Name 就照 cp950 寫。回 path。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data.encode("utf-8") if isinstance(data, str) else data)
    return path


def test_gather_unzips_nested_and_decodes_cp950(tmp_path, load):
    hk = load("hk_tk")
    inner = make_zip(tmp_path / "src" / "inner.zip", {"深/HK5.txt": "inner"})
    outer = make_zip(tmp_path / "src" / "HK5.zip", {Cp950Name("王小明/HK5.txt"): "cp950 名字",
                                                     "inner.zip": inner.read_bytes(),
                                                     "李大華/HK5.txt": "utf-8 名字"})
    result = hk.gather([outer], tmp_path / "work")
    root = result.root
    assert root == tmp_path / "work" / "原件"
    assert (root / "HK5" / "王小明" / "HK5.txt").read_text(encoding="utf-8") == "cp950 名字"
    assert (root / "HK5" / "李大華" / "HK5.txt").read_text(encoding="utf-8") == "utf-8 名字"
    assert (root / "HK5" / "inner" / "深" / "HK5.txt").read_text(encoding="utf-8") == "inner"
    assert result.skipped == 0


def test_gather_copies_folders_and_files(tmp_path, load):
    hk = load("hk_tk")
    (tmp_path / "kit" / "HK1Space").mkdir(parents=True)
    (tmp_path / "kit" / "HK1.txt").write_text("hk1", encoding="utf-8")
    (tmp_path / "loose.py").write_text("x = 1", encoding="utf-8")
    root = hk.gather([tmp_path / "kit", tmp_path / "loose.py"], tmp_path / "work").root
    assert (root / "kit" / "HK1.txt").read_text(encoding="utf-8") == "hk1"
    assert (root / "kit" / "HK1Space").is_dir()
    assert (root / "loose.py").read_text(encoding="utf-8") == "x = 1"


def test_gather_skips_dotdot_members(tmp_path, load):
    hk = load("hk_tk")
    bad = make_zip(tmp_path / "src" / "bad.zip", {"../x.txt": "out", "/abs.txt": "abs", "ok/HK5.txt": "ok"})
    result = hk.gather([bad], tmp_path / "work" / "deep")
    assert result.skipped == 2
    assert not (tmp_path / "work" / "deep" / "原件" / "x.txt").exists()
    assert not list(tmp_path.rglob("x.txt")) and not list(tmp_path.rglob("abs.txt"))
    assert (result.root / "bad" / "ok" / "HK5.txt").exists()


def teacher_kit(tmp_path, hks=("HK1", "HK2", "HK5"), text="v1"):
    """老師的 t2026fscSpace/：每份 HKn.txt；HK5Space/a.pdf；HK1Space/ 是空的。"""
    kit = tmp_path / "老師" / "t2026fscSpace"
    kit.mkdir(parents=True, exist_ok=True)
    for name in hks:
        (kit / f"{name}.txt").write_text(f"# {name} {text}\n", encoding="utf-8")
    (kit / "HK5Space").mkdir(exist_ok=True)
    (kit / "HK5Space" / "a.pdf").write_bytes(b"%PDF")
    (kit / "HK1Space").mkdir(exist_ok=True)
    (kit / "HK1_threebody_backup.txt").write_text("不是作業", encoding="utf-8")
    return kit


def test_import_kit_builds_hk_folders(tmp_path, load):
    hk = load("hk_tk")
    course = course_copy(tmp_path)
    app = HwApp(tmp_path, course)
    said = hk.import_kit(app, [teacher_kit(tmp_path)], course)
    for name in ("HK1", "HK2", "HK5"):
        assert (course / name / "iplot.py").read_text(encoding="utf-8") == hk.STUB
        assert (course / name / "t2026fscSpace" / f"{name}.txt").read_text(encoding="utf-8") == f"# {name} v1\n"
        assert (course / name / "t2026fscSpace" / f"{name}Space").is_dir()
    assert (course / "HK5" / "t2026fscSpace" / "HK5Space" / "a.pdf").read_bytes() == b"%PDF"
    assert not (course / "HK1_threebody_backup").exists()
    assert said == "匯入了 HK1、HK2、HK5（新 3、更新 0）"
    assert app.logs == [said] and app.rescans == 1


def test_import_kit_names_a_run_as_a_range(tmp_path, load):
    hk = load("hk_tk")
    course = course_copy(tmp_path)
    zipped = make_zip(tmp_path / "t2026fscSpace.zip",
                      {f"t2026fscSpace/HK{n}.txt": f"# {n}" for n in range(1, 13)})
    said = hk.import_kit(HwApp(tmp_path, course), [zipped], course)
    assert said == "匯入了 HK1–HK12（新 12、更新 0）"
    assert sorted(p.name for p in course.iterdir() if p.is_dir()) == sorted(f"HK{n}" for n in range(1, 13))


def test_import_kit_twice_updates_text_keeps_stub(tmp_path, load):
    hk = load("hk_tk")
    course = course_copy(tmp_path)
    app = HwApp(tmp_path, course)
    hk.import_kit(app, [teacher_kit(tmp_path)], course)
    stub = course / "HK5" / "iplot.py"
    os.utime(stub, (1_000_000, 1_000_000))
    said = hk.import_kit(app, [teacher_kit(tmp_path, text="v2")], course)
    assert (course / "HK5" / "t2026fscSpace" / "HK5.txt").read_text(encoding="utf-8") == "# HK5 v2\n"
    assert stub.stat().st_mtime == 1_000_000
    assert said == "匯入了 HK1、HK2、HK5（新 0、更新 3）"
    assert app.rescans == 2


def test_import_kit_with_nothing_says_so(tmp_path, load):
    hk = load("hk_tk")
    course = course_copy(tmp_path)
    (tmp_path / "空" / "x.txt").parent.mkdir()
    (tmp_path / "空" / "x.txt").write_text("x", encoding="utf-8")
    app = HwApp(tmp_path, course)
    said = hk.import_kit(app, [tmp_path / "空"], course)
    assert said == "收到的東西裡沒有 HK<n>.txt；要給的是老師的 t2026fscSpace 資料夾或它的 zip"
    assert app.logs == [said] and app.rescans == 0
    assert sorted(p.name for p in course.iterdir()) == ["hk_page.py", "hk_tk.py"]


# ── Task 4：課程 .venv、import 掃描、pip 名對照、一個一個裝 ──


def test_course_packages_adds_mlx_only_on_apple_silicon(load):
    hk = load("hk_tk")
    mac_arm = hk.course_packages("darwin", "arm64")
    assert mac_arm[-1] == "mlx-lm" and mac_arm[:-1] == hk.COURSE_PACKAGES
    assert hk.course_packages("darwin", "x86_64") == hk.COURSE_PACKAGES
    assert hk.course_packages("win32", "AMD64") == hk.COURSE_PACKAGES
    assert {"PyYAML", "tqdm"} <= set(hk.COURSE_PACKAGES)  # pykan 沒寫、但 import kan 要（Task 0 量的）


def test_course_batches_split_basic_from_heavy(load):
    hk = load("hk_tk")
    basic, heavy = hk.course_batches("darwin", "arm64")
    assert basic + heavy[:-1] == hk.COURSE_PACKAGES and heavy[-1] == "mlx-lm"
    assert "numpy" in basic and "torch" in heavy and "torch" not in basic
    assert hk.course_batches("linux", "x86_64")[1] == tuple(p for p in heavy if p != "mlx-lm")


def test_pip_name_table_and_default(load):
    hk = load("hk_tk")
    assert hk.pip_name("cv2") == "opencv-python"
    assert hk.pip_name("sklearn") == "scikit-learn"
    assert hk.pip_name("kan") == "pykan"
    assert hk.pip_name("mlx_lm") == "mlx-lm"
    assert hk.pip_name("foo") == "foo"


def test_scan_imports_walks_into_functions(tmp_path, load):
    hk = load("hk_tk")
    assert hk.scan_imports(old_hk(tmp_path)) == {"tkinter", "json", "sklearn"}
    bad = tmp_path / "bad.txt"
    bad.write_text("import numpy\nx = (\n", encoding="utf-8")
    assert hk.scan_imports(bad) == set()  # 讀不懂就當沒有
    assert hk.scan_imports(tmp_path / "沒有這個檔.txt") == set()
    rel = tmp_path / "rel.py"
    rel.write_text("from . import x\nfrom .y import z\nimport a.b.c\n", encoding="utf-8")
    assert hk.scan_imports(rel) == {"a"}


def test_third_party_drops_stdlib_and_siblings(tmp_path, load):
    hk = load("hk_tk")
    (tmp_path / "helper.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    names = {"json", "os", "__future__", "helper", "pkg", "numpy", "sklearn"}
    assert hk.third_party(names, tmp_path) == {"numpy", "sklearn"}


def test_ensure_venv_argv_and_no_install_guard(tmp_path, load, monkeypatch):
    hk = load("hk_tk")
    said, popen = [], FakePopen()
    with pytest.raises(RuntimeError, match="HK_NO_INSTALL"):
        hk.ensure_venv(tmp_path / ".venv", said.append, popen=popen)
    assert popen.calls == []
    monkeypatch.delenv("HK_NO_INSTALL")
    got = hk.ensure_venv(tmp_path / ".venv", said.append, popen=popen, python="/py")
    assert popen.argvs == [["/py", "-m", "venv", str(tmp_path / ".venv")]]
    assert got == hk.python_in(tmp_path / ".venv") and said == ["在建 .venv …"]
    got.parent.mkdir(parents=True)
    got.write_text("", encoding="utf-8")
    assert hk.ensure_venv(tmp_path / ".venv", said.append, popen=popen) == got
    assert len(popen.calls) == 1  # 已經有了：不再建
    with pytest.raises(RuntimeError, match="建不了"):
        hk.ensure_venv(tmp_path / "v2", said.append, popen=FakePopen(fail=lambda argv: True))


def test_installed_parses_json_and_normalizes(tmp_path, load):
    hk = load("hk_tk")
    popen = FakePopen(output=lambda argv: ['["Scikit_Learn","numpy","PyYAML","zope.interface"]\n'])
    assert hk.installed(Path("/venv/python"), popen=popen) == {"scikit-learn", "numpy", "pyyaml", "zope-interface"}
    argv, kw = popen.calls[0]
    assert argv[:2] == ["/venv/python", "-c"] and "importlib.metadata" in argv[2]
    assert "shell" not in kw
    assert hk.installed(Path("/x"), popen=FakePopen(output=lambda argv: ["壞掉\n"])) == set()


def test_missing_keeps_order_and_dedupes(load):
    hk = load("hk_tk")
    popen = FakePopen(output=lambda argv: ['["numpy","scikit-learn"]'])
    got = hk.missing(Path("/py"), ["torch", "numpy", "scikit_learn", "Pillow", "torch"], popen=popen)
    assert got == ["torch", "Pillow"]


def pip_popen(fail=(), lines=("Collecting x\n", "Successfully installed x\n")):
    """假的 pip：argv 最後一個是套件名；在 fail 裡的回非零，輸出帶一行 ERROR。"""
    def output(argv):
        if argv[-1] in fail:
            return ["Collecting x\n", "  some detail\n", f"ERROR: No matching distribution found for {argv[-1]}\n"]
        return list(lines)
    return FakePopen(output=output, fail=lambda argv: argv[-1] in fail)


def test_install_one_at_a_time_without_shell(tmp_path, load, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.delenv("HK_NO_INSTALL")
    popen = pip_popen()
    ok, failed = hk.install(Path("/venv/bin/python"), ["pandas", "PyWavelets"], [].append, popen=popen)
    assert ok == ["pandas", "PyWavelets"] and failed == []
    assert popen.argvs == [["/venv/bin/python", "-m", "pip", "install", "--no-input", "--disable-pip-version-check", p]
                           for p in ("pandas", "PyWavelets")]
    for _, kw in popen.calls:
        assert "shell" not in kw and kw["text"] is True


def test_install_keeps_going_when_one_package_fails(tmp_path, load, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.delenv("HK_NO_INSTALL")
    popen = pip_popen(fail={"mlx-lm"})
    ok, failed = hk.install(Path("/py"), ["mlx-lm", "pandas"], [].append, popen=popen)
    assert ok == ["pandas"]
    assert failed == [("mlx-lm", "ERROR: No matching distribution found for mlx-lm")]
    assert hk.summary_of_install(ok, failed) == "已裝 pandas；裝不了 mlx-lm（ERROR: No matching distribution found for mlx-lm）"


def test_install_reason_falls_back_to_the_last_lines(load, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.delenv("HK_NO_INSTALL")
    lines = [f"line {n}\n" for n in range(8)]
    popen = FakePopen(output=lambda argv: lines, fail=lambda argv: True)
    _, failed = hk.install(Path("/py"), ["x"], [].append, popen=popen)
    assert failed == [("x", "line 3 / line 4 / line 5 / line 6 / line 7")]


def test_install_rejects_bad_names(load):
    hk = load("hk_tk")
    popen = FakePopen()
    ok, failed = hk.install(Path("/py"), ["-x", "a b", "numpy"], [].append, popen=popen)
    assert ok == [] and popen.calls == []
    assert failed == [("-x", "名字不合法"), ("a b", "名字不合法"), ("numpy", "HK_NO_INSTALL")]


def test_install_says_mlx_needs_apple_silicon(load, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.delenv("HK_NO_INSTALL")
    monkeypatch.setattr(hk.platform, "machine", lambda: "x86_64")
    popen = pip_popen()
    ok, failed = hk.install(Path("/py"), ["mlx-lm", "numpy"], [].append, popen=popen)
    assert ok == ["numpy"] and popen.argvs[0][-1] == "numpy" and len(popen.calls) == 1
    assert failed == [("mlx-lm", "這台機器裝不了，HK9 要在 Apple Silicon 的 Mac 上看")]


def test_install_says_progress_every_five_seconds(tmp_path, load, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.delenv("HK_NO_INSTALL")
    ticks = iter([0, 4, 6, 12])
    said = []
    popen = pip_popen(lines=("Collecting torch\n", "Downloading torch (127 MB)\n", "Installing collected packages\n"))
    hk.install(Path("/py"), ["torch"], said.append, popen=popen, clock=lambda: next(ticks, 12))
    assert said == ["torch：Downloading torch (127 MB)", "torch：Installing collected packages"]


def test_summary_of_install_empty(load):
    hk = load("hk_tk")
    assert hk.summary_of_install([], []) == ""
    assert hk.summary_of_install(["a", "b"], []) == "已裝 a、b"


# ── Task 5：收作業（舊格式）──


def course_with_hk(tmp_path, hk_name="HK5", space=True, venv=False):
    """課程資料夾＋已經匯入的 HK5/（墊片、老師的 HK5.txt、HK5Space/a.pdf）；venv=True 再放一個假的 .venv Python。
    回（課程, HK5 資料夾）。"""
    course = course_copy(tmp_path)
    folder = course / hk_name
    old_hk(folder, hk_name)
    if space:
        (folder / "t2026fscSpace" / f"{hk_name}Space").mkdir()
        (folder / "t2026fscSpace" / f"{hk_name}Space" / "a.pdf").write_bytes(b"%PDF")
    (folder / "iplot.py").write_text("# 墊片\n", encoding="utf-8")
    if venv:
        exe = course / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        exe.parent.mkdir(parents=True)
        exe.write_text("", encoding="utf-8")
    return course, folder


def handed_in(tmp_path, files):
    """學生交的檔：{相對路徑: 內容}，寫在 tmp_path/交/ 底下；回（那個資料夾, [每個檔]）。"""
    base = tmp_path / "交"
    out = []
    for rel, text in files.items():
        f = base / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        out.append(f)
    return base, out


GOOD = OLD_HK.replace("{hk}", "HK5")


def test_student_name_rules(tmp_path, load):
    hk = load("hk_tk")
    root, taken = tmp_path / "原件" / "HK5", set()
    assert hk.student_name(root, root / "B11234567_王小明.txt", taken) == "B11234567_王小明"
    assert hk.student_name(root, root / "李大華" / "作業" / "HK5.txt", taken) == "李大華"
    decomposed = unicodedata.normalize("NFD", "café")
    assert hk.student_name(root, root / decomposed / "x.txt", taken) == unicodedata.normalize("NFC", "café")
    assert hk.student_name(root, root / 'a:b*c?"d<e>f|g.txt', taken) == "abcdefg"
    assert hk.student_name(root, root / "..." / "x.txt", taken) == "未命名"
    assert hk.student_name(root, root / ".hidden.txt", taken) == "hidden"
    assert hk.student_name(root, root / "B11234567_王小明.py", taken) == "B11234567_王小明-2"
    assert hk.student_name(root, root / "B11234567_王小明.py", taken) == "B11234567_王小明-3"


def test_classify_old_broken_none_and_not_utf8(tmp_path, load):
    hk = load("hk_tk")
    files = {"old.txt": GOOD, "broken.txt": "def HK5(:\n", "none.txt": "print('hi')\n",
             "nolf.txt": "def HK5():\n    pass\n"}
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "big5.txt").write_bytes("def HK5():\n    LF_subWIN\n    print('中文')\n".encode("cp950"))
    assert hk.classify(tmp_path / "old.txt") == ("old", "HK5")
    assert hk.classify(tmp_path / "broken.txt") == ("broken", None)
    assert hk.classify(tmp_path / "none.txt") == ("none", None)
    assert hk.classify(tmp_path / "nolf.txt") == ("none", None)  # 有 def HK5( 但沒用到 LF_subWIN
    assert hk.classify(tmp_path / "big5.txt") == ("not-utf8", None)


def test_kit_space_finds_the_teachers_space(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    assert hk.kit_space(folder, "HK5") == folder / "t2026fscSpace" / "HK5Space"
    _, bare = course_with_hk(tmp_path / "b", space=False)
    assert hk.kit_space(bare, "HK5") is None


def test_collect_places_old_format_with_stub_and_space(tmp_path, load):
    hk = load("hk_tk")
    course, folder = course_with_hk(tmp_path, venv=True)
    _, [b1] = handed_in(tmp_path, {"B1.txt": GOOD})
    app = HwApp(tmp_path, folder)
    popen = FakePopen(output=lambda argv: ['["scikit-learn"]'])
    said = hk.collect(app, [b1], folder, popen=popen)
    dest = folder / "B1"
    assert (dest / "t2026fscSpace" / "HK5.txt").read_bytes() == b1.read_bytes()
    assert (dest / "t2026fscSpace" / "HK5Space" / "a.pdf").read_bytes() == b"%PDF"
    assert (dest / "iplot.py").read_text(encoding="utf-8") == hk.STUB
    assert said == "收了 1 份進 HK5（新 1、覆蓋 0）"
    assert app.logs[-1] == said and app.rescans == 1 and app.confirms == []


def test_collect_names_by_student_folder_and_decodes_cp950(tmp_path, load):
    hk = load("hk_tk")
    course, folder = course_with_hk(tmp_path)
    zipped = make_zip(tmp_path / "下載" / "HK5.zip", {Cp950Name("王小明/HK5.txt"): GOOD,
                                                      Cp950Name("李大華/HK5.txt"): GOOD})
    said = hk.collect(HwApp(tmp_path, folder), [zipped], folder)
    students = sorted(p.name for p in folder.iterdir() if (p / "iplot.py").exists())
    assert students == ["李大華", "王小明"]
    assert said.startswith("收了 2 份進 HK5（新 2、覆蓋 0）")


def test_collect_names_through_a_single_top_folder(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    zipped = make_zip(tmp_path / "下載" / "全班.zip", {"HK5/B1/HK5.txt": GOOD, "HK5/B2/HK5.txt": GOOD})
    hk.collect(HwApp(tmp_path, folder), [zipped], folder)
    assert (folder / "B1" / "iplot.py").exists() and (folder / "B2" / "iplot.py").exists()


def test_collect_keeps_and_lists_broken_files(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    _, files = handed_in(tmp_path, {"好.txt": GOOD, "壞.txt": "def HK5(:\n    LF_subWIN\n"})
    said = hk.collect(HwApp(tmp_path, folder), files, folder)
    assert (folder / "壞" / "t2026fscSpace" / "HK5.txt").exists()
    assert (folder / "壞" / "iplot.py").exists()
    assert "收了 2 份進 HK5（新 2、覆蓋 0）" in said
    assert "；1 份有語法錯誤（壞）" in said
    assert "不是 HK5 的作業檔" not in said  # 語法錯的不重複列


def test_collect_lists_wrong_hk_and_not_utf8(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    base, files = handed_in(tmp_path, {"交錯.txt": OLD_HK.replace("{hk}", "HK3"), "空的.py": "x = 1\n"})
    big5 = base / "big5.txt"
    big5.write_bytes("def HK5():\n    LF_subWIN\n    print('中文')\n".encode("cp950"))
    said = hk.collect(HwApp(tmp_path, folder), [*files, big5], folder)
    assert "；2 份不是 HK5 的作業檔（交錯、空的）" in said
    assert "；1 份不是 UTF-8（big5）" in said
    assert (folder / "交錯" / "t2026fscSpace" / "HK5.txt").exists()  # 照放


def test_collect_counts_files_it_skips(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    zipped = make_zip(tmp_path / "HK5.zip", {"B1/HK5.txt": GOOD, "B1/報告.pdf": b"%PDF", "B2/圖.png": b"png",
                                             "__MACOSX/B1/._HK5.txt": "x", "../逃.txt": "x"})
    said = hk.collect(HwApp(tmp_path, folder), [zipped], folder)
    assert said.startswith("收了 1 份進 HK5（新 1、覆蓋 0）")
    assert "；略過 2 個不是 .py/.txt 的檔" in said
    assert "；擋掉 1 個路徑不安全" in said


def test_collect_says_when_the_teachers_space_is_missing(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path, space=False)
    _, [b1] = handed_in(tmp_path, {"B1.txt": GOOD})
    said = hk.collect(HwApp(tmp_path, folder), [b1], folder)
    assert (folder / "B1" / "t2026fscSpace" / "HK5Space").is_dir()  # 空的也要在（HK11 會 chdir 進去）
    assert "；老師的 HK5Space 還沒匯入，要用資料檔的 case 會缺檔" in said


def test_collect_confirms_once_and_installs_once(tmp_path, load, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.delenv("HK_NO_INSTALL")
    course, folder = course_with_hk(tmp_path, venv=True)
    a = GOOD + "def extra():\n    import pandas\n"
    _, files = handed_in(tmp_path, {"B1.txt": a, "B2.txt": a})
    popen = FakePopen(output=lambda argv: ['["numpy"]'] if "-c" in argv else ["Successfully installed\n"])
    app = HwApp(tmp_path, folder)
    said = hk.collect(app, files, folder, popen=popen)
    [question] = app.confirms
    assert question == "這批用到還沒裝的套件：pandas、scikit-learn。現在裝進 科學計算/.venv？"
    pip_calls = [argv for argv in popen.argvs if "pip" in argv]
    assert [argv[-1] for argv in pip_calls] == ["pandas", "scikit-learn"]
    assert pip_calls[0][0] == str(hk.python_in(course / ".venv"))
    assert said.endswith("；已裝 pandas、scikit-learn")


def test_collect_cancel_installs_nothing(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path, venv=True)
    _, files = handed_in(tmp_path, {"B1.txt": GOOD})
    popen = FakePopen(output=lambda argv: ['[]'])
    app = HwApp(tmp_path, folder)
    app.answers = [False]
    said = hk.collect(app, files, folder, popen=popen)
    assert [argv for argv in popen.argvs if "pip" in argv] == []
    assert "；沒裝：scikit-learn" in said


def test_collect_without_venv_skips_packages(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    _, files = handed_in(tmp_path, {"B1.txt": GOOD})
    popen = FakePopen()
    app = HwApp(tmp_path, folder)
    said = hk.collect(app, files, folder, popen=popen)
    assert app.confirms == [] and popen.calls == []
    assert said.endswith("；.venv 還沒建，套件沒掃")


def test_recollect_overwrites_and_counts_separately(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    zipped = make_zip(tmp_path / "HK5.zip", {"B1/HK5.txt": GOOD, "B2/HK5.txt": GOOD})
    app = HwApp(tmp_path, folder)
    hk.collect(app, [zipped], folder)
    again = make_zip(tmp_path / "HK5-重交.zip", {"B1/HK5.txt": GOOD + "# 改過\n"})
    said = hk.collect(app, [again], folder)
    assert said.startswith("收了 1 份進 HK5（新 0、覆蓋 1）")
    assert (folder / "B1" / "t2026fscSpace" / "HK5.txt").read_text(encoding="utf-8").endswith("# 改過\n")
    assert not (folder / "B1-2").exists()
    assert app.rescans == 2


def test_collect_on_student_folder_redirects(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    (folder / "B1").mkdir()
    _, files = handed_in(tmp_path, {"B9.txt": GOOD})
    app = HwApp(tmp_path, folder / "B1")
    said = hk.collect(app, files, folder / "B1")
    assert said == "這是學生的資料夾；作業要收進 HK5（按「科學計算」底下的「收作業」）"
    assert app.logs == [said] and app.rescans == 0
    assert not (folder / "B1" / "B9").exists()


def test_collect_with_nothing_useful_says_so(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    zipped = make_zip(tmp_path / "HK5.zip", {"B1/報告.pdf": b"%PDF"})
    app = HwApp(tmp_path, folder)
    said = hk.collect(app, [zipped], folder)
    assert said == "收到的東西裡沒有 .py 或 .txt"
    assert app.rescans == 0


def test_collect_refuses_paths_outside_hk_folder(tmp_path, load, monkeypatch):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    _, files = handed_in(tmp_path, {"B1.txt": GOOD})
    monkeypatch.setattr(hk, "student_name", lambda root, file, taken: "../../逃出去")
    said = hk.collect(HwApp(tmp_path, folder), files, folder)
    assert not (tmp_path / "逃出去").exists() and not (folder.parent / "逃出去").exists()
    assert said.startswith("收了 0 份進 HK5")


# ── Task 6：批次模式（沒有 iPLoT 也能收、名單視窗）──


def test_hk_in_name(load):
    hk = load("hk_tk")
    assert hk.hk_in_name("HK5") == "HK5"
    assert hk.hk_in_name("2026科學計算_hk12_全班") == "HK12"
    assert hk.hk_in_name("作業") is None
    assert hk.hk_in_name("HK05_全班") == "HK5"  # 補零的也是老師的 HK5（最終審查）
    assert hk.hk_in_name("CHK5_x") is None  # 前面接字母的不算


def test_batch_collects_next_to_the_zip_with_kit_space(tmp_path, load):
    hk = load("hk_tk")
    zipped = make_zip(tmp_path / "下載" / "HK5.zip", {"B1/HK5.txt": GOOD})
    kit = teacher_kit(tmp_path)
    said = []
    out = hk.batch(zipped, kit=kit, say=said.append)
    assert out == tmp_path / "下載" / "HK5_收件"
    assert (out / "B1" / "t2026fscSpace" / "HK5.txt").read_bytes() == GOOD.encode("utf-8")
    assert (out / "B1" / "t2026fscSpace" / "HK5Space" / "a.pdf").read_bytes() == b"%PDF"
    assert (out / "B1" / "iplot.py").exists()
    assert said[-1].startswith("收了 1 份進 HK5（新 1、覆蓋 0）")
    assert said[-1].endswith("；.venv 還沒建，套件沒掃")  # HK_NO_INSTALL：不建 venv，只報
    assert any("HK_NO_INSTALL" in line for line in said)


def test_batch_needs_hk_in_name_or_flag(tmp_path, load):
    hk = load("hk_tk")
    zipped = make_zip(tmp_path / "作業.zip", {"B1/HK5.txt": GOOD})
    with pytest.raises(RuntimeError, match="用 --hk HK5 指定"):
        hk.batch(zipped, say=[].append)
    out = hk.batch(zipped, hk="HK5", out=tmp_path / "收", say=[].append)
    assert (out / "B1" / "t2026fscSpace" / "HK5.txt").exists()


def test_batch_uses_the_venv_flag(tmp_path, load):
    hk = load("hk_tk")
    zipped = make_zip(tmp_path / "HK5.zip", {"B1/HK5.txt": GOOD})
    venv = tmp_path / "我的-venv"
    exe = hk.python_in(venv)
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    popen = FakePopen(output=lambda argv: ['["scikit-learn"]'])
    said = []
    hk.batch(zipped, kit=teacher_kit(tmp_path), venv=venv, say=said.append, popen=popen)
    assert popen.argvs[0][0] == str(exe)  # 用 --venv 那一個問裝了什麼
    assert said[-1] == "收了 1 份進 HK5（新 1、覆蓋 0）"


def test_batch_default_venv_sits_next_to_the_zip(tmp_path, load, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.delenv("HK_NO_INSTALL")
    zipped = make_zip(tmp_path / "下載" / "HK5.zip", {"B1/HK5.txt": "x = 1\n"})
    popen = FakePopen(output=lambda argv: ['[]'])
    hk.batch(zipped, say=[].append, popen=popen)
    assert popen.argvs[0][1:] == ["-m", "venv", str(tmp_path / "下載" / "科學計算-venv")]


def test_cli_app_confirm_with_yes_and_with_typing(load, capsys):
    hk = load("hk_tk")
    said = []
    assert hk.CliApp(said.append, yes=True).confirm("裝嗎？") is True
    assert hk.CliApp(said.append, ask=lambda prompt: "y").confirm("裝嗎？") is True
    assert hk.CliApp(said.append, ask=lambda prompt: "").confirm("裝嗎？") is False

    def eof(prompt):
        raise EOFError

    assert hk.CliApp(said.append, ask=eof).confirm("裝嗎？") is False


def roster_out(tmp_path):
    """HK5_收件/：B1 好的、B2 語法錯、B3 交成 HK3。"""
    out = tmp_path / "HK5_收件"
    old_hk(out / "B1")
    old_hk(out / "B2", src="def HK5(:\n")
    old_hk(out / "B3", src=OLD_HK.replace("{hk}", "HK3"))  # 檔名是 HK5.txt，內容是 HK3
    (out / "t2026fscSpace" / "HK5Space").mkdir(parents=True)  # 老師的 Space：不是學生
    return out


def test_roster_marks(tmp_path, load):
    hk = load("hk_tk")
    out = roster_out(tmp_path)
    assert hk.roster(out) == [("B1", ""), ("B2", "語法錯誤"), ("B3", "不是作業檔")]


def test_roster_marks_missing_packages(tmp_path, load):
    hk = load("hk_tk")
    out = roster_out(tmp_path)
    assert hk.roster(out, have={"numpy"})[0] == ("B1", "缺 scikit-learn")
    assert hk.roster(out, have={"scikit-learn"})[0] == ("B1", "")


def test_roster_window_opens_student_with_venv_python(tmp_path, load, tk_root):
    hk = load("hk_tk")
    out = roster_out(tmp_path)
    popen = FakePopen()
    win = hk.Roster(out, Path("/venv/bin/python"), tk_root, popen=popen)
    assert win.listbox.get(0, "end") == ("B1", "B2    語法錯誤", "B3    不是作業檔")
    assert tk_root.title() == "HK5_收件 — 3 份"
    win.listbox.selection_set(0)
    win.open_button.invoke()
    assert popen.argvs == [["/venv/bin/python", str(COURSE / "hk_tk.py"), str(out / "B1"), "HK5"]]
    assert popen.calls[0][1] == {"cwd": str(out / "B1")}
    win.listbox.selection_clear(0, "end")
    win.open_button.invoke()  # 沒選：不開
    assert len(popen.calls) == 1
    assert "<Double-Button-1>" in win.listbox.bind()  # 雙擊一樣開（Tk 不准用 event_generate 造雙擊）
    win.listbox.selection_set(2)
    win.open_selected()
    assert popen.argvs[-1][2] == str(out / "B3")


def test_main_batch_parses_flags(load, monkeypatch, tmp_path):
    hk = load("hk_tk")
    got = {}

    def fake_batch(source, **kw):
        got.update(kw, source=source)
        return tmp_path / "o"

    shown = []
    monkeypatch.setattr(hk, "batch", fake_batch)
    monkeypatch.setattr(hk, "show_roster", lambda out, python: shown.append((out, python)) or 0)
    argv = ["--batch", "x.zip", "--kit", "k", "--out", "o", "--venv", "v", "--hk", "HK5", "--yes"]
    assert hk.main(argv) == 0
    assert got["source"] == Path("x.zip")
    assert (got["kit"], got["out"], got["venv"], got["hk"], got["yes"]) == (Path("k"), Path("o"), Path("v"), "HK5", True)
    assert shown == [(tmp_path / "o", hk.python_in(Path("v")))]


def test_main_batch_error_is_one_sentence(load, monkeypatch, capsys, tmp_path):
    hk = load("hk_tk")
    zipped = make_zip(tmp_path / "作業.zip", {"B1/HK5.txt": GOOD})
    monkeypatch.setattr(hk, "show_roster", lambda out, python: 0)
    assert hk.main(["--batch", str(zipped)]) == 1
    assert "檔名裡看不出是哪一份作業" in capsys.readouterr().err


# ── Task 7：課程模組「科學計算」與下一層的「匯入作業包」「收作業」──


@pytest.fixture
def course_module(load, monkeypatch, tmp_path):
    """載入 modules/科學計算/iplot.py（它 import 的 hk_tk 就是 load 進來的那一個）；
    hk_tk 的 ensure_venv 換成回假的路徑，missing 依 absent 回缺的，install 記下收到什麼。"""
    import importlib.util

    hk = load("hk_tk")
    spec = importlib.util.spec_from_file_location("course_iplot", COURSE / "iplot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rec = types.SimpleNamespace(hk=hk, mod=mod, absent=set(), installs=[])
    monkeypatch.setattr(hk, "ensure_venv", lambda venv_dir, say, **kw: venv_dir / "bin" / "python")
    monkeypatch.setattr(hk, "missing", lambda python, pkgs, **kw: [p for p in pkgs if p in rec.absent])

    def install(python, pkgs, say, **kw):
        rec.installs.append(list(pkgs))
        return list(pkgs), []

    monkeypatch.setattr(hk, "install", install)
    return rec


def test_course_run_installs_only_missing_after_confirm(tmp_path, course_module):
    c = course_module
    c.absent = {"torch"}
    app = HwApp(tmp_path, COURSE)
    c.mod.run(app)
    [question] = app.confirms
    assert "torch" in question and "約 1.1 GB" in question and "numpy" not in question
    assert c.installs == [["torch"]]
    assert app.logs[-1] == "已裝 torch"


def test_course_run_installs_the_basic_batch_first(tmp_path, course_module):
    c = course_module
    c.absent = {"numpy", "torch"}
    app = HwApp(tmp_path, COURSE)
    c.mod.run(app)
    [question] = app.confirms
    assert "numpy" in question and "torch" not in question and "約 480 MB" in question
    assert c.installs == [["numpy"]]
    assert app.logs[-1] == "已裝 numpy；第二批（HK9–HK12 用的 torch 那些，約 1.1 GB）再按一次「科學計算」"


def test_course_run_says_all_present(tmp_path, course_module):
    c = course_module
    app = HwApp(tmp_path, COURSE)
    c.mod.run(app)
    assert app.confirms == [] and c.installs == []
    assert app.logs[-1] == "課程套件都在"


def test_course_run_cancel_touches_nothing(tmp_path, course_module):
    c = course_module
    c.absent = {"numpy"}
    app = HwApp(tmp_path, COURSE)
    app.answers = [False]
    c.mod.run(app)
    assert c.installs == []
    assert app.logs[-1] == "沒裝"


def test_course_run_says_why_when_the_venv_cannot_be_made(tmp_path, course_module, monkeypatch):
    c = course_module

    def refuse(venv_dir, say, **kw):
        raise RuntimeError("HK_NO_INSTALL：不建 .venv")

    monkeypatch.setattr(c.hk, "ensure_venv", refuse)
    app = HwApp(tmp_path, COURSE)
    c.mod.run(app)
    assert app.logs == ["HK_NO_INSTALL：不建 .venv"] and app.confirms == []


def test_course_on_files_imports_kit(tmp_path, course_module, monkeypatch):
    c = course_module
    got = []
    monkeypatch.setattr(c.hk, "import_kit", lambda app, paths, course: got.append((app, paths, course)))
    app = HwApp(tmp_path, COURSE)
    c.mod.on_files(app, [str(tmp_path / "t2026fscSpace")])
    assert got == [(app, [tmp_path / "t2026fscSpace"], COURSE)]


def test_course_module_scans_as_module_with_icon(load):
    from core.scan import find_children, module_info

    info = module_info(COURSE, COURSE.parent, "here")
    assert info.icon == "🎓" and info.accepts_files and info.has_run and info.error is None
    children = {c.name: c for c in find_children(COURSE, COURSE.parent)}
    assert {"匯入作業包", "收作業"} <= set(children)
    assert all(children[n].has_run and children[n].error is None for n in ("匯入作業包", "收作業"))
    assert not any(n in children for n in ("examples", ".venv"))


def course_with_buttons(tmp_path):
    """tmp 的課程資料夾：真的 hk_tk.py 與兩顆按鈕的 iplot.py 複本。"""
    course = course_copy(tmp_path)
    for name in ("匯入作業包", "收作業"):
        (course / name).mkdir()
        (course / name / "iplot.py").write_bytes((COURSE / name / "iplot.py").read_bytes())
    return course


def press(folder, app, course):
    from core.runner import run_module
    from core.scan import module_info

    result = run_module(module_info(folder, course, "child"), app)
    assert result.ok, result.error
    return result


def test_import_button_chooses_a_folder(tmp_path, load):
    course = course_with_buttons(tmp_path)
    app = HwApp(tmp_path, course / "匯入作業包")
    app.chosen_folder = teacher_kit(tmp_path)
    press(course / "匯入作業包", app, course)
    assert app.logs[-1] == "匯入了 HK1、HK2、HK5（新 3、更新 0）"
    assert (course / "HK5" / "t2026fscSpace" / "HK5.txt").exists()
    assert str(course) not in sys.path


def test_import_button_cancelled(tmp_path, load):
    course = course_with_buttons(tmp_path)
    app = HwApp(tmp_path, course / "匯入作業包")
    press(course / "匯入作業包", app, course)
    assert app.logs == ["沒選資料夾，沒有匯入"]


def test_collect_button_finds_hk_in_the_zip_name(tmp_path, load):
    course = course_with_buttons(tmp_path)
    old_hk(course / "HK5")
    app = HwApp(tmp_path, course / "收作業")
    app.chosen_files = [make_zip(tmp_path / "科學計算_hk5_全班.zip", {"B1/HK5.txt": GOOD, "B2/HK5.txt": GOOD})]
    press(course / "收作業", app, course)
    assert (course / "HK5" / "B1" / "iplot.py").exists() and (course / "HK5" / "B2" / "iplot.py").exists()
    assert any(line.startswith("收了 2 份進 HK5（新 2、覆蓋 0）") for line in app.logs)
    assert app.asks == []


def test_collect_button_asks_when_the_name_says_nothing(tmp_path, load):
    course = course_with_buttons(tmp_path)
    app = HwApp(tmp_path, course / "收作業")
    app.chosen_files = [make_zip(tmp_path / "全班.zip", {"B1/HK5.txt": GOOD})]
    app.answers_ask = ["hk5"]
    press(course / "收作業", app, course)
    [(question, _)] = app.asks
    assert "全班.zip" in question
    assert (course / "HK5" / "iplot.py").exists()  # 還沒匯入的 HK：先放墊片，學生才看得到
    assert (course / "HK5" / "B1" / "t2026fscSpace" / "HK5.txt").exists()


def test_collect_button_cancelled_or_no_answer(tmp_path, load):
    course = course_with_buttons(tmp_path)
    app = HwApp(tmp_path, course / "收作業")
    press(course / "收作業", app, course)
    assert app.logs == ["沒選檔，沒有收"]
    app.chosen_files = [make_zip(tmp_path / "全班.zip", {"B1/HK5.txt": GOOD})]
    app.answers_ask = [None]
    press(course / "收作業", app, course)
    assert app.logs[-1] == "沒說是哪一份，這幾個沒收：全班.zip"
    assert sorted(p.name for p in course.iterdir()) == ["hk_page.py", "hk_tk.py", "匯入作業包", "收作業"]



# ── Task 11：收作業兩種格式都收（D99）──

NEW_HK = """REQUIRES = ["numpy"]
import hk_page; hk_page.ensure(REQUIRES, __file__)
import numpy as np

NAME = "HK5 新格式"
DOCS = []
NOTE = ""
CASES = {"case-1": dict(label="一")}


def compute(case):
    return {"text": str(np.arange(3))}


draw = None
stats = None

# ── 以下不用改 ──
import sys
HOMEWORK = dict(name=NAME, docs=DOCS, note=NOTE, cases=CASES, compute=compute, draw=draw, stats=stats, file=__file__)
def run(app): hk_page.show(app, HOMEWORK)
def on_files(app, paths): hk_page.collect(app, paths)
if __name__ == "__main__" and "core.runner" not in sys.modules:
    hk_page.main(HOMEWORK)
"""


def test_classify_three_kinds(tmp_path, load):
    hk = load("hk_tk")
    files = {"old.txt": GOOD, "new.py": NEW_HK, "none.py": "x = 1\n", "broken.py": "def (\n",
             "both.py": GOOD + "\nHOMEWORK = dict(name='x')\n"}
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    assert hk.classify(tmp_path / "old.txt") == ("old", "HK5")
    assert hk.classify(tmp_path / "new.py") == ("new", None)
    assert hk.classify(tmp_path / "none.py") == ("none", None)
    assert hk.classify(tmp_path / "broken.py") == ("broken", None)
    assert hk.classify(tmp_path / "both.py") == ("new", None)


def test_kit_space_also_looks_next_to_a_new_format_homework(tmp_path, load):
    hk = load("hk_tk")
    (tmp_path / "HK13" / "HK13Space").mkdir(parents=True)
    assert hk.kit_space(tmp_path / "HK13", "HK13") == tmp_path / "HK13" / "HK13Space"


def test_collect_mixed_batch(tmp_path, load):
    hk = load("hk_tk")
    course, folder = course_with_hk(tmp_path)
    zipped = make_zip(tmp_path / "HK5.zip", {"B1/HK5.txt": GOOD, "B2/HK5.py": NEW_HK, "B3/HK5.py": "x = 1\n"})
    said = hk.collect(HwApp(tmp_path, folder), [zipped], folder)
    assert (folder / "B1" / "t2026fscSpace" / "HK5.txt").exists() and (folder / "B1" / "iplot.py").read_text(
        encoding="utf-8") == hk.STUB
    b2 = folder / "B2"
    assert (b2 / "iplot.py").read_text(encoding="utf-8") == NEW_HK  # 學生的檔改名，照原 bytes
    assert (b2 / "hk_page.py").read_bytes() == (course / "hk_page.py").read_bytes()
    assert (b2 / "HK5Space" / "a.pdf").read_bytes() == b"%PDF"
    assert not (b2 / "t2026fscSpace").exists()
    assert (folder / "B3" / "t2026fscSpace" / "HK5.txt").exists()  # 都不是：照舊格式放
    assert said.startswith("收了 3 份進 HK5（舊格式 1、新格式 1；新 3、覆蓋 0）")
    assert "；1 份不是 HK5 的作業檔（B3）" in said


def test_collect_old_only_keeps_the_short_sentence(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    _, files = handed_in(tmp_path, {"B1.txt": GOOD})
    assert hk.collect(HwApp(tmp_path, folder), files, folder).startswith("收了 1 份進 HK5（新 1、覆蓋 0）")


def test_collect_rebuilds_when_format_changes(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    app = HwApp(tmp_path, folder)
    hk.collect(app, [make_zip(tmp_path / "a" / "HK5.zip", {"B1/HK5.txt": GOOD})], folder)
    said = hk.collect(app, [make_zip(tmp_path / "b" / "HK5.zip", {"B1/HK5.py": NEW_HK})], folder)
    b1 = folder / "B1"
    assert not (b1 / "t2026fscSpace").exists() and (b1 / "hk_page.py").exists()
    assert (b1 / "iplot.py").read_text(encoding="utf-8") == NEW_HK
    assert "覆蓋 1" in said
    hk.collect(app, [make_zip(tmp_path / "c" / "HK5.zip", {"B1/HK5.txt": GOOD})], folder)  # 再換回舊格式
    assert not (b1 / "hk_page.py").exists() and (b1 / "t2026fscSpace" / "HK5.txt").exists()
    assert (b1 / "iplot.py").read_text(encoding="utf-8") == hk.STUB


def test_collect_unions_requires_line(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path, venv=True)
    new = NEW_HK.replace('REQUIRES = ["numpy"]', 'REQUIRES = ["numpy", "scipy"]')
    _, files = handed_in(tmp_path, {"B1/HK5.py": new})
    app = HwApp(tmp_path, folder)
    app.answers = [False]
    hk.collect(app, files, folder, popen=FakePopen(output=lambda argv: ['["numpy"]']))
    [question] = app.confirms
    assert "scipy" in question  # 只寫在 REQUIRES、沒有 import 的也算


def test_collect_lists_check_failures(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    bad = NEW_HK.replace("import numpy as np", "import numpy as np\nimport tkinter")
    base, _ = handed_in(tmp_path, {"B1/HK5.py": bad, "B2/HK5.py": NEW_HK})
    said = hk.collect(HwApp(tmp_path, folder), [base], folder)
    assert "；1 份新格式檢查不過（B1：不能 import tkinter：畫面是殼的事）" in said
    assert (folder / "B1" / "iplot.py").read_text(encoding="utf-8") == bad  # 照放


def test_roster_marks_and_opens_new_format(tmp_path, load, tk_root):
    hk = load("hk_tk")
    out = tmp_path / "HK5_收件"
    old_hk(out / "B1")
    for name, src in (("B2", NEW_HK), ("B3", NEW_HK.replace("import numpy as np", "import numpy as np\nimport turtle"))):
        (out / name).mkdir(parents=True)
        (out / name / "iplot.py").write_text(src, encoding="utf-8")
        (out / name / "hk_page.py").write_bytes((COURSE / "hk_page.py").read_bytes())
    assert hk.roster(out) == [("B1", ""), ("B2", ""), ("B3", "檢查不過")]
    popen = FakePopen()
    win = hk.Roster(out, Path("/venv/bin/python"), tk_root, popen=popen)
    win.listbox.selection_set(1)
    win.open_selected()
    [(argv, kw)] = popen.calls
    assert argv == ["/venv/bin/python", str(out / "B2" / "iplot.py"), "--all"]
    assert kw["cwd"] == str(out / "B2") and kw["env"]["HK_FROM_IPLOT"] == "1"


def test_gather_keeps_both_loose_files_with_the_same_name(tmp_path, load):
    hk = load("hk_tk")
    for who in ("a", "b"):
        (tmp_path / who).mkdir()
        (tmp_path / who / "HK5.py").write_text(who, encoding="utf-8")
    root = hk.gather([tmp_path / "a" / "HK5.py", tmp_path / "b" / "HK5.py"], tmp_path / "work").root
    assert sorted(p.name for p in root.iterdir()) == ["HK5-2.py", "HK5.py"]  # 副檔名留著，才收得到



def tree_of(folder):
    return sorted(str(p.relative_to(folder)) for p in Path(folder).rglob("*"))


def test_collect_never_deletes_teacher_entries_named_in_another_case(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)  # 舊格式：HK5/iplot.py、t2026fscSpace/HK5.txt、HK5Space/a.pdf
    teacher = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    zipped = make_zip(tmp_path / "HK5.zip", {"T2026FSCSPACE/HK5.py": NEW_HK, "IPLOT.PY/HK5.txt": GOOD,
                                             "hk5space/HK5.py": NEW_HK})
    said = hk.collect(HwApp(tmp_path, folder), [zipped], folder)
    for path, data in teacher.items():  # macOS 不分大小寫：這幾個名字開到的是老師的東西，絕不能被砍、被蓋
        assert path.read_bytes() == data, path
    assert said.startswith("收了 3 份進 HK5")
    assert {"T2026FSCSPACE-2", "IPLOT.PY-2", "hk5space-2"} <= {p.name for p in folder.iterdir()}


def test_collect_into_a_new_format_homework_keeps_its_space(tmp_path, load):
    hk = load("hk_tk")
    course = course_copy(tmp_path)
    hk13 = course / "HK13"
    (hk13 / "HK13Space").mkdir(parents=True)
    (hk13 / "HK13Space" / "data.csv").write_text("1,2\n", encoding="utf-8")
    (hk13 / "iplot.py").write_text(NEW_HK, encoding="utf-8")
    (hk13 / "hk_page.py").write_bytes((course / "hk_page.py").read_bytes())
    zipped = make_zip(tmp_path / "HK13.zip", {"hk13space/HK13.py": NEW_HK, "B1/HK13.txt": GOOD})
    hk.collect(HwApp(tmp_path, hk13), [zipped], hk13)
    assert (hk13 / "HK13Space" / "data.csv").read_text(encoding="utf-8") == "1,2\n"
    assert (hk13 / "iplot.py").read_text(encoding="utf-8") == NEW_HK and not (hk13 / "HK13Space" / "iplot.py").exists()
    assert (hk13 / "hk13space-2" / "HK13Space" / "data.csv").exists()  # 學生拿到的是老師 Space 的複本


def test_student_names_that_differ_only_in_case_get_their_own_folders(tmp_path, load):
    hk = load("hk_tk")
    _, folder = course_with_hk(tmp_path)
    said = hk.collect(HwApp(tmp_path, folder), [make_zip(tmp_path / "HK5.zip", {"B1/HK5.txt": GOOD,
                                                                                "b1/HK5.txt": GOOD + "#2\n"})], folder)
    names = sorted(p.name for p in folder.iterdir() if (p / "t2026fscSpace" / "HK5.txt").exists())
    assert len(names) == 2 and said.startswith("收了 2 份進 HK5（新 2、覆蓋 0）")


def test_collect_skips_the_students_copy_of_the_shell(tmp_path, load):
    hk = load("hk_tk")
    course, folder = course_with_hk(tmp_path)
    zipped = make_zip(tmp_path / "HK5.zip", {"B1/HK5.py": NEW_HK, "B1/hk_page.py": "# 學生那份殼\n"})
    said = hk.collect(HwApp(tmp_path, folder), [zipped], folder)
    assert said.startswith("收了 1 份進 HK5") and not (folder / "B1-2").exists()
    assert (folder / "B1" / "hk_page.py").read_bytes() == (course / "hk_page.py").read_bytes()  # 用課程的正本


def test_third_party_never_offers_the_shell(tmp_path, load):
    hk = load("hk_tk")
    assert hk.third_party({"hk_page", "hk_tk", "numpy"}, tmp_path) == {"numpy"}


def test_install_rejects_a_name_with_a_trailing_newline(load, monkeypatch):
    hk = load("hk_tk")
    monkeypatch.delenv("HK_NO_INSTALL")
    popen = FakePopen()
    _, failed = hk.install(Path("/py"), ["numpy\n"], [].append, popen=popen)
    assert failed == [("numpy\n", "名字不合法")] and popen.calls == []


def test_roster_compares_package_names_normalized(tmp_path, load):
    hk = load("hk_tk")
    out = tmp_path / "HK5_收件"
    (out / "B1").mkdir(parents=True)
    (out / "B1" / "iplot.py").write_text(NEW_HK.replace('["numpy"]', '["numpy", "Pillow"]'), encoding="utf-8")
    (out / "B1" / "hk_page.py").write_bytes((COURSE / "hk_page.py").read_bytes())
    assert hk.roster(out, have={"numpy", "pillow"}) == [("B1", "")]


def test_roster_window_uses_absolute_paths(tmp_path, load, tk_root, monkeypatch):
    hk = load("hk_tk")
    out = tmp_path / "HK5_收件"
    (out / "B1").mkdir(parents=True)
    (out / "B1" / "iplot.py").write_text(NEW_HK, encoding="utf-8")
    (out / "B1" / "hk_page.py").write_bytes((COURSE / "hk_page.py").read_bytes())
    monkeypatch.chdir(tmp_path)
    popen = FakePopen()
    win = hk.Roster(Path("HK5_收件"), Path("venv/bin/python"), tk_root, popen=popen)  # --out、--venv 給相對路徑
    win.listbox.selection_set(0)
    win.open_selected()
    [(argv, kw)] = popen.calls
    assert Path(argv[0]).is_absolute() and Path(argv[1]) == out / "B1" / "iplot.py" and Path(kw["cwd"]).is_absolute()


# ── 最終審查延後的四件小事（回報第 3 節）──


def lone_hk_tk(tmp_path):
    """批次模式只複製了 hk_tk.py 的那個資料夾：從那裡載入一份，它的 SHELL 指到旁邊不存在的 hk_page.py。"""
    folder = tmp_path / "只有hk_tk"
    folder.mkdir()
    (folder / "hk_tk.py").write_bytes((COURSE / "hk_tk.py").read_bytes())
    spec = importlib.util.spec_from_file_location("_hk_tk_alone", folder / "hk_tk.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_batch_without_the_shell_places_new_format_files_without_it(tmp_path, load):
    hk = lone_hk_tk(tmp_path)
    assert not hk.SHELL.exists()
    zipped = make_zip(tmp_path / "下載" / "HK5.zip", {"B1/HK5.py": NEW_HK, "B2/HK5.py": NEW_HK, "B3/HK5.txt": GOOD})
    said = []
    out = hk.batch(zipped, kit=teacher_kit(tmp_path), say=said.append)
    for name in ("B1", "B2"):
        assert (out / name / "iplot.py").read_text(encoding="utf-8") == NEW_HK  # 照放
        assert (out / name / "HK5Space" / "a.pdf").read_bytes() == b"%PDF"
        assert not (out / name / "hk_page.py").exists()
    assert (out / "B3" / "t2026fscSpace" / "HK5.txt").exists()  # 舊格式不受影響
    assert said[-1].startswith("收了 3 份進 HK5（舊格式 1、新格式 2；新 3、覆蓋 0）")
    assert "；hk_page.py 不在 hk_tk.py 旁邊，新格式的 2 份沒放殼（B1、B2）" in said[-1]
    assert [name for name, _ in hk.roster(out)] == ["B3"]  # 沒有殼的不是學生資料夾，名單上沒有
    # docs/08 8.8 寫的補法：hk_page.py 放到旁邊、刪掉那幾個學生的資料夾、再跑一次
    hk.SHELL.write_bytes((COURSE / "hk_page.py").read_bytes())
    for name in ("B1", "B2"):
        shutil.rmtree(out / name)
    hk.batch(zipped, kit=teacher_kit(tmp_path), say=said.append)
    assert (out / "B1" / "hk_page.py").read_bytes() == hk.SHELL.read_bytes()
    assert said[-1].startswith("收了 3 份進 HK5（舊格式 1、新格式 2；新 2、覆蓋 1）") and "沒放殼" not in said[-1]
