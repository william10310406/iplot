"""舊格式作業的執行器：python hk_tk.py <資料夾> <HKn> 開一個 Tk 視窗跑 <資料夾>/t2026fscSpace/HKn.txt。

老師的啟動器 t2026fsc.txt 只留下讓 HKn.txt 活得了的那幾行（設計第 5 節）：一個 800×800 的視窗、
LF_subWIN 那個框、HKn.txt 要的全域；exec 之後叫 HKn()，HKn.txt 自己的那排鈕原樣留著。
學生的檔出錯時跳一個框說哪裡錯（語法錯在第幾行、缺哪個套件、pip 要打什麼），print 的東西同時寫進
<資料夾>/執行紀錄.txt。

這個檔頂層只 import 標準庫、而且不 import tkinter：課程模組與墊片在 iPLoT 的面板程序裡 import 它，
面板擋 tkinter；tkinter 只在真的開視窗的函式裡 import。
"""

import contextlib
import dataclasses
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

KIT = "t2026fscSpace"
LOG = "執行紀錄.txt"
HK_RE = re.compile(r"^(HK\d+)\.txt$")
NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"  # pip 名只接這些字元（設計第 6 節），不經 shell
NO_INSTALL = "HK_NO_INSTALL"  # 設了就不建 venv、不跑 pip，缺了只報（測試用）
GLOBALS = ("LF", "LF_subWIN", "t2026fscHOMEDIR", "os", "sys", "tkinter")  # 老師的啟動器給 HKn.txt 的全域
USAGE = "用法：python hk_tk.py <資料夾> <HKn>    （跑 <資料夾>/t2026fscSpace/HKn.txt）"


def hk_of(folder: Path) -> str | None:
    """folder/t2026fscSpace 裡唯一一個 HK<n>.txt 的 HK<n>；沒有或不只一個回 None。"""
    try:
        found = [m.group(1) for m in map(HK_RE.match, os.listdir(Path(folder) / KIT)) if m]
    except OSError:
        return None
    return found[0] if len(found) == 1 else None


def course_root(start: Path) -> Path | None:
    """從 start 自己開始往上找，第一個有 hk_tk.py 的資料夾（課程資料夾）；找不到回 None。"""
    start = Path(start).resolve()
    return next((p for p in (start, *start.parents) if (p / "hk_tk.py").is_file()), None)


def python_in(venv_dir: Path) -> Path:
    """venv 裡 Python 的位置（不查在不在）。"""
    return Path(venv_dir) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def venv_python(course: Path | None) -> Path | None:
    """課程 .venv 的 Python；還沒建（或 course 是 None）回 None。"""
    if course is None:
        return None
    python = python_in(Path(course) / ".venv")
    return python if python.is_file() else None


# 每份作業與每個學生資料夾裡的 iplot.py（匯入、收作業時產生；HK 那一層與學生那一層同一份，設計第 5 節）
STUB = '''"""按下去用課程的 Python 另開視窗跑這個資料夾的 t2026fscSpace/HKn.txt（舊格式）。收作業按「科學計算」底下的「收作業」。"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
COURSE = next(p for p in HERE.parents if (p / "hk_tk.py").is_file())
sys.modules.pop("hk_tk", None)  # 每次都讀課程資料夾裡現在那一份
sys.path.insert(0, str(COURSE))
try:
    import hk_tk
finally:
    sys.path.remove(str(COURSE))


def run(app):
    hk_tk.launch(app, HERE)  # 用課程 .venv 的 Python 另開視窗；沒有 .venv 就用 iPLoT 的 Python 並說一句


def on_files(app, paths):
    hk_tk.collect(app, paths, HERE)  # 收作業（只有 HKn 那一層有意義）
'''
STUB_MARK = "hk_tk.launch(app, HERE)"  # 有這一行的 iplot.py 是墊片（舊版本的也算），可以換成這一版


def write_stub(folder: Path) -> Path:
    """寫 folder/iplot.py 墊片。已經是這一版就不碰；是舊版本的墊片就換；是別的檔（新格式的作業本身）不碰。"""
    file = Path(folder) / "iplot.py"
    if file.exists():
        old = file.read_text(encoding="utf-8", errors="replace")
        if old == STUB or STUB_MARK not in old:
            return file
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(STUB, encoding="utf-8")
    return file


def launch(app, folder: Path, popen=None) -> None:
    """墊片的 run：用課程 .venv 的 Python 另開一個程序跑 hk_tk.py <folder> <HKn>，不等它，立刻回來。"""
    folder = Path(folder)
    hk = hk_of(folder)
    if hk is None:
        app.log(f"{folder.name}：這個資料夾裡沒有 {KIT}/HK*.txt")
        return
    course = course_root(folder)
    if course is None:
        app.log("找不到課程資料夾（上層沒有 hk_tk.py）")
        return
    python = venv_python(course)
    if python is None:
        python = Path(sys.executable)
        app.log("課程的 .venv 還沒建：先按「科學計算」裝課程套件；這次用 iPLoT 自己的 Python 試")
    (popen or subprocess.Popen)([str(python), str(course / "hk_tk.py"), str(folder), hk], cwd=str(folder))
    app.log(f"{folder.name}：{hk} 的視窗開了（在 Dock 上找 Python）")


