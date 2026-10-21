"""tools/publish.py：把一個版本變成可以放上網的檔案（核心 zip、update.json、模組 zip、index.json）。
tools/ 不是套件，用檔案路徑載入。真的跑 git archive 的那一個測試在 tmp 裡自己建一個小 repo。"""

import hashlib
import importlib.util
import json
import re
import subprocess
import zipfile
from pathlib import Path

import pytest
from conftest import make_module

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def publish():
    spec = importlib.util.spec_from_file_location("iplot_publish", ROOT / "tools" / "publish.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sha256_of(publish, tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(b"abc")
    assert publish.sha256_of(f) == hashlib.sha256(b"abc").hexdigest()


def test_changelog_notes_extracts_section(publish, tmp_path):
    f = tmp_path / "CHANGELOG.md"
    f.write_text("# Changelog\n\n## [Unreleased]\n\n## [0.5.0] - 2026-10-05\n\n摘要一句。\n\n### 新增\n- 一\n\n"
                 "## [0.4.0] - 2026-10-05\n\n舊的。\n", encoding="utf-8")
    assert publish.changelog_notes(f, "0.5.0") == "摘要一句。"
    assert publish.changelog_notes(f, "0.4.0") == "舊的。"
    assert publish.changelog_notes(f, "9.9.9") == "", "找不到那一版：空字串，不是錯"


def test_pack_module_layout_and_exclusions(publish, tmp_path):
    """zip 最上層剛好是模組資料夾的名字；不帶 .history/、.origin、.unconfirmed、__pycache__、.DS_Store。"""
    folder = make_module(tmp_path / "modules", "整理 桌面", 'ICON = "🧹"\n')
    (folder / "helper.py").write_text("x = 1\n", encoding="utf-8")
    (folder / "data").mkdir()
    (folder / "data" / "a.txt").write_text("a", encoding="utf-8")
    for junk in (".history/2026.py", "__pycache__/h.pyc", "data/__pycache__/x.pyc", ".origin", ".unconfirmed", ".DS_Store"):
        (folder / junk).parent.mkdir(exist_ok=True)
        (folder / junk).write_text("junk", encoding="utf-8")
    out = publish.pack_module(folder, tmp_path / "out")
    assert out == tmp_path / "out" / "整理 桌面.zip"
    with zipfile.ZipFile(out) as z:
        assert sorted(z.namelist()) == ["整理 桌面/data/a.txt", "整理 桌面/helper.py", "整理 桌面/iplot.py"]
        assert z.read("整理 桌面/helper.py") == b"x = 1\n"


def test_pack_module_handles_files_from_before_1980(publish, tmp_path):
    """第三輪審查 I4：模組裡有 1980 年以前的檔案時間，打包照樣成功（zip 記成 1980 年），不是 traceback、不是半個 --out。"""
    import os
    folder = make_module(tmp_path / "modules", "舊模組")
    os.utime(folder / "iplot.py", (0, 0))
    with zipfile.ZipFile(publish.pack_module(folder, tmp_path / "out")) as z:
        assert z.namelist() == ["舊模組/iplot.py"]


def test_write_update_shape(publish, tmp_path):
    z = tmp_path / "iPLoT-v0.5.0.zip"
    z.write_bytes(b"zip bytes")
    path = publish.write_update(z, "0.5.0", "https://example.invalid/iplot/iPLoT-v0.5.0.zip", "這一版改了什麼", tmp_path)
    assert path == tmp_path / "update.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "version": "0.5.0", "zip_url": "https://example.invalid/iplot/iPLoT-v0.5.0.zip", "sha256": sha(z),
        "notes": "這一版改了什麼"}


def test_write_index_shape(publish, tmp_path):
    entries = [{"name": "整理桌面", "version": "1.0.0", "zip_url": "u", "sha256": "s", "description": "一句話", "icon": "🧹"}]
    path = publish.write_index(entries, tmp_path)
    assert path == tmp_path / "index.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {"modules": entries}
    assert "整理桌面" in path.read_text(encoding="utf-8"), "中文照原樣寫，人看得懂"


