"""隨附模組「更新」（modules/更新）：只換核心的四樣東西、換之前備份、sha256 不符什麼都不動（規格 13.2、D69）。
全部在 tmp 裡的假 iPLoT 上做，來源用 file:// 網址，不連網。"""

import hashlib
import importlib.util
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import FakeApp

from core.runner import run_module
from core.scan import module_info

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules" / "更新"
OLD = {"core/__init__.py": '__version__ = "0.4.9"\n', "core/x.py": "old core\n", "ui/a.js": "old ui\n",
       "main.py": "old main\n", "requirements/r.txt": "old==1\n"}
NEW = {"core/__init__.py": '__version__ = "9.9.9"\n', "core/y.py": "new core\n", "ui/a.js": "new ui\n",
       "main.py": "new main\n", "requirements/r.txt": "new==2\n"}
MINE = {"config.py": "ROOTS = ['modules']\n", "custom.css": ":root{}\n", "modules/m/iplot.py": "print('mine')\n",
        "modules/m/.history/old.py": "print('older')\n", "logs/l": "log\n", "lib/w.py": "lib\n", "lib/.installed": "abc"}


@pytest.fixture(scope="module")
def update():
    spec = importlib.util.spec_from_file_location("iplot_update", MODULE / "update.py")
    module = importlib.util.module_from_spec(spec)
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    return module


def write(base, files):
    for name, text in files.items():
        (base / name).parent.mkdir(parents=True, exist_ok=True)
        (base / name).write_text(text, encoding="utf-8")


def tree(base):
    """base 底下每個檔案的（相對路徑 → 內容）。"""
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "我的 iPLoT"
    write(h, {**OLD, **MINE})
    return h


