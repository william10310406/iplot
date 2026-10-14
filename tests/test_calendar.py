"""工作坊模組「行事曆」（modules/行事曆）：資料、圖片、網頁、程序、Api、畫面（D89–D93）。
模組裡的檔用 load("名字") 當一般模組 import（跟 runner 一樣走 sys.path，不寫 .pyc）。絕不碰 ~/Documents/行事曆、
不在 repo 的 modules/行事曆 裡寫檔：資料夾一律在 tmp_path；sips、ps、Popen、app.open、app.trash、AppKit 一律換成假的。"""

import dataclasses
import datetime
import importlib
import os
import re
import shutil
import struct
import sys
import threading
import types
import urllib.parse
import zlib
from html.parser import HTMLParser
from pathlib import Path

import pytest

from core.types import DEFAULT_CONFIG

CALENDAR = Path(__file__).resolve().parents[1] / "modules" / "行事曆"
NAMES = ("diary", "pages", "photos", "iplot")


@pytest.fixture
def load(monkeypatch):
    """load("diary")：把 modules/行事曆/diary.py 當一般模組 import（不寫 .pyc）——跟 runner 一樣走 sys.path；
    結束時從 sys.modules 拿掉。"""
    monkeypatch.syspath_prepend(str(CALENDAR))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    for n in NAMES:
        monkeypatch.delitem(sys.modules, n, raising=False)
    yield importlib.import_module
    for n in NAMES:
        sys.modules.pop(n, None)


def write_day(root, date, **fields):
    """直接在磁碟上寫一天（不經 diary）：write_day(root, "2026-10-14", 行程="開會", 心情="🙂\\n好")。"""
    folder = Path(root) / date[:4] / date[5:7] / date[8:]
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in fields.items():
        (folder / f"{name}.txt").write_text(text, encoding="utf-8")
    return folder


class CalApp:
    """模組拿到的 app 的替身（conftest.FakeApp 沒有 open/trash/modules/choose_folder/run，所以自己寫，不改 conftest）。
    open／reveal 只記錄；trash 把檔案搬到 home 旁邊的「垃圾桶」並記錄；page 記 (title, html, api)、有 on_page 就呼叫它、
    立刻回來；choose_folder 回 folder_answer。"""

    def __init__(self, home, **config):
        self.home, self.module, self.modules = Path(home), None, []
        self.config = dataclasses.replace(DEFAULT_CONFIG, **config)
        self.logs, self.opened, self.trashed, self.revealed, self.pages, self.ran = [], [], [], [], [], []
        self.folder_answer, self.on_page = None, None

    def log(self, text):
        self.logs.append(text)

    def open(self, path):
        self.opened.append(Path(path))

    def reveal(self, path):
        self.revealed.append(Path(path))

    def trash(self, path):
        path = Path(path)
        self.trashed.append(path)
        bin_ = self.home.parent / "垃圾桶"
        bin_.mkdir(exist_ok=True)
        dest = bin_ / f"{len(self.trashed)}-{path.name}"
        shutil.move(str(path), str(dest))
        return dest

    def page(self, title, html, api=None):
        self.pages.append((title, html, api))
        if self.on_page is not None:
            self.on_page()

    def choose_folder(self):
        return self.folder_answer

    def choose_files(self):
        return []

    def run(self, name):
        self.ran.append(name)


def in_thread(fn):
    """在另一條執行緒跑 fn，回那條執行緒與裝結果的盒子（照 tests/test_interop.py 的 in_thread）。"""
    box = []
    t = threading.Thread(target=lambda: box.append(fn()), daemon=True)
    t.start()
    return t, box


def never(*a, **k):
    pytest.fail(f"不該被叫：{a} {k}")


def pid_file_with(tmp_path, text):
    path = Path(tmp_path) / ".pid"
    path.write_text(text, encoding="utf-8")
    return path


def fake_sips_ok(argv, **kw):
    """假的 sips：把 --out 前面那個檔複製到最後一個參數，回 returncode 0。"""
    assert isinstance(argv, list) and "shell" not in kw
    shutil.copyfile(argv[argv.index("--out") - 1], argv[-1])
    return types.SimpleNamespace(returncode=0, stdout="", stderr="")


def _segment(marker, body):
    return bytes([0xFF, marker]) + struct.pack(">H", len(body) + 2) + body


