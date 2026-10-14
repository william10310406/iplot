"""工作坊模組「行事曆」（modules/行事曆）：資料、圖片、網頁、程序、Api、畫面（D89–D93）。
模組裡的檔用 load("名字") 當一般模組 import（跟 runner 一樣走 sys.path，不寫 .pyc）。絕不碰 ~/Documents/行事曆、
不在 repo 的 modules/行事曆 裡寫檔：資料夾一律在 tmp_path；sips、ps、Popen、app.open、app.trash、AppKit 一律換成假的。"""

import dataclasses
import datetime
import importlib
import inspect
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import types
import unicodedata
import urllib.parse
import zlib
from html.parser import HTMLParser
from pathlib import Path

import conftest
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


# ── 公開版：發佈/ 只放打開「公開」的日子（D91、D92；每次重寫所有網頁，設計第 15 節第 5 條） ──

def three_days(tmp_path, public=("2026-10-10", "2026-10-20")):
    d = load_diary()
    for date in ("2026-10-10", "2026-10-14", "2026-10-20"):
        (write_day(tmp_path, date, 行程=f"寫在 {date}") / "a.jpg").write_bytes(gps_jpeg())
    for date in public:
        d.set_public(tmp_path, date, True)


def load_diary():
    return sys.modules["diary"]


def test_publish_contains_only_public_days_and_returns_the_folder(load, tmp_path):
    pg = load("pages")
    three_days(tmp_path)
    out = pg.publish(tmp_path, run=fake_sips_ok, platform="darwin")
    assert out == tmp_path / "發佈" and (out / "2026/10/10/index.html").exists() and not (out / "2026/10/14").exists()
    month = (out / "2026/10/index.html").read_text(encoding="utf-8")
    assert "14/index.html" not in month and 'href="10/index.html"' in month
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "寫在 2026-10-14" not in index and "寫在 2026-10-20" in index
    assert "../../../2026/10/20/index.html" in (out / "2026/10/10/index.html").read_text(encoding="utf-8")


def test_every_public_page_has_noindex(load, tmp_path):
    pg = load("pages")
    three_days(tmp_path)
    pages = list(pg.publish(tmp_path, run=fake_sips_ok, platform="darwin").rglob("*.html"))
    assert len(pages) == 2 + 1 + 1 + 1
    assert all('<meta name="robots" content="noindex">' in p.read_text(encoding="utf-8") for p in pages)


def test_publish_never_copies_private_files(load, tmp_path):
    pg = load("pages")
    three_days(tmp_path)
    folder = tmp_path / "2026/10/10"
    (folder / "b.heic").write_bytes(b"heic")
    (folder / "b.jpg").write_bytes(gps_jpeg())
    (folder / "c.png").write_bytes(png_with_text())
    (folder / ".縮圖").mkdir()
    (folder / ".縮圖" / "a.jpg.jpg").write_bytes(b"thumb")
    (folder / ".history").mkdir()
    (folder / ".history" / "行程-20261014-093000.txt").write_text("舊的", encoding="utf-8")
    write_day(tmp_path, "2026-10-10", 心情="😢\n很私人")
    out = pg.publish(tmp_path, run=fake_sips_ok, platform="darwin")
    files = [p for p in out.rglob("*") if p.is_file()]
    assert {p.suffix for p in files} <= {".html", ".jpg", ".png", ".gif"}
    assert not any(p.name in ("公開",) or p.suffix in (".txt", ".heic", ".heif") or ".history" in p.parts
                   or ".縮圖" in p.parts for p in out.rglob("*"))
    assert sorted(p.name for p in (out / "2026/10/10").iterdir()) == ["a.jpg", "b.jpg", "c.png", "index.html"]
    assert b"secret" not in (out / "2026/10/10/c.png").read_bytes() and b"Exif" not in (out / "2026/10/10/b.jpg").read_bytes()


def test_unpublishing_removes_the_day_and_relinks_the_public_neighbours(load, tmp_path):   # 第 5 條（公開版）
    pg = load("pages")
    three_days(tmp_path, public=("2026-10-10", "2026-10-14", "2026-10-20"))
    out = pg.publish(tmp_path, run=fake_sips_ok, platform="darwin")
    assert (out / "2026/10/14/index.html").exists()
    load_diary().set_public(tmp_path, "2026-10-14", False)
    pg.publish(tmp_path, run=fake_sips_ok, platform="darwin")
    assert not (out / "2026/10/14").exists()
    page = (out / "2026/10/10/index.html").read_text(encoding="utf-8")
    assert "../../../2026/10/20/index.html" in page and "2026-10-14" not in page
    assert "寫在 2026-10-14" not in (out / "index.html").read_text(encoding="utf-8")


