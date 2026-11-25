"""「更新」的做法：抓 update.json、下載並驗證 zip、備份、換掉核心。
這裡都是普通的函式，旁邊的 iplot.py 只負責把它們串起來、把結果說給人聽。

只換 PARTS 列的四樣，與 iPLoT 1.0 起在 modules/ 裡的核心（D167，長相見 kernels）。config.py、custom.css、
其他模組、logs/、lib/ 一律不碰，iPLoT 資料夾以外的東西也不碰（D69）。其他隨附模組由新的核心第一次啟動時照包換（D156）。"""
import contextlib
import errno
import hashlib
import http.client
import json
import os
import re
import shutil
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

PARTS = ("core", "ui", "main.py", "requirements")  # iPLoT 資料夾最上層會換掉的東西；1.0 起 core、ui 是種子（D167）
ORDER = ("ui", "main.py", "requirements", "core")  # 換上去的順序：帶著版本號的最後才換（1.0 起是 modules/ 裡的核心）
TRASH = ".update-old"  # 換下來的舊版先改名成 .update-old-<名稱>-<n> 再刪
# 連線這一段會遇到的錯：連不上、逾時、連到一半斷掉、伺服器沒回話。iplot.py 把它們說成一句話
NETWORK = (OSError, http.client.HTTPException)


def _context():
    """驗證 https 憑證用的設定。python.org 的 macOS Python 預設沒有根憑證（要另外執行 Install Certificates.command），
    那樣每個 https 網址都會驗證失敗；憑證庫是空的時候，改用 macOS 自己的那一份。驗證本身不關。"""
    context = ssl.create_default_context()
    if not context.cert_store_stats()["x509_ca"] and os.path.exists("/etc/ssl/cert.pem"):
        context.load_verify_locations("/etc/ssl/cert.pem")
    return context


def plain(exc):
    """連不上、下載不下來、寫不進去的原因，一句中文，後面接現在可以怎麼做。不給人看 Python 的英文原文與錯誤代碼。
    網路的三種失敗各一句：沒有網路、逾時、網站回了錯誤（帶代碼）；另外有憑證不對、磁碟與權限。"""
    reason = getattr(exc, "reason", exc)
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        what = ("找不到那個檔案" if code == 404 else "網站不讓我們讀，或短時間內被問太多次" if code in (401, 403, 429)
                else "網站暫時有問題" if code >= 500 else "網站不接受這個要求")
        return f"網站回了錯誤（{code}）：{what}。晚一點再試一次"
    if any(isinstance(e, TimeoutError) for e in (exc, reason)):
        return "連線逾時了，網路可能太慢或不穩。確認網路之後再試一次"
    if any(isinstance(e, ssl.SSLError) for e in (exc, reason)):
        return "網站的憑證驗證不過（電腦的日期時間不對，或網路被擋住時會這樣）。確認之後再試一次"
    if isinstance(reason, FileNotFoundError):
        return "找不到那個檔案，網址可能寫錯了"
    code = getattr(reason, "errno", None)
    if code == errno.ENOSPC:
        return "磁碟滿了。清出一些空間之後再試一次"
    if code in (errno.EACCES, errno.EPERM, errno.EROFS):
        return "沒有權限寫進 iPLoT 這個資料夾。確認它可以寫入之後再試一次"
    if isinstance(reason, (socket.gaierror, ConnectionRefusedError)) or isinstance(exc, urllib.error.URLError):
        return "連不上網站，可能是沒有網路。確認網路之後再試一次"
    if isinstance(exc, (http.client.HTTPException, ConnectionError)):
        return "連線到一半斷了，網路可能不穩。確認網路之後再試一次"
    return "讀寫時出了意外。再試一次；還是不行，請回報這個問題"


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


def check(info):
    """update.json 裡的版本、zip 的網址、sha256，回 (version, zip_url, sha256)。
    少了哪一項丟 KeyError；不是文字（null、數字）丟 ValueError。"""
    values = tuple(info[key] for key in ("version", "zip_url", "sha256"))
    if not all(isinstance(value, str) for value in values):
        raise ValueError("update.json 裡的 version、zip_url、sha256 應該都是文字")
    return values


def newer(current, latest):
    """latest 這個版本是不是比 current 新：用 . 切開，一段一段當整數比。看不懂的版本號一律當作不比較新。"""
    try:
        return tuple(int(p) for p in latest.split(".")) > tuple(int(p) for p in current.split("."))
    except (ValueError, AttributeError):
        return False


def kernels(root):
    """root/modules/ 底下長得像核心的資料夾（有 core/__init__.py 與 ui/start.py，D167），回 "modules/<名字>" 的清單。
    看長相、不看名字（規則 2）；1.0 以前的 iPLoT 沒有，是空的。換到一半留下的 .<名字>.new／.old 也認（收拾用）。"""
    found = set()
    with contextlib.suppress(OSError):
        for folder in Path(root, "modules").iterdir():
            name = folder.name
            for end in (".new", ".old"):
                if name.startswith(".") and name.endswith(end):
                    name = name[1:-len(end)]
            if (folder / "core" / "__init__.py").is_file() and (folder / "ui" / "start.py").is_file():
                found.add(f"modules/{name}")
    return sorted(found)


def parts(root):
    """root 這一份 iPLoT 要換的東西：最上層的四樣，加上 modules/ 裡的核心（排最後：它帶著版本號）。"""
    return [*PARTS, *kernels(root)]


