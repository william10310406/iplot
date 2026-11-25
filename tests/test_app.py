import dataclasses
import re
from pathlib import Path

from conftest import make_module

from core.app import App

CJK = re.compile(r"[一-鿿]")


def test_memory_persists_across_apps(fake_core, info):
    App(fake_core, info).memory["n"] = 1
    assert App(fake_core, info).memory == {"n": 1}


def test_log_goes_to_view(fake_core, info):
    App(fake_core, info).log("hi")
    assert fake_core.view.logs == ["hi"]


def test_edit_uses_config_editor(fake_core, info):
    fake_core.config = dataclasses.replace(fake_core.config, editor=("code", "{file}"))
    App(fake_core, info).edit(Path("/x"), 3)
    assert fake_core.calls == [("action", "edit", Path("/x").absolute(), ("code", "{file}"), 3)]


def test_open_reveal_terminal_trash_delegate(fake_core, info):
    app, p = App(fake_core, info), Path("/x").absolute()
    app.open(p)
    app.reveal(p)
    app.terminal(p)
    assert app.trash(p) == "value"
    assert fake_core.calls == [("action", "open", p), ("action", "reveal", p),
                               ("action", "terminal", p), ("action", "trash", p)]


def test_relative_paths_become_absolute_in_the_callers_folder(fake_core, info, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = App(fake_core, info)
    app.open(Path("a.txt"))
    app.edit(Path("b.txt"))
    app.reveal(Path("c"))
    app.terminal(Path("d"))
    app.trash(Path("e"))
    assert [c[2] for c in fake_core.calls] == [Path.cwd() / n for n in ("a.txt", "b.txt", "c", "d", "e")]


def test_run_delegates(fake_core, info):
    assert App(fake_core, info).run("B") == "result"
    assert fake_core.calls == [("run_by_name", "B")]


def test_rescan_delegates(fake_core, info):
    App(fake_core, info).rescan()
    assert fake_core.calls == [("rescan",)]


def test_ask_and_choose_delegate(fake_core, info):
    app = App(fake_core, info)
    assert app.ask("名字？", "預設") == "預設"
    assert app.choose_files() == [Path("/f")] and app.choose_folder() == Path("/d")


def test_api_version_is_7(fake_core, info):
    """3 加了 config、version、page；4 加了 parent、children（D152）；5 加了 call、each、providers 與轉接（D159）；
    6 每按一次另開程序、加了 start 與 MIN_API（D161）；7 加了 top_modules、parent_of、children_of、panel、describe（D164）。"""
    assert App(fake_core, info).api_version == 7


def test_parent_of_and_children_of_work_for_any_module(fake_core, info):
    """導覽列替開頁面的那個模組畫上一層、下一層：問的是別的模組，不是自己（D164）。"""
    other = App(fake_core, info)
    make_module(info.folder, "子")
    [kid] = other.children_of(info)
    assert other.parent_of(kid).folder == info.folder and other.parent_of(info) is None
    assert App(fake_core, kid).children_of(kid) == ()


def test_top_modules_reads_every_root_from_disk(fake_core, info):
    app = App(fake_core, info)
    make_module(fake_core.home / "modules", "新")
    assert {"A", "新"} <= {m.name for m in app.top_modules()}
    assert all(m.level != "child" for m in app.top_modules())


def test_panel_and_describe_ask_the_core(fake_core, info):
    fake_core.view.name = "網頁"
    fake_core.describe = lambda error: "白話：" + error
    app = App(fake_core, info)
    assert app.panel == "網頁" and app.describe("壞了") == "白話：壞了"


def test_children_are_the_modules_one_level_down(fake_core, info):
    make_module(make_module(info.folder, "子二"), "孫")
    make_module(info.folder, "子一")
    kids = App(fake_core, info).children
    assert [(k.name, k.level, k.root, k.has_children) for k in kids] == [
        ("子一", "child", info.root, False), ("子二", "child", info.root, True)]
    assert isinstance(kids, tuple)


def test_children_are_read_from_disk_every_time(fake_core, info):
    app = App(fake_core, info)
    assert app.children == ()
    make_module(info.folder, "新")
    assert [k.name for k in app.children] == ["新"]


def test_parent_is_none_at_the_top_and_the_module_above_otherwise(fake_core, info):
    assert App(fake_core, info).parent is None
    [kid] = (make_module(info.folder, "子"), App(fake_core, info).children)[1]
    up = App(fake_core, kid).parent
    assert (up.name, up.folder, up.level) == ("A", info.folder, "here")


def test_children_and_parent_can_be_handed_to_run(fake_core, info):
    make_module(info.folder, "子")
    [kid] = App(fake_core, info).children
    assert App(fake_core, info).run(kid) == "result"
    assert fake_core.calls == [("run_by_name", kid)]


def test_config_and_version(fake_core, info):
    """模組讀得到設定（唯讀的 Config）與核心版本：「更新」「工作坊」靠這兩樣。"""
    import core
    app = App(fake_core, info)
    assert app.config is fake_core.config and app.version == core.__version__


def test_page_goes_to_view(fake_core, info):
    api = object()
    App(fake_core, info).page("標題", "<p>內容</p>", api)
    App(fake_core, info).page("沒有 api", "<p></p>")
    assert fake_core.view.events == [("page", ("標題", "<p>內容</p>", api)), ("page", ("沒有 api", "<p></p>", None))]


def test_no_window(fake_core, info):
    """D66：沒有 tk 主視窗了，app.window 拿掉（api_version 2）。"""
    assert not hasattr(App(fake_core, info), "window")


def test_confirm_goes_to_view(fake_core, info):
    fake_core.view.answers = [False]
    assert App(fake_core, info).confirm("q") is False
    assert App(fake_core, info).confirm("r") is True  # answers 用完之後預設 True
    assert fake_core.view.confirmed == ["q", "r"]


def test_all_members_have_docstrings():
    members = {k: v for k, v in vars(App).items()
               if not k.startswith("_") and (callable(v) or isinstance(v, property))}
    assert set(members) >= {"module", "home", "modules", "memory", "confirm", "page", "config", "log", "open",
                            "edit", "reveal", "terminal", "trash", "run", "rescan", "ask", "choose_files", "choose_folder"}
    for name, member in members.items():
        assert CJK.search(member.__doc__ or ""), name
    assert CJK.search(App.__doc__) and "api_version" in App.__doc__


def test_identity_members(fake_core, info, home):
    app = App(fake_core, info)
    assert (app.module, app.home, app.modules) == (info, home, ())
