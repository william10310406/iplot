"""新增模組：照範本寫一個 iplot.py。"""

from pathlib import Path

from .text import TEMPLATE


class BadName(ValueError):
    """名稱是空白、含 /、或以 . 開頭。"""


class AlreadyExists(FileExistsError):
    """那個資料夾已經有 iplot.py。"""


def template() -> str:
    """新模組的範本（規格附錄 A）。"""
    return TEMPLATE


def new_module(parent: Path, name: str) -> Path:
    """在 parent 底下做一個叫 name 的模組，回傳它的資料夾。

    資料夾不存在就建立；已存在但沒有 iplot.py 就只寫入 iplot.py，把它變成模組。"""
    if not name.strip() or "/" in name or name.startswith("."):
        raise BadName(name)
    file = parent / name / "iplot.py"
    if file.exists():  # 不分大小寫：原版的 iPLoT.py 也算，絕不覆寫
        raise AlreadyExists(name)
    file.parent.mkdir(exist_ok=True)
    file.write_text(template(), encoding="utf-8")
    return file.parent
