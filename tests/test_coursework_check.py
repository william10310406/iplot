"""殼的 --check（docs/09 第 3 節 R1–R28；設計第 5 節）：每條規則一個只違反它的檔，只報那一條、行號對。
基準是 docs/09 第 1 節那個檔（範本到 Task 9 才有）；它本身要全過。不執行作業檔。"""

import re
import sys
from pathlib import Path

import pytest
from cw_support import ROOT, TYPE_DIR, load

SHELL = TYPE_DIR / "coursework.py"
SPEC = ROOT / "docs" / "09_作業規範.md"
MARK = "# ── 以下不用改 ──"


@pytest.fixture(autouse=True)
def _no_install(monkeypatch):
    monkeypatch.setenv("CW_NO_INSTALL", "1")
    monkeypatch.delenv("CW_FROM_IPLOT", raising=False)


@pytest.fixture
def cw():
    return load(SHELL, "coursework")


def good() -> str:
    """docs/09 第 1 節那個檔的原文。"""
    text = SPEC.read_text(encoding="utf-8")
    return re.search(r"## 1\..*?```python\n(.*?)```", text, re.S).group(1)


def write(tmp_path, src, name="HK1.py", space=True):
    if space:
        (tmp_path / "HK1Space").mkdir(exist_ok=True)
    file = tmp_path / name
    file.write_text(src, encoding="utf-8", newline="\n")
    return file


def line_of(src: str, text: str) -> int:
    return next(n for n, line in enumerate(src.splitlines(), 1) if text in line)


def replaced(old: str, new: str) -> tuple[str, int]:
    """基準換掉一處；回（原文, new 的第一行行號）。"""
    src = good()
    assert src.count(old) == 1, old
    out = src.replace(old, new)
    return out, line_of(out, new.splitlines()[0])


def inserted(snippet: str, offset: int = 0) -> tuple[str, int]:
    """在固定尾段前插一段頂層程式；回（原文, 段落第 offset 行的行號）。"""
    src = good()
    out = src.replace(MARK, snippet.rstrip("\n") + "\n\n" + MARK)
    return out, line_of(out, snippet.splitlines()[0]) + offset


def found(cw, file):
    return [(p.rule, p.line) for p in cw.check(file)]


# ── 基準 ──

def test_spec_example_passes(cw, tmp_path):
    assert cw.check(write(tmp_path, good())) == []


def test_problem_has_rule_line_text(cw, tmp_path):
    src, line = replaced('NAME = "HK1 範例：一顆球繞圓"', "NAME = 1")
    (p,) = cw.check(write(tmp_path, src))
    assert (p.rule, p.line) == ("R3", line) and p.text


# ── R1–R12：結構 ──

