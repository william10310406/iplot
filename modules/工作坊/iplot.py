"""工作坊：從一份清單安裝、更新別人做的模組。裝進來的東西只寫進它自己的資料夾；
覆蓋之前，舊的資料夾會整個存進它的 .history/；裝進來的模組第一次執行前會先問一次。
清單的網址寫在 config.py 的 WORKSHOP_URL。

做法都在旁邊的 workshop.py，清單那一頁是 page.html。清單最上面那一行與每一列的上傳者，都是清單給的。按了才會連網。"""
import importlib.util
from pathlib import Path

import workshop

ICON = "🧰"


def run(app):
    url = app.config.workshop_url
    if not url:
        return app.log("尚未設定工作坊的來源：在 config.py 的 WORKSHOP_URL 填 index.json 的網址")
    if not _separate(app):  # 清單在另開的程序裡抓、裡面開；面板空出來
        return
    try:
        entries, notice = workshop.read_listing(url)
    except ValueError as exc:  # 不是 JSON、格式不對、網址寫錯
        why = f"（{exc}）" if type(exc) is ValueError else ""  # 自己寫的中文原因照留；JSON 解析器的英文原文不給人看
        return app.log(f"讀不懂工作坊的清單（index.json）{why}。可能是 config.py 的 WORKSHOP_URL 寫錯了（它要指到 index.json），"
                       "或清單暫時壞了；確認之後再雙擊一次「工作坊」。")
    except workshop.NETWORK as exc:
        return app.log(f"工作坊的清單抓不下來：{workshop.plain(exc)}。也請確認 config.py 的 WORKSHOP_URL 沒有寫錯，再雙擊一次「工作坊」。")
    modules_dir = app.home / "modules"
    template = (Path(__file__).parent / "page.html").read_text(encoding="utf-8")
    app.page("工作坊", workshop.render(entries, modules_dir, template, notice), workshop.Api(app, entries, modules_dir))
    app.rescan()  # 頁面關掉之後：新裝的模組出現在面板上


def _separate(app) -> bool:
    """有「互通」的 separate.py（互通 0.4.0 起）就經它另開一個程序開這一頁，面板不會被卡住；回 False 表示已經另開
    或叫到最前面了，這裡不用開。沒有就照舊在這裡開。用檔案路徑載入：這個模組的 sys.path[0] 是自己的資料夾。"""
    path = Path(app.home) / "modules" / "互通" / "separate.py"
    if not path.is_file():
        return True
    spec = importlib.util.spec_from_file_location("iplot_interop_separate", path)
    separate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(separate)
    return separate.here(app)
