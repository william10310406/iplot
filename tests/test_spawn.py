"""另開程序要確認起來了（D160 第 3 條）：行事曆、主控面板、互通的 nav.py 各有一份一樣的 _spawn（tools/copies.json 登記成 same）。
等 wait 秒：這段時間裡出錯結束了回 False；stderr 接到 logs/separate.log。"""
import importlib.util
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]




@pytest.fixture(params=["modules/行事曆/iplot.py", "modules/主控面板/iplot.py", "modules/互通/nav.py"])
def spawn(request, monkeypatch):
    monkeypatch.syspath_prepend(str((ROOT / request.param).parent))
    monkeypatch.syspath_prepend(str(ROOT))
    spec = importlib.util.spec_from_file_location("iplot_spawn_test", ROOT / request.param)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._spawn


def test_a_child_that_dies_at_once_is_a_failure_and_its_stderr_is_kept(spawn, tmp_path):
    argv = [sys.executable, "-c", "import sys; sys.stderr.write('壞了'); sys.exit(1)"]
    assert spawn(subprocess.Popen, argv, tmp_path, wait=10) is False
    assert "壞了" in (tmp_path / "logs" / "separate.log").read_text(encoding="utf-8")


def test_a_child_that_keeps_running_or_finishes_fine_is_up(spawn, tmp_path):
    assert spawn(subprocess.Popen, [sys.executable, "-c", "pass"], tmp_path, wait=10) is True
    proc = []

    def popen(argv, **kw):
        proc.append(types.SimpleNamespace(poll=lambda: None))
        return proc[0]

    assert spawn(popen, ["x"], tmp_path, wait=0.2) is True


def test_popen_failing_still_raises(spawn, tmp_path):
    def popen(argv, **kw):
        raise OSError(2, "no")

    with pytest.raises(OSError):
        spawn(popen, ["x"], tmp_path, wait=1)
