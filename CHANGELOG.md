# Changelog

本檔案記錄 iPLoT 每個版本的變更，格式依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號依 [語意化版本](https://semver.org/lang/zh-TW/)。`app.api_version` 另外計算，見 `docs/api.md`。

## [Unreleased]

## [0.1.1] - 2026-10-03

M1.1「修補」：把 M1 最終審查留下的三個洞補上——「怎麼改壞都能啟動並說哪裡壞」在 `logs/`、`EDITOR`、Python 版本三處的缺口。不加功能、不改介面，`api_version` 仍是 1。

### 修正
- `logs/` 建不了或寫不了（剛好是個檔案、或 iPLoT 放在唯讀位置）不再擋啟動；核心錯誤照樣進面板，記錄檔寫不了就只進面板（D45）。
- `config.py` 的 `EDITOR = []`／`EDITOR = ()` 視為型別錯誤：用預設值啟動並報告「EDITOR 的型別不對」，而不是等到打開檔案時才在面板上冒出一個核心錯誤（IndexError）。
- `main.py` 在 import 核心之前先檢查 Python 版本，3.10 以下在 stderr 印一句「iPLoT 需要 Python 3.10 以上（目前是 …）」就退出，不再是一段 TypeError traceback（D46）。

### 文件
- 規格 §4.1（`requirements-dev.txt` 含 pytest-cov）、§8.2（面板圖對齊實作：麵包屑是一排按鈕、⚠ 在按鈕文字前、訊息區先 traceback 再白話那一句）、§8.4（自動啟動標 M2，D39）對齊實作。

## [0.1.0] - 2026-10-02

M1「種子」：取代原版 `iPLoT.py` + `iPLoT.txt` 的全新實作，`api_version = 1`。

### 新增
- 三層掃描：資料夾裡有 `iplot.py` 就是模組（`modules/`、上一層、`config.py` 的 `ROOTS`，模組裡還可以有模組）。只用 `ast` 靜態讀取，不執行任何模組程式碼；語法錯誤的模組照樣列出並標 ⚠。
- 面板：單一視窗、麵包屑、每組一顆 ＋、顏色按層、可捲動；左鍵執行、右鍵「打開程式碼／在 Finder 顯示／在 Terminal 打開」；視窗取得焦點就重掃。
- 執行：每次按下都在乾淨的命名空間重新執行 `iplot.py`，`print()` 的輸出進訊息區；例外與 `exit()` 都變成面板上的一句話，附檔案、行號與「打開檔案」。
- `app` 介面 v1：`module`、`home`、`modules`、`memory`、`window`、`log`、`open`、`edit`、`run`、`rescan`、`ask`、`choose_files`、`choose_folder`。
- 滑鼠新增模組：＋ → 名字 → 編輯器打開範本；既有資料夾可以直接變成模組。
- 快照：每次執行前把 `iplot.py` 存進模組自己的 `.history/`（去重、保留 `HISTORY_KEEP` 份）；復原的底層函式已就位，右鍵 UI 在 M2。
- `config.py`（`ROOTS`、`EDITOR`、`HISTORY_KEEP`）：壞了或型別不對就用預設值啟動並顯示哪裡壞。
- `--safe`：只掃 `modules/`、不載入拖放套件。核心自己的錯誤進面板並寫 `logs/iplot.log`。
- 隨附模組：開工、打開核心原始碼、開Terminal、重新啟動。
- `iPLoT.command` 雙擊啟動；`tests/smoke.sh` 從零啟動情境 1–6；CI（macOS，Python 3.10 與 3.12）跑 ruff、pytest（含覆蓋率）、smoke。

### 原版
- 老闆的 `iPLoT.py`／`iPLoT.txt` 存檔在 `docs/original/`，tag `v0.0-original`。原版 `X/X.txt` 模組的匯入工具在 M2。

[Unreleased]: https://github.com/
[0.1.1]: https://github.com/
[0.1.0]: https://github.com/
