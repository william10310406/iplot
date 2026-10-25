"""回報問題、提建議、看大家在討論什麼。"""
# ── 互通 ── 直接執行這個檔（python3 iplot.py）時交給 iPLoT 用彈出式視窗跑；從 iPLoT 裡執行時這段不做事。不要可以整段刪掉
import sys

if __name__ == "__main__" and "core.runner" not in sys.modules:
    import os
    import subprocess
    here = folder = os.path.dirname(os.path.abspath(__file__))
    run = None
    while run is None and folder != os.path.dirname(folder):  # 往上一層層找 iPLoT：模組在它裡面或旁邊都找得到
        folder = os.path.dirname(folder)
        try:
            names = [""] + sorted(os.listdir(folder))
        except OSError:
            names = [""]
        runs = (os.path.join(folder, n, "modules", "互通", "run.py") for n in names)
        run = next((r for r in runs if os.path.isfile(r)), None)
    if run and not os.environ.get("IPLOT_DIRECT"):  # IPLOT_DIRECT=1：不交出去，照一般腳本跑（例如在編輯器裡除錯）
        sys.exit(subprocess.call([sys.executable, run, here, *sys.argv[1:]]))
    if not run:
        print("找不到 iPLoT 的「互通」（先在工作坊裝「互通」；模組要放在 iPLoT 資料夾裡或它旁邊），照一般的 python3 iplot.py 跑",
              file=sys.stderr)
# ── 互通 ──

import json
import threading
import time
import webbrowser
from pathlib import Path

import forum
import redact
import report

ICON = "💬"
HERE = Path(__file__).resolve().parent
OUTBOX = HERE / "回報"  # 完整的回報（.txt）與 tkinter 面板的草稿（.md）：只放在這台電腦，不進 git、不進包
BROWSER_FAILS = (webbrowser.Error, OSError, ValueError)  # 找不到瀏覽器、Windows 的 ShellExecute、3.14 對 - 開頭的網址
OPENED = ("已經在瀏覽器打開了。登入 GitHub、按 Start discussion 才會公開。{where}如果 GitHub 出錯（例如顯示 500，或填好的"
          "內容不見了）：確認瀏覽器已經登入之後，回到這裡再按一次「在瀏覽器打開」；還是不行，就在 GitHub 的新增頁把內文整個換成"
          "完整的回報、直接貼上（複製下面的網址會蓋掉剪貼簿，貼上之前先按「再複製一次」）。這個視窗可以關掉了。")
CUT_SAVED = ("內容太長，網址裡的 traceback 中間截掉了；那個檔是完整的，貼上之後也可以把它拖進留言框當附件。"
             "關掉這個視窗之後 iPLoT 會指給你看。")
CUT_UNSAVED = "內容太長，網址裡的 traceback 中間截掉了。"  # 存不了檔：沒有「那個檔」可以指
NOT_OPENED = "瀏覽器打不開。把下面這串網址整個複製到瀏覽器的網址列；{where}"


def stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def render(data: dict) -> str:
    """page.html，資料以 JSON 放進 <script type="application/json">：< 換成 \\u003c，traceback 裡的 </script>
    關不掉它；頁面上的字一律用 textContent／value。"""
    return (HERE / "page.html").read_text(encoding="utf-8").replace(
        "__DATA__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c"), 1)


def _again(rep: report.Report, title: str, body: str) -> tuple[str, str, str]:
    """送出前再遮一次（同一個 ctx：使用者在頁面上、草稿裡貼進來的路徑也遮），回 (title, body, full)。
    full 是剪貼簿與 .txt 那一份：遮過、沒截、不帶 HINT（設計第 17 節第 15 條）。"""
    title, body = redact.redact(title, rep.ctx)[0], redact.redact(body, rep.ctx)[0]
    return title, body, f"{title}\n\n{body}"


