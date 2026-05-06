import os
"""
交易信號生成模組
根據趨勢分析和篩選結果生成買賣信號
"""
from typing import Dict, Optional, List
from datetime import datetime
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.binance_client import BinanceFuturesClient
from analyzer.trend import TrendAnalyzer


class SignalGenerator:
    """信號生成器"""
    
    def __init__(self, client: BinanceFuturesClient, config: Dict):
        """
        初始化信號生成器
        
        Args:
            client: Binance API 客戶端
            config: 配置字典
        """
        self.client = client
        self.config = config
        self.trend_analyzer = TrendAnalyzer(client, config)
    
    def generate_buy_signal(self, symbol: str) -> Optional[Dict]:
        """
        生成買入信號
        
        Args:
            symbol: 交易對
            
        Returns:
            買入信號字典，無信號則回傳 None
        """
        try:
            # 趨勢分析
            trend_data = self.trend_analyzer.analyze(symbol)
            
            trend = trend_data.get('trend', 'UNKNOWN')
            
            # 只考慮上升趨勢
            if trend not in ['UP', 'STRONG_UP']:
                return None
            
            # 取得 24h 數據
            ticker = self.client.get_ticker(symbol)
            price_change = float(ticker.get('priceChangePercent', 0))
            min_change = self.config.get('screening', {}).get('min_price_change', 5.0)
            max_change = self.config.get('screening', {}).get('max_price_change', 21.0)

            # 檢查漲幅是否達標
            if price_change < min_change:
                return None
            if price_change > max_change:
                return None
            
            # 生成信號
            confidence = self._calculate_confidence(trend_data, price_change)
            
            return {
                'action': 'BUY',
                'symbol': symbol,
                'price': trend_data.get('price'),
                'trend': trend,
                'price_change': price_change,
                'volume_ratio': trend_data.get('volume_ratio', 1.0),
                'confidence': confidence,
                'reason': f"{trend} + 漲幅{price_change:.2f}%",
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            print(f"[信號生成錯誤] {symbol}: {str(e)}")
            return None
    
    def _calculate_confidence(self, trend_data: Dict, price_change: float) -> float:
        """
        計算信號信心指數
        
        Returns:
            0.0-1.0 的信心指數
        """
        confidence = 0.5  # 基礎信心
        
        # 趨勢強度
        trend = trend_data.get('trend', '')
        if trend == 'STRONG_UP':
            confidence += 0.2
        elif trend == 'UP':
            confidence += 0.1
        
        # 成交量放大
        volume_ratio = trend_data.get('volume_ratio', 1.0)
        if volume_ratio >= 2.0:
            confidence += 0.15
        elif volume_ratio >= 1.5:
            confidence += 0.1
        elif volume_ratio >= 1.0:
            confidence += 0.05
        
        # 漲幅適中（不要過高）
        if 20 <= price_change <= 50:
            confidence += 0.1
        elif 50 < price_change <= 100:
            confidence += 0.05
        
        return min(1.0, confidence)
    
    def check_sell_signal(self, symbol: str, position: Dict, 
                          current_price: float) -> Optional[Dict]:
        """
        檢查賣出信號
        
        Args:
            symbol: 交易對
            position: 當前持倉資訊
            current_price: 當前價格
            
        Returns:
            賣出信號字典，無信號則回傳 None
        """
        try:
            trend_data = self.trend_analyzer.analyze(symbol)
            
            # 趨勢反轉
            if trend_data.get('trend') in ['DOWN', 'STRONG_DOWN']:
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'reason': '趨勢反轉',
                    'type': 'TECHNICAL_EXIT'
                }
            
            # 成交量萎縮
            if trend_data.get('volume_ratio', 1.0) < 0.5:
                return {
                    'action': 'SELL',
                    'symbol': symbol,
                    'reason': '成交量萎縮',
                    'type': 'TECHNICAL_EXIT'
                }
            
            return None
            
        except Exception as e:
            print(f"[賣出信號錯誤] {symbol}: {str(e)}")
            return None
