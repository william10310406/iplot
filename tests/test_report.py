"""隨附模組「回報與討論」（modules/回報與討論）：遮蔽、內文、網址、截斷、預覽頁與面板的流程（M8、D110–D116）。
不開瀏覽器（autouse 的替身）、不連網、不寫進 repo（跑模組的流程先複製到 tmp）；遮蔽的表用假的 Ctx，只有端對端的兩個用這台機器。"""

import dataclasses
import errno
import getpass
import importlib
import inspect
import itertools
import json
import os
import platform
import re
import shutil
import sys
import threading
import types
import webbrowser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from conftest import FakeApp, FakeCore, FakeView, make_module

from core.app import App
from core.runner import run_module
from core.scan import module_info
from core.types import DEFAULT_CONFIG, ErrorInfo

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules" / "回報與討論"
NAMES = ("forum", "redact", "report", "iplot")


@pytest.fixture
def load(monkeypatch):
    """load("forum")：把 modules/回報與討論/forum.py 當一般模組 import（不寫 .pyc）——跟 runner 一樣走 sys.path；
    結束時從 sys.modules 拿掉。"""
    monkeypatch.syspath_prepend(str(MODULE))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    for n in NAMES:
        monkeypatch.delitem(sys.modules, n, raising=False)
    yield importlib.import_module
    for n in NAMES:
        sys.modules.pop(n, None)


@pytest.fixture(autouse=True)
def opened(monkeypatch):
    """每一個測試都不開真的瀏覽器：webbrowser.open 換成記下網址、回 True 的替身；回那一串網址。
    有 tkinter 的話，tkinter 自己的那個 Tk 先當作沒有：tkinter 的流程不碰真的剪貼簿，不靠測試的順序。"""
    calls = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: calls.append(url) or True)
    try:
        import tkinter
    except ImportError:  # 沒有 tkinter 的 Python：tkinter 的流程本來就跑不到
        return calls
    monkeypatch.setattr(tkinter, "_default_root", None, raising=False)
    return calls


@pytest.fixture
def web(monkeypatch):
    """網頁面板的樣子：只有 ui.web。"""
    monkeypatch.delitem(sys.modules, "ui.tk", raising=False)
    monkeypatch.setitem(sys.modules, "ui.web", types.ModuleType("ui.web"))


@pytest.fixture
def tk(monkeypatch):
    """後備的 tkinter 面板的樣子：網頁面板開不起來之後 ui.web 還在，兩個都在。"""
    monkeypatch.setitem(sys.modules, "ui.tk", types.ModuleType("ui.tk"))
    monkeypatch.setitem(sys.modules, "ui.web", types.ModuleType("ui.web"))


def test_helper_names_are_not_stdlib():
    assert not {"forum", "redact", "report"} & set(sys.stdlib_module_names)


def test_forum_points_at_this_repo(load):
    forum = load("forum")
    assert forum.REPO == "william10310406/iplot"
    assert forum.FORUM == "https://github.com/william10310406/iplot/discussions"


def test_forum_has_four_categories(load):
    # 整份測試只有這裡寫死 slug（Task 0 Step 1 照實測改的就是這一行）；其他測試一律從 forum.CATEGORIES 查
    forum = load("forum")
    assert forum.CATEGORIES == {"BUG": "問題回報", "IDEA": "功能建議", "QA": "問答", "NEWS": "公告"}
    assert not any("%" in slug for slug in forum.CATEGORIES.values())  # 存解開 %XX 之後的樣子


def test_report_folder_is_ignored_by_git():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "modules/回報與討論/回報/" in lines


# ── 遮蔽（redact.py）：表格式的例子一律用假的 Ctx（家目錄 /Users/laoban、C:\Users\laoban 只寫在這裡）──

MAC = dict(home="/Users/laoban", users=("laoban",), iplot="/Users/laoban/iPLoT",
           pythons=("/Library/Frameworks/Python.framework/Versions/3.14",
                    "/opt/homebrew/opt/python@3.12/Frameworks/Python.framework/Versions/3.12",
                    "/opt/homebrew/Cellar/python@3.12/3.12.13_2/Frameworks/Python.framework/Versions/3.12",
                    "/Users/laoban/iPLoT/.venv"),
           module="/Users/laoban/iPLoT/modules/科學計算", module_name="科學計算")
WIN = dict(home="C:\\Users\\laoban", users=("laoban",), iplot="C:\\Users\\laoban\\iPLoT",
           pythons=("C:\\Users\\laoban\\AppData\\Local\\Programs\\Python\\Python312",), module=None, module_name=None)
SPACE = dict(iplot="/Users/laoban/我的 iPLoT", module="/Users/laoban/我的 iPLoT/modules/科學計算")  # 第 14、39 列
KEYS = ("路徑", "使用者名稱", "疑似學號", "電子郵件", "原始碼", "下一層模組")
RUNNER = '  File "/Users/laoban/iPLoT/core/runner.py", line 72, in run_module\n    exec(code, ns)\n    ~~~~^^^^^^^^^^\n'
DECODE = "    obj, end = self.raw_decode(s, idx=_w(s, 0).end())\n"

# (名字, ctx 的覆寫, 輸入, 輸出)：ctx 從 MAC 起、覆寫的鍵蓋上去
CASES = [
    ("iplot_frame_keeps_source", {}, RUNNER,
     '  File "<IPLOT>/core/runner.py", line 72, in run_module\n    exec(code, ns)\n    ~~~~^^^^^^^^^^\n'),
    ("python_frame_keeps_source", {},
     '  File "/Library/Frameworks/Python.framework/Versions/3.14/lib/python3.14/json/decoder.py", line 345, in decode\n'
     + DECODE + "               ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^\n",
     '  File "<PYTHON>/lib/python3.14/json/decoder.py", line 345, in decode\n'
     + DECODE + "               ~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^\n"),
    ("homebrew_cellar_is_python", {},
     '  File "/opt/homebrew/Cellar/python@3.12/3.12.13_2/Frameworks/Python.framework/Versions/3.12/lib/python3.12/json/__init__.py", line 346, in loads\n'
     "    return _default_decoder.decode(s)\n",
     '  File "<PYTHON>/lib/python3.12/json/__init__.py", line 346, in loads\n    return _default_decoder.decode(s)\n'),
    ("venv_is_python", {},
     '  File "/Users/laoban/iPLoT/.venv/lib/python3.14/site-packages/x.py", line 2, in f\n    y = 2\n',
     '  File "<PYTHON>/lib/python3.14/site-packages/x.py", line 2, in f\n    y = 2\n'),
    ("module_top_file_drops_source_and_marker", {},
     '  File "/Users/laoban/iPLoT/modules/科學計算/hk_tk.py", line 120, in grade\n    score = row["score"]\n            ~~~^^^^^^^^^\n',
     '  File "<模組:科學計算>/hk_tk.py", line 120, in grade\n    （原始碼已略過）\n'),
    ("module_deep_file", {},
     '  File "/Users/laoban/iPLoT/modules/科學計算/HK2/王小明_B11201234/作業.py", line 5, in grade\n    score = row["score"]\n',
     '  File "<模組:科學計算>/.../<檔名已遮蔽>.py", line 5, in grade\n    （原始碼已略過）\n'),
    ("home_other_folder", {},
     '  File "/Users/laoban/課程/HK2/王小明_B11201234/作業.py", line 3, in f\n    print("王小明")\n',
     '  File "<HOME>/.../<檔名已遮蔽>.py", line 3, in f\n    （原始碼已略過）\n'),
    ("external_volume", {},
     '  File "/Volumes/硬碟/學生/王小明.py", line 3, in f\n    print("王小明")\n',
     '  File "<PATH>/.../<檔名已遮蔽>.py", line 3, in f\n    （原始碼已略過）\n'),
    ("home_prefix_is_not_eaten", {}, "'/Users/laobanxyz/a.py'", "'<PATH>/.../<檔名已遮蔽>.py'"),
    ("windows_home", WIN,
     '  File "C:\\Users\\laoban\\Desktop\\王小明.py", line 3, in <module>\n    x\n',
     '  File "<HOME>/.../<檔名已遮蔽>.py", line 3, in <module>\n    （原始碼已略過）\n'),
    ("windows_case_insensitive", WIN, "'c:\\users\\LAOBAN\\x\\y.txt'", "'<HOME>/.../<檔名已遮蔽>.txt'"),
    ("windows_python", WIN,
     '  File "C:\\Users\\laoban\\AppData\\Local\\Programs\\Python\\Python312\\Lib\\json\\decoder.py", line 345, in decode\n'
     + DECODE,
     '  File "<PYTHON>/Lib/json/decoder.py", line 345, in decode\n' + DECODE),
    ("unc_path", {}, "\\\\server\\share\\王小明\\a.csv", "<PATH>/.../<檔名已遮蔽>.csv"),
    ("path_with_space", SPACE,
     '  File "/Users/laoban/我的 iPLoT/modules/科學計算/iplot.py", line 3, in run\n    x = 1\n',
     '  File "<模組:科學計算>/iplot.py", line 3, in run\n    （原始碼已略過）\n'),
    ("config_frame_keeps_name_drops_source", {},
     '  File "/Users/laoban/iPLoT/config.py", line 1\n    ROOTS = [\n    ^\n',
     '  File "<IPLOT>/config.py", line 1\n    （原始碼已略過）\n'),
    ("syntax_error_location", {},
     '  File "/Users/laoban/iPLoT/modules/科學計算/iplot.py", line 3\n    if name = "x":\n       ^^^^^^^^^^\nSyntaxError: invalid syntax\n',
     '  File "<模組:科學計算>/iplot.py", line 3\n    （原始碼已略過）\nSyntaxError: invalid syntax\n'),
    ("syntax_message_filename", {},
     "invalid syntax (壞掉.py, line 1)\ninvalid syntax (iplot.py, line 3)\n",
     "invalid syntax (<檔名已遮蔽>.py, line 1)\ninvalid syntax (iplot.py, line 3)\n"),
    ("relative_frame", {},
     '  File "HK2/王小明_B11201234/頂層錯.py", line 3, in <module>\n    print(x)\n',
     '  File ".../<檔名已遮蔽>.py", line 3, in <module>\n    （原始碼已略過）\n'),
    ("quoted_relative_in_message", {},
     "No such file or directory: 'HK2/王小明/作業.py'", "No such file or directory: '.../<檔名已遮蔽>.py'"),
    ("quoted_absolute_in_message", {},
     "'/Users/laoban/課程/成績.csv' -> 'HK2/王小明/作業.py'", "'<HOME>/.../<檔名已遮蔽>.csv' -> '.../<檔名已遮蔽>.py'"),
    ("unquoted_path_in_text", {}, "see /Users/laoban/課程/HK2/x.txt now", "see <HOME>/.../<檔名已遮蔽>.txt now"),
    ("urls_are_not_paths", {},
     "https://github.com/william10310406/iplot/discussions", "https://github.com/william10310406/iplot/discussions"),
    ("frozen_and_string_frames", {},
     '  File "<frozen runpy>", line 293, in run_path\n  File "<string>", line 2, in <module>\n',
     '  File "<frozen runpy>", line 293, in run_path\n  File "<string>", line 2, in <module>\n'),
    ("exception_group", {},
     '  |   File "/Users/laoban/iPLoT/modules/科學計算/iplot.py", line 5, in run\n  |     raise ExceptionGroup("x", [])\n'
     "  | ExceptionGroup: x (0 sub-exceptions)\n",
     '  |   File "<模組:科學計算>/iplot.py", line 5, in run\n  |     （原始碼已略過）\n  | ExceptionGroup: x (0 sub-exceptions)\n'),
    ("user_in_text", {}, "owner laoban and LaoBan said hi", "owner <USER> and <USER> said hi"),
    ("user_whole_word_only", {}, "laobanxyz", "laobanxyz"),
    ("short_user_is_left", {"users": ("ab",)}, "ab cd", "ab cd"),
    ("student_id_after_cjk", {}, "王小明B11201234", "王小明<疑似學號>"),
    ("student_id_digits", {}, "學號 411234567 的作業", "學號 <疑似學號> 的作業"),
    ("not_student_ids", {},
     "line 120, 0x7f3a9c2b10, [Errno 2], 3.14.7, pytest-1234, 2026-10-23, 20:47:56",
     "line 120, 0x7f3a9c2b10, [Errno 2], 3.14.7, pytest-1234, 2026-10-23, 20:47:56"),
    ("email", {}, "寄給 laoban.b@school.edu.tw", "寄給 <EMAIL>"),
    ("secret_module_name", {"secrets": ("王小明_B11201234",)},
     "模組『王小明_B11201234』第 3 行出錯", "模組『<下一層模組>』第 3 行出錯"),
    ("placeholders_are_left_alone", {},
     "'<HOME>/.../<檔名已遮蔽>.py' \"<模組:科學計算>/hk_tk.py\" <IPLOT>/core/runner.py",
     "'<HOME>/.../<檔名已遮蔽>.py' \"<模組:科學計算>/hk_tk.py\" <IPLOT>/core/runner.py"),
    ("user_named_like_a_placeholder", {"users": ("User",)}, "owner User and <USER>", "owner <USER> and <USER>"),
    ("user_next_to_id", {"users": ("王小明",)}, "王小明B11201234", "<USER><疑似學號>"),
    ("import_error_path_with_space", {},
     "ImportError: cannot import name 'g' from '工具' (/Users/laoban/My Drive/課程/王小明/工具.py)",
     "ImportError: cannot import name 'g' from '工具' (<HOME>/.../<檔名已遮蔽>.py)"),
    ("apostrophe_before_quoted_path", {},
     "Can't get attribute 'C' on <module '工具' from '/Users/laoban/My Drive/王小明/工具.py'>",
     "Can't get attribute 'C' on <module '工具' from '<HOME>/.../<檔名已遮蔽>.py'>"),
    ("onedrive_in_parens", WIN,
     "(C:\\Users\\laoban\\OneDrive - 國立某大學\\HK2\\王小明\\作業.py)", "(<HOME>/.../<檔名已遮蔽>.py)"),
    ("unquoted_space_in_iplot_prefix", SPACE,
     "see /Users/laoban/我的 iPLoT/modules/科學計算/HK2/王小明/作業.py now", "see <模組:科學計算>/.../<檔名已遮蔽>.py now"),
    ("module_in_external_root_unquoted", {"module": "/Volumes/硬碟/課/科學計算", "secrets": ("王小明_B11201234", "HK2")},
     "see /Volumes/硬碟/課/科學計算/HK2/王小明_B11201234/王小明.py now", "see <模組:科學計算>/.../<檔名已遮蔽>.py now"),
    ("windows_repr_doubles_backslashes", WIN,  # 字面上是兩個反斜線：Windows 上 OSError 的訊息是 repr
     "No such file or directory: 'C:\\\\Users\\\\laoban\\\\Desktop\\\\成績.csv'",
     "No such file or directory: '<HOME>/.../<檔名已遮蔽>.csv'"),
    ("syntax_filename_with_parens", {}, "invalid syntax (王小明 (1).py, line 1)", "invalid syntax (<檔名已遮蔽>.py, line 1)"),
    ("never_closed_keeps_its_first_half", {},
     "'(' was never closed (王小明 (1).py, line 3)", "'(' was never closed (<檔名已遮蔽>.py, line 3)"),
    ("never_closed_iplot_kept", {}, "'(' was never closed (iplot.py, line 1)", "'(' was never closed (iplot.py, line 1)"),
    ("onedrive_unquoted", {},
     "FileNotFoundError: /Users/laoban/OneDrive - 國立臺灣大學/課程/B11234567_王小明/data.txt not found.",
     "FileNotFoundError: <HOME>/.../<檔名已遮蔽>.txt not found."),
    ("onedrive_unquoted_windows", WIN,
     "FileNotFoundError: C:\\Users\\laoban\\OneDrive - 國立臺灣大學\\課程\\B11234567_王小明\\data.txt not found.",
     "FileNotFoundError: <HOME>/.../<檔名已遮蔽>.txt not found."),
    ("cjk_right_before_a_path", {},
     "RuntimeError: 找不到/Volumes/USB/學生/王小明.csv", "RuntimeError: 找不到<PATH>/.../<檔名已遮蔽>.csv"),
    ("windows_forward_slashes", WIN,
     "RuntimeError: 讀不到 D:/課程/李大華/作業.py", "RuntimeError: 讀不到 <PATH>/.../<檔名已遮蔽>.py"),
    ("string_frame_drops_source", {},
     '  File "<string>", line 1\n    王小明 的分數 +\n        ^^^\nSyntaxError: invalid syntax\n',
     '  File "<string>", line 1\n    （原始碼已略過）\nSyntaxError: invalid syntax\n'),
    ("quote_inside_a_frame_path", {},
     '  File "/Users/laoban/課程/期中 "重交"/作業.py", line 3, in g\n    names = ["王小明"]\n',
     '  File "<HOME>/.../<檔名已遮蔽>.py", line 3, in g\n    （原始碼已略過）\n'),
    ("user_named_core", {"users": ("core",)}, RUNNER,
     '  File "<IPLOT>/<USER>/runner.py", line 72, in run_module\n    exec(code, ns)\n    ~~~~^^^^^^^^^^\n'),
    ("user_case_variants", {"users": ("User", "user")}, "owner User and user", "owner <USER> and <USER>"),
    ("apostrophe_before_quoted_relative", {},  # Can't 的撇號不能當開頭的引號：不然跟路徑開頭的那個配成一對
     "Can't read 'HK2/王小明/成績.csv'", "Can't read '.../<檔名已遮蔽>.csv'"),
    ("secret_named_core", {"secrets": ("core",)}, RUNNER,  # 下一層模組剛好叫 core：遮第二次也不能把原始碼拿掉
     '  File "<IPLOT>/<下一層模組>/runner.py", line 72, in run_module\n    exec(code, ns)\n    ~~~~^^^^^^^^^^\n'),
    ("bytes_repr_relative", {},  # bytes 的 repr：b 緊貼開頭的引號，不是撇號，裡面的相對路徑照樣遮
     "No such file or directory: b'HK2/王小明/a.txt'", "No such file or directory: b'.../<檔名已遮蔽>.txt'"),
    ("one_letter_word_apostrophe", {},  # 一個字母的字（B）接撇號會當開頭的引號：裡面沒有 / 或 \ 就不算一對，不吃掉路徑的開引號
     "Plan B's 'HK2/王小明/a.txt'", "Plan B's '.../<檔名已遮蔽>.txt'"),
    ("closing_quote_does_not_open", {},  # 'x ' 的閉引號跟路徑的開引號之間是 " / "：頭尾是空白，不算一對
     "'x ' / 'HK2/a.txt'", "'x ' / '.../<檔名已遮蔽>.txt'"),
    ("quoted_name_then_date_then_path", {},  # '王小明' 的閉引號到路徑的開引號之間有日期的 /，但頭尾是空白
     "ValueError: '王小明' 2026/10/25 交的 'HK2/王小明/成績.csv'", "ValueError: '王小明' 2026/10/25 交的 '.../<檔名已遮蔽>.csv'"),
    ("dict_repr_keeps_context", {},  # "v" 的閉引號到 "z" 的開引號那一段結尾是空白：不算一對，不把中間整段遮掉
     '{"k": "v", \'p\': \'HK2/王小明/x.txt\', "z": 1}', '{"k": "v", \'p\': \'.../<檔名已遮蔽>.txt\', "z": 1}'),
    ("one_letter_apostrophe_then_slash", {},  # B' 也可能是 b'…' 的開引號：那樣讀 's 1/2 ' 是一對（含 /），跟路徑那一對
     "Plan B's 1/2 'HK2/x.txt'", "Plan B'.../<檔名已遮蔽>.txt'"),  # 共用一個引號，合起來整段遮（多遮，接受）
    ("trailing_space_inside_quotes", {},  # 檔名後面多打一個空白是 FileNotFoundError 的老原因：空白留在標籤外面
     "FileNotFoundError: [Errno 2] No such file or directory: 'HK2/王小明_B11201234/成績.csv '",
     "FileNotFoundError: [Errno 2] No such file or directory: '.../<檔名已遮蔽>.csv '"),
    ("leading_space_inside_quotes", {}, "open(' HK2/王小明/a.txt')", "open(' .../<檔名已遮蔽>.txt')"),
    ("full_width_space_inside_quotes", {},  # 全形空白也算頭尾的空白（str.strip 的空白）
     "'　HK2/王小明/a.txt'", "'　.../<檔名已遮蔽>.txt'"),
    ("closing_quote_then_slash", {},  # 'x ' 的閉引號後面緊接著 /：當成絕對路徑讀是一對，跟路徑那一對共用一個引號，合起來整段遮
     "'x '/ 'HK2/王小明/a.txt'", "'x '<PATH>/.../<檔名已遮蔽>.txt'"),
    ("slash_between_pairs", {}, '"a"/"HK2/王小明/a.txt"', '"a"<PATH>/.../<檔名已遮蔽>.txt"'),
    ("lone_quote_before_spaced_path", {},  # 從左邊配是 ''（沒有分隔符號），從右邊配才是路徑那一對
     "'' HK2/王小明/a.txt'", "'' .../<檔名已遮蔽>.txt'"),
    ("single_inside_double_starting_with_lt", {},  # 雙引號那一對以 < 開頭，原樣；裡面的單引號那一對分開找，照樣遮
     '"<\'HK2/王小明/a.txt\'"', '"<\'.../<檔名已遮蔽>.txt\'"'),
    ("unc_glued_to_quote", {},  # 字面上是兩個反斜線接 a：第 5 步把它遮成標籤之後，緊貼標籤的引號才當得了開頭（再找一次）
     "\\\\a'HK2/王小明/a.txt'", "<PATH>/.../<檔名已遮蔽>'.../<檔名已遮蔽>.txt'"),
    ("doubled_double_quotes", {},  # 從左、從右兩兩配都是兩個 ""：只有 (c)（含分隔符號、頭尾不是空白）認得中間那一對
     '""HK2/王小明/a.txt""', '"".../<檔名已遮蔽>.txt""'),
]

