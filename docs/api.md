# `app`：模組看得到的全部

- `api_version = 1`。介面只加不減；要拿掉東西就升 `api_version` 並寫進 `CHANGELOG.md`。
- 每次按下按鈕都新建一個 `App` 傳給 `run(app)`（或 `on_files(app, paths)`）；`module` 與 `memory` 在建立時綁好。
- 本表整理自 `core/app.py` 的 docstring；兩邊不一致時以 `core/app.py` 為準。

| 組 | 成員 | 說明 |
|---|---|---|
| 身分 | `app.module` → `ModuleInfo`（唯讀） | 正在執行的模組的資訊：name、title、folder、file 等（見附錄 B 的 ModuleInfo）。 |
| 身分 | `app.home` → `Path`（唯讀） | iPLoT 程式資料夾。 |
| 身分 | `app.modules` → `tuple[ModuleInfo, ...]`（唯讀） | 目前範圍內所有模組的唯讀清單。 |
| 狀態 | `app.memory` → `dict`（唯讀） | 這個模組自己的 dict，iPLoT 開著期間保留；跨次啟動要留的請寫成檔案放 module.folder。 |
| 畫面 | `app.window` → `Any`（唯讀） | tkinter 主視窗，模組要自己畫東西時用。 |
| 動作 | `app.log(text: str)` → `None` | 寫一行到面板下方的訊息區。 |
| 動作 | `app.open(path: Path)` → `None` | 用 macOS 的 open 打開：資料夾進 Finder，檔案用預設程式。 |
| 動作 | `app.edit(path: Path, line: int | None = None)` → `None` | 用 config.py 的 EDITOR 打開檔案（None 時用系統預設文字編輯器）；資料夾改用 open。 |
| 動作 | `app.run(name: str | ModuleInfo)` → `Result` | 執行目前範圍內另一個模組；找不到或有兩個同名時丟 LookupError，不猜。 |
| 動作 | `app.rescan()` → `None` | 重新掃描並重畫面板；在模組執行中呼叫時，會等這次執行結束後才做。 |
| 問人 | `app.ask(prompt: str, default: str = '')` → `str | None` | 跳出對話框問一個字串；按取消回 None。 |
| 問人 | `app.choose_files()` → `list[Path]` | 跳出檔案選擇視窗；按取消回空清單。 |
| 問人 | `app.choose_folder()` → `Path | None` | 跳出資料夾選擇視窗；按取消回 None。 |

## 幾個約定

- 同步執行，在主視窗的執行緒上。長時間工作會凍住視窗；背景執行是之後的事。
- 不改變工作目錄、不改 `sys.path`。模組要讀自己的檔案用 `app.module.folder / "x.txt"`。
- 跨次執行要保留的東西放 `app.memory`；跨次啟動要保留的寫成檔案放 `app.module.folder`。
- `exit()` / `sys.exit()` 算錯誤，iPLoT 不會關掉。
- `app.module` 是 `ModuleInfo`：`name`（資料夾名稱）、`title`（`TITLE` 或 name）、`description`（docstring 第一段）、`folder`、`file`、`root`、`level`、`has_run`、`accepts_files`、`has_children`、`error`。

## 最小的模組

```python
"""一句話說明這個模組做什麼。"""

def run(app):
    app.log(f"{app.module.title} 執行了")
```