def test_public_images_are_stripped_and_only_redone_when_newer(load, tmp_path):
    pg, calls = load("pages"), []
    three_days(tmp_path, public=("2026-10-10",))

    def run(argv, **kw):
        calls.append(argv)
        return fake_sips_ok(argv, **kw)

    out = pg.publish(tmp_path, run=run, platform="darwin")
    published = out / "2026/10/10/a.jpg"
    assert [c[:3] for c in calls] == [["sips", "-Z", "1600"]] and b"\xff\xe1" not in published.read_bytes()
    before = published.stat().st_mtime
    pg.publish(tmp_path, run=run, platform="darwin")
    assert len(calls) == 1 and published.stat().st_mtime == before
    src = tmp_path / "2026/10/10/a.jpg"
    os.utime(src, (before + 10, before + 10))
    pg.publish(tmp_path, run=run, platform="darwin")
    assert len(calls) == 2


def test_image_that_cannot_be_published_is_one_line_in_problems(load, tmp_path):
    pg = load("pages")
    folder = write_day(tmp_path, "2026-10-10", 行程="x")
    (folder / "x.gif").write_bytes(b"BM not a gif")
    (folder / "y.heic").write_bytes(b"heic")
    (folder / "z.heic").write_bytes(b"heic")
    (folder / "z.jpg").write_bytes(gps_jpeg())
    load_diary().set_public(tmp_path, "2026-10-10", True)
    problems = []
    out = pg.publish(tmp_path, run=fake_sips_ok, platform="darwin", problems=problems)
    assert problems == ["2026-10-10 x.gif：沒放上網路：不是 JPEG、PNG、GIF",
                        "2026-10-10 y.heic：沒放上網路：HEIC 不放上網路，轉成 JPG 才會"]
    page = (out / "2026/10/10/index.html").read_text(encoding="utf-8")
    assert "x.gif" not in page and "y.heic" not in page and 'src="z.jpg"' in page
    assert sorted(p.name for p in (out / "2026/10/10").iterdir()) == ["index.html", "z.jpg"]


def test_publish_with_no_public_days_leaves_an_empty_site(load, tmp_path):
    pg = load("pages")
    three_days(tmp_path, public=())
    out = pg.publish(tmp_path, run=fake_sips_ok, platform="darwin")
    assert [p.name for p in out.iterdir()] == ["index.html"]


# ── 程序：面板裡另開程序、自己的程序裡開頁面、已經開著就叫到最前面（D89） ──

PS = "  101 /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 {run} {folder}\n  202 /usr/bin/python3 /x/main.py\n"


def with_run_py(home):
    run_py = home / "modules" / "互通" / "run.py"
    run_py.parent.mkdir(parents=True, exist_ok=True)
    run_py.write_text("", encoding="utf-8")
    return run_py


def test_in_the_panel_process_launches_detached_with_the_env(load, home, tmp_path):
    mod, app, folder = load("iplot"), CalApp(home), tmp_path / "行事曆"
    run_py, launched = with_run_py(home), []
    mod.open_or_focus(app, folder, environ={"PATH": "/bin"}, ps=lambda: "",
                      popen=lambda argv, **kw: launched.append((argv, kw)), activate=never, platform="darwin", me=999)
    [(argv, kw)] = launched
    assert argv == [sys.executable, str(run_py), str(folder)]
    assert kw["env"] == {"PATH": "/bin", "IPLOT_CALENDAR": "1"} and kw["start_new_session"] is True
    assert (kw["stdin"], kw["stdout"], kw["stderr"]) == (subprocess.DEVNULL,) * 3 and app.logs == ["打開行事曆"] and app.pages == []


def test_without_interop_says_one_sentence_and_does_not_launch(load, home, tmp_path):
    mod, app = load("iplot"), CalApp(home)
    mod.open_or_focus(app, tmp_path / "行事曆", environ={}, ps=lambda: "", popen=never, activate=never, me=999)
    assert app.logs == ["行事曆要用「互通」另開視窗：到工作坊裝「互通」"]


def test_a_launch_that_fails_is_one_sentence(load, home, tmp_path):
    mod, app = load("iplot"), CalApp(home)
    with_run_py(home)

    def popen(argv, **kw):
        raise OSError("沒有這個程式")

    mod.open_or_focus(app, tmp_path / "行事曆", environ={}, ps=lambda: "", popen=popen, activate=never, me=999)
    assert app.logs == ["打不開行事曆：沒有這個程式"]


def test_in_own_process_removes_the_env_first_writes_pid_opens_the_page_then_removes_pid(load, home, tmp_path):
    mod, app, env, seen = load("iplot"), CalApp(home), {"IPLOT_CALENDAR": "1", "HOME": "/h"}, []
    folder = tmp_path / "行事曆"
    folder.mkdir()
    (folder / "page.html").write_text("<title>行事曆</title>", encoding="utf-8")
    app.on_page = lambda: seen.append((dict(env), (folder / ".pid").read_text(encoding="utf-8")))
    marker = object()
    mod.open_or_focus(app, folder, environ=env, ps=lambda: "", popen=never, activate=never, me=999, api=marker)
    assert seen == [({"HOME": "/h"}, str(os.getpid()))] and not (folder / ".pid").exists()
    assert app.pages == [("行事曆", "<title>行事曆</title>", marker)] and app.logs == []


