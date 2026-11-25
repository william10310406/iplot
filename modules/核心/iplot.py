"""iPLoT 的核心（D167）：找模組、執行模組、依角色把事交給別的模組。按這顆打開它的程式碼；開機程式（iPLoT 資料夾的 main.py）找的就是這個資料夾。"""
# ── iPLoT ── 直接執行這個檔（python3 iplot.py）時交給 iPLoT 跑（python3 main.py --run）；從 iPLoT 裡執行時這段不做事。不要可以整段刪掉
import sys

if __name__ == "__main__" and "core.runner" not in sys.modules:
    import os
    import subprocess
    here = folder = os.path.dirname(os.path.abspath(__file__))
    main = None
    while main is None and folder != os.path.dirname(folder):  # 往上一層層找 iPLoT：模組在它裡面或旁邊都找得到
        folder = os.path.dirname(folder)
        try:
            names = [""] + sorted(os.listdir(folder))
        except OSError:
            names = [""]
        mains = (os.path.join(folder, n, "main.py") for n in names)
        main = next((m for m in mains if os.path.isfile(m) and os.path.isdir(os.path.join(os.path.dirname(m), "core"))), None)
    if main and not os.environ.get("IPLOT_DIRECT"):  # IPLOT_DIRECT=1：不交出去，照一般腳本跑（例如在編輯器裡除錯）
        sys.exit(subprocess.call([sys.executable, main, "--run", here, *sys.argv[1:]]))
    if not main:
        print("找不到 iPLoT（模組要放在 iPLoT 資料夾裡或它旁邊），照一般的 python3 iplot.py 跑", file=sys.stderr)
# ── iPLoT ──
ICON = "🧬"
STEADY = "改壞了也開得起來：開機程式會退回上一次開得起來的那一份（這個資料夾的 .local/核心.good/）。"


def version(folder):
    """這一份核心的版本（core/__init__.py 的 __version__）；讀不到回「不明」。"""
    import re

    try:
        text = (folder / "core" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return "不明"
    found = re.search(r'__version__ = "([^"]+)"', text)
    return found.group(1) if found else "不明"


def run(app):
    folder = app.module.folder
    app.log(f"iPLoT 核心 {version(folder)}。{STEADY}")
    app.open(folder)
