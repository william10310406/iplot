"""面板上的「改名…」「移到垃圾桶…」（Discussion #4）：只動使用者自己新增的模組；隨附的、從工作坊裝來的，擋下並說為什麼。
刪除一律是系統的垃圾桶（交給「作業系統」模組的 trash），不直接刪。這裡的垃圾桶是假的：搬到 home 旁邊的資料夾。測試絕不碰真的垃圾桶。"""

import fnmatch
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest
from conftest import make_module

from core import scan
from core.core import Core
from core.text import BUNDLED, T
from core.types import DEFAULT_CONFIG

ROOT = Path(__file__).resolve().parents[1]
FAKE_OS = ('import shutil\nfrom pathlib import Path\n\n'
           'def trash(app, path):\n'
           '    bin_ = Path(app.home) / "fake-trash"\n'
           '    bin_.mkdir(exist_ok=True)\n'
           '    dest = bin_ / Path(path).name\n'
           '    shutil.move(str(path), str(dest))\n'
           '    return dest\n')


def started(home, view):
    core = Core(home, DEFAULT_CONFIG, view)
    core.rescan()
    return core


def find(core, name):
    return next(m for m in core.all_modules() if m.name == name)


@pytest.fixture
def os_module(home):
    return make_module(home / "modules", "作業系統", FAKE_OS)


# ── 誰可以動 ──

def test_own_module_can_be_renamed(home, view):
    make_module(home / "modules", "我的")
    core = started(home, view)
    assert core.rename(find(core, "我的"), "新的") == home / "modules" / "新的"


@pytest.mark.parametrize("name", sorted(BUNDLED))
@pytest.mark.parametrize("action", ["rename", "remove"])
def test_bundled_modules_are_refused_with_a_reason(home, view, os_module, name, action):
    make_module(home / "modules", name)
    core = started(home, view)
    info = find(core, name)
    result = core.rename(info, "別的名字") if action == "rename" else core.remove(info)
    assert not result and (home / "modules" / name / "iplot.py").is_file()
    assert view.logs == [T["protected_bundled"].format(name=name)] and view.confirmed == []


def test_a_user_module_that_shares_a_bundled_name_elsewhere_is_not_protected(home, view, os_module):
    """隨附的是 modules/ 底下的那一個；別的根目錄（例如 iPLoT 的上一層）裡同名的是使用者自己的。"""
    make_module(home.parent, "開工")
    core = started(home, view)
    info = next(m for m in core.all_modules() if m.folder.parent == home.parent.resolve())
    assert core.rename(info, "我的開工") is not None


def test_child_of_a_bundled_module_is_refused(home, view):
    make_module(home / "modules" / "開工", "孩子")
    make_module(home / "modules", "開工")
    core = started(home, view)
    info = scan.find_children(home / "modules" / "開工", (home / "modules").resolve())[0]
    assert core.rename(info, "x") is None and core.remove(info) is False
    assert view.logs == [T["protected_bundled"].format(name="開工")] * 2


def test_workshop_module_cannot_be_renamed_but_can_be_removed_after_a_warning(home, view, os_module):
    folder = make_module(home / "modules", "外來")
    (folder / ".origin").write_text("source: x\n", encoding="utf-8")
    core = started(home, view)
    assert core.rename(find(core, "外來"), "改了") is None
    assert view.logs == [T["protected_workshop"].format(name="外來")] and folder.is_dir()
    assert core.remove(find(core, "外來")) is True
    assert not folder.exists() and (home / "fake-trash" / "外來" / ".origin").is_file()
    assert view.confirmed[-1].endswith(T["confirm_remove_workshop"])


def test_child_of_a_workshop_module_is_part_of_it(home, view):
    parent = make_module(home / "modules", "課")
    (parent / ".origin").write_text("source: x\n", encoding="utf-8")
    make_module(parent, "一課")
    core = started(home, view)
    kid = scan.find_children(parent, (home / "modules").resolve())[0]
    assert core.rename(kid, "x") is None and core.remove(kid) is False
    assert view.logs == [T["protected_parent"].format(name="一課", parent="課")] * 2 and view.confirmed == []


