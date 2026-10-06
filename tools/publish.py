"""發佈工具（開發端）：把一個版本變成可以放上網的檔案，給「更新」與「工作坊」兩個模組讀。

    python3 tools/publish.py --version 0.5.0 --base-url <放檔案的地方> --modules 整理桌面 開工

在 交付/發佈/ 產生：
    iPLoT-v0.5.0.zip   核心的包（git archive 那個 tag；還沒打 tag 時加 --ref HEAD）
    update.json        「更新」讀的：版本、zip 的網址與 sha256、這一版改了什麼（取自 CHANGELOG.md 那一節）
    模組/<名稱>.zip    每個模組一包，最上層是 <名稱>/
    index.json         「工作坊」讀的：每個模組的名稱、版本、網址、sha256、說明、圖示

--base-url 是 交付/發佈/ 上傳之後對應的網址。放在 GitHub 公開 repo 的話用 raw 網址，例如
https://raw.githubusercontent.com/<帳號>/<repo>/main/發佈；在本機試就用 file:///…/交付/發佈。
然後在 config.py 填 UPDATE_URL = "<base-url>/update.json"、WORKSHOP_URL = "<base-url>/index.json"。
模組的版本與這一版改了什麼，取自模組資料夾裡的 CHANGELOG.md（格式跟 repo 的一樣）最上面那一節：
版本號，與那一節的第一段（寫進 index.json 的 notes）。沒有 CHANGELOG.md 的模組，版本跟 --version 一樣、notes 是空的；
要另外指定就寫「名稱=版本」，例如 --modules 整理桌面=1.2.0。兩邊都有又不一樣就停下來，一個檔都不產生。"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.meta import read_meta  # noqa: E402

# 不進模組的包：各台電腦自己的東西（跟 modules/工作坊/workshop.py 的 SKIP 一樣；比對時不分大小寫）
SKIP = {".history", ".origin", ".unconfirmed", "__pycache__", ".ds_store"}
MODULES = "模組"  # 交付/發佈/ 裡放模組 zip 的資料夾


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changelog_notes(changelog: Path, version: str) -> str:
    """CHANGELOG.md 裡「## [version]」那一節的第一段（摘要）；找不到那一版回空字串。
    它會整段顯示在「要更新嗎」的對話框裡，所以只取摘要，不是整節。"""
    lines, found = [], False
    for line in changelog.read_text(encoding="utf-8").splitlines():
        if line.startswith("## ["):
            if found:
                break
            found = line.startswith(f"## [{version}]")
        elif found:
            if not line.strip() and lines:
                break
            if line.strip():
                lines.append(line)
    return "\n".join(lines)


def latest(changelog: Path) -> tuple[str | None, str]:
    """CHANGELOG.md 最上面那一節的（版本號, 第一段）；[Unreleased] 這類不是版本號的節不算。
    沒有這個檔、或裡面沒有任何一節是版本號，回 (None, "")。"""
    if not changelog.is_file():
        return None, ""
    found = re.search(r"^## \[(\d+(?:\.\d+)*)\]", changelog.read_text(encoding="utf-8"), re.M)
    return (found[1], changelog_notes(changelog, found[1])) if found else (None, "")


def pack_module(folder: Path, out_dir: Path) -> Path:
    """把模組資料夾壓成 out_dir/<名稱>.zip，最上層是 <名稱>/；SKIP 裡的名字不管在哪一層都不帶。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{folder.name}.zip"
    files = sorted(p for p in folder.rglob("*")
                   if p.is_file() and not SKIP & {part.casefold() for part in p.relative_to(folder).parts})
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, f"{folder.name}/{p.relative_to(folder).as_posix()}")
    return out


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_update(zip_path: Path, version: str, zip_url: str, notes: str, out: Path) -> Path:
    """out/update.json：「更新」模組讀的那一個檔。"""
    return _write(out / "update.json", {"version": version, "zip_url": zip_url, "sha256": sha256_of(zip_path), "notes": notes})


def write_index(entries: list[dict], out: Path) -> Path:
    """out/index.json：「工作坊」模組讀的那一個檔。"""
    return _write(out / "index.json", {"modules": entries})


