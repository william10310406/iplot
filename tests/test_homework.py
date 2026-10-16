"""工作坊模組「科學計算」（M6）：舊格式執行器、墊片、匯入作業包、套件、收作業、批次模式。

不連網、不裝東西：每個測試都在 HK_NO_INSTALL=1 底下跑，Popen 一律是假的（FakePopen）。
Tk 的部分用藏起來的真 Tk（tests/test_tk_smoke.py 的做法：destroy 之前先 update）；沒有顯示器就跳過那幾個。
"""

import ast
import importlib
import io
import sys
import types
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


@pytest.fixture
def load(monkeypatch):
    """load("hk_tk")：把 modules/科學計算/hk_tk.py 當一般模組 import（不寫 .pyc），結束時從 sys.modules 拿掉。"""
    monkeypatch.syspath_prepend(str(COURSE))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    for n in NAMES:
        monkeypatch.delitem(sys.modules, n, raising=False)
    yield importlib.import_module
    for n in NAMES:
        sys.modules.pop(n, None)


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


@pytest.mark.parametrize("name", ["hk_tk"])
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
    assert f"缺 sklearn：{sys.executable} -m pip install sklearn" in message


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

