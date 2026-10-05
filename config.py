# iPLoT 設定。改壞了 iPLoT 會用預設值啟動並告訴你哪裡壞。

ROOTS = ["modules", ".."]      # 去哪裡找模組，相對於 iPLoT 資料夾；絕對路徑也可以，例如 "~/Desktop"
EDITOR = None                  # None = 系統預設文字編輯器；或例如 ["code", "-g", "{file}:{line}"]
HISTORY_KEEP = 20              # 每個模組保留幾份上一版
UPDATE_URL = None              # 「更新」從哪裡看有沒有新版：update.json 的網址；None = 不設，按「更新」時會說怎麼填
WORKSHOP_URL = None            # 「工作坊」的模組清單：index.json 的網址；None = 不設
