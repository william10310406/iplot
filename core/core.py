"""組裝與編排：持有設定、畫面與記憶，把面板上的動作接到底層的檔案。"""

import contextlib
import importlib.util
import json
import runpy
import sys
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any, Protocol

from . import history, runner, scan
from .app import App
from .create import AlreadyExists, BadName, new_module
from .errors import describe, from_exception, reason
from .text import T
from .types import DEFAULT_CONFIG, Config, ErrorInfo, Group, ModuleInfo, Result, Root, Scope


class View(Protocol):
    """面板要做到的事：ui/ 裡的面板實作，測試用 FakeView。"""

    def show(self, scope: Scope) -> None: ...
    def log(self, text: str) -> None: ...
    def report(self, error: ErrorInfo) -> None: ...
    def ask(self, prompt: str, default: str = "") -> str | None: ...
    def confirm(self, prompt: str) -> bool: ...
    def page(self, title: str, html: str, api: object | None) -> None: ...
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
    except (Exception, SystemExit) as exc:  # noqa: BLE001  規格 §11 允許的三處之一
        return DEFAULT_CONFIG, from_exception(exc, None, "config")
    d, get = DEFAULT_CONFIG, ns.get
    roots, editor, keep = get("ROOTS", d.roots), get("EDITOR", d.editor), get("HISTORY_KEEP", d.history_keep)
    update, workshop = get("UPDATE_URL"), get("WORKSHOP_URL")
    for name, ok, expected in [("ROOTS", _strs(roots), "list[str]"),
                               ("EDITOR", editor is None or (_strs(editor) and len(editor) > 0),
                                "None | non-empty list[str]"),
                               ("HISTORY_KEEP", type(keep) is int and keep >= 1, "int >= 1"),
                               ("UPDATE_URL", isinstance(update, str | None), "None | str"),
                               ("WORKSHOP_URL", isinstance(workshop, str | None), "None | str")]:
        if not ok:
            message = T["config_type"].format(name=name, expected=expected)
            return d, ErrorInfo("TypeError", message, path, None, "", "config", None)
    for s in roots:
        if scan.home_path(s) is None:  # 「~Desktop」：少了斜線，各平台都算壞
            return d, ErrorInfo("ValueError", T["bad_root"].format(entry=s), path, None, "", "config", None)
    return Config(tuple(roots), None if editor is None else tuple(editor), keep, update, workshop), None


