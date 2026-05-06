#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CryptoAI 暴漲規律分析工具
1. 掃描過去 24 小時漲幅 > 10% 的幣種
2. 回溯暴漲前 1-4 小時的數據
3. 分析成交量、波動率、均線特徵
"""

import pandas as pd
import numpy as np
from binance.client import Client
from binance.exceptions import BinanceAPIException
import time
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# 配置
API_KEY = ""  # 可選，使用公開接口
API_SECRET = ""
INTERVALS = ['15m', '1h', '4h']  # 分析的時間週期
LOOKBACK_BARS = 20  # 暴漲前回溯的 K 線數量
PUMP_THRESHOLD = 0.10  # 漲幅超過 10% 定義為暴漲

class PumpPatternAnalyzer:
    def __init__(self):
        self.client = Client(API_KEY, API_SECRET)
        self.pump_symbols = []
        self.analysis_results = []
        
    def get_top_gainers(self, limit=50):
        """獲取漲幅最大的幣種"""
        print("🔍 正在掃描 24 小時漲幅榜...")
        try:
            tickers = self.client.get_ticker()
            df = pd.DataFrame(tickers)
            df['priceChangePercent'] = pd.to_numeric(df['priceChangePercent'], errors='coerce') / 100
            df = df[df['symbol'].str.endswith('USDT')]
            df = df.sort_values('priceChangePercent', ascending=False)
            
            # 篩選漲幅超過 10% 的
            gainers = df[df['priceChangePercent'] > PUMP_THRESHOLD]
            print(f"✓ 找到 {len(gainers)} 個漲幅 > 10% 的幣種")
            return gainers[['symbol', 'priceChangePercent', 'lastPrice']].reset_index(drop=True)
        except Exception as e:
            print(f"❌ 獲取漲幅榜失敗：{e}")
            return pd.DataFrame()
    
    def get_historical_klines(self, symbol, interval, end_time=None, limit=100):
        """獲取歷史 K 線數據"""
        try:
            if end_time is None:
                klines = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
            else:
                # 計算開始時間
                start_time = end_time - (limit * self._interval_to_ms(interval))
                klines = self.client.get_historical_klines(
                    symbol=symbol, 
                    interval=interval, 
                    start_str=start_time.strftime("%Y-%m-%d %H:%M:%S"),
                    end_str=end_time.strftime("%Y-%m-%d %H:%M:%S")
                )
            
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base', 
                'taker_buy_quote', 'ignore'
            ])
            df['close'] = pd.to_numeric(df['close'])
            df['volume'] = pd.to_numeric(df['volume'])
            df['high'] = pd.to_numeric(df['high'])
            df['low'] = pd.to_numeric(df['low'])
            df['open'] = pd.to_numeric(df['open'])
            return df
        except Exception as e:
            return pd.DataFrame()
    
    def _interval_to_ms(self, interval):
        """將時間間隔轉換為毫秒"""
        unit = interval[-1]
        value = int(interval[:-1])
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        elif unit == 'd':
            return value * 24 * 60 * 60 * 1000
        return 60000
    
    def calculate_features(self, df):
        """計算暴漲前的特徵指標"""
        if len(df) < 10:
            return None
            
        features = {}
        
        # 1. 成交量特徵
        features['vol_ma5'] = df['volume'].rolling(5).mean().iloc[-1]
        features['vol_ma20'] = df['volume'].rolling(20).mean().iloc[-1]
        features['vol_ratio'] = features['vol_ma5'] / features['vol_ma20'] if features['vol_ma20'] > 0 else 0
        
        # 最後一根 K 線的成交量相對於均線的倍數
        features['last_vol_ratio'] = df['volume'].iloc[-1] / features['vol_ma20'] if features['vol_ma20'] > 0 else 0
        
        # 2. 波動率特徵
        df['range'] = (df['high'] - df['low']) / df['open']
        features['avg_range'] = df['range'].rolling(10).mean().iloc[-1]
        features['last_range'] = df['range'].iloc[-1]
        
        # 波動率壓縮 (ATR)
        features['atr'] = (df['high'] - df['low']).rolling(14).mean().iloc[-1] / df['close'].iloc[-1]
        
        # 3. 均線特徵
        features['ma5'] = df['close'].rolling(5).mean().iloc[-1]
        features['ma20'] = df['close'].rolling(20).mean().iloc[-1]
        features['ma_deviation'] = (df['close'].iloc[-1] - features['ma20']) / features['ma20']
        
        # 4. 價格位置
        recent_high = df['high'].rolling(20).max().iloc[-1]
        features['price_to_high'] = (df['close'].iloc[-1] - recent_high) / recent_high
        
        # 5. 趨勢強度 (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        features['rsi'] = 100 - (100 / (1 + rs)).iloc[-1]
        
        return features

    def analyze_pump_patterns(self, symbols, interval='1h'):
        """分析指定幣種在暴漲前的模式"""
        print(f"\n📊 開始分析 {len(symbols)} 個暴漲幣種在 '{interval}' 級別的模式...")
        
        results = []
        
        for _, row in symbols.iterrows():
            symbol = row['symbol']
            current_price = row['lastPrice']
            
            # 獲取當前時間前的數據 (假設現在是暴漲後，我們看暴漲前)
            # 為了模擬，我們獲取過去 100 根 K 線，並假設最後一根是暴漲開始
            df = self.get_historical_klines(symbol, interval, limit=100)
            
            if len(df) < 30:
                continue
                
            # 計算特徵（使用暴漲前的數據，這裡簡化處理，取倒數第 2 根 K 線作為觀察點）
            # 實際應用中應該更精確地定位暴漲啟動點
            pre_pump_df = df.iloc[:-2]  # 排除最後兩根（暴漲段）
            
            if len(pre_pump_df) < 30:
                continue
                
            features = self.calculate_features(pre_pump_df)
            if features:
                features['symbol'] = symbol
                features['pump_percent'] = row['priceChangePercent']
                features['current_price'] = current_price
                results.append(features)
        
        return pd.DataFrame(results)

    def generate_report(self, df):
        """生成分析報告"""
        if df.empty:
            print("沒有足夠的數據生成報告")
            return
            
        print("\n" + "="*70)
        print("📈 暴漲前特徵分析報告")
        print("="*70)
        print(f"樣本數量：{len(df)} 個幣種")
        
        # 統計摘要
        print("\n1. 成交量特徵 (Volume)")
        print(f"   平均成交量比率 (Vol5/Vol20): {df['vol_ratio'].mean():.2f}")
        print(f"   暴漲前最後一根量能倍數：{df['last_vol_ratio'].mean():.2f} 倍")
        
        print("\n2. 波動率特徵 (Volatility)")
        print(f"   平均 K 線振幅：{df['avg_range'].mean()*100:.2f}%")
        print(f"   ATR (相對值): {df['atr'].mean()*100:.2f}%")
        
        print("\n3. 均線與趨勢 (Moving Average)")
        print(f"   均線乖離率 (Price vs MA20): {df['ma_deviation'].mean()*100:.2f}%")
        print(f"   RSI 平均值：{df['rsi'].mean():.1f}")
        
        print("\n4. 關鍵規律總結")
        
        # 規律 1: 成交量
        if df['last_vol_ratio'].mean() > 1.5:
            print("   ✅ [成交量] 暴漲前常有明顯放量 (大於均量 1.5 倍)")
        else:
            print("   ⚠️  [成交量] 暴漲前成交量無明顯異常")
            
        # 規律 2: 波動率
        if df['avg_range'].mean() < 0.02:
            print("   ✅ [波動率] 暴漲前波動率極度壓縮 (振幅 < 2%)，變盤在即")
        else:
            print("   ⚠️  [波動率] 暴漲前波動率正常")
            
        # 規律 3: 均線
        if df['ma_deviation'].mean() < 0.01:
            print("   ✅ [均線] 價格緊貼均線，乖離率極小")
        else:
            print("   ⚠️  [均線] 價格偏離均線較遠")
            
        # 規律 4: RSI
        if 40 <= df['rsi'].mean() <= 60:
            print("   ✅ [RSI] RSI 處於中性區域 (40-60)，多空平衡")
        elif df['rsi'].mean() < 40:
            print("   ✅ [RSI] RSI 偏低，存在超賣反彈需求")
            
        print("="*70)

def main():
    analyzer = PumpPatternAnalyzer()
    
    # 1. 獲取漲幅榜
    gainers = analyzer.get_top_gainers()
    
    if gainers.empty:
        print("未找到符合條件的幣種")
        return
        
    print("\nTop 5 漲幅榜:")
    print(gainers.head(5).to_string(index=False))
    
    # 2. 分析不同時間週期的模式
    for interval in INTERVALS:
        results = analyzer.analyze_pump_patterns(gainers, interval=interval)
        if not results.empty:
            analyzer.generate_report(results)
            
            # 保存詳細數據
            output_file = f"pump_analysis_{interval}.csv"
            results.to_csv(output_file, index=False)
            print(f"\n📄 詳細數據已保存至：{output_file}")

if __name__ == "__main__":
    main()
