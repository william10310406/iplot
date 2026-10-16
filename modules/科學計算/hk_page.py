"""作業的殼 v0（docs/09_作業規範.md）：新格式的作業檔最後那六行叫的四個東西——ensure、main、show、collect——
加上 python hk_page.py --check <檔>。這一版沒有網頁：畫面是 matplotlib 自己的視窗，文字印在終端機。

學生的檔在 ensure 之前就 import hk_page，所以這個檔頂層只 import 標準庫；numpy、matplotlib 在用到的函式裡才 import。
學生的包裡只有這個檔（沒有 hk_tk.py），所以 pip 名對照表、import 掃描在這裡各自複製一份。
"""

import ast
import contextlib
import importlib
import importlib.metadata
import os
import platform
import re
import site
import subprocess
import sys
import traceback
from pathlib import Path

NO_INSTALL = "HK_NO_INSTALL"  # 設了就不跑 pip，缺了只報（測試用）
# iPLoT（面板、批次名單）另開的子程序都帶著：不自動補 REQUIRES（收進來的檔絕不被改），
# 不在 venv 裡就不裝（不裝進 iPLoT 自己的、系統的 Python），也不問 case（--all，沒有終端機可答）
FROM_IPLOT = "HK_FROM_IPLOT"
NAME_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"  # pip 名只接這些字元，不經 shell
PIP_NAMES = {"cv2": "opencv-python", "PIL": "Pillow", "sklearn": "scikit-learn", "kan": "pykan", "mlx_lm": "mlx-lm",
             "pywt": "PyWavelets", "yaml": "PyYAML", "bs4": "beautifulsoup4", "skimage": "scikit-image",
             "dateutil": "python-dateutil", "mpl_toolkits": "matplotlib", "pylab": "matplotlib"}
APPLE_SILICON_ONLY = ("mlx-lm",)
# 規範第 1 節下半那幾行（不用改的固定尾段）；HOMEWORK = dict(…) 那一行另外查鍵
TAIL = ("import sys", "def run(app): hk_page.show(app, HOMEWORK)", "def on_files(app, paths): hk_page.collect(app, paths)",
        'if __name__ == "__main__" and "core.runner" not in sys.modules:', "    hk_page.main(HOMEWORK)")
REQUIRED = ("REQUIRES", "NAME", "CASES", "compute", "HOMEWORK")
HOMEWORK_KEYS = ("name", "cases", "compute")
FORBIDDEN_IMPORTS = ("tkinter", "_tkinter", "turtle")
FORBIDDEN_CALLS = ("plt.show", "input", "os.chdir")
ABSOLUTE = ("/Users/", "C:\\", "C:/", "/home/")
NOT_PACKAGES = {"hk_page"}  # 殼自己：跟作業檔放在一起，不是 pip 套件


# ── 套件 ──


def _normal(dist: str) -> str:
    return re.sub(r"[-_.]+", "-", dist).lower()


