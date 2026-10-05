"""網頁面板：pywebview 開的原生視窗裡跑 ui/index.html。

WebPanel 實作 core.View，把 show／log／report／ask 翻成對頁面的呼叫（iplot.<名字>(…)）；
Bridge 是頁面呼叫 Python 的入口，動作都排進單一工作執行緒交給 Core。沒有 server、沒有 port：
頁面用 file:// 載入，JS 直接呼叫 Python（pywebview 的 js_api）。Core 不知道執行緒的存在。"""

import base64
import contextlib
import itertools
import json
import queue
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.core import Core
from core.errors import describe
from core.scan import is_module
from core.text import T
from core.types import ErrorInfo, ModuleInfo, Scope

MAX_ICON = 1024 * 1024  # 圖示檔的上限：1 MB（D65）
MIME = {".png": "image/png", ".svg": "image/svg+xml"}
PATHS = {"here": "modules/", "parent": "../"}  # 組標題旁邊顯示的路徑；extra 顯示 config 裡寫的那個字串
ACTIONS = ("reveal", "terminal")  # 頁面可以要求「作業系統」模組做的事；另有 edit，參數不同
_icons: dict[Path, tuple[tuple[int, int], str]] = {}  # 圖示檔 →（（修改時間, 大小）, data URI）


def _data_uri(file: Path) -> str | None:
    """圖示檔變成 data URI；空的、超過 1 MB 或讀不到回 None。檔案沒變就用上次讀的。
    內容是不是一張讀得出來的圖，要到頁面上才知道：讀不出來時頁面自己換成預設圖示（app.js 的 iconEl）。"""
    try:
        stat = file.stat()
        if not 0 < stat.st_size <= MAX_ICON:
            return None
        stamp = (stat.st_mtime_ns, stat.st_size)
        if _icons.get(file, (None, ""))[0] != stamp:
            data = base64.b64encode(file.read_bytes()).decode("ascii")
            _icons[file] = (stamp, f"data:{MIME[file.suffix]};base64,{data}")
        return _icons[file][1]
    except OSError:
        return None


def icon_for(info: ModuleInfo, warned: set[Path], log: Callable[[str], None]) -> dict | None:
    """圖示的來源依序：資料夾裡的圖檔 → ICON 常數 → None（頁面用名字第一個字）。
    圖檔不能用就當作沒有，並用 log 記一行；warned 記著說過的檔，每個檔只說一次。"""
    if info.icon_file is not None:
        uri = _data_uri(info.icon_file)
        if uri is not None:
            return {"file": uri}
        if info.icon_file not in warned:
            warned.add(info.icon_file)
            log(T["icon_unusable"].format(title=info.title))
    return {"text": info.icon} if info.icon else None


def scope_json(scope: Scope, icon_for: Callable[[ModuleInfo], dict | None]) -> dict:
    """Scope 變成給頁面的 JSON（規格附錄 A）。進到下一層時只有一組，level 是 child；
    root 是那一組的資料夾，頁面按 ＋ 時原樣傳回來。"""
    nested = len(scope.crumbs) > 1
    return {"crumbs": list(scope.crumbs), "groups": [{
        "label": g.label, "level": "child" if nested else g.level,
        "path": g.root.name + "/" if nested else PATHS.get(g.level, g.label), "root": str(g.root), "note": g.note,
        "modules": [{"id": str(m.folder), "name": m.name, "title": m.title, "description": m.description,
                     "icon": icon_for(m), "has_children": m.has_children, "error": m.error}
                    for m in g.modules]} for g in scope.groups]}


def error_json(error: ErrorInfo) -> dict:
    """ErrorInfo 變成給頁面的 JSON：白話那一句（sentence）與 traceback 分開，怎麼排由頁面決定。"""
    return {"kind": error.kind, "message": error.message,
            "file": None if error.file is None else str(error.file), "line": error.line,
            "traceback": error.traceback_text, "source": error.source, "module": error.module,
            "sentence": describe(error)}