def git(repo, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True,
                   capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """tmp 裡的小 iPLoT repo：main.py、core/、CHANGELOG.md、兩個模組，tag v9.9.9。"""
    r = tmp_path / "iPLoT"
    (r / "core").mkdir(parents=True)
    (r / "core" / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    (r / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (r / "CHANGELOG.md").write_text("# Changelog\n\n## [9.9.9] - 2026-10-05\n\n九九九。\n\n## [0.1.0]\n舊。\n", encoding="utf-8")
    make_module(r / "modules", "整理桌面", '"""把桌面上的截圖收起來。"""\nICON = "🧹"\ndef run(app):\n    pass\n')
    make_module(r / "modules", "沒圖示", "def run(app):\n    pass\n")
    git(r, "init", "-q")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "x")
    git(r, "tag", "v9.9.9")
    return r


def test_main_end_to_end(publish, repo, capsys):
    out = repo / "交付" / "發佈"
    code = publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/我的 repo/main/發佈/",
                         "--modules", "整理桌面=1.2.0", "沒圖示"], root=repo)
    assert code == 0
    core_zip = out / "iPLoT-v9.9.9.zip"
    with zipfile.ZipFile(core_zip) as z:
        assert {"iPLoT-v9.9.9/main.py", "iPLoT-v9.9.9/core/__init__.py"} <= set(z.namelist())
    update = json.loads((out / "update.json").read_text(encoding="utf-8"))
    base = "https://example.invalid/%E6%88%91%E7%9A%84%20repo/main/%E7%99%BC%E4%BD%88"
    assert update == {"version": "9.9.9", "zip_url": base + "/iPLoT-v9.9.9.zip", "sha256": sha(core_zip), "notes": "九九九。"}
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))["modules"]
    mods = base + "/%E6%A8%A1%E7%B5%84/"
    assert index == [
        {"name": "整理桌面", "version": "1.2.0", "zip_url": mods + "%E6%95%B4%E7%90%86%E6%A1%8C%E9%9D%A2.zip",
         "sha256": sha(out / "模組" / "整理桌面.zip"), "description": "把桌面上的截圖收起來。", "icon": "🧹", "notes": ""},
        {"name": "沒圖示", "version": "9.9.9", "zip_url": mods + "%E6%B2%92%E5%9C%96%E7%A4%BA.zip",
         "sha256": sha(out / "模組" / "沒圖示.zip"), "description": "", "icon": None, "notes": ""}]
    assert "update.json" in capsys.readouterr().out


def test_main_file_base_url_is_kept_openable(publish, repo):
    """驗收用 file:// 網址：產生的 zip_url 用 urllib 真的打得開。"""
    import urllib.request
    out = repo / "交付" / "發佈"
    assert publish.main(["--version", "9.9.9", "--base-url", out.as_uri(), "--modules", "整理桌面"], root=repo) == 0
    update = json.loads((out / "update.json").read_text(encoding="utf-8"))
    with urllib.request.urlopen(update["zip_url"]) as r:
        assert hashlib.sha256(r.read()).hexdigest() == update["sha256"]
    entry = json.loads((out / "index.json").read_text(encoding="utf-8"))["modules"][0]
    with urllib.request.urlopen(entry["zip_url"]) as r:
        assert hashlib.sha256(r.read()).hexdigest() == entry["sha256"]


def test_main_unknown_module_is_a_plain_error(publish, repo, capsys):
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "不存在"], root=repo) == 1
    assert "不存在" in capsys.readouterr().out and not (repo / "交付" / "發佈" / "index.json").exists()


def test_main_ref_defaults_to_the_version_tag(publish, repo):
    git(repo, "tag", "-d", "v9.9.9")
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x"], root=repo) == 1, "沒有 v9.9.9 這個 tag 了"
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--ref", "HEAD"], root=repo) == 0
    assert (repo / "交付" / "發佈" / "iPLoT-v9.9.9.zip").exists()


# 最終審查的修正

def test_notes_are_the_summary_paragraph(publish, tmp_path):
    """update.json 的 notes 會整段顯示在「要更新嗎」的對話框裡：只取那一版的第一段（摘要），不是整節。"""
    f = tmp_path / "CHANGELOG.md"
    f.write_text("## [0.5.0] - 2026-10-05\n\n摘要第一行，\n摘要第二行。\n\n**粗體一段**\n\n### 新增\n- 一\n\n## [0.4.0]\n舊。\n", encoding="utf-8")
    assert publish.changelog_notes(f, "0.5.0") == "摘要第一行，\n摘要第二行。"