@pytest.fixture
def source(tmp_path):
    """放更新檔的地方：zip（最上層 iPLoT-v9.9.9/，另外夾帶 README 與 modules/，那些不該被套用）與 update.json。"""
    src = tmp_path / "發佈"
    src.mkdir()
    z = src / "iPLoT-v9.9.9.zip"
    with zipfile.ZipFile(z, "w") as f:
        for name, text in {**NEW, "README.md": "readme\n", "modules/m/iplot.py": "print('theirs')\n",
                           "config.py": "ROOTS = []\n"}.items():
            f.writestr(f"iPLoT-v9.9.9/{name}", text)
    info = {"version": "9.9.9", "zip_url": z.as_uri(), "sha256": hashlib.sha256(z.read_bytes()).hexdigest(),
            "notes": "這一版改了什麼"}
    (src / "update.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return src


def run(app):
    """真的經過 runner 執行 modules/更新/iplot.py（工作目錄、sys.path 都跟面板上按下去一樣）。"""
    info = module_info(MODULE, MODULE.parent, "here")
    result = run_module(info, app)
    assert result.error is None, result.error
    return result


def test_newer(update):
    assert update.newer("0.4.0", "0.5.0") and update.newer("0.9.9", "0.10.0") and update.newer("0.5", "0.5.1")
    assert not update.newer("0.5.0", "0.5.0") and not update.newer("0.5.0", "0.4.9")
    assert not update.newer("0.5.0", "x") and not update.newer("0.5.0", None)


def test_fetch_json_from_file_url_with_spaces_and_chinese(update, source):
    assert update.fetch_json((source / "update.json").as_uri())["version"] == "9.9.9"
    raw = "file://" + str(source / "update.json")  # 沒有轉成 %XX 的寫法也要開得了
    assert update.fetch_json(raw)["notes"] == "這一版改了什麼"


def test_download_verifies_sha(update, source, tmp_path):
    z = source / "iPLoT-v9.9.9.zip"
    good = hashlib.sha256(z.read_bytes()).hexdigest()
    dest = tmp_path / "下載" / "x.zip"
    assert update.download(z.as_uri(), dest, good) == dest and dest.read_bytes() == z.read_bytes()
    with pytest.raises(ValueError):
        update.download(z.as_uri(), dest, "0" * 64)
    assert not dest.exists(), "對不上就刪掉，不留一個不可信的檔"


def test_backup_has_old_parts(update, home):
    saved = update.backup(home, "0.4.9")
    assert saved.parent == home / ".backup" and saved.name.startswith("0.4.9-")
    assert tree(saved) == {k: v.encode() for k, v in OLD.items()}
    assert update.backup(home, "0.4.9") != saved, "同一秒內再備份一次也不會撞名"


def test_apply_replaces_only_parts_and_keeps_rest(update, home, source, tmp_path):
    """不變量：四樣換成 zip 裡的；config.py、custom.css、modules/（含 .history/）、logs/、lib/ 逐位元組不變；
    iPLoT 資料夾以外沒有任何寫入；.update-tmp/ 做完不存在。"""
    outside = {k: v for k, v in tree(tmp_path).items() if not k.startswith(home.name + "/")}
    update.apply(home, source / "iPLoT-v9.9.9.zip")
    after = tree(home)
    assert {k: v for k, v in after.items() if k in NEW} == {k: v.encode() for k, v in NEW.items()}
    assert "core/x.py" not in after, "舊的 core/ 整個換掉，不是疊上去"
    assert {k: after[k] for k in MINE} == {k: v.encode() for k, v in MINE.items()}
    assert set(after) == set(NEW) | set(MINE), "zip 裡夾帶的 README、modules/、config.py 不套用；沒有 .new／.old 殘留"
    assert not (home / ".update-tmp").exists()
    assert {k: v for k, v in tree(tmp_path).items() if not k.startswith(home.name + "/")} == outside


def test_apply_refuses_a_zip_without_all_four_parts(update, home, tmp_path):
    """包不完整（例如少了 ui/）：一樣都不換，不會留下半套。"""
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("iPLoT-v9.9.9/core/__init__.py", "x")
        f.writestr("iPLoT-v9.9.9/main.py", "x")
    before = tree(home)
    with pytest.raises(ValueError):
        update.apply(home, z)
    assert tree(home) == before


def test_apply_refuses_a_zip_with_two_top_folders(update, home, tmp_path):
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as f:
        for top in ("a", "b"):
            for name in NEW:
                f.writestr(f"{top}/{name}", "x")
    before = tree(home)
    with pytest.raises(ValueError):
        update.apply(home, z)
    assert tree(home) == before


def test_run_without_url_logs_hint(home):
    app = FakeApp(home)
    run(app)
    assert len(app.logs) == 1 and "UPDATE_URL" in app.logs[0] and "config.py" in app.logs[0]
    assert tree(home) == {k: v.encode() for k, v in {**OLD, **MINE}.items()}


def test_run_updates_backs_up_and_says_restart(home, source):
    app = FakeApp(home, update_url=(source / "update.json").as_uri())
    run(app)
    assert len(app.confirms) == 1 and "9.9.9" in app.confirms[0] and "這一版改了什麼" in app.confirms[0]
    after = tree(home)
    assert after["core/__init__.py"] == NEW["core/__init__.py"].encode() and after["config.py"] == MINE["config.py"].encode()
    [saved] = [p for p in (home / ".backup").iterdir() if p.is_dir()]
    assert saved.name.startswith("0.4.9-") and (saved / "core" / "x.py").read_text() == "old core\n"
    assert "9.9.9" in app.logs[-1] and "重新啟動" in app.logs[-1]


def test_run_when_already_latest(home, source):
    app = FakeApp(home, version="9.9.9", update_url=(source / "update.json").as_uri())
    (home / "core" / "__init__.py").write_text('__version__ = "9.9.9"\n', encoding="utf-8")
    run(app)
    assert app.confirms == [] and "9.9.9" in app.logs[-1] and not (home / ".backup").exists()


def test_run_cancelled_at_the_confirmation_touches_nothing(home, source):
    app = FakeApp(home, update_url=(source / "update.json").as_uri())
    app.answers = [False]
    before = tree(home)
    run(app)
    assert tree(home) == before and len(app.logs) == 1


def test_sha_mismatch_touches_nothing(home, source):
    """sha256 不符：一句話，四樣都不動，下載的檔刪掉，也不備份。"""
    info = json.loads((source / "update.json").read_text(encoding="utf-8"))
    info["sha256"] = "0" * 64
    (source / "update.json").write_text(json.dumps(info), encoding="utf-8")
    app = FakeApp(home, update_url=(source / "update.json").as_uri())
    before = tree(home)
    run(app)
    assert tree(home) == before and len(app.logs) == 1 and "sha256" in app.logs[0]


def test_update_twice_second_is_noop(home, source):
    """計畫的審查焦點 3：還沒重新啟動又按一次「更新」。app.version 還是舊的（程序沒換），
    但磁碟上已經是新版：不再下載、不再備份、不再換一次，只提醒重新啟動。"""
    app = FakeApp(home, update_url=(source / "update.json").as_uri())
    run(app)
    backups = sorted(p.name for p in (home / ".backup").iterdir())
    after = tree(home)
    run(app)
    assert sorted(p.name for p in (home / ".backup").iterdir()) == backups and tree(home) == after
    assert len(app.confirms) == 1 and "重新啟動" in app.logs[-1]


@pytest.mark.parametrize("broken, word", [
    ("not json", "update.json"), ('{"version": "9.9.9"}', "zip_url"), ('["a list"]', "update.json")])
def test_bad_update_json_is_one_plain_sentence(home, source, broken, word):
    (source / "update.json").write_text(broken, encoding="utf-8")
    app = FakeApp(home, update_url=(source / "update.json").as_uri())
    before = tree(home)
    run(app)
    assert tree(home) == before and len(app.logs) == 1 and word in app.logs[0]


def test_unreachable_source_is_one_plain_sentence(home, tmp_path):
    app = FakeApp(home, update_url=(tmp_path / "沒有這個檔.json").as_uri())
    run(app)
    assert len(app.logs) == 1 and "Traceback" not in app.logs[0]


def test_not_a_zip_is_one_plain_sentence(home, source):
    z = source / "iPLoT-v9.9.9.zip"
    z.write_bytes(b"this is not a zip")
    info = json.loads((source / "update.json").read_text(encoding="utf-8"))
    info["sha256"] = hashlib.sha256(z.read_bytes()).hexdigest()
    (source / "update.json").write_text(json.dumps(info), encoding="utf-8")
    app = FakeApp(home, update_url=(source / "update.json").as_uri())
    run(app)
    assert tree(home)["core/x.py"] == b"old core\n" and "zip" in app.logs[-1]
    shutil.rmtree(home / ".backup", ignore_errors=True)
