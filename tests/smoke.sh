#!/bin/bash
# 規格 §12 從零啟動情境 1–6：每個情境複製一份乾淨的 iPLoT 到暫存目錄，真的啟動 8 秒，
# 看還活著沒、stderr 乾不乾淨。只驗「啟動後活著」；按下按鈕之後的行為由 tests/test_startup.py 驗（D43）。
# 用法：bash tests/smoke.sh    （PYTHON 環境變數可指定直譯器，預設 python3）
PY="${PYTHON:-python3}"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'kill $(jobs -p) 2>/dev/null; rm -rf "$WORK"' EXIT   # 不留下任何 iPLoT 視窗
FAIL=0

fresh() {  # 乾淨副本：只有 main.py、config.py、core/、空的 modules/；上一層只有它自己
    local dir="$WORK/$1/iPLoT"
    rm -rf "$WORK/$1"
    mkdir -p "$dir/modules"
    cp "$SRC/main.py" "$SRC/config.py" "$dir/" && cp -R "$SRC/core" "$dir/core"
    rm -rf "$dir/core/__pycache__"
    echo "$dir"
}

check() {  # check 編號 說明 資料夾 指令...
    local n="$1" what="$2" dir="$3"; shift 3
    local err="$WORK/$n.stderr" status
    (cd "$dir" && exec "$@" >/dev/null 2>"$err") &   # exec：$! 才是 Python 本身，kill 得到它
    local pid=$!
    sleep 8
    if kill -0 "$pid" 2>/dev/null; then
        status="活著"
        kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
    else
        wait "$pid"; status="死了，結束碼 $?"; FAIL=1
    fi
    if [ -s "$err" ]; then
        FAIL=1
        printf '情境 %s（%s）：%s，stderr 不乾淨：\n' "$n" "$what" "$status"
        sed 's/^/    /' "$err"
    else
        printf '情境 %s（%s）：%s，stderr 乾淨\n' "$n" "$what" "$status"
    fi
}

d=$(fresh 1)
check 1 "空 modules/、空上一層" "$d" "$PY" main.py

d=$(fresh 2)
printf 'ROOTS = ["modules", "/nonexistent"]\n' > "$d/config.py"
check 2 "ROOTS 含不存在的路徑" "$d" "$PY" main.py

d=$(fresh 3)
printf 'ROOTS = [\n' > "$d/config.py"
check 3 "config.py 語法錯誤" "$d" "$PY" main.py

d=$(fresh 4)
mkdir "$d/modules/壞掉" && printf 'def run(app)\n    pass\n' > "$d/modules/壞掉/iplot.py"
check 4 "只有一個語法錯誤的模組" "$d" "$PY" main.py

d=$(fresh 5)
mkdir "$d/modules/炸" && printf 'def run(app):\n    1/0\n' > "$d/modules/炸/iplot.py"
check 5 "模組 run 丟例外" "$d" "$PY" main.py

d=$(fresh 6)
check 6 "沒裝 tkinterdnd2" "$d" "$PY" -c "import sys, runpy; sys.modules['tkinterdnd2'] = None; runpy.run_path('main.py', run_name='__main__')"

if [ "$FAIL" -eq 0 ]; then echo "smoke：6 個情境全部活著、stderr 乾淨"; else echo "smoke：有情境失敗"; fi
exit "$FAIL"
