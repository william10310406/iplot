# Changelog

本檔案記錄 iPLoT 每個版本的變更，格式依 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版本號依 [語意化版本](https://semver.org/lang/zh-TW/)。`app.api_version` 另外計算，見 `docs/api.md`。

## [Unreleased]

核心沒有改（`core/`、`ui/`、`main.py`、`requirements/` 一行都沒動，核心邏輯仍是 502 有效行）；這一節記的是 repo 的 `modules/` 裡的工作坊模組。

### 新增
- 工作坊模組「行事曆」0.1.0（`modules/行事曆`，圖示是 `icon.png` 的月曆，D89–D92）：以行事曆為主控，每天寫行程、心情、看到了什麼、做了什麼，放照片，存成一天一個資料夾並產生網頁；「發佈」產生只含公開日子的 `發佈/`（不上傳）。見 README 的「行事曆」。`tests/test_calendar.py`，102 個。

### 變更
- 「互通」0.1.0（還沒發佈過，改在同一版）：小視窗的回去鈕，最上層剛好一個「行事曆」就回行事曆，否則照舊回主控面板（D93，D88 的修訂）；面板外 `app.page` 開著的期間，小視窗不再因為跑太久冒出「執行中」，那段期間關掉它只是藏起來，選完檔案或資料夾也藏回去（docs/07 第 12 節本來就這樣寫，之前沒做到）。`tests/test_interop.py` 123 → 136 個。

## [0.5.1] - 2026-10-07

核心的小改版，給兩個新的工作坊模組用：`app.run` 在面板停在下一層時，目前這一層找不到就退到最上層找（D83）；＋ 建的新模組檔頭帶「互通」的那一小段，裝了「互通」就能直接 `python3 iplot.py`（D84）。新功能在工作坊：「互通」讓任何模組不開面板也能打開（Spotlight、Dock、一行指令、直接執行），「主控面板」讓任何模組用 `app.run("主控面板")` 叫出面板。

**與 0.5.0 相容：既有模組不用改；`api_version` 仍是 3，`app` 沒有多也沒有少。** 從 0.5.0 更新：按「更新」（換掉 `core/`、`ui/`、`main.py`、`requirements/`；`requirements/` 這一版沒變，不會重裝 `lib/`）；「更新」不碰 `modules/`，所以「互通」「主控面板」要從工作坊裝。新下載的 0.5.1 已經帶著這兩個模組。隨附的「開工」「打開核心原始碼」升到 0.5.1（檔頭帶那一小段），工作坊上也是。

**從這一版起，核心只在大版本（1.0.0、2.0.0…）才真正修改，新功能以工作坊模組上線（D80）；這一版是明講的例外。** 工作坊模組可以依賴的核心介面列在 `docs/07_接口與邊界.md` 第 13 節，到 1.0.0 前只加不改（D85，`tests/test_interfaces.py`）。

**只在 macOS 驗過，而且只有一台機器（macOS 26.5、arm64、python.org 的 Python 3.14.7）。** 自動測試之外，2026-10-07 在那台 Mac 上、在一份暫存的 iPLoT 複本（路徑有空白與中文）裡真的走過：系統內建的 Python 3.9 執行 `run.py`，自動換成記下的 Python 3.14 跑完；從捷徑（交給 Python.app）打開；直接 `python3 iplot.py`；「主控面板」在面板沒開時開一個、面板被別的視窗蓋住時叫到最前面（從捷徑開、從終端機開各一次）。還沒驗的：乾淨的 Mac 上 macOS 對「Python 取用『文件』」是不是只問一次（這台在測之前就允許過）；藏著的小視窗打開檔案選擇視窗（要人按）；Windows（未經實機驗證）。

量出來的數字：測試 487 → 685 個；核心邏輯 500 → 502 有效行（上限 500 → 505，D68 修訂）；`core/` 仍是 11 個檔，這一版改了其中 4 個（`core.py` 的 `run_by_name`、`app.py` 的 `App.run` 說明、`text.py` 的範本、`__init__.py` 的版本號），`ui/`、`main.py`、`requirements/` 沒動；`core/text.py` 的文字仍是 55 個 key；範本裡的那一小段 22 行；repo 裡的模組 7 → 9 個。「互通」7 個 Python 檔共 803 有效行、兩頁 HTML 217＋162 行，「主控面板」111 行，都是模組，不在核心預算裡。

這一版沒有做：常駐的背景程式（一有變動就同步、開機就跑、快捷鍵、監看資料夾、排程）；用名字叫下一層的模組；面板外的模組把訊息送進開著的面板、或跟面板共用 `app.memory`（要跨程序連線）；捷徑用 emoji 的 `ICON` 當圖示（只用 `icon.png`）；Windows、Linux 的捷徑與「叫到最前面」。

還留著的缺口：0.5.0 列的缺口裡，「發佈工具打模組的包…沒 commit 的檔會進去」這一條這一版收掉了，其餘照舊。新的：在面板外叫「主控面板」時，小視窗會先蓋在面板前面 3 秒；這一版的 Linux 在面板外打不開時，那一句說的是「lib/ 是給別的 Python 裝的」，不是「這一版的 Linux 沒有網頁面板」。

### 新增
- 工作坊模組「互通」0.1.0（`modules/互通`，圖示 🔗，D81、D84、D86）：`run.py` 是面板外唯一的入口（`<Python> <iPLoT>/modules/互通/run.py <模組資料夾或名稱> [檔案…]`，結束碼 0／1／2）；彈出式視窗照核心的 `View` 做，平常藏著，有話才出來；捷徑（macOS 的 `.app`，在 `modules/互通/捷徑/`，交給 Python 的 Python.app 開）；同步（捷徑與 `.sync-error`；不改任何模組檔案，D87），只在 `run.py` 跑完與按「互通」時做；在面板按「互通」看狀態頁，舊模組要能直接執行，在那裡看清楚會改哪幾個檔、按「加上」（只限 iPLoT 的 `modules/`，改之前存快照）；模組跑完、小視窗還在時，底下的「主控面板」按鈕回到面板（D88）。詳細在 `docs/07_接口與邊界.md` 第 12 節、README 的「在面板外打開模組」（`tests/test_interop.py`，123 個）。
- 工作坊模組「主控面板」0.1.0（`modules/主控面板`，圖示 🎛️，D82）：打開面板，已經開著就叫到最前面；在面板外也一樣（`tests/test_open_panel.py`，17 個）。
- `tests/test_interfaces.py`：釘住工作坊模組可以依賴的核心介面（D85，30 個）。

### 變更
- `app.run`（`Core.run_by_name`）：先找面板目前這一層，找不到再找最上層；同一處有兩個同名就丟 `LookupError`，不猜（D83，`tests/test_core.py::test_run_by_name_falls_back_to_top_level` 等四個）。面板在最上層時行為跟 0.5.0 一樣。
- ＋ 的範本：第一行的說明之後帶「互通」的那一小段（D84，`tests/test_create.py::test_template_*`）。在 iPLoT 裡執行時它不做事；直接執行時往上找 `modules/互通/run.py`，找到就交給它；找不到就在 stderr 說一句、照一般的腳本繼續跑（跟 0.5.0 一樣）；環境變數 `IPLOT_DIRECT=1` 時一律不交出去（在編輯器裡除錯用）。
- 核心邏輯的上限 500 → 505（D68 修訂）。
- 隨附模組「開工」「打開核心原始碼」0.5.0 → 0.5.1，「重新啟動」「開Terminal」：檔頭帶那一小段，可以直接 `python3 iplot.py`（`tests/test_bundled.py::test_repo_modules_carry_the_interop_snippet`）；「作業系統」「更新」「工作坊」不帶（`::test_iplots_own_modules_stay_untouched`）。
- `.gitignore` 加上「互通」自己產生的 `modules/互通/捷徑/`、`.python`、`.patched`（開發途中用過，後來不用了，那一行留著）、`.sync-error`、`.lock`。

### 修正
- `tools/publish.py` 打模組的包只收 git 追蹤的檔（`git ls-files`），沒 commit 的檔、自己產生的紀錄不會被發出去；整個模組都還沒 commit 就停下來說一句（`tests/test_publish.py::test_main_packs_only_tracked_files`、`::test_main_stops_for_a_module_git_does_not_track`）。

## [0.5.0] - 2026-10-06

M3「更新與工作坊」：多了兩個隨附模組——「更新」把核心換成新版（D69），「工作坊」從一份清單安裝、更新別人做的模組（D70）——以及開發端的發佈工具 `tools/publish.py`。兩個來源網址寫在 `config.py`（D71），隨附的已經填好 GitHub Pages 上 `iplot-workshop` 的網址（D79），改成 `None` 就不連網；按了才連網，平常使用不需要網路。模組有自己的版本與更新紀錄（模組資料夾裡的 `CHANGELOG.md`，D78）。`app` 多 `page`、`config`、`version`，`api_version` 2 → 3（D72）。從工作坊裝進來的模組，第一次執行前先問一次（D59 採用、D73）。

**與 0.4.0 相容：既有模組不用改，`api_version` 2 → 3 只加不減。從 0.4.0 更新：換掉 `core/`、`ui/`、`main.py`、`requirements/`，把 `modules/更新`、`modules/工作坊` 複製進 `modules/`，在 `config.py` 加 `UPDATE_URL`、`WORKSHOP_URL` 兩行（照 0.5.0 隨附的 `config.py` 抄；不加也能用，等於沒設定）；`config.py` 原有的內容、`custom.css`、自己的模組不動。從 0.5.0 起，下一版可以直接按「更新」。** 這一版的 `requirements/` 跟 0.4.0 的一樣，換上來之後不會重裝 `lib/`、不需要網路。0.4.0 就有的隨附模組裡，開工、打開核心原始碼、開Terminal、重新啟動沒有變，不用換；「作業系統」只改了 `linux.py`、`win.py` 的 `webview_ready` 回的那一句（不再叫人用安全模式，見「變更」），不換也能用。另外有兩件 0.4.0 的行為改了：網頁面板開不起來時退到的 tkinter 面板不再是安全模式（D75，見「變更」）；需求檔變了，下次啟動會重裝 `lib/`（D76，見「新增」）。

**「更新」與「工作坊」只在 macOS 驗過，而且只有一台機器（macOS 26.5、arm64、python.org 的 Python 3.14.7），自動測試的來源都是本機的 `file://` 網址。放檔案的地方是 GitHub Pages 上的 `iplot-workshop`（D79）；從 GitHub Pages 上的 `iplot-workshop` 真的下載、更新、安裝，2026-10-06 在 macOS 上用 `tests/acceptance_workshop.py` 走過一次（全部通過；確認框的長相、用瀏覽器看那一頁、沒有網路時的那一句，要人眼看的部分還沒做）；在這之前 https 只驗過連得上 raw.githubusercontent.com、憑證過得了。Windows 未經實機驗證。Linux 這一版仍然沒有網頁面板，所以也沒有工作坊的清單頁，而且沒有在真的 Linux 桌面上跑過。CI 設了 macOS、Windows、Ubuntu 三個平台，但這個 repo 沒有遠端，CI 一次都沒有跑過。**

量出來的數字：測試 323 → 487 個；核心邏輯 490 → 500 有效行（上限 500，剛好用滿）；`core/` 仍是 11 個檔；隨附模組 5 → 7 個；`core/text.py` 的文字 50 → 55 個 key。預算仍是七項，有效行／上限：核心邏輯 500/500、`ui/web.py` 199/220、`ui/tk.py` 120/180、`ui/install.py` 58/80、`ui/index.html` 30/120、`ui/app.js` 256/400、`ui/style.css` 126/300。`ui/web.py` 的上限這一版從 200 調到 220（D68 修訂）：0.4.0 已經用到 194，這一版的 `page` 要 5 行，另外替日後「關閉前確認」留 8 行。不在預算內的新檔（有效行）：`tools/publish.py` 187；`modules/更新/` 的 `update.py` 131、`iplot.py` 43；`modules/工作坊/` 的 `workshop.py` 291、`iplot.py` 17、`page.html` 82。`tests/smoke.py` 的七個情境在上面那一台機器上全過。

這一版沒有做：模組執行中關視窗先確認（決定延後）；中途停掉執行中的模組（D56 仍延後）；工作坊的移除、降版、評分、留言、自動更新、多個索引；更新的自動檢查、差異比較、一鍵回溯；套件的 hash 釘死；Linux 的網頁面板（所以在 Linux 上按「工作坊」，讀完索引只會在訊息區看到「這個面板沒有頁面（安全模式與備用面板都是）；這個功能要在一般的網頁面板裡用」那一句，沒有清單頁）；拖放；自動啟動；匯入原版模組。寫這一節的時候，0.4.0 與 0.5.0 的人工驗收（`docs/plans/2026-10-05-M2-網頁面板與更新.md` 第 11 節的 (a)–(m)、13.6 的 (a)–(g)）都還沒做。

還留著的缺口：「更新」剛好在兩次改名之間（毫秒級）被強制結束的話，磁碟上會暫時是新舊混合，直到下一次按「更新」才收回；iPLoT 啟動時不檢查這件事，開不起來時照 README 的「怎麼回到舊版」用手救。「更新」先備份、才收回上一次留下的殘餘，所以上一次換到一半被強制結束的話，下一次的備份存的是新舊混合的四樣，名字卻標成舊版本。iPLoT 資料夾裡叫 `core.old`、`ui.new`、`.update-old-…` 這類名字的東西，會被「更新」當成自己的殘餘換進去或刪掉。工作坊裝到一半出錯時，放回原樣的做法是「刪掉、再從快照解回去」，不是在暫存處組好整個新資料夾再交換：遇到刪不掉、寫不回去的東西時，原本就有的資料夾會留在新舊混合的樣子，那一列說快照在哪裡，要用手放回；快照也不是一模一樣的複本，指向資料夾的符號連結不在快照裡、指向檔案的放回來變成一般檔，執行權限與空資料夾不會回來。這幾件記在 `docs/05_使用紀錄.md` 的待辦。發佈工具打模組的包是從資料夾直接打的，沒 commit 的檔、符號連結指到的內容都會進去；模組 zip 的 sha256 跟檔案時間有關，同樣的內容重打一次 sha256 會變。`.backup/`、`.origin`、`.unconfirmed`、`.update-old-…` 不在 `.gitignore` 裡（暫存的 `.update-tmp/`、`modules/.workshop-tmp/` 做完就清掉，不會留下；`.update-old-<名稱>-<n>` 是換下來的舊版改的名字，換好就刪，刪不掉的留到下一次更新開頭再刪）。

### 新增
- 隨附模組「更新」（`modules/更新`，圖示 ⬆️，D69）：把核心換成新版。`config.py` 的 `UPDATE_URL` 指到一個 `update.json`（`version`、`zip_url`、`sha256`、`notes`），zip 就是交付用的那一包（最上層是 `iPLoT-vX.Y.Z/`）。按了才連網，不會自己去檢查有沒有新版。來源的版本比較新時，先用「確定／取消」顯示版本與 `notes`（這一版的摘要）；確定之後下載到 `.backup/download-<版本>.zip` 並驗 sha256，把現在的 `core/`、`ui/`、`main.py`、`requirements/` 複製到 `.backup/<舊版本>-<日期時間>/`，再把包裡的這四樣換上去（先解到 `.update-tmp/`，四樣各自搬成 `<名稱>.new`，再照 `ui/`、`main.py`、`requirements/`、`core/` 的順序逐一改名換上去：舊的先改名成 `<名稱>.old`，四樣都換好才改名成 `.update-old-<名稱>-<n>` 再刪；做完清掉暫存）。`core/` 最後換，所以磁碟上的版本是新的，就代表四樣都換好了。確認對話框裡的「現在是…」與備份資料夾名稱裡的 `<舊版本>`，用的都是磁碟上 `core/__init__.py` 寫的版本（`tests/test_update.py::test_core_is_swapped_last`、`::test_backup_is_named_after_the_version_on_disk`）。訊息區說「已更新到 x.y.z，執行「重新啟動」就會用新版。舊版備份在 .backup/…/」。不是熱更新：換完要執行「重新啟動」才會用新版，`app.memory` 會清空。來源的版本沒有比較新時說「已是最新（x.y.z）」；剛換完、還沒重新啟動又按一次，說「已經換成 x.y.z 了，執行「重新啟動」就會用新版」，不會再下載、再備份、再換一次。
- 「更新」只換那四樣：`config.py`、`custom.css`、`modules/`（含各模組的 `.history/`）、`logs/`、`lib/` 逐位元組不變，iPLoT 資料夾以外沒有任何寫入（`tests/test_update.py::test_apply_replaces_only_parts_and_keeps_rest`）。sha256 對不上：刪掉下載的檔、說一句、什麼都不動（`::test_sha_mismatch_touches_nothing`）。包不完整（四樣少一樣）或最上層不只一個資料夾：一樣都不換。換上去的過程中出錯（`OSError`）：已經換上的全部放回、`.new` 丟掉，四樣要嘛全新、要嘛全舊（`::test_apply_rolls_back_when_a_swap_fails`）。備份或換上去時出錯（權限、磁碟滿、檔案被佔著）是訊息區的一句話，不是模組錯誤，而且照磁碟上的實況說：都放回去了，是「沒有更新：<錯誤>。core/、ui/、main.py、requirements/ 都還是原來的」；放回去時也出錯了，是「沒有更新，而且放回原來的版本時出錯了：<錯誤>。<留下的東西> 要用手整理（舊版的備份在 .backup/<資料夾>/，做法見 README 的「怎麼回到舊版」）」，留下的東西是還在的 `<名稱>.old`、`<名稱>.new` 與不見了的那幾樣，備份本身就失敗時括號裡是「這一次沒有做成備份」（`::test_a_failed_swap_is_one_sentence_and_everything_is_put_back`、`::test_a_failed_backup_is_one_sentence`、`::test_when_putting_back_fails_too_the_sentence_does_not_say_it_was_put_back`）。每次更新在換上去之前，先收上一次留下的殘餘：還有任何 `<名稱>.new`，表示上一次換到一半被強制結束，留著的 `<名稱>.old` 全部放回去，最後才丟 `.new`（放回的途中又被強制結束，下一次還看得到 `.new`，會接著收）；沒有 `.new`，表示上一次已經全部換好、只是舊版沒刪掉，那些 `.old` 不放回去，先在原地改名成 `.update-old-<名稱>-<n>` 再刪（同一層的改名，整個唯讀的舊資料夾也改得動），刪不掉的（例如裡面有唯讀的子資料夾）留著那個名字、不會再叫 `<名稱>.old`，下一次更新開頭再刪一次（`::test_apply_recovers_from_a_swap_that_was_killed_half_way`、`::test_a_restore_that_is_killed_half_way_is_finished_next_time`、`::test_leftover_old_without_new_is_not_put_back`、`::test_old_that_cannot_be_deleted_is_renamed_before_it_is_cleared`、`::test_a_read_only_old_folder_is_still_moved_out_of_the_way`）。連不上來源、連線到一半斷掉或伺服器沒回話（「連不上更新來源，或下載到一半斷了，沒有更新：…」）、網址寫錯（「網址寫錯了，沒有更新：…」，並指出去看 `config.py` 的 `UPDATE_URL` 或 `update.json` 裡的 `zip_url`）、`update.json` 不是 JSON 或缺項（「更新來源的 update.json 少了 'zip_url' 這一項，沒有更新」）、`version`、`zip_url`、`sha256` 不是文字（null、數字：「沒有更新：update.json 裡的 version、zip_url、sha256 應該都是文字（update.json 或下載的檔案有問題）」，`::test_wrong_types_in_update_json_are_one_sentence`）、下載的檔不是 zip：訊息區一句話，不是 traceback。這三項在比版本之前就檢查，所以 `update.json` 缺項時，就算已是最新也說缺了哪一項。隨附模組在 `modules/` 裡，「更新」不碰它們：開工、打開核心原始碼、開Terminal、重新啟動的新版可以從工作坊來；「作業系統」「更新」「工作坊」工作坊不覆蓋，要換新版得自己把新的資料夾複製進 `modules/`。要回到舊版：把 `.backup/<舊版本>-…/` 裡的四樣用手搬回去。
- 隨附模組「工作坊」（`modules/工作坊`，圖示 🧰，D70）：從一份清單安裝、更新別人做的模組。`config.py` 的 `WORKSHOP_URL` 指到一個 `index.json`（`modules` 清單，每一筆有 `name`、`version`、`zip_url`、`sha256`、`description`、`icon`，可以有 `notes`），每個 zip 的最上層是 `<name>/`。按了才連網：讀完索引，用 `app.page` 開一頁清單（`page.html`，零外部資源），每個模組一列——圖示、名稱、說明（索引有 `notes` 的，底下多一行「這一版：…」，D78）、索引的版本、在這台電腦上的狀態、一顆按鈕。六種狀態：未安裝（沒有這個資料夾）→「安裝」；已安裝（內容沒變、索引的版本不比它新）→ 沒有按鈕；可更新（內容沒變、索引比較新）→「更新」；已修改（當初裝進來的檔有被改過或刪掉，或 `.origin` 壞了；模組自己另外存的設定、資料不算）→「覆蓋」；版本未知（資料夾在但沒有 `.origin`：自己建的同名模組，或開工這類隨附模組，D74）→「覆蓋」；隨附模組（索引裡的名字是「作業系統」「更新」「工作坊」，D74 修訂）→ 沒有按鈕，那一列多一句「這是 iPLoT 自己要用的隨附模組，工作坊不覆蓋它；要換新版，自己把新的資料夾複製進 modules/。」。不覆蓋這三個，是因為從工作坊覆蓋之後它們會帶著 `.unconfirmed`：在面板上按過一次確定之前，用到「作業系統」的右鍵動作、「打開檔案」都會先問；啟動時要安裝介面，問的是主控台那一頭，沒辦法回答。名字先做 Unicode NFC 正規化、不分大小寫再比，資料夾在的話再問檔案系統是不是同一個資料夾，所以相容表意字（U+F901 就是「更」）、大小寫不同的寫法也擋得住；這三個資料夾被刪掉了，也不從工作坊裝回來（`tests/test_workshop.py::test_workshop_never_overwrites_iplots_own_modules`）。自己複製進來的資料夾沒有 `.unconfirmed`，不會先問。「覆蓋」先在同一列問一次：按鈕變成「確定覆蓋」與「取消」，旁邊一句「這會覆蓋現有的模組，舊版會整個存進它的 .history/」，再按才做。從工作坊裝過的模組按「更新」，包裡的檔會蓋掉或拿掉模組自己存的檔時，也在同一列這樣問一次（D77，見下一條）。按「取消」回到那一顆按鈕原來的字（「更新」或「覆蓋」），下次按一樣先問（`::test_cancel_puts_back_the_buttons_own_label`）。兩列同時按，安裝會排隊，一次裝一個（`::test_two_installs_at_once_both_finish`）。關掉清單頁，面板重掃，新裝的格子出現。索引裡的字（名稱、說明、版本、圖示、`notes`）在清單頁一律當文字顯示，不當 HTML（`tests/test_workshop.py::test_page_shows_the_notes_as_text`）。
- 工作坊的安裝：下載到 `modules/.workshop-tmp/`、驗 sha256；資料夾已經在的話，先把整個資料夾（最上層的 `.history/` 自己除外）壓成 `modules/<name>/.history/<日期時間>-folder.zip`；放程式之前，先在包裡與磁碟上（模組資料夾底下，`.history/`、`__pycache__` 這些裡面的不算）每一個有 `iplot.py` 的資料夾建空檔案 `.unconfirmed`（所以下一層的子模組也會問；包只帶了下一層模組旁邊的 `helper.py`、沒帶它的 `iplot.py` 時，上一版留下的那個資料夾也會問，`tests/test_workshop.py::test_nested_modules_are_asked_about_too`、`::test_module_folders_already_on_disk_are_asked_about_too`）；把包裡的檔案蓋上去（包裡沒有的舊檔案留著；舊版的某個名字是檔案、新版是資料夾或反過來，照新版的放；資料夾裡本來的符號連結拿掉、換成包裡的檔案，不順著它寫到 `modules/<name>/` 外面）；寫來源記錄 `.origin`（一行一個 `key: value`：`url`、`version`、`sha256`、`digest`、`files`、`installed`）；清掉暫存。蓋到一半出錯（磁碟滿、權限、Finder 鎖定的檔…）：照剛才的快照把資料夾放回裝之前的樣子，原本沒有這個資料夾就整個拿掉。讓安裝失敗的原因通常也讓刪除失敗，所以放回時遇到刪不掉、寫不回去的東西不停下來：能刪的刪，快照裡每個檔都試著解回去，最後逐檔跟快照比，一樣才算放回去了（快照資料夾不分大小寫，本來就有的 `.History/` 不刪；快照讀不到就一樣都不刪）；沒放回去的話，留下來的每個有 `iplot.py` 的資料夾都放 `.unconfirmed`（裡面可能有新下載的程式）。清單那一列照實說：「無法安裝：<錯誤>；沒有裝成，已從快照放回」或「無法安裝：<錯誤>；沒有裝成，放回時出錯，快照在 <快照 zip 的完整路徑>」，快照讀不到時是「無法安裝：<錯誤>；沒有裝成，快照讀不到、沒有放回，資料夾現在是新舊混合：<資料夾路徑>」；原本沒有這個資料夾的，是「…；沒有裝成，裝了一半的資料夾已經拿掉」或「…；沒有裝成，裝了一半的資料夾拿不掉：<資料夾路徑>」（`::test_failed_install_puts_the_old_folder_back`、`::test_failed_first_install_leaves_no_folder`、`::test_rollback_goes_on_past_a_read_only_folder`、`::test_rollback_with_a_locked_file`、`::test_when_the_rollback_cannot_finish_the_sentence_says_where_the_snapshot_is`、`::test_rollback_that_cannot_write_a_file_back_does_not_say_it_put_it_back`、`::test_a_rollback_that_cannot_finish_leaves_every_module_folder_asking`、`::test_rollback_keeps_the_snapshot_when_the_folder_already_has_dot_History`（只在不分大小寫的檔案系統上跑）、`::test_rollback_does_not_delete_anything_when_the_snapshot_is_unreadable`）。`files` 是裝進來的檔的清單，`digest` 是這些檔的摘要，用來判斷「已修改」：清單以外的檔（模組自己存的設定、資料）不算，`.history/`、`__pycache__`、拿掉 `.unconfirmed` 也都不算，所以執行過、確認過都不算已修改（`::test_a_modules_own_data_does_not_make_it_modified`）。反過來，從工作坊裝過（有 `.origin`）的模組要更新時，下載、解開之後先看包裡的檔放上去會不會蓋掉或拿掉不在 `files` 清單裡的本機檔——同名的檔、同名的資料夾（整個會被拿掉）、擋在要建資料夾的地方的檔；會的話先回「需要確認」，資料夾一個位元組都不動，清單頁在那一列問，按「確定覆蓋」才再下載一次、照常存快照再裝；包裡的檔只蓋到當初裝進來的那些，就不多問（D77，修正規格 13.3；`::test_update_asks_before_overwriting_a_file_the_module_made`、`::test_update_asks_before_removing_what_the_module_made`、`::test_update_that_only_replaces_its_own_files_does_not_ask`）。包裡夾帶的 `.history`、`.origin`、`.unconfirmed`、`__pycache__`、`.DS_Store` 不裝，比對不分大小寫（macOS 上 `.Origin` 跟 `.origin` 是同一個名字，`::test_case_variants_of_local_names_cannot_switch_off_the_question`）。不變量：只寫進 `modules/<name>/` 與暫存，其他資料夾逐位元組不變（`tests/test_workshop.py::test_install_writes_only_its_folder`）；覆蓋前有快照（`::test_install_snapshots_existing_folder`）。不裝、資料夾不動、清單那一列顯示一句「無法安裝：…」的情況：sha256 對不上；zip 的最上層不是 `<name>/`；包裡沒有 `iplot.py`；路徑裡有 `..`；索引裡的名稱不是單純的資料夾名（含 `/`、`\`，或以 `.` 開頭）；名稱是「作業系統」「更新」「工作坊」（「「<名稱>」是 iPLoT 自己要用的隨附模組，工作坊不覆蓋它」）；`modules/<name>` 本身是符號連結。連線到一半斷掉、伺服器沒回話也是那一列一句「無法安裝：…」；寫檔出錯的那一句見上面，會說放回去了沒有。打開工作坊時，索引讀不懂（不是 JSON、缺項，或名稱、網址、sha256 不是文字）或網址寫錯，訊息區說「讀不懂工作坊的清單（index.json），或 WORKSHOP_URL 寫錯了：…」；索引的版本一律當字串，同名的只留第一筆。
- 「更新」與「工作坊」開網址時自己帶一份驗證 https 憑證的設定：python.org 的 macOS Python 預設沒有根憑證（要另外執行「Install Certificates.command」），那樣每個 https 網址都驗證失敗；憑證庫是空的時候改用 macOS 自己的 `/etc/ssl/cert.pem`。驗證本身不關（`tests/test_update.py::test_https_open_brings_a_trust_store`、`tests/test_workshop.py::test_https_open_brings_a_trust_store`）。
- 發佈工具 `tools/publish.py`（開發端用，不在核心裡）：`python3 tools/publish.py --version 0.5.0 --base-url <放檔案的地方> --modules 整理桌面 開工`，在 `交付/發佈/`（或 `--out` 指的資料夾）產生 `iPLoT-v0.5.0.zip`（`git archive` 那個 tag；還沒打 tag 時加 `--ref HEAD`）、`update.json`（`notes` 取自本檔那一版那一節的第一段，也就是摘要：它整段顯示在「要更新嗎」的對話框裡）、`模組/<名稱>.zip`、`index.json`、給還沒裝 iPLoT 的人看的一頁 `index.html`（同一份資料；沒有 JS、沒有外部資源，字都先跳脫）、空檔 `.nojekyll`（D79；`tests/test_publish.py::test_index_html_lists_every_module_and_escapes_text`、`::test_out_dir_gets_everything_and_the_default_folder_stays_untouched`、`::test_nojekyll_is_written`、`::test_core_only_run_keeps_the_modules_on_the_page`），並印出要填進 `config.py` 的兩行（前面沒有空白，可以直接貼上）。模組的版本與 `index.json` 的 `notes` 取自模組資料夾裡的 `CHANGELOG.md` 最上面那一節（D78）；沒有這個檔的模組，版本跟 `--version` 一樣、`notes` 是空的；要另外指定寫「名稱=版本」，跟 `CHANGELOG.md` 不一樣就停、不產生任何檔；`CHANGELOG.md` 讀不出最上面那一版（不是 UTF-8、沒有任何一節、版本不是只有數字與點）也停（`tests/test_publish.py::test_a_module_changelog_whose_top_version_cannot_be_read_stops_before_writing_anything`（四種）、`::test_a_module_changelog_with_a_bom_is_read`、`tests/test_publish.py::test_module_version_and_notes_come_from_its_changelog`、`::test_conflicting_versions_stop_before_writing_anything`、`::test_modules_without_a_changelog_follow_the_core_version`）。寫進 JSON 的網址，中文與空白會寫成 %XX。打包的那個 ref 裡 `core/__init__.py` 的版本不等於 `--version` 就停：說一句、代碼 1、不產生任何檔。`git archive` 先寫到 `.part` 再改名，寫到一半失敗也不會把同名的舊 zip 蓋掉（`tests/test_publish.py::test_failed_archive_does_not_destroy_the_previous_zip`）。沒給 `--modules`（只發佈核心）時不動原本的 `index.json`。工作目錄有還沒 commit 的改動時提醒一句：核心的包是從 ref 打的，不含那些改動（模組的包含）。打包模組時略過的東西跟工作坊安裝時略過的是同一組，比對都不分大小寫（`tests/test_workshop.py::test_publish_and_workshop_agree`、`tests/test_publish.py::test_skip_ignores_case`）。放檔案的地方是另一個公開 repo `iplot-workshop` 的 GitHub Pages（D79）：`--out ../iplot-workshop --base-url https://<帳號>.github.io/iplot-workshop`，再在那裡 commit、push；在本機試用 `file://` 網址；Google Drive 的分享連結不是直接取檔，不行。
- `config.py` 多兩行（D71）：`UPDATE_URL`（`update.json` 的網址）、`WORKSHOP_URL`（`index.json` 的網址）。隨附的 `config.py` 填的是 GitHub Pages 上 `iplot-workshop` 的正式網址 `https://william10310406.github.io/iplot-workshop/update.json`、`https://william10310406.github.io/iplot-workshop/index.json`，剛拿到的 iPLoT 按「更新」「工作坊」就有東西；改成 `None` 就不連網（D71 修訂、D79，`tests/test_bundled.py::test_shipped_config_points_at_the_workshop_site`）。`Config` 對應多 `update_url`、`workshop_url`；型別不對（不是 `None` 也不是字串）時跟 `ROOTS` 一樣，整份用預設值啟動並說哪裡不對。`Config` 的預設值是 `None`：兩個網址是 `None`（或 `config.py` 裡沒寫）時，「更新」「工作坊」各說一句怎麼設定，不連網、不寫任何檔（`tests/test_bundled.py::test_update_and_workshop_do_nothing_until_a_url_is_set`）。
- `app` 多三個成員（`api_version` 2 → 3，D72）：`app.config`（唯讀的 `Config`：`roots`、`editor`、`history_keep`、`update_url`、`workshop_url`）、`app.version`（核心的版本字串）、`app.page(title, html, api=None)`——開第二個視窗顯示一頁 HTML，關掉才回來（像對話框）；`api` 的公開方法給那一頁的 JS 用 `pywebview.api.<方法>` 呼叫。安全模式與後備的 tkinter 面板沒有頁面，`page` 只在訊息區記一行。`View` 對應多一個 `page`，現在八個方法：`show`、`log`、`report`、`ask`、`confirm`、`page`、`choose_files`、`choose_folder`。用法與要注意的事見 `docs/api.md`。
- 外來模組第一次執行前確認（D59 採用、D73）：模組資料夾裡有空檔案 `.unconfirmed`（工作坊安裝時會放，包裡與磁碟上那個模組資料夾底下每一個有 `iplot.py` 的資料夾都放，所以下一層的子模組也會問）時，執行之前先問「『<名稱>』是從外面裝進來的，第一次執行前確認：要執行嗎？」。取消：不執行、不存快照，訊息區記一行，標記留著，下次還問。確定：拿掉標記、照常執行，之後不再問；標記拿不掉（唯讀）也照常執行，只是下次還會再問。標記只是一個空檔案，核心只看它在不在（`tests/test_core.py::test_unconfirmed_module_asks_first`、`::test_unconfirmed_cancel_does_not_run`、`::test_marker_that_cannot_be_removed_does_not_block_the_module`）。
- 需求檔變了，下次啟動重裝 `lib/`（D76，補上 0.4.0 沒接的那一段）：`lib/.installed` 記的 sha256 對不上 `requirements/` 裡任何一份時（「更新」換過需求檔），`main.py` 在開網頁面板之前先用 pip 重裝，裝好直接開面板，不用再重啟。沒有網路、裝不成時（pip 連不上就馬上放棄，不重試），主控台與面板的訊息區都說「介面的套件這次沒有換成新的：…先用現有的開；有網路之後重新啟動 iPLoT 會再試一次。」，照常用現有的 `lib/` 開網頁面板；記號沒動，所以之後每次啟動都會再試，直到裝成。還沒裝過（沒有記號）不算，那是第一次安裝的事；記號檔壞了（不是文字）當作過期、重裝一次，不是啟動時的 traceback；`requirements/` 整個不見就沒得比、不重裝；`--safe` 完全不碰 `lib/`（`tests/test_main.py::test_changed_requirements_reinstall_before_the_panel_opens`、`::test_changed_requirements_offline_opens_the_old_panel_and_keeps_trying`、`tests/test_install.py::test_stale_means_lib_was_installed_from_other_requirements`、`::test_stale_survives_a_garbled_marker_and_a_missing_requirements_folder`）。
- `core/text.py` 多 5 個文字 key：`confirm_foreign`、`cancelled`、`page_unsupported`、`refreshing`、`refresh_failed`。兩個新模組自己說的話寫在模組裡，不在 `core/text.py`。
- 驗收腳本 `tests/acceptance_workshop.py`：0.5.0 驗收裡能自動做的部分，對 `config.py` 裡真的網址跑——等網路上的檔換成剛發佈的、核對每個 zip 的 sha256，再在複本裡開真的視窗按「更新」「重新啟動」「工作坊」、從網路裝一個模組，每一項印證據。跟 `tests/smoke.py` 一樣自己跑，pytest 不收；只在 macOS。
- 測試：新檔 `tests/test_acceptance_script.py`（2 個，驗收腳本裡不開視窗就測得到的部分）、`tests/test_update.py`（32 個測試函式）、`tests/test_workshop.py`（56 個）、`tests/test_publish.py`（26 個）。前兩個用 `file://` 網址與暫存資料夾裡假的 iPLoT；第三個在暫存資料夾裡自己建一個小 repo 來跑 `git archive`。三個都不連網。既有的檔：`tests/test_main.py` 21 → 26、`tests/test_install.py` 14 → 17、`tests/test_web.py` 44 → 45、`tests/test_core.py` 28 → 32、`tests/test_app.py` 13 → 15、`tests/test_bundled.py` 23 → 26、`tests/test_startup.py` 11 → 13、`tests/test_tk_smoke.py` 16 → 17。清單頁（`page.html`）裡的 JS 在 repo 裡沒有會執行它的自動測試，只檢查原始碼（不重新載入頁面、有接住失敗，`tests/test_workshop.py::test_page_does_not_reload_and_handles_failures`；按「取消」回到按鈕原來的字，`::test_cancel_puts_back_the_buttons_own_label`）；實際開視窗試過的（macOS、`file://`）是：清單頁列出索引、安裝後狀態變「已安裝」、覆蓋先問再存快照、按「覆蓋」再按「取消」回到只有一顆「覆蓋」的樣子、關掉清單頁後格子出現、第一次雙擊先問、取消不執行、確定後執行而且標記消失、之後不再問、裝一個帶下一層模組的包之後進到下一層雙擊子模組也先問（取消就不執行）、會蓋到模組自己存的檔的「更新」先在同一列問、取消回到「更新」、再按並確定覆蓋後變「已安裝」、索引裡的「作業系統」那一列沒有按鈕而有那一句說明。
- 模組自己的版本與更新紀錄（D78）：模組資料夾裡可以放 `CHANGELOG.md`（格式跟本檔一樣），發佈工具從最上面那一節取版本與摘要；它跟著模組的 zip 一起裝進去。工作坊的清單頁在那一列的說明底下多一行「這一版：<notes>」。「開工」「作業系統」「打開核心原始碼」各有一份，從 0.5.0 起算。

### 變更
- 後備面板不是安全模式（D75）：網頁面板開不起來（這個平台沒有網頁面板、缺前置條件、pip 失敗、裝完重啟還是不行）時退到的 tkinter 面板，現在照常掃上一層與 `ROOTS`，標題沒有「（安全模式）」；只有 `python3 main.py --safe` 才是安全模式、只掃 `modules/`。0.4.0 是兩種情況都只掃 `modules/`。那一句說明從「網頁面板開不起來：…。已改用安全模式」改成「…已改用備用面板」（`web_failed`）。其他幾句也跟著改，不再叫人用安全模式：`install_failed` 的結尾改成「現在先改用備用面板」；`no_tk` 改成「這個 Python 沒有 tkinter，安全模式與備用面板都開不了；請用 python.org 的版本」；「作業系統」模組的 `webview_ready` 回的原因，Linux 是「這一版的網頁面板還不支援 Linux」，Windows 是「找不到 WebView2 runtime：請先安裝 Microsoft Edge WebView2 Runtime（Windows 11 內建）」（未經實機驗證）。所以在 Linux 上不加 `--safe` 啟動，看到的是完整範圍的 tkinter 面板。
- `ui/web.py` 的預算上限 200 → 220（D68 修訂），理由見上面的數字；其他六項上限不變。
- `main.py`：`safe_mode(home, config, err, note=None)` 改名 `tk_or_exit(home, config, err, safe, note=None)`，多一個 `safe` 參數決定是不是安全模式；`run_web` 多一個 `note` 參數；新增 `refresh`（上面「需求檔變了」那一段）。`ui/install.py` 的 `install` 多一個 `quick` 參數，新增 `stale`。
- `core/scan.py` 整理，行為不變：找圖示檔併進 `module_info`，三處 `try/except OSError` 改成 `contextlib.suppress`。省下的行數讓核心邏輯放得下這一版加的十幾行。

### 修正
這一節是 0.5.0 寫好之後、發佈之前的第二輪審查改的（2026-10-06）。
- 工作坊放回原樣時不會把自己的快照刪掉：以前用精確的 `.history` 認快照資料夾，macOS 不分大小寫，模組資料夾裡本來就有 `.History/` 時，快照寫進它裡面，裝到一半出錯、放回原樣時連 `.History/` 帶快照一起刪掉，那一列還說「快照在 <已經不在的路徑>」。現在認快照資料夾不分大小寫；動手刪之前先確定快照讀得到，讀不到就一樣都不刪，留下來的每個模組資料夾放 `.unconfirmed`，那一列說「沒有裝成，快照讀不到、沒有放回，資料夾現在是新舊混合：<資料夾路徑>」（第二輪審查 R2，`tests/test_workshop.py::test_rollback_keeps_the_snapshot_when_the_folder_already_has_dot_History`（只在不分大小寫的檔案系統上跑）、`::test_rollback_does_not_delete_anything_when_the_snapshot_is_unreadable`）。
- 工作坊存快照時出錯（磁碟滿、`.history/` 不能寫）也是一句話：以前那一列只有「無法安裝：<錯誤>」，`.history/` 裡可能留一個寫到一半的 zip。現在寫到一半的 zip 刪掉，那一列是「無法安裝：<錯誤>；沒有裝成，還沒動到資料夾（存快照時出錯）」（`tests/test_workshop.py::test_a_failed_snapshot_is_one_sentence_and_leaves_no_half_zip`）。
- 工作坊放回原樣時不再弄丟下一層子模組自己的 `.history/`（核心替它存的上一版）：以前任何一層的 `.history/` 都不進快照，放回時整個子模組資料夾先被刪掉，它就回不來，那一列卻說「已從快照放回」。現在只有最上層的 `.history/` 是快照住的地方，下一層的跟著進快照、放回來，比對也算它（`tests/test_workshop.py::test_rollback_keeps_the_history_of_a_module_one_level_down`）。
- 模組資料夾裡有 1980 年以前的檔案時間（zip 記不了）時，工作坊存快照、發佈工具打模組的包照樣成功，那個檔在 zip 裡記成 1980 年：以前工作坊那一列是一句英文、`.history/` 留下半個 zip、那個模組永遠更新不了，發佈工具是 traceback、`--out` 只寫了一半（第三輪審查 I4，`tests/test_workshop.py::test_a_file_from_before_1980_does_not_break_the_snapshot`、`tests/test_publish.py::test_pack_module_handles_files_from_before_1980`）。

### 移除
- 模組用得到的東西一樣都沒有拿掉：`app` 的成員、`View` 的方法、`core/text.py` 的 key 都只有增加。程式內部有兩個名字不在了，都寫在上面的「變更」：`main.py` 的 `safe_mode`（改名 `tk_or_exit`）、`core/scan.py` 的 `_icon_file`（併進 `module_info`）。

### 文件
- 規格 v2.1（`docs/02_重構設計.md`）；`docs/03_設計決定.md`（D59 從延後改為採用，D68、D69、D70 補上這一版的細節，新增 D71–D79；D71 修訂；D77 修正規格 13.3 與 D70 的「已修改」）；`docs/05_使用紀錄.md`（審查找到、這一版先不修的五條待辦）；`docs/06_架構說明與試用.md`、`docs/07_接口與邊界.md`（新增第 10 節「更新」、第 11 節「工作坊」）、`docs/api.md`、`README.md`（新增「更新與工作坊」：怎麼設定、怎麼發佈、怎麼回到舊版）同步。
- 這一版的設計在 `docs/plans/2026-10-05-M2-網頁面板與更新.md` 第 13 節，實作計畫在 `docs/plans/2026-10-05-M2-M3-實作計畫.md` 的第二部分。

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
[0.5.0]: https://github.com/
[0.4.0]: https://github.com/
[0.3.0]: https://github.com/
[0.2.1]: https://github.com/
[0.2.0]: https://github.com/
[0.1.1]: https://github.com/
[0.1.0]: https://github.com/
