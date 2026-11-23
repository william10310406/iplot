"""所有畫面文字，與新模組範本。要換語言只換這個檔。"""

# main.py 的版本防線之前就會 import 這個檔：型別註記不能在舊版 Python 求值（D46）
from __future__ import annotations

T: dict[str, str] = {
    "here": "這一層",
    "parent": "上一層",
    "empty_group": "尚無模組，按 ＋ 新增",
    "root_missing": "找不到 {path}。確認那個資料夾還在；如果是在 config.py 的 ROOTS 自己加的位置、不需要了，把那一行拿掉",
    "root_unreadable": "讀不到 {path}，可能是沒有權限。macOS 請到「系統設定 → 隱私權與安全性 → 檔案與檔案夾」，把 Python 的開關打開；"
                       "如果是在 config.py 的 ROOTS 自己加的位置、不需要了，把那一行拿掉",
    "done": "{title} 完成（{seconds:.1f} 秒）",
    "error_at_line": "模組『{module}』第 {line} 行出錯：{kind}，{message}",
    "error_no_line": "模組『{module}』出錯：{kind}，{message}",
    "core_error": "核心錯誤：iPLoT 自己出了問題，剛才的動作沒做成。再做一次看看；還是不行，詳細內容在 logs/iplot.log",
    "config_error": "config.py 壞了，已用預設值啟動：{message}",
    "missing_handler": "iplot.py 沒有定義 {handler}(app)",
    "module_exit": "模組以 exit({code}) 結束",
    "input_cancelled": "在提問時按了取消",
    "module_cancelled": "模組『{module}』已取消",
    "not_found": "找不到模組『{name}』",
    "ambiguous": "有兩個以上的模組叫『{name}』：{paths}",
    "file_unreadable": "iplot.py 讀不了：它的編碼不是 UTF-8、含有看不見的特殊字元，或是沒有讀取的權限。用文字編輯器打開，另存成 UTF-8",
    "bad_name": "名稱不能是空白、以 . 開頭、結尾是 . 或空白、含 / \\ : * ? \" < > |，"
                "也不能是 CON、NUL 這類 Windows 保留字（模組要能複製到任何系統）",
    "already_exists": "『{name}』已經是模組了",
    "ask_name": "新模組的名稱",
    "bundled_updated": "隨附模組已換成這一版的：{names}。換下來的舊檔案備份在 {backup}",
    "bundled_modified": "隨附模組『{name}』的程式你改過，這次沒有換，你的版本照舊留著。新版在 {package} 裡的 modules/{name}/：想用新版，把它複製過去（你改過的先自己留一份）",
    "bundled_failed": "隨附模組『{name}』沒換成新版：{message}。已經放回原來的檔案，下次啟動會再試一次",
    "open_file": "打開檔案",
    "menu_edit": "打開程式碼",
    "menu_reveal": "在資料夾中顯示",
    "menu_terminal": "在終端機打開",
    "menu_add_child": "在這裡新增下一層模組…",
    "menu_run": "執行",
    "menu_enter": "進入下一層",
    "add_tile": "新模組",
    "status_hint": "單擊選一個模組看它的說明；雙擊執行。",
    "details": "詳細",
    "hide_details": "收起",
    "report_issue": "回報這個問題",
    "offer_report": "出錯了，要回報嗎？\n{sentence}\n\n回報之前會先給你看要送出的內容，可以改。",
    "offer_mute": "這次執行期間不要再問",
    "offer_yes": "回報",
    "offer_no": "不用",
    "ok": "確定",
    "cancel": "取消",
    "scanned": "已掃描 {roots}，找到 {count} 個模組",
    "list_sep": "、",
    "icon_unusable": "『{title}』的圖示檔讀不到或超過 1 MB，先用預設圖示",
    "installing": "第一次啟動：正在安裝介面（需要網路，約 {size}）…",
    "install_done": "安裝完成，重新啟動中…",
    "install_failed": "介面安裝失敗：{message}\n安裝需要網路。再試一次：重新啟動 iPLoT。現在先改用備用面板",
    "no_pip": "這個 Python 沒有 pip（Python 用來安裝套件的工具），裝不了介面。請改用 python.org 的 Python（它內含 pip）",
    "no_tk": "這個 Python 沒有 tkinter，安全模式與備用面板都開不了；請用 python.org 的版本",
    "web_failed": "網頁面板開不起來：{message}。已改用備用面板",
    "refreshing": "介面要用的套件換了版本，正在重新安裝（需要網路）…",
    "refresh_failed": "介面的套件這次沒有換成新的：{message}\n先用現有的開；有網路之後重新啟動 iPLoT 會再試一次。",
    "confirm_foreign": "『{title}』是從外面裝進來的，第一次執行前確認：它是會在這台電腦上執行的程式，能讀寫你的檔案。要執行嗎？",
    "cancelled": "已取消執行『{title}』",
    "nav_gone": "找不到模組『{title}』，可能已經被移除了",
    "page_unsupported": "這個面板沒有頁面（安全模式與備用面板都是）；這個功能要在一般的網頁面板裡用",
    "running": "執行中：{title}…",
    "tk_in_web": "這個面板裡的模組不能開 tkinter 的視窗（turtle、tkinter 的對話框都算）。"
                 "要用的話，請用安全模式開 iPLoT：python3 main.py --safe",
    "title": "iPLoT v{version}",
    "safe_mode": "（安全模式）",
    "syntax_error": "第 {line} 行：{message}",
    "create_failed": "無法在 {path} 建立模組：{message}。確認那個位置可以寫入，或換一個位置再按一次 ＋",
    "snapshot_failed": "無法存上一版：{message}。這次照常執行，只是沒有留下可以復原的上一版",
    "config_type": "{name} 的型別不對，應該是 {expected}",
    "bad_root": "ROOTS 裡的 {entry} 不是合法路徑（~ 後面要接 /）",
    "need_python": "iPLoT 需要 Python 3.10 以上（目前是 {found}）。請安裝 python.org 的版本。",
    "start_failed": "iPLoT 沒辦法啟動。技術細節記在 iPLoT 資料夾裡的 logs/iplot.log。可以試試：關掉這個視窗再開一次；"
                    "還是不行，就用安全模式開（在終端機進到 iPLoT 資料夾，打 python3 main.py --safe），"
                    "或把 logs/iplot.log 拿給幫你的人看。",
    "os_EACCES": "沒有權限",
    "os_EPERM": "沒有權限",
    "os_ENOSPC": "磁碟滿了",
    "os_EROFS": "這個位置是唯讀的",
    "os_ENOTDIR": "路徑裡有一段不是資料夾",
    "os_ENAMETOOLONG": "名稱太長",
    "os_ENOENT": "找不到檔案或資料夾",
    "os_other": "系統拒絕了這個動作，可以再試一次；還是不行就看 logs/iplot.log",
    "allow_roles": "『{title}』是從工作坊裝來的，它想提供這些功能：{roles}。\n允許的話，iPLoT 需要這些功能時會執行它的程式"
                   "（不用等你按它）。要允許嗎？\n不允許也沒關係：它照樣是一顆按鈕，下次啟動會再問。",
    "no_system": "沒有『{module}』模組，無法執行 {name}。要有這個功能，在 modules/ 新增一個叫『{module}』的模組"
                 "並定義 {name}(app, …)；見 docs/07_接口與邊界.md",
}

