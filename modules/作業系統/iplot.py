"""碰作業系統的事都在這個資料夾：打開檔案、編輯、在資料夾中顯示、開終端機、搬到垃圾桶、把視窗叫到最前面。
核心一行作業系統的程式碼都沒有；要改這些行為，改這裡的 mac.py / win.py / linux.py。"""
import sys
from pathlib import Path

if sys.platform == "darwin":
    import mac as backend
elif sys.platform == "win32":
    import win as backend
else:
    import linux as backend

ICON = "🖥️"
open, edit, reveal = backend.open, backend.edit, backend.reveal
terminal, trash, activate, app_name = backend.terminal, backend.trash, backend.activate, backend.app_name
requirements, webview_ready = backend.requirements, backend.webview_ready  # 第一次啟動的安裝會問這兩個
# iPLoT 0.8 起核心照這張表找做這些事的模組（D159），不再靠「作業系統」這個名字；更舊的核心不看它
PROVIDES = {"os.open": "open", "os.edit": "edit", "os.reveal": "reveal", "os.terminal": "terminal", "os.trash": "trash",
            "os.requirements": "requirements", "os.webview_ready": "webview_ready",
            "os.activate": "activate", "os.app_name": "app_name"}  # 1.0 起（D164、D166）
ROLE_NAMES = {"os.open": "打開檔案", "os.edit": "用編輯器打開檔案", "os.reveal": "在 Finder 或檔案總管中顯示",
              "os.terminal": "開終端機", "os.trash": "把檔案移到垃圾桶", "os.requirements": "選要裝的套件",
              "os.webview_ready": "檢查網頁面板能不能開", "os.activate": "把視窗叫到最前面",
              "os.app_name": "Dock 上顯示的名字"}  # 「要允許嗎？」用（D166）


def run(app):
    name = Path(backend.__file__).name
    app.log(f"作業系統：{backend.NAME}，用的是 {name}。要改打開檔案、資料夾、終端機、垃圾桶的做法："
            f"右鍵這顆按鈕 → 打開程式碼，再改 {name}")
