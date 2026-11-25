"""核心模組的啟動：開機程式（iPLoT 資料夾的 main.py，1.0 起凍結，D167）找到這一份核心之後交給 run(home, kernel)。
python3 main.py [--safe | --run <模組> [檔案…]]：選面板 → 進入事件迴圈（規格 §3）。Python 夠不夠新，開機程式已經看過了。

預設開網頁面板（提供 main 的模組，隨附的是 modules/主控面板/，用 lib/ 裡的 pywebview，D162）。第一次啟動、或 lib/ 壞了，就用 pip 裝一次再重啟自己；
裝不起來就退到 tkinter 面板（ui/tk.py，照常掃上一層與 ROOTS）並說明原因。--safe：直接開 tkinter 面板，只掃 modules/。
--run：不開面板，在面板外跑一個模組（ui/cli.py，D163）。

開機程式先叫 ready()：這一份核心的每一塊都載得起來才用它，載不起來就換下一份（上一次開得起來的那一份、包裡帶的種子）。
開得起來的這一份記成 .local/核心.good（remember），下次 modules/核心/ 被改壞了還有它。"""

from __future__ import annotations

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
    from ui import errlog

    try:
        return "\n".join(bundled.sync(home, version)) or None
    except Exception as exc:  # noqa: BLE001  這一步不能讓 iPLoT 開不起來；細節進 logs/iplot.log
        errlog.log(home, exc)
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


def ready() -> None:
    """開機程式問：這一份核心的每一塊都載得起來嗎？載不起來就丟（語法錯、少了檔案），開機程式換下一份。"""
    import importlib

    for name in ("core.core", "core.app", "core.worker", "core.bundled", "ui.cli", "ui.install", "ui.errlog", "ui.menu"):
        importlib.import_module(name)


def remember(home: Path, kernel: Path) -> None:
    """平常用的那一份核心（kernel）開得起來：跟上一次記的不一樣就整份存成它的 .local/<名字>.good/（D167），先寫暫存再換上去。
    用的是 .good（在 .local 裡）或種子（iPLoT 資料夾本身）的時候不存；存不了不擋啟動。"""
    import hashlib
    import shutil

    here = kernel
    if here == home or here.parent.name == ".local":
        return
    good, tmp = here / ".local" / f"{here.name}.good", here / ".local" / f"{here.name}.good.tmp"
    parts = [p for p in sorted(here.rglob("*.py")) + sorted(here.rglob("*.json"))
             if p.is_file() and ".local" not in p.relative_to(here).parts and "__pycache__" not in p.parts]
    digest = hashlib.sha256(b"".join(p.relative_to(here).as_posix().encode() + p.read_bytes() for p in parts)).hexdigest()
    try:
        if (good / ".digest").read_text(encoding="utf-8") == digest:
            return
    except OSError:
        pass
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        for p in parts:
            (tmp / p.relative_to(here)).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, tmp / p.relative_to(here))
        (tmp / ".digest").write_text(digest, encoding="utf-8")
        shutil.rmtree(good, ignore_errors=True)
        tmp.rename(good)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)


def main(home: Path, kernel: Path) -> None:
    """啟動 iPLoT。--safe：開 tkinter 面板，只掃 modules/。kernel 是開機程式選的那一份核心。"""
    from core import __version__
    from core.core import load_config
    from ui import errlog

    errlog.install(home)  # 沒接住的例外也寫進 logs/iplot.log（D150）
    sys.path.insert(1, str(home / "lib"))  # iPLoT 自己裝的套件：排在程式自己的資料夾後面、系統的套件前面
    rebooted = os.environ.pop("IPLOT_BOOT", None) == "1"  # 這次啟動是不是剛裝完 lib/ 重啟的那一次
    config, err = load_config(home / "config.py")
    news = bundle_news(home, __version__)
    remember(home, kernel)
    if sys.argv[1:2] == ["--run"]:  # 在面板外跑一個模組（D163）：不開面板
        from ui import cli

        print(news or "", end="\n" if news else "", flush=True)
        sys.exit(cli.run(home, config, err, sys.argv[2:]))
    if "--safe" in sys.argv[1:]:
        return tk_or_exit(home, config, err, True, news)
    try:
        run_web(home, config, err, "\n".join(filter(None, [news, refresh(home, config)])) or None)
    except ImportError as exc:
        bootstrap(home, config, err, str(exc), rebooted)


def run(home: Path, kernel: Path) -> None:
    """啟動；途中沒預料到的例外不把 traceback 丟到使用者眼前：寫進 logs/iplot.log，終端機只說一句（體驗 1-02）。"""
    try:
        main(Path(home), Path(kernel))
    except Exception as exc:  # noqa: BLE001  最外層：使用者看到的是一句話，細節在記錄檔
        import time
        import traceback

        logs = Path(home) / "logs"
        try:
            logs.mkdir(exist_ok=True)
            with (logs / "iplot.log").open("a", encoding="utf-8", errors="replace") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{''.join(traceback.format_exception(exc))}\n")
        except (OSError, ValueError):
            pass  # 記錄寫不了就算了：不能讓說明這一句也出不來
        print(T["start_failed"], flush=True)
        sys.exit(1)

