"""框架 course.py：讀 課程.py（ast，不執行）、作業代號與資料夾名、找課與找框架。"""

import dataclasses

import cw_support
import pytest
from cw_support import CW, FRAMEWORK, TYPE_DIR, load, make_course


@pytest.fixture(autouse=True)
def _no_install(monkeypatch):
    monkeypatch.setenv("CW_NO_INSTALL", "1")


@pytest.fixture
def course_mod():
    return load(FRAMEWORK, "course")


def write(folder, text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "課程.py").write_text(text, encoding="utf-8", newline="\n")
    return folder


def read(course_mod, tmp_path, text):
    return course_mod.read_course(write(tmp_path / "課", text))


# ── A1：讀 課程.py ──

def test_defaults_when_file_has_only_a_comment(course_mod, tmp_path):
    course = read(course_mod, tmp_path, "# 什麼都沒設定\n")
    assert course.folder == tmp_path / "課"
    assert course.name == "課"  # 沒寫 NAME 就是資料夾名
    assert (course.code, course.folder_format) == ("HK{n}", "HK{n:02d}")
    assert course.types == ("算完畫圖",)
    assert course.packages == ()
    assert course.only_on == {}


def test_all_names_are_read(course_mod, tmp_path):
    folder = make_course(
        tmp_path, "科學計算", CODE="Lab{n}", FOLDER="Lab{n:03d}", TYPES=["算完畫圖"],
        PACKAGES=[(["numpy", "matplotlib"], "基本那批", "約 480 MB"), (["torch"], "第二批", "約 1.1 GB")],
        ONLY_ON={"mlx-lm": "apple-silicon"})
    course = course_mod.read_course(folder)
    assert (course.name, course.code, course.folder_format) == ("科學計算", "Lab{n}", "Lab{n:03d}")
    assert course.types == ("算完畫圖",)
    assert course.packages == ((("numpy", "matplotlib"), "基本那批", "約 480 MB"),
                               (("torch",), "第二批", "約 1.1 GB"))
    assert course.only_on == {"mlx-lm": "apple-silicon"}


def test_docstring_is_allowed_and_course_is_frozen(course_mod, tmp_path):
    course = read(course_mod, tmp_path, '"""這門課的說明。"""\nNAME = "有說明的課"\n')
    assert course.name == "有說明的課"
    with pytest.raises(dataclasses.FrozenInstanceError):
        course.name = "別的"


@pytest.mark.parametrize("name, literal", [
    ("NAME", "1"), ("NAME", "''"), ("NAME", "'   '"),
    ("CODE", "5"), ("FOLDER", "5"),
    ("TYPES", "'算完畫圖'"), ("TYPES", "[1]"),
    ("PACKAGES", "'numpy'"), ("PACKAGES", "[(['numpy'], '說明')]"),
    ("PACKAGES", "[(['bad name'], '說明', '大小')]"), ("PACKAGES", "[([1], '說明', '大小')]"),
    ("PACKAGES", "[(['numpy'], 1, '大小')]"),
    ("ONLY_ON", "[]"), ("ONLY_ON", "{'mlx-lm': 'linux'}"), ("ONLY_ON", "{1: 'apple-silicon'}"),
])
def test_wrong_type_or_value_names_the_name_and_line(course_mod, tmp_path, name, literal):
    with pytest.raises(course_mod.CourseError) as err:
        read(course_mod, tmp_path, f"{name} = {literal}\n")
    assert name in str(err.value) and "第 1 行" in str(err.value)


def test_value_that_is_not_a_literal(course_mod, tmp_path):
    with pytest.raises(course_mod.CourseError) as err:
        read(course_mod, tmp_path, "# 註解\nNAME = 'a' + 'b'\n")
    assert "NAME" in str(err.value) and "第 2 行" in str(err.value)


@pytest.mark.parametrize("code", [
    "HK{n}{n}", "HK{n.real}", "HK{n!r}", "HK", "HK{n}/x", "H K{n}", "HK{n}{", "../{n}", "{n:02d}",
])
def test_bad_code_is_refused(course_mod, tmp_path, code):
    with pytest.raises(course_mod.CourseError) as err:
        read(course_mod, tmp_path, f"CODE = {code!r}\n")
    assert "CODE" in str(err.value)


@pytest.mark.parametrize("code", ["HK{n}", "Lab-{n}_x", "作業{n}", "{n}", "t2026fsc{n}"])
def test_good_code_is_accepted(course_mod, tmp_path, code):
    assert read(course_mod, tmp_path, f"CODE = {code!r}\n").code == code


@pytest.mark.parametrize("folder", [
    "HK{n:05d}", "HK{n:00d}", "HK{n:d}", "HK{n:2d}", "HK{n}{n}", "HK{n}{n:02d}", "HK{n.real}", "HK{n!r}",
    "HK", "HK{n:02d", "HK{x}{n}",
])
def test_bad_folder_format_is_refused(course_mod, tmp_path, folder):
    with pytest.raises(course_mod.CourseError) as err:
        read(course_mod, tmp_path, f"FOLDER = {folder!r}\n")
    assert "FOLDER" in str(err.value)


@pytest.mark.parametrize("folder", ["HK{n}", "HK{n:01d}", "HK{n:02d}", "Lab{n:03d}", "作業{n:04d}"])
def test_good_folder_format_is_accepted(course_mod, tmp_path, folder):
    assert read(course_mod, tmp_path, f"FOLDER = {folder!r}\n").folder_format == folder


