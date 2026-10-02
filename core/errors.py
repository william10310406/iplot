"""錯誤是資料：例外變成 ErrorInfo，ErrorInfo 變成面板上的一句話。"""

import dataclasses
import traceback
from pathlib import Path

from .text import T
from .types import ErrorInfo, ModuleInfo, Source


def _inside(filename: str | None, info: ModuleInfo) -> bool:
    return bool(filename) and Path(filename).is_relative_to(info.folder)


def from_exception(exc: BaseException, info: ModuleInfo | None, source: Source) -> ErrorInfo:
    """把例外變成 ErrorInfo。訊息是 Python 原文；檔案與行號取模組資料夾裡最內層的那一格，
    模組的錯誤找不到這一格時用 iplot.py、不帶行號；核心與設定的錯誤取最後一格。"""
    file: Path | None = None
    line: int | None = None
    frames = traceback.extract_tb(exc.__traceback__)
    if isinstance(exc, SyntaxError) and exc.filename and (info is None or _inside(exc.filename, info)):
        file, line = Path(exc.filename), exc.lineno
    elif frames and info is not None:
        mine = [f for f in frames if _inside(f.filename, info)]
        file, line = (Path(mine[-1].filename), mine[-1].lineno) if mine else (info.file, None)
    elif frames:
        file, line = Path(frames[-1].filename), frames[-1].lineno
    return ErrorInfo(type(exc).__name__, str(exc), file, line,
                     "".join(traceback.format_exception(exc)), source, info.name if info else None)


def describe(error: ErrorInfo) -> str:
    """把 ErrorInfo 組成一句話，例如「模組『開工』第 7 行出錯：NameError，name 'x' is not defined」。"""
    if error.source != "module":
        key = f"{error.source}_error"  # core_error / config_error
    else:
        key = "error_no_line" if error.line is None else "error_at_line"
    return T[key].format(**dataclasses.asdict(error))
