"""工作程序：每按一次，核心開一個程序跑那個模組（D161）。這個檔兩頭都有：spawn 在主程序開程序、替它跑腿；
main 在工作程序裡跑模組。開程序是「執行」本身，所以這裡是核心唯一用 subprocess 的地方（規則 16 的例外）。

模組改工作目錄、sys.argv、input、sys.modules 都只影響自己的程序，所以面板可以同時跑好幾個、頁面開著也不卡。
模組拿到的 app 跟以前一樣；要面板做的事（log、ask、confirm、report、rescan、選檔案、開別的模組）經管道交給主程序。
app.page 在工作程序裡開（交給提供 app.page 的模組），主執行緒是它自己的。
工作程序裡 "core.runner" 照樣在 sys.modules（模組檔頭的那一小段靠它，永久保留）。"""

import contextlib
import itertools
import os
import pickle
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from . import runner
from .app import App
from .pipe import Pipe
from .text import T
from .types import ErrorInfo, ModuleInfo, Result

# 工作程序的入口：argv[1] 是 core 所在的資料夾。拿掉 -c 放進來的 ''，工作目錄裡的同名檔才不會蓋掉標準庫
ENTRY = "import sys; sys.path[:] = [sys.argv[1]] + [p for p in sys.path if p]; from core import worker; worker.main()"
# 工作程序可以要主程序做的事：面板的對話框與訊息區、重掃、開始跑另一個模組（不等它）
SERVED = ("log", "report", "ask", "confirm", "choose_files", "choose_folder", "rescan", "start")


# ── 主程序這一頭 ──