def _exif_gps():
    """APP1 的內容：Exif\\0\\0 + TIFF（MM）+ IFD0（GPSInfo 指標）+ GPS IFD（北緯 25.03、東經 121.56）。"""
    def entry(tag, typ, count, value):
        return struct.pack(">HHI", tag, typ, count) + value

    gps_off = 8 + 2 + 12 + 4
    data_off = gps_off + 2 + 4 * 12 + 4
    ifd0 = struct.pack(">H", 1) + entry(0x8825, 4, 1, struct.pack(">I", gps_off)) + struct.pack(">I", 0)
    gps = (struct.pack(">H", 4) + entry(1, 2, 2, b"N\x00\x00\x00") + entry(2, 5, 3, struct.pack(">I", data_off))
           + entry(3, 2, 2, b"E\x00\x00\x00") + entry(4, 5, 3, struct.pack(">I", data_off + 24)) + struct.pack(">I", 0))
    rationals = struct.pack(">IIIIII", 25, 1, 1, 1, 4800, 100) + struct.pack(">IIIIII", 121, 1, 33, 1, 3600, 100)
    return b"Exif\x00\x00" + b"MM\x00\x2a" + struct.pack(">I", 8) + ifd0 + gps + rationals


def gps_jpeg() -> bytes:
    """帶 APP1（Exif GPS）與 APP13 的最小 JPEG（段落結構對，不一定解得出畫面；照 Task 0 Step 6 的探針）。"""
    return (b"\xff\xd8" + _segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            + _segment(0xE1, _exif_gps()) + _segment(0xED, b"Photoshop 3.0\x008BIM\x04\x04\x00\x00\x00\x00\x00\x00")
            + _segment(0xDB, b"\x00" + bytes(range(1, 65)))
            + _segment(0xC0, b"\x08\x00\x01\x00\x01\x01\x01\x11\x00")
            + _segment(0xC4, b"\x00" + b"\x01" + bytes(15) + b"\x00")
            + _segment(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"\x00\x3f\xff\x00\x12" + b"\xff\xd9")


def _png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_with_text() -> bytes:
    """2×2 PNG，IDAT 之前放 tEXt、iTXt、zTXt、eXIf 四個 chunk。"""
    rows = b"".join(b"\x00" + b"\xc8\x3c\x3c" * 2 for _ in range(2))
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + _png_chunk(b"tEXt", b"Comment\x00secret") + _png_chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x/>")
            + _png_chunk(b"zTXt", b"Author\x00\x00" + zlib.compress(b"me")) + _png_chunk(b"eXIf", _exif_gps()[6:])
            + _png_chunk(b"IDAT", zlib.compress(rows)) + _png_chunk(b"IEND", b""))


def api(load, tmp_path, *, home=None, **kw):
    """Task 6 用：home 預設 tmp_path/"iPLoT"（建好 modules/）；config 的欄位（例如 history_keep=2）給 CalApp，其他給 Api。"""
    fields = {f.name for f in dataclasses.fields(DEFAULT_CONFIG)}
    config = {k: kw.pop(k) for k in list(kw) if k in fields}
    if home is None:
        home = tmp_path / "iPLoT"
        (home / "modules").mkdir(parents=True, exist_ok=True)
    kw.setdefault("default_root", tmp_path / "資料")
    kw.setdefault("run", fake_sips_ok)
    kw.setdefault("popen", never)
    kw.setdefault("platform", "darwin")
    kw.setdefault("environ", {})
    kw.setdefault("today", lambda: datetime.date(2026, 10, 14))
    return load("iplot").Api(CalApp(home, **config), tmp_path / "設定.json", **kw)


def page_html() -> str:
    return (CALENDAR / "page.html").read_text(encoding="utf-8")


# ── diary：一天一個資料夾、四欄、心情、公開標記、.history（D90） ──

def test_save_and_read_four_fields(load, tmp_path):
    d = load("diary")
    got = d.save_day(tmp_path, "2026-10-14", {"行程": "開會", "心情": d.mood_text("🙂", "還好"), "看到": "", "做了": "寫字"}, 20)
    assert got == {"changed": ["行程", "心情", "做了"], "unreadable": {}}
    day = d.read_day(tmp_path, "2026-10-14")
    assert (day["行程"], day["mood"], day["note"], day["看到"], day["做了"]) == ("開會", "🙂", "還好", "", "寫字")
    assert (tmp_path / "2026" / "10" / "14" / "行程.txt").read_text(encoding="utf-8") == "開會"
    assert not (tmp_path / "2026" / "10" / "14" / "看到.txt").exists()


