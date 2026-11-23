"""依角色找模組（D159）：模組在 iplot.py 頂層宣告 PROVIDES = {"角色": "函式名"}，核心用 ast 讀、不執行，
providers／call／each 依掃描順序交給它們；角色是什麼意思核心不管。從工作坊裝來的（.origin）要使用者允許過才算。"""

import json
from pathlib import Path

import pytest
from conftest import make_module

from core import scan
from core.app import App
from core.core import Core
from core.meta import read_meta
from core.text import T
from core.types import DEFAULT_CONFIG

GREET = 'PROVIDES = {"greet": "hello"}\n\ndef hello(app, who):\n    return f"{app.module.name} 跟 {who} 打招呼"\n'


def started(home, view):
    core = Core(home, DEFAULT_CONFIG, view)
    core.rescan()
    return core


# ── 宣告 ──

@pytest.mark.parametrize(("source", "expected"), [
    ('PROVIDES = {"a": "f", "b.c": "g"}\n', (("a", "f"), ("b.c", "g"))),
    ("PROVIDES = {}\n", ()),
    ('PROVIDES = {"a": 1}\n', ()),  # 不是字串對字串：整份不算
    ('PROVIDES = {**X}\n', ()),
    ('PROVIDES = dict(a="f")\n', ()),  # 只認字面值，不執行
    ('X = "a"\nPROVIDES = {X: "f"}\n', ()),
    ('if True:\n    PROVIDES = {"a": "f"}\n', ()),  # 只看頂層
])
def test_provides_is_read_without_running_and_only_as_a_literal(tmp_path, source, expected):
    file = tmp_path / "iplot.py"
    file.write_text(source + "raise SystemExit('不該執行')\n", encoding="utf-8")
    assert read_meta(file).provides == expected


def test_module_info_carries_what_it_provides(home):
    folder = make_module(home / "modules", "A", GREET)
    assert scan.module_info(folder, home / "modules", "here").provides == (("greet", "hello"),)


# ── providers、call、each ──

def test_providers_are_in_scan_order_and_only_those_that_declare_the_role(home, view):
    make_module(home / "modules", "B", GREET)
    make_module(home / "modules", "A", GREET)
    make_module(home / "modules", "C")
    core = started(home, view)
    assert [m.name for m in core.providers("greet")] == ["A", "B"] and core.providers("別的") == []


def test_call_runs_the_first_provider_and_each_runs_all(home, view):
    make_module(home / "modules", "A", GREET)
    make_module(home / "modules", "B", GREET)
    core = started(home, view)
    assert core.call("greet", "你") == "A 跟 你 打招呼"
    assert [(m.name, v) for m, v in core.each("greet", "我")] == [("A", "A 跟 我 打招呼"), ("B", "B 跟 我 打招呼")]
    assert view.logs == []  # 走 press 的 quiet：不記「完成」


def test_call_with_no_provider_is_none_and_says_nothing(home, view):
    core = started(home, view)
    assert core.call("沒人提供") is None and core.each("沒人提供") == [] and view.logs == []


def test_a_broken_provider_is_reported_like_any_module_and_the_others_still_run(home, view):
    make_module(home / "modules", "A", 'PROVIDES = {"greet": "hello"}\n\ndef hello(app, who):\n    1 / 0\n')
    make_module(home / "modules", "B", GREET)
    core = started(home, view)
    assert [v for _, v in core.each("greet", "你")] == [None, "B 跟 你 打招呼"]
    assert [e.kind for e in view.reports] == ["ZeroDivisionError"]


def test_providers_on_the_other_roots_count_too(home, view):
    make_module(home.parent, "上一層的", GREET)
    core = started(home, view)
    assert core.call("greet", "你") == "上一層的 跟 你 打招呼"


# ── app ──

def test_app_forwards_names_it_does_not_have_to_a_provider_of_app_name(home, view):
    make_module(home / "modules", "通知", 'PROVIDES = {"app.notify": "notify"}\n\ndef notify(app, text):\n'
                '    return "通知：" + text\n')
    user = make_module(home / "modules", "用的人", 'def run(app):\n    return app.notify("嗨")\n')
    core = started(home, view)
    info = scan.module_info(user, (home / "modules").resolve(), "here")
    assert core.press(info).value == "通知：嗨"


