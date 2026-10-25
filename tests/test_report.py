"""隨附模組「回報與討論」（modules/回報與討論）：遮蔽、內文、網址、截斷、預覽頁與面板的流程（M8、D110–D116）。
不開瀏覽器（autouse 的替身）、不連網、不寫進 repo（跑模組的流程先複製到 tmp）；遮蔽的表用假的 Ctx，只有端對端的兩個用這台機器。"""

import getpass
import importlib
import itertools
import os
import re
import sys
import types
import webbrowser
from pathlib import Path

import pytest
from conftest import FakeApp, make_module

from core.runner import run_module
from core.scan import module_info

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
