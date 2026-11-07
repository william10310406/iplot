"""檢查與打包（A14、A18 的 zip 那一半、N3 的程式那一半）：check 擋 ✗、⚠ 照打包（D141）；學生包 zip 的內容與
README；.版本/ 留一份同樣 bytes 的 zip、不自動刪（D135）。只在 tmp 裡做，不開 Finder（app.reveal 是假的）。"""

import getpass
import re
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cw_support import CW, FRAMEWORK, TYPE_DIR, CwApp, load, make_course

README = CW / "框架" / "學生README.txt"


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
def cw():
    return load(TYPE_DIR / "coursework.py", "coursework")


def homework(course, n=1):
    return load(TYPE_DIR / "type.py", "cw_type_算完畫圖").new(course / f"HK{n:02d}", f"HK{n}")


@pytest.fixture
def course(tmp_path):
    folder = make_course(tmp_path)
    homework(folder, 1)
    return folder


AT = datetime(2026, 11, 6, 14, 30, 8)


def pack(course_mod, course, *answers, now=lambda: AT):
    app = CwApp(course)
    app.answers_ask = list(answers)
    course_mod.check_and_pack(app, course, now=now)
    return app


def sent(course, code="HK1"):
    return course / "發出去的" / f"{code}_學生包.zip"


def versions(course, folder="HK01"):
    return sorted((course / folder / ".版本").glob("*.zip")) if (course / folder / ".版本").is_dir() else []


def readme_of(zip_path, code="HK1"):
    with zipfile.ZipFile(zip_path) as z:
        return z.read(f"{code}/README.txt").decode("utf-8")


# ── 問哪一份 ──

def test_default_is_the_highest_number(course_mod, course):
    homework(course, 3)
    homework(course, 2)
    app = pack(course_mod, course, None)
    assert app.asks == [("要打包哪一份？", "HK3")]
    assert app.logs[-1] == "沒打包" and not (course / "發出去的").exists()


@pytest.mark.parametrize("typed", ["abc", "", "HK7"])
def test_a_code_that_is_not_a_homework_here_says_so(course_mod, course, typed):
    app = pack(course_mod, course, typed)
    assert not (course / "發出去的").exists() and versions(course) == []
    assert "HK1" in app.logs[-1] and "沒打包" in app.logs[-1]


def test_typed_code_is_read_like_everywhere_else(course_mod, course):
    pack(course_mod, course, " hk01 ")
    assert sent(course).is_file()


def test_course_without_homework(course_mod, tmp_path):
    folder = make_course(tmp_path)
    app = pack(course_mod, folder)
    assert app.asks == [] and "新增作業" in app.logs[-1]


# ── check：✗ 擋，⚠ 照打包（D131、D141）──

def test_a_blocking_problem_stops_the_pack(course_mod, course):
    file = course / "HK01" / "HK1.py"
    text = file.read_text(encoding="utf-8")
    text = text.replace("import numpy as np\n", "import numpy as np\nimport matplotlib.pyplot as plt\n", 1)
    file.write_text(text.replace("def compute(case):", "def compute(case):\n    plt.show()", 1), encoding="utf-8")  # R16
    app = pack(course_mod, course, "HK1")
    assert not (course / "發出去的").exists() and versions(course) == [] and app.revealed == []
    assert any(line.startswith("✗ R16 第 ") for line in app.logs)
    assert app.logs[-1] == "沒有打包：先改好上面 ✗ 的這幾條"


def test_warnings_alone_still_pack(course_mod, course):
    file = course / "HK01" / "HK1.py"
    file.write_text(file.read_text(encoding="utf-8").replace("def stats(run):", "import scipy\n\n\ndef stats(run):", 1),
                    encoding="utf-8")
    app = pack(course_mod, course, "HK1")
    assert sent(course).is_file() and len(versions(course)) == 1
    assert any(line.startswith("⚠ R12") for line in app.logs)


def test_not_a_v2_file_is_not_packed(course_mod, course):
    (course / "HK01" / "HK1.py").write_text("def compute(case:\n", encoding="utf-8")
    app = pack(course_mod, course, "HK1")
    assert not (course / "發出去的").exists() and any(line.startswith("✗ R27") for line in app.logs)
    assert "沒有打包" in app.logs[-1]