def test_saving_empty_deletes_the_file(load, tmp_path):
    d = load("diary")
    d.save_day(tmp_path, "2026-10-14", {"行程": "x"}, 20)
    assert d.save_day(tmp_path, "2026-10-14", {"行程": ""}, 20)["changed"] == ["行程"]
    folder = tmp_path / "2026" / "10" / "14"
    assert not (folder / "行程.txt").exists()
    [old] = (folder / ".history").glob("行程-*.txt")
    assert old.read_text(encoding="utf-8") == "x"


def test_mood_three_ways(load, tmp_path):
    d = load("diary")
    assert d.parse_mood("🙂\n好") == ("🙂", "好")
    assert d.parse_mood("\n好") == ("", "好")
    assert d.parse_mood("隨便改的\n好") == ("", "隨便改的\n好")
    assert d.mood_text("", "") == "" and d.mood_text("😢", "") == "😢\n" and d.mood_text("", "一句") == "\n一句"
    write_day(tmp_path, "2026-10-14", 心情="隨便改的\n好")
    day = d.read_day(tmp_path, "2026-10-14")
    assert (day["mood"], day["note"]) == ("", "隨便改的\n好")


def test_history_keeps_n_versions_per_field(load, tmp_path, monkeypatch):
    d = load("diary")
    monkeypatch.setattr(d, "_now", lambda: datetime.datetime(2026, 10, 14, 9, 30, 0))
    folder = tmp_path / "2026" / "10" / "14"
    (folder / ".history").mkdir(parents=True)
    (folder / ".history" / "其他.txt").write_text("別人的", encoding="utf-8")
    for text in ("v1", "v2", "v3", "v4"):
        d.save_day(tmp_path, "2026-10-14", {"行程": text}, 2)
    kept = sorted((folder / ".history").glob("行程-*.txt"))
    assert [p.name for p in kept] == ["行程-20261014-093000-2.txt", "行程-20261014-093000-3.txt"]
    assert [p.read_text(encoding="utf-8") for p in kept] == ["v2", "v3"]
    assert (folder / ".history" / "其他.txt").read_text(encoding="utf-8") == "別人的"


def test_write_goes_through_a_temp_file_and_replace(load, tmp_path, monkeypatch):
    d, seen, real = load("diary"), [], os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: (seen.append((Path(src), Path(dst))), real(src, dst))[1])
    d.save_day(tmp_path, "2026-10-14", {"行程": "開會"}, 20)
    [(src, dst)] = seen
    folder = tmp_path / "2026" / "10" / "14"
    assert src.parent == folder and src.name.startswith(".") and f".tmp-{os.getpid()}" in src.name
    assert dst == folder / "行程.txt" and not src.exists()


def test_a_non_utf8_file_is_not_overwritten(load, tmp_path):
    d = load("diary")
    folder = write_day(tmp_path, "2026-10-14")
    (folder / "行程.txt").write_bytes(b"\xff\xfe")
    day = d.read_day(tmp_path, "2026-10-14")
    assert day["行程"] == "" and day["unreadable"] == {"行程": str(folder / "行程.txt")}
    got = d.save_day(tmp_path, "2026-10-14", {"行程": "新的"}, 20)
    assert got == {"changed": [], "unreadable": {"行程": str(folder / "行程.txt")}}
    assert (folder / "行程.txt").read_bytes() == b"\xff\xfe"


def test_month_summary(load, tmp_path):
    d = load("diary")
    (write_day(tmp_path, "2026-10-03") / "a.jpg").write_bytes(b"jpg")
    write_day(tmp_path, "2026-10-14", 心情="🙂\n好", 行程="開會\n吃飯")
    (write_day(tmp_path, "2026-10-20", 做了="寫字") / "公開").write_bytes(b"")
    (write_day(tmp_path, "2026-10-05") / "公開").write_bytes(b"")
    assert d.month_summary(tmp_path, "2026-10") == {
        "03": {"mood": "", "first": "", "images": True, "public": False},
        "14": {"mood": "🙂", "first": "開會", "images": False, "public": False},
        "20": {"mood": "", "first": "寫字", "images": False, "public": True},
    }
    assert list(d.month_summary(tmp_path, "2026-10", public_only=True)) == ["20"]


def test_first_line_order(load):
    d = load("diary")
    assert d.first_line({"行程": "", "做了": "\n a\nb", "看到": "c"}) == "a"
    assert d.first_line({"行程": "", "做了": "", "看到": ""}) == ""