def _save(kind: str, full: str) -> tuple[Path | None, OSError | None]:
    """把完整的回報存進 OUTBOX（一律存，不只截過的時候）；存不了回 (None, 錯誤)，照樣往下走。"""
    try:
        return report.save(OUTBOX, stamp(), kind, full), None
    except OSError as exc:
        return None, exc


def _open(u: str) -> bool:
    """標準庫的 webbrowser.open，不經過核心；打不開回 False，不丟例外。"""
    try:
        return bool(webbrowser.open(u))
    except BROWSER_FAILS:
        return False


def _sentence(ok: bool, cut: bool, f: Path | None, err: OSError | None) -> str:
    """send 回給頁面的那一句：只講檔案與網址（剪貼簿成不成，頁面自己知道，那一句由頁面加）。"""
    lost = f"存不了檔（{err}）；完整的回報只在剪貼簿裡。"
    if not ok:
        return NOT_OPENED.format(where=f"完整的回報存在 回報/{f.name}，關掉這個視窗之後 iPLoT 會指給你看。" if f else lost)
    text = OPENED.format(where=f"完整的回報也存在 回報/{f.name}。" if f else lost)
    if cut:
        text += CUT_SAVED if f else CUT_UNSAVED
    return text


class Api:
    """預覽頁的 JS 呼叫的入口（pywebview.api.measure／send），照「工作坊」的樣子：在 pywebview 的執行緒上跑，
    只遮、組網址、存檔、開瀏覽器，不叫 app、不碰 core（設計第 17 節第 4 條）；屬性都以底線開頭，不丟例外。"""

    def __init__(self, rep: report.Report, kind: str, saved: list[Path]):
        self._rep, self._kind = rep, kind
        self._saved = saved  # 截過、或瀏覽器打不開的那一次存的檔：on_error 在頁面關掉之後指給人看
        self._lock = threading.Lock()  # pywebview 每一次 api 呼叫各一條執行緒

    def measure(self, title: str, body: str) -> dict:
        """長度那一行與 full：頁面把 full 放進 #full，按下去時複製的就是它（跟 send 存的檔一字不差）。"""
        with self._lock:
            rep = self._rep
            title, body, full = _again(rep, title, body)
            u, limit = report.url(rep.category, title, report.with_hint(body)), report.max_url()
            sentence = f"網址長度 {len(u)}／{limit}"
            if not report.fits(u, limit):
                sentence += "：traceback 會從中間截斷；完整的會在剪貼簿與檔案裡"
            return {"length": len(u), "limit": limit, "sentence": sentence, "full": full}

    def send(self, title: str, body: str) -> dict:
        """再遮一次、先存檔、再組網址開瀏覽器（研究助理 2026-10-24：登入之後 GitHub 可能回 500，不能只靠網址）。"""
        with self._lock:
            rep = self._rep
            title, body, full = _again(rep, title, body)
            f, err = _save(self._kind, full)
            u, cut = report.fit(rep.category, title, body, report.max_url())
            ok = _open(u)
            if f is not None and (cut or not ok) and f not in self._saved:
                self._saved.append(f)
            return {"ok": ok, "url": "" if ok else u, "file": f.name if f else "", "cut": cut,
                    "new_url": report.url(rep.category, "", ""), "sentence": _sentence(ok, cut, f, err)}


def run(app):
    app.log(f"還沒做好：{forum.FORUM}")


def on_error(app, error):
    """面板上的「回報這個問題」（D110）：遮過的回報給人看、讓人改，再用預填的網址開瀏覽器（設計第 5.1、5.2 節）。
    頁面那一頭不碰 app：存了要指給人看的檔，等頁面關掉、回到這裡才 reveal。"""
    rep = report.from_error(error, app)
    if report.panel_kind() == "tkinter":
        return _by_file(app, rep, error.kind)
    saved = []
    data = {"mode": "edit", "title": rep.title, "body": rep.body, "notice": rep.notice, "hint": report.HINT}
    app.page("回報這個問題", render(data), Api(rep, error.kind, saved))
    for p in saved:
        app.reveal(p)


