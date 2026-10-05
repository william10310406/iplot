"""「更新」的做法：抓 update.json、下載並驗證 zip、備份、換掉核心的四樣東西。
這裡都是普通的函式，旁邊的 iplot.py 只負責把它們串起來、把結果說給人聽。

只換 PARTS 列的四樣。config.py、custom.css、modules/、logs/、lib/ 一律不碰，iPLoT 資料夾以外的東西也不碰（D69）。"""
import hashlib
import http.client
import json
import os
import re
import shutil
import ssl
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

PARTS = ("core", "ui", "main.py", "requirements")  # 更新會換掉的東西；其他都是使用者的
ORDER = ("ui", "main.py", "requirements", "core")  # 換上去的順序：core 帶著版本號，最後才換
# 連線這一段會遇到的錯：連不上、逾時、連到一半斷掉、伺服器沒回話。iplot.py 把它們說成一句話
NETWORK = (OSError, http.client.HTTPException)


def _context():
    """驗證 https 憑證用的設定。python.org 的 macOS Python 預設沒有根憑證（要另外執行 Install Certificates.command），
    那樣每個 https 網址都會驗證失敗；憑證庫是空的時候，改用 macOS 自己的那一份。驗證本身不關。"""
    context = ssl.create_default_context()
    if not context.cert_store_stats()["x509_ca"] and os.path.exists("/etc/ssl/cert.pem"):
        context.load_verify_locations("/etc/ssl/cert.pem")
    return context


def _open(url, timeout):
    """打開網址（https://、file:// 都行）。網址裡的中文與空白先寫成 %XX：urllib 只收 ASCII 的網址。"""
    return urllib.request.urlopen(urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~"), timeout=timeout,
                                  context=_context())


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


def _restore(home):
    """把換到一半的狀態收回來：還留著 <名稱>.old 的，舊的放回去；<名稱>.new 丟掉。之後四樣是完整的舊版。
    上一次換到一半程式被關掉、或這一次換到一半出錯，都靠這個。"""
    for name in PARTS:
        if (home / f"{name}.old").exists():
            _remove(home / name)
            (home / f"{name}.old").rename(home / name)
        _remove(home / f"{name}.new")


def apply(home, zip_path):
    """把 zip 裡的四樣換進 home。zip 的最上層要剛好是一個資料夾（交付用的包是 iPLoT-vX.Y.Z/），裡面四樣都要有，
    否則丟 ValueError、什麼都不動。先解到 home/.update-tmp/，四樣各自搬到 <名稱>.new，再逐一改名換上去
    （舊的先改名成 <名稱>.old，全部換完才刪）。換到一半出錯就全部放回去：要嘛四樣都是新的，要嘛都是舊的。
    core/ 最後換，所以「磁碟上的版本是新的」就代表四樣都換好了。做完清掉暫存。"""
    tmp = home / ".update-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    _restore(home)
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        tops = list(tmp.iterdir())
        if len(tops) != 1 or not tops[0].is_dir():
            raise ValueError("zip 的最上層應該只有一個資料夾")
        missing = [name for name in PARTS if not (tops[0] / name).exists()]
        if missing:
            raise ValueError("zip 裡少了：" + "、".join(missing))
        try:
            for name in PARTS:
                shutil.move(str(tops[0] / name), str(home / f"{name}.new"))
            for name in ORDER:
                if (home / name).exists():
                    (home / name).rename(home / f"{name}.old")
                (home / f"{name}.new").rename(home / name)
        except OSError:
            _restore(home)
            raise
        for name in PARTS:  # 全部換好了，舊的才丟；丟不掉也不算失敗（下次更新開頭會再收一次）
            shutil.rmtree(home / f"{name}.old", ignore_errors=True)
            if (home / f"{name}.old").is_file():
                (home / f"{name}.old").unlink()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _remove(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