def test_public_marker_toggles(load, tmp_path):
    d = load("diary")
    write_day(tmp_path, "2026-10-14", 行程="x")
    d.set_public(tmp_path, "2026-10-14", True)
    marker = tmp_path / "2026" / "10" / "14" / "公開"
    assert marker.is_file() and marker.read_bytes() == b"" and d.read_day(tmp_path, "2026-10-14")["public"] is True
    assert d.all_days(tmp_path, public_only=True) == ["2026-10-14"]
    d.set_public(tmp_path, "2026-10-14", False)
    assert not marker.exists() and d.all_days(tmp_path, public_only=True) == []


def test_all_days_sorted_and_ignores_junk_folders(load, tmp_path):
    d = load("diary")
    write_day(tmp_path, "2026-10-14", 行程="b")
    write_day(tmp_path, "2025-12-31", 行程="a")
    (tmp_path / "2026" / "10" / "發佈").mkdir()
    (tmp_path / "2026" / "10" / "發佈" / "行程.txt").write_text("x", encoding="utf-8")
    write_day(tmp_path, "2026-13-01", 行程="壞月份")
    write_day(tmp_path, "2026-02-30", 行程="壞日子")
    (tmp_path / "發佈" / "2026" / "10" / "01").mkdir(parents=True)
    assert d.all_days(tmp_path) == ["2025-12-31", "2026-10-14"]
    assert d.all_days(tmp_path / "沒有") == []


def test_heic_hidden_when_jpg_exists(load, tmp_path):
    d = load("diary")
    folder = write_day(tmp_path, "2026-10-14")
    for name in ("a.heic", "a.jpg", "b.HEIC", "c.txt", ".隱藏.jpg"):
        (folder / name).write_bytes(b"x")
    assert d.read_day(tmp_path, "2026-10-14")["images"] == ["a.jpg", "b.HEIC"]


def test_dates_are_checked_by_regex_and_datetime(load):
    d = load("diary")
    assert d.parse_date("2024-02-29") == datetime.date(2024, 2, 29)
    for bad in ("2026-02-30", "2026-2-3", "20261014", "2026-10-14x", "２０２６-10-14", ""):
        with pytest.raises(ValueError):
            d.parse_date(bad)
    assert d.parse_ym("2026-10") == (2026, 10) and d.parse_year("2026") == 2026
    for bad in ("2026-13", "26-10", "2026-1"):
        with pytest.raises(ValueError):
            d.parse_ym(bad)
    with pytest.raises(ValueError):
        d.parse_year("26")


def test_settings_default_and_roundtrip(load, tmp_path):
    d = load("diary")
    settings, default = tmp_path / "設定.json", tmp_path / "預設"
    assert d.load_root(settings, default) == default.resolve()
    d.save_root(settings, tmp_path / "別處")
    assert d.load_root(settings, default) == (tmp_path / "別處").resolve()
    settings.write_text("{壞掉", encoding="utf-8")
    assert d.load_root(settings, default) == default.resolve()


# ── photos：收進來、HEIC 轉 JPG、縮圖、公開版縮小並拿掉中繼資料 ──

def test_clean_name_takes_the_basename_and_drops_bad_characters(load):
    p = load("photos")
    assert p.clean_name("/Users/x/a:b.jpg") == "ab.jpg" and p.clean_name("..隱藏.png") == "隱藏.png"
    assert p.clean_name("C:\\x\\y.JPG") == "y.JPG" and p.clean_name("") == "圖片" and p.clean_name("a\x00\nb.jpg") == "ab.jpg"


def test_duplicate_names_get_a_number(load, tmp_path):
    p = load("photos")
    (tmp_path / "a.jpg").write_bytes(b"x")
    assert p.unique_name(tmp_path, "a.jpg") == "a 2.jpg" and p.unique_name(tmp_path, "A.JPG") == "A 2.JPG"
    (tmp_path / "a 2.jpg").write_bytes(b"x")
    assert p.unique_name(tmp_path, "a.jpg") == "a 3.jpg"
    (tmp_path / "b.heic").write_bytes(b"x")
    assert p.unique_name(tmp_path, "b.jpg") == "b 2.jpg" and p.unique_name(tmp_path, "c.png") == "c.png"


def test_add_image_rejects_too_big_and_non_images(load, tmp_path):
    p = load("photos")
    assert p.add_image(tmp_path, "x.jpg", b"\0" * (30 * 1024 * 1024 + 1)) == (None, "x.jpg：太大（超過 30 MB）")
    assert p.add_image(tmp_path, "x.txt", b"hi") == (None, "x.txt：不是圖片")
    assert list(tmp_path.iterdir()) == []