# 隨附的模組（核心的包帶的）：「更新」之後跟著換成新版的就是這些（D156）。0.9 跟著隨附同步一起搬進「更新」。
# 「整理」模組有一份一樣的（不讓人在面板上改名或刪除，D155）；tests/test_modify.py 對照 git 的內容，兩份多一個、少一個都會紅
BUNDLED = frozenset({"主控面板", "互通", "作業系統", "回報與討論", "工作坊", "打開核心原始碼", "更新", "行事曆", "重新啟動",
                     "開Terminal", "開工", "整理", "導覽列"})
# 碰作業系統的事（打開、編輯、顯示、終端機、垃圾桶）由 modules/ 裡叫這個名字的模組做（D50、D52）
SYSTEM_MODULE = "作業系統"
# 錯誤那一列的「回報這個問題」交給 modules/ 裡叫這個名字的模組的 on_error(app, error)（D110）
REPORT_MODULE = "回報與討論"

TEMPLATE = '''"""一句話說明這個模組做什麼。"""
# 規則在 iPLoT 資料夾的 AGENTS.md（給 AI 助手：改這個檔之前先讀它）。重點：只透過 app 碰 iPLoT，不 import core；
# 要別的模組的功能用角色（app.call），用到的角色或模組寫在 NEEDS；第三方套件包在 try 裡、或在頂層寫 REQUIRES = [...] 自己裝
# TITLE = "顯示名稱"   # 要讓按鈕文字跟資料夾名稱不同時才打開這一行
# ICON = "🧩"   # 按鈕的圖示：一個 emoji；或在資料夾放 icon.png

# run 可省略：沒有 run 時，最外層程式碼就是按下的動作（input()、print() 照常用）
def run(app):
    """按下按鈕時執行。app 的用法見 docs/api.md"""
    app.log(f"{app.module.title} 執行了")

# def on_files(app, paths):
#     """把檔案拖到按鈕上、或右鍵「選擇檔案後執行…」時執行。paths 是 Path 的清單"""
#     for p in paths:
#         app.log(f"收到 {p.name}")
'''
