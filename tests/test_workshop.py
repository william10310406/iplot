"""隨附模組「工作坊」（modules/工作坊）：從索引安裝、更新模組；只寫進自己裝的那個資料夾，覆蓋前整個存進 .history/
（規格 13.3、D70）。全部在 tmp 裡做，來源用 file:// 網址，不連網。"""

import hashlib
import importlib.util
import json
import os
import stat
import sys
import zipfile
from pathlib import Path

import pytest
from conftest import FakeApp, make_module

from core.runner import run_module
from core.scan import module_info

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modules" / "工作坊"
V1 = {"iplot.py": '"""把桌面上的截圖收起來。"""\nICON = "🧹"\ndef run(app):\n    app.log("v1")\n', "helper.py": "x = 1\n"}
V2 = {"iplot.py": '"""把桌面上的截圖收起來。"""\nICON = "🧹"\ndef run(app):\n    app.log("v2")\n', "helper.py": "x = 2\n",
      "data/new.txt": "new\n"}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    old, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    return module


@pytest.fixture(scope="module")
def workshop():
    return load(MODULE / "workshop.py", "iplot_workshop")


def tree(base):
    return {p.relative_to(base).as_posix(): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


def pack(src, name, files, top=None):
    """做一個模組的 zip（最上層 top/，預設就是 name/），回索引裡的那一筆。"""
    src.mkdir(parents=True, exist_ok=True)
    z = src / f"{name}.zip"
    with zipfile.ZipFile(z, "w") as f:
        for rel, text in files.items():
            f.writestr(f"{top or name}/{rel}", text)
    return {"name": name, "version": "1.0.0", "zip_url": z.as_uri(), "sha256": hashlib.sha256(z.read_bytes()).hexdigest(),
            "description": "把桌面上的截圖收起來。", "icon": "🧹"}


@pytest.fixture
def mods(tmp_path):
    d = tmp_path / "我的 iPLoT" / "modules"
    d.mkdir(parents=True)
    make_module(d, "other", "print('別人的')\n")
    (d / "other" / ".history").mkdir()
    (d / "other" / ".history" / "old.py").write_text("old", encoding="utf-8")
    return d


@pytest.fixture
def src(tmp_path):
    return tmp_path / "發佈" / "模組"


@pytest.fixture
def entry(src):
    return pack(src, "整理桌面", V1)


def test_read_index(workshop, src, entry):
    index = src.parent / "index.json"
    index.write_text(json.dumps({"modules": [entry]}, ensure_ascii=False), encoding="utf-8")
    assert workshop.read_index(index.as_uri()) == [entry]
    for broken in ('{"mods": []}', "[]", '{"modules": [{"name": "x"}]}', '{"modules": "x"}'):
        index.write_text(broken, encoding="utf-8")
        with pytest.raises(ValueError):
            workshop.read_index(index.as_uri())


def test_digest_covers_the_listed_files_only(workshop, mods):
    """摘要只算當初裝進來的那些檔：改一個字、刪掉一個都會變；清單以外的檔（各台電腦自己的東西、模組自己存的資料）不算。"""
    folder = make_module(mods, "A", "x = 1\n")
    (folder / "helper.py").write_text("h", encoding="utf-8")
    listed = ["helper.py", "iplot.py"]
    d = workshop.digest(folder, listed)
    assert workshop.digest(folder, list(reversed(listed))) == d, "順序不影響"
    for junk in (".history/a.py", "__pycache__/a.pyc", ".origin", ".unconfirmed", ".DS_Store", "extra.txt"):
        (folder / junk).parent.mkdir(exist_ok=True)
        (folder / junk).write_text("junk", encoding="utf-8")
    assert workshop.digest(folder, listed) == d
    (folder / "iplot.py").write_text("x = 2\n", encoding="utf-8")
    assert workshop.digest(folder, listed) != d
    (folder / "iplot.py").write_text("x = 1\n", encoding="utf-8")
    (folder / "helper.py").unlink()
    assert workshop.digest(folder, listed) != d, "少了一個也算改過"


def test_installed_has_unconfirmed_and_state_installed(workshop, mods, entry):
    assert workshop.state(entry, mods) == "absent"
    assert workshop.install(entry, mods) == "installed"
    folder = mods / "整理桌面"
    assert {k: v for k, v in tree(folder).items() if not k.startswith(".")} == {k: v.encode() for k, v in V1.items()}
    assert (folder / ".unconfirmed").exists() and (folder / ".unconfirmed").read_bytes() == b""
    origin = workshop.read_origin(folder)
    assert (origin["url"], origin["version"], origin["sha256"]) == (entry["zip_url"], "1.0.0", entry["sha256"])
    assert origin["digest"] == workshop.digest(folder, ["helper.py", "iplot.py"]) and origin["installed"]
    assert workshop.state(entry, mods) == "installed"


def test_install_writes_only_its_folder(workshop, mods, entry, tmp_path):
    """不變量：只寫進 modules/<name>/；modules/ 裡其他資料夾逐位元組不變；暫存做完不存在；modules/ 以外沒有寫入。"""
    before = {k: v for k, v in tree(tmp_path).items() if "/整理桌面/" not in k}
    workshop.install(entry, mods)
    assert {k: v for k, v in tree(tmp_path).items() if "/整理桌面/" not in k} == before
    assert not (mods / ".workshop-tmp").exists()


def test_state_five_cases(workshop, mods, entry, src):
    assert workshop.state(entry, mods) == "absent"
    workshop.install(entry, mods)
    assert workshop.state(entry, mods) == "installed"
    newer = {**pack(src, "整理桌面", V2), "version": "1.1.0"}
    assert workshop.state(newer, mods) == "update"
    assert workshop.state({**entry, "version": "0.9.0"}, mods) == "installed", "索引比較舊：不叫人降版"
    (mods / "整理桌面" / "helper.py").write_text("x = 99\n", encoding="utf-8")
    assert workshop.state(entry, mods) == "modified" and workshop.state(newer, mods) == "modified"
    make_module(mods, "自己做的")
    assert workshop.state({**entry, "name": "自己做的"}, mods) == "unknown"


def test_edit_makes_modified(workshop, mods, entry):
    workshop.install(entry, mods)
    (mods / "整理桌面" / "iplot.py").write_text("print('我改的')\n", encoding="utf-8")
    assert workshop.state(entry, mods) == "modified"


def test_running_it_does_not_make_it_modified(workshop, mods, entry):
    """確認過（.unconfirmed 拿掉）、跑過（.history/、__pycache__ 出現）都不算改過。"""
    workshop.install(entry, mods)
    folder = mods / "整理桌面"
    (folder / ".unconfirmed").unlink()
    (folder / ".history").mkdir()
    (folder / ".history" / "2026-10-05_120000.py").write_text("snap", encoding="utf-8")
    assert workshop.state(entry, mods) == "installed"


def test_broken_origin_counts_as_modified(workshop, mods, entry):
    """計畫的審查焦點 5：.origin 被手動改壞（亂碼、缺行）算「已修改」，不是 traceback。"""
    workshop.install(entry, mods)
    origin = mods / "整理桌面" / ".origin"
    good = origin.read_text(encoding="utf-8")
    for broken in ("garbage", "", good.replace("digest: ", "digest "), "\n".join(good.splitlines()[:2]), "\xff\xfe"):
        origin.write_bytes(broken.encode("utf-8", "surrogateescape") if broken != "\xff\xfe" else b"\xff\xfe\x00")
        assert workshop.read_origin(mods / "整理桌面") == {}
        assert workshop.state(entry, mods) == "modified"


def test_bundled_without_origin_is_unknown(workshop, mods, entry):
    """隨附模組、使用者自己建的同名模組：資料夾在、沒有 .origin。"""
    make_module(mods, "整理桌面", "print('我自己的')\n")
    assert workshop.read_origin(mods / "整理桌面") is None and workshop.state(entry, mods) == "unknown"


def test_install_snapshots_existing_folder(workshop, mods, entry, src):
    """覆蓋前整個舊資料夾存成 .history/…-folder.zip（不含 .history/ 自己）；包裡沒有的舊檔案留著。"""
    folder = make_module(mods, "整理桌面", "print('我自己的')\n")
    (folder / "mine.txt").write_text("我的資料", encoding="utf-8")
    (folder / ".history").mkdir()
    (folder / ".history" / "2026-10-05_120000.py").write_text("snap", encoding="utf-8")
    assert workshop.install(entry, mods) == "installed"
    [saved] = list((folder / ".history").glob("*-folder.zip"))
    with zipfile.ZipFile(saved) as z:
        assert sorted(z.namelist()) == ["iplot.py", "mine.txt"]
        assert z.read("iplot.py") == b"print('\xe6\x88\x91\xe8\x87\xaa\xe5\xb7\xb1\xe7\x9a\x84')\n"
    assert (folder / "iplot.py").read_text(encoding="utf-8") == V1["iplot.py"]
    assert (folder / "mine.txt").read_text(encoding="utf-8") == "我的資料"
    assert (folder / ".history" / "2026-10-05_120000.py").exists()
    assert workshop.install({**pack(src, "整理桌面", V2), "version": "1.1.0"}, mods) == "installed"
    assert len(list((folder / ".history").glob("*-folder.zip"))) == 2, "同一秒內再覆蓋一次，快照也不會撞名"


def test_install_rejects_bad_sha(workshop, mods, entry):
    with pytest.raises(ValueError):
        workshop.install({**entry, "sha256": "0" * 64}, mods)
    assert not (mods / "整理桌面").exists() and not (mods / ".workshop-tmp").exists()


def test_install_rejects_wrong_top_folder(workshop, mods, src):
    """計畫的審查焦點 4：zip 的最上層不是 <name>/（打包錯）：不解壓、資料夾不變。"""
    folder = make_module(mods, "整理桌面", "print('我自己的')\n")
    before = tree(mods)
    for bad in (pack(src, "整理桌面", V1, top="別的名字"), pack(src, "整理桌面", {"../逃出去.txt": "x", "iplot.py": "x"}),
                pack(src, "整理桌面", {"readme.txt": "沒有 iplot.py"})):
        with pytest.raises(ValueError):
            workshop.install(bad, mods)
        assert tree(mods) == before and not (folder / ".origin").exists()
    assert not (mods.parent / "逃出去.txt").exists()


@pytest.mark.parametrize("name", ["../外面", "a/b", "a\\b", ".藏起來", "", ".", ".."])
def test_install_rejects_names_that_are_not_a_plain_folder_name(workshop, mods, entry, name):
    """索引是從網路來的：名稱不是單純的資料夾名（想寫到 modules/ 外面）就不裝。"""
    before = tree(mods.parent)
    with pytest.raises(ValueError):
        workshop.install({**entry, "name": name}, mods)
    assert tree(mods.parent) == before


def test_package_cannot_bring_its_own_local_files(workshop, mods, src):
    """包裡夾帶 .history/、.origin、.unconfirmed 也不會被寫進去：那些是這台電腦自己的。"""
    e = pack(src, "整理桌面", {**V1, ".history/2026-10-05_120000.py": "偽造的上一版", ".origin": "digest: x", "__pycache__/a.pyc": "x"})
    workshop.install(e, mods)
    folder = mods / "整理桌面"
    assert not (folder / ".history").exists() and not (folder / "__pycache__").exists()
    assert workshop.read_origin(folder)["sha256"] == e["sha256"]


def test_render_escapes_what_came_from_the_index(workshop, mods, entry):
    """索引的內容不可信：名稱、說明、版本、圖示一律當文字，不當 HTML。"""
    evil = {**entry, "name": "<img src=x onerror=alert(1)>", "description": "</td><script>alert(2)</script>",
            "version": '"><b>', "icon": "<i>"}
    html = workshop.render([entry, evil], mods, "<table>{rows}</table>")
    for raw in (evil["name"], evil["description"], evil["version"], evil["icon"], "<script>", "<img"):
        assert raw not in html, raw
    assert "整理桌面" in html and workshop.LABELS["absent"] in html and "&lt;script&gt;" in html
    assert html.startswith("<table>") and "{rows}" not in html


def test_render_shows_state_and_the_right_button(workshop, mods, entry):
    assert ">安裝<" in workshop.render([entry], mods, "{rows}")
    workshop.install(entry, mods)
    html = workshop.render([entry], mods, "{rows}")
    assert workshop.LABELS["installed"] in html and "<button" not in html, "已安裝：沒有按鈕"
    assert ">更新<" in workshop.render([{**entry, "version": "2.0.0"}], mods, "{rows}")
    (mods / "整理桌面" / "helper.py").write_text("改過", encoding="utf-8")
    assert ">覆蓋<" in workshop.render([entry], mods, "{rows}")


def test_api_install_returns_the_new_label(workshop, mods, entry, tmp_path):
    api = workshop.Api(FakeApp(tmp_path), [entry], mods)
    assert api.install("整理桌面") == workshop.LABELS["installed"]
    assert api.install("沒有這個").startswith("無法安裝：")


def test_api_install_asks_before_overwrite(workshop, mods, entry, tmp_path):
    """已修改、版本未知的要先確認才覆蓋。確認是在工作坊那一頁做的（按鈕按第二次）；沒帶「確認過」就不動。"""
    folder = make_module(mods, "整理桌面", "print('我自己的')\n")
    api = workshop.Api(FakeApp(tmp_path), [entry], mods)
    before = tree(mods)
    assert api.install("整理桌面") == workshop.CONFIRM and tree(mods) == before
    assert api.install("整理桌面", True) == workshop.LABELS["installed"]
    assert list((folder / ".history").glob("*-folder.zip"))
    (folder / "helper.py").write_text("改過", encoding="utf-8")
    assert api.install("整理桌面") == workshop.CONFIRM


def test_api_install_error_is_a_sentence(workshop, mods, entry, tmp_path):
    api = workshop.Api(FakeApp(tmp_path), [{**entry, "sha256": "0" * 64}, {**entry, "name": "連不上", "zip_url": "file:///no/such.zip"}], mods)
    for name in ("整理桌面", "連不上"):
        answer = api.install(name)
        assert answer.startswith("無法安裝：") and "Traceback" not in answer
    assert not (mods / "整理桌面").exists() and not (mods / "連不上").exists()


def test_api_exposes_only_install(workshop, mods, entry, tmp_path):
    """pywebview 會把 api 的公開屬性一路攤開給那一頁的 JS：只露出 install。"""
    api = workshop.Api(FakeApp(tmp_path), [entry], mods)
    assert [n for n in dir(api) if not n.startswith("_")] == ["install"]


def test_publish_and_workshop_agree(workshop, mods, tmp_path):
    """tools/publish.py 打的包，工作坊裝得進去、狀態是已安裝。"""
    publish = load(ROOT / "tools" / "publish.py", "iplot_publish_for_workshop")
    folder = make_module(tmp_path / "來源", "整理桌面", V1["iplot.py"])
    (folder / ".history").mkdir()
    (folder / ".history" / "x.py").write_text("x", encoding="utf-8")
    packed = publish.pack_module(folder, tmp_path / "out")
    e = {"name": "整理桌面", "version": "1.0.0", "zip_url": packed.as_uri(), "sha256": publish.sha256_of(packed)}
    assert workshop.install(e, mods) == "installed" and not (mods / "整理桌面" / ".history").exists()
    assert publish.SKIP == workshop.SKIP


# iplot.py：經過 runner 真的執行

def run(app):
    result = run_module(module_info(MODULE, MODULE.parent, "here"), app)
    assert result.error is None, result.error
    return result


def test_run_without_url_logs_hint(tmp_path):
    app = FakeApp(tmp_path)
    run(app)
    assert len(app.logs) == 1 and "WORKSHOP_URL" in app.logs[0] and app.pages == [] and app.rescans == 0


def test_run_opens_the_page_then_rescans(mods, src, entry):
    index = src.parent / "index.json"
    index.write_text(json.dumps({"modules": [entry]}, ensure_ascii=False), encoding="utf-8")
    app = FakeApp(mods.parent, workshop_url=index.as_uri())
    run(app)
    [(title, html, api)] = app.pages
    assert title == "工作坊" and "整理桌面" in html and "{rows}" not in html and callable(api.install)
    assert app.rescans == 1
    assert "http://" not in html and "https://" not in html, "頁面零外部資源"


def test_run_with_unreadable_index_is_one_sentence(mods, tmp_path):
    for url in ((tmp_path / "沒有.json").as_uri(), None):
        if url is None:
            bad = tmp_path / "bad.json"
            bad.write_text("not json", encoding="utf-8")
            url = bad.as_uri()
        app = FakeApp(mods.parent, workshop_url=url)
        run(app)
        assert len(app.logs) == 1 and app.pages == [] and "Traceback" not in app.logs[0]


# 最終審查的修正

def test_https_open_brings_a_trust_store(workshop, monkeypatch):
    import ssl
    seen = {}
    monkeypatch.setattr(workshop.urllib.request, "urlopen", lambda url, timeout=None, context=None: seen.update(context=context))
    workshop._open("https://raw.githubusercontent.com/someone/iplot/main/index.json", 5)
    assert isinstance(seen["context"], ssl.SSLContext) and seen["context"].verify_mode == ssl.CERT_REQUIRED


def test_case_variants_of_local_names_cannot_switch_off_the_question(workshop, mods, src):
    """macOS 的檔案系統不分大小寫：包裡的「.Origin/x」跟 .origin 是同一個名字。這類成員一律不裝，
    安裝照常完成，.unconfirmed 一定在（否則下載來的程式不問就能跑）。"""
    e = pack(src, "整理桌面", {**V1, ".Origin/x": "x", ".UNCONFIRMED/y": "y", ".History/2026-10-05_120000.py": "z",
                              "sub/.Unconfirmed": "", "__PyCache__/a.pyc": "x", ".ds_store": "x"})
    assert workshop.install(e, mods) == "installed"
    folder = mods / "整理桌面"
    assert (folder / ".unconfirmed").is_file() and (folder / ".origin").is_file()
    assert sorted(p.name for p in folder.iterdir()) == [".origin", ".unconfirmed", "helper.py", "iplot.py"]


def test_nested_modules_are_asked_about_too(workshop, mods, src, tmp_path):
    """包裡帶著下一層模組：每一個有 iplot.py 的資料夾都放 .unconfirmed，進到下一層執行也會先問。"""
    from conftest import FakeView

    from core.core import Core
    from core.types import DEFAULT_CONFIG
    e = pack(src, "工具箱", {"iplot.py": "x = 1\n", "子工具/iplot.py": "open('ran.txt', 'w').close()\n", "子工具/更深/iplot.py": "y = 1\n",
                           "資料/a.txt": "a"})
    workshop.install(e, mods)
    folder = mods / "工具箱"
    assert all((folder / d / ".unconfirmed").is_file() for d in ("", "子工具", "子工具/更深"))
    assert not (folder / "資料" / ".unconfirmed").exists()
    assert workshop.state(e, mods) == "installed"
    view = FakeView()
    view.answers = [False]
    core = Core(mods.parent, DEFAULT_CONFIG, view)
    core.rescan()
    core.enter(next(m for m in core.all_modules() if m.name == "工具箱"))
    core.press(next(m for m in core.all_modules() if m.name == "子工具"))
    assert len(view.confirmed) == 1 and not (folder / "子工具" / "ran.txt").exists()
    (folder / ".unconfirmed").unlink()
    (folder / "子工具" / ".unconfirmed").unlink()
    workshop.install(e, mods)
    assert (folder / ".unconfirmed").is_file() and (folder / "子工具" / ".unconfirmed").is_file(), "覆蓋之後重新要問"


def test_module_folders_already_on_disk_are_asked_about_too(workshop, mods, src):
    """獨立審查 C1：下一層的模組資料夾已經在磁碟上（上一版裝的、確認過），新的包只帶它旁邊的 helper.py、不帶它的 iplot.py。
    那個資料夾一樣要放 .unconfirmed：不然執行它，就不經確認跑了新下載的 helper.py。"""
    from conftest import FakeView

    from core.core import Core
    from core.types import DEFAULT_CONFIG
    v1 = {"iplot.py": "x = 1\n", "子工具/iplot.py": "import helper\nhelper.go()\n",
          "子工具/helper.py": "def go():\n    pass\n"}
    workshop.install(pack(src / "v1", "工具箱", v1), mods)
    folder = mods / "工具箱"
    for marker in folder.rglob(".unconfirmed"):  # 使用者兩個都確認過了
        marker.unlink()
    v2 = {"iplot.py": "x = 2\n", "子工具/helper.py": "def go():\n    open('ran.txt', 'w').close()\n"}
    e2 = {**pack(src / "v2", "工具箱", v2), "version": "2.0.0"}
    assert workshop.state(e2, mods) == "update"
    workshop.install(e2, mods)
    assert (folder / "子工具" / ".unconfirmed").is_file()
    view = FakeView()
    view.answers = [False]
    core = Core(mods.parent, DEFAULT_CONFIG, view)
    core.rescan()
    core.enter(next(m for m in core.all_modules() if m.name == "工具箱"))
    core.press(next(m for m in core.all_modules() if m.name == "子工具"))
    assert len(view.confirmed) == 1 and not (folder / "子工具" / "ran.txt").exists()


def test_failed_install_puts_the_old_folder_back(workshop, mods, src, monkeypatch):
    """複製到一半出錯：模組資料夾回到安裝前的樣子（靠覆蓋前存的那份快照），不會留下一半新一半舊、又沒有 .unconfirmed。"""
    folder = make_module(mods, "整理桌面", "print('我自己的')\n")
    (folder / "helper.py").write_text("mine\n", encoding="utf-8")
    before = {k: v for k, v in tree(mods).items() if "/.history/" not in k}
    real, calls = workshop.shutil.copyfile, []

    def copyfile(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError(28, "模擬：磁碟滿了")
        return real(source, target)

    monkeypatch.setattr(workshop.shutil, "copyfile", copyfile)
    with pytest.raises(OSError):
        workshop.install(pack(src, "整理桌面", V2), mods)
    assert {k: v for k, v in tree(mods).items() if "/.history/" not in k} == before
    assert not (mods / ".workshop-tmp").exists()


POSIX_USER = pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="靠 POSIX 的唯讀權限讓寫入失敗")


@POSIX_USER
def test_rollback_goes_on_past_a_read_only_folder(workshop, mods, src, tmp_path):
    """獨立審查 I3：讓安裝失敗的原因（唯讀的子資料夾）通常也讓放回原樣時的刪除失敗。放回不能在第一個錯就停下來
    （以前會連包根本沒碰的 a.py 都刪掉）：能刪的刪、從快照補回來，比對過一樣才說「已從快照放回」。"""
    folder = make_module(mods, "整理桌面", "print('我自己的')\n")
    (folder / "a.py").write_text("a\n", encoding="utf-8")
    (folder / "資料").mkdir()
    (folder / "資料" / "old.txt").write_text("old\n", encoding="utf-8")
    before = {k: v for k, v in tree(folder).items() if not k.startswith(".history/")}
    (folder / "資料").chmod(0o555)
    try:
        api = workshop.Api(FakeApp(tmp_path), [pack(src, "整理桌面", {"iplot.py": "x = 2\n", "資料/new.txt": "new\n"})], mods)
        answer = api.install("整理桌面", True)
        assert answer.startswith("無法安裝：") and "沒有裝成，已從快照放回" in answer, answer
        assert {k: v for k, v in tree(folder).items() if not k.startswith(".history/")} == before
    finally:
        (folder / "資料").chmod(0o755)


@pytest.mark.skipif(not hasattr(os, "chflags") or not hasattr(stat, "UF_IMMUTABLE"), reason="macOS／BSD 的鎖定旗標")
def test_rollback_with_a_locked_file(workshop, mods, src):
    """在 Finder 裡「鎖定」的檔（chflags uchg）：包要蓋它會失敗，放回時也刪不掉它。它本來就是舊的，其他的放回去就是原樣。"""
    folder = make_module(mods, "整理桌面", "print('我自己的')\n")
    (folder / "notes.txt").write_text("我的筆記\n", encoding="utf-8")
    before = {k: v for k, v in tree(folder).items() if not k.startswith(".history/")}
    os.chflags(folder / "notes.txt", stat.UF_IMMUTABLE)
    try:
        with pytest.raises(OSError) as raised:
            workshop.install(pack(src, "整理桌面", {"iplot.py": "x = 2\n", "notes.txt": "包裡的\n"}), mods)
        assert "沒有裝成，已從快照放回" in str(raised.value)
        assert {k: v for k, v in tree(folder).items() if not k.startswith(".history/")} == before
    finally:
        os.chflags(folder / "notes.txt", 0)


@POSIX_USER
def test_when_the_rollback_cannot_finish_the_sentence_says_where_the_snapshot_is(workshop, mods, src, monkeypatch):
    """快照讀不回來（權限）：不能說放回了。2026-10-06（R2）起快照讀不到就一樣都不刪，那一句說資料夾是新舊混合、在哪裡；
    「放回時出錯，快照在 <路徑>」留給快照讀得到、卻有檔解不回去的時候（下一個測試）。"""
    folder = make_module(mods, "整理桌面", "print('我自己的')\n")
    real, calls = workshop.shutil.copyfile, []

    def copyfile(source, target):
        calls.append(target)
        if len(calls) == 2:
            for saved in (folder / ".history").glob("*-folder.zip"):
                saved.chmod(0)
            raise OSError(28, "模擬：磁碟滿了")
        return real(source, target)

    monkeypatch.setattr(workshop.shutil, "copyfile", copyfile)
    try:
        with pytest.raises(OSError) as raised:
            workshop.install(pack(src, "整理桌面", V2), mods)
        assert "已從快照放回" not in str(raised.value)
        assert f"快照讀不到、沒有放回，資料夾現在是新舊混合：{folder}" in str(raised.value)
    finally:
        for saved in (folder / ".history").glob("*-folder.zip"):
            saved.chmod(0o644)


def test_rollback_that_cannot_write_a_file_back_does_not_say_it_put_it_back(workshop, mods, src, monkeypatch):
    """快照打得開、但有一個檔解不回去（例如磁碟還是滿的）：要靠逐檔比對抓到，不能說「已從快照放回」；
    要說放回時出錯、快照在哪裡，並替留下來的模組資料夾放 .unconfirmed。（第二輪審查 R1：以前沒有測試走到這條路，
    把比對拿掉、一律當成放回了，其他放回原樣的測試照樣通過。）"""
    folder = make_module(mods, "記帳", "print('v1')\n")
    (folder / "帳本.csv").write_text("我的帳\n", encoding="utf-8")
    real_copy, calls = workshop.shutil.copyfile, []

    def copyfile(source, target):
        calls.append(target)
        if len(calls) == 2:
            raise OSError(28, "模擬：磁碟滿了")
        return real_copy(source, target)

    real_extract = zipfile.ZipFile.extract

    def extract(self, member, path=None, pwd=None):
        if (member.filename if isinstance(member, zipfile.ZipInfo) else member) == "帳本.csv":
            raise OSError(28, "模擬：磁碟還是滿的")
        return real_extract(self, member, path, pwd)

    monkeypatch.setattr(workshop.shutil, "copyfile", copyfile)
    monkeypatch.setattr(zipfile.ZipFile, "extract", extract)
    with pytest.raises(OSError) as raised:
        workshop.install(pack(src, "記帳", {"iplot.py": "print('v2')\n", "b.py": "x = 1\n"}), mods)
    monkeypatch.undo()
    [saved] = list((folder / ".history").glob("*-folder.zip"))
    assert "已從快照放回" not in str(raised.value) and f"放回時出錯，快照在 {saved}" in str(raised.value)
    assert not (folder / "帳本.csv").exists() and (folder / ".unconfirmed").is_file()
    with zipfile.ZipFile(saved) as z:
        assert z.read("帳本.csv") == "我的帳\n".encode()


def _fail_second_copy(workshop, monkeypatch, before_raising=lambda: None):
    real, calls = workshop.shutil.copyfile, []

    def copyfile(source, target):
        calls.append(target)
        if len(calls) == 2:
            before_raising()
            raise OSError(28, "模擬：磁碟滿了")
        return real(source, target)

    monkeypatch.setattr(workshop.shutil, "copyfile", copyfile)


def test_rollback_keeps_the_snapshot_when_the_folder_already_has_dot_History(workshop, mods, src, monkeypatch):
    """第二輪審查 R2：macOS 不分大小寫，模組資料夾裡本來就有 .History/（使用者或別的工具建的）時，快照寫進它裡面。
    以前用精確的 ".history" 認快照資料夾：放回原樣時把 .History/ 連快照一起刪掉，那一句還說「快照在 <已經不在的路徑>」。"""
    probe = mods / "Aa"
    probe.mkdir()
    insensitive = (mods / "aA").exists()
    probe.rmdir()
    if not insensitive:
        pytest.skip("只在不分大小寫的檔案系統上會碰到")
    folder = make_module(mods, "記帳", "print('v1')\n")
    (folder / "帳本.csv").write_text("我的帳\n", encoding="utf-8")
    (folder / ".History").mkdir()
    (folder / ".History" / "mine.txt").write_text("我自己的\n", encoding="utf-8")
    before = {k: v for k, v in tree(folder).items() if not k.lower().startswith(".history/")}
    _fail_second_copy(workshop, monkeypatch)
    with pytest.raises(OSError) as raised:
        workshop.install(pack(src, "記帳", {"iplot.py": "print('v2')\n", "b.py": "x = 1\n"}), mods)
    monkeypatch.undo()
    message = str(raised.value)
    assert (folder / ".History" / "mine.txt").read_text(encoding="utf-8") == "我自己的\n"
    assert [p.name for p in (folder / ".History").iterdir() if p.name.endswith("-folder.zip")], "快照還在"
    for path in message.split("快照在 ")[1:]:
        assert Path(path).exists(), message
    assert "沒有裝成，已從快照放回" in message, message
    assert {k: v for k, v in tree(folder).items() if not k.lower().startswith(".history/")} == before


def test_rollback_does_not_delete_anything_when_the_snapshot_is_unreadable(workshop, mods, src, monkeypatch):
    """第二輪審查 R2：快照讀不到（寫壞了）時，放回原樣不能先把資料夾清掉——清了就補不回來。
    一樣都不刪：包沒碰到的檔逐位元組不變；留下的每個模組資料夾放 .unconfirmed；那一句照實說是新舊混合、在哪裡。"""
    folder = make_module(mods, "記帳", "print('v1')\n")
    (folder / "帳本.csv").write_text("我的帳\n", encoding="utf-8")
    make_module(folder, "子", "print('子')\n")

    def spoil():
        for saved in (folder / ".history").glob("*-folder.zip"):
            saved.write_bytes(b"not a zip any more")

    _fail_second_copy(workshop, monkeypatch, spoil)
    with pytest.raises(OSError) as raised:
        workshop.install(pack(src, "記帳", {"iplot.py": "print('v2')\n", "b.py": "x = 1\n"}), mods)
    monkeypatch.undo()
    message = str(raised.value)
    assert (folder / "帳本.csv").read_bytes() == "我的帳\n".encode()
    assert (folder / "子" / "iplot.py").read_bytes() == "print('子')\n".encode()
    assert "已從快照放回" not in message
    assert f"沒有裝成，快照讀不到、沒有放回，資料夾現在是新舊混合：{folder}" in message, message
    assert (folder / ".unconfirmed").is_file() and (folder / "子" / ".unconfirmed").is_file()


def test_a_failed_snapshot_is_one_sentence_and_leaves_no_half_zip(workshop, mods, src, tmp_path, monkeypatch):
    """存快照時出錯（磁碟滿、.history/ 不能寫）：還沒動到資料夾，那一列一句話說清楚；.history/ 裡不留寫到一半的 zip。"""
    folder = make_module(mods, "記帳", "print('v1')\n")
    (folder / "帳本.csv").write_text("我的帳\n", encoding="utf-8")
    (folder / ".history").mkdir()
    (folder / ".history" / "2026-10-01_120000.py").write_text("print('v0')\n", encoding="utf-8")
    before = tree(folder)
    real, calls = zipfile.ZipFile.write, []

    def write(self, filename, arcname=None, *args, **kwargs):
        calls.append(arcname)
        if len(calls) == 2:
            raise OSError(28, "模擬：磁碟滿了")
        return real(self, filename, arcname, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "write", write)
    api = workshop.Api(FakeApp(tmp_path), [pack(src, "記帳", {"iplot.py": "print('v2')\n"})], mods)
    answer = api.install("記帳", True)
    monkeypatch.undo()
    assert len(calls) == 2, "真的走到存快照"
    assert answer == "無法安裝：[Errno 28] 模擬：磁碟滿了；沒有裝成，還沒動到資料夾（存快照時出錯）", answer
    assert tree(folder) == before, "資料夾逐位元組不變，.history/ 沒有新檔"


def test_a_rollback_that_cannot_finish_leaves_every_module_folder_asking(workshop, mods, tmp_path, monkeypatch):
    """放不回去時，資料夾裡可能留著新下載的程式：剩下的每一個模組資料夾都放 .unconfirmed，執行前一樣會問。"""
    folder = make_module(mods, "整理桌面", "x = 2\n")
    make_module(folder, "子", "y = 2\n")
    not_a_zip = tmp_path / "壞掉的快照.zip"
    not_a_zip.write_bytes(b"not a zip")
    real = os.unlink

    def unlink(path, *args, **kwargs):  # 兩個 iplot.py 都刪不掉（被別的程式鎖著）
        if os.path.basename(path) == "iplot.py":
            raise PermissionError(13, "模擬：刪不掉")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", unlink)
    assert workshop._rollback(folder, not_a_zip) is False
    monkeypatch.undo()
    assert (folder / ".unconfirmed").is_file() and (folder / "子" / ".unconfirmed").is_file()


def test_failed_first_install_leaves_no_folder(workshop, mods, src, monkeypatch):
    def copyfile(source, target):
        raise OSError(28, "模擬：磁碟滿了")

    monkeypatch.setattr(workshop.shutil, "copyfile", copyfile)
    with pytest.raises(OSError):
        workshop.install(pack(src, "整理桌面", V1), mods)
    assert not (mods / "整理桌面").exists()


def test_file_versus_folder_between_versions(workshop, mods, src):
    """舊版的 data 是檔案、新版的 data 是資料夾（或反過來）：照新版的，舊的在快照裡。"""
    workshop.install(pack(src, "整理桌面", {**V1, "data": "一個檔", "conf/a.txt": "a"}), mods)
    assert workshop.install(pack(src, "整理桌面", {**V1, "data/x.txt": "x", "conf": "現在是檔"}), mods) == "installed"
    folder = mods / "整理桌面"
    assert (folder / "data" / "x.txt").read_text(encoding="utf-8") == "x" and (folder / "conf").read_text(encoding="utf-8") == "現在是檔"


def test_symlinks_in_the_target_are_not_followed(workshop, mods, src, tmp_path):
    """模組資料夾裡本來有指到外面的符號連結：安裝不能順著它寫到 modules/<名稱>/ 以外。"""
    outside = tmp_path / "外面.txt"
    outside.write_text("不能動", encoding="utf-8")
    elsewhere = tmp_path / "外面的資料夾"
    elsewhere.mkdir()
    folder = make_module(mods, "整理桌面", "print('我自己的')\n")
    (folder / "helper.py").symlink_to(outside)
    (folder / "data").symlink_to(elsewhere, target_is_directory=True)
    workshop.install(pack(src, "整理桌面", V2), mods)
    assert outside.read_text(encoding="utf-8") == "不能動" and list(elsewhere.iterdir()) == []
    assert not (folder / "helper.py").is_symlink() and (folder / "helper.py").read_text(encoding="utf-8") == "x = 2\n"
    assert (folder / "data" / "new.txt").is_file() and not (folder / "data").is_symlink()


def test_a_symlinked_module_folder_is_refused(workshop, mods, src, tmp_path):
    real = tmp_path / "真的在這"
    real.mkdir()
    (mods / "整理桌面").symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError):
        workshop.install(pack(src, "整理桌面", V1), mods)
    assert list(real.iterdir()) == []


