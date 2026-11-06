"""課程作業的框架：跟科目、跟作業長什麼樣都無關的部分（讀 課程.py、課的 .venv、面板上的格子、打包）。
只 import 標準庫；從不執行老師或學生的檔，判斷一律用 ast，真的跑一律是子程序。"""

from __future__ import annotations

import ast
import collections
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

MARK = "課程.py"  # 一門課就是一個有這個檔的資料夾
NO_INSTALL = "CW_NO_INSTALL"  # 設了就不建 venv、不跑 pip，缺了只報
FROM_IPLOT = "CW_FROM_IPLOT"  # iPLoT 另開的子程序：不問、不改檔、文字開視窗
VERSIONS = ".版本"  # 作業資料夾裡框架留的版本（D135）
SENT = "發出去的"  # 一門課裡放學生包 zip 的資料夾
KEEP_PY = 20  # .版本/ 裡作業檔的 .py 最多留幾份

FRAMEWORK = Path("框架") / "course.py"  # 往上找框架時認的檔
TYPES_DIR = "作業類型"  # 框架所在的資料夾底下：每種作業一個資料夾，裡面是 type.py
PIP_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
# 子程序裡列出這個 Python 裝了哪些套件（不 import 它們）
LIST_INSTALLED = ("import importlib.metadata, json; "
                  "print(json.dumps([d.metadata['Name'] for d in importlib.metadata.distributions()]))")
FOLDER_SLOT = re.compile(r"\{n(?::0([1-4])d)?\}")  # {n} 或 {n:01d}…{n:04d}；不用 str.format 驗使用者給的字串


class CourseError(ValueError):
    """課程.py 讀不了或寫得不對：訊息是一句中文，有行號時含「第 n 行」。"""


@dataclass(frozen=True)
class Course:
    folder: Path
    name: str
    code: str
    folder_format: str
    types: tuple[str, ...]
    packages: tuple[tuple[tuple[str, ...], str, str], ...]
    only_on: dict[str, str]


def _fail(name: str, line: int, what: str) -> CourseError:
    return CourseError(f"第 {line} 行：{name} {what}")


def _is_text_list(value: object) -> bool:
    return isinstance(value, (list, tuple)) and all(isinstance(v, str) and v for v in value)


