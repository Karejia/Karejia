#!/bin/bash
# CryptoAI 快速啟動腳本

echo "╔══════════════════════════════════════════════════╗"
echo "║                                                  ║"
echo "║           CryptoAI 自動交易系統 v2.0              ║"
echo "║                                                  ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# 檢查 Python
if ! command -v python3 &> /dev/null; then
    echo "[錯誤] 未找到 Python 3，請先安裝"
    exit 1
fi

# 檢查依賴
echo "[檢查] 檢查依賴套件..."
pip3 install -q pyyaml requests pandas numpy python-dateutil

# 啟動主程式
echo ""
echo "[啟動] 啟動 CryptoAI 交易器..."
echo ""
python3 main.py
