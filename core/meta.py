"""不執行地讀模組資訊：只用 ast 解析 iplot.py，不跑任何模組程式碼。"""

import ast
from itertools import takewhile
from pathlib import Path

from .text import T
from .types import Meta


def read_meta(file: Path) -> Meta:
    """解析 file，取 docstring 第一段、TITLE、ICON、有沒有 run 與 on_files；壞掉的檔案把錯誤放進 error。"""
    try:
        tree = ast.parse(file.read_text(encoding="utf-8-sig"), str(file))
    except SyntaxError as exc:
        if exc.lineno is None:
            return Meta(None, "", False, False, str(exc))
        return Meta(None, "", False, False, T["syntax_error"].format(line=exc.lineno, message=exc.msg))
    except (ValueError, OSError) as exc:  # 解碼失敗、3.10 的 NUL 位元組、讀不到
        return Meta(None, "", False, False, str(exc))
    consts, funcs = {}, set()  # 頂層的 TITLE = "…"、ICON = "…"：只認字串常數
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            funcs.add(node.name)
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ("TITLE", "ICON")
              and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            consts[node.targets[0].id] = node.value.value
    doc = ast.get_docstring(tree) or ""
    description = "\n".join(takewhile(str.strip, doc.splitlines()))
    return Meta(consts.get("TITLE"), description, "run" in funcs, "on_files" in funcs, None,
                consts.get("ICON"))
