import subprocess
import sys


def test_bottom_layer_never_imports_tkinter():
    code = ("import sys; sys.modules['tkinter']=None; import core.types, core.text, core.meta, "
            "core.scan, core.errors, core.runner, core.history, core.create, core.actions, "
            "core.app, core.core")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
