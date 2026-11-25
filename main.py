"""iPLoT 的開機程式：python3 main.py [--safe | --run <模組> [檔案…]]。1.0 起凍結，不再改（D167，tests/test_frozen_boot.py 鎖著它的 sha256）。

它只做一件事：找一份開得起來的核心，交給它。依序試
  1. modules/核心/                       平常用的這一份（隨附的「核心」模組，跟著「更新」換）
  2. modules/核心/.local/核心.good/      上一次開得起來的那一份（核心自己記的）
  3. iPLoT 資料夾本身（core/、ui/）           發佈的包裡帶的種子；0.8 的「更新」換的就是這兩個資料夾
每一份都是「有 ui/start.py、它的 ready() 不出錯」才用，用的時候呼叫 run(iPLoT 資料夾, 那一份的資料夾)。

這個檔要在很舊的 Python 上也讀得懂（只說一句「請裝新版 Python」，不丟 traceback），所以不用 f 字串、不用型別標註，
畫面上的兩句話直接寫在這裡（核心的 core/text.py 可能就是壞掉的那一份）。"""

import os
import sys

HOME = os.path.dirname(os.path.abspath(__file__))
NEED = "iPLoT 需要 Python 3.10 以上（目前是 {found}）。請安裝 python.org 的版本。"
GONE = ("iPLoT 找不到能用的核心：modules/核心/ 壞了或不見了，也沒有備份。"
        "請到 iPLoT 的網站重新下載一份，把 modules/ 和 config.py 搬到新的資料夾。技術細節記在 logs/iplot.log。")


def kernels():
    """依序要試的核心資料夾。"""
    here = os.path.join(HOME, "modules", "核心")
    return [here, os.path.join(here, ".local", "核心.good"), HOME]


def log(text):
    """寫進 logs/iplot.log；寫不了就算了。"""
    try:
        folder = os.path.join(HOME, "logs")
        if not os.path.isdir(folder):
            os.mkdir(folder)
        with open(os.path.join(folder, "iplot.log"), "a", encoding="utf-8", errors="replace") as f:
            f.write(text + "\n")
    except (OSError, ValueError):
        pass


def forget(folder):
    """這一份載不起來：把它放進 sys.path 的與載入的東西都拿掉，下一份從乾淨的狀態開始。"""
    while folder in sys.path:
        sys.path.remove(folder)
    for name in list(sys.modules):
        if name.split(".")[0] in ("core", "ui"):
            del sys.modules[name]


def load(folder):
    """folder 開得起來就回它的 ui.start，否則回 None（原因寫進記錄檔）。"""
    if not os.path.isfile(os.path.join(folder, "ui", "start.py")):
        return None
    sys.path.insert(0, folder)
    try:
        from ui import start
        start.ready()
        return start
    except Exception:  # noqa: BLE001  任何一種壞法都是「這一份不能用」，換下一份
        import time
        import traceback

        log(time.strftime("%Y-%m-%d %H:%M:%S") + " 核心載不起來：" + folder + "\n" + traceback.format_exc())
        forget(folder)
        return None


def main():
    if sys.version_info < (3, 10):  # noqa: UP036  這一行就是要在 3.10 以下的直譯器上跑
        sys.exit(NEED.format(found=".".join(map(str, sys.version_info[:3]))))
    for folder in kernels():
        start = load(folder)
        if start is not None:
            return start.run(HOME, folder)
    print(GONE)
    sys.exit(1)


if __name__ == "__main__":
    main()
