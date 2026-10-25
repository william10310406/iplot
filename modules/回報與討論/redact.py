"""遮蔽規則：回報送出去之前，把路徑、使用者名稱、疑似學號、電子郵件、下一層模組的名字與模組的原始碼行遮掉（D111）。
純函式，只用標準庫：ctx 帶這台機器的事實，所以測試可以在任何平台上餵 macOS、Windows、Linux 的路徑。
冪等：遮過的再遮一次，字一樣（記號 <…> 不會再被換；送出前會再遮一次）。"""

import contextlib
import getpass
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# 統計的鍵；也是 summary 列出來的順序
KEYS = ("路徑", "使用者名稱", "疑似學號", "電子郵件", "原始碼", "下一層模組")

# traceback 的 frame 那一行：lead 認得 ExceptionGroup 的 "  | "；path 貪婪（路徑裡有 " 也認得）；tail 可以是空的（SyntaxError）
FRAME = re.compile(r'^(?P<lead>(?:[ \t]*\|)?[ \t]*)File "(?P<path>.*)", line (?P<n>\d+)(?P<tail>[^\n]*)$')
# 本來就沒有原始碼的 frame：<frozen runpy> 這種（<string>、<stdin> 不算：底下是 eval／exec 的那個字串）
FROZEN = re.compile(r"<frozen [^\n]*>")
# 引號後面緊接著絕對路徑開頭（/、X:\、X:/、\\），到同一種引號為止：Can't 的撇號配不錯、路徑裡可以有空白
QUOTED_ABS = re.compile(r"(?P<q>['\"])(?P<p>(?:/|[A-Za-z]:[\\/]|\\\\)(?:(?!(?P=q))[^\n])*)(?P=q)")
# 其他引號裡的字（同一行）；裡面含 / 或 \ 的才當路徑。單引號前面緊貼 ASCII 英數字的是撇號（Can't、couldn't），
# 不當開頭：不然它跟路徑開頭的那個引號配成一對，Can't read 'HK2/王小明/…' 的相對路徑就漏了。
# 例外是字串的前綴：前面是一個 b r u f（大小寫）或兩個 b r（rb、br…），而前綴本身前面不是 ASCII 英數字的，
# 照樣當開頭——bytes／raw 的 repr：No such file or directory: b'HK2/王小明/a.txt'
QUOTED = re.compile(r"(?:(?<![A-Za-z0-9])|(?<=(?<![A-Za-z0-9])[bBrRuUfF])|(?<=(?<![A-Za-z0-9])[bBrR][bBrR]))"
                    r"'[^'\n]*'|\"[^\"\n]*\"")
# 括號裡的絕對路徑，整段（可以有空白）：ImportError 的 (…/My Drive/…/工具.py)
PAREN_ABS = re.compile(r"\((?P<p>(?:/|[A-Za-z]:[\\/]|\\\\)[^()\n]*)\)")
# 路徑開頭之後的延伸：吃到同一行裡、不跨過引號 ( ) < > 的最後一個 / 或 \，最後一段到空白、引號、括號為止
TAIL = r"(?:[^'\"\n()<>]*[/\\])?[^\s'\"()<>/\\]*"
# 已知開頭（第 4 步）後面要接的：分隔符號、空白、引號、) 或字串結尾——以分隔符號為界
KNOWN_END = r"(?=$|[/\\\s'\")])"
# 沒有引號的其他絕對路徑：前面只看 ASCII（中文字也算 \w）；POSIX 至少兩段、Windows 的 X:\ 或 X:/、UNC 的 \\
OTHER_ABS = re.compile(r"(?<![A-Za-z0-9_>.:~/\\-])"
                       r"(?:/[^\s'\"()<>/\\]+(?=[/\\][^\s'\"()<>/\\])|(?<![A-Za-z0-9])[A-Za-z]:[\\/]|\\\\)" + TAIL)
