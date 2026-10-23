import contextlib
import subprocess
import sys
from pathlib import Path

import pytest

from core.create import AlreadyExists, BadName, new_module, template
from core.meta import read_meta

SNIPPET_MARK = "# ── 互通 ──"


def test_template_is_readable_by_meta(tmp_path):
    f = tmp_path / "iplot.py"
    f.write_text(template(), encoding="utf-8")
    m = read_meta(f)
    assert (m.has_run, m.accepts_files, m.title, m.error) == (True, False, None, None)


def test_creates_folder_and_file(tmp_path):
    folder = new_module(tmp_path, "A")
    assert folder == tmp_path / "A"
    assert (folder / "iplot.py").read_text(encoding="utf-8") == template()


def test_existing_folder_without_iplot_becomes_module(tmp_path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "keep.txt").write_text("x", encoding="utf-8")
    folder = new_module(tmp_path, "Documents")
    assert sorted(p.name for p in folder.iterdir()) == ["iplot.py", "keep.txt"]


def test_already_exists(tmp_path):
    new_module(tmp_path, "A")
    with pytest.raises(AlreadyExists):
        new_module(tmp_path, "A")


@pytest.mark.parametrize("bad", ["", "  ", "a/b", ".hidden", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b",
                                 "a>b", "a|b", "x.", "x ", "a\tb", "CON", "con", "nul.txt", "COM1", "LPT9"])
def test_bad_name(tmp_path, bad):
    with pytest.raises(BadName):
        new_module(tmp_path, bad)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("good", ["整理 桌面", "a.b", "COM10", "CONTEXT", "nul2", " a"])
def test_good_name(tmp_path, good):
    assert new_module(tmp_path, good) == tmp_path / good


def test_chinese_name_ok(tmp_path):
    assert (new_module(tmp_path, "整理 桌面") / "iplot.py").is_file()


def test_never_overwrites_differently_cased_iplot(tmp_path):
    old = tmp_path / "old"
    old.mkdir()
    (old / "iPLoT.py").write_text("original", encoding="utf-8")
    with contextlib.suppress(AlreadyExists):
        new_module(tmp_path, "old")
    assert (old / "iPLoT.py").read_text(encoding="utf-8") == "original"


def test_template_says_run_is_optional():
    assert "可省略" in template()


def test_new_module_has_no_interop_snippet(tmp_path):
    """0.5.1 的範本回到 0.5.0 的樣子：＋ 建出來的 iplot.py 不帶「互通」那一小段（要直接執行就在「互通」按「加上」）。"""
    assert SNIPPET_MARK not in template()
    folder = new_module(tmp_path, "A")
    assert SNIPPET_MARK not in (folder / "iplot.py").read_text(encoding="utf-8")


def test_template_passes_ruff():
    """＋ 建出來的模組要過這個 repo 的 ruff check（設計 4.2）：範本到下一個大版本都改不了，所以在這裡擋。"""
    pytest.importorskip("ruff")
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "--config", str(root / "pyproject.toml"),
                        "--stdin-filename", "iplot.py", "-"], input=template(), capture_output=True,
                       encoding="utf-8")   # 範本有中文與 emoji：不能用 Windows 預設的 cp1252 寫進 stdin
    assert r.returncode == 0, r.stdout
