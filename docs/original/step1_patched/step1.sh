#!/bin/bash
# tests/step1.sh — 驗收「空無一物也開得起來，而且模組出錯時看得見」
# 用法：bash tests/step1.sh
# 選用環境變數：
#   STEP1_SHOT_DIR=<目錄>  把情況 1 的截圖 s1.png 複製到這個目錄（暫存目錄跑完會刪掉）
# macOS 沒有 timeout，改用「背景執行 & + sleep + kill -0」判斷 8 秒後是否還活著。
# 執行時螢幕上會短暫跳出 Tk 視窗，正常。

SRC=/Users/waiheng/Documents/6000_work/iplot
WAIT=8
export PYTHONUNBUFFERED=1

TMPS=()
PIDS=()
# 中途 Ctrl-C 時，背景的 python 會忽略 SIGINT 而留下孤兒 Tk 視窗，所以先 kill 再刪暫存檔
cleanup() {
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
  for d in "${TMPS[@]}"; do rm -rf "$d"; done
}
trap cleanup EXIT

# 建立 <T>/iPLoT/，從 SRC 複製當下的 iPLoT.py 和 iPLoT.txt；$1=yes 時另外建空的 <T>/Desktop/
# 結果放在全域變數 T（不用 $(...)，否則 TMPS 在子 shell 裡記不住，跑完刪不掉）
make_env() {
  T=$(mktemp -d)
  TMPS+=("$T")
  mkdir "$T/iPLoT"
  cp "$SRC/iPLoT.py" "$SRC/iPLoT.txt" "$T/iPLoT/"
  [ "$1" = yes ] && mkdir "$T/Desktop"
  echo "暫存目錄: $T"
}

# run_case <工作目錄> <指令...>；設定 ALIVE、CODE、OUT、ERR
# 若 SHOT 有值：啟動 3 秒後 screencapture -x "$SHOT"
run_case() {
  local dir=$1; shift
  OUT=$(mktemp); ERR=$(mktemp); TMPS+=("$OUT" "$ERR")
  echo "工作目錄: $dir"
  echo "指令: PYTHONUNBUFFERED=1 $*"
  (cd "$dir" && exec "$@") >"$OUT" 2>"$ERR" &
  local pid=$!
  PIDS+=("$pid")
  if [ -n "$SHOT" ]; then
    sleep 3
    screencapture -x "$SHOT" && echo "截圖: $SHOT"
    sleep $((WAIT-3))
  else
    sleep $WAIT
  fi
  if kill -0 $pid 2>/dev/null; then
    ALIVE=yes; kill $pid; wait $pid; CODE=$?
    echo "${WAIT} 秒後還活著: 是（已 kill）"
    echo "結束碼: $CODE（kill 之後 wait 取得，非程式自行結束）"
  else
    ALIVE=no; wait $pid; CODE=$?
    echo "${WAIT} 秒後還活著: 否（自行結束）"
    echo "結束碼: $CODE"
  fi
  echo "----- stdout -----"; cat "$OUT"
  echo "----- stderr -----"; cat "$ERR"
  echo "------------------"
}

RESULTS=()
verdict() { # $1=情況編號 $2=原因（空字串代表通過）
  if [ -z "$2" ]; then echo "判定: PASS"; RESULTS+=("情況 $1: PASS")
  else echo "判定: FAIL —$2"; RESULTS+=("情況 $1: FAIL —$2"); fi
}

echo "python3: $(command -v python3)  $(python3 -c 'import sys;print(sys.version.split()[0])')"

# ---------------------------------------------------------------- 情況 1
echo; echo "===== 情況 1：只有 <T>/iPLoT/，沒有 <T>/Desktop/ ====="
make_env no
SHOT="$T/s1.png" run_case "$T/iPLoT" python3 iPLoT.py
if [ -n "$STEP1_SHOT_DIR" ] && [ -f "$T/s1.png" ]; then
  cp "$T/s1.png" "$STEP1_SHOT_DIR/s1.png" && echo "截圖已複製到 $STEP1_SHOT_DIR/s1.png"
