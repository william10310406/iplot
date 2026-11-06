"""作業的殼（docs/09_作業規範.md v2）：作業檔第二行的 ensure、最後一行的 main，加上 python coursework.py --check <檔>。
學生拿到的學生包裡，這個檔跟作業檔放在一起；老師的作業資料夾裡沒有它，iPLoT 另開程序時用 PYTHONPATH 指過來。

作業檔在 ensure 之前就 import coursework，所以這個檔頂層只 import 標準庫；numpy、matplotlib 在用到的函式裡才 import。
沒裝 python.org 的 Mac 打 python3 會是 Apple 的 3.9：這個檔的頂層 3.9 也讀得懂（不用 3.10 才有的語法），
ensure 第一件事檢查版本，說一句話就結束，不是一段 traceback。
從 modules/科學計算/hk_page.py 複製過來改的（那個檔不動）；pip 名對照表、import 掃描各自一份。
"""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

NO_INSTALL = "CW_NO_INSTALL"  # 設了就不跑 pip，缺了只報（測試用）
FROM_IPLOT = "CW_FROM_IPLOT"  # iPLoT 另開的子程序都帶著：不自動補 REQUIRES、不問 case、文字開視窗
MIN_PYTHON = (3, 10)
# README 與錯誤句子都從這幾個常數來（學生包的 README 打包時代換進去，測試核對）
MAKE_VENV = "python3 -m venv .venv"
RUN = "python3 {file}"
WIN_MAKE_VENV = "py -m venv .venv"
WIN_RUN = "py {file}"
TOO_OLD = "這份作業要 Python 3.10 以上，現在是 {have}。照 README 第 1 步裝 python.org 的 Python，再用 python3 跑一次。"
MARK = "課程.py"  # 老師的課程資料夾（跟框架的 course.MARK 同一個名字）
NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"  # pip 名只接這些字元，不經 shell
PIP_NAMES = {"cv2": "opencv-python", "PIL": "Pillow", "sklearn": "scikit-learn", "kan": "pykan", "mlx_lm": "mlx-lm",
             "pywt": "PyWavelets", "yaml": "PyYAML", "bs4": "beautifulsoup4", "skimage": "scikit-image",
             "dateutil": "python-dateutil", "mpl_toolkits": "matplotlib", "pylab": "matplotlib"}
APPLE_SILICON_ONLY = ("mlx-lm",)
NOT_PACKAGES = {"coursework"}  # 殼自己：跟作業檔放在一起，不是 pip 套件


# ── 套件 ──


def _normal(dist: str) -> str:
    return re.sub(r"[-_.]+", "-", dist).lower()


def imports_of(file: Path) -> set[str]:
    """檔裡所有 import 的頂層名字（連函式裡的，ast.walk 整棵樹；相對 import 不算）；讀不懂回空集合。"""
    try:
        tree = ast.parse(Path(file).read_text(encoding="utf-8-sig"))
    except (SyntaxError, ValueError, OSError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def third_party(names: set[str], folder: Path) -> set[str]:
    """扣掉標準庫、__future__、coursework、folder 裡同名的 .py 或資料夾。"""
    try:
        siblings = {p.stem if p.suffix == ".py" else p.name for p in Path(folder).iterdir()}
    except OSError:
        siblings = set()
    return set(names) - set(sys.stdlib_module_names) - {"__future__"} - NOT_PACKAGES - siblings


def dist_for(name: str) -> str:
    """import 名 → pip 名：裝了的照它自己的 metadata，沒裝的查對照表，都沒有就同名。"""
    found = importlib.metadata.packages_distributions().get(name)
    return found[0] if found else PIP_NAMES.get(name, name)


def _covered(requires: list[str]) -> set[str]:
    """REQUIRES 裡那些套件提供的 import 名（裝了的照 metadata；沒裝的當作提供同名的，再加對照表反查）。"""
    wanted = {_normal(r) for r in requires}
    names = {imp for imp, dists in importlib.metadata.packages_distributions().items()
             if any(_normal(d) in wanted for d in dists)}
    names |= {imp for imp, pip in PIP_NAMES.items() if _normal(pip) in wanted}
    names |= {r for r in requires} | {_normal(r).replace("-", "_") for r in requires}
    return names


def _forgotten(file: Path, requires: list[str]) -> list[str]:
    """檔裡 import 了、REQUIRES 沒寫的 pip 名（照 import 名排序，不重複）。"""
    file = Path(file)
    names = sorted(third_party(imports_of(file), file.parent) - _covered(requires))
    out, have = [], {_normal(r) for r in requires}
    for dist in map(dist_for, names):
        if _normal(dist) not in have:
            have.add(_normal(dist))
            out.append(dist)
    return out


def requires_line(source: str) -> tuple[int, int, str] | None:
    """頂層 REQUIRES = [...] 那一行：（行號, 結束行號, 那一行 list 後面的字（註解，含前面的空白）或 ""）。
    寫成好幾行的 list、不是 list 字面值、沒有 REQUIRES：回 None。"""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "REQUIRES" and isinstance(node.value, ast.List)):
            if node.lineno != node.end_lineno:
                return None
            # 行號照 ast 算（只認 \n、\r、\r\n；str.splitlines 還會在 \x0c、U+2028 斷行），col_offset 是 UTF-8 的 byte
            line = source.encode("utf-8").splitlines()[node.lineno - 1]
            return node.lineno, node.end_lineno, line[node.value.end_col_offset:].decode("utf-8")
    return None


