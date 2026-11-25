# `app`：模組看得到的全部

- `api_version = 7`。介面只加不減；要拿掉東西就升 `api_version` 並寫進 `CHANGELOG.md`。1 是第一版；2（核心 0.4.0）拿掉了 `app.window`——面板換成網頁面板之後，沒有 tkinter 主視窗可以交給模組了（D66）——同一版多了 `app.confirm`；3（核心 0.5.0）加了 `app.config`、`app.version`、`app.page`（D72），只加、沒有拿掉任何東西，照 2 寫的模組不用改；4（核心 0.7.0）加了 `app.parent`、`app.children`（D152），一樣只加，照 3 寫的模組不用改；5（核心 0.8.0）加了 `app.call`、`app.each`、`app.providers`，`app` 上沒有的名字轉給提供 `app.<名字>` 的模組（D159），一樣只加；6（核心 0.9.0）每按一次另開一個程序跑模組，加了 `app.start` 與模組頂層的 `MIN_API`（D161），一樣只加；7（核心 1.0.0）加了 `app.top_modules`、`app.parent_of`、`app.children_of`、`app.panel`、`app.describe`，模組不用再 import 核心、不用猜自己在哪個面板（D164），還有 `app.restart`（D166），一樣只加。
- 每次執行都新建一個 `App` 傳給 `run(app)`（或 `on_files(app, paths)`）；`module` 與 `memory` 在建立時綁好。執行一次＝在面板上雙擊模組的圖示，或右鍵選「執行」；tkinter 面板是單擊按鈕。tkinter 面板在兩種時候出現：安全模式（`python3 main.py --safe`，只掃 `modules/`），以及網頁面板開不起來時的備用面板（照常掃上一層與 `ROOTS`，不是安全模式，D75）；下面說「tkinter 面板」就是指這兩種。下面說的「按下」都是指執行這一次。
- `def run(app)` 可省略：沒有 `run` 時最外層程式碼就是按下的動作，不用 `app` 也能寫模組（見最後一節）。
- 本表整理自 `modules/核心/core/app.py` 的 docstring；兩邊不一致時以 `modules/核心/core/app.py` 為準。

