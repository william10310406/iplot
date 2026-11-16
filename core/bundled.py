"""隨附模組跟著核心一起更新（D156）：「更新」下載的包留在 .backup/download-<版本>.zip，新版核心第一次啟動時，
照那個包把 modules/ 裡隨附的模組換成新版。只動「沒改過」的檔案：安裝的檔案的 sha256 是任何一版發出去過的
（core/bundled_hashes.json）才換；不認得的就是使用者改過的，整個模組都不換，只說一句。工作坊裝來的（有 .origin）、
包裡沒有的檔（資料、設定、.history、捷徑）、使用者刪掉的整個模組，一律不碰。"""

import contextlib
import hashlib
import json
import os
import re
import time
import zipfile
from pathlib import Path

from . import scan
from .errors import reason
from .text import BUNDLED, T

MARKER = ".bundled-version"  # 記著哪一版核心已經處理過隨附模組；沒有這個檔的舊安裝，第一次會處理
HASHES = Path(__file__).with_name("bundled_hashes.json")
SKIP = {"__pycache__", ".DS_Store"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package_files(package: Path, version: str) -> dict[str, dict[str, bytes]]:
    """包裡隨附模組的檔案：{模組名: {相對路徑: 內容}}。包不是這一版核心的（最上層不只一個資料夾、core/__init__.py 的版本不同）
    就回空的。路徑一律在 modules/<名稱>/ 底下，有 .. 或絕對路徑的丟掉。"""
    with zipfile.ZipFile(package) as z:
        tops = {n.split("/")[0] for n in z.namelist()}
        if len(tops) != 1:
            return {}
        top = tops.pop()
        init = z.read(f"{top}/core/__init__.py").decode("utf-8") if f"{top}/core/__init__.py" in z.namelist() else ""
        if not re.search(rf"""^__version__\s*=\s*["']{re.escape(version)}["']""", init, re.M):
            return {}
        found: dict[str, dict[str, bytes]] = {}
        for name in z.namelist():
            parts = name.split("/")
            if (len(parts) < 4 or parts[1] != "modules" or parts[2] not in BUNDLED or name.endswith("/")
                    or ".." in parts or any(p in SKIP for p in parts)):
                continue
            found.setdefault(parts[2], {})["/".join(parts[3:])] = z.read(name)
        return found


def sync(home: Path, version: str, known: dict | None = None) -> list[str]:
    """處理這一版核心的隨附模組，回要說給使用者聽的句子（沒事可說是空的）。已經處理過、沒有包（新下載的，模組本來就是新的）、
    包不對，都只記下版本號就回來。換的過程出錯（OSError）：那個模組放回原來的樣子，不記版本號，下次啟動再試。"""
    marker, package = home / MARKER, home / ".backup" / f"download-{version}.zip"
    with contextlib.suppress(OSError):
        if marker.read_text(encoding="utf-8").strip() == version:
            return []
    if known is None:
        known = json.loads(HASHES.read_text(encoding="utf-8"))
    try:
        files = package_files(package, version) if package.is_file() else {}
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError):
        files = {}
    done, notes, retry = [], [], False
    backup = home / ".backup" / f"{version}-bundled-{time.strftime('%Y%m%d-%H%M%S')}"
    for name, new in sorted(files.items()):
        folder = home / "modules" / name
        if not scan.is_module(folder) or (folder / ".origin").exists():
            continue
        todo, modified = {}, False
        for rel, data in new.items():
            path = folder / rel
            if path.is_symlink() or path.is_dir():
                modified = True
            elif path.is_file():
                have = _sha(path.read_bytes())
                if have != _sha(data):
                    modified = modified or have not in known.get(name, {}).get(rel, ())
                    todo[rel] = data
            else:
                todo[rel] = data
        if modified:
            notes.append(T["bundled_modified"].format(name=name, package=package.relative_to(home).as_posix()))
        elif todo:
            try:
                _write(folder, todo, backup / name)
            except OSError as exc:
                retry = True
                notes.append(T["bundled_failed"].format(name=name, message=reason(exc)))
            else:
                done.append(name)
    if done:
        notes.insert(0, T["bundled_updated"].format(names="、".join(done), backup=backup.relative_to(home).as_posix()))
    if not retry:
        with contextlib.suppress(OSError):
            marker.write_text(version + "\n", encoding="utf-8")
    return notes


def _write(folder: Path, todo: dict[str, bytes], backup: Path) -> None:
    """把 todo 的檔一個一個換上去（先寫暫存再換名），換之前先把舊的複製到 backup；出錯就把已經換的放回去再丟出去。"""
    changed: list[tuple[Path, Path | None]] = []
    try:
        for rel, data in todo.items():
            path, saved = folder / rel, backup / rel
            if path.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(path.read_bytes())
            else:
                saved = None
            changed.append((path, saved))
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".iplot-new")
            try:
                tmp.write_bytes(data)
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
    except OSError:
        for path, saved in changed:
            with contextlib.suppress(OSError):
                if saved:
                    path.write_bytes(saved.read_bytes())
                else:
                    path.unlink(missing_ok=True)
        raise
