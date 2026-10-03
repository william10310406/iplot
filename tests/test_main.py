"""main.py 的入口防線。main.py 在 repo 根目錄，不在套件裡，用檔案路徑載入。"""

import importlib.util
import sys
from pathlib import Path

import pytest

from core.text import T


def load_main():
    spec = importlib.util.spec_from_file_location("iplot_main", Path(__file__).resolve().parent.parent / "main.py")
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
