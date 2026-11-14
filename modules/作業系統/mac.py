"""macOS：全部用 open 指令；垃圾桶是 ~/.Trash。"""
import shutil
import subprocess
from pathlib import Path

NAME = "macOS"
GONE = "找不到「{path}」，可能被改名或刪掉了，沒有打開"


def _launch(argv, **kw):
    """啟動後不等。"""
    subprocess.Popen(argv, **kw)


def _there(app, path) -> bool:
    """路徑還在才打開；不在就在訊息區說一句。open 的錯誤只會印在看不到的終端機，使用者只會覺得按了沒反應（體驗 8a-01）。"""
    if Path(path).exists():
        return True
    app.log(GONE.format(path=path))
    return False


def open(app, path):
    """資料夾進 Finder，檔案用預設程式。"""
    if not _there(app, path):
        return
    _launch(["open", str(path)])


def edit(app, path, editor, line):
    """editor 是 None 時用系統預設文字編輯器，否則照 config.py 的 EDITOR；資料夾一律交給 open。"""
    if Path(path).is_dir():
        return open(app, path)
    if not _there(app, path):
        return
    _launch(["open", "-t", str(path)] if editor is None
            else [p.format(file=str(path), line=line or 1) for p in editor])


def reveal(app, path):
    """在 Finder 裡顯示並選取。"""
    if not _there(app, path):
        return
    _launch(["open", "-R", str(path)])


def terminal(app, path):
    """在 Terminal 打開這個資料夾。想換成別的終端機程式，改 "Terminal" 這個名字。"""
    if not _there(app, path):
        return
    _launch(["open", "-a", "Terminal", str(path)])


def requirements(app):
    """網頁面板要裝的套件清單：requirements/ 裡的檔名。"""
    return "web-mac.txt"


def webview_ready(app):
    """網頁面板的前置條件都有就回 None，缺什麼就回一句話。macOS 內建 WebKit，什麼都不缺。"""
    return None


def trash(app, path):
    """搬到 ~/.Trash（同名就加「 2」「 3」…），回傳搬到哪裡。永遠不刪除。"""
    folder, name = Path.home() / ".Trash", Path(path).name
    folder.mkdir(exist_ok=True)
    dest, n = folder / name, 1
    while dest.exists():
        n += 1
        dest = folder / f"{name} {n}"
    shutil.move(str(path), str(dest))
    return dest
