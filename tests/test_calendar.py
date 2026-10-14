"""工作坊模組「行事曆」（modules/行事曆）：資料、圖片、網頁、程序、Api、畫面（D89–D93）。
模組裡的檔用 load("名字") 當一般模組 import（跟 runner 一樣走 sys.path，不寫 .pyc）。絕不碰 ~/Documents/行事曆、
不在 repo 的 modules/行事曆 裡寫檔：資料夾一律在 tmp_path；sips、ps、Popen、app.open、app.trash、AppKit 一律換成假的。"""

import dataclasses
import datetime
import importlib
import os
import shutil
import struct
import sys
import threading
import types
import zlib
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
