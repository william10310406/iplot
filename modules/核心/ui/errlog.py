"""後備的 tkinter 面板的錯誤紀錄（D150）：最近的訊息、自動問「要回報嗎？」的節流，與 main.py 裝的全域例外處理。
只寫 iPLoT 自己的 logs/，寫不了就算了：記錄出錯不能讓面板跟著出錯。哪些錯誤值得回報、logs/last-error.json 由提供
panel.error 的模組決定與寫（D162）。網頁面板（modules/主控面板/panel_web.py）有自己的一份 Recent、Offer。"""

import contextlib
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

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


class Offer:
    """自動跳出「出錯了，要回報嗎？」該不該問：同一種錯誤 WINDOW 秒內只問一次；勾了「這次執行期間不要再問」
    （muted）之後都不問。config.py 的錯誤（自己改壞的設定）、在 input() 的提問框按取消不問。哪些錯誤值得回報
    （例如學生作業不算）由 panel.error 的提供者決定，不在這裡。只記在記憶體。"""

    def __init__(self, window: float = WINDOW, clock: Callable[[], float] = time.monotonic) -> None:
        self._window, self._clock = window, clock
        self._asked: dict[tuple, float] = {}
        self.muted = False

    def due(self, error: ErrorInfo) -> bool:
        if self.muted or error.source == "config" or error.kind == "InputCancelled":
            return False
        key, now = (error.kind, str(error.file), error.line), self._clock()
        if now - self._asked.get(key, -self._window) < self._window:
            return False
        self._asked[key] = now
        return True


# 面板開著時，別的執行緒沒接住的例外交給它（網頁面板設；tkinter 不能從別的執行緒碰，不設）
sink: Callable[[BaseException], None] | None = None


def log(home: Path, exc: BaseException) -> None:
    """例外與 traceback 寫進 logs/iplot.log；寫不了就算了。"""
    import traceback

    with contextlib.suppress(OSError, ValueError):
        (home / "logs").mkdir(exist_ok=True)
        with (home / "logs" / "iplot.log").open("a", encoding="utf-8", errors="replace") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{''.join(traceback.format_exception(exc))}\n")


def install(home: Path) -> None:
    """全域的例外處理：主執行緒與其他執行緒沒接住的例外，照樣印在終端機，也寫進 logs/iplot.log；
    網頁面板開著的話，別的執行緒的再交給 sink 進面板。"""
    default, thread_default = sys.excepthook, threading.excepthook

    def main_hook(kind, exc, tb):
        log(home, exc)
        default(kind, exc, tb)

    def thread_hook(args):
        if args.exc_value is not None and not isinstance(args.exc_value, SystemExit):
            log(home, args.exc_value)
            if sink is not None:  # 只是排進面板的工作佇列，不會在這裡出錯
                sink(args.exc_value)
        thread_default(args)

    sys.excepthook, threading.excepthook = main_hook, thread_hook