# ── 改名 ──

def test_rename_moves_the_folder_with_everything_in_it_and_it_still_runs(home, view):
    folder = make_module(home / "modules", "舊", 'def run(app):\n    print("跑了", app.module.name)\n')
    (folder / "資料.txt").write_text("留著", encoding="utf-8")
    core = started(home, view)
    core.press(find(core, "舊"))  # 先跑一次：有 .history、memory
    assert (folder / ".history").is_dir()
    assert core.rename(find(core, "舊"), "新") == home / "modules" / "新"
    assert not folder.exists()
    assert (home / "modules" / "新" / "資料.txt").read_text(encoding="utf-8") == "留著"
    assert (home / "modules" / "新" / ".history").is_dir()
    assert view.logs[-1] == T["renamed"].format(old="舊", new="新")
    assert [m.name for m in view.shows[-1].groups[0].modules] == ["新"]
    assert core.press(find(core, "新")).ok and "跑了 新" in view.logs
    assert folder.resolve() not in core.memories


def test_rename_carries_the_submodules_along(home, view):
    parent = make_module(home / "modules", "爸")
    make_module(parent, "兒")
    core = started(home, view)
    core.rename(find(core, "爸"), "爹")
    kids = scan.find_children(home / "modules" / "爹", (home / "modules").resolve())
    assert [k.name for k in kids] == ["兒"] and core.press(kids[0]).ok


@pytest.mark.parametrize("taken", ["B", "b"])
def test_rename_onto_an_existing_name_is_refused_and_nothing_moves(home, view, taken):
    a, b = make_module(home / "modules", "A"), make_module(home / "modules", "B")
    core = started(home, view)
    assert core.rename(find(core, "A"), taken) is None
    assert a.is_dir() and b.is_dir()
    assert view.logs[-1] == T["name_taken"].format(name=taken)


def test_rename_onto_an_existing_non_module_folder_or_file_is_refused_too(home, view):
    a = make_module(home / "modules", "A")
    (home / "modules" / "資料夾").mkdir()
    (home / "modules" / "檔案.txt").write_text("x")
    core = started(home, view)
    for taken in ("資料夾", "檔案.txt"):
        assert core.rename(find(core, "A"), taken) is None
    assert a.is_dir() and len(view.logs) == 2


def test_nfd_and_nfc_spellings_of_one_name_are_the_same_name(home, view):
    nfc = "ガ"
    make_module(home / "modules", "A")
    make_module(home / "modules", nfc)
    core = started(home, view)
    assert core.rename(find(core, "A"), unicodedata.normalize("NFD", nfc)) is None
    assert view.logs[-1].startswith("這裡已經有叫")


@pytest.mark.parametrize("bad", ["", "  ", ".隱藏", "a/b", "a:b", "結尾.", "CON", "nul.txt", 'a"b', "a\x01"])
def test_rename_to_an_unportable_name_is_refused_with_the_naming_rules(home, view, bad):
    folder = make_module(home / "modules", "A")
    core = started(home, view)
    assert core.rename(find(core, "A"), bad) is None
    assert view.logs == [T["bad_name"]] and folder.is_dir()


def test_rename_to_the_same_name_does_nothing(home, view):
    make_module(home / "modules", "A")
    core = started(home, view)
    assert core.rename(find(core, "A"), "A") is None and view.logs == []


def test_rename_only_the_case_is_allowed(home, view):
    make_module(home / "modules", "abc")
    core = started(home, view)
    assert core.rename(find(core, "abc"), "ABC") == home / "modules" / "ABC"
    assert "ABC" in [p.name for p in (home / "modules").iterdir()]


def test_rename_trims_the_spaces_around_the_name(home, view):
    make_module(home / "modules", "A")
    core = started(home, view)
    assert core.rename(find(core, "A"), "  新名字 ") == home / "modules" / "新名字"