def test_main_refuses_a_package_whose_core_is_another_version(publish, repo, capsys):
    """打包的那個 ref 裡，core 的版本不是 --version：update.json 會宣稱一個包裡沒有的版本，裝了永遠「還有新版」。"""
    out = repo / "交付" / "發佈"
    assert publish.main(["--version", "1.0.0", "--base-url", "https://example.invalid/x", "--ref", "HEAD"], root=repo) == 1
    assert "9.9.9" in capsys.readouterr().out and not (out / "iPLoT-v1.0.0.zip").exists() and not (out / "update.json").exists()


def test_failed_archive_does_not_destroy_the_previous_zip(publish, repo, monkeypatch):
    """git show 讀得到那一版、git archive 卻寫到一半失敗：上一次產生的 zip 不能被蓋壞，也不留 .part。
    （獨立審查 I5：以前這裡用 --ref no-such-ref，在 git show 就停了，走不到 git archive；拿掉 .part 的保護照樣通過。）"""
    out = repo / "交付" / "發佈"
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x"], root=repo) == 0
    good = (out / "iPLoT-v9.9.9.zip").read_bytes()
    real = subprocess.run

    def run(args, **kwargs):
        if "archive" in args:  # 寫了一半就失敗
            Path(args[args.index("-o") + 1]).write_bytes(b"half a zip")
            return subprocess.CompletedProcess(args, 128, "", "fatal: 模擬：寫到一半失敗")
        return real(args, **kwargs)

    monkeypatch.setattr(publish.subprocess, "run", run)
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x"], root=repo) == 1
    assert (out / "iPLoT-v9.9.9.zip").read_bytes() == good and not list(out.glob("*.part"))


def test_printed_config_lines_can_be_pasted(publish, repo, capsys):
    """印出來要填進 config.py 的兩行前面不能有空白：原樣貼上會是 IndentationError。"""
    import re
    publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x"], root=repo)
    out = capsys.readouterr().out
    assert re.search(r'^UPDATE_URL = "https://example.invalid/x/update.json"$', out, re.M)
    assert re.search(r'^WORKSHOP_URL = "https://example.invalid/x/index.json"$', out, re.M)


@pytest.mark.parametrize("extra", [[], ["--modules-site", "https://example.invalid/modules/"]])
def test_core_only_run_keeps_the_index(publish, repo, capsys, extra):
    out = repo / "交付" / "發佈"
    publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面"], root=repo)
    before = (out / "index.json").read_bytes()
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", *extra], root=repo) == 0
    assert (out / "index.json").read_bytes() == before, "沒給 --modules：不動原本的 index.json"


def test_uncommitted_changes_are_mentioned(publish, repo, capsys):
    (repo / "main.py").write_text("print('還沒 commit')\n", encoding="utf-8")
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x"], root=repo) == 0
    assert "commit" in capsys.readouterr().out


def test_skip_ignores_case(publish, tmp_path):
    folder = make_module(tmp_path / "modules", "A")
    for junk in (".History/a.py", ".Origin", ".DS_STORE"):
        (folder / junk).parent.mkdir(exist_ok=True)
        (folder / junk).write_text("x", encoding="utf-8")
    with zipfile.ZipFile(publish.pack_module(folder, tmp_path / "out")) as z:
        assert z.namelist() == ["A/iplot.py"]


# 模組自己的版本與更新紀錄（D78）：模組資料夾裡的 CHANGELOG.md

MODULE_LOG = ("# Changelog\n\n「整理桌面」的版本紀錄。\n\n## [Unreleased]\n\n## [1.3.0] - 2026-10-06\n\n截圖改收進「截圖」資料夾，\n"
              "不再收進「下載」。\n\n### 變更\n- 一\n\n## [1.2.0] - 2026-10-01\n\n舊的。\n")


