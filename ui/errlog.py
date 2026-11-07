"""兩個面板共用的錯誤紀錄（D150）：最近的訊息、最近一次的錯誤（logs/last-error.json）、自動問「要回報嗎？」的節流，
與 main.py 裝的全域例外處理。只寫 iPLoT 自己的 logs/，寫不了就算了：記錄出錯不能讓面板跟著出錯。

logs/last-error.json 是給「回報與討論」讀的（docs/07 第 13 節）：沒遮過，只放在這台電腦（logs/ 不進 git、不進包）。"""

import contextlib
import dataclasses
import json
import sys
import threading
import time
import unicodedata
from collections import deque
from collections.abc import Callable
from pathlib import Path

from core.errors import describe
from core.text import REPORT_MODULE
from core.types import ErrorInfo

RECENT = 40          # 最近的訊息留幾行
WINDOW = 600.0       # 同一種錯誤（類型、檔案、行號）幾秒內只問一次


class Recent:
    """訊息區最近的 RECENT 行（面板的 log 與 report 各記一行）。"""

    def __init__(self) -> None:
        self._lines: deque[str] = deque(maxlen=RECENT)

    def add(self, text: str) -> None:
        self._lines.extend(str(text).splitlines() or [""])

    def lines(self) -> list[str]:
        return list(self._lines)


def student_homework(error: ErrorInfo) -> bool:
    """出錯的位置是不是「科學計算」收進來的學生作業檔（D150 修訂）。學生的程式出錯是常態、不是 iPLoT 的 bug，
    不自動問、也不當成「最近一次的錯誤」（免得被附進公開的回報）；那一列的「回報這個問題」照樣能按。
    科學計算只有新格式的學生作業在面板的程序裡跑（舊格式的 HKn.txt 一律是另開的程序，錯誤進不了面板）：
    收作業把它放成 <課程>/<HKn>/<學生>/iplot.py，旁邊是殼 hk_page.py、沒有 t2026fscSpace/，課程資料夾有 hk_tk.py。
    照 modules/科學計算/hk_tk.py 的 course_root、_is_new_folder、_is_student 判斷資料夾的樣子，不看名字猜；
    出錯的位置是 error.file（traceback 裡、正在跑的模組資料夾裡最內層的那一格），正在跑的模組就是那個學生資料夾。
    殼（hk_page.py）裡出的錯照常問：那是 iPLoT 這邊的程式。"""
    if error.source != "module" or error.file is None or error.module is None:
        return False
    file = Path(error.file)
    student = file.parent
    hk, course = student.parent, student.parent.parent
    try:
        return (file.name == "iplot.py" and file.is_file()
                and unicodedata.normalize("NFC", student.name) == unicodedata.normalize("NFC", error.module)
                and student.is_dir() and not student.is_symlink() and (student / "hk_page.py").is_file()
                and not (student / "t2026fscSpace").is_dir() and (course / "hk_tk.py").is_file()
                and not (student / "hk_tk.py").exists() and not (hk / "hk_tk.py").exists())
    except OSError:
        return False


def write(home: Path, error: ErrorInfo, recent: list[str]) -> None:
    """把這一筆錯誤與那時候最近的訊息寫進 logs/last-error.json（整份換掉）。「回報與討論」自己的錯誤不寫：
    它壞了的時候，不能把人原本要回報的那一筆蓋掉。學生作業的錯誤也不寫（student_homework）。
    寫不了（唯讀、磁碟滿了、孤立的代理字元）就算了。"""
    if error.module == REPORT_MODULE or student_homework(error):
        return
    data = {**dataclasses.asdict(error), "file": None if error.file is None else str(error.file),
            "sentence": describe(error), "time": time.strftime("%Y-%m-%d %H:%M:%S"), "recent": recent}
    with contextlib.suppress(OSError, ValueError):
        (home / "logs").mkdir(exist_ok=True)
        text = json.dumps(data, ensure_ascii=False, indent=1)
        temp = home / "logs" / "last-error.json.tmp"
        temp.write_text(text, encoding="utf-8", errors="surrogateescape")
        temp.replace(home / "logs" / "last-error.json")


class Offer:
    """自動跳出「出錯了，要回報嗎？」該不該問：同一種錯誤 WINDOW 秒內只問一次；勾了「這次執行期間不要再問」
    （muted）之後都不問。config.py 的錯誤（自己改壞的設定）、「回報與討論」自己的錯誤、學生作業的錯誤
    （student_homework）不問。只記在記憶體。"""

    def __init__(self, window: float = WINDOW, clock: Callable[[], float] = time.monotonic) -> None:
        self._window, self._clock = window, clock
        self._asked: dict[tuple, float] = {}
        self.muted = False

    def due(self, error: ErrorInfo) -> bool:
        if self.muted or error.source == "config" or error.module == REPORT_MODULE or student_homework(error):
            return False
        key, now = (error.kind, str(error.file), error.line), self._clock()
        if now - self._asked.get(key, -self._window) < self._window:
            return False
        self._asked[key] = now
        return True


# 面板開著時，別的執行緒沒接住的例外交給它（網頁面板設；tkinter 不能從別的執行緒碰，不設）
sink: Callable[[BaseException], None] | None = None


def install(home: Path) -> None:
    """全域的例外處理：主執行緒與其他執行緒沒接住的例外，照樣印在終端機，也寫進 logs/iplot.log；
    網頁面板開著的話，別的執行緒的再交給 sink 進面板。"""
    default, thread_default = sys.excepthook, threading.excepthook

    def log(exc: BaseException) -> None:
        import traceback

        with contextlib.suppress(OSError, ValueError):
            (home / "logs").mkdir(exist_ok=True)
            with (home / "logs" / "iplot.log").open("a", encoding="utf-8", errors="replace") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{''.join(traceback.format_exception(exc))}\n")

    def main_hook(kind, exc, tb):
        log(exc)
        default(kind, exc, tb)

    def thread_hook(args):
        if args.exc_value is not None and not isinstance(args.exc_value, SystemExit):
            log(args.exc_value)
            if sink is not None:  # 只是排進面板的工作佇列，不會在這裡出錯
                sink(args.exc_value)
        thread_default(args)

    sys.excepthook, threading.excepthook = main_hook, thread_hook
