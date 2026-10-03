"""iPLoT 入口：python3 main.py [--safe]。組裝設定、核心與面板，然後進入事件迴圈。

core.core 與 core.ui 的 import 放在 main() 裡、版本檢查之後：core/ 用了 3.10 的語法，在太舊的
Python 上一 import 就炸，使用者得先看到「請裝新版 Python」那一句，而不是一段 traceback。
檢查之前只 import core.text（它和 core/__init__.py 必須在舊版也 import 得起來，見 D46）。"""

import sys
from pathlib import Path

from core.text import T


def main() -> None:
    """啟動 iPLoT。--safe：不載入拖放套件、只掃 modules/。"""
    found = ".".join(map(str, sys.version_info[:3]))
    if sys.version_info < (3, 10):  # noqa: UP036  這一行就是要在 3.10 以下的直譯器上跑
        sys.exit(T["need_python"].format(found=found))
    from core import __version__
    from core.core import Core, load_config
    from core.ui import Panel

    safe = "--safe" in sys.argv[1:]
    home = Path(__file__).resolve().parent
    config, err = load_config(home / "config.py")
    panel = Panel(__version__, safe)
    core = Core(home, config, panel, safe)
    panel.attach(core)
    panel.window.report_callback_exception = core.report_internal
    if err is not None:
        panel.report(err)
    core.rescan()
    panel.mainloop()


if __name__ == "__main__":
    main()
