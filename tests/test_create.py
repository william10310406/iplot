import contextlib

import pytest

from core.create import AlreadyExists, BadName, new_module, template
from core.meta import read_meta


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


@pytest.mark.parametrize("bad", ["", "  ", "a/b", ".hidden"])
def test_bad_name(tmp_path, bad):
    with pytest.raises(BadName):
        new_module(tmp_path, bad)
    assert list(tmp_path.iterdir()) == []


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
