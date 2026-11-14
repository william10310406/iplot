"""模組頁面（page.html）裡的 JavaScript 沒有別的地方會執行：機器上有 node 時，把 script 區塊抽出來跑 node --check，
抓得到語法錯誤（重複宣告、少一個括號、引號沒跳脫）。沒有 node 就略過。新增的 page.html 會自動被涵蓋（審查 S2）。"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
SCRIPT = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.S)


def tracked_pages() -> list[Path]:
    """git 追蹤中的 modules/**/page.html（別人放進來、沒有被追蹤的模組不算）；不在 git 裡就掃資料夾。"""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--", "modules"], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return sorted((ROOT / "modules").glob("**/page.html"))
    names = out.decode("utf-8").split("\0")
    return [ROOT / n for n in names if n.endswith("/page.html") and (ROOT / n).is_file()]


def code(html: str) -> str:
    """要執行的 script：type 是 application/json 之類的資料區塊不算。"""
    return "\n".join(m["body"] for m in SCRIPT.finditer(html) if "json" not in m["attrs"] and m["body"].strip())


def check(js: str, tmp_path: Path) -> subprocess.CompletedProcess:
    file = tmp_path / "page.js"
    file.write_text(js, encoding="utf-8")
    return subprocess.run([NODE, "--check", str(file)], capture_output=True, text=True)


def test_the_pages_are_found():
    names = {p.parent.name for p in tracked_pages()}
    assert {"互通", "回報與討論", "工作坊", "行事曆"} <= names


@pytest.mark.skipif(NODE is None, reason="這台機器沒有 node")
@pytest.mark.parametrize("page", tracked_pages(), ids=lambda p: p.parent.name)
def test_every_module_page_script_has_valid_syntax(page, tmp_path):
    result = check(code(page.read_text(encoding="utf-8")), tmp_path)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(NODE is None, reason="這台機器沒有 node")
def test_the_check_catches_a_broken_script(tmp_path):
    ok = "<script>function ask(a) { return a; }</script>"
    assert check(code(ok), tmp_path).returncode == 0
    assert check(code(ok.replace("</script>", "\nconst ask = 1; function ask() {}</script>")), tmp_path).returncode != 0
    assert check(code("<script>let a = ;</script>"), tmp_path).returncode != 0
