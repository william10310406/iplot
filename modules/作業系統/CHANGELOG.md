# Changelog

「作業系統」這個模組的版本紀錄，格式跟 iPLoT 的 CHANGELOG.md 一樣（[Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)）。`tools/publish.py` 取最上面那一節的版本號當工作坊裡的版本，取那一節的第一段當清單頁上的「這一版」。

## [0.5.0] - 2026-10-05

`linux.py`、`win.py` 的 `webview_ready` 回的那一句改了：網頁面板開不起來時不再叫人用安全模式（iPLoT 會自己改用備用面板）。

### 變更
- `linux.py`：「這一版的網頁面板還不支援 Linux」。
- `win.py`：「找不到 WebView2 runtime：請先安裝 Microsoft Edge WebView2 Runtime（Windows 11 內建）」（未經實機驗證）。
