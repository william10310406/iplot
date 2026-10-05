# Changelog

本檔案記錄 iPLoT 每個版本的變更，格式依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號依 [語意化版本](https://semver.org/lang/zh-TW/)。`app.api_version` 另外計算，見 `docs/api.md`。

## [Unreleased]

## [0.4.0] - 2026-10-05

M2「圖示面板」：面板從 tkinter 的按鈕清單換成 pywebview 視窗裡的網頁面板（D61、D63）——分組的圖示格，單擊選取、雙擊執行（D64），每個模組有自己的圖示（D65）。網頁面板要用的套件在第一次啟動時自動裝進 iPLoT 自己的 `lib/`（D62）。`app.window` 拿掉，`api_version` 1 → 2（D66）。

**與 0.3.0 不完全相容：`app.window` 沒有了，用到它的模組要改；網頁面板下模組也不能再靠 tkinter 自己開視窗（D63）；其餘模組不用改。從 0.3.0 更新：換掉 `core/`、`main.py`，新增 `ui/`、`requirements/`，並把 `modules/作業系統/` 換成新的；`config.py` 與自己的模組不動。更新後第一次啟動會下載介面，要網路，而且這個 Python 要有 pip。** 隨附模組沒有用到 `app.window`。`core/ui.py` 沒有了（搬到 `ui/tk.py`），所以 `core/` 是整個換掉。沒有換 `modules/作業系統/` 的話，第一次啟動問不到要裝哪一份套件，網頁面板裝不起來，會改開安全模式。其他隨附模組只多了一行 `ICON`，不換也能用。下載或安裝失敗時，主控台說明原因（不是 traceback），接著自動改開安全模式；之後重新啟動 iPLoT 會再裝一次。

**網頁面板只在 macOS 實際開過，而且只有一台機器（macOS 26.5、arm64、python.org 的 Python 3.14.7）。Windows 未經實機驗證：`requirements/web-win.txt` 的版本是 pip 解出來的，沒有在 Windows 裝過。Linux 這一版沒有網頁面板，只能用安全模式（`python3 main.py --safe`），而且沒有在真的 Linux 桌面上跑過。CI 設了 macOS、Windows、Ubuntu 三個平台，但這個 repo 沒有遠端，CI 一次都沒有跑過。**

量出來的數字：測試 210 → 323 個；核心邏輯 479 → 490 有效行（上限 500）；`core/` 12 → 11 個檔。預算從兩項變成七項（D68），有效行／上限：核心邏輯 490/500、`ui/web.py` 194/200、`ui/tk.py` 118/180、`ui/install.py` 49/80、`ui/index.html` 30/120、`ui/app.js` 256/400、`ui/style.css` 126/300。安裝與啟動只在上面那一台機器量過：`lib/` 裝完 36 MB、10 個套件；乾淨下載安裝 1 分 46 秒（看網路）；`lib/` 在的時候，啟動到視窗出現 0.6 秒。

這一版沒有做：把檔案拖到圖示上（拖放）；Linux 的網頁面板；中途停掉執行中的模組（執行模型 D56 仍延後）；套件的 hash 釘死（現在只釘版本）。D69、D70（更新核心、下載模組）這一版只定了原則，沒有程式。

### 新增
- 網頁面板（`ui/web.py`、`ui/index.html`、`ui/app.js`、`ui/style.css`）：頁面在 pywebview（6.2.1）開的原生視窗裡跑，零外部資源、不用框架、不用 build；用 `file://` 載入，沒有 HTTP server、沒有 port。上方是麵包屑（按任一段回去），中間是可捲動的分組圖示格，下方是狀態列與訊息區；視窗拉寬，格子自動多排幾格；深色模式跟系統。
- 每個模組一格：圖示、名稱（最多兩行）、右上角紅點（檔案有語法錯誤）、右下角 ▸（有子模組，按了進去）。每組標題前面有顏色點（這一層藍、上一層紅、`ROOTS` 加的綠、進到下一層之後紫），後面是路徑。右鍵選單六項：執行／進入下一層（有子模組才出現）／打開程式碼／在資料夾中顯示／在終端機打開／在這裡新增下一層模組…。
- 面板內的對話框：`app.ask`、模組的 `input()`、`app.confirm`、新模組取名都用它；Enter 確定、Esc 取消，中文輸入法選字時按的 Enter 不算確定。取名時名字不合規則，原因直接顯示在對話框裡，對話框不關。
- 模組在面板的單一工作執行緒上執行，一次一個：跑很久時視窗不會凍住，可以捲訊息區；執行中再執行別的模組會排隊；不能中途停掉。
- 訊息區最多留 2000 條，文字可以選取複製。
- 「執行中」：模組開始執行超過四分之一秒，狀態列右邊顯示「執行中：<名稱>…」，跑完就消失。模組的 `print()` 要等它結束才進訊息區，這一行讓人看得出它還在跑。
- 雙擊要兩下都落在同一個模組上才算：第一下按的是 ▸、選單、對話框的按鈕時，畫面會換，第二下落在哪裡都不會執行東西。
- 模組裡用 tkinter 開視窗（`turtle` 也是）：網頁面板開著的時候，`import tkinter` 會得到一句錯誤，說要用安全模式開 iPLoT。不擋的話，整個 iPLoT 會被 macOS 直接中止、沒有任何訊息（實測）。這類模組在安全模式照常能跑。
- 視窗關掉之後，排著還沒做的工作不再做。
- 圖示（D65）：模組資料夾裡的 `icon.png` 或 `icon.svg`（1 MB 以內）→ `iplot.py` 頂層的 `ICON = "🧩"` → 都沒有就用名字第一個字，底色由資料夾名稱算出來。圖檔是空的、超過 1 MB、讀不到，或內容不是一張讀得出來的圖，就當作沒有，訊息區記一行。`ModuleInfo` 多 `icon`、`icon_file` 兩欄；新模組的範本多一行註解掉的 `ICON`；隨附模組各加了 `ICON`（開工 🧭、打開核心原始碼 🧬、開Terminal ⌨️、重新啟動 🔄、作業系統 🖥️）。圖示只在網頁面板顯示。
- `app.confirm(prompt)`：跳出「確定／取消」對話框，按確定回 `True`。`View` 對應多一個 `confirm`，現在七個方法：`show`、`log`、`report`、`ask`、`confirm`、`choose_files`、`choose_folder`。
- 第一次啟動自動安裝（D62）：網頁面板開不起來（`lib/` 裡還沒有 pywebview）時，`ui/install.py` 用 `python -m pip install --target lib` 把 `requirements/` 裡釘死版本的套件裝進 iPLoT 自己的 `lib/`，不碰系統的 Python；pip 的輸出一行行印在主控台，裝好就自動重新啟動。需求檔兩份：`requirements/web-mac.txt`、`requirements/web-win.txt`（未經實機驗證）；兩個檔只寫 ASCII，因為舊版 pip 用系統的編碼讀它，在中文 Windows 上遇到中文註解會讀不進來。`lib/` 不進版本控制，`lib/.installed` 記著裝的是哪一份需求檔。把 iPLoT 資料夾丟進垃圾桶，裝的東西跟著一起移除。
- 安全模式自動後備：這個平台沒有網頁面板、缺前置條件、pip 失敗，或裝完重啟還是開不起來時，主控台印出原因，然後自動改開 tkinter 面板的安全模式，同一句原因寫在訊息區。只重裝一次，不會無限重啟。連 tkinter 都沒有時印一句話、以代碼 1 結束。
- 「作業系統」模組多兩個函式（三個後端簽名一致，現在各七個）：`requirements(app)` 回要裝哪一份需求檔（Linux 回空字串，表示這個平台沒有網頁面板）；`webview_ready(app)` 回缺什麼前置條件，不缺回 `None`（Windows 查有沒有 WebView2 runtime，未經實機驗證）。「裝哪一份、缺什麼」跟其他作業系統的事一樣，改這個模組就能換。
- `custom.css`：在 iPLoT 資料夾（跟 `config.py` 同一層）放這個檔就能覆寫外觀；它在 `ui/style.css` 之後載入，不存在也沒關係，而且不在 `ui/` 裡，換新版的 `ui/` 不會蓋掉它。`style.css` 開頭是顏色與尺寸的變數，其餘規則只用變數。
- `core/text.py` 多 18 個文字 key：`menu_run`、`menu_enter`、`add_tile`、`status_hint`、`details`、`hide_details`、`ok`、`cancel`、`scanned`、`list_sep`、`icon_unusable`、`installing`、`install_done`、`install_failed`、`no_tk`、`web_failed`、`running`、`tk_in_web`。畫面文字在啟動時整份送進頁面，`ui/app.js` 的程式碼裡沒有中文字串。
- 測試：新檔 `tests/test_web.py`（44 個測試函式，用假的視窗，不需要顯示器）、`tests/test_install.py`（14 個測試函式，用假的 pip，不連網）；`tests/test_main.py` 3 → 21 個（啟動流程：安全模式、安裝、重啟、後備，不真的跑 pip、不開視窗）。`tests/test_boundaries.py` 3 → 12 個，新釘住的邊界：`core/` 不 import `webview`；`core/`（`text.py` 除外）、`ui/*.py`、`main.py` 不寫中文字串常數（D32 以前沒有測試）；`ui/` 的 HTML／CSS／JS 沒有外部網址；`app.js` 註解以外沒有中文、用到的文字 key 都存在、呼叫的剛好是 `Bridge` 的方法、Python 會呼叫的入口都有定義；`index.html` 依序載入 `style.css`、`custom.css`、`app.js`；`style.css` 的顏色都在開頭的變數裡。前端的行為在 repo 裡沒有自動測試，靠人工驗收。

### 變更
- 執行模組的操作（D64，推翻 D13）：網頁面板單擊是選取（狀態列顯示名稱與說明；檔案有語法錯誤的模組顯示錯誤），雙擊才執行，右鍵選單第一項也是「執行」。只在網頁面板；安全模式的 tkinter 面板照舊單擊執行、右鍵四項。
- ＋ 的位置：網頁面板每組最後一格是虛線的 ＋（根目錄讀不到的那一組沒有）；以前在每組標題右邊，tkinter 面板照舊。
- 錯誤訊息的排法：網頁面板先顯示白話那一句，右邊是「打開檔案」（用編輯器打開出錯的檔案；`config.py` 的 `EDITOR` 設成認得行號的編輯器時，會跳到出錯的那一行）與「詳細」（展開 traceback，再按一次收起）；以前是先整段 traceback、最後才是白話那一句，tkinter 面板照舊。
- 需求：從「python.org 的 Python（內含 tkinter），不用安裝任何套件」變成「Python ≥ 3.10 加 pip，第一次啟動要網路」；不必是 python.org 的（Homebrew 的照理也行，但實測只跑過 python.org 的）。tkinter 不再是必要的，只有安全模式與後備需要它。
- `core/ui.py` 搬到 `ui/tk.py`：tkinter 面板現在只以安全模式出現（`python3 main.py --safe`，或網頁面板開不起來時自動退到它），標題有「（安全模式）」、只掃 `modules/`。所以在 Linux 上，以及網頁面板裝不起來的時候，上一層與 `ROOTS` 的模組不會出現在面板上。
- 「視窗取得焦點就重掃」照舊（D11）；網頁面板改由頁面的 `focus` 事件觸發，內容沒變就不重畫。
- `app.choose_files`、`app.choose_folder` 在網頁面板開的是 pywebview 的原生選擇視窗（D67）。
- 預算從兩項改成七項（D68，修訂 D48）：核心邏輯 ≤ 500 不變；`ui.py` ≤ 150 換成 `ui/` 六個檔各自的上限（見上面的數字）。HTML／CSS／JS 的有效行＝非空白、非整行註解。
- `tests/smoke.py` 從六個情境變七個：前六個改走 `--safe`；第七個是預設啟動（網頁面板），只在 macOS 而且 `lib/` 已經裝好時才跑。每個情境除了 stderr，stdout 也要是空的：網頁面板開不起來、改開安全模式時 iPLoT 會在 stdout 說明，這樣第七個情境才分得出「開的是網頁面板」還是「退到了安全模式」。
- `tests/test_ui_smoke.py` 改名 `tests/test_tk_smoke.py`；coverage 略過的範圍從 `core/ui.py` 改成 `ui/*`。
- 全專案的 `except Exception` 從兩處變三處：多了 `ui/web.py` 的工作執行緒迴圈——一件工作出錯，回報之後面板繼續做下一件。

### 移除
- `app.window`（D66）與 `View.window`：沒有 tkinter 主視窗了。模組不能再靠它畫自己的介面；模組自己的畫面是之後的事，這一版沒有替代的做法。
- `core/ui.py`（搬到 `ui/tk.py`）。

### 文件
- 規格 v2.0（`docs/02_重構設計.md`）；D61–D70（`docs/03_設計決定.md`；D13 被 D64 推翻，D48 由 D68 修訂）；`docs/06_架構說明與試用.md`、`docs/07_接口與邊界.md`、`docs/api.md`、`README.md` 同步。
- 這一版的設計與實作計畫在 `docs/plans/`。

## [0.3.0] - 2026-10-05

M1.4「接口與邊界」：碰作業系統的事（打開、編輯、在資料夾中顯示、開終端機、搬到垃圾桶）從核心搬到隨附模組 `modules/作業系統`，macOS、Windows、Linux 各一個檔；核心零作業系統程式碼（D50）。`app` 多三個動作，`api_version` 仍是 1。

**與 0.2.1 相容：既有模組不用改，`api_version` 仍是 1。從 0.2.1 更新：換掉 `core/`、`main.py`，並把 `modules/作業系統/` 複製進 `modules/`；其他不動。** 沒有複製 `modules/作業系統/` 的話，打開檔案、右鍵前三項、按 ＋ 或右鍵「在這裡新增下一層模組…」之後開編輯器都不會動作，訊息區會說為什麼。

**Windows 未經實機驗證。Linux 只由測試驗過參數，沒有在真的 Linux 桌面上跑過。CI 設了 macOS、Windows、Ubuntu 三個平台，但這個 repo 沒有遠端，CI 一次都沒有跑過。**

量出來的數字：測試 162 → 210 個；核心邏輯 482 → 479 有效行（上限 500），`ui.py` 117 → 118（上限 150）；`core/` 13 → 12 個檔。

### 新增
- `app.reveal(path)`（在檔案總管裡顯示並選取）、`app.terminal(path)`（在終端機打開這個資料夾）、`app.trash(path)`（搬到系統垃圾桶，回傳搬到哪裡；Windows 的資源回收筒沒有路徑，回 `None`）。
- 隨附模組 `modules/作業系統`：`iplot.py` 是選擇器，`mac.py`、`win.py`、`linux.py` 各自實作 `open`、`edit`、`reveal`、`terminal`、`trash` 五個函式。按它的按鈕，訊息區說現在用的是哪一個檔。要改「終端機開哪個程式」這類行為，改這個模組，不用動核心。
- `Core.action(name, *args)`：核心把作業系統的動作交給那個模組；`Core.press` 多一個 `quiet` 參數（不印「完成」那一行）；`Result.value` 帶回處理函式的回傳值。
- 右鍵選單多第四項「在這裡新增下一層模組…」：問名字，在那個模組的資料夾裡建一個模組，建好後跟按 ＋ 一樣重掃、打開編輯器。沒有子模組的模組沒有 ▸，進不去就按不到裡面的 ＋，以前它的第一個子模組只能到檔案總管自己建資料夾、放進 `iplot.py`；現在只用滑鼠就能做（D60）。
- 啟動器 `iPLoT.bat`（Windows，未經實機驗證）、`iPLoT.sh`（Linux，沒有在真的桌面上跑過）。
- `tests/smoke.py`：三個平台同一個檔的啟動測試。CI 設了三個平台（沒跑過）。
- `docs/07_接口與邊界.md`：可以換零件的地方、各自的規則與擋住規則的測試；怎麼改、怎麼加一個作業系統、怎麼加一個動作。

### 變更
- `app.open`、`app.edit`、右鍵選單原有的三項、錯誤訊息的「打開檔案」、按 ＋ 之後打開編輯器，改由 `modules/作業系統` 執行。沒有那個模組時訊息區記一行、動作不執行，其他功能不受影響。
- 這些動作啟動外部程式之後不再等它結束。動作失敗時（例如系統上沒有那個程式），錯誤顯示在面板上、記在「作業系統」模組名下；呼叫 `app.open` 的模組不會收到例外。
- 右鍵標籤改成不分作業系統的說法：「在 Finder 顯示」→「在資料夾中顯示」、「在 Terminal 打開」→「在終端機打開」（D55）。
- 模組名稱規則收緊，三個平台都擋同一套（D54）。新擋的：結尾是 `.` 或空白；含 `\ : * ? " < > |` 或控制字元；Windows 保留字 `CON`、`PRN`、`AUX`、`NUL`、`COM1`–`COM9`、`LPT1`–`LPT9`（不分大小寫，後面接副檔名如 `nul.txt` 也算）。原本就擋的照舊：空白、含 `/`、以 `.` 開頭。已經存在的模組不受影響。
- 隨附的「開工」「開Terminal」改用 `app.terminal`，不再自己呼叫 macOS 的 `open`。

### 移除
- `core/actions.py`（內容搬到 `modules/作業系統/mac.py`；推翻 D10）與 `tests/test_actions.py`。
- `tests/smoke.sh`（改成 `tests/smoke.py`）。

### 文件
- 規格 v1.2（`docs/02_重構設計.md`）；D50–D60（`docs/03_設計決定.md`）；`docs/api.md`、`README.md` 同步。
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
[0.4.0]: https://github.com/
[0.3.0]: https://github.com/
[0.2.1]: https://github.com/
[0.2.0]: https://github.com/
[0.1.1]: https://github.com/
[0.1.0]: https://github.com/
