"""main.py 的入口防線。main.py 在 repo 根目錄，不在套件裡，用檔案路徑載入。"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from core.text import T

ROOT = Path(__file__).resolve().parent.parent
PRE_GATE = ["main.py", "core/__init__.py", "core/text.py"]  # 版本防線之前就會被 import 的檔案


def load_main():
    spec = importlib.util.spec_from_file_location("iplot_main", ROOT / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_old_python_exits_with_message(monkeypatch):
    main = load_main()
    monkeypatch.setattr(sys, "version_info", (3, 9, 6, "final", 0))
    with pytest.raises(SystemExit) as ei:
        main.main()
    assert "3.10" in str(ei.value) and "3.9.6" in str(ei.value)


def test_need_python_text_in_t():
    assert "{found}" in T["need_python"]


def _annotations(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from (a.annotation for a in node.args.args + node.args.kwonlyargs if a.annotation)
            if node.returns:
                yield node.returns


def test_pre_gate_files_import_on_old_python():
    """D46：防線之前 import 的檔案不能用 3.10 才有的語法，型別註記也不能在 import 時求值（3.8 沒有 dict[str, str]）。"""
    for name in PRE_GATE:
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"), feature_version=(3, 7))
        lazy = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                   and any(a.name == "annotations" for a in n.names) for n in tree.body)
        evaluated = [ast.unparse(a) for a in _annotations(tree)
                     if any(isinstance(x, (ast.Subscript, ast.BinOp)) for x in ast.walk(a))]
        assert lazy or not evaluated, f"{name} 的型別註記 {evaluated} 會在舊版 Python import 時炸"
