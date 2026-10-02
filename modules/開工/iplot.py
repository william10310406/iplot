"""每日入口：一鍵打開 iPLoT 資料夾、docs/、設計文件和 Terminal，然後開工。"""

import subprocess


def run(app):
    app.open(app.home)
    app.open(app.home / "docs")
    app.edit(app.home / "docs" / "02_重構設計.md")
    subprocess.run(["open", "-a", "Terminal", str(app.home)], check=False)
    app.log("開工：iPLoT 資料夾、docs、設計文件、Terminal 都開了")