# 引號裡的相對路徑前面有各種會騙引號配對的字：撇號、一個字母的字接撇號、沒有分隔符號的一對、中間有 / 的日期與分數、
# 字串前綴、dict／list 的 repr、閉引號後面緊接著 /、落單的引號、緊貼引號的 UNC 開頭（字面上是兩個反斜線接 a）；
# 路徑本身也可以頭尾有空白。前綴裡不放「王小明」（只看路徑裡的那一個有沒有漏；'王小明' 在前面的那一句是第 58 列）
NOISY_PREFIXES = ("Can't ", "Plan B's ", "it's 1/2 ", "'x ' / ", '"a" / ', "'李大華' 2026/10/25 ", "[b'a', ",
                  "{'k': 'v', ", "rock'n'roll ", "'分數' / ", "b's ", "isn't 3/4 ", 'x = "" / ', "(", "",
                  "'x '/ ", '"a"/', "'", "\\\\a")
NOISY_PATHS = ("'HK2/王小明_B11201234/a.txt'", "'HK2\\\\王小明_B11201234\\\\a.txt'",  # 第二個是 Windows 的 repr：兩個反斜線
               "b'HK2/王小明_B11201234/a.txt'", '"HK2/王小明_B11201234/a.txt"',
               "' HK2/王小明_B11201234/a.txt'", "'HK2/王小明_B11201234/a.txt '")
NOISY_SUFFIXES = ("", " not found", "。")
# 引號湯：前綴是這些記號任取 0–2 個接起來，接一個 NOISY_PATHS，後面再接 0–1 個記號
SOUP = ("'", '"', "/", "\\", " ", "a", "1", "王", "<", "C:")

# 手寫的 3.14 樣子的 traceback：三段串起來（FileNotFoundError → SyntaxError → KeyError）
SAMPLE = (
    "Traceback (most recent call last):\n"
    '  File "/Users/laoban/iPLoT/core/runner.py", line 72, in run_module\n'
    "    exec(code, ns)\n"
    "    ~~~~^^^^^^^^^^\n"
    '  File "/Users/laoban/課程/王小明/工具.py", line 3, in load\n'
    "    return open('/Users/laoban/課程/王小明/成績.csv', encoding='utf-8')\n"
    "FileNotFoundError: [Errno 2] No such file or directory: '/Users/laoban/課程/王小明/成績.csv'\n"
    "\n"
    "During handling of the above exception, another exception occurred:\n"
    "\n"
    "Traceback (most recent call last):\n"
    '  File "/Users/laoban/iPLoT/modules/科學計算/iplot.py", line 9, in <module>\n'
    '    runpy.run_path("HK2/王小明_B11201234/頂層錯.py")\n'
    '  File "<frozen runpy>", line 287, in run_path\n'
    '  File "HK2/王小明_B11201234/頂層錯.py", line 1\n'
    '    print("王小明 B11201234 laoban"\n'
    "         ^\n"
    "SyntaxError: '(' was never closed (頂層錯.py, line 1)\n"
    "\n"
    "The above exception was the direct cause of the following exception:\n"
    "\n"
    "Traceback (most recent call last):\n"
    '  File "/Users/laoban/iPLoT/core/runner.py", line 75, in run_module\n'
    "    value = fn(app, *args)\n"
    "            ~~^^^^^^^^^^^^\n"
    '  File "/Users/laoban/iPLoT/modules/科學計算/HK2/王小明_B11201234/作業.py", line 5, in grade\n'
    '    score = row["B11201234"]\n'
    "            ~~~^^^^^^^^^^^^^\n"
    "KeyError: 'B11201234'\n"
    "學生名單在 /Users/laoban/課程/名單.csv ，由 laoban 整理\n"  # 3.11 起的 add_note
)


@pytest.mark.parametrize("name, over, text, want", CASES, ids=[c[0] for c in CASES])
def test_redact_table(load, name, over, text, want):
    redact = load("redact")
    assert redact.redact(text, redact.Ctx(**{**MAC, **over}))[0] == want


@pytest.mark.parametrize("name, over, text, want", CASES, ids=[c[0] for c in CASES])
def test_redact_is_idempotent(load, name, over, text, want):
    redact = load("redact")
    ctx = redact.Ctx(**{**MAC, **over})
    once = redact.redact(text, ctx)[0]
    assert redact.redact(once, ctx)[0] == once


def test_quoted_relative_path_is_masked_in_noisy_lines(load):
    redact = load("redact")
    ctx = redact.Ctx(**MAC)
    for prefix, path, suffix in itertools.product(NOISY_PREFIXES, NOISY_PATHS, NOISY_SUFFIXES):
        text = prefix + path + suffix
        once = redact.redact(text, ctx)[0]
        assert "王小明" not in once and "B11201234" not in once, (text, once)
        assert redact.redact(once, ctx)[0] == once, (text, once)


def test_quote_soup_is_idempotent_and_only_ambiguous_quotes_leak(load):
    redact = load("redact")
    ctx = redact.Ctx(**MAC)
    prefixes = ["", *("".join(p) for n in (1, 2) for p in itertools.product(SOUP, repeat=n))]
    for prefix, path, suffix in itertools.product(prefixes, NOISY_PATHS, ("", *SOUP)):
        text = prefix + path + suffix
        once = redact.redact(text, ctx)[0]
        assert redact.redact(once, ctx)[0] == once, (text, once)
        if "王小明" in once:
            quote = path[-1]
            # 漏得掉的只有兩類，都是照引號本身分不出來的：
            # (1) 前綴的最後一個字是 ASCII 英數字：開引號緊貼英數字是撇號的規則（crab'…'），照設計不當開頭
            # (2) 後綴就是路徑的那種引號、前綴裡也有一個：路徑自己的兩個引號外面都有落單的同一種引號，
            #     哪兩個配成一對都說得通
            glued = prefix[-1:].isascii() and prefix[-1:].isalnum()
            assert glued or (suffix == quote and quote in prefix), (text, once)


def test_redact_counts(load):
    # secret 在路徑以外也出現一次：第 7 步排在路徑規則後面，只在路徑裡的名字已經跟著路徑不見了
    redact = load("redact")
    text = ('  File "/Users/laoban/iPLoT/modules/科學計算/HK2/王小明_B11201234/作業.py", line 5, in grade\n    score = row["score"]\n'
            + "FileNotFoundError: [Errno 2] No such file or directory: '/Users/laoban/課程/成績.csv'\n"
            + "模組『王小明_B11201234』 owner laoban, id B11201234, mail a.b@school.edu.tw\n")
    counts = redact.redact(text, redact.Ctx(**{**MAC, "secrets": ("王小明_B11201234",)}))[1]
    assert counts == {"路徑": 2, "使用者名稱": 1, "疑似學號": 1, "電子郵件": 1, "原始碼": 1, "下一層模組": 1}


