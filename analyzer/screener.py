#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
進階選幣篩選模組
整合：技術面 (價格/成交量) + 資金面 (OI/費率) + 情緒面 (大戶比/散戶比)
"""

import os
from typing import List, Dict
import sys
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.binance_client import BinanceFuturesClient
from services.sentiment_client import SentimentAnalyzer

class Screener:
    """進階加密貨幣篩選器 - 多因子量化模型"""

    def __init__(self, client: BinanceFuturesClient, config: Dict):
        """
        初始化篩選器

        Args:
        client: Binance API 客戶端
        config: 配置字典
        """
        self.client = client
        self.config = config.get('screening', {})
        self.trend_config = config.get('trend', {})

        # 檢查是否使用實盤數據源
        self.use_mainnet_data = config.get('use_mainnet_data', True)

        # 進階因子配置
        self.enable_sentiment = self.config.get('screening', {}).get('enable_sentiment', True)
        self.sentiment_weight = self.config.get('sentiment_weight', 0.4) # 情緒面權重 40%
        self.technical_weight = self.config.get('technical_weight', 0.4) # 技術面權重 40%
        self.volume_weight = self.config.get('volume_weight', 0.2) # 成交量權重 20%

        if self.use_mainnet_data:
            print("[Screener] 已啟用實盤數據源 (Mainnet Data Source)")
            status = "開啟" if self.enable_sentiment else "關閉"
            print(f"[Screener] 進階因子：{status} (情緒{self.sentiment_weight*100:.0f}% + 技術{self.technical_weight*100:.0f}% + 量能{self.volume_weight*100:.0f}%)")
        else:
            print("[Screener] 已啟用測試網數據源 (Testnet Data Source)")

        # 獲取測試網支持的交易對列表（用於驗證）
        self.testnet_symbols = set()
        self._load_testnet_symbols()

        # 初始化情緒分析器
        self.sentiment_analyzer = None
        if self.enable_sentiment:
            self.sentiment_analyzer = SentimentAnalyzer()

    def _load_testnet_symbols(self):
        """加載交易對列表（用於驗證標的是否可交易）"""
        try:
            data_client = getattr(self.client, 'data_client', None)

            if data_client:
                exchange_info = data_client._request('GET', '/fapi/v1/exchangeInfo')
                self.testnet_symbols = {s['symbol'] for s in exchange_info.get('symbols', [])
                                        if s.get('status') == 'TRADING' and s['symbol'].endswith('USDT')}
                print(f"[Screener] 實盤支持 {len(self.testnet_symbols)} 個 USDT 交易對（模擬模式）")
            else:
                exchange_info = self.client._request('GET', '/fapi/v1/exchangeInfo')
                self.testnet_symbols = {s['symbol'] for s in exchange_info.get('symbols', [])
                                        if s.get('status') == 'TRADING' and s['symbol'].endswith('USDT')}
                mode_name = "測試網" if self.client.testnet else "實盤"
                print(f"[Screener] {mode_name}支持 {len(self.testnet_symbols)} 個 USDT 交易對")
        except Exception as e:
            print(f"[Screener] 加載交易對列表失敗：{e}")
            self.testnet_symbols = set()

    def _is_symbol_tradable(self, symbol: str) -> bool:
        """檢查標的是否可交易"""
        if not self.use_mainnet_data:
            return True
        if self.testnet_symbols and symbol not in self.testnet_symbols:
            return False
        try:
            symbol_info = self.client.get_symbol_info(symbol)
            if symbol_info.get('status') != 'TRADING':
                return False
            return True
        except:
            return False

    def _get_sentiment_score_sync(self, symbol: str) -> Dict:
        """同步獲取單一幣種的情緒分數（使用長壽命 loop 執行緒）"""
        if not self.sentiment_analyzer:
            return {'score': 50, 'details': 'Disabled'}

        try:
            sentiment_data = self.sentiment_analyzer.get_sentiment_sync(symbol)
            score = sentiment_data.get('score', 50)
            return {
                'score': score,
                'details': {
                    'score': sentiment_data.get('score', 50),
                    'funding_rate': sentiment_data.get('funding_rate', 0),
                    'open_interest': sentiment_data.get('open_interest', 0),
                    'top_account_ratio': sentiment_data.get('top_account_ratio', 1.0),
                    'global_ratio': sentiment_data.get('global_ratio', 1.0),
                    'taker_ratio': sentiment_data.get('taker_ratio', 1.0),
                    'mark_price': sentiment_data.get('mark_price', 0)
                }
            }
        except Exception as e:
            return {'score': 50, 'details': f'Error: {str(e)}'}

    def screen(self) -> List[Dict]:
        """
        執行篩選（同步版本）
        不再自己創建 event loop，直接用同步方法調用情緒分析
        """
        if self.enable_sentiment:
            return self._screen_with_sentiment_sync()
        else:
            return self._screen_traditional()

    def _screen_with_sentiment_sync(self) -> List[Dict]:
        """進階篩選（同步版本）- 透過長壽命 loop 執行緒執行情緒分析"""
        data_client = getattr(self.client, 'data_client', None)

        if self.use_mainnet_data:
            if data_client:
                tickers = data_client.get_all_tickers()
            else:
                tickers = self.client.get_mainnet_all_tickers()
        else:
            tickers = self.client.get_all_tickers()

        min_change = self.config.get('min_price_change', 5.0)
        max_change = self.config.get('max_price_change', 21.0)
        min_volume = self.config.get('min_volume_24h', 1000000)

        candidates = []

        print(f"\n[篩選] 掃描 {len(tickers)} 個交易對...")

        for ticker in tickers:
            symbol = ticker.get('symbol', '')

            if not symbol.endswith('USDT'):
                continue
            if not self._is_symbol_tradable(symbol):
                continue

            price_change = float(ticker.get('priceChangePercent', 0))
            volume_24h = float(ticker.get('quoteVolume', 0))

            if price_change < min_change:
                continue
            if price_change > max_change:
                continue
            if volume_24h < min_volume:
                continue

            tech_score = self._calculate_technical_score(ticker)
            vol_score = self._calculate_volume_score(ticker)

            candidates.append({
                'symbol': symbol,
                'price_change': price_change,
                'volume_24h': volume_24h,
                'tech_score': tech_score,
                'vol_score': vol_score,
                'last_price': float(ticker.get('lastPrice', 0))
            })

        top_n = self.config.get('top_n', 10)
        candidates.sort(key=lambda x: x['tech_score'] + x['vol_score'], reverse=True)
        candidates = candidates[:top_n * 2]

        print(f"[進階分析] 對 {len(candidates)} 個候選幣種進行情緒分析...")

        # 同步批量獲取情緒分數（每個都透過長壽命 loop）
        sentiment_results = []
        for c in candidates:
            result = self._get_sentiment_score_sync(c['symbol'])
            sentiment_results.append(result)

        final_candidates = []
        for i, candidate in enumerate(candidates):
            sentiment = sentiment_results[i]
            sentiment_score = sentiment.get('score', 50)

            total_score = (
                candidate['tech_score'] * self.technical_weight +
                candidate['vol_score'] * self.volume_weight +
                sentiment_score * self.sentiment_weight
            )

            final_candidates.append({
                'symbol': candidate['symbol'],
                'price_change': candidate['price_change'],
                'volume_24h': candidate['volume_24h'],
                'score': total_score,
                'last_price': candidate['last_price'],
                'tech_score': candidate['tech_score'],
                'vol_score': candidate['vol_score'],
                'sentiment_score': sentiment_score,
                'sentiment_details': sentiment
            })

        final_candidates.sort(key=lambda x: x['score'], reverse=True)

        if final_candidates:
            print(f"\n[篩選結果] Top 3:")
            for i, c in enumerate(final_candidates[:3]):
                print(f" {i+1}. {c['symbol']}: {c['score']:.1f}分 (技術{c['tech_score']:.0f} + 量能{c['vol_score']:.0f} + 情緒{c['sentiment_score']:.0f})")

        return final_candidates[:top_n]

    async def screen_async(self) -> List[Dict]:
        """進階篩選 - 異步版本（保留供直接調用）"""
        data_client = getattr(self.client, 'data_client', None)

        if self.use_mainnet_data:
            if data_client:
                tickers = data_client.get_all_tickers()
            else:
                tickers = self.client.get_mainnet_all_tickers()
        else:
            tickers = self.client.get_all_tickers()

        min_change = self.config.get('min_price_change', 5.0)
        max_change = self.config.get('max_price_change', 21.0)
        min_volume = self.config.get('min_volume_24h', 1000000)

        candidates = []

        print(f"\n[篩選] 掃描 {len(tickers)} 個交易對...")

        for ticker in tickers:
            symbol = ticker.get('symbol', '')

            if not symbol.endswith('USDT'):
                continue
            if not self._is_symbol_tradable(symbol):
                continue

            price_change = float(ticker.get('priceChangePercent', 0))
            volume_24h = float(ticker.get('quoteVolume', 0))

            if price_change < min_change:
                continue
            if price_change > max_change:
                continue
            if volume_24h < min_volume:
                continue

            tech_score = self._calculate_technical_score(ticker)
            vol_score = self._calculate_volume_score(ticker)

            candidates.append({
                'symbol': symbol,
                'price_change': price_change,
                'volume_24h': volume_24h,
                'tech_score': tech_score,
                'vol_score': vol_score,
                'last_price': float(ticker.get('lastPrice', 0))
            })

        top_n = self.config.get('top_n', 10)
        candidates.sort(key=lambda x: x['tech_score'] + x['vol_score'], reverse=True)
        candidates = candidates[:top_n * 2]

        print(f"[進階分析] 對 {len(candidates)} 個候選幣種進行情緒分析...")

        sentiment_results = []
        for c in candidates:
            result = self._get_sentiment_score_sync(c['symbol'])
            sentiment_results.append(result)

        final_candidates = []
        for i, candidate in enumerate(candidates):
            sentiment = sentiment_results[i]
            sentiment_score = sentiment.get('score', 50)

            total_score = (
                candidate['tech_score'] * self.technical_weight +
                candidate['vol_score'] * self.volume_weight +
                sentiment_score * self.sentiment_weight
            )

            final_candidates.append({
                'symbol': candidate['symbol'],
                'price_change': candidate['price_change'],
                'volume_24h': candidate['volume_24h'],
                'score': total_score,
                'last_price': candidate['last_price'],
                'tech_score': candidate['tech_score'],
                'vol_score': candidate['vol_score'],
                'sentiment_score': sentiment_score,
                'sentiment_details': sentiment
            })

        final_candidates.sort(key=lambda x: x['score'], reverse=True)

        if final_candidates:
            print(f"\n[篩選結果] Top 3:")
            for i, c in enumerate(final_candidates[:3]):
                print(f" {i+1}. {c['symbol']}: {c['score']:.1f}分 (技術{c['tech_score']:.0f} + 量能{c['vol_score']:.0f} + 情緒{c['sentiment_score']:.0f})")

        return final_candidates[:top_n]

    def _screen_traditional(self) -> List[Dict]:
        """傳統篩選模式（無情緒分析）"""
        data_client = getattr(self.client, 'data_client', None)

        if self.use_mainnet_data:
            if data_client:
                tickers = data_client.get_all_tickers()
            else:
                tickers = self.client.get_mainnet_all_tickers()
        else:
            tickers = self.client.get_all_tickers()

        min_change = self.config.get('min_price_change', 20)
        min_volume = self.config.get('min_volume_24h', 1000000)

        candidates = []

        for ticker in tickers:
            symbol = ticker.get('symbol', '')

            if not symbol.endswith('USDT'):
                continue
            if not self._is_symbol_tradable(symbol):
                continue

            price_change = float(ticker.get('priceChangePercent', 0))
            volume_24h = float(ticker.get('quoteVolume', 0))

            if price_change < min_change:
                continue
            if volume_24h < min_volume:
                continue

            score = self._calculate_score(ticker)

            candidates.append({
                'symbol': symbol,
                'price_change': price_change,
                'volume_24h': volume_24h,
                'score': score,
                'last_price': float(ticker.get('lastPrice', 0))
            })

        candidates.sort(key=lambda x: x['score'], reverse=True)
        top_n = self.config.get('top_n', 10)
        return candidates[:top_n]

    def _calculate_technical_score(self, ticker: Dict) -> float:
        """計算技術面分數 (0-100)"""
        price_change = float(ticker.get('priceChangePercent', 0))
        price_score = min(100, price_change * 2)
        return price_score

    def _calculate_volume_score(self, ticker: Dict) -> float:
        """計算成交量分數 (0-100)"""
        volume = float(ticker.get('quoteVolume', 0))
        volume_score = min(100, (volume / 1000000000) * 100)
        return volume_score

    def _calculate_score(self, ticker: Dict) -> float:
        """傳統評分方法（向後兼容）"""
        price_score = self._calculate_technical_score(ticker)
        volume_score = self._calculate_volume_score(ticker)
        rank_score = 50
        return (price_score * 0.4) + (volume_score * 0.4) + (rank_score * 0.2)

    def get_top_gainers(self, limit: int = 10) -> List[Dict]:
        """取得漲幅前 N 名"""
        if self.use_mainnet_data:
            tickers = self.client.get_mainnet_all_tickers()
        else:
            tickers = self.client.get_all_tickers()

        usdt_pairs = [t for t in tickers if t.get('symbol', '').endswith('USDT')]
        usdt_pairs.sort(key=lambda x: float(x.get('priceChangePercent', 0)), reverse=True)
        return usdt_pairs[:limit]

    def close(self):
        """關閉篩選器並釋放資源（由主程式調用）"""
        if self.enable_sentiment and self.sentiment_analyzer:
            self.sentiment_analyzer.close()
            print("[Screener] 情緒分析連接已關閉")
