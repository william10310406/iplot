"""工作坊在每一版核心上都要開得起來（研究助理 2026-11-19：「不管在哪個版本工作坊都一定要能開」「它比核心還重要」，D158）。

做法：把 v0.5.0 以後每一個 tag 的 core/（git archive）拿出來，配上現在的 modules/工作坊，用那一版的 Core.press 真的按一次：
清單要開得出來、裝得了一個模組；清單裡有維護者上傳的新版工作坊時，要先把自己換掉、再用新版開清單。
每一版在自己的子程序裡跑（core 是同一個套件名，不能在同一個程序裡載兩版）。全部用 file:// 網址，不連網。

CI 要拿得到 tag：.github/workflows/ci.yml 的 checkout 設了 fetch-depth: 0。拿不到 tag 的本機淺 clone 會跳過；在 CI 上（環境變數 CI）
拿不到就直接失敗，免得這條保證悄悄沒在跑。"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKSHOP = ROOT / "modules" / "工作坊"
FIRST = (0, 5, 0)  # 工作坊從 0.5.0 起才有（D70）


def core_tags():
    out = subprocess.run(["git", "tag", "--list", "v*"], cwd=ROOT, capture_output=True, text=True, check=False).stdout
    found = []
    for tag in out.split():
        m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", tag)
        if m and tuple(map(int, m.groups())) >= FIRST:
            found.append(tag)
    return sorted(found, key=lambda t: tuple(map(int, t[1:].split("."))))


TAGS = core_tags()
if not TAGS and os.environ.get("CI"):
    raise RuntimeError("CI 上拿不到 git tag：checkout 要 fetch-depth: 0，工作坊的跨版本測試才會跑")

HARNESS = r'''
import json, sys
from pathlib import Path
home, url = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(home))
from core.core import Core
from core.types import Config

seen = {"logs": [], "pages": [], "installed": [], "reports": []}

class View:
    def show(self, scope): pass
    def log(self, text): seen["logs"].append(text)
    def report(self, error): seen["reports"].append(f"{error.kind}: {error.message}")
    def ask(self, prompt, default=""): return None
    def confirm(self, prompt): return True
    def choose_files(self): return []
    def choose_folder(self): return None
    def page(self, title, html, api):
        seen["pages"].append(title)
        seen["installed"].append(api.install("車車") if api is not None else None)

core = Core(home, Config(roots=("modules",), editor=None, history_keep=3, workshop_url=url), View())
core.rescan()
[info] = [m for m in core.all_modules() if m.folder.name == "工作坊"]
core.press(info)
print(json.dumps(seen, ensure_ascii=False))
'''


def pack(dest, top, files):
    with zipfile.ZipFile(dest, "w") as z:
        for rel, data in files.items():
            z.writestr(f"{top}/{rel}", data)
    return hashlib.sha256(dest.read_bytes()).hexdigest()


def entry(src, name, files, version, author):
    z = src / f"{name}.zip"
    return {"name": name, "version": version, "zip_url": z.as_uri(), "sha256": pack(z, name, files),
            "description": "測試用", "icon": "🚗", "author": author}


def newer_workshop():
    """現在的工作坊，CHANGELOG 最上面多一節 9.9.9，iplot.py 多一行看得出是新版的記號。"""
    files = {p.relative_to(WORKSHOP).as_posix(): p.read_bytes() for p in WORKSHOP.rglob("*")
             if p.is_file() and "__pycache__" not in p.parts}
    changelog = files["CHANGELOG.md"].decode("utf-8").replace("## [Unreleased]\n", "## [Unreleased]\n\n## [9.9.9] - 2099-01-01\n\n測試。\n", 1)
    files["CHANGELOG.md"] = changelog.encode("utf-8")
    files["iplot.py"] = files["iplot.py"] + b'\nNEW_VERSION_MARK = "9.9.9"\n'
    return files


def setup(tmp_path, tag, with_new_workshop, author="william10310406"):
    home = tmp_path / "iPLoT"
    home.mkdir()
    archive = subprocess.run(["git", "archive", tag, "core"], cwd=ROOT, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(home)], input=archive, check=True)
    shutil.copytree(WORKSHOP, home / "modules" / "工作坊", ignore=shutil.ignore_patterns("__pycache__", ".history"))
    src = tmp_path / "site"
    src.mkdir()
    entries = [entry(src, "車車", {"iplot.py": 'def run(app):\n    app.log("叭叭")\n'}, "0.1.0", "someone")]
    if with_new_workshop:
        entries.append(entry(src, "工作坊", newer_workshop(), "9.9.9", author))
    index = src / "index.json"
    index.write_text(json.dumps({"notice": "測試", "uploads": entries}, ensure_ascii=False), encoding="utf-8")
    return home, index.as_uri()


def press(home, url):
    env = {k: v for k, v in os.environ.items() if not k.startswith("IPLOT_")}
    done = subprocess.run([sys.executable, "-c", HARNESS, str(home), url], capture_output=True, text=True,
                          encoding="utf-8", env=env, cwd=str(home), timeout=120, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


needs_tags = pytest.mark.skipif(not TAGS, reason="這個 clone 沒有 git tag（淺 clone）")


@needs_tags
@pytest.mark.parametrize("tag", TAGS)
def test_the_workshop_opens_and_installs_on_every_core(tmp_path, tag):
    home, url = setup(tmp_path, tag, with_new_workshop=False)
    seen = press(home, url)
    assert seen["reports"] == [] and seen["pages"] == ["工作坊"], seen
    assert seen["installed"] == ["已安裝"] and (home / "modules" / "車車" / "iplot.py").is_file()


@needs_tags
@pytest.mark.parametrize("tag", TAGS)
def test_the_workshop_updates_itself_first_on_every_core(tmp_path, tag):
    home, url = setup(tmp_path, tag, with_new_workshop=True)
    seen = press(home, url)
    folder = home / "modules" / "工作坊"
    assert seen["reports"] == [] and seen["pages"] == ["工作坊"], seen  # 清單只開一次，而且是新版開的
    assert any("工作坊已自動更新：1.0.0 → 9.9.9" in line for line in seen["logs"]), seen["logs"]
    assert b"NEW_VERSION_MARK" in (folder / "iplot.py").read_bytes()
    assert not (folder / ".unconfirmed").exists() and not (folder / ".origin").exists()
    assert list((folder / ".history").glob("*-folder.zip"))


@needs_tags
def test_a_workshop_uploaded_by_someone_else_is_not_installed(tmp_path):
    home, url = setup(tmp_path, TAGS[-1], with_new_workshop=True, author="someone")
    seen = press(home, url)
    assert seen["pages"] == ["工作坊"] and not any("自動更新" in line for line in seen["logs"])
    assert b"NEW_VERSION_MARK" not in (home / "modules" / "工作坊" / "iplot.py").read_bytes()


def test_the_old_frozen_listing_is_read_from_where_it_moved(monkeypatch):
    """0.5.0、0.5.1 的 config.py 指著凍結的舊清單：工作坊改讀新的那一份、說一句，不用使用者自己改 config.py。"""
    import runpy
    import types

    asked = []
    fake = types.ModuleType("workshop")
    fake.NETWORK = (OSError,)
    fake.plain = str

    def read_listing(url):
        asked.append(url)
        raise OSError("停在這裡")

    fake.read_listing = read_listing
    monkeypatch.setitem(sys.modules, "workshop", fake)
    ns = runpy.run_path(str(WORKSHOP / "iplot.py"))
    logs = []
    app = types.SimpleNamespace(config=types.SimpleNamespace(workshop_url="https://william10310406.github.io/iplot-workshop/index.json"),
                                home=Path("/nowhere"), log=logs.append)
    ns["run"](app)
    assert asked == ["https://william10310406.github.io/iplot-modules/index.json"]
    assert "搬家" in logs[0]
