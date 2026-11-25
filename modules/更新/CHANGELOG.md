# Changelog

「更新」這個模組的版本紀錄，格式跟 iPLoT 的 CHANGELOG.md 一樣（[Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)）。`tools/publish.py` 取最上面那一節的版本號當工作坊裡的版本，取那一節的第一段當清單頁上的「這一版」。

## [Unreleased]

## [1.0.1] - 2026-11-25

iPLoT 1.0 起核心在 `modules/核心/`（D167）：更新直接換掉它，連同最上層的種子 `core/`、`ui/`；核心記的「上一份開得起來的」（`.local/`）跟著留下，新的開不起來時還退得回去。現在是哪一版也看 `modules/` 裡的核心。

## [1.0.0] - 2026-11-25

按了才連網，把 iPLoT 換成新版（D69）：先備份、驗 sha256，換到一半出錯就全部放回。這以前的版本沒有記錄；從 1.0 起補上，版本號跟著 iPLoT。
