# Changelog

本檔案記錄 iPLoT 每個版本的變更，格式依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號依 [語意化版本](https://semver.org/lang/zh-TW/)。`app.api_version` 另外計算，見 `docs/api.md`。

## [Unreleased]

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
[0.1.0]: https://github.com/
