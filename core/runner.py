"""執行模組：進入模組程式碼唯一的門。每次按下都在乾淨的命名空間重新執行 iplot.py，
就像在模組自己的資料夾裡打 python3 iplot.py，只是鍵盤和螢幕換成了視窗（D47）。"""

import builtins
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
    """讀檔、編譯、在乾淨的 dict 裡執行，有定義 handler 就再呼叫 handler(app, *args)。

    執行期間是腳本的樣子：__name__ 是 "__main__"、工作目錄與 sys.path[0] 是模組資料夾、
    sys.argv 是 [iplot.py]、input() 變成對話框（按取消得到空字串）；結束時一定還原，
    並把這次從模組資料夾載入的模組清掉，helper.py 改了下次會重讀（所以執行期間也不寫 .pyc）。
    沒有 run 不是錯，最外層程式碼就是動作；指定了別的 handler 而模組沒定義才是 MissingHandler。
    print 的輸出收進 Result.output；任何錯誤（包括 exit()）都變成 Result.error，不會往外丟。"""
    start, out, error = time.perf_counter(), io.StringIO(), None
    cwd, argv, pyc, ask = os.getcwd(), sys.argv, sys.dont_write_bytecode, builtins.input
    folder = str(info.folder)
    loaded = set(sys.modules)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = compile(info.file.read_text(encoding="utf-8-sig"), str(info.file), "exec")
            ns: dict[str, Any] = {"__name__": "__main__", "__file__": str(info.file)}
            os.chdir(info.folder)
            sys.argv = [str(info.file)]
            sys.path.insert(0, folder)
            sys.dont_write_bytecode = True
            builtins.input = lambda prompt="": app.ask(str(prompt)) or ""
            exec(code, ns)  # noqa: S102  規格 §7 第 2 條：進入模組程式碼唯一的門
            fn = ns.get(handler)
            if callable(fn):
                fn(app, *args)
            elif handler != "run":  # 沒有 run 不是錯：最外層程式碼就是按下的動作（D47）
                error = ErrorInfo("MissingHandler", T["missing_handler"].format(handler=handler),
                                  info.file, None, "", "module", info.name)
    except SystemExit as exc:
        error = dataclasses.replace(from_exception(exc, info, "module"), message=T["module_exit"])
    except Exception as exc:  # noqa: BLE001  規格 §7 允許的兩處之一
        error = from_exception(exc, info, "module")
    finally:
        sys.argv, sys.dont_write_bytecode, builtins.input = argv, pyc, ask
        if folder in sys.path:
            sys.path.remove(folder)
        for name in set(sys.modules) - loaded:
            file = getattr(sys.modules[name], "__file__", None)
            if file and Path(file).is_relative_to(info.folder):
                del sys.modules[name]
        os.chdir(cwd)
    return Result(error is None, error, time.perf_counter() - start, out.getvalue())
