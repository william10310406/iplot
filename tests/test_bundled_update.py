"""隨附模組跟著核心更新（D156）：「更新」之後的第一次啟動，core/bundled.py 照 .backup/download-<版本>.zip 把隨附模組換成新版。
三件事要守住：舊版升級拿得到新的檔（例如 mac.py）、使用者改過的檔不被蓋掉、資料與工作坊裝來的模組不被動到。
全部在暫存資料夾裡用假的 iPLoT、假的包；最後一個用真的 git 歷史（沒有 v0.7.1 的 tag 就跳過）。"""

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest

import core
from core import bundled
from core.text import T

ROOT = Path(__file__).resolve().parents[1]
V = "0.7.2"
OLD, NEW = "# mac.py 舊版\n".encode(), "# mac.py 新版\n".encode()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package(home: Path, files: dict[str, bytes], version: str = V, extra: dict[str, bytes] | None = None) -> Path:
    """.backup/download-<版本>.zip：跟 publish 的包一樣，最上層是 iPLoT-v<版本>/；files 是 modules/ 底下的檔。"""
    path = home / ".backup" / f"download-{version}.zip"
    path.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"iPLoT-v{version}/core/__init__.py", f'__version__ = "{version}"\n')
        for rel, data in {**files, **(extra or {})}.items():
            z.writestr(f"iPLoT-v{version}/modules/{rel}", data)
    return path


def module(home: Path, name: str, files: dict[str, bytes]) -> Path:
    folder = home / "modules" / name
    for rel, data in {"iplot.py": b"def run(app):\n    pass\n", **files}.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(data)
    return folder


def known(**modules: dict[str, list[bytes]]) -> dict:
    return {name: {rel: [sha(d) for d in datas] for rel, datas in files.items()} for name, files in modules.items()}


@pytest.fixture
def home(tmp_path):
    (tmp_path / "iPLoT" / "modules").mkdir(parents=True)
    return tmp_path / "iPLoT"


def test_an_older_release_gets_the_new_mac_py_and_the_old_one_is_backed_up(home):
    os_dir = module(home, "作業系統", {"mac.py": OLD})
    package(home, {"作業系統/mac.py": NEW, "作業系統/iplot.py": b"def run(app):\n    pass\n"})
    notes = bundled.sync(home, V, known(作業系統={"mac.py": [OLD]}))
    assert (os_dir / "mac.py").read_bytes() == NEW
    assert len(notes) == 1 and "作業系統" in notes[0] and ".backup/" in notes[0]
    [saved] = (home / ".backup").glob(f"{V}-bundled-*/作業系統/mac.py")
    assert saved.read_bytes() == OLD
    assert (home / bundled.MARKER).read_text().strip() == V
    assert not list(os_dir.glob("*.iplot-new"))


def test_it_runs_once_per_version(home):
    module(home, "作業系統", {"mac.py": OLD})
    package(home, {"作業系統/mac.py": NEW})
    bundled.sync(home, V, known(作業系統={"mac.py": [OLD]}))
    (home / "modules" / "作業系統" / "mac.py").write_bytes("# 之後使用者自己改的\n".encode())
    assert bundled.sync(home, V, known()) == []  # 記著這一版處理過了：不再看
    assert (home / "modules" / "作業系統" / "mac.py").read_bytes() == "# 之後使用者自己改的\n".encode()


def test_a_file_the_user_changed_is_kept_and_the_whole_module_is_left_alone(home):
    mine = "# 我自己改的 mac.py\n".encode()
    os_dir = module(home, "作業系統", {"mac.py": mine, "win.py": "# win 舊\n".encode()})
    other = module(home, "更新", {"update.py": "# 舊\n".encode()})
    package(home, {"作業系統/mac.py": NEW, "作業系統/win.py": "# win 新\n".encode(), "更新/update.py": "# 新\n".encode()})
    notes = bundled.sync(home, V, known(作業系統={"mac.py": [OLD], "win.py": ["# win 舊\n".encode()]}, 更新={"update.py": ["# 舊\n".encode()]}))
    assert (os_dir / "mac.py").read_bytes() == mine and (os_dir / "win.py").read_bytes() == "# win 舊\n".encode()
    assert (other / "update.py").read_bytes() == "# 新\n".encode()  # 沒改過的模組照換
    joined = "\n".join(notes)
    assert T["bundled_modified"].format(name="作業系統", package=f".backup/download-{V}.zip") in joined
    assert "更新" in notes[0] and "作業系統" not in notes[0]  # 「已換成」那一句只列真的換了的
    assert (home / ".backup" / f"download-{V}.zip").is_file()  # 新版還在包裡，使用者想用可以自己拿


