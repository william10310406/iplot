"""課程作業的測試共用工具。不是 test_ 開頭，不會被 pytest 收集；tests/ 沒有 __init__.py，
pytest 預設把 tests/ 放進 sys.path，測試檔直接 from cw_support import …"""

import importlib.util
import sys
import types
from pathlib import Path

from conftest import FakeApp

ROOT = Path(__file__).resolve().parents[1]
CW = ROOT / "modules" / "課程作業"  # 模組資料夾
FRAMEWORK = CW / "框架" / "course.py"
TYPE_DIR = CW / "作業類型" / "算完畫圖"


def load(path: Path, name: str):
    """從檔案載入一個模組：不寫 .pyc；執行期間放在 sys.modules（dataclass 要找得到），用完拿掉。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    old, pyc = sys.modules.get(name), sys.dont_write_bytecode
    sys.modules[name], sys.dont_write_bytecode = module, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = pyc
        if old is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = old
    return module


class CwApp(FakeApp):
    """FakeApp 加上課程作業會叫的：ask（answers_ask 依序回，用完回 default；None 是按了取消）、
    edit、reveal、open、choose_files、choose_folder，都記下來；module.folder 是正在執行的模組資料夾。"""

    def __init__(self, home, module_folder=None, **config):
        super().__init__(home, **config)
        self.module = types.SimpleNamespace(folder=Path(module_folder or home))
        self.answers_ask, self.asks = [], []  # ask 依序要回的答案；問過的 (提示, 預設)
        self.edits, self.revealed, self.opened = [], [], []
        self.files, self.folder_answer = [], None  # choose_files、choose_folder 要回的

    def ask(self, prompt, default=""):
        self.asks.append((prompt, default))
        return self.answers_ask.pop(0) if self.answers_ask else default

    def edit(self, path, line=None):
        self.edits.append((Path(path), line))

    def reveal(self, path):
        self.revealed.append(Path(path))

    def open(self, path):
        self.opened.append(Path(path))

    def choose_files(self):
        return list(self.files)

    def choose_folder(self):
        return self.folder_answer


class _FakeProcess:
    def __init__(self, argv, kwargs, returncode, lines):
        self.args, self.kwargs, self.returncode = list(argv), kwargs, returncode
        self.stdout = iter(lines)
        self._lines = list(lines)

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def communicate(self, timeout=None):
        return "".join(self._lines), ""


class FakePopen:
    """假的 subprocess.Popen：FakePopen(fail=…, lines=…) 這個物件當 popen 注入；每次被叫就在 calls
    記下 (argv, kwargs)。fail(argv) 為真時 returncode 是 1，否則 0；stdout 依序給 lines。"""

    def __init__(self, fail=None, lines=()):
        self.calls, self.fail, self.lines = [], fail, list(lines)

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        return _FakeProcess(argv, kwargs, 1 if self.fail and self.fail(argv) else 0, self.lines)


def make_course(root: Path, name: str = "測試課", **settings) -> Path:
    """在 root 底下建資料夾 name，寫一個 課程.py（NAME 預設是 name；其他名字用關鍵字給，值照字面值寫）。"""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    values = {"NAME": name, **settings}
    lines = ["# 測試用的課程設定：只寫字面值。"] + [f"{key} = {value!r}" for key, value in values.items()]
    (folder / "課程.py").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return folder


HOMEWORK_SRC = """REQUIRES = ["numpy", "matplotlib"]
import coursework; coursework.ensure(REQUIRES, __file__)

NAME = "{code} 範例"
DOCS = []
NOTE = ""
CASES = {"case-1": dict(label="第一個")}

def compute(case): return {}
def draw(fig, run): return None
def stats(run): return ""

HOMEWORK = dict(name=NAME, docs=DOCS, note=NOTE, cases=CASES, compute=compute, draw=draw, stats=stats, file=__file__)
if __name__ == "__main__":
    raise SystemExit(coursework.main(HOMEWORK))
"""


def make_homework(course: Path, n: int, src: str | None = None) -> Path:
    """照課的 CODE 與 FOLDER 建第 n 份作業的資料夾與 <代號>.py（src 不給就用 HOMEWORK_SRC，{code} 換成代號），
    回傳作業檔。代號與資料夾名由框架的 code_of、folder_of 算，跟真的程式同一份。"""
    framework = load(FRAMEWORK, "course")
    info = framework.read_course(course)
    code, folder = framework.code_of(info, n), course / framework.folder_of(info, n)
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / f"{code}.py"
    text = HOMEWORK_SRC.replace("{code}", code) if src is None else src
    file.write_text(text, encoding="utf-8", newline="\n")
    return file
