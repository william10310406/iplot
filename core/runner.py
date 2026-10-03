"""執行模組：進入模組程式碼唯一的門。每次按下都在乾淨的命名空間重新執行 iplot.py。"""

import contextlib
import dataclasses
import io
import os
import sys
import time
from pathlib import Path
from typing import Any

from .errors import from_exception
from .text import T
from .types import ErrorInfo, ModuleInfo, Result


def run_module(info: ModuleInfo, app: Any, handler: str = "run", args: tuple = ()) -> Result:
    """讀檔、編譯、在乾淨的 dict 裡執行，再呼叫 handler(app, *args)。

    print 的輸出收進 Result.output；任何錯誤（包括 exit()）都變成 Result.error，不會往外丟。"""
    start, out, error = time.perf_counter(), io.StringIO(), None
    cwd, argv, folder, pyc = os.getcwd(), sys.argv, str(info.folder), sys.dont_write_bytecode
    loaded = set(sys.modules)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = compile(info.file.read_text(encoding="utf-8-sig"), str(info.file), "exec")
            ns: dict[str, Any] = {"__name__": "__main__", "__file__": str(info.file)}
            os.chdir(info.folder)
            sys.argv = [str(info.file)]
            sys.path.insert(0, folder)
            sys.dont_write_bytecode = True
            exec(code, ns)  # noqa: S102  規格 §7 第 2 條：進入模組程式碼唯一的門
            fn = ns.get(handler)
            if callable(fn):
                fn(app, *args)
            else:
                error = ErrorInfo("MissingHandler", T["missing_handler"].format(handler=handler),
                                  info.file, None, "", "module", info.name)
    except SystemExit as exc:
        error = dataclasses.replace(from_exception(exc, info, "module"), message=T["module_exit"])
    except Exception as exc:  # noqa: BLE001  規格 §7 允許的兩處之一
        error = from_exception(exc, info, "module")
    finally:
        sys.argv, sys.dont_write_bytecode = argv, pyc
        if folder in sys.path:
            sys.path.remove(folder)
        for name in set(sys.modules) - loaded:
            file = getattr(sys.modules[name], "__file__", None)
            if file and Path(file).is_relative_to(info.folder):
                del sys.modules[name]
        os.chdir(cwd)
    return Result(error is None, error, time.perf_counter() - start, out.getvalue())
