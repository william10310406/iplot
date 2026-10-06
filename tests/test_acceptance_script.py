"""tests/acceptance_workshop.py（自己跑的驗收腳本）裡不開視窗、不連網就測得到的事（Task 17 審查）。"""

import importlib.util
import json
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

    monkeypatch.setattr(script, "check_site", lambda *a, **k: ({"version": "0.5.0"}, []))
    monkeypatch.setattr(script.shutil, "copytree", copytree)
    monkeypatch.setattr(script, "run_copy", run_copy)
    assert script.main(["--keep", str(tmp_path / "複本")]) == 1
    out = capsys.readouterr().out
    assert "通過 開出來的是舊版" in out and "失敗 面板" in out and "面板沒有出現格子" in out, out
    assert "結果：2/3 通過" in out, out
