"""ui/install.py：第一次啟動把 pywebview 裝進 lib/。全部用假的 Popen，不真的跑 pip、不連網。"""

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from core.core import Core
from core.text import SYSTEM_MODULE, T
from core.types import DEFAULT_CONFIG, ErrorInfo
from ui import install

ROOT = Path(__file__).resolve().parents[1]


class FakePopen:
    """假的 subprocess.Popen：記下 argv 與參數，stdout 吐出 lines，wait() 回 code。"""

    def __init__(self, lines, code):
        self.lines, self.code, self.calls = lines, code, []

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        self.stdout = iter(line + "\n" for line in self.lines)
        return self

    def wait(self):
        return self.code


@pytest.fixture
def req(home):
    (home / "requirements").mkdir()
    f = home / "requirements" / "web-mac.txt"
    f.write_text("pywebview==6.2.1\n", encoding="utf-8")
    return f


def console_core(home):
    return Core(home, DEFAULT_CONFIG, install.ConsoleView())


def test_install_argv_is_list_no_shell(home, req):
    popen = FakePopen([], 0)
    install.install(home, req, lambda line: None, popen)
    [(argv, kw)] = popen.calls
    assert isinstance(argv, list) and argv[0] == sys.executable and argv[1:4] == ["-m", "pip", "install"]
    assert argv[argv.index("--target") + 1] == str(home / "lib") and argv[argv.index("-r") + 1] == str(req)
    assert "--upgrade" in argv and "--no-input" in argv, "pip 不能停下來等人回答"
    assert not kw.get("shell") and kw["stdout"] == subprocess.PIPE and kw["stderr"] == subprocess.STDOUT


def test_install_streams_lines_and_marks(home, req):
    said = []
    (home / "lib").mkdir()  # 真的 pip 會建這個資料夾
    result = install.install(home, req, said.append, FakePopen(["Collecting pywebview", "Downloading", "Done"], 0))
    assert result is None and said == ["Collecting pywebview", "Downloading", "Done"]
    assert (home / "lib" / ".installed").read_text(encoding="utf-8") == hashlib.sha256(req.read_bytes()).hexdigest()
    assert install.installed(home, req)


def test_install_fails_offline_with_plain_message(home, req):
    """審查焦點 1：沒有網路時 pip 以非 0 結束，回傳的是 pip 自己說的原因（ERROR 那幾行），不寫 .installed。
    這幾行是真的拔掉網路時 pip 26 印的。"""
    errors = ["ERROR: Could not find a version that satisfies the requirement bottle==0.13.4 (from versions: none)",
              "ERROR: No matching distribution found for bottle==0.13.4"]
    lines = [f"WARNING: Retrying (Retry(total={n})) after connection broken" for n in (4, 3, 2, 1, 0)] + errors
    said = []
    result = install.install(home, req, said.append, FakePopen(lines, 1))
    assert result == "\n".join(errors) and said == lines, "重試的雜訊只在主控台，不進原因"
    assert not (home / "lib" / ".installed").exists() and not install.installed(home, req)


def test_install_failure_without_error_lines_returns_the_last_five(home, req):
    lines = [f"line {n}" for n in range(8)]
    assert install.install(home, req, lambda line: None, FakePopen(lines, 2)) == "\n".join(lines[-5:])


def test_install_without_pip_reports_the_reason(home, req):
    result = install.install(home, req, lambda line: None, FakePopen(["/usr/bin/python3: No module named pip"], 1))
    assert "No module named pip" in result


def test_installed_compares_hash(home, req):
    assert not install.installed(home, req), "還沒裝過"
    (home / "lib").mkdir()
    (home / "lib" / ".installed").write_text(hashlib.sha256(req.read_bytes()).hexdigest(), encoding="utf-8")
    assert install.installed(home, req)
    req.write_text("pywebview==9.9.9\n", encoding="utf-8")
    assert not install.installed(home, req), "需求檔換了（更新之後）就要重裝"


def test_requirements_file_without_system_module(home, capsys):
    """作業系統模組不在：回 None，主控台印出 no_system 那一句（跟其他動作一樣）。"""
    assert install.requirements_file(home, console_core(home)) is None
    assert T["no_system"].format(module=SYSTEM_MODULE, name="requirements") in capsys.readouterr().out


def with_system_module(home):
    shutil.copytree(ROOT / "modules" / SYSTEM_MODULE, home / "modules" / SYSTEM_MODULE,
                    ignore=shutil.ignore_patterns("__pycache__", ".history"))
    return console_core(home)


def test_requirements_file_and_ready_ask_the_system_module(home, monkeypatch, capsys):
    core = with_system_module(home)
    monkeypatch.setattr(sys, "platform", "darwin")
    assert install.requirements_file(home, core) == home / "requirements" / "web-mac.txt"
    assert install.ready(core) is None
    monkeypatch.setattr(sys, "platform", "linux")
    assert install.requirements_file(home, core) is None, "Linux 這一版沒有網頁面板"
    assert "--safe" in install.ready(core)
    assert capsys.readouterr().out == "", "問這兩件事不在主控台留下「完成」之類的字"


def test_broken_system_module_is_reported_in_plain_words(home, capsys):
    core = with_system_module(home)
    (home / "modules" / SYSTEM_MODULE / "iplot.py").write_text("def requirements(app)\n", encoding="utf-8")
    assert install.requirements_file(home, core) is None
    out = capsys.readouterr().out
    assert SYSTEM_MODULE in out and "Traceback" not in out


def test_console_view_is_a_minimal_view(capsys):
    view = install.ConsoleView()
    view.show(None)
    view.log("一行")
    view.report(ErrorInfo("TypeError", "m", None, None, "Traceback…", "config", None))
    assert capsys.readouterr().out == "一行\n" + T["config_error"].format(message="m") + "\n"
    assert (view.ask("q"), view.confirm("q"), view.choose_files(), view.choose_folder()) == (None, False, [], None)


@pytest.mark.parametrize("name", ["web-mac.txt", "web-win.txt"])
def test_requirements_are_pinned(name):
    lines = (ROOT / "requirements" / name).read_text(encoding="utf-8").splitlines()
    pins = [line for line in lines if line.strip() and not line.startswith("#")]
    assert pins and all(re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", p) for p in pins), pins
    assert "pywebview==6.2.1" in pins


def test_windows_requirements_say_unverified():
    text = (ROOT / "requirements" / "web-win.txt").read_text(encoding="utf-8")
    assert "未經實機驗證" in text.splitlines()[0] and "pythonnet==" in text


def test_lib_is_ignored_by_git():
    assert "lib/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