| 組 | 成員 | 說明 |
|---|---|---|
| 身分 | `app.module` → `ModuleInfo`（唯讀） | 正在執行的模組的資訊：name、title、folder、file 等（見附錄 B 的 ModuleInfo）。 |
| 身分 | `app.home` → `Path`（唯讀） | iPLoT 程式資料夾。 |
| 身分 | `app.modules` → `tuple[ModuleInfo, ...]`（唯讀） | 目前範圍內所有模組的唯讀清單。 |
| 身分 | `app.parent` → `ModuleInfo | None`（唯讀） | 這個模組的父層模組（資料夾上一層，不越過根目錄）；最上層的模組沒有，回 None。可以直接交給 `app.run`。 |
| 身分 | `app.children` → `tuple[ModuleInfo, ...]`（唯讀） | 這個模組的子模組，每次都重新看磁碟；跟面板進到下一層時看到的一樣。可以直接交給 `app.run`。 |
| 身分 | `app.top_modules()` → `tuple[ModuleInfo, ...]` | 每個根目錄最上層的模組，每次都重新看磁碟；不管面板現在停在哪一層（D164，`api_version` 7）。 |
| 身分 | `app.parent_of(info)` → `ModuleInfo | None` | 任何一個模組的父層，規則跟 `app.parent` 一樣；例如導覽列替開頁面的模組畫「上一層」（D164）。 |
| 身分 | `app.children_of(info)` → `tuple[ModuleInfo, ...]` | 任何一個模組的子模組，規則跟 `app.children` 一樣（D164）。 |
| 身分 | `app.panel` → `str | None`（唯讀） | 開這個模組的面板說它是哪一種（「網頁」「tkinter」）；不是從面板開的（`python3 main.py --run`）是 None。不要自己看 `sys.modules` 猜（AGENTS.md 第 4 條，D164）。 |
| 身分 | `app.config` → `Config`（唯讀） | config.py 讀出來的設定（唯讀）：roots、editor、history_keep、update_url、workshop_url。 |
| 身分 | `app.version` → `str` | 核心的版本字串（這一版是 `"0.8.0"`）。跟 `api_version` 一樣是類別屬性，說明寫在 `App` 的 docstring 裡。 |
| 狀態 | `app.memory` → `dict`（唯讀） | 這個模組自己的 dict，iPLoT 開著期間保留；跨次啟動要留的請寫成檔案放 module.folder。 |
| 動作 | `app.log(text: str)` → `None` | 寫一行到面板下方的訊息區。 |
| 動作 | `app.open(path: Path)` → `None` | 打開：資料夾用檔案總管、檔案用預設程式。由 modules/作業系統 執行。 |
| 動作 | `app.edit(path: Path, line: int | None = None)` → `None` | 用 config.py 的 EDITOR 打開檔案（None 時用系統預設文字編輯器）；資料夾改用 open。 |
| 動作 | `app.reveal(path: Path)` → `None` | 在檔案總管裡顯示並選取這個檔案或資料夾。 |
| 動作 | `app.terminal(path: Path)` → `None` | 在終端機打開這個資料夾。 |
| 動作 | `app.trash(path: Path)` → `Path | None` | 搬到系統垃圾桶，永遠不直接刪除；回傳搬到哪裡（Windows 的資源回收筒沒有路徑，回 None）。 |
| 動作 | `app.run(name: str | ModuleInfo)` → `Result` | 執行另一個模組：先找面板目前這一層，找不到再找最上層；同一處有兩個同名就丟 LookupError，不猜。 |
| 角色 | `app.call(role: str, *args)` → 回傳值或 `None` | 交給第一個提供 role 的模組（`PROVIDES` 宣告的），回它的回傳值；沒有提供者回 None（D159，核心 0.8.0）。 |
| 角色 | `app.each(role: str, *args)` → `list[tuple[ModuleInfo, 回傳值]]` | 交給每一個提供 role 的模組，依掃描順序；某一個壞了照常報錯，不影響其他的。 |
| 角色 | `app.providers(role: str)` → `tuple[ModuleInfo, ...]` | 提供 role 的模組，依掃描順序。 |
| 角色 | `app.<名字>(…)` | `app` 上沒有的名字：有模組提供 `app.<名字>` 這個角色，就交給它；沒有就是 AttributeError，所以 `hasattr(app, "x")` 看得出有沒有。 |
| 動作 | `app.start(name: str | ModuleInfo)` → `None` | 開始跑另一個模組，不等它：它在自己的程序裡跑，這邊馬上回來（D161，`api_version` 6）。要它的結果用 `app.run`。 |
| 動作 | `app.describe(error)` → `str` | 一筆錯誤（有 kind、message、file、line、source、module）的白話一句，跟面板訊息區說的一樣（D164）。 |
| 動作 | `app.restart()` → `None` | 請面板關掉、整個 iPLoT 從頭再來，啟動參數照舊（安全模式還是安全模式，D166）。不是面板開的（`python3 main.py --run`）丟 AttributeError。 |
| 動作 | `app.rescan()` → `None` | 重新掃描並重畫面板；在模組執行中呼叫時，會等這次執行結束後才做。 |
| 問人 | `app.ask(prompt: str, default: str = '')` → `str | None` | 跳出對話框問一個字串；按取消回 None。 |
| 問人 | `app.confirm(prompt: str)` → `bool` | 跳出對話框問「確定／取消」；按確定回 True。 |
| 問人 | `app.page(title: str, html: str, api: object | None = None)` → `None` | 開一個視窗顯示一頁 HTML，關掉才回來（只擋自己：模組在自己的程序裡跑，面板上別的模組照樣能按，D161）；api 的公開方法給那一頁的 JS 用 pywebview.api.<方法> 呼叫。tkinter 面板（安全模式與備用面板）沒有頁面，只在訊息區記一行。 |
| 問人 | `app.choose_files()` → `list[Path]` | 跳出檔案選擇視窗；按取消回空清單。 |
| 問人 | `app.choose_folder()` → `Path | None` | 跳出資料夾選擇視窗；按取消回 None。 |

## 幾個約定

