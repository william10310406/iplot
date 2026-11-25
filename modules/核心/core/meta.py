"""不執行地讀模組資訊：只用 ast 解析 iplot.py，不跑任何模組程式碼。"""

import ast
from itertools import takewhile
from pathlib import Path

from .text import T
from .types import Meta


def read_meta(file: Path) -> Meta:
    """解析 file，取 docstring 第一段、TITLE、ICON、PROVIDES、ROLE_NAMES、MIN_API、有沒有 run 與 on_files；
    壞掉的檔案把錯誤放進 error。"""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8-sig"), str(file))
    except SyntaxError as exc:
        if exc.lineno is None:
            return Meta(None, "", False, False, T["file_unreadable"])
        return Meta(None, "", False, False, T["syntax_error"].format(line=exc.lineno, message=exc.msg))
    except (ValueError, OSError):  # 解碼失敗、3.10 的 NUL 位元組、讀不到
        return Meta(None, "", False, False, T["file_unreadable"])
    consts, funcs, pairs, min_api = {}, set(), {"PROVIDES": (), "ROLE_NAMES": ()}, 0  # 字串常數、字串對字串的字面值
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs.add(node.name)
        elif any(_assigns(node, n) for n in pairs) and isinstance(node.value, ast.Dict):  # D159、D166
            kv = list(zip(node.value.keys, node.value.values, strict=True))
            if all(_str(k) and _str(v) for k, v in kv):
                pairs[node.targets[0].id] = tuple((k.value, v.value) for k, v in kv)
        elif _assigns(node, "MIN_API") and isinstance(node.value, ast.Constant) and type(node.value.value) is int:
            min_api = node.value.value
        elif (_assigns(node, "TITLE") or _assigns(node, "ICON")) and _str(node.value):
            consts[node.targets[0].id] = node.value.value
    doc = ast.get_docstring(tree) or ""
    description = "\n".join(takewhile(str.strip, doc.splitlines()))
    return Meta(consts.get("TITLE"), description, "run" in funcs, "on_files" in funcs, None,
                consts.get("ICON"), pairs["PROVIDES"], min_api, pairs["ROLE_NAMES"])


def _assigns(node: ast.stmt, name: str) -> bool:
    return (isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name)


def _str(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)
