"""回報的內容：環境（iPLoT、作業系統、Python、出錯的模組與版本）與內文（D112）。
遮蔽一律交給 redact.redact，這裡不自己認路徑。core 只在 from_error 裡 import：直接執行（IPLOT_DIRECT=1）時
core 不在 sys.path 上。"""

import os
import platform
import re
import sys
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path

import redact

REPORTER = "0.1.0"  # 內文最後那一行的 HTML 註解帶的版本：跟 CHANGELOG.md 最上面那一節一樣（測試核）
MARKER = "iplot.py"
WHAT_ERROR = "（請寫一兩句：按了什麼、預期是什麼）"
WHAT_BLANK = "（請寫：按了什麼、看到什麼、預期是什麼）"
LOST = "<模組>"  # 出錯的模組找不到它的資料夾時，標題與那一句白話裡的名字（不退回 error.module）


@dataclass(frozen=True)
class Report:
    """一份遮過的回報。"""
    category: str     # forum.CATEGORIES 的鍵："BUG"、"IDEA"、"QA"
    title: str
    body: str
    notice: str       # redact.summary(...) 那一句
    ctx: redact.Ctx   # 按送出時再遮一次要用同一個


def panel_kind(modules=sys.modules) -> str:
    """後備的 tkinter 面板裡 ui.web 也在（網頁面板開不起來才退到它）：先看 ui.tk（設計第 17 節第 7 條）。"""
    if "ui.tk" in modules:
        return "tkinter"
    return "網頁" if "ui.web" in modules else "面板外"


def python_source(base: str) -> str:
    """Python 從哪裡來，只給類別、不給路徑。base 是 os.path.realpath(sys.base_prefix)：venv 裡的 sys.executable
    在 venv 裡，看不出來（設計第 17 節第 10 條）。"""
    if base.startswith("/Library/Frameworks/Python.framework/"):
        return "python.org"
    if "/Cellar/python@" in base or base.startswith(("/opt/homebrew/", "/usr/local/opt/python@")):
        return "Homebrew"
    usr = base == "/usr" or (base.startswith("/usr/") and not (base + "/").startswith("/usr/local/"))
    if usr or base.startswith(("/Applications/Xcode.app/", "/Library/Developer/CommandLineTools/")):
        return "系統"
    return "其他"


def os_line(system: str, machine: str, mac: str = "", build: str = "", linux: str = "") -> str:
    """作業系統那一行，不帶主機名稱：macOS 26.5（arm64）、Windows（build 22631，AMD64）、
    Linux：Ubuntu 24.04 LTS（x86_64）；細節讀不到的寫 Linux（x86_64）這種。"""
    if system == "Darwin" and mac:
        return f"macOS {mac}（{machine}）"
    if system == "Windows" and build:
        return f"Windows（build {build}，{machine}）"
    if system == "Linux" and linux:
        return f"Linux：{linux}（{machine}）"
    return f"{system}（{machine}）"


def this_os() -> str:
    """這台的作業系統。macOS 用 mac_ver（platform.release() 是 Darwin 的版本）；Windows 寫 build 號（3.10 的
    platform.release() 把 Windows 11 說成 10）；不讀 platform.node()：主機名稱常常是人名。"""
    system = platform.system()
    mac = platform.mac_ver()[0] if system == "Darwin" else ""
    build = platform.version().rsplit(".", 1)[-1] if system == "Windows" else ""
    linux = ""
    if system == "Linux":
        try:
            linux = platform.freedesktop_os_release().get("PRETTY_NAME", "")
        except OSError:  # 沒有 os-release
            linux = ""
    return os_line(system, platform.machine(), mac=mac, build=build, linux=linux)


def _nfc(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def _is_module(folder: Path) -> bool:
    """跟 core.scan 一樣比對實際檔名（不分大小寫的磁碟上 iPLoT.py 不算）；讀不到就不是。"""
    try:
        return MARKER in os.listdir(folder) and (folder / MARKER).is_file()
    except OSError:
        return False


def module_of(error) -> tuple[Path | None, tuple[str, ...]]:
    """出錯的模組的最上層模組資料夾，與中間那幾層下一層模組的名字（要藏的；從出錯的那一層往上）。
    從 error.file 往上找第一個有 iplot.py、名字是 error.module 的資料夾，再往上到上一層沒有 iplot.py 為止
    （設計第 17 節第 8 條）。核心與設定的錯誤、找不到那個資料夾的，回 (None, ())。"""
    if error.file is None or error.module is None:
        return None, ()
    want = _nfc(error.module)
    mod = next((p for p in Path(error.file).parents if _nfc(p.name) == want and _is_module(p)), None)
    if mod is None:
        return None, ()
    names, top = [], mod
    while top.parent != top and _is_module(top.parent):
        names.append(_nfc(top.name))
        top = top.parent
    return top, tuple(names)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):  # 讀不到、不是 UTF-8：當作沒有
        return ""


