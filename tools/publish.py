"""發佈工具（開發端）：把一個版本變成可以放上網的檔案，給「更新」與「工作坊」兩個模組讀。

    python3 tools/publish.py --version 0.5.0 --base-url <放檔案的地方> --modules 整理桌面 開工

在 --out（預設 交付/發佈/）產生：
    iPLoT-v0.5.0.zip   核心的包（git archive 那個 tag；還沒打 tag 時加 --ref HEAD）
    update.json        「更新」讀的：版本、zip 的網址與 sha256、這一版改了什麼（取自 CHANGELOG.md 那一節）
    模組/<名稱>.zip    每個模組一包，最上層是 <名稱>/
    index.json         「工作坊」讀的：每個模組的名稱、版本、網址、sha256、說明、圖示、這一版改了什麼
    index.html         給還沒裝 iPLoT 的人看的一頁：同一份資料
    .nojekyll          空檔：GitHub Pages 照原樣放出每個檔

--base-url 是 --out 那個資料夾放上網之後對應的網址。iPLoT 自己的檔放在 GitHub Pages（D79）：
    python3 tools/publish.py --version 0.5.0 --base-url https://<帳號>.github.io/iplot-workshop \
        --out ../iplot-workshop --modules-site https://william10310406.github.io/iplot-modules/
iPLoT 自己只發核心：--modules-site https://william10310406.github.io/iplot-modules/（模組從 iplot-modules 的上傳表單發）；
--modules 留給本機 file:// 試與測試。在本機試就用 file:///…/交付/發佈。
config.py 填 UPDATE_URL = "<base-url>/update.json"、WORKSHOP_URL = "<base-url>/index.json"。
模組的版本與這一版改了什麼，取自模組資料夾裡的 CHANGELOG.md（格式跟 repo 的一樣）最上面那一節：
版本號，與那一節的第一段（寫進 index.json 的 notes）。沒有 CHANGELOG.md 的模組，版本跟 --version 一樣、notes 是空的；
要另外指定就寫「名稱=版本」，例如 --modules 整理桌面=1.2.0。兩邊都有又不一樣就停下來，一個檔都不產生。"""

import argparse
import contextlib
import hashlib
import html
import json
import re
import subprocess
import sys
import unicodedata
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
    for line in changelog.read_text(encoding="utf-8-sig").splitlines():
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
    """CHANGELOG.md 最上面那一節（[Unreleased] 不算）的（版本號, 第一段）；沒有這個檔回 (None, "")。
    有這個檔、卻讀不出最上面那一版（不是 UTF-8、沒有任何一節、版本號不是 1.2.0 這種寫法）丟 ValueError（一句話）：
    不悄悄跳過那一節去發佈舊的，也不悄悄改用 --version。"""
    if not changelog.is_file():
        return None, ""
    try:
        text = changelog.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("不是 UTF-8 的文字檔") from None
    heads = [h for h in re.findall(r"^## \[([^\]]*)\]", text, re.M) if h.strip().casefold() != "unreleased"]
    if not heads:
        raise ValueError("裡面沒有「## [1.0.0] - 日期」這樣的一節")
    if not re.fullmatch(r"\d+(\.\d+)*", heads[0]):
        raise ValueError(f"最上面那一節的版本「{heads[0]}」不是 1.2.0 這種只有數字與點的寫法（工作坊比不了別的寫法）")
    return heads[0], changelog_notes(changelog, heads[0])


