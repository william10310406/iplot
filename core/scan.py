"""找模組：資料夾裡有 iplot.py 就是模組。只看檔名和 ast，不執行任何模組程式碼。"""

import contextlib
import os
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from .meta import read_meta
from .text import T
from .types import Group, Level, ModuleInfo, Root

MARKER = "iplot.py"
ICONS = ("icon.png", "icon.svg")  # 模組資料夾裡的圖示檔，前面的優先（D65）


def _nfc(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def home_path(s: str) -> Path | None:
    """「~」與「~/…」把 ~ 換成家目錄；「~名字」各平台都不認，回 None。不靠 expanduser 丟不丟例外：Windows 不丟，會猜成別人的家目錄。"""
    if not s.startswith("~"):
        return Path(s)
    return Path(s).expanduser() if s[1:2] in ("", "/", os.sep) else None


def is_module(folder: Path) -> bool:
    """folder 是資料夾（不是符號連結），裡面有檔名剛好是 iplot.py 的檔案；讀不到就不是。"""
    with contextlib.suppress(OSError):  # APFS 不分大小寫，所以比對 listdir 的實際檔名，iPLoT.py 不算
        return (not folder.is_symlink() and folder.is_dir()
                and MARKER in os.listdir(folder) and (folder / MARKER).is_file())
    return False


def _module_folders(folder: Path) -> list[Path]:
    """folder 底下是模組的子資料夾，略過 . 開頭，按名稱排序；folder 讀不到時丟 OSError。"""
    found = [p for p in folder.iterdir() if not p.name.startswith(".") and is_module(p)]
    return sorted(found, key=lambda p: _nfc(p.name))


def module_info(folder: Path, root: Path, level: Level) -> ModuleInfo:
    """讀一個模組的資訊，不執行它。圖示檔是檔名剛好叫 icon.png 或 icon.svg 的檔案：
    跟 iplot.py 一樣比對實際檔名，Icon.png 不算。"""
    name, file = _nfc(folder.name), folder / MARKER
    meta, icon_file, has_children = read_meta(file), None, False
    with contextlib.suppress(OSError):  # 資料夾讀不到：當作沒有圖示檔、沒有子模組
        names = os.listdir(folder)
        icon_file = next((folder / n for n in ICONS if n in names and (folder / n).is_file()), None)
        has_children = bool(_module_folders(folder))
    return ModuleInfo(name, meta.title or name, meta.description, folder, file, root, level,
                      meta.has_run, meta.accepts_files, has_children, meta.error, meta.icon, icon_file)


def _same(a: Path, b: Path) -> bool:
    """同一個資料夾：都存在時用 samefile（不分大小寫也認得），否則比 resolve 後的字串。"""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return str(a) == str(b)


def roots_from_config(home: Path, roots: Iterable[str]) -> list[Root]:
    """把 config 的 ROOTS 變成 Root 清單；解析到同一個資料夾的只留第一個。"""
    result: list[Root] = []
    for s in roots:
        if s == "modules":
            root = Root(T["here"], "here", (home / "modules").resolve())
        elif s == "..":
            root = Root(T["parent"], "parent", home.parent.resolve())
        else:
            p = home_path(s) or Path(s)  # 「~Desktop」少了斜線：當成相對路徑
            root = Root(s, "extra", (p if p.is_absolute() else home / p).resolve())
        if not any(_same(root.path, r.path) for r in result):
            result.append(root)
    return result


def find_modules(roots: list[Root]) -> list[Group]:
    """每個根目錄一組；根目錄找不到或讀不到時是空的組，note 說明原因。"""
    groups = []
    for r in roots:
        try:
            mods = tuple(module_info(f, r.path, r.level) for f in _module_folders(r.path))
            groups.append(Group(r.label, r.level, r.path, mods))
        except FileNotFoundError:
            groups.append(Group(r.label, r.level, r.path, (), T["root_missing"].format(path=r.path)))
        except OSError:
            groups.append(Group(r.label, r.level, r.path, (), T["root_unreadable"].format(path=r.path)))
    return groups


def find_children(folder: Path, root: Path) -> list[ModuleInfo]:
    """folder 底下的子模組（level 為 child）；讀不到就當作沒有。"""
    with contextlib.suppress(OSError):
        return [module_info(f, root, "child") for f in _module_folders(folder)]
    return []