def test_summary_lists_what_was_masked(load):
    redact = load("redact")
    ctx = redact.Ctx(**MAC)
    zero = dict.fromkeys(reversed(KEYS), 0)  # 字典的順序反過來：句子照鍵的順序，不照字典的
    assert redact.summary({**zero, "路徑": 3, "使用者名稱": 1}, ctx) == "已自動遮蔽：3 個路徑、1 個使用者名稱。"
    assert redact.summary({**zero, "原始碼": 2}, ctx) == "已自動遮蔽：2 段原始碼。"
    assert redact.summary(zero, ctx) == "沒有找到要自動遮的東西。"


def test_summary_warns_about_a_short_user(load):
    redact = load("redact")
    ctx = redact.Ctx(**{**MAC, "users": ("ab",)})
    zero = dict.fromkeys(KEYS, 0)
    assert (redact.summary({**zero, "路徑": 1}, ctx)
            == "已自動遮蔽：1 個路徑。你的使用者名稱太短，沒有自動遮，請自己找找看。")
    assert redact.summary(zero, ctx).endswith("你的使用者名稱太短，沒有自動遮，請自己找找看。")


def test_redact_empty(load):
    redact = load("redact")
    text, counts = redact.redact("", redact.Ctx(**MAC))
    assert text == ""
    assert list(counts.items()) == [(k, 0) for k in KEYS]


@pytest.mark.parametrize("exc", [ImportError, KeyError, OSError])
def test_context_survives_getuser_failing(load, monkeypatch, exc):
    redact = load("redact")

    def fail():
        raise exc("找不到名字")

    monkeypatch.setattr(getpass, "getuser", fail)
    monkeypatch.setenv("USER", "laoban")
    monkeypatch.setenv("USERNAME", "LaoBan")  # 去重不分大小寫，留第一次出現的寫法
    monkeypatch.setenv("LOGNAME", "LAOBAN")
    ctx = redact.context(ROOT)
    assert [u for u in ctx.users if u.lower() == "laoban"] == ["laoban"]


def test_context_reads_this_machine(load):
    redact = load("redact")
    ctx = redact.context(ROOT, MODULE, ["王小明_B11201234"])
    assert ctx.home == str(Path.home())
    assert os.path.realpath(sys.base_prefix) in ctx.pythons
    assert sys.prefix in ctx.pythons
    assert (ctx.iplot, ctx.module, ctx.module_name) == (str(ROOT), str(MODULE), "回報與討論")
    assert ctx.secrets == ("王小明_B11201234",)
    try:
        user = getpass.getuser()
    except (ImportError, KeyError, OSError):  # 這台拿不到名字：只看上面的
        return
    assert user in ctx.users


def test_whole_sample_leaks_nothing(load):
    redact = load("redact")
    out = redact.redact(SAMPLE, redact.Ctx(**MAC))[0]
    for leak in ("laoban", "王小明", "B11201234", "課程", "/Users/"):
        assert leak not in out
    assert "<IPLOT>/core/runner.py" in out
    assert "<模組:科學計算>" in out


def test_real_traceback_from_tmp_leaks_nothing(load, tmp_path):
    # 真的跑一個會出錯的模組、context() 讀這台機器：macOS 的 tmp_path 帶著帳號名
    redact = load("redact")
    student = tmp_path / "Users" / "someone" / "課程" / "王小明_B11201234" / "作業.py"
    student.parent.mkdir(parents=True)
    student.write_text("1/0\n", encoding="utf-8", newline="\n")
    modules = tmp_path / "iPLoT" / "modules"
    folder = make_module(modules, "科學計算", f"import runpy\nrunpy.run_path(r'{student}', run_name='作業')\n")
    info = module_info(folder, modules.resolve(), "here")
    error = run_module(info, FakeApp(tmp_path / "iPLoT")).error
    ctx = redact.context(ROOT, info.folder)  # 第一個 frame 是這個 repo 的 core/runner.py（測試 import 的 core）
    out = redact.redact(error.traceback_text, ctx)[0]
    for leak in (str(tmp_path), os.path.realpath(tmp_path), "王小明", "B11201234"):
        assert leak not in out
    try:
        user = getpass.getuser()
    except (ImportError, KeyError, OSError):
        user = ""
    if len(user) >= 3:
        assert user not in out
    assert "<IPLOT>/core/" in out  # 不寫死 runner.py：CI 的帳號就叫 runner
    files = re.findall(r'File "([^"]*)"', out)
    assert files and all(f.startswith("<") for f in files)


# ── 環境與內文（report.py 前半）──

def copied(home):
    """把模組複製到 home/modules/回報與討論（不帶 回報/、__pycache__、.history），回它的 ModuleInfo。"""
    folder = home / "modules" / MODULE.name
    shutil.copytree(MODULE, folder, ignore=shutil.ignore_patterns("回報", "__pycache__", ".history"))
    return module_info(folder, (home / "modules").resolve(), "here")


def make_app(home):
    """真的 App：app.home 是 tmp 的 iPLoT、app.version 是核心的版本；FakeCore 的 all_modules() 是空的。"""
    return App(FakeCore(home, DEFAULT_CONFIG, FakeView()), copied(home))


def child_tree(home):
    """科學計算/、科學計算/HK2/、科學計算/HK2/王小明_B11201234/ 各有 iplot.py：學生的作業本身是下一層模組（D95）。回最深那個資料夾。"""
    top = make_module(home / "modules", "科學計算")
    return make_module(make_module(top, "HK2"), "王小明_B11201234")


@pytest.mark.parametrize("mods, want", [({"ui.tk"}, "tkinter"), ({"ui.tk", "ui.web"}, "tkinter"), ({"ui.web"}, "網頁"),
                                        (set(), "面板外")])
def test_panel_kind(load, mods, want):
    # 後備的 tkinter 面板裡兩個都在：先看 ui.tk
    assert load("report").panel_kind(dict.fromkeys(mods)) == want


@pytest.mark.parametrize("base, want", [
    ("/Library/Frameworks/Python.framework/Versions/3.14", "python.org"),
    ("/opt/homebrew/Cellar/python@3.12/3.12.13_2/Frameworks/Python.framework/Versions/3.12", "Homebrew"),
    ("/opt/homebrew/opt/python@3.10/Frameworks/Python.framework/Versions/3.10", "Homebrew"),
    ("/usr/local/Cellar/python@3.11/3.11.9/Frameworks/Python.framework/Versions/3.11", "Homebrew"),
    ("/usr", "系統"), ("/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9", "系統"),
    ("/usr/local", "其他"), ("/Users/laoban/.pyenv/versions/3.12.1", "其他"),
    ("C:\\Users\\laoban\\AppData\\Local\\Programs\\Python\\Python312", "其他")])
def test_python_source(load, base, want):
    assert load("report").python_source(base) == want


@pytest.mark.parametrize("args, kw, want", [
    (("Darwin", "arm64"), {"mac": "26.5"}, "macOS 26.5（arm64）"),
    (("Windows", "AMD64"), {"build": "22631"}, "Windows（build 22631，AMD64）"),
    (("Linux", "x86_64"), {"linux": "Ubuntu 24.04 LTS"}, "Linux：Ubuntu 24.04 LTS（x86_64）"),
    (("Linux", "x86_64"), {}, "Linux（x86_64）")])
def test_os_line(load, args, kw, want):
    assert load("report").os_line(*args, **kw) == want


def test_this_os_never_names_the_machine(load):
    # platform.node() 常常是「王老師的 MacBook」
    report = load("report")
    node = platform.node()
    if not node:
        pytest.skip("這台沒有主機名稱")
    assert node not in report.this_os()