class Bridge:
    """頁面的 JS 用 pywebview.api.<方法> 呼叫的入口。除了 state 與 answer，都只把工作排進工作執行緒、
    立刻回傳。頁面傳來的 id、資料夾、動作名稱只認目前面板上有的，其餘一律當作「畫面過期了」重掃。
    面板放在 _panel：pywebview 會把公開屬性一路攤開進 pywebview.api，底線讓攤出去的只有下面這些方法。
    這是整潔，不是安全邊界；真正的邊界是頁面不載入任何外來的內容（零外部資源、模組的輸出一律當文字）。"""

    def __init__(self, panel: "WebPanel") -> None:
        self._panel = panel

    def _on(self, id: str, fn: Callable[[Core, Any], object], find: Callable[[str], Any] | None = None) -> None:
        """排一件工作：用 find（預設找模組）把頁面給的 id 找回來，交給 fn(core, 找到的)；找不到就重掃。"""
        def job() -> None:
            core, found = self._panel.core, (find or self._panel.find)(id)
            if found is None:  # 不在面板上，或資料夾已經被刪掉
                core.rescan()
            else:
                fn(core, found)
        self._panel.submit(job)

    def state(self) -> dict:
        """目前的範圍（跟 iplot.show 收到的一樣）。"""
        return scope_json(self._panel.core.scope, self._panel.icon)

    def press(self, id: str) -> None:
        """執行模組。"""
        self._on(id, self._panel.press)

    def enter(self, id: str) -> None:
        """進入下一層。"""
        self._on(id, lambda core, info: core.enter(info))

    def back(self, depth: int) -> None:
        """麵包屑回上；0 是頂層。"""
        self._panel.submit(lambda: self._panel.core.back(int(depth)))

    def create(self, parent: str, name: str) -> None:
        """在某一組的資料夾（那一組的 root）新增模組。"""
        self._on(parent, lambda core, root: core.create(root, name), self._panel.root)

    def add_child(self, id: str, name: str) -> None:
        """在模組底下新增下一層模組。"""
        self._on(id, lambda core, info: core.create(info.folder, name))

    def action(self, name: str, id: str) -> None:
        """右鍵選單的 edit／reveal／terminal，交給「作業系統」模組做。"""
        if name == "edit":
            self._on(id, lambda core, info: core.action("edit", info.file, core.config.editor, None))
        elif name in ACTIONS:
            self._on(id, lambda core, info: core.action(name, info.folder))

    def open_error(self, error_id: int) -> None:
        """「打開檔案」：用編輯器打開第 error_id 筆回報的檔案，跳到出錯的那一行。"""
        errors, core = self._panel.errors, self._panel.core
        if isinstance(error_id, int) and 0 <= error_id < len(errors) and errors[error_id].file is not None:
            error = errors[error_id]
            self._panel.submit(lambda: core.action("edit", error.file, core.config.editor, error.line))

    def rescan(self) -> None:
        """重掃（視窗取得焦點時頁面會呼叫，D11）。"""
        self._panel.submit(self._panel.core.rescan)

    def answer(self, ask_id: int, value: Any) -> None:
        """回答第 ask_id 個對話框：字串、true／false，或 null（取消）。"""
        self._panel.answer(ask_id, value)


