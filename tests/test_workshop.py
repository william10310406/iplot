"""隨附模組「工作坊」（modules/工作坊）：從索引安裝、更新模組；只寫進自己裝的那個資料夾，覆蓋前整個存進 .history/
（規格 13.3、D70）。全部在 tmp 裡做，來源用 file:// 網址，不連網。"""

import hashlib
import importlib.util
import json
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


def test_digest_ignores_local_things_and_sees_edits(workshop, mods):
    folder = make_module(mods, "A", "x = 1\n")
    d = workshop.digest(folder)
    for junk in (".history/a.py", "__pycache__/a.pyc", ".origin", ".unconfirmed", ".DS_Store"):
        (folder / junk).parent.mkdir(exist_ok=True)
        (folder / junk).write_text("junk", encoding="utf-8")
    assert workshop.digest(folder) == d, "各台電腦自己的東西不算進摘要"
    (folder / "iplot.py").write_text("x = 2\n", encoding="utf-8")
    assert workshop.digest(folder) != d
    (folder / "iplot.py").write_text("x = 1\n", encoding="utf-8")
    (folder / "extra.txt").write_text("", encoding="utf-8")
    assert workshop.digest(folder) != d, "多一個檔也算改過"


def test_installed_has_unconfirmed_and_state_installed(workshop, mods, entry):
    assert workshop.state(entry, mods) == "absent"
    assert workshop.install(entry, mods) == "installed"
    folder = mods / "整理桌面"
    assert {k: v for k, v in tree(folder).items() if not k.startswith(".")} == {k: v.encode() for k, v in V1.items()}
    assert (folder / ".unconfirmed").exists() and (folder / ".unconfirmed").read_bytes() == b""
    origin = workshop.read_origin(folder)
    assert (origin["url"], origin["version"], origin["sha256"]) == (entry["zip_url"], "1.0.0", entry["sha256"])
    assert origin["digest"] == workshop.digest(folder) and origin["installed"]
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