def test_pid_is_removed_even_if_the_page_raises(load, home, tmp_path):
    mod, app = load("iplot"), CalApp(home)
    folder = tmp_path / "行事曆"
    folder.mkdir()
    (folder / "page.html").write_text("x", encoding="utf-8")

    def boom():
        raise RuntimeError("頁面壞了")

    app.on_page = boom
    with pytest.raises(RuntimeError):
        mod.open_or_focus(app, folder, environ={"IPLOT_CALENDAR": "1"}, ps=lambda: "", popen=never, activate=never,
                          me=999, api=object())
    assert not (folder / ".pid").exists()


def test_a_live_calendar_is_brought_forward_and_nothing_new_is_opened(load, home, tmp_path):
    mod, app, folder = load("iplot"), CalApp(home), tmp_path / "行事曆"
    folder.mkdir()
    (folder / ".pid").write_text("101", encoding="utf-8")
    activated = []
    mod.open_or_focus(app, folder, environ={"IPLOT_CALENDAR": "1"},
                      ps=lambda: PS.format(run=home / "modules/互通/run.py", folder=folder), popen=never,
                      activate=lambda pid, platform: activated.append(pid) or True, platform="darwin", me=999)
    assert activated == [101] and app.logs == ["行事曆已經開著"] and app.pages == []


def test_a_live_calendar_that_will_not_come_forward_says_where_to_find_it(load, home, tmp_path):
    mod, app, folder = load("iplot"), CalApp(home), tmp_path / "行事曆"
    folder.mkdir()
    (folder / ".pid").write_text("101", encoding="utf-8")
    mod.open_or_focus(app, folder, environ={}, ps=lambda: PS.format(run="/i/modules/互通/run.py", folder=folder),
                      popen=never, activate=lambda pid, platform: False, platform="darwin", me=999)
    assert app.logs == [mod.ALREADY_BEHIND] and mod.ALREADY_BEHIND.startswith("行事曆已經開著（在 Dock 上找")


def test_a_dead_pid_opens_a_new_one(load, home, tmp_path):
    mod, app, folder, launched = load("iplot"), CalApp(home), tmp_path / "行事曆", []
    with_run_py(home)
    folder.mkdir()
    (folder / ".pid").write_text("101", encoding="utf-8")
    mod.open_or_focus(app, folder, environ={}, ps=lambda: "  202 /usr/bin/python3 /x/main.py\n",
                      popen=lambda argv, **kw: launched.append(argv), activate=never, platform="darwin", me=999)
    assert len(launched) == 1 and app.logs == ["打開行事曆"]


def test_a_reused_pid_whose_command_is_not_the_calendar_counts_as_stale(load, home, tmp_path):   # Review Focus 3
    mod, app, folder, launched = load("iplot"), CalApp(home), tmp_path / "行事曆", []
    with_run_py(home)
    folder.mkdir()
    (folder / ".pid").write_text("202", encoding="utf-8")
    mod.open_or_focus(app, folder, environ={}, ps=lambda: PS.format(run="/i/modules/互通/run.py", folder=folder),
                      popen=lambda argv, **kw: launched.append(argv), activate=never, platform="darwin", me=999)
    assert len(launched) == 1


def test_running_pid_matches_an_nfd_path_in_ps_output(load, tmp_path):     # Review Focus 3（NFC/NFD）
    mod, folder = load("iplot"), tmp_path / "行事曆"
    nfd = unicodedata.normalize("NFD", str(folder))
    assert mod.running_pid(folder, pid_file_with(tmp_path, "101"), ps=lambda: f"  101 python3 /i/modules/互通/run.py {nfd}\n",
                           me=999) == 101
    assert mod.running_pid(folder, pid_file_with(tmp_path, "101"), ps=lambda: f"  101 python3 /i/main.py {nfd}\n",
                           me=999) is None


def test_running_pid_ignores_itself_and_garbage(load, tmp_path):
    mod = load("iplot")
    assert mod.running_pid(tmp_path, pid_file_with(tmp_path, "101"), ps=never, me=101) is None
    assert mod.running_pid(tmp_path, pid_file_with(tmp_path, "abc"), ps=never, me=999) is None
    assert mod.running_pid(tmp_path, tmp_path / "沒有.pid", ps=never, me=999) is None


