"""課程作業第一階段的 N1–N3（設計第 8.1 節），要網路，pytest 不收，跟 smoke.py 一樣自己跑。

    python3 tests/acceptance_coursework.py [--keep <空資料夾>]

先把範例課程「科學計算」複製到暫存資料夾，用框架的「檢查與打包」打 HK2 的學生包（真的打包結果，不是另外寫的），解開成兩份：

N1  近似乾淨的學生：照解開的 README.txt 裡「前面剛好四個空格、python3 開頭」的指令逐行執行（指令從 README 讀出來，
    不是另外寫一份），最後一行加 --case case-1。環境變數 PYTHONNOUSERSITE=1（這台 Mac 的 numpy 在 user site，
    要藏起來）、MPLBACKEND=Agg；pip 與 matplotlib 的快取也指到暫存資料夾，所以裝的東西全部在暫存資料夾裡。
    結束碼 0、.venv 裡 import 得了 numpy 與 matplotlib、系統 python3 的 pip list --user 跑前跑後一樣。
    沒有網路就說「沒網路，N1 沒跑」，結束碼非零。
N2  同一包用 /usr/bin/python3（Apple 的 3.9）跑 HK2.py：印「要 3.10 以上」那一句、結束碼 1、沒有 traceback。
N3  打出來的 zip 掃一次：沒有家目錄路徑、帳號名、外接硬碟的掛載路徑、暫存資料夾的路徑。

每一項印出證據（秒數、.venv 的 MB、句子）。全部通過結束碼 0。暫存資料夾跑完刪掉；--keep 給一個空的（或不存在的）資料夾就留下。
不碰系統的 Python、不用 --user。"""

import argparse
import getpass
import importlib.util
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import NamedTuple

SRC = Path(__file__).resolve().parents[1]
CW = SRC / "modules" / "課程作業"
EXAMPLE = CW / "範例課程" / "科學計算"
CODE = "HK2"
CASE = "case-1"
OLD_PYTHON = "/usr/bin/python3"
PYPI = ("pypi.org", 443)
MIN_PYTHON = (3, 10)
HIDDEN_ENV = ("VIRTUAL_ENV", "PYTHONPATH", "PYTHONHOME")


class Result(NamedTuple):
    code: int
    out: str  # stdout 加 stderr


def sh(argv, cwd=None, env=None):
    """跑一個指令（不經 shell），回結束碼與輸出。找不到程式回 127。"""
    try:
        proc = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", stdin=subprocess.DEVNULL, timeout=3600)
    except FileNotFoundError:
        return Result(127, f"找不到 {argv[0]}")
    return Result(proc.returncode, proc.stdout + proc.stderr)


def online(address=PYPI, timeout=10):
    try:
        socket.create_connection(address, timeout=timeout).close()
    except OSError:
        return False
    return True


