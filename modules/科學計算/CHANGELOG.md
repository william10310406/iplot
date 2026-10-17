# Changelog

「科學計算」這個模組的版本紀錄，格式跟 iPLoT 的 CHANGELOG.md 一樣（[Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)）。`tools/publish.py` 取最上面那一節的版本號當工作坊裡的版本，取那一節的第一段當清單頁上的「這一版」。

## [0.1.0] - 2026-10-16

第一版：一門課一顆「科學計算」。按下去裝課程套件（分兩批，裝進這個資料夾自己的 .venv）；下一層的「匯入作業包」選老師的 t2026fscSpace，長出 HK1–HK12；「收作業」選 TronClass 下載的檔（一人一個 .zip 或 .txt，或全班一包的 zip），每個學生長出一顆；按一個學生＝用課程的 Python 另開一個 Tk 視窗，照原樣跑他交的 HKn.txt；照 docs/09 寫的新格式作業也收得進來，由新格式的殼 hk_page.py 開 matplotlib 的視窗。沒有 iPLoT 的助教用 `python hk_tk.py --batch HK5.zip --kit t2026fscSpace`。

### 新增
- 課程模組（`iplot.py`）：按下去（第一次先建 `.venv`）裝基本那批（numpy、matplotlib、scipy、Pillow、opencv-python、pandas、scikit-learn、PyWavelets，HK1–HK8 用的，約 480 MB）；都在了再按一次，才問第二批（torch、pykan、PyYAML、tqdm、torchdiffeq，Apple Silicon 的 Mac 多 mlx-lm；HK9–HK12 用的，約 1.1 GB）。確認的句子寫著大小，也說裝的時候別的按鈕要等。PyYAML、tqdm 是 pykan 沒寫、但 `import kan` 要的。在 Apple Silicon 的 Mac 上兩批裝完，`.venv` 約 1.6 GB。
- 下一層的兩顆按鈕：「匯入作業包」選資料夾；「收作業」選檔（可以多選），HKn 從檔名看，看不出來問一次，還沒匯入的那一份先放墊片。0.5.1 的面板沒有拖放，所以是兩顆按鈕；`on_files` 留著（「科學計算」的是匯入、每個 HKn 的是收作業），從「互通」的命令列叫得到。
- 舊格式執行器（`hk_tk.py`）：老師的啟動器只留下 HKn.txt 要的那幾個全域與視窗；語法錯（第幾行）、缺套件（pip 指令）、不是 UTF-8、按 RUN 之後在回呼裡出的錯，都跳一個框；print 的東西寫進 `執行紀錄.txt`。
- 匯入作業包、收作業：zip（裡面的 zip 再解一層、中文檔名 cp950 也解得對）、資料夾（收作業時裡面的 zip 也解）、檔都收。收作業時一樣東西（檔、zip、資料夾）是一個學生，名字是它的名字；名字就是 HKn（HK5.zip、資料夾 HK5）、或裝著兩樣以上又沒有 HKn.txt 的，是全班一包（名字只是含著 HKn 的 HK5_王小明.zip 是一個學生）；一個人交的 zip 裡收檔名就叫 HKn.txt 的那一份，其他的（備份、自測、筆記）不收、那一句列名字；學生那一層收不到的（不是 .py/.txt 的檔、解不開或第三層沒解的 zip、底下沒有 .py/.txt 的資料夾）也列名字；名字看起來是檔名時句尾提示。再收同一個人＝覆蓋；語法錯、交錯份、不是 UTF-8 的照收、列名字；名字含 `..` 或絕對路徑的 zip 成員擋掉。
- 套件：收作業時掃每份的 import（連函式裡的），缺的問一次、一個一個裝，一個裝不了其他照裝；mlx-lm（HK9）只在 Apple Silicon 的 Mac 上裝。
- 批次模式：`hk_tk.py --batch`（給全班一包的 zip，或放一人一個 .zip、.txt 的資料夾加 `--hk`），收進它旁邊的 `<名字>_收件/`，一個 Tk 名單視窗，雙擊開一份。
- 新格式的殼 v0（`hk_page.py`，頂層只 import 標準庫）：`ensure` 把缺的套件裝進正在跑的這個 Python（不在 venv 裡加 `--user`）；學生自己跑自己的 `HKn.py` 時，把 import 了、`REQUIRES` 沒寫的補進那一行（其他行一個 byte 都不動、註解留著）；在 iPLoT 的面板程序裡不裝、不改檔，缺了就交給課程的 `.venv` 另開程序。`main` 在終端機列出 case 選一個（0 是全部；`--case <名>`、`--all` 不問），每個 case 先印文字與數字，有 `draw` 就開一個 matplotlib 視窗、關掉才下一個；一個 case 出錯印 traceback、接著跑下一個。
- 殼在 iPLoT 裡：`show` 用課程的 `.venv` 另開程序跑同一個檔，帶 `--all` 與 `HK_FROM_IPLOT=1`：不問 case、不改檔、不裝進 iPLoT 自己的 Python，文字與數字也開在視窗裡；`collect` 轉給課程資料夾的 `hk_tk.collect`（收作業只有一份程式）。`python hk_page.py --check <檔>`：規範第 7 節的靜態檢查（名字、固定尾段、tkinter／turtle、`plt.show`／`input`／`os.chdir`、絕對路徑、`REQUIRES` 漏寫、`DATA` 的資料夾），每條一句，不過回 1。
- 收作業兩種格式都收（D99）：用 ast 分辨、不執行（頂層有 `HOMEWORK = dict(…)` 是新格式，有 `def HKn(` 又用到 `LF_subWIN` 是舊格式），同一個 `HKn/` 底下兩種並存。新格式的學生資料夾裡是他的檔（存成 `iplot.py`）、課程的 `hk_page.py` 與老師的 `HKnSpace/` 複本，沒有墊片；學生 zip 裡自己帶的 `hk_page.py` 不收。同一個人上次舊、這次新（或反過來）就整個資料夾重建，只動真的學生資料夾（名字不分大小寫比，老師的東西不會被蓋掉或砍掉）。套件另外讀 `REQUIRES` 那一行；`--check` 不過的照收、列名字與第一條；有新格式時，總結那句多「舊格式 a、新格式 b」。批次名單也開得了新格式的學生，標「檢查不過」。
- `examples/`：HK2（靜態圖：電偶極、有限差分解 Poisson 方程）、HK6（動畫：淺水波 1D、2D）、HK8（純文字：n-gram）從舊格式搬成新格式，各兩個 case，`--check` 都過。物理照抄、只換殼；舊格式 `ich==1` 那段畫出來空白或畫壞的地方，`draw` 照 `ich==0` 要畫的畫。是規範的對照物，也是下一份作業的起點；這個資料夾沒有 `iplot.py`，面板上不會出現。
- 作業規範 v0（repo 的 `docs/09_作業規範.md`）：一份作業＝一個 Python 檔；上半是作業（六個名字 `REQUIRES`、`NAME`、`DOCS`、`NOTE`、`DATA`、`CASES`，三個函式 `compute`、`draw`、`stats`），下半六行固定、不改；學生 `python3 HKn.py`、助教在 iPLoT 裡按、批次名單跑的都是同一個檔。附舊格式→新格式的對照表與發作業前的檢查；下學期畫面換成網頁時約定不變。
- 量出來的數字：`tests/test_homework.py` 163 個測試、`tests/test_hk_page.py` 62 個；`hk_tk.py` 1130 行、`hk_page.py` 464 行；`examples/` 的 HK2、HK6、HK8 各 181、252、127 行。

### 這一版沒有做
- 新格式的網頁畫面：殼 v0 的畫面是 matplotlib 自己的視窗，網頁是下學期的殼 v1。舊格式的檔不會自動轉成新格式。
- 老師的 `HKnSpace/` 每個學生複製一份，沒有用硬連結省空間（佔多少還沒量）。
- Windows 未經實機驗證（助教那條路只用標準庫與 venv）；HK9 要 Apple Silicon 的 Mac（mlx-lm），別的機器不裝 mlx-lm，HK9 看不了。
