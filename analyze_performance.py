#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CryptoAI 交易績效分析腳本
分析 trades.csv 並生成詳細的統計報告與可視化圖表
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import numpy as np
import warnings
import os
import sys

# 忽略警告
warnings.filterwarnings("ignore")

# 設置 matplotlib 支持中文顯示
# 嘗試多種常見中文字體
plt.rcParams['font.sans-serif'] = [
    'WenQuanYi Micro Hei', 
    'WenQuanYi Zen Hei',
    'Arial Unicode MS', 
    'DejaVu Sans',
    'SimHei',
    'Microsoft YaHei'
]
plt.rcParams['axes.unicode_minus'] = False

def analyze_crypto_ai_data(csv_path='trades.csv'):
    """分析 CryptoAI 交易數據"""
    
    print("=" * 70)
    print("📊 CryptoAI 交易績效分析工具")
    print("=" * 70)
    
    # 1. 讀取數據
    print(f"\n📥 正在讀取數據：{csv_path} ...")
    
    if not os.path.exists(csv_path):
        print(f"❌ 錯誤：找不到文件 {csv_path}")
        print(f"   當前工作目錄：{os.getcwd()}")
        return
    
    try:
        # 讀取 CSV，自動處理 BOM
        df = pd.read_csv(csv_path, encoding='utf-8-sig')
        print(f"✓ 成功讀取 {len(df)} 筆記錄")
    except Exception as e:
        print(f"❌ 讀取失敗：{e}")
        return
    
    # 2. 數據預處理
    print("\n🔧 正在處理數據...")
    
    # 轉換時間格式 (處理 / 和 - 混合格式)
    df['timestamp_open'] = pd.to_datetime(df['timestamp_open'].str.replace('/', '-'))
    
    # 過濾掉沒有平倉的記錄 (exit_price 為空或 NaN)
    df_closed = df[df['exit_price'].notna() & (df['exit_price'] != '')].copy()
    
    if df_closed.empty:
        print("⚠️ 沒有找到已平倉的交易記錄。")
        return
    
    print(f"✓ 已平倉交易：{len(df_closed)} 筆")
    
    # 計算淨損益
    if 'net_pnl' in df_closed.columns:
        df_closed['pnl'] = pd.to_numeric(df_closed['net_pnl'], errors='coerce')
    elif 'net_pnl_usdt' in df_closed.columns:
        df_closed['pnl'] = pd.to_numeric(df_closed['net_pnl_usdt'], errors='coerce')
    else:
        df_closed['pnl'] = pd.to_numeric(df_closed['pnl_usdt'], errors='coerce')
    
    # 去除 NaN 值
    df_closed = df_closed.dropna(subset=['pnl'])
    
    # 按時間排序
    df_closed = df_closed.sort_values('timestamp_open')
    
    # 計算累計損益
    df_closed['cum_pnl'] = df_closed['pnl'].cumsum()
    
    # 計算持倉時間（分鐘）
    if 'holding_minutes' in df_closed.columns:
        df_closed['duration_min'] = pd.to_numeric(df_closed['holding_minutes'], errors='coerce').fillna(0)
    else:
        df_closed['duration_min'] = (df_closed['timestamp_close'] - df_closed['timestamp_open']).dt.total_seconds() / 60
    
    # 3. 核心指標計算
    print("\n📈 計算績效指標...")
    
    total_trades = len(df_closed)
    winning_trades = df_closed[df_closed['pnl'] > 0]
    losing_trades = df_closed[df_closed['pnl'] <= 0]
    
    win_count = len(winning_trades)
    loss_count = len(losing_trades)
    win_rate = win_count / total_trades if total_trades > 0 else 0
    
    total_pnl = df_closed['pnl'].sum()
    avg_pnl = df_closed['pnl'].mean()
    max_win = df_closed['pnl'].max()
    max_loss = df_closed['pnl'].min()
    
    # 盈虧比
    avg_win = winning_trades['pnl'].mean() if win_count > 0 else 0
    avg_loss = abs(losing_trades['pnl'].mean()) if loss_count > 0 else 0
    profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0
    
    # 最大回撤
    df_closed['peak'] = df_closed['cum_pnl'].cummax()
    df_closed['drawdown'] = df_closed['cum_pnl'] - df_closed['peak']
    max_drawdown = df_closed['drawdown'].min()
    
    # 期望值
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    
    # 4. 輸出統計報告
    print("\n" + "=" * 70)
    print("📈 CryptoAI 交易績效分析報告")
    print("=" * 70)
    print(f"📅 時間區間：{df_closed['timestamp_open'].min()} 至 {df_closed['timestamp_open'].max()}")
    print(f"⏱️  運行總時長：{(df_closed['timestamp_open'].max() - df_closed['timestamp_open'].min()).total_seconds() / 3600:.2f} 小時")
    print(f"🔢 總交易筆數：{total_trades} 筆")
    print(f"✅ 獲利筆數：{win_count} | ❌ 虧損筆數：{loss_count}")
    print("-" * 70)
    print(f"💰 總淨損益：{total_pnl:+.2f} USDT")
    print(f"📊 平均單筆盈虧：{avg_pnl:+.2f} USDT")
    print(f"🎯 勝率：{win_rate*100:.2f}%")
    print(f"⚖️  盈虧比 (Avg Win / Avg Loss): {profit_loss_ratio:.2f}")
    print(f"📉 最大單筆虧損：{max_loss:.2f} USDT")
    print(f"📈 最大單筆獲利：{max_win:.2f} USDT")
    print(f"📉 最大回撤 (Max Drawdown): {max_drawdown:.2f} USDT")
    print(f"🔮 數学期望值 (Expectancy): {expectancy:+.2f} USDT / 筆")
    print("=" * 70)
    
    # 5. 進階分析：哪個幣最賠錢？
    print("\n🔥 虧損熱點分析 (Top 5 虧損標的)")
    symbol_stats = df_closed.groupby('symbol')['pnl'].sum().sort_values(ascending=True)
    print(symbol_stats.head(5).to_string())
    
    print("\n💰 獲利熱點分析 (Top 5 獲利標的)")
    print(symbol_stats.tail(5).sort_values(ascending=False).to_string())
    
    # 6. 出場原因分佈
    print("\n🚪 出場原因分佈")
    if 'exit_reason' in df_closed.columns:
        exit_reasons = df_closed['exit_reason'].value_counts()
        print(exit_reasons.to_string())
    else:
        print("（無出場原因數據）")
    
    # 7. 每小時績效分佈
    print("\n⏰ 每小時交易績效分佈")
    df_closed['hour'] = df_closed['timestamp_open'].dt.hour
    hourly_stats = df_closed.groupby('hour').agg({
        'pnl': ['sum', 'mean', 'count']
    }).round(2)
    hourly_stats.columns = ['Net_PnL', 'Avg_PnL', 'Count']
    print(hourly_stats.to_string())
    
    # 8. 繪圖
    print("\n🎨 正在生成圖表...")
    
    fig, axs = plt.subplots(3, 1, figsize=(14, 10))
    fig.suptitle('CryptoAI 交易績效分析', fontsize=16, fontweight='bold')
    
    # 圖 1: 資金曲線
    axs[0].plot(df_closed['timestamp_open'], df_closed['cum_pnl'], label='Cumulative PnL', color='blue', linewidth=1.5)
    axs[0].fill_between(df_closed['timestamp_open'], df_closed['cum_pnl'], 0, 
                        where=(df_closed['cum_pnl'] > 0), interpolate=True, color='green', alpha=0.2)
    axs[0].fill_between(df_closed['timestamp_open'], df_closed['cum_pnl'], 0, 
                        where=(df_closed['cum_pnl'] < 0), interpolate=True, color='red', alpha=0.2)
    axs[0].set_title(f'資金曲線 (總損益：{total_pnl:+.2f} USDT)', fontsize=12)
    axs[0].set_ylabel('PnL (USDT)')
    axs[0].grid(True, alpha=0.3)
    axs[0].axhline(0, color='black', linewidth=0.8)
    
    # 圖 2: 每小時交易分佈
    hourly_pnl = df_closed.groupby('hour')['pnl'].sum()
    colors = ['green' if x > 0 else 'red' for x in hourly_pnl.values]
    axs[1].bar(hourly_pnl.index.astype(int), hourly_pnl.values, color=colors, alpha=0.7)
    axs[1].set_title('每小時淨損益分佈', fontsize=12)
    axs[1].set_xlabel('Hour (UTC)')
    axs[1].set_ylabel('Net PnL (USDT)')
    axs[1].grid(True, alpha=0.3, axis='y')
    axs[1].axhline(0, color='black', linewidth=0.8)
    
    # 圖 3: 盈虧分佈直方圖
    axs[2].hist(df_closed['pnl'], bins=30, color='skyblue', edgecolor='black', alpha=0.7)
    axs[2].set_title(f'單筆交易盈虧分佈 (共 {total_trades} 筆)', fontsize=12)
    axs[2].set_xlabel('PnL (USDT)')
    axs[2].set_ylabel('交易次數')
    axs[2].grid(True, alpha=0.3)
    axs[2].axvline(0, color='red', linestyle='--', linewidth=1)
    
    plt.tight_layout()
    
    # 保存圖片
    output_img = 'performance_report.png'
    plt.savefig(output_img, dpi=150, bbox_inches='tight')
    print(f"✓ 圖表已保存至：{output_img}")
    
    # 保存詳細數據到 CSV
    output_csv = 'analysis_details.csv'
    df_closed[['timestamp_open', 'symbol', 'pnl', 'cum_pnl', 'exit_reason', 'duration_min']].to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"✓ 詳細數據已保存至：{output_csv}")
    
    print("\n" + "=" * 70)
    print("✅ 分析完成！")
    print("=" * 70)
    
    # 返回關鍵指標供進一步使用
    return {
        'total_trades': total_trades,
        'win_rate': win_rate,
        'total_pnl': total_pnl,
        'avg_pnl': avg_pnl,
        'expectancy': expectancy,
        'max_drawdown': max_drawdown,
        'profit_loss_ratio': profit_loss_ratio
    }

if __name__ == "__main__":
    # 預設使用當前目錄下的 trades.csv
    csv_file = 'trades.csv'
    
    # 如果提供了命令行參數，使用參數中的文件路徑
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    
    analyze_crypto_ai_data(csv_file)
