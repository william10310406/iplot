"""所有畫面文字，與新模組範本。要換語言只換這個檔。"""

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
    "module_exit": "模組呼叫了 exit()，已忽略",
    "not_found": "找不到模組『{name}』",
    "ambiguous": "有兩個以上的模組叫『{name}』：{paths}",
    "bad_name": "名稱不能是空白、含 /、或以 . 開頭",
    "already_exists": "『{name}』已經是模組了",
    "ask_name": "新模組的名稱",
    "open_file": "打開檔案",
    "menu_edit": "打開程式碼",
    "menu_reveal": "在 Finder 顯示",
    "menu_terminal": "在 Terminal 打開",
    "title": "iPLoT v{version}",
    "safe_mode": "（安全模式）",
    "syntax_error": "第 {line} 行：{message}",
    "create_failed": "無法在 {path} 建立模組：{message}",
    "snapshot_failed": "無法存上一版：{message}",
    "config_type": "{name} 的型別不對，應該是 {expected}",
    "bad_root": "ROOTS 裡的 {entry} 不是合法路徑（~ 後面要接 /）",
}

TEMPLATE = '''"""一句話說明這個模組做什麼。"""
# TITLE = "顯示名稱"   # 要讓按鈕文字跟資料夾名稱不同時才打開這一行

def run(app):
    """按下按鈕時執行。app 的用法見 docs/api.md"""
    app.log(f"{app.module.title} 執行了")

# def on_files(app, paths):
#     """把檔案拖到按鈕上、或右鍵「選擇檔案後執行…」時執行。paths 是 Path 的清單"""
#     for p in paths:
#         app.log(f"收到 {p.name}")
'''
