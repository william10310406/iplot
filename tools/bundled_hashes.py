"""產生 modules/核心/core/bundled_hashes.json：隨附模組的每個檔，每一版發出去過的 sha256（D156）。

    python3 tools/bundled_hashes.py            # 所有 v0.5.0 以後的 tag ＋ 現在的暫存區
    python3 tools/bundled_hashes.py --check    # 不寫檔，只看 modules/核心/core/bundled_hashes.json 有沒有涵蓋現在的檔

「更新」之後的第一次啟動，core/bundled.py 拿安裝的檔的 sha256 跟這份表比：在表裡就是某一版發出去的原樣（沒改過，可以換成新版），
不在表裡就是使用者改過的（不換）。隨附模組改了、發新版之前要重新產生；tests/test_bundled_update.py 會擋住忘記的人。
每個 tag 用 git archive 取（跟核心的包一樣尊重 .gitattributes 的 export-ignore），所以只在有 tag 的完整 clone 裡才收得齊舊版。"""

import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "modules" / "核心" / "core"  # 1.0 起核心是隨附模組「核心」（D167）
OUT = CORE / "bundled_hashes.json"
# 這張表自己不進表（它每一版都變、表裡放不進自己的雜湊）：core/bundled.py 一律照包裡的換
SKIP = {"__pycache__", ".DS_Store", OUT.name}
# 拿掉的隨附模組：{名稱: 哪一版拿掉}。表裡的 ".retired" 留著它每一版發出去過的雜湊，新的核心第一次啟動時，
# 本機那一份沒改過才移到 .backup/（D171）；改過的、工作坊裝來的不碰。
RETIRED = {"打開核心原始碼": "1.0.0"}


def bundled_names() -> list[str]:
    """隨附的模組＝核心的包帶的：git 追蹤的 modules/ 底下、沒有標 export-ignore 的資料夾（D169：名單不寫在核心裡，
    核心從這張表的鍵知道有哪些）。"""
    listed = subprocess.run(["git", "ls-files", "-z", "modules"], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", check=True).stdout.split("\0")
    tops = sorted({path.split("/")[1] for path in listed if path.count("/") >= 2})
    attrs = subprocess.run(["git", "check-attr", "-z", "export-ignore", "--", *(f"modules/{n}/" for n in tops)],
                           cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout.split("\0")
    ignored = {attrs[i].split("/")[1] for i in range(0, len(attrs) - 2, 3) if attrs[i + 2] == "set"}
    return [n for n in tops if n not in ignored]


def tags() -> list[str]:
    out = subprocess.run(["git", "tag", "--list", "v*"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    found = [t for t in out.split() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    return [t for t in found if tuple(map(int, t[1:].split("."))) >= (0, 5, 0)]


def from_tag(tag: str, names: list[str]) -> dict[tuple[str, str], str]:
    raw = subprocess.run(["git", "archive", tag, "modules"], cwd=ROOT, capture_output=True, check=True).stdout
    found = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        for member in tar:
            parts = member.name.split("/")
            if member.isfile() and len(parts) >= 3 and parts[1] in names and not SKIP & set(parts):
                found[(parts[1], "/".join(parts[2:]))] = hashlib.sha256(tar.extractfile(member).read()).hexdigest()
    return found


def tree_files(names: list[str]) -> dict[tuple[str, str], bytes]:
    """現在 git 暫存區的檔：追蹤的、隨附模組的（核心的包會帶的就是這些）。讀暫存區的內容、不讀工作目錄：
    Windows 的 git 可能把換行換成 CRLF 再檢出，包（git archive）裡的是沒換過的。"""
    listed = subprocess.run(["git", "ls-files", "-z", "modules"], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", check=True).stdout.split("\0")
    found = {}
    for path in filter(None, listed):
        parts = path.split("/")
        if len(parts) >= 3 and parts[1] in names and not SKIP & set(parts):
            found[(parts[1], "/".join(parts[2:]))] = subprocess.run(
                ["git", "show", f":{path}"], cwd=ROOT, capture_output=True, check=True).stdout
    return found


def from_tree(names: list[str]) -> dict[tuple[str, str], str]:
    return {key: hashlib.sha256(data).hexdigest() for key, data in tree_files(names).items()}


def retired_hashes(name: str) -> dict[str, list[str]]:
    """拿掉的模組在 git 歷史裡每一個 commit 的每個檔的雜湊（沒有 tag 的 clone 也收得齊；多收了沒發出去的版本只是比較寬）。"""
    commits = subprocess.run(["git", "log", "--format=%H", "--", f"modules/{name}"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.split()
    found: dict[str, list[str]] = {}
    for commit in commits:
        listed = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", commit, "--", f"modules/{name}/"], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", check=True).stdout.split("\0")
        for path in filter(None, listed):
            parts = path.split("/")
            if not SKIP & set(parts):
                data = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True, check=True).stdout
                digest = hashlib.sha256(data).hexdigest()
                if digest not in (hashes := found.setdefault("/".join(parts[2:]), [])):
                    hashes.append(digest)
    return dict(sorted(found.items()))


def current_version() -> str:
    text = (CORE / "__init__.py").read_text(encoding="utf-8")
    return re.search(r"""__version__\s*=\s*["']([^"']+)["']""", text).group(1)


def build(extra_tags: bool = True) -> dict[str, dict]:
    """{模組: {檔: [sha256…]}}，另加 ".introduced": {模組: 第一次出現在哪一版}（D159：新加的隨附模組，「更新」之後要裝上）。
    模組名不會以 . 開頭（掃描會略過），所以 ".introduced" 不會撞名。"""
    names, table, introduced = bundled_names(), {}, {}
    versions = [*(t[1:] for t in sorted(tags() if extra_tags else [], key=lambda t: tuple(map(int, t[1:].split("."))))),
                current_version()]
    if OUT.is_file():  # 已經在表裡的雜湊一個都不丟：發出去過的版本不一定有 tag（例如在沒有 tag 的 clone 裡重新產生）
        for name, files in json.loads(OUT.read_text(encoding="utf-8")).items():
            if not name.startswith(".") and name in names:
                for rel, hashes in files.items():
                    table.setdefault(name, {})[rel] = list(hashes)
    for version, found in zip(versions, [*(from_tag(f"v{v}", names) for v in versions[:-1]), from_tree(names)], strict=True):
        for (name, rel), digest in found.items():
            introduced.setdefault(name, version)
            hashes = table.setdefault(name, {}).setdefault(rel, [])
            if digest not in hashes:
                hashes.append(digest)
    have = json.loads(OUT.read_text(encoding="utf-8")).get(".retired", {}) if OUT.is_file() else {}
    retired = {n: have.get(n) or {"since": since, "files": retired_hashes(n)} for n, since in sorted(RETIRED.items())}
    return {**{n: dict(sorted(table[n].items())) for n in sorted(table)}, ".introduced": dict(sorted(introduced.items())),
            ".retired": retired}


def main() -> int:
    if "--check" in sys.argv[1:]:
        have = json.loads(OUT.read_text(encoding="utf-8"))
        missing = [f"{n}/{rel}" for (n, rel), d in from_tree(bundled_names()).items() if d not in have.get(n, {}).get(rel, [])]
        missing += [f"{n}（.introduced）" for n in bundled_names() if n not in have.get(".introduced", {})]
        print("\n".join(missing) or "ok")
        return 1 if missing else 0
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=0, sort_keys=False) + "\n", encoding="utf-8")
    print(f"寫了 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