def imports_of(file: Path) -> set[str]:
    """檔裡所有 import 的頂層名字（連函式裡的，ast.walk 整棵樹；相對 import 不算）；讀不懂回空集合。"""
    try:
        tree = ast.parse(Path(file).read_text(encoding="utf-8-sig"))
    except (SyntaxError, ValueError, OSError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def third_party(names: set[str], folder: Path) -> set[str]:
    """扣掉標準庫、__future__、hk_page、folder 裡同名的 .py 或資料夾。"""
    try:
        siblings = {p.stem if p.suffix == ".py" else p.name for p in Path(folder).iterdir()}
    except OSError:
        siblings = set()
    return set(names) - set(sys.stdlib_module_names) - {"__future__"} - NOT_PACKAGES - siblings


def dist_for(name: str) -> str:
    """import 名 → pip 名：裝了的照它自己的 metadata，沒裝的查對照表，都沒有就同名。"""
    found = importlib.metadata.packages_distributions().get(name)
    return found[0] if found else PIP_NAMES.get(name, name)


def _covered(requires: list[str]) -> set[str]:
    """REQUIRES 裡那些套件提供的 import 名（裝了的照 metadata；沒裝的當作提供同名的，再加對照表反查）。"""
    wanted = {_normal(r) for r in requires}
    names = {imp for imp, dists in importlib.metadata.packages_distributions().items()
             if any(_normal(d) in wanted for d in dists)}
    names |= {imp for imp, pip in PIP_NAMES.items() if _normal(pip) in wanted}
    names |= {r for r in requires} | {_normal(r).replace("-", "_") for r in requires}
    return names


def _forgotten(file: Path, requires: list[str]) -> list[str]:
    """檔裡 import 了、REQUIRES 沒寫的 pip 名（照 import 名排序，不重複）。"""
    file = Path(file)
    names = sorted(third_party(imports_of(file), file.parent) - _covered(requires))
    out, have = [], {_normal(r) for r in requires}
    for dist in map(dist_for, names):
        if _normal(dist) not in have:
            have.add(_normal(dist))
            out.append(dist)
    return out


def requires_line(source: str) -> tuple[int, int, str] | None:
    """頂層 REQUIRES = [...] 那一行：（行號, 結束行號, 那一行 list 後面的字（註解，含前面的空白）或 ""）。
    寫成好幾行的 list、不是 list 字面值、沒有 REQUIRES：回 None。"""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "REQUIRES" and isinstance(node.value, ast.List)):
            if node.lineno != node.end_lineno:
                return None
            # 行號照 ast 算（只認 \n、\r、\r\n；str.splitlines 還會在 \x0c、U+2028 斷行），col_offset 是 UTF-8 的 byte
            line = source.encode("utf-8").splitlines()[node.lineno - 1]
            return node.lineno, node.end_lineno, line[node.value.end_col_offset:].decode("utf-8")
    return None


def fill_requires(file: Path, extra: list[str]) -> bool:
    """把 extra 補進 file 裡 REQUIRES = [...] 那一行：雙引號、原來的順序在前、註解留著；其他行一個 byte 都不動。
    回有沒有改。寫成好幾行的 REQUIRES 不改，印一句叫人手動加。"""
    file = Path(file)
    data = file.read_bytes()
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    source = data[len(bom):].decode("utf-8")
    found = requires_line(source)
    if found is None:
        if extra:
            print(f"REQUIRES 寫成好幾行（或不是一個 list），沒有自動補：請手動加 {'、'.join(extra)}")
        return False
    lineno, _, comment = found
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "REQUIRES")
    names = list(ast.literal_eval(node.value))
    have = {_normal(n) for n in names}
    for name in extra:
        if _normal(name) not in have:
            have.add(_normal(name))
            names.append(name)
    if len(names) == len(ast.literal_eval(node.value)):
        return False
    lines = data[len(bom):].splitlines(keepends=True)
    old = lines[lineno - 1]
    ending = old[len(old.rstrip(b"\r\n")):]
    lines[lineno - 1] = ("REQUIRES = [" + ", ".join(f'"{n}"' for n in names) + "]" + comment).encode("utf-8") + ending
    try:
        file.write_bytes(bom + b"".join(lines))
    except OSError:
        print(f"這個檔寫不進去，沒有自動補：請手動把 {'、'.join(extra)} 加進 REQUIRES")
        return False
    return True


def missing(requires: list[str]) -> list[str]:
    """requires 裡這個 Python 還沒裝的（不重複、照原順序）。"""
    out = []
    for name in requires:
        try:
            importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            if _normal(name) not in map(_normal, out):
                out.append(name)
    return out


def _course(file: Path) -> Path | None:
    """往上找第一個有 hk_tk.py 的資料夾（課程資料夾）。"""
    file = Path(file).resolve()
    return next((p for p in file.parents if (p / "hk_tk.py").is_file()), None)


def _venv_python(course: Path | None) -> Path | None:
    if course is None:
        return None
    python = course / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    return python if python.is_file() else None


def _hand_off(file: Path, need: list[str], popen) -> None:
    """在 iPLoT 的面板程序裡、面板的 Python 缺套件：不裝、不改檔，交給課程的 .venv 另開程序跑這個檔，
    然後正常結束（runner 把 sys.exit(0) 當作跑完；印的那句進訊息區）。"""
    file = Path(file).resolve()
    python = _venv_python(_course(file))
    if python is None:
        print(f"iPLoT 的 Python 沒有 {'、'.join(need)}，課程的 .venv 也還沒建：先按「科學計算」裝課程套件")
    else:
        print(f"iPLoT 的 Python 沒有 {'、'.join(need)}；改用課程的 .venv 另開視窗跑")
        popen([str(python), str(file), "--all"], cwd=str(file.parent), env={**os.environ, FROM_IPLOT: "1"})
    sys.exit(0)


