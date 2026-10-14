"""行事曆：打開就是這個月的月曆；每天寫行程、心情、看到了什麼、做了什麼，放圖片，存成一天一個資料夾並產生網頁。

上方的模組列叫得到任何模組；任何模組寫 app.run("行事曆") 就叫得到它。行事曆的頁面只在它自己另開的程序裡開（D89）：
在面板裡、或被別的模組叫到時，經「互通」的 run.py 另開一個程序；已經開著就叫到最前面。資料在 ~/Documents/行事曆
（⚙ 可以換），一天一個資料夾 <年>/<月>/<日>/，Finder 看得到；「發佈」只產生 發佈/ 資料夾，不上傳。"""
import datetime
import os
import pathlib
import subprocess

# ── 互通 ── 直接執行這個檔（python3 iplot.py）時交給 iPLoT 用彈出式視窗跑；從 iPLoT 裡執行時這段不做事。不要可以整段刪掉
import sys

if __name__ == "__main__" and "core.runner" not in sys.modules:
    import os
    import subprocess
    here = folder = os.path.dirname(os.path.abspath(__file__))
    run = None
    while run is None and folder != os.path.dirname(folder):  # 往上一層層找 iPLoT：模組在它裡面或旁邊都找得到
        folder = os.path.dirname(folder)
        try:
            names = [""] + sorted(os.listdir(folder))
        except OSError:
            names = [""]
        runs = (os.path.join(folder, n, "modules", "互通", "run.py") for n in names)
        run = next((r for r in runs if os.path.isfile(r)), None)
    if run and not os.environ.get("IPLOT_DIRECT"):  # IPLOT_DIRECT=1：不交出去，照一般腳本跑（例如在編輯器裡除錯）
        sys.exit(subprocess.call([sys.executable, run, here, *sys.argv[1:]]))
    if not run:
        print("找不到 iPLoT 的「互通」（先在工作坊裝「互通」；模組要放在 iPLoT 資料夾裡或它旁邊），照一般的 python3 iplot.py 跑",
              file=sys.stderr)
# ── 互通 ──

import threading
import unicodedata

import diary
import pages
import photos  # noqa: F401  （Api 的圖片方法在 Task 6 用到）

try:  # 在 iPLoT 裡一定在；直接 python3 iplot.py（IPLOT_DIRECT=1）時 core 不在 sys.path 上
    from core import scan
    from core.text import SYSTEM_MODULE
except ImportError:
    scan, SYSTEM_MODULE = None, "作業系統"

ICON = "📅"
ENV = "IPLOT_CALENDAR"  # 行事曆自己另開的程序：一開始就從環境變數拿掉，之後從它開的子程序不會繼承
PID = ".pid"
SETTINGS = "設定.json"
HERE = pathlib.Path(__file__).resolve().parent
ICON_FILE = HERE / "icon.png"
RUN_PY = ("modules", "互通", "run.py")
NO_INTEROP = "行事曆要用「互通」另開視窗：到工作坊裝「互通」"
OPENED = "打開行事曆"
ALREADY = "行事曆已經開著"
ALREADY_BEHIND = "行事曆已經開著（在 Dock 上找月曆的圖示）"
# macOS 14 起，自己不在最前面的 App 叫別人到最前面會被拒絕；不是 App 的一般 python 程序叫就可以（跟「主控面板」同一段）。
# 被拒絕時交給這一小段在子程序裡叫：argv 是 [-c, lib 的路徑, pid]
HELPER = ("import sys\n"
          "sys.path.insert(0, sys.argv[1])\n"
          "import AppKit\n"
          "app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(int(sys.argv[2]))\n"
          "sys.exit(0 if app is not None and app.activateWithOptions_("
          "AppKit.NSApplicationActivateIgnoringOtherApps) else 1)\n")


def _ps() -> str:
    """所有程序的 pid 與完整指令。一定用 UTF-8 的 locale 叫 ps（從 Dock 開的程式沒有 locale，中文路徑會變成跳脫字）；-ww 不截斷。"""
    try:
        return subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, encoding="utf-8",
                              errors="replace", env={**os.environ, "LC_ALL": "en_US.UTF-8"}, check=False).stdout
    except OSError:
        return ""