def _side(home, name, end):
    """name 換到一半的 .new／.old 放哪裡：最上層的照舊是 <名稱>.old；modules/ 裡的核心是 modules/.<名稱>.old，
    點開頭的不會被當成一個模組掃出來。"""
    path = Path(home, name)
    return path.with_name(f".{path.name}{end}") if "/" in name else Path(home, f"{name}{end}")


def installed_version(home):
    """磁碟上現在那一份核心的版本（modules/ 裡的核心，1.0 以前是最上層 core/__init__.py 的 __version__）；讀不到回 None。
    剛更新完、還沒重新啟動時，它已經是新版，而執行中的程式（app.version）還是舊的。"""
    texts = []
    for name in [*reversed(kernels(home)), ""]:
        with contextlib.suppress(OSError):
            texts.append((Path(home) / name / "core" / "__init__.py").read_text(encoding="utf-8"))
    if not texts:
        return None
    text = texts[0]
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
    """把現在要換的東西（parts）複製到 home/.backup/<舊版本>-<日期時間>/，回那個資料夾。要回到舊版，把裡面的東西搬回去就是。"""
    stamp = f"{old_version}-{datetime.now():%Y%m%d-%H%M%S}"
    dest, n = home / ".backup" / stamp, 1
    while dest.exists():
        n += 1
        dest = home / ".backup" / f"{stamp}-{n}"
    dest.mkdir(parents=True)
    for name in parts(home):
        source = home / name
        if source.is_dir():
            shutil.copytree(source, dest / name, ignore=shutil.ignore_patterns("__pycache__", ".local"))
        elif source.exists():
            shutil.copy2(source, dest / name)
    return dest


def _restore(home):
    """把沒做完的交換收回來（上一次換到一半程式被關掉、或這一次換到一半出錯）。
    還有任何 <名稱>.new 就是沒換完（core 最後換，換完就沒有 .new 了）：留著的 <名稱>.old 放回去、.new 丟掉，
    四樣回到完整的舊版。.new 等 .old 全部放回去之後才丟：放回的途中程式被關掉，下一次還看得到 .new，就知道還沒收完。
    沒有 .new 就是上一次已經全部換好、只是舊的沒刪掉：那些 .old 不放回去，改名再刪。"""
    names = parts(home)
    if any(_side(home, name, ".new").exists() for name in names):
        for name in names:
            if _side(home, name, ".old").exists():
                _remove(home / name)
                _side(home, name, ".old").rename(home / name)
        for name in names:
            _remove(_side(home, name, ".new"))
    _discard(home)


def _discard(home):
    """丟掉換下來的舊版：每個 <名稱>.old 先在原地改名成 .update-old-<名稱>-<n>，再刪掉。
    改了名就不會再被當成舊版放回去；刪不掉的（唯讀的資料夾）留著那個名字，下一次更新再刪一次。
    名字留在同一層：把唯讀的資料夾搬進別的資料夾底下會被拒絕（要改它裡面的「..」）。"""
    for name in parts(home):
        old = _side(home, name, ".old")
        if old.exists():
            n, label = 1, Path(name).name
            while old.with_name(f"{TRASH}-{label}-{n}").exists():
                n += 1
            old.rename(old.with_name(f"{TRASH}-{label}-{n}"))
    for trash in [*home.glob(f"{TRASH}-*"), *home.glob(f"modules/{TRASH}-*")]:
        if trash.is_dir() and not trash.is_symlink():
            shutil.rmtree(trash, ignore_errors=True)
        else:
            with contextlib.suppress(OSError):
                trash.unlink()


def apply(home, zip_path):
    """把 zip 裡的四樣換進 home。zip 的最上層要剛好是一個資料夾（交付用的包是 iPLoT-vX.Y.Z/），裡面四樣都要有，
    否則丟 ValueError、什麼都不動。先解到 home/.update-tmp/，四樣各自搬到 <名稱>.new，再逐一改名換上去
    （舊的先改名成 <名稱>.old，全部換完才改名成 .update-old-<名稱>-<n> 刪掉）。換到一半出錯就全部放回去：要嘛四樣都是新的，要嘛都是舊的。
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
        kernel = kernels(tops[0])
        try:
            for name in [*PARTS, *kernel]:
                shutil.move(str(tops[0] / name), str(_side(home, name, ".new")))
            for name in [*ORDER, *kernel]:
                if (home / name).exists():
                    (home / name).rename(_side(home, name, ".old"))
                _side(home, name, ".new").rename(home / name)
                keep = _side(home, name, ".old") / ".local"  # 核心記的「上一份開得起來的」跟著留下：新的開不起來時退回它
                if "/" in name and keep.is_dir() and not (home / name / ".local").exists():
                    keep.rename(home / name / ".local")
        except OSError:
            _restore(home)
            raise
        with contextlib.suppress(OSError):  # 全部換好了，舊的才丟；丟不掉也不算失敗（下次更新開頭會再收一次）
            _discard(home)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def unfinished(home):
    """換到一半留下來、要用手整理的東西：還在的 <名稱>.old、<名稱>.new，與不見了的那幾樣。都沒有就是空的清單。"""
    names = parts(home)
    left = [_side(home, name, end).relative_to(home).as_posix() for name in names for end in (".old", ".new")
            if _side(home, name, end).exists()]
    return left + [name for name in names if not (home / name).exists()]


def _remove(path):
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
