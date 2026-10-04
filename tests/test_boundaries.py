import subprocess
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "core"
FORBIDDEN = ("subprocess", "sys.platform", "os.name", "startfile", "ctypes")


def test_bottom_layer_never_imports_tkinter():
    code = ("import sys; sys.modules['tkinter']=None; import core.types, core.text, core.meta, "
            "core.scan, core.errors, core.runner, core.history, core.create, "
            "core.app, core.core")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_core_has_no_os_code():
    """碰作業系統的事放 modules/作業系統，核心連字都不能出現（含註解與 docstring）。"""
    for p in sorted(CORE.glob("*.py")):
        src = p.read_text(encoding="utf-8")
        for word in FORBIDDEN:
            # 若有誤判（例如某個識別字剛好含 os.name），改用 re 加字界，不要放寬清單
            assert word not in src, f"core/{p.name} 出現 {word}"


def test_actions_module_is_gone():
    assert not (CORE / "actions.py").exists()
