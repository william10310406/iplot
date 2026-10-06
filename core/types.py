"""核心共用的資料結構（規格附錄 B）。全部是 frozen dataclass，沒有邏輯。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Level = Literal["here", "parent", "extra", "child"]
Source = Literal["module", "core", "config"]


@dataclass(frozen=True)
class Meta:
    """不執行地從 iplot.py 讀出來的資訊。"""

    title: str | None
    description: str
    has_run: bool
    accepts_files: bool
    error: str | None
    icon: str | None = None


@dataclass(frozen=True)
class ModuleInfo:
    """一個模組：含 iplot.py 的資料夾。"""

    name: str
    title: str
    description: str
    folder: Path
    file: Path
    root: Path
    level: Level
    has_run: bool
    accepts_files: bool
    has_children: bool
    error: str | None
    icon: str | None = None
    icon_file: Path | None = None


@dataclass(frozen=True)
class Root:
    """一個要去找模組的根目錄。"""

    label: str
    level: Level
    path: Path


@dataclass(frozen=True)
class Config:
    """config.py 讀出來的設定。"""

    roots: tuple[str, ...]
    editor: tuple[str, ...] | None
    history_keep: int


@dataclass(frozen=True)
class Group:
    """面板上的一組按鈕。"""

    label: str
    level: Level
    root: Path
    modules: tuple[ModuleInfo, ...]
    note: str | None = None


@dataclass(frozen=True)
class Scope:
    """面板目前顯示的範圍。"""

    crumbs: tuple[str, ...]
    groups: tuple[Group, ...]


@dataclass(frozen=True)
class ErrorInfo:
    """錯誤變成的資料。"""

    kind: str
    message: str
    file: Path | None
    line: int | None
    traceback_text: str
    source: Source
    module: str | None


@dataclass(frozen=True)
class Result:
    """執行一次模組的結果。"""

    ok: bool
    error: ErrorInfo | None
    duration: float
    output: str
    value: Any = None


DEFAULT_CONFIG = Config(roots=("modules", ".."), editor=None, history_keep=20)
