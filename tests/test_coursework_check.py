"""殼的 --check（docs/09 第 3 節 R1–R28；設計第 5 節）：每條規則一個只違反它的檔，只報那一條、行號對。
基準是 docs/09 第 1 節那個檔（範本到 Task 9 才有）；它本身要全過。不執行作業檔。"""

import re
import sys

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
    "R12": ("R12", lambda: inserted("import scipy")),
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
