# Changelog

本檔案記錄 iPLoT 每個版本的變更，格式依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號依 [語意化版本](https://semver.org/lang/zh-TW/)。`app.api_version` 另外計算，見 `docs/api.md`。

## [Unreleased]

## [0.2.0] - 2026-10-03

M1.2「腳本語意」：課本寫的 Python 腳本不改一行就能當模組。按下按鈕 ＝ 在模組自己的資料夾裡執行 `python3 iplot.py`，只是鍵盤和螢幕換成了視窗（D47）。模組合約只放寬、往後相容：既有模組不用改，`api_version` 仍是 1。

### 新增
- `input()` 跳對話框（等同 `app.ask`），不再凍住視窗；按取消得到空字串，模組繼續跑。模組 import 的 helper 裡的 `input()` 也一樣。
- `def run(app)` 可省略：沒有 `run` 時最外層程式碼就是按下的動作。`if __name__ == "__main__":` 底下的會跑。
- 執行期間工作目錄是模組自己的資料夾（`open("x.txt")` 讀寫模組資料夾）、`import helper` 找旁邊的 `helper.py` 而且改了下次會重讀、`sys.argv` 是 `[iplot.py 的路徑]`；跑完（含出錯、含 `exit()`）全部還原。

### 變更
- 模組執行期間的工作目錄從「iPLoT 啟動時的那個」變成模組自己的資料夾；用相對路徑讀 iPLoT 資料夾的模組請改用 `app.home`。執行期間不寫 `.pyc`。
- 拖放／「選擇檔案後執行」指定 `on_files` 而模組沒定義，仍是錯誤（`MissingHandler`）；只有缺 `run` 不再是錯誤。
- 核心邏輯行數上限 450 → 500（D48）。

### 修正
- 隨附的「重新啟動」在 `execv` 前先回 iPLoT 資料夾，新的 iPLoT 不會以模組資料夾當工作目錄起來。

### 文件
- 規格 §7 加「腳本語意」與已知限制（`time.sleep`、長迴圈會凍住視窗，M2 用背景執行緒）；§3、§5.1、§5.2、§6.3、§10、附錄 A、`docs/api.md`、`README.md` 同步；新增 `docs/05_使用紀錄.md`。

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
[0.2.0]: https://github.com/
[0.1.1]: https://github.com/
[0.1.0]: https://github.com/
