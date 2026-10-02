"""重新啟動 iPLoT：改了 core/ 或 config.py 之後按這顆，整個程式從頭再來。"""

import os
import sys


def run(app):
    os.execv(sys.executable, [sys.executable, str(app.home / "main.py")])