def ensure(requires: list[str], file: str, popen=subprocess.Popen, argv: list[str] | None = None) -> None:
    """作業檔第二行：缺的套件裝進正在跑的這個 Python（不在 venv 裡就加 --user），裝完才往下 import。
    學生自己跑自己的檔時，先把檔裡 import 了、REQUIRES 沒寫的補進 REQUIRES 那一行。
    在 iPLoT 的面板程序裡絕不裝、絕不改檔：缺了就交給課程的 .venv（回報第 0 節「要定的事」第 2 條）。"""
    requires = [requires] if isinstance(requires, str) else list(requires)
    if "core.runner" in sys.modules:
        need = missing(requires + _forgotten(Path(file), requires))  # 只看、不改
        if need:
            _hand_off(Path(file), need, popen)
        return
    extra = []
    own = Path(file).resolve() == Path((argv if argv is not None else sys.argv)[0]).resolve()
    if own and not os.environ.get(FROM_IPLOT) and _course(Path(file)) is None:  # 課程資料夾裡的是收進來的或老師的
        extra = _forgotten(Path(file), requires)
        if extra and fill_requires(Path(file), extra):
            print(f"已把 {'、'.join(extra)} 加進 REQUIRES")
    need = missing(requires + extra)
    if not need:
        return
    if os.environ.get(NO_INSTALL):
        raise RuntimeError(f"缺 {'、'.join(need)}；HK_NO_INSTALL 設著，不裝")
    bad = [n for n in need if not re.match(NAME_RE, n)]
    if bad:
        raise RuntimeError(f"套件名字不合法：{'、'.join(bad)}")
    arm_mac = sys.platform == "darwin" and platform.machine() == "arm64"
    only = [n for n in need if _normal(n) in {_normal(x) for x in APPLE_SILICON_ONLY}]
    if only and not arm_mac:
        raise RuntimeError(f"{'、'.join(only)} 只有 Apple Silicon 的 Mac 裝得了：這份作業要在 Apple Silicon 的 Mac 上跑")
    in_venv = sys.prefix != sys.base_prefix
    if os.environ.get(FROM_IPLOT) and not in_venv:
        raise RuntimeError(f"缺 {'、'.join(need)}：先按「科學計算」裝課程套件（不裝進 iPLoT 自己的 Python）")
    print(f"在裝 {'、'.join(need)}（第一次要幾分鐘）…")
    argv_pip = [sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
                *([] if in_venv else ["--user"]), *need]
    if popen(argv_pip).wait() != 0:
        raise RuntimeError(f"裝不了 {'、'.join(need)}：在終端機 {sys.executable} -m pip install {' '.join(need)}")
    if not in_venv:  # 剛建好的 user site 不在 sys.path 上（Python 啟動時它還不在）
        site.addsitedir(site.getusersitepackages())
    importlib.invalidate_caches()


# ── 跑：單獨跑是終端機選 case＋matplotlib 的視窗；在 iPLoT 裡是另開一個程序跑同一個檔（規範第 5 節）──


def _choose(cases: list[str], hw: dict, argv: list[str], ask, out) -> list[str] | None:
    """要跑哪幾個 case：--case <名> 直接指定、--all 全部；不然列出來問，0 是全部。選不了印一句、回 None。"""
    if "--all" in argv:
        return cases
    if "--case" in argv:
        i = argv.index("--case")
        name = argv[i + 1] if i + 1 < len(argv) else ""
        if name in cases:
            return [name]
        print(f"沒有 {name}：有 {'、'.join(cases)}", file=out)
        return None
    for n, name in enumerate(cases, 1):
        print(f"{n}) {name}  {hw['cases'][name].get('label', '')}", file=out)
    print("0) 全部", file=out)
    try:
        answer = ask("選：").strip()
    except EOFError:
        answer = ""
    number = int(answer) if answer.isdecimal() else -1  # ①、² 這種 isdigit 但 int() 不收的，當作沒選
    if number == 0:
        return cases
    if 1 <= number <= len(cases):
        return [cases[number - 1]]
    print(f"要選 0 到 {len(cases)} 之間的數字", file=out)
    return None


