# iPLoT 的規則（給寫程式的 AI 助手，也給人）

這份是 iPLoT 唯一的規則清單。Claude、ChatGPT、Gemini、Copilot、Cursor 等助手：在這個資料夾裡寫或改任何程式之前，先照這份做。
`CLAUDE.md`、`GEMINI.md` 只是指到這裡。每條後面寫著**哪個檢查會擋**；寫「人工」的沒有自動檢查，要靠你自己守。

名詞：**核心**是 `modules/核心/core/`，**面板**是 `modules/核心/ui/`（1.0 起核心本身也是一個模組，D167），**開機程式**是 iPLoT 資料夾的 `main.py`（凍結，不准改，`tests/test_frozen_boot.py`），**模組**是 `modules/` 底下（或 `config.py` 的 `ROOTS` 加的位置）一個有 `iplot.py` 的資料夾。
iPLoT 的方向是「核心只負責執行，功能都長在模組裡」：功能加在模組，不加在核心。

## 一、寫模組（每個人都要守）

上傳到工作坊（iplot-modules）的模組，收件時會跑同一套檢查：iPLoT 維護者的模組違規就退回；別人上傳的只警告、寫在清單上，遵不遵守由你決定，但不守的模組很可能在下一版 iPLoT 壞掉。

**1. 只透過 `app` 碰 iPLoT。不准 import `core`、`ui` 的任何東西。**（R2，`tests/test_module_deps.py::test_no_new_violations`）

```python
# 可以
def run(app):
    app.log("完成")
    folder = app.module.folder

# 不可以
from core import scan          # 核心的內部，下一版就可能改名
from core.types import ModuleInfo
```

**2. 不准用名字或檔案路徑碰別的模組。要用別的模組的功能，用角色：`app.call`、`app.each`、`app.providers`。**（R1）

```python
# 可以：問「誰提供 page.top」，核心不知道、也不在乎是哪個模組
bar = app.call("page.top", app.module)

# 不可以：寫死別的模組的名字或路徑
path = app.home / "modules" / "互通" / "separate.py"
subprocess.Popen([sys.executable, str(app.home / "modules" / "行事曆" / "iplot.py")])
```

要提供功能給別人用，在 `iplot.py` 頂層宣告 `PROVIDES = {"角色": "函式名"}`（字面值，核心只用 ast 讀，不執行）：

```python
PROVIDES = {"menu.module": "items"}   # 右鍵選單多幾項

def items(app, info):
    return [("改名…", "rename")]
```

從工作坊裝來的模組宣告角色，第一次會先問使用者允不允許（D159）。

**3. 用到的角色或模組，都要寫在 `iplot.py` 頂層的 `NEEDS`。可有可無的也要寫。**（R5）

```python
# 可以
NEEDS = ("page.top", "互通")

# 不可以：程式裡用了 app.call("page.top")，NEEDS 沒寫
```

列一份名單（三個以上模組名字的 tuple／list／set，例如「隨附的有哪些」）只是列名字，不算用到。

**4. 不准猜自己在哪個環境：不看 `sys.modules` 裡有沒有 `"ui.web"`、`"ui.tk"`，不猜固定路徑。**（R3）
唯一的例外是模組檔頭的「那一小段」（`"core.runner" in sys.modules`）：iPLoT 永久保留 `core.runner` 這個名字給它用。

**5. 第三方套件只能這三種用法；不管哪一種，都不准 import 套件的內部（`_` 開頭，或 `platforms`、`internal`、`vendor`、`backends` 這類子模組）。**（R4）

```python
# 可以 (一)：包在 try 裡，而且沒有它也能跑
try:
    import numpy
except ImportError:
    numpy = None

# 可以 (二)：頂層宣告 REQUIRES，自己負責裝（課程作業的做法）
REQUIRES = ["numpy", "matplotlib"]

# 不可以
import webview.platforms.cocoa   # 套件的內部，套件一升版就壞
import requests                  # 沒有退路、也沒宣告
```

**6. 另開程序要確認它真的起來了；不准把它的錯誤輸出丟掉（`stderr=subprocess.DEVNULL`）。**（R11）
丟出去就回「成功」，對方失敗時沒有任何人知道。做法：錯誤輸出接到 `logs/separate.log`，等一下看它有沒有馬上出錯結束（抄 `modules/行事曆/iplot.py` 的 `_spawn`）；等不到就跟使用者說一句，自己在這裡做。