def test_rename_that_the_system_refuses_says_why_and_leaves_the_folder(home, view, monkeypatch):
    folder = make_module(home / "modules", "A")
    core = started(home, view)

    def refuse(self, target):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "rename", refuse)
    assert core.rename(find(core, "A"), "B") is None
    assert "沒有權限" in view.logs[-1] and "PermissionError" not in view.logs[-1] and folder.is_dir()


# ── 移到垃圾桶 ──

def test_remove_asks_first_and_cancel_touches_nothing(home, view, os_module):
    folder = make_module(home / "modules", "A")
    view.answers = [False]
    core = started(home, view)
    assert core.remove(find(core, "A")) is False
    assert folder.is_dir() and not (home / "fake-trash").exists() and view.logs == []
    assert "A" in view.confirmed[0] and str(folder) in view.confirmed[0] and "找回來" in view.confirmed[0]


def test_remove_moves_the_whole_folder_to_the_trash_it_never_deletes(home, view, os_module):
    folder = make_module(home / "modules", "A")
    (folder / "資料.txt").write_text("重要", encoding="utf-8")
    core = started(home, view)
    assert core.remove(find(core, "A")) is True
    assert not folder.exists()
    assert (home / "fake-trash" / "A" / "資料.txt").read_text(encoding="utf-8") == "重要"
    assert view.logs[-1] == T["removed"].format(title="A")
    assert "A" not in [m.name for m in view.shows[-1].groups[0].modules]


def test_remove_never_calls_a_direct_delete(home, view, os_module, monkeypatch):
    make_module(home / "modules", "A")
    core = started(home, view)

    def boom(*a, **k):
        raise AssertionError("不能直接刪")

    monkeypatch.setattr(shutil, "rmtree", boom)
    monkeypatch.setattr(Path, "rmdir", boom)
    assert core.remove(find(core, "A")) is True


def test_remove_without_the_system_module_leaves_the_folder_and_says_so(home, view):
    folder = make_module(home / "modules", "A")
    core = started(home, view)
    assert core.remove(find(core, "A")) is False
    assert folder.is_dir() and view.logs[-1] == T["remove_failed"].format(title="A")
    assert T["no_system"].format(module="作業系統", name="trash") in view.logs


def test_remove_when_the_trash_fails_reports_it_and_leaves_the_folder(home, view):
    make_module(home / "modules", "作業系統", 'def trash(app, path):\n    raise OSError("垃圾桶滿了")\n')
    folder = make_module(home / "modules", "A")
    core = started(home, view)
    assert core.remove(find(core, "A")) is False
    assert folder.is_dir() and view.reports and view.logs[-1] == T["remove_failed"].format(title="A")


def test_remove_a_submodule_only_moves_that_submodule(home, view, os_module):
    parent = make_module(home / "modules", "爸")
    make_module(parent, "兒")
    core = started(home, view)
    kid = scan.find_children(parent, (home / "modules").resolve())[0]
    assert core.remove(kid) is True
    assert parent.is_dir() and not (parent / "兒").exists() and (home / "fake-trash" / "兒").is_dir()


# ── 隨附的名單要跟核心的包一致 ──

def test_bundled_names_match_what_the_core_package_ships():
    """BUNDLED ＝ git 追蹤的 modules/ 底下、沒有被 .gitattributes 標 export-ignore 的資料夾（核心的包帶的那些）。"""
    git = subprocess.run(["git", "ls-files", "modules"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if git.returncode:
        pytest.skip("不是 git 的工作目錄")
    ignored = [line.split()[0].rstrip("/") for line in (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.startswith("#") and line.split()[-1] == "export-ignore"]
    tracked = {line.split("/")[1] for line in git.stdout.splitlines() if "/" in line}
    shipped = {name for name in tracked if not any(fnmatch.fnmatch(f"modules/{name}", pat.rstrip("/")) for pat in ignored)}
    assert shipped == set(BUNDLED), f"核心的包帶的是 {sorted(shipped)}；core/text.py 的 BUNDLED 是 {sorted(BUNDLED)}"