class WebPanel:
    """iPLoT 的主視窗（網頁版）：上面是麵包屑和一組組圖示，下面是狀態列和訊息區。實作 core.View。"""

    def __init__(self, home: Path, version: str, safe: bool, webview: Any = None) -> None:
        if webview is None:
            import webview  # lib/ 裡的 pywebview：只有這個檔可以 import 它
        self.home, self.version, self.safe, self.webview = home, version, safe, webview
        self.core: Core | None = None
        self.window: Any = None
        self.errors: list[ErrorInfo] = []  # 回報過的錯誤；頁面的「打開檔案」用編號指回來
        self._jobs: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._waiting: dict[int, tuple[threading.Event, list]] = {}  # 等回答的對話框
        self._closed = False
        self._warned: set[Path] = set()

    def attach(self, core: Core) -> None:
        """接上 Core；之後頁面的動作都交給它。"""
        self.core = core

    def run(self) -> None:
        """開視窗，進入 pywebview 的事件迴圈（佔住主執行緒）；視窗關掉才回傳。"""
        title = T["title"].format(version=self.version) + (T["safe_mode"] if self.safe else "")
        self.window = self.webview.create_window(
            title, url=(self.home / "ui" / "index.html").as_uri(), js_api=Bridge(self),
            width=820, height=620, min_size=(480, 420))
        self.window.events.loaded += self._loaded
        self.window.events.closing += lambda: self._cancel(closed=True)
        self.webview.start()

    def _loaded(self) -> None:
        """頁面載入完成：先把文字整份送進去，工作執行緒才開始做事，頁面拿到文字之前不會收到別的呼叫。"""
        self._cancel()  # 重新載入的話，舊頁面上的對話框已經不在了
        self._js("init", {"text": T, "version": self.version, "safe": self.safe})
        self.submit(self.core.rescan)
        if self._worker is None:  # 第一次載入（啟動）
            self.submit(self._scanned)
            self._worker = threading.Thread(target=self._work, daemon=True)
            self._worker.start()

    def _scanned(self) -> None:
        roots = T["list_sep"].join(PATHS.get(g.level, g.label) for g in self.core.scope.groups)
        self.log(T["scanned"].format(roots=roots, count=len(self.core.all_modules())))

    def _cancel(self, closed: bool = False) -> None:
        """等回答的對話框全部當作按了取消；closed（視窗關了）之後不再對頁面說話，新的對話框直接回取消。"""
        with self._lock:
            self._closed = self._closed or closed
            for event, _ in self._waiting.values():
                event.set()
            self._waiting.clear()

    def _work(self) -> None:
        """工作執行緒：一次只做一件。沒接住的例外交給 core.report_internal，迴圈繼續。"""
        while True:
            job = self._jobs.get()
            try:
                if not self._closed:  # 視窗關了：排著還沒做的工作不再做
                    job()
            except Exception as exc:  # noqa: BLE001  規格 §11 允許的三處之一：一件工作出錯，面板不能就此不動
                self.core.report_internal(type(exc), exc, exc.__traceback__)
            finally:
                self._jobs.task_done()

    def press(self, core: Core, info: ModuleInfo) -> None:
        """執行模組，前後各告訴頁面一聲：輸出要等模組結束才進訊息區，執行期間頁面得看得出它還在跑。"""
        self._js("busy", info.title)
        core.press(info)
        self._js("busy", None)

    def submit(self, job: Callable[[], object]) -> None:
        """排一件工作給工作執行緒，立刻回傳。"""
        self._jobs.put(job)

    def wait(self) -> None:
        """等排著的工作全部做完（測試用）。"""
        self._jobs.join()

    def find(self, id: str) -> ModuleInfo | None:
        """目前面板上資料夾是 id 的模組；不在面板上、或那個資料夾已經不是模組（被刪了）就回 None。"""
        return next((m for m in self.core.all_modules() if str(m.folder) == id and is_module(m.folder)), None)

    def root(self, path: str) -> Path | None:
        """目前面板上資料夾是 path 的那一組的資料夾；沒有這一組就回 None。"""
        return next((g.root for g in self.core.scope.groups if str(g.root) == path), None)

    def icon(self, info: ModuleInfo) -> dict | None:
        """info 的圖示（見 icon_for）。"""
        return icon_for(info, self._warned, self.log)

    def _js(self, name: str, *args: Any) -> None:
        """呼叫頁面的 iplot.<name>(…)。參數用 JSON 寫進去：JSON 就是合法的 JS 字面值，不另外轉義；
        非 ASCII 一律寫成 \\uXXXX，名稱裡有引號、反斜線、換行都不會壞。視窗關了就不做。"""
        if not self._closed:
            self.window.evaluate_js(f"iplot.{name}({', '.join(json.dumps(a) for a in args)})")

    def show(self, scope: Scope) -> None:
        """把範圍交給頁面，整個重畫。"""
        self._js("show", scope_json(scope, self.icon))

    def log(self, text: str) -> None:
        """訊息區末尾加一行。"""
        self._js("log", text)

    def report(self, error: ErrorInfo) -> None:
        """訊息區顯示錯誤：白話一句，「打開檔案」與「詳細」由頁面排。頁面壞到顯示不了也不往外丟。"""
        self.errors.append(error)
        with contextlib.suppress(self.webview.JavascriptException):
            self._js("report", {**error_json(error), "id": len(self.errors) - 1})

    def _dialog(self, kind: str, *args: Any) -> Any:
        """推一個對話框給頁面，等頁面用 answer(編號, 值) 回來；視窗關掉、頁面重新載入都算取消（None）。"""
        event, box = threading.Event(), [None]
        with self._lock:
            if self._closed:
                return None
            ask_id = next(self._ids)
            self._waiting[ask_id] = (event, box)
        self._js(kind, ask_id, *args)
        event.wait()
        return box[0]

    def answer(self, ask_id: int, value: Any) -> None:
        """頁面回答了第 ask_id 個對話框；不認得的編號（答過了、取消了）不理。"""
        with self._lock:
            event, box = self._waiting.pop(ask_id, (None, None))
            if event is not None:
                box[0] = value
                event.set()

    def ask(self, prompt: str, default: str = "") -> str | None:
        """面板內的對話框問一個字串；按取消回 None。模組的 input() 也是這個。"""
        value = self._dialog("ask", prompt, default)
        return value if isinstance(value, str) else None

    def confirm(self, prompt: str) -> bool:
        """面板內的「確定／取消」對話框；按確定回 True。"""
        return self._dialog("confirm", prompt) is True

    def choose_files(self) -> list[Path]:
        """原生的檔案選擇視窗（D67）；按取消回空清單。"""
        found = self.window.create_file_dialog(self.webview.FileDialog.OPEN, allow_multiple=True)
        return [Path(p) for p in found or ()]

    def choose_folder(self) -> Path | None:
        """原生的資料夾選擇視窗；按取消回 None。"""
        found = self.window.create_file_dialog(self.webview.FileDialog.FOLDER)
        return Path(found[0]) if found else None