def load(path, name):
    """從檔案載入一個模組（不寫 .pyc；dataclass 要在 sys.modules 裡找得到自己，所以留著）。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name], pyc = module, sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = pyc
    return module


class Recorder:
    """框架要的 app，只要 log、ask、reveal；問哪一份一律回 HK2。"""

    def __init__(self):
        self.logs = []

    def log(self, text):
        self.logs.append(text)

    def ask(self, prompt, default=""):
        return CODE

    def reveal(self, path):
        pass


# ---------- 打包與解開 ----------

def pack_example(work):
    """範例課程複製到 work/課/科學計算，用框架的「檢查與打包」打 HK2，回 zip 的路徑。"""
    course = load(CW / "框架" / "course.py", "cw_course_for_acceptance")
    folder = Path(work) / "課" / "科學計算"
    shutil.copytree(EXAMPLE, folder, ignore=shutil.ignore_patterns("__pycache__"))
    app = Recorder()
    course.check_and_pack(app, folder)
    target = folder / course.SENT / f"{CODE}_學生包.zip"
    if not target.is_file():
        raise RuntimeError("打包沒有產生 zip：" + "；".join(app.logs))
    return target


def unpack(zip_path, dest):
    """zip 解開到 dest，回裡面的 HK2/ 資料夾。"""
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)
    return Path(dest) / CODE


# ---------- 從 README 讀指令 ----------

def readme_commands(text):
    """README 裡前面剛好四個空格、python3 開頭的行（縮六格的重建指令、Windows 的 py 不算）。"""
    found = (re.fullmatch(r" {4}(python3 \S.*?)\s*", line) for line in text.splitlines())
    return [m.group(1) for m in found if m]


def student_steps(commands):
    """逐行拆成 argv；最後一行（跑作業）加 --case。"""
    if not commands:
        raise ValueError("README 裡沒有 python3 開頭的指令")
    steps = [shlex.split(command) for command in commands]
    steps[-1] += ["--case", CASE]
    return steps


def student_env(base, work):
    """學生的終端機：藏起 user site，看不到開發用的 venv；pip 與 matplotlib 的快取都放在暫存資料夾。"""
    env = {k: v for k, v in base.items() if k not in HIDDEN_ENV}
    venv = base.get("VIRTUAL_ENV")
    if venv and "PATH" in env:
        env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep) if Path(p) != Path(venv) / "bin")
    env.update(PYTHONNOUSERSITE="1", MPLBACKEND="Agg",
               PIP_CACHE_DIR=str(Path(work) / "pip-cache"), MPLCONFIGDIR=str(Path(work) / "matplotlib"))
    return env


def venv_mb(folder):
    total = sum(f.stat().st_size for f in Path(folder).rglob("*") if f.is_file() and not f.is_symlink())
    return total / 1_000_000


def tail(text, n=15):
    return "\n".join(f"      {line}" for line in text.strip().splitlines()[-n:])


def user_packages(sh, python, env):
    """系統 python3 的 pip list --user（不設 PYTHONNOUSERSITE，不然看不到 user site）。"""
    return sh([python, "-m", "pip", "list", "--user", "--format=json"], env=env).out.strip()


# ---------- N1 ----------

def n1(folder, work, sh=sh, system_python=None, base_env=None):
    base = dict(os.environ if base_env is None else base_env)
    env = student_env(base, work)
    listing_env = {k: v for k, v in env.items() if k != "PYTHONNOUSERSITE"}
    python = system_python or shutil.which("python3", path=env.get("PATH")) or "python3"
    before = user_packages(sh, python, listing_env)
    steps = student_steps(readme_commands((Path(folder) / "README.txt").read_text(encoding="utf-8")))
    began = time.monotonic()
    for step in steps:
        started = time.monotonic()
        result = sh(step, cwd=folder, env=env)
        print(f"  $ {' '.join(step)}    ({time.monotonic() - started:.1f} 秒，結束碼 {result.code})")
        if result.code != 0:
            print(tail(result.out))
            return False
        if step[1:] == ["--version"]:
            found = re.search(r"Python (\d+)\.(\d+)", result.out)
            if not found or (int(found.group(1)), int(found.group(2))) < MIN_PYTHON:
                print(f"  這台的 python3 是 {result.out.strip()!r}，不到 3.10：README 第 3 步就過不了，N1 驗不了")
                return False
    total = time.monotonic() - began
    venv_python = Path(folder) / ".venv" / "bin" / "python"
    check = sh([str(venv_python), "-c", "import numpy, matplotlib"], cwd=folder, env=env)
    print(f"  .venv 裡 import numpy、matplotlib：結束碼 {check.code}")
    if check.code != 0:
        print(tail(check.out))
        return False
    after = user_packages(sh, python, listing_env)
    if before != after:
        print("  系統 python3 的 pip list --user 跑前跑後不一樣：")
        print(f"    前：{before[:300]}\n    後：{after[:300]}")
        return False
    print(f"  總共 {total:.1f} 秒；.venv {venv_mb(Path(folder) / '.venv'):.0f} MB；pip list --user 前後一樣")
    return True


# ---------- N2 ----------

def n2(folder, sh=sh, python=OLD_PYTHON, base_env=None):
    base = {k: v for k, v in dict(os.environ if base_env is None else base_env).items() if k not in HIDDEN_ENV}
    base["PYTHONNOUSERSITE"] = "1"
    shell = load(Path(folder) / "coursework.py", "cw_shell_for_acceptance")
    opening = shell.TOO_OLD.split("{have}")[0]
    result = sh([python, f"{CODE}.py"], cwd=folder, env=base)
    first = result.out.strip().splitlines()[0] if result.out.strip() else ""
    print(f"  $ {python} {CODE}.py    (結束碼 {result.code})\n      {first}")
    if result.code != 1:
        print(f"  結束碼要是 1，是 {result.code}")
        return False
    if not result.out.startswith(opening):
        print(f"  輸出要以「{opening}」開頭")
        return False
    if "Traceback" in result.out:
        print("  輸出裡有 Traceback")
        return False
    return True


# ---------- N3 ----------

def scan_needles(work):
    return {"家目錄": str(Path.home()), "帳號名": getpass.getuser(),
            "外接硬碟": str(Path("/", "Volumes")), "暫存資料夾": str(work)}


def scan_zip(zip_path, needles):
    """zip 的每個成員的名字與內容，有哪些東西不該出現：回 [(成員, 哪一種)]。"""
    found = []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            data = b"" if info.is_dir() else z.read(info)
            for key, needle in needles.items():
                raw = needle.encode("utf-8")
                if raw and (raw in info.filename.encode("utf-8") or raw in data):
                    found.append((info.filename, key))
    return found


# ---------- 主程式 ----------

def main(argv=None):
    parser = argparse.ArgumentParser(description="課程作業 N1–N3（要網路）")
    parser.add_argument("--keep", metavar="資料夾", help="暫存資料夾留在這裡（要是空的或不存在）；不給就跑完刪掉")
    args = parser.parse_args(argv)
    if args.keep:
        work = Path(args.keep).expanduser().resolve()
        if work.exists() and (not work.is_dir() or any(work.iterdir())):
            print(f"--keep 要給一個空的資料夾，{work} 裡面已經有東西：什麼都沒做")
            return 1
        work.mkdir(parents=True, exist_ok=True)
    else:
        work = Path(tempfile.mkdtemp(prefix="cw-accept-")).resolve()
    try:
        return run(work)
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


def run(work):
    print(f"暫存資料夾：{work}")
    zip_path = pack_example(work)
    print(f"打包 {CODE}：{zip_path.name}（{zip_path.stat().st_size} bytes）")
    results = {}
    print("N1 照 README 的指令做（要網路）")
    if online():
        results["N1"] = n1(unpack(zip_path, work / "學生"), work)
    else:
        print("  沒網路，N1 沒跑")
        results["N1"] = False
    print(f"N2 用 {OLD_PYTHON} 跑")
    results["N2"] = n2(unpack(zip_path, work / "舊"))
    print("N3 掃 zip")
    found = scan_zip(zip_path, scan_needles(work))
    for member, key in found:
        print(f"  {member}：有{key}")
    results["N3"] = not found
    print()
    for name, ok in results.items():
        print(f"{name}  {'通過' if ok else '沒過（或沒跑）'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
