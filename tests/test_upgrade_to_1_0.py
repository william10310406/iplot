"""0.8 → 1.0（D167）：0.8 的「更新」只換最上層的 core、ui、main.py、requirements。1.0 的包在最上層帶著種子，
所以換完第一次啟動由開機程式用種子開，新的核心照包把「核心」裝進 modules/；第二次啟動就用 modules/核心/，並記下 .good。

舊的那一份 iPLoT 從 git 拿：有 v0.8.0 的 tag 就用它，沒有（雲端的 clone）就用核心搬家之前的最後一個 commit。"""

import importlib.util
import shutil
import subprocess
import sys
import tarfile
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(*args, **kw):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True, **kw).stdout


def old_ref():
    """0.8 的那一份：v0.8.0，或最上層還有 core/ 的最後一個 commit。"""
    if subprocess.run(["git", "rev-parse", "-q", "--verify", "v0.8.0^{commit}"], cwd=ROOT, capture_output=True).returncode == 0:
        return "v0.8.0"
    gone = git("rev-list", "-1", "HEAD", "--", "core/__init__.py", text=True).strip()
    if not gone:
        pytest.skip("git 歷史裡沒有核心搬家之前的版本（淺 clone）")
    return f"{gone}^"


def old_install(home, ref):
    """ref 那一版的 iPLoT（git archive，跟發出去的包一樣），解到 home。"""
    with tarfile.open(fileobj=BytesIO(git("archive", ref, "core", "ui", "main.py", "requirements", "modules/更新"))) as tar:
        tar.extractall(home, filter="data")
    (home / "config.py").write_text("", encoding="utf-8")


def new_package(path, version):
    """這棵樹的 1.0 包：最上層 iPLoT-v<版本>/，modules/ 裡的核心，加上 tools/publish.py 放的種子。"""
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import publish
    finally:
        sys.path.remove(str(ROOT / "tools"))
    path.parent.mkdir(parents=True, exist_ok=True)
    top = f"iPLoT-v{version}/"
    listed = git("ls-files", "-z", "main.py", "requirements", "modules/核心", text=True, encoding="utf-8").split("\0")
    with zipfile.ZipFile(path, "w") as z:
        for name in filter(None, listed):
            z.write(ROOT / name, top + name)
    assert publish.add_seeds(path, top) == ["core", "ui"]
    return path


def boot(home, *args):
    return subprocess.run([sys.executable, "main.py", *args], cwd=home, capture_output=True, text=True,
                          encoding="utf-8", timeout=120)


def test_an_0_8_install_updated_with_its_own_updater_starts_and_moves_into_modules(tmp_path):
    from core import __version__

    home = tmp_path / "iPLoT"
    old_install(home, old_ref())
    spec = importlib.util.spec_from_file_location("old_update", home / "modules" / "更新" / "update.py")
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    package = new_package(home / ".backup" / f"download-{__version__}.zip", __version__)
    old.apply(home, package)  # 0.8 的「更新」：只換四樣
    assert (home / "core").is_dir() and not (home / "modules" / "核心").exists()
    shutil.copytree(ROOT / "modules" / "更新", home / "modules" / "甲")  # 隨便一個能在面板外跑的模組
    (home / "modules" / "甲" / "iplot.py").write_text("def run(app):\n    print('甲跑了', app.version)\n", encoding="utf-8")

    first = boot(home, "--run", "甲")
    assert f"甲跑了 {__version__}" in first.stdout, first.stdout + first.stderr
    kernel = home / "modules" / "核心"
    assert (kernel / "ui" / "start.py").is_file(), "第一次啟動（種子開的）把「核心」裝進 modules/"
    assert not (kernel / ".local").exists(), "用種子開的那一次不記 .good"

    second = boot(home, "--run", "甲")
    assert f"甲跑了 {__version__}" in second.stdout, second.stdout + second.stderr
    assert (kernel / ".local" / "核心.good" / "ui" / "start.py").is_file(), "第二次從 modules/核心/ 開，記下這一份"
