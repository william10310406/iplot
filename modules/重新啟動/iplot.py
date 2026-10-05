"""重新啟動 iPLoT：改了 core/ 或 config.py 之後按這顆，整個程式從頭再來。"""

import os
import sys

ICON = "🔄"


def run(app):
    os.chdir(app.home)  # 執行期間的工作目錄是這個模組的資料夾；新的 iPLoT 要從自己的資料夾起來
    os.execv(sys.executable, [sys.executable, str(app.home / "main.py")])
