"""更新 iPLoT 的核心：只換 core/、ui/、main.py、requirements/ 四樣，換之前先備份到 .backup/。
自己的模組、config.py、custom.css 都不會被動到。更新來源寫在 config.py 的 UPDATE_URL。

做法都在旁邊的 update.py；這個檔只負責問、說、串起來。按了才會連網，不會自己去檢查有沒有新版。"""
import http.client
import zipfile

import update

ICON = "⬆️"


def run(app):
    url = app.config.update_url
    if not url:
        return app.log("尚未設定更新來源：在 config.py 的 UPDATE_URL 填 update.json 的網址")
    on_disk = update.installed_version(app.home) or app.version  # 剛更新過、還沒重新啟動時，磁碟上的比執行中的新
    try:  # 連網的這一段：讀 update.json、問、下載
        info = update.fetch_json(url)
        latest = str(info["version"])
        if not update.newer(on_disk, latest):
            if on_disk != app.version:
                return app.log(f"已經換成 {on_disk} 了，執行「重新啟動」就會用新版")
            return app.log(f"已是最新（{app.version}）")
        if not app.confirm(f"有新版 {latest}（現在是 {on_disk}）：\n{info.get('notes', '')}\n\n要更新嗎？"):
            return app.log("已取消更新")
        package = update.download(info["zip_url"], app.home / ".backup" / f"download-{latest}.zip", info["sha256"])
    except http.client.InvalidURL as exc:
        return app.log(f"網址寫錯了，沒有更新：{exc}（看 config.py 的 UPDATE_URL，或 update.json 裡的 zip_url）")
    except KeyError as exc:
        return app.log(f"更新來源的 update.json 少了 {exc} 這一項，沒有更新")
    except ValueError as exc:  # sha256 對不上、update.json 不是 JSON
        return app.log(f"沒有更新：{exc}（update.json 或下載的檔案有問題）")
    except update.NETWORK as exc:
        return app.log(f"連不上更新來源，或下載到一半斷了，沒有更新：{getattr(exc, 'reason', exc)}")
    try:  # 動到檔案的這一段：備份、換上去
        saved = update.backup(app.home, on_disk)
        update.apply(app.home, package)
    except zipfile.BadZipFile:
        return app.log("下載的檔案不是 zip，沒有更新")
    except ValueError as exc:  # zip 的內容不對
        return app.log(f"沒有更新：{exc}（下載的包有問題）")
    app.log(f"已更新到 {latest}，執行「重新啟動」就會用新版。舊版備份在 .backup/{saved.name}/")
