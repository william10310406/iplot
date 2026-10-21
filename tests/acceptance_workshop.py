"""0.5.0 的驗收（規格 13.6）裡可以自動做的部分，對真的網址跑（D-g）：每發一版都跑得了。pytest 不收，跟 smoke.py 一樣自己跑。

    python3 tests/acceptance_workshop.py [--published ../iplot-workshop] [--keep <資料夾>]

一、網路上的檔：照 config.py 的 UPDATE_URL、WORKSHOP_URL，用工作坊自己的 _context() 經 urllib 下載。Pages 剛推完要等
    一兩分鐘：照 UPDATE_URL 輪詢到 update.json 跟 --published（publish.py --out 的那個資料夾）裡的一樣為止（只比這一個），
    最多 10 分鐘。index.json 用這一版的 workshop.read_listing 讀，modules 要是空的、要有 notice；核心那一頁從 UPDATE_URL
    那一層拿；核心 zip 與每個上傳的 zip，sha256 要跟 json 寫的一樣。
二、真的視窗：把這個 iPLoT 資料夾整個複製到暫存處（真的工作樹不動），core/__init__.py 改成 0.4.9，config.py 用隨附的
    （也就是真的網址），刪掉複本的「打開核心原始碼」，PATH 最前面放空的 open、code（不在桌面上彈出 Finder、編輯器），
    跑複本的 main.py，用 evaluate_js 代替滑鼠：按「更新」從網路換成新版、.backup/ 長出來、按「重新啟動」（真的 os.execv）
    之後標題是新版；打開「工作坊」：清單上的每一列、notice、每一列的上傳者、有 notes 的列有「這一版」；
    從網路裝「打開核心原始碼」：裝好的資料夾裡有 .origin、.unconfirmed、CHANGELOG.md，關掉清單頁格子出現。
每一項印出證據（句子、sha256、pid）。全部通過結束碼 0。要人眼看的（確認框長相、Safari 開那一頁、Wi-Fi 關掉）不在這裡。
要等設計第 9.3 節的種子收完、網站更新之後才跑（要從清單裝「打開核心原始碼」）。

同一個檔也是驅動：複本的 Python 由 sitecustomize 把這個檔載進去，在背景執行緒裡呼叫 drive()。"""

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
NAME = "打開核心原始碼"
DBL = ("(t => { t.dispatchEvent(new MouseEvent('click', {bubbles: true, detail: 1})); "
       "t.dispatchEvent(new MouseEvent('click', {bubbles: true, detail: 2})); })")
TILE = "[...document.querySelectorAll('.tile')].find(t => t.querySelector('.label').textContent === %r)"
LOGS = "[...document.querySelectorAll('.entry .t')].map(e => e.firstChild ? e.firstChild.textContent : '')"
ROWS = ("[...document.querySelectorAll('#list tr')].map(r => [r.querySelector('b').textContent, "
        "r.querySelector('.state').textContent, [...r.querySelectorAll('button')].map(b => b.textContent), "
        "r.querySelector('.notes') ? r.querySelector('.notes').textContent : null, "
        "r.querySelector('.author') ? r.querySelector('.author').textContent : null])")
