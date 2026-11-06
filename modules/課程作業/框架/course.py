"""課程作業的框架：跟科目、跟作業長什麼樣都無關的部分（讀 課程.py、課的 .venv、面板上的格子、打包）。
只 import 標準庫；從不執行老師或學生的檔，判斷一律用 ast，真的跑一律是子程序。"""

MARK = "課程.py"  # 一門課就是一個有這個檔的資料夾
NO_INSTALL = "CW_NO_INSTALL"  # 設了就不建 venv、不跑 pip，缺了只報
FROM_IPLOT = "CW_FROM_IPLOT"  # iPLoT 另開的子程序：不問、不改檔、文字開視窗
VERSIONS = ".版本"  # 作業資料夾裡框架留的版本（D135）
SENT = "發出去的"  # 一門課裡放學生包 zip 的資料夾
KEEP_PY = 20  # .版本/ 裡作業檔的 .py 最多留幾份