def test_module_version_and_notes_come_from_its_changelog(publish, repo):
    """有 CHANGELOG.md 的模組：版本是最上面那一節（[Unreleased] 不算）的版本號，notes 是那一節的第一段；
    CHANGELOG.md 跟著模組的 zip 一起出去（commit 過的才算：模組的包只收 git 追蹤的檔）。"""
    (repo / "modules" / "整理桌面" / "CHANGELOG.md").write_text(MODULE_LOG, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "log")
    out = repo / "交付" / "發佈"
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面"], root=repo) == 0
    [entry] = json.loads((out / "index.json").read_text(encoding="utf-8"))["modules"]
    assert (entry["version"], entry["notes"]) == ("1.3.0", "截圖改收進「截圖」資料夾，\n不再收進「下載」。")
    with zipfile.ZipFile(out / "模組" / "整理桌面.zip") as z:
        assert "整理桌面/CHANGELOG.md" in z.namelist()
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面=1.3.0"],
                        root=repo) == 0, "指令列寫的跟 CHANGELOG.md 一樣：照常"


def test_conflicting_versions_stop_before_writing_anything(publish, repo, capsys):
    """指令列的「名稱=版本」跟模組的 CHANGELOG.md 不一樣：單一來源，不悄悄蓋掉——說一句、代碼 1、一個檔都不產生。"""
    (repo / "modules" / "整理桌面" / "CHANGELOG.md").write_text(MODULE_LOG, encoding="utf-8")
    code = publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面=1.2.0", "沒圖示"],
                        root=repo)
    said = capsys.readouterr().out
    assert code == 1
    assert "整理桌面" in said and "1.2.0" in said and "1.3.0" in said and "CHANGELOG.md" in said
    assert len(said.strip().splitlines()) == 1, said
    assert not (repo / "交付").exists(), "一個檔都不產生"


def test_modules_without_a_changelog_follow_the_core_version(publish, repo):
    """沒有 CHANGELOG.md 的模組：版本同 --version（或指令列的「名稱=版本」），notes 是空字串。"""
    out = repo / "交付" / "發佈"
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "沒圖示", "整理桌面=1.0.1"],
                        root=repo) == 0
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))["modules"]
    assert [(e["name"], e["version"], e["notes"]) for e in index] == [("沒圖示", "9.9.9", ""), ("整理桌面", "1.0.1", "")]


# 一頁 index.html、.nojekyll、--out（D79）

class Tags(__import__("html.parser").parser.HTMLParser):
    """收集開始標籤、檢查每個非 void 標籤都有關上。"""
    VOID = {"meta", "link", "br", "hr", "img", "input", "wbr"}

    def __init__(self):
        super().__init__()
        self.opened, self.stack, self.text = [], [], []

    def handle_starttag(self, tag, attrs):
        self.opened.append((tag, dict(attrs)))
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack and self.stack[-1] == tag, (tag, self.stack)
        self.stack.pop()

    def handle_data(self, data):
        self.text.append(data)


def parsed(page):
    tags = Tags()
    tags.feed(page)
    tags.close()
    assert tags.stack == [], tags.stack
    return tags


def test_index_html_lists_every_module_and_escapes_text(publish, repo):
    """index.html 給還沒裝 iPLoT 的人看：核心的版本、下載連結、sha256、notes；每個模組的名稱、版本、說明、這一版、zip 連結、sha256。
    所有字都當文字：說明裡的 <script> 以文字出現，頁面裡沒有 <script；沒有外部資源。"""
    (repo / "modules" / "整理桌面" / "CHANGELOG.md").write_text(MODULE_LOG, encoding="utf-8")
    (repo / "modules" / "沒圖示" / "iplot.py").write_text('"""壞人 <script>alert(1)</script> & 好人。"""\ndef run(app):\n    pass\n',
                                                         encoding="utf-8")
    out = repo / "交付" / "發佈"
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面", "沒圖示"],
                        root=repo) == 0
    page = (out / "index.html").read_text(encoding="utf-8")
    update = json.loads((out / "update.json").read_text(encoding="utf-8"))
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))["modules"]
    tags = parsed(page)
    text = "".join(tags.text)
    links = [a["href"] for tag, a in tags.opened if tag == "a"]
    assert "iPLoT 工作坊" in text and "9.9.9" in text and update["sha256"] in text and "九九九。" in text
    assert "解壓縮後雙擊 iPLoT.command；第一次啟動會自動安裝介面，要有網路" in text
    assert "在 iPLoT 裡按「工作坊」就能安裝、更新這些模組；也可以下載 zip、解開後把資料夾放進 modules/" in text
    assert update["zip_url"] in links
    for entry in index:
        assert entry["name"] in text and entry["version"] in text and entry["sha256"] in text and entry["zip_url"] in links
        assert entry["description"] in text
    assert "這一版：截圖改收進「截圖」資料夾，\n不再收進「下載」。" in text
    assert text.count("這一版：") == 1, "沒有 notes 的模組沒有「這一版」"
    assert "<script" not in page.lower() and "&lt;script&gt;alert(1)&lt;/script&gt; &amp; 好人" in page
    assert not [t for t, a in tags.opened if t in ("script", "link", "img", "iframe")], "沒有 JS、沒有外部資源"
    assert "prefers-color-scheme: dark" in page and 'name="viewport"' in page