def _name(value: object, line: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail("NAME", line, "要是不空的字串")
    return value


def _code(value: object, line: int) -> str:
    if not isinstance(value, str) or value.count("{n}") != 1:
        raise _fail("CODE", line, "要是字串，而且剛好有一個 {n}（例如 \"HK{n}\"）")
    rest = value.replace("{n}", "")
    if not all(c.isalnum() or c in "_-" for c in rest):
        raise _fail("CODE", line, "除了 {n}，只能有字母、數字、_、-")
    return value


def _folder(value: object, line: int) -> str:
    if not isinstance(value, str) or len(FOLDER_SLOT.findall(value)) != 1 \
            or re.search(r"[{}]", FOLDER_SLOT.sub("", value)):
        raise _fail("FOLDER", line, "要是字串，而且剛好有一個 {n} 或 {n:0kd}（k 是 1–4，例如 \"HK{n:02d}\"）")
    if re.search(r"[/\\]", value) or value.startswith("."):  # D136：作業資料夾一定在課裡、面板掃得到
        raise _fail("FOLDER", line, "是作業資料夾的名字，作業資料夾要放在這門課的資料夾裡：不能有 / 或 \\，"
                                    "也不能用 . 開頭（. 開頭的資料夾面板看不到）")
    return value


def _types(value: object, line: int) -> tuple[str, ...]:
    if not _is_text_list(value):
        raise _fail("TYPES", line, "要是字串的 list（例如 [\"算完畫圖\"]）")
    return tuple(value)  # type: ignore[arg-type]


def _packages(value: object, line: int) -> tuple[tuple[tuple[str, ...], str, str], ...]:
    what = "要是 [(套件的 list, 說明, 大小), …]，套件名只能有字母、數字、. _ -"
    if not isinstance(value, (list, tuple)):
        raise _fail("PACKAGES", line, what)
    batches = []
    for item in value:
        if not (isinstance(item, (list, tuple)) and len(item) == 3 and _is_text_list(item[0]) and item[0]
                and all(PIP_NAME.fullmatch(p) for p in item[0])
                and isinstance(item[1], str) and isinstance(item[2], str)):
            raise _fail("PACKAGES", line, what)
        batches.append((tuple(item[0]), item[1], item[2]))
    return tuple(batches)


def _only_on(value: object, line: int) -> dict[str, str]:
    if not (isinstance(value, dict)
            and all(isinstance(k, str) and PIP_NAME.fullmatch(k) and v == "apple-silicon"
                    for k, v in value.items())):
        raise _fail("ONLY_ON", line, "要是 {套件名: \"apple-silicon\"}（只認這一種機器）")
    return dict(value)


CHECKS = {"NAME": _name, "CODE": _code, "FOLDER": _folder, "TYPES": _types, "PACKAGES": _packages,
          "ONLY_ON": _only_on}


def read_course(folder: Path) -> Course:
    """讀 folder/課程.py：只用 ast，不執行、不 import。頂層只接認得的名字的 = 字面值，以及字串常數
    的說明；其他一律 CourseError（說第幾行）。沒寫的名字用預設值。"""
    folder = Path(folder)
    file = folder / MARK
    try:
        tree = ast.parse(file.read_text(encoding="utf-8-sig"), str(file))
    except SyntaxError as exc:
        where = f"第 {exc.lineno} 行" if exc.lineno else "某一行"
        raise CourseError(f"{MARK} 的{where}語法不對：{exc.msg}") from exc
    except (OSError, ValueError) as exc:  # 讀不到、不是 UTF-8、含 NUL 位元組
        raise CourseError(f"讀不了 {folder.name}/{MARK}：{exc}") from exc
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            continue  # 說明文字
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            raise CourseError(f"第 {node.lineno} 行：{MARK} 裡只能放「名字 = 值」的設定，這一行不行")
        name = node.targets[0].id
        if name not in CHECKS:
            raise CourseError(f"第 {node.lineno} 行：不認得的名字 {name}（認得：{'、'.join(CHECKS)}）")
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError) as exc:
            raise _fail(name, node.lineno, "只能寫字面值（字串、數字、list、dict、tuple）") from exc
        values[name] = CHECKS[name](value, node.lineno)
    course = Course(
        folder=folder,
        name=values.get("NAME", folder.name),  # type: ignore[arg-type]
        code=values.get("CODE", "HK{n}"),  # type: ignore[arg-type]
        folder_format=values.get("FOLDER", "HK{n:02d}"),  # type: ignore[arg-type]
        types=values.get("TYPES", ("算完畫圖",)),  # type: ignore[arg-type]
        packages=values.get("PACKAGES", ()),  # type: ignore[arg-type]
        only_on=values.get("ONLY_ON", {}),  # type: ignore[arg-type]
    )
    # D136：用 FOLDER 組出來的作業資料夾，解析後（連結、..）一定在課的資料夾之內
    first = (folder / folder_of(course, 1)).resolve()
    if first.parent != folder.resolve():
        line = next((n.lineno for n in tree.body if isinstance(n, ast.Assign)
                     and getattr(n.targets[0], "id", "") == "FOLDER"), None)
        where = f"第 {line} 行：" if line else ""
        raise CourseError(f"{where}FOLDER 組出來的作業資料夾 {folder_of(course, 1)} 實際上指到這門課的資料夾外面"
                          "（可能是連結），作業資料夾要放在這門課的資料夾裡")
    return course


def code_of(course: Course, n: int) -> str:
    return course.code.replace("{n}", str(n))


def folder_of(course: Course, n: int) -> str:
    return FOLDER_SLOT.sub(lambda m: f"{n:0{m.group(1)}d}" if m.group(1) else str(n), course.folder_format)


