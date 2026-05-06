"""
測試網成交量數據診斷工具 - 簡化版
直接分析 Binance 測試網數據
"""
import sys
sys.path.insert(0, '/mnt/c/Users/ljes9/OneDrive/Desktop/CryptoAI - 複製 (2) - 複製 - 複製')

from services.binance_client import BinanceFuturesClient
from datetime import datetime

# 你的 API Key（從之前對話中取得）
API_KEY = "6wDwEuXx3oeIzH8FIzi5aZp7YMskEKg2gARGDE4w8U1S1yzKoxvNt96mOEJguN3C"
API_SECRET = "N0wOCXmBq74SG4shH7xQ4IqNd4HdAHcxodSHdrrc9YWNv3dJbRFQVaFfSjyMsvdx"

def main():
    print("=" * 60)
    print("測試網成交量數據診斷")
    print("=" * 60)
    
    # 建立客戶端
    client = BinanceFuturesClient(API_KEY, API_SECRET, testnet=True)
    
    # 測試連接
    print("\n[1/5] 測試 API 連接...")
    try:
        account = client.get_account_info()
        balance = client.get_usdt_balance()
        print(f"  ✓ 連接成功")
        print(f"  帳戶餘額：{balance:.2f} USDT")
    except Exception as e:
        print(f"  ❌ 連接失敗：{e}")
        return
    
    # 取得所有 ticker
    print("\n[2/5] 取得所有交易對 24h 數據...")
    try:
        all_tickers = client.get_all_tickers()
        print(f"  找到 {len(all_tickers)} 個交易對")
    except Exception as e:
        print(f"  ❌ 錯誤：{e}")
        return
    
    # 篩選 USDT 交易對
    usdt_pairs = [t for t in all_tickers if t['symbol'].endswith('USDT')]
    print(f"  USDT 交易對：{len(usdt_pairs)} 個")
    
    # 分析成交量
    print("\n[3/5] 成交量分析...")
    volumes = []
    for ticker in usdt_pairs:
        vol = float(ticker.get('quoteVolume', 0))
        change = float(ticker.get('priceChangePercent', 0))
        volumes.append({
            'symbol': ticker['symbol'],
            'volume': vol,
            'change': change,
            'price': float(ticker.get('lastPrice', 0))
        })
    
    volumes.sort(key=lambda x: x['volume'], reverse=True)
    
    print(f"\n  成交量前 5 名:")
    for i, data in enumerate(volumes[:5], 1):
        print(f"    {i}. {data['symbol']}: {data['volume']:,.0f} USDT (+{data['change']:.1f}%)")
    
    print(f"\n  漲幅前 5 名:")
    by_change = sorted(volumes, key=lambda x: x['change'], reverse=True)
    for i, data in enumerate(by_change[:5], 1):
        print(f"    {i}. {data['symbol']}: +{data['change']:.1f}% (vol: {data['volume']:,.0f})")
    
    # 統計
    vol_values = [v['volume'] for v in volumes]
    zero_vol = len([v for v in vol_values if v == 0])
    low_vol = len([v for v in vol_values if 0 < v < 100000])
    
    print(f"\n  統計:")
    print(f"    平均成交量：{sum(vol_values)/len(vol_values):,.0f} USDT")
    print(f"    中位數：{sorted(vol_values)[len(vol_values)//2]:,.0f} USDT")
    print(f"    零成交量：{zero_vol} 個 ({zero_vol/len(vol_values)*100:.1f}%)")
    print(f"    低成交量：{low_vol} 個")
    
    # 分析 K 線成交量
    print("\n[4/5] 分析熱門標的 K 線成交量...")
    test_symbols = [v['symbol'] for v in volumes[:3]]
    
    for symbol in test_symbols:
        print(f"\n  {symbol}:")
        try:
            # 取得 1 分鐘 K 線
            klines = client.get_klines(symbol, interval='1m', limit=5)
            
            if not klines:
                print(f"    ❌ 無 K 線數據")
                continue
            
            print(f"    最近 5 根 K 棒 (時間, 成交量):")
            for i, k in enumerate(klines[-5:]):
                ts = datetime.fromtimestamp(k[0] / 1000)
                vol = float(k[4])  # K 線 [4] 是成交量
                print(f"      {ts.strftime('%H:%M')}: {vol:,.0f}")
            
            # 計算比率
            vols = [float(k[4]) for k in klines]
            if len(vols) >= 2:
                avg_vol = sum(vols) / len(vols)
                latest_vol = vols[-1]
                ratio = latest_vol / avg_vol if avg_vol > 0 else 0
                print(f"\n    成交量比率 (最新/平均): {ratio:.2f}")
                
        except Exception as e:
            print(f"    ❌ 錯誤：{e}")
    
    # 測試 TrendAnalyzer
    print("\n[5/5] 測試 TrendAnalyzer 成交量比率...")
    try:
        from analyzer.trend import TrendAnalyzer
        import yaml
        
        with open('/mnt/c/Users/ljes9/OneDrive/Desktop/CryptoAI - 複製 (2) - 複製 - 複製/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        for symbol in test_symbols:
            try:
                trend = TrendAnalyzer(client, config)
                result = trend.analyze(symbol)
                
                print(f"\n  {symbol}:")
                print(f"    當前成交量：{result.get('current_volume', 0):,.0f}")
                print(f"    平均成交量：{result.get('avg_volume', 0):,.0f}")
                print(f"    成交量比率：{result.get('volume_ratio', 0):.2f}")
                
                if result.get('volume_ratio', 0) == 0:
                    print(f"    ⚠️ 警告：比率為 0")
                elif result.get('volume_ratio', 0) < 0.5:
                    print(f"    ⚠️ 警告：比率 < 0.5，可能觸發技術出場")
                    
            except Exception as e:
                print(f"    ❌ 錯誤：{e}")
                
    except Exception as e:
        print(f"  ❌ 無法載入 TrendAnalyzer: {e}")
    
    print("\n" + "=" * 60)
    print("診斷完成！")
    print("=" * 60)
    
    # 總結
    print("\n📊 分析結果:")
    if zero_vol > len(usdt_pairs) * 0.3:
        print("  ⚠️ 超過 30% 交易對成交量為 0")
        print("  建議：放棄成交量指標")
    elif len([v for v in volumes if v['volume'] < 1000000]) > len(volumes) * 0.5:
        print("  ⚠️ 超過 50% 交易對 24h 成交量 < 100 萬")
        print("  建議：降低成交量門檻或改用其他指標")
    else:
        print("  ✓ 成交量數據品質尚可")

if __name__ == '__main__':
    main()
