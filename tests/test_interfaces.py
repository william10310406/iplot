"""工作坊模組可以依賴的核心介面（D85，docs/07 第 13 節）：到 1.0.0 之前只加不改。
這裡把每一項的名字、參數與預設值釘住；改了任何一項，就是大版本（D80），「互通」「主控面板」要同時跟著改。"""

import dataclasses
import importlib.util
import inspect

import pytest
from conftest import make_module

import core
from core import errors, history, scan
from core.app import App
from core.core import Core, View, load_config
from core.runner import run_module
from core.text import SYSTEM_MODULE, T
from core.types import Config, ErrorInfo, Group, ModuleInfo, Result, Root, Scope

EMPTY = inspect.Parameter.empty


def params(fn):
    """[(參數名, 預設值)]；沒有預設值的是 EMPTY。"""
    return [(p.name, p.default) for p in inspect.signature(fn).parameters.values()]


def test_version_and_api_version():
    assert isinstance(core.__version__, str) and core.__version__.startswith("0.")
    assert App.api_version >= 3


@pytest.mark.parametrize(("fn", "expected"), [
    (Core.__init__, [("self", EMPTY), ("home", EMPTY), ("config", EMPTY), ("view", EMPTY), ("safe", False)]),
    (Core.rescan, [("self", EMPTY)]),
    (Core.all_modules, [("self", EMPTY)]),
    (Core.roots, [("self", EMPTY)]),
    (Core.press, [("self", EMPTY), ("info", EMPTY), ("handler", "run"), ("args", ()), ("quiet", False)]),
    (Core.run_by_name, [("self", EMPTY), ("name", EMPTY)]),
    (Core.action, [("self", EMPTY), ("name", EMPTY), ("args", EMPTY)]),
    (load_config, [("path", EMPTY)]),
    (scan.module_info, [("folder", EMPTY), ("root", EMPTY), ("level", EMPTY)]),
    (scan.find_modules, [("roots", EMPTY)]),
    (scan.find_children, [("folder", EMPTY), ("root", EMPTY)]),
    (scan.roots_from_config, [("home", EMPTY), ("roots", EMPTY)]),
    (scan.is_module, [("folder", EMPTY)]),
    (history.snapshot, [("file", EMPTY), ("keep", EMPTY)]),
    (errors.describe, [("error", EMPTY)]),
], ids=lambda x: getattr(x, "__qualname__", ""))
def test_signatures(fn, expected):
    assert params(fn) == expected


def test_action_takes_any_number_of_args():
    assert inspect.signature(Core.action).parameters["args"].kind is inspect.Parameter.VAR_POSITIONAL


def test_core_attributes(home, view):
    c = Core(home, load_config(home / "config.py")[0], view)
    assert (c.home, c.config.roots) == (home, ("modules", ".."))
    assert isinstance(c.scope, Scope)


def test_view_has_the_eight_methods():
    names = {"show", "log", "report", "ask", "confirm", "page", "choose_files", "choose_folder"}
    assert names <= {n for n in vars(View) if not n.startswith("_")}
    assert params(View.ask) == [("self", EMPTY), ("prompt", EMPTY), ("default", "")]
    assert params(View.page) == [("self", EMPTY), ("title", EMPTY), ("html", EMPTY), ("api", EMPTY)]


def test_load_config_returns_config_and_error(tmp_path):
    (tmp_path / "config.py").write_text("ROOTS = 1\n", encoding="utf-8")
    config, err = load_config(tmp_path / "config.py")
    assert isinstance(config, Config) and isinstance(err, ErrorInfo)
    assert load_config(tmp_path / "nope.py")[1] is None


@pytest.mark.parametrize(("cls", "fields"), [
    (Config, {"roots", "editor", "history_keep", "update_url", "workshop_url"}),
    (ErrorInfo, {"kind", "message", "file", "line", "traceback_text", "source", "module"}),
    (ModuleInfo, {"name", "title", "description", "folder", "file", "root", "level", "has_run",
                  "accepts_files", "has_children", "error", "icon", "icon_file"}),
    (Result, {"ok", "error", "duration", "output", "value"}),
    (Scope, {"crumbs", "groups"}),
    (Group, {"label", "level", "root", "modules", "note"}),
    (Root, {"label", "level", "path"}),
], ids=lambda x: getattr(x, "__name__", ""))
def test_types_keep_their_fields(cls, fields):
    """只加不改：這些欄位都還在（多了新的欄位不算違反）。"""
    assert fields <= {f.name for f in dataclasses.fields(cls)}


def test_text_keys_and_system_module():
    assert {"not_found", "ambiguous"} <= set(T)
    assert "{name}" in T["not_found"] and "{name}" in T["ambiguous"] and "{paths}" in T["ambiguous"]
    assert SYSTEM_MODULE == "作業系統"


def test_core_runner_is_loaded_while_a_module_runs(home, fake_core):
    folder = make_module(home / "modules", "A", 'import sys\nprint("core.runner" in sys.modules)\n')
    info = scan.module_info(folder, home / "modules", "here")
    assert run_module(info, App(fake_core, info)).output.strip() == "True"


def test_panel_modules_keep_their_names():
    """面板的程序裡 "ui.web" 或 "ui.tk" 在 sys.modules 裡（「主控面板」靠它判斷自己是不是在面板裡）。"""
    assert importlib.util.find_spec("ui.web") is not None and importlib.util.find_spec("ui.tk") is not None