def test_a_modules_own_data_does_not_make_it_modified(workshop, mods, entry, src):
    """模組執行時自己存的檔（設定、資料）不算「已修改」：比的是當初從包裡裝進來的那些檔。改了、刪了其中一個才算。"""
    workshop.install(entry, mods)
    folder = mods / "整理桌面"
    (folder / "settings.json").write_text("{}", encoding="utf-8")
    (folder / "輸出").mkdir()
    (folder / "輸出" / "a.txt").write_text("a", encoding="utf-8")
    assert workshop.state(entry, mods) == "installed"
    assert workshop.state({**pack(src / "新版", "整理桌面", V2), "version": "1.1.0"}, mods) == "update"
    (folder / "helper.py").unlink()
    assert workshop.state(entry, mods) == "modified"
    workshop.install(entry, mods)
    assert (folder / "settings.json").exists() and workshop.state(entry, mods) == "installed"


def test_update_asks_before_overwriting_a_file_the_module_made(workshop, mods, entry, src, tmp_path):
    """獨立審查 I4（D77）：「已修改」只看當初裝進來的檔，所以模組自己存的 帳本.csv 不讓它變成已修改。
    新版的包裡剛好也有一個 帳本.csv（作者測試時模組寫出來、一起被打包）：按「更新」不能不問就蓋掉。
    先回「需要確認」、什麼都不動；確認之後才蓋，舊的在快照裡。"""
    workshop.install(entry, mods)
    folder = mods / "整理桌面"
    (folder / "帳本.csv").write_text("我的帳\n", encoding="utf-8")
    newer = {**pack(src / "v2", "整理桌面", {**V2, "帳本.csv": "作者的測試資料\n"}), "version": "1.1.0"}
    assert workshop.state(newer, mods) == "update"
    api = workshop.Api(FakeApp(tmp_path), [newer], mods)
    before = tree(folder)
    assert api.install("整理桌面") == workshop.CONFIRM
    assert tree(folder) == before and not (mods / ".workshop-tmp").exists()
    assert api.install("整理桌面", True) == workshop.LABELS["installed"]
    assert (folder / "帳本.csv").read_text(encoding="utf-8") == "作者的測試資料\n"
    [saved] = list((folder / ".history").glob("*-folder.zip"))
    with zipfile.ZipFile(saved) as z:
        assert z.read("帳本.csv") == "我的帳\n".encode()