def test_module_of_top_level(load, tmp_path):
    report = load("report")
    folder = make_module(tmp_path / "modules", "科學計算")
    (folder / "hk_tk.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    error = ErrorInfo("KeyError", "'score'", folder / "hk_tk.py", 3, "", "module", "科學計算")
    assert report.module_of(error) == (folder, ())
    # 指到模組的符號連結：核心不當它是模組（core.scan.is_module），這裡也不認
    link = tmp_path / "modules" / "連結"
    try:
        link.symlink_to(folder, target_is_directory=True)
    except OSError:  # Windows 沒有建符號連結的權限
        return
    error = ErrorInfo("KeyError", "'score'", link / "hk_tk.py", 3, "", "module", "連結")
    assert report.module_of(error) == (None, ())


def test_module_of_deep_file_in_the_module(load, tmp_path):
    # 學生的作業在模組資料夾深處，那兩層沒有 iplot.py：不是下一層模組，沒有名字要藏
    report = load("report")
    folder = make_module(tmp_path / "modules", "科學計算")
    work = folder / "HK2" / "王小明_B11201234" / "作業.py"
    work.parent.mkdir(parents=True)
    work.write_text("1/0\n", encoding="utf-8", newline="\n")
    error = ErrorInfo("ZeroDivisionError", "division by zero", work, 1, "", "module", "科學計算")
    assert report.module_of(error) == (folder, ())


def test_module_of_child_module_hides_its_name(load, tmp_path):
    report = load("report")
    student = child_tree(tmp_path)
    error = ErrorInfo("KeyError", "'score'", student / "iplot.py", 3, "", "module", "王小明_B11201234")
    assert report.module_of(error) == (tmp_path / "modules" / "科學計算", ("王小明_B11201234", "HK2"))


def test_module_of_core_error(load):
    report = load("report")
    error = ErrorInfo("KeyError", "'a'", ROOT / "core" / "core.py", 120, "", "core", None)
    assert report.module_of(error) == (None, ())


@pytest.mark.parametrize("files, want", [
    ({".origin": "url: x\nversion: 0.2.0\n"}, "0.2.0（工作坊）"),
    ({"CHANGELOG.md": "# Changelog\n\n## [Unreleased]\n\n## [0.3.1] - 2026-10-01\n\nx\n"}, "0.3.1"),
    ({}, "版本未知")])
def test_module_version(load, tmp_path, files, want):
    report = load("report")
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8", newline="\n")
    assert report.module_version(tmp_path) == want


def test_reporter_version_matches_changelog(load):
    # 內文最後那一行的 HTML 註解帶的版本：跟這個模組 CHANGELOG.md 最上面那一節一樣
    text = (MODULE / "CHANGELOG.md").read_text(encoding="utf-8")
    heads = [h for h in re.findall(r"^## \[([^\]]*)\]", text, re.M) if h.casefold() != "unreleased"]
    assert heads[0] == load("report").REPORTER


def test_fence_is_longer_than_any_tilde_run(load):
    report = load("report")
    assert report.fence("a ~~~~~~ b") == "~~~~~~~"
    assert report.fence("x") == "~~~~"


ENV = ["- iPLoT：0.6.0（面板：網頁）", "- 作業系統：macOS 26.5（arm64）", "- Python：3.14.7（python.org）",
       "- 模組：科學計算 0.2.0（工作坊）"]
SENTENCE = "模組『科學計算』第 120 行出錯：KeyError，'score'"
TB = ('Traceback (most recent call last):\n  File "<模組:科學計算>/hk_tk.py", line 120, in grade\n'
      "  （原始碼已略過）\nKeyError: 'score'\n")


def test_body_layout(load):
    report = load("report")
    assert report.body("（請寫一兩句：按了什麼、預期是什麼）", ENV, SENTENCE, TB) == (
        "### 發生了什麼\n"
        "（請寫一兩句：按了什麼、預期是什麼）\n"
        "\n"
        "### 環境\n"
        "- iPLoT：0.6.0（面板：網頁）\n"
        "- 作業系統：macOS 26.5（arm64）\n"
        "- Python：3.14.7（python.org）\n"
        "- 模組：科學計算 0.2.0（工作坊）\n"
        "\n"
        "### 錯誤\n"
        "模組『科學計算』第 120 行出錯：KeyError，'score'\n"
        "\n"
        "~~~~text\n"
        "Traceback (most recent call last):\n"
        '  File "<模組:科學計算>/hk_tk.py", line 120, in grade\n'
        "  （原始碼已略過）\n"
        "KeyError: 'score'\n"
        "~~~~\n"
        "\n"
        f"<!-- iPLoT 回報 {report.REPORTER} -->")


def test_body_without_traceback_text(load):
    # MissingHandler、config.py 的型別錯：traceback_text 是 ""
    report = load("report")
    out = report.body("x", ENV, SENTENCE, "")
    assert "~~~~text\n（沒有 traceback）\n~~~~\n" in out


def test_body_without_error(load):
    report = load("report")
    out = report.body("x", ENV, None, None)
    assert "### 錯誤" not in out and "~~~~" not in out
    assert out.startswith("### 發生了什麼\nx\n\n### 環境\n- iPLoT：")
    assert out.endswith("- 模組：科學計算 0.2.0（工作坊）\n\n<!-- iPLoT 回報 " + report.REPORTER + " -->")


ERROR_KINDS = {"module": "NameError", "core": "KeyError", "config": "TypeError"}


@pytest.mark.parametrize("source, module, want", [("module", "科學計算", "[回報] 科學計算：NameError（iPLoT 9.9.9）"),
                                                  ("core", None, "[回報] 核心：KeyError（iPLoT 9.9.9）"),
                                                  ("config", None, "[回報] config.py：TypeError（iPLoT 9.9.9）")])
def test_from_error_title(load, tmp_path, monkeypatch, source, module, want):
    report = load("report")
    monkeypatch.setattr(App, "version", "9.9.9")
    home = tmp_path / "iPLoT"
    app = make_app(home)
    file = {"module": make_module(home / "modules", "科學計算") / "iplot.py",
            "core": ROOT / "core" / "core.py", "config": home / "config.py"}[source]
    error = ErrorInfo(ERROR_KINDS[source], "x", file, None, "", source, module)
    assert report.from_error(error, app).title == want


def test_from_error_redacts_title_and_body(load, tmp_path, web):
    report = load("report")
    home = tmp_path / "iPLoT"
    app = make_app(home)
    student = child_tree(home)
    missing = student / "成績.csv"
    tb = (f'Traceback (most recent call last):\n  File "{student / "iplot.py"}", line 3, in <module>\n'
          f"    open('{missing}')\nFileNotFoundError: [Errno 2] No such file or directory: '{missing}'\n")
    error = ErrorInfo("FileNotFoundError", f"[Errno 2] No such file or directory: '{missing}'",
                      student / "iplot.py", 3, tb, "module", "王小明_B11201234")
    rep = report.from_error(error, app)
    assert rep.category == "BUG"
    assert rep.title.startswith("[回報] 科學計算：FileNotFoundError")
    for leak in ("王小明", "B11201234", str(tmp_path)):
        assert leak not in rep.title and leak not in rep.body
    assert "出錯的是它的下一層模組，名稱已遮蔽" in rep.body
    for part in ("- iPLoT：", "（面板：網頁）", "- 作業系統：", "- Python：", "### 錯誤"):
        assert part in rep.body
    assert "下一層模組" in rep.notice


def test_from_error_module_folder_gone_hides_name(load, tmp_path, web):
    # 按鈕按下去之前，那個資料夾被刪、改名或搬走（收作業會 rmtree 學生的資料夾）：不退回 error.module
    report = load("report")
    app = make_app(tmp_path / "iPLoT")
    gone = tmp_path / "不存在" / "王小明_B11201234" / "iplot.py"
    tb = (f'Traceback (most recent call last):\n  File "{gone}", line 3, in run\n'
          "    score = row['score']\nKeyError: 'score'\n")
    error = ErrorInfo("KeyError", "'score'", gone, 3, tb, "module", "王小明_B11201234")
    rep = report.from_error(error, app)
    assert rep.title.startswith("[回報] <模組>：KeyError")
    assert rep.ctx.secrets == ()  # error.module 不放進 secrets：叫 A 的模組會把整段 traceback 換爛
    for leak in ("王小明", "B11201234", str(tmp_path)):
        assert leak not in rep.title and leak not in rep.body
    assert "找不到它的資料夾，名稱已遮蔽" in rep.body


def test_blank_report_has_environment_and_no_error(load, tmp_path, web):
    report = load("report")
    rep = report.blank(make_app(tmp_path / "iPLoT"), "BUG")
    assert (rep.category, rep.title) == ("BUG", "[回報] ")
    assert "### 錯誤" not in rep.body
    assert "- iPLoT：" in rep.body and "- 模組：" not in rep.body


def test_short_env_has_no_paths(load, tmp_path, monkeypatch, web):
    # 作業系統那一段換成固定的：Debian 的 PRETTY_NAME「Debian GNU/Linux 12」帶一個 /，那不是路徑。
    # 這裡測的是 short_env 自己不加路徑
    report = load("report")
    monkeypatch.setattr(report, "this_os", lambda: "macOS 26.5（arm64）")
    out = report.short_env(make_app(tmp_path / "iPLoT"))
    assert out.startswith("iPLoT ")
    assert "/" not in out and "\\" not in out


# ── 網址、截斷、存檔（report.py 後半）──

def query(u):
    """網址的參數拆回 {名字: 值}（parse_qs 的值是清單，每個參數這裡只有一個）。"""
    return {k: v[0] for k, v in parse_qs(urlsplit(u).query, keep_blank_values=True).items()}


def long_tb(n):
    """n 行的 traceback：Traceback (most recent call last):、n - 2 個 frame、例外那一行。"""
    frames = [f'  File "<模組:科學計算>/hk_tk.py", line {i}, in step{i}' for i in range(n - 2)]
    return "\n".join(["Traceback (most recent call last):", *frames, "KeyError: 'score'"]) + "\n"


def inside_a_fence(text):
    """照 GitHub（CommonMark）的讀法，text 讀完還在框裡嗎：行首最多 3 個空白、~ 至少 3 個的那一行開框（後面帶什麼字
    都算，所以 ~~~、~~~~tex 也開框），~ 至少一樣多、後面只有空白的那一行關框。"""
    mark = None
    for line in text.split("\n"):
        if mark is None:
            m = re.match(r" {0,3}(~{3,})", line)
            mark = m[1] if m else None
        elif re.fullmatch(rf" {{0,3}}{mark}~*[ \t]*", line):
            mark = None
    return mark is not None


@pytest.mark.parametrize("value", ["a&b=c#d", "100% +1", "第一行\n第二行", "~~~~text\nx\n~~~~", "王小明 💬",
                                   "a/b\\c\"d'e"])
def test_url_roundtrips(load, value):
    q = parse_qs(urlsplit(load("report").url("BUG", value, value)).query)
    assert q["title"] == [value] and q["body"] == [value]


def test_url_category_is_the_quoted_slug(load):
    report, forum = load("report"), load("forum")
    u = report.url("BUG", "t", "b")
    assert u.startswith(forum.FORUM + "/new?")
    assert "category=" + quote(forum.CATEGORIES["BUG"], safe="") in u
    assert query(u)["category"] == forum.CATEGORIES["BUG"]


def test_url_replaces_lone_surrogates(load):
    # Linux 上 os.fsdecode 解不開的檔名帶著孤立的代理字元：quote 會丟 UnicodeEncodeError
    assert query(load("report").url("BUG", "a\udce9b", "x"))["title"] == "a?b"


@pytest.mark.parametrize("platform", ["win32", "darwin", "linux"])
def test_max_url_is_the_conservative_2000_everywhere(load, platform):
    report = load("report")
    assert report.max_url(platform) == 2000 == report.MAX_URL


def test_fit_leaves_a_short_report_alone(load):
    report = load("report")
    t, b = "[回報] 科學計算：KeyError（iPLoT 0.6.0）", report.body("x", ENV, SENTENCE, TB)
    assert report.fit("BUG", t, b, report.MAX_URL) == (report.url("BUG", t, report.with_hint(b)), False)


def test_fit_always_ends_the_body_with_the_hint(load):
    # 短的、traceback 中間截的、「發生了什麼」截的、沒有框的：網址裡的內文最後一行都是 HINT
    report = load("report")
    bodies = [report.body("x", ENV, SENTENCE, TB), report.body("x", ENV, SENTENCE, long_tb(200)),
              report.body("中" * 1000, ENV, SENTENCE, TB), "中" * 2000]
    cuts = []
    for b in bodies:
        u, cut = report.fit("BUG", "t", b, report.MAX_URL)
        cuts.append(cut)
        assert query(u)["body"].split("\n")[-1] == report.HINT
    assert cuts == [False, True, True, True]


def test_fit_keeps_the_login_redirect_short(load):
    # 之後放寬 limit 時：沒登入的話 GitHub 把整條網址再編碼一次放進 return_to，中文多的會長成大約 5/3 倍
    report = load("report")
    u, cut = report.fit("BUG", "t", "中" * 2000, 8000)
    assert cut and len(u) <= 8000 and report.login_redirect(u) <= report.MAX_LOGIN_REDIRECT
    assert report.login_redirect(u) == len(report.LOGIN + quote(u, safe=""))
    # 式子對著量到的那一組（2026-10-24：內文全是 ASCII、5621 字的網址，轉去登入的那條 5742 字）。量的那一組沒有
    # 記下標題，這裡也不是重現它：拼一條 5621 字的網址，標題挑「網址長度測試」，是因為這樣要再編碼一次的字
    # （%、:、/、?、=、&）剛好 43 個，5621 + len(LOGIN) 35 + 2 × 43 = 5742，跟量到的兩個數合得上。釘住的是式子
    base = report.url("BUG", "網址長度測試", "")
    u = report.url("BUG", "網址長度測試", "a" * (5621 - len(base)))
    assert (len(u), report.login_redirect(u)) == (5621, 5742)


def test_fit_boundary(load):
    report = load("report")
    b = report.body("x", ENV, SENTENCE, long_tb(10))
    whole = report.url("BUG", "t", report.with_hint(b))
    assert report.login_redirect(whole) <= report.MAX_LOGIN_REDIRECT  # 這裡只看 limit
    assert report.fit("BUG", "t", b, len(whole)) == (whole, False)
    u, cut = report.fit("BUG", "t", b, len(whole) - 1)
    assert cut and len(u) <= len(whole) - 1


def test_fit_keeps_the_first_and_last_lines(load):
    report = load("report")
    lines = long_tb(200).rstrip("\n").split("\n")
    u, cut = report.fit("BUG", "t", report.body("x", ENV, SENTENCE, long_tb(200)), 3000)
    assert cut and len(u) <= 3000
    out = query(u)["body"]
    inner = out.split("~~~~text\n", 1)[1].split("\n~~~~\n", 1)[0].split("\n")
    k = len(inner) - 2
    assert inner[0] == lines[0] and inner[-1] == lines[-1] and k >= 1
    assert inner[1] == report.TRUNCATED.format(n=len(lines) - 1 - k)
    assert inner[2:] == lines[-k:]
    # 二分找的是最大的 k：再多留一行就放不下
    more = [lines[0], report.TRUNCATED.format(n=len(lines) - 2 - k), *lines[-k - 1:]]
    assert len(report.url("BUG", "t", out.replace("\n".join(inner), "\n".join(more)))) > 3000
    assert out.endswith("\n\n" + report.HINT)


def test_fit_cuts_what_happened_when_one_line_is_too_long(load):
    # 使用者在「發生了什麼」貼了一大段：traceback 只留最後一行也放不下，「發生了什麼」從後面截，其他照留
    report = load("report")
    tb = 'Traceback (most recent call last):\n  File "<模組:科學計算>/hk_tk.py", line 3, in run\nKeyError: \'score\'\n'
    u, cut = report.fit("BUG", "t", report.body("中" * 1000, ENV, SENTENCE, tb), report.MAX_URL)
    assert cut and len(u) <= report.MAX_URL
    out = query(u)["body"]
    what = out.split("### 發生了什麼\n", 1)[1].split("\n\n### 環境\n", 1)[0]
    assert what.startswith("中") and what.endswith("中\n（太長，已截斷）")
    assert "### 環境\n" + "\n".join(ENV) in out and SENTENCE in out and "KeyError: 'score'" in out
    # 二分找的是最多能留幾個字：再多留一個就放不下
    longer = out.replace(what, what.replace("\n（太長，已截斷）", "中\n（太長，已截斷）"))
    assert len(report.url("BUG", "t", longer)) > report.MAX_URL


def test_fit_without_a_fence_cuts_the_tail(load):
    # 使用者把框整個刪了、貼了一大段：從內文的尾巴截
    report = load("report")
    head = "### 發生了什麼\nx\n\n### 錯誤\n"
    u, cut = report.fit("BUG", "t", head + "中" * 2000, report.MAX_URL)
    assert cut and len(u) <= report.MAX_URL
    out = query(u)["body"]
    assert out.startswith(head + "中")
    assert out.endswith("中\n（太長，已截斷）\n\n" + report.HINT)


def test_fit_closes_the_fence_it_cuts_into(load):
    # traceback 的最後一行就放不下：從尾巴截會截在框裡，補上關框的那一行，後面的字才不會被畫成程式碼
    report = load("report")
    tb = 'Traceback (most recent call last):\n  File "<模組:科學計算>/hk_tk.py", line 3, in run\nValueError: ' + "值" * 5000
    u, cut = report.fit("BUG", "t", report.body("x", ENV, SENTENCE, tb), report.MAX_URL)
    assert cut and len(u) <= report.MAX_URL
    out = query(u)["body"]
    assert "### 環境\n" + "\n".join(ENV) in out and "\n~~~~text\nTraceback (most recent call last):\n" in out
    assert out.endswith("值\n~~~~\n（太長，已截斷）\n\n" + report.HINT)


def test_fit_never_leaves_half_a_fence_line(load):
    # 從尾巴截、截在開框（~~~~text）或關框（~~~~）那一行的中間：那半行拿掉。~~~、~~~~tex 也會開框（CommonMark：~ 至少
    # 3 個、後面帶什麼字都算），留著的話 CUT 與 HINT 都被畫成程式碼；~、~~ 只是半個框。limit 一個字一個字往上加，
    # 截的地方從框的前面走過開框那一行、框裡、關框那一行，一直到留下第一個「中」
    report = load("report")
    end = "\n" + report.CUT + "\n\n" + report.HINT

    def size(head):  # 內文截成 head 加一行 CUT 時，網址多長
        return len(report.url("BUG", "t", report.with_hint(head + "\n" + report.CUT)))
    half = {"~", "~~", "~~~", "~~~~t", "~~~~te", "~~~~tex"}
    top, box = "### 發生了什麼\nx\n\n### 錯誤\nzz", "\n\n~~~~text\n"
    cases = [(top + box + "中" * 300 + "\n~~~~", ["", box + "~~~~", box + "中\n~~~~"])]  # 審查的那一組
    for k in range(1, 9):  # 框裡那一行 k 個 y：二分每次試的地方不一樣，截在關框那一行中間的情形才試得到
        ys = [box + "y" * i + "\n~~~~" for i in range(1, k + 1)]
        cases.append((top + box + "y" * k + "\n~~~~\n\n" + "中" * 300, ["", box + "~~~~", *ys, ys[-1] + "\n\n中"]))
    low = size(top)
    for b, want in cases:
        seen = []
        for limit in range(low, low + 100):
            u, cut = report.fit("BUG", "t", b, limit)
            out = query(u)["body"]
            assert cut and len(u) <= limit and out.endswith(end), limit
            head = out[:-len(end)]
            assert not inside_a_fence(head) and not half & set(head.split("\n")), (limit, head[-20:])
            assert head.startswith(top), limit
            tail = head[len(top):]
            if not seen or seen[-1] != tail:
                seen.append(tail)
            if "中" in tail:
                break
        assert seen == want


def test_fit_cuts_a_long_title(load):
    report = load("report")
    title = "標" * 500
    u, cut = report.fit("BUG", title, report.body("x", ENV, SENTENCE, TB), report.MAX_URL)
    assert cut and len(u) <= report.MAX_URL
    assert len(query(u)["title"]) <= 200 and title.startswith(query(u)["title"])
    # 標題截到 200 字就放得下的話，內文照留
    title = "a" * 3000
    u, cut = report.fit("BUG", title, report.body("x", ENV, SENTENCE, TB), report.MAX_URL)
    assert cut and len(u) <= report.MAX_URL
    assert query(u)["title"] == "a" * 200
    assert "### 環境\n" + "\n".join(ENV) in query(u)["body"]


def test_fit_caps_the_title_whenever_it_cuts(load):
    # 要截的時候，標題超過 200 字一律先截到 200 字，再截內文：不會留著 300、1500 字的標題，去截環境與 traceback
    report = load("report")
    b = report.body("x", ENV, SENTENCE, long_tb(10))
    u, cut = report.fit("BUG", "a" * 300, b, report.MAX_URL)
    assert cut and len(u) <= report.MAX_URL
    assert query(u)["title"] == "a" * 200
    assert u == report.fit("BUG", "a" * 200, b, report.MAX_URL)[0]
    assert "### 環境\n" + "\n".join(ENV) in query(u)["body"]
    # 標題截到 200 字內文就放得下的話，內文一個字都不截
    b = report.body("x", ENV, SENTENCE, TB)
    u, cut = report.fit("BUG", "a" * 1500, b, report.MAX_URL)
    assert cut and query(u)["title"] == "a" * 200 and query(u)["body"] == report.with_hint(b)
    # 不用截就不動標題（第 1 步：放得下就照用）
    assert report.fit("BUG", "a" * 250, b, report.MAX_URL) == (report.url("BUG", "a" * 250, report.with_hint(b)), False)


@pytest.mark.parametrize("limit", [1500, 2000, 4000])
def test_fit_never_exceeds_the_limit(load, limit):
    report = load("report")
    huge = 'Traceback (most recent call last):\n  File "<模組:科學計算>/hk_tk.py", line 3, in run\nValueError: ' + "x" * 5000
    sick = {"很長的中文內文": ("[回報] 科學計算：KeyError", report.body("中" * 3000, ENV, SENTENCE, long_tb(300))),
            "一行 5000 字的 traceback": ("t", report.body("x", ENV, SENTENCE, huge)),
            "沒有框": ("t", "中" * 5000),
            "標題 3000 字": ("標" * 3000, report.body("x", ENV, SENTENCE, TB)),
            "全部是 emoji": ("💬" * 500, "💬" * 5000)}
    for name, (title, b) in sick.items():
        u, cut = report.fit("BUG", title, b, limit)
        assert cut, name
        assert len(u) <= limit and report.login_redirect(u) <= report.MAX_LOGIN_REDIRECT, name
        assert query(u)["body"].endswith("\n\n" + report.HINT), name


def test_save_writes_utf8_with_stamp_and_kind(load, tmp_path):
    path = load("report").save(tmp_path / "回報", "20261023-201500", "NameError", "王小明\n")
    assert path == tmp_path / "回報" / "20261023-201500-NameError.txt"
    assert path.read_bytes() == "王小明\n".encode()  # UTF-8、換行是 \n（Windows 也一樣）


# ── 預覽頁與 on_error（iplot.py、page.html）──

PAGE = MODULE / "page.html"
STUDENT = "/Users/laoban/課程/王小明.py"  # 使用者自己貼進內文的路徑（配 MAC 的假 Ctx 是家目錄底下）


class View(FakeView):
    """View(hook=None, on_confirm=None)：page 被叫的時候先記一筆 ("page-open", title, html)，叫 hook(html, api)，
    再記一筆 ("page-closed",)；confirm 被叫的時候 on_confirm 有值就先叫 on_confirm(self)，再照 FakeView 用 answers 回。"""

    def __init__(self, hook=None, on_confirm=None):
        super().__init__()
        self.hook, self.on_confirm = hook, on_confirm

    def page(self, title, html, api):
        self.events.append(("page-open", title, html))
        if self.hook is not None:
            self.hook(html, api)
        self.events.append(("page-closed",))

    def confirm(self, prompt):
        if self.on_confirm is not None:
            self.on_confirm(self)
        return super().confirm(prompt)


def press(home, view, handler, *args, core=None):
    """真的 run_module(info, App(core, info), handler, args)（模組先複製到 home/modules），回 (result, core)。
    core.calls 就是 view.events：page-open／page-closed 與 app.reveal、app.edit 記的 action 才比得出先後。"""
    core = core or FakeCore(home, DEFAULT_CONFIG, view)
    core.calls = view.events
    info = copied(home)
    return run_module(info, App(core, info), handler, args), core


def make_api(load, tmp_path, monkeypatch, rep, kind="KeyError", **menu):
    """直接建 iplot.Api 的測試一律經過它：OUTBOX 先指到 tmp_path/回報（用 load 匯進來的 iplot，OUTBOX 指的是
    repo 裡的 modules/回報與討論/回報）。menu 是 run 那一頁才給的 starts=、short_env=（沒給就跟 on_error 一樣
    只傳前三個）。回 (api, saved)。"""
    iplot = load("iplot")
    monkeypatch.setattr(iplot, "OUTBOX", tmp_path / "回報")
    saved = []
    return iplot.Api(rep, kind, saved, **menu), saved


def sample_error(home):
    """在 home/modules 做一個「科學計算」，裡面的 hk.py 丟 KeyError；用真的 run_module 拿它的 ErrorInfo。"""
    folder = make_module(home / "modules", "科學計算", "import hk\n\n\ndef run(app):\n    hk.grade({})\n")
    (folder / "hk.py").write_text('def grade(row):\n    return row["score"]\n', encoding="utf-8", newline="\n")
    error = run_module(module_info(folder, (home / "modules").resolve(), "here"), FakeApp(home)).error
    assert error is not None and error.kind == "KeyError"
    return error


def sample_rep(load, body="### 發生了什麼\n按了「批改」\n"):
    """遮過的回報（假的 MAC Ctx）：直接建 Api 的測試用。"""
    report, redact = load("report"), load("redact")
    return report.Report("BUG", "[回報] 科學計算：KeyError（iPLoT 0.6.0）", body, "已自動遮蔽：1 個路徑。",
                         redact.Ctx(**MAC))


def page_data(html):
    """render 放進頁面的資料（<script type="application/json" id="data"> 裡那一段）。"""
    return json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S)[1])