def module_version(folder: Path) -> str:
    """模組的版本：工作坊裝的看 .origin 的 version（標「工作坊」）；否則 CHANGELOG.md 最上面那一節
    （[Unreleased] 不算，D78）；都沒有是「版本未知」。"""
    for line in _read(folder / ".origin").splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "version" and value.strip():
            return f"{value.strip()}（工作坊）"
    heads = (h.strip() for h in re.findall(r"^## \[([^\]]*)\]", _read(folder / "CHANGELOG.md"), re.M))
    return next((h for h in heads if h and h.casefold() != "unreleased"), "版本未知")


def environment(app, top: Path | None, hidden: bool, source: str | None) -> list[str]:
    """「環境」那一節，一行一個。source 是 error.source；沒有錯誤的回報傳 None，沒有模組那一行
    （top 有值的話照樣寫）。"""
    python = f"{platform.python_version()}（{python_source(os.path.realpath(sys.base_prefix))}）"
    lines = [f"- iPLoT：{app.version}（面板：{panel_kind()}）", f"- 作業系統：{this_os()}", f"- Python：{python}"]
    if top is not None:
        note = "（出錯的是它的下一層模組，名稱已遮蔽）" if hidden else ""
        lines.append(f"- 模組：{top.name} {module_version(top)}{note}")
    elif source == "module":  # 按鈕按下去之前，那個資料夾被刪、改名或搬走了
        lines.append("- 模組：（找不到它的資料夾，名稱已遮蔽）")
    elif source == "core":
        lines.append("- 模組：—（核心的錯誤）")
    elif source == "config":
        lines.append("- 模組：—（config.py）")
    return lines


def fence(text: str) -> str:
    """traceback 的框：至少 4 個 ~，而且比 text 裡最長的一串 ~ 多一個（3.11 起的 ~^ 標記不會把框提早關掉）。"""
    longest = max((len(run) for run in re.findall(r"~+", text)), default=0)
    return "~" * max(4, longest + 1)


def body(what: str, env: list[str], sentence: str | None, tb: str | None) -> str:
    """內文（設計第 7 節）。sentence 與 tb 都是 None：沒有「錯誤」那一節；tb 是 ""：框裡寫「（沒有 traceback）」。"""
    parts = [f"### 發生了什麼\n{what}", "### 環境\n" + "\n".join(env)]
    if sentence is not None or tb is not None:
        inner = (tb or "").rstrip("\n") or "（沒有 traceback）"
        mark = fence(inner)
        parts.append(f"### 錯誤\n{sentence or ''}\n\n{mark}text\n{inner}\n{mark}")
    parts.append(f"<!-- iPLoT 回報 {REPORTER} -->")
    return "\n\n".join(parts)


def _masked(category: str, title: str, text: str, ctx: redact.Ctx) -> Report:
    """標題、內文各遮一次，統計加起來給 summary。"""
    title, one = redact.redact(title, ctx)
    text, two = redact.redact(text, ctx)
    counts = {key: one[key] + two[key] for key in redact.KEYS}
    return Report(category, title, text, redact.summary(counts, ctx), ctx)


def from_error(error, app) -> Report:
    """「回報這個問題」：一筆 ErrorInfo 變成遮過的回報。下一層模組的名字藏起來，標題用最上層模組的名字。
    出錯的模組找不到它的資料夾時，名字一律寫 <模組>：error.module 可能是學生的名字，也不放進 secrets
    （redact 的第 7 步不分大小寫、沒有字界，叫 A 的模組會把整段 traceback 換爛）。"""
    from core.errors import describe

    top, hidden = module_of(error)
    ctx = redact.context(app.home, top, hidden)
    lost = top is None and error.source == "module"
    if top is not None:
        name = top.name
    elif lost:
        name = LOST
    else:
        name = {"core": "核心", "config": "config.py"}.get(error.source, "iPLoT")
    sentence = describe(replace(error, module=LOST) if lost else error)
    text = body(WHAT_ERROR, environment(app, top, bool(hidden), error.source), sentence, error.traceback_text)
    return _masked("BUG", f"[回報] {name}：{error.kind}（iPLoT {app.version}）", text, ctx)


def blank(app, category: str, module: str | None = None) -> Report:
    """沒有錯誤的回報（面板上的「回報問題」）：沒有「錯誤」那一節；module 有值就寫那個最上層模組與版本。"""
    top = None
    if module is not None:
        top = next((m.folder for m in app.modules if m.name == module and m.level != "child"), None)
    text = body(WHAT_BLANK, environment(app, top, False, None), None, None)
    return _masked(category, "[回報] ", text, redact.context(app.home, top))


def short_env(app) -> str:
    """提建議、問問題的內文最後那一行：iPLoT 0.6.0・macOS 26.5（arm64）・Python 3.14.7（沒有路徑）。"""
    return f"iPLoT {app.version}・{this_os()}・Python {platform.python_version()}"
