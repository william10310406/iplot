"""行事曆的圖片：收進來（HEIC 轉 JPG）、畫面用的縮圖、公開版縮小並拿掉中繼資料（D91 的一部分）。

sips（macOS 內建）一律用清單參數、不經過 shell；測試把 run 換成假的。拿掉中繼資料是純 Python：
JPEG 丟 APP1（EXIF、XMP）與 APP13（IPTC），PNG 丟 eXIf、tEXt、iTXt、zTXt，GIF 照原樣。不 import core、不 import diary。"""

import base64
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

MAX_BYTES = 30 * 1024 * 1024
THUMB_SOURCE_MAX = 5 * 1024 * 1024  # 沒有 sips 時，原圖這麼小以內就直接當縮圖
SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".heic", ".heif")
PUBLISHABLE = (".jpg", ".jpeg", ".png", ".gif")
HEIC = (".heic", ".heif")
THUMBS = ".縮圖"
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}
TOO_BIG = "{name}：太大（超過 30 MB）"
NOT_IMAGE = "{name}：不是圖片"
NO_JPEG = "{name}：轉不成 JPG，Chrome 看不到"
JPEG_DROP = (0xE1, 0xED)
PNG_DROP = (b"eXIf", b"tEXt", b"iTXt", b"zTXt")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def clean_name(name: str) -> str:
    """只取 basename，拿掉 :、控制字元、開頭的點；空了就是「圖片」。其餘一個字都不改。"""
    base = re.split(r"[/\\]", str(name))[-1]
    base = "".join(c for c in base if c != ":" and c.isprintable())
    return base.lstrip(".") or "圖片"


def _taken(folder: Path, name: str) -> bool:
    """同名（不分大小寫）就算有了；同 stem 的 HEIC 與 JPG 算同一個名字（HEIC 轉出來的 JPG 會用那個 stem）。"""
    try:
        names = [p.name.lower() for p in folder.iterdir()]
    except OSError:
        return False
    stem, suffix = Path(name).stem.lower(), Path(name).suffix.lower()
    if name.lower() in names:
        return True
    linked = HEIC + (".jpg",)
    return suffix in linked and any(Path(n).stem == stem and Path(n).suffix in linked for n in names)


def unique_name(folder: Path, name: str) -> str:
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, n = name, 1
    while _taken(folder, candidate):
        n += 1
        candidate = f"{stem} {n}{suffix}"
    return candidate


def _write(path: Path, data: bytes) -> None:
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _sips(argv: list[str], out: Path, run) -> bool:
    try:
        done = run(argv, capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0 and out.exists()


def to_jpeg(path: Path, run=subprocess.run) -> Path | None:
    out = path.with_suffix(".jpg")
    return out if _sips(["sips", "-s", "format", "jpeg", str(path), "--out", str(out)], out, run) else None


def add_image(folder: Path, name: str, data: bytes, *, run=subprocess.run,
              platform: str = sys.platform) -> tuple[str | None, str | None]:
    """收一張圖：回 (存成的檔名, 問題那一句或 None)。"""
    name = clean_name(name)
    if len(data) > MAX_BYTES:
        return None, TOO_BIG.format(name=name)
    if Path(name).suffix.lower() not in SUFFIXES:
        return None, NOT_IMAGE.format(name=name)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = unique_name(folder, name)
    _write(folder / name, data)
    heic = Path(name).suffix.lower() in HEIC
    if heic and (platform != "darwin" or to_jpeg(folder / name, run) is None):
        return name, NO_JPEG.format(name=name)
    return name, None


def shrink(src: Path, dst: Path, run=subprocess.run) -> bool:
    return _sips(["sips", "-Z", "1600", str(src), "--out", str(dst)], dst, run)


def _strip_jpeg(data: bytes) -> bytes:
    out, i = bytearray(data[:2]), 2
    while i < len(data):
        if data[i] != 0xFF or i + 4 > len(data):
            raise ValueError("JPEG 的段落壞了")
        marker = data[i + 1]
        if marker == 0xDA:  # SOS 之後是影像資料，照抄到結尾
            out += data[i:]
            return bytes(out)
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if marker not in JPEG_DROP:
            out += data[i:i + 2 + length]
        i += 2 + length
    raise ValueError("JPEG 沒有影像資料")


def _strip_png(data: bytes) -> bytes:
    out, i = bytearray(PNG_SIGNATURE), len(PNG_SIGNATURE)
    while i < len(data):
        if i + 8 > len(data):
            raise ValueError("PNG 的區塊壞了")
        length, kind = struct.unpack(">I", data[i:i + 4])[0], data[i + 4:i + 8]
        end = i + 12 + length
        if kind not in PNG_DROP:
            out += data[i:end]
        i = end
    return bytes(out)


def strip_metadata(src: Path, dst: Path) -> None:
    """拿掉拍攝地點等中繼資料，寫到 dst（先寫暫存再換）；不是 JPEG、PNG、GIF 丟 ValueError。"""
    data = Path(src).read_bytes()
    if data[:2] == b"\xff\xd8":
        out = _strip_jpeg(data)
    elif data[:8] == PNG_SIGNATURE:
        out = _strip_png(data)
    elif data[:4] == b"GIF8":
        out = data
    else:
        raise ValueError("不是 JPEG、PNG、GIF")
    _write(Path(dst), out)


def public_copy(src: Path, dst: Path, *, run=subprocess.run, platform: str = sys.platform) -> None:
    """公開版的一張圖：macOS 上 JPEG／PNG 先縮到長邊 1600，再拿掉中繼資料；GIF 與其他系統只拿掉中繼資料。"""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    source = Path(src)
    tmp = dst.with_name(f".{dst.name}.small-{os.getpid()}{dst.suffix}")
    try:
        if platform == "darwin" and source.suffix.lower() in (".jpg", ".jpeg", ".png") and shrink(source, tmp, run):
            source = tmp
        strip_metadata(source, dst)
    finally:
        tmp.unlink(missing_ok=True)


def thumbnail(src: Path, dst: Path, run=subprocess.run) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    return _sips(["sips", "-s", "format", "jpeg", "-Z", "320", str(src), "--out", str(dst)], dst, run)


def thumbnail_url(folder: Path, name: str, *, run=subprocess.run, platform: str = sys.platform) -> str | None:
    """畫面用的縮圖，以 data URL 給頁面（app.page 的頁面顯示不了 file:// 的圖，Task 0 Step 4）。
    macOS：sips -Z 320 做到 .縮圖/<檔名>.jpg，原圖比較新才重做；其他系統：小的 JPEG／PNG／GIF 原圖直接用，否則 None。"""
    src = Path(folder) / name
    if platform == "darwin":
        thumb = Path(folder) / THUMBS / f"{name}.jpg"
        try:
            fresh = thumb.exists() and thumb.stat().st_mtime >= src.stat().st_mtime
        except OSError:
            return None
        if not fresh and not thumbnail(src, thumb, run):
            return None
        return "data:image/jpeg;base64," + base64.b64encode(thumb.read_bytes()).decode("ascii")
    mime = MIME.get(src.suffix.lower())
    try:
        if mime is None or src.stat().st_size > THUMB_SOURCE_MAX:
            return None
        return f"data:{mime};base64," + base64.b64encode(src.read_bytes()).decode("ascii")
    except OSError:
        return None
