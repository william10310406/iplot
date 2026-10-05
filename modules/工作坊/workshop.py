"""「工作坊」的做法：讀索引、算每個模組在這台電腦上的狀態、下載安裝、覆蓋前把舊資料夾整個存起來。
這裡都是普通的函式，旁邊的 iplot.py 只負責串起來，page.html 是列出清單的那一頁。

規矩（D70）：只寫進自己裝的那個 modules/<名稱>/ 與暫存資料夾；覆蓋前，舊資料夾整個存進它自己的 .history/；
從這裡裝進來的模組帶著空檔案 .unconfirmed，第一次執行前 iPLoT 會先問一次。"""
import hashlib
import html
import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime

ORIGIN, UNCONFIRMED = ".origin", ".unconfirmed"
# 各台電腦自己的東西：不進包、不算進摘要、包裡夾帶了也不裝（跟 tools/publish.py 的 SKIP 要一樣）
SKIP = {".history", ".origin", ".unconfirmed", "__pycache__", ".DS_Store"}
LABELS = {"absent": "未安裝", "installed": "已安裝", "update": "可更新", "modified": "已修改", "unknown": "版本未知"}
BUTTONS = {"absent": "安裝", "update": "更新", "modified": "覆蓋", "unknown": "覆蓋"}  # 已安裝的沒有按鈕
CONFIRM = "需要確認"  # 已修改、版本未知的要先確認才覆蓋：page.html 看到這個回答就不會當成裝好了
NEEDED = ("name", "version", "zip_url", "sha256")  # 索引的每一筆至少要有這幾項


