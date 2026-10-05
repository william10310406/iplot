"""第一次啟動的安裝（D62）：用 pip 把 requirements/ 裡釘死版本的套件裝進 iPLoT 自己的 lib/，
不碰系統的 Python。裝哪一份、缺什麼前置條件，問 modules/作業系統；pip 本身不分作業系統。"""

import hashlib
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.core import Core
from core.errors import describe
from core.types import ErrorInfo, Scope


class ConsoleView:
    """印到主控台的最小 View：安裝時視窗還沒開，Core 要說的話（例如作業系統模組不在、壞了）印在這裡。"""

    def show(self, scope: Scope) -> None:
        """沒有畫面可畫。"""

    def log(self, text: str) -> None:
        print(text, flush=True)

    def report(self, error: ErrorInfo) -> None:
        print(describe(error), flush=True)

    def ask(self, prompt: str, default: str = "") -> str | None:
        return None

    def confirm(self, prompt: str) -> bool:
        return False

    def page(self, title: str, html: str, api: object | None) -> None:
        """沒有畫面。"""

    def choose_files(self) -> list[Path]:
        return []

    def choose_folder(self) -> Path | None:
        return None


def requirements_file(home: Path, core: Core) -> Path | None:
    """要裝哪一份需求檔：作業系統模組回檔名。模組不在、壞了，或這個平台沒有網頁面板（回空字串）時回 None。"""
    name = core.action("requirements")
    return home / "requirements" / name if name else None


def ready(core: Core) -> str | None:
    """缺前置條件時回一句原因（例如 Windows 沒有 WebView2 runtime）；可以裝就回 None。"""
    return core.action("webview_ready")


def _digest(req: Path) -> str:
    return hashlib.sha256(req.read_bytes()).hexdigest()


def installed(home: Path, req: Path) -> bool:
    """lib/.installed 記的是不是目前這一份需求檔（內容的 sha256）；需求檔換了就要重裝。"""
    try:
        return (home / "lib" / ".installed").read_text(encoding="utf-8") == _digest(req)
    except OSError:
        return False


def stale(home: Path) -> bool:
    """lib/ 是照別的需求檔裝的：lib/.installed 記的 sha256 對不上 requirements/ 裡任何一份（「更新」換過需求檔）。
    沒裝過（沒有記號）不算過期，那是第一次安裝的事。"""
    try:
        marker = (home / "lib" / ".installed").read_text(encoding="utf-8")
        return marker not in {_digest(f) for f in (home / "requirements").glob("*.txt")}
    except OSError:
        return False


def install(home: Path, req: Path, say: Callable[[str], None], popen: Any = subprocess.Popen,
            quick: bool = False) -> str | None:
    """用 pip 把 req 裝進 home/lib，pip 的輸出一行行交給 say。quick：連不上就馬上放棄，不重試。
    成功就寫下 lib/.installed、回 None；失敗回 pip 說的原因：最後五行裡 ERROR 開頭的那幾行，沒有就整五行。
    指令是列表，不經過 shell。"""
    lib = home / "lib"
    argv = [sys.executable, "-m", "pip", "install", "--target", str(lib), "--upgrade", "--no-input",
            "--disable-pip-version-check", *(("--retries", "0", "--timeout", "8") if quick else ()), "-r", str(req)]
    proc = popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    tail: list[str] = []
    for line in proc.stdout:
        say(line.rstrip("\n"))
        tail = [*tail, line.rstrip("\n")][-5:]
    if proc.wait() != 0:
        return "\n".join([line for line in tail if line.startswith("ERROR")] or tail)
    lib.mkdir(exist_ok=True)
    (lib / ".installed").write_text(_digest(req), encoding="utf-8")
    return None