@pytest.mark.parametrize("mine, theirs", [
    ({"輸出/a.txt": "我的輸出\n"}, {"輸出": "包裡的一個檔\n"}),  # 包裡的檔會把模組自己的資料夾整個拿掉
    ({"data": "我的 data 檔\n"}, {"data/new.txt": "new\n"}),  # 包裡的資料夾要擋路的那個檔讓路
])
def test_update_asks_before_removing_what_the_module_made(workshop, mods, entry, src, tmp_path, mine, theirs):
    workshop.install(entry, mods)
    folder = mods / "整理桌面"
    for rel, text in mine.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(text, encoding="utf-8")
    newer = {**pack(src / "v2", "整理桌面", {**V1, **theirs}), "version": "1.1.0"}
    before = tree(folder)
    assert workshop.Api(FakeApp(tmp_path), [newer], mods).install("整理桌面") == workshop.CONFIRM
    assert tree(folder) == before


def test_update_that_only_replaces_its_own_files_does_not_ask(workshop, mods, entry, src, tmp_path):
    """包裡的檔只蓋到當初裝進來的那些（.origin 的 files），模組自己存的檔沒碰到：照舊直接更新，不多問。"""
    workshop.install(entry, mods)
    folder = mods / "整理桌面"
    (folder / "settings.json").write_text("{}", encoding="utf-8")
    newer = {**pack(src / "v2", "整理桌面", V2), "version": "1.1.0"}
    assert workshop.Api(FakeApp(tmp_path), [newer], mods).install("整理桌面") == workshop.LABELS["installed"]
    assert (folder / "helper.py").read_text(encoding="utf-8") == "x = 2\n" and (folder / "settings.json").exists()


