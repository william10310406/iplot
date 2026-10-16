# Changelog

「科學計算」這個模組的版本紀錄，格式跟 iPLoT 的 CHANGELOG.md 一樣（[Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)）。`tools/publish.py` 取最上面那一節的版本號當工作坊裡的版本，取那一節的第一段當清單頁上的「這一版」。

## [0.1.0] - 2026-10-16

第一版：一門課一顆「科學計算」。按下去裝課程套件（分兩批，裝進這個資料夾自己的 .venv）；下一層的「匯入作業包」選老師的 t2026fscSpace，長出 HK1–HK12；「收作業」選 TronClass 下載的 zip，每個學生長出一顆；按一個學生＝用課程的 Python 另開一個 Tk 視窗，照原樣跑他交的 HKn.txt。沒有 iPLoT 的助教用 `python hk_tk.py --batch HK5.zip --kit t2026fscSpace`。

### 新增
- 舊格式執行器（`hk_tk.py`）：老師的啟動器只留下 HKn.txt 要的那幾個全域與視窗；語法錯（第幾行）、缺套件（pip 指令）、不是 UTF-8、按 RUN 之後在回呼裡出的錯，都跳一個框；print 的東西寫進 `執行紀錄.txt`。
- 匯入作業包、收作業：zip（裡面的 zip 再解一層、中文檔名 cp950 也解得對）、資料夾、檔都收；一人一個資料夾，再收同一個人＝覆蓋；語法錯、交錯份、不是 UTF-8 的照收、列名字；名字含 `..` 或絕對路徑的 zip 成員擋掉。
- 套件：收作業時掃每份的 import（連函式裡的），缺的問一次、一個一個裝，一個裝不了其他照裝；mlx-lm（HK9）只在 Apple Silicon 的 Mac 上裝。
- 批次模式：`hk_tk.py --batch`，收進 zip 旁邊的 `<zip 名>_收件/`，一個 Tk 名單視窗，雙擊開一份。