def test_unreadable_file_is_one_sentence(course_mod, course, monkeypatch):
    real = course_mod.load_type

    def broken(name, fw):
        module = real(name, fw)

        def boom(path):
            raise PermissionError(13, "Permission denied")

        module.classify = boom
        return module

    monkeypatch.setattr(course_mod, "load_type", broken)
    app = pack(course_mod, course, "HK1")
    assert "讀不了 HK1.py" in app.logs[-1] and "沒有打包" in app.logs[-1] and not (course / "發出去的").exists()


# ── zip 的內容（A14）──

def test_zip_has_exactly_the_homework_shell_space_and_readme(course_mod, course):
    space = course / "HK01" / "HK1Space"
    (space / "data.csv").write_text("x\n1\n", encoding="utf-8")
    (space / "子資料夾").mkdir()
    (space / "子資料夾" / "圖.png").write_bytes(b"\x89PNG")
    app = pack(course_mod, course, "HK1")
    with zipfile.ZipFile(sent(course)) as z:
        names = z.namelist()
        assert names == sorted(names)
        assert names == ["HK1/HK1.py", "HK1/HK1Space/", "HK1/HK1Space/data.csv", "HK1/HK1Space/子資料夾/",
                         "HK1/HK1Space/子資料夾/圖.png", "HK1/README.txt", "HK1/coursework.py"]
        assert z.read("HK1/HK1.py") == (course / "HK01" / "HK1.py").read_bytes()
        assert z.read("HK1/coursework.py") == (TYPE_DIR / "coursework.py").read_bytes()
        assert z.read("HK1/HK1Space/子資料夾/圖.png") == b"\x89PNG"
        infos = z.infolist()
    assert all(i.date_time == (2026, 11, 6, 14, 30, 8) for i in infos)
    # UTF-8 檔名旗標：中文名字都有；純 ASCII 的名字 zipfile 自己會拿掉旗標（ASCII 在哪種編碼都一樣）
    assert all(i.flag_bits & 0x800 for i in infos if not i.filename.isascii())
    assert any(not i.filename.isascii() for i in infos)
    assert app.revealed == [sent(course)]


def test_an_empty_space_is_still_a_folder_in_the_zip(course_mod, course):
    pack(course_mod, course, "HK1")
    with zipfile.ZipFile(sent(course)) as z:
        assert "HK1/HK1Space/" in z.namelist()


def test_without_a_space_folder_the_zip_still_has_an_empty_one(course_mod, course):
    space = course / "HK01" / "HK1Space"
    space.rmdir()
    file = course / "HK01" / "HK1.py"  # 沒有 DATA 的作業（範例課程那三份就是）：R6 不要求 Space
    file.write_text("".join(line for line in file.read_text(encoding="utf-8").splitlines(True)
                            if not line.startswith("DATA =")), encoding="utf-8")
    pack(course_mod, course, "HK1")
    with zipfile.ZipFile(sent(course)) as z:
        assert z.namelist() == ["HK1/HK1.py", "HK1/HK1Space/", "HK1/README.txt", "HK1/coursework.py"]
    assert not space.exists()  # 老師的資料夾不動


def test_a_linked_space_folder_is_not_followed(course_mod, course, tmp_path):
    space = course / "HK01" / "HK1Space"
    space.rmdir()
    (tmp_path / "別處").mkdir()
    (tmp_path / "別處" / "秘密.txt").write_text("x", encoding="utf-8")
    space.symlink_to(tmp_path / "別處")
    app = pack(course_mod, course, "HK1")
    with zipfile.ZipFile(sent(course)) as z:
        assert [n for n in z.namelist() if "Space" in n] == ["HK1/HK1Space/"]
    assert any("沒放進學生包" in line and "HK1Space" in line for line in app.logs)


def test_hidden_files_pycache_and_links_are_left_out_and_named(course_mod, course, tmp_path):
    space = course / "HK01" / "HK1Space"
    (space / ".DS_Store").write_bytes(b"x")
    (space / "__pycache__").mkdir()
    (space / "__pycache__" / "a.pyc").write_bytes(b"x")
    outside = tmp_path / "外面.txt"
    outside.write_text("秘密", encoding="utf-8")
    (space / "連結.txt").symlink_to(outside)
    (space / "留著.txt").write_text("ok", encoding="utf-8")
    app = pack(course_mod, course, "HK1")
    with zipfile.ZipFile(sent(course)) as z:
        assert [n for n in z.namelist() if n.startswith("HK1/HK1Space/")] == ["HK1/HK1Space/", "HK1/HK1Space/留著.txt"]
    said = [line for line in app.logs if "沒放進學生包" in line]
    assert len(said) == 1 and all(name in said[0] for name in (".DS_Store", "__pycache__", "連結.txt"))