def _url(base: str, *parts: str) -> str:
    """base 加上幾段路徑；中文與空白寫成 %XX（https 的網址只能是 ASCII），file:// 也照樣打得開。"""
    return "/".join([urllib.parse.quote(base.rstrip("/"), safe=":/%"), *(urllib.parse.quote(p) for p in parts)])


def main(argv: list[str], root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="產生 交付/發佈/：核心 zip、update.json、模組 zip、index.json")
    parser.add_argument("--version", required=True, help="核心版本，例如 0.5.0")
    parser.add_argument("--base-url", required=True, help="交付/發佈/ 上傳之後對應的網址")
    parser.add_argument("--modules", nargs="*", default=[], help="要放進工作坊的模組：名稱，或 名稱=版本")
    parser.add_argument("--ref", help="核心 zip 從哪個 git ref 打包；預設是 v<版本> 這個 tag")
    args = parser.parse_args(argv)
    version, out = args.version, root / "交付" / "發佈"
    asked = [(name, ver) for name, _, ver in (m.partition("=") for m in args.modules)]
    missing = [name for name, _ in asked if not (root / "modules" / name / "iplot.py").is_file()]
    if missing:
        print("modules/ 裡沒有這些模組：" + "、".join(missing))
        return 1
    wanted = []  # (名稱, 版本, notes)
    for name, ver in asked:
        logged, notes = latest(root / "modules" / name / "CHANGELOG.md")
        if ver and logged and ver != logged:  # 單一來源：不悄悄蓋掉其中一邊
            print(f"「{name}」：指令列寫 {ver}，modules/{name}/CHANGELOG.md 最上面那一節是 {logged}；"
                  "拿掉指令列的版本，或改 CHANGELOG.md，再發佈")
            return 1
        wanted.append((name, ver or logged or version, notes))
    out.mkdir(parents=True, exist_ok=True)
    ref, core_zip = args.ref or f"v{version}", out / f"iPLoT-v{version}.zip"
    git = lambda *a: subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)  # noqa: E731
    shown = git("show", f"{ref}:core/__init__.py")
    if shown.returncode != 0:
        print(f"讀不到 {ref} 這個版本（還沒打 tag 的話加 --ref HEAD）：" + shown.stderr.strip())
        return 1
    packed_version = (re.findall(r'__version__ = "([^"]+)"', shown.stdout) or ["?"])[0]
    if packed_version != version:  # update.json 會宣稱一個包裡沒有的版本：裝了之後永遠「還有新版」
        print(f"{ref} 裡的核心是 {packed_version}，不是 --version 的 {version}：先 commit（或打對 tag）再發佈")
        return 1
    partial = core_zip.with_suffix(".part")
    archive = git("archive", "--format=zip", f"--prefix=iPLoT-v{version}/", "-o", str(partial), ref)
    if archive.returncode != 0:
        partial.unlink(missing_ok=True)
        print("git archive 失敗：" + archive.stderr.strip())
        return 1
    partial.replace(core_zip)
    notes = changelog_notes(root / "CHANGELOG.md", version)
    made = [core_zip, write_update(core_zip, version, _url(args.base_url, core_zip.name), notes, out)]
    entries = []
    for name, ver, module_notes in wanted:
        folder = root / "modules" / name
        packed, meta = pack_module(folder, out / MODULES), read_meta(folder / "iplot.py")
        entries.append({"name": name, "version": ver, "zip_url": _url(args.base_url, MODULES, packed.name),
                        "sha256": sha256_of(packed), "description": meta.description, "icon": meta.icon,
                        "notes": module_notes})
        made.append(packed)
    if wanted:  # 沒給 --modules：只發佈核心，原本的 index.json 不動
        made.append(write_index(entries, out))
    print("產生了：\n" + "\n".join(f"  {p.relative_to(root)}" for p in made))
    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        print(f"注意：工作目錄有還沒 commit 的改動；核心的包是從 {ref} 打的，不含那些改動（模組的包含）。")
    print(f"上傳 {out.relative_to(root)}/ 之後，在 config.py 填這兩行（從行首貼上，前面不要留空白）：\n"
          f'UPDATE_URL = "{_url(args.base_url, "update.json")}"\nWORKSHOP_URL = "{_url(args.base_url, "index.json")}"')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
