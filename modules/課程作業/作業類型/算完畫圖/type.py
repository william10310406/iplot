"""作業類型「算完畫圖」：一個 <代號>.py，CASES 裡每個 case 算一次、印數字、畫一張圖（docs/09 規範 v2）。
框架用 course.load_type 載入這個檔、照設計第 2.2 節的介面叫這幾個函式。只 import 標準庫；
判斷一律用 ast，從不執行作業檔。"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

NAME = "算完畫圖"
ACCEPTS = (".py",)  # 收作業時哪些副檔名算作業檔
SHELL = "coursework"  # 殼：跟作業檔放在一起，不是 pip 套件


def _tree(file: Path) -> ast.Module | None:
    """讀懂就回 ast；不是 UTF-8、語法錯、含 NUL 都回 None。"""
    try:
        return ast.parse(Path(file).read_text(encoding="utf-8-sig"), str(file))
    except (SyntaxError, ValueError):
        return None


def _assigned(tree: ast.Module, name: str) -> ast.expr | None:
    """頂層 name = … 最後一次的值。"""
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            found = node.value
    return found


def _top_imports(tree: ast.Module) -> set[str]:
    return {a.name for node in tree.body if isinstance(node, ast.Import) for a in node.names}


def classify(file: Path) -> tuple[str, str | None]:
    """("mine", None)：頂層有 HOMEWORK = dict(…) 與 import coursework；("broken", None)：語法錯；
    ("not-utf8", None)：不是 UTF-8；("none", None)：其他，包括 import hk_page 的規範 v0 檔（不收）。"""
    try:
        text = Path(file).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return ("not-utf8", None)
    try:
        tree = ast.parse(text, str(file))
    except (SyntaxError, ValueError):
        return ("broken", None)
    imports = _top_imports(tree)
    homework = _assigned(tree, "HOMEWORK")
    is_dict = isinstance(homework, ast.Call) and isinstance(homework.func, ast.Name) and homework.func.id == "dict"
    if "hk_page" in imports or not (is_dict and SHELL in imports):
        return ("none", None)
    return ("mine", None)


def _label(value: ast.expr) -> str:
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "dict":
        node = next((k.value for k in value.keywords if k.arg == "label"), None)
    elif isinstance(value, ast.Dict):
        node = next((v for k, v in zip(value.keys, value.values, strict=True)
                     if isinstance(k, ast.Constant) and k.value == "label"), None)
    else:
        node = None
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def cases(file: Path) -> list[tuple[str, str]] | None:
    """頂層 CASES = {…} 的（名字, label），照檔裡的順序；label 不是字串常數或沒寫就是 ""。
    CASES 不是 dict 字面值、有一個鍵不是字串常數、檔讀不懂 → None。不執行。"""
    tree = _tree(file)
    value = _assigned(tree, "CASES") if tree else None
    if not isinstance(value, ast.Dict):
        return None
    if not all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in value.keys):
        return None  # 鍵是變數、數字，或 **展開（鍵是 None）
    return [(k.value, _label(v)) for k, v in zip(value.keys, value.values, strict=True)]  # type: ignore[union-attr]


def requires(file: Path) -> set[str]:
    """這份作業要的 pip 名：頂層 REQUIRES = [...] 的字面值（ast 讀，D137）裡的非空字串。
    import 了、REQUIRES 沒寫的不算在這裡：那是 --check 的 R12（只警告、打包時擋）。
    沒有 REQUIRES、不是字串 list 的字面值、檔讀不懂 → 空集合。"""
    tree = _tree(file)
    line = _assigned(tree, "REQUIRES") if tree else None
    try:
        written = ast.literal_eval(line) if line is not None else []
    except ValueError:
        return set()
    return {r for r in written if isinstance(r, str) and r} if isinstance(written, list) else set()


def _shell():
    """從檔案載入旁邊的 coursework.py（換個名字，不動 sys.modules 裡的 coursework：那可能是別人的）。
    dataclass 要在 sys.modules 找得到自己的模組，所以載入期間放著、載完拿掉。"""
    name = "_coursework_for_check"
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / f"{SHELL}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def check(file: Path) -> list:
    """docs/09 第 3 節的規則（R1–R28）：coursework.check 的 Problem(rule, line, text) 清單；空的就是通過。
    作業那一格只警告、檢查與打包時擋（D131），由框架決定。不執行作業檔。"""
    return _shell().check(Path(file))


def argv(file: Path, python: Path, case: str | None):
    raise NotImplementedError("Task 12：在 iPLoT 裡另開程序跑")


def new(folder: Path, code: str) -> Path:
    raise NotImplementedError("Task 11：新增作業")


def pack(folder: Path, code: str):
    raise NotImplementedError("Task 13：檢查與打包")