def _by_file(app, rep: report.Report, kind: str) -> None:
    """tkinter 面板沒有頁面（設計第 5.2 節）：草稿用編輯器打開，改好按「確定」才送。草稿沒有再遮過、只留在這台電腦；
    拿去貼、拖去當附件的是讀回來再遮過、存成 .txt 的那一份。tkinter 的模組在主執行緒上跑，這裡叫 app 沒問題。"""
    OUTBOX.mkdir(parents=True, exist_ok=True)
    draft = OUTBOX / f"{stamp()}-{kind}.md"
    draft.write_text(f"{rep.title}\n\n{rep.body}", encoding="utf-8", newline="\n")
    app.log(rep.notice)
    app.edit(draft)
    if not app.confirm(f"草稿在 回報/{draft.name}，已經用編輯器打開。改好、存檔之後按「確定」就用瀏覽器打開；"
                       "按「取消」就不送，草稿留著。"):
        app.log(f"沒有送出；草稿留在 回報/{draft.name}")
        return
    first, _, rest = draft.read_text(encoding="utf-8-sig").partition("\n")  # 記事本存檔可能加 BOM
    lines = rest.split("\n")
    while lines and not lines[0].strip():  # 標題底下的空行不算內文
        lines.pop(0)
    title, body, full = _again(rep, first, "\n".join(lines))
    p, err = _save(kind, full)  # 先存檔、複製，再開瀏覽器
    copied = _copy_tk(full)
    u, cut = report.fit(rep.category, title, body, report.max_url())
    ok = _open(u)
    app.log(_tk_sentence(p, err, copied, report.url(rep.category, "", ""), draft.name))
    if not ok:
        app.log(f"瀏覽器打不開。把這串網址整個複製到瀏覽器的網址列：{u}")
    if p is not None and (cut or not ok):
        app.reveal(p)


def _tk_sentence(p: Path | None, err: OSError | None, copied: bool, new_url: str, draft: str) -> str:
    """tkinter 面板開了瀏覽器之後訊息區的那一句：完整的回報在哪裡、GitHub 出錯時怎麼貼。"""
    if p is None and copied:
        return (f"完整的回報已經複製到剪貼簿；存不了檔（{err}），完整的回報只在剪貼簿裡。如果 GitHub 出錯（例如顯示 500）："
                f"確認瀏覽器已經登入之後再選一次；還是不行，就打開 {new_url}、直接貼上（複製這個網址會蓋掉剪貼簿）。"
                + report.HINT)
    if p is None:
        return (f"存不了檔（{err}），剪貼簿也沒有複製成功：如果 GitHub 出錯，打開 {new_url}，再從草稿 回報/{draft} 複製全文、"
                "直接貼上（草稿沒有再遮過，貼上之前再看一次）。")
    if copied:
        return (f"完整的回報已經複製到剪貼簿，也存在 回報/{p.name}。如果 GitHub 出錯（例如顯示 500）：確認瀏覽器已經登入之後"
                f"再選一次；還是不行，就打開 {new_url}（複製這個網址會蓋掉剪貼簿），再從 回報/{p.name} 複製全文、直接貼上。"
                + report.HINT)
    return (f"完整的回報存在 回報/{p.name}（剪貼簿沒有複製成功）：如果 GitHub 出錯，打開 {new_url}，"
            "再從那個檔複製全文、直接貼上。")


def _copy_tk(text: str) -> bool:
    """複製到 tkinter 面板自己的那個 Tk 的剪貼簿（app 沒有剪貼簿的動作）。只在 tkinter 面板叫：網頁面板開著的時候
    import tkinter 會被擋。拿不到那個 Tk、或任何一步出錯，回 False。"""
    try:
        import tkinter

        root = getattr(tkinter, "_default_root", None)
        if root is None:
            return False
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()  # 不用 update()：它會在模組裡面重入地處理排著的滑鼠事件
    except Exception:  # noqa: BLE001  複製不成不能讓整個回報停下來
        return False
    return True
