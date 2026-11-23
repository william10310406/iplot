"""行數預算（規格「全域限制」、D68）：核心邏輯 ≤ 699 有效行，而且只降不升（D159；2026-10-07 由 500 調到 505，D83；2026-11-14 體驗打磨 2-10 調到 510；2026-11-15 導覽列 516 → 530，D152；2026-11-16 面板上的改名與移到垃圾桶 → 595，D155；隨附模組跟著更新 → 700，D156；2026-11-23 依角色找模組 → 699，從此只降不升，D159）；UI 的各檔各有上限（`UI_BUDGETS`）。

有效行（Python）＝非空白、非純註解、非 docstring 所在的行。
有效行（HTML／CSS／JS）＝非空白、非整行註解（//、/* … */、<!-- … -->）的行。"""

import ast
import io
import re
import subprocess
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
        tokenize.ENCODING, tokenize.ENDMARKER}
# ui/web.py：2026-10-05 由 200 調到 220（M3 的 page 5 行，日後關閉前確認 8 行）；2026-11-07 由 220 調到 230
# （M9 自動問「要回報嗎？」，D150）；2026-11-15 由 230 調到 235（導覽列，D153）；2026-11-23 由 240 調到 242（右鍵選單改問提供 menu.module 的模組，拿掉改名、刪除兩個入口，D159）。ui/errlog.py 是 M9 新加的，兩個面板與 main.py 共用
UI_BUDGETS = {"ui/web.py": 242, "ui/tk.py": 180, "ui/install.py": 80, "ui/errlog.py": 80, "ui/nav.py": 60, "ui/menu.py": 20,
              "ui/index.html": 120, "ui/app.js": 400, "ui/style.css": 300}
BLOCKS = (("/*", "*/"), ("<!--", "-->"))


def effective_lines(path: Path) -> int:
    src = path.read_text(encoding="utf-8")
    doc = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                doc.update(range(first.lineno, first.end_lineno + 1))
    lines = set()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type not in SKIP:
            lines.update(range(tok.start[0], tok.end[0] + 1))
    return len(lines - doc)


def web_lines(path: Path) -> int:
    """HTML／CSS／JS 的有效行。註解後面同一行還有程式碼就算一行。"""
    count, closer = 0, None  # closer：還在多行註解裡的時候，等的是哪一種結尾
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if closer:
            if closer in line:
                line, closer = line.split(closer, 1)[1].strip(), None
                count += bool(line)
            continue
        if not line or line.startswith("//"):
            continue
        opener, end = next((b for b in BLOCKS if line.startswith(b[0])), (None, None))
        if opener is None:
            count += 1
        elif end not in line[len(opener):]:
            closer = end
        elif line.split(end, 1)[1].strip():
            count += 1
    return count


def core_logic() -> dict[str, int]:
    """核心邏輯：core/ 的每個 .py，扣掉只放文字的 text.py。"""
    return {p.name: effective_lines(p) for p in sorted(CORE.glob("*.py")) if p.name != "text.py"}


def test_effective_lines_definition(tmp_path):
    f = tmp_path / "x.py"
    f.write_text('"""doc\n\nmore"""\n\n# comment\nx = 1  # trailing\ny = (\n    2,\n)\n', encoding="utf-8")
    assert effective_lines(f) == 4


def test_web_lines_definition(tmp_path):
    f = tmp_path / "x.css"
    f.write_text("/* 一行註解 */\n\n* { margin: 0 }\n/* 多行\n * 第二行\n 沒有星號的第三行\n */\n"
                 "a { b: c }  /* 行尾註解 */\n/* 前面有註解 */ d { e: f }\n// js 的註解\n"
                 "<!-- html 註解 -->\n<!-- 多行\n結束 --> <p>\n", encoding="utf-8")
    assert web_lines(f) == 4  # * { }、a { }、d { }、<p>


CORE_LIMIT = 699  # 依角色找模組 700 → 699（D159，量到 699；之後只降不升，見 test_core_limit_never_goes_up）；隨附模組跟著更新 595 → 700（D156，量到 695）；面板上的改名與移到垃圾桶 530 → 595（D155，量到 591）；導覽列的基礎 516 → 530（D152）； 體驗打磨 2-10：505 → 510；審查 S4：510 → 516（清單檔「裁決紀錄」）


def test_core_logic_within_limit():
    logic = core_logic()
    total = sum(logic.values())
    assert total <= CORE_LIMIT, f"核心邏輯 {total} 行 > {CORE_LIMIT}：{logic}"


def _tagged_limit() -> tuple[str, int] | None:
    """最新一個 vX.Y.Z tag 的 CORE_LIMIT；不是 git 的工作目錄、沒有 tag（淺 clone）就回 None。"""
    run = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")  # noqa: E731
    tags = [t for t in run("tag", "--list", "v*").stdout.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    if not tags:
        return None
    last = max(tags, key=lambda t: tuple(map(int, t[1:].split("."))))
    found = re.search(r"^CORE_LIMIT = (\d+)", run("show", f"{last}:tests/test_budget.py").stdout, re.M)
    return (last, int(found.group(1))) if found else None


def test_core_limit_never_goes_up():
    """D159：上限只降不升。真的要升，同一個 PR 要先把某個功能從核心搬成模組，讓量到的行數先降下來。"""
    tagged = _tagged_limit()
    if tagged is None:
        pytest.skip("沒有 tag 可以比（淺 clone、或不是 git 的工作目錄）")
    assert tagged[1] >= CORE_LIMIT, f"CORE_LIMIT {CORE_LIMIT} 比 {tagged[0]} 的 {tagged[1]} 高：上限只降不升（D159）"


# 0.8 過渡：核心還認得的模組名字，只能出現在 core/text.py 的這三個常數裡（0.9 隨附同步搬進「更新」、作業系統只靠 PROVIDES、
# 回報改用角色之後拿掉）。其他地方——core/ 的其他檔——一個模組的名字都不能當成字串出現（D159）。
# 只比「整個字串就是名字」與「modules/名字」：訊息裡的一般用字（「重新啟動 iPLoT」、「從工作坊裝來的」）不是在找模組
TRANSITIONAL = {"BUNDLED", "SYSTEM_MODULE", "REPORT_MODULE"}


def test_core_names_no_module_except_the_transitional_constants():
    names = {p.name for p in (ROOT / "modules").iterdir() if p.is_dir()}
    found = []
    for path in sorted(CORE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        allowed = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr)}  # docstring 是說明，不算
        if path.name == "text.py":
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in TRANSITIONAL for t in node.targets):
                    allowed |= {id(n) for n in ast.walk(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in allowed:
                found += [f"{path.name}:{node.lineno} {n}" for n in names if node.value == n or f"modules/{n}" in node.value]
    assert found == []


def test_panel_is_not_in_core():
    """面板在 ui/：core/ 裡沒有 ui.py，核心邏輯才是「一個下午讀得完」的那一塊。"""
    assert not (CORE / "ui.py").exists() and (ROOT / "ui" / "tk.py").exists()


@pytest.mark.parametrize("name", UI_BUDGETS)
def test_ui_file_budgets(name):
    path = ROOT / name
    if not path.exists():
        pytest.skip(f"{name} 還沒有")
    n = effective_lines(path) if path.suffix == ".py" else web_lines(path)
    assert n <= UI_BUDGETS[name], f"{name} {n} 行 > {UI_BUDGETS[name]}"
