from pathlib import Path
from types import SimpleNamespace

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


def test_missing_run(home):
    r = run_module(mod(home, "def on_files(app, paths):\n    pass\n"), None)
    assert not r.ok and r.error.kind == "MissingHandler"


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
