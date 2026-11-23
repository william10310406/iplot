"""抄本的檢查（D160 第 2 條）：函式本體（扣掉 docstring）逐字一樣、至少 3 行的，就是抄本。只讀 git 認得的 .py（追蹤的與還沒追蹤、也沒被忽略的），不執行。

    python3 tools/check_copies.py            # 列出抄本，標出沒登記的
    python3 tools/check_copies.py --write    # 把現在的抄本整份寫進 tools/copies.json（第一次上線、或確定要接受時用）

tools/copies.json 每一筆是一組抄本：places（「檔案:函式名」）、same（true：要一直保持一樣，改一份就要改全部；
false：已經分家或允許分家，只是登記著）、why。tests/test_copies.py 擋三件事：沒登記的新抄本、same 的那一組不一樣了、
登記了但已經不是抄本的舊項目。"""

import ast
import collections
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPIES = ROOT / "tools" / "copies.json"
SKIP = ("tests/", "docs/", "lib/")


def tracked() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.py"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
    return [ROOT / p for p in out.split("\0") if p and not p.startswith(SKIP)]


def bodies() -> dict[str, str]:
    """「檔案:函式名」→ 本體的雜湊（同一個檔裡同名的函式取最後一個）。"""
    found = {}
    for path in tracked():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                body = [b for b in node.body if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
                src = ast.unparse(ast.Module(body=body, type_ignores=[]))
                if src.count("\n") >= 2:
                    found[f"{path.relative_to(ROOT).as_posix()}:{node.name}"] = hashlib.sha256(src.encode()).hexdigest()
    return found


def groups(found: dict[str, str]) -> list[list[str]]:
    by = collections.defaultdict(list)
    for place, digest in found.items():
        by[digest].append(place)
    return sorted(sorted(g) for g in by.values() if len(g) > 1)


def registered() -> list[dict]:
    return json.loads(COPIES.read_text(encoding="utf-8")) if COPIES.is_file() else []


def problems() -> list[str]:
    found, entries = bodies(), registered()
    out = []
    for group in groups(found):
        if not any(set(group) <= set(e["places"]) for e in entries):
            out.append("沒登記的抄本：" + " ＝ ".join(group))
    for e in entries:
        here = [p for p in e["places"] if p in found]
        if len(here) < len(e["places"]):
            out.append("登記的抄本不見了（搬家或刪了，改 tools/copies.json）：" + "、".join(set(e["places"]) - set(here)))
        elif e["same"] and len({found[p] for p in here}) > 1:
            out.append("說好要一樣的抄本不一樣了（改一份就要改全部）：" + " ＝ ".join(e["places"]))
        elif not e["same"] and len({found[p] for p in here}) == len(here):
            out.append("已經沒有兩份一樣的了，從 tools/copies.json 刪掉：" + "、".join(e["places"]))
    return out


def main() -> int:
    if "--write" in sys.argv[1:]:
        old = {tuple(sorted(e["places"])): e for e in registered()}
        rows = [old.get(tuple(g), {"places": g, "same": False, "why": "待補"}) for g in groups(bodies())]
        COPIES.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"寫了 {COPIES}（{len(rows)} 組）")
        return 0
    found = problems()
    print("\n".join(found) or "抄本都登記了")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
