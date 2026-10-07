"""工作坊模組「互通」（modules/互通）：面板外的入口、彈出式視窗、那一小段、捷徑、同步、狀態頁。
模組裡的檔用 load("名字") 當一般模組 import（不寫 .pyc）。絕不真的開程式、不碰真的家目錄與 repo 的 modules/互通：
會開程式的呼叫一律換成記錄，要寫的資料夾一律在 tmp_path。"""

import ast
import importlib
import os
import sys
from pathlib import Path

import pytest

INTEROP = Path(__file__).resolve().parents[1] / "modules" / "互通"
NAMES = ("boot", "popup", "snippet", "shortcut", "sync", "run")


@pytest.fixture
def load(monkeypatch):
    """load("boot")：把 modules/互通/boot.py 當一般模組 import（不寫 .pyc）；結束時從 sys.modules 拿掉。"""
    monkeypatch.syspath_prepend(str(INTEROP))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    for n in NAMES:
        monkeypatch.delitem(sys.modules, n, raising=False)
    yield importlib.import_module
    for n in NAMES:
        sys.modules.pop(n, None)


def fake_iplot(root):
    """root 底下一個看起來像 iPLoT 的資料夾（有 main.py、core/app.py、modules/互通/），回 (home, run_file)。"""
    (root / "core").mkdir(parents=True)
    (root / "core" / "app.py").write_text("", encoding="utf-8")
    (root / "main.py").write_text("", encoding="utf-8")
    (root / "modules" / "互通").mkdir(parents=True)
    return root, str(root / "modules" / "互通" / "run.py")


def fake_framework(root):
    """root 底下一個 python.org 樣子的 Python.framework：回 (bin/python3, Python.app, Python.app 裡的執行檔)。"""
    version = root / "Python.framework" / "Versions" / "3.14"
    exe, app = version / "bin" / "python3", version / "Resources" / "Python.app"
    inner = app / "Contents" / "MacOS" / "Python"
    for f in (exe, inner):
        f.parent.mkdir(parents=True)
        f.write_text("", encoding="utf-8")
    return str(exe), app, str(inner)


def never(*args, **kw):
    pytest.fail(f"不該被呼叫：{args} {kw}")


# ── boot：找 iPLoT、用對的 Python、核對核心版本、提示框（D86） ──

def test_iplot_home_is_two_levels_up(load, tmp_path):
    home, run_file = fake_iplot(tmp_path / "iPLoT")
    assert load("boot").iplot_home(run_file) == home


def test_iplot_home_with_spaces_and_chinese(load, tmp_path):           # Review Focus 3
    home, run_file = fake_iplot(tmp_path / "我的 iPLoT")
    assert load("boot").iplot_home(run_file) == home


def test_iplot_home_none_when_not_in_modules(load, tmp_path):
    assert load("boot").iplot_home(str(tmp_path / "x" / "run.py")) is None


