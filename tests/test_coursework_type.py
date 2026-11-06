"""作業類型：框架的 load_type，與「算完畫圖」的靜態部分（classify、cases、requires；只用 ast，不執行）。"""

import pytest
from cw_support import CW, FRAMEWORK, TYPE_DIR, load


@pytest.fixture(autouse=True)
def _no_install(monkeypatch):
    monkeypatch.setenv("CW_NO_INSTALL", "1")


@pytest.fixture
def course_mod():
    return load(FRAMEWORK, "course")


@pytest.fixture
def kind():
    return load(TYPE_DIR / "type.py", "cw_type_算完畫圖")


def hw(tmp_path, text, name="HK1.py"):
    file = tmp_path / name
    file.write_text(text, encoding="utf-8", newline="\n")
    return file


V2 = """REQUIRES = ["numpy"]
import coursework; coursework.ensure(REQUIRES, __file__)
import numpy as np
NAME = "x"
CASES = {"case-1": dict(r=1, label="半徑 1"), "case-2": {"r": 2, "label": "半徑 2"}}
def compute(case): return {}
HOMEWORK = dict(name=NAME, cases=CASES, compute=compute, file=__file__)
if __name__ == "__main__":
    raise SystemExit(coursework.main(HOMEWORK))
"""


# ── load_type ──

def test_load_type_loads_the_real_type(course_mod, kind):
    loaded = course_mod.load_type("算完畫圖", CW)
    assert loaded.NAME == "算完畫圖" == kind.NAME
    assert loaded.ACCEPTS == (".py",)


@pytest.mark.parametrize("name", ["不存在", "../框架", "算完畫圖/..", ".隱藏", "", "/算完畫圖"])
def test_load_type_refuses_names_not_under_types(course_mod, name):
    with pytest.raises(course_mod.CourseError) as err:
        course_mod.load_type(name, CW)
    assert "作業類型" in str(err.value)


def test_load_type_refuses_a_folder_without_type_py(course_mod, tmp_path):
    (tmp_path / "作業類型" / "空的").mkdir(parents=True)
    with pytest.raises(course_mod.CourseError):
        course_mod.load_type("空的", tmp_path)


# ── classify ──

def test_classify_mine(kind, tmp_path):
    assert kind.classify(hw(tmp_path, V2)) == ("mine", None)


def test_classify_broken(kind, tmp_path):
    assert kind.classify(hw(tmp_path, "def f(:\n")) == ("broken", None)
    nul = tmp_path / "nul.py"
    nul.write_bytes(b"x = 1\x00\n")
    assert kind.classify(nul) == ("broken", None)


def test_classify_not_utf8(kind, tmp_path):
    file = tmp_path / "big5.py"
    file.write_bytes('NAME = "作業"\n'.encode("big5"))
    assert kind.classify(file) == ("not-utf8", None)


def test_classify_v0_is_none(kind, tmp_path):
    v0 = V2.replace("import coursework; coursework.ensure", "import hk_page; hk_page.ensure")
    assert kind.classify(hw(tmp_path, v0)) == ("none", None)
    both = "import hk_page\n" + V2  # 兩個都 import：還是 v0 的檔，不收
    assert kind.classify(hw(tmp_path, both, "HK2.py")) == ("none", None)


@pytest.mark.parametrize("text", [
    "print('hi')\n",
    V2.replace("HOMEWORK = dict(", "HOMEWORK = make("),  # 不是 dict(…)
    V2.replace("import coursework; coursework.ensure(REQUIRES, __file__)", ""),  # 沒有 import coursework
    "import coursework\ndef f():\n    HOMEWORK = dict()\n",  # HOMEWORK 不在頂層
])
def test_classify_other_files_are_none(kind, tmp_path, text):
    assert kind.classify(hw(tmp_path, text)) == ("none", None)


def test_classify_does_not_execute(kind, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    file = hw(tmp_path, 'open("寫了.txt", "w")\nimport zz_不存在\n' + V2)
    assert kind.classify(file) == ("mine", None)
    assert kind.cases(file) == [("case-1", "半徑 1"), ("case-2", "半徑 2")]
    kind.requires(file)
    assert not (tmp_path / "寫了.txt").exists()


# ── cases ──

def test_cases_reads_names_and_labels_in_order(kind, tmp_path):
    assert kind.cases(hw(tmp_path, V2)) == [("case-1", "半徑 1"), ("case-2", "半徑 2")]


def test_cases_label_missing_or_not_a_constant_is_empty(kind, tmp_path):
    text = 'L = "x"\nCASES = {"a": dict(r=1), "b": {"r": 2}, "c": dict(label=L), "d": {"label": f"{L}"}}\n'
    assert kind.cases(hw(tmp_path, text)) == [("a", ""), ("b", ""), ("c", ""), ("d", "")]


@pytest.mark.parametrize("text", [
    'K = "case-1"\nCASES = {K: dict(label="a")}\n',  # 鍵是變數
    'CASES = {1: dict(label="a")}\n',  # 鍵不是字串
    'BASE = {}\nCASES = {**BASE, "case-1": dict()}\n',  # 展開
    'CASES = dict(a=dict())\n',  # 不是 dict 字面值
    'CASES = [("a", {})]\n',
    'NAME = "沒有 CASES"\n',
    "def f(:\n",
])
def test_cases_unreadable_is_none(kind, tmp_path, text):
    assert kind.cases(hw(tmp_path, text)) is None


def test_cases_not_utf8_is_none(kind, tmp_path):
    file = tmp_path / "big5.py"
    file.write_bytes('CASES = {"甲": dict()}\n'.encode("big5"))
    assert kind.cases(file) is None


# ── requires ──

def test_requires_is_exactly_the_requires_line(kind, tmp_path):
    """D137：以 ast 讀到的 REQUIRES 字面值為準；import 了沒寫的不算（那是 --check 的事，Task 7）。"""
    text = V2.replace("def compute(case): return {}",
                      "def compute(case):\n    from sklearn.cluster import KMeans\n    import cv2\n    return {}")
    assert kind.requires(hw(tmp_path, text)) == {"numpy"}
    text = 'REQUIRES = ["Pillow", "scikit-learn"]\nimport coursework\nimport PIL\nimport scipy\n'
    assert kind.requires(hw(tmp_path, text, "HK2.py")) == {"Pillow", "scikit-learn"}


@pytest.mark.parametrize("text", [
    "import scipy\n",  # 沒有 REQUIRES
    'REQUIRES = "numpy"\nimport yaml\n',  # 不是 list
    'X = "numpy"\nREQUIRES = [X]\n',  # 不是字面值
    "def f(:\n",  # 讀不懂
])
def test_requires_without_a_usable_line_is_empty(kind, tmp_path, text):
    assert kind.requires(hw(tmp_path, text)) == set()


def test_requires_keeps_only_the_strings(kind, tmp_path):
    assert kind.requires(hw(tmp_path, 'REQUIRES = ["numpy", 1, "", "matplotlib"]\n')) == {"numpy", "matplotlib"}