def pack_module(folder: Path, out_dir: Path, files: list[str] | None = None) -> Path:
    """把模組資料夾壓成 out_dir/<名稱>.zip，最上層是 <名稱>/；SKIP 裡的名字不管在哪一層都不帶。
    給了 files（相對於模組資料夾的路徑，main 給的是 git 追蹤的檔）就只收那些，不在磁碟上的略過。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{folder.name}.zip"
    found = folder.rglob("*") if files is None else (folder / f for f in files)
    files = sorted(p for p in found
                   if p.is_file() and not SKIP & {part.casefold() for part in p.relative_to(folder).parts})
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as z:  # 1980 年以前的檔記成 1980 年
        for p in files:
            z.write(p, f"{folder.name}/{p.relative_to(folder).as_posix()}")
    return out


def tracked(root: Path, name: str) -> list[str]:
    """modules/<name> 裡 git 追蹤的檔，相對於模組資料夾。自己產生的檔（例如互通的捷徑與紀錄）、
    還沒 commit 的新檔都不在裡面（D79 之後的缺口，0.5.1 收掉）。"""
    listed = subprocess.run(["git", "ls-files", "-z", "--", f"modules/{name}"], cwd=root, capture_output=True)
    prefix = unicodedata.normalize("NFC", f"modules/{name}/")
    paths = (unicodedata.normalize("NFC", p) for p in listed.stdout.decode("utf-8").split("\0") if p)
    return [p[len(prefix):] for p in paths if p.startswith(prefix)]


def _write(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def update_data(zip_path: Path, version: str, zip_url: str, notes: str) -> dict:
    return {"version": version, "zip_url": zip_url, "sha256": sha256_of(zip_path), "notes": notes}


def write_update(zip_path: Path, version: str, zip_url: str, notes: str, out: Path) -> Path:
    """out/update.json：「更新」模組讀的那一個檔。"""
    return _write(out / "update.json", update_data(zip_path, version, zip_url, notes))


def write_index(entries: list[dict], out: Path) -> Path:
    """out/index.json：「工作坊」模組讀的那一個檔。"""
    return _write(out / "index.json", {"modules": entries})


PAGE = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>iPLoT 工作坊</title>
<style>
:root {{ color-scheme: light dark; --bg: #ffffff; --fg: #1c1d21; --muted: #6b7080; --line: #dfe2e9; --accent: #3d6ee0; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg: #242529; --fg: #ebecf0; --muted: #9a9fae; --line: #34363f; --accent: #7398f4; }}
}}
body {{ margin: 0 auto; max-width: 760px; padding: 20px 16px 40px; background: var(--bg); color: var(--fg);
  font: 15px/1.6 -apple-system, BlinkMacSystemFont, "PingFang TC", "Microsoft JhengHei", "Segoe UI", sans-serif; }}
h1 {{ font-size: 22px; margin: 0 0 16px; }}
h2 {{ font-size: 17px; margin: 28px 0 8px; }}
a {{ color: var(--accent); }}
.box {{ border-top: 1px solid var(--line); padding: 12px 0; }}
.icon {{ font-size: 22px; margin-right: 6px; }}
.muted, .sha {{ color: var(--muted); font-size: 13px; }}
.sha {{ font-family: ui-monospace, Menlo, monospace; overflow-wrap: anywhere; }}
.notes {{ white-space: pre-line; }}
</style>
</head>
<body>
<h1>iPLoT 工作坊</h1>
<h2>iPLoT {version}</h2>
<div class="box">
<p><a href="{zip_url}">下載 {zip_name}</a></p>
<p class="sha">sha256 {sha256}</p>
<p>解壓縮後雙擊 iPLoT.command；第一次啟動會自動安裝介面，要有網路。</p>
<p class="notes">{notes}</p>
</div>
<h2>模組</h2>
{modules}
</body>
</html>
"""
HERE = "<p>在 iPLoT 裡按「工作坊」就能安裝、更新這些模組；也可以下載 zip、解開後把資料夾放進 modules/。</p>"
SITE = '<p>模組在 <a href="{url}">{url}</a>，誰都能上傳。</p>'
MODULE = """<div class="box">
<p><span class="icon">{icon}</span><b>{name}</b> <span class="muted">{version}</span></p>
<p>{description}</p>
{notes}<p><a href="{zip_url}">下載 {name}.zip</a></p>
<p class="sha">sha256 {sha256}</p>
</div>"""


def write_html(update: dict, entries: list[dict], out: Path, modules_site: str | None = None) -> Path:
    """out/index.html：給還沒裝 iPLoT 的人看的一頁，資料就是 update.json 與 index.json 那兩份。
    純 HTML 加內嵌的 CSS，沒有 JS、沒有外部資源；每個字都先 html.escape。"""
    e = lambda value: html.escape(str(value or ""), quote=True)  # noqa: E731
    blocks = [MODULE.format(icon=e(m.get("icon")), name=e(m["name"]), version=e(m["version"]), description=e(m.get("description")),
                            notes=f'<p class="notes">這一版：{e(m.get("notes"))}</p>\n' if m.get("notes") else "",
                            zip_url=e(m["zip_url"]), sha256=e(m["sha256"])) for m in entries]
    modules = HERE + "\n" + "\n".join(blocks) if modules_site is None else SITE.format(url=e(modules_site))
    page = PAGE.format(version=e(update["version"]), zip_url=e(update["zip_url"]), zip_name=e(update["zip_url"].rpartition("/")[2]),
                       sha256=e(update["sha256"]), notes=e(update["notes"]), modules=modules)
    (out / "index.html").write_text(page, encoding="utf-8")
    return out / "index.html"