@pytest.mark.parametrize("name, on_disk", [("作業系統", "作業系統"), ("更新", "更新"), ("工作坊", "工作坊"),
                                           ("更新", "更新"),  # 相容表意字：NFC 之後就是「更新」，macOS 上是同一個資料夾
                                           ("作業系統", None)])  # 被刪掉了也不從工作坊裝回來
def test_workshop_never_overwrites_iplots_own_modules(workshop, mods, src, tmp_path, name, on_disk):
    """裁定（2026-10-06，0.5.0 審查「作業系統」被覆蓋）：工作坊不讓索引覆蓋「作業系統」「更新」「工作坊」。
    覆蓋之後帶著 .unconfirmed：右鍵動作每次先問、啟動時要安裝介面卻沒辦法回答。清單上那一列沒有按鈕，有一句說明。"""
    if on_disk:
        make_module(mods, on_disk, "print('隨附的')\n")
    e = pack(src, name, V1)
    before = tree(mods)
    assert workshop.state(e, mods) == "bundled"
    row = workshop.render([e], mods, "{rows}")
    assert "<button" not in row and "工作坊不覆蓋" in row
    assert workshop.Api(FakeApp(tmp_path), [e], mods).install(name, True).startswith("無法安裝：")
    with pytest.raises(ValueError):
        workshop.install(e, mods, True)
    assert tree(mods) == before


