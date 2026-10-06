"""Linux：xdg-open；終端機依序找常見的幾個；垃圾桶照 XDG 規範寫 files/ 與 info/。"""
import shutil
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path

NAME = "Linux"
# 終端機程式，與「在這個資料夾打開」的旗標；依序找，用第一個找得到的
TERMINALS = [("x-terminal-emulator", []), ("gnome-terminal", ["--working-directory={dir}"]),
             ("konsole", ["--workdir", "{dir}"]), ("xfce4-terminal", ["--working-directory={dir}"]),
             ("xterm", [])]


def _launch(argv, **kw):
    """啟動後不等。"""
    subprocess.Popen(argv, **kw)


def open(app, path):
    """資料夾進檔案管理員，檔案用預設程式。"""
    _launch(["xdg-open", str(path)])


def edit(app, path, editor, line):
    """editor 是 None 時交給 xdg-open，否則照 config.py 的 EDITOR；資料夾一律交給 open。"""
    if editor is None or Path(path).is_dir():
        return open(app, path)
    _launch([p.format(file=str(path), line=line or 1) for p in editor])


def reveal(app, path):
    """打開上一層資料夾（xdg-open 沒有「選取」這個功能）。"""
    _launch(["xdg-open", str(Path(path).parent)])


def terminal(app, path):
    """在終端機打開這個資料夾：用 TERMINALS 裡第一個找得到的。"""
    for name, flags in TERMINALS:
        if shutil.which(name):
            return _launch([name, *(f.format(dir=str(path)) for f in flags)], cwd=str(path))
    raise OSError("找不到終端機程式，試過：" + "、".join(name for name, _ in TERMINALS))


def requirements(app):
    """網頁面板要裝的套件清單：requirements/ 裡的檔名。空字串＝這個平台還沒有網頁面板。"""
    return ""


def webview_ready(app):
    """網頁面板的前置條件都有就回 None，缺什麼就回一句話。Linux 要系統層的 GTK／WebKit2GTK，pip 裝不了。"""
    return "這一版的網頁面板還不支援 Linux，請用安全模式：python3 main.py --safe"


def trash(app, path):
    """照 XDG 規範搬到 ~/.local/share/Trash：東西進 files/，原本的位置與時間寫進 info/。
    同名就加「 2」「 3」…；回傳搬到哪裡。永遠不刪除。"""
    base, source = Path.home() / ".local" / "share" / "Trash", Path(path).absolute()
    files, info = base / "files", base / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    name, n = source.name, 1
    while (files / name).exists() or (info / f"{name}.trashinfo").exists():
        n += 1
        name = f"{source.name} {n}"
    # 寫檔用 write_text：這個檔裡 open 已經是上面那個函式，不是內建的 open
    (info / f"{name}.trashinfo").write_text(
        f"[Trash Info]\nPath={urllib.parse.quote(str(source))}\n"
        f"DeletionDate={datetime.now():%Y-%m-%dT%H:%M:%S}\n", encoding="utf-8")
    shutil.move(str(source), str(files / name))
    return files / name
