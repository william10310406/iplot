"""課程作業的框架：跟科目、跟作業長什麼樣都無關的部分（讀 課程.py、課的 .venv、面板上的格子、打包）。
只 import 標準庫；從不執行老師或學生的檔，判斷一律用 ast，真的跑一律是子程序。"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path

MARK = "課程.py"  # 一門課就是一個有這個檔的資料夾
NO_INSTALL = "CW_NO_INSTALL"  # 設了就不建 venv、不跑 pip，缺了只報
FROM_IPLOT = "CW_FROM_IPLOT"  # iPLoT 另開的子程序：不問、不改檔、文字開視窗
VERSIONS = ".版本"  # 作業資料夾裡框架留的版本（D135）
SENT = "發出去的"  # 一門課裡放學生包 zip 的資料夾
KEEP_PY = 20  # .版本/ 裡作業檔的 .py 最多留幾份

FRAMEWORK = Path("框架") / "course.py"  # 往上找框架時認的檔
PIP_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
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
    return Course(
        folder=folder,
        name=values.get("NAME", folder.name),  # type: ignore[arg-type]
        code=values.get("CODE", "HK{n}"),  # type: ignore[arg-type]
        folder_format=values.get("FOLDER", "HK{n:02d}"),  # type: ignore[arg-type]
        types=values.get("TYPES", ("算完畫圖",)),  # type: ignore[arg-type]
        packages=values.get("PACKAGES", ()),  # type: ignore[arg-type]
        only_on=values.get("ONLY_ON", {}),  # type: ignore[arg-type]
    )


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