- 模組在面板的工作執行緒上執行，一次一個；跑超過四分之一秒，狀態列會顯示「執行中：<名稱>…」。長時間工作（`time.sleep`、長迴圈）不會凍住視窗，執行中可以捲訊息區；但這段時間再執行別的模組（或同一個再執行一次）只會排隊，等前一個結束才輪到，執行中的模組也不能中途停掉。模組仍然在 iPLoT 自己的程序裡執行，關掉視窗會結束整個程序。`print` 的輸出等模組結束才整批進訊息區；`app.log` 是呼叫當下就寫進去，長時間工作要報進度用它。tkinter 面板沒有工作執行緒：模組在視窗的執行緒上執行，跑多久視窗就凍多久。
- 模組不能再靠 tkinter 開自己的視窗：`app.window` 拿掉了，而且主執行緒被面板的視窗系統佔著，模組是在另一條執行緒上執行的（D63 的代價）。在網頁面板上，模組一 `import tkinter`（`turtle` 也會）就得到一句錯誤：「這個面板裡的模組不能開 tkinter 的視窗…請用安全模式開 iPLoT：python3 main.py --safe」；在安全模式下這類模組照常能跑。模組要有自己的畫面，用 `app.page` 開一頁自己的網頁（下一點）。
- `app.page(title, html, api=None)`（D72）另外開一個視窗（開出來是 640×520）顯示 `html` 這一頁，那個視窗關掉 `app.page` 才回來，跟對話框一樣；頁面開著的期間模組停在這一行，所以這段時間再執行別的模組一樣只會排隊。`api` 是模組自己寫的一個普通物件：它的公開方法（名字不以底線開頭的）給那一頁的 JS 用 `pywebview.api.<方法>(…)` 呼叫，回傳的是 Promise，Python 那邊的回傳值在 `.then(…)` 裡拿到。頁面剛載入的那一刻 `pywebview.api` 還沒準備好：按鈕按下去才呼叫的不用管；一載入就要呼叫的，等頁面收到 `pywebviewready` 事件之後再呼叫。安全模式與備用的 tkinter 面板沒有頁面：`app.page` 只在訊息區記一行「這個面板沒有頁面（安全模式與備用面板都是）；這個功能要在一般的網頁面板裡用」就回來，不開視窗、不丟例外，`api` 的方法一個都不會被呼叫；有沒有開成，`app.page` 都是回 `None`。Linux 這一版沒有網頁面板，所以也沒有頁面。`app.page` 只在 macOS 的網頁面板上實際開過，Windows 未經實機驗證。隨附的「工作坊」就是用它做的（`modules/工作坊/` 的 `iplot.py`、`workshop.py` 裡的 `Api`、`page.html`），最小的例子在本頁最後。
- 寫 `app.page` 的頁面，有四件事要模組自己顧，核心不看 `html` 的內容、也不替模組做。一，`api` 物件自己的屬性，名字要以底線開頭（`self._n`、`self._app`）：pywebview 會把不以底線開頭的屬性一路攤開給頁面，寫成 `self.app = app` 的話，頁面的 JS 就呼叫得到 `pywebview.api.app.trash(…)`。二，頁面不載入外部資源：樣式與 JS 直接寫在那一頁裡，不放 `http://`、`https://` 的網址。三，外來的字（網路上抓的、檔案裡讀的、別人填的）要自己跳脫：在 Python 組 HTML 時用 `html.escape`，在 JS 裡用 `textContent`，不用 `innerHTML`。四，頁面開著的時候要問「確定／取消」，在那一頁自己問：`app.ask`、`app.confirm` 的對話框開在面板的主視窗、不在這一頁上，會被這一頁擋住（「工作坊」的「覆蓋」，與會蓋掉模組自己存的檔的「更新」，就是在清單的同一列再問一次）。
- 按下按鈕 ＝ 在模組自己的資料夾裡執行 `python3 iplot.py`：執行期間工作目錄是模組資料夾（`open("x.txt")` 讀寫的是模組資料夾裡的檔案）、`import helper` 找旁邊的 `helper.py`（改了下次會重讀）、`__name__` 是 `"__main__"`、`sys.argv` 是 `[iplot.py 的路徑]`；跑完全部還原。`app.module.folder / "x.txt"` 照樣可用。
- `input("提示")` 會跳對話框，等同 `app.ask("提示")`：對話框開在面板裡面（提示文字、一個輸入框、取消／確定兩顆鈕；Enter 確定、Esc 取消），tkinter 面板是另外跳出來的小對話框（tkinter 的）。上次問完之後 `print` 的東西會放在提示前面。按取消時 `input()` 丟 `EOFError`（就像真的 `input()` 遇到 Ctrl-D）：丟的是 `EOFError` 的子類別 `InputCancelled`（`except EOFError` 照舊接得到）。不接的話模組在那一行停下來，訊息區只出現一行「模組『X』已取消」，不是錯誤、不會問要不要回報；想自己處理就 `except EOFError`（`while True:` 的驗證迴圈請接 `except ValueError`，不要寫什麼都接的 `except:`，不然按取消出不去）；`app.ask` 按取消回 `None`，不丟例外。
- `app.confirm("要繼續嗎")` 跳的是同一種對話框，沒有輸入框、只有取消／確定：按確定回 `True`，按取消回 `False`。
- `app.choose_files`、`app.choose_folder` 在網頁面板開的是系統原生的選擇視窗（pywebview 的，D67），tkinter 面板用 tkinter 的檔案對話框；兩邊回傳的都是真實路徑，按取消回空清單／`None`。
- `app.open`、`edit`、`reveal`、`terminal`、`trash` 都是交給 `modules/作業系統` 做的；沒有那個模組時訊息區會記一行、動作不執行；要改這些行為改那個模組，見 `docs/07_接口與邊界.md`。路徑可以是相對的：以呼叫當下的工作目錄為準，執行期間那就是模組自己的資料夾，所以 `app.open(Path("notes.txt"))` 開的是模組資料夾裡的 `notes.txt`。這五個動作啟動外部程式之後不等它結束。動作失敗時（例如系統上沒有那個程式），錯誤顯示在面板上、記在「作業系統」模組名下，呼叫它的模組不會收到例外、會繼續執行，動作的回傳值是 `None`——要確認 `trash` 有沒有搬走，自己看 `path.exists()`。Windows 上的做法未經實機驗證。
- 跨次執行要保留的東西放 `app.memory`；跨次啟動要保留的寫成檔案放 `app.module.folder`。
- 在面板外執行（裝了工作坊模組「互通」之後：捷徑、一行指令、直接 `python3 iplot.py`，見 `docs/07_接口與邊界.md` 第 12 節）時，`app` 的用法完全一樣，差別只有這幾件：每一次都是一個新的程序，`app.memory` 每次都是空的、不跟開著的面板共用；`app.log`、`print` 與錯誤出現在彈出式視窗，不進面板的訊息區；`app.modules` 是最上層（面板外沒有「進到下一層」）；`input()`、`app.ask`、`app.confirm` 的對話框開在彈出式視窗裡；`app.page` 一樣另開一個視窗；`import tkinter` 一樣被擋。要叫出面板，寫 `app.run("主控面板")`（同名的工作坊模組，D82）。
- 模組要讀設定用 `app.config`，不用自己去讀 `config.py`：`app.config.roots`、`.editor`、`.history_keep`、`.update_url`、`.workshop_url`，對應 `config.py` 的 `ROOTS`、`EDITOR`、`HISTORY_KEEP`、`UPDATE_URL`、`WORKSHOP_URL`。它是啟動時讀好的那一份，唯讀（改它的欄位會丟例外）；`config.py` 改了，要重新啟動 iPLoT 才會變。兩個網址沒設定時是 `None`；`config.py` 壞了或型別不對時，整份是預設值。隨附的「更新」讀 `app.config.update_url`、「工作坊」讀 `app.config.workshop_url`，沒設定就只說一句怎麼設定，不連網。`app.version` 是核心的版本字串，指的是正在執行的這一份。剛更新完、還沒重新啟動時，它還是舊的，磁碟上的檔案已經是新的；所以「更新」比新舊、在確認對話框裡說「現在是哪一版」、給舊版的備份資料夾命名，用的都是磁碟上核心的 `core/__init__.py` 寫的版本（1.0 起在 `modules/核心/`）（`modules/更新/update.py` 的 `installed_version`），讀不到才用 `app.version`。
- 從「工作坊」裝進來的模組，第一次執行前會先問一次（D59、D73）。工作坊安裝、更新或覆蓋一個模組時，在放程式之前先在它的資料夾裡放一個空檔案 `.unconfirmed`；包裡與磁碟上（這個模組的資料夾底下）每一個有 `iplot.py` 的資料夾都放一個，所以進到下一層執行子模組，一樣會先問。磁碟上的也算：新的包只帶了下一層模組旁邊的 `helper.py`、沒帶它的 `iplot.py` 時，那個上一版裝的、已經確認過的資料夾也重新放標記，執行它一樣先問。裝到一半出錯、又沒能放回原樣時，留下來的每個有 `iplot.py` 的資料夾也都放（裡面可能有新下載的程式）。資料夾裡有這個檔的模組，執行之前先跳「確定／取消」：「『<顯示名稱>』是從外面裝進來的，第一次執行前確認：它是會在這台電腦上執行的程式，能讀寫你的檔案。要執行嗎？」。按取消：不執行、不存快照，訊息區記一行「已取消執行『<顯示名稱>』」，標記留著，下次還會問。按確定：拿掉標記、照常執行，之後不再問；標記拿不掉（例如資料夾是唯讀的）也照常執行，只是下次還會再問。這是核心在執行之前做的，模組自己不用寫任何東西；用 `app.run` 執行這樣的模組一樣會先問，按取消時拿到的 `Result` 是 `ok=False`、`error=None`。工作坊不覆蓋「作業系統」「更新」「工作坊」這三個 iPLoT 自己要用的隨附模組（清單上那一列沒有按鈕），所以「作業系統」不會因為工作坊帶上這個標記；它們要換新版，是自己把新的資料夾複製進 `modules/`。「作業系統」的資料夾裡真的有這個檔的話（例如從別處複製進來的資料夾裡本來就帶著一個），在確認之前，每次 `app.open`、`edit`、`reveal`、`terminal`、`trash` 都會先問，按取消就不做、回 `None`。核心只看這個檔在不在，不讀它的內容：不是經過工作坊、自己把別人的資料夾複製進來的模組沒有這個檔，不會問。
- `exit()` / `sys.exit(0)` / `quit()` 是正常結束；代碼非零（`exit(1)`、`sys.exit("壞了")`）才算錯誤，面板顯示「模組以 exit(1) 結束」。兩種都不會關掉 iPLoT。
- `app.module` 是 `ModuleInfo`：`name`（資料夾名稱）、`title`（`TITLE` 或 name）、`description`（docstring 第一段）、`folder`、`file`、`root`、`level`、`has_run`、`accepts_files`、`has_children`、`error`、`icon`（`ICON` 寫的字串，沒寫是 `None`）、`icon_file`（圖示檔的路徑，沒有是 `None`）。
- `app.parent`、`app.children`（D152，核心 0.7.0）給的是 `ModuleInfo`，直接交給 `app.run` 就能叫到那一個，哪一層都叫得到：`app.run(app.parent)`、`app.run(next(m for m in app.children if m.name == "子"))`。`app.run("名稱")` 還是只找面板目前這一層與最上層，不找下一層（D83）。父層的定義：資料夾上一層是模組（符號連結不算）、而且不是根目錄；中間隔著一個不是模組的資料夾，就沒有父層。
- **有頁面的模組有一排「模組導覽列」**（D153，核心 0.7.0；互通 0.3.0 起面板外也有）：`app.page` 開出來的頁面，載入後最上面多一排——主控面板、「↑ 父層名稱」、這個模組的子模組——按一下就關掉這一頁、再跑那個模組。模組什麼都不用寫。已經有一頁開著時再開的頁面沒有；`body` 是橫向的 flex 或 grid 的頁面、或自己已經有一排模組列的頁面，在 `<head>` 放 `<meta name="iplot-nav" content="off">` 就不會有。它在頁面最前面多一個 `<iplot-nav>` 元素（內容在 closed 的 Shadow DOM 裡），`pywebview.api` 多一個 `_iplot_nav`。tkinter 面板沒有頁面，也沒有導覽列。
- 圖示的來源依序是（D65）：模組資料夾裡的 `icon.png` 或 `icon.svg`（檔名要一字不差，`Icon.png` 不算；兩個都有用 png；1 MB 以內）→ `iplot.py` 頂層的 `ICON = "🧩"`（一個 emoji；跟 `TITLE` 一樣只認寫死的字串，不執行模組就讀得到）→ 都沒有就用顯示名稱的第一個字，底色由資料夾名稱算出來，同一個模組每次都一樣。圖檔超過 1 MB 或讀不到時當作沒有圖檔（有 `ICON` 就用 `ICON`），訊息區記一行。圖示只在網頁面板顯示，tkinter 面板沒有圖示。

