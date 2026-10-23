"""Tk 測試什麼時候可以跳過（conftest.new_tk）：只有 Linux 沒有顯示器時；其他 TclError 照原本 Tcl 的訊息丟出去。"""

import sys

import pytest
from conftest import new_tk

tkinter = pytest.importorskip("tkinter")
TCL = 'couldn\'t connect to display ":0"'


@pytest.fixture
def broken_tk(monkeypatch):
    """Tk() 一建就丟 TclError；DISPLAY、WAYLAND_DISPLAY 先拿掉，各測試自己決定要不要給。"""
    def boom(*args, **kwargs):
        raise tkinter.TclError(TCL)

    monkeypatch.setattr(tkinter, "Tk", boom)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    return monkeypatch


def test_linux_without_a_display_is_skipped(broken_tk):
    broken_tk.setattr(sys, "platform", "linux")
    with pytest.raises(pytest.skip.Exception, match="沒有顯示器"):
        new_tk()


@pytest.mark.parametrize(("platform", "env"), [
    ("linux", {"DISPLAY": ":0"}), ("linux", {"WAYLAND_DISPLAY": "wayland-0"}), ("win32", {}), ("darwin", {}),
])
def test_any_other_tcl_error_fails_with_the_tcl_message(broken_tk, platform, env):
    broken_tk.setattr(sys, "platform", platform)
    for name, value in env.items():
        broken_tk.setenv(name, value)
    with pytest.raises(tkinter.TclError) as raised:
        new_tk()
    assert str(raised.value) == TCL


def test_a_working_tk_is_returned_as_is(monkeypatch):
    root = object()
    monkeypatch.setattr(tkinter, "Tk", lambda: root)
    assert new_tk() is root