def fill_requires(file: Path, extra: list[str]) -> bool:
    """把 extra 補進 file 裡 REQUIRES = [...] 那一行：雙引號、原來的順序在前、註解留著；其他行一個 byte 都不動。
    回有沒有改。寫成好幾行的 REQUIRES 不改，印一句叫人手動加。"""
    file = Path(file)
    data = file.read_bytes()
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    source = data[len(bom):].decode("utf-8")
    found = requires_line(source)
    if found is None:
        if extra:
            print(f"REQUIRES 寫成好幾行（或不是一個 list），沒有自動補：請手動加 {'、'.join(extra)}")
        return False
    lineno, _, comment = found
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "REQUIRES")
    names = list(ast.literal_eval(node.value))
    have = {_normal(n) for n in names}
    for name in extra:
        if _normal(name) not in have:
            have.add(_normal(name))
            names.append(name)
    if len(names) == len(ast.literal_eval(node.value)):
        return False
    lines = data[len(bom):].splitlines(keepends=True)
    old = lines[lineno - 1]
    ending = old[len(old.rstrip(b"\r\n")):]
    lines[lineno - 1] = ("REQUIRES = [" + ", ".join(f'"{n}"' for n in names) + "]" + comment).encode("utf-8") + ending
    try:
        file.write_bytes(bom + b"".join(lines))
    except OSError:
        print(f"這個檔寫不進去，沒有自動補：請手動把 {'、'.join(extra)} 加進 REQUIRES")
        return False
    return True


def missing(requires: list[str]) -> list[str]:
    """requires 裡這個 Python 還沒裝的（不重複、照原順序）。"""
    out = []
    for name in requires:
        try:
            importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            if _normal(name) not in map(_normal, out):
                out.append(name)
    return out



def _venv_python(folder: Path) -> Path | None:
    """folder/.venv 的 Python；不在就 None。不 resolve：venv 的 python 是指到基底 Python 的連結。"""
    python = Path(folder) / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return python if python.is_file() else None


def find_venv(file: Path) -> Path | None:
    """先看作業檔旁邊的 .venv（學生包），再往上找有 課程.py 的資料夾的 .venv（老師的課）。"""
    folder = Path(file).resolve().parent
    found = _venv_python(folder)
    if found:
        return found
    course = next((p for p in (folder, *folder.parents) if (p / MARK).is_file()), None)
    return _venv_python(course) if course else None


def _no_venv(need: list[str], file: Path) -> str:
    """不在 venv 裡、旁邊也沒有 .venv：照 README 的兩行做（跟 README 同一份常數）。"""
    name = Path(file).name
    return (f"缺 {'、'.join(need)}。這份作業的套件要裝在作業旁邊的 .venv 裡（不裝進電腦本身的 Python）。"
            "照 README 做：在這個資料夾打開終端機，打這兩行（第一行只要做一次）：\n"
            f"    {MAKE_VENV}\n"
            f"    {RUN.format(file=name)}\n"
            "Windows（未經實機驗證）：\n"
            f"    {WIN_MAKE_VENV}\n"
            f"    {WIN_RUN.format(file=name)}")


def ensure(requires: list[str], file: str, popen=subprocess.Popen, argv: list[str] | None = None,
           version=sys.version_info) -> None:
    """作業檔第二行：缺的套件在這一行裝好，裝完才往下 import。
    1. Python 不到 3.10：說一句話、結束碼 1。
    2. 不在 venv 裡（系統的 Python）：找得到 .venv（作業旁邊，或上面的課程資料夾）就用它重跑同一個檔、
       帶原本的參數、結束碼照它的（先重跑，不先查缺什麼）；找不到就只看缺不缺，缺了說 README 的兩行，絕不叫 pip。
    3. 在 venv 裡：學生自己跑自己的檔時，先把 import 了、REQUIRES 沒寫的補進 REQUIRES 那一行；缺的裝進這個 venv。"""
    if tuple(version[:2]) < MIN_PYTHON:
        print(TOO_OLD.format(have=".".join(str(v) for v in version[:3])))
        sys.exit(1)
    requires = [requires] if isinstance(requires, str) else list(requires)
    argv = list(sys.argv if argv is None else argv)
    if sys.prefix == sys.base_prefix:
        python = find_venv(Path(file))
        if python is not None:
            sys.exit(popen([str(python), str(Path(file).resolve()), *argv[1:]],
                           cwd=str(Path(file).resolve().parent)).wait())
        need = missing(requires)
        if need:
            raise RuntimeError(_no_venv(need, Path(file)))
        return
    extra = []
    own = bool(argv) and Path(file).resolve() == Path(argv[0]).resolve()
    if own and not os.environ.get(FROM_IPLOT):
        extra = _forgotten(Path(file), requires)
        if extra and fill_requires(Path(file), extra):
            print(f"已把 {'、'.join(extra)} 加進 REQUIRES")
    need = missing(requires + extra)
    if not need:
        return
    if os.environ.get(NO_INSTALL):
        raise RuntimeError(f"缺 {'、'.join(need)}；{NO_INSTALL} 設著，不裝")
    bad = [n for n in need if not re.fullmatch(NAME_RE, n)]  # fullmatch：$ 會放過結尾的換行
    if bad:
        raise RuntimeError(f"套件名字不合法：{'、'.join(bad)}")
    arm_mac = sys.platform == "darwin" and platform.machine() == "arm64"
    only = [n for n in need if _normal(n) in {_normal(x) for x in APPLE_SILICON_ONLY}]
    if only and not arm_mac:
        raise RuntimeError(f"{'、'.join(only)} 只有 Apple Silicon 的 Mac 裝得了：這份作業要在 Apple Silicon 的 Mac 上跑")
    print(f"在裝 {'、'.join(need)}（第一次要幾分鐘）…")
    argv_pip = [sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check", *need]
    if popen(argv_pip).wait() != 0:
        raise RuntimeError(f"裝不了 {'、'.join(need)}：在終端機 {sys.executable} -m pip install {' '.join(need)}")
    importlib.invalidate_caches()