def test_extracted_files_are_the_same_bytes(course_mod, course, tmp_path):
    pack(course_mod, course, "HK1")
    with zipfile.ZipFile(sent(course)) as z:
        z.extractall(tmp_path / "解開")
    got = tmp_path / "解開" / "HK1"
    assert (got / "HK1.py").read_bytes() == (course / "HK01" / "HK1.py").read_bytes()
    assert (got / "HK1Space").is_dir()


def test_a_second_pack_replaces_the_sent_zip(course_mod, course):
    pack(course_mod, course, "HK1")
    file = course / "HK01" / "HK1.py"
    file.write_text(file.read_text(encoding="utf-8").replace("半徑 1、", "半徑一、", 1), encoding="utf-8")
    pack(course_mod, course, "HK1", now=lambda: AT + timedelta(seconds=5))
    with zipfile.ZipFile(sent(course)) as z:
        assert "半徑一、" in z.read("HK1/HK1.py").decode("utf-8")
    assert len(versions(course)) == 2


def test_other_course_codes_and_folders(course_mod, tmp_path):
    folder = make_course(tmp_path, CODE="Lab{n}", FOLDER="Lab{n:02d}")
    load(TYPE_DIR / "type.py", "cw_type_算完畫圖").new(folder / "Lab03", "Lab3")
    app = pack(course_mod, folder, "Lab3")
    zip_path = folder / "發出去的" / "Lab3_學生包.zip"
    with zipfile.ZipFile(zip_path) as z:
        assert z.namelist() == ["Lab3/Lab3.py", "Lab3/Lab3Space/", "Lab3/README.txt", "Lab3/coursework.py"]
    assert app.revealed == [zip_path] and len(list((folder / "Lab03" / ".版本").glob("Lab3_*_學生包.zip"))) == 1


# ── README ──

def sections(text):
    """README 的三大段：macOS、Windows、出問題的時候（以「== 標題 ==」切）。"""
    parts = re.split(r"^== (.+?) ==$", text, flags=re.M)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_readme_is_filled_from_the_shell_constants(course_mod, course, cw):
    pack(course_mod, course, "HK1")
    text = readme_of(sent(course))
    assert re.search(r"\{[a-z_]+\}", text) is None
    commands = [line[4:] for line in text.splitlines() if re.match(r" {4}\S", line)]  # 剛好四格；出問題那段縮得更深
    run, win_run = cw.RUN.format(file="HK1.py"), cw.WIN_RUN.format(file="HK1.py")
    assert commands == [cw.VERSION, cw.MAKE_VENV, run, cw.WIN_VERSION, cw.WIN_MAKE_VENV, win_run]
    assert (cw.VERSION, cw.WIN_VERSION) == ("python3 --version", "py --version")
    assert "Windows（未經實機驗證）" in text
    assert "python.org" in text and "3.10" in text and "終端機" in text and "只交 HK1.py" in text
    assert "\r" not in text


def test_readme_sections_and_their_steps(course_mod, course, cw):
    pack(course_mod, course, "HK1")
    text = readme_of(sent(course))
    parts = sections(text)
    mac = next(v for k, v in parts.items() if k == "macOS")
    win = next(v for k, v in parts.items() if k.startswith("Windows"))
    assert [int(n) for n in re.findall(r"^第 (\d) 步", mac, flags=re.M)] == [1, 2, 3, 4, 5]
    assert [int(n) for n in re.findall(r"^第 (\d) 步", win, flags=re.M)] == [0, 1, 2, 3, 4, 5]
    assert "第 1 步" in cw.TOO_OLD and "python.org" in step(mac, 1)  # 殼說「照 README 第 1 步裝 python.org 的 Python」
    assert "python.org" in step(win, 1)


def step(section, n):
    m = re.search(rf"^第 {n} 步.*?(?=^第 \d 步|\Z)", section, flags=re.M | re.S)
    return m.group(0)


