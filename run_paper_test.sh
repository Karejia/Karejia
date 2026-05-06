#!/usr/bin/env python3
"""
快速測試本地模擬盤模式
自動執行並在前 30 秒內觀察運行情況
"""
import subprocess
import time
import sys

print("="*60)
print("本地模擬盤快速測試")
print("="*60)

# 構建輸入
inputs = "3\n"  # 選擇模擬盤模式

# 執行 main.py
proc = subprocess.Popen(
    ['python3', 'main.py'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    cwd='/mnt/c/Users/ljes9/OneDrive/Desktop/CryptoAI - 複製 (2) - 複製 - 複製'
)

# 發送輸入
output, _ = proc.communicate(inputs, timeout=35)

print(output)

print("\n" + "="*60)
print("測試完成")
print("="*60)