def test_add_image_writes_atomically(load, tmp_path, monkeypatch):
    p, seen, real = load("photos"), [], os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: (seen.append((Path(src).name, Path(dst))), real(src, dst))[1])
    assert p.add_image(tmp_path, "a.jpg", b"jpgdata") == ("a.jpg", None)
    assert seen == [(f".a.jpg.tmp-{os.getpid()}", tmp_path / "a.jpg")] and (tmp_path / "a.jpg").read_bytes() == b"jpgdata"


def test_add_image_creates_the_day_folder(load, tmp_path):
    p = load("photos")
    folder = tmp_path / "2026" / "10" / "14"
    assert p.add_image(folder, "a.jpg", b"x") == ("a.jpg", None) and (folder / "a.jpg").exists()


def test_heic_calls_sips_with_list_arguments(load, tmp_path):
    p, calls = load("photos"), []

    def run(argv, **kw):
        calls.append((argv, kw))
        Path(argv[-1]).write_bytes(b"jpg")
        return types.SimpleNamespace(returncode=0)

    assert p.add_image(tmp_path, "IMG_1.HEIC", b"heic", run=run, platform="darwin") == ("IMG_1.HEIC", None)
    assert calls[0][0] == ["sips", "-s", "format", "jpeg", str(tmp_path / "IMG_1.HEIC"), "--out", str(tmp_path / "IMG_1.jpg")]
    assert "shell" not in calls[0][1] and (tmp_path / "IMG_1.HEIC").exists() and (tmp_path / "IMG_1.jpg").exists()


def test_heic_that_will_not_convert_keeps_the_original_and_says_so(load, tmp_path):
    p = load("photos")
    run = lambda argv, **kw: types.SimpleNamespace(returncode=1)  # noqa: E731
    assert p.add_image(tmp_path, "IMG_1.HEIC", b"heic", run=run, platform="darwin") == (
        "IMG_1.HEIC", "IMG_1.HEIC：轉不成 JPG，Chrome 看不到")
    assert (tmp_path / "IMG_1.HEIC").exists() and not (tmp_path / "IMG_1.jpg").exists()


def test_heic_elsewhere_is_kept_and_says_so(load, tmp_path):
    p = load("photos")
    assert p.add_image(tmp_path, "a.heif", b"heif", run=never, platform="linux") == ("a.heif", "a.heif：轉不成 JPG，Chrome 看不到")


def test_jpeg_strip_removes_app1_and_app13(load, tmp_path):
    p = load("photos")
    src, dst = tmp_path / "gps.jpg", tmp_path / "clean.jpg"
    src.write_bytes(gps_jpeg())
    p.strip_metadata(src, dst)
    out = dst.read_bytes()
    assert b"\xff\xe1" not in out and b"\xff\xed" not in out and b"Exif" not in out and b"Photoshop" not in out
    assert out[:2] == b"\xff\xd8" and out[-2:] == b"\xff\xd9" and b"JFIF" in out and b"\xff\xda" in out


def test_png_strip_removes_text_and_exif_chunks(load, tmp_path):
    p = load("photos")
    src, dst = tmp_path / "a.png", tmp_path / "b.png"
    src.write_bytes(png_with_text())
    p.strip_metadata(src, dst)
    out = dst.read_bytes()
    assert out[:8] == b"\x89PNG\r\n\x1a\n" and all(k in out for k in (b"IHDR", b"IDAT", b"IEND"))
    assert not any(k in out for k in (b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"secret", b"Exif"))


def test_gif_is_copied_as_is_and_others_are_refused(load, tmp_path):
    p = load("photos")
    (tmp_path / "a.gif").write_bytes(b"GIF89a\x01\x00\x01\x00rest")
    p.strip_metadata(tmp_path / "a.gif", tmp_path / "b.gif")
    assert (tmp_path / "b.gif").read_bytes() == b"GIF89a\x01\x00\x01\x00rest"
    (tmp_path / "x.gif").write_bytes(b"BM....")
    with pytest.raises(ValueError):
        p.strip_metadata(tmp_path / "x.gif", tmp_path / "y.gif")
    assert not (tmp_path / "y.gif").exists()


def test_public_copy_shrinks_on_macos_then_strips(load, tmp_path):
    p, calls = load("photos"), []
    src = tmp_path / "a.jpg"
    src.write_bytes(gps_jpeg())
    p.public_copy(src, tmp_path / "out" / "a.jpg", run=lambda argv, **kw: (calls.append(argv), fake_sips_ok(argv))[1],
                  platform="darwin")
    assert calls[0][:3] == ["sips", "-Z", "1600"] and calls[0][3] == str(src) and calls[0][4] == "--out"
    assert b"\xff\xe1" not in (tmp_path / "out" / "a.jpg").read_bytes()
    p.public_copy(src, tmp_path / "out2" / "a.jpg", run=never, platform="linux")
    assert b"\xff\xe1" not in (tmp_path / "out2" / "a.jpg").read_bytes() and not list((tmp_path / "out").glob(".*"))


