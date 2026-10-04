"""Windows：startfile、notepad、explorer、wt／cmd；垃圾桶走 SHFileOperationW。未經實機驗證。"""
import os
import shutil
import subprocess
from pathlib import Path

NAME = "Windows"


def _launch(argv, **kw):
    """啟動後不等。"""
    subprocess.Popen(argv, **kw)


def open(app, path):
    """資料夾進檔案總管，檔案用預設程式。"""
    os.startfile(str(path))


def edit(app, path, editor, line):
    """editor 是 None 時用記事本，否則照 config.py 的 EDITOR；資料夾一律交給 open。"""
    if Path(path).is_dir():
        return open(app, path)
    if editor is None:
        return _launch(["notepad", str(path)])
    argv = [p.format(file=str(path), line=line or 1) for p in editor]
    argv[0] = shutil.which(argv[0]) or argv[0]  # code 在 Windows 是 code.cmd，要先找出完整路徑
    _launch(argv)


def reveal(app, path):
    """在檔案總管裡顯示並選取。"""
    _launch(["explorer", f"/select,{path}"])


def terminal(app, path):
    """有 Windows Terminal（wt）就用它；沒有就開一個新的 cmd 視窗。"""
    if shutil.which("wt"):
        return _launch(["wt", "-d", str(path)])
    _launch(["cmd"], cwd=str(path), creationflags=0x10)  # 0x10 是 CREATE_NEW_CONSOLE


def trash(app, path):
    """搬到資源回收筒；資源回收筒沒有路徑，所以回 None。永遠不刪除。"""
    import ctypes  # 放在函式裡：windll 只有 Windows 有，其他系統也要 import 得了這個檔

    class _Op(ctypes.Structure):  # SHFILEOPSTRUCTW
        _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint),
                    ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                    ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]

    # wFunc 3 是 FO_DELETE；0x454 = 不顯示進度 0x4 + 不問 0x10 + 可復原（進資源回收筒）0x40 + 不跳錯誤視窗 0x400
    op = _Op(None, 3, str(path) + "\0", None, 0x454, 0, None, None)  # pFrom 要雙 NUL 結尾
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if code:
        raise OSError(f"資源回收筒拒絕：{code}")
    return None
