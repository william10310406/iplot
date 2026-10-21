"""tests/acceptance_workshop.py（自己跑的驗收腳本）裡不開視窗、不連網就測得到的事（第三輪審查）。"""

import hashlib
import importlib.util
import json
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def script():
    spec = importlib.util.spec_from_file_location("acceptance_script", ROOT / "tests" / "acceptance_workshop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_keep_refuses_a_folder_that_already_has_something_in_it(script, tmp_path, monkeypatch, capsys):
    """--keep 給了一個裡面有東西的資料夾（例如 ~/Desktop、或 . 也就是 iPLoT 資料夾自己）：一個檔都不能刪，說一句就停。"""
    victim = tmp_path / "桌面"
    victim.mkdir()
    (victim / "important.txt").write_text("不能刪", encoding="utf-8")
    monkeypatch.setattr(script, "check_site", lambda *a, **k: pytest.fail("不該走到檢查網路"))
    assert script.main(["--keep", str(victim)]) == 1
    assert (victim / "important.txt").read_text(encoding="utf-8") == "不能刪"
    assert sorted(p.name for p in victim.iterdir()) == ["important.txt"]
    said = capsys.readouterr().out.strip().splitlines()
    assert len(said) == 1 and "--keep" in said[0], said


def test_failures_with_a_plain_sentence_as_evidence_are_still_printed(script, tmp_path, monkeypatch, capsys):
    """驅動在失敗的路上記的證據是一句話（不是 dict）：照樣印出每一項，不是 traceback。複本與視窗都用替身。"""
    def copytree(src, home, **kwargs):
        (home / "core").mkdir(parents=True)
        (home / "core" / "__init__.py").write_text('__version__ = "0.5.0"\n', encoding="utf-8")
        (home / "modules" / script.NAME).mkdir(parents=True)

    def run_copy(acc, home, version, stubs):
        lines = [{"item": "開出來的是舊版", "ok": True, "evidence": {"標題": "iPLoT v0.4.9"}, "pid": 7},
                 {"item": "面板", "ok": False, "evidence": "面板沒有出現格子", "pid": 7}]
        (acc / "results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in lines), encoding="utf-8")
        (acc / "stage").write_text("done", encoding="utf-8")
        (acc / "main.err").write_text("", encoding="utf-8")
        return True

    monkeypatch.setattr(script, "check_site", lambda *a, **k: ({"version": "0.5.0"}, [], ""))
    monkeypatch.setattr(script.shutil, "copytree", copytree)
    monkeypatch.setattr(script, "run_copy", run_copy)
    assert script.main(["--keep", str(tmp_path / "複本")]) == 1
    out = capsys.readouterr().out
    assert "通過 開出來的是舊版" in out and "失敗 面板" in out and "面板沒有出現格子" in out, out
    assert "結果：2/3 通過" in out, out


ENTRY_NAME = "整理桌面"


def sites(tmp_path, *, modules=(), notice="沒有人審查"):
    """tmp 裡兩個資料夾：core/（update.json、iPLoT-v9.9.9.zip、index.html）、mods/（index.json、模組/整理桌面.zip）。
    回 (update_url, index_url, core)。"""
    core, mods = tmp_path / "core", tmp_path / "mods"
    (mods / "模組").mkdir(parents=True)
    core.mkdir()
    core_zip = core / "iPLoT-v9.9.9.zip"
    with zipfile.ZipFile(core_zip, "w") as z:
        z.writestr("iPLoT-v9.9.9/main.py", "print(1)\n")
    core_sha = hashlib.sha256(core_zip.read_bytes()).hexdigest()
    mod_zip = mods / "模組" / f"{ENTRY_NAME}.zip"
    with zipfile.ZipFile(mod_zip, "w") as z:
        z.writestr(f"{ENTRY_NAME}/iplot.py", "x = 1\n")
    entry = {"name": ENTRY_NAME, "version": "1.0", "zip_url": mod_zip.as_uri(),
             "sha256": hashlib.sha256(mod_zip.read_bytes()).hexdigest(), "description": "整理", "icon": "🗂",
             "notes": "第一版", "author": "someone"}
    (core / "update.json").write_text(json.dumps({"version": "9.9.9", "zip_url": core_zip.as_uri(), "sha256": core_sha,
                                                  "notes": "n"}, ensure_ascii=False), encoding="utf-8")
    (core / "index.html").write_text(f"<h1>iPLoT 工作坊</h1>{core_sha} 誰都能上傳", encoding="utf-8")
    (mods / "index.json").write_text(json.dumps({"notice": notice, "modules": list(modules) and [entry] or [],
                                                 "uploads": [entry]}, ensure_ascii=False), encoding="utf-8")
    return (core / "update.json").as_uri(), (mods / "index.json").as_uri(), core


def test_check_site_waits_only_for_update_json(script, tmp_path):
    update_url, index_url, core = sites(tmp_path)
    published = tmp_path / "published"
    published.mkdir()
    (published / "update.json").write_bytes((core / "update.json").read_bytes())
    (published / "index.json").write_text('{"modules": []}', encoding="utf-8")
    results = []
    update, entries, notice = script.check_site(update_url, index_url, published, results, wait=1)
    assert update["version"] == "9.9.9" and [e["name"] for e in entries] == [ENTRY_NAME] and notice == "沒有人審查"
    assert all(ok for _, ok, _ in results), results
    assert any("modules 是空的" in item and ok for item, ok, _ in results)


def test_check_site_says_so_when_modules_is_not_empty(script, tmp_path):
    update_url, index_url, _ = sites(tmp_path, modules=[1])
    results = []
    script.check_site(update_url, index_url, None, results, wait=1)
    bad = [item for item, ok, _ in results if not ok]
    assert len(bad) == 1 and "modules 是空的" in bad[0], results


def test_check_site_stops_quickly_when_update_json_differs(script, tmp_path):
    update_url, index_url, _ = sites(tmp_path)
    published = tmp_path / "published"
    published.mkdir()
    (published / "update.json").write_text('{"version": "0.0.1"}', encoding="utf-8")
    results = []
    start = time.monotonic()
    assert script.check_site(update_url, index_url, published, results, wait=0.5) == (None, None, "")
    assert time.monotonic() - start < 5
    assert len(results) == 1 and not results[0][1]
