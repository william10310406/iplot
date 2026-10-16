"""科學計算的課：按下去＝裝課程套件（分兩批，裝進這個資料夾的 .venv）。下一層是「匯入作業包」（選老師的 t2026fscSpace）、「收作業」（選 TronClass 的 zip）與每一份作業 HK1–HK12，再下一層是全班；按一個學生＝另開視窗跑他的那份。沒有 iPLoT 的助教：python hk_tk.py --batch HK5.zip --kit t2026fscSpace。"""

import pathlib

import hk_tk  # 跟這個檔在同一個資料夾：iPLoT 執行模組時 sys.path[0] 就是這裡

HERE = pathlib.Path(__file__).resolve().parent
ICON = "🎓"


def run(app):
    try:
        python = hk_tk.ensure_venv(HERE / ".venv", say=app.log)
    except RuntimeError as exc:
        app.log(str(exc))
        return
    basic, heavy = hk_tk.course_batches()
    need, label, size = hk_tk.missing(python, basic), "基本那批（HK1–HK8 用的）", hk_tk.BATCH_SIZES[0]
    if not need:
        need, label, size = hk_tk.missing(python, heavy), "第二批（HK9–HK12 用的）", hk_tk.BATCH_SIZES[1]
    if not need:
        app.log("課程套件都在")
        return
    if not app.confirm(f"要裝課程套件的{label}嗎？{'、'.join(need)}。{size}，裝進 科學計算/.venv；"
                       "網路慢的話要很久，裝的時候別的按鈕要等它裝完"):
        app.log("沒裝")
        return
    ok, failed = hk_tk.install(python, need, say=app.log)
    said = hk_tk.summary_of_install(ok, failed)
    if need[0] in basic and hk_tk.missing(python, heavy):
        said += f"；第二批（HK9–HK12 用的 torch 那些，{hk_tk.BATCH_SIZES[1]}）再按一次「科學計算」"
    app.log(said)


def on_files(app, paths):
    hk_tk.import_kit(app, [pathlib.Path(p) for p in paths], HERE)