def click_send(html, api):
    """頁面上什麼都不改，按「在瀏覽器打開」。"""
    data = page_data(html)
    api.send(data["title"], data["body"])


class Tree(HTMLParser):
    """每個有 id 的元素：(標籤, 屬性, 祖先的 [(標籤, 屬性)])；body 底下那一層的標籤與 id，照順序。"""

    VOID = {"meta", "input", "br", "img", "link", "hr"}

    def __init__(self, page):
        super().__init__()
        self.stack, self.ids, self.top = [], {}, []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids[a["id"]] = (tag, a, list(self.stack))
        if [t for t, _ in self.stack] == ["html", "body"]:
            self.top.append((tag, a.get("id")))
        if tag not in self.VOID:
            self.stack.append((tag, a))

    def handle_endtag(self, tag):
        while self.stack and self.stack.pop()[0] != tag:
            pass


def handler(page, button):
    """page.html 裡 $("<button>").addEventListener("click", … 那個函式的本體（到頂層的 }); 為止）。"""
    head = f'$("{button}").addEventListener("click"'
    assert page.count(head) == 1, button
    return page.split(head, 1)[1].split("\n});", 1)[0]


def test_api_takes_no_app(load):
    # 頁面那一頭在 pywebview 的執行緒上跑：拿得到 app 就可能叫它（設計第 17 節第 4 條）
    ps = list(inspect.signature(load("iplot").Api).parameters)
    assert "app" not in ps and ps[:3] == ["rep", "kind", "saved"]


def test_api_exposes_only_its_methods(load, tmp_path, monkeypatch):
    api, _ = make_api(load, tmp_path, monkeypatch, sample_rep(load))
    assert [n for n in dir(api) if not n.startswith("_")] == ["go", "measure", "open_forum", "send", "start"]


def test_send_redacts_again(load, tmp_path, monkeypatch, opened):
    # 使用者在預覽頁上自己貼了路徑：按送出時用同一個 ctx 再遮一次（標題、內文都是）
    api, _ = make_api(load, tmp_path, monkeypatch, sample_rep(load))
    api.send(f"[回報] {STUDENT}", f"### 發生了什麼\n我的檔是 {STUDENT}\n")
    q = query(opened[0])
    assert "<HOME>/.../<檔名已遮蔽>.py" in q["body"] and "<HOME>/.../<檔名已遮蔽>.py" in q["title"]
    assert "王小明" not in q["body"] and "王小明" not in q["title"]


def test_send_opens_the_browser_once_with_the_fitted_url(load, tmp_path, monkeypatch, opened):
    report = load("report")
    rep = sample_rep(load)
    api, _ = make_api(load, tmp_path, monkeypatch, rep)
    long = report.body("x", ENV, SENTENCE, long_tb(300))
    r = api.send(rep.title, long)
    assert r["cut"] and len(opened) == 1
    assert opened[0] == report.fit("BUG", rep.title, long, report.max_url())[0]


def test_send_always_saves_the_full_text_before_opening_the_browser(load, tmp_path, monkeypatch):
    # 研究助理 Task 0：沒登入的瀏覽器登入之後 GitHub 回 500——開瀏覽器的那一刻，遮過的全文一定已經在 回報/ 裡
    redact, report = load("redact"), load("report")
    seen, outbox = [], []

    def browser(u, *a, **k):
        seen.append(sorted(p.read_text(encoding="utf-8") for p in outbox[-1].glob("*.txt")))
        return True

    monkeypatch.setattr(webbrowser, "open", browser)
    rep = sample_rep(load)
    short = f"{rep.body}我的檔是 {STUDENT}\n"
    outbox.append(tmp_path / "短" / "回報")
    api, saved = make_api(load, tmp_path / "短", monkeypatch, rep)
    r = api.send(rep.title, short)
    full = f"{rep.title}\n\n{redact.redact(short, rep.ctx)[0]}"
    assert seen == [[full]] and "王小明" not in full and report.HINT not in full
    assert (r["ok"], r["cut"], saved) == (True, False, [])  # 沒截、開成了：不用指給人看
    assert r["file"] == next(outbox[-1].glob("*.txt")).name
    long = report.body("x", ENV, SENTENCE, long_tb(300))
    outbox.append(tmp_path / "長" / "回報")
    api, saved = make_api(load, tmp_path / "長", monkeypatch, rep)
    r = api.send(rep.title, long)
    full = f"{rep.title}\n\n{redact.redact(long, rep.ctx)[0]}"
    assert seen[-1] == [full] and r["cut"]
    assert [p.name for p in saved] == [r["file"]] and saved[0].read_text(encoding="utf-8") == full  # 沒截的全文
    assert report.HINT not in full


@pytest.mark.parametrize("fail", ["false", "error", "oserror"])
def test_send_when_the_browser_fails_returns_the_url(load, tmp_path, monkeypatch, fail):
    def browser(u, *a, **k):
        if fail == "error":
            raise webbrowser.Error("找不到瀏覽器")
        if fail == "oserror":
            raise OSError("ShellExecute 失敗")
        return False

    monkeypatch.setattr(webbrowser, "open", browser)
    report = load("report")
    rep = sample_rep(load)
    api, saved = make_api(load, tmp_path, monkeypatch, rep)
    r = api.send(rep.title, rep.body)
    assert r["ok"] is False and r["url"] == report.fit("BUG", rep.title, rep.body, report.max_url())[0]
    assert r["sentence"].startswith("瀏覽器打不開")
    assert [p.name for p in saved] == [r["file"]] and saved[0].parent == tmp_path / "回報"


def test_measure_reports_length_and_limit(load, tmp_path, monkeypatch):
    report = load("report")
    rep = sample_rep(load)
    api, _ = make_api(load, tmp_path, monkeypatch, rep)
    r = api.measure(rep.title, rep.body)
    want = len(report.url("BUG", rep.title, report.with_hint(rep.body)))
    assert (r["length"], r["limit"]) == (want, report.max_url())
    assert r["sentence"] == f"網址長度 {want}／{report.max_url()}"
    r = api.measure(rep.title, report.body("x", ENV, SENTENCE, long_tb(300)))
    assert r["length"] > r["limit"]
    assert r["sentence"].startswith(f"網址長度 {r['length']}／{r['limit']}")
    assert "traceback 會從中間截斷；完整的會在剪貼簿與檔案裡" in r["sentence"]


def test_measure_gives_the_redacted_full_text(load, tmp_path, monkeypatch):
    # 頁面複製的就是這一份：要跟按下去之後存的檔一字不差
    rep = sample_rep(load)
    api, _ = make_api(load, tmp_path, monkeypatch, rep)
    b = f"{rep.body}我的檔是 {STUDENT}\n"
    full = api.measure(rep.title, b)["full"]
    assert "<HOME>/.../<檔名已遮蔽>.py" in full and "王小明" not in full
    assert full.startswith(rep.title + "\n\n")
    r = api.send(rep.title, b)
    assert (tmp_path / "回報" / r["file"]).read_text(encoding="utf-8") == full


def test_page_html_is_self_contained():
    page = PAGE.read_text(encoding="utf-8")
    for bad in ("http://", "https://", "innerHTML", "<a "):
        assert bad not in page, bad
    assert "prefers-color-scheme: dark" in page and "pywebviewready" in page
    assert page.count("__DATA__") == 1


def test_data_reaches_the_page_as_json_not_markup(load):
    out = load("iplot").render({"title": "<b>x</b>"})
    assert "\\u003cb>x" in out and "<b>x</b>" not in out


def test_page_copies_before_it_sends():
    # 瀏覽器只讓使用者按下去的那一下複製：複製在 click 裡、叫 send 之前，不在 send 回來之後
    page = PAGE.read_text(encoding="utf-8")
    body = handler(page, "open")
    copy, send = body.index('execCommand("copy")'), body.index(".send(")
    assert copy < send and ".then(" not in body[copy:send]
    assert 'execCommand("copy")' in handler(page, "again")
    tree = Tree(page)
    tag, attrs, parents = tree.ids["full"]
    assert tag == "textarea" and "readonly" in attrs and "hidden" not in attrs  # 藏起來的選不起來、複製不了
    assert [t for t, _ in parents] == ["html", "body"]  # 直接在 <body> 底下：不在 #edit／#menu 裡
    assert not any("hidden" in a for _, a in parents)
    assert re.search(r"#full\s*\{[^}]*position:\s*absolute;[^}]*left:\s*-9999px", page)


def test_page_copies_only_the_redacted_full_text(load, tmp_path, web):
    # 剪貼簿裡絕對不能是沒遮過的版本（研究助理 2026-10-25）：只複製 measure 回來的 full
    page = PAGE.read_text(encoding="utf-8")
    sets = re.findall(r'\$\("full"\)\.value = ([^;\n]*);', page)
    assert len(sets) == 1 and sets[0].endswith(".full")
    copies = [m.start() for m in re.finditer(r'execCommand\("copy"\)', page)]
    assert len(copies) == 2  # 「在瀏覽器打開」與「再複製一次」
    for at in copies:
        before = page[:at]
        assert before[:before.rindex(".select()")].endswith('$("full")')
    assert page.count(".select()") == page.count('$("full").select()')  # 標題、內文那兩格從不 select()
    # 預覽頁（#edit 顯示的時候）最後一行是 HINT：字由 render 的資料帶進來，page.html 不另抄一份；
    # #menu 上藏著它（test_page_shows_the_hint_only_with_the_preview）
    report = load("report")
    assert report.HINT not in page and '$("hint").textContent = data.hint' in page
    tree = Tree(page)
    assert tree.top[-3:] == [("p", "hint"), ("script", "data"), ("script", None)]  # 最後一行（#full 在畫面外）
    home = tmp_path / "iPLoT"
    view = View()
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    assert page_data(view.events[0][2])["hint"] == report.HINT


