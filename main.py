"""iPLoT 入口：python3 main.py [--safe]。版本檢查 → 選面板 → 進入事件迴圈（規格 §3）。

預設開網頁面板（提供 main 的模組，隨附的是 modules/主控面板/，用 lib/ 裡的 pywebview，D162）。第一次啟動、或 lib/ 壞了，就用 pip 裝一次再重啟自己；
裝不起來就退到 tkinter 面板（ui/tk.py，照常掃上一層與 ROOTS）並說明原因。--safe：直接開 tkinter 面板，只掃 modules/。

core 與 ui 的 import 都放在函式裡、版本檢查之後：它們用了 3.10 的語法，在太舊的 Python 上一 import 就炸，
使用者得先看到「請裝新版 Python」那一句，而不是一段 traceback。
檢查之前只 import core.text（它和 core/__init__.py 必須在舊版也 import 得起來，見 D46）。"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from core.text import T

if TYPE_CHECKING:
    from core.types import Config, ErrorInfo

INSTALL_SIZE = "40 MB"  # 第一次啟動要下載多少，給人看的概數（macOS 實測裝完 36 MB）


def run_tk(home: Path, config: Config, err: ErrorInfo | None, safe: bool, note: str | None = None) -> None:
    """tkinter 面板：安全模式（safe，只掃 modules/），或網頁面板開不起來時的後備（掃完整範圍）。note 有值就先寫進訊息區。
    這個 Python 沒有 tkinter 時丟 ImportError。"""
    from core import __version__
    from core.core import Core
    from ui.tk import Panel

    panel = Panel(__version__, safe)
    core = Core(home, config, panel, safe)
    panel.attach(core)
    if note is not None:
        panel.log(note)
    if err is not None:
        panel.report(err)
    core.rescan()
    panel.mainloop()


def run_web(home: Path, config: Config, err: ErrorInfo | None, note: str | None = None) -> None:
    """網頁面板：交給提供 main 的模組（隨附的「主控面板」），在這個程序裡開，視窗關掉才回傳（D162）。
    每按一次另開一個程序跑模組（D161）。沒有提供者、或它開不起來（lib/ 裡沒有 pywebview、找不到能用的視窗套件）時
    丟 ImportError：開機程式去裝、或退到後備的 tkinter 面板。"""
    from core.core import Core
    from ui import errlog
    from ui.install import ConsoleView

    core = Core(home, config, ConsoleView(), separate=True)  # 面板開起來之前，核心要說的話印在終端機
    errlog.sink = lambda exc: core.report_internal(type(exc), exc, exc.__traceback__)
    try:
        if not core.providers("main"):
            return tk_or_exit(home, config, err, False, T["no_panel"])
        core.call_here("main", core, note, err)
    except ImportError:
        raise
    except Exception as exc:  # noqa: BLE001  面板是模組（D162）：它壞了不能讓 iPLoT 開不起來，退到後備面板
        errlog.log(home, exc)
        return tk_or_exit(home, config, err, False, T["panel_broken"].format(message=exc))
    finally:
        errlog.sink = None  # 面板關了：別的執行緒的例外只進終端機與 logs/iplot.log
    return None


def tk_or_exit(home: Path, config: Config, err: ErrorInfo | None, safe: bool, note: str | None = None) -> None:
    """開 tkinter 面板；連 tkinter 都沒有就說一句，以代碼 1 結束。"""
    try:
        run_tk(home, config, err, safe, note)
    except ImportError:
        print(T["no_tk"], flush=True)
        sys.exit(1)


def refresh(home: Path, config: Config) -> str | None:
    """「更新」換了 requirements/ 之後的第一次啟動：lib/ 是照舊的需求檔裝的，開面板之前先重裝。
    這時候還沒 import 任何 lib/ 的東西，裝好直接往下開，不用重啟。沒裝成（多半是沒有網路）就回那句說明：
    先用現有的 lib/ 開；lib/.installed 沒動，所以下次啟動會再試。沒事可做、或裝好了，回 None。"""
    from core.core import Core
    from ui import install

    if not install.stale(home):
        return None
    core = Core(home, config, install.ConsoleView())
    req = install.requirements_file(home, core)
    if req is None or install.ready(core) is not None:
        return None
    print(T["refreshing"], flush=True)
    failure = install.install(home, req, lambda line: print(line, flush=True), quick=True)
    if failure is None:
        return None
    print(T["refresh_failed"].format(message=failure), flush=True)
    return T["refresh_failed"].format(message=failure)


def bundle_news(home: Path, version: str) -> str | None:
    """「更新」之後的第一次啟動：隨附模組跟著換成這一版的（D156）。回要寫進訊息區的話；沒事、或出了意外都不擋啟動。"""
    from core import bundled

    try:
        return "\n".join(bundled.sync(home, version)) or None
    except Exception:  # noqa: BLE001  這一步不能讓 iPLoT 開不起來；細節進 logs/iplot.log
        import traceback

        with contextlib.suppress(OSError):
            (home / "logs").mkdir(exist_ok=True)
            with (home / "logs" / "iplot.log").open("a", encoding="utf-8", errors="replace") as f:
                f.write(f"{traceback.format_exc()}\n")
        return None


def bootstrap(home: Path, config: Config, err: ErrorInfo | None, reason: str, rebooted: bool) -> None:
    """網頁面板開不起來（reason）：用 pip 把介面裝進 lib/，裝好就重啟自己（乾淨的程序）。
    這個平台裝不了、pip 失敗、或剛裝完重啟還是開不起來（rebooted），就說明原因、退到 tkinter 面板（不是安全模式）。
    裝哪一份、缺什麼，問 modules/作業系統（ui/install.py）。只重裝一次，不會無限重啟。"""
    from core.core import Core
    from ui import install

    message = T["web_failed"].format(message=reason)
    if not rebooted:
        core = Core(home, config, install.ConsoleView())
        req, problem = install.requirements_file(home, core), install.ready(core)
        if req is None or problem is not None:
            message = T["web_failed"].format(message=problem or reason)
        else:
            (home / "lib" / ".installed").unlink(missing_ok=True)  # 這次沒裝完的話，下次啟動還會再裝
            print(T["installing"].format(size=INSTALL_SIZE), flush=True)
            failure = install.install(home, req, lambda line: print(line, flush=True))
            if failure is None:
                print(T["install_done"], flush=True)
                os.environ["IPLOT_BOOT"] = "1"
                os.execv(sys.executable, [sys.executable, str(home / "main.py"), *sys.argv[1:]])
            message = T["install_failed"].format(message=failure)
    print(message, flush=True)
    tk_or_exit(home, config, err, False, message)  # 後備面板不是安全模式：照常掃上一層與 ROOTS


def main() -> None:
    """啟動 iPLoT。--safe：開 tkinter 面板，只掃 modules/。"""
    found = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info < (3, 10):  # noqa: UP036  這一行就是要在 3.10 以下的直譯器上跑
        sys.exit(T["need_python"].format(found=found))
    from core import __version__
    from core.core import load_config
    from ui import errlog

    home = Path(__file__).resolve().parent
    errlog.install(home)  # 沒接住的例外也寫進 logs/iplot.log（D150）
    sys.path.insert(1, str(home / "lib"))  # iPLoT 自己裝的套件：排在程式自己的資料夾後面、系統的套件前面
    rebooted = os.environ.pop("IPLOT_BOOT", None) == "1"  # 這次啟動是不是剛裝完 lib/ 重啟的那一次
    config, err = load_config(home / "config.py")
    news = bundle_news(home, __version__)
    if "--safe" in sys.argv[1:]:
        return tk_or_exit(home, config, err, True, news)
    try:
        run_web(home, config, err, "\n".join(filter(None, [news, refresh(home, config)])) or None)
    except ImportError as exc:
        bootstrap(home, config, err, str(exc), rebooted)


def run() -> None:
    """啟動；途中沒預料到的例外不把 traceback 丟到使用者眼前：寫進 logs/iplot.log，終端機只說一句（體驗 1-02）。"""
    try:
        main()
    except Exception as exc:  # noqa: BLE001  最外層：使用者看到的是一句話，細節在記錄檔
        import time
        import traceback

        logs = Path(__file__).resolve().parent / "logs"
        try:
            logs.mkdir(exist_ok=True)
            with (logs / "iplot.log").open("a", encoding="utf-8", errors="replace") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{''.join(traceback.format_exception(exc))}\n")
        except (OSError, ValueError):
            pass  # 記錄寫不了就算了：不能讓說明這一句也出不來
        print(T["start_failed"], flush=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
