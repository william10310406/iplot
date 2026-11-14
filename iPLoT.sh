#!/bin/bash
command -v python3 >/dev/null 2>&1 || { echo "找不到 Python（python3）。iPLoT 需要 Python 3.10 以上，請到 https://www.python.org/downloads/ 下載安裝；裝好之後再開一次 iPLoT。"; exit 1; }
cd "$(dirname "$0")" && exec python3 main.py "$@"
