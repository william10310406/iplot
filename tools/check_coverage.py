"""覆蓋率只准持平或上升（D160 第 5 條）：拿 pytest-cov 的 JSON 報告跟 tools/coverage-baseline.json 比。

    python -m pytest --cov --cov-report=json:coverage.json
    python3 tools/check_coverage.py coverage.json            # 比基準低就失敗
    python3 tools/check_coverage.py coverage.json --write    # 升上去了：把基準一起升（只准升，不准用它降）

量哪些在 pyproject.toml 的 [tool.coverage.run]（核心、面板、main.py、隨附模組）。各作業系統跳過的測試不一樣，
CI 只在 ubuntu、Python 3.12 那一格比。容許 0.1 個百分點的誤差（同一份程式碼，執行緒的時機不同，偶爾差一兩行）。"""

import json
import sys
from pathlib import Path

BASELINE = Path(__file__).resolve().parents[1] / "tools" / "coverage-baseline.json"
SLACK = 0.1


def main(argv: list[str]) -> int:
    report = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    now = round(report["totals"]["percent_covered"], 2)
    base = json.loads(BASELINE.read_text(encoding="utf-8"))["percent"] if BASELINE.is_file() else 0.0
    if "--write" in argv[1:]:
        if now < base:
            print(f"覆蓋率 {now}% 比基準 {base}% 低：基準只准升，不准用 --write 降")
            return 1
        BASELINE.write_text(json.dumps({"percent": now}, indent=1) + "\n", encoding="utf-8")
        print(f"基準改成 {now}%")
        return 0
    if now + SLACK < base:
        print(f"覆蓋率 {now}% 比基準 {base}% 低：補測試，不要降基準（AGENTS.md 第 17 條）")
        return 1
    print(f"覆蓋率 {now}%（基準 {base}%）" + ("：升上去了，可以用 --write 把基準一起升" if now >= base + 1 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