STRUCTURE = {
    "R1-tuple": ("R1", lambda: replaced('REQUIRES = ["numpy", "matplotlib"]', 'REQUIRES = ("numpy", "matplotlib")')),
    "R1-not-str": ("R1", lambda: replaced('REQUIRES = ["numpy", "matplotlib"]', 'REQUIRES = ["numpy", "matplotlib", 3]')),
    "R1-not-literal": ("R1", lambda: replaced('REQUIRES = ["numpy", "matplotlib"]',
                                              'REQUIRES = ["numpy", "matplotlib"] + []')),
    "R2": ("R2", lambda: replaced("coursework.ensure(REQUIRES, __file__)", "coursework.ensure(REQUIRES, file=__file__)")),
    "R3": ("R3", lambda: replaced('NAME = "HK1 範例：一顆球繞圓"', "NAME = 1")),
    "R4-ftp": ("R4", lambda: replaced("https://en.wikipedia.org", "ftp://en.wikipedia.org")),
    "R4-list-pair": ("R4", lambda: replaced('DOCS = [("Uniform circular motion", "https://en.wikipedia.org/wiki/Circular_motion")]',
                                            'DOCS = [["Uniform circular motion", "https://en.wikipedia.org/wiki/Circular_motion"]]')),
    "R5": ("R5", lambda: replaced('NOTE = """筆記寫這裡。純文字。"""', "NOTE = None")),
    "R6-shape": ("R6", lambda: replaced('Path(__file__).resolve().parent / "HK1Space"', 'Path(__file__).parent / "HK1Space"')),
    "R6-name": ("R6", lambda: replaced('Path(__file__).resolve().parent / "HK1Space"', 'Path(__file__).resolve().parent / "HK2Space"')),
    "R7-key": ("R7", lambda: replaced('"case-1": dict(', "case1: dict(")),
    "R7-value": ("R7", lambda: replaced('"case-1": dict(r=1.0, w=1.0, label="半徑 1、角速度 1"),', '"case-1": [1.0, 1.0],')),
    "R7-label": ("R7", lambda: replaced('label="半徑 1、角速度 1"', "label=1")),
    "R8": ("R8", lambda: replaced("def compute(case):", "def compute(case, extra):")),
    "R9": ("R9", lambda: replaced("def draw(fig, run):", "def draw(fig):")),
    "R10": ("R10", lambda: replaced("def stats(run):", "def stats():")),
    "R11-key": ("R11", lambda: replaced("stats=stats, file=", "file=")),
    "R11-value": ("R11", lambda: replaced("name=NAME,", 'name="HK1",')),
    "R11-last": ("R11", lambda: replaced("    raise SystemExit(coursework.main(HOMEWORK))", "    coursework.main(HOMEWORK)")),
    "R12": ("R12", lambda: inserted("import cv2")),
    "R12-in-function": ("R12", lambda: inserted("def helper():\n    from sklearn.cluster import KMeans\n    return KMeans", 1)),
}


@pytest.mark.parametrize("case", list(STRUCTURE))
def test_each_structure_rule_alone(cw, tmp_path, case):
    rule, make = STRUCTURE[case]
    src, line = make()
    assert found(cw, write(tmp_path, src)) == [(rule, line)]


def test_missing_name_has_no_line(cw, tmp_path):
    src, _ = replaced('NAME = "HK1 範例：一顆球繞圓"', "TITLE_ = 1")
    assert found(cw, write(tmp_path, src)) == [("R3", None)]


def test_r6_folder_missing(cw, tmp_path):
    src = good()
    assert found(cw, write(tmp_path, src, space=False)) == [("R6", line_of(src, "DATA = "))]


def test_r6_without_data_is_fine(cw, tmp_path):
    src = "\n".join(line for line in good().splitlines() if not line.startswith("DATA = ")) + "\n"
    assert cw.check(write(tmp_path, src, space=False)) == []


def test_draw_and_stats_may_be_none(cw, tmp_path):
    src = re.sub(r"def draw\(fig, run\):.*?(?=\ndef stats)", "draw = None\n", good(), flags=re.S)
    src = re.sub(r"def stats\(run\):.*?(?=\n# ──)", "stats = None\n", src, flags=re.S)
    assert cw.check(write(tmp_path, src)) == []


def test_r12_names_the_pip_package(cw, tmp_path):
    src, _ = inserted("import cv2")
    (p,) = cw.check(write(tmp_path, src))
    assert p.rule == "R12" and "opencv-python" in p.text


def blocking(problems):
    return [p for p in problems if p.block]


def test_r12_table_name_blocks(cw, tmp_path):
    """D141：import 名在對照表裡（cv2 → opencv-python）、REQUIRES 沒寫那個 pip 名：擋。"""
    src, line = inserted("import cv2")
    assert [(p.rule, p.line) for p in blocking(cw.check(write(tmp_path, src)))] == [("R12", line)]


def test_r12_unknown_name_only_warns(cw, tmp_path):
    """D141：不在對照表、也不是標準函式庫：只警告，打包不擋；句子請老師確認 REQUIRES 有寫它的 pip 名。"""
    src, line = inserted("import scipy")
    (p,) = cw.check(write(tmp_path, src))
    assert (p.rule, p.line, p.block) == ("R12", line, False)
    assert "scipy" in p.text and "REQUIRES" in p.text and "pip" in p.text


