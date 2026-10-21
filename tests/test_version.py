import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _publish():
    spec = importlib.util.spec_from_file_location("publish", ROOT / "tools" / "publish.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _notes():
    return _publish().changelog_notes(ROOT / "CHANGELOG.md", "0.5.2")


def test_version_is_string():
    import core
    assert core.__version__.startswith("0.5.2")


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


def test_docs_08_repeats_the_0_5_2_notes():
    doc = (ROOT / "docs" / "08_操作說明-0.5.2.md").read_text(encoding="utf-8")
    assert _notes() in doc
