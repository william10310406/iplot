"""AGENTS.md（給寫程式的 AI 助手讀的規則，D160）：每一條都寫著哪個檢查在擋，寫到的測試與工具都要真的存在；
CLAUDE.md、GEMINI.md 只指到它，不另寫一份（兩份就會分家）。"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = (ROOT / "AGENTS.md").read_text(encoding="utf-8")


def test_every_rule_names_its_check_or_says_it_is_manual():
    rules = re.findall(r"^\*\*(\d+)\. (.+?)\*\*(.*)$", RULES, re.M)
    assert [int(n) for n, *_ in rules] == list(range(1, len(rules) + 1))
    for n, _, tail in rules:
        assert tail.strip().startswith("（") and ("人工" in tail or "工作坊收件" in tail or "test" in tail or "tools/" in tail or "R" in tail), n


def test_the_checks_it_names_exist():
    for path, name in re.findall(r"`(tests/[\w/]+\.py)(?:::(\w+))?", RULES):
        assert (ROOT / path).is_file(), path
        if name:
            tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
            assert name in {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}, f"{path}::{name}"
    for path in re.findall(r"`(?:python3? )?(tools/[\w.-]+)", RULES):
        assert (ROOT / path).is_file(), path


def test_rule_codes_match_what_check_deps_reports():
    source = (ROOT / "tools" / "check_deps.py").read_text(encoding="utf-8")
    for code in set(re.findall(r"（(R\d+)[，）]", RULES)):
        assert f'"{code}"' in source, code


def test_the_other_assistants_files_only_point_here():
    for name in ("CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "AGENTS.md" in text and len(text) < 200, name