def activate(pid: int | None, platform: str = sys.platform, run=subprocess.run) -> bool:
    """把 pid（None 是自己）叫到最前面；macOS 以外、或載不進 AppKit 就回 False。照抄「主控面板」的做法。"""
    if platform != "darwin":
        return False
    try:
        import AppKit
    except ImportError:
        return False
    running = AppKit.NSRunningApplication
    app = running.currentApplication() if pid is None else running.runningApplicationWithProcessIdentifier_(pid)
    if app is not None and app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps):
        return True
    lib = str(pathlib.Path(AppKit.__file__).parents[1])
    target = os.getpid() if pid is None else pid
    try:
        done = run([sys.executable, "-c", HELPER, lib, str(target)], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def set_dock_icon(path: pathlib.Path, platform: str = sys.platform) -> bool:
    """macOS：把這個程序在 Dock 上的圖示換成 path（交給主執行緒換）。其他系統、或載不進 AppKit 回 False。"""
    if platform != "darwin":
        return False
    try:
        import AppKit
        from PyObjCTools import AppHelper
    except ImportError:
        return False
    image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(path))
    if image is None:
        return False
    AppHelper.callAfter(AppKit.NSApplication.sharedApplication().setApplicationIconImage_, image)
    return True


def running_pid(folder: pathlib.Path, pid_file: pathlib.Path, ps=_ps, me: int | None = None) -> int | None:
    """.pid 記的程序還活著、而且它的指令裡有互通的 run.py 與這個資料夾，才回它的 pid；否則 None（過期）。"""
    me = os.getpid() if me is None else me
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if pid == me:
        return None
    target = unicodedata.normalize("NFC", str(folder))
    for line in unicodedata.normalize("NFC", ps()).splitlines():
        pid_text, _, command = line.strip().partition(" ")
        if pid_text == str(pid):
            return pid if "run.py" in command and target in command else None
    return None


def launch(home: pathlib.Path, folder: pathlib.Path, *, popen=subprocess.Popen, python: str = sys.executable,
           environ=os.environ) -> None:
    """經互通的 run.py 另開一個行事曆的程序（跟這個程序分開；IPLOT_CALENDAR=1 記號）。"""
    popen([python, str(home.joinpath(*RUN_PY)), str(folder)], env={**environ, ENV: "1"}, start_new_session=True,
          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_or_focus(app, folder: pathlib.Path, *, environ=os.environ, ps=_ps, popen=subprocess.Popen, activate=activate,
                  platform: str | None = None, me: int | None = None, api=None) -> None:
    """設計第 3.1 節的三步：已經開著 → 叫到最前面；這是行事曆自己另開的程序 → 開頁面；其他 → 另開一個。"""
    platform = platform or sys.platform
    pid = running_pid(folder, folder / PID, ps, me)
    if pid is not None:
        app.log(ALREADY if platform == "darwin" and activate(pid, platform) else ALREADY_BEHIND)
        return
    if environ.get(ENV):
        environ.pop(ENV, None)
        diary.write_text(folder / PID, str(os.getpid()))
        try:
            app.page("行事曆", (folder / "page.html").read_text(encoding="utf-8"), api or Api(app, folder / SETTINGS))
        finally:
            (folder / PID).unlink(missing_ok=True)
        return
    if not app.home.joinpath(*RUN_PY).is_file():
        app.log(NO_INTEROP)
        return
    try:
        launch(app.home, folder, popen=popen, environ=environ)
    except OSError as exc:
        app.log(f"打不開行事曆：{exc}")
        return
    app.log(OPENED)


class Api:
    """頁面的 JS 用 pywebview.api.<方法> 呼叫的入口。自己的屬性一律底線開頭（頁面碰不到）；頁面不傳路徑。"""

    def __init__(self, app, settings_file: pathlib.Path, *, default_root: pathlib.Path | None = None,
                 run=subprocess.run, popen=subprocess.Popen, platform: str = sys.platform, environ=os.environ,
                 today=datetime.date.today, dock_icon=set_dock_icon) -> None:
        self._app, self._settings = app, pathlib.Path(settings_file).absolute()
        self._default_root = default_root or pathlib.Path.home() / "Documents" / "行事曆"
        self._run, self._popen, self._platform, self._environ = run, popen, platform, environ
        self._today, self._dock_icon, self._icon_done = today, dock_icon, False
        self._lock = threading.Lock()

    def _root(self) -> pathlib.Path:
        return diary.load_root(self._settings, self._default_root)

    def month(self, ym):
        with self._lock:
            return {}

    def rebuild(self):
        with self._lock:
            return {"pages": len(pages.rebuild_all(self._root()))}


def run(app):
    """打開行事曆，或叫到最前面。"""
    open_or_focus(app, HERE)

