import unicodedata
from pathlib import Path

from conftest import make_module

from core.scan import find_children, find_modules, is_module, module_info, roots_from_config
from core.text import T
from core.types import Root


def here(home):
    return Root("這一層", "here", home / "modules")


def names(group):
    return [m.name for m in group.modules]


def test_rule_needs_iplot_py(home):
    make_module(home / "modules", "A")
    (home / "modules" / "B").mkdir()
    [g] = find_modules([here(home)])
    assert names(g) == ["A"]


def test_skips_dotfolders_and_symlinks(home):
    a = make_module(home / "modules", "A")
    make_module(home / "modules", ".x")
    (home / "modules" / "link").symlink_to(a)
    [g] = find_modules([here(home)])
    assert names(g) == ["A"]


def test_three_levels(home):
    a = make_module(home / "modules", "A")
    make_module(home.parent, "P")
    make_module(a, "C")
    groups = find_modules(roots_from_config(home, ["modules", ".."]))
    assert [names(g) for g in groups] == [["A"], ["P"]]
    assert groups[0].modules[0].has_children is True
    [c] = find_children(a, home / "modules")
    assert (c.name, c.level) == ("C", "child")


def test_missing_root_has_note(home):
    missing = home / "nope"
    [g] = find_modules([Root("x", "extra", missing)])
    assert g.modules == () and str(missing) in g.note


def test_sorted_by_name(home):
    for n in ["c", "a", "b"]:
        make_module(home / "modules", n)
    [g] = find_modules([here(home)])
    assert names(g) == ["a", "b", "c"]


def test_title_from_meta(home):
    folder = make_module(home / "modules", "kaigong", 'TITLE = "開工"\ndef run(app):\n    pass\n')
    info = module_info(folder, home / "modules", "here")
    assert (info.title, info.name) == ("開工", "kaigong")


def test_name_is_nfc(home):
    nfc = "開工ガイド"  # ガ 有分解形；「開工」兩個漢字沒有，單用它測不到東西
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc
    make_module(home / "modules", nfd)
    [g] = find_modules([here(home)])
    assert names(g) == [nfc]


def test_roots_dedupe(home):
    roots = roots_from_config(home, ["modules", "modules/", str(home / "modules")])
    assert len(roots) == 1 and roots[0].level == "here"


def test_roots_levels(home):
    roots = roots_from_config(home, ["modules", "..", "~/Desktop"])
    assert [r.level for r in roots] == ["here", "parent", "extra"]
    assert roots[2].label == "~/Desktop"
    assert roots[2].path == (Path.home() / "Desktop").resolve()


def test_case_must_match_exactly(home):
    old = home / "modules" / "old"
    old.mkdir()
    (old / "iPLoT.py").write_text("print('old')\n", encoding="utf-8")
    assert not is_module(old)
    [g] = find_modules([here(home)])
    assert g.modules == ()
    assert len(roots_from_config(home, ["modules", "Modules"])) == 1


def test_root_is_a_file_has_note(home):
    f = home / "file.txt"
    f.write_text("x", encoding="utf-8")
    [g] = find_modules([Root("x", "extra", f)])
    assert g.modules == () and g.note == T["root_unreadable"].format(path=f)


def test_unreadable_child_folder_is_skipped(home):
    make_module(home / "modules", "A")
    locked = home / "modules" / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        [g] = find_modules([here(home)])
    finally:
        locked.chmod(0o755)
    assert names(g) == ["A"] and g.note is None