def test_page_reminds_to_log_in_and_paste(load, tmp_path, monkeypatch, opened):
    page = PAGE.read_text(encoding="utf-8")
    for part in ("已經登入 GitHub", "直接貼上", "再複製一次"):
        assert part in page, part
    rep = sample_rep(load)
    api, _ = make_api(load, tmp_path, monkeypatch, rep)
    r = api.send(rep.title, rep.body)
    for part in ("直接貼上", f"回報/{r['file']}", "再按一次"):
        assert part in r["sentence"], part
    blocker = tmp_path / "是一個檔"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(load("iplot"), "OUTBOX", blocker)  # 存不了檔：照樣開瀏覽器，不丟例外
    opened.clear()
    r = api.send(rep.title, rep.body)
    assert (r["ok"], len(opened), r["file"]) == (True, 1, "")
    assert "存不了檔" in r["sentence"] and "完整的回報只在剪貼簿裡" in r["sentence"]


def test_on_error_opens_the_preview_page(tmp_path, web, opened):
    home = tmp_path / "iPLoT"
    view = View()
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    pages = [e for e in view.events if e[0] == "page-open"]
    assert len(pages) == 1 and pages[0][1] == "回報這個問題"
    data = page_data(pages[0][2])
    assert data["mode"] == "edit" and "[回報] 科學計算：KeyError" in data["title"]
    assert "### 錯誤" in data["body"] and data["notice"].startswith(("已自動遮蔽", "沒有找到"))
    assert opened == []


def test_on_error_reveals_the_saved_file_after_the_page_closes(tmp_path, web, opened):
    # reveal 經過 Core.press：在 api 裡（pywebview 的執行緒）叫會弄壞整個程序的 cwd、stdout（設計第 17 節第 4 條）
    home = tmp_path / "iPLoT"

    def hook(html, api):
        assert api.send(page_data(html)["title"], "x\n" + long_tb(300))["cut"]

    view = View(hook=hook)
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    assert [e[0] for e in view.events] == ["page-open", "page-closed", "action"]
    action = view.events[2]
    assert action[:2] == ("action", "reveal") and action[2].suffix == ".txt"
    assert action[2].parent == (home / "modules" / "回報與討論" / "回報").resolve()
    assert len(opened) == 1


def test_on_error_outside_the_panel_uses_the_page(tmp_path, monkeypatch, opened):
    # 互通的小視窗：兩個都不在，app.page 在那裡能用
    monkeypatch.delitem(sys.modules, "ui.tk", raising=False)
    monkeypatch.delitem(sys.modules, "ui.web", raising=False)
    home = tmp_path / "iPLoT"
    view = View()
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    assert [e[1] for e in view.events if e[0] == "page-open"] == ["回報這個問題"]
    assert opened == []


def test_on_error_in_tk_uses_a_file(tmp_path, tk, opened):
    # 後備的 tkinter 面板（ui.tk 與 ui.web 都在）：沒有頁面，走草稿檔（設計第 5.2 節、第 17 節第 7 條）
    home = tmp_path / "iPLoT"
    view = View()
    view.answers = [True]
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    assert not [e for e in view.events if e[0] in ("page", "page-open")]
    outbox = (home / "modules" / "回報與討論" / "回報").resolve()
    draft, = outbox.glob("*.md")
    assert [e for e in view.events if e[:2] == ("action", "edit")] == [("action", "edit", draft, None, None)]
    assert draft.read_text(encoding="utf-8").split("\n")[0].startswith("[回報] 科學計算：KeyError")
    assert "草稿在 回報/" in view.confirmed[0]
    assert len(opened) == 1


def test_on_error_in_tk_copies_and_saves_before_opening(tmp_path, tk, monkeypatch):
    tkinter = pytest.importorskip("tkinter")
    mine = str(Path.home() / "課程" / "王小明.py")  # 真的 Ctx（這台的家目錄）底下的一個路徑：遮成 <HOME>/…

    class Root:
        """tkinter 面板自己的那個 Tk 的替身：記下剪貼簿裡的字。"""
        text = None

        def clipboard_clear(self):
            self.text = ""

        def clipboard_append(self, s):
            self.text += s

        def update_idletasks(self):
            pass

    order = []
    outbox = []

    def browser(u, *a, **k):  # 開瀏覽器的那一刻：剪貼簿與 回報/ 的 .txt 都已經是遮過的全文
        texts = sorted(p.read_text(encoding="utf-8") for p in outbox[-1].glob("*.txt"))
        order.append((root.text if root else None, texts))
        return True

    def add(view):  # 按「確定」之前，使用者在草稿裡貼了一個路徑
        draft = next(e[2] for e in view.events if e[:2] == ("action", "edit"))
        draft.write_text(draft.read_text(encoding="utf-8") + f"\n我的檔是 {mine}\n", encoding="utf-8", newline="\n")

    monkeypatch.setattr(webbrowser, "open", browser)
    root = Root()
    monkeypatch.setattr(tkinter, "_default_root", root, raising=False)
    home = tmp_path / "一" / "iPLoT"
    outbox.append(home / "modules" / "回報與討論" / "回報")
    view = View(on_confirm=add)
    view.answers = [True]
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    (text, files), = order
    assert text and files == [text]  # 短的也存
    assert "<HOME>/.../<檔名已遮蔽>.py" in text and "王小明" not in text
    assert any("已經複製到剪貼簿" in s for s in view.logs) and any("⌘V／Ctrl+V" in s for s in view.logs)
    # tkinter 自己的 Tk 拿不到：照樣存檔、開瀏覽器
    root = None
    monkeypatch.setattr(tkinter, "_default_root", None, raising=False)
    home = tmp_path / "二" / "iPLoT"
    outbox.append(home / "modules" / "回報與討論" / "回報")
    view = View(on_confirm=add)
    view.answers = [True]
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    assert len(order) == 2 and len(order[1][1]) == 1 and "王小明" not in order[1][1][0]
    assert any("剪貼簿沒有複製成功" in s for s in view.logs)
    # report.save 丟 OSError（磁碟滿、沒有權限）：照 send 的做法，照樣複製、開瀏覽器，那一句說存不了檔
    root = Root()
    monkeypatch.setattr(tkinter, "_default_root", root, raising=False)
    home = tmp_path / "三" / "iPLoT"
    outbox.append(home / "modules" / "回報與討論" / "回報")

    def refuse(*a):
        raise OSError("磁碟滿了")

    def full_disk(view):
        add(view)
        assert Path(sys.modules["report"].__file__).resolve().parent == outbox[-1].parent.resolve()  # tmp 的那一份
        monkeypatch.setattr(sys.modules["report"], "save", refuse)

    view = View(on_confirm=full_disk)
    view.answers = [True]
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    assert len(order) == 3 and order[2] == (root.text, []) and "王小明" not in root.text
    assert any("存不了檔（磁碟滿了）" in s and "已經複製到剪貼簿" in s for s in view.logs)
    assert not [e for e in view.events if e[:2] == ("action", "reveal")]


def test_on_error_in_tk_cancel_keeps_the_draft(tmp_path, tk, opened):
    home = tmp_path / "iPLoT"
    view = View()
    view.answers = [False]
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    assert opened == []
    assert any(s.startswith("沒有送出；草稿留在 回報/") for s in view.logs)
    outbox = home / "modules" / "回報與討論" / "回報"
    assert len(list(outbox.glob("*.md"))) == 1 and not list(outbox.glob("*.txt"))


def test_on_error_in_tk_reveals_a_redacted_txt_when_cut(tmp_path, tk, opened):
    # 草稿沒有再遮過（使用者可能貼了路徑）：指給人看、拿去貼、拖去當附件的是遮過的 .txt
    def add(view):
        draft = next(e[2] for e in view.events if e[:2] == ("action", "edit"))
        extra = f"\n我的檔是 {STUDENT}\n" + "很長的一段字。" * 400 + "\n"
        draft.write_text(draft.read_text(encoding="utf-8") + extra, encoding="utf-8", newline="\n")

    home = tmp_path / "iPLoT"
    view = View(on_confirm=add)
    view.answers = [True]
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    reveals = [e for e in view.events if e[:2] == ("action", "reveal")]
    assert len(reveals) == 1 and reveals[0][2].suffix == ".txt"
    text = reveals[0][2].read_text(encoding="utf-8")
    assert "王小明" not in text and "<檔名已遮蔽>.py" in text and "很長的一段字。" * 400 in text
    assert len(opened) == 1 and len(opened[0]) <= 2000


def test_on_error_for_a_child_module_hides_its_name(tmp_path, web, opened):
    home = tmp_path / "iPLoT"
    deep = child_tree(home)
    (deep / "iplot.py").write_text('def run(app):\n    {}["score"]\n', encoding="utf-8", newline="\n")
    error = run_module(module_info(deep, (home / "modules").resolve(), "child"), FakeApp(home)).error
    assert error.module == "王小明_B11201234"
    result, _ = press(home, View(hook=click_send), "on_error", error)
    assert result.ok, result.error
    q = query(opened[0])
    assert q["title"].startswith("[回報] 科學計算：KeyError")
    for leak in ("王小明", "B11201234"):
        assert leak not in q["title"] and leak not in q["body"]


def test_on_error_end_to_end_leaks_nothing(tmp_path, web, opened):
    # 不用假的 Ctx：tmp 的 iPLoT、真的 run_module 拿到的錯誤（macOS 的 tmp_path 帶著帳號名）、按送出、拆回網址
    student = tmp_path / "課程" / "王小明_B11201234" / "作業.py"
    student.parent.mkdir(parents=True)
    student.write_text(f"open(r'{student.parent / '成績.csv'}')\n", encoding="utf-8", newline="\n")
    home = tmp_path / "iPLoT"
    folder = make_module(home / "modules", "科學計算", f"import runpy\nrunpy.run_path(r'{student}', run_name='作業')\n")
    error = run_module(module_info(folder, (home / "modules").resolve(), "here"), FakeApp(home)).error
    assert error.kind == "FileNotFoundError" and "王小明" in error.traceback_text
    result, _ = press(home, View(hook=click_send), "on_error", error)
    assert result.ok, result.error
    q = query(opened[0])
    out = q["title"] + "\n" + q["body"]
    for leak in (str(tmp_path), os.path.realpath(tmp_path), "王小明", "B11201234"):
        assert leak not in out
    try:
        user = getpass.getuser()
    except (ImportError, KeyError, OSError):
        user = ""
    if len(user) >= 3:
        assert user not in out
    assert "FileNotFoundError" in q["title"] and "### 錯誤" in q["body"]


# ── 存不了檔、草稿讀不回、開不成又截過、頁面關掉時 send 還在跑（Task 7 修補）──

class Clipboard:
    """tkinter 面板自己的那個 Tk 的替身：記下剪貼簿裡的字。"""
    text = None

    def clipboard_clear(self):
        self.text = ""

    def clipboard_append(self, s):
        self.text += s

    def update_idletasks(self):
        pass


def denied(where):
    """report.save 真的存不了檔時的那種 OSError：字帶著完整的路徑（str(OSError) 是 [Errno 13] …: '<路徑>'）。"""
    return OSError(errno.EACCES, "Permission denied", str(where))


def refusing(monkeypatch, exc, before=None):
    """tkinter 那一頭的 on_confirm：先叫 before(view)（有的話），再把 tmp 那一份 report.save 換成丟 exc 的替身
    （run_module 匯進來的是 tmp 的複本，不是 load 的那一份）。"""
    def swap(view):
        if before is not None:
            before(view)

        def refuse(*a):
            raise exc

        monkeypatch.setattr(sys.modules["report"], "save", refuse)
    return swap


def press_tk(home, on_confirm, error=None):
    """後備的 tkinter 面板上按「回報這個問題」、在草稿那一步按「確定」（之前先叫 on_confirm(view)）；回 view。
    error 沒給就用 sample_error(home)。"""
    view = View(on_confirm=on_confirm)
    view.answers = [True]
    result, _ = press(home, view, "on_error", error or sample_error(home))
    assert result.ok, result.error
    return view


def assert_no_leak(lines):
    """訊息區的每一行都沒有這台的家目錄（含 Windows 的 repr：兩個反斜線）、帳號名、學生的名字。"""
    home = str(Path.home())
    try:
        user = getpass.getuser()
    except (ImportError, KeyError, OSError):
        user = ""
    for s in lines:
        for leak in (home, repr(home)[1:-1], "王小明", *([user] if len(user) >= 3 else [])):
            assert leak not in s, (leak, s)


def test_send_masks_the_save_error(load, tmp_path, monkeypatch, opened):
    # OSError 的字帶著完整的路徑（家目錄、帳號名）：頁面上那一句可能被複製進公開的貼文，先用同一個 ctx 遮過
    rep = sample_rep(load)
    api, saved = make_api(load, tmp_path, monkeypatch, rep)
    exc = denied(f"{rep.ctx.home}/課程/王小明/回報/x.txt")

    def refuse(*a):
        raise exc

    monkeypatch.setattr(load("report"), "save", refuse)
    r = api.send(rep.title, rep.body)
    assert (r["ok"], r["file"], saved, len(opened)) == (True, "", [], 1)
    assert "存不了檔（[Errno 13] Permission denied: '<HOME>/.../<檔名已遮蔽>.txt'）" in r["sentence"]
    for leak in (rep.ctx.home, "laoban", "王小明"):
        assert leak not in r["sentence"], leak


def test_send_survives_a_lone_surrogate(load, tmp_path, monkeypatch, opened):
    # Linux 上解不開的資料夾名字（os.fsdecode 留下孤立的代理字元）：write_text 丟 UnicodeEncodeError（ValueError），
    # 跟存不了檔一樣照樣開瀏覽器，不能讓 send 丟出去
    rep = sample_rep(load)
    api, saved = make_api(load, tmp_path, monkeypatch, rep)
    r = api.send("[回報] 科學計算\udce9：KeyError", rep.body)
    assert (r["ok"], r["file"], saved, len(opened)) == (True, "", [], 1)
    # UnicodeEncodeError 的字裡有 '\udce9' 這種跳脫，redact 會把它當成路徑：不給人看那串字，只說一句短的
    assert "存不了檔（有沒辦法存成 UTF-8 的字）；完整的回報只在剪貼簿裡。" in r["sentence"]
    assert "<PATH>" not in r["sentence"] and "codec" not in r["sentence"]
    assert list((tmp_path / "回報").iterdir()) == []  # report.save 寫到一半丟的：不留 0 位元組的 .txt