def _url(base: str, *parts: str) -> str:
    """base 加上幾段路徑；中文與空白寫成 %XX（https 的網址只能是 ASCII），file:// 也照樣打得開。"""
    return "/".join([urllib.parse.quote(base.rstrip("/"), safe=":/%"), *(urllib.parse.quote(p) for p in parts)])


FORGOT = ("{ref} 的 config.py 的 WORKSHOP_URL（{url}）不在 --base-url 底下：模組不從這裡發了，"
          "加 --modules-site <模組網站的網址>（那一頁就不會把舊的 index.json 列回去）；真的要從這裡發模組才用 --modules")
ATTRS = ("注意：工作樹的 .gitattributes 跟 {ref} 裡的不一樣（改了還沒 commit，或還沒追蹤）；"
         "核心的包照 {ref} 裡的那一份排除檔案（export-ignore）。要照新的排，先 commit、重打 tag 再發佈。")
TOP = "核心的包最上層："


def workshop_url_at(root: Path, ref: str) -> str | None:
    """<ref>:config.py 的 WORKSHOP_URL；那個 ref 沒有 config.py、或不是一個字串（例如 None）回 None。位元組讀、自己解碼。"""
    shown = subprocess.run(["git", "show", f"{ref}:config.py"], cwd=root, capture_output=True)
    if shown.returncode != 0:
        return None
    found = re.search(r'^WORKSHOP_URL\s*=\s*(["\'])(.*?)\1', shown.stdout.decode("utf-8", "replace"), re.M)
    return found.group(2) if found else None


def under(url: str, base: str) -> bool:
    return urllib.parse.quote(url, safe=":/%").startswith(_url(base, ""))


def attributes_differ(root: Path, ref: str) -> bool:
    """工作樹的 .gitattributes 跟 ref 裡的不一樣（比 git 的 blob，不比位元組：Windows 的 autocrlf 會把工作樹改成 CRLF）。"""
    run = lambda *a: subprocess.run(["git", *a], cwd=root, capture_output=True, text=True)  # noqa: E731
    here = run("hash-object", "--", ".gitattributes") if (root / ".gitattributes").is_file() else None
    there = run("rev-parse", f"{ref}:.gitattributes")
    return (here.stdout.strip() if here and here.returncode == 0 else None) != (there.stdout.strip() if there.returncode == 0 else None)


def top_level(zip_path: Path) -> list[str]:
    """核心 zip 最上層（iPLoT-vX.Y.Z/ 底下的第一段）；資料夾後面加 /。"""
    names = set()
    with zipfile.ZipFile(zip_path) as z:
        for entry in z.namelist():
            parts = [p for p in entry.split("/")[1:] if p]
            if parts:
                names.add(parts[0] + ("/" if len(parts) > 1 or entry.endswith("/") else ""))
    return sorted(names)


