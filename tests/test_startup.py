"""規格 §12 從零啟動情境 1–5，用 FakeView 不開視窗。情境 6 由 tests/smoke.py 負責。"""

import dataclasses

import pytest
from conftest import make_module

from core.core import Core, load_config
from core.text import T
from core.types import DEFAULT_CONFIG


def started(home, view, roots=("modules", "..")):
    c = Core(home, dataclasses.replace(DEFAULT_CONFIG, roots=roots), view)
    c.rescan()
    return c


def test_empty_everything(home, view):
    c = started(home, view)
    assert [(g.modules, g.note) for g in c.scope.groups] == [((), None), ((), None)]


def test_missing_root_noted(home, view):
    c = started(home, view, ("modules", "/nonexistent"))
    assert "/nonexistent" in c.scope.groups[1].note


def test_broken_config_falls_back(tmp_path):
    f = tmp_path / "config.py"
    f.write_text("ROOTS = [\n", encoding="utf-8")
    config, err = load_config(f)
    assert config == DEFAULT_CONFIG and err.source == "config"


def test_load_config_wrong_type_falls_back(tmp_path):
    f = tmp_path / "config.py"
    for src in ['ROOTS = "modules"\n', 'HISTORY_KEEP = "20"\n']:
        f.write_text(src, encoding="utf-8")
        config, err = load_config(f)
        assert config == DEFAULT_CONFIG and (err.source, err.kind, err.file) == ("config", "TypeError", f)


def test_only_broken_module_listed(home, view):
    make_module(home / "modules", "Bad", "def run(app)\n    pass\n")
    c = started(home, view)
    [info] = c.scope.groups[0].modules
    assert info.error is not None
    c.press(info)
    assert view.reports[0].line == 1


def test_module_exit_keeps_core_alive(home, view):
    make_module(home / "modules", "A", "def run(app):\n    exit(1)\n")
    c = started(home, view)
    [info] = c.scope.groups[0].modules
    assert not c.press(info).ok
    assert (view.reports[0].kind, view.reports[0].file, view.reports[0].line) == ("SystemExit", info.file, 2)


def test_config_exit_falls_back(tmp_path):
    f = tmp_path / "config.py"
    f.write_text("exit()\n", encoding="utf-8")
    config, err = load_config(f)
    assert config == DEFAULT_CONFIG and (err.source, err.kind) == ("config", "SystemExit")


def test_valid_config_loaded(tmp_path):
    f = tmp_path / "config.py"
    assert load_config(f) == (DEFAULT_CONFIG, None)
    f.write_text('ROOTS = ["modules", "~/Desktop"]\nEDITOR = ["code", "{file}"]\n', encoding="utf-8")
    assert load_config(f) == (dataclasses.replace(
        DEFAULT_CONFIG, roots=("modules", "~/Desktop"), editor=("code", "{file}")), None)


def test_load_config_bad_tilde_falls_back(tmp_path):
    f = tmp_path / "config.py"
    f.write_text('ROOTS = ["modules", "~Desktop"]\n', encoding="utf-8")
    config, err = load_config(f)
    assert config == DEFAULT_CONFIG and (err.source, err.file) == ("config", f)
    assert "~Desktop" in err.message


@pytest.mark.parametrize("src, name", [
    ('ROOTS = "modules"\n', "ROOTS"), ('ROOTS = ["modules", 1]\n', "ROOTS"),
    ('EDITOR = "code"\n', "EDITOR"), ('HISTORY_KEEP = "20"\n', "HISTORY_KEEP"),
    ("HISTORY_KEEP = 0\n", "HISTORY_KEEP"), ("HISTORY_KEEP = True\n", "HISTORY_KEEP"),
    ("EDITOR = []\n", "EDITOR"), ("EDITOR = ()\n", "EDITOR"),
])
def test_load_config_type_errors_name_the_variable(tmp_path, src, name):
    f = tmp_path / "config.py"
    f.write_text(src, encoding="utf-8")
    config, err = load_config(f)
    assert config == DEFAULT_CONFIG and err.kind == "TypeError"
    assert err.message.startswith(name)


def test_plus_without_system_module(home, view):
    c = Core(home, DEFAULT_CONFIG, view)
    c.rescan()
    folder = c.create(home / "modules", "整理桌面")
    assert (folder / "iplot.py").exists()
    assert any(m.name == "整理桌面" for m in c.all_modules())
    assert view.logs[-1] == T["no_system"].format(module="作業系統", name="edit")
