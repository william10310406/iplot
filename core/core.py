"""組裝與編排：持有設定、畫面與記憶，把面板上的動作接到底層的檔案。"""

import contextlib
import runpy
import time
import unicodedata
from pathlib import Path
from typing import Any, Protocol

from . import actions, history, runner, scan
from .app import App
from .create import AlreadyExists, BadName, new_module
from .errors import from_exception
from .text import T
from .types import DEFAULT_CONFIG, Config, ErrorInfo, Group, ModuleInfo, Result, Root, Scope


class View(Protocol):
    """面板要做到的事：ui.Panel 實作，測試用 FakeView。"""

    window: Any

    def show(self, scope: Scope) -> None: ...
    def log(self, text: str) -> None: ...
    def report(self, error: ErrorInfo) -> None: ...
    def ask(self, prompt: str, default: str = "") -> str | None: ...
    def choose_files(self) -> list[Path]: ...
    def choose_folder(self) -> Path | None: ...


def _strs(value: object) -> bool:
    return isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value)


def load_config(path: Path) -> tuple[Config, ErrorInfo | None]:
    """執行 config.py 取出設定，缺的用預設值補；壞了或型別不對就整份用預設值，並回報錯在哪。"""
    if not path.exists():
        return DEFAULT_CONFIG, None
    try:
        ns = runpy.run_path(str(path))
    except (Exception, SystemExit) as exc:  # noqa: BLE001  規格 §7 允許的兩處之一
        return DEFAULT_CONFIG, from_exception(exc, None, "config")
    d = DEFAULT_CONFIG
    roots, editor = ns.get("ROOTS", d.roots), ns.get("EDITOR", d.editor)
    keep = ns.get("HISTORY_KEEP", d.history_keep)
    for name, ok, expected in [("ROOTS", _strs(roots), "list[str]"),
                               ("EDITOR", editor is None or _strs(editor), "None | list[str]"),
                               ("HISTORY_KEEP", type(keep) is int and keep >= 1, "int >= 1")]:
        if not ok:
            message = T["config_type"].format(name=name, expected=expected)
            return d, ErrorInfo("TypeError", message, path, None, "", "config", None)
    for s in roots:
        try:
            Path(s).expanduser()
        except RuntimeError:  # 「~Desktop」：少了斜線，pathlib 會在掃描時丟例外，這裡先攔下來
            return d, ErrorInfo("ValueError", T["bad_root"].format(entry=s), path, None, "", "config", None)
    return Config(tuple(roots), None if editor is None else tuple(editor), keep), None


class Core:
    """iPLoT 的編排：重掃、進入／返回、按下、依名稱執行、新增、回報核心錯誤。"""

    def __init__(self, home: Path, config: Config, view: View, safe: bool = False) -> None:
        self.home, self.config, self.view, self.safe = home, config, view, safe
        self.scope = Scope(("iPLoT",), ())
        self.memories: dict[Path, dict] = {}
        self._stack: list[ModuleInfo] = []
        self._depth, self._pending = 0, False

    def roots(self) -> list[Root]:
        """要掃的根目錄；安全模式只掃 modules。"""
        return scan.roots_from_config(self.home, ("modules",) if self.safe else self.config.roots)

    def rescan(self) -> None:
        """重掃目前範圍並重畫；模組執行中只先記著，等執行結束才做。"""
        if self._depth:
            self._pending = True
            return
        gone = [i for i, m in enumerate(self._stack) if not scan.is_module(m.folder)]
        del self._stack[gone[0] if gone else len(self._stack):]
        if self._stack:
            top = self._stack[-1]
            kids = tuple(scan.find_children(top.folder, top.root))
            groups = (Group(top.title, self._stack[0].level, top.folder, kids),)
        else:
            groups = tuple(scan.find_modules(self.roots()))
        self.scope = Scope(("iPLoT", *(m.title for m in self._stack)), groups)
        self.view.show(self.scope)

    def enter(self, info: ModuleInfo) -> None:
        """進入下一層，顯示 info 底下的模組。"""
        self._stack.append(info)
        self.rescan()

    def back(self, depth: int) -> None:
        """麵包屑回上；depth 0 是頂層。"""
        del self._stack[depth:]
        self.rescan()

    def all_modules(self) -> tuple[ModuleInfo, ...]:
        """目前範圍內的所有模組。"""
        return tuple(m for g in self.scope.groups for m in g.modules)

    def press(self, info: ModuleInfo, handler: str = "run", args: tuple = ()) -> Result:
        """執行模組：先存快照再交給 runner，結果寫進訊息區；執行中收到的重掃延到結束才做。"""
        self._depth += 1
        try:
            try:
                history.snapshot(info.file, self.config.history_keep)
            except OSError as exc:
                self.view.log(T["snapshot_failed"].format(message=exc))
            result = runner.run_module(info, App(self, info), handler, args)
            for line in result.output.splitlines():
                self.view.log(line)
            if result.error:
                self.view.report(result.error)
            else:
                self.view.log(T["done"].format(title=info.title, seconds=result.duration))
            return result
        finally:
            self._depth -= 1
            if not self._depth and self._pending:
                self._pending = False
                self.rescan()

    def run_by_name(self, name: str | ModuleInfo) -> Result:
        """依資料夾名稱執行目前範圍內的模組（先 NFC 正規化）；找不到或不只一個就丟 LookupError。"""
        if isinstance(name, str):
            name = unicodedata.normalize("NFC", name)
            found = [m for m in self.all_modules() if m.name == name]
            if len(found) != 1:
                paths = "\n".join(str(m.folder) for m in found)
                raise LookupError(T["ambiguous" if found else "not_found"].format(name=name, paths=paths))
            name = found[0]
        return self.press(name)

    def create(self, parent: Path, name: str) -> Path | None:
        """新增模組：建好後重掃並打開編輯器；名稱不對、已存在或建不了時寫進訊息區、回 None。"""
        try:
            folder = new_module(parent, name)
        except BadName:
            return self.view.log(T["bad_name"])
        except AlreadyExists:
            return self.view.log(T["already_exists"].format(name=name))
        except OSError as exc:
            return self.view.log(T["create_failed"].format(path=parent, message=exc))
        self.rescan()
        actions.edit(folder / "iplot.py", self.config.editor)
        return folder

    def report_internal(self, exc_type: type, exc: BaseException, tb: Any) -> None:
        """核心自己的錯誤（tkinter 回呼裡丟出來的）：寫進 logs/iplot.log，再進面板。記錄檔寫不了就只進面板。"""
        error = from_exception(exc, None, "core")
        with contextlib.suppress(OSError):
            (self.home / "logs").mkdir(exist_ok=True)
            with (self.home / "logs" / "iplot.log").open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{error.traceback_text}\n")
        self.view.report(error)
