"""iPLoT 入口：python3 main.py [--safe]。版本檢查 → 選面板 → 進入事件迴圈（規格 §3）。

預設開網頁面板（ui/web.py，用 lib/ 裡的 pywebview）。第一次啟動、或 lib/ 壞了，就用 pip 裝一次再重啟自己；
裝不起來就退到 tkinter 面板（ui/tk.py，照常掃上一層與 ROOTS）並說明原因。--safe：直接開 tkinter 面板，只掃 modules/。

core 與 ui 的 import 都放在函式裡、版本檢查之後：它們用了 3.10 的語法，在太舊的 Python 上一 import 就炸，
使用者得先看到「請裝新版 Python」那一句，而不是一段 traceback。
檢查之前只 import core.text（它和 core/__init__.py 必須在舊版也 import 得起來，見 D46）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from core.text import T

if TYPE_CHECKING:
    from core.types import Config, ErrorInfo

INSTALL_SIZE = "40 MB"  # 第一次啟動要下載多少，給人看的概數（macOS 實測裝完 36 MB）


class NoTk:
    """網頁面板開著的期間擋住 import tkinter（turtle 也會 import 它）。主執行緒被網頁面板的視窗系統佔著，
    模組在別的執行緒上一開 tkinter 視窗，整個程序就被作業系統中止，連一句錯誤都來不及說（macOS 實測）；
    擋在 import 這一步，它就只是一個一般的模組錯誤，訊息說怎麼辦。排在 sys.meta_path 最前面。"""

    def find_spec(self, name, path=None, target=None):
        if name in ("tkinter", "_tkinter"):
            raise ImportError(T["tk_in_web"])


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


def run_web(home: Path, config: Config, err: ErrorInfo | None, version: str) -> None:
    """網頁面板：視窗關掉才回傳。lib/ 裡沒有 pywebview、或它找不到能用的視窗套件（裝壞了）時丟 ImportError。"""
    from core.core import Core
    from ui.web import WebPanel

    panel = WebPanel(home, version, False)
    core = Core(home, config, panel)
    panel.attach(core)
    if err is not None:
        panel.submit(lambda: panel.report(err))  # 頁面就緒之後才送得出去，先排著
    guard = NoTk()
    sys.meta_path.insert(0, guard)
    try:
        panel.run()
    except panel.webview.WebViewException as exc:
        raise ImportError(str(exc)) from exc
    finally:
        sys.meta_path.remove(guard)  # 面板關了、或根本沒開起來：後備的 tkinter 面板在同一個程序裡，要 import 得到


def tk_or_exit(home: Path, config: Config, err: ErrorInfo | None, safe: bool, note: str | None = None) -> None:
    """開 tkinter 面板；連 tkinter 都沒有就說一句，以代碼 1 結束。"""
    try:
        run_tk(home, config, err, safe, note)
    except ImportError:
        print(T["no_tk"], flush=True)
        sys.exit(1)


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

    home = Path(__file__).resolve().parent
    sys.path.insert(1, str(home / "lib"))  # iPLoT 自己裝的套件：排在程式自己的資料夾後面、系統的套件前面
    rebooted = os.environ.pop("IPLOT_BOOT", None) == "1"  # 這次啟動是不是剛裝完 lib/ 重啟的那一次
    config, err = load_config(home / "config.py")
    if "--safe" in sys.argv[1:]:
        return tk_or_exit(home, config, err, True)
    try:
        run_web(home, config, err, __version__)
    except ImportError as exc:
        bootstrap(home, config, err, str(exc), rebooted)


if __name__ == "__main__":
    main()
