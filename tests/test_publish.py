"""tools/publish.py：把一個版本變成可以放上網的檔案（核心 zip、update.json、模組 zip、index.json）。
tools/ 不是套件，用檔案路徑載入。真的跑 git archive 的那一個測試在 tmp 裡自己建一個小 repo。"""

import hashlib
import importlib.util
import json
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
         "sha256": sha(out / "模組" / "整理桌面.zip"), "description": "把桌面上的截圖收起來。", "icon": "🧹"},
        {"name": "沒圖示", "version": "9.9.9", "zip_url": mods + "%E6%B2%92%E5%9C%96%E7%A4%BA.zip",
         "sha256": sha(out / "模組" / "沒圖示.zip"), "description": "", "icon": None}]
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


def test_core_only_run_keeps_the_index(publish, repo, capsys):
    out = repo / "交付" / "發佈"
    publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x", "--modules", "整理桌面"], root=repo)
    before = (out / "index.json").read_bytes()
    assert publish.main(["--version", "9.9.9", "--base-url", "https://example.invalid/x"], root=repo) == 0
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