def main(argv: list[str], root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description="產生核心 zip、update.json、模組 zip、index.json、index.html、.nojekyll")
    parser.add_argument("--version", required=True, help="核心版本，例如 0.5.0")
    parser.add_argument("--base-url", required=True, help="--out 那個資料夾放上網之後對應的網址")
    modules = parser.add_mutually_exclusive_group()
    modules.add_argument("--modules", nargs="*", default=[], help="要放進工作坊的模組：名稱，或 名稱=版本")
    modules.add_argument("--modules-site", metavar="網址",
                         help="模組網站的網址，例如 https://william10310406.github.io/iplot-modules/："
                              "給了就只發核心，index.json 不動，那一頁的模組那一段換成一句話＋連結")
    parser.add_argument("--ref", help="核心 zip 從哪個 git ref 打包；預設是 v<版本> 這個 tag")
    parser.add_argument("--out", help="產生的檔放哪裡（相對於現在的資料夾）；預設是 iPLoT 資料夾裡的 交付/發佈/")
    args = parser.parse_args(argv)
    version, out = args.version, Path(args.out).resolve() if args.out else root / "交付" / "發佈"
    asked = [(name, ver) for name, _, ver in (m.partition("=") for m in args.modules)]
    missing = [name for name, _ in asked if not (root / "modules" / name / "iplot.py").is_file()]
    if missing:
        print("modules/ 裡沒有這些模組：" + "、".join(missing))
        return 1
    wanted = []  # (名稱, 版本, notes)
    for name, ver in asked:
        try:
            logged, notes = latest(root / "modules" / name / "CHANGELOG.md")
        except ValueError as exc:
            print(f"modules/{name}/CHANGELOG.md {exc}；改好再發佈")
            return 1
        if ver and logged and ver != logged:  # 單一來源：不悄悄蓋掉其中一邊
            print(f"「{name}」：指令列寫 {ver}，modules/{name}/CHANGELOG.md 最上面那一節是 {logged}；"
                  "拿掉指令列的版本，或改 CHANGELOG.md，再發佈")
            return 1
        files = tracked(root, name)
        if not files:  # 整個資料夾都還沒 commit：包會是空的
            print(f"「{name}」沒有任何 git 追蹤的檔：模組的包只收 git 追蹤的檔，先 commit 再發佈")
            return 1
        wanted.append((name, ver or logged or version, notes, files))
    ref, core_zip = args.ref or f"v{version}", out / f"iPLoT-v{version}.zip"
    if not args.modules and args.modules_site is None:  # 忘了 --modules-site：照 <ref>:config.py，不是工作樹的
        url = workshop_url_at(root, ref)
        if url is not None and not under(url, args.base_url):
            print(FORGOT.format(ref=ref, url=url))
            return 1
    out.mkdir(parents=True, exist_ok=True)
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
    update = update_data(core_zip, version, _url(args.base_url, core_zip.name), notes)
    made = [core_zip, _write(out / "update.json", update)]
    entries = []
    for name, ver, module_notes, files in wanted:
        folder = root / "modules" / name
        packed, meta = pack_module(folder, out / MODULES, files), read_meta(folder / "iplot.py")
        entries.append({"name": name, "version": ver, "zip_url": _url(args.base_url, MODULES, packed.name),
                        "sha256": sha256_of(packed), "description": meta.description, "icon": meta.icon,
                        "notes": module_notes})
        made.append(packed)
    if wanted:  # 沒給 --modules：只發佈核心，原本的 index.json 不動，網頁上的模組照它列
        made.append(write_index(entries, out))
    elif args.modules_site is None:
        with contextlib.suppress(OSError, ValueError, KeyError, TypeError):
            entries = json.loads((out / "index.json").read_text(encoding="utf-8"))["modules"]
    (out / ".nojekyll").write_bytes(b"")
    made += [write_html(update, entries, out, args.modules_site), out / ".nojekyll"]
    print(f"產生在 {out}：\n" + "\n".join(f"  {p.relative_to(out)}" for p in made))
    print(TOP + "  ".join(top_level(core_zip)))
    if git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        print(f"注意：工作目錄有還沒 commit 的改動；核心的包是從 {ref} 打的，不含那些改動"
              "（模組的包含：模組收的是 git 追蹤的檔在磁碟上的樣子）。")
    if attributes_differ(root, ref):
        print(ATTRS.format(ref=ref))
    update_line = f'UPDATE_URL = "{_url(args.base_url, "update.json")}"'
    if args.modules_site is not None:
        print(f"把 {out} 放上 --base-url 那個網址之後，在 config.py 填這一行（從行首貼上，前面不要留空白）：\n"
              f"{update_line}\nWORKSHOP_URL 照 config.py，不改（模組在 {args.modules_site}）。")
        return 0
    print(f"把 {out} 放上 --base-url 那個網址之後，在 config.py 填這兩行（從行首貼上，前面不要留空白）：\n"
          f'{update_line}\nWORKSHOP_URL = "{_url(args.base_url, "index.json")}"')
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
