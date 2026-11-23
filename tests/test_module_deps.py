"""模組依賴規則（D160，AGENTS.md）：tools/check_deps.py 的掃描結果只准是白名單 tools/deps_allow.json 上的；
白名單上已經不存在的舊項目也要刪掉，到了 until 那一版還在就紅。另外用小模組核對每一條規則真的抓得到。"""
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("iplot_check_deps", ROOT / "tools" / "check_deps.py")
deps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deps)


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split("."))


def test_no_new_violations():
    ok = deps.allowed()
    new = [f"{r} {f}: {w}" for r, f, w in deps.violations() if (r, f, w) not in ok]
    assert new == [], "新的依賴違規（規則見 AGENTS.md；改用角色、寫 NEEDS，真的不得不就在 tools/deps_allow.json 加一筆並寫 why）：\n" + "\n".join(new)


def test_no_stale_allow_entries():
    found = set(deps.violations())
    gone = [f"{r} {f}: {w}" for r, f, w in deps.allowed() if (r, f, w) not in found]
    assert gone == [], "這些已經改掉了，從 tools/deps_allow.json 刪掉：\n" + "\n".join(gone)


def test_allow_entries_say_why_and_until_and_are_not_expired():
    now = _version(re.search(r'__version__ = "([\d.]+)"', (ROOT / "core" / "__init__.py").read_text(encoding="utf-8")).group(1))
    for entry in json.loads(deps.ALLOW.read_text(encoding="utf-8")):
        assert entry["why"] and entry["until"], entry
        if entry["until"] != "永久":
            assert now < _version(entry["until"]), f"白名單說 {entry['until']} 前拿掉，還在：{entry}"


@pytest.fixture
def tree(tmp_path):
    for name in ("甲", "乙", "丙", "丁"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "iplot.py").write_text("", encoding="utf-8")
    return tmp_path


def scan(tree, source, name="甲", extra=None):
    (tree / name / "iplot.py").write_text(source, encoding="utf-8")
    for rel, text in (extra or {}).items():
        (tree / name / rel).write_text(text, encoding="utf-8")
    return {(r, w) for r, _, w in deps.scan_module(tree / name, {"甲", "乙", "丙", "丁"})}


def test_r1_r5_another_modules_name(tree):
    assert scan(tree, 'X = "乙"\n') == {("R1", "乙"), ("R5", "乙")}
    assert scan(tree, 'NEEDS = ("乙",)\nX = "乙"\n') == {("R1", "乙")}  # 寫明了還是 R1：要用功能請改用角色


def test_docstrings_comments_and_name_lists_do_not_count(tree):
    assert scan(tree, '"""跟乙一起用。"""\n# "乙"\nALL = ("乙", "丙", "丁")\n') == set()


def test_r5_roles_must_be_declared(tree):
    assert scan(tree, 'def run(app):\n    app.call("page.top")\n') == {("R5", "page.top")}
    assert scan(tree, 'NEEDS = ("page.top",)\ndef run(app):\n    app.each("page.top")\n') == set()


def test_r2_core_imports(tree):
    assert scan(tree, "from core import scan\nimport core.types\n") == {("R2", "core.scan"), ("R2", "core.types")}


def test_r3_guessing_the_environment(tree):
    assert scan(tree, 'import sys\nX = "core.runner" in sys.modules\n') == {("R3", "core.runner")}


def test_r4_third_party(tree):
    assert scan(tree, "import requests\n") == {("R4", "requests")}
    assert scan(tree, "try:\n    import requests\nexcept ImportError:\n    requests = None\n") == set()
    assert scan(tree, '"""x"""\n# REQUIRES = ["requests"]\nimport requests\n') != set()  # 註解不算
    assert scan(tree, '"""x"""\nREQUIRES = ["requests"]\nimport requests\n') == set()
    assert scan(tree, "import helper\n", extra={"helper.py": ""}) == set()  # 自己資料夾裡的檔


def test_r4_package_internals_even_when_guarded(tree):
    source = "try:\n    import webview.platforms.cocoa\n    from pkg._impl import x\nexcept ImportError:\n    pass\n"
    assert scan(tree, source) == {("R4", "webview.platforms.cocoa"), ("R4", "pkg._impl")}


def test_r11_throwing_away_a_childs_errors(tree):
    source = "import subprocess\nsubprocess.Popen(['x'], stderr=subprocess.DEVNULL)\n"
    assert scan(tree, source) == {("R11", "subprocess.Popen(stderr=DEVNULL)")}
    assert scan(tree, "import subprocess\nsubprocess.Popen(['x'], stdout=subprocess.DEVNULL)\n") == set()