@pytest.mark.parametrize("save", ["saved", "unsaved"])
def test_send_when_the_browser_fails_and_the_url_was_cut_says_so(load, tmp_path, monkeypatch, save):
    # 開不成、網址又截過：只叫人複製網址的話，人不知道網址裡的 traceback 少了一段
    iplot, report = load("iplot"), load("report")
    monkeypatch.setattr(webbrowser, "open", lambda u, *a, **k: False)
    rep = sample_rep(load)
    api, saved = make_api(load, tmp_path, monkeypatch, rep)
    if save == "unsaved":
        blocker = tmp_path / "是一個檔"
        blocker.write_text("x", encoding="utf-8")
        monkeypatch.setattr(iplot, "OUTBOX", blocker)
    r = api.send(rep.title, report.body("x", ENV, SENTENCE, long_tb(300)))
    assert (r["ok"], r["cut"]) == (False, True) and r["sentence"].startswith("瀏覽器打不開")
    if save == "saved":
        assert iplot.CUT_SAVED in r["sentence"] and f"回報/{r['file']}" in r["sentence"]
        assert r["sentence"].count("關掉這個視窗之後 iPLoT 會指給你看") == 1
        assert [p.name for p in saved] == [r["file"]]
    else:
        assert r["sentence"].endswith(iplot.CUT_UNSAVED) and "存不了檔" in r["sentence"] and saved == []


def test_send_marks_a_cut_file_before_opening_the_browser(load, tmp_path, monkeypatch):
    # 頁面可能在 webbrowser.open 還沒回來的時候就被關掉：截過的檔在開瀏覽器之前就已經記在 saved 裡
    report = load("report")
    rep = sample_rep(load)
    api, saved = make_api(load, tmp_path, monkeypatch, rep)
    seen = []
    monkeypatch.setattr(webbrowser, "open", lambda u, *a, **k: seen.append(list(saved)) or True)
    r = api.send(rep.title, report.body("x", ENV, SENTENCE, long_tb(300)))
    assert r["cut"] and seen == [[tmp_path / "回報" / r["file"]]]


@pytest.mark.parametrize("case", ["cut", "browser-failed"])
def test_on_error_waits_for_a_send_still_running(tmp_path, web, monkeypatch, case):
    # pywebview 每一次 api 呼叫各一條執行緒：頁面關掉的時候 send 可能還卡在 webbrowser.open 裡。
    # on_error 拿 Api 的鎖、等它做完，才看要指哪些檔（不然截過、開不成的那個檔指不到）
    entered, release, results, threads = threading.Event(), threading.Event(), [], []

    def browser(u, *a, **k):
        entered.set()
        assert release.wait(10)
        return case == "cut"

    monkeypatch.setattr(webbrowser, "open", browser)

    def hook(html, api):  # 按了「在瀏覽器打開」，send 還沒回來就關掉頁面；0.2 秒之後瀏覽器才回來
        body = "x\n" + long_tb(300) if case == "cut" else "x\n"
        t = threading.Thread(target=lambda: results.append(api.send(page_data(html)["title"], body)))
        t.start()
        threads.append(t)
        assert entered.wait(10)
        threading.Timer(0.2, release.set).start()

    home = tmp_path / "iPLoT"
    view = View(hook=hook)
    result, _ = press(home, view, "on_error", sample_error(home))
    release.set()
    threads[0].join(10)
    assert result.ok, result.error
    r, = results
    assert r["cut"] if case == "cut" else not r["ok"]
    assert [e[0] for e in view.events] == ["page-open", "page-closed", "action"]
    action = view.events[2]
    assert action[:2] == ("action", "reveal") and action[2].name == r["file"]


def test_on_error_in_tk_masks_the_save_error(tmp_path, tk, monkeypatch):
    tkinter = pytest.importorskip("tkinter")
    root = Clipboard()
    monkeypatch.setattr(tkinter, "_default_root", root, raising=False)
    where = Path.home() / "課程" / "王小明" / "回報" / "x.txt"  # 真的 Ctx：這台的家目錄底下（執行時才算，不寫進檔）
    view = press_tk(tmp_path / "iPLoT", refusing(monkeypatch, denied(where)))
    line, = [s for s in view.logs if "存不了檔" in s]
    assert "已經複製到剪貼簿" in line and "<HOME>/.../<檔名已遮蔽>.txt" in line
    assert_no_leak(view.logs)
    assert root.text and "王小明" not in root.text


def test_on_error_in_tk_logs_the_redacted_full_text_when_it_can_neither_save_nor_copy(tmp_path, tk, monkeypatch, opened):
    # 存不了檔、剪貼簿也沒複製成（_default_root 是 None）：遮過的全文直接寫進訊息區；
    # 草稿沒有再遮過，不叫人從草稿複製
    mine = Path.home() / "課程" / "王小明.py"

    def add(view):
        draft = next(e[2] for e in view.events if e[:2] == ("action", "edit"))
        draft.write_text(draft.read_text(encoding="utf-8") + f"\n我的檔是 {mine}\n", encoding="utf-8", newline="\n")

    view = press_tk(tmp_path / "iPLoT", refusing(monkeypatch, denied(Path.home() / "課程" / "王小明" / "x.txt"), add))
    line, = [s for s in view.logs if "存不了檔" in s]
    assert "剪貼簿也沒有複製成功" in line and "<HOME>/.../<檔名已遮蔽>.txt" in line
    assert "訊息區" in line and "草稿" not in line
    full, = [s for s in view.logs if s.startswith("[回報] 科學計算：KeyError")]
    assert "我的檔是 <HOME>/.../<檔名已遮蔽>.py" in full and "### 錯誤" in full
    assert view.logs.index(full) == view.logs.index(line) + 1  # 那一句說的「下面那一則」
    assert_no_leak(view.logs)
    assert len(opened) == 1


def spoiler(how, names):
    """草稿那一步按「確定」之前（View 的 on_confirm）：deleted 把草稿刪掉，big5 用 Big5（cp950）蓋過；草稿的檔名記進 names。"""
    def spoil(view):
        draft = next(e[2] for e in view.events if e[:2] == ("action", "edit"))
        names.append(draft.name)
        if how == "deleted":
            draft.unlink()
        else:
            draft.write_bytes("[回報] 科學計算：KeyError\n\n我改過了\n".encode("cp950"))

    return spoil


def assert_unreadable(view, home, how, name, tmp_path, opened):
    """讀不回草稿：訊息區一句話、不開瀏覽器、不存 .txt、不指檔案。那一句不提任何一顆鈕：同一個 _by_file 從
    「回報這個問題」（on_error）與選單的「1」（run）都會走到，兩邊按的不一樣（控制者的裁定）。"""
    line, = [s for s in view.logs if s.startswith("讀不回草稿")]
    assert "沒有送出" in line and "請再試一次（會開新的一份）" in line
    assert "再按一次" not in line and "「" not in line
    if how == "big5":
        assert f"草稿留在 回報/{name}" in line and "UTF-8" in line
    else:
        assert "<檔名已遮蔽>.md" in line  # FileNotFoundError 的字帶著草稿的完整路徑：遮過
    for leak in (str(tmp_path), os.path.realpath(tmp_path)):
        assert leak not in line
    assert_no_leak([line])
    assert opened == []
    assert not list((home / "modules" / "回報與討論" / "回報").glob("*.txt"))
    assert not [e for e in view.events if e[:2] == ("action", "reveal")]


@pytest.mark.parametrize("how", ["deleted", "big5"])
def test_on_error_in_tk_unreadable_draft_is_one_sentence(tmp_path, tk, opened, how):
    # 按「確定」之前草稿被刪了、或用 Big5（cp950）存了：一句話、不開瀏覽器，不變成「回報與討論」自己的錯誤
    names = []
    home = tmp_path / "iPLoT"
    view = press_tk(home, spoiler(how, names))
    assert_unreadable(view, home, how, names[0], tmp_path, opened)


# ── 草稿存不了、寫到一半的檔、tkinter 那一頭截過時也說（Task 7 修補第 2 輪）──

def test_save_leaves_no_file_when_writing_fails(load, tmp_path, monkeypatch):
    # write_text 先建檔再編碼：孤立的代理字元丟 UnicodeEncodeError 時，回報/ 裡不能留一個 0 位元組的 <時間>-<kind>.txt
    report = load("report")
    with pytest.raises(UnicodeEncodeError):
        report.save(tmp_path / "回報", "20261025-120000", "KeyError", "[回報] 科學計算\udce9：KeyError\n")
    assert list((tmp_path / "回報").iterdir()) == []
    # 開不了的（同一秒存過、沒有權限）不刪：那個檔不是這一次寫的
    old = tmp_path / "回報" / "20261025-120001-KeyError.txt"
    old.write_text("上一次的", encoding="utf-8", newline="\n")
    real_open = Path.open

    def refuse(self, *a, **k):
        if self == old:
            raise denied(old)
        return real_open(self, *a, **k)

    monkeypatch.setattr(Path, "open", refuse)
    with pytest.raises(PermissionError):
        report.save(tmp_path / "回報", "20261025-120001", "KeyError", "這一次的")
    with open(old, encoding="utf-8") as fh:  # 內建的 open：Path.open 還是替身
        assert fh.read() == "上一次的"


@pytest.mark.parametrize("how", ["mkdir", "write", "surrogate"])
def test_on_error_in_tk_draft_that_cannot_be_written_is_one_sentence(tmp_path, tk, monkeypatch, opened, how):
    # 草稿那一步就存不了（回報/ 建不了、草稿寫不進去、標題裡有孤立的代理字元）：一句話，不問、不開編輯器、不開瀏覽器，
    # 不變成「回報與討論」自己的錯誤（那個錯誤又會帶一顆「回報這個問題」）
    where = Path.home() / "課程" / "王小明" / "回報"  # 真的 Ctx：這台的家目錄底下（執行時才算，不寫進檔）
    if how == "mkdir":
        real_mkdir = Path.mkdir

        def mkdir(self, *a, **k):
            if self.name == "回報" and self.parent.name == MODULE.name:
                raise denied(where)
            return real_mkdir(self, *a, **k)

        monkeypatch.setattr(Path, "mkdir", mkdir)
    elif how == "write":
        real_write = Path.write_text

        def write_text(self, *a, **k):
            if self.suffix == ".md" and self.parent.name == "回報":
                raise denied(where / "x.md")
            return real_write(self, *a, **k)

        monkeypatch.setattr(Path, "write_text", write_text)
    else:  # 孤立的代理字元從 App.version 帶進標題（Linux 上解不開的資料夾名字也是這樣進到標題裡的）
        monkeypatch.setattr(App, "version", "0.6.0\udce9")
    home = tmp_path / "iPLoT"
    view = View()
    result, _ = press(home, view, "on_error", sample_error(home))
    assert result.ok, result.error
    line, = view.logs
    assert line.startswith("草稿存不了（") and line.endswith("），沒有送出。")
    if how == "surrogate":
        assert line == "草稿存不了（有沒辦法存成 UTF-8 的字），沒有送出。"
    else:
        assert "Permission denied" in line and "<HOME>/.../<檔名已遮蔽>" in line
    assert "<PATH>" not in line
    assert_no_leak(view.logs)
    assert view.confirmed == [] and opened == []
    assert not [e for e in view.events if e[0] == "action"]  # 沒有 edit、沒有 reveal
    outbox = home / "modules" / "回報與討論" / "回報"
    assert not outbox.exists() or list(outbox.iterdir()) == []  # 也不留一個空的草稿


TK_CUT_CASES = [("opened", "saved"), ("failed", "saved"), ("opened", "copied"), ("failed", "copied"),
                ("opened", "unsaved"), ("failed", "unsaved")]


@pytest.mark.parametrize("browser, save", TK_CUT_CASES, ids=["-".join(c) for c in TK_CUT_CASES])
def test_on_error_in_tk_says_when_the_url_was_cut(tmp_path, tk, monkeypatch, browser, save):
    # tkinter 那一頭截過時也要說（網頁那一頭是 CUT_SAVED／CUT_UNSAVED）：只給人網址的話，人不知道網址裡的 traceback
    # 少了一段。開成了說在訊息區那一句裡、開不成說在給網址的那一行裡，只說一次；檔案一定會指給人看
    calls = []
    monkeypatch.setattr(webbrowser, "open", lambda u, *a, **k: calls.append(u) or browser == "opened")
    if save == "copied":
        tkinter = pytest.importorskip("tkinter")
        monkeypatch.setattr(tkinter, "_default_root", Clipboard(), raising=False)
    home = tmp_path / "iPLoT"
    error = dataclasses.replace(sample_error(home), traceback_text=long_tb(300))  # 網址放不下：從 traceback 中間截
    unsaved = refusing(monkeypatch, denied(Path.home() / "課程" / "王小明" / "x.txt"))
    view = press_tk(home, unsaved if save == "unsaved" else None, error)
    assert len(calls) == 1 and len(calls[0]) <= 2000
    reveals = [e[2] for e in view.events if e[:2] == ("action", "reveal")]
    if save == "unsaved":
        assert reveals == []
        cut = "內容太長，網址裡的 traceback 中間截掉了。"
    else:
        p, = reveals
        assert p.suffix == ".txt" and "Traceback (most recent call last):" in p.read_text(encoding="utf-8")
        cut = (f"內容太長，網址裡的 traceback 中間截掉了；回報/{p.name} 是完整的，貼上之後也可以把它拖進留言框當附件。"
               "iPLoT 會指給你看。")
    assert sum(s.count("網址裡的 traceback 中間截掉了") for s in view.logs) == 1
    first, = [s for s in view.logs if "如果 GitHub 出錯" in s]
    failed = [s for s in view.logs if s.startswith("瀏覽器打不開")]
    hint = "完整報告已複製，GitHub 出錯或內容被截斷時，按 ⌘V／Ctrl+V 貼上。"
    if browser == "opened":
        assert failed == []
        assert first.endswith(cut + hint) if save == "copied" else first.endswith(cut)  # HINT 一樣是最後一句
    else:
        assert failed == [f"瀏覽器打不開。{cut}把這串網址整個複製到瀏覽器的網址列：{calls[0]}"]
        assert cut not in first and first.endswith(hint if save == "copied" else "直接貼上。")
    assert_no_leak(view.logs)