def test_readme_checks_the_python_version_before_making_the_venv(course_mod, course, cw):
    pack(course_mod, course, "HK1")
    parts = sections(readme_of(sent(course)))
    mac, win = parts["macOS"], parts["Windows（未經實機驗證）"]
    check = step(mac, 3)
    assert "確認 Python 版本" in check and f"    {cw.VERSION}\n" in check and "3.10 以上" in check
    assert "3.9" in check and "安裝命令列開發者工具" in check and "取消" in check
    assert "⌘Q" in check and "重開" in check and "回到第 2 步" in check
    assert cw.MAKE_VENV in step(mac, 4) and "只要做一次" in step(mac, 4)
    assert cw.RUN.format(file="HK1.py") in step(mac, 5)
    wcheck = step(win, 3)
    assert "確認 Python 版本" in wcheck and f"    {cw.WIN_VERSION}\n" in wcheck and "3.10 以上" in wcheck
    assert cw.WIN_MAKE_VENV in step(win, 4) and cw.WIN_RUN.format(file="HK1.py") in step(win, 5)


def test_windows_starts_by_unzipping_the_download(course_mod, course):
    pack(course_mod, course, "HK1")
    win = next(v for k, v in sections(readme_of(sent(course))).items() if k.startswith("Windows"))
    zero = step(win, 0)
    assert "右鍵" in zero and "全部解壓縮" in zero and "不能在 zip 裡面" in zero
    assert win.index("第 0 步") < win.index("第 1 步")


def test_readme_says_where_the_homework_part_starts_and_ends(course_mod, course):
    pack(course_mod, course, "HK1")
    text = readme_of(sent(course))
    assert "上半部" not in text
    assert "「# ── 從這裡開始是作業 ──」和「# ── 以下不用改 ──」兩行中間的部分" in text
    assert "再做一次第 5 步" in text
    template = (TYPE_DIR / "範本.py").read_text(encoding="utf-8")
    assert "# ── 從這裡開始是作業 ──" in template and "# ── 以下不用改 ──" in template  # README 說的兩行真的在範本裡


def test_readme_has_a_trouble_section_with_exactly_three_items(course_mod, course, cw):
    pack(course_mod, course, "HK1")
    parts = sections(readme_of(sent(course)))
    trouble = parts["出問題的時候"]
    items = [line for line in trouble.splitlines() if line.startswith("- ")]
    assert len(items) == 3
    assert "這份作業要 Python 3.10 以上" in items[0] and "第 3 步" in items[0]
    assert "這份作業要 Python 3.10 以上" in cw.TOO_OLD  # 殼真的會說這一句
    assert "裝套件失敗" in items[1] and "網路" in items[1] and "第 5 步" in items[1]
    assert list(parts) == ["macOS", "Windows（未經實機驗證）", "出問題的時候", "交作業"]
    assert "macOS" not in trouble  # 兩邊共用，步號相同
    assert "「.venv 是用舊的 Python 建的」" in items[2] and "第 3 步通過" in items[2] and "第 5 步" in items[2]
    assert ".venv 是用舊的 Python 建的" in cw.OLD_VENV  # 殼真的會說這一句
    deep = [line for line in trouble.splitlines() if re.match(r" {6}\S", line)]
    assert [line.strip() for line in deep] == [cw.REMAKE_VENV, cw.WIN_REMAKE_VENV]  # macOS 一行、Windows 一行


def test_readme_template_has_every_placeholder_and_no_you(course_mod):
    text = README.read_text(encoding="utf-8")
    for key in ("{code}", "{file}", "{make_venv}", "{run}", "{win_make_venv}", "{win_run}",
                "{version_check}", "{win_version_check}", "{remake_venv}", "{win_remake_venv}"):
        assert key in text, key
    assert "您" not in text and "共用" not in text  # 學生包沒有 課程.py，學生端不會共用 .venv（D130）


# ── .版本/ 的 zip（D135，A18 的 zip 那一半）──

def test_the_kept_zip_is_the_same_bytes(course_mod, course):
    app = pack(course_mod, course, "HK1")
    [kept] = versions(course)
    assert kept.name == "HK1_2026-11-06_143008_學生包.zip"
    assert kept.read_bytes() == sent(course).read_bytes()
    said = app.logs[-1]
    assert "發出去的/HK1_學生包.zip" in said and ".版本/HK1_2026-11-06_143008_學生包.zip" in said


