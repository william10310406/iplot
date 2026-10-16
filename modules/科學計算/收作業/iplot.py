"""選 TronClass 下載的 zip（可以多選），收進對應的那一份作業：一人一個資料夾，在 HKn 的下一層。zip 的檔名裡看得出 HKn 就照它，看不出來會問一次。"""

import pathlib
import sys

ICON = "📥"
COURSE = pathlib.Path(__file__).resolve().parent.parent
sys.modules.pop("hk_tk", None)  # 每次都讀課程資料夾裡現在那一份
sys.path.insert(0, str(COURSE))
try:
    import hk_tk
finally:
    sys.path.remove(str(COURSE))


def run(app):
    paths = app.choose_files()
    if not paths:
        app.log("沒選檔，沒有收")
        return
    hk_tk.collect_files(app, paths, COURSE)
