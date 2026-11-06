"""範本與範例課程「科學計算」（HK2、HK6、HK8 照規範 v2）：--check 全綠；compute／draw／stats 真的跑得動
（Agg、不裝套件、不連網）；單獨 python3 HKn.py 跑得完。範例是從 modules/科學計算/examples/ 複製再改的，原檔不動。"""

import os
import shutil
import subprocess
import sys

import pytest
from cw_support import CW, FRAMEWORK, TYPE_DIR, load

pytest.importorskip("matplotlib")
pytestmark = pytest.mark.filterwarnings("ignore:Animation was deleted")  # 不 show，動畫沒畫出來就被回收，是預期的

TEMPLATE = TYPE_DIR / "範本.py"
COURSE = CW / "範例課程" / "科學計算"
EXAMPLES = {n: COURSE / n / f"{n}.py" for n in ("HK2", "HK6", "HK8")}
ALL = {"範本(HK1)": TEMPLATE, **EXAMPLES}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("CW_NO_INSTALL", "1")
    monkeypatch.setenv("MPLBACKEND", "Agg")
    monkeypatch.delenv("CW_FROM_IPLOT", raising=False)


@pytest.fixture
def cw():
    return load(TYPE_DIR / "coursework.py", "coursework")


@pytest.fixture
def homework(monkeypatch):
    """像 PYTHONPATH 指到殼的資料夾那樣：載入作業檔（第二行 import coursework）；用完把 coursework 從 sys.modules 拿掉。"""
    monkeypatch.syspath_prepend(str(TYPE_DIR))
    monkeypatch.delitem(sys.modules, "coursework", raising=False)
    loaded = []

    def make(path, tmp_path):
        # 範本寫的是 HK1：複製成 HK1.py（連 HK1Space），檔名、DATA 才對得上
        work = tmp_path / path.stem
        work.mkdir()
        dest = work / (path.stem if path != TEMPLATE else "HK1")
        file = work / f"{dest.name}.py"
        shutil.copy(path, file)
        (work / f"{dest.name}Space").mkdir()
        mod = load(file, f"hw_{dest.name}")
        loaded.append(mod)
        return mod, file

    yield make
    sys.modules.pop("coursework", None)


# ── 範本與範例都過 --check（A13）──

@pytest.mark.parametrize("name", list(ALL))
def test_check_is_clean(cw, name, tmp_path):
    src = ALL[name]
    work = tmp_path / "w"
    work.mkdir()
    file = work / ("HK1.py" if src == TEMPLATE else src.name)
    shutil.copy(src, file)
    (work / f"{file.stem}Space").mkdir()
    assert cw.check(file) == []


def test_example_course_and_template_files_exist():
    assert TEMPLATE.is_file() and (COURSE / "課程.py").is_file()
    assert all(p.is_file() for p in EXAMPLES.values())
    assert not any((COURSE / n / "iplot.py").exists() for n in EXAMPLES)  # 範例沒有墊片，加入範例課程時才長出來


def test_example_course_reads_and_asks_only_for_numpy_and_matplotlib():
    course = load(FRAMEWORK, "course")
    info = course.read_course(COURSE)
    assert info.name == "科學計算"
    assert [set(batch[0]) for batch in info.packages] == [{"numpy", "matplotlib"}]
    kind = load(TYPE_DIR / "type.py", "cw_type")
    assert set().union(*(kind.requires(p) for p in EXAMPLES.values())) <= {"numpy", "matplotlib"}


def test_examples_are_classified_mine_and_have_cases():
    kind = load(TYPE_DIR / "type.py", "cw_type")
    for name, path in {**EXAMPLES, "範本": TEMPLATE}.items():
        assert kind.classify(path) == ("mine", None), name
        assert kind.cases(path), name
    assert [c for c, _ in kind.cases(TEMPLATE)] == ["case-1", "case-2"]
    assert [c for c, _ in kind.cases(EXAMPLES["HK2"])] == ["case-1", "case-2"]


def test_examples_do_not_import_the_v0_shell():
    for path in ALL.values():
        assert "hk_page" not in path.read_text(encoding="utf-8"), path


# ── compute／draw／stats 真的跑（A15）──

@pytest.mark.parametrize("name", list(ALL))
def test_every_case_computes_a_dict(name, homework, tmp_path):
    mod, _ = homework(ALL[name], tmp_path)
    hw = mod.HOMEWORK
    for case in hw["cases"]:
        run = hw["compute"](case)
        assert isinstance(run, dict) and run, case


def draw_all(mod):
    from matplotlib.figure import Figure

    out = {}
    for case in mod.HOMEWORK["cases"]:
        run = mod.HOMEWORK["compute"](case)
        fig = Figure()
        out[case] = mod.HOMEWORK["draw"](fig, run)
        stats = mod.HOMEWORK["stats"](run) if mod.HOMEWORK["stats"] else []
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in stats), case
    return out


def test_template_draws_an_animation_and_stats(homework, tmp_path):
    from matplotlib.animation import FuncAnimation

    mod, _ = homework(TEMPLATE, tmp_path)
    assert all(isinstance(a, FuncAnimation) for a in draw_all(mod).values())


def test_hk2_draws_static_figures(homework, tmp_path):
    mod, _ = homework(EXAMPLES["HK2"], tmp_path)
    assert list(draw_all(mod).values()) == [None, None]


def test_hk6_draws_an_animation(homework, tmp_path):
    from matplotlib.animation import FuncAnimation

    mod, _ = homework(EXAMPLES["HK6"], tmp_path)
    assert all(isinstance(a, FuncAnimation) for a in draw_all(mod).values())


def test_hk8_is_text_only(homework, tmp_path):
    mod, _ = homework(EXAMPLES["HK8"], tmp_path)
    hw = mod.HOMEWORK
    assert hw["draw"] is None
    for case in hw["cases"]:
        assert hw["compute"](case).get("text")


# ── 單獨 python3 HKn.py（Agg、CW_NO_INSTALL）：跑完、結束碼 0、先印 NAME ──

@pytest.mark.parametrize("name", list(ALL))
def test_runs_standalone(name, tmp_path):
    src = ALL[name]
    work = tmp_path / "w"
    work.mkdir()
    file = work / ("HK1.py" if src == TEMPLATE else src.name)
    shutil.copy(src, file)
    (work / f"{file.stem}Space").mkdir()
    env = {**os.environ, "PYTHONPATH": str(TYPE_DIR), "MPLBACKEND": "Agg", "CW_NO_INSTALL": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "MPLCONFIGDIR": str(tmp_path / "mpl")}
    env.pop("CW_FROM_IPLOT", None)
    done = subprocess.run([sys.executable, file.name, "--all"], cwd=work, env=env, capture_output=True, text=True,
                          encoding="utf-8", timeout=300)
    assert done.returncode == 0, done.stderr[-2000:]
    assert "Traceback" not in done.stdout + done.stderr
    assert done.stdout.splitlines()[0]  # NAME