def spawn(core: Any, info: ModuleInfo, handler: str, args: tuple) -> Result:
    """開一個工作程序跑 info，一邊替它跑腿（每件一條執行緒，對話框等著也不擋別件），等它交回結果。
    程序沒交結果就結束了，變成 WorkerDied。錯誤輸出接到 logs/worker.log，不丟掉（R11）。"""
    try:
        (core.home / "logs").mkdir(exist_ok=True)
        err: Any = (core.home / "logs" / "worker.log").open("ab")
    except OSError:
        err = None  # 記錄檔寫不了：錯誤輸出留在終端機
    try:
        proc = subprocess.Popen([sys.executable, "-c", ENTRY, str(Path(__file__).resolve().parent.parent)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, cwd=core.home)
    except OSError as exc:
        message = T["worker_failed"].format(message=core._why(exc))
        return Result(False, ErrorInfo("WorkerFailed", message, None, None, "", "core", None), 0.0, "")
    finally:
        if err is not None:
            err.close()
    pipe = Pipe(proc.stdout, proc.stdin)
    job = {"home": core.home, "config": core.config, "safe": core.safe, "info": info, "handler": handler,
           "args": args, "scope": core.scope, "memories": dict(core._blobs), "panel": getattr(core.view, "name", None)}
    try:
        pipe.send(("start", job))
        while (message := pipe.recv())[0] == "req":
            threading.Thread(target=_serve, args=(core, pipe, *message[1:]), daemon=True).start()
        _, result, blobs = message
        core._blobs.update(blobs)
    except (EOFError, OSError):
        died = T["worker_died"].format(code=proc.wait())
        result = Result(False, ErrorInfo("WorkerDied", died, info.file, None, "", "module", info.name), 0.0, "")
    threading.Thread(target=proc.wait, daemon=True).start()  # 收屍；模組自己開的執行緒還在跑的話等它
    return result


def _serve(core: Any, pipe: Pipe, n: int, name: str, args: tuple) -> None:
    """替工作程序做一件事，把結果或例外送回去。"""
    try:
        if name not in SERVED:
            raise AttributeError(name)
        target = getattr(core, name) if name in ("rescan", "start") else getattr(core.view, name)
        reply = ("res", n, True, target(*args))
    except Exception as exc:  # noqa: BLE001  面板那邊出錯：交回工作程序，在模組裡丟出來
        reply = ("res", n, False, exc)
    with contextlib.suppress(OSError):  # 工作程序已經結束了：沒人等這個回答
        pipe.send(reply)


# ── 工作程序這一頭 ──

class Remote:
    """對主程序發問：remote("ask", "名字？") 等主程序回答。很多條執行緒可以同時問（頁面的 JS 呼叫在別的執行緒）。"""

    def __init__(self, pipe: Pipe) -> None:
        self.pipe, self._ids, self._lock = pipe, itertools.count(1), threading.Lock()
        self._waiting: dict[int, tuple[threading.Event, list]] = {}

    def listen(self) -> None:
        """收主程序的回答，交給在等的那一個。主程序不在了（面板關了），這個程序也結束。"""
        while True:
            try:
                _, n, ok, value = self.pipe.recv()
            except EOFError:
                os._exit(0)
            with self._lock:
                event, box = self._waiting.pop(n)
            box[:] = [ok, value]
            event.set()

    def __call__(self, name: str, *args: Any) -> Any:
        event, box = threading.Event(), []
        with self._lock:
            n = next(self._ids)
            self._waiting[n] = (event, box)
        self.pipe.send(("req", n, name, args))
        event.wait()
        if not box[0]:
            raise box[1]
        return box[1]


class RemoteView:
    """工作程序裡的 View：show 不做（主程序自己畫）；page 走到這裡表示沒有提供 app.page 的模組；其他交給主程序。"""

    def __init__(self, remote: Remote, name: str | None = None) -> None:
        self._remote, self.name = remote, name  # name：開這個程序的面板是哪一種（app.panel）

    def show(self, scope: Any) -> None:
        pass

    def page(self, title: str, html: str, api: object | None) -> None:
        self.log(T["no_page"].format(title=title))

    def __getattr__(self, name: str) -> Any:
        return lambda *args: self._remote(name, *args)


def _load(blobs: dict) -> dict:
    """主程序存著的 memory（pickle 過的位元組）還原；還原不了的（例如存了模組自己定義的類別）從空的開始。"""
    found = {}
    for folder, blob in blobs.items():
        try:
            found[folder] = pickle.loads(blob)  # noqa: S301  是工作程序之前自己存的
        except Exception:  # noqa: BLE001  還原不了就當沒存過，不讓模組因此跑不了
            found[folder] = {}
    return found


def _dump(memories: dict) -> dict:
    """memory 存回去；存不了的那一個不帶回去，主程序留著上一次的。"""
    found = {}
    for folder, memory in memories.items():
        with contextlib.suppress(Exception):
            found[folder] = pickle.dumps(memory)
    return found


def main() -> None:
    """讀主程序交來的工作、跑、把結果交回去。管道用原本的 stdin／stdout；之後模組讀 stdin 讀到空的，
    寫到 stdout 的（C 程式庫直接寫的也算）都進 stderr，也就是 logs/worker.log，不會弄壞管道。"""
    pipe = Pipe(os.fdopen(os.dup(0), "rb"), os.fdopen(os.dup(1), "wb"))
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    os.dup2(2, 1)
    serve(pipe)


def serve(pipe: Pipe) -> None:
    """從管道收一件工作、跑完、交回去（main 把管道接好之後的那一段）。"""
    from .core import Core  # core.py 也 import 這個檔，放在這裡才不會循環

    _, job = pipe.recv()
    remote = Remote(pipe)
    threading.Thread(target=remote.listen, daemon=True).start()
    home, info = job["home"], job["info"]
    sys.path.insert(1, str(home / "lib"))
    core = Core(home, job["config"], RemoteView(remote, job.get("panel")), job["safe"], remote=remote)
    core.scope, core.memories = job["scope"], _load(job["memories"])
    core.running.append(info)
    result = runner.run_module(info, App(core, info), job["handler"], job["args"])
    try:
        pipe.send(("done", result, _dump(core.memories)))
    except Exception as exc:  # noqa: BLE001  回傳值傳不過去：說清楚是哪個型別，結果當作出錯
        what = T["not_passable"].format(title=info.title, kind=type(result.value).__name__)
        error = ErrorInfo("NotPassable", what, info.file, None, repr(exc), "module", info.name)
        pipe.send(("done", Result(False, error, result.duration, result.output), _dump(core.memories)))
    sys.stdout.flush()