## 角色：模組之間怎麼合作（核心 0.8.0，D159）

核心不知道任何模組的名字，也不解讀角色的意思：它只認「哪個模組宣告提供哪個角色」，叫的人和提供的人自己約定角色字串的意思。
要用別的模組的功能，問角色，不要寫死它的名字或路徑（規則全文在 iPLoT 資料夾的 `AGENTS.md`）。

```python
# 提供：iplot.py 頂層，字面值（核心只用 ast 讀，不執行）
PROVIDES = {"menu.module": "items"}

def items(app, info):            # 被叫的時候，第一個參數是 app，後面是叫的人給的
    return [("改名…", "rename")]

# 使用：寫明用到哪些角色（AGENTS.md 第 3 條）
NEEDS = ("page.top",)

def run(app):
    if not hasattr(app, "call"):  # 核心 0.7 以前沒有角色
        return app.log("這個功能要 iPLoT 0.8 以上")
    bar = app.call("page.top", app.module)
```

- 提供者的函式跟按下一樣執行（存快照、錯誤顯示在面板、一次一個排隊）。
- 從工作坊裝來的模組宣告角色，第一次會先問使用者允不允許；不允許的話，這次執行期間它不算提供者，下次啟動再問。隨附的與自己寫的不用問。
- 問的時候寫的是角色的名字：自己寫的與隨附的模組可以在頂層用 `ROLE_NAMES = {"menu.module": "右鍵選單裡的項目"}`（字面值）替角色取一個給人看的名字（D166），沒有人取的就寫角色字串本身。工作坊裝來的模組取的名字不算，免得它把自己說得無害。
- 現在有的角色：`os.open`、`os.edit`、`os.reveal`、`os.terminal`、`os.trash`、`os.requirements`、`os.webview_ready`（作業系統）；`menu.module`（整理：面板上右鍵選單多的項目，回 `[(文字, 函式名), …]`）；`page.top`（導覽列：頁面上方那一排）。

