"""同步：讓舊模組能直接執行（補那一小段，每個模組一次）、讓捷徑跟上模組（macOS），把這一次的問題寫下來。

只在兩個時機做：run.py 每次跑完、在面板按「互通」。沒有背景程式（D84）。同一時間只有一個在做（.lock）。
「互通」只寫自己的資料夾；例外只有一個：在沒有那一小段的模組 iplot.py 加上它（先存快照）。"""

import contextlib
import json
import os
import sys
import time
from pathlib import Path

import shortcut
import snippet

from core import scan
from core.text import SYSTEM_MODULE
from core.types import Config, ModuleInfo, Root

LOCK, PATCHED, ERRORS = ".lock", ".patched", ".sync-error"
STALE = 120  # 秒：比這個舊的鎖當作上次沒清掉
BUNDLED = ("作業系統", "更新", "工作坊")  # iPLoT 自己要用的三個隨附模組，不補


def modules(home: Path, config: Config) -> list[tuple[ModuleInfo, list[str]]]:
    """ROOTS 底下所有模組，一路往下到每一層；每個模組帶著它一路的顯示名稱（給捷徑的「父 › 子」）。"""
    found: list[tuple[ModuleInfo, list[str]]] = []

    def walk(info: ModuleInfo, titles: list[str]) -> None:
        found.append((info, titles))
        for child in scan.find_children(info.folder, info.root):
            walk(child, [*titles, child.title])

    for group in scan.find_modules(scan.roots_from_config(home, config.roots)):
        for info in group.modules:
            walk(info, [info.title])
    return found


def why_not(info: ModuleInfo, roots: list[Root]) -> str | None:
    """這個模組不補那一小段的原因；要補就回 None。狀態頁也用這一份。"""
    if info.file.is_symlink():
        return "是符號連結"
    if (info.folder / ".origin").exists():
        return "工作坊裝來的"  # 補了會變「已修改」（D77）
    if info.level == "here" and info.name in BUNDLED:
        return "隨附模組"
    if any(r.level == "extra" and r.path == info.root for r in roots):
        return "在 ROOTS 另外加的資料夾裡"  # 那一小段在那裡找不到 iPLoT
    return None


def _links(roots: list[Root], found: list[tuple[ModuleInfo, list[str]]]) -> list[str]:
    """根目錄與模組資料夾裡，指向模組的符號連結資料夾（掃描不把它們當模組）；回一路的名稱。"""
    places = [(r.path, []) for r in roots] + [(info.folder, titles) for info, titles in found]
    names = []
    for folder, titles in places:
        with contextlib.suppress(OSError):
            for p in sorted(folder.iterdir()):
                if not p.name.startswith(".") and p.is_symlink() and (p / scan.MARKER).is_file():
                    names.append(" › ".join([*titles, p.name]))
    return names


def _lock(path: Path, now) -> bool:
    """拿鎖；別人拿著而且不到 STALE 秒就回 False。"""
    for _ in range(2):
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            with contextlib.suppress(OSError):
                if now() - path.stat().st_mtime <= STALE:
                    return False
                path.unlink()
    return False


def _write(path: Path, text: str) -> None:
    """先寫暫存檔再換上去：紀錄永遠不會只寫到一半。"""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def patched(folder: Path) -> set[str]:
    """.patched 記著的模組資料夾（補過、或本來就有那一小段的）；讀不到就當作沒有。"""
    try:
        data = json.loads((folder / PATCHED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {s for s in data if isinstance(s, str)} if isinstance(data, list) else set()


def sync(home: Path, config: Config, python: str, folder: Path, platform: str = sys.platform,
         now=time.time) -> list[str]:
    """同步一次（folder 是 modules/互通）。回這一次的問題，一個一句；有人正在同步就跳過、回空清單。"""
    lock = folder / LOCK
    if not _lock(lock, now):
        return []
    try:
        problems: list[str] = []
        roots = scan.roots_from_config(home, config.roots)
        found = modules(home, config)
        done = patched(folder)
        before = set(done)
        for info, titles in found:
            reason, name = why_not(info, roots), " › ".join(titles)
            if reason == "是符號連結":
                problems.append(f"{name}：是符號連結，沒補")
            if reason or str(info.folder) in done:
                continue
            try:
                snippet.add(info.file, config.history_keep)
                done.add(str(info.folder))
            except SyntaxError:
                problems.append(f"{name}：有語法錯誤，沒補")
            except (OSError, ValueError) as exc:
                problems.append(f"{name}：沒補：{exc}")
        problems += [f"{name}：是符號連結，沒補" for name in _links(roots, found)]
        try:
            if done != before:
                _write(folder / PATCHED, json.dumps(sorted(done), ensure_ascii=False, indent=1))
        except OSError as exc:
            problems.append(f"紀錄寫不進去：{exc}")
        if platform == "darwin":
            wanted = shortcut.names([(titles, info.folder) for info, titles in found
                                     if not (info.level == "here" and info.name == SYSTEM_MODULE)])
            problems += shortcut.sync(folder / shortcut.FOLDER, wanted, python, folder / "run.py")
        try:
            if problems:
                _write(folder / ERRORS, "".join(p + "\n" for p in problems))
            else:
                (folder / ERRORS).unlink(missing_ok=True)
        except OSError as exc:
            problems.append(f"紀錄寫不進去：{exc}")
        return problems
    finally:
        lock.unlink(missing_ok=True)
