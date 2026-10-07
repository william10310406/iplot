"""重新啟動 iPLoT：改了 core/ 或 config.py 之後按這顆，整個程式從頭再來。"""

import os

# ── 互通 ── 直接執行這個檔（python3 iplot.py）時交給 iPLoT 用彈出式視窗跑；從 iPLoT 裡執行時這段不做事。不要可以整段刪掉
import sys

if __name__ == "__main__" and "core.runner" not in sys.modules:
    import os
    import subprocess
    here = folder = os.path.dirname(os.path.abspath(__file__))
    run = None
    while run is None and folder != os.path.dirname(folder):  # 往上一層層找 iPLoT：模組在它裡面或旁邊都找得到
        folder = os.path.dirname(folder)
        try:
            names = [""] + sorted(os.listdir(folder))
        except OSError:
            names = [""]
        runs = (os.path.join(folder, n, "modules", "互通", "run.py") for n in names)
        run = next((r for r in runs if os.path.isfile(r)), None)
    sys.exit(subprocess.call([sys.executable, run, here, *sys.argv[1:]]) if run
             else "找不到 iPLoT 的「互通」：先在工作坊裝「互通」；模組要放在 iPLoT 資料夾裡或它旁邊")
# ── 互通 ──

ICON = "🔄"


def run(app):
    os.chdir(app.home)  # 執行期間的工作目錄是這個模組的資料夾；新的 iPLoT 要從自己的資料夾起來
    os.execv(sys.executable, [sys.executable, str(app.home / "main.py")])