# ── 四個入口：run、Api 的 start／go／open_forum、#menu（Task 8，設計第 5、9 節）──

MENU = "要做什麼？輸入 1 回報問題、2 提建議、3 問問題、4 看論壇"
ENV_LINE = "iPLoT 0.6.0・macOS 26.5（arm64）・Python 3.14.7"  # short_env 的樣子：直接建 Api 的測試用


class ModulesCore(FakeCore):
    """FakeCore，all_modules()（也就是 app.modules）回給定的 ModuleInfo：面板目前範圍內的模組。"""

    def __init__(self, home, config, view, modules):
        super().__init__(home, config, view)
        self.modules = tuple(modules)

    def all_modules(self):
        return self.modules


def science(home):
    """照 child_tree 建：「科學計算」（最上層，level "here"）與它底下的學生作業「王小明_B11201234」（下一層模組，
    level "child"）；回兩個的 ModuleInfo。"""
    root = (home / "modules").resolve()
    child = child_tree(home)
    return module_info(home / "modules" / "科學計算", root, "here"), module_info(child, root, "child")


def start_api(load, tmp_path, monkeypatch):
    """照 run 的樣子建 Api：rep 是沒指定模組的那一份，starts 只有「科學計算」。回 (api, 「科學計算」的資料夾)。"""
    report = load("report")
    home = tmp_path / "iPLoT"
    top, child = science(home)
    app = App(ModulesCore(home, DEFAULT_CONFIG, FakeView(), (top, child)), copied(home))
    api, _ = make_api(load, tmp_path, monkeypatch, report.blank(app, "BUG"), "回報",
                      starts={"科學計算": report.blank(app, "BUG", "科學計算")}, short_env=report.short_env(app))
    return api, top.folder


def test_run_opens_the_menu_page(load, tmp_path, web, opened):
    home = tmp_path / "iPLoT"
    view = View()
    result, _ = press(home, view, "run")
    assert result.ok, result.error
    pages = [e for e in view.events if e[0] == "page-open"]
    assert len(pages) == 1 and pages[0][1] == "回報與討論"
    data = page_data(pages[0][2])
    assert data["mode"] == "menu" and data["modules"] == [] and data["short_env"].startswith("iPLoT ")
    assert data["hint"] == load("report").HINT  # 換到預覽那一段才顯示（page.html 的 show），字一樣從資料來
    assert [e[0] for e in view.events] == ["page-open", "page-closed"]  # 沒送：不寫訊息區、不指檔案
    assert opened == []


@pytest.mark.parametrize("twice", [False, True])
def test_menu_lists_only_top_level_modules(tmp_path, web, twice):
    # 下一層模組的名字是學生的名字與學號（D95）：不列進清單，run 給 Api 的 starts 裡也沒有。
    # twice：另一個根底下也有一個最上層的「科學計算」（config 的 ROOTS 多一個資料夾）：選單裡只列一次
    home = tmp_path / "iPLoT"
    bodies = []
    modules = science(home)
    if twice:
        other = tmp_path / "另一個根"
        modules += (module_info(make_module(other, "科學計算"), other.resolve(), "extra"),)

    def hook(html, api):
        bodies.extend([api.start("科學計算")["body"], api.start("王小明_B11201234")["body"]])

    view = View(hook=hook)
    result, _ = press(home, view, "run", core=ModulesCore(home, DEFAULT_CONFIG, view, modules))
    assert result.ok, result.error
    html = view.events[0][2]
    assert page_data(html)["modules"] == ["科學計算"]
    assert "王小明" not in html and "B11201234" not in html
    named, child = bodies
    assert "- 模組：科學計算 " in named
    assert "- 模組：" not in child and "王小明" not in child


def test_run_reveals_the_saved_file_after_the_page_closes(tmp_path, web, opened):
    # 跟 on_error 一樣：頁面那一頭不叫 app；截過的檔等頁面關掉、回到 run 才指給人看
    home = tmp_path / "iPLoT"

    def hook(html, api):
        r = api.start()
        assert api.send(r["title"], f"{r['body']}\n{long_tb(300)}")["cut"]

    view = View(hook=hook)
    result, _ = press(home, view, "run")
    assert result.ok, result.error
    assert [e[0] for e in view.events] == ["page-open", "page-closed", "action"]
    action = view.events[2]
    assert action[:2] == ("action", "reveal") and action[2].name.endswith("-回報.txt")
    assert action[2].parent == (home / "modules" / "回報與討論" / "回報").resolve()
    assert len(opened) == 1


def test_api_start_returns_a_blank_report(load, tmp_path, monkeypatch, web):
    api, _ = start_api(load, tmp_path, monkeypatch)
    r = api.start()
    assert set(r) == {"title", "body", "notice"} and r["title"] == "[回報] "
    assert "### 錯誤" not in r["body"] and "- iPLoT：" in r["body"] and "- 模組：" not in r["body"]
    assert r["notice"].startswith(("已自動遮蔽", "沒有找到"))


def test_api_start_names_an_allowed_module(load, tmp_path, monkeypatch, opened, web):
    # 換成那一份之後，measure、send 都用它的 ctx：「科學計算」資料夾裡的路徑遮成 <模組:科學計算>/…
    report = load("report")
    api, top = start_api(load, tmp_path, monkeypatch)
    r = api.start("科學計算")
    assert "- 模組：科學計算 " in r["body"]
    mine = f"{r['body']}\n我的檔是 {top.resolve() / 'hk.py'}\n"
    assert "<模組:科學計算>/hk.py" in api.measure(r["title"], mine)["full"]
    sent = api.send(r["title"], mine)
    assert "<模組:科學計算>/hk.py" in query(opened[0])["body"] and sent["new_url"] == report.url("BUG", "", "")
    api.start()  # 換回沒指定模組的那一份：同一個路徑不再當成模組裡的
    assert "<模組:科學計算>" not in api.measure(r["title"], mine)["full"]


def test_api_start_refuses_other_names(load, tmp_path, monkeypatch, web):
    # 不在 starts 裡的（下一層模組的名字、沒有的名字、不是字串的）一律是沒指定模組的那一份；start 不另外去找
    api, _ = start_api(load, tmp_path, monkeypatch)
    blank = api.start("")
    for name in ("王小明_B11201234", "不存在", None, ["科學計算"]):
        api.start("科學計算")
        assert api.start(name) == blank, name
    assert "王小明" not in blank["body"] and "- 模組：" not in blank["body"]


@pytest.mark.parametrize("category", ["IDEA", "QA"])
def test_api_go_opens_the_category(load, tmp_path, monkeypatch, opened, category):
    forum = load("forum")
    api, saved = make_api(load, tmp_path, monkeypatch, sample_rep(load), "回報", starts={}, short_env=ENV_LINE)
    assert api.go(category) == {"ok": True, "url": ""}
    u, = opened
    assert u.startswith(forum.FORUM + "/new?")
    assert query(u) == {"category": forum.CATEGORIES[category], "title": "", "body": "\n\n---\n" + ENV_LINE}
    monkeypatch.setattr(webbrowser, "open", lambda u, *a, **k: False)  # 開不成：網址交給頁面，讓人自己複製
    assert api.go(category) == {"ok": False, "url": u}
    assert saved == [] and not (tmp_path / "回報").exists()  # 不存檔


def test_api_go_refuses_other_categories(load, tmp_path, monkeypatch, opened):
    # 公告（NEWS）是研究助理自己發的；回報問題（BUG）走 start 的預覽頁
    api, _ = make_api(load, tmp_path, monkeypatch, sample_rep(load), "回報", starts={}, short_env=ENV_LINE)
    for category in ("NEWS", "x", "BUG", None, ["IDEA"]):
        assert api.go(category)["ok"] is False, category
    assert opened == []


def test_api_open_forum(load, tmp_path, monkeypatch, opened):
    forum = load("forum")
    api, _ = make_api(load, tmp_path, monkeypatch, sample_rep(load))
    assert api.open_forum() == {"ok": True, "url": ""} and opened == [forum.FORUM]

    def broken(u, *a, **k):
        raise webbrowser.Error("找不到瀏覽器")

    monkeypatch.setattr(webbrowser, "open", broken)
    assert api.open_forum() == {"ok": False, "url": forum.FORUM}  # 不丟例外


def test_menu_fills_the_edit_page_then_measures():
    # 「回報問題」：start 回來的標題、內文用 .value 放進去，不會觸發 input 事件——不自己量一次的話 #full 還是空的，
    # 按「在瀏覽器打開」複製出去的是空的。放進去之後才 measure（按鈕先變灰、最新的那一次回來才亮）
    page = PAGE.read_text(encoding="utf-8")
    tree = Tree(page)
    assert tree.ids["menu"][0] == "section" and tree.ids["edit"][0] == "section"
    for button, text in (("report", "回報問題"), ("idea", "提建議"), ("qa", "問問題"), ("forum", "看論壇")):
        tag, attrs, parents = tree.ids[button]
        assert tag == "button" and "disabled" in attrs and ("section", {"id": "menu"}) in parents, button
        assert f'id="{button}" type="button" disabled>{text}</button>' in page, button
    assert tree.ids["module"][0] == "select" and '<option value="">（不指定模組）</option>' in page
    assert 'createElement("option")' in page and ".textContent = name" in page  # 模組的名字當文字放
    assert page.count("show(data.mode);") == 1  # 一開始照 mode：menu 先顯示 #menu（show 見下一個測試）
    body = handler(page, "report")
    start = body.index('.start($("module").value)')
    then = body.index(".then(", start)
    title, text = body.index('$("title").value = r.title', then), body.index('$("body").value = r.body', then)
    shown = body.index('show("edit");', max(title, text))  # 放好了才藏 #menu、顯示 #edit
    assert then < title and then < text < shown < body.index("measure();", shown)


def test_page_shows_the_hint_only_with_the_preview():
    # 「完整報告已複製…」只在預覽那一段（#edit）看得到：#menu 上什麼都還沒複製，提建議、問問題、看論壇也從不複製
    # （控制者的裁定）。#hint 跟 #edit 在同一個地方、照同一個條件藏：一開始照 mode，「回報問題」換到 #edit 時一起出來
    page = PAGE.read_text(encoding="utf-8")
    script = page.split("<script>", 1)[1]
    sets = {k: re.findall(rf'\$\("{k}"\)\.hidden = ([^;\n]*);', script) for k in ("menu", "edit", "hint")}
    assert sets == {"menu": ['mode !== "menu"'], "edit": ['mode !== "edit"'], "hint": ['mode !== "edit"']}
    show = script.split("function show(mode) {", 1)[1].split("\n}", 1)[0]
    assert all(f'$("{k}").hidden = ' in show for k in sets)  # 三個都只在 show 裡設
    assert script.count("show(data.mode);") == 1 and script.count('show("edit");') == 1
    assert 'show("edit");' in handler(page, "report")


@pytest.mark.parametrize("answer, want", [("1", "edit"), ("2", "IDEA"), ("3", "QA"), ("4", "forum"), (None, None),
                                          ("x", "log"), ("1 ", "log"), (" 4", "log")])  # 只認剛好 "1"–"4"（工作單）
def test_run_in_tk_asks_first(load, tmp_path, tk, opened, answer, want):
    # 後備的 tkinter 面板沒有頁面：問一次（設計第 9 節）。「1」走跟「回報這個問題」一樣的草稿檔
    home = tmp_path / "iPLoT"
    view = View()
    view.answer = answer
    view.answers = [False]  # 「1」：草稿那一步按「取消」，不送
    result, _ = press(home, view, "run")
    assert result.ok, result.error
    forum = load("forum")  # run_module 跑完才匯：不然模組匯到的是 repo 那一份
    assert view.asks == [MENU]
    assert not [e for e in view.events if e[0] in ("page", "page-open")]
    edits = [e[2] for e in view.events if e[:2] == ("action", "edit")]
    if want == "edit":
        draft, = edits
        assert draft.parent == (home / "modules" / "回報與討論" / "回報").resolve() and draft.name.endswith("-回報.md")
        text = draft.read_text(encoding="utf-8")
        assert text.startswith("[回報] \n\n### 發生了什麼\n") and "- iPLoT：" in text and "### 錯誤" not in text
        assert view.logs[-1] == f"沒有送出；草稿留在 回報/{draft.name}"
    else:
        assert edits == []
    if want in ("IDEA", "QA"):
        u, = opened
        q = query(u)
        assert (q["category"], q["title"]) == (forum.CATEGORIES[want], "") and q["body"].startswith("\n\n---\niPLoT ")
    elif want == "forum":
        assert opened == [forum.FORUM]
    else:
        assert opened == []
    if want in ("IDEA", "QA", "forum"):
        assert view.logs == []
    elif want == "log":
        assert view.logs == ["請輸入 1 到 4"]
    elif want is None:
        assert view.events == [("ask", MENU)]  # 按了取消：什麼都不做


def test_run_in_tk_gives_the_url_when_the_browser_fails(load, tmp_path, tk, monkeypatch):
    # 找不到瀏覽器不變成這個模組的錯誤：網址寫在訊息區，讓人自己複製
    def broken(u, *a, **k):
        raise webbrowser.Error("找不到瀏覽器")

    monkeypatch.setattr(webbrowser, "open", broken)
    home = tmp_path / "iPLoT"
    view = View()
    view.answer = "4"
    result, _ = press(home, view, "run")
    assert result.ok, result.error
    assert view.logs == [f"瀏覽器打不開。把這串網址整個複製到瀏覽器的網址列：{load('forum').FORUM}"]


@pytest.mark.parametrize("how", ["deleted", "big5"])
def test_run_in_tk_unreadable_draft_is_one_sentence(tmp_path, tk, opened, how):
    # 選單的「1」重用 _by_file：讀不回草稿的那一句跟「回報這個問題」那條路一樣，不叫人去按這條路上沒有的鈕
    names = []
    home = tmp_path / "iPLoT"
    view = View(on_confirm=spoiler(how, names))
    view.answer, view.answers = "1", [True]
    result, _ = press(home, view, "run")
    assert result.ok, result.error
    assert view.asks == [MENU] and names[0].endswith("-回報.md")
    assert_unreadable(view, home, how, names[0], tmp_path, opened)