def test_wrong_python_reexecs_once_with_the_recorded_one(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    folder, env, calls = Path(run_file).parent, {}, []
    (folder / ".python").write_text(sys.executable, encoding="utf-8")

    def importer(name):
        raise ImportError("compiled for another Python")

    boot.ensure_python(home, folder, run_file, ["開工"], importer=importer, environ=env,
                       execv=lambda exe, argv: calls.append((exe, argv)), exe="/usr/bin/python3")
    assert calls == [(sys.executable, [sys.executable, run_file, "開工"])] and env[boot.REEXEC] == "1"


def test_after_one_reexec_it_says_one_sentence_instead_of_looping(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    folder = Path(run_file).parent
    (folder / ".python").write_text(sys.executable, encoding="utf-8")

    def importer(name):
        raise ImportError("compiled for another Python")

    said = boot.ensure_python(home, folder, run_file, [], importer=importer, environ={boot.REEXEC: "1"},
                              execv=never, exe="/usr/bin/python3")
    assert said == (f"換成記下的 Python（{sys.executable}）還是開不起來：compiled for another Python。"
                    "在面板按一次「互通」重新記下。")


def test_old_python_without_record_says_one_sentence(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    said = boot.ensure_python(home, Path(run_file).parent, run_file, [], version=(3, 9, 6), importer=never,
                              environ={}, execv=never, exe="/usr/bin/python3")
    assert said == "互通需要 Python 3.10 以上，這個是 3.9.6。先在面板按一次「互通」，讓它記下面板用的 Python。"


def test_lib_that_does_not_load_without_record_says_one_sentence(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")

    def importer(name):
        if name == "webview":
            raise ImportError("bad magic number")

    said = boot.ensure_python(home, Path(run_file).parent, run_file, [], importer=importer, environ={},
                              execv=never, exe="/x/python3")
    assert said == ("這個 Python（/x/python3）載不進 iPLoT 的介面套件（lib/ 是給別的 Python 裝的）。"
                    "先在面板按一次「互通」，讓它記下面板用的 Python。")


def test_a_record_that_is_gone_or_is_this_python_is_not_tried(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    folder = Path(run_file).parent

    def importer(name):
        raise ImportError("x")

    for rec in (str(tmp_path / "gone" / "python3"), sys.executable):
        (folder / ".python").write_text(rec, encoding="utf-8")
        said = boot.ensure_python(home, folder, run_file, [], importer=importer, environ={}, execv=never,
                                  exe=sys.executable)
        assert said.startswith("這個 Python（")


def test_ensure_python_ok_puts_home_and_lib_first(load, tmp_path):
    boot, (home, run_file) = load("boot"), fake_iplot(tmp_path / "iPLoT")
    env = {"IPLOT_INTEROP_REEXEC": "1"}
    assert boot.ensure_python(home, Path(run_file).parent, run_file, [], importer=lambda name: None,
                              environ=env, execv=never) is None
    assert sys.path[:2] == [str(home), str(home / "lib")]
    assert env == {}  # 換過、成功了：之後這個程序開的程式不再帶著這個記號


def test_check_version(load):
    b = load("boot")
    assert b.check_version("0.5.1", 3, "0.1.0") is None and b.check_version("0.5.0", 3, "0.1.0") is None
    assert b.check_version("0.6.0", 3, "0.1.0") == "互通 0.1.0 支援 iPLoT 0.5，這台是 0.6.0。到工作坊看看互通有沒有新版。"
    assert b.check_version("0.5.1", 2, "0.1.0") is not None


def test_alert_passes_text_as_arguments(load, capsys):
    calls = []
    load("boot").alert("互通", "這是 \" 與 ' 與 end tell", platform="darwin", call=calls.append)
    assert calls[0][-2:] == ["互通", "這是 \" 與 ' 與 end tell"] and "end tell" in capsys.readouterr().err
    assert calls[0][:2] == ["osascript", "-e"] and "on run argv" in calls[0]


def test_alert_elsewhere_only_writes_stderr(load, capsys):
    load("boot").alert("互通", "只寫 stderr", platform="linux", call=never)
    assert "只寫 stderr" in capsys.readouterr().err


def test_remember_python_only_when_changed(load, tmp_path):
    boot, record = load("boot"), tmp_path / ".python"
    assert boot.recorded_python(tmp_path) is None
    boot.remember_python(tmp_path, "/a/python3")
    os.utime(record, ns=(1, 1))
    boot.remember_python(tmp_path, "/a/python3")
    assert record.stat().st_mtime_ns == 1 and boot.recorded_python(tmp_path) == "/a/python3"
    boot.remember_python(tmp_path, "/b/python3")
    assert boot.recorded_python(tmp_path) == "/b/python3" and not list(tmp_path.glob(".python.*"))


def test_python_app_from_bin_and_from_the_app_itself(load, tmp_path):
    boot = load("boot")
    exe, app, inner = fake_framework(tmp_path / "fw")
    assert boot.python_app(exe) == app and boot.python_app(inner) == app
    lone = tmp_path / "venv" / "bin" / "python3"
    lone.parent.mkdir(parents=True)
    lone.write_text("", encoding="utf-8")
    assert boot.python_app(str(lone)) is None


def test_the_app_binary_counts_as_the_same_python(load, tmp_path):
    """從捷徑開時 sys.executable 是 Python.app 裡的執行檔，面板記下的是 bin/python3：是同一個，不重寫紀錄。"""
    boot = load("boot")
    exe, _, inner = fake_framework(tmp_path / "fw")
    boot.remember_python(tmp_path, exe)
    os.utime(tmp_path / ".python", ns=(1, 1))
    boot.remember_python(tmp_path, inner)
    assert boot.recorded_python(tmp_path) == exe and (tmp_path / ".python").stat().st_mtime_ns == 1
    assert boot.same_python(exe, inner) and not boot.same_python(exe, "/usr/bin/python3")


def test_own_version(load, tmp_path):
    boot = load("boot")
    assert boot.own_version(tmp_path) == "?"
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [0.2.0] - 2026-10-08\n\nx\n\n## [0.1.0]\n",
                                           encoding="utf-8")
    assert boot.own_version(tmp_path) == "0.2.0" and boot.own_version(INTEROP) == "0.1.0"


def test_boot_and_run_read_on_python_3_8():
    for name in ("boot.py", "run.py"):
        if (INTEROP / name).exists():
            ast.parse((INTEROP / name).read_text(encoding="utf-8"), feature_version=(3, 8))
