import unicodedata
from pathlib import Path

import pytest
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
    if not (home / "Modules").exists():
        pytest.skip("只在不分大小寫的檔案系統（macOS 預設）上有意義")
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


def test_bad_tilde_root_becomes_missing_not_crash(home):
    [root] = roots_from_config(home, ["~Desktop"])
    [g] = find_modules([root])
    assert g.modules == () and g.note is not None


def icon_of(home, name, *files):
    folder = make_module(home / "modules", name)
    for f in files:
        (folder / f).write_bytes(b"x")
    return module_info(folder, home / "modules", "here").icon_file


def test_icon_file_exact_name(home):
    assert icon_of(home, "A", "icon.png") == home / "modules" / "A" / "icon.png"
    assert icon_of(home, "B", "icon.svg") == home / "modules" / "B" / "icon.svg"
    assert icon_of(home, "C", "Icon.png") is None  # APFS 不分大小寫：比對實際檔名，跟 iplot.py 同一套
    assert icon_of(home, "D", "icon.jpg") is None
    assert icon_of(home, "E") is None


def test_icon_file_prefers_png(home):
    assert icon_of(home, "A", "icon.svg", "icon.png").name == "icon.png"


def test_icon_folder_is_not_an_icon_file(home):
    folder = make_module(home / "modules", "A")
    (folder / "icon.png").mkdir()
    assert module_info(folder, home / "modules", "here").icon_file is None


def test_icon_constant_reaches_module_info(home):
    folder = make_module(home / "modules", "A", 'ICON = "🧩"\ndef run(app):\n    pass\n')
    assert module_info(folder, home / "modules", "here").icon == "🧩"
