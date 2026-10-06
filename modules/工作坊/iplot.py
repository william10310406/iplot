"""工作坊：從一份清單安裝、更新別人做的模組。裝進來的東西只寫進它自己的資料夾；
覆蓋之前，舊的資料夾會整個存進它的 .history/；裝進來的模組第一次執行前會先問一次。
清單的網址寫在 config.py 的 WORKSHOP_URL。

做法都在旁邊的 workshop.py，清單那一頁是 page.html。按了才會連網。"""
from pathlib import Path

import workshop

ICON = "🧰"


def run(app):
    url = app.config.workshop_url
    if not url:
        return app.log("尚未設定工作坊的來源：在 config.py 的 WORKSHOP_URL 填 index.json 的網址")
    try:
        entries = workshop.read_index(url)
    except ValueError as exc:  # 不是 JSON、格式不對、網址寫錯
        return app.log(f"讀不懂工作坊的清單（index.json），或 WORKSHOP_URL 寫錯了：{exc}")
    except workshop.NETWORK as exc:
        return app.log(f"連不上工作坊的來源：{getattr(exc, 'reason', exc)}")
    modules_dir = app.home / "modules"
    template = (Path(__file__).parent / "page.html").read_text(encoding="utf-8")
    app.page("工作坊", workshop.render(entries, modules_dir, template), workshop.Api(app, entries, modules_dir))
    app.rescan()  # 頁面關掉之後：新裝的模組出現在面板上