def test_origin_lists_the_installed_files(workshop, mods, entry):
    workshop.install(entry, mods)
    origin = workshop.read_origin(mods / "整理桌面")
    assert json.loads(origin["files"]) == ["helper.py", "iplot.py"]
    text = (mods / "整理桌面" / ".origin").read_text(encoding="utf-8")
    assert all(": " in line for line in text.splitlines()) and len(text.splitlines()) == 6


def test_two_installs_at_once_both_finish(workshop, mods, src, tmp_path):
    """清單頁可以連按兩列：pywebview 一個呼叫一條執行緒。兩個安裝不能搶同一個暫存檔。"""
    import threading
    import time
    a, b = pack(src, "甲", V1), pack(src, "乙", V2)
    api = workshop.Api(FakeApp(tmp_path), [a, b], mods)
    real = workshop.download

    def slow(*args, **kwargs):
        time.sleep(0.15)
        return real(*args, **kwargs)

    workshop.download = slow
    try:
        answers = {}
        threads = [threading.Thread(target=lambda n=n: answers.__setitem__(n, api.install(n))) for n in ("甲", "乙")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
    finally:
        workshop.download = real
    assert answers == {"甲": workshop.LABELS["installed"], "乙": workshop.LABELS["installed"]}
    assert (mods / "甲" / "helper.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (mods / "乙" / "data" / "new.txt").is_file() and not (mods / ".workshop-tmp").exists()


def test_api_install_turns_any_download_trouble_into_a_sentence(workshop, mods, entry, tmp_path, monkeypatch):
    import http.client
    api = workshop.Api(FakeApp(tmp_path), [entry, {**entry, "name": "型別不對", "zip_url": 5}], mods)
    for error in (http.client.IncompleteRead(b"abc", 100), ConnectionResetError(54, "reset"), TimeoutError("timed out")):
        def broken(*args, error=error, **kwargs):
            raise error

        monkeypatch.setattr(workshop, "download", broken)
        assert api.install("整理桌面").startswith("無法安裝：")
    monkeypatch.undo()
    assert api.install("型別不對").startswith("無法安裝：")
    assert not (mods / "整理桌面").exists()


def test_read_index_checks_the_types(workshop, src, entry):
    index = src.parent / "index.json"
    for bad in ({**entry, "name": 5}, {**entry, "zip_url": None}, {**entry, "sha256": 1}):
        index.write_text(json.dumps({"modules": [bad]}), encoding="utf-8")
        with pytest.raises(ValueError):
            workshop.read_index(index.as_uri())
    index.write_text(json.dumps({"modules": [{**entry, "version": 2}, entry]}), encoding="utf-8")
    assert [e["version"] for e in workshop.read_index(index.as_uri())] == ["2"], "版本一律當字串；同名的只留第一筆"


def test_page_does_not_reload_and_handles_failures():
    """清單頁是用 html 字串開的，重新載入會變成空白頁：「取消」不能用 location.reload()。"""
    page = (MODULE / "page.html").read_text(encoding="utf-8")
    assert "location.reload" not in page and ".catch(" in page
    assert page.count("{rows}") == 1, "{rows} 只出現在要放清單的地方（註解裡再寫一次，清單會被塞進去兩次）"


def test_cancel_puts_back_the_buttons_own_label():
    """「更新」也可能要先確認（D77）：在同一列按「取消」要回到那一顆按鈕原來的字，不是一律變成「覆蓋」。
    （真的視窗另外驗過：spikes/workshop_fix_probe.py）"""
    page = (MODULE / "page.html").read_text(encoding="utf-8")
    assert 'main.textContent = "覆蓋"' not in page and "dataset.label" in page


def test_render_fills_the_rows_once(workshop, mods, entry):
    html = workshop.render([entry], mods, "<!-- {rows} 在這 -->\n<table>{rows}</table>")
    assert html.count("整理桌面</b>") == 1
