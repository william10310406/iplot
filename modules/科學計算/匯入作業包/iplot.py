"""選老師的 t2026fscSpace 資料夾，匯入成「科學計算」底下的 HK1–HK12（每份一顆）。老師改了題目再匯入一次：只換題目，收進來的學生不動。"""

import pathlib
import sys

ICON = "📦"
COURSE = pathlib.Path(__file__).resolve().parent.parent
sys.modules.pop("hk_tk", None)  # 每次都讀課程資料夾裡現在那一份
sys.path.insert(0, str(COURSE))
try:
    import hk_tk
finally:
    sys.path.remove(str(COURSE))


def run(app):
    folder = app.choose_folder()
    if folder is None:
        app.log("沒選資料夾，沒有匯入")
        return
    hk_tk.import_kit(app, [folder], COURSE)