def test_hasattr_still_tells_whether_anyone_provides_it(home, view):
    folder = make_module(home / "modules", "A")
    core = started(home, view)
    app = App(core, scan.module_info(folder, (home / "modules").resolve(), "here"))
    assert not hasattr(app, "notify") and not hasattr(app, "_secret")
    with pytest.raises(AttributeError):
        app.notify("x")
    make_module(home / "modules", "通知", 'PROVIDES = {"app.notify": "notify"}\n\ndef notify(app, text):\n    pass\n')
    assert hasattr(app, "notify")


def test_app_call_each_and_providers(home, view):
    make_module(home / "modules", "A", GREET)
    folder = make_module(home / "modules", "Z")
    core = started(home, view)
    app = App(core, scan.module_info(folder, (home / "modules").resolve(), "here"))
    assert app.call("greet", "Z") == "A 跟 Z 打招呼" and [m.name for m in app.providers("greet")] == ["A"]
    assert [v for _, v in app.each("greet", "Z")] == ["A 跟 Z 打招呼"]


# ── 從工作坊裝來的：先問一次 ──

def foreign(home, name="外來", source=GREET):
    folder = make_module(home / "modules", name, source)
    (folder / ".origin").write_text("source: x\n", encoding="utf-8")
    (folder / ".unconfirmed").write_text("", encoding="utf-8")
    return folder


def test_a_workshop_module_is_asked_once_and_remembered(home, view):
    folder = foreign(home)
    core = started(home, view)
    assert [m.name for m in core.providers("greet")] == ["外來"]
    assert view.confirmed == [T["allow_roles"].format(title="外來", roles="greet")]
    assert json.loads((folder / ".roles-ok").read_text(encoding="utf-8")) == [["greet", "hello"]]
    assert not (folder / ".unconfirmed").exists()  # 允許它提供功能，就是允許它執行：不再問第二次
    assert core.call("greet", "你") == "外來 跟 你 打招呼" and len(view.confirmed) == 1
    assert Core(home, DEFAULT_CONFIG, view).providers("greet") and len(view.confirmed) == 1  # 重新啟動也不再問


def test_saying_no_keeps_it_out_and_is_not_asked_again_this_run(home, view):
    folder = foreign(home)
    view.answers = [False]
    core = started(home, view)
    assert core.providers("greet") == [] and core.call("greet", "你") is None
    assert len(view.confirmed) == 1 and not (folder / ".roles-ok").exists() and (folder / ".unconfirmed").exists()
    assert Core(home, DEFAULT_CONFIG, view).providers("greet") and len(view.confirmed) == 2  # 下次啟動會再問


def test_a_changed_declaration_is_asked_again(home, view):
    folder = foreign(home)
    core = started(home, view)
    core.providers("greet")
    (folder / "iplot.py").write_text('PROVIDES = {"greet": "hello", "app.trash": "hello"}\n' + GREET.split("\n", 1)[1],
                                     encoding="utf-8")
    view.answers = [False]
    assert core.providers("greet") == [] and len(view.confirmed) == 2
    assert "greet、app.trash" in view.confirmed[-1]


def test_own_and_bundled_modules_are_never_asked(home, view):
    make_module(home / "modules", "自己的", GREET)
    core = started(home, view)
    assert core.providers("greet") and view.confirmed == []


# ── 作業系統 ──

def test_os_actions_go_to_the_provider_of_os_name(home, view):
    make_module(home / "modules", "別的系統", 'PROVIDES = {"os.reveal": "reveal"}\n\ndef reveal(app, path):\n'
                '    return "顯示 " + path.name\n')
    core = started(home, view)
    assert core.action("reveal", home / "x.txt") == "顯示 x.txt"


def test_an_old_system_module_without_provides_still_works_by_name_for_now(home, view):
    """0.8 過渡：使用者改過的舊版「作業系統」沒有 PROVIDES，照舊用名字找到它（0.9 拿掉）。"""
    make_module(home / "modules", "作業系統", 'def reveal(app, path):\n    return "舊的 " + path.name\n')
    core = started(home, view)
    assert core.action("reveal", home / "x.txt") == "舊的 x.txt"


def test_the_bundled_system_module_declares_every_action_the_core_and_app_use():
    meta = read_meta(Path(__file__).resolve().parents[1] / "modules" / "作業系統" / "iplot.py")
    assert {r for r, _ in meta.provides} == {f"os.{n}" for n in ("open", "edit", "reveal", "terminal", "trash",
                                                                  "requirements", "webview_ready")}
    assert all(r == "os." + f for r, f in meta.provides)
