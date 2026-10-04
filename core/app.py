"""模組看得到的全部：每次執行新建一個 App，傳給模組的 run(app)。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .types import ModuleInfo, Result

if TYPE_CHECKING:
    from .core import Core


class App:
    """模組拿到的 app。介面只加不減；要拿掉東西就升 api_version（第一版是 1）並寫進 CHANGELOG。"""

    api_version: int = 1

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
    def memory(self) -> dict:
        """這個模組自己的 dict，iPLoT 開著期間保留；跨次啟動要留的請寫成檔案放 module.folder。"""
        return self._memory

    @property
    def window(self) -> Any:
        """tkinter 主視窗，模組要自己畫東西時用。"""
        return self._core.view.window

    def log(self, text: str) -> None:
        """寫一行到面板下方的訊息區。"""
        self._core.view.log(text)

    def open(self, path: Path) -> None:
        """打開：資料夾用檔案總管、檔案用預設程式。由 modules/作業系統 執行。"""
        self._core.action("open", path)

    def edit(self, path: Path, line: int | None = None) -> None:
        """用 config.py 的 EDITOR 打開檔案（None 時用系統預設文字編輯器）；資料夾改用 open。"""
        self._core.action("edit", path, self._core.config.editor, line)

    def reveal(self, path: Path) -> None:
        """在檔案總管裡顯示並選取這個檔案或資料夾。"""
        self._core.action("reveal", path)

    def terminal(self, path: Path) -> None:
        """在終端機打開這個資料夾。"""
        self._core.action("terminal", path)

    def trash(self, path: Path) -> Path | None:
        """搬到系統垃圾桶，永遠不直接刪除；回傳搬到哪裡（Windows 的資源回收筒沒有路徑，回 None）。"""
        return self._core.action("trash", path)

    def run(self, name: str | ModuleInfo) -> Result:
        """執行目前範圍內另一個模組；找不到或有兩個同名時丟 LookupError，不猜。"""
        return self._core.run_by_name(name)

    def rescan(self) -> None:
        """重新掃描並重畫面板；在模組執行中呼叫時，會等這次執行結束後才做。"""
        self._core.rescan()

    def ask(self, prompt: str, default: str = "") -> str | None:
        """跳出對話框問一個字串；按取消回 None。"""
        return self._core.view.ask(prompt, default)

    def choose_files(self) -> list[Path]:
        """跳出檔案選擇視窗；按取消回空清單。"""
        return self._core.view.choose_files()

    def choose_folder(self) -> Path | None:
        """跳出資料夾選擇視窗；按取消回 None。"""
        return self._core.view.choose_folder()
