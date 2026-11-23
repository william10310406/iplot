import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _publish():
    spec = importlib.util.spec_from_file_location("publish", ROOT / "tools" / "publish.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _notes(version="0.5.2"):
    return _publish().changelog_notes(ROOT / "CHANGELOG.md", version)


def test_version_is_string():
    import core
    assert core.__version__.startswith("0.8.0")


def test_0_5_2_notes_carry_the_two_manual_steps():
    notes = _notes()
    assert notes
    assert "\n" not in notes
    assert "`" not in notes
    for part in (
        ".backup/download-0.5.2.zip",
        "iPLoT-v0.5.2/modules/工作坊",
        'WORKSHOP_URL = "https://william10310406.github.io/iplot-modules/index.json"',
        "只做②",
    ):
        assert part in notes


def test_0_6_0_notes_carry_the_manual_steps():
    """「要更新嗎？」的對話框裡就是這一段：一整行、沒有反引號；先到工作坊換互通，再按「更新」（研究助理 2026-10-24）。
    沒做過 0.5.2 那兩件事的人（0.5.0、0.5.1）能看到的只有這一段——「更新」不換 README 與 docs/——
    所以退路要連工作坊、WORKSHOP_URL、怎麼打開 .backup、換完重做捷徑都寫進來（最後審查 release-1、release-3）。"""
    notes = _notes("0.6.0")
    assert notes
    assert "\n" not in notes
    assert "`" not in notes
    for part in (
        "回報這個問題",
        "回報與討論",
        "互通 0.2.0",
        "互通 0.1.0 支援 iPLoT 0.5",
        ".backup/download-0.6.0.zip",
        "iPLoT-v0.6.0/modules",
        "重新啟動",
        "先按「取消」",
        "這一次按「確定」",
        "「工作坊」三個資料夾",
        'WORKSHOP_URL = "https://william10310406.github.io/iplot-modules/index.json"',
        "open .backup",
        "雙擊一次「互通」",
        "回報功能剛上線，畫面異常或複製失敗請直接用它回報。",  # 研究助理 2026-10-26：發佈說明加的兩句
        "按送出前，請先看一下 GitHub 內文裡有沒有人名或學號，有的話不要送出，直接告訴我。",
    ):
        assert part in notes, part
    assert notes.index("「互通」按「覆蓋」或「更新」") < notes.index("再回來按「更新」")
    assert notes.rindex("重新啟動") < notes.index("雙擊一次「互通」")  # 捷徑在新的核心起來之後才重做


def test_0_6_1_notes_carry_both_paths():
    """0.6.1 的「要更新嗎？」：0.6.0 的人直接按「確定」；還在 0.5.x 的人看到的也只有這一段，所以 0.6.0 那套
    「先到工作坊換互通、再按更新」的退路照樣帶著（版本號換成 0.6.1）。"""
    notes = _notes("0.6.1")
    assert notes
    assert "\n" not in notes
    assert "`" not in notes
    for part in (
        "modules/ 資料夾被刪掉時",
        "這會公開在網路上",
        "已經是 0.6.0 的人：按「確定」",
        "還在 0.5.x 的人請先按「取消」",
        "互通 0.1.0 支援 iPLoT 0.5",
        ".backup/download-0.6.1.zip",
        "iPLoT-v0.6.1/modules",
        'WORKSHOP_URL = "https://william10310406.github.io/iplot-modules/index.json"',
        "雙擊一次「互通」",
        "按送出前，請先看一下 GitHub 內文裡有沒有人名或學號，有的話不要送出，直接告訴我。",
    ):
        assert part in notes, part
    assert "0.6.0.zip" not in notes and "iPLoT-v0.6.0" not in notes
    assert notes.index("「互通」按「覆蓋」或「更新」") < notes.index("再回來按「更新」")


def test_0_6_2_notes_carry_both_paths():
    """0.6.2 的「要更新嗎？」：0.6.0、0.6.1 的人直接按「確定」；還在 0.5.x 的人看到的也只有這一段，
    所以「先到工作坊換互通、再按更新」的退路照樣帶著（版本號換成 0.6.2）。"""
    notes = _notes("0.6.2")
    assert notes
    assert "\n" not in notes
    assert "`" not in notes
    for part in (
        "出錯了，要回報嗎？",
        "這次執行期間不要再問",
        "學生作業出錯不會問",
        "已經是 0.6.0 或 0.6.1 的人：按「確定」",
        "還在 0.5.x 的人請先按「取消」",
        "互通 0.1.0 支援 iPLoT 0.5",
        ".backup/download-0.6.2.zip",
        "iPLoT-v0.6.2/modules",
        'WORKSHOP_URL = "https://william10310406.github.io/iplot-modules/index.json"',
        "雙擊一次「互通」",
        "按送出前，請先看一下 GitHub 內文裡有沒有人名或學號，有的話不要送出，直接告訴我。",
    ):
        assert part in notes, part
    assert "0.6.1.zip" not in notes and "iPLoT-v0.6.1" not in notes
    assert notes.index("「互通」按「覆蓋」或「更新」") < notes.index("再回來按「更新」")


def test_0_6_3_notes_are_for_users_not_for_the_publisher():
    """「要更新嗎？」的對話框裡就是這一段（清單 1-07）：三到五行、沒有反引號、沒有寫給發佈者的提醒。"""
    notes = _notes("0.6.3")
    assert 3 <= len(notes.splitlines()) <= 5
    assert "`" not in notes
    for banned in ("按送出前", "直接告訴我", "人名或學號"):
        assert banned not in notes
    for part in ("已經是 0.6.0、0.6.1、0.6.2 的人：按「確定」", "重新啟動", "還在 0.5.x 的人請先按「取消」", "「互通」按「覆蓋」或「更新」"):
        assert part in notes, part
    assert notes.index("先按「取消」") < notes.index("再回來按「更新」")


def test_0_7_0_notes_say_the_order_and_that_nothing_was_checked_by_hand():
    """按「更新」顯示的就是這一段：第一句是先換互通與行事曆（順序反了互通會擋下來），最後說明沒有人工驗收、怎麼回報。"""
    notes = _notes("0.7.0")
    assert "\n" not in notes and "`" not in notes
    assert notes.startswith("先到「工作坊」把「互通」更新到 0.3.0、「行事曆」更新到 0.1.3，再按「更新」；順序反了的話")
    assert "到工作坊更新互通就好。" in notes.split("這一版有頁面的模組")[0]
    assert notes.endswith("這一版的導覽列沒有人工驗收過，碰到問題請用「回報與討論」回報。")
    assert "還在 0.5.x 的人請先按「取消」" in notes


def test_0_7_1_notes_still_say_what_the_new_menu_does():
    notes = _notes("0.7.1")
    for part in ("「改名…」或「移到垃圾桶…」", "不會直接刪掉", "已經是 0.7.0 的人：按「確定」"):
        assert part in notes, part


def test_0_7_2_notes_are_for_users_and_say_what_is_and_is_not_replaced():
    """「更新」的確認框裡就是這一段：三到五行、沒有反引號、沒有寫給發佈者的提醒；說隨附模組一起換、哪些不動、改過的怎麼辦。"""
    notes = _notes("0.7.2")
    assert 3 <= len(notes.splitlines()) <= 5
    assert "`" not in notes
    for part in ("隨附的模組換成新版", "重新啟動", "你自己做的模組、從工作坊裝的模組、模組裡留下的資料都不會動", "被你改過，就不會換",
                 "「放回」", "「互通」更新到 0.3.0、「行事曆」更新到 0.1.3", "還在 0.5.x 的人請先按「取消」"):
        assert part in notes, part
    for banned in ("按送出前", "直接告訴我", "人名或學號"):
        assert banned not in notes
    assert notes.index("先按「取消」") < notes.index("再回來按「更新」")


def test_0_7_3_notes_are_for_users_and_say_pages_open_in_their_own_window():
    """「更新」的確認框：三到五行、沒有反引號；說有頁面的模組另開、已經開著會叫到前面、互通要 0.4.0、舊版的順序。"""
    notes = _notes("0.7.3")
    assert 3 <= len(notes.splitlines()) <= 5
    assert "`" not in notes
    for part in ("在自己的視窗裡開", "不用等它關掉", "叫到最前面", "重新啟動", "互通要 0.4.0", "已經是 0.7.x 的人直接按「確定」",
                 "還在 0.5.x 的人請先按「取消」"):
        assert part in notes, part
    for banned in ("按送出前", "直接告訴我", "人名或學號"):
        assert banned not in notes


def test_0_8_0_notes_say_what_moved_into_modules_and_that_everyone_presses_ok():
    """「更新」的確認框：三到五行、沒有反引號；整理、導覽列自動裝上、互通要到工作坊更新、工作坊的模組先問一次（D159）。"""
    notes = _notes("0.8.0")
    assert 3 <= len(notes.splitlines()) <= 5
    assert "`" not in notes
    for part in ("「整理」", "「導覽列」", "同一層", "重新啟動", "「互通」到「工作坊」按「更新」", "先問你一次",
                 "0.5.x、0.6.x、0.7.x 的人都直接按「確定」"):
        assert part in notes


def test_0_7_4_notes_say_only_the_workshop_updates_itself():
    """「更新」的確認框：三到五行、沒有反引號；工作坊自己更新、其他模組不會、0.5.x 也按確定再到工作坊換互通（D158）。"""
    notes = _notes("0.7.4")
    assert 3 <= len(notes.splitlines()) <= 5
    assert "`" not in notes
    for part in ("任何一版都打得開", "自己更新自己", "其他模組不會自動更新", "重新啟動", "0.6.x、0.7.x 的人直接按「確定」",
                 "還在 0.5.x 的人也按「確定」", "把「互通」按「更新」或「覆蓋」"):
        assert part in notes, part


def test_docs_08_repeats_the_0_7_4_notes():
    doc = (ROOT / "docs" / "08_操作說明-0.7.4.md").read_text(encoding="utf-8")
    assert _notes("0.7.4") in doc
