"""記住上一版：模組 iplot.py 的快照存在模組自己的 .history/，可以復原。"""

import hashlib
import re
from datetime import datetime
from pathlib import Path

NAME = re.compile(r"\d{4}-\d{2}-\d{2}_\d{6}(_\d+)?")  # 只認自己的命名；.history/ 裡別的檔案一律不碰


def _now() -> datetime:
    return datetime.now()


def _order(p: Path) -> tuple[str, int]:
    tail = p.stem[18:]  # 「2026-10-02_140905」之後的序號
    return p.stem[:17], int(tail) if tail.isdigit() else 0


def versions(file: Path) -> list[Path]:
    """file 的所有快照，新到舊。"""
    found = (p for p in (file.parent / ".history").glob("*.py") if NAME.fullmatch(p.stem))
    return sorted(found, key=_order, reverse=True)


def snapshot(file: Path, keep: int) -> Path | None:
    """存一份 file 的快照；跟最新一份內容相同就不存、回 None。只保留最新 keep 份。"""
    data, old = file.read_bytes(), versions(file)
    if old and hashlib.sha256(old[0].read_bytes()).digest() == hashlib.sha256(data).digest():
        return None
    folder = file.parent / ".history"
    folder.mkdir(exist_ok=True)
    stamp = _now().strftime("%Y-%m-%d_%H%M%S")
    new, n = folder / f"{stamp}.py", 0
    while new.exists():
        n += 1
        new = folder / f"{stamp}_{n}.py"
    new.write_bytes(data)
    for extra in versions(file)[keep:]:
        extra.unlink()
    return new


def restore(file: Path, version: Path, keep: int) -> None:
    """把 file 換回 version 的內容；換之前先存一份快照，所以復原本身也能再復原。"""
    data = version.read_bytes()  # 先讀進來：快照存滿時，下一行可能刪掉的正是這一份
    snapshot(file, keep)
    file.write_bytes(data)
