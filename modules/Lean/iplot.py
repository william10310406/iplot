"""Lean 實數遊戲：只用 Lean，從自然數一路蓋到實數，再證不等式與極限。遊戲在網路上，不用安裝。"""
import http.client
import json
import os
import ssl
import urllib.request
import webbrowser

ICON = "📐"
GAME_URL = "https://adam.math.hhu.de/#/g/william10310406/reals-game"
CHECK_URL = "https://adam.math.hhu.de/"  # 只看伺服器連不連得上，不讀內容
TIMEOUT = 8
NETWORK = (OSError, http.client.HTTPException)  # 連不上、逾時、憑證不對、連到一半斷掉、伺服器沒回話
BROWSER_FAILS = (webbrowser.Error, OSError, ValueError)

INTRO = ("Lean 實數遊戲：只用 Lean，從自然數一路蓋到整數、有理數、實數，再證不等式與極限；遊戲內容是英文。"
         "需要網路，不用安裝任何東西：遊戲跑在 adam.math.hhu.de 的公開伺服器上。")
OFFLINE = "連不上 adam.math.hhu.de（{reason}），遊戲沒有打開。確認網路連得上之後再按一次。"
OPENED = "已經用瀏覽器打開遊戲。進度存在那個瀏覽器裡。"
NOT_OPENED = "瀏覽器打不開。把這個網址複製到瀏覽器的網址列：{url}"
NO_PAGE = "這個面板不能把遊戲放在 iPLoT 的視窗裡（安全模式與後備面板都是），改用瀏覽器開。"
CLOSED = "遊戲視窗關了。"

PAGE = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>Lean 實數遊戲</title>
<style>
  body { font: 15px/1.6 -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif; margin: 28px; color: #222; }
  h1 { font-size: 22px; margin: 0 0 12px; }
  p { margin: 0 0 10px; }
  .buttons { margin: 20px 0 14px; }
  button { font: inherit; padding: 8px 18px; margin-right: 10px; border-radius: 6px; border: 1px solid #888;
           background: #f4f4f4; cursor: pointer; }
  button.main { background: #1f6feb; border-color: #1f6feb; color: #fff; }
  .note { font-size: 13px; color: #555; }
  #status { margin-top: 12px; }
</style>
</head>
<body>
<h1>Lean 實數遊戲</h1>
<p>只用 Lean，從自然數一路蓋到整數、有理數、實數，最後證不等式與極限。遊戲內容是英文。</p>
<p>需要網路；不用安裝任何東西，遊戲跑在 adam.math.hhu.de 的公開伺服器上。</p>
<div class="buttons">
  <button class="main" id="here">在這個視窗裡玩</button>
  <button id="browser">用瀏覽器玩</button>
</div>
<p class="note">在這個視窗裡玩：關掉視窗之後進度不會留著；視窗開著的時候，iPLoT 其他格要等它關掉才會執行。
要慢慢玩、留著進度，用瀏覽器。</p>
<p id="status"></p>
<script>
const GAME = __GAME__;
window.addEventListener("pywebviewready", () => { window.pywebview.api.shown(); });
document.getElementById("here").addEventListener("click", () => { window.location.href = GAME; });
document.getElementById("browser").addEventListener("click", () => {
  window.pywebview.api.browser().then((text) => { document.getElementById("status").textContent = text; });
});
</script>
</body>
</html>
"""


def page() -> str:
    """那一頁的 HTML。遊戲的網址以 JSON 字串放進 JS（< 寫成 \\u003c）；頁面本身不載入任何外部資源。"""
    return PAGE.replace("__GAME__", json.dumps(GAME_URL).replace("<", "\\u003c"))


def _context():
    """驗證 https 憑證用的設定（跟「工作坊」一樣）：python.org 的 macOS Python 憑證庫是空的時候，改用 macOS 自己的那一份。"""
    context = ssl.create_default_context()
    if not context.cert_store_stats()["x509_ca"] and os.path.exists("/etc/ssl/cert.pem"):
        context.load_verify_locations("/etc/ssl/cert.pem")
    return context


def unreachable(url: str = CHECK_URL, timeout: float = TIMEOUT) -> str | None:
    """連得上回 None；連不上回一句原因（給人看的，不是 traceback）。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout, context=_context()) as response:
            response.read(1)
    except NETWORK as exc:
        return str(getattr(exc, "reason", "") or exc) or type(exc).__name__
    return None


def open_browser() -> str:
    """用瀏覽器開遊戲，回一句結果。"""
    try:
        ok = webbrowser.open(GAME_URL)
    except BROWSER_FAILS:
        ok = False
    return OPENED if ok else NOT_OPENED.format(url=GAME_URL)


class Api:
    """給那一頁的 JS 用。在 pywebview 的執行緒上執行，不碰 app；屬性名以底線開頭，頁面碰不到。"""

    def __init__(self):
        self._shown = False

    def shown(self):
        """頁面載入好了：表示這個面板真的開得出頁面。"""
        self._shown = True

    def browser(self):
        return open_browser()


def run(app):
    app.log(INTRO)
    reason = unreachable()
    if reason:
        app.log(OFFLINE.format(reason=reason))
        return
    api = Api()
    app.page("Lean 實數遊戲", page(), api)  # 網頁面板：開一個視窗，關掉才回來；tkinter 面板只記一行就回來
    if api._shown:
        app.log(CLOSED)
        return
    app.log(NO_PAGE)
    app.log(open_browser())
