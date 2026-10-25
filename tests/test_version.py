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
    assert core.__version__.startswith("0.6.0")


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
    """「要更新嗎？」的對話框裡就是這一段：一整行、沒有反引號；先到工作坊換互通，再按「更新」（研究助理 2026-10-24）。"""
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
    ):
        assert part in notes, part
    assert notes.index("「互通」按「覆蓋」或「更新」") < notes.index("再回來按「更新」")


def test_docs_08_repeats_the_0_6_0_notes():
    doc = (ROOT / "docs" / "08_操作說明-0.6.0.md").read_text(encoding="utf-8")
    assert _notes("0.6.0") in doc
