"""
測試網成交量數據診斷工具
檢查 Binance 測試網的成交量數據品質
"""
import sys
import yaml
from datetime import datetime

# 載入配置
BASE_PATH = '/mnt/c/Users/ljes9/OneDrive/Desktop/CryptoAI - 複製 (2) - 複製 - 複製'
sys.path.insert(0, BASE_PATH)

from services.binance_client import BinanceFuturesClient
from analyzer.trend import TrendAnalyzer

def load_config():
    with open(f'{BASE_PATH}/config.yaml', 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def main():
    print("""
╔══════════════════════════════════════════════════╗
║                                                  ║
║   測試網成交量數據診斷工具                       ║
║                                                  ║
╚══════════════════════════════════════════════════╝
    """)
    
    # 載入配置
    config = load_config()
    api_key = config['api'].get('api_key', '')
    api_secret = config['api'].get('api_secret', '')
    testnet = config['api'].get('testnet', True)
    
    # 如果配置檔沒有 API Key，要求輸入
    if not api_key or not api_secret:
        print("配置檔中沒有 API Key，請手動輸入：")
        api_key = input("API Key: ").strip()
        api_secret = input("API Secret: ").strip()
    
    if not api_key or not api_secret:
        print("❌ API Key 或 Secret 不能為空")
        return
    
    print(f"\n連接測試網：{testnet}")
    print("=" * 60)
    
    # 建立客戶端
    client = BinanceFuturesClient(api_key, api_secret, testnet)
    
    # 取得所有 ticker
    print("\n[1/4] 取得所有交易對 24h 數據...")
    try:
        all_tickers = client.get_all_tickers()
        print(f"  找到 {len(all_tickers)} 個交易對")
    except Exception as e:
        print(f"  ❌ 錯誤：{e}")
        return
    
    # 篩選 USDT 交易對
    usdt_pairs = [t for t in all_tickers if t['symbol'].endswith('USDT')]
    print(f"  USDT 交易對：{len(usdt_pairs)} 個")
    
    # 分析成交量分佈
    print("\n[2/4] 分析成交量分佈...")
    volumes = []
    for ticker in usdt_pairs:
        vol = float(ticker.get('quoteVolume', 0))
        volumes.append((ticker['symbol'], vol))
    
    volumes.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n  成交量前 10 名:")
    for i, (symbol, vol) in enumerate(volumes[:10], 1):
        print(f"    {i}. {symbol}: {vol:,.0f} USDT")
    
    print(f"\n  成交量後 10 名:")
    for i, (symbol, vol) in enumerate(volumes[-10:], 1):
        print(f"    {len(volumes)-10+i}. {symbol}: {vol:,.0f} USDT")
    
    # 統計數據
    vol_values = [v[1] for v in volumes]
    avg_vol = sum(vol_values) / len(vol_values) if vol_values else 0
    median_vol = sorted(vol_values)[len(vol_values)//2] if vol_values else 0
    
    print(f"\n  統計數據:")
    print(f"    平均成交量：{avg_vol:,.0f} USDT")
    print(f"    中位數：{median_vol:,.0f} USDT")
    print(f"    最大值：{max(vol_values):,.0f} USDT")
    print(f"    最小值：{min(vol_values):,.0f} USDT")
    
    # 檢查零成交量
    zero_vol_pairs = [v for v in volumes if v[1] == 0]
    low_vol_pairs = [v for v in volumes if 0 < v[1] < 100000]  # 小於 10 萬
    
    print(f"\n  異常數據:")
    print(f"    零成交量交易對：{len(zero_vol_pairs)} 個")
    print(f"    低成交量交易對 (<100k)：{len(low_vol_pairs)} 個")
    
    if zero_vol_pairs:
        print(f"\n    零成交量交易對列表 (前 10 個):")
        for symbol, _ in zero_vol_pairs[:10]:
            print(f"      - {symbol}")
    
    # 分析特定標的的 K 線成交量
    print("\n[3/4] 分析熱門標的 K 線成交量...")
    test_symbols = volumes[:5]  # 前 5 大成交量
    
    for symbol, _ in test_symbols:
        print(f"\n  {symbol}:")
        try:
            # 取得 K 線
            klines = client.get_klines(symbol, interval='1m', limit=10)
            
            if not klines:
                print(f"    ❌ 無 K 線數據")
                continue
            
            print(f"    最近 10 根 K 棒 (時間, 成交量):")
            for i, k in enumerate(klines[-10:]):
                timestamp = datetime.fromtimestamp(k[0] / 1000)
                vol = float(k[4])  # K 線 [4] 是成交量
                print(f"      {i+1}. {timestamp.strftime('%H:%M')}: {vol:,.0f}")
            
            # 計算 K 線成交量趨勢
            vols = [float(k[4]) for k in klines]
            avg_kline_vol = sum(vols) / len(vols)
            print(f"\n    K 線統計:")
            print(f"      平均：{avg_kline_vol:,.0f}")
            print(f"      最大：{max(vols):,.0f}")
            print(f"      最小：{min(vols):,.0f}")
            
        except Exception as e:
            print(f"    ❌ 錯誤：{e}")
    
    # 測試 TrendAnalyzer 的成交量比率計算
    print("\n[4/4] 測試 TrendAnalyzer 成交量比率...")
    config_obj = load_config()
    
    for symbol, _ in test_symbols:
        try:
            trend = TrendAnalyzer(client, config_obj)
            result = trend.analyze(symbol)
            
            print(f"\n  {symbol}:")
            print(f"    當前成交量: {result.get('current_volume', 0):,.0f}")
            print(f"    平均成交量: {result.get('avg_volume', 0):,.0f}")
            print(f"    成交量比率: {result.get('volume_ratio', 0):.2f}")
            
            if result.get('volume_ratio', 0) == 0:
                print(f"    ⚠️ 警告：成交量比率為 0，可能除零錯誤")
            
        except Exception as e:
            print(f"    ❌ 錯誤：{e}")
    
    print("\n" + "=" * 60)
    print("診斷完成！")
    print("=" * 60)
    
    # 總結建議
    print("\n📊 建議:")
    
    if len(zero_vol_pairs) > len(usdt_pairs) * 0.5:
        print("  ⚠️ 超過 50% 交易對成交量為 0，測試網數據可能不完整")
        print("  建議：放棄成交量指標，改用價格相關指標")
    
    if avg_vol < 1000000:
        print("  ⚠️ 平均成交量偏低，市場可能不活躍")
        print("  建議：提高最小成交量門檻或改用其他指標")
    
    print("\n  可選擇的替代方案:")
    print("    1. 價格偏離度 (Price Deviation)")
    print("    2. 高點回撤 (Drawdown)")
    print("    3. 時間 + 收益組合 (Time + Profit)")
    print("    4. 動能衰竭 (Momentum)")
    print("    5. 布林通道 (Bollinger Bands)")

if __name__ == '__main__':
    main()
