#!/usr/bin/env bash
# 一鍵本機啟動所有 LINE/LIFF 介面 + Demo Hub（純靜態，mock 模式）。
set -e
cd "$(dirname "$0")"
PORT="${1:-8080}"
echo "浪浪 LINE 介面 · http://localhost:${PORT}"
echo "  Demo Hub          → http://localhost:${PORT}/demo/"
echo "  工作人員動物輸入  → http://localhost:${PORT}/staff-animal/"
echo "  志工選單          → http://localhost:${PORT}/volunteer/"
echo "  領養人選單        → http://localhost:${PORT}/adopter/"
echo "（Ctrl-C 結束）"
python3 -m http.server "${PORT}"