# SyntaxError 訊息尾巴的 (檔名, line N)：檔名裡可以有一層括號（王小明 (1).py），不吃掉前面的 '(' was never closed
SYNTAX_FILE = re.compile(r"\((?P<f>[^()\n/\\<]+(?:\([^()\n/\\<]*\)[^()\n/\\<]*)*), line (?P<n>\d+)\)")
# SyntaxError 尾巴裡留著的檔名：iPLoT 自己的
KEEP_FILES = ("iplot.py", "config.py", "main.py")
# 遮出來的記號：第 7–10 步只換記號之外的字
TOKEN = re.compile(r"<(?:HOME|PATH|USER|EMAIL|IPLOT|PYTHON|疑似學號|下一層模組|檔名已遮蔽)>")
# 電子郵件
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 疑似學號：英文字母接 7–9 位數字、或 8–10 位數字；前後只看 ASCII（王小明B11201234 要中）
STUDENT_ID = re.compile(r"(?<![A-Za-z0-9])(?:[A-Za-z]\d{7,9}|\d{8,10})(?![A-Za-z0-9])")
# 留下來的副檔名
EXT = re.compile(r"\.[A-Za-z0-9]{1,8}")
# 分隔符號：/ 與 \ 都算，連續的當一個（Windows 的 repr 是兩個反斜線）
SEP = re.compile(r"[/\\]+")
# Windows 的磁碟機開頭（分隔符號換成 / 之後）
DRIVE = re.compile(r"[A-Za-z]:/")
# 換過之後還是 iPLoT 自己、Python 的 frame：原始碼留著。<IPLOT>/ 後面第一段含 <USER> 或 <下一層模組> 的也算：
# 帳號名或下一層模組的名字剛好是 core、lib、main、re 這種（是第一段的一部分），第一次遮完的標籤是
# <IPLOT>/<下一層模組>/runner.py、<IPLOT>/co<下一層模組>/…、<IPLOT>/<USER>.py；不認的話遮第二次會把留著的原始碼拿掉，不冪等
SAFE = re.compile(r"<PYTHON>/|<IPLOT>/(?:core/|ui/|lib/|main\.py|[^/]*<(?:USER|下一層模組)>)")
# 路徑被遮掉的記號：結果含這幾個的才算一個「路徑」
MASKED = ("<HOME>", "<PATH>", "<檔名已遮蔽>")
SKIPPED = "  （原始碼已略過）"
SHORT_USER = "你的使用者名稱太短，沒有自動遮，請自己找找看。"


@dataclass(frozen=True)
class Ctx:
    """這台機器上要認得的東西。都是字串；比對時不分大小寫、/ 與 \\ 都算分隔符號。"""
    home: str                       # 家目錄
    users: tuple[str, ...]          # 使用者名稱（去重）
    iplot: str                      # iPLoT 資料夾（app.home）
    pythons: tuple[str, ...]        # Python 的 prefix（含 realpath）
    module: str | None = None       # 出錯模組的「最上層」模組資料夾（report.module_of 算的）
    module_name: str | None = None  # 那個資料夾的名稱
    secrets: tuple[str, ...] = ()   # 一定要藏的字（中間那幾層下一層模組的名字）


def context(iplot, module=None, secrets=()) -> Ctx:
    """讀這台機器：家目錄、使用者名稱（getpass、USER、USERNAME、LOGNAME、家目錄最後一段；不分大小寫去重，
    留第一次出現的寫法）、Python 的 prefix（sys.prefix、base_prefix、exec_prefix 與它們的 realpath）；
    iplot 與 module 是 resolve 過的絕對路徑。"""
    home = str(Path.home())
    names = []
    with contextlib.suppress(ImportError, KeyError, OSError):  # 找不到名字：3.10、3.12 是 ModuleNotFoundError／KeyError，3.13 起是 OSError
        names.append(getpass.getuser())
    names += [os.environ.get(key, "") for key in ("USER", "USERNAME", "LOGNAME")]
    names.append(Path(home).name)
    users, seen = [], set()
    for name in names:
        if name and name.lower() not in seen:
            seen.add(name.lower())
            users.append(name)
    prefixes = (sys.prefix, sys.base_prefix, sys.exec_prefix)
    pythons = tuple(dict.fromkeys([*prefixes, *map(os.path.realpath, prefixes)]))
    folder = None if module is None else str(Path(module).resolve())
    return Ctx(home, tuple(users), str(Path(iplot).resolve()), pythons, folder,
               None if folder is None else Path(folder).name, tuple(secrets))


