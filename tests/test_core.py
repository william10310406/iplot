import shutil
import unicodedata

import pytest
from conftest import make_module

from core import actions, history
from core.core import Core
from core.text import T
from core.types import DEFAULT_CONFIG


def started(home, view, **kw):
    c = Core(home, DEFAULT_CONFIG, view, **kw)
    c.rescan()
    return c


def find(c, name):
    return next(m for m in c.all_modules() if m.name == name)


def test_rescan_shows_two_groups(home, view):
    started(home, view)
    assert [g.level for g in view.shows[-1].groups] == ["here", "parent"]


def test_press_runs_and_logs_done(home, view):
    make_module(home / "modules", "A")
    c = started(home, view)
    assert c.press(find(c, "A")).ok
    assert "完成（" in view.logs[-1]


def test_press_logs_output(home, view):
    make_module(home / "modules", "A", "def run(app):\n    print('hi')\n")
    c = started(home, view)
    c.press(find(c, "A"))
    assert "hi" in view.logs


def test_press_error_reports(home, view):
    make_module(home / "modules", "A", "def run(app):\n    x = 1\n    1/0\n")
    c = started(home, view)
    c.press(find(c, "A"))
    assert view.reports[0].line == 3


def test_press_snapshots_before_run(home, view):
    src = "def run(app):\n    open(__file__, 'w').write('changed')\n"
    folder = make_module(home / "modules", "A", src)
    c = started(home, view)
    c.press(find(c, "A"))
    [snap] = (folder / ".history").glob("*.py")
    assert snap.read_text(encoding="utf-8") == src


def test_run_by_name_nfd(home, view):
    nfc = "開工ガイド"
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfd != nfc
    make_module(home / "modules", nfd)
    make_module(home / "modules", "B", f"def run(app):\n    app.run({nfc!r})\n    app.run({nfd!r})\n")
    c = started(home, view)
    assert c.press(find(c, "B")).ok
    assert view.logs.count("ok") == 2


def test_run_by_name_ambiguous_raises(home, view):
    here, parent = make_module(home / "modules", "A"), make_module(home.parent, "A")
    c = started(home, view)
    with pytest.raises(LookupError) as ei:
        c.run_by_name("A")
    assert str(here.resolve()) in str(ei.value) and str(parent.resolve()) in str(ei.value)


def test_rescan_deferred_while_busy(home, view):
    make_module(home / "modules", "A", "def run(app):\n    app.rescan()\n    app.log('after')\n")
    c = started(home, view)
    view.events.clear()
    c.press(find(c, "A"))
    kinds = [e[1] if e[0] == "log" else e[0] for e in view.events]
    assert kinds[0] == "after" and kinds.count("show") == 1 and kinds[-1] == "show"


def test_enter_and_back(home, view):
    make_module(make_module(home / "modules", "A"), "C")
    c = started(home, view)
    a = find(c, "A")
    c.enter(a)
    assert c.scope.crumbs == ("iPLoT", "A")
    [g] = c.scope.groups
    assert (g.level, g.label, g.root, [m.name for m in g.modules]) == ("here", "A", a.folder, ["C"])
    c.back(0)
    assert c.scope.crumbs == ("iPLoT",) and len(c.scope.groups) == 2


def test_create_opens_editor(home, view, monkeypatch):
    seen = []
    monkeypatch.setattr(actions, "edit", lambda *a: seen.append(a))
    c = started(home, view)
    folder = c.create(c.scope.groups[0].root, "新的")
    assert seen == [(folder / "iplot.py", None)]
    assert [m.name for m in c.scope.groups[0].modules] == ["新的"]


def test_create_bad_name_logs(home, view):
    c = started(home, view)
    assert c.create(home / "modules", "a/b") is None
    assert view.logs[-1] == T["bad_name"]


def test_report_internal_writes_log_and_view(home, view):
    c = started(home, view)
    with pytest.raises(RuntimeError) as ei:
        raise RuntimeError("壞了")
    c.report_internal(ei.type, ei.value, ei.tb)
    assert "RuntimeError: 壞了" in (home / "logs" / "iplot.log").read_text(encoding="utf-8")
    assert view.reports[-1].source == "core"


def test_safe_only_modules(home, view):
    c = started(home, view, safe=True)
    assert [g.level for g in c.scope.groups] == ["here"]


def test_entered_folder_deleted(home, view):
    make_module(make_module(home / "modules", "A"), "C")
    c = started(home, view)
    c.enter(find(c, "A"))
    shutil.rmtree(home / "modules" / "A")
    c.rescan()
    assert c.scope.crumbs == ("iPLoT",) and view.reports == []


def test_create_in_missing_root_logs(home, view):
    c = started(home, view)
    assert c.create(home / "nope", "A") is None
    assert view.logs[-1].startswith(f"無法在 {home / 'nope'} 建立模組")


def test_snapshot_failure_still_runs_and_rescans(home, view, monkeypatch):
    make_module(home / "modules", "A")
    c = started(home, view)

    def boom(*args):
        raise PermissionError("唯讀")

    monkeypatch.setattr(history, "snapshot", boom)
    assert c.press(find(c, "A")).ok
    assert any(line.startswith("無法存上一版") for line in view.logs)
    shown = len(view.shows)
    c.rescan()
    assert len(view.shows) == shown + 1


def test_press_logs_output_before_reporting_error(home, view):
    make_module(home / "modules", "A", "def run(app):\n    print('before')\n    1/0\n")
    c = started(home, view)
    view.events.clear()
    c.press(find(c, "A"))
    assert [e[0] for e in view.events] == ["log", "report"]
    assert view.logs == ["before"] and view.reports[0].line == 3


def test_run_by_name_not_found_raises(home, view):
    c = started(home, view)
    with pytest.raises(LookupError) as ei:
        c.run_by_name("nope")
    assert str(ei.value) == T["not_found"].format(name="nope")


def test_create_already_exists_logs(home, view):
    make_module(home / "modules", "A")
    c = started(home, view)
    assert c.create(home / "modules", "A") is None
    assert view.logs[-1] == T["already_exists"].format(name="A")