## 每按一次另開一個程序（核心 1.0.0，D161）

網頁面板每按一次就另開一個程序跑那個模組。所以：

- `app.page` 開著的時候，面板上按別的模組馬上就跑，不用等頁面關掉。以前要貼的 `_separate`（「互通」的 `separate.py`）不用再貼。
- 模組改工作目錄、`sys.argv`、`input`、`sys.path`、`sys.modules` 只影響自己的程序。
- `app.memory` 照樣跨次保留，但存的東西要能 pickle（數字、字串、清單、dict 都可以）；存不了的那一次不帶回去，下一次拿到的是上一次存得了的。
- 模組的回傳值也要能 pickle，傳不回來就當作出錯，錯誤會說是哪個型別。
- 程序自己結束了（例如 `os._exit`、C 程式庫當掉）變成一個錯誤，面板照常。
- 寫到 stdout、stderr 的東西照樣進訊息區；C 程式庫直接寫的進 `logs/worker.log`。
- `app.run`、`app.call` 在同一個程序裡跑對方；`app.start` 另開一個、不等它。
- 要用 `api_version` 6 才有的東西，在 `iplot.py` 頂層寫 `MIN_API = 6`：舊的 iPLoT 按下去會說「請按『更新』」，不會跑到一半才壞。

頁面視窗由提供 `app.page` 這個角色的隨附模組「頁面」開，最上面那一排照樣問 `page.top`。tkinter 面板（安全模式與備用面板）照舊在同一個程序裡跑、沒有頁面。