def _below(n: str, base: str | None) -> str | None:
    """n（分隔符號已經換成 /）在 base 底下就回相對路徑（n 原本的大小寫），等於 base 回 ""，都不是回 None。
    不分大小寫，以分隔符號為界：家目錄不吃到名字比較長的另一個家目錄。"""
    b = SEP.sub("/", base or "").rstrip("/")
    if not b or n[:len(b)].lower() != b.lower():
        return None
    rest = n[len(b):]
    if rest == "":
        return ""
    return rest[1:] if rest.startswith("/") else None


def _ext(name: str) -> str:
    """最後一段的副檔名，像副檔名的才留（.py、.csv），不然是空字串。"""
    suffix = PurePosixPath(name).suffix
    return suffix if EXT.fullmatch(suffix) else ""


def path_label(p: str, ctx: Ctx) -> str:
    """一個路徑換成什麼：iPLoT 自己的 <IPLOT>/…、Python 的 <PYTHON>/…、出錯模組第一層的 <模組:X>/檔名，
    其他都只留副檔名（<模組:X>/.../、<HOME>/.../、<PATH>/.../、.../ 加上 <檔名已遮蔽>）。以 < 開頭的原樣。"""
    if p.startswith("<"):
        return p
    n = SEP.sub("/", p)
    ext = _ext(n.rsplit("/", 1)[-1])
    rel = _below(n, ctx.iplot)
    if rel and (rel.lower().startswith(("core/", "ui/", "lib/")) or rel.lower() in ("main.py", "config.py")):
        return "<IPLOT>/" + rel
    for base in sorted(ctx.pythons, key=lambda b: len(SEP.sub("/", b)), reverse=True):  # 最長的先比
        rel = _below(n, base)
        if rel:
            return "<PYTHON>/" + rel
    rel = _below(n, ctx.module)
    if rel:
        return f"<模組:{ctx.module_name}>/" + (rel if "/" not in rel else f".../<檔名已遮蔽>{ext}")
    rel = _below(n, ctx.home)
    if rel == "":
        return "<HOME>"
    if rel is not None:
        return f"<HOME>/.../<檔名已遮蔽>{ext}"
    if n.startswith("/") or DRIVE.match(n):
        return f"<PATH>/.../<檔名已遮蔽>{ext}"
    return f".../<檔名已遮蔽>{ext}"


def _labeler(ctx: Ctx, counts: dict[str, int]):
    """path_label，順便數：換掉了、而且結果有遮掉東西的，算一個路徑。"""
    def label(p: str) -> str:
        out = path_label(p, ctx)
        if out != p and any(mark in out for mark in MASKED):
            counts["路徑"] += 1
        return out
    return label


def _frames(text: str, label, counts: dict[str, int]) -> str:
    """第 1 步：frame 的路徑換成標籤；不安全的 frame 底下的原始碼與 ~^ 標記換成一行「（原始碼已略過）」。"""
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        m = FRAME.match(lines[i])
        i += 1
        if m is None:
            out.append(lines[i - 1])
            continue
        lead, path = m["lead"], m["path"]
        new = label(path)
        out.append(f'{lead}File "{new}", line {m["n"]}{m["tail"]}')
        if SAFE.match(new) or FROZEN.fullmatch(path):
            continue
        prefix = lead[:lead.find("|") + 1]  # 到 | 為止（含 |）；沒有 | 是空字串
        depth = len(lead) - len(prefix)
        j = i
        while j < len(lines) and lines[j].startswith(prefix):  # 比 frame 那一行縮得深、不是下一個 frame 的
            rest = lines[j][len(prefix):]
            body = rest.lstrip(" \t")
            if len(rest) - len(body) <= depth or body.startswith('File "'):
                break
            j += 1
        if j > i:
            out.append(lead + SKIPPED)
            counts["原始碼"] += 1
            i = j
    return "\n".join(out)