def test_elsewhere_a_live_calendar_is_only_announced_never_activated_or_relaunched(load, home, tmp_path):
    mod, app, folder = load("iplot"), CalApp(home), tmp_path / "行事曆"
    folder.mkdir()
    (folder / ".pid").write_text("101", encoding="utf-8")
    mod.open_or_focus(app, folder, environ={}, ps=lambda: PS.format(run="/i/modules/互通/run.py", folder=folder),
                      popen=never, activate=never, platform="linux", me=999)
    assert app.logs == [mod.ALREADY_BEHIND]


def test_helper_names_do_not_shadow_stdlib():                                # 設計第 15 節第 3 條
    assert "site" in sys.stdlib_module_names and "calendar" in sys.stdlib_module_names
    for name in ("diary", "pages", "photos"):
        assert name not in sys.stdlib_module_names and (CALENDAR / f"{name}.py").exists(), name
    assert not (CALENDAR / "site.py").exists()


def test_iplot_runs_through_the_real_runner(home, tmp_path, monkeypatch):    # 第 3 條；跑的是複本，repo 的 modules/行事曆 一個檔都不動
    from core.app import App
    from core.runner import run_module
    from core.scan import module_info

    copy = home / "modules" / "行事曆"
    shutil.copytree(CALENDAR, copy, ignore=shutil.ignore_patterns(".pid", "設定.json", "__pycache__"))
    (copy / "設定.json").write_text(json.dumps({"資料夾": str(tmp_path / "資料")}, ensure_ascii=False), encoding="utf-8")
    before = sorted(p.name for p in CALENDAR.iterdir())
    for n in NAMES:
        monkeypatch.delitem(sys.modules, n, raising=False)
    seen = []

    class View(conftest.FakeView):
        def page(self, title, html, api):
            seen.append(api)
            api.rebuild()   # 會用到 pages；資料夾還沒建 → 只寫綜合

    monkeypatch.setenv("IPLOT_CALENDAR", "1")                                 # 第 2 步：寫 .pid、開頁面；沒有 .pid 所以不叫 ps
    info = module_info(copy, home / "modules", "here")
    result = run_module(info, App(conftest.FakeCore(home, DEFAULT_CONFIG, View()), info))
    assert result.ok, result.error
    assert seen and type(seen[0]).__name__ == "Api" and not (copy / ".pid").exists()
    assert (tmp_path / "資料" / "index.html").exists() and "IPLOT_CALENDAR" not in os.environ
    assert sorted(p.name for p in CALENDAR.iterdir()) == before


def test_iplot_imports_helpers_at_module_level(load):                       # 第 4 條
    mod = load("iplot")
    assert all(Path(getattr(mod, n).__file__).parent == CALENDAR for n in ("diary", "pages", "photos"))
    assert not re.search(r"^\s+(import |from \S+ import )", inspect.getsource(mod.Api), re.M)