TEXT_FONTS = ("PingFang TC", "Heiti TC", "Microsoft JhengHei", "Noto Sans CJK TC", "Arial Unicode MS")


def _show_text(title: str, text: str, show_fn=None) -> None:
    """把文字結果放進一個 matplotlib 視窗（iPLoT 另開的程序沒有終端機，印出來沒人看得到）。"""
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    installed = {f.name for f in font_manager.fontManager.ttflist}
    fonts = [f for f in TEXT_FONTS if f in installed] + ["DejaVu Sans"]  # 只列裝了的：不然 matplotlib 一直警告
    fig = plt.figure(figsize=(7, 6))
    try:
        with contextlib.suppress(AttributeError):
            fig.canvas.manager.set_window_title(f"{title}（文字）")
        fig.text(0.03, 0.97, text, va="top", ha="left", fontfamily=fonts, fontsize=11, wrap=True)
        (show_fn or plt.show)()
    finally:
        plt.close(fig)


def main(hw: dict, argv: list[str] | None = None, ask=input, out=None, show_fn=None) -> int:
    """單獨跑（python3 HKn.py）：選 case；每個 case 先 compute，印 text 與 stats，有 draw 就開一個 matplotlib
    視窗（關掉才下一個）。一個 case 出錯印 traceback 全文、接著跑下一個。回結束碼。"""
    out = out or sys.stdout
    with contextlib.suppress(AttributeError, ValueError):
        out.reconfigure(encoding="utf-8")
    cases = list(hw["cases"])
    chosen = _choose(cases, hw, list(sys.argv[1:] if argv is None else argv), ask, out)
    if chosen is None:
        return 2
    for case in chosen:
        print(f"── {case} ──", file=out)
        try:
            run = hw["compute"](case)
            lines = [run["text"]] if run.get("text") else []
            lines += [f"{key}：{value}" for key, value in (hw.get("stats") or (lambda r: []))(run)]
            for line in lines:
                print(line, file=out)
            if lines and os.environ.get(FROM_IPLOT):  # iPLoT 另開的程序沒有終端機：文字與數字也開一個視窗
                _show_text(f"{hw['name']} — {case}", "\n".join(lines), show_fn)
            if hw.get("draw"):
                import matplotlib.pyplot as plt  # 只有要畫圖時才 import（頂層只 import 標準庫）

                fig = plt.figure(figsize=(7, 6))
                try:
                    with contextlib.suppress(AttributeError):
                        fig.canvas.manager.set_window_title(f"{hw['name']} — {case}")
                    ani = hw["draw"](fig, run)  # 動畫要抓著，不然一回來就被回收、畫面不動
                    (show_fn or plt.show)()
                    del ani
                finally:
                    plt.close(fig)  # draw 畫到一半壞了也關掉，不然下一個 case 的視窗會一起跳出來
        except Exception:  # noqa: BLE001  學生的 compute／draw 怎麼壞都印出來，接著跑下一個 case
            traceback.print_exc(file=out)
    return 0


def show(app, hw: dict, popen=subprocess.Popen) -> None:
    """在 iPLoT 裡按下去：用課程 .venv 的 Python 另開一個程序跑這個檔（走它自己的 main，--all 一個 case 一個視窗，
    不問：iPLoT 另開的程序沒有終端機可答），立刻回來。"""
    file = Path(hw["file"]).resolve()
    course = _course(file)
    python = _venv_python(course)
    if python is None:
        python = Path(sys.executable)
        if course is not None:
            app.log("課程的 .venv 還沒建：先按「科學計算」裝課程套件；這次用 iPLoT 自己的 Python 試")
    popen([str(python), str(file), "--all"], cwd=str(file.parent), env={**os.environ, FROM_IPLOT: "1"})
    app.log(f"{file.parent.name}：{hw['name']} 的視窗開了（在 Dock 上找 Python）")


def collect(app, paths) -> None:
    """把 TronClass 的 zip 收進這份作業（收作業只有一份程式：轉給課程資料夾的 hk_tk.collect）。"""
    folder = Path(app.module.folder)
    course = _course(folder / "iplot.py")
    if course is None:
        app.log("找不到課程資料夾（上層沒有 hk_tk.py），沒有收")
        return
    sys.modules.pop("hk_tk", None)  # 讀課程資料夾裡現在那一份
    sys.path.insert(0, str(course))
    try:
        import hk_tk
    finally:
        sys.path.remove(str(course))
    hk_tk.collect(app, [Path(p) for p in paths], folder)