def test_thumbnail_is_made_once_with_sips_and_comes_back_as_a_data_url(load, tmp_path):   # Task 0 Step 4 的退路
    p, calls = load("photos"), []
    (tmp_path / "a.png").write_bytes(b"png")

    def run(argv, **kw):
        calls.append(argv)
        Path(argv[-1]).write_bytes(b"thumb")
        return types.SimpleNamespace(returncode=0)

    url = p.thumbnail_url(tmp_path, "a.png", run=run, platform="darwin")
    thumb = tmp_path / ".縮圖" / "a.png.jpg"
    assert calls == [["sips", "-s", "format", "jpeg", "-Z", "320", str(tmp_path / "a.png"), "--out", str(thumb)]]
    assert url == "data:image/jpeg;base64,dGh1bWI=" and p.thumbnail_url(tmp_path, "a.png", run=never, platform="darwin") == url
    os.utime(tmp_path / "a.png", (thumb.stat().st_mtime + 10,) * 2)       # 原圖比縮圖新 → 重做
    p.thumbnail_url(tmp_path, "a.png", run=run, platform="darwin")
    assert len(calls) == 2


def test_thumbnail_without_sips_uses_small_originals_only(load, tmp_path):
    p = load("photos")
    (tmp_path / "a.png").write_bytes(b"png")
    (tmp_path / "b.heic").write_bytes(b"heic")
    (tmp_path / "c.jpg").write_bytes(b"\0" * (5 * 1024 * 1024 + 1))
    assert p.thumbnail_url(tmp_path, "a.png", run=never, platform="linux") == "data:image/png;base64,cG5n"
    assert p.thumbnail_url(tmp_path, "b.heic", run=never, platform="linux") is None
    assert p.thumbnail_url(tmp_path, "c.jpg", run=never, platform="linux") is None
    failing = lambda argv, **kw: types.SimpleNamespace(returncode=1)  # noqa: E731
    assert p.thumbnail_url(tmp_path, "b.heic", run=failing, platform="darwin") is None


# ── pages：本機網頁（日、月、年、綜合）；存一天連鄰居一起重產（D91、設計第 15 節第 3、5 條） ──

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links += [v for k, v in attrs if k in ("href", "src") and v is not None]


def links_in(path):
    parser = Links()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.links


def month_cells(page):
    """月頁的格子，依序："" 是空格，數字字串是那一天。"""
    table = page[page.index('<table class="month">'):page.index("</table>")]
    return [n or "" for n in re.findall(r'<td class="(?:empty"|day[^"]*")>(?:<a [^>]*>)?(?:<span class="n">(\d+)</span>)?', table)]


def test_day_page_escapes_text_and_has_no_script_or_external_url(load, tmp_path):
    pg = load("pages")
    write_day(tmp_path, "2026-10-14", 行程="<b>開會</b> & 吃飯", 心情="🙂\n還好")
    html_text = pg.render_day(tmp_path, "2026-10-14")
    assert "&lt;b&gt;開會&lt;/b&gt; &amp; 吃飯" in html_text and "<b>開會" not in html_text
    assert "2026 年 10 月 14 日（三）" in html_text and "🙂" in html_text and "還好" in html_text
    assert all(w not in html_text for w in ("<script", "http://", "https://")) and 'charset="utf-8"' in html_text
    assert "prefers-color-scheme: dark" in html_text and 'name="viewport"' in html_text and "noindex" not in html_text


def test_every_link_is_relative_and_points_at_an_existing_file(load, tmp_path):
    pg = load("pages")
    for date in ("2026-09-30", "2026-10-14", "2027-01-01"):
        (write_day(tmp_path, date, 行程=date) / "a.jpg").write_bytes(b"jpg")
    pg.rebuild_all(tmp_path)
    pages = sorted(tmp_path.rglob("index.html"))
    assert len(pages) == 3 + 3 + 2 + 1
    for page in pages:
        for link in links_in(page):
            assert not link.startswith(("/", "file:", "http", "data:", "#")), (page, link)
            assert (page.parent / urllib.parse.unquote(link)).resolve().exists(), (page, link)


