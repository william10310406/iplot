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

    window = None

    def __init__(self):
        self.events = []

    @property
    def logs(self):
        return [e[1] for e in self.events if e[0] == "log"]

    def log(self, text):
        self.events.append(("log", text))

    def ask(self, prompt, default=""):
        return default

    def choose_files(self):
        return [Path("/f")]

    def choose_folder(self):
        return Path("/d")


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
