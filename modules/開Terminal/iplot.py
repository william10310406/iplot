"""在 Terminal 打開 iPLoT 資料夾。示範模組不必經過 app 也能做事：直接用標準庫的 subprocess 就好。"""

import subprocess


def run(app):
    subprocess.run(["open", "-a", "Terminal", str(app.home)], check=False)
