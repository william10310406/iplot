import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
CJK = re.compile(r"[一-鿿]")
FORBIDDEN = ("subprocess", "sys.platform", "os.name", "startfile", "ctypes")


def test_bottom_layer_never_imports_tkinter():
    code = ("import sys; sys.modules['tkinter']=None; import core.types, core.text, core.meta, "
            "core.scan, core.errors, core.runner, core.history, core.create, "
            "core.app, core.core")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_core_has_no_os_code():
    """碰作業系統的事放 modules/作業系統，核心連字都不能出現（含註解與 docstring）。"""
    for p in sorted(CORE.glob("*.py")):
        src = p.read_text(encoding="utf-8")
        for word in FORBIDDEN:
            # 若有誤判（例如某個識別字剛好含 os.name），改用 re 加字界，不要放寬清單
            assert word not in src, f"core/{p.name} 出現 {word}"


def test_actions_module_is_gone():
    assert not (CORE / "actions.py").exists()


def _string_constants(path):
    """path 裡不是 docstring 的字串常數。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docs.add(id(first.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs]


def test_no_chinese_string_constants_outside_text():
    """D32：畫面文字都在 core/text.py；core/ 其他檔、ui/*.py、main.py 的字串常數沒有中文（註解與 docstring 不算）。"""
    files = [p for p in CORE.glob("*.py") if p.name != "text.py"] + list((ROOT / "ui").glob("*.py"))
    for p in sorted(files + [ROOT / "main.py"]):
        found = [s for s in _string_constants(p) if CJK.search(s)]
        assert not found, f"{p.relative_to(ROOT)} 有中文字串常數：{found}"


def test_core_never_imports_webview():
    """只有 ui/web.py 可以用 lib/ 裡的 pywebview；core/ 一行都不能 import 它。"""
    for p in sorted(CORE.glob("*.py")):
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            assert not any(n.split(".")[0] in ("webview", "ui") for n in names), f"core/{p.name} import 了 {names}"