def _outside(text: str, pattern: re.Pattern, repl: str, counts: dict[str, int], key: str) -> str:
    """只換記號之外的字：先用 TOKEN 切開（每次都重新切：前一個換出來的記號也擋住），只對記號之間的段落換。"""
    pieces, pos = [], 0
    for m in TOKEN.finditer(text):
        pieces += [text[pos:m.start()], m.group()]
        pos = m.end()
    pieces.append(text[pos:])
    for k in range(0, len(pieces), 2):
        pieces[k], n = pattern.subn(repl, pieces[k])
        counts[key] += n
    return "".join(pieces)


def redact(text: str, ctx: Ctx) -> tuple[str, dict[str, int]]:
    """遮蔽，冪等（遮過的再遮一次，字一樣）。回 (遮過的字, 統計)；統計的鍵是 KEYS，沒遮到的鍵是 0。"""
    counts = dict.fromkeys(KEYS, 0)
    label = _labeler(ctx, counts)
    # 1. frame
    text = _frames(text, label, counts)

    # 2. 引號裡的路徑：先找引號後面緊接著絕對路徑開頭的，再找其他含 / 或 \ 的
    def quoted(m: re.Match) -> str:
        s, inner = m.group(), m.group()[1:-1]
        if ("/" in inner or "\\" in inner) and not inner.startswith("<") and "://" not in inner:
            return s[0] + label(inner) + s[-1]
        return s

    text = QUOTED_ABS.sub(lambda m: m["q"] + label(m["p"]) + m["q"], text)
    text = QUOTED.sub(quoted, text)
    # 3. 括號裡的絕對路徑
    text = PAREN_ABS.sub(lambda m: "(" + label(m["p"]) + ")", text)
    # 4. 沒有引號的已知開頭（長的先比；/ 與 \ 兩種寫法都試；不分大小寫）
    starts = []
    for s in (ctx.iplot, *ctx.pythons, ctx.module, ctx.home):
        s = (s or "").rstrip("/\\")
        if s:
            starts += [s.replace("\\", "/"), s.replace("/", "\\")]
    if starts:
        alts = "|".join(re.escape(s) for s in sorted(dict.fromkeys(starts), key=len, reverse=True))
        known = re.compile(f"(?:{alts}){KNOWN_END}{TAIL}", re.IGNORECASE)
        text = known.sub(lambda m: label(m.group()), text)
    # 5. 沒有引號的其他絕對路徑
    text = OTHER_ABS.sub(lambda m: label(m.group()), text)

    # 6. SyntaxError 訊息尾巴的檔名
    def syntax(m: re.Match) -> str:
        if m["f"] in KEEP_FILES:
            return m.group()
        counts["路徑"] += 1
        return f"(<檔名已遮蔽>{_ext(m['f'])}, line {m['n']})"

    text = SYNTAX_FILE.sub(syntax, text)
    # 7–10. 只換記號之外的字；排在路徑規則後面（路徑先整段變成標籤）。長的先換：短的是長的一部分時才不會留下半截
    for secret in sorted(filter(None, ctx.secrets), key=len, reverse=True):
        text = _outside(text, re.compile(re.escape(secret), re.IGNORECASE), "<下一層模組>", counts, "下一層模組")
    text = _outside(text, EMAIL, "<EMAIL>", counts, "電子郵件")  # 信箱裡常常有帳號名：排在使用者名稱前面
    text = _outside(text, STUDENT_ID, "<疑似學號>", counts, "疑似學號")  # 中文的帳號名接著學號：也排在前面
    for user in sorted((u for u in ctx.users if len(u) >= 3), key=len, reverse=True):
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(user)}(?![A-Za-z0-9])", re.IGNORECASE)
        text = _outside(text, pattern, "<USER>", counts, "使用者名稱")
    return text, counts


def summary(counts: dict[str, int], ctx: Ctx) -> str:
    """頁面最上面那一行：「已自動遮蔽：3 個路徑、1 個使用者名稱。」；都是 0 就「沒有找到要自動遮的東西。」；
    使用者名稱有少於 3 個字的（沒有遮）再提醒一句。"""
    parts = [f"{counts[key]} 段原始碼" if key == "原始碼" else f"{counts[key]} 個{key}"
             for key in KEYS if counts.get(key)]
    text = "已自動遮蔽：" + "、".join(parts) + "。" if parts else "沒有找到要自動遮的東西。"
    return text + SHORT_USER if any(len(u) < 3 for u in ctx.users) else text
