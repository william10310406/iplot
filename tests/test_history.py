from datetime import datetime

from core import history


def write(tmp_path, text):
    f = tmp_path / "iplot.py"
    f.write_text(text, encoding="utf-8")
    return f


def contents(f):
    return [p.read_text(encoding="utf-8") for p in history.versions(f)]


def test_first_snapshot_creates_history_dir(tmp_path):
    p = history.snapshot(write(tmp_path, "v1"), 20)
    assert p.parent == tmp_path / ".history" and p.read_text(encoding="utf-8") == "v1"


def test_identical_content_not_stored(tmp_path):
    f = write(tmp_path, "v1")
    history.snapshot(f, 20)
    assert history.snapshot(f, 20) is None
    assert len(history.versions(f)) == 1


def test_keep_limit(tmp_path):
    for v in ["v1", "v2", "v3"]:
        f = write(tmp_path, v)
        history.snapshot(f, 2)
    assert contents(f) == ["v3", "v2"]


def test_versions_newest_first(tmp_path):
    for v in ["old", "new"]:
        f = write(tmp_path, v)
        history.snapshot(f, 20)
    assert contents(f) == ["new", "old"]


def test_restore_snapshots_current_first(tmp_path):
    f = write(tmp_path, "old")
    old = history.snapshot(f, 20)
    f.write_text("current", encoding="utf-8")
    history.restore(f, old, 20)
    assert f.read_text(encoding="utf-8") == "old"
    assert contents(f) == ["current", "old"]


def test_same_second_suffix(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "_now", lambda: datetime(2026, 10, 2, 14, 9, 5))
    history.snapshot(write(tmp_path, "a"), 20)
    assert history.snapshot(write(tmp_path, "b"), 20).name == "2026-10-02_140905_1.py"


def test_restore_oldest_when_full(tmp_path):
    for v in ["v1", "v2"]:
        f = write(tmp_path, v)
        history.snapshot(f, 2)
    f.write_text("edited", encoding="utf-8")
    history.restore(f, history.versions(f)[-1], 2)
    assert f.read_text(encoding="utf-8") == "v1"
    assert contents(f) == ["edited", "v2"]


def test_foreign_files_in_history_are_ignored(tmp_path):
    hist = tmp_path / ".history"
    hist.mkdir()
    for n in range(5):
        (hist / f"notes_{n}.py").write_text("foreign", encoding="utf-8")
    f = write(tmp_path, "mine")
    snap = history.snapshot(f, 3)
    assert snap.exists() and history.versions(f) == [snap]
    assert sorted(p.name for p in hist.glob("notes_*.py")) == [f"notes_{n}.py" for n in range(5)]
    assert history.snapshot(write(tmp_path, "foreign"), 3) is not None  # 去重只跟自己的快照比
