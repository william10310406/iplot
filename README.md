# iPLoT — 需要 Python ≥ 3.10（[python.org](https://www.python.org/) 的版本，內含 tkinter）

第一次接觸先看 [docs/06_架構說明與試用.md](docs/06_架構說明與試用.md)。

一個可以放在任何位置的資料夾。啟動後把周圍含有 `iplot.py` 的資料夾變成按鈕；按下去就執行那個檔案，錯了在面板上說清楚；按「＋」用滑鼠長出新按鈕。核心本身不內建任何用途，連 iPLoT 自己的工具都是模組。

## 安裝

1. 裝 Python 3.10 以上，要含 tkinter：
   - macOS：[python.org 的安裝檔](https://www.python.org/downloads/)。Homebrew 或系統內建的版本可能沒有 tkinter，不要用。
   - Windows：python.org 的安裝檔，安裝時勾選 tcl/tk。
   - Linux：發行版的 Python 加上 `python3-tk` 套件（Debian／Ubuntu：`sudo apt install python3-tk`）。
2. 下載這個資料夾，放哪裡都可以（例如 `~/iPLoT`）。
3. 啟動：
   - macOS：雙擊 `iPLoT.command`。第一次 macOS 可能問你要不要打開，選「打開」。
   - Windows：雙擊 `iPLoT.bat`。**未經實機驗證。**
   - Linux：執行 `./iPLoT.sh`。**只由測試驗過參數，沒有在真的 Linux 桌面上跑過。**

三個系統的差別都在 `modules/作業系統/` 這一個模組裡（打開檔案、開終端機、垃圾桶各系統的做法）；現況與怎麼驗見 [docs/07_接口與邊界.md](docs/07_接口與邊界.md) 第 9 節。

不用安裝任何套件。要移除就把資料夾丟進垃圾桶。開發端另外需要 `pip install -r requirements-dev.txt`（pytest、pytest-cov、ruff）。

核心改壞了開不起來時：`python3 main.py --safe`（只掃 `modules/`、不載入拖放套件），再不行就 `git checkout -- core/`。

## 三層

**資料夾裡有 `iplot.py` 就是模組。** 三層都用這一條，資料夾叫什麼模組就叫什麼：

| 層 | 在哪裡 | 顏色 |
|---|---|---|
| 這一層 | `iPLoT/modules/` 底下的資料夾。隨附的五個工具和你自己做的模組都在這 | 藍 |
| 上一層 | iPLoT 資料夾的上一層底下的資料夾。把 iPLoT 放在 `~/`，`Documents` 只要放進一個 `iplot.py` 就變成按鈕 | 紅 |
| 下一層 | 任何模組資料夾裡面再有模組，按鈕旁出現 ▸，點進去看，可以一直往下 | 沿用上一層的顏色 |

要多掃別的地方（例如桌面），打開 `config.py` 在 `ROOTS` 加一行；設定改壞了 iPLoT 會用預設值啟動並告訴你哪裡壞。

## 三下做出第一個模組

1. 按那一組右邊的 **＋**。
2. 打名字（中文、空白都可以；不能含 `/ \ : * ? " < > |`，結尾不能是 `.` 或空白），按確定。
3. 編輯器開了範本，按鈕已經在面板上；按下去，訊息區出現「<名字> 執行了」。

範本只有一個函式：

```python
"""一句話說明這個模組做什麼。"""

def run(app):
    app.log(f"{app.module.title} 執行了")
```

`run` 可省略：沒有 `run` 時最外層程式碼就是按下的動作。課本寫的腳本不改一行就能當模組——按下按鈕就像在模組自己的資料夾裡打 `python3 iplot.py`，只是 `input()` 跳對話框、`print()` 進訊息區：

```python
x = input("年齡")
print("你的年齡是" + x + "歲")
```

改完檔案再按一次就是新版本，不用重啟。`app` 能做的事見 [docs/api.md](docs/api.md)。每次執行前 iPLoT 會把 `iplot.py` 存一份到模組自己的 `.history/`，改壞了找得回來。

## 面板長這樣

```
┌ iPLoT ▸ 開工 ──────────────────────┐   麵包屑，點任一段回上去
│ 這一層                        ＋   │   每一組自己一顆 ＋
│   [ 開工            ]  ▸           │   ▸ 表示底下還有模組
│   [ 打開核心原始碼  ]              │
│   [ ⚠ 整理桌面      ]              │   ⚠ 語法錯誤，按下去看錯在哪
│ 上一層                        ＋   │
│   [ Documents       ]  ▸           │
├────────────────────────────────────┤
│ 模組『整理桌面』第 7 行出錯：       │   訊息區：錯誤和 app.log 都在這
│ NameError，name 'x' is not defined  │
│                      [ 打開檔案 ]   │
└────────────────────────────────────┘
```

左鍵執行；右鍵有「打開程式碼」「在資料夾中顯示」「在終端機打開」；視窗一取得焦點就重掃，在檔案總管建好資料夾點回來，按鈕就在。

## 文件

- [docs/06_架構說明與試用.md](docs/06_架構說明與試用.md)：第一次接觸先看——保留了什麼、改了什麼、四步試用
- [docs/02_重構設計.md](docs/02_重構設計.md)：規格
- [docs/03_設計決定.md](docs/03_設計決定.md)：每個決定的理由
- [docs/api.md](docs/api.md)：模組拿到的 `app`
- [docs/07_接口與邊界.md](docs/07_接口與邊界.md)：可以換零件的地方、各自的規則、怎麼改、怎麼加一個作業系統
- [CHANGELOG.md](CHANGELOG.md)
