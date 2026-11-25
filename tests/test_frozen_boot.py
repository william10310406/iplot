"""開機程式 main.py（D167）：1.0 起凍結，依序試 modules/核心/、它的 .local/核心.good/、iPLoT 資料夾本身的種子。
核心的 ui/start.py 的 remember 把開得起來的那一份記成 .good。"""

import hashlib
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
KERNEL = ROOT / "modules" / "核心"


def fake_kernel(folder, *, good=True, says=None):
    """假的核心：ui/start.py 的 ready() 好或壞，run() 印出自己是哪一份。"""
    (folder / "ui").mkdir(parents=True, exist_ok=True)
    ready = "pass" if good else "raise SyntaxError('壞了')"
    (folder / "ui" / "start.py").write_text(
        f"def ready():\n    {ready}\n\n\ndef run(home, kernel):\n    print('用了', {says or folder.name!r}, kernel == {str(folder)!r})\n",
        encoding="utf-8")
    return folder


@pytest.fixture
def tmp_path(tmp_path):
    """假的 iPLoT 資料夾放深一層：模組檔頭的那一小段往上找 iPLoT 時，不會在 pytest 的暫存區撿到這裡的 main.py 與 core/。"""
    home = tmp_path / "iPLoT"
    home.mkdir()
    return home


def boot(home):
    shutil.copy2(ROOT / "main.py", home / "main.py")
    return subprocess.run([sys.executable, str(home / "main.py")], cwd=home, capture_output=True, text=True,
                          encoding="utf-8", timeout=60)


def test_the_boot_program_is_frozen():
    digest = hashlib.sha256((ROOT / "main.py").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    lock = (ROOT / "tools" / "frozen_boot.sha256").read_text(encoding="utf-8").split()[0]
    assert digest == lock, ("main.py 是凍結的開機程式（D167）：每個人的 iPLoT 資料夾裡都有一份，「更新」不換它。"
                            "要改的是 modules/核心/ui/start.py。真的非改不可：寫一筆設計決定，再更新 tools/frozen_boot.sha256")


def test_the_primary_kernel_is_used_first(tmp_path):
    fake_kernel(tmp_path / "modules" / "核心", says="平常")
    fake_kernel(tmp_path / "modules" / "核心" / ".local" / "核心.good", says="備份")
    fake_kernel(tmp_path, says="種子")
    out = boot(tmp_path)
    assert out.returncode == 0 and out.stdout.split() == ["用了", "平常", "True"]


def test_a_broken_kernel_falls_back_to_the_last_good_one_and_says_why_in_the_log(tmp_path):
    fake_kernel(tmp_path / "modules" / "核心", good=False)
    fake_kernel(tmp_path / "modules" / "核心" / ".local" / "核心.good", says="備份")
    out = boot(tmp_path)
    assert out.stdout.split() == ["用了", "備份", "True"]
    assert "SyntaxError: 壞了" in (tmp_path / "logs" / "iplot.log").read_text(encoding="utf-8")


def test_both_broken_falls_back_to_the_seed(tmp_path):
    """0.8 的「更新」換的是 iPLoT 資料夾的 core/、ui/、main.py：第一次啟動時 modules/核心/ 還沒有，用種子開。"""
    fake_kernel(tmp_path / "modules" / "核心" / ".local" / "核心.good", good=False)
    fake_kernel(tmp_path, says="種子")
    assert boot(tmp_path).stdout.split() == ["用了", "種子", "True"]


def test_nothing_usable_says_one_sentence_and_exits_1(tmp_path):
    (tmp_path / "modules").mkdir()
    out = boot(tmp_path)
    assert out.returncode == 1 and "找不到能用的核心" in out.stdout and "Traceback" not in out.stdout + out.stderr


def test_a_failed_kernel_leaves_nothing_behind_for_the_next(tmp_path):
    """壞的那一份 import 了一半的 core 不能讓下一份撿到。"""
    bad = tmp_path / "modules" / "核心"
    (bad / "core").mkdir(parents=True)
    (bad / "ui").mkdir()
    (bad / "core" / "__init__.py").write_text("WHO = '壞的'\n", encoding="utf-8")
    (bad / "ui" / "start.py").write_text("import core\n\ndef ready():\n    raise ImportError('少了')\n", encoding="utf-8")
    seed = fake_kernel(tmp_path, says="種子")
    (seed / "core").mkdir()
    (seed / "core" / "__init__.py").write_text("WHO = '種子的'\n", encoding="utf-8")
    (seed / "ui" / "start.py").write_text("import core\n\ndef ready():\n    pass\n\ndef run(home, kernel):\n    print(core.WHO)\n",
                                         encoding="utf-8")
    assert boot(tmp_path).stdout.strip() == "種子的"


def test_the_real_kernel_is_ready():
    """這個 repo 的 modules/核心/ 本身過得了開機程式的 ready()。"""
    out = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from ui import start; "
                          "start.ready(); print('ok')", str(KERNEL)], capture_output=True, text=True, timeout=60)
    assert out.stdout.strip() == "ok", out.stderr


@pytest.fixture
def start():
    spec = importlib.util.spec_from_file_location("iplot_start_for_remember", KERNEL / "ui" / "start.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_remember_keeps_a_copy_of_the_kernel_that_started(tmp_path, start):
    kernel = tmp_path / "modules" / "核心"
    (kernel / "core").mkdir(parents=True)
    (kernel / "ui").mkdir()
    (kernel / "core" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (kernel / "core" / "t.json").write_text("{}\n", encoding="utf-8")
    (kernel / "ui" / "start.py").write_text("\n", encoding="utf-8")
    start.remember(tmp_path, kernel)
    good = kernel / ".local" / "核心.good"
    assert (good / "core" / "a.py").read_text(encoding="utf-8") == "x = 1\n" and (good / "core" / "t.json").exists()
    assert (good / "ui" / "start.py").exists() and not (kernel / ".local" / "核心.good.tmp").exists()
    stamp = (good / ".digest").stat().st_mtime_ns
    start.remember(tmp_path, kernel)  # 沒改：不重寫
    assert (good / ".digest").stat().st_mtime_ns == stamp
    (kernel / "core" / "a.py").write_text("x = 2\n", encoding="utf-8")
    start.remember(tmp_path, kernel)
    assert (good / "core" / "a.py").read_text(encoding="utf-8") == "x = 2\n"


def test_remember_does_nothing_for_the_backup_or_the_seed(tmp_path, start):
    good = tmp_path / "modules" / "核心" / ".local" / "核心.good"
    (good / "ui").mkdir(parents=True)
    (good / "ui" / "start.py").write_text("\n", encoding="utf-8")
    start.remember(tmp_path, good)
    start.remember(tmp_path, tmp_path)
    assert not (good / ".local").exists() and not (tmp_path / ".local").exists()