def test_out_dir_gets_everything_and_the_default_folder_stays_untouched(publish, repo, tmp_path, capsys):
    """--out：所有檔寫到那裡（核心 zip 照樣先寫 .part 再改名），交付/發佈/ 不建；印出來要填的兩行照舊。"""
    out = tmp_path / "iplot-workshop"
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面",
                         "--out", str(out)], root=repo) == 0
    made = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert made == [".nojekyll", "iPLoT-v9.9.9.zip", "index.html", "index.json", "update.json", "模組/整理桌面.zip"]
    assert not (repo / "交付").exists()
    said = capsys.readouterr().out
    assert 'UPDATE_URL = "https://example.invalid/x/update.json"' in said and str(out) in said


def test_nojekyll_is_written(publish, repo):
    """GitHub Pages 預設用 Jekyll 處理檔案：以底線、點開頭的會被略過。一個空的 .nojekyll 讓它照原樣放出來。"""
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x"], root=repo) == 0
    assert (repo / "交付" / "發佈" / ".nojekyll").read_bytes() == b""


def test_core_only_run_keeps_the_modules_on_the_page(publish, repo):
    """只發佈核心（沒給 --modules）：index.json 不動，所以 index.html 的模組那一段照原本 index.json 上的模組列。"""
    out = repo / "交付" / "發佈"
    publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面"], root=repo)
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x"], root=repo) == 0
    text = "".join(parsed((out / "index.html").read_text(encoding="utf-8")).text)
    assert "整理桌面" in text and "把桌面上的截圖收起來。" in text


@pytest.mark.parametrize("log", [
    "## [1.0.0-beta.1] - 2026-10-06\n\n新的。\n\n## [0.9.0] - 2026-10-01\n\n舊的。\n",  # 以前：悄悄發佈 0.9.0 與舊的說明
    "## [v1.0.0] - 2026-10-06\n\n新的。\n",  # 以前：當作沒有 CHANGELOG.md，跟著 --version
    "# Changelog\n\n還沒有任何一版。\n",
    "## [1.0.0]\n\n新的。\n".encode("big5"),  # 以前：traceback
])
def test_a_module_changelog_whose_top_version_cannot_be_read_stops_before_writing_anything(publish, repo, capsys, log):
    """第三輪審查（原本跳過那一節，改判）：有 CHANGELOG.md、卻讀不出最上面那一版是哪一版，就停下來說一句——不悄悄發佈舊的那一節、
    不悄悄跟著 --version、不是 traceback；一個檔都不產生。"""
    path = repo / "modules" / "整理桌面" / "CHANGELOG.md"
    path.write_bytes(log) if isinstance(log, bytes) else path.write_text(log, encoding="utf-8")
    code = publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面"], root=repo)
    said = capsys.readouterr().out.strip().splitlines()
    assert code == 1 and len(said) == 1 and "modules/整理桌面/CHANGELOG.md" in said[0], said
    assert not (repo / "交付").exists()


def test_a_module_changelog_with_a_bom_is_read(publish, repo):
    (repo / "modules" / "整理桌面" / "CHANGELOG.md").write_text("﻿## [1.3.0] - 2026-10-06\n\n摘要。\n", encoding="utf-8")
    assert publish.latest(repo / "modules" / "整理桌面" / "CHANGELOG.md") == ("1.3.0", "摘要。")


def test_main_packs_only_tracked_files(publish, repo):
    (repo / "modules" / "整理桌面" / "沒追蹤.txt").write_text("x", encoding="utf-8")
    (repo / "modules" / "整理桌面" / "捷徑").mkdir()
    (repo / "modules" / "整理桌面" / "捷徑" / "a.txt").write_text("x", encoding="utf-8")
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x",
                         "--modules", "整理桌面"], root=repo) == 0
    with zipfile.ZipFile(repo / "交付" / "發佈" / "模組" / "整理桌面.zip") as z:
        assert "整理桌面/沒追蹤.txt" not in z.namelist() and "整理桌面/iplot.py" in z.namelist()
        assert z.namelist() == ["整理桌面/iplot.py"]


