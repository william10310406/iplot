"""頁面上方的那一排（D153、D159）：開頁面時問提供 page.top 的模組（隨附的「導覽列」）要畫什麼，這裡只負責注入與跳過去。
那個模組回 {"js": 函式的原始碼, "cells": 格子, "targets": 每一格的目標}；目標 None 是「只關掉這一頁」。
頁面的 JS 只送一個編號給 _iplot_nav；目標的 ModuleInfo 留在這裡，頁面給不了路徑。「互通」另開的頁面問同一個模組。"""

import json
from collections.abc import Callable
from typing import Any

from core import scan
from core.core import Core
from core.text import T
from core.types import ModuleInfo

ROLE = "page.top"


def make(window: Any, core: Core) -> "Nav | None":
    """問提供 page.top 的模組；沒有提供者、或回的東西不對，就不畫（頁面照常開）。"""
    owner = core.running[-1]  # 呼叫 app.page 的模組：最裡面那一個
    got = core.call(ROLE, owner)
    if not (isinstance(got, dict) and isinstance(got.get("js"), str) and isinstance(got.get("cells"), list)
            and isinstance(got.get("targets"), list) and len(got["cells"]) == len(got["targets"])
            and all(t is None or isinstance(t, ModuleInfo) for t in got["targets"])):
        return None
    return Nav(window, core, got)


class Nav:
    """一個頁面視窗的導覽列。格子與目標一一對應。"""

    def __init__(self, window: Any, core: Core, got: dict) -> None:
        self.core, self.choice, self.targets, self.cells = core, None, got["targets"], got["cells"]

        def _iplot_nav(i: int) -> None:
            if self.choice is None and type(i) is int and 0 <= i < len(self.targets):  # 只認編號，不認 True、"1"、1.0；連按兩下第一次算數
                self.choice = i
                window.destroy()

        window.expose(_iplot_nav)
        window.events.loaded += lambda: window.evaluate_js(f"({got['js']})({json.dumps(got['cells'])})")

    def jump(self, press: Callable[[Core, ModuleInfo], object]) -> None:
        """頁面關掉之後做：按的是模組就跑它（用 press）；已經不是模組了就說一句、重掃。"""
        target = self.targets[self.choice] if self.choice is not None else None
        if target is None:
            return
        if scan.is_module(target.folder):
            press(self.core, target)
        else:
            self.core.view.log(T["nav_gone"].format(title=target.title))
            self.core.rescan()
