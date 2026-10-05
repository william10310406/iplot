"""所有畫面文字，與新模組範本。要換語言只換這個檔。"""

# main.py 的版本防線之前就會 import 這個檔：型別註記不能在舊版 Python 求值（D46）
from __future__ import annotations

T: dict[str, str] = {
    "here": "這一層",
    "parent": "上一層",
    "empty_group": "尚無模組，按 ＋ 新增",
    "root_missing": "找不到 {path}",
    "root_unreadable": "讀不到 {path}",
    "done": "{title} 完成（{seconds:.1f} 秒）",
    "error_at_line": "模組『{module}』第 {line} 行出錯：{kind}，{message}",
    "error_no_line": "模組『{module}』出錯：{kind}，{message}",
    "core_error": "核心錯誤：{kind}，{message}。詳細內容在 logs/iplot.log",
    "config_error": "config.py 壞了，已用預設值啟動：{message}",
    "missing_handler": "iplot.py 沒有定義 {handler}(app)",
    "module_exit": "模組以 exit({code}) 結束",
    "input_cancelled": "在提問時按了取消",
    "not_found": "找不到模組『{name}』",
    "ambiguous": "有兩個以上的模組叫『{name}』：{paths}",
    "bad_name": "名稱不能是空白、以 . 開頭、結尾是 . 或空白、含 / \\ : * ? \" < > |，"
                "也不能是 CON、NUL 這類 Windows 保留字（模組要能複製到任何系統）",
    "already_exists": "『{name}』已經是模組了",
    "ask_name": "新模組的名稱",
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
    "ok": "確定",
    "cancel": "取消",
    "scanned": "已掃描 {roots}，找到 {count} 個模組",
    "list_sep": "、",
    "icon_unusable": "『{title}』的圖示檔讀不到或超過 1 MB，先用預設圖示",
    "installing": "第一次啟動：正在安裝介面（需要網路，約 {size}）…",
    "install_done": "安裝完成，重新啟動中…",
    "install_failed": "介面安裝失敗：{message}\n安裝需要網路。再試一次：重新啟動 iPLoT。先用安全模式：python3 main.py --safe",
    "no_tk": "這個 Python 沒有 tkinter，安全模式開不了；請用 python.org 的版本",
    "web_failed": "網頁面板開不起來：{message}。已改用安全模式",
    "title": "iPLoT v{version}",
    "safe_mode": "（安全模式）",
    "syntax_error": "第 {line} 行：{message}",
    "create_failed": "無法在 {path} 建立模組：{message}",
    "snapshot_failed": "無法存上一版：{message}",
    "config_type": "{name} 的型別不對，應該是 {expected}",
    "bad_root": "ROOTS 裡的 {entry} 不是合法路徑（~ 後面要接 /）",
    "need_python": "iPLoT 需要 Python 3.10 以上（目前是 {found}）。請安裝 python.org 的版本。",
    "no_system": "沒有『{module}』模組，無法執行 {name}。要有這個功能，在 modules/ 新增一個叫『{module}』的模組"
                 "並定義 {name}(app, …)；見 docs/07_接口與邊界.md",
}

# 碰作業系統的事（打開、編輯、顯示、終端機、垃圾桶）由 modules/ 裡叫這個名字的模組做（D50、D52）
SYSTEM_MODULE = "作業系統"

TEMPLATE = '''"""一句話說明這個模組做什麼。"""
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
