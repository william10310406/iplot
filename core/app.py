"""模組看得到的全部：每次執行新建一個 App，傳給模組的 run(app)。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__
from .types import Config, ModuleInfo, Result

if TYPE_CHECKING:
    from .core import Core


class App:
    """模組拿到的 app。介面只加不減；要拿掉東西就升 api_version 並寫進 CHANGELOG
    （1 是第一版；2 拿掉了 window，見 D66；3 加了 config、version、page）。version 是核心的版本字串。"""

    api_version: int = 3
    version: str = __version__

    def __init__(self, core: Core, info: ModuleInfo) -> None:
        self._core, self._info = core, info
        self._memory = core.memories.setdefault(info.folder, {})

    @property
    def module(self) -> ModuleInfo:
        """正在執行的模組的資訊：name、title、folder、file 等（見附錄 B 的 ModuleInfo）。"""
        return self._info

    @property
    def home(self) -> Path:
        """iPLoT 程式資料夾。"""
        return self._core.home

    @property
    def modules(self) -> tuple[ModuleInfo, ...]:
        """目前範圍內所有模組的唯讀清單。"""
        return self._core.all_modules()

    @property
    def config(self) -> Config:
        """config.py 讀出來的設定（唯讀）：roots、editor、history_keep、update_url、workshop_url。"""
        return self._core.config

    @property
    def memory(self) -> dict:
        """這個模組自己的 dict，iPLoT 開著期間保留；跨次啟動要留的請寫成檔案放 module.folder。"""
        return self._memory

    def log(self, text: str) -> None:
        """寫一行到面板下方的訊息區。"""
        self._core.view.log(text)

    # 以下五個動作交給 modules/作業系統 執行（core.action）。那個模組執行時工作目錄是它自己的資料夾，
    # 所以路徑在這裡先變成絕對的：相對路徑指的是呼叫的模組自己的資料夾，跟 open("x.txt") 一樣

    def open(self, path: Path) -> None:
        """打開：資料夾用檔案總管、檔案用預設程式。由 modules/作業系統 執行。"""
        self._core.action("open", Path(path).absolute())

    def edit(self, path: Path, line: int | None = None) -> None:
        """用 config.py 的 EDITOR 打開檔案（None 時用系統預設文字編輯器）；資料夾改用 open。"""
        self._core.action("edit", Path(path).absolute(), self._core.config.editor, line)

    def reveal(self, path: Path) -> None:
        """在檔案總管裡顯示並選取這個檔案或資料夾。"""
        self._core.action("reveal", Path(path).absolute())

    def terminal(self, path: Path) -> None:
        """在終端機打開這個資料夾。"""
        self._core.action("terminal", Path(path).absolute())

    def trash(self, path: Path) -> Path | None:
        """搬到系統垃圾桶，永遠不直接刪除；回傳搬到哪裡（Windows 的資源回收筒沒有路徑，回 None）。"""
        return self._core.action("trash", Path(path).absolute())

    def run(self, name: str | ModuleInfo) -> Result:
        """執行目前範圍內另一個模組；找不到或有兩個同名時丟 LookupError，不猜。"""
        return self._core.run_by_name(name)

    def rescan(self) -> None:
        """重新掃描並重畫面板；在模組執行中呼叫時，會等這次執行結束後才做。"""
        self._core.rescan()

    def ask(self, prompt: str, default: str = "") -> str | None:
        """跳出對話框問一個字串；按取消回 None。"""
        return self._core.view.ask(prompt, default)

    def confirm(self, prompt: str) -> bool:
        """跳出對話框問「確定／取消」；按確定回 True。"""
        return self._core.view.confirm(prompt)

    def page(self, title: str, html: str, api: object | None = None) -> None:
        """開一個視窗顯示一頁 HTML，關掉才回來；api 的公開方法給那一頁的 JS 用 pywebview.api.<方法> 呼叫。
        安全模式沒有頁面，只在訊息區記一行。"""
        self._core.view.page(title, html, api)

    def choose_files(self) -> list[Path]:
        """跳出檔案選擇視窗；按取消回空清單。"""
        return self._core.view.choose_files()

    def choose_folder(self) -> Path | None:
        """跳出資料夾選擇視窗；按取消回 None。"""
        return self._core.view.choose_folder()
