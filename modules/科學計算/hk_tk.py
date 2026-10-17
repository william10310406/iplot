"""舊格式作業的執行器：python hk_tk.py <資料夾> <HKn> 開一個 Tk 視窗跑 <資料夾>/t2026fscSpace/HKn.txt。

老師的啟動器 t2026fsc.txt 只留下讓 HKn.txt 活得了的那幾行（設計第 5 節）：一個 800×800 的視窗、
LF_subWIN 那個框、HKn.txt 要的全域；exec 之後叫 HKn()，HKn.txt 自己的那排鈕原樣留著。
學生的檔出錯時跳一個框說哪裡錯（語法錯在第幾行、缺哪個套件、pip 要打什麼），print 的東西同時寫進
<資料夾>/執行紀錄.txt。

這個檔頂層只 import 標準庫、而且不 import tkinter：課程模組與墊片在 iPLoT 的面板程序裡 import 它，
面板擋 tkinter；tkinter 只在真的開視窗的函式裡 import。
"""

import ast
import collections
import contextlib
import dataclasses
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

KIT = "t2026fscSpace"
LOG = "執行紀錄.txt"
HK_RE = re.compile(r"^(HK\d+)\.txt$")
NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"  # pip 名只接這些字元（設計第 6 節），不經 shell
NO_INSTALL = "HK_NO_INSTALL"  # 設了就不建 venv、不跑 pip，缺了只報（測試用）
FROM_IPLOT = "HK_FROM_IPLOT"  # 交給新格式子程序的記號（hk_page 那邊同名）：不問 case、不改檔、不裝進系統的 Python
BATCH = "HK_BATCH"  # 批次名單另開的子程序多帶這個（hk_page 那邊同名）：明說是批次模式，句子不提「科學計算」那顆按鈕
GLOBALS = ("LF", "LF_subWIN", "t2026fscHOMEDIR", "os", "sys", "tkinter")  # 老師的啟動器給 HKn.txt 的全域
USAGE = ("用法：python hk_tk.py <資料夾> <HKn>    （跑 <資料夾>/t2026fscSpace/HKn.txt）\n"
         "　　　python hk_tk.py --batch <zip> [--kit 老師的t2026fscSpace] [--out 資料夾] [--venv 資料夾] [--hk HKn] [--yes]")


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


# ── 套件：課程自己的 .venv（設計第 6 節、D96）──

# 從老師的 12 份掃出來的。分兩批裝（Task 0 量的：基本那批約 480 MB，第二批約 1.1 GB）：
# 基本那批 HK1–HK8 要；第二批 HK9–HK12 要。pykan 沒寫它的依賴，import kan 要 PyYAML 與 tqdm。
BASIC_PACKAGES = ("numpy", "matplotlib", "scipy", "Pillow", "opencv-python", "pandas", "scikit-learn", "PyWavelets")
HEAVY_PACKAGES = ("torch", "pykan", "PyYAML", "tqdm", "torchdiffeq")
COURSE_PACKAGES = BASIC_PACKAGES + HEAVY_PACKAGES
BATCH_SIZES = ("約 480 MB", "約 1.1 GB")  # 兩批裝好的大小（Task 0 在 Apple Silicon 的 Mac 上量的，第二批含 mlx-lm）
APPLE_SILICON_ONLY = ("mlx-lm",)  # HK9；只有 Apple Silicon 的 Mac 有
NO_APPLE_SILICON = "這台機器裝不了，HK9 要在 Apple Silicon 的 Mac 上看"
PIP_NAMES = {"cv2": "opencv-python", "PIL": "Pillow", "sklearn": "scikit-learn", "kan": "pykan", "mlx_lm": "mlx-lm",
             "pywt": "PyWavelets", "yaml": "PyYAML", "bs4": "beautifulsoup4", "skimage": "scikit-image",
             "dateutil": "python-dateutil", "mpl_toolkits": "matplotlib", "pylab": "matplotlib"}
# 子程序裡列出這個 Python 裝了哪些套件（不 import 它們）
LIST_INSTALLED = ("import importlib.metadata, json; "
                  "print(json.dumps([d.metadata['Name'] for d in importlib.metadata.distributions()]))")


def _apple_silicon(platform_: str | None = None, machine: str | None = None) -> bool:
    return (platform_ or sys.platform) == "darwin" and (machine or platform.machine()) == "arm64"


def course_packages(platform_: str | None = None, machine: str | None = None) -> tuple[str, ...]:
    """課程套件；Apple Silicon 的 Mac 多 mlx-lm。"""
    return COURSE_PACKAGES + (APPLE_SILICON_ONLY if _apple_silicon(platform_, machine) else ())