def test_twenty_five_packs_keep_twenty_five_zips(course_mod, course):
    for i in range(25):
        pack(course_mod, course, "HK1", now=lambda i=i: AT + timedelta(minutes=i))
    assert len(versions(course)) == 25


def test_two_packs_in_the_same_second_both_stay(course_mod, course):
    pack(course_mod, course, "HK1")
    pack(course_mod, course, "HK1")
    assert [p.name for p in versions(course)] == ["HK1_2026-11-06_143008_1_學生包.zip", "HK1_2026-11-06_143008_學生包.zip"]


def test_packing_never_touches_the_py_versions(course_mod, course):
    keep = course / "HK01" / ".版本"
    keep.mkdir()
    old = keep / "HK1_2026-01-01_000000.py"
    old.write_text("# 舊的", encoding="utf-8")
    pack(course_mod, course, "HK1")
    assert old.read_text(encoding="utf-8") == "# 舊的"


def test_keep_pack(course_mod, course, tmp_path):
    zip_path = tmp_path / "HK1_學生包.zip"
    zip_path.write_bytes(b"PK zip")
    kept = course_mod.keep_pack(zip_path, course / "HK01", AT)
    assert kept == course / "HK01" / ".版本" / "HK1_2026-11-06_143008_學生包.zip" and kept.read_bytes() == b"PK zip"


# ── N3：zip 裡沒有這台電腦的東西 ──

def test_nothing_in_the_zip_points_at_this_computer(course_mod, course, tmp_path):
    pack(course_mod, course, "HK1")
    volumes = str(Path("/", "Volumes"))
    with zipfile.ZipFile(sent(course)) as z:
        for name in z.namelist():
            data = z.read(name).decode("utf-8", errors="replace") + name
            assert str(Path.home()) not in data, name
            assert getpass.getuser() not in data, name
            assert volumes not in data, name
            assert str(tmp_path) not in data, name


# ── 墊片 ──

def test_the_course_stub_calls_check_and_pack(course_mod, tmp_path):
    from core.runner import run_module
    from core.scan import module_info

    root = tmp_path / "modules" / "課程作業"
    root.mkdir(parents=True)
    import shutil

    for name in ("框架", "作業類型"):
        shutil.copytree(CW / name, root / name, ignore=shutil.ignore_patterns("__pycache__"))
    app = CwApp(tmp_path)
    app.answers_ask = ["測試課"]
    course_mod.new_course(app, root)
    folder = root / "測試課"
    homework(folder, 1)
    app = CwApp(tmp_path)
    app.answers_ask = ["HK1"]
    result = run_module(module_info(folder / "檢查與打包", root, "child"), app)
    assert result.error is None, result.error
    assert sent(folder).is_file() and app.revealed == [sent(folder)]


# ── D147：OSError 的句子指到真正出錯的路徑，不一律說作業檔 ──

def test_sent_being_a_file_names_sent_not_the_homework(course_mod, course):
    (course / "發出去的").write_text("", encoding="utf-8")
    app = pack(course_mod, course, "HK1")
    assert app.logs[-1].startswith("HK1：測試課/發出去的 有問題（") and app.logs[-1].endswith("），沒有打包")
    assert "HK1.py" not in app.logs[-1] and app.revealed == []


def test_an_unreadable_space_file_is_named(course_mod, course):
    secret = course / "HK01" / "HK1Space" / "secret.txt"
    secret.write_text("x", encoding="utf-8")
    secret.chmod(0)
    try:
        app = pack(course_mod, course, "HK1")
    finally:
        secret.chmod(0o644)
    assert app.logs[-1] == "HK1：測試課/HK01/HK1Space/secret.txt 有問題（Permission denied），沒有打包"


def test_versions_being_a_file_is_named_when_packing(course_mod, course):
    (course / "HK01" / ".版本").write_text("", encoding="utf-8")
    app = pack(course_mod, course, "HK1")
    assert app.logs[-1].startswith("HK1：測試課/HK01/.版本 有問題（") and "有問題（" in app.logs[-1] and "HK1.py" not in app.logs[-1]
