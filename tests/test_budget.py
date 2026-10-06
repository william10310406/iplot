"""行數預算（規格「全域限制」、D68）：核心邏輯 ≤ 500 有效行；UI 的六個檔各有上限。

有效行（Python）＝非空白、非純註解、非 docstring 所在的行。
有效行（HTML／CSS／JS）＝非空白、非整行註解（//、/* … */、<!-- … -->）的行。"""

import ast
import io
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
        tokenize.ENCODING, tokenize.ENDMARKER}
# ui/web.py：2026-10-05 由 200 調到 220（M3 的 page 5 行，日後關閉前確認 8 行）
UI_BUDGETS = {"ui/web.py": 220, "ui/tk.py": 180, "ui/install.py": 80,
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


def test_core_logic_within_500():
    logic = core_logic()
    total = sum(logic.values())
    assert total <= 500, f"核心邏輯 {total} 行 > 500：{logic}"


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