def _open(url, timeout):
    """打開網址（https://、file:// 都行）。網址裡的中文與空白先寫成 %XX：urllib 只收 ASCII 的網址。"""
    return urllib.request.urlopen(urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~"), timeout=timeout)


def read_index(url, timeout=15):
    """讀 index.json，回裡面的 modules 清單；格式不對（不是 JSON、沒有 modules、某一筆缺項）丟 ValueError。"""
    with _open(url, timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    entries = data.get("modules") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not all(isinstance(e, dict) and all(k in e for k in NEEDED) for e in entries):
        raise ValueError("index.json 的格式不對")
    return entries


def read_origin(folder):
    """讀模組資料夾裡的 .origin（一行一個「key: value」）。沒有這個檔回 None；
    讀不懂、或少了 url／version／sha256／digest 任何一項，回空的 dict（當作壞掉）。"""
    try:
        lines = (folder / ORIGIN).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}
    pairs = [line.partition(": ") for line in lines if line.strip()]
    data = {key: value for key, sep, value in pairs if sep}
    complete = len(data) == len(pairs) and all(k in data for k in ("url", "version", "sha256", "digest"))
    return data if complete else {}


def write_origin(folder, data):
    (folder / ORIGIN).write_text("".join(f"{key}: {value}\n" for key, value in data.items()), encoding="utf-8")


def _files(folder):
    """folder 裡算數的檔案（相對路徑, 路徑），照相對路徑排序；SKIP 裡的名字不管在哪一層都不算。"""
    found = [(p.relative_to(folder).as_posix(), p) for p in folder.rglob("*")
             if p.is_file() and not SKIP & set(p.relative_to(folder).parts)]
    return sorted(found)


def digest(folder):
    """資料夾內容的摘要：照相對路徑的順序，把「路徑＋內容」一個個餵進 sha256。改一個字、多一個檔都會變。"""
    h = hashlib.sha256()
    for rel, path in _files(folder):
        h.update(rel.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def _newer(current, latest):
    try:
        return tuple(int(p) for p in str(latest).split(".")) > tuple(int(p) for p in str(current).split("."))
    except ValueError:
        return False


def state(entry, modules_dir):
    """索引裡這一筆，在這台電腦上是什麼狀態：
    absent 沒有這個資料夾；unknown 資料夾在但不是從工作坊裝的（沒有 .origin）；
    modified 裝完之後內容變過（或 .origin 壞了）；update 沒改過、索引的版本比較新；installed 沒改過、已經是這一版。"""
    folder = modules_dir / entry["name"]
    if not folder.exists():
        return "absent"
    origin = read_origin(folder)
    if origin is None:
        return "unknown"
    if origin.get("digest") != digest(folder):
        return "modified"
    return "update" if _newer(origin["version"], entry["version"]) else "installed"


def _stamped(folder, suffix):
    """folder 底下一個帶日期時間的新檔名；同一秒內的第二個加 -2。"""
    stamp, n = f"{datetime.now():%Y%m%d-%H%M%S}", 1
    path = folder / f"{stamp}{suffix}"
    while path.exists():
        n += 1
        path = folder / f"{stamp}-{n}{suffix}"
    return path


def snapshot(folder):
    """把整個模組資料夾（.history/ 自己除外）壓成 .history/<日期時間>-folder.zip，回那個檔。"""
    (folder / ".history").mkdir(exist_ok=True)
    saved = _stamped(folder / ".history", "-folder.zip")
    files = [(p.relative_to(folder).as_posix(), p) for p in sorted(folder.rglob("*"))
             if p.is_file() and ".history" not in p.relative_to(folder).parts]
    with zipfile.ZipFile(saved, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, path in files:
            z.write(path, rel)
    return saved


def download(url, dest, sha256, timeout=60):
    """把 url 下載到 dest，回 dest。內容的 sha256 對不上就把 dest 刪掉、丟 ValueError。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with _open(url, timeout) as r, dest.open("wb") as f:
        for chunk in iter(lambda: r.read(1 << 16), b""):
            h.update(chunk)
            f.write(chunk)
    if h.hexdigest() != str(sha256).lower():
        dest.unlink()
        raise ValueError("下載的檔案跟索引寫的 sha256 對不上")
    return dest


def install(entry, modules_dir):
    """照索引的這一筆安裝（或覆蓋）一個模組，回安裝後的狀態。任何一步不對就丟 ValueError，模組資料夾不動：
    名稱要是單純的資料夾名；sha256 要對；zip 的最上層要剛好是 <名稱>/，裡面要有 iplot.py。
    資料夾已經在的話，先整個存進它的 .history/，再把包裡的檔案蓋上去（包裡沒有的舊檔案留著）。"""
    name = entry["name"]
    if not isinstance(name, str) or not name.strip() or name.startswith(".") or set(name) & set("/\\"):
        raise ValueError("索引裡的模組名稱不是單純的資料夾名")
    folder, tmp = modules_dir / name, modules_dir / ".workshop-tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        package = download(entry["zip_url"], tmp / "package.zip", entry["sha256"])
        with zipfile.ZipFile(package) as z:
            names = z.namelist()
            if any(not n.startswith(name + "/") or ".." in n.split("/") for n in names):
                raise ValueError(f"zip 的最上層不是「{name}/」")
            if f"{name}/iplot.py" not in names:
                raise ValueError("包裡沒有 iplot.py")
            z.extractall(tmp / "unpacked")
        if folder.exists():
            snapshot(folder)
        for rel, source in _files(tmp / "unpacked" / name):
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, folder / rel)
        write_origin(folder, {"url": entry["zip_url"], "version": entry["version"], "sha256": entry["sha256"],
                              "digest": digest(folder), "installed": f"{datetime.now():%Y-%m-%d %H:%M:%S}"})
        (folder / UNCONFIRMED).touch()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return state(entry, modules_dir)


def render(entries, modules_dir, template):
    """把索引變成 page.html 裡的一列列（放進 template 的 {rows}）。索引是從網路來的，裡面的字一律當文字，不當 HTML。"""
    rows = []
    for entry in entries:
        now = state(entry, modules_dir)
        name = html.escape(str(entry["name"]), quote=True)
        button = (f'<button type="button" data-name="{name}" data-ask="{int(now in ("modified", "unknown"))}">'
                  f"{BUTTONS[now]}</button>") if now in BUTTONS else ""
        rows.append(
            f'<tr><td class="icon">{html.escape(str(entry.get("icon") or ""))}</td>'
            f'<td><b>{name}</b><div class="desc">{html.escape(str(entry.get("description") or ""))}</div></td>'
            f'<td class="ver">{html.escape(str(entry["version"]))}</td>'
            f'<td class="state">{LABELS[now]}</td><td class="act">{button}</td></tr>')
    return template.replace("{rows}", "\n".join(rows))


class Api:
    """工作坊那一頁的 JS 呼叫的入口（pywebview.api.install）。屬性都以底線開頭：公開的只有 install。"""

    def __init__(self, app, entries, modules_dir):
        self._app, self._entries, self._modules_dir = app, entries, modules_dir

    def install(self, name, confirmed=False):
        """安裝、更新或覆蓋 name，回新的狀態（中文）。已修改、版本未知的要 confirmed 才覆蓋，否則回 CONFIRM、什麼都不動。
        出錯回一句「無法安裝：…」，不丟例外。"""
        entry = next((e for e in self._entries if e["name"] == name), None)
        if entry is None:
            return f"無法安裝：清單裡沒有「{name}」"
        try:
            if state(entry, self._modules_dir) in ("modified", "unknown") and not confirmed:
                return CONFIRM
            return LABELS[install(entry, self._modules_dir)]
        except zipfile.BadZipFile:
            return "無法安裝：下載的檔案不是 zip"
        except (urllib.error.URLError, TimeoutError) as exc:
            return f"無法安裝：連不上來源（{getattr(exc, 'reason', exc)}）"
        except (ValueError, KeyError, OSError) as exc:
            return f"無法安裝：{exc}"
