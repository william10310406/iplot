"""墊片與格子：新增一門課、加入範例課程、新增作業（A3–A6），以及 write_stub、type.new。
測試在 tmp 裡的模組複本上做（iplot.py 的格子、框架、作業類型、範例課程），不碰 repo 裡的東西。"""

import ast
import re
import shutil

import pytest
from cw_support import CW, FRAMEWORK, TYPE_DIR, CwApp, load, make_course, make_homework

from core.meta import read_meta
from core.runner import run_module
from core.scan import find_children, module_info


@pytest.fixture(autouse=True)
def _no_install(monkeypatch):
    monkeypatch.setenv("CW_NO_INSTALL", "1")


@pytest.fixture
def course_mod():
    return load(FRAMEWORK, "course")


@pytest.fixture
def kind():
    return load(TYPE_DIR / "type.py", "cw_type_算完畫圖")


@pytest.fixture
def mod(tmp_path):
    """tmp 裡的模組複本：跟 repo 裡追蹤進 git 的那些一樣（不連同使用的時候長出來的東西）。"""
    root = tmp_path / "modules" / "課程作業"
    root.mkdir(parents=True)
    for name in ("框架", "作業類型", "範例課程", "新增一門課", "加入範例課程"):
        shutil.copytree(CW / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(CW / "iplot.py", root / "iplot.py")
    return root


def ask(tmp_path, *answers):
    app = CwApp(tmp_path)
    app.answers_ask = list(answers)
    return app


def stub_of(folder):
    return read_meta(folder / "iplot.py")


def run_stub(folder, root, app):
    result = run_module(module_info(folder, root, "child"), app)
    assert result.error is None, result.error


# ── write_stub ──

def test_write_stub_writes_a_stub_that_core_can_read(course_mod, tmp_path):
    file = course_mod.write_stub(tmp_path / "HK01", "HK1", "homework_button(app, HERE)", doc="跑這份作業。")
    meta = read_meta(file)
    assert file == tmp_path / "HK01" / "iplot.py"
    assert (meta.title, meta.has_run, meta.error, meta.description) == ("HK1", True, None, "跑這份作業。")
    text = file.read_text(encoding="utf-8")
    assert course_mod.STUB_MARK in text and "course.homework_button(app, HERE)" in text
    ast.parse(text)


def test_write_stub_leaves_the_current_one_alone(course_mod, tmp_path):
    file = course_mod.write_stub(tmp_path, "HK1", "homework_button(app, HERE)")
    before = file.stat().st_mtime_ns
    course_mod.write_stub(tmp_path, "HK1", "homework_button(app, HERE)")
    assert file.stat().st_mtime_ns == before


def test_write_stub_replaces_a_framework_stub_of_another_version(course_mod, tmp_path):
    (tmp_path / "iplot.py").write_text(f'"""舊的"""\n# {course_mod.STUB_MARK}\nTITLE = "舊"\ndef run(app): pass\n',
                                       encoding="utf-8")
    course_mod.write_stub(tmp_path, "HK1", "homework_button(app, HERE)")
    assert stub_of(tmp_path).title == "HK1"


def test_write_stub_never_touches_a_file_that_is_not_a_stub(course_mod, tmp_path):
    mine = '"""老師自己寫的格子。"""\nTITLE = "我的"\n\ndef run(app):\n    app.log("我的")\n'
    (tmp_path / "iplot.py").write_text(mine, encoding="utf-8")
    course_mod.write_stub(tmp_path, "HK1", "homework_button(app, HERE)")
    assert (tmp_path / "iplot.py").read_text(encoding="utf-8") == mine


def test_write_stub_title_with_odd_characters_stays_a_string(course_mod, tmp_path):
    course_mod.write_stub(tmp_path, 'a"b\\c\'d', "course_button(app, HERE)")
    assert stub_of(tmp_path).title == 'a"b\\c\'d'


def test_tracked_top_level_buttons_are_the_stub(course_mod, tmp_path):
    for title, (call, doc) in course_mod.TOP_BUTTONS.items():
        made = course_mod.write_stub(tmp_path / title, title, call, doc=doc)
        assert made.read_text(encoding="utf-8") == (CW / title / "iplot.py").read_text(encoding="utf-8")
    assert set(course_mod.TOP_BUTTONS) == {"新增一門課", "加入範例課程"}


# ── 新增一門課（A3）──

def test_new_course_builds_the_course_and_its_buttons(course_mod, mod, tmp_path):
    app = ask(tmp_path, "測試課")
    course_mod.new_course(app, mod)
    course = mod / "測試課"
    assert app.asks == [("課的名字：", "")] and app.rescans == 1
    for rel in ("課程.py", "iplot.py", "新增作業/iplot.py", "檢查與打包/iplot.py"):
        assert (course / rel).is_file(), rel
    assert [stub_of(course).title, stub_of(course / "新增作業").title, stub_of(course / "檢查與打包").title] \
        == ["測試課", "新增作業", "檢查與打包"]
    assert course_mod.read_course(course).name == "測試課"
    assert not (course / ".venv").exists()


def test_new_course_file_has_only_name(course_mod, mod, tmp_path):
    course_mod.new_course(ask(tmp_path, "測試課"), mod)
    text = (mod / "測試課" / "課程.py").read_text(encoding="utf-8")
    body = ast.parse(text).body
    assert len(body) == 1 and body[0].targets[0].id == "NAME"
    assert text.count("#") >= 6  # 每個名字有一行註解說它是什麼
    for name in ("CODE", "FOLDER", "TYPES", "PACKAGES", "ONLY_ON"):
        assert name in text
    default = course_mod.read_course(mod / "測試課")
    assert (default.code, default.folder_format, default.types, default.packages) == ("HK{n}", "HK{n:02d}", ("算完畫圖",), ())


def test_new_course_template_is_in_the_framework(course_mod):
    template = CW / "框架" / "範本" / "課程.py"
    assert template.is_file() and ast.parse(template.read_text(encoding="utf-8"))


def test_new_course_stubs_run_the_framework(course_mod, mod, tmp_path):
    course_mod.new_course(ask(tmp_path, "測試課"), mod)
    app = CwApp(tmp_path)
    run_stub(mod / "測試課", mod, app)  # 課那一格：新課還沒有作業，課的 .venv 也要 matplotlib（D145）
    assert "CW_NO_INSTALL" in app.logs[-1] and "matplotlib" in app.logs[-1]
    app = ask(tmp_path)
    run_stub(mod / "測試課" / "新增作業", mod, app)  # 新增作業：問代號，預設 HK1
    assert app.asks == [("作業代號：", "HK1")]
    assert (mod / "測試課" / "HK01" / "HK1.py").is_file()


@pytest.mark.parametrize("answer", [None, "", "   "])
def test_new_course_cancel_or_empty_does_nothing(course_mod, mod, tmp_path, answer):
    before = sorted(p.name for p in mod.iterdir())
    app = ask(tmp_path, answer)
    course_mod.new_course(app, mod)
    assert sorted(p.name for p in mod.iterdir()) == before and app.rescans == 0
    assert app.logs and "沒新增" in app.logs[-1]


@pytest.mark.parametrize("name", [".隱藏", "a/b", "a\\b", "x.", "x ", "CON", "a:b", "a|b"])
def test_new_course_refuses_names_core_would_refuse(course_mod, mod, tmp_path, name):
    before = sorted(p.name for p in mod.iterdir())
    app = ask(tmp_path, name)
    course_mod.new_course(app, mod)
    assert sorted(p.name for p in mod.iterdir()) == before and app.rescans == 0
    assert len(app.logs) == 1 and "名" in app.logs[0]


@pytest.mark.parametrize("name", ["測試課", "框架", "新增一門課"])
def test_new_course_never_overwrites_an_existing_folder(course_mod, mod, tmp_path, name):
    existing = mod / name
    existing.mkdir(exist_ok=True)
    keep = existing / "我的.txt"
    keep.write_text("不要動", encoding="utf-8")
    app = ask(tmp_path, name)
    course_mod.new_course(app, mod)
    assert keep.read_text(encoding="utf-8") == "不要動" and not (existing / "課程.py").exists()
    assert app.rescans == 0 and "已經有" in app.logs[-1]


def test_new_course_name_with_quotes_in_it_still_reads_back(course_mod, mod, tmp_path):
    course_mod.new_course(ask(tmp_path, "測試 '課'"), mod)
    assert course_mod.read_course(mod / "測試 '課'").name == "測試 '課'"


def test_tracked_new_course_button_works_from_the_module(mod, tmp_path):
    app = ask(tmp_path, "測試課")
    run_stub(mod / "新增一門課", mod, app)
    assert (mod / "測試課" / "課程.py").is_file() and app.rescans == 1


# ── 加入範例課程（A4）──

def test_add_example_copies_the_course_with_stubs(course_mod, mod, tmp_path):
    app = CwApp(tmp_path)
    course_mod.add_example(app, mod)
    got, src = mod / "科學計算", mod / "範例課程" / "科學計算"
    assert app.rescans == 1
    assert (got / "課程.py").read_bytes() == (src / "課程.py").read_bytes()
    for code, folder in (("HK2", "HK02"), ("HK6", "HK06"), ("HK8", "HK08")):
        assert (got / folder / f"{code}.py").read_bytes() == (src / folder / f"{code}.py").read_bytes()
        assert stub_of(got / folder).title == code
    for rel, title in (("", "科學計算"), ("新增作業", "新增作業"), ("檢查與打包", "檢查與打包")):
        assert stub_of(got / rel).title == title
    assert sorted(c.title for c in find_children(got, mod)) == sorted(["HK2", "HK6", "HK8", "新增作業", "檢查與打包"])


def test_example_folders_follow_the_course_folder_format(course_mod):
    info = course_mod.read_course(CW / "範例課程" / "科學計算")
    found = course_mod.homeworks(info)
    assert [(code, file.parent.name) for code, file in found] \
        == [(code, course_mod.folder_of(info, course_mod.code_number(info, code))) for code, _ in found] \
        == [("HK2", "HK02"), ("HK6", "HK06"), ("HK8", "HK08")]


def test_add_example_then_new_homework_sorts_after_the_examples(course_mod, mod, tmp_path):
    course_mod.add_example(CwApp(tmp_path), mod)
    course = mod / "科學計算"
    app = new_hw(course_mod, tmp_path, course)  # 直接按確定：預設 HK9
    assert app.asks == [("作業代號：", "HK9")] and (course / "HK09" / "HK9.py").is_file()
    titles = [c.title for c in find_children(course, mod) if c.title.startswith("HK")]
    assert titles == ["HK2", "HK6", "HK8", "HK9"]


def test_add_example_leaves_the_example_alone(course_mod, mod, tmp_path):
    src = mod / "範例課程" / "科學計算"
    before = sorted(str(p.relative_to(src)) for p in src.rglob("*"))
    course_mod.add_example(CwApp(tmp_path), mod)
    assert sorted(str(p.relative_to(src)) for p in src.rglob("*")) == before
    assert not list(src.rglob("iplot.py"))


def test_add_example_does_not_copy_pycache(course_mod, mod, tmp_path):
    (mod / "範例課程" / "科學計算" / "HK02" / "__pycache__").mkdir()
    (mod / "範例課程" / "科學計算" / "HK02" / "__pycache__" / "x.pyc").write_bytes(b"x")
    course_mod.add_example(CwApp(tmp_path), mod)
    assert not list((mod / "科學計算").rglob("__pycache__"))


def test_add_example_copy_is_a_course_whose_homeworks_check_clean(course_mod, kind, mod, tmp_path):
    course_mod.add_example(CwApp(tmp_path), mod)
    found = course_mod.homeworks(course_mod.read_course(mod / "科學計算"))
    assert [code for code, _ in found] == ["HK2", "HK6", "HK8"]
    assert all(kind.check(file) == [] for _, file in found)


def test_add_example_second_time_says_so_and_changes_nothing(course_mod, mod, tmp_path):
    course_mod.add_example(CwApp(tmp_path), mod)
    mine = mod / "科學計算" / "HK02" / "HK2.py"
    mine.write_text("# 學生改過的\n", encoding="utf-8")
    app = CwApp(tmp_path)
    course_mod.add_example(app, mod)
    assert mine.read_text(encoding="utf-8") == "# 學生改過的\n"
    assert app.rescans == 0 and "已經有" in app.logs[-1]


def test_add_example_without_the_example_folder(course_mod, mod, tmp_path):
    shutil.rmtree(mod / "範例課程")
    app = CwApp(tmp_path)
    course_mod.add_example(app, mod)
    assert not (mod / "科學計算").exists() and app.rescans == 0 and "範例課程" in app.logs[-1]


def test_tracked_add_example_button_works_from_the_module(mod, tmp_path):
    app = CwApp(tmp_path)
    run_stub(mod / "加入範例課程", mod, app)
    assert (mod / "科學計算" / "HK06" / "iplot.py").is_file() and app.rescans == 1


def test_example_homework_stub_points_at_the_homework_button(course_mod, mod, tmp_path):
    course_mod.add_example(CwApp(tmp_path), mod)
    assert "course.homework_button(app, HERE)" in (mod / "科學計算" / "HK06" / "iplot.py").read_text(encoding="utf-8")


# ── 新增作業（A5、A6）──

def new_hw(course_mod, tmp_path, course, *answers):
    app = ask(tmp_path, *answers)
    course_mod.new_homework(app, course)
    return app


def test_new_homework_default_is_the_next_unused_number(course_mod, tmp_path):
    course = make_course(tmp_path)
    assert new_hw(course_mod, tmp_path, course, None).asks == [("作業代號：", "HK1")]
    for n in (1, 5):
        make_homework(course, n)
    assert new_hw(course_mod, tmp_path, course, None).asks == [("作業代號：", "HK6")]


def test_new_homework_builds_folder_file_space_and_stub(course_mod, tmp_path):
    course = make_course(tmp_path)
    app = new_hw(course_mod, tmp_path, course, "HK1")
    folder = course / "HK01"
    assert sorted(p.name for p in folder.iterdir()) == ["HK1.py", "HK1Space", "iplot.py"]
    assert (folder / "HK1Space").is_dir() and not list((folder / "HK1Space").iterdir())
    assert (folder / "HK1.py").read_bytes() == (TYPE_DIR / "範本.py").read_bytes()
    meta = stub_of(folder)
    assert (meta.title, meta.has_run, meta.error) == ("HK1", True, None)
    assert "course.homework_button(app, HERE)" in (folder / "iplot.py").read_text(encoding="utf-8")
    assert app.edits == [(folder / "HK1.py", None)] and app.rescans == 1


def test_new_homework_default_answer_is_taken_when_the_user_just_confirms(course_mod, tmp_path):
    course = make_course(tmp_path)
    make_homework(course, 1)
    new_hw(course_mod, tmp_path, course)  # 沒有 answers：CwApp.ask 回預設
    assert (course / "HK02" / "HK2.py").is_file()


@pytest.mark.parametrize("code", ["HK1", "HK12", "HK123"])
def test_new_homework_passes_check_and_has_no_other_codes_left(course_mod, kind, tmp_path, code):
    course = make_course(tmp_path)
    new_hw(course_mod, tmp_path, course, code)
    file = course / f"HK{int(code[2:]):02d}" / f"{code}.py"
    text = file.read_text(encoding="utf-8")
    assert kind.check(file) == [] and (file.parent / f"{code}Space").is_dir()
    assert f'NAME = "{code} 範例' in text and f'/ "{code}Space"' in text
    if code == "HK1":
        assert text == (TYPE_DIR / "範本.py").read_text(encoding="utf-8")
    else:  # 換的是整個字：HK12 裡的 HK1 不是 HK1，但原本的 HK1 一個都不剩
        assert re.search(r"HK1(?!\d)", text) is None


def test_new_homework_with_a_code_that_does_not_start_with_hk(course_mod, kind, tmp_path):
    course = make_course(tmp_path, CODE="Lab{n}", FOLDER="Lab{n:02d}")
    app = new_hw(course_mod, tmp_path, course, "Lab3")
    file = course / "Lab03" / "Lab3.py"
    space = course / "Lab03" / "Lab3Space"
    assert kind.check(file) == [] and space.is_dir() and not list(space.iterdir())
    text, template = file.read_text(encoding="utf-8"), (TYPE_DIR / "範本.py").read_text(encoding="utf-8")
    assert "HK1" not in text and text == template.replace("HK1", "Lab3")  # 每個 HK1、HK1Space 都換成了 Lab3
    assert 'NAME = "Lab3 範例' in text and '/ "Lab3Space"' in text and template.count("HK1") >= 2
    assert stub_of(course / "Lab03").title == "Lab3"
    assert app.edits == [(file, None)]


def test_new_homework_default_for_a_lab_course(course_mod, tmp_path):
    course = make_course(tmp_path, CODE="Lab{n}", FOLDER="Lab{n:02d}")
    assert new_hw(course_mod, tmp_path, course, None).asks == [("作業代號：", "Lab1")]


@pytest.mark.parametrize(("typed", "code", "folder"), [("hk07", "HK7", "HK07"), ("  HK3  ", "HK3", "HK03"), ("HK0004", "HK4", "HK04")])
def test_new_homework_writes_the_canonical_code(course_mod, tmp_path, typed, code, folder):
    course = make_course(tmp_path)
    new_hw(course_mod, tmp_path, course, typed)
    assert (course / folder / f"{code}.py").is_file() and stub_of(course / folder).title == code


def test_new_homework_cancel_does_nothing(course_mod, tmp_path):
    course = make_course(tmp_path)
    app = new_hw(course_mod, tmp_path, course, None)
    assert sorted(p.name for p in course.iterdir()) == ["課程.py"]
    assert app.rescans == 0 and app.edits == [] and "沒新增" in app.logs[-1]


@pytest.mark.parametrize("typed", ["abc", "", "H5K", "CHK1", "HK"])
def test_new_homework_says_when_it_cannot_read_the_code(course_mod, tmp_path, typed):
    course = make_course(tmp_path)
    app = new_hw(course_mod, tmp_path, course, typed)
    assert sorted(p.name for p in course.iterdir()) == ["課程.py"]
    assert app.rescans == 0 and "HK" in app.logs[-1] and "代號" in app.logs[-1]


def test_new_homework_never_overwrites(course_mod, tmp_path):
    course = make_course(tmp_path)
    file = make_homework(course, 1, "# 學生寫的\n")
    app = new_hw(course_mod, tmp_path, course, "HK1")
    assert file.read_text(encoding="utf-8") == "# 學生寫的\n" and not (file.parent / "iplot.py").exists()
    assert app.rescans == 0 and "已經有" in app.logs[-1]


def test_new_homework_refuses_a_number_that_exists_under_another_folder_name(course_mod, tmp_path):
    course = make_course(tmp_path)  # FOLDER 預設補零，老師自己建的資料夾卻是 HK2（沒補零）
    (course / "HK2").mkdir()
    (course / "HK2" / "HK2.py").write_text("# 範例\n", encoding="utf-8")
    app = new_hw(course_mod, tmp_path, course, "HK2")
    assert not (course / "HK02").exists() and app.rescans == 0 and "已經有" in app.logs[-1]


def test_new_homework_default_counts_the_example_folders_too(course_mod, tmp_path):
    course = make_course(tmp_path)
    for n in (2, 6, 8):
        (course / f"HK{n}").mkdir()
        (course / f"HK{n}" / f"HK{n}.py").write_text("# 範例\n", encoding="utf-8")
    assert new_hw(course_mod, tmp_path, course, None).asks == [("作業代號：", "HK9")]


def test_new_homework_reports_a_broken_course_file(course_mod, tmp_path):
    course = make_course(tmp_path)
    (course / "課程.py").write_text("NAME = 'x'\nimport os\n", encoding="utf-8")
    app = new_hw(course_mod, tmp_path, course, "HK1")
    assert "第 2 行" in app.logs[-1] and app.asks == [] and app.rescans == 0


def test_twelve_homeworks_sort_by_number_in_the_panel(course_mod, mod, tmp_path):
    course_mod.new_course(ask(tmp_path, "測試課"), mod)
    course = mod / "測試課"
    for _ in range(12):
        course_mod.new_homework(ask(tmp_path), course)
    titles = [c.title for c in find_children(course, mod)]
    homework = [t for t in titles if t.startswith("HK")]
    assert homework == [f"HK{n}" for n in range(1, 13)]
    assert sorted(p.name for p in course.iterdir() if p.name.startswith("HK")) == [f"HK{n:02d}" for n in range(1, 13)]
    assert set(titles) - set(homework) == {"新增作業", "檢查與打包"}


def test_new_homework_uses_the_first_type_of_the_course(course_mod, tmp_path):
    course = make_course(tmp_path, TYPES=["不存在的類型"])
    app = new_hw(course_mod, tmp_path, course, "HK1")
    assert "不存在的類型" in app.logs[-1] and not (course / "HK01").exists()


# ── type.new ──

def test_type_new_copies_the_template_with_the_code_swapped(kind, tmp_path):
    file = kind.new(tmp_path / "HK09", "HK9")
    assert file == tmp_path / "HK09" / "HK9.py" and (tmp_path / "HK09" / "HK9Space").is_dir()
    assert file.read_text(encoding="utf-8") == (TYPE_DIR / "範本.py").read_text(encoding="utf-8").replace("HK1", "HK9")
    assert b"\r" not in file.read_bytes()


def test_type_new_refuses_to_overwrite(kind, tmp_path):
    (tmp_path / "HK1.py").write_text("# 已經有\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        kind.new(tmp_path, "HK1")
    assert (tmp_path / "HK1.py").read_text(encoding="utf-8") == "# 已經有\n"


# ── D148：文件照程式說——NAME 只在建課時用（課那一格的字是墊片裡寫死的 TITLE）──

def test_template_says_name_is_used_only_when_the_course_is_made(course_mod, mod, tmp_path):
    template = (CW / "框架" / "範本" / "課程.py").read_text(encoding="utf-8")
    assert "NAME 只在建課時用" in template.splitlines()[0] and "其他設定改完存檔，面板重掃就生效" in template.splitlines()[0]
    course_mod.new_course(ask(tmp_path, "測試課"), mod)
    settings = mod / "測試課" / "課程.py"
    settings.write_text(settings.read_text(encoding="utf-8").replace('NAME = "測試課"', 'NAME = "改過的名字"', 1),
                        encoding="utf-8")
    run_stub(mod / "測試課", mod, CwApp(tmp_path))
    assert stub_of(mod / "測試課").title == "測試課"  # 範本說的：改 NAME 不會改課那一格的字
