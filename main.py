"""iPLoT 入口：python3 main.py [--safe]。組裝設定、核心與面板，然後進入事件迴圈。"""

import sys
from pathlib import Path

from core import __version__
from core.core import Core, load_config
from core.ui import Panel


def main() -> None:
    """啟動 iPLoT。--safe：不載入拖放套件、只掃 modules/。"""
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
