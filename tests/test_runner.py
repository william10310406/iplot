import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from conftest import make_module

from core.runner import run_module
from core.scan import module_info
from core.text import T


def mod(home, src, name="A"):
    folder = make_module(home / "modules", name, src)
    return module_info(folder, home / "modules", "here")


def test_calls_run_with_app(home):
    app = SimpleNamespace(seen=[])
    r = run_module(mod(home, "def run(app):\n    app.seen.append(app)\n"), app)
    assert r.ok and r.error is None and app.seen == [app]


def test_fresh_namespace_each_press(home):
    info = mod(home, "def run(app):\n    assert 'FLAG' not in globals()\n    globals()['FLAG'] = 1\n")
    assert run_module(info, None).ok
    assert run_module(info, None).ok


def test_sees_file_changes(home):
    app = SimpleNamespace(seen=[])
    info = mod(home, "def run(app):\n    app.seen.append(1)\n")
    run_module(info, app)
    info.file.write_text("def run(app):\n    app.seen.append(2)\n", encoding="utf-8")
    run_module(info, app)
    assert app.seen == [1, 2]


def test_missing_run_is_not_an_error(home):
    r = run_module(mod(home, "def on_files(app, paths):\n    pass\n"), None)
    assert r.ok and r.error is None


def test_exception_has_file_and_line(home):
    info = mod(home, "def run(app):\n    x = 1\n    1/0\n")
    r = run_module(info, None)
    assert (r.ok, r.error.file, r.error.line, r.error.kind) == (False, info.file, 3, "ZeroDivisionError")


def test_syntax_error_reported(home):
    r = run_module(mod(home, "x = 1\ndef run(app)\n    pass\n"), None)
    assert (r.ok, r.error.kind, r.error.line) == (False, "SyntaxError", 2)


def test_exit_is_error_not_fatal(home):
    info = mod(home, "def run(app):\n    exit()\n")
    r = run_module(info, None)
    assert (r.ok, r.error.kind, r.error.message) == (False, "SystemExit", T["module_exit"])
    assert (r.error.file, r.error.line) == (info.file, 2)


def test_on_files_handler(home):
    app = SimpleNamespace(seen=[])
    info = mod(home, "def on_files(app, paths):\n    app.seen.extend(paths)\n")
    r = run_module(info, app, "on_files", ([Path("a")],))
    assert r.ok and app.seen == [Path("a")]


def test_print_is_captured(home):
    r = run_module(mod(home, "def run(app):\n    print('hi')\n"), None)
    assert r.output == "hi\n"


def test_null_byte_reported_not_raised(home):
    folder = make_module(home / "modules", "A")
    (folder / "iplot.py").write_bytes(b"x = 1\x00\n")
    r = run_module(module_info(folder, home / "modules", "here"), None)
    assert not r.ok and r.error.file == folder / "iplot.py"


def test_eval_syntax_error_points_at_module_line(home):
    info = mod(home, "def run(app):\n    x = 1\n    eval('1+')\n")
    r = run_module(info, None)
    assert (r.error.kind, r.error.file, r.error.line) == ("SyntaxError", info.file, 3)


def test_stderr_is_captured_too(home):
    src = "import sys\ndef run(app):\n    print('out')\n    sys.stderr.write('err\\n')\n"
    assert run_module(mod(home, src), None).output == "out\nerr\n"


# ── 腳本語意（M1.2，D47）：按下 ＝ 在模組自己的資料夾裡執行 python3 iplot.py ──


def test_main_guard_runs(home):
    r = run_module(mod(home, 'if __name__ == "__main__":\n    print("main")\n'), None)
    assert r.output == "main\n"


def test_cwd_is_module_folder_and_restored(home):
    before = os.getcwd()
    info = mod(home, 'open("x.txt", "w").write("1")\n')
    run_module(info, None)
    assert (info.folder / "x.txt").exists()
    assert os.getcwd() == before


def test_sys_argv_is_module_file(home):
    before = sys.argv
    info = mod(home, "import sys\nprint(sys.argv)\n")
    r = run_module(info, None)
    assert r.output == f"{[str(info.file)]}\n"
    assert sys.argv is before


def test_sibling_import_reloads_after_edit(home, monkeypatch):
    # 同一秒內改成同樣大小的內容，舊的 .pyc 會被當成有效：執行期間不寫 .pyc 才保證重讀
    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    info = mod(home, "import helper\nprint(helper.V)\n")
    (info.folder / "helper.py").write_text("V = 1\n", encoding="utf-8")
    assert run_module(info, None).output == "1\n"
    (info.folder / "helper.py").write_text("V = 2\n", encoding="utf-8")
    assert run_module(info, None).output == "2\n"


def test_purge_spares_modules_loaded_before_the_run(home, monkeypatch):
    # iPLoT 放在某個模組的資料夾裡時，core 自己的 __file__ 也在那個資料夾底下：不能被清掉
    info = mod(home, "x = 1\n")
    early = ModuleType("early")
    early.__file__ = str(info.folder / "early.py")
    monkeypatch.setitem(sys.modules, "early", early)
    run_module(info, None)
    assert sys.modules.get("early") is early


def test_toplevel_script_without_run_is_ok(home):
    r = run_module(mod(home, 'print("hi")\n'), None)
    assert (r.ok, r.error, r.output) == (True, None, "hi\n")


def test_on_files_missing_still_errors(home):
    r = run_module(mod(home, 'print("hi")\n'), None, "on_files", ([Path("a")],))
    assert not r.ok and r.error.kind == "MissingHandler"