def test_icon_png_is_a_small_valid_png():                                   # 設計第 15 節第 9 條（Task 0 Step 9 過了）
    data = (CALENDAR / "icon.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and len(data) < 1024 * 1024
    assert struct.unpack(">II", data[16:24]) == (256, 256)


def test_set_dock_icon_is_mac_only(load):
    assert load("iplot").set_dock_icon(CALENDAR / "icon.png", platform="linux") is False


# ── Api：設計第 7 節的 15 個方法；一把鎖、模組列自己掃（設計第 15 節第 4、7 條） ──

FIFTEEN = {"month", "year", "day", "save", "set_public", "add_image", "remove_image", "open_page", "publish",
           "modules", "launch", "settings", "change_folder", "reveal_folder", "rebuild"}


def test_api_exposes_exactly_the_fifteen_methods(load):
    assert {n for n in vars(load("iplot").Api) if not n.startswith("_")} == FIFTEEN


def test_month_returns_today_the_days_and_the_folder(load, tmp_path):
    a = api(load, tmp_path)
    write_day(tmp_path / "資料", "2026-10-14", 心情="🙂\n", 行程="開會")
    got = a.month("2026-10")
    assert got == {"ym": "2026-10", "today": "2026-10-14", "folder": str((tmp_path / "資料").resolve()),
                   "days": {"14": {"mood": "🙂", "first": "開會", "images": False, "public": False}}}


def test_month_sets_the_dock_icon_once(load, tmp_path):                       # 設計第 15 節第 9 條（Task 0 Step 9 過了）
    calls = []
    a = api(load, tmp_path, dock_icon=lambda path, platform: calls.append((path, platform)) or True)
    a.month("2026-10")
    a.month("2026-11")
    assert calls == [(CALENDAR / "icon.png", "darwin")]
    b = api(load, tmp_path, platform="linux", dock_icon=never)
    b.month("2026-10")


def test_year_lists_moods_per_month(load, tmp_path):
    a = api(load, tmp_path)
    write_day(tmp_path / "資料", "2026-10-14", 心情="🙂\n", 行程="x")
    write_day(tmp_path / "資料", "2026-03-02", 做了="y")
    assert a.year("2026") == {"y": "2026", "months": {"03": {"02": ""}, "10": {"14": "🙂"}}}


def test_day_returns_the_fields_and_thumbnails_as_data_urls(load, tmp_path):  # Task 0 Step 4 的退路
    a = api(load, tmp_path)
    folder = write_day(tmp_path / "資料", "2026-10-14", 行程="開會", 心情="😐\n普通")
    (folder / "a.png").write_bytes(b"png")
    got = a.day("2026-10-14")
    assert (got["行程"], got["mood"], got["note"], got["public"]) == ("開會", "😐", "普通", False)
    assert got["images"] == [{"name": "a.png", "src": "data:image/jpeg;base64,cG5n"}]
    assert "file:" not in json.dumps(got)


def test_save_writes_the_four_fields_and_rebuilds_the_pages(load, tmp_path):
    a, root = api(load, tmp_path), tmp_path / "資料"
    got = a.save("2026-10-14", {"行程": "開會", "看到": "雲", "做了": "寫字", "mood": "🙂", "note": "好", "路徑": "/etc"})
    assert got == {"saved": ["行程", "心情", "看到", "做了"], "unreadable": []}
    day = load("diary").read_day(root, "2026-10-14")
    assert (day["行程"], day["看到"], day["做了"], day["mood"], day["note"]) == ("開會", "雲", "寫字", "🙂", "好")
    for page in ("2026/10/14/index.html", "2026/10/index.html", "2026/index.html", "index.html"):
        assert (root / page).exists(), page
    assert a.save("2026-10-14", {"行程": "開會"}) == {"saved": [], "unreadable": []}   # 沒給 mood/note：心情不動
    assert load("diary").read_day(root, "2026-10-14")["mood"] == "🙂"


def test_save_reports_unreadable_fields_as_sentences(load, tmp_path):
    a = api(load, tmp_path)
    folder = write_day(tmp_path / "資料", "2026-10-14")
    (folder / "做了.txt").write_bytes(b"\xff\xfe")
    got = a.save("2026-10-14", {"做了": "x"})
    assert got == {"saved": [], "unreadable": [f"讀不到這個檔（不是 UTF-8），沒有覆寫它：{(folder / '做了.txt').resolve()}"]}


def test_save_into_a_missing_or_read_only_folder_is_one_sentence_and_keeps_the_text(load, tmp_path):  # Review Focus 5
    a, root = api(load, tmp_path), tmp_path / "資料"
    root.mkdir()
    root.chmod(0o500)                     # 唯讀：子資料夾建不起來（跟外接硬碟拔掉、權限改了同一條路）
    try:
        got = a.save("2026-10-14", {"行程": "x"})
    finally:
        root.chmod(0o700)
    assert got["error"].startswith("存不進去：") and got["error"].endswith("。字還在，等一下會再試")
    assert list(root.iterdir()) == [] and a._app.logs == []


def test_save_keeps_history_keep_versions_from_app_config(load, tmp_path):
    a = api(load, tmp_path, history_keep=2)
    for text in ("v1", "v2", "v3", "v4"):
        a.save("2026-10-14", {"行程": text})
    assert len(list((tmp_path / "資料/2026/10/14/.history").glob("行程-*.txt"))) == 2


def test_dates_are_checked_by_regex_and_datetime_at_the_api(load, tmp_path):
    a = api(load, tmp_path)
    for call in (lambda: a.day("2026-02-30"), lambda: a.day("2026-2-3"), lambda: a.month("2026-13"),
                 lambda: a.year("26"), lambda: a.save("../../etc", {"行程": "x"}), lambda: a.set_public(None, True)):
        assert call()["error"].startswith("日期格式不對：")
    assert a.day("2024-02-29")["date"] == "2024-02-29"
    assert not (tmp_path / "資料").exists()


def test_api_calls_do_not_overlap(load, tmp_path, monkeypatch):                     # Review Focus 2、第 4 條
    spans, d = [], load("diary")

    def slow_open(path):
        t = time.perf_counter()
        time.sleep(0.2)
        spans.append(("open", t, time.perf_counter()))

    real = d.save_day
    monkeypatch.setattr(d, "save_day", lambda *a, **k: (spans.append(("save", time.perf_counter(), None)), real(*a, **k))[1])
    a = api(load, tmp_path)
    a._app.open = slow_open
    write_day(tmp_path / "資料", "2026-10-14", 行程="x")
    a.rebuild()
    t1, _ = in_thread(lambda: a.open_page("day", "2026-10-14"))
    t2, _ = in_thread(lambda: (time.sleep(0.05), a.save("2026-10-14", {"行程": "y"}))[1])
    t1.join(3)
    t2.join(3)
    [open_span] = [s for s in spans if s[0] == "open"]
    [save_span] = [s for s in spans if s[0] == "save"]
    assert save_span[1] >= open_span[2]


def test_change_folder_releases_the_lock_while_the_dialog_is_open(load, tmp_path):   # 第 4 條
    a, answer = api(load, tmp_path), threading.Event()
    a._app.choose_folder = lambda: (answer.wait(3), tmp_path / "新")[1]
    t, box = in_thread(a.change_folder)
    time.sleep(0.05)
    start = time.perf_counter()
    assert a.save("2026-10-14", {"行程": "舊資料夾"}) == {"saved": ["行程"], "unreadable": []}
    assert time.perf_counter() - start < 0.5
    answer.set()
    t.join(3)
    assert box == [{"folder": str((tmp_path / "新").resolve()), "public_days": 0}]
    assert (tmp_path / "資料/2026/10/14/行程.txt").exists() and a.settings()["folder"] == str((tmp_path / "新").resolve())


def test_api_writes_absolute_paths_even_when_cwd_changes(load, tmp_path, monkeypatch):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    monkeypatch.chdir(tmp_path / "a")
    a = load("iplot").Api(CalApp(tmp_path / "iPLoT"), pathlib_rel("設定.json"), default_root=pathlib_rel("資料"),
                          run=fake_sips_ok, popen=never, platform="darwin", environ={})
    monkeypatch.chdir(tmp_path / "b")     # app.open 跑「作業系統」時 cwd 會暫時換掉
    a.save("2026-10-14", {"行程": "x"})
    a.change_folder()
    assert (tmp_path / "a/資料/2026/10/14/行程.txt").exists() and not (tmp_path / "b/資料").exists()


def pathlib_rel(name):
    return Path(name)


def test_set_public_toggles_and_rebuilds(load, tmp_path):
    a, root = api(load, tmp_path), tmp_path / "資料"
    write_day(root, "2026-10-14", 行程="x")
    assert a.set_public("2026-10-14", True) == {"public": True} and (root / "2026/10/14/公開").exists()
    assert (root / "2026/10/14/index.html").exists()
    assert a.set_public("2026-10-14", False) == {"public": False} and not (root / "2026/10/14/公開").exists()


def test_add_image_decodes_base64_and_rejects_junk(load, tmp_path):
    import base64
    a = api(load, tmp_path)
    got = a.add_image("2026-10-14", "a.jpg", "data:image/jpeg;base64," + base64.b64encode(gps_jpeg()).decode())
    assert [i["name"] for i in got["images"]] == ["a.jpg"] and "error" not in got
    assert (tmp_path / "資料/2026/10/14/a.jpg").read_bytes() == gps_jpeg() and (tmp_path / "資料/2026/10/14/index.html").exists()
    assert a.add_image("2026-10-14", "b.jpg", "not base64!")["error"] == "b.jpg：不是圖片"
    big = base64.b64encode(b"\0" * (30 * 1024 * 1024 + 1)).decode()
    assert a.add_image("2026-10-14", "c.jpg", big)["error"] == "c.jpg：太大（超過 30 MB）"


def test_remove_image_trashes_the_jpg_and_the_heic_together(load, tmp_path):
    a = api(load, tmp_path)
    folder = write_day(tmp_path / "資料", "2026-10-14", 行程="x")
    for name in ("a.jpg", "a.HEIC", "b.png"):
        (folder / name).write_bytes(b"x")
    a.day("2026-10-14")                                       # 做出縮圖
    assert (folder / ".縮圖" / "a.jpg.jpg").exists()
    got = a.remove_image("2026-10-14", "a.jpg")
    assert sorted(p.name for p in a._app.trashed) == ["a.HEIC", "a.jpg"] and [i["name"] for i in got["images"]] == ["b.png"]
    assert not (folder / ".縮圖" / "a.jpg.jpg").exists()
    a.remove_image("2026-10-14", "../b.png")                  # 只取 basename：拿掉的是這一天的 b.png，不是別處的
    a.remove_image("2026-10-14", "沒有.jpg")
    assert sorted(p.name for p in a._app.trashed) == ["a.HEIC", "a.jpg", "b.png"]


def test_open_page_builds_a_missing_page_then_opens_it(load, tmp_path):
    a, root = api(load, tmp_path), tmp_path / "資料"
    write_day(root, "2026-10-14", 行程="x")
    assert a.open_page("day", "2026-10-14") == {} and a._app.opened == [root.resolve() / "2026/10/14/index.html"]
    assert (root / "2026/10/14/index.html").exists()
    a.open_page("month", "2026-10")
    a.open_page("year", "2026")
    a.open_page("index", "")
    assert a._app.opened[1:] == [root.resolve() / p for p in ("2026/10/index.html", "2026/index.html", "index.html")]
    assert "error" in a.open_page("x", "2026") and "error" in a.open_page("day", "2026-13-01") and len(a._app.opened) == 4


def test_publish_requires_a_public_day_then_opens_the_folder(load, tmp_path):
    a, root = api(load, tmp_path), tmp_path / "資料"
    write_day(root, "2026-10-14", 行程="x")
    assert a.publish() == {"error": "還沒有打開「公開」的日子"} and a._app.opened == []
    a.set_public("2026-10-14", True)
    got = a.publish()
    assert got == {"days": 1, "folder": str(root.resolve() / "發佈"), "problems": [],
                   "note": "上傳方式還沒設定：把『發佈』裡的東西放到網頁空間"}
    assert a._app.opened == [root.resolve() / "發佈"] and a.settings()["public_days"] == 1


def test_modules_excludes_the_os_module_and_itself_and_flags_the_panel(load, home, tmp_path):
    for name in ("開工", "作業系統", "行事曆", "主控面板"):
        conftest.make_module(home / "modules", name)
    a = api(load, tmp_path, home=home)
    assert a.modules() == {"modules": [{"name": "開工", "icon": "開", "title": "開工"}], "panel": True}
    conftest.make_module(home.parent, "主控面板")             # 上一層（ROOTS 的 ".."）也有一個 → 不知道是哪一個
    assert a.modules()["panel"] is False


def test_modules_sees_a_module_installed_after_the_page_opened(load, home, tmp_path):    # 第 7 條
    a = api(load, tmp_path, home=home)
    assert a.modules()["modules"] == []
    conftest.make_module(home / "modules", "新的", 'ICON = "🌱"\ndef run(app):\n    pass\n')
    assert a.modules()["modules"] == [{"name": "新的", "icon": "🌱", "title": "新的"}]


def test_launch_runs_run_py_without_the_env_and_only_for_known_names(load, home, tmp_path):
    conftest.make_module(home / "modules", "開工")
    conftest.make_module(home / "modules", "主控面板")
    run_py, launched = with_run_py(home), []
    a = api(load, tmp_path, home=home, popen=lambda argv, **kw: launched.append((argv, kw)),
            environ={"IPLOT_CALENDAR": "1", "HOME": "/h"})
    assert a.launch("開工") == {} and launched[0][0] == [sys.executable, str(run_py), str(home / "modules" / "開工")]
    assert launched[0][1]["env"] == {"HOME": "/h"} and launched[0][1]["start_new_session"] is True
    assert a.launch("主控面板") == {} and len(launched) == 2           # 「圖示面板」那顆鈕
    assert a.launch("沒有") == {"error": "找不到「沒有」（可能被改名或刪掉了）"} and len(launched) == 2
    assert a.launch("作業系統")["error"] == "找不到「作業系統」（可能被改名或刪掉了）"
    conftest.make_module(home / "modules", "後來的")                   # 每點一次重掃一次
    assert a.launch("後來的") == {} and len(launched) == 3


def test_settings_change_folder_and_reveal(load, tmp_path):
    a = api(load, tmp_path)
    assert a.settings() == {"folder": str((tmp_path / "資料").resolve()), "public_days": 0}
    assert a.change_folder() == a.settings() and not (tmp_path / "設定.json").exists()   # 按了取消
    a._app.folder_answer = tmp_path / "新"
    assert a.change_folder()["folder"] == str((tmp_path / "新").resolve())
    assert json.loads((tmp_path / "設定.json").read_text(encoding="utf-8")) == {"資料夾": str(tmp_path / "新")}
    assert a.reveal_folder() == {} and a._app.opened == [(tmp_path / "新").resolve()] and (tmp_path / "新").is_dir()


def test_rebuild_counts_pages(load, tmp_path):
    a = api(load, tmp_path)
    write_day(tmp_path / "資料", "2026-10-14", 行程="x")
    write_day(tmp_path / "資料", "2026-10-15", 行程="y")
    assert a.rebuild() == {"pages": 2 + 1 + 1 + 1}


def test_api_never_logs_while_the_page_is_open(load, home, tmp_path):
    a = api(load, tmp_path, home=home)
    a.save("2026-10-14", {"行程": "x"})
    a.add_image("2026-10-14", "壞.jpg", "!!")
    a.open_page("x", "")
    a.publish()
    a.launch("沒有")
    a.month("2026-10")
    a.day("2026-10-14")
    assert a._app.logs == []


# ── page.html：行事曆的畫面（靜態檢查；瀏覽器試走在 spikes/m5/page_harness.py） ──

def test_page_html_is_self_contained_and_never_uses_inner_html():
    html_text = page_html()
    assert not any(w in html_text for w in ("http://", "https://", "innerHTML", "outerHTML", "style.css",
                                            "insertAdjacentHTML", "document.write", "eval("))
    assert "prefers-color-scheme: dark" in html_text and "pywebviewready" in html_text and 'charset="utf-8"' in html_text


def test_page_html_calls_exactly_the_api_methods():
    html_text = page_html()
    assert set(re.findall(r'call\("(\w+)"', html_text)) == FIFTEEN
    assert "pywebview.api." not in html_text.replace("window.pywebview.api[name]", "")   # 只經 call()：保證順序


def test_page_html_has_the_five_moods_the_three_fields_and_the_sentences():
    html_text = page_html()
    assert all(m in html_text for m in ("😄", "🙂", "😐", "😟", "😢", "行程", "看到了什麼", "做了什麼", "公開", "看網頁",
                                        "發佈", "重建全部網頁", "換資料夾", "打開資料夾", "打開綜合網頁", "圖示面板"))
    assert "要放上網路的有 " in html_text and "產生發佈用的資料夾？" in html_text and "已存" in html_text
    assert "🌐" in html_text and "🖼" in html_text and "today" in html_text and "讀不到這個檔（不是 UTF-8），沒有覆寫它：" in html_text


def test_page_html_debounces_typing_and_rescans_modules_only_on_focus():       # 設計第 15 節第 8、7 條
    html_text = page_html()
    assert "1000" in html_text and "pagehide" in html_text
    assert html_text.count('call("modules"') == 1 and 'addEventListener("focus"' in html_text


def test_remove_image_leaves_an_unrelated_heic_with_the_same_stem(load, tmp_path):   # 審查 I3
    a = api(load, tmp_path)
    folder = write_day(tmp_path / "資料", "2026-10-14", 行程="x")
    for name in ("a.heic", "a.png"):
        (folder / name).write_bytes(b"x")
    a.remove_image("2026-10-14", "a.png")
    assert [p.name for p in a._app.trashed] == ["a.png"] and (folder / "a.heic").exists()


def test_jpeg_strip_keeps_only_image_segments_and_stops_at_the_end_of_the_image(load, tmp_path):   # 審查 I4
    p = load("photos")
    second = b"\xff\xd8" + _segment(0xE1, _exif_gps()) + b"\xff\xd9"          # Motion Photo、MPF 的第二張圖放在 EOI 之後
    scan = b"\x12\xff\x00\x34\xff\xd0\x56"                                    # 位元填充（FF 00）與 RST0 都是影像資料
    data = (b"\xff\xd8" + _segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
            + _segment(0xE1, _exif_gps()) + _segment(0xE6, b"GoPro GPMF GPS5 25.03 121.56")
            + _segment(0xFE, b"secret comment") + _segment(0xE2, b"ICC_PROFILE\x00\x01\x01icc")
            + _segment(0xE2, b"MPF\x00II*\x00") + _segment(0xEE, b"Adobe\x00\x64\x00\x00\x00\x00\x01")
            + _segment(0xDB, b"\x00" + bytes(range(1, 65))) + _segment(0xC2, b"\x08\x00\x01\x00\x01\x01\x01\x11\x00")
            + _segment(0xC4, b"\x00" + b"\x01" + bytes(15) + b"\x00") + _segment(0xDA, b"\x01\x01\x00\x00\x3f\x00") + scan
            + _segment(0xC4, b"\x10" + b"\x01" + bytes(15) + b"\x00") + _segment(0xDA, b"\x01\x01\x00\x00\x3f\x00") + scan
            + b"\xff\xd9" + second)
    (tmp_path / "a.jpg").write_bytes(data)
    p.strip_metadata(tmp_path / "a.jpg", tmp_path / "b.jpg")
    out = (tmp_path / "b.jpg").read_bytes()
    assert not any(k in out for k in (b"Exif", b"GoPro", b"secret", b"MPF"))
    assert all(k in out for k in (b"JFIF", b"ICC_PROFILE", b"Adobe")) and out.count(scan) == 2
    assert out.endswith(scan + b"\xff\xd9") and out.count(b"\xff\xd8") == 1


def test_png_strip_keeps_only_image_chunks_and_stops_at_iend(load, tmp_path):   # 審查 I4
    p = load("photos")
    base = png_with_text()
    iend = base.index(b"IEND") - 4
    data = (base[:iend] + _png_chunk(b"tIME", b"\x07\xea\x0a\x0e\x09\x1e\x00") + _png_chunk(b"caBX", b"c2pa")
            + base[iend:] + b"trailing Exif data after IEND")
    (tmp_path / "a.png").write_bytes(data)
    p.strip_metadata(tmp_path / "a.png", tmp_path / "b.png")
    out = (tmp_path / "b.png").read_bytes()
    assert not any(k in out for k in (b"tIME", b"caBX", b"trailing", b"tEXt", b"eXIf"))
    assert out.endswith(_png_chunk(b"IEND", b"")) and b"IHDR" in out and b"IDAT" in out
