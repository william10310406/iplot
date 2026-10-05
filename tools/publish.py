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
模組的版本預設跟 --version 一樣；要另外指定就寫「名稱=版本」，例如 --modules 整理桌面=1.2.0。"""

import argparse
import hashlib
import json
import subprocess
import sys
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.meta import read_meta  # noqa: E402

SKIP = {".history", ".origin", ".unconfirmed", "__pycache__", ".DS_Store"}  # 不進模組的包：各台電腦自己的東西
MODULES = "模組"  # 交付/發佈/ 裡放模組 zip 的資料夾


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def changelog_notes(changelog: Path, version: str) -> str:
    """CHANGELOG.md 裡「## [version]」到下一個「## [」之間的文字；找不到那一版回空字串。"""
    lines, found = [], False
    for line in changelog.read_text(encoding="utf-8").splitlines():
        if line.startswith("## ["):
            if found:
                break
            found = line.startswith(f"## [{version}]")
        elif found:
            lines.append(line)
    return "\n".join(lines).strip()


def pack_module(folder: Path, out_dir: Path) -> Path:
    """把模組資料夾壓成 out_dir/<名稱>.zip，最上層是 <名稱>/；SKIP 裡的名字不管在哪一層都不帶。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{folder.name}.zip"
    files = sorted(p for p in folder.rglob("*") if p.is_file() and not SKIP & set(p.relative_to(folder).parts))
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
    wanted = [(name, ver or version) for name, _, ver in (m.partition("=") for m in args.modules)]
    missing = [name for name, _ in wanted if not (root / "modules" / name / "iplot.py").is_file()]
    if missing:
        print("modules/ 裡沒有這些模組：" + "、".join(missing))
        return 1
    out.mkdir(parents=True, exist_ok=True)
    core_zip = out / f"iPLoT-v{version}.zip"
    archive = subprocess.run(["git", "archive", "--format=zip", f"--prefix=iPLoT-v{version}/", "-o", str(core_zip),
                              args.ref or f"v{version}"], cwd=root, capture_output=True, text=True)
    if archive.returncode != 0:
        print("git archive 失敗（還沒打 tag 的話加 --ref HEAD）：" + archive.stderr.strip())
        return 1
    notes = changelog_notes(root / "CHANGELOG.md", version)
    made = [core_zip, write_update(core_zip, version, _url(args.base_url, core_zip.name), notes, out)]
    entries = []
    for name, ver in wanted:
        folder = root / "modules" / name
        packed, meta = pack_module(folder, out / MODULES), read_meta(folder / "iplot.py")
        entries.append({"name": name, "version": ver, "zip_url": _url(args.base_url, MODULES, packed.name),
                        "sha256": sha256_of(packed), "description": meta.description, "icon": meta.icon})
        made.append(packed)
    made.append(write_index(entries, out))
    print("產生了：\n" + "\n".join(f"  {p.relative_to(root)}" for p in made))
    print(f"上傳 {out.relative_to(root)}/ 之後，在 config.py 填：\n"
          f'  UPDATE_URL = "{_url(args.base_url, "update.json")}"\n  WORKSHOP_URL = "{_url(args.base_url, "index.json")}"')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
