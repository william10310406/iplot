"""每日入口：一鍵打開 iPLoT 資料夾、docs/、設計文件和終端機，然後開工。"""


def run(app):
    app.open(app.home)
    app.open(app.home / "docs")
    app.edit(app.home / "docs" / "02_重構設計.md")
    app.terminal(app.home)
    app.log("開工：iPLoT 資料夾、docs、設計文件、終端機都開了")
