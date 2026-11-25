"""python3 main.py --run <模組> [檔案…]：在面板外跑一個模組（D163）。

目標是模組資料夾、它的 iplot.py，或最上層模組的名字；後面的參數是檔案（以目前的工作目錄為準），交給模組的 on_files，
沒有就執行 run。跟面板按下走同一條路：Core(separate=True) 每按一次另開工作程序（D161）。
有模組提供角色 run.outside（「互通」：彈出式視窗、跑完同步捷徑）就交給它，開不起來（沒有 pywebview）或沒有人提供，
就在終端機跑：輸出印出來，提問用 input() 回答。結束碼：0 跑完沒出錯；1 出錯、取消、找不到模組；2 開不起來。"""

from __future__ import annotations

import shlex
import unicodedata
from pathlib import Path

from core import scan
from core.core import Core
from core.errors import describe
from core.text import T
from core.types import Config, ErrorInfo, ModuleInfo
from ui import errlog
from ui.install import ConsoleView

OK, FAILED, CANNOT_START = 0, 1, 2
ROLE = "run.outside"


class TerminalView(ConsoleView):
    """在終端機跑：跟安裝時的 ConsoleView 一樣印出來，另外提問用 input() 回答（按 Ctrl-D 是取消）。"""

    def report(self, error: ErrorInfo) -> None:
        print(f"{error.traceback_text.rstrip()}\n{describe(error)}" if error.traceback_text else describe(error), flush=True)

    def ask(self, prompt: str, default: str = "") -> str | None:
        try:
            answer = input(f"{prompt}{f' [{default}]' if default else ''} ")
        except EOFError:
            return None
        return answer or default

    def confirm(self, prompt: str) -> bool:
        return (self.ask(prompt + T["cli_yes_no"]) or "").strip().lower() in ("y", "yes")

    def choose_files(self) -> list[Path]:
        return [Path(p) for p in shlex.split(self.ask(T["cli_files"]) or "")]

    def choose_folder(self) -> Path | None:
        answer = self.ask(T["cli_folder"])
        return Path(answer) if answer else None


def resolve(core: Core, target: str, cwd: Path) -> tuple[ModuleInfo | None, str | None]:
    """目標 → (ModuleInfo, None)，或 (None, 說明為什麼的那一句)。名字只找最上層（D83）。"""
    path = scan.home_path(target) or Path(target)
    path = path if path.is_absolute() else cwd / path
    if path.exists():
        folder = path.parent if path.is_file() and path.name == scan.MARKER else path
        if not scan.is_module(folder):
            return None, T["cli_not_module"].format(path=folder)
        folder = folder.resolve()
        for root in core.roots():  # 第一個包含它的根目錄；直接在根目錄底下是那一組，再下去是 child
            try:
                depth = len(folder.relative_to(root.path).parts)
            except ValueError:
                continue
            return scan.module_info(folder, root.path, root.level if depth == 1 else "child"), None
        return scan.module_info(folder, folder.parent, "extra"), None
    if "/" in target or target.startswith("~"):
        return None, T["cli_gone"].format(path=target)
    name = unicodedata.normalize("NFC", target)
    found = [m for m in core.all_modules() if m.name == name]
    if len(found) == 1:
        return found[0], None
    return None, T["ambiguous" if found else "not_found"].format(name=name, paths="\n".join(str(m.folder) for m in found))


def run(home: Path, config: Config, err: ErrorInfo | None, argv: list[str], cwd: Path | None = None) -> int:
    """跑一次，回結束碼。"""
    if not argv:
        print(T["cli_usage"], flush=True)
        return FAILED
    cwd = cwd or Path.cwd()
    core = Core(home, config, TerminalView(), separate=True)
    core.rescan()  # 在面板外一律是最上層
    info, problem = resolve(core, argv[0], cwd)
    files = [p if p.is_absolute() else cwd / p for p in (scan.home_path(a) or Path(a) for a in argv[1:])]
    if core.providers(ROLE):
        try:
            return core.call_here(ROLE, core, info, files, problem, err)
        except ImportError as exc:  # 它的視窗開不起來（多半是沒有 pywebview）：改在終端機跑
            errlog.log(home, exc)
            core.view = TerminalView()
            print(T["cli_window_failed"].format(message=exc), flush=True)
    if err is not None:
        core.view.report(err)
    if problem is not None:
        print(problem, flush=True)
        return FAILED
    result = core.press(info, "on_files", (files,), quiet=True) if files else core.press(info, quiet=True)
    return OK if result.ok else FAILED