fi
r=""
[ "$ALIVE" = yes ] || r="$r 沒有活過 ${WAIT} 秒;"
[ -s "$ERR" ] && r="$r stderr 不是空的;"
verdict 1 "$r"

# ---------------------------------------------------------------- 情況 2
echo; echo "===== 情況 2：<T>/iPLoT/ 加上空的 <T>/Desktop/ ====="
make_env yes
run_case "$T/iPLoT" python3 iPLoT.py
r=""
[ "$ALIVE" = yes ] || r="$r 沒有活過 ${WAIT} 秒;"
[ -s "$ERR" ] && r="$r stderr 不是空的;"
verdict 2 "$r"

# ---------------------------------------------------------------- 情況 3
echo; echo "===== 情況 3：在原位 $SRC 執行 ====="
run_case "$SRC" python3 iPLoT.py
r=""
[ "$ALIVE" = yes ] || r="$r 沒有活過 ${WAIT} 秒;"
[ -s "$ERR" ] && r="$r stderr 不是空的;"
grep -qi 'iplot/iplot\.txt$' "$OUT" && r="$r stdout 有以 iplot/iplot.txt 結尾的行;"
verdict 3 "$r"

# ---------------------------------------------------------------- 情況 4
echo; echo "===== 情況 4：情況 2 加上會出錯的 <T>/David/David.txt ====="
make_env yes
mkdir "$T/David"
cat > "$T/David/David.txt" <<'EOF'
print('[David] line 1')
1/0
print('[David] line 3 should not appear')
EOF
echo "David.txt 內容:"; cat -n "$T/David/David.txt"
run_case "$T/iPLoT" python3 iPLoT.py
r=""
[ "$ALIVE" = yes ] || r="$r 沒有活過 ${WAIT} 秒;"
grep -qF 'David.txt", line 2' "$ERR" || r="$r stderr 沒有 David.txt\", line 2;"
grep -qF 'ZeroDivisionError' "$ERR" || r="$r stderr 沒有 ZeroDivisionError;"
grep -qF '[David] line 1' "$OUT" || r="$r stdout 沒有 [David] line 1;"
grep -qF '[David] line 3' "$OUT" && r="$r stdout 出現了 [David] line 3;"
verdict 4 "$r"

# ---------------------------------------------------------------- 情況 5
echo; echo "===== 情況 5：情況 2，但模擬沒裝 tkinterdnd2 ====="
make_env yes
DND=$(python3 -c "import tkinterdnd2;print(tkinterdnd2.__file__)" 2>&1)
USERSITE=$(python3 -c "import site;print(site.getusersitepackages())")
echo "tkinterdnd2 位置: $DND"
echo "user site: $USERSITE"
case "$DND" in
  "$USERSITE"/*)
    echo "→ 裝在 user site，用 python3 -s 停用 user site"
    run_case "$T/iPLoT" python3 -s iPLoT.py ;;
  *)
    echo "→ 不在 user site，用 sys.modules['tkinterdnd2']=None 遮掉"
    run_case "$T/iPLoT" python3 -c "import sys,runpy; sys.modules['tkinterdnd2']=None; runpy.run_path('iPLoT.py',run_name='__main__')" ;;
esac
r=""
[ "$ALIVE" = no ] || r="$r 程式沒有自行結束;"
grep -qF 'Traceback' "$ERR" || r="$r stderr 沒有 traceback;"
grep -qF 'ModuleNotFoundError' "$ERR" || r="$r stderr 沒有 ModuleNotFoundError;"
[ "$CODE" != 0 ] || r="$r 結束碼是 0;"
verdict 5 "$r"

# ---------------------------------------------------------------- 總結
echo; echo "===== 總結 ====="
printf '%s\n' "${RESULTS[@]}"
for x in "${RESULTS[@]}"; do case "$x" in *FAIL*) exit 1;; esac; done
exit 0