def code_number(course: Course, name: str) -> int | None:
    """名字（檔名去副檔名、zip 名、資料夾名都行）裡認作業代號，回數字；認不出回 None。不分大小寫、
    數字可以補零（HK05 就是 HK5）；代號前後緊鄰英文字母不算（CHK1 不是 HK1、HK1A 也不是）。"""
    before, after = course.code.split("{n}")
    pattern = rf"(?<![A-Za-z]){re.escape(before)}0*(\d+)(?!\d){re.escape(after)}(?![A-Za-z])"
    found = re.search(pattern, name, re.IGNORECASE)
    return int(found.group(1)) if found else None


def _up(start: Path, wanted: Path) -> Path | None:
    here = Path(os.path.abspath(start))
    for folder in (here, *here.parents):
        if (folder / wanted).is_file():
            return folder
    return None


def course_root(start: Path) -> Path | None:
    """從 start 自己往上，第一個有 課程.py 的資料夾。"""
    return _up(start, Path(MARK))


def framework_root(start: Path) -> Path | None:
    """從 start 自己往上，第一個有 框架/course.py 的資料夾。"""
    return _up(start, FRAMEWORK)


def load_type(name: str, framework: Path) -> ModuleType:
    """載入作業類型 framework/作業類型/<name>/type.py（框架自己帶的程式，不是老師或學生的）。
    name 不是 作業類型/ 底下的一個資料夾、或那裡沒有 type.py → CourseError。"""
    base = Path(framework) / TYPES_DIR
    file = base / name / "type.py"
    if not name or re.search(r"[/\\]", name) or name.startswith(".") or not file.is_file() \
            or file.resolve().parent.parent != base.resolve():
        try:
            have = sorted(p.name for p in base.iterdir() if (p / "type.py").is_file())
        except OSError:
            have = []
        raise CourseError(f"沒有「{name}」這種作業：{TYPES_DIR}/ 底下有的是 {'、'.join(have) or '（沒有）'}")
    spec = importlib.util.spec_from_file_location(f"cw_type_{name}", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ── 課的 .venv：建、列已裝、缺的問一次、一個一個裝（從科學計算的 hk_tk 複製來改，不 import 它）──

def python_in(venv_dir: Path) -> Path:
    """venv 裡 Python 的位置（不查在不在）。"""
    return Path(venv_dir) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def venv_python(course: Path | None) -> Path | None:
    """課 .venv 的 Python；還沒建（或 course 是 None）回 None。"""
    if course is None:
        return None
    python = python_in(Path(course) / ".venv")
    return python if python.is_file() else None


def _normal(dist: str) -> str:
    return re.sub(r"[-_.]+", "-", dist).lower()


def ensure_venv(venv_dir: Path, say, popen=subprocess.Popen, python: str = sys.executable) -> Path:
    """venv_dir 的 Python；還沒有就用 python -m venv 建（不帶 --system-site-packages）。"""
    venv_dir = Path(venv_dir)
    exe = python_in(venv_dir)
    if exe.is_file():
        return exe
    if os.environ.get(NO_INSTALL):
        raise RuntimeError(f"{NO_INSTALL}：不建 .venv")
    say(f"在建 {venv_dir.parent.name}/{venv_dir.name} …")
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
    """一個一個 pip install 進 python 那個環境；一個裝不了，其他照裝。
    pip 的輸出一行一行讀，每 5 秒 say 一次最後一行。回（裝好的, [(裝不了的, 原因)]）。"""
    ok, failed = [], []
    for pkg in pkgs:
        if not PIP_NAME.fullmatch(pkg):  # fullmatch：$ 會放過結尾的換行
            failed.append((pkg, "名字不合法"))
        elif os.environ.get(NO_INSTALL):
            failed.append((pkg, NO_INSTALL))
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


# ── 課那一格 ──

def _apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def homeworks(course: Course) -> list[tuple[str, Path]]:
    """這門課的作業（代號, 作業檔），照數字排：課裡每個資料夾（. 開頭的不算）底下名字剛好是 <代號>.py 的檔，
    而且是 TYPES 裡某一種認得的作業（classify 說 mine）。只看檔名與 ast，不執行。"""
    found: list[tuple[int, str, Path]] = []
    try:
        folders = sorted(p for p in course.folder.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        return []
    for sub in folders:
        for file in sorted(sub.glob("*.py")):
            n = code_number(course, file.stem)
            if n is not None and file.stem == code_of(course, n):
                found.append((n, file.stem, file))
    return [(code, file) for _, code, file in sorted(found)]


def _requires(course: Course, kinds: list[ModuleType]) -> dict[str, set[str]]:
    """代號 → 這份作業要的 pip 名；不是任何一種 TYPES 認得的作業就不算。"""
    out: dict[str, set[str]] = {}
    for code, file in homeworks(course):
        kind = next((k for k in kinds if k.classify(file)[0] == "mine"), None)
        if kind is not None:
            out[code] = kind.requires(file)
    return out


def course_button(app, folder: Path, popen=subprocess.Popen, apple_silicon: bool | None = None) -> None:
    """課那一格：把這門課要的套件裝進課的 .venv。PACKAGES 有就一批一批問（一次只問一批），沒有就裝每份作業
    REQUIRES 的聯集；ONLY_ON 的套件在不對的機器上不裝，句子說哪幾份作業在這裡看不了。先問、確定了才建 .venv。"""
    folder = Path(folder)
    apple = _apple_silicon() if apple_silicon is None else apple_silicon
    try:
        course = read_course(folder)
        framework = Path(__file__).resolve().parent.parent
        needs = _requires(course, [load_type(name, framework) for name in course.types])
    except CourseError as exc:
        app.log(f"{folder.name}：{exc}")
        return
    if course.packages:
        batches = [(f"{why}：", list(pkgs), size) for pkgs, why, size in course.packages]
    else:
        batches = [("", sorted(set().union(*needs.values()), key=str.lower), "")]
    off = {_normal(p) for p in course.only_on} if not apple else set()
    skipped = [p for _, pkgs, _ in batches for p in pkgs if _normal(p) in off]
    batches = [(label, [p for p in pkgs if _normal(p) not in off], size) for label, pkgs, size in batches]
    note = ""
    if skipped:
        users = [code for code, req in needs.items() if {_normal(r) for r in req} & {_normal(p) for p in skipped}]
        note = f"這台機器裝不了 {'、'.join(skipped)}（只有 Apple Silicon 的 Mac 裝得了）"
        if users:
            note += f"，用到它的作業 {'、'.join(users)} 在這裡看不了"
    python = venv_python(folder)
    pending = [(label, pkgs if python is None else missing(python, pkgs, popen), size)
               for label, pkgs, size in batches if pkgs]
    pending = [item for item in pending if item[1]]
    if not pending:
        said = "課程套件都在" if any(pkgs for _, pkgs, _ in batches) else "這門課還沒有需要裝的套件（沒有作業，或作業的 REQUIRES 都是空的）"
        app.log(f"{said}；{note}" if note else said)
        return
    label, need, size = pending[0]
    if os.environ.get(NO_INSTALL):
        app.log(f"{NO_INSTALL}：不建 .venv、不裝套件（還缺 {'、'.join(need)}）")
        return
    ask = f"要裝{course.name}的課程套件嗎？{label}{'、'.join(need)}。{size + '，' if size else ''}裝進 {folder.name}/.venv" \
          + ("（還沒建，會先建）" if python is None else "") + "；網路慢的話要很久，裝的時候別的按鈕要等它裝完"
    if not app.confirm(f"{ask}。{note}" if note else ask):
        app.log("沒裝")
        return
    try:
        python = ensure_venv(folder / ".venv", say=app.log, popen=popen)
    except RuntimeError as exc:
        app.log(str(exc))
        return
    ok, failed = install(python, need, say=app.log, popen=popen)
    said = summary_of_install(ok, failed)
    if len(pending) > 1:
        later = pending[1]
        said += f"；{later[0].rstrip('：')}{'（' + later[2] + '）' if later[2] else ''}再按一次「{course.name}」"
    app.log(f"{said}；{note}" if note else said)
