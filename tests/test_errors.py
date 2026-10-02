import runpy
from pathlib import Path

import pytest

from core.errors import describe, from_exception
from core.types import ErrorInfo, ModuleInfo


def info_for(f):
    return ModuleInfo("開工", "開工", "", f.parent, f, f.parent, "here", True, False, False, None)


def raised_by(f, src, kind):
    f.write_text(src, encoding="utf-8")
    with pytest.raises(kind) as ei:
        runpy.run_path(str(f))
    return ei.value


def test_line_from_module_frame(tmp_path):
    f = tmp_path / "iplot.py"
    e = from_exception(raised_by(f, "x=1\nraise ValueError('boom')\n", ValueError), info_for(f), "module")
    assert (e.file, e.line, e.kind, e.message) == (f, 2, "ValueError", "boom")


def test_innermost_module_frame(tmp_path):
    f = tmp_path / "iplot.py"
    src = "def a():\n    b()\n\ndef b():\n    raise ValueError('x')\n\na()\n"
    e = from_exception(raised_by(f, src, ValueError), info_for(f), "module")
    assert e.line == 5


def test_syntax_error(tmp_path):
    f = tmp_path / "iplot.py"
    with pytest.raises(SyntaxError) as ei:
        compile("def run(app)\n  pass\n", str(f), "exec")
    e = from_exception(ei.value, info_for(f), "module")
    assert (e.file, e.line) == (f, ei.value.lineno)


def boom():
    raise KeyError("k")


def test_no_info_uses_last_frame():
    with pytest.raises(KeyError) as ei:
        boom()
    e = from_exception(ei.value, None, "core")
    assert (e.file, e.line, e.module) == (Path(__file__), boom.__code__.co_firstlineno + 1, None)


def test_describe_module_with_line():
    e = ErrorInfo("ValueError", "boom", Path("x"), 2, "", "module", "開工")
    assert describe(e) == "模組『開工』第 2 行出錯：ValueError，boom"


def test_describe_core():
    e = ErrorInfo("KeyError", "'k'", None, None, "", "core", None)
    assert describe(e).startswith("核心錯誤：")


def test_decode_error_points_at_module_file(tmp_path):
    f = tmp_path / "iplot.py"
    f.write_bytes("x = '中文'\n".encode("big5"))
    with pytest.raises(UnicodeDecodeError) as ei:
        f.read_text(encoding="utf-8-sig")
    e = from_exception(ei.value, info_for(f), "module")
    assert (e.file, e.line) == (f, None)
    assert describe(e).startswith("模組『開工』出錯：UnicodeDecodeError")


def test_empty_traceback(tmp_path):
    e = from_exception(ValueError("x"), info_for(tmp_path / "iplot.py"), "module")
    assert (e.file, e.line) == (None, None)
