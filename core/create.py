"""新增模組：照範本寫一個 iplot.py。"""

from pathlib import Path

from .text import TEMPLATE

FORBIDDEN_CHARS = set('/\\:*?"<>|')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10))}


class BadName(ValueError):
    """名稱不可攜：空白、以 . 開頭、結尾是 . 或空白、含 / \\ : * ? " < > | 或控制字元、或是 Windows 保留字。"""


class AlreadyExists(FileExistsError):
    """那個資料夾已經有 iplot.py。"""


def template() -> str:
    """新模組的範本（規格附錄 A）。"""
    return TEMPLATE


def _bad_name(name: str) -> bool:
    """三個平台擋同一套：模組以後會被複製到別的電腦（D54）。"""
    return (not name.strip() or name.startswith(".") or name != name.rstrip(". ")
            or any(c in FORBIDDEN_CHARS or ord(c) < 32 for c in name)
            or name.split(".")[0].upper() in RESERVED)


def new_module(parent: Path, name: str) -> Path:
    """在 parent 底下做一個叫 name 的模組，回傳它的資料夾。

    資料夾不存在就建立；已存在但沒有 iplot.py 就只寫入 iplot.py，把它變成模組。"""
    if _bad_name(name):
        raise BadName(name)
    file = parent / name / "iplot.py"
    if file.exists():  # 不分大小寫：原版的 iPLoT.py 也算，絕不覆寫
        raise AlreadyExists(name)
    file.parent.mkdir(exist_ok=True)
    file.write_text(template(), encoding="utf-8")
    return file.parent
