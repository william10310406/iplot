"""模組導覽列（D153）：有頁面的模組，頁面最上面多一排——主控面板、父層、子模組，按一格就跳過去。
頁面載入後才注入（nav.js 在 Shadow DOM 裡畫一個 <iplot-nav>），不碰模組給的 HTML；
跳 = 關掉這一頁，再跑那個模組（面板裡排在這次執行之後，不在頁面的 JS 執行緒上跑，D152 的 running 在這裡用）。
頁面的 JS 只送一個編號給 _iplot_nav；目標的 ModuleInfo 留在這裡，頁面給不了路徑。「互通」帶自己的一份。"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core import scan
from core.core import Core
from core.text import T
from core.types import ModuleInfo

JS = Path(__file__).with_name("nav.js")


def source() -> str:
    """nav.js 的文字：一個函式，收格子的清單。"""
    return JS.read_text(encoding="utf-8")


class Nav:
    """一個頁面視窗的導覽列。格子與目標一一對應：0 是主控面板（只關掉這一頁，目標是 None），接著父層、子模組。"""

    def __init__(self, window: Any, core: Core) -> None:
        owner = core.running[-1]  # 呼叫 app.page 的模組：最裡面那一個
        up, kids = scan.parent_of(owner, core.roots()), scan.find_children(owner.folder, owner.root)
        self.core, self.choice = core, None
        self.targets: list[ModuleInfo | None] = [None, *([up] if up else []), *kids]
        self.cells = [{"k": "panel", "t": T["nav_panel"], "i": "", "d": ""}]
        if up:
            self.cells.append({"k": "parent", "t": T["nav_parent"].format(title=up.title), "i": "", "d": up.description})
        self.cells += [{"k": "child", "t": m.title, "i": m.icon or m.title[:1], "d": m.description} for m in kids]

        def _iplot_nav(i: int) -> None:
            if type(i) is int and 0 <= i < len(self.targets):  # 只認編號，不認 True、"1"、1.0
                self.choice = i
                window.destroy()

        window.expose(_iplot_nav)
        window.events.loaded += lambda: window.evaluate_js(f"({source()})({json.dumps(self.cells)})")

    def jump(self, press: Callable[[Core, ModuleInfo], object]) -> None:
        """頁面關掉之後做：按的是子模組或父層就跑它（用 press）；已經不是模組了就說一句、重掃。"""
        target = self.targets[self.choice] if self.choice else None
        if target is None:
            return
        if scan.is_module(target.folder):
            press(self.core, target)
        else:
            self.core.view.log(T["nav_gone"].format(title=target.title))
            self.core.rescan()
