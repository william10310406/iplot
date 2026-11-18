"""macOS：打開、編輯、顯示、終端機都用 open 指令；垃圾桶走系統的做法（Finder 同一條路），不行才直接搬進 ~/.Trash。"""
import shutil
import subprocess
from pathlib import Path

NAME = "macOS"
GONE = "找不到「{path}」，可能被改名或刪掉了，沒有打開"


def _launch(argv, **kw):
    """啟動後不等。"""
    subprocess.Popen(argv, **kw)


def _there(app, path) -> bool:
    """路徑還在才打開；不在就在訊息區說一句。open 的錯誤只會印在看不到的終端機，使用者只會覺得按了沒反應（體驗 8a-01）。"""
    if isinstance(path, str) and "://" in path:  # 網址不是路徑：不檢查，交給 open
        return True
    try:
        if Path(path).exists():
            return True
    except OSError:  # 查不了（例如沒有權限）：當作在，交給 open 自己處理
        return True
    app.log(GONE.format(path=path))
    return False


def open(app, path):
    """資料夾進 Finder，檔案用預設程式。"""
    if not _there(app, path):
        return
    _launch(["open", str(path)])


def edit(app, path, editor, line):
    """editor 是 None 時用系統預設文字編輯器，否則照 config.py 的 EDITOR；資料夾一律交給 open。"""
    if Path(path).is_dir():
        return open(app, path)
    if not _there(app, path):
        return
    _launch(["open", "-t", str(path)] if editor is None
            else [p.format(file=str(path), line=line or 1) for p in editor])


def reveal(app, path):
    """在 Finder 裡顯示並選取。"""
    if not _there(app, path):
        return
    _launch(["open", "-R", str(path)])


def terminal(app, path):
    """在 Terminal 打開這個資料夾。想換成別的終端機程式，改 "Terminal" 這個名字。"""
    if not _there(app, path):
        return
    _launch(["open", "-a", "Terminal", str(path)])


def requirements(app):
    """網頁面板要裝的套件清單：requirements/ 裡的檔名。"""
    return "web-mac.txt"


def webview_ready(app):
    """網頁面板的前置條件都有就回 None，缺什麼就回一句話。macOS 內建 WebKit，什麼都不缺。"""
    return None


def _system_trash(path):
    """跟 Finder 的「移到垃圾桶」同一條路（NSFileManager 的 trashItemAtURL）：垃圾桶裡可以按「放回」，
    外接硬碟上的東西進那顆硬碟自己的垃圾桶，不用跨碟複製。用 ctypes 呼叫 Objective-C，不裝任何套件。回傳搬到哪裡。"""
    import ctypes
    import ctypes.util

    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    ctypes.cdll.LoadLibrary(ctypes.util.find_library("Foundation"))
    objc.objc_getClass.restype = objc.sel_registerName.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = objc.sel_registerName.argtypes = [ctypes.c_char_p]
    ptr = ctypes.c_void_p

    def send(obj, sel, *args, types=(), result=ptr):
        objc.objc_msgSend.restype, objc.objc_msgSend.argtypes = result, [ptr, ptr, *types]
        return objc.objc_msgSend(obj, objc.sel_registerName(sel), *args)

    def string(obj):
        return ctypes.cast(send(obj, b"UTF8String"), ctypes.c_char_p).value.decode("utf-8")

    pool = send(send(objc.objc_getClass(b"NSAutoreleasePool"), b"alloc"), b"init")
    try:
        text = send(objc.objc_getClass(b"NSString"), b"stringWithUTF8String:", str(path).encode("utf-8"), types=[ctypes.c_char_p])
        url = send(objc.objc_getClass(b"NSURL"), b"fileURLWithPath:", text, types=[ptr])
        manager = send(objc.objc_getClass(b"NSFileManager"), b"defaultManager")
        moved, error = ptr(), ptr()
        ok = send(manager, b"trashItemAtURL:resultingItemURL:error:", url, ctypes.byref(moved), ctypes.byref(error),
                  types=[ptr, ptr, ptr], result=ctypes.c_bool)
        if not ok:
            raise OSError(string(send(error, b"localizedDescription")) if error.value else "trashItemAtURL")
        return Path(string(send(moved, b"path")))
    finally:
        send(pool, b"drain")


def trash(app, path):
    """搬到垃圾桶，回傳搬到哪裡。永遠不刪除。先走系統的做法（可以在垃圾桶裡按「放回」）；
    那條路走不通（找不到系統的函式庫等）就退回直接搬進 ~/.Trash（同名加「 2」「 3」…），這樣只能手動拖回來。"""
    try:
        return _system_trash(path)
    except Exception:  # noqa: BLE001  ctypes 找不到函式庫、系統拒絕都退回舊做法；兩條路都不通時，下面那一條丟出它的錯
        folder, name = Path.home() / ".Trash", Path(path).name
        folder.mkdir(exist_ok=True)
        dest, n = folder / name, 1
        while dest.exists():
            n += 1
            dest = folder / f"{name} {n}"
        shutil.move(str(path), str(dest))
        return dest
