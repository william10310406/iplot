import ast
import contextlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.core import Core
from core.create import AlreadyExists, BadName, new_module, template
from core.meta import read_meta
from core.types import DEFAULT_CONFIG

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


def _tree(tmp_path, with_run_py):
    """tmp/我的 iPLoT/modules/A 是用範本建的模組；with_run_py 時放一個假的 modules/互通/run.py：
    把收到的參數寫成 argv.json、以 3 結束。"""
    home = tmp_path / "我的 iPLoT"
    (home / "modules").mkdir(parents=True)
    folder = new_module(home / "modules", "A")
    if with_run_py:
        run = home / "modules" / "互通" / "run.py"
        run.parent.mkdir(parents=True)
        run.write_text("import json, sys\nopen(sys.argv[0] + '.argv.json', 'w').write(json.dumps(sys.argv[1:]))\n"
                       "sys.exit(3)\n", encoding="utf-8")
    return home, folder


def test_template_carries_the_interop_snippet_after_the_docstring():
    tree = ast.parse(template())
    assert ast.get_docstring(tree) == "一句話說明這個模組做什麼。"
    assert template().splitlines()[1].startswith(SNIPPET_MARK)


def test_template_snippet_does_nothing_inside_iplot(home, view, monkeypatch):
    new_module(home / "modules", "A")
    monkeypatch.setattr(subprocess, "call", lambda *a, **k: pytest.fail("在 iPLoT 裡不該交出去"))
    c = Core(home, DEFAULT_CONFIG, view)
    c.rescan()
    assert c.press(next(m for m in c.all_modules() if m.name == "A")).ok


def test_template_snippet_without_interop_says_one_sentence(tmp_path):
    _, folder = _tree(tmp_path, with_run_py=False)
    r = subprocess.run([sys.executable, "iplot.py"], cwd=folder, capture_output=True, text=True)
    assert r.returncode == 1 and "找不到 iPLoT 的「互通」" in r.stderr


def test_template_snippet_hands_folder_and_args_to_run_py(tmp_path):
    home, folder = _tree(tmp_path, with_run_py=True)
    r = subprocess.run([sys.executable, "iplot.py", "f.txt"], cwd=folder, capture_output=True, text=True)
    argv = json.loads((home / "modules" / "互通" / "run.py.argv.json").read_text(encoding="utf-8"))
    assert r.returncode == 3 and argv == [str(folder), "f.txt"]


def test_template_snippet_finds_iplot_from_beside_it(tmp_path):
    home, _ = _tree(tmp_path, with_run_py=True)
    beside = new_module(tmp_path, "旁邊的模組")            # 跟 iPLoT 資料夾同一層（ROOTS 的 ".."）
    r = subprocess.run([sys.executable, "iplot.py"], cwd=beside, capture_output=True, text=True)
    assert r.returncode == 3


def test_template_snippet_reads_on_python_3_8():
    ast.parse(template(), feature_version=(3, 8))


def test_template_passes_ruff():
    """＋ 建出來的模組要過這個 repo 的 ruff check（設計 4.2）：範本到下一個大版本都改不了，所以在這裡擋。"""
    pytest.importorskip("ruff")
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run([sys.executable, "-m", "ruff", "check", "--config", str(root / "pyproject.toml"),
                        "--stdin-filename", "iplot.py", "-"], input=template(), capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