## 面板也是模組（核心 1.0.0，D162）

網頁面板是隨附模組「主控面板」：它宣告角色 `main`，iPLoT 開機時在自己的程序裡叫它。

- `main`：`start(app, core, note=None, err=None)`，開面板、視窗關掉才回來。只有開機程式會叫，一般模組不用管。
- `run.outside`：`outside(app, core, info, files, problem, config_error)`，`python3 main.py --run <模組>` 在面板外跑一個模組時要的畫面（D163）。`info` 是找好的模組（找不到是 `None`，`problem` 是那一句），`files` 是要交給 `on_files` 的檔案；回結束碼。丟 `ImportError` 就改在終端機跑。隨附的「互通」提供它。
- `home`：`run(app)`，使用者的「首頁」：面板外跑完的小視窗，回去鈕先回這裡，沒有人提供才回面板（`main`，D93、D165）。剛好一個模組提供時才算。隨附的「行事曆」提供它。
- `os.app_name`：`app_name(app, name)`，這個程序在 Dock、⌘-Tab 上的名字（不改是「Python」，D166）；要在開第一個視窗之前叫，改到了回 `True`。隨附的「作業系統」提供它（macOS；其他系統回 `False`）。主控面板、頁面、互通的小視窗開視窗前會叫。
- `os.activate`：`activate(app, pid)`，把另一個程序的視窗叫到最前面，叫到了回 `True`（D164）。隨附的「作業系統」提供它，跟 `os.open`、`os.trash` 那些放在一起；這個系統做不到就回 `False`，由你跟使用者說下一步。
- `panel.error`：`on_panel_error(app, error, recent, pressed)`。面板上出了錯（不是你這個模組出的錯），先交給你看一眼，`pressed` 是 `False`：回 `True` 表示值得問「要回報嗎？」，面板會問（每個錯誤最多問一次，可以「不要再問」）；使用者按了「回報這個問題」，或答了要回報，會再交一次，`pressed` 是 `True`。`error` 是那一筆錯誤，`recent` 是那時候訊息區最後幾行。隨附的「回報與討論」提供它。