def course_batches(platform_: str | None = None, machine: str | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """（基本那批, 第二批）；第二批在 Apple Silicon 的 Mac 多 mlx-lm。"""
    extra = APPLE_SILICON_ONLY if _apple_silicon(platform_, machine) else ()
    return BASIC_PACKAGES, HEAVY_PACKAGES + extra


def pip_name(name: str) -> str:
    """import 名 → pip 名；表上沒有的當作同名。"""
    return PIP_NAMES.get(name, name)


def _normal(dist: str) -> str:
    return re.sub(r"[-_.]+", "-", dist).lower()


def scan_imports(file: Path) -> set[str]:
    """檔裡所有 import 的頂層名字（連函式裡的也算，ast.walk 整棵樹；相對 import 不算）；讀不懂回空集合。"""
    try:
        tree = ast.parse(Path(file).read_text(encoding="utf-8-sig"))
    except (SyntaxError, ValueError, OSError):  # UnicodeDecodeError 是 ValueError
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def third_party(names: set[str], folder: Path) -> set[str]:
    """扣掉標準庫、__future__、folder 裡同名的 .py 或資料夾，剩下的就是要 pip 裝的。"""
    try:
        siblings = {p.stem if p.suffix == ".py" else p.name for p in Path(folder).iterdir()}
    except OSError:
        siblings = set()
    return set(names) - set(sys.stdlib_module_names) - {"__future__", "hk_page", "hk_tk"} - siblings


def ensure_venv(venv_dir: Path, say, popen=subprocess.Popen, python: str = sys.executable) -> Path:
    """venv_dir 的 Python；還沒有就用 python -m venv 建（不帶 --system-site-packages）。"""
    venv_dir = Path(venv_dir)
    exe = python_in(venv_dir)
    if exe.is_file():
        return exe
    if os.environ.get(NO_INSTALL):
        raise RuntimeError("HK_NO_INSTALL：不建 .venv")
    say(f"在建 {venv_dir.name} …")
    code = popen([str(python), "-m", "venv", str(venv_dir)]).wait()
    if code != 0:
        raise RuntimeError(f"建不了 {venv_dir}：代碼 {code}")
    return exe


def installed(python: Path, popen=subprocess.Popen) -> set[str]:
    """python 那個環境裝了哪些套件（名字正規化成小寫、- 連接）；問不到回空集合。"""
    proc = popen([str(python), "-c", LIST_INSTALLED], stdout=subprocess.PIPE, text=True)
    out, _ = proc.communicate()
    try:
        return {_normal(n) for n in json.loads(out)}
    except (ValueError, TypeError):
        return set()


def missing(python: Path, pkgs, popen=subprocess.Popen) -> list[str]:
    """pkgs 裡 python 那個環境還沒有的，照原順序、不重複。"""
    have, out = installed(python, popen=popen), []
    for pkg in pkgs:
        if _normal(pkg) not in have and _normal(pkg) not in map(_normal, out):
            out.append(pkg)
    return out


def install(python: Path, pkgs: list[str], say, popen=subprocess.Popen, clock=time.monotonic):
    """一個一個 pip install 進 python 那個環境；一個裝不了，其他照裝（Review Focus 第 3 條）。
    pip 的輸出一行一行讀，每 5 秒 say 一次最後一行。回（裝好的, [(裝不了的, 原因)]）。"""
    ok, failed = [], []
    for pkg in pkgs:
        if not re.fullmatch(NAME_RE, pkg):  # fullmatch：$ 會放過結尾的換行
            failed.append((pkg, "名字不合法"))
        elif os.environ.get(NO_INSTALL):
            failed.append((pkg, "HK_NO_INSTALL"))
        elif pkg in APPLE_SILICON_ONLY and not _apple_silicon():
            failed.append((pkg, NO_APPLE_SILICON))
        else:
            proc = popen([str(python), "-m", "pip", "install", "--no-input", "--disable-pip-version-check", pkg],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            tail, last = collections.deque(maxlen=5), clock()
            for raw in proc.stdout:
                line = raw.rstrip()
                if not line:
                    continue
                tail.append(line)
                now = clock()
                if now - last >= 5:
                    say(f"{pkg}：{line}")
                    last = now
            if proc.wait() == 0:
                ok.append(pkg)
            else:
                errors = [t.strip() for t in tail if t.strip().startswith("ERROR")]
                failed.append((pkg, " / ".join(errors or [t.strip() for t in tail])))
    return ok, failed


def summary_of_install(ok, failed) -> str:
    """「已裝 a、b；裝不了 c（原因）」；兩個都空回空字串。"""
    parts = []
    if ok:
        parts.append("已裝 " + "、".join(ok))
    if failed:
        parts.append("裝不了 " + "、".join(f"{p}（{why}）" for p, why in failed))
    return "；".join(parts)


def _nfc(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def _unique(path: Path, keep_suffix: bool = False) -> Path:
    """path 已經有東西就加 -2、-3…；keep_suffix 時加在副檔名前面（HK5.py → HK5-2.py）。"""
    n, candidate = 2, path
    while candidate.exists():
        name = f"{path.stem}-{n}{path.suffix}" if keep_suffix else f"{path.name}-{n}"
        candidate, n = path.with_name(name), n + 1
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


def _folder(dest: Path, parts: list[str], folders: dict[tuple[str, ...], Path]) -> Path:
    """zip 裡 parts 那個資料夾解在 dest 底下的哪裡（順便建好；folders 記著同一個 zip 解過的）。
    只差大小寫的另一個資料夾已經在了（B1/ 之後又來 b1/），macOS 會開到同一個：另開 b1-2/，兩個學生不混在一起。"""
    where = dest
    for i, part in enumerate(parts):
        key = tuple(parts[: i + 1])
        if key not in folders:
            here = where / part
            if any(n != part and n.casefold() == part.casefold() for n in os.listdir(where)):
                here = _unique(here)
            here.mkdir(parents=True, exist_ok=True)
            folders[key] = here
        where = folders[key]
    return where


def _unzip(file: Path, dest: Path) -> int:
    """把 file 解到 dest；名字含 .. 或是絕對路徑的成員不解、計數；回擋掉幾個。"""
    skipped = 0
    folders: dict[tuple[str, ...], Path] = {}
    with zipfile.ZipFile(file) as zf:
        dest.mkdir(parents=True, exist_ok=True)
        for info in zf.infolist():
            name = _nfc(_decode_member(info).replace("\\", "/"))
            parts = [p for p in name.split("/") if p not in ("", ".")]
            if (PurePosixPath(name).is_absolute() or PureWindowsPath(name).drive or ".." in parts
                    or not _inside(dest.joinpath(*parts or ["."]), dest)):
                skipped += 1
                continue
            if not parts:
                continue
            if name.endswith("/"):
                _folder(dest, parts, folders)
                continue
            target = _folder(dest, parts[:-1], folders) / parts[-1]
            if target.exists():  # 同一個資料夾裡只差大小寫的兩個檔（HK5.txt、hk5.txt）在 macOS 是同一個檔：兩份都留
                target = _unique(target, keep_suffix=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return skipped


@dataclasses.dataclass
class GatherResult:
    root: Path  # 收進來的東西都在這底下
    skipped: int  # 擋掉的 zip 成員（.. 或絕對路徑）與解不開的 zip
    zips: dict[Path, str] = dataclasses.field(default_factory=dict)  # zip 解開的資料夾 → 那個 zip 的檔名


def _unzip_inside(folder: Path, levels: int, zips: dict[Path, str]) -> int:
    """folder 底下的 zip 解在原地（解開的資料夾叫 zip 的名字，解完拿掉 zip）；levels 是還能往下解幾層。回擋掉幾個。"""
    skipped = 0
    if levels <= 0:
        return skipped
    # 先列好：這一輪解出來的 zip 交給下一層。副檔名不分大小寫（.ZIP），但只認 .zip（.docx 也是 zip）
    for inner in sorted(p for p in folder.rglob("*") if p.suffix.lower() == ".zip"):
        if inner.is_file() and zipfile.is_zipfile(inner):
            dest = _unique(inner.with_name(inner.stem))
            try:
                skipped += _unzip(inner, dest)
                inner.unlink()
            except (zipfile.BadZipFile, OSError):
                skipped += 1
                continue
            zips[dest] = _nfc(inner.name)
            skipped += _unzip_inside(dest, levels - 1, zips)
    return skipped


def gather(paths: list[Path], into: Path, zips_in_folders: bool = False) -> GatherResult:
    """把拖進來（或選進來）的東西都放進 into/原件/：zip 解開到 原件/<zip 名>/（裡面的 zip 再解一層），
    資料夾整個複製進 原件/<名>/，檔案複製進 原件/。zips_in_folders（收作業）：選進來的資料夾裡的 zip 也解，
    解開的 zip 裡再有 zip 再解一次，第三層不解（TronClass 下載下來一個學生就是一個 .zip）。"""
    root = Path(into) / "原件"
    root.mkdir(parents=True, exist_ok=True)
    skipped, zips = 0, {}
    for path in map(Path, paths):
        if path.is_file() and zipfile.is_zipfile(path):
            dest = _unique(root / _nfc(path.stem))
            try:
                skipped += _unzip(path, dest)
            except (zipfile.BadZipFile, OSError):
                skipped += 1
                continue
            zips[dest] = _nfc(path.name)
            skipped += _unzip_inside(dest, 1, zips)  # 只解一層：這裡解出來的 zip 不再往下找
        elif path.is_dir():
            dest = _unique(root / _nfc(path.name))
            _copytree(path, dest)
            skipped += _unzip_inside(dest, 2 if zips_in_folders else 0, zips)
        elif path.is_file():
            shutil.copy2(path, _unique(root / _nfc(path.name), keep_suffix=True))
    return GatherResult(root, skipped, zips)


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


# ── 收作業（設計第 7 節後半、D97）──

BAD_CHARS = re.compile(r'[/\\:*?"<>|]')
NOTHING = "收到的東西裡沒有 .py 或 .txt"


def student_name(raw: str, taken: set[str]) -> str:
    """學生資料夾的名字：raw（那一樣東西的名字，已去副檔名）NFC、去掉 / \\ : * ? " < > | 與開頭的 .；
    空了叫「未命名」；taken 裡有了就加 -2、-3…，再放進 taken。"""
    name = BAD_CHARS.sub("", _nfc(raw)).lstrip(".").strip() or "未命名"
    folded = {t.casefold() for t in taken}  # macOS、Windows 的檔名不分大小寫：B1 和 b1 是同一個資料夾
    final, n = name, 2
    while final.casefold() in folded:
        final, n = f"{name}-{n}", n + 1
    taken.add(final)
    return final


def _visible(folder: Path) -> list[Path]:
    return [p for p in folder.iterdir() if not (p.name.startswith(".") or p.name == "__MACOSX")]


def _homework_file(file: Path) -> bool:
    """收得進來的檔：.py、.txt（學生自己那份殼 hk_page.py 不算：用課程的正本）。"""
    return file.is_file() and file.suffix.lower() in (".py", ".txt") and file.name.casefold() != "hk_page.py"


def _homework_files(path: Path) -> list[Path]:
    """path 自己（是收得進來的檔的話），或它底下所有收得進來的檔（藏起來的不算），照路徑排。"""
    if path.is_file():
        return [path] if _homework_file(path) else []
    return sorted(f for f in path.rglob("*") if _homework_file(f) and not _hidden(f, path))


def _candidates(folder: Path) -> list[Path]:
    """folder 直接底下的候選：.py/.txt 散檔、底下有 .py/.txt 的資料夾（zip 解開的也是資料夾）。"""
    return [k for k in sorted(_visible(folder), key=lambda p: _nfc(p.name)) if _homework_files(k)]


def _exact(file: Path, hk: str) -> bool:
    """檔名就是這份作業：HK1.txt、HK1.py（大小寫、補零跟 hk_in_name 一樣看）。"""
    m = re.fullmatch(r"HK0*(\d+)", file.stem, re.IGNORECASE)
    return file.suffix.lower() in (".py", ".txt") and m is not None and f"HK{int(m.group(1))}" == hk


def _name_of(thing: Path, zips: dict[Path, str]) -> str:
    """一樣東西的名字：檔去副檔名；zip 解開的資料夾是那個 zip 的名字去副檔名；資料夾就是它的名字。"""
    if thing.is_file():
        return thing.stem
    return Path(zips[thing]).stem if thing in zips else thing.name


def _is_wrapper(thing: Path, kids: list[Path], hk: str, zips: dict[Path, str]) -> bool:
    """thing 是全班一包（包裝），不是一個學生：名字像 HKn；或候選兩個以上、自己直接底下沒有 HKn.txt／HKn.py。
    只有一個候選的就往下走（只包了一層的全班）：走到的那一層直接有 HKn.txt 或只剩一個檔，thing 就是那個學生；
    走到的那一層名字像 HKn、或候選兩個以上，thing 只是包裝（拿不準就一人一份，不把全班合成一個人）；
    資料夾裡只放著一個 zip 時也是包裝：那個 zip 就是學生（TronClass 一人一個 zip）。"""
    if hk_in_name(_name_of(thing, zips)) == hk:
        return True
    level = thing
    while not any(k.is_file() and _exact(k, hk) for k in kids):
        if len(kids) >= 2 or (level != thing and hk_in_name(_name_of(level, zips)) == hk):
            return True
        if kids[0].is_file():
            return False
        if kids[0] in zips and level not in zips:
            return True
        level, kids = kids[0], _candidates(kids[0])
    return False


@dataclasses.dataclass
class Student:
    thing: Path  # 選進來（或包裝裡）的那一樣東西：檔，或資料夾（zip 解開的也是）
    name: str  # 它的名字（去副檔名）
    files: list[Path]  # 它底下收得進來的檔，正本排第一，其他是多交的


def _students_in(thing: Path, hk: str, zips: dict[Path, str], wrapper: bool = False) -> list[Student]:
    """誰是一個學生（設計第 7 節）：一樣東西（檔、zip、資料夾）＝一個學生，名字是它的名字；全班一包是包裝，
    裡面的每個候選各自再看一次。wrapper：thing 一定是包裝（批次模式給的 zip 就是全班那一包）。"""
    if thing.is_file():
        return [Student(thing, thing.stem, [thing])] if _homework_file(thing) else []
    kids = _candidates(thing)
    if not kids:
        return []
    if wrapper or _is_wrapper(thing, kids, hk, zips):
        return [s for kid in kids for s in _students_in(kid, hk, zips)]
    files = _homework_files(thing)
    primary = min(files, key=lambda f: (-_homework_rank(f, hk), len(f.relative_to(thing).parts)))  # 同一層：淺的、排前面的
    return [Student(thing, _name_of(thing, zips), [primary, *(f for f in files if f != primary)])]


def _shown(file: Path, thing: Path, zips: dict[Path, str]) -> str:
    """file 在 thing 裡的路徑；zip 解開的資料夾寫回 zip 的檔名（王小明.zip/HK1.txt）。"""
    parts, here = [], thing
    for part in file.relative_to(thing).parts:
        here = here / part
        parts.append(zips.get(here, part))
    return "/".join(parts)


def _homework_rank(file: Path, hk: str) -> int:
    """越大越像這份作業的正本（四層）：3 檔名就是 HKn（HK1.txt、HK1.py）；2 classify 認得、檔名含 HKn；
    1 classify 認得；0 其他。標準樣本的備份 HK1_threebody_backup.txt 也是完整的舊格式 HK1，只能靠檔名分。"""
    if _exact(file, hk):
        return 3
    known = classify(file)[0] in ("old", "new")
    return (2 if hk_in_name(file.stem) == hk else 1) if known else 0


def kit_space(hk_folder: Path, hk: str) -> Path | None:
    """老師那份的 HKnSpace/：舊格式在 t2026fscSpace/ 底下，新格式就在 HKn/ 底下；還沒匯入回 None。"""
    for space in (Path(hk_folder) / KIT / f"{hk}Space", Path(hk_folder) / f"{hk}Space"):
        if space.is_dir():
            return space
    return None


def classify(file: Path) -> tuple[str, str | None]:
    """不執行、只用 ast 看是哪一種（D99）：頂層有 HOMEWORK = dict(…) 是 ("new", None)（兩種都有也算新）；
    有 def HKn( 而且用到 LF_subWIN 是 ("old", "HKn")；其他是 ("broken", None)、("not-utf8", None)、("none", None)。"""
    try:
        source = Path(file).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return "not-utf8", None
    except OSError:
        return "none", None
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return "broken", None
    for node in tree.body:
        if (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "HOMEWORK" for t in node.targets)
                and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "dict"):
            return "new", None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and re.fullmatch(r"HK\d+", node.name) and "LF_subWIN" in source:
            return "old", node.name
    return "none", None


SHELL = Path(__file__).resolve().parent / "hk_page.py"  # 新格式的殼：正本跟這個檔放在一起（課程資料夾）


def _requires_of(file: Path) -> set[str]:
    """新格式檔的 REQUIRES（pip 名）；讀不懂回空集合。"""
    try:
        tree = ast.parse(Path(file).read_text(encoding="utf-8-sig"))
    except (SyntaxError, ValueError, OSError):
        return set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "REQUIRES" for t in node.targets):
            with contextlib.suppress(ValueError, TypeError, SyntaxError):
                value = ast.literal_eval(node.value)
                if isinstance(value, (list, tuple)):
                    return {v for v in value if isinstance(v, str)}
    return set()


def _shell_check(file: Path) -> list[str]:
    """新格式的檔跑一次 hk_page 的 --check（從課程資料夾的正本載入，不動 sys.path、不碰 sys.modules 裡的 hk_page）。
    正本不在（批次模式只複製了 hk_tk.py，或 hk_page.py 事後被刪）就不查，回 []：名單照開，不載學生資料夾裡的那份。"""
    import importlib.util

    if not SHELL.is_file():
        return []
    spec = importlib.util.spec_from_file_location("_hk_page_for_check", SHELL)
    shell = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shell)
    return shell.check(Path(file))


def _is_new_folder(folder: Path) -> bool:
    """學生資料夾放的是新格式（iplot.py 是作業本身、旁邊有殼），不是舊格式的迷你作業包。"""
    return (folder / "hk_page.py").is_file() and (folder / "iplot.py").is_file() and not (folder / KIT).is_dir()


def _is_student(folder: Path, hk: str) -> bool:
    """收作業放出來的學生資料夾（舊格式的迷你作業包，或新格式）；不是的話不能覆蓋、更不能砍。"""
    return (folder.is_dir() and not folder.is_symlink()
            and ((folder / KIT / f"{hk}.txt").is_file() or _is_new_folder(folder)))


def _packages(app, python: Path | None, pkgs: list[str], popen, batch: bool = False) -> str:
    """這批用到、還沒裝的套件：問一次，一個一個裝；回總結那句後面要接的話。"""
    if python is None:
        return "venv 沒建好，套件沒掃" if batch else ".venv 還沒建，套件沒掃"
    need = missing(python, pkgs, popen=popen) if pkgs else []
    if not need:
        return ""
    venv = Path(python).parents[1]
    if not app.confirm(f"這批用到還沒裝的套件：{'、'.join(need)}。現在裝進 {venv.parent.name}/{venv.name}？"):
        return f"沒裝：{'、'.join(need)}"
    return summary_of_install(*install(python, need, app.log, popen=popen))


def collect(app, paths: list[Path], hk_folder: Path, python: Path | None = None, popen=subprocess.Popen,
            hk: str | None = None, batch: bool = False) -> str:
    """收作業：拖進來（或選進來）的 zip、資料夾、檔，每份放成 hk_folder/<學生>/（迷你作業包，D95），
    再收同一個人＝覆蓋。用到的套件問一次、裝進 python 那個 venv（沒給就用課程的 .venv）。回訊息區那一句。
    hk 沒給就是 hk_folder 的名字（批次模式的 hk_folder 是 HK5_收件，另外給 hk）。batch 是批次模式（batch() 明說，不猜）：
    hk_folder 是 --out 給的，不找課程資料夾（hk_tk.py 放哪裡都收得了）、不用課程的 .venv、句子不提它；給的 zip 是全班那一包。"""
    hk_folder = Path(hk_folder)
    hk = hk or hk_folder.name
    course = None if batch else course_root(hk_folder)
    if course is not None and hk_folder.resolve().parent != course:  # 面板上把東西收到學生資料夾上
        said = f"這是學生的資料夾；作業要收進 {hk_folder.parent.name}（按「科學計算」底下的「收作業」）"
        app.log(said)
        return said
    if python is None:
        python = venv_python(course)
    work = Path(tempfile.mkdtemp(prefix="hk-collect-"))
    try:
        got = gather([Path(p) for p in paths], work, zips_in_folders=True)
        files, others = [], 0
        for f in sorted(got.root.rglob("*")):
            if f.is_file() and not _hidden(f, got.root):
                if f.name.casefold() == "hk_page.py":  # 學生自己那份殼：用課程的正本，不當作業
                    continue
                if f.suffix.lower() in (".py", ".txt"):
                    files.append(f)
                else:
                    others += 1
        if not files:
            app.log(NOTHING)
            return NOTHING
        space = kit_space(hk_folder, hk)
        # 不能拿來當學生名字的：老師的東西與 HKn/ 裡其他不是學生資料夾的（不分大小寫比；學生資料夾可以覆蓋）
        taken = {KIT, f"{hk}Space", "iplot.py", "hk_page.py", LOG, ".history", "__pycache__"}
        with contextlib.suppress(OSError):
            taken |= {p.name for p in hk_folder.iterdir() if not _is_student(p, hk)}
        lists: dict[str, list[str]] = {"broken": [], "not-utf8": [], "wrong": [], "check": [], "no-shell": []}
        new = over = 0
        kinds = {"old": 0, "new": 0}
        unsafe = got.skipped
        imports: set[str] = set()
        has_shell = SHELL.is_file()  # 批次模式只複製了 hk_tk.py：新格式不收（補上殼再跑就對了，不用刪東西）
        students = [s for top in sorted(_visible(got.root), key=lambda p: _nfc(p.name))
                    for s in _students_in(top, hk, got.zips, wrapper=batch)]  # 批次模式給的 zip 就是全班那一包
        placed: list[tuple[str, Student]] = []
        for student in students:
            file = student.files[0]
            kind, found = classify(file)
            if kind == "new" and not has_shell:  # 不落地、不佔名字：放進去的會是程式自己不承認的資料夾
                lists["no-shell"].append(student_name(student.name, set()))
                continue
            name = student_name(student.name, taken)
            dest = hk_folder / name
            if (not _inside(dest, hk_folder) or dest.resolve() == hk_folder.resolve()
                    or (dest.exists() and not _is_student(dest, hk))):
                unsafe += 1
                continue
            if kind in ("broken", "not-utf8"):
                lists[kind].append(name)
            elif kind != "new" and found != hk:
                lists["wrong"].append(name)
            if kind in kinds:
                kinds[kind] += 1
            if dest.exists():
                over += 1
                # 格式換了（上次舊這次新，或反過來）：整個學生資料夾重建（_is_student 已經確定它是學生資料夾、不是連結）
                if (kind == "new") != _is_new_folder(dest):
                    shutil.rmtree(dest)
            else:
                new += 1
            if kind == "new":  # 新格式：學生的檔就是 iplot.py，旁邊放殼與老師的 Space，沒有墊片
                dest.mkdir(parents=True, exist_ok=True)
                (dest / "iplot.py").write_bytes(file.read_bytes())
                shutil.copy2(SHELL, dest / "hk_page.py")
                target_space = dest / f"{hk}Space"
                requires = _requires_of(file)
            else:
                kit = dest / KIT
                kit.mkdir(parents=True, exist_ok=True)
                (kit / f"{hk}.txt").write_bytes(file.read_bytes())
                target_space = kit / f"{hk}Space"
                requires = set()
            if space is not None:
                _copytree(space, target_space)
            else:
                target_space.mkdir(exist_ok=True)
            if kind == "new":
                problems = _shell_check(dest / "iplot.py")  # Space 放好了才查（DATA 指的資料夾要在）
                if problems:
                    lists["check"].append(f"{name}：{problems[0]}")
            else:
                write_stub(dest)
            imports |= third_party(scan_imports(file), dest)
            imports |= requires
            placed.append((name, student))
        notes = []
        for key, what in (("broken", "有語法錯誤"), ("not-utf8", "不是 UTF-8"), ("wrong", f"不是 {hk} 的作業檔"),
                          ("check", "新格式檢查不過")):
            if lists[key]:
                notes.append(f"{len(lists[key])} 份{what}（{'、'.join(lists[key])}）")
        if lists["no-shell"]:
            notes.append(f"{len(lists['no-shell'])} 份新格式沒收：hk_page.py 不在 hk_tk.py 旁邊"
                         f"（{'、'.join(lists['no-shell'])}）")
        if others:
            notes.append(f"略過 {others} 個不是 .py/.txt 的檔")
        extra = [(name, s) for name, s in placed if len(s.files) > 1]
        if extra:  # 同一個學生多交的（備份、自測、筆記）：一個一個列，少收的東西一定看得到
            listed = "；".join(f"{name}：{'、'.join(_shown(f, s.thing, got.zips) for f in s.files[1:])}" for name, s in extra)
            notes.append(f"多交的 {sum(len(s.files) - 1 for _, s in extra)} 個檔沒收（{listed}）")
        if unsafe:
            notes.append(_skipped_note(unsafe)[1:])
        if space is None:
            notes.append(f"老師的 {hk}Space 還沒匯入，要用資料檔的 case 會缺檔")
        pkgs = sorted({pip_name(n) for n in imports}, key=str.lower)
        package_note = _packages(app, python, pkgs, popen, batch)
        if package_note:
            notes.append(package_note)
        notes += _hints(placed, got.zips)
        formats = f"舊格式 {kinds['old']}、新格式 {kinds['new']}；" if kinds["new"] else ""  # 這學期全是舊的：不多說
        said = f"收了 {new + over} 份進 {hk}（{formats}新 {new}、覆蓋 {over}）" + "".join(f"；{n}" for n in notes)
        app.log(said)
        app.rescan()
        return said
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _hints(placed: list[tuple[str, Student]], zips: dict[Path, str]) -> list[str]:
    """句尾的提示（設計第 7 節「誰是一個學生」第 4 條：不猜，但看得到）：名字看起來是檔名的；
    直接放著一個 HKn.txt、所以整個資料夾（或 zip）被當成一個人，而子資料夾、子 zip 裡另有作業被折進多交的。"""
    hints = []
    looks = [name for name, _ in placed if hk_in_name(name)]
    if looks:
        hints.append(f"這幾份的名字看起來是檔名不是學生（{'、'.join(looks)}）：把檔（或 zip）改成學生的名字再收一次")
    for _, s in placed:
        primary = s.files[0]
        if primary.parent == s.thing and any(f.parent != s.thing and classify(f)[0] in ("old", "new")
                                             for f in s.files[1:]):
            what = "zip" if s.thing in zips else "資料夾"
            hints.append(f"{zips.get(s.thing, s.thing.name)} 直接放著一個 {primary.name}，"
                         f"所以整個{what}被當成一個人：把它改成那個學生的名字再收一次")
    return hints


def hk_in_name(name: str) -> str | None:
    """名字裡的 HK<n>（大小寫都認）；沒有回 None。zip 的檔名靠這個知道是哪一份作業。"""
    m = re.search(r"(?<![A-Za-z])HK0*(\d+)", name, re.IGNORECASE)  # HK05 就是 HK5；CHK5 不算
    return f"HK{int(m.group(1))}" if m else None


def collect_files(app, paths: list[Path], course: Path) -> None:
    """「收作業」那顆按鈕：選好的檔照檔名裡的 HKn 分好，各收進 course/HKn/；看不出來的問一次。
    （0.5.1 的面板沒有拖放，收作業靠這顆按鈕；HKn 的 on_files 留著，從「互通」的命令列叫得到。）"""
    groups: dict[str, list[Path]] = {}
    unknown = []
    for path in map(Path, paths):
        hk = hk_in_name(path.stem)
        (groups.setdefault(hk, []) if hk else unknown).append(path)
    if unknown:
        names = "、".join(p.name for p in unknown)
        hk = hk_in_name(app.ask(f"{names} 的名字裡看不出是哪一份作業：收進哪一份？（例如 HK5）") or "")
        if hk is None:
            app.log(f"沒說是哪一份，這幾個沒收：{names}")
        else:
            groups.setdefault(hk, []).extend(unknown)
    for hk, files in sorted(groups.items(), key=lambda item: int(item[0][2:])):
        write_stub(Path(course) / hk)  # 還沒匯入的 HK 先放墊片，收進來的學生才看得到
        collect(app, files, Path(course) / hk)


# ── 批次模式：沒有 iPLoT 也能收、能看（設計第 8 節、D98）──


class CliApp:
    """批次模式給 collect 的 app：訊息印出來、確認用打字（--yes 一律是）、沒有面板可以重掃。"""

    def __init__(self, say, yes: bool = False, ask=input):
        self.log, self._yes, self._ask = say, yes, ask

    def confirm(self, prompt: str) -> bool:
        if self._yes:
            self.log(f"{prompt} → 是（--yes）")
            return True
        try:
            return self._ask(f"{prompt} [y/N] ").strip().lower() in ("y", "yes", "是")
        except EOFError:
            return False

    def rescan(self) -> None:
        pass


def batch(source: Path, kit: Path | None = None, out: Path | None = None, venv: Path | None = None, say=print,
          popen=subprocess.Popen, hk: str | None = None, yes: bool = False, ask=input) -> Path:
    """python hk_tk.py --batch HK5.zip：跟面板同一個 collect，收進 zip 旁邊的 HK5_收件/；
    --kit 給老師的 t2026fscSpace（HK5Space/ 從那裡拿），套件裝進 zip 旁邊的 科學計算-venv/（幾個 HK 共用）。回收件資料夾。"""
    source = Path(source)
    hk = hk or hk_in_name(source.stem)
    if hk is None:
        raise RuntimeError("檔名裡看不出是哪一份作業：用 --hk HK5 指定")
    out = Path(out) if out else source.with_name(f"{source.stem}_收件")
    out.mkdir(parents=True, exist_ok=True)
    if kit is not None and (Path(kit) / f"{hk}Space").is_dir():
        _copytree(Path(kit) / f"{hk}Space", out / KIT / f"{hk}Space")
    try:
        python = ensure_venv(Path(venv) if venv else source.parent / "科學計算-venv", say, popen=popen)
    except RuntimeError as exc:  # 建不了（或 HK_NO_INSTALL）：照收，只是套件不裝
        say(str(exc))
        python = None
    collect(CliApp(say, yes, ask), [source], out, python=python, popen=popen, hk=hk, batch=True)
    return out


def _students(out: Path) -> list[Path]:
    return sorted((p for p in Path(out).iterdir()
                   if p.is_dir() and p.name != KIT and ((p / KIT).is_dir() or _is_new_folder(p))),
                  key=lambda p: _nfc(p.name))


def roster(out: Path, have: set[str] | None = None) -> list[tuple[str, str]]:
    """名單：[(學生, 標記)]，標記是「語法錯誤」「不是 UTF-8」「不是作業檔」或「缺 x、y」（have＝venv 裝了的，正規化過）。"""
    rows = []
    for student in _students(out):
        new_format = _is_new_folder(student)
        hk = None if new_format else hk_of(student)
        file = student / "iplot.py" if new_format else student / KIT / f"{hk}.txt"
        kind, found = classify(file) if new_format or hk else ("none", None)
        mark = {"broken": "語法錯誤", "not-utf8": "不是 UTF-8"}.get(kind, "")
        if not mark and (kind != "new" if new_format else found != hk):
            mark = "不是作業檔"
        if not mark and new_format and _shell_check(file):
            mark = "檢查不過"
        if not mark and have is not None:
            names = {pip_name(n) for n in third_party(scan_imports(file), student)} | _requires_of(file)
            need = sorted((n for n in names if _normal(n) not in _have(have)), key=str.lower)
            mark = f"缺 {'、'.join(need)}" if need else ""
        rows.append((_nfc(student.name), mark))
    return rows


def _have(names: set[str]) -> set[str]:
    return {_normal(n) for n in names} | set(names)


class Roster:
    """全班名單的 Tk 視窗：一列一個學生，雙擊或按「開」→ 另開一個執行器視窗跑他的那份。"""

    def __init__(self, out: Path, python: Path, root, popen=subprocess.Popen, have: set[str] | None = None):
        import tkinter

        # 絕對路徑（--out、--venv 可能是相對的，子程序的 cwd 是學生資料夾）；不 resolve：venv 的 python 是連結
        self.out, self.python, self.popen = Path(out).absolute(), Path(python).absolute(), popen
        self.rows = roster(self.out, have)
        root.title(f"{self.out.name} — {len(self.rows)} 份")
        root.geometry("420x600")
        self.listbox = tkinter.Listbox(root, font=("TkDefaultFont", 14))
        for name, mark in self.rows:
            self.listbox.insert("end", f"{name}    {mark}" if mark else name)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", lambda event: self.open_selected())
        self.open_button = tkinter.Button(root, text="開", command=self.open_selected)
        self.open_button.pack(fill="x")

    def open_selected(self) -> None:
        picked = self.listbox.curselection()
        if not picked:
            return
        folder = self.out / self.rows[picked[0]][0]
        if _is_new_folder(folder):  # 新格式：跑學生的 iplot.py（走 hk_page.main，一個 case 一個視窗、不問）
            self.popen([str(self.python), str(folder / "iplot.py"), "--all"], cwd=str(folder),
                       env={**os.environ, FROM_IPLOT: "1", BATCH: "1"})
            return
        hk = hk_of(folder)
        if hk is not None:
            self.popen([str(self.python), str(Path(__file__).resolve()), str(folder), hk], cwd=str(folder))


def show_roster(out: Path, python: Path) -> int:
    """開名單視窗，關掉才回來。"""
    import tkinter

    root = tkinter.Tk()
    have = installed(python) if python.is_file() else None
    Roster(out, python if python.is_file() else Path(sys.executable), root, have=have)
    root.mainloop()
    return 0


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
    entry = ns.get(hk)
    if not callable(entry):  # 交錯份（def HK3）、或根本不是作業：說是哪一種，不丟 KeyError（設計第 7、9 節）
        raise NotThisHomework(f"這份不是 {hk} 的作業檔：檔裡沒有 def {hk}()")
    entry()
    return ns


class NotThisHomework(LookupError):
    """HKn.txt 裡沒有 def HKn()：交錯份或不是作業。"""


def explain(exc: BaseException) -> str:
    """出錯時框裡的字：語法錯說第幾行、缺套件給 pip 指令、不是 UTF-8 直說；後面都接 traceback 全文。"""
    text = "".join(traceback.format_exception(exc))
    if isinstance(exc, NotThisHomework):
        return f"{exc}\n\n{text}"
    if isinstance(exc, SyntaxError):
        return f"語法錯誤：第 {exc.lineno} 行\n\n{text}"
    if isinstance(exc, ModuleNotFoundError) and exc.name:
        return f"{text}\n缺 {exc.name}：{sys.executable} -m pip install {pip_name(exc.name.split('.')[0])}"
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


def _batch_args(argv: list[str]):
    import argparse

    p = argparse.ArgumentParser(prog="hk_tk.py", description="批次模式：收一份作業的 zip，開全班名單")
    p.add_argument("--batch", required=True, type=Path, help="TronClass 下載的 zip")
    p.add_argument("--kit", type=Path, help="老師的 t2026fscSpace 資料夾（HKnSpace/ 從這裡拿）")
    p.add_argument("--out", type=Path, help="收進哪裡（預設：zip 旁邊的 <zip 名>_收件）")
    p.add_argument("--venv", type=Path, help="套件裝進哪個 venv（預設：zip 旁邊的 科學計算-venv）")
    p.add_argument("--hk", help="哪一份作業（zip 檔名裡看不出來時用，例如 HK5）")
    p.add_argument("--yes", action="store_true", help="要裝套件時不問")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--batch":
        args = _batch_args(argv)
        try:
            out = batch(args.batch, kit=args.kit, out=args.out, venv=args.venv, hk=args.hk, yes=args.yes)
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 1
        venv = args.venv or args.batch.parent / "科學計算-venv"
        return show_roster(out, python_in(venv))
    if len(argv) == 2 and not argv[0].startswith("-"):
        return run_homework(Path(argv[0]), argv[1])
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