def test_image_links_quote_spaces_hash_percent_and_chinese(load, tmp_path):            # Review Focus 1
    pg = load("pages")
    name = "螢幕擷取畫面 2026-10-14 上午9.30 #1 100%.png"
    (write_day(tmp_path, "2026-10-14", 行程="x") / name).write_bytes(b"png")
    page = pg.render_day(tmp_path, "2026-10-14")
    img = page.split("<img", 1)[1].split(">", 1)[0]
    assert re.search(r'src="([^"]+)"', img).group(1) == urllib.parse.quote(name) and 'loading="lazy"' in img
    assert 'alt=""' in img and f'href="{urllib.parse.quote(name)}"' in page and name not in img
    index = pg.render_index(tmp_path)
    assert f'src="2026/10/14/{urllib.parse.quote(name)}"' in index


def test_month_grid_starts_on_sunday_and_has_the_right_days(load, tmp_path):
    pg = load("pages")
    page = pg.render_month(tmp_path, "2026-10")
    assert "".join(re.findall(r"<th>(.)</th>", page)) == "日一二三四五六"
    cells = month_cells(page)
    assert cells[:5] == ["", "", "", "", "1"] and [c for c in cells if c] == [str(n) for n in range(1, 32)]
    for ym, days in (("2026-02", 28), ("2024-02", 29), ("2026-04", 30)):
        assert len([c for c in month_cells(pg.render_month(tmp_path, ym)) if c]) == days, ym
    assert "2026 年 10 月" in page


def test_month_cell_shows_mood_first_line_cut_to_20_and_camera(load, tmp_path):
    pg = load("pages")
    folder = write_day(tmp_path, "2026-10-14", 心情="😄\n", 行程="一二三四五六七八九十一二三四五六七八九十多出來的五")
    (folder / "a.jpg").write_bytes(b"jpg")
    write_day(tmp_path, "2026-10-15", 行程="")
    page = pg.render_month(tmp_path, "2026-10")
    cell = page.split('href="14/index.html"', 1)[1].split("</td>", 1)[0]
    assert "😄" in cell and "一二三四五六七八九十一二三四五六七八九十…" in cell and "多出來" not in cell and "🖼" in cell
    assert 'href="15/index.html"' not in page


def test_month_prev_next_links_only_when_there_is_content(load, tmp_path):
    pg = load("pages")
    write_day(tmp_path, "2026-09-03", 行程="九月")
    write_day(tmp_path, "2026-10-14", 行程="十月")
    write_day(tmp_path, "2025-12-31", 行程="去年")
    page = pg.render_month(tmp_path, "2026-10")
    assert 'href="../09/index.html"' in page and "../11/index.html" not in page and "下一個月" in page
    assert 'href="../../2025/12/index.html"' in pg.render_month(tmp_path, "2026-01")


def test_year_page_has_twelve_months_and_marks_days(load, tmp_path):
    pg = load("pages")
    write_day(tmp_path, "2026-10-14", 心情="🙂\n", 行程="x")
    write_day(tmp_path, "2026-03-02", 做了="y")
    page = pg.render_year(tmp_path, "2026")
    assert page.count('<table class="mini">') == 12 and "2026 年" in page
    assert '<a href="10/14/index.html">🙂</a>' in page and '<a href="03/02/index.html">·</a>' in page
    assert 'href="10/index.html"' in page and 'href="05/index.html"' not in page


def test_index_lists_thirty_recent_days_newest_first_and_year_month_entries(load, tmp_path):
    pg = load("pages")
    start = datetime.date(2026, 9, 1)
    for i in range(35):
        date = (start + datetime.timedelta(days=i)).isoformat()
        folder = write_day(tmp_path, date, 行程=f"第{i}天", 看到="看到", 做了="做了")
    for n in range(5):
        (folder / f"{n}.jpg").write_bytes(b"jpg")
    page = pg.render_index(tmp_path)
    days = re.findall(r'<article><h2><a href="(\d{4}/\d{2}/\d{2})/index.html"', page)
    assert len(days) == 30 and days[0] == "2026/10/05" and days[-1] == "2026/09/06"
    newest = page.split("<article>", 2)[1]
    assert newest.count("<img") == 4 and "第34天" in newest and "看到" in newest and "做了" in newest
    assert 'href="2026/index.html"' in page and "10 月（5 天）" in page and "9 月（30 天）" in page


