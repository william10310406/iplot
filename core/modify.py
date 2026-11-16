"""改名與移到垃圾桶的規則：只讓使用者動自己新增的模組。隨附的、從工作坊裝來的，核心擋下並說為什麼（D155）。"""

import os
import unicodedata
from pathlib import Path

from .create import BadName, _bad_name
from .text import BUNDLED, T
from .types import ModuleInfo


def refusal(info: ModuleInfo, home: Path, rename: bool) -> str | None:
    """不能動就回一句話（說為什麼、現在可以怎麼做），可以動回 None。
    隨附的模組（modules/ 底下名字在 BUNDLED 裡的）、它們底下的子模組，一律不能改名或刪除；
    別的模組底下的子模組，要處理就處理整個父層；從工作坊裝來的（資料夾裡有 .origin）不能改名，可以刪。"""
    top = (home / "modules").resolve()
    for folder in (info.folder, *info.folder.parents):
        if folder == info.root or folder == folder.parent:
            break
        if folder.parent == top and folder.name in BUNDLED:
            return T["protected_bundled"].format(name=info.name if folder == info.folder else folder.name)
        if folder != info.folder and (folder / ".origin").is_file():
            return T["protected_parent"].format(name=info.name, parent=folder.name)
    if rename and (info.folder / ".origin").is_file():
        return T["protected_workshop"].format(name=info.name)
    return None


def target(info: ModuleInfo, new: str) -> Path | None:
    """改名後的資料夾；名稱沒變回 None。名稱不可攜丟 BadName；同一層已經有同名的（不分大小寫、不分 NFC／NFD，
    各系統都一樣擋，因為模組以後會被複製到別的電腦）丟 FileExistsError。只改大小寫不算撞名。"""
    new = unicodedata.normalize("NFC", new.strip())
    if _bad_name(new):
        raise BadName(new)
    if new == unicodedata.normalize("NFC", info.folder.name):
        return None
    key = new.casefold()
    for name in os.listdir(info.folder.parent):
        same_folder = name == info.folder.name
        if not same_folder and unicodedata.normalize("NFC", name).casefold() == key:
            raise FileExistsError(new)
    return info.folder.with_name(new)
