import os
"""
趨勢分析模組
計算 MA、成交量等技術指標
"""
from typing import Dict, List, Optional, Tuple
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.binance_client import BinanceFuturesClient


class TrendAnalyzer:
    """趨勢分析器"""
    
    def __init__(self, client: BinanceFuturesClient, config: Dict):
        """
        初始化分析器
        
        Args:
            client: Binance API 客戶端
            config: 配置字典
        """
        self.client = client
        self.config = config.get('trend', {})
        self.ma_period = self.config.get('ma_period', 20)
        self.volume_ma_period = self.config.get('volume_ma_period', 10)
    
    def analyze(self, symbol: str, interval: str = "5m") -> Dict:
        """
        分析趨勢
        
        Args:
            symbol: 交易對
            interval: K 線間隔
            
        Returns:
            分析結果字典
        """
        # 取得 K 線數據
        klines = self.client.get_klines(symbol, interval, limit=100)
        
        if not klines or len(klines) < self.ma_period:
            return {
                'trend': 'UNKNOWN',
                'ma': None,
                'price': None,
                'volume_ratio': None,
                'reason': '數據不足'
            }
        
        # 解析 K 線
        closes = []
        volumes = []
        highs = []
        lows = []
        
        for k in klines:
            # kline: [開盤時間, 開盤價, 最高價, 最低價, 收盤價, 成交量, ...]
            closes.append(float(k[4]))
            volumes.append(float(k[5]))
            highs.append(float(k[2]))
            lows.append(float(k[3]))
        
        current_price = closes[-1]
        
        # 計算 MA
        ma = self._calculate_ma(closes, self.ma_period)
        
        # 計算成交量 MA
        volume_ma = self._calculate_ma(volumes, self.volume_ma_period)
        current_volume = volumes[-1]
        volume_ratio = current_volume / volume_ma if volume_ma > 0 else 1.0
        
        # 判斷趨勢
        trend = self._determine_trend(current_price, ma, volume_ratio)
        
        return {
            'trend': trend,
            'ma': ma,
            'price': current_price,
            'volume_ratio': volume_ratio,
            'price_change': (current_price - closes[-2]) / closes[-2] * 100 if len(closes) > 1 else 0,
            'high_24h': max(highs),
            'low_24h': min(lows),
        }
    
    def _calculate_ma(self, data: List[float], period: int) -> Optional[float]:
        """計算移動平均線"""
        if len(data) < period:
            return None
        return sum(data[-period:]) / period
    
    def _determine_trend(self, price: float, ma: Optional[float], 
                         volume_ratio: float) -> str:
        """
        判斷趨勢
        
        Returns:
            'UP', 'DOWN', or 'SIDEWAYS'
        """
        if ma is None:
            return 'UNKNOWN'
        
        # 價格在 MA 之上且成交量放大
        if price > ma:
            if volume_ratio >= 1.5:
                return 'STRONG_UP'
            return 'UP'
        
        # 價格在 MA 之下
        if price < ma:
            if volume_ratio >= 1.5:
                return 'STRONG_DOWN'
            return 'DOWN'
        
        # 價格接近 MA
        return 'SIDEWAYS'
    
    def get_ma_breakout(self, symbol: str, interval: str = "5m") -> Dict:
        """
        檢測 MA 突破
        
        Args:
            symbol: 交易對
            interval: K 線間隔
            
        Returns:
            突破資訊
        """
        klines = self.client.get_klines(symbol, interval, limit=50)
        
        if len(klines) < 25:
            return {'breakout': False, 'direction': None}
        
        # 計算 MA
        closes = [float(k[4]) for k in klines]
        ma = sum(closes[-21:-1]) / 20  # 前 20 根 MA
        
        current_price = closes[-1]
        prev_price = closes[-2]
        
        # 檢測突破
        breakout = False
        direction = None
        
        # 向上突破：前一根在 MA 下，現在在 MA 上
        if prev_price < ma and current_price > ma:
            breakout = True
            direction = 'UP'
        
        # 向下跌破：前一根在 MA 上，現在在 MA 下
        elif prev_price > ma and current_price < ma:
            breakout = True
            direction = 'DOWN'
        
        return {
            'breakout': breakout,
            'direction': direction,
            'ma': ma,
            'price': current_price
        }