HOOK = """import os, threading, importlib.util
if os.environ.get("IPLOT_ACCEPT_DIR"):
    spec = importlib.util.spec_from_file_location("acceptance_workshop", os.environ["IPLOT_ACCEPT_SCRIPT"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    threading.Thread(target=module.drive, daemon=True).start()
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def until(fn, timeout=10.0, step=0.1):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 —— 視窗還沒好、頁面還在載入
            pass
        time.sleep(step)
    return False


# ---------- 驅動：在複本的 iPLoT 程序裡跑 ----------

def record(item, ok, evidence):
    acc = Path(os.environ["IPLOT_ACCEPT_DIR"])
    with (acc / "results.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"item": item, "ok": bool(ok), "evidence": evidence, "pid": os.getpid()}, ensure_ascii=False) + "\n")


def drive():
    acc, home = Path(os.environ["IPLOT_ACCEPT_DIR"]), Path(os.environ["IPLOT_ACCEPT_HOME"])
    if not until(lambda: "webview" in sys.modules and sys.modules["webview"].windows, 90):
        return
    webview = sys.modules["webview"]
    win = webview.windows[0]
    js = win.evaluate_js
    if not until(lambda: js("document.querySelectorAll('.tile').length") > 3, 30):
        return record("面板", False, "面板沒有出現格子")
    time.sleep(1.5)
    logs = lambda: js(LOGS) or []  # noqa: E731
    stage = (acc / "stage").read_text(encoding="utf-8").strip()
    try:
        if stage == "update":
            update(acc, home, webview, js, logs)
        else:
            workshop(acc, home, webview, js, logs)
    except Exception:  # noqa: BLE001
        import traceback
        record(f"驅動（{stage}）", False, traceback.format_exc())
    finally:
        if stage != "update":
            (acc / "stage").write_text("done", encoding="utf-8")
            close(win)


def close(window):
    from PyObjCTools import AppHelper
    AppHelper.callAfter(lambda: window.native.performClose_(None))


def answer_dialog(js, ok):
    if not until(lambda: js("!document.getElementById('scrim').hidden")):
        return None
    title = js("document.getElementById('dlgTitle').textContent")
    js(f"document.getElementById('{'dlgOk' if ok else 'dlgCancel'}').click()")
    return title


def update(acc, home, webview, js, logs):
    title = js("document.title")
    record("開出來的是舊版", title == "iPLoT v0.4.9", {"標題": title})
    n = len(logs())
    js(f"{DBL}({TILE % '更新'})")
    question = answer_dialog(js, True) or ""
    until(lambda: any(t.startswith(("已更新到", "沒有更新", "連不上")) for t in logs()[n:]), 120, 0.5)
    said = logs()[n:]
    backups = sorted(p.name for p in (home / ".backup").iterdir()) if (home / ".backup").exists() else []
    core = (home / "core" / "__init__.py").read_text(encoding="utf-8").strip()
    version = os.environ["IPLOT_ACCEPT_VERSION"]
    record("按「更新」從網路換成新版", f"有新版 {version}" in question and any(t.startswith(f"已更新到 {version}") for t in said)
           and f'"{version}"' in core and any(b.startswith("0.4.9-") for b in backups),
           {"確認框（前 200 字）": question[:200], "訊息區": said, ".backup/": backups, "磁碟上的 core/__init__.py": core})
    (acc / "pid").write_text(str(os.getpid()), encoding="utf-8")
    (acc / "stage").write_text("workshop", encoding="utf-8")
    js(f"{DBL}({TILE % '重新啟動'})")  # os.execv：同一個程序換成新版，sitecustomize 再載入這個檔、做下一段
    time.sleep(30)
    record("按「重新啟動」", False, "30 秒後還是舊的程序：os.execv 沒有發生")
    (acc / "stage").write_text("done", encoding="utf-8")
    close(webview.windows[0])


def workshop(acc, home, webview, js, logs):
    title, old_pid = js("document.title"), (acc / "pid").read_text(encoding="utf-8")
    version = os.environ["IPLOT_ACCEPT_VERSION"]
    record("重新啟動之後是新版", title == f"iPLoT v{version}" and str(os.getpid()) == old_pid,
           {"標題": title, "重新啟動前的 pid": old_pid, "現在的 pid（一樣表示是 os.execv 換掉的同一個程序）": os.getpid()})
    data = json.loads((acc / "index.json").read_text(encoding="utf-8"))
    index = data["modules"]
    js(f"{DBL}({TILE % '工作坊'})")
    if not until(lambda: len(webview.windows) >= 2, 30):
        return record("打開工作坊", False, {"訊息區": logs()[-3:]})
    page = webview.windows[1]
    until(lambda: page.evaluate_js("document.querySelectorAll('#list tr').length") > 0, 15)
    rows = lambda: page.evaluate_js(ROWS)  # noqa: E731
    listing = rows()
    record("清單上的每一列", [r[0] for r in listing] == [e["name"] for e in index], {"清單頁": listing})
    notice = page.evaluate_js("document.querySelector('.notice') ? document.querySelector('.notice').textContent : null")
    record("清單最上面那一行是 notice", notice == data["notice"], {"頁面上": notice, "index.json 的 notice": data["notice"]})
    ws = load_workshop()
    shown_by = {r[0]: r[4] for r in listing}
    record("每一列有上傳者", all(shown_by[e["name"]] == ws.uploader(e.get("author")) for e in index) and all(r[4] for r in listing),
           {"上傳者": shown_by})
    shown = {r[0]: r[3] for r in listing}
    record("有 notes 的列有「這一版」", all(shown[e["name"]] == (f"這一版：{e['notes']}" if e.get("notes") else None) for e in index),
           {"這一版": shown})
    i = [r[0] for r in listing].index(NAME)
    before = listing[i]
    page.evaluate_js(f"document.querySelectorAll('#list tr')[{i}].querySelector('button').click()")
    done = until(lambda: rows()[i][1] == "已安裝", 120, 0.5)
    after = rows()[i]
    folder = home / "modules" / NAME
    files = sorted(p.name for p in folder.iterdir()) if folder.exists() else []
    origin = (folder / ".origin").read_text(encoding="utf-8") if (folder / ".origin").exists() else ""
    entry = next(e for e in index if e["name"] == NAME)
    record(f"從網路裝「{NAME}」", done and {".origin", ".unconfirmed", "CHANGELOG.md", "iplot.py"} <= set(files)
           and f"sha256: {entry['sha256']}" in origin and f"url: {entry['zip_url']}" in origin,
           {"按之前": before, "按之後": after, "資料夾裡的檔": files, ".origin": origin.splitlines()})
    close(page)
    tile = until(lambda: js(f"{TILE % NAME} !== undefined"), 15)
    record("關掉清單頁，格子出現", tile, {"格子": tile})


# ---------- 主程式：網路上的檔、複本、跑兩次 main.py ----------

def load_workshop():
    spec = importlib.util.spec_from_file_location("acceptance_workshop_module", SRC / "modules" / "工作坊" / "workshop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch(workshop, url):
    with workshop._open(url, 60) as r:
        return r.read()


def check_site(update_url, index_url, published, results, wait=600):
    """一、網路上的檔。回 (update.json, 清單, notice)；對不上或讀不懂就是 (None, None, "")。"""
    workshop = load_workshop()
    want = (published / "update.json").read_bytes() if published else None
    got = {}

    def ready():
        got["update.json"] = fetch(workshop, update_url)
        return want is None or got["update.json"] == want

    start = time.monotonic()
    fresh = until(ready, wait, 10 if wait > 60 else 0.1)
    waited = round(time.monotonic() - start)
    results.append(("網路上的 update.json 是剛發佈的那一份", fresh,
                    {"等了幾秒": waited, "比對的資料夾": str(published) if published else "（沒有給，不比）"}))
    if not fresh:
        return None, None, ""
    update = json.loads(got["update.json"])
    try:
        entries, notice = workshop.read_listing(index_url)
    except (ValueError, *workshop.NETWORK) as e:
        results.append(("index.json 用這一版的工作坊讀得懂", False, {"網址": index_url, "錯誤": repr(e)}))
        return None, None, ""
    results.append(("index.json 用這一版的工作坊讀得懂", True, {"網址": index_url, "幾筆": len(entries), "notice": notice}))
    raw = json.loads(fetch(workshop, index_url))
    results.append(("index.json 的 modules 是空的（0.5.1 的工作坊看到空清單）", raw.get("modules") == [],
                    {"modules": raw.get("modules")}))
    results.append(("清單最上面有 notice", bool(notice.strip()), {"notice": notice}))
    base = update_url.rpartition("/")[0]
    page = fetch(workshop, base + "/index.html").decode("utf-8")
    results.append(("核心那一頁（index.html）", "iPLoT 工作坊" in page and update["sha256"] in page and "誰都能上傳" in page,
                    {"網址": base + "/index.html", "大小": len(page)}))
    for label, url, expected in [(f"核心 zip（{update['version']}）", update["zip_url"], update["sha256"])] + [
            (f"模組 zip「{e['name']}」", e["zip_url"], e["sha256"]) for e in entries]:
        data = fetch(workshop, url)
        results.append((label, sha(data) == expected, {"網址": url, "sha256": sha(data), "json 寫的": expected, "大小": len(data)}))
    return update, entries, notice


def run_copy(acc, home, version, stubs):
    env = dict(os.environ, IPLOT_ACCEPT_DIR=str(acc), IPLOT_ACCEPT_HOME=str(home), IPLOT_ACCEPT_VERSION=version,
               IPLOT_ACCEPT_SCRIPT=str(Path(__file__).resolve()), PYTHONPATH=str(acc / "hook"),
               PATH=f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}")
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    with (acc / "main.out").open("w") as out, (acc / "main.err").open("w") as err:
        proc = subprocess.Popen([sys.executable, "main.py"], cwd=home, env=env, stdout=out, stderr=err)
        try:
            proc.wait(timeout=600)
        except subprocess.TimeoutExpired:
            proc.kill()
            return False
    return True


def main(argv):
    import argparse
    parser = argparse.ArgumentParser(description="0.5.0 驗收的自動部分，對 config.py 裡真的網址跑")
    parser.add_argument("--published", default=str(SRC.parent / "iplot-workshop"),
                        help="publish.py --out 的那個資料夾：等網路上的 update.json 跟它一樣才開始（沒有這個資料夾就不比）")
    parser.add_argument("--keep", help="複本放在這個新的（或空的）資料夾；跑完留著，人工驗收可以接著用。預設是暫存資料夾")
    args = parser.parse_args(argv)
    keep = Path(args.keep).resolve() if args.keep else None
    if keep and keep.exists() and (not keep.is_dir() or any(keep.iterdir())):  # 不刪別人的東西：只用新的或空的資料夾
        print(f"--keep 要給一個還不存在、或空的資料夾；{keep} 裡已經有東西，什麼都沒做")
        return 1
    sys.path.insert(0, str(SRC))
    from core.core import load_config
    config, err = load_config(SRC / "config.py")
    if err or not (config.update_url and config.workshop_url):
        print("config.py 的 UPDATE_URL、WORKSHOP_URL 要是網址")
        return 1
    published = Path(args.published) if Path(args.published, "update.json").is_file() else None
    results = []
    update, index, notice = check_site(config.update_url, config.workshop_url, published, results)
    if update:
        acc = keep or Path(tempfile.mkdtemp(prefix="iplot-acceptance-")).resolve()
        acc.mkdir(parents=True, exist_ok=True)
        home = acc / "iPLoT"
        shutil.copytree(SRC, home, symlinks=True, ignore=shutil.ignore_patterns(
            ".git", ".venv", "交付", ".superpowers", "spikes", "__pycache__", ".pytest_cache", ".ruff_cache"))
        init = home / "core" / "__init__.py"
        init.write_text(init.read_text(encoding="utf-8").replace(f'"{update["version"]}"', '"0.4.9"'), encoding="utf-8")
        shutil.rmtree(home / "modules" / NAME)
        (acc / "hook").mkdir()
        (acc / "hook" / "sitecustomize.py").write_text(HOOK, encoding="utf-8")
        stubs = acc / "stubs"
        stubs.mkdir()
        for name in ("open", "code"):
            (stubs / name).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (stubs / name).chmod(0o755)
        (acc / "index.json").write_text(json.dumps({"modules": index, "notice": notice}, ensure_ascii=False), encoding="utf-8")
        (acc / "stage").write_text("update", encoding="utf-8")
        finished = run_copy(acc, home, update["version"], stubs)
        for line in (acc / "results.jsonl").read_text(encoding="utf-8").splitlines() if (acc / "results.jsonl").exists() else []:
            r = json.loads(line)
            evidence = r["evidence"] if isinstance(r["evidence"], dict) else {"說明": r["evidence"]}  # 失敗的路上記的是一句話
            results.append((r["item"], r["ok"], {**evidence, "pid": r["pid"]}))
        stage = (acc / "stage").read_text(encoding="utf-8").strip()
        results.append(("複本的 iPLoT 自己結束", finished and stage == "done", {"複本": str(home), "最後的階段": stage,
                        "stderr": (acc / "main.err").read_text(encoding="utf-8").strip().splitlines()[-5:]}))
    for item, ok, evidence in results:
        print(("通過 " if ok else "失敗 ") + item)
        for key, value in evidence.items():
            print(f"      {key}：{json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value}")
    passed = sum(ok for _, ok, _ in results)
    print(f"結果：{passed}/{len(results)} 通過")
    return 0 if results and passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
