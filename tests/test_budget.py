"""行數預算（規格「全域限制」、D68）：核心邏輯與 main.py、ui/ 各檔的上限在 tools/limits.json，只降不升，破例在 tools/exceptions.json（D160；核心的歷史：2026-10-07 由 500 調到 505，D83；2026-11-14 體驗打磨 2-10 調到 510；2026-11-15 導覽列 516 → 530，D152；2026-11-16 面板上的改名與移到垃圾桶 → 595，D155；隨附模組跟著更新 → 700，D156；2026-11-23 依角色找模組 → 699，從此只降不升，D159）。

有效行（Python）＝非空白、非純註解、非 docstring 所在的行。
有效行（HTML／CSS／JS）＝非空白、非整行註解（//、/* … */、<!-- … -->）的行。"""

import ast
import io
import json
import re
import subprocess
import tokenize
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KERNEL = ROOT / "modules" / "核心"  # 1.0 起核心是一個模組（D167）
CORE = KERNEL / "core"
CORE_KEY = "modules/核心/core"  # limits.json 裡核心邏輯總和的那一項
SKIP = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
        tokenize.ENCODING, tokenize.ENDMARKER}
# 上限在 tools/limits.json，破例在 tools/exceptions.json（D160）：歷史記在 git 與 docs/03，不再記在這裡的註解
LIMITS = {k: v for k, v in json.loads((ROOT / "tools" / "limits.json").read_text(encoding="utf-8")).items() if k != "說明"}
EXCEPTIONS = json.loads((ROOT / "tools" / "exceptions.json").read_text(encoding="utf-8"))
UI_BUDGETS = {k: v for k, v in LIMITS.items() if k.startswith("modules/核心/ui/")}
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


CORE_LIMIT = LIMITS[CORE_KEY]


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split("."))


def current_version() -> tuple[int, ...]:
    found = re.search(r'__version__ = "([\d.]+)"', (CORE / "__init__.py").read_text(encoding="utf-8"))
    return _version(found.group(1))


def measured() -> dict[str, int]:
    """limits.json 每一項現在量到的行數；列了的檔不見了就是 None（測試會紅，不 skip）。"""
    out = {CORE_KEY: sum(core_logic().values())}
    for name in LIMITS:
        if name != CORE_KEY:
            path = ROOT / name
            out[name] = (None if not path.exists()
                         else effective_lines(path) if path.suffix == ".py" else web_lines(path))
    return out


def test_core_logic_within_limit():
    logic = core_logic()
    total = sum(logic.values())
    assert total <= CORE_LIMIT, f"核心邏輯 {total} 行 > {CORE_LIMIT}：{logic}"


@pytest.mark.parametrize("name", [k for k in LIMITS if k != CORE_KEY])
def test_file_within_limit(name):
    """列在 limits.json 的檔不見了也算紅：改名、搬家要一起改上限表，上限才不會靜靜失效。"""
    n = measured()[name]
    assert n is not None, f"{name} 不見了：搬家或改名要一起改 tools/limits.json"
    assert n <= LIMITS[name], f"{name} {n} 行 > {LIMITS[name]}（tools/limits.json）"


def test_limits_leave_no_slack():
    """量到的比上限低 20 行以上，就該把上限降下來（只提醒，不擋）。"""
    for name, n in measured().items():
        if n is not None and LIMITS[name] - n >= 20:
            warnings.warn(f"{name} 量到 {n}，上限 {LIMITS[name]}：可以把 tools/limits.json 降下來", stacklevel=1)


def _git(*args: str) -> str | None:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return done.stdout if done.returncode == 0 else None


def tagged_limits() -> tuple[str, dict[str, int]] | None:
    """最新一個 vX.Y.Z tag 的上限：有 tools/limits.json 就讀它；更早的版本從 tests/test_budget.py 的 CORE_LIMIT、UI_BUDGETS 讀。
    不是 git 的工作目錄、沒有 tag（淺 clone）就回 None。"""
    tags = [t for t in (_git("tag", "--list", "v*") or "").split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    if not tags:
        return None
    last = max(tags, key=lambda t: _version(t[1:]))
    if (data := _git("show", f"{last}:tools/limits.json")) is not None:
        return last, {k: v for k, v in json.loads(data).items() if k != "說明"}
    old = _git("show", f"{last}:tests/test_budget.py") or ""
    limits = {}
    if found := re.search(r"^CORE_LIMIT = (\d+)", old, re.M):
        limits["core"] = int(found.group(1))
    if found := re.search(r"^UI_BUDGETS = (\{.*?\})", old, re.M | re.S):
        limits.update(ast.literal_eval(found.group(1)))
    return last, limits


def test_limits_never_go_up():
    """D159、D160：上限只降不升。比最新的 tag 高，就要有一筆沒到期的例外，raises 寫著這個數字。"""
    tagged = tagged_limits()
    if tagged is None:
        pytest.skip("沒有 tag 可以比（淺 clone、或不是 git 的工作目錄）")
    tag, before = tagged
    raised = {}
    for e in EXCEPTIONS:
        for name, n in e.get("raises", {}).items():
            raised[name] = max(raised.get(name, 0), n)
    up = [f"{name}：{tag} 是 {before[name]}，現在 {n}" for name, n in LIMITS.items()
          if name in before and n > before[name] and raised.get(name, 0) < n]
    assert up == [], "上限只降不升；真的要升，在 tools/exceptions.json 加一筆例外（D 編號、為什麼、要換成什麼、remove_by、raises）：" + "；".join(up)


def test_exceptions_are_complete_and_not_expired():
    """每一筆例外都寫齊；版本號到了 remove_by 還沒回收就紅：要嘛回收，要嘛改 remove_by 明著延期（D160）。"""
    now = current_version()
    for e in EXCEPTIONS:
        assert all(e.get(k) for k in ("id", "where", "why", "replace_with", "remove_by")), e
        assert set(e.get("raises", {})) <= set(LIMITS), e
        if e["remove_by"] != "不回收":
            assert now < _version(e["remove_by"]), f"例外 {e['id']} 說 {e['remove_by']} 前回收，現在是 {'.'.join(map(str, now))}"


# 核心的任何一個檔都不能把模組的名字當成字串（D159）。0.8 的三個過渡常數都拿掉了：SYSTEM_MODULE（D164）、
# REPORT_MODULE（D162）、BUNDLED（D169，隨附的名單改從雜湊表的鍵讀）。
# 只比「整個字串就是名字」與「modules/名字」：訊息裡的一般用字（「重新啟動 iPLoT」、「從工作坊裝來的」）不是在找模組
TRANSITIONAL: set[str] = set()


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
    """面板在 ui/：core/ 裡沒有 ui.py，核心邏輯才是「一個下午讀得完」的那一塊。iPLoT 資料夾裡沒有 core/、ui/（D167：只有發佈的包帶種子）。"""
    assert not (CORE / "ui.py").exists() and (KERNEL / "ui" / "tk.py").exists()
    assert not (ROOT / "core").exists() and not (ROOT / "ui").exists()