@pytest.mark.parametrize("line", [
    "import os", "FOO = 1", "NAME, CODE = 'a', 'b'", "NAME = CODE = 'a'", "NAME: str = 'a'",
    "print('hi')", "1", "if True:\n    NAME = 'a'",
])
def test_other_top_level_statements_are_refused_with_line(course_mod, tmp_path, line):
    with pytest.raises(course_mod.CourseError) as err:
        read(course_mod, tmp_path, f"# 第一行是註解\n{line}\n")
    assert "第 2 行" in str(err.value)


def test_file_is_never_executed(course_mod, tmp_path, monkeypatch):
    work = tmp_path / "工作目錄"
    work.mkdir()
    monkeypatch.chdir(work)
    folder = tmp_path / "課"
    with pytest.raises(course_mod.CourseError) as err:
        read(course_mod, tmp_path, 'open("寫了.txt", "w")\n')
    assert "第 1 行" in str(err.value)
    assert not (work / "寫了.txt").exists() and not (folder / "寫了.txt").exists()


def test_syntax_error_not_utf8_and_missing_file(course_mod, tmp_path):
    with pytest.raises(course_mod.CourseError) as err:
        read(course_mod, tmp_path, "NAME = \n")
    assert "第 1 行" in str(err.value)
    bad = tmp_path / "亂碼"
    bad.mkdir()
    (bad / "課程.py").write_bytes("NAME = '甲'\n".encode("big5"))
    with pytest.raises(course_mod.CourseError):
        course_mod.read_course(bad)
    with pytest.raises(course_mod.CourseError):
        course_mod.read_course(tmp_path / "沒有這個資料夾")


def test_utf8_bom_is_fine(course_mod, tmp_path):
    folder = tmp_path / "課"
    folder.mkdir()
    (folder / "課程.py").write_bytes(b"\xef\xbb\xbf" + 'NAME = "有 BOM"\n'.encode())
    assert course_mod.read_course(folder).name == "有 BOM"


# ── A2：代號與資料夾名 ──

def test_code_number_recognises_the_code(course_mod, tmp_path):
    course = read(course_mod, tmp_path, "")
    for name, expected in [("HK1", 1), ("hk01", 1), ("HK1_學生A.zip", 1), ("HK12", 12), ("HK05.py", 5),
                           ("交 HK3 作業", 3), ("HK5王小明.zip", 5), ("HK1_HK2", 1)]:
        assert course_mod.code_number(course, name) == expected, name
    for name in ["CHK1", "HK", "HK1A", "作業1", "", "xhk2"]:
        assert course_mod.code_number(course, name) is None, name


def test_code_number_uses_the_courses_own_format(course_mod, tmp_path):
    course = read(course_mod, tmp_path, "CODE = 'Lab-{n}_v'\n")
    assert course_mod.code_number(course, "lab-007_v.zip") == 7
    assert course_mod.code_number(course, "HK1") is None
    suffix_less = read(course_mod, tmp_path / "二", "CODE = 'W{n}x'\n")
    assert course_mod.code_number(suffix_less, "W3x") == 3
    assert course_mod.code_number(suffix_less, "W3") is None


def test_code_of_and_folder_of(course_mod, tmp_path):
    default = read(course_mod, tmp_path, "")
    assert (course_mod.code_of(default, 1), course_mod.folder_of(default, 1)) == ("HK1", "HK01")
    assert (course_mod.code_of(default, 12), course_mod.folder_of(default, 12)) == ("HK12", "HK12")
    assert course_mod.folder_of(default, 123) == "HK123"
    lab = read(course_mod, tmp_path / "二", "CODE = 'Lab{n}'\nFOLDER = 'Lab{n:03d}'\n")
    assert (course_mod.code_of(lab, 1), course_mod.folder_of(lab, 1)) == ("Lab1", "Lab001")
    plain = read(course_mod, tmp_path / "三", "FOLDER = '作業{n}'\n")
    assert course_mod.folder_of(plain, 4) == "作業4"
    assert course_mod.code_number(default, course_mod.code_of(default, 7)) == 7


# ── 找課與找框架 ──

def test_course_root_walks_up_from_a_homework_folder(course_mod, tmp_path):
    course = make_course(tmp_path, "課")
    (course / "HK01").mkdir()
    assert course_mod.course_root(course / "HK01") == course
    assert course_mod.course_root(course / "HK01" / "HK1Space") == course
    assert course_mod.course_root(course) == course
    assert course_mod.course_root(tmp_path / "別處") is None


def test_framework_root_walks_up_to_the_folder_holding_framework(course_mod, tmp_path):
    mods = tmp_path / "modules" / "課程作業"
    (mods / "框架").mkdir(parents=True)
    (mods / "框架" / "course.py").write_text("", encoding="utf-8")
    deep = mods / "測試課" / "HK01"
    deep.mkdir(parents=True)
    assert course_mod.framework_root(deep) == mods
    assert course_mod.framework_root(tmp_path / "別處") is None
    assert course_mod.framework_root(TYPE_DIR) == CW  # 真的模組：作業類型資料夾往上就是框架所在


# ── cw_support.make_homework（Task 1 留到這裡：它要用 read_course、code_of、folder_of）──

def test_support_make_homework_follows_the_courses_format(tmp_path):
    course = make_course(tmp_path, "課")
    file = cw_support.make_homework(course, 3)
    assert file == course / "HK03" / "HK3.py"
    assert "HK3" in file.read_text(encoding="utf-8") and "{code}" not in file.read_text(encoding="utf-8")
    lab = make_course(tmp_path, "實驗課", CODE="Lab{n}", FOLDER="Lab{n:03d}")
    assert cw_support.make_homework(lab, 12, src="x = 1\n") == lab / "Lab012" / "Lab12.py"
    assert (lab / "Lab012" / "Lab12.py").read_text(encoding="utf-8") == "x = 1\n"