def test_data_and_other_files_in_a_module_are_never_touched(home):
    folder = module(home, "行事曆", {"iplot.py": "# 舊\n".encode(), "設定.json": '{"資料夾": "/x"}'.encode(), ".pid": b"123",
                                    ".history/old.py": b"h", "捷徑/a.txt": b"s", "使用者的筆記.md": b"mine"})
    before = {p.relative_to(folder): (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()}
    package(home, {"行事曆/iplot.py": "# 新\n".encode()})
    bundled.sync(home, V, known(行事曆={"iplot.py": ["# 舊\n".encode()]}))
    after = {p.relative_to(folder): (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()}
    assert after.pop(Path("iplot.py"))[0] == "# 新\n".encode() and before.pop(Path("iplot.py"))[0] == "# 舊\n".encode()
    assert after == before


def test_a_bundled_module_installed_from_outside_and_unchanged_is_taken_back(home):
    """升 1.0 的人從工作坊裝過「主控面板」（有 .origin）：每個檔都是發出去過的原樣，就換成新版、拿掉 .origin 等記號，
    回到跟著核心更新；不然舊的那份不提供面板，又因為是外來的而不算數，開起來只剩備用面板（D172）。"""
    marks = {".origin": b"url: x\nversion: 0.3.0\n", ".roles-ok": b"[]", ".unconfirmed": b""}
    folder = module(home, "互通", {"run.py": OLD, "LICENSE": b"MIT\n", "data.json": b"{}", **marks})
    package(home, {"互通/run.py": NEW})
    notes = bundled.sync(home, V, known(互通={"run.py": [OLD]}))
    assert (folder / "run.py").read_bytes() == NEW and notes and "互通" in notes[0]
    assert not any((folder / m).exists() for m in marks)
    assert (folder / "LICENSE").read_bytes() == b"MIT\n" and (folder / "data.json").is_file()


def test_an_outside_copy_already_equal_to_the_new_one_just_loses_its_marks(home):
    folder = module(home, "互通", {"run.py": NEW, ".origin": b"url: x\n"})
    package(home, {"互通/run.py": NEW})
    bundled.sync(home, V, known(互通={"run.py": [OLD]}))
    assert (folder / "run.py").read_bytes() == NEW and not (folder / ".origin").exists()


def test_a_changed_module_installed_from_outside_is_left_alone_quietly(home):
    folder = module(home, "互通", {"run.py": "# 改過\n".encode(), ".origin": b"url: x\n"})
    package(home, {"互通/run.py": NEW})
    assert bundled.sync(home, V, known(互通={"run.py": [OLD]})) == []
    assert (folder / "run.py").read_bytes() == "# 改過\n".encode() and (folder / ".origin").is_file()


def test_a_module_the_user_removed_is_not_brought_back_but_a_new_file_is_added(home):
    kept = module(home, "更新", {"update.py": "# 舊\n".encode()})
    package(home, {"更新/update.py": "# 新\n".encode(), "更新/helper.py": "# 新的檔\n".encode(), "開工/iplot.py": "# 開工\n".encode()})
    notes = bundled.sync(home, V, known(更新={"update.py": ["# 舊\n".encode()]}))
    assert not (home / "modules" / "開工").exists() and (kept / "helper.py").read_bytes() == "# 新的檔\n".encode()
    assert len(notes) == 1


def introduced(table: dict, **versions: str) -> dict:
    return {**table, ".introduced": versions}


def test_a_module_new_in_this_version_is_installed(home):
    """D159：0.8 新加的「整理」「導覽列」，從 0.7.x 更新上來的人本機沒有：這一版才加的就裝上。"""
    (home / ".bundled-version").write_text("0.7.1\n", encoding="utf-8")
    package(home, {"整理/iplot.py": b"# new\n", "整理/CHANGELOG.md": b"x"})
    notes = bundled.sync(home, V, introduced(known(), 整理=V))
    assert (home / "modules" / "整理" / "iplot.py").read_bytes() == b"# new\n"
    assert (home / "modules" / "整理" / "CHANGELOG.md").read_bytes() == b"x"
    assert "整理" in notes[0] and not list((home / "modules").glob(".*"))  # 暫存的資料夾不留下


def test_a_module_that_existed_before_and_was_removed_stays_removed(home):
    (home / ".bundled-version").write_text("0.7.1\n", encoding="utf-8")
    package(home, {"開工/iplot.py": b"# new\n"})
    assert bundled.sync(home, V, introduced(known(), 開工="0.5.0")) == []
    assert not (home / "modules" / "開工").exists()


def test_an_install_without_a_marker_only_gets_modules_new_in_exactly_this_version(home):
    package(home, {"整理/iplot.py": b"# new\n", "開工/iplot.py": b"# old\n"})
    bundled.sync(home, V, introduced(known(), 整理=V, 開工="0.5.0"))
    assert (home / "modules" / "整理").is_dir() and not (home / "modules" / "開工").exists()


def test_a_new_module_that_fails_to_install_leaves_nothing_and_tries_again(home, monkeypatch):
    (home / ".bundled-version").write_text("0.7.1\n", encoding="utf-8")
    package(home, {"整理/iplot.py": b"# new\n"})
    real = os.replace
    monkeypatch.setattr(bundled.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError(13, "no")))
    notes = bundled.sync(home, V, introduced(known(), 整理=V))
    assert not (home / "modules" / "整理").exists() and not list((home / "modules").glob(".*")) and notes
    assert (home / ".bundled-version").read_text(encoding="utf-8").strip() == "0.7.1"
    monkeypatch.setattr(bundled.os, "replace", real)
    bundled.sync(home, V, introduced(known(), 整理=V))
    assert (home / "modules" / "整理" / "iplot.py").is_file()


def test_a_symlinked_module_and_non_module_folders_are_skipped(home, tmp_path):
    real = tmp_path / "elsewhere"
    real.mkdir()
    (real / "iplot.py").write_text("x")
    try:
        (home / "modules" / "更新").symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("這個系統不能建符號連結")
    (home / "modules" / "開工").mkdir()  # 沒有 iplot.py：不是模組
    package(home, {"更新/iplot.py": "# 新\n".encode(), "開工/iplot.py": "# 新\n".encode()})
    assert bundled.sync(home, V, known()) == [] and (real / "iplot.py").read_text() == "x"


def test_a_fresh_download_has_no_package_and_just_remembers_the_version(home):
    module(home, "作業系統", {"mac.py": NEW})
    assert bundled.sync(home, V, known()) == []
    assert (home / bundled.MARKER).read_text().strip() == V


@pytest.mark.parametrize("made", ["other_version", "two_tops", "bad_zip"])
def test_a_package_that_is_not_this_cores_is_ignored(home, made):
    folder = module(home, "作業系統", {"mac.py": OLD})
    if made == "other_version":
        package(home, {"作業系統/mac.py": NEW}, version="0.7.9").rename(home / ".backup" / f"download-{V}.zip")
    elif made == "two_tops":
        path = package(home, {"作業系統/mac.py": NEW})
        with zipfile.ZipFile(path, "a") as z:
            z.writestr("別的資料夾/x", b"x")
    else:
        (home / ".backup").mkdir()
        (home / ".backup" / f"download-{V}.zip").write_bytes(b"not a zip")
    assert bundled.sync(home, V, known(作業系統={"mac.py": [OLD]})) == []
    assert (folder / "mac.py").read_bytes() == OLD


def test_paths_that_escape_the_module_folder_and_other_modules_are_ignored(home):
    module(home, "作業系統", {"mac.py": OLD})
    package(home, {"作業系統/mac.py": NEW}, extra={"作業系統/../../evil.py": b"x", "我的模組/iplot.py": b"x"})
    bundled.sync(home, V, known(作業系統={"mac.py": [OLD]}))
    assert not (home / "evil.py").exists() and not (home / "modules" / "evil.py").exists()
    assert not (home / "modules" / "我的模組").exists()


def test_a_write_that_fails_puts_the_module_back_and_tries_again_next_start(home, monkeypatch):
    folder = module(home, "作業系統", {"mac.py": OLD, "win.py": "# win 舊\n".encode()})
    package(home, {"作業系統/mac.py": NEW, "作業系統/win.py": "# win 新\n".encode()})
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise PermissionError(13, "denied")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    notes = bundled.sync(home, V, known(作業系統={"mac.py": [OLD], "win.py": ["# win 舊\n".encode()]}))
    assert (folder / "mac.py").read_bytes() == OLD and (folder / "win.py").read_bytes() == "# win 舊\n".encode()
    assert not list(folder.glob("*.iplot-new")) and "沒有權限" in notes[0] and "PermissionError" not in notes[0]
    assert not (home / bundled.MARKER).exists()
    monkeypatch.undo()
    bundled.sync(home, V, known(作業系統={"mac.py": [OLD], "win.py": ["# win 舊\n".encode()]}))
    assert (folder / "mac.py").read_bytes() == NEW and (home / bundled.MARKER).exists()


def test_an_up_to_date_module_is_left_alone_without_a_backup(home):
    folder = module(home, "作業系統", {"mac.py": NEW})
    package(home, {"作業系統/mac.py": NEW, "作業系統/iplot.py": b"def run(app):\n    pass\n"})
    assert bundled.sync(home, V, known()) == [] and not list((home / ".backup").glob("*-bundled-*"))
    assert (folder / "mac.py").read_bytes() == NEW


def test_start_up_never_fails_because_of_the_sync(home, monkeypatch):
    from ui import start as main

    monkeypatch.setattr(bundled, "sync", lambda *a: (_ for _ in ()).throw(RuntimeError("炸了")))
    assert main.bundle_news(home, V) is None
    assert "RuntimeError" in (home / "logs" / "iplot.log").read_text(encoding="utf-8")
    monkeypatch.setattr(bundled, "sync", lambda *a: ["一句", "兩句"])
    assert main.bundle_news(home, V) == "一句\n兩句"


# ── 發出去過的雜湊表 ──

def tool():
    spec = importlib.util.spec_from_file_location("bundled_hashes", ROOT / "tools" / "bundled_hashes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_hash_table_covers_every_bundled_file_in_this_tree():
    """隨附模組改了、發版之前要 python3 tools/bundled_hashes.py：沒重新產生，舊使用者的新檔會被當成「他改過的」而不換。"""
    git = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT, capture_output=True)
    if git.returncode:
        pytest.skip("不是 git 的工作目錄")
    have = __import__("json").loads(bundled.HASHES.read_text(encoding="utf-8"))
    missing = [f"{n}/{rel}" for (n, rel), d in tool().from_tree(tool().bundled_names()).items()
               if d not in have.get(n, {}).get(rel, [])]
    assert not missing, f"core/bundled_hashes.json 少了：{missing}；執行 python3 tools/bundled_hashes.py"


def test_the_hash_table_lists_exactly_the_bundled_modules():
    """D169：核心不寫隨附的名單，從雜湊表的鍵知道有哪些；表裡多一個、少一個都不行。"""
    have = json.loads(bundled.HASHES.read_text(encoding="utf-8"))
    assert {n for n in have if not n.startswith(".")} == set(tool().bundled_names()) == set(have[".introduced"])


def test_real_0_7_1_install_upgrades_to_this_trees_files_and_keeps_data(tmp_path):
    """真的歷史：把 v0.7.1 的隨附模組原樣解出來當舊安裝（加上資料檔），包是這個工作目錄的檔；
    用 core/bundled_hashes.json 真的那一份表。沒有 v0.7.1 的 tag（CI 是淺 clone）就跳過。"""
    if subprocess.run(["git", "rev-parse", "-q", "--verify", "v0.7.1"], cwd=ROOT, capture_output=True).returncode:
        pytest.skip("沒有 v0.7.1 的 tag")
    home = tmp_path / "iPLoT"
    (home / "modules").mkdir(parents=True)
    # Windows 的 git 會照 core.autocrlf 把 archive 裡的文字檔換成 CRLF；發出去的包是 LF 的，這裡也要 LF
    raw = subprocess.run(["git", "-c", "core.autocrlf=false", "archive", "v0.7.1", "modules"], cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
        # filter 是 3.10.12 才有的（CI 的 Windows 是 3.10.11）；包是自己的 git archive，沒有它也安全
        tar.extractall(home, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    data = {"行事曆/設定.json": '{"資料夾": "/x"}'.encode(), "互通/捷徑/a.txt": b"s", "作業系統/.history/h.py": b"h"}
    for rel, content in data.items():
        (home / "modules" / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / "modules" / rel).write_bytes(content)
    current = tool().tree_files(tool().bundled_names())
    files = {f"{n}/{rel}": data for (n, rel), data in current.items()}
    package(home, files, version=core.__version__)
    old_mac = (home / "modules" / "作業系統" / "mac.py").read_bytes()
    notes = bundled.sync(home, core.__version__)
    assert not any("你改過" in n for n in notes), notes
    assert (home / "modules" / "作業系統" / "mac.py").read_bytes() == current[("作業系統", "mac.py")]
    for rel, content in data.items():
        assert (home / "modules" / rel).read_bytes() == content
    if old_mac != current[("作業系統", "mac.py")]:
        assert any("作業系統" in n for n in notes)


def retired(table: dict, **modules: dict[str, list[bytes]]) -> dict:
    """雜湊表的 .retired（D171）：這一版拿掉的隨附模組，與它每一版發出去過的雜湊。"""
    table[".retired"] = {name: {"since": V, "files": known(x=files)["x"]} for name, files in modules.items()}
    return table


BUTTON = "def run(app):\n    app.log('舊按鈕')\n".encode()


def test_a_retired_module_nobody_changed_is_moved_to_the_backup(home):
    """0.8 升 1.0：「打開核心原始碼」由「核心」取代，沒改過的那一份移到 .backup/，不留一格打開舊種子的按鈕。"""
    folder = module(home, "舊按鈕", {"iplot.py": BUTTON, "LICENSE": b"MIT\n", ".history/1.json": b"{}"})
    notes = bundled.sync(home, V, retired(known(), 舊按鈕={"iplot.py": [b"# older\n", BUTTON], "LICENSE": [b"MIT\n"]}))
    assert not folder.exists()
    [backup] = (home / ".backup").glob(f"{V}-bundled-*")
    assert (backup / "舊按鈕" / "iplot.py").read_bytes() == BUTTON and (backup / "舊按鈕" / ".history" / "1.json").is_file()
    assert notes == [T["bundled_retired"].format(names="舊按鈕", backup=backup.relative_to(home).as_posix())]


@pytest.mark.parametrize("extra", [{"iplot.py": b"# \xe6\x94\xb9\xe9\x81\x8e\n"}, {"mine.py": b"x = 1\n"}])
def test_a_retired_module_that_was_changed_or_added_to_stays(home, extra):
    folder = module(home, "舊按鈕", {"iplot.py": BUTTON, **extra})
    assert bundled.sync(home, V, retired(known(), 舊按鈕={"iplot.py": [BUTTON]})) == []
    assert (folder / "iplot.py").is_file()


def test_a_retired_module_installed_from_outside_and_unchanged_is_moved_too(home):
    """工作坊裝的那份多一個收件機器人加的 LICENSE 和 .origin，不算改過（D172）。"""
    folder = module(home, "舊按鈕", {"iplot.py": BUTTON, "LICENSE": b"MIT\n", ".origin": b"url: x\n"})
    assert bundled.sync(home, V, retired(known(), 舊按鈕={"iplot.py": [BUTTON]}))
    assert not folder.exists()


def test_a_retired_module_that_is_already_gone_says_nothing(home):
    assert bundled.sync(home, V, retired(known(), 舊按鈕={"iplot.py": [BUTTON]})) == []


def test_the_real_table_retires_the_old_open_source_button_with_its_0_8_hashes():
    entry = json.loads(bundled.HASHES.read_text(encoding="utf-8"))[".retired"]["打開核心原始碼"]
    old = subprocess.run(["git", "show", "9e85f44:modules/打開核心原始碼/iplot.py"], cwd=ROOT, capture_output=True)
    if old.returncode:
        pytest.skip("git 歷史裡沒有 0.8 的「打開核心原始碼」（淺 clone）")
    assert entry["since"] == "1.0.0" and sha(old.stdout) in entry["files"]["iplot.py"]