def test_r12_crypto_with_pycryptodome_is_not_blocked(cw, tmp_path):
    """import 名與 pip 名不同、對照表沒有的（import Crypto 是 pycryptodome）：老師寫對了，打包不能被擋。"""
    src = good().replace('REQUIRES = ["numpy", "matplotlib"]', 'REQUIRES = ["numpy", "matplotlib", "pycryptodome"]')
    src = src.replace(MARK, "from Crypto.Cipher import AES\n\n" + MARK)
    file = write(tmp_path, src)
    assert blocking(cw.check(file)) == []
    kind = load(TYPE_DIR / "type.py", "cw_type")
    assert blocking(kind.check(file)) == []


def test_cli_warning_alone_passes(cw, tmp_path, capsys):
    src, line = inserted("import scipy")
    assert cw.cli(["--check", str(write(tmp_path, src))]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith(f"⚠ R12 第 {line} 行：") and out[-1] == "通過"


def test_every_other_rule_blocks(cw, tmp_path):
    """只有 R12 不在對照表的那一種是警告；其他規則都擋。"""
    src, _ = replaced('NAME = "HK1 範例：一顆球繞圓"', "NAME = 1")
    (p,) = cw.check(write(tmp_path, src))
    assert p.block


def test_r12_ignores_siblings_and_stdlib(cw, tmp_path):
    (tmp_path / "helper.py").write_text("", encoding="utf-8")
    src, _ = inserted("import helper\nimport json\nfrom . import x")
    assert cw.check(write(tmp_path, src)) == []


# ── R27、R28：讀得懂 ──

def test_r27_not_utf8(cw, tmp_path):
    file = tmp_path / "HK1.py"
    file.write_bytes(good().replace("筆記寫這裡", "caf\xe9").encode("latin-1", "replace"))
    assert found(cw, file) == [("R27", None)]


def test_r27_syntax_error_says_the_line(cw, tmp_path):
    src, line = replaced("def compute(case):", "def compute(case:")
    assert found(cw, write(tmp_path, src)) == [("R27", line)]


@pytest.mark.parametrize("snippet", [
    "def pick(x):\n    match x:\n        case 1:\n            return 1\n    return 0",   # 3.10
    "def guard():\n    try:\n        pass\n    except* ValueError:\n        pass",        # 3.11
])
def test_r28_newer_syntax_is_flagged_alone(cw, tmp_path, snippet):
    src, line = inserted(snippet, 1)
    assert found(cw, write(tmp_path, src)) == [("R28", line)]


def test_r28_parenthesized_with_is_fine(cw, tmp_path):
    """括號的 with：Apple 的 3.9.6 讀得懂（3.9 的新 parser 就收），feature_version=(3, 9) 也收，不是問題。"""
    src, _ = inserted('def both():\n    with (open(DATA / "a") as f,\n          open(DATA / "b") as g):\n        return f, g')
    assert cw.check(write(tmp_path, src)) == []


def test_r28_rule_text_says_best_effort(cw):
    assert "盡力而為" in cw.RULES["R28"]


# ── 命令列 ──

def test_cli_prints_rule_and_line_and_returns_1(cw, tmp_path, capsys):
    src, line = replaced('NAME = "HK1 範例：一顆球繞圓"', "NAME = 1")
    assert cw.cli(["--check", str(write(tmp_path, src))]) == 1
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1 and out[0].startswith(f"✗ R3 第 {line} 行：")


def test_cli_without_line(cw, tmp_path, capsys):
    file = tmp_path / "HK1.py"
    file.write_bytes(b"\xff\xfe")
    assert cw.cli(["--check", str(file)]) == 1
    assert capsys.readouterr().out.startswith("✗ R27：")


def test_cli_passes(cw, tmp_path, capsys):
    assert cw.cli(["--check", str(write(tmp_path, good()))]) == 0
    assert capsys.readouterr().out.strip() == "通過"


def test_cli_too_old_says_the_version_line(cw, tmp_path, capsys):
    """D139：Python 不到 3.10 時跟 ensure 同一句、結束碼 1，不檢查、不出 traceback。"""
    file = write(tmp_path, good())
    assert cw.cli(["--check", str(file)], version=(3, 9, 6)) == 1
    out = capsys.readouterr()
    assert out.out.strip() == cw.TOO_OLD.format(have="3.9.6") and out.err == ""


APPLE = Path("/usr/bin/python3")


def _apple_version():
    import subprocess

    if not APPLE.is_file():
        return None
    done = subprocess.run([str(APPLE), "-c", "import sys; print(sys.version_info[0], sys.version_info[1])"],
                          capture_output=True, text=True)
    return tuple(int(v) for v in done.stdout.split()) if done.returncode == 0 else None


@pytest.mark.skipif(not (_apple_version() or (99,)) < (3, 10), reason="這台沒有 3.10 以前的 /usr/bin/python3")
def test_cli_on_real_old_python(tmp_path):
    """真的用 Apple 的 3.9 打 python3 coursework.py --check HK1.py：一句話、結束碼 1、沒有 traceback。"""
    import shutil
    import subprocess

    shutil.copy(SHELL, tmp_path / "coursework.py")
    write(tmp_path, good())
    done = subprocess.run([str(APPLE), "coursework.py", "--check", "HK1.py"], cwd=tmp_path, capture_output=True,
                          text=True, encoding="utf-8", env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"})
    assert done.returncode == 1, done.stderr
    assert "Traceback" not in done.stdout + done.stderr
    assert done.stdout.startswith("這份作業要 Python 3.10 以上")


@pytest.mark.parametrize("argv", [[], ["--check"], ["HK1.py"], ["--check", "a.py", "b.py"]])
def test_cli_usage_returns_2(cw, argv, capsys):
    assert cw.cli(argv) == 2
    assert "--check" in capsys.readouterr().err


def test_shell_runs_check_as_a_script(tmp_path):
    """docs/09 第 7 節那一句：python3 coursework.py --check HK1.py（在殼所在的資料夾）。"""
    import shutil
    import subprocess

    shutil.copy(SHELL, tmp_path / "coursework.py")
    write(tmp_path, good())
    done = subprocess.run([sys.executable, "coursework.py", "--check", "HK1.py"], cwd=tmp_path,
                          capture_output=True, text=True, encoding="utf-8", env={"PATH": "", "PYTHONDONTWRITEBYTECODE": "1"})
    assert (done.returncode, done.stdout.strip()) == (0, "通過"), done.stderr
    assert "python3 coursework.py --check HK1.py" in SPEC.read_text(encoding="utf-8")


# ── 作業類型的 check：從檔案載入殼，不動 sys.modules 裡的同名模組 ──

def test_type_check_uses_the_shell_without_touching_sys_modules(tmp_path, monkeypatch):
    sentinel = object()
    monkeypatch.setitem(sys.modules, "coursework", sentinel)
    kind = load(TYPE_DIR / "type.py", "cw_type")
    src, line = replaced("def compute(case):", "def compute():")
    problems = kind.check(write(tmp_path, src))
    assert [(p.rule, p.line) for p in problems] == [("R8", line)]
    assert sys.modules["coursework"] is sentinel
    assert kind.check(write(tmp_path, good())) == []


def test_type_check_does_not_run_the_file(tmp_path):
    kind = load(TYPE_DIR / "type.py", "cw_type")
    src, _ = inserted('open("寫了.txt", "w").close()')
    kind.check(write(tmp_path, src))
    assert not (tmp_path / "寫了.txt").exists()


# ── R13–R26：禁止項（每個片段插在固定尾段前；（規則, 片段, 違規的是片段第幾行（0 起算））──

FORBIDDEN = {
    "R13-tkinter": ("R13", "import tkinter", 0),
    "R13-submodule": ("R13", "from tkinter import ttk", 0),
    "R13-turtle": ("R13", "def pen():\n    import turtle\n    return turtle", 1),
    "R13-_tkinter": ("R13", "import _tkinter", 0),
    "R14-import": ("R14", "from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg", 0),
    "R14-module": ("R14", "import matplotlib.backends.backend_tk", 0),
    "R14-name": ("R14", "def bar(c):\n    return c.NavigationToolbar2Tk", 1),
    "R15-use": ("R15", 'import matplotlib\nmatplotlib.use("TkAgg")', 1),
    "R15-rcparams": ("R15", 'import matplotlib as mpl\nmpl.rcParams["backend"] = "TkAgg"', 1),
    "R16-alias": ("R16", "import matplotlib.pyplot as plt\nplt.show()", 1),
    "R16-from-pyplot-as": ("R16", "from matplotlib import pyplot as P\nP.figure()", 1),
    "R16-from-pyplot-import": ("R16", "from matplotlib.pyplot import subplots\nsubplots()", 1),
    "R16-in-function": ("R16", "import matplotlib.pyplot as plt\ndef grab():\n    return plt.gca()", 2),
    "R17-input": ("R17", "def ask():\n    return input()", 1),
    "R17-stdin": ("R17", "import sys\ndef read():\n    return sys.stdin.read()", 2),
    "R18-subprocess": ("R18", "import subprocess", 0),
    "R18-webbrowser": ("R18", "from webbrowser import open as browse", 0),
    "R18-system": ("R18", 'import os\nos.system("ls")', 1),
    "R18-exec": ("R18", 'import os\nos.execv("a", ["a"])', 1),
    "R18-spawn": ("R18", 'import os\nos.spawnl(0, "a")', 1),
    "R18-startfile": ("R18", 'from os import startfile\nstartfile("a.pdf")', 1),
    "R19": ("R19", "import os\nos.chdir(DATA)", 1),
    "R20-posix": ("R20", 'SAMPLE = "/data/run/a.csv"', 0),
    "R20-home": ("R20", 'SAMPLE = "~/a.csv"', 0),
    "R20-drive": ("R20", 'SAMPLE = "C:\\\\data\\\\a.csv"', 0),
    "R20-drive-slash": ("R20", 'SAMPLE = "D:/data/a.csv"', 0),
    "R20-unc": ("R20", 'SAMPLE = "\\\\\\\\server\\\\share"', 0),
    "R21-homedir": ("R21", 't2026fscHOMEDIR = "."', 0),
    "R21-arg": ("R21", "def old(ich, LF_subWIN):\n    return ich", 0),
    "R21-LF": ("R21", "def old2():\n    return LF", 1),
    "R22-global": ("R22", "def bump():\n    global COUNT\n    COUNT = 1", 1),
    "R23-w": ("R23", 'def save():\n    open("out.txt", "w").close()', 1),
    "R23-mode-kw": ("R23", 'def log():\n    open("log.txt", mode="a").close()', 1),
    "R24-list": ("R24", 'import matplotlib\nmatplotlib.rcParams["font.sans-serif"] = ["PingFang TC"]', 1),
    "R24-str": ("R24", 'from matplotlib import rcParams\nrcParams["font.family"] = "PingFang TC"', 1),
    "R25-title": ("R25", 'TITLE = "HK1"', 0),
    "R25-icon": ("R25", 'ICON = "chart"', 0),
    "R25-run": ("R25", "def run(app):\n    return app", 0),
    "R25-on-files": ("R25", "def on_files(app, paths):\n    return paths", 0),
    "R25-on-error": ("R25", "def on_error(app, exc):\n    return exc", 0),
    "R26-sys-exit": ("R26", "import sys\nsys.exit(0)", 1),
    "R26-exit": ("R26", "def stop():\n    exit()", 1),
    "R26-quit": ("R26", "def stop():\n    quit()", 1),
    "R26-os-exit": ("R26", "import os\ndef stop():\n    os._exit(1)", 2),
}


@pytest.mark.parametrize("case", list(FORBIDDEN))
def test_each_forbidden_rule_alone(cw, tmp_path, case):
    rule, snippet, offset = FORBIDDEN[case]
    src, line = inserted(snippet, offset)
    assert found(cw, write(tmp_path, src)) == [(rule, line)]


@pytest.mark.parametrize("snippet", [
    'SEP = "/"',                                             # R20：一個字元的分隔符
    'UNIT = "km/s"',
    'def keep():\n    open(DATA / "out.txt", "w").close()',   # R23：用變數組出來的路徑（寫在 DATA 底下）
    'def peek():\n    return open(DATA / "in.txt").read()',
    'import matplotlib\nmatplotlib.rcParams["font.sans-serif"] = ["PingFang TC", "DejaVu Sans"]',  # R24：有備選
    "import matplotlib.pyplot as plt\ncolors = plt.cm.viridis",                                  # R16：不是開圖
    "def shape(fig):\n    return fig.add_subplot(2, 1, 1)",
    # R22：nonlocal 在 draw 的 update 裡記狀態是正常寫法（D140）
    "def blink(fig, run):\n    frame = 0\n    def update(i):\n        nonlocal frame\n        frame += 1\n        return ()\n    return update",
])
def test_allowed_things_are_not_reported(cw, tmp_path, snippet):
    src, _ = inserted(snippet)
    assert cw.check(write(tmp_path, src)) == []


def test_tail_raise_is_not_r26(cw, tmp_path):
    assert all(p.rule != "R26" for p in cw.check(write(tmp_path, good())))


def test_every_rule_has_a_bad_file():
    """每條規則都有一個只觸發它的壞檔測試（R27、R28 在上面各自的測試裡）。"""
    covered = {rule for rule, _ in STRUCTURE.values()} | {rule for rule, _, _ in FORBIDDEN.values()} | {"R27", "R28"}
    assert covered == set(load(SHELL, "coursework").RULES)


# ── docs/09 第 3 節的表與 RULES 是同一份清單（D131、A13）──

HEADER = "| 編號 | 規則 | --check | 擋到哪裡 |"


def table_rows() -> list[list[str]]:
    section = re.search(r"\n## 3\..*?(?=\n## )", SPEC.read_text(encoding="utf-8"), re.S).group(0)
    lines = section.splitlines()
    start = lines.index(HEADER)
    block = []
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        block.append(line)
    assert re.fullmatch(r"\|(-+\|){4}", block[1].replace(" ", ""))
    rows = [[c.strip() for c in re.split(r"(?<!\\)\|", line)[1:-1]] for line in block[2:]]
    return rows


def test_rules_table_matches_docs(cw):
    rows = table_rows()
    assert [row[0] for row in rows] == list(cw.RULES)


def test_rules_table_has_no_empty_cells():
    for row in table_rows():
        assert len(row) == 4 and all(row), row
        assert re.fullmatch(r"R[0-9]+", row[0]), row


def test_rules_table_is_one_block():
    """表中間沒有空行（有空行 markdown 就斷成兩張表，後半讀不到）。"""
    rows = table_rows()
    assert len(rows) == len(re.findall(r"^\| R[0-9]+ \|", SPEC.read_text(encoding="utf-8"), re.M))


def test_r28_row_says_best_effort():
    assert "盡力而為" in dict((row[0], " ".join(row)) for row in table_rows())["R28"]


def test_template_is_the_spec_example(cw, tmp_path):
    """範本（「新增作業」放進去的起點）就是 docs/09 第 1 節那個檔，寫的是 HK1；放成 HK1.py 就過 --check。"""
    template = TYPE_DIR / "範本.py"
    assert template.read_text(encoding="utf-8") == good()
    assert cw.check(write(tmp_path, template.read_text(encoding="utf-8"))) == []
