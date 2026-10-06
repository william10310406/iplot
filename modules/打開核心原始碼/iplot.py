"""在 Finder 打開 core/ 資料夾。所有人都能改原始碼，從看得到它開始。"""
ICON = "🧬"


def run(app):
    app.open(app.home / "core")