def test_main_stops_for_a_module_git_does_not_track(publish, repo, capsys):
    make_module(repo / "modules", "新的")
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x",
                         "--modules", "新的"], root=repo) == 1
    assert "「新的」沒有任何 git 追蹤的檔" in capsys.readouterr().out
    assert not (repo / "交付" / "發佈" / "模組" / "新的.zip").exists()


def test_pack_module_with_a_file_list_keeps_skip(publish, tmp_path):
    folder = make_module(tmp_path / "modules", "M")
    (folder / ".origin").write_text("{}", encoding="utf-8")
    (folder / "a.txt").write_text("a", encoding="utf-8")
    out = publish.pack_module(folder, tmp_path / "out", ["iplot.py", ".origin", "gone.txt"])
    with zipfile.ZipFile(out) as z:
        assert z.namelist() == ["M/iplot.py"]


SITE_URL = "https://example.invalid/modules/"


def test_modules_and_modules_site_cannot_be_given_together(publish, repo, capsys):
    with pytest.raises(SystemExit) as exc:
        publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面",
                      "--modules-site", SITE_URL], root=repo)
    assert exc.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err
    assert not (repo / "交付").exists(), "一個檔都不產生"


def test_modules_site_prints_only_the_update_line(publish, repo, capsys):
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules-site", SITE_URL],
                        root=repo) == 0
    said = capsys.readouterr().out
    assert re.search(r'^UPDATE_URL = "https://example.invalid/x/update.json"$', said, re.M)
    assert not re.search(r"^WORKSHOP_URL = ", said, re.M)
    assert "WORKSHOP_URL 照 config.py，不改" in said


def test_modules_site_replaces_the_module_list_with_a_link(publish, repo):
    out = repo / "交付" / "發佈"
    publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面"], root=repo)
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules-site", SITE_URL],
                        root=repo) == 0
    tags = parsed((out / "index.html").read_text(encoding="utf-8"))
    text = "".join(tags.text)
    assert SITE_URL in [a["href"] for tag, a in tags.opened if tag == "a"]
    assert f"模組在 {SITE_URL}，誰都能上傳。" in text
    assert "整理桌面" not in text and "在 iPLoT 裡按「工作坊」就能安裝" not in text
    assert json.loads((out / "update.json").read_text(encoding="utf-8"))["sha256"] in text


def test_modules_site_is_escaped_in_the_page(publish, repo):
    site = 'https://example.invalid/m?a=1&b="x"'
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules-site", site],
                        root=repo) == 0
    page = (repo / "交付" / "發佈" / "index.html").read_text(encoding="utf-8")
    assert "&amp;" in page and "&quot;" in page and '"x"' not in page
    assert site in [a["href"] for tag, a in parsed(page).opened if tag == "a"]


def commit_config(repo, line):
    """repo/config.py 寫 line 一行、add、commit、git tag -f v9.9.9（tag 跟著新的 commit）。"""
    (repo / "config.py").write_text(line + "\n", encoding="utf-8")
    git(repo, "add", "config.py")
    git(repo, "commit", "-q", "-m", "config")
    git(repo, "tag", "-f", "v9.9.9")


FORGOT_ARGS = ["--version", "9.9.9", "--base-url", "https://example.invalid/x"]


def test_forgetting_modules_site_stops_before_writing_anything(publish, repo, capsys):
    commit_config(repo, 'WORKSHOP_URL = "https://example.invalid/modules/index.json"')
    assert publish.main(FORGOT_ARGS, root=repo) == 1
    said = capsys.readouterr().out
    assert len(said.strip().splitlines()) == 1 and "--modules-site" in said and "v9.9.9" in said
    assert not (repo / "交付").exists(), "一個檔都不產生"


def test_forgetting_modules_site_reads_config_from_the_ref(publish, repo, capsys):
    commit_config(repo, 'WORKSHOP_URL = "https://example.invalid/modules/index.json"')
    (repo / "config.py").write_text('WORKSHOP_URL = "https://example.invalid/x/index.json"\n', encoding="utf-8")
    assert publish.main(FORGOT_ARGS, root=repo) == 1


