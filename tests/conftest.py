import dataclasses
import json
import time
import types
from pathlib import Path

import pytest

from core.scan import module_info
from core.types import DEFAULT_CONFIG

DEFAULT_SRC = 'def run(app):\n    print("ok")\n'


def make_module(parent, name, src=DEFAULT_SRC):
    """在 parent 底下建資料夾 name 並寫入 iplot.py，回傳資料夾。"""
    folder = parent / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "iplot.py").write_text(src, encoding="utf-8")
    return folder


class FakeView:
    """不開視窗的 View：依序記錄事件，對話框回固定答案。"""

    answer = ...  # ask 的答案：... 表示回 default；測試可以設成字串，或 None（按了取消）

    def __init__(self):
        self.events = []
        self.confirmed, self.answers = [], []  # confirm 問過的句子；依序要回的答案，用完之後回 True

    @property
    def asks(self):
        return [e[1] for e in self.events if e[0] == "ask"]

    @property
    def logs(self):
        return [e[1] for e in self.events if e[0] == "log"]

    @property
    def shows(self):
        return [e[1] for e in self.events if e[0] == "show"]

    @property
    def reports(self):
        return [e[1] for e in self.events if e[0] == "report"]

    def show(self, scope):
        self.events.append(("show", scope))

    def log(self, text):
        self.events.append(("log", text))

    def report(self, error):
        self.events.append(("report", error))

    def ask(self, prompt, default=""):
        self.events.append(("ask", prompt))
        return default if self.answer is ... else self.answer

    def confirm(self, prompt):
        self.confirmed.append(prompt)
        return self.answers.pop(0) if self.answers else True

    def page(self, title, html, api):
        self.events.append(("page", (title, html, api)))

    def choose_files(self):
        return [Path("/f")]

    def choose_folder(self):
        return Path("/d")


class FakeApp:
    """模組拿到的 app 的替身：記下 log、confirm、page、rescan；設定用關鍵字給（update_url=…）。"""

    def __init__(self, home, version="0.4.9", **config):
        self.home, self.version = home, version
        self.config = dataclasses.replace(DEFAULT_CONFIG, **config)
        self.logs, self.confirms, self.answers, self.pages, self.rescans = [], [], [], [], 0

    def log(self, text):
        self.logs.append(text)

    def confirm(self, prompt):
        self.confirms.append(prompt)
        return self.answers.pop(0) if self.answers else True

    def page(self, title, html, api=None):
        self.pages.append((title, html, api))

    def rescan(self):
        self.rescans += 1


class FakeCore:
    """只記錄呼叫的假 Core，給 test_app 用。"""

    def __init__(self, home, config, view):
        self.home, self.config, self.view = home, config, view
        self.memories = {}
        self.calls = []

    def all_modules(self):
        return ()

    def run_by_name(self, name):
        self.calls.append(("run_by_name", name))
        return "result"

    def rescan(self):
        self.calls.append(("rescan",))

    def action(self, name, *args):
        self.calls.append(("action", name, *args))
        return "value"


class FakeEvent:
    """pywebview 的事件：用 += 掛處理函式。"""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeWindow:
    """不開視窗的 pywebview 視窗：evaluate_js 的字串存進 js，檔案對話框回 dialog_result。"""

    def __init__(self, title, kw):
        self.title, self.kw = title, kw
        self.js, self.dialogs, self.dialog_result, self.js_error = [], [], None, None
        self.shown, self.destroyed = False, False  # show()／hide()／destroy() 只記狀態
        self.events = types.SimpleNamespace(loaded=FakeEvent(), closing=FakeEvent(), closed=FakeEvent())

    def show(self):
        self.shown = True

    def hide(self):
        self.shown = False

    def destroy(self):
        self.destroyed = True

    def evaluate_js(self, script):
        if self.js_error and script.startswith(self.js_error):  # 模擬頁面那一頭的 JS 丟例外
            raise FakeWebview.JavascriptException(script[:40])
        self.js.append(script)

    def create_file_dialog(self, *args, **kw):
        self.dialogs.append((args, kw))
        return self.dialog_result

    def fire(self, name):
        for handler in getattr(self.events, name).handlers:
            handler()

    def calls(self, name):
        """推給頁面的 iplot.<name>(…) 呼叫，每筆是解析過的參數清單。"""
        head = f"iplot.{name}("
        return [json.loads("[" + j[len(head):-1] + "]") for j in self.js if j.startswith(head)]


class FakeWebview:
    """假的 webview 套件：create_window 回 FakeWindow；start 立刻觸發 loaded 然後回傳。"""

    class JavascriptException(Exception):
        pass

    class WebViewException(Exception):
        pass

    class FileDialog:
        OPEN, FOLDER, SAVE = 10, 20, 30

    def __init__(self):
        self.windows = []

    def create_window(self, title, **kw):
        self.windows.append(FakeWindow(title, kw))
        return self.windows[-1]

    def start(self):
        self.windows[0].fire("loaded")


def until(condition, timeout=3.0):
    """等到 condition() 成立（另一條執行緒在做事的時候用）；逾時就失敗。"""
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "等太久了"
        time.sleep(0.005)


@pytest.fixture
def panel(home):
    """接好 Core、跑過 run() 的 WebPanel：假的 webview，不開視窗；啟動時的重掃已經做完。"""
    from core.core import Core
    from ui.web import WebPanel

    p = WebPanel(home, "0.4.0", False, webview=FakeWebview())
    p.attach(Core(home, DEFAULT_CONFIG, p))
    p.run()
    p.wait()
    return p


@pytest.fixture
def home(tmp_path):
    """假的 iPLoT 程式資料夾：tmp/iPLoT，裡面有空的 modules/。"""
    h = tmp_path / "iPLoT"
    (h / "modules").mkdir(parents=True)
    return h


@pytest.fixture
def info(home):
    return module_info(make_module(home / "modules", "A"), home / "modules", "here")


@pytest.fixture
def fake_core(home):
    return FakeCore(home, DEFAULT_CONFIG, FakeView())


@pytest.fixture
def view():
    return FakeView()
