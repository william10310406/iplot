"""行數預算（規格 §4.2、D48）：核心邏輯 ≤ 500 有效行、ui.py ≤ 150。

有效行 = 非空白、非純註解、非 docstring 所在的行。"""

import ast
import io
import tokenize
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "core"
SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
        tokenize.ENCODING, tokenize.ENDMARKER}


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


def counts() -> dict[str, int]:
    return {p.name: effective_lines(p) for p in sorted(CORE.glob("*.py"))}


def test_effective_lines_definition(tmp_path):
    f = tmp_path / "x.py"
    f.write_text('"""doc\n\nmore"""\n\n# comment\nx = 1  # trailing\ny = (\n    2,\n)\n', encoding="utf-8")
    assert effective_lines(f) == 4


def test_core_logic_within_500():
    logic = {k: v for k, v in counts().items() if k not in ("ui.py", "text.py")}
    total = sum(logic.values())
    assert total <= 500, f"核心邏輯 {total} 行 > 500：{logic}"


def test_ui_within_150():
    n = counts()["ui.py"]
    assert n <= 150, f"ui.py {n} 行 > 150"