def test_saving_a_day_relinks_both_neighbours(load, tmp_path):                        # 第 5 條
    pg = load("pages")
    write_day(tmp_path, "2026-10-10", 行程="a")
    write_day(tmp_path, "2026-10-20", 行程="c")
    pg.rebuild_all(tmp_path)
    write_day(tmp_path, "2026-10-14", 行程="b")
    written = pg.rebuild_after_save(tmp_path, "2026-10-14")
    assert "../../../2026/10/14/index.html" in (tmp_path / "2026/10/10/index.html").read_text(encoding="utf-8")
    assert "../../../2026/10/14/index.html" in (tmp_path / "2026/10/20/index.html").read_text(encoding="utf-8")
    assert {p.relative_to(tmp_path).as_posix() for p in written} >= {
        "2026/10/10/index.html", "2026/10/14/index.html", "2026/10/20/index.html", "2026/10/index.html",
        "2026/index.html", "index.html"}


def test_clearing_a_day_relinks_its_neighbours_back(load, tmp_path):
    pg = load("pages")
    for date, text in (("2026-10-10", "a"), ("2026-10-14", "b"), ("2026-10-20", "c")):
        write_day(tmp_path, date, 行程=text)
    pg.rebuild_all(tmp_path)
    (tmp_path / "2026/10/14/行程.txt").unlink()
    pg.rebuild_after_save(tmp_path, "2026-10-14")
    page = (tmp_path / "2026/10/10/index.html").read_text(encoding="utf-8")
    assert "../../../2026/10/20/index.html" in page and "2026/10/14" not in page
    assert "這一天沒有內容" in (tmp_path / "2026/10/14/index.html").read_text(encoding="utf-8")


def test_neighbours_cross_month_and_year(load, tmp_path):
    pg = load("pages")
    write_day(tmp_path, "2026-09-30", 行程="a")
    write_day(tmp_path, "2026-10-01", 行程="b")
    write_day(tmp_path, "2026-12-31", 行程="c")
    pg.rebuild_all(tmp_path)
    assert "../../../2026/10/01/index.html" in (tmp_path / "2026/09/30/index.html").read_text(encoding="utf-8")
    write_day(tmp_path, "2027-01-01", 行程="d")
    written = pg.rebuild_after_save(tmp_path, "2027-01-01")
    assert tmp_path / "2026/12/31/index.html" in written
    assert "../../../2027/01/01/index.html" in (tmp_path / "2026/12/31/index.html").read_text(encoding="utf-8")
    assert pg.neighbours(["2026-09-30", "2026-10-01", "2026-12-31"], "2026-10-15") == ("2026-10-01", "2026-12-31")
    assert pg.neighbours(["2026-10-01"], "2026-10-01") == (None, None)


def test_next_month_link_appears_after_the_first_entry_of_the_next_year(load, tmp_path):
    pg = load("pages")
    write_day(tmp_path, "2026-12-05", 行程="x")
    pg.rebuild_all(tmp_path)
    assert "2027/01" not in (tmp_path / "2026/12/index.html").read_text(encoding="utf-8")
    write_day(tmp_path, "2027-01-01", 行程="y")
    pg.rebuild_after_save(tmp_path, "2027-01-01")
    assert 'href="../../2027/01/index.html"' in (tmp_path / "2026/12/index.html").read_text(encoding="utf-8")


def test_rebuild_after_save_does_not_create_pages_for_months_that_never_existed(load, tmp_path):
    pg = load("pages")
    write_day(tmp_path, "2026-10-14", 行程="x")
    pg.rebuild_after_save(tmp_path, "2026-10-14")
    assert not (tmp_path / "2026/09").exists() and not (tmp_path / "2026/11").exists()
    assert (tmp_path / "2026/10/index.html").exists() and (tmp_path / "2026/index.html").exists()


def test_rebuild_all_with_no_days_writes_only_the_index(load, tmp_path):
    pg = load("pages")
    root = tmp_path / "空"
    assert pg.rebuild_all(root) == [root / "index.html"]
    assert (root / "index.html").exists() and [p.name for p in root.iterdir()] == ["index.html"]


def test_rebuild_all_survives_a_non_utf8_file_and_marks_the_field(load, tmp_path):   # Review Focus 4
    pg = load("pages")
    write_day(tmp_path, "2026-10-14", 行程="ok")
    (tmp_path / "2026/10/14/做了.txt").write_bytes(b"\xff\xfe\x00")
    pg.rebuild_all(tmp_path)
    page = (tmp_path / "2026/10/14/index.html").read_text(encoding="utf-8")
    assert "讀不到" in page and "ok" in page and (tmp_path / "2026/10/14/做了.txt").read_bytes() == b"\xff\xfe\x00"
