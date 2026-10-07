"""互通：任何模組都能在面板外打開——Spotlight、Dock、一行指令、直接 python3 iplot.py。
按這裡會先同步一次（捷徑、讓舊模組能直接執行的那一小段），再顯示現在的狀態。"""
import ast
import json
import pathlib
import shlex
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

ICON = "🔗"
HERE = pathlib.Path(__file__).resolve().parent
EXAMPLE = "開工"  # 指令的例子優先用它；沒有就用最上層第一個模組
# 這個檔被直接執行（python3 iplot.py）時，檔頭的 import 在那一小段之前跑，那時候 core 還不在 sys.path 上：
# 所以這裡只 import 標準庫，同一個資料夾的 boot、sync…與 core 都在函式裡才 import


def status(home: pathlib.Path, config, python: str, folder: pathlib.Path) -> dict:
    """狀態頁要的資料：幾個模組能在面板外打開、幾個能直接執行、沒補的與原因、捷徑在哪、指令怎麼寫、上一次同步的問題。"""
    import shortcut
    import snippet
    import sync

    from core import scan
    from core.text import SYSTEM_MODULE

    roots, done = scan.roots_from_config(home, config.roots), sync.patched(folder)
    total, direct, skipped, top = 0, 0, [], []
    for info, titles in sync.modules(home, config):
        if info.level != "child":
            top.append(info.name)
        if not (info.level == "here" and info.name == SYSTEM_MODULE):
            total += 1
        reason = sync.why_not(info, roots)
        try:
            text = info.file.read_text(encoding="utf-8-sig")
        except (OSError, ValueError):
            text = ""
        if snippet.has(text) and reason != "在 ROOTS 另外加的資料夾裡":
            direct += 1  # 自己帶著那一小段（例如工作坊裝來的新版）也算
            continue
        if reason is None:
            try:
                ast.parse(text)
                reason = "拿掉了那一小段（不會再補）" if str(info.folder) in done else "還沒補（見上一次同步的問題）"
            except (SyntaxError, ValueError):
                reason = "有語法錯誤"
        skipped.append({"name": " › ".join(titles), "reason": reason})
    others = [n for n in top if n not in ("互通", SYSTEM_MODULE)]
    example = EXAMPLE if EXAMPLE in top else (others[0] if others else "<模組名稱>")
    try:
        problems = (folder / sync.ERRORS).read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        problems = []
    return {"total": total, "direct": direct, "skipped": skipped, "problems": problems, "python": python,
            "shortcuts": str(folder / shortcut.FOLDER), "mac": sys.platform == "darwin",
            "command": shlex.join([python, str(folder / "run.py"), example])}


def render(data: dict) -> str:
    """page.html，資料以 JSON 放進 <script type="application/json">；< 寫成 \\u003c，名稱裡有 </script> 也只是字。"""
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return (HERE / "page.html").read_text(encoding="utf-8").replace("__STATUS__", payload)


class Api:
    """狀態頁的 JS 用 pywebview.api.<方法> 呼叫的入口；自己的東西都以底線開頭，攤出去的只有這三個方法。"""

    def __init__(self, app, home: pathlib.Path, config, python: str, folder: pathlib.Path) -> None:
        self._app, self._home, self._config, self._python, self._folder = app, home, config, python, folder

    def reveal(self) -> None:
        """「在 Finder 中顯示」：捷徑的資料夾。"""
        import shortcut
        self._app.reveal(self._folder / shortcut.FOLDER)

    def copy(self, text: str) -> bool:
        """「複製」：把指令放進剪貼簿（macOS 的 pbcopy）；別的系統回 False，頁面說一句「請自己選取複製」。"""
        if sys.platform != "darwin":
            return False
        subprocess.run(["pbcopy"], input=str(text).encode(), check=False)
        return True

    def resync(self) -> dict:
        """「再同步一次」：同步之後回新的狀態，頁面用 textContent 重畫。"""
        import sync
        sync.sync(self._home, self._config, self._python, self._folder)
        return status(self._home, self._config, self._python, self._folder)


def run(app):
    """記下面板用的 Python、同步一次、打開狀態頁。"""
    import boot
    import sync

    boot.remember_python(HERE, sys.executable)
    python = boot.recorded_python(HERE) or sys.executable
    sync.sync(app.home, app.config, python, HERE)
    data = status(app.home, app.config, python, HERE)
    app.page("互通", render(data), Api(app, app.home, app.config, python, HERE))
