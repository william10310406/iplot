# Changelog

「核心」這個模組的版本紀錄，格式跟 iPLoT 的 CHANGELOG.md 一樣（[Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)）。`tools/publish.py` 取最上面那一節的版本號當工作坊裡的版本，取那一節的第一段當清單頁上的「這一版」。

## [Unreleased]

## [1.0.0] - 2026-11-25

iPLoT 的核心搬進這個資料夾，變成一個隨附的模組（D167）。iPLoT 資料夾的 main.py 只是開機程式：先用這一份，載不起來就退回上一次開得起來的那一份（`.local/核心.good/`），再不行用包裡帶的種子。

### 新增
- 按這顆：說出核心的版本，打開它的程式碼。取代原本的「打開核心原始碼」。
