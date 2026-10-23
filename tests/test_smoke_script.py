"""tests/smoke.py 自己的小函式：跳過情境 7 的原因、跳過那一行、總結那一行。smoke.py 本身是腳本，pytest 不收。"""

import importlib.util
from pathlib import Path

SMOKE = Path(__file__).resolve().parent / "smoke.py"


def load_smoke():
    spec = importlib.util.spec_from_file_location("smoke_script", SMOKE)
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    return smoke


def test_web_scenario_skip_reason_names_each_condition_that_does_not_hold(tmp_path):
    smoke = load_smoke()
    assert smoke.web_skip_reason("linux", tmp_path) == "不是 macOS、旁邊沒有裝好的 lib/"
    assert smoke.web_skip_reason("darwin", tmp_path) == "旁邊沒有裝好的 lib/"
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / ".installed").write_text("sha", encoding="utf-8")
    assert smoke.web_skip_reason("win32", tmp_path) == "不是 macOS"
    assert smoke.web_skip_reason("darwin", tmp_path) is None


def test_skip_line_and_summary_say_what_ran_and_what_was_skipped():
    smoke = load_smoke()
    assert smoke.skip_line(7, "lib/ 在、預設啟動（網頁面板）", "不是 macOS") == \
        "情境 7（lib/ 在、預設啟動（網頁面板））：跳過——不是 macOS"
    assert smoke.summary(6, 1, True) == "smoke：跑了 6 個情境、跳過 1 個，全部活著、stderr 乾淨"
    assert smoke.summary(7, 0, False) == "smoke：跑了 7 個情境、跳過 0 個，有情境失敗"
