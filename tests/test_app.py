import dataclasses
import re
from pathlib import Path

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


def test_api_version_is_3(fake_core, info):
    assert App(fake_core, info).api_version == 3


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