**7. 要別的模組的小工具，寧可抄一份也不要依賴它；抄的時候註明出處。**（人工；在 iPLoT 的 repo 裡由 `tests/test_copies.py` 擋：沒登記的抄本會紅）

**8. 用到 `app` 在 `api_version` 4 以後才有的東西（`app.call`、`app.each`、`app.providers` 是 5，`app.start` 是 6），要嘛先 `hasattr(app, "call")` 判斷，要嘛頂層宣告 `MIN_API = 5`（iPLoT 1.0 起不夠新就不跑、會請使用者更新）。**（人工）
使用者的 iPLoT 不一定是最新版。

**9. 每台電腦自己的東西（設定、快取、`.pid`、登入資訊）不准放進上傳的包。**（工作坊收件時退回）
現在的做法：寫在模組資料夾的點檔或 `設定.json`，並在 `.gitignore` 加一行。1.0 起統一放 `.local/`。

**10. 畫面上的文字寫給一般人看：中文、完整句子、說出下一步怎麼辦。錯誤要說清楚發生什麼、使用者可以做什麼。**（人工）

**11. 改了模組，就在它的 `CHANGELOG.md` 最上面加一節、升版本號。**（隨附模組：`tools/bundled_hashes.py --check` 與 `tests/test_bundled_update.py`）

## 二、改 iPLoT 本身（維護者與幫維護者寫程式的 AI）

**12. 功能加在模組，不加在核心。核心與面板不准出現任何模組的名字或角色的意思。**（R6，`tests/test_budget.py::test_core_names_no_module_except_the_transitional_constants` 與 `tests/test_module_deps.py::test_no_new_violations`）
0.8 的三個過渡常數（`BUNDLED`、`SYSTEM_MODULE`、`REPORT_MODULE`）1.0 都拿掉了：隨附的有哪些，核心從雜湊表的鍵讀（D169）。白名單上永久留著的只有工作坊叫「互通」那一筆與 `core.runner` 這個名字。

**13. 行數上限只降不升。**（`tests/test_budget.py::test_limits_never_go_up`、`test_file_within_limit`）
上限在 `tools/limits.json`（核心總和、`modules/核心/ui/` 各檔、主控面板各檔）。真的非升不可：同一個 PR 在 `tools/exceptions.json` 加一筆例外（D 編號、破在哪裡、為什麼、要換成什麼、`remove_by` 版本、`raises`）。
版本號到了 `remove_by` 還沒回收，`test_exceptions_are_complete_and_not_expired` 就紅：要嘛回收，要嘛明著改 `remove_by` 延期。列在上限表的檔不見了也算紅，改名或搬家要一起改表。

**14. 依賴違規只准變少。**（`tests/test_module_deps.py`）
`python3 tools/check_deps.py` 列出現在的違規。白名單 `tools/deps_allow.json` 的每一筆寫著原因（`why`）和哪一版拿掉（`until`）；改掉了就從白名單刪掉（不刪會紅），到了 `until` 還在也會紅。新加一筆白名單要有站得住的理由，寫在 `why`。

**15. 抄本要登記。**（`tests/test_copies.py`）
`python3 tools/check_copies.py` 找逐字一樣的函式。登記在 `tools/copies.json`：`same: true` 的那一組改一份就要改全部，不然會紅。

**16. 核心不碰作業系統，不 import tkinter、pywebview；畫面文字只放在 `modules/核心/core/text.py`。**（`tests/test_boundaries.py`）
碰作業系統的事交給「作業系統」模組（角色 `os.*`）。

**17. 覆蓋率只准持平或上升。**（CI 的 `python tools/check_coverage.py`，基準在 `tools/coverage-baseline.json`）
量的是開機程式、核心與隨附模組。升上去了就把基準一起升（`--write`），讓下一個人不能再降回來。

**18. 工作坊在每一版核心上都要打得開，它只能用 `app` 在 0.5 就有的東西、標準庫和自己的檔；交出去給別的模組之後，要確認對方真的開起來了，否則自己開。**（`tests/test_workshop_every_core.py`）

**19. 每個重要的決定寫進 `docs/03_設計決定.md`（D 編號）；CHANGELOG 寫給使用者看。**（人工）

**20. 不准自己合併、打 tag、發佈、上傳或刪分支：這些都要 William 先說好。**（人工）

## 三、改完之前跑這些

```sh
ruff check .
python3 tools/check_deps.py
python3 tools/check_copies.py
python3 -m pytest -q
```

規則的來由與每一筆白名單的細節：`docs/03_設計決定.md` 的 D159（角色）、D160（規則上 CI）。