@pytest.mark.parametrize("line", ['WORKSHOP_URL = "https://example.invalid/x/index.json"', "WORKSHOP_URL = None"])
def test_workshop_url_under_the_base_url_needs_no_flag(publish, repo, line):
    commit_config(repo, line)
    assert publish.main(FORGOT_ARGS, root=repo) == 0


def test_modules_or_modules_site_skips_the_check(publish, repo):
    commit_config(repo, 'WORKSHOP_URL = "https://example.invalid/modules/index.json"')
    assert publish.main([*FORGOT_ARGS, "--modules", "整理桌面"], root=repo) == 0
    assert publish.main([*FORGOT_ARGS, "--modules-site", "https://example.invalid/modules/"], root=repo) == 0


def test_uncommitted_gitattributes_is_mentioned(publish, repo, capsys):
    (repo / ".gitattributes").write_bytes(b"tests/ export-ignore\n")
    assert publish.main(FORGOT_ARGS, root=repo) == 0
    assert "工作樹的 .gitattributes 跟 v9.9.9 裡的不一樣" in capsys.readouterr().out


def test_committed_gitattributes_is_not_mentioned(publish, repo, capsys):
    assert publish.main(FORGOT_ARGS, root=repo) == 0
    assert "工作樹的 .gitattributes" not in capsys.readouterr().out
    (repo / ".gitattributes").write_bytes(b"tests/ export-ignore\n")
    git(repo, "add", ".gitattributes")
    git(repo, "commit", "-q", "-m", "attrs")
    git(repo, "tag", "-f", "v9.9.9")
    assert publish.main(FORGOT_ARGS, root=repo) == 0
    assert "工作樹的 .gitattributes" not in capsys.readouterr().out


def test_core_zip_top_level_is_printed(publish, repo, capsys):
    assert publish.main(FORGOT_ARGS, root=repo) == 0
    assert "核心的包最上層：CHANGELOG.md  core/  main.py  modules/" in capsys.readouterr().out.splitlines()


EXPORT_IGNORE = ["tests/", "docs/plans/", "docs/original/", "docs/00_*", "docs/01_*", "docs/04_*", "tools/", ".github/",
                 "requirements-dev.txt", "pyproject.toml", ".gitignore", ".gitattributes", "modules/科學計算/"]


def test_gitattributes_lists_exactly_the_design_paths():
    """設計第 9.1 節：核心的包不帶的東西，一樣不多、一樣不少。"""
    lines = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert [x for x in lines if x.strip() and not x.startswith("#")] == [f"{p} export-ignore" for p in EXPORT_IGNORE]


def test_real_gitattributes_keeps_the_ignored_paths_out_of_the_core_zip(publish, repo):
    """用 repo 真的 .gitattributes 跑一次 git archive：該擋的擋掉，docs/02、03、05 與核心留著。"""
    files = ["tests/a.py", "tools/p.py", "docs/plans/x.md", "docs/original/o.py", "docs/00_現況分析.md", "docs/01_從零啟動.md",
             "docs/02_重構設計.md", "docs/03_設計決定.md", "docs/04_M1驗收.md", "docs/05_使用紀錄.md",
             ".github/workflows/ci.yml", "requirements-dev.txt", "pyproject.toml", "modules/科學計算/iplot.py"]
    for name in files:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("x\n", encoding="utf-8")
    (repo / ".gitignore").write_text("logs/\n", encoding="utf-8")
    (repo / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "files")
    git(repo, "tag", "-f", "v9.9.9")
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x"], root=repo) == 0
    with zipfile.ZipFile(repo / "交付" / "發佈" / "iPLoT-v9.9.9.zip") as z:
        names = [n.removeprefix("iPLoT-v9.9.9/") for n in z.namelist()]
    for pattern in EXPORT_IGNORE:
        prefix = pattern.rstrip("*")
        assert not [n for n in names if n.startswith(prefix)], pattern
    for kept in ["docs/02_重構設計.md", "docs/03_設計決定.md", "docs/05_使用紀錄.md", "modules/整理桌面/iplot.py",
                 "main.py", "CHANGELOG.md"]:
        assert kept in names, kept
