# Changelog

本檔案記錄 iPLoT 每個版本的變更，格式依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號依 [語意化版本](https://semver.org/lang/zh-TW/)。`app.api_version` 另外計算，見 `docs/api.md`。

## [Unreleased]

## [0.3.0] - 2026-10-05

M1.4「接口與邊界」：碰作業系統的事（打開、編輯、在資料夾中顯示、開終端機、搬到垃圾桶）從核心搬到隨附模組 `modules/作業系統`，macOS、Windows、Linux 各一個檔；核心零作業系統程式碼（D50）。`app` 多三個動作，`api_version` 仍是 1。

**與 0.2.1 相容：既有模組不用改，`api_version` 仍是 1。從 0.2.1 更新：換掉 `core/`、`main.py`，並把 `modules/作業系統/` 複製進 `modules/`；其他不動。** 沒有複製 `modules/作業系統/` 的話，打開檔案、右鍵三項、按 ＋ 之後開編輯器都不會動作，訊息區會說為什麼。

**Windows 未經實機驗證。Linux 只由測試驗過參數，沒有在真的 Linux 桌面上跑過。CI 設了 macOS、Windows、Ubuntu 三個平台，但這個 repo 沒有遠端，CI 一次都沒有跑過。**

量出來的數字：測試 162 → 206 個；核心邏輯 482 → 479 有效行（上限 500），`ui.py` 117（上限 150）；`core/` 13 → 12 個檔。

### 新增
- `app.reveal(path)`（在檔案總管裡顯示並選取）、`app.terminal(path)`（在終端機打開這個資料夾）、`app.trash(path)`（搬到系統垃圾桶，回傳搬到哪裡；Windows 的資源回收筒沒有路徑，回 `None`）。
- 隨附模組 `modules/作業系統`：`iplot.py` 是選擇器，`mac.py`、`win.py`、`linux.py` 各自實作 `open`、`edit`、`reveal`、`terminal`、`trash` 五個函式。按它的按鈕，訊息區說現在用的是哪一個檔。要改「終端機開哪個程式」這類行為，改這個模組，不用動核心。
- `Core.action(name, *args)`：核心把作業系統的動作交給那個模組；`Core.press` 多一個 `quiet` 參數（不印「完成」那一行）；`Result.value` 帶回處理函式的回傳值。
- 啟動器 `iPLoT.bat`（Windows，未經實機驗證）、`iPLoT.sh`（Linux，沒有在真的桌面上跑過）。
- `tests/smoke.py`：三個平台同一個檔的啟動測試。CI 設了三個平台（沒跑過）。
- `docs/07_接口與邊界.md`：可以換零件的地方、各自的規則與擋住規則的測試；怎麼改、怎麼加一個作業系統、怎麼加一個動作。

### 變更
- `app.open`、`app.edit`、右鍵選單三項、錯誤訊息的「打開檔案」、按 ＋ 之後打開編輯器，改由 `modules/作業系統` 執行。沒有那個模組時訊息區記一行、動作不執行，其他功能不受影響。
- 這些動作啟動外部程式之後不再等它結束。動作失敗時（例如系統上沒有那個程式），錯誤顯示在面板上、記在「作業系統」模組名下；呼叫 `app.open` 的模組不會收到例外。
- 右鍵標籤改成不分作業系統的說法：「在 Finder 顯示」→「在資料夾中顯示」、「在 Terminal 打開」→「在終端機打開」（D55）。
- 模組名稱規則收緊，三個平台都擋同一套（D54）。新擋的：結尾是 `.` 或空白；含 `\ : * ? " < > |` 或控制字元；Windows 保留字 `CON`、`PRN`、`AUX`、`NUL`、`COM1`–`COM9`、`LPT1`–`LPT9`（不分大小寫，後面接副檔名如 `nul.txt` 也算）。原本就擋的照舊：空白、含 `/`、以 `.` 開頭。已經存在的模組不受影響。
- 隨附的「開工」「開Terminal」改用 `app.terminal`，不再自己呼叫 macOS 的 `open`。

### 移除
- `core/actions.py`（內容搬到 `modules/作業系統/mac.py`；推翻 D10）與 `tests/test_actions.py`。
- `tests/smoke.sh`（改成 `tests/smoke.py`）。

### 文件
- 規格 v1.2（`docs/02_重構設計.md`）；D50–D59（`docs/03_設計決定.md`）；`docs/api.md`、`README.md` 同步。
- `docs/06` 改名為 `06_架構說明與試用.md`，改寫成給一般讀者的說明。
- 新增 `docs/07_接口與邊界.md`。

## [0.2.1] - 2026-10-03

M1.3「修補」：把 0.2.0 腳本語意裡兩處不像 `python3 iplot.py` 的地方改對（D49）。`app.*` 沒有變，`api_version` 仍是 1。

**與 0.2.0 不相容：按取消的模組現在會以 EOFError 停止；`exit()` 不再顯示錯誤。**

### 變更
- `input()` 的對話框按取消，現在丟 `EOFError`（訊息「在提問時按了取消」），就像真的 `input()` 遇到 Ctrl-D；0.2.0 是回空字串、模組繼續跑。不接的話模組停在那一行，面板顯示「模組『X』第 N 行出錯：EOFError，在提問時按了取消」；模組可以自己 `except EOFError`。`app.ask` 不變，按取消照舊回 `None`。
- `exit()` / `sys.exit(0)` / `quit()` 現在是正常結束，不再顯示錯誤；0.2.0 一律算錯誤（「模組呼叫了 exit()，已忽略」）。代碼非零（`exit(1)`、`sys.exit("壞了")`）仍是錯誤，訊息改為「模組以 exit(1) 結束」。

### 修正
- `while True:` 裡 `int(input())` 配 `except ValueError` 這種課本的驗證迴圈，按取消不再出不去（0.2.0 只能強制結束 iPLoT）。迴圈裡寫 `except:` 或 `except Exception:`（什麼都接）的仍然出不去，見規格 §7 已知限制。

### 文件
- 規格 §5.2、§7（第 4 條、腳本語意表；拿掉「驗證迴圈出不去」的已知限制）、§10、§12、`docs/api.md` 同步；D49；D47 的「老闆裁定」更正為研究助理裁定。

## [0.2.0] - 2026-10-03

M1.2「腳本語意」：課本寫的 Python 腳本不改一行就能當模組。按下按鈕 ＝ 在模組自己的資料夾裡執行 `python3 iplot.py`，只是鍵盤和螢幕換成了視窗（D47）。模組合約只放寬，`api_version` 仍是 1；既有模組照舊能跑，要注意的兩點見「變更」。

### 新增
- `input()` 跳對話框（等同 `app.ask`），不再凍住視窗；上次問完之後 `print` 的東西放在提示前面；按取消得到空字串，模組繼續跑。模組 import 的 helper 裡的 `input()` 也一樣。
- `def run(app)` 可省略：沒有 `run` 時最外層程式碼就是按下的動作。`if __name__ == "__main__":` 底下的會跑。
- 執行期間工作目錄是模組自己的資料夾（`open("x.txt")` 讀寫模組資料夾）、`import helper` 找旁邊的 `helper.py`（子資料夾裡的也算）而且改了下次會重讀、`sys.argv` 是 `[iplot.py 的路徑]`；跑完（含出錯、含 `exit()`）全部還原。

### 變更
- 既有模組裡的 `if __name__ == "__main__":` 區塊現在會在按下時執行（先最外層、再 `run(app)`）；以前 `__name__` 是資料夾名稱，那一段不會跑。
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
[0.3.0]: https://github.com/
[0.2.1]: https://github.com/
[0.2.0]: https://github.com/
[0.1.1]: https://github.com/
[0.1.0]: https://github.com/
