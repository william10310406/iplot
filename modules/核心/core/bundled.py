"""隨附模組跟著核心一起更新（D156）：「更新」下載的包留在 .backup/download-<版本>.zip，新版核心第一次啟動時，
照那個包把 modules/ 裡隨附的模組換成新版。只動「沒改過」的檔案：安裝的檔案的 sha256 是任何一版發出去過的
（core/bundled_hashes.json）才換；不認得的就是使用者改過的，整個模組都不換，只說一句。工作坊裝來的（有 .origin）、
包裡沒有的檔（資料、設定、.history、捷徑）、使用者刪掉的整個模組，一律不碰；
這一版才新加的隨附模組（雜湊表的 .introduced 比上次處理過的版本新）本機沒有就裝上（D159）；
拿掉的（.retired）本機那一份沒改過就移到備份（D171）。
哪些是隨附的，看雜湊表裡有哪些模組：核心自己不知道任何一個模組的名字（D169）。"""

import contextlib
import hashlib
import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path

from . import scan
from .errors import reason
from .text import T

MARKER = ".bundled-version"  # 記著哪一版核心已經處理過隨附模組；沒有這個檔的舊安裝，第一次會處理
HASHES = Path(__file__).with_name("bundled_hashes.json")
SKIP = {"__pycache__", ".DS_Store"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package_files(package: Path, version: str, names: set[str]) -> dict[str, dict[str, bytes]]:
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
            if (len(parts) < 4 or parts[1] != "modules" or parts[2] not in names or name.endswith("/")
                    or ".." in parts or any(p in SKIP for p in parts)):
                continue
            found.setdefault(parts[2], {})["/".join(parts[3:])] = z.read(name)
        return found


def sync(home: Path, version: str, known: dict | None = None) -> list[str]:
    """處理這一版核心的隨附模組，回要說給使用者聽的句子（沒事可說是空的）。已經處理過、沒有包（新下載的，模組本來就是新的）、
    包不對，都只記下版本號就回來。換的過程出錯（OSError）：那個模組放回原來的樣子，不記版本號，下次啟動再試。"""
    marker, package, before = home / MARKER, home / ".backup" / f"download-{version}.zip", None
    with contextlib.suppress(OSError):
        if (before := marker.read_text(encoding="utf-8").strip()) == version:
            return []
    known = json.loads(HASHES.read_text(encoding="utf-8")) if known is None else known
    names = {n for n in known if not n.startswith(".")} | set(known.get(".introduced", {}))  # 隨附的：表裡有的（D169）
    try:
        files = package_files(package, version, names) if package.is_file() else {}
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError):
        files = {}
    done, notes, retry = [], [], False
    backup = home / ".backup" / f"{version}-bundled-{time.strftime('%Y%m%d-%H%M%S')}"
    for name, new in sorted(files.items()):
        folder = home / "modules" / name
        added = not folder.exists() and _added_since(known.get(".introduced", {}).get(name), before, version)
        if not added and (not scan.is_module(folder) or (folder / ".origin").exists()):
            continue  # 包裡有、本機沒有的、以前就有的模組是使用者刪的，不補；新加的（例如 0.8 的「整理」）才裝
        todo, modified = (dict(new) if added else {}), False
        for rel, data in () if added else new.items():
            path = folder / rel
            if path.is_symlink() or path.is_dir():
                modified = True
            elif path.is_file():
                have = _sha(path.read_bytes())
                if have != _sha(data):  # 雜湊表自己不在表裡（每一版都變）：一律照包裡的換
                    modified = modified or (have not in known.get(name, {}).get(rel, ()) and path.name != HASHES.name)
                    todo[rel] = data
            else:
                todo[rel] = data
        if modified:
            notes.append(T["bundled_modified"].format(name=name, package=package.relative_to(home).as_posix()))
        elif todo:
            try:
                _install(folder, todo) if added else _write(folder, todo, backup / name)
            except OSError as exc:
                retry = True
                notes.append(T["bundled_failed"].format(name=name, message=reason(exc)))
            else:
                done.append(name)
    retired = [n for n in sorted(known.get(".retired", {})) if _retire(home / "modules" / n, known[".retired"][n], backup)]
    if retired:
        notes.append(T["bundled_retired"].format(names="、".join(retired), backup=backup.relative_to(home).as_posix()))
    if done:
        notes.insert(0, T["bundled_updated"].format(names="、".join(done), backup=backup.relative_to(home).as_posix()))
    if not retry:
        with contextlib.suppress(OSError):
            marker.write_text(version + "\n", encoding="utf-8")
    return notes


def _retire(folder: Path, entry: dict, backup: Path) -> bool:
    """這一版拿掉的隨附模組（雜湊表的 .retired，D171）：本機那一份每個檔都是發出去過的原樣，才整個移到 backup；
    改過的、工作坊裝來的（.origin）、移不動的都留著（下次啟動不再試，只是多一格舊按鈕）。"""
    if not scan.is_module(folder) or (folder / ".origin").exists():
        return False
    files = (p for p in folder.rglob("*") if p.is_file() and not any(x[0] == "." or x in SKIP for x in p.relative_to(folder).parts))
    if any(_sha(p.read_bytes()) not in entry["files"].get(p.relative_to(folder).as_posix(), ()) for p in files):
        return False
    try:
        backup.mkdir(parents=True, exist_ok=True)
        shutil.move(folder, backup / folder.name)
    except OSError:
        return False
    return True


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", text)[:3])


def _added_since(introduced: str | None, before: str | None, version: str) -> bool:
    """隨附模組 introduced 那一版才加進來（bundled_hashes.json 的 .introduced）：上次處理過的是更舊的版本才算新的。
    沒有 .bundled-version 的舊安裝不知道上次是哪一版，只認這一版才加的。"""
    if introduced is None:
        return False
    return _version(introduced) > _version(before) if before else _version(introduced) == _version(version)


def _install(folder: Path, files: dict[str, bytes]) -> None:
    """新加的隨附模組：整個寫進旁邊的隱藏暫存資料夾，寫完才換名成 folder；寫到一半失敗就丟掉暫存的，下次啟動再試。"""
    tmp = folder.with_name(f".{folder.name}.iplot-new")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        for rel, data in files.items():
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_bytes(data)
        os.replace(tmp, folder)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
                path.write_bytes(saved.read_bytes()) if saved else path.unlink(missing_ok=True)
        raise