class Core:
    """iPLoT 的編排：重掃、進入／返回、按下、依名稱執行、依角色找模組（D159）、新增、回報核心錯誤。
    separate：每按一次另開一個工作程序跑（D161，網頁面板用）；remote：自己就是工作程序，對主程序發問的函式。"""

    def __init__(self, home: Path, config: Config, view: View, safe: bool = False,
                 separate: bool = False, remote: Any = None) -> None:
        self.home, self.config, self.view, self.safe = home, config, view, safe
        self.separate, self.remote, self._blobs = separate, remote, {}  # _blobs：工作程序交回來的 memory（pickle 過）
        self.scope = Scope(("iPLoT",), ())
        self.memories: dict[Path, dict] = {}
        self._stack: list[ModuleInfo] = []
        self._declined: set[Path] = set()  # 這次執行期間答了「不允許」的工作坊模組，不再問
        self.running, self._pending = [], False  # running：正在執行的模組（ModuleInfo），最裡面的在最後；app.page 被呼叫時 running[-1] 就是開頁面的那一個

    def roots(self) -> list[Root]:
        """要掃的根目錄；安全模式只掃 modules。"""
        return scan.roots_from_config(self.home, ("modules",) if self.safe else self.config.roots)

    def rescan(self) -> None:
        """重掃目前範圍並重畫；模組執行中只先記著，等執行結束才做。工作程序裡交給主程序做。"""
        if self.remote is not None:
            return self.remote("rescan")
        if self.running and not self.separate:
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

    def press(self, info: ModuleInfo, handler: str = "run", args: tuple = (),
              quiet: bool = False) -> Result:
        """執行模組：先存快照再交給 runner，結果寫進訊息區；執行中收到的重掃延到結束才做。
        quiet 只省掉「完成」那一行，快照、輸出、錯誤照舊。
        模組資料夾裡有空檔案 .unconfirmed（工作坊裝進來的）時先問一次：取消就不執行，確定就拿掉標記（D59）。"""
        if info.min_api > App.api_version:  # 要的指令集比這個核心新：不跑，說要更新（D161）
            message = T["needs_api"].format(title=info.title, need=info.min_api, have=App.api_version)
            error = ErrorInfo("NeedsNewerIPLoT", message, info.file, None, "", "module", info.name)
            self.view.report(error)
            return Result(False, error, 0.0, "")
        marker = info.folder / ".unconfirmed"
        if marker.exists() and not self.view.confirm(T["confirm_foreign"].format(title=info.title)):
            self.view.log(T["cancelled"].format(title=info.title))
            return Result(False, None, 0.0, "")
        with contextlib.suppress(OSError):  # 拿不掉（唯讀）：照常執行，只是下次還會再問
            marker.unlink(missing_ok=True)
        self.running.append(info)
        try:
            try:
                history.snapshot(info.file, self.config.history_keep)
            except OSError as exc:
                self.view.log(T["snapshot_failed"].format(message=self._why(exc)))
            if self.separate:
                from . import worker  # worker 也 import 這個檔，放在這裡才不會循環
                result = worker.spawn(self, info, handler, args)
            else:
                result = runner.run_module(info, App(self, info), handler, args)
            for line in result.output.splitlines():
                self.view.log(line)
            if result.error:
                self.view.report(result.error)
            elif not quiet:
                self.view.log(T["done"].format(title=info.title, seconds=result.duration))
            return result
        finally:
            self.running.remove(info)
            if not self.running and self._pending:
                self._pending = False
                self.rescan()

    def start(self, info: ModuleInfo) -> None:
        """開始跑 info，不等它（D161）：工作程序裡交給主程序；主程序裡另開一條執行緒按下去。"""
        if self.remote is not None:
            return self.remote("start", info)
        threading.Thread(target=self.press, args=(info,), daemon=True).start()
        return None

    def run_by_name(self, name: str | ModuleInfo) -> Result:
        """執行另一個模組：先找面板目前這一層，找不到再找最上層；同一處有兩個同名就丟 LookupError，不猜。
        名稱先 NFC 正規化。面板在最上層時只找一次，跟 0.5.0 一樣（D83）。"""
        if isinstance(name, str):
            name = unicodedata.normalize("NFC", name)
            found = [m for m in self.all_modules() if m.name == name]
            if not found and self._stack:  # 面板停在下一層：退到最上層找
                found = [m for g in scan.find_modules(self.roots()) for m in g.modules if m.name == name]
            if len(found) != 1:
                paths = "\n".join(str(m.folder) for m in found)
                raise LookupError(T["ambiguous" if found else "not_found"].format(name=name, paths=paths))
            name = found[0]
        return self.press(name)

    def providers(self, role: str) -> list[ModuleInfo]:
        """最上層宣告了 PROVIDES 而且裡面有 role 的模組，依掃描順序（D159）。role 是什麼意思核心不管，
        由提供的模組和使用的模組自己約定。從工作坊裝來的（有 .origin）要使用者允許過才算。"""
        found = [m for g in scan.find_modules(self.roots()) for m in g.modules if role in dict(m.provides)]
        return [m for m in found if self._allowed(m)]

    def _allowed(self, info: ModuleInfo) -> bool:
        """自己寫的、隨附的直接算；有 .origin 的，.roles-ok 記著的宣告跟現在一樣才算，否則問一次。
        答應了就記下（並拿掉 .unconfirmed：允許它提供功能，就是允許它執行）；不答應的這次執行期間不再問。"""
        if not (info.folder / ".origin").is_file():
            return True
        stamp, ok = json.dumps(sorted(info.provides), ensure_ascii=False), info.folder / ".roles-ok"
        with contextlib.suppress(OSError):
            if ok.read_text(encoding="utf-8") == stamp:
                return True
        roles = "、".join(role for role, _ in info.provides)
        if info.folder in self._declined or not self.view.confirm(T["allow_roles"].format(title=info.title, roles=roles)):
            self._declined.add(info.folder)
            return False
        with contextlib.suppress(OSError):
            ok.write_text(stamp, encoding="utf-8")
            (info.folder / ".unconfirmed").unlink(missing_ok=True)
        return True

    def call(self, role: str, *args: Any) -> Any:
        """交給第一個提供 role 的模組執行，回它的回傳值；沒有提供者回 None。"""
        found = self.providers(role)
        return self.run_role(found[0], role, args) if found else None

    def call_here(self, role: str, *args: Any) -> Any:
        """在這個程序裡直接執行第一個提供 role 的模組，交給它 app 與 args，回它的回傳值；沒有提供者回 None（D162）。
        不另開程序、不接輸出、不改工作目錄：開機程式用它開面板，面板要佔著這個程序的主執行緒到視窗關掉。
        模組資料夾放進 sys.path 最前面，它自己的檔照常 import 得到；載入或執行時的例外照樣丟給呼叫的人。"""
        found = self.providers(role)
        if not found:
            return None
        info = found[0]
        spec = importlib.util.spec_from_file_location("iplot_host_" + role.replace(".", "_"), info.file)
        module = importlib.util.module_from_spec(spec)
        sys.path.insert(0, str(info.folder))
        spec.loader.exec_module(module)
        return getattr(module, dict(info.provides)[role])(App(self, info), *args)

    @staticmethod
    def describe(error: ErrorInfo) -> str:
        """錯誤的白話一句（面板顯示用，跟訊息區、記錄檔說的一樣）。"""
        return describe(error)

    def each(self, role: str, *args: Any) -> list[tuple[ModuleInfo, Any]]:
        """交給每一個提供 role 的模組，依序執行；回（模組, 回傳值）。某一個壞了照常報錯，不影響其他的。"""
        return [(m, self.run_role(m, role, args)) for m in self.providers(role)]

    def run_role(self, info: ModuleInfo, role: str, args: tuple = ()) -> Any:
        """執行 info 為 role 宣告的那個函式，跟按下一樣走 press（快照、錯誤、排隊照舊）。"""
        return self.press(info, dict(info.provides)[role], args, quiet=True).value

    def action(self, name: str, *args: Any) -> Any:
        """碰作業系統的事（open、edit、reveal、terminal、trash、requirements、webview_ready）：交給提供 os.<name> 的模組；
        沒有就在訊息區說一句（1.0 起不再照名字找「作業系統」，D164）。"""
        if found := self.providers("os." + name):
            return self.run_role(found[0], "os." + name, args)
        return self.view.log(T["no_system"].format(role="os." + name))

    def create(self, parent: Path, name: str) -> Path | None:
        """新增模組：建好後重掃並打開編輯器；名稱不對、已存在或建不了時寫進訊息區、回 None。"""
        try:
            folder = new_module(parent, name)
        except BadName:
            return self.view.log(T["bad_name"])
        except AlreadyExists:
            return self.view.log(T["already_exists"].format(name=name))
        except OSError as exc:
            return self.view.log(T["create_failed"].format(path=parent, message=self._why(exc)))
        self.rescan()
        self.action("edit", folder / "iplot.py", self.config.editor, None)
        return folder

    def _why(self, exc: OSError) -> str:
        """OSError 的中文原因；errno 與英文原文寫進 logs/iplot.log，事後才查得到（審查 S4）。"""
        with contextlib.suppress(OSError):
            (self.home / "logs").mkdir(exist_ok=True)
            with (self.home / "logs" / "iplot.log").open("a", encoding="utf-8", errors="replace") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{type(exc).__name__}: {exc}\n")
        return reason(exc)

    def report_internal(self, exc_type: type, exc: BaseException, tb: Any) -> None:
        """核心自己的錯誤（tkinter 回呼裡丟出來的）：寫進 logs/iplot.log，再進面板。記錄檔寫不了就只進面板。"""
        error = from_exception(exc, None, "core")
        with contextlib.suppress(OSError):
            (self.home / "logs").mkdir(exist_ok=True)
            with (self.home / "logs" / "iplot.log").open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n{error.traceback_text}\n")
        self.view.report(error)
