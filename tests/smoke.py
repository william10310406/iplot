"""規格 §12 從零啟動情境 1–6：每個情境複製一份乾淨的 iPLoT 到暫存目錄，真的啟動 8 秒，
看還活著沒、stderr 乾不乾淨。只驗「啟動後活著」；按下按鈕之後的行為由 tests/test_startup.py 驗（D43）。

用法：python3 tests/smoke.py    （PYTHON 環境變數可指定直譯器，預設是跑這個檔的那一個）
三個平台都是這一個檔；Linux 沒有顯示器時前面加 xvfb-run -a。"""

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PY = os.environ.get("PYTHON", sys.executable)
SRC = Path(__file__).resolve().parents[1]
SECONDS = 8
NO_DND = ("import sys, runpy; sys.modules['tkinterdnd2'] = None; "
          "runpy.run_path('main.py', run_name='__main__')")
# （說明，要寫進乾淨副本的檔案，啟動指令）
SCENARIOS = [
    ("空 modules/、空上一層", {}, [PY, "main.py"]),
    ("ROOTS 含不存在的路徑", {"config.py": 'ROOTS = ["modules", "/nonexistent"]\n'}, [PY, "main.py"]),
    ("config.py 語法錯誤", {"config.py": "ROOTS = [\n"}, [PY, "main.py"]),
    ("只有一個語法錯誤的模組", {"modules/壞掉/iplot.py": "def run(app)\n    pass\n"}, [PY, "main.py"]),
    ("模組 run 丟例外", {"modules/炸/iplot.py": "def run(app):\n    1/0\n"}, [PY, "main.py"]),
    ("沒裝 tkinterdnd2", {}, [PY, "-c", NO_DND]),
]
started: list[subprocess.Popen] = []


def fresh(work: Path, n: int) -> Path:
    """乾淨副本：只有 main.py、config.py、core/、ui/、空的 modules/；上一層只有它自己。"""
    home = work / str(n) / "iPLoT"
    (home / "modules").mkdir(parents=True)
    for name in ("main.py", "config.py"):
        shutil.copy(SRC / name, home / name)
    for name in ("core", "ui"):
        shutil.copytree(SRC / name, home / name, ignore=shutil.ignore_patterns("__pycache__"))
    return home


def check(n: int, what: str, cwd: Path, argv: list[str]) -> bool:
    """在 cwd 啟動 argv，等 8 秒：還活著而且 stderr 是空的才算過。"""
    err = cwd.parent / "stderr.txt"
    with err.open("wb") as f:
        proc = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.DEVNULL, stderr=f)
    started.append(proc)
    time.sleep(SECONDS)
    code = proc.poll()
    proc.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=5)
    status = "活著" if code is None else f"死了，結束碼 {code}"
    text = err.read_text(encoding="utf-8", errors="replace")
    if text:
        print(f"情境 {n}（{what}）：{status}，stderr 不乾淨：")
        print("".join(f"    {line}\n" for line in text.splitlines()), end="")
    else:
        print(f"情境 {n}（{what}）：{status}，stderr 乾淨")
    return code is None and not text


def main() -> int:
    """六個情境依序跑；全過回 0，否則 1。不留下任何 iPLoT 視窗。"""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 的主控台不一定是 UTF-8
    ok = True
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        try:
            for n, (what, files, argv) in enumerate(SCENARIOS, start=1):
                home = fresh(Path(tmp), n)
                for name, text in files.items():
                    (home / name).parent.mkdir(parents=True, exist_ok=True)
                    (home / name).write_text(text, encoding="utf-8")
                ok = check(n, what, home, argv) and ok
        finally:
            for proc in started:
                if proc.poll() is None:
                    proc.kill()
    print(f"smoke：{len(SCENARIOS)} 個情境全部活著、stderr 乾淨" if ok else "smoke：有情境失敗")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
