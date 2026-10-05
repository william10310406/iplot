# `app`：模組看得到的全部

- `api_version = 1`。介面只加不減；要拿掉東西就升 `api_version` 並寫進 `CHANGELOG.md`。
- 每次按下按鈕都新建一個 `App` 傳給 `run(app)`（或 `on_files(app, paths)`）；`module` 與 `memory` 在建立時綁好。
- `def run(app)` 可省略：沒有 `run` 時最外層程式碼就是按下的動作，不用 `app` 也能寫模組（見最後一節）。
- 本表整理自 `core/app.py` 的 docstring；兩邊不一致時以 `core/app.py` 為準。

| 組 | 成員 | 說明 |
|---|---|---|
| 身分 | `app.module` → `ModuleInfo`（唯讀） | 正在執行的模組的資訊：name、title、folder、file 等（見附錄 B 的 ModuleInfo）。 |
| 身分 | `app.home` → `Path`（唯讀） | iPLoT 程式資料夾。 |
| 身分 | `app.modules` → `tuple[ModuleInfo, ...]`（唯讀） | 目前範圍內所有模組的唯讀清單。 |
| 狀態 | `app.memory` → `dict`（唯讀） | 這個模組自己的 dict，iPLoT 開著期間保留；跨次啟動要留的請寫成檔案放 module.folder。 |
| 畫面 | `app.window` → `Any`（唯讀） | tkinter 主視窗，模組要自己畫東西時用。 |
| 動作 | `app.log(text: str)` → `None` | 寫一行到面板下方的訊息區。 |
| 動作 | `app.open(path: Path)` → `None` | 打開：資料夾用檔案總管、檔案用預設程式。由 modules/作業系統 執行。 |
| 動作 | `app.edit(path: Path, line: int | None = None)` → `None` | 用 config.py 的 EDITOR 打開檔案（None 時用系統預設文字編輯器）；資料夾改用 open。 |
| 動作 | `app.reveal(path: Path)` → `None` | 在檔案總管裡顯示並選取這個檔案或資料夾。 |
| 動作 | `app.terminal(path: Path)` → `None` | 在終端機打開這個資料夾。 |
| 動作 | `app.trash(path: Path)` → `Path | None` | 搬到系統垃圾桶，永遠不直接刪除；回傳搬到哪裡（Windows 的資源回收筒沒有路徑，回 None）。 |
| 動作 | `app.run(name: str | ModuleInfo)` → `Result` | 執行目前範圍內另一個模組；找不到或有兩個同名時丟 LookupError，不猜。 |
| 動作 | `app.rescan()` → `None` | 重新掃描並重畫面板；在模組執行中呼叫時，會等這次執行結束後才做。 |
| 問人 | `app.ask(prompt: str, default: str = '')` → `str | None` | 跳出對話框問一個字串；按取消回 None。 |
| 問人 | `app.choose_files()` → `list[Path]` | 跳出檔案選擇視窗；按取消回空清單。 |
| 問人 | `app.choose_folder()` → `Path | None` | 跳出資料夾選擇視窗；按取消回 None。 |

## 幾個約定

- 同步執行，在主視窗的執行緒上。長時間工作（`time.sleep`、長迴圈）會凍住視窗；背景執行是之後的事。
- 按下按鈕 ＝ 在模組自己的資料夾裡執行 `python3 iplot.py`：執行期間工作目錄是模組資料夾（`open("x.txt")` 讀寫的是模組資料夾裡的檔案）、`import helper` 找旁邊的 `helper.py`（改了下次會重讀）、`__name__` 是 `"__main__"`、`sys.argv` 是 `[iplot.py 的路徑]`；跑完全部還原。`app.module.folder / "x.txt"` 照樣可用。
- `input("提示")` 會跳對話框，等同 `app.ask("提示")`；上次問完之後 `print` 的東西會放在提示前面。按取消時 `input()` 丟 `EOFError`（就像真的 `input()` 遇到 Ctrl-D）：不接的話模組以「EOFError，在提問時按了取消」結束，想自己處理就 `except EOFError`（`while True:` 的驗證迴圈請接 `except ValueError`，不要寫什麼都接的 `except:`，不然按取消出不去）；`app.ask` 按取消回 `None`，不丟例外。
- `app.open`、`edit`、`reveal`、`terminal`、`trash` 都是交給 `modules/作業系統` 做的；沒有那個模組時訊息區會記一行、動作不執行；要改這些行為改那個模組，見 `docs/07_接口與邊界.md`。路徑可以是相對的：以呼叫當下的工作目錄為準，執行期間那就是模組自己的資料夾，所以 `app.open(Path("notes.txt"))` 開的是模組資料夾裡的 `notes.txt`。這五個動作啟動外部程式之後不等它結束。動作失敗時（例如系統上沒有那個程式），錯誤顯示在面板上、記在「作業系統」模組名下，呼叫它的模組不會收到例外、會繼續執行，動作的回傳值是 `None`——要確認 `trash` 有沒有搬走，自己看 `path.exists()`。Windows 上的做法未經實機驗證。
- 跨次執行要保留的東西放 `app.memory`；跨次啟動要保留的寫成檔案放 `app.module.folder`。
- `exit()` / `sys.exit(0)` / `quit()` 是正常結束；代碼非零（`exit(1)`、`sys.exit("壞了")`）才算錯誤，面板顯示「模組以 exit(1) 結束」。兩種都不會關掉 iPLoT。
- `app.module` 是 `ModuleInfo`：`name`（資料夾名稱）、`title`（`TITLE` 或 name）、`description`（docstring 第一段）、`folder`、`file`、`root`、`level`、`has_run`、`accepts_files`、`has_children`、`error`。

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
