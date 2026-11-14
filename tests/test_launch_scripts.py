"""iPLoT.command／iPLoT.sh：雙擊啟動的那一個檔。用假的 PATH，不真的啟動 iPLoT、不開視窗。"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ["iPLoT.command", "iPLoT.sh"]
pytestmark = pytest.mark.skipif(not Path("/bin/bash").exists(), reason="要有 /bin/bash")


def run(script, tmp_path, path_dirs, *args):
    """把啟動檔複製到有空白與中文的資料夾，用 /bin/bash 跑，PATH 只有 path_dirs。"""
    home = tmp_path / "我的 iPLoT"
    home.mkdir()
    target = home / script
    shutil.copy(ROOT / script, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR)
    env = {"PATH": os.pathsep.join(map(str, path_dirs))}
    return subprocess.run(["/bin/bash", str(target), *args], cwd=tmp_path, env=env, capture_output=True, text=True,
                          timeout=20)


def fake_bin(tmp_path, with_python):
    """一個只有 dirname（和假的 python3）的 PATH。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "dirname").symlink_to(shutil.which("dirname"))
    if with_python:
        py = bin_dir / "python3"
        py.write_text('#!/bin/bash\necho "cwd=$(pwd) args=$*"\n', encoding="utf-8")
        py.chmod(0o755)
    return bin_dir


@pytest.mark.parametrize("script", SCRIPTS)
def test_missing_python_is_a_sentence_not_command_not_found(script, tmp_path):
    """體驗 1-01：電腦上沒有 python3，說的是怎麼辦，不是英文的 command not found。"""
    result = run(script, tmp_path, [fake_bin(tmp_path, with_python=False)])
    out = result.stdout + result.stderr
    assert result.returncode == 1, "非 0：終端機視窗會留著，使用者讀得到這句話"
    assert "找不到 Python" in out and "python.org" in out and "3.10" in out
    assert "not found" not in out


@pytest.mark.parametrize("script", SCRIPTS)
def test_with_python_it_still_starts_main_py_in_its_own_folder_with_the_arguments(script, tmp_path):
    result = run(script, tmp_path, [fake_bin(tmp_path, with_python=True)], "--safe")
    assert result.returncode == 0
    assert "cwd=" in result.stdout and "我的 iPLoT" in result.stdout, "在 iPLoT 自己的資料夾裡跑（路徑有空白與中文也行）"
    assert "args=main.py --safe" in result.stdout


def test_both_scripts_are_the_same_and_executable():
    assert (ROOT / "iPLoT.command").read_bytes() == (ROOT / "iPLoT.sh").read_bytes()
    for script in SCRIPTS:
        mode = subprocess.run(["git", "ls-files", "-s", script], cwd=ROOT, capture_output=True, text=True).stdout
        assert mode.startswith("100755"), f"{script} 要有執行權限，雙擊才打得開"