## 直接執行 `iplot.py`：檔頭的那一小段（核心 1.0.0，D163）

隨附模組的 `iplot.py` 檔頭有下面這一段：在編輯器裡直接執行 `python3 iplot.py`，它會往上找 iPLoT 的 `main.py`，交給 `python3 main.py --run` 跑（有「互通」就開小視窗，沒有就在終端機）；從 iPLoT 裡執行時不做事。自己的模組要直接執行，照抄這一段；`IPLOT_DIRECT=1` 就照一般腳本跑。比較舊的 iPLoT 沒有 `--run`，請用「互通」加上它自己的那一段。

```python
# ── iPLoT ── 直接執行這個檔（python3 iplot.py）時交給 iPLoT 跑（python3 main.py --run）；從 iPLoT 裡執行時這段不做事。不要可以整段刪掉
import sys

if __name__ == "__main__" and "core.runner" not in sys.modules:
    import os
    import subprocess
    here = folder = os.path.dirname(os.path.abspath(__file__))
    main = None
    while main is None and folder != os.path.dirname(folder):  # 往上一層層找 iPLoT：模組在它裡面或旁邊都找得到
        folder = os.path.dirname(folder)
        try:
            names = [""] + sorted(os.listdir(folder))
        except OSError:
            names = [""]
        mains = (os.path.join(folder, n, "main.py") for n in names)
        main = next((m for m in mains if os.path.isfile(m) and os.path.isdir(os.path.join(os.path.dirname(m), "core"))), None)
    if main and not os.environ.get("IPLOT_DIRECT"):  # IPLOT_DIRECT=1：不交出去，照一般腳本跑（例如在編輯器裡除錯）
        sys.exit(subprocess.call([sys.executable, main, "--run", here, *sys.argv[1:]]))
    if not main:
        print("找不到 iPLoT（模組要放在 iPLoT 資料夾裡或它旁邊），照一般的 python3 iplot.py 跑", file=sys.stderr)
# ── iPLoT ──
```

## 最小的模組

```python
"""一句話說明這個模組做什麼。"""

def run(app):
    app.log(f"{app.module.title} 執行了")
```

不用 `app` 的話，課本寫的腳本原樣就是模組——沒有 `run`，最外層程式碼就是動作：

```python
x = input("年齡")
print("你的年齡是" + x + "歲")
```

要有自己的畫面，用 `app.page`——一頁 HTML、一顆按鈕，按下去呼叫 `api` 的一個方法：

```python
"""開一頁自己的畫面：按一下加一。"""

PAGE = """<!doctype html>
<meta charset="utf-8">
<button id="add">加一</button> <span id="n">0</span>
<script>
document.getElementById("add").addEventListener("click", () => {
  window.pywebview.api.add().then((n) => { document.getElementById("n").textContent = n; });
});
</script>"""


class Api:
    def __init__(self):
        self._n = 0          # 屬性名以底線開頭：頁面碰不到

    def add(self):           # 公開方法：頁面用 pywebview.api.add() 呼叫
        self._n += 1
        return self._n


def run(app):
    api = Api()
    app.page("加一", PAGE, api)   # 視窗關掉才回到這裡
    app.log(f"關掉之前按了 {api._n} 次")
```

在安全模式與備用的 tkinter 面板執行它，不會開視窗：訊息區先記一行「這個面板沒有頁面…」，接著是「關掉之前按了 0 次」。
