import dataclasses
from pathlib import Path

import pytest

from core.text import TEMPLATE, T
from core.types import DEFAULT_CONFIG, Group, ModuleInfo, Result


def test_moduleinfo_is_frozen():
    m = ModuleInfo("a", "a", "", Path("a"), Path("a/iplot.py"), Path("."), "here", True, False, False, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.name = "b"


def test_group_note_defaults_none():
    assert Group("這一層", "here", Path("."), ()).note is None


def test_result_has_output():
    assert Result(True, None, 0.0, "").output == ""


def test_default_config():
    assert DEFAULT_CONFIG.roots == ("modules", "..") and DEFAULT_CONFIG.history_keep == 20


def test_text_keys():
    for k in ["here", "parent", "empty_group", "done", "error_at_line", "missing_handler", "title"]:
        assert k in T


def test_module_info_icon_defaults():
    m = ModuleInfo("a", "a", "", Path("a"), Path("a/iplot.py"), Path("."), "here", True, False, False, None)
    assert m.icon is None and m.icon_file is None


def test_panel_text_keys():
    """規格 §7：新面板的文字都在 T，值是中文。"""
    for k in ["menu_run", "menu_enter", "add_tile", "status_hint", "details", "hide_details", "ok", "cancel",
              "scanned", "icon_unusable", "installing", "install_done", "install_failed", "no_tk", "web_failed",
              "running", "tk_in_web", "confirm_foreign", "cancelled", "page_unsupported", "refreshing", "refresh_failed"]:
        assert T.get(k), k
    assert "{roots}" in T["scanned"] and "{count}" in T["scanned"] and "{title}" in T["icon_unusable"]
    assert "{size}" in T["installing"] and "{message}" in T["install_failed"] and "{message}" in T["web_failed"]
    assert "網路" in T["installing"] and "網路" in T["install_failed"], "裝不起來多半是沒網路：兩句都要講"
    assert "{title}" in T["running"] and "--safe" in T["tk_in_web"]
    assert "{title}" in T["confirm_foreign"] and "{title}" in T["cancelled"]
    for key in ("web_failed", "install_failed"):
        assert "安全模式" not in T[key], f"{key}：後備面板不是安全模式（它掃完整範圍），這句話後面開的就是後備面板"
    assert "備用面板" in T["page_unsupported"], "這句話在安全模式與備用面板上都會出現"
    assert "安全模式" in T["no_tk"] and "備用面板" in T["no_tk"], "沒有 tkinter：安全模式與備用面板都開不了"


def test_template_mentions_icon_after_title():
    lines = TEMPLATE.splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith("# TITLE"))
    assert lines[i + 1].startswith('# ICON = "🧩"') and "icon.png" in lines[i + 1]
