"""「更新」的做法：抓 update.json、下載並驗證 zip、備份、換掉核心的四樣東西。
這裡都是普通的函式，旁邊的 iplot.py 只負責把它們串起來、把結果說給人聽。

只換 PARTS 列的四樣。config.py、custom.css、modules/、logs/、lib/ 一律不碰，iPLoT 資料夾以外的東西也不碰（D69）。"""
import hashlib
import json
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

PARTS = ("core", "ui", "main.py", "requirements")  # 更新會換掉的東西；其他都是使用者的


def _open(url, timeout):
    """打開網址（https://、file:// 都行）。網址裡的中文與空白先寫成 %XX：urllib 只收 ASCII 的網址。"""
    return urllib.request.urlopen(urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~"), timeout=timeout)


def fetch_json(url, timeout=15):
    """讀 update.json，回一個 dict；內容不是 JSON、或不是一個物件就丟 ValueError。"""
    with _open(url, timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("內容不是一個 JSON 物件")
    return data


def newer(current, latest):
    """latest 這個版本是不是比 current 新：用 . 切開，一段一段當整數比。看不懂的版本號一律當作不比較新。"""
    try:
        return tuple(int(p) for p in latest.split(".")) > tuple(int(p) for p in current.split("."))
    except (ValueError, AttributeError):
        return False


def installed_version(home):
    """磁碟上現在那一份核心的版本（core/__init__.py 裡的 __version__）；讀不到回 None。
    剛更新完、還沒重新啟動時，它已經是新版，而執行中的程式（app.version）還是舊的。"""
    try:
        text = (Path(home) / "core" / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return None
    found = re.search(r"""^__version__\s*=\s*["']([^"']+)["']""", text, re.M)
    return found.group(1) if found else None


def download(url, dest, sha256, timeout=60):
    """把 url 下載到 dest，回 dest。內容的 sha256 對不上就把 dest 刪掉、丟 ValueError：不留一個不可信的檔。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with _open(url, timeout) as r, dest.open("wb") as f:
        for chunk in iter(lambda: r.read(1 << 16), b""):
            digest.update(chunk)
            f.write(chunk)
    if digest.hexdigest() != str(sha256).lower():
        dest.unlink()
        raise ValueError("下載的檔案跟 update.json 寫的 sha256 對不上")
    return dest


def backup(home, old_version):
    """把現在的四樣複製到 home/.backup/<舊版本>-<日期時間>/，回那個資料夾。要回到舊版，把裡面的東西搬回去就是。"""
    stamp = f"{old_version}-{datetime.now():%Y%m%d-%H%M%S}"
    dest, n = home / ".backup" / stamp, 1
    while dest.exists():
        n += 1
        dest = home / ".backup" / f"{stamp}-{n}"
    dest.mkdir(parents=True)
    for name in PARTS:
        source = home / name
        if source.is_dir():
            shutil.copytree(source, dest / name, ignore=shutil.ignore_patterns("__pycache__"))
        elif source.exists():
            shutil.copy2(source, dest / name)
    return dest


def apply(home, zip_path):
    """把 zip 裡的四樣換進 home。zip 的最上層要剛好是一個資料夾（交付用的包是 iPLoT-vX.Y.Z/），裡面四樣都要有，
    否則丟 ValueError、什麼都不動。先解到 home/.update-tmp/，四樣各自搬到 <名稱>.new，再逐一改名換上去：
    中途出事也不會留下只換了一半的 core/。做完清掉暫存。"""
    tmp = home / ".update-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        tops = list(tmp.iterdir())
        if len(tops) != 1 or not tops[0].is_dir():
            raise ValueError("zip 的最上層應該只有一個資料夾")
        missing = [name for name in PARTS if not (tops[0] / name).exists()]
        if missing:
            raise ValueError("zip 裡少了：" + "、".join(missing))
        for name in PARTS:
            _remove(home / f"{name}.new")
            shutil.move(str(tops[0] / name), str(home / f"{name}.new"))
        for name in PARTS:
            _remove(home / f"{name}.old")
            if (home / name).exists():
                (home / name).rename(home / f"{name}.old")
            (home / f"{name}.new").rename(home / name)
            _remove(home / f"{name}.old")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _remove(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
