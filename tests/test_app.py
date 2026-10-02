import dataclasses
import re
from pathlib import Path

from core import actions
from core.app import App

CJK = re.compile(r"[一-鿿]")


def test_memory_persists_across_apps(fake_core, info):
    App(fake_core, info).memory["n"] = 1
    assert App(fake_core, info).memory == {"n": 1}


def test_log_goes_to_view(fake_core, info):
    App(fake_core, info).log("hi")
    assert fake_core.view.logs == ["hi"]


def test_edit_uses_config_editor(fake_core, info, monkeypatch):
    seen = []
    monkeypatch.setattr(actions, "edit", lambda *a: seen.append(a))
    fake_core.config = dataclasses.replace(fake_core.config, editor=("code", "{file}"))
    App(fake_core, info).edit(Path("/x"), 3)
    assert seen == [(Path("/x"), ("code", "{file}"), 3)]


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


def test_api_version_is_1(fake_core, info):
    assert App(fake_core, info).api_version == 1


def test_all_members_have_docstrings():
    members = {k: v for k, v in vars(App).items()
               if not k.startswith("_") and (callable(v) or isinstance(v, property))}
    assert set(members) >= {"module", "home", "modules", "memory", "window", "log", "open",
                            "edit", "run", "rescan", "ask", "choose_files", "choose_folder"}
    for name, member in members.items():
        assert CJK.search(member.__doc__ or ""), name
    assert CJK.search(App.__doc__) and "api_version" in App.__doc__


def test_identity_members(fake_core, info, home):
    app = App(fake_core, info)
    assert (app.module, app.home, app.modules, app.window) == (info, home, (), None)
