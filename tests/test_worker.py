"""工作程序的兩頭在同一個程序裡測（D161）：test_concurrency 真的開程序，但子程序裡跑的那一半量不到覆蓋率。
這裡用兩條 os.pipe 接起主程序那頭與工作程序那頭，直接呼叫 worker.serve。"""

import os
import pickle
import sys
import threading
import time

from conftest import FakeView, make_module

from core import worker
from core.core import Core
from core.pipe import Pipe
from core.scan import module_info
from core.types import DEFAULT_CONFIG

# 工作程序那頭的 listen 讀到 EOF 就 os._exit（面板關了，工作程序跟著結束）：測試期間管道都開著，不讓它讀到 EOF
_KEEP: list = []


def pipes() -> tuple[Pipe, Pipe]:
    to_child, to_host = os.pipe(), os.pipe()
    host = Pipe(os.fdopen(to_host[0], "rb"), os.fdopen(to_child[1], "wb"))
    child = Pipe(os.fdopen(to_child[0], "rb"), os.fdopen(to_host[1], "wb"))
    _KEEP.append((host, child))
    return host, child


def run_in_process(tmp_path, monkeypatch, src: str, view: FakeView | None = None, blob: bytes | None = None):
    """像 spawn 一樣交一件工作給 serve，替它跑腿，回 ("done", Result, memory) 與面板那邊的 core。"""
    monkeypatch.setattr(sys, "path", list(sys.path))  # serve 會把 lib/ 加進 sys.path
    home = tmp_path / "iplot"
    make_module(home / "modules", "W", src)
    core = Core(home, DEFAULT_CONFIG, view or FakeView())
    core.rescan()
    info = module_info(home / "modules" / "W", (home / "modules").resolve(), "here")
    host, child = pipes()
    job = {"home": home, "config": DEFAULT_CONFIG, "safe": False, "info": info, "handler": "run", "args": (),
           "scope": core.scope, "memories": {} if blob is None else {info.folder: blob}}
    host.send(("start", job))
    threading.Thread(target=worker.serve, args=(child,), daemon=True).start()
    while (message := host.recv())[0] == "req":
        threading.Thread(target=worker._serve, args=(core, host, *message[1:]), daemon=True).start()
    return message, info


def test_serve_runs_the_module_and_passes_app_calls_to_the_panel(tmp_path, monkeypatch):
    view = FakeView()
    view.answer = "小華"
    src = ('def run(app):\n    app.log("嗨")\n    name = app.ask("名字？")\n    app.memory["n"] = app.memory.get("n", 0) + 1\n'
           '    app.rescan()\n    app.page("沒有提供者", "<p></p>")\n'
           '    try:\n        app.nothing_like_this()\n    except AttributeError:\n        app.log("沒有這個")\n'
           '    return [name, app.memory["n"], app.confirm("好？"), app.api_version]\n')

    (kind, result, blobs), info = run_in_process(tmp_path, monkeypatch, src, view, pickle.dumps({"n": 4}))

    assert kind == "done" and result.ok, result.error
    assert result.value == ["小華", 5, True, 7]
    assert pickle.loads(blobs[info.folder]) == {"n": 5}
    assert view.asks == ["名字？"] and "嗨" in view.logs and "沒有這個" in view.logs
    assert any("沒有提供者" in line for line in view.logs)  # 沒有提供 app.page 的模組：說一句，不開視窗


def test_a_value_that_cannot_cross_processes_becomes_an_error_that_names_its_type(tmp_path, monkeypatch):
    src = 'def run(app):\n    app.memory["f"] = lambda: 0\n    return lambda: 0\n'

    (kind, result, blobs), _ = run_in_process(tmp_path, monkeypatch, src, blob=b"not a pickle")

    assert kind == "done" and not result.ok
    assert result.error.kind == "NotPassable" and "function" in result.error.message
    assert blobs == {}  # memory 存不了：不帶回去，主程序留著上一次的


def test_a_panel_error_is_raised_inside_the_module(tmp_path, monkeypatch):
    class Broken(FakeView):
        def confirm(self, prompt):
            raise RuntimeError("面板壞了")

    src = 'def run(app):\n    try:\n        app.confirm("好？")\n    except RuntimeError as exc:\n        return str(exc)\n'

    (_, result, _), _ = run_in_process(tmp_path, monkeypatch, src, Broken())

    assert result.ok and result.value == "面板壞了"


def test_serve_refuses_names_it_does_not_serve_and_ignores_a_closed_pipe(tmp_path):
    sent = []

    class Closed:
        def send(self, message):
            sent.append(message)
            raise OSError("closed")

    core = Core(tmp_path, DEFAULT_CONFIG, FakeView())
    worker._serve(core, Closed(), 1, "quit", ())
    assert sent[0][:3] == ("res", 1, False) and isinstance(sent[0][3], AttributeError)


def test_spawn_says_so_when_python_cannot_start(tmp_path, monkeypatch):
    (tmp_path / "logs").write_text("")  # logs 是個檔：記錄檔開不了，錯誤輸出留在終端機

    def refuse(*args, **kwargs):
        raise OSError("no python")

    monkeypatch.setattr(worker.subprocess, "Popen", refuse)
    make_module(tmp_path / "modules", "W")
    info = module_info(tmp_path / "modules" / "W", (tmp_path / "modules").resolve(), "here")

    result = worker.spawn(Core(tmp_path, DEFAULT_CONFIG, FakeView()), info, "run", ())

    assert not result.ok and result.error.kind == "WorkerFailed"


def test_start_runs_in_a_thread_here_and_asks_the_panel_from_a_worker(tmp_path):
    asked = []
    make_module(tmp_path / "modules", "W", 'def run(app):\n    app.log("跑了")\n')
    view = FakeView()
    core = Core(tmp_path, DEFAULT_CONFIG, view)
    core.rescan()
    info = module_info(tmp_path / "modules" / "W", (tmp_path / "modules").resolve(), "here")

    core.start(info)
    end = time.monotonic() + 10
    while "跑了" not in view.logs:
        assert time.monotonic() < end
        time.sleep(0.01)

    remote = Core(tmp_path, DEFAULT_CONFIG, FakeView(), remote=lambda *args: asked.append(args))
    remote.start(info)
    remote.rescan()
    assert asked == [("start", info), ("rescan",)]
