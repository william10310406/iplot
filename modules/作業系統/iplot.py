"""碰作業系統的事都在這個資料夾：打開檔案、編輯、在資料夾中顯示、開終端機、搬到垃圾桶。
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
terminal, trash = backend.terminal, backend.trash
requirements, webview_ready = backend.requirements, backend.webview_ready  # 第一次啟動的安裝會問這兩個


def run(app):
    name = Path(backend.__file__).name
    app.log(f"作業系統：{backend.NAME}，用的是 {name}。要改打開檔案、資料夾、終端機、垃圾桶的做法："
            f"右鍵這顆按鈕 → 打開程式碼，再改 {name}")