# ── 發作業前的靜態檢查（規範第 7 節）──


def _dotted(node) -> str:
    """ast 的 func 轉成 a.b.c；轉不了回 ""。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else ""
    return ""


def _top_names(tree: ast.Module) -> set[str]:
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _assigned(tree: ast.Module, name: str):
    """頂層 name = … 的值（最後一個）；沒有回 None。"""
    found = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            found = node.value
    return found


def _code_part(line: str) -> str:
    return line.split("#", 1)[0].strip() if "#" in line else line.strip()


def check(file: Path) -> list[str]:
    """規範第 7 節的靜態檢查；回問題清單（每條一句），空的就是通過。不執行檔案。"""
    file = Path(file)
    try:
        source = file.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return ["這個檔不是 UTF-8"]
    except OSError:
        return [f"讀不到這個檔：{file}"]
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        line = getattr(exc, "lineno", None)
        return [f"語法錯誤：第 {line} 行" if line else "語法錯誤（檔裡有不能出現的字元）"]
    problems = [f"少了 {name}" for name in REQUIRED if name not in _top_names(tree)]
    code_lines = {_code_part(line) for line in source.splitlines()}
    problems += [f"固定尾段少了這一行（或被改了）：{t.strip()}" for t in TAIL if t.strip() not in code_lines]
    hw = _assigned(tree, "HOMEWORK")
    if isinstance(hw, ast.Call) and _dotted(hw.func) == "dict":
        keys = {k.arg: k.value for k in hw.keywords if k.arg}
        problems += [f"HOMEWORK = dict(…) 裡少了 {k}=" for k in HOMEWORK_KEYS if k not in keys]
        if not (isinstance(keys.get("file"), ast.Name) and keys["file"].id == "__file__"):
            problems.append("HOMEWORK = dict(…) 要寫 file=__file__")
        defined = _top_names(tree) | set(REQUIRED) | {"__file__"}  # REQUIRED 少了的上面已經說過
        for value in keys.values():  # 固定尾段那一行用到的名字都要有，不然 import 就 NameError
            if isinstance(value, ast.Name) and value.id not in defined:
                empty = {"DOCS": "DOCS = []", "NOTE": 'NOTE = ""'}.get(value.id, f"{value.id} = None")
                problems.append(f"HOMEWORK = dict(…) 用到的 {value.id} 沒有定義（不需要就寫 {empty}）")
    elif hw is not None:
        problems.append("HOMEWORK 要寫成 HOMEWORK = dict(…)，照規範第 1 節的固定尾段")
    imported = imports_of(file)
    problems += [f"不能 import {name}：畫面是殼的事" for name in FORBIDDEN_IMPORTS if name in imported]
    calls = {_dotted(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    problems += [f"不能呼叫 {name}()：圖畫在 draw 收到的 fig 上、檔案從 DATA 讀" for name in FORBIDDEN_CALLS if name in calls]
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(ABSOLUTE):
            problems.append(f"不能寫絕對路徑：{node.value}（從 DATA 或 Path(__file__) 出發）")
    req = _assigned(tree, "REQUIRES")
    try:
        value = ast.literal_eval(req) if req is not None else []
    except (ValueError, TypeError, SyntaxError):
        value = None
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        requires = list(value)
    else:
        requires = []
        problems.append('REQUIRES 要是一個 list，像 ["numpy", "matplotlib"]')
    forgotten = _forgotten(file, requires)
    if forgotten:
        problems.append(f"REQUIRES 漏了 {'、'.join(forgotten)}")
    data = _assigned(tree, "DATA")
    space = data.right.value if isinstance(data, ast.BinOp) and isinstance(data.right, ast.Constant) else None
    if isinstance(space, str) and not (file.parent / space).is_dir():
        problems.append(f"DATA 指的資料夾不存在：{space}")
    return problems


def cli(argv: list[str]) -> int:
    """python hk_page.py --check <檔>：印每條問題，有問題回 1；全過印「通過」回 0。"""
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) != 2 or argv[0] != "--check":
        print("用法：python hk_page.py --check <作業檔>", file=sys.stderr)
        return 2
    problems = check(Path(argv[1]))
    for p in problems:
        print(f"✗ {p}")
    if not problems:
        print("通過")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))