def _nfc(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def _unique(path: Path) -> Path:
    """path 已經有東西就加 -2、-3…"""
    n, candidate = 2, path
    while candidate.exists():
        candidate, n = path.with_name(f"{path.name}-{n}"), n + 1
    return candidate


def _inside(path: Path, base: Path) -> bool:
    return Path(path).resolve().is_relative_to(Path(base).resolve())


def _no_links(folder: str, names: list[str]) -> list[str]:
    """copytree 的 ignore：符號連結不複製、不跟（設計第 10 節）。"""
    return [n for n in names if os.path.islink(os.path.join(folder, n))]


def _copytree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=_no_links, dirs_exist_ok=True)


def _decode_member(info: zipfile.ZipInfo) -> str:
    """zip 成員名：有 UTF-8 旗標就照用；沒有的（zipfile 當 cp437 解的）改試 UTF-8，再試 cp950，都不行照原樣。"""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        raw = info.filename.encode("cp437")
    except UnicodeEncodeError:
        return info.filename
    for encoding in ("utf-8", "cp950"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return info.filename


def _unzip(file: Path, dest: Path) -> int:
    """把 file 解到 dest；名字含 .. 或是絕對路徑的成員不解、計數；回擋掉幾個。"""
    skipped = 0
    with zipfile.ZipFile(file) as zf:
        for info in zf.infolist():
            name = _nfc(_decode_member(info).replace("\\", "/"))
            parts = [p for p in name.split("/") if p not in ("", ".")]
            if (PurePosixPath(name).is_absolute() or PureWindowsPath(name).drive or ".." in parts
                    or not _inside(dest.joinpath(*parts or ["."]), dest)):
                skipped += 1
                continue
            if not parts:
                continue
            target = dest.joinpath(*parts)
            if name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return skipped


@dataclasses.dataclass
class GatherResult:
    root: Path  # 收進來的東西都在這底下
    skipped: int  # 擋掉的 zip 成員（.. 或絕對路徑）與解不開的 zip


def gather(paths: list[Path], into: Path) -> GatherResult:
    """把拖進來（或選進來）的東西都放進 into/原件/：zip 解開到 原件/<zip 名>/（裡面的 zip 再解一層），
    資料夾整個複製進 原件/<名>/，檔案複製進 原件/。"""
    root = Path(into) / "原件"
    root.mkdir(parents=True, exist_ok=True)
    skipped = 0
    for path in map(Path, paths):
        if path.is_file() and zipfile.is_zipfile(path):
            dest = _unique(root / _nfc(path.stem))
            try:
                skipped += _unzip(path, dest)
            except (zipfile.BadZipFile, OSError):
                skipped += 1
                continue
            for inner in sorted(dest.rglob("*.zip")):  # 只解一層：這裡解出來的 zip 不再往下找
                if inner.is_file() and zipfile.is_zipfile(inner):
                    try:
                        skipped += _unzip(inner, _unique(inner.with_name(inner.stem)))
                        inner.unlink()
                    except (zipfile.BadZipFile, OSError):
                        skipped += 1
        elif path.is_dir():
            _copytree(path, _unique(root / _nfc(path.name)))
        elif path.is_file():
            shutil.copy2(path, _unique(root / _nfc(path.name)))
    return GatherResult(root, skipped)


def _hidden(file: Path, root: Path) -> bool:
    """macOS 壓縮時帶的 __MACOSX/、. 開頭的檔與資料夾：不是作業。"""
    return any(p == "__MACOSX" or p.startswith(".") for p in file.relative_to(root).parts)


def _hk_list(names) -> str:
    """HK1、HK2、HK5；連號就寫 HK1–HK12。"""
    nums = sorted(int(n[2:]) for n in names)
    if len(nums) > 1 and nums == list(range(nums[0], nums[-1] + 1)):
        return f"HK{nums[0]}–HK{nums[-1]}"
    return "、".join(f"HK{n}" for n in nums)


def _skipped_note(skipped: int) -> str:
    return f"；擋掉 {skipped} 個路徑不安全（.. 或絕對路徑）或解不開的東西" if skipped else ""


NO_KIT = "收到的東西裡沒有 HK<n>.txt；要給的是老師的 t2026fscSpace 資料夾或它的 zip"


def import_kit(app, paths: list[Path], course: Path) -> str:
    """匯入老師的作業包：每個 HK<n>.txt 變成 course/HK<n>/（墊片＋t2026fscSpace/HK<n>.txt＋HK<n>Space/）。
    已經有的 HK 只換 HK<n>.txt 與補 Space 的檔，墊片不動（設計第 7 節）。回訊息區那一句。"""
    course = Path(course)
    work = Path(tempfile.mkdtemp(prefix="hk-kit-"))
    try:
        got = gather([Path(p) for p in paths], work)
        found: dict[str, Path] = {}
        for file in sorted(got.root.rglob("*.txt")):
            m = HK_RE.match(file.name)
            if m and m.group(1) not in found and not _hidden(file, got.root):
                found[m.group(1)] = file
        if not found:
            app.log(NO_KIT)
            return NO_KIT
        new = updated = 0
        for hk, src in found.items():
            target = course / hk / KIT / f"{hk}.txt"
            if target.exists():
                updated += 1
            else:
                new += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
            space = src.parent / f"{hk}Space"
            if space.is_dir():
                _copytree(space, target.parent / space.name)
            else:
                (target.parent / f"{hk}Space").mkdir(exist_ok=True)
            write_stub(course / hk)
        said = f"匯入了 {_hk_list(found)}（新 {new}、更新 {updated}）{_skipped_note(got.skipped)}"
        app.log(said)
        app.rescan()
        return said
    finally:
        shutil.rmtree(work, ignore_errors=True)


def build(folder: Path, hk: str, root) -> dict:
    """在 root（tkinter.Tk）上擺好老師啟動器的樣子，exec folder/t2026fscSpace/<hk>.txt 再叫 <hk>()；回 exec 用的 dict。
    工作目錄換到 folder；例外不接，呼叫的人接。"""
    import tkinter

    folder = Path(folder)
    file = folder / KIT / f"{hk}.txt"
    os.chdir(folder)
    root.title(f"{folder.name} — {hk}")
    root.geometry("800x800+100+50")
    sub = tkinter.LabelFrame(root)
    sub.place(relx=0.05, rely=0.1, relwidth=0.9, relheight=0.8)
    sub.configure(text="Homework")
    source = file.read_text(encoding="utf-8-sig")
    ns = {"__name__": "__main__", "__file__": str(file), "LF": root, "LF_subWIN": sub,
          "t2026fscHOMEDIR": str(folder), "HAS_DND": False, "os": os, "sys": sys, "tkinter": tkinter}
    exec(compile(source, str(file), "exec"), ns)  # noqa: S102  跟老師的啟動器一樣 exec 作業檔（設計第 5 節）
    ns[hk]()
    return ns


def explain(exc: BaseException) -> str:
    """出錯時框裡的字：語法錯說第幾行、缺套件給 pip 指令、不是 UTF-8 直說；後面都接 traceback 全文。"""
    text = "".join(traceback.format_exception(exc))
    if isinstance(exc, SyntaxError):
        return f"語法錯誤：第 {exc.lineno} 行\n\n{text}"
    if isinstance(exc, ModuleNotFoundError) and exc.name:
        return f"{text}\n缺 {exc.name}：{sys.executable} -m pip install {exc.name}"
    if isinstance(exc, UnicodeDecodeError):
        return f"這個檔不是 UTF-8（存檔時選 UTF-8 再交）\n\n{text}"
    return text


class Tee:
    """同時寫到幾個串流：學生 print 的東西進終端機，也進 執行紀錄.txt。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for s in self.streams:
            s.write(text)
        return len(text)

    def flush(self):
        for s in self.streams:
            s.flush()

    def __getattr__(self, name):  # encoding、isatty 之類的問第一個（終端機那個）
        return getattr(self.streams[0], name)


def _report(root, exc: BaseException) -> None:
    """錯誤印到 stderr（也就進了 執行紀錄.txt），再跳一個框；視窗留著。"""
    from tkinter import messagebox

    text = explain(exc)
    print(text, file=sys.stderr)
    messagebox.showerror("這份作業出錯了", text, parent=root)


def run_homework(folder: Path, hk: str) -> int:
    """開視窗跑 folder 的 <hk>.txt，視窗關掉才回來。exec、HKn()、按鈕之後的回呼出錯都跳框（設計第 5 節第 4 點）。"""
    import tkinter

    folder = Path(folder)
    out, err = sys.stdout, sys.stderr
    for stream in (out, err):  # 終端機是 cp950 之類的也印得出中文
        with contextlib.suppress(AttributeError, ValueError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")
    log = open(folder / LOG, "w", encoding="utf-8", buffering=1)  # noqa: SIM115  整段執行期間都開著，finally 關
    sys.stdout, sys.stderr = Tee(out, log), Tee(err, log)
    try:
        root = tkinter.Tk()
        root.report_callback_exception = lambda kind, exc, tb: _report(root, exc)
        try:
            build(folder, hk, root)
        except BaseException as exc:  # noqa: BLE001  學生的檔怎麼壞都要變成看得到的框，不能無聲結束
            _report(root, exc)
        root.mainloop()
    finally:
        sys.stdout, sys.stderr = out, err
        log.close()
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and not argv[0].startswith("-"):
        return run_homework(Path(argv[0]), argv[1])
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
