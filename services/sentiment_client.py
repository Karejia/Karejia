#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
情緒分析模塊 - 使用 Binance API 獲取市場情緒數據
修復版本：SentimentAnalyzer 持有長壽命 event loop 執行緒，
所有 API 請求透過該執行緒執行，避免跨 loop 使用的問題。
"""
import asyncio
import threading
from typing import Dict, Optional
from binance.async_client import AsyncClient


class SentimentAnalyzer:
    """
    情緒分析器 - 擁有自己的 event loop 執行緒，
    確保 AsyncClient 永遠綁定在正確的 event loop 上。
    """

    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self._client: Optional[AsyncClient] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._started = False
        self._lock = threading.Lock()

    def _run_loop(self):
        """在獨立執行緒中運行 event loop"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _ensure_started(self):
        """啟動執行緒（只執行一次）"""
        if self._started:
            return
        with self._lock:
            if self._started:
                return
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            # 等 loop 啟動
            while self._loop is None:
                import time; time.sleep(0.01)
            self._started = True
            print("[SentimentAnalyzer] Event loop 執行緒已啟動")

    async def _ensure_client(self):
        """在正確的 event loop 上創建 client"""
        if self._client is not None:
            return self._client

        print("[SentimentAnalyzer] 正在創建新的連接...")
        self._client = await AsyncClient.create(
            self.api_key,
            self.api_secret
        )
        print("[SentimentAnalyzer] 連接已建立")
        return self._client

    # ========== 各指標方法（在正確 loop 上執行）==========

    async def _get_funding_rate(self, symbol: str) -> float:
        await self._ensure_client()
        try:
            data = await self._client.futures_funding_rate(symbol=symbol)
            if data and len(data) > 0:
                return float(data[-1].get('fundingRate', 0))
            return 0.0
        except Exception as e:
            print(f"[SentimentAnalyzer] {symbol} 資金費率失敗：{e}")
            raise

    async def _get_open_interest(self, symbol: str) -> float:
        await self._ensure_client()
        try:
            data = await self._client.futures_open_interest(symbol=symbol)
            if data and isinstance(data, dict):
                return float(data.get('openInterest', 0))
            return 0.0
        except Exception as e:
            print(f"[SentimentAnalyzer] {symbol} 持倉量失敗：{e}")
            raise

    async def _get_top_account_ratio(self, symbol: str) -> float:
        await self._ensure_client()
        try:
            data = await self._client.futures_top_longshort_account_ratio(
                symbol=symbol, period="5m"
            )
            if data and len(data) > 0:
                return float(data[-1].get('longShortRatio', 1.0))
            return 1.0
        except Exception as e:
            print(f"[SentimentAnalyzer] {symbol} Top Account L/S 失敗：{e}")
            raise

    async def _get_global_longshort_ratio(self, symbol: str) -> float:
        await self._ensure_client()
        try:
            data = await self._client.futures_global_longshort_ratio(
                symbol=symbol, period="5m"
            )
            if data and len(data) > 0:
                return float(data[-1].get('longShortRatio', 1.0))
            return 1.0
        except Exception as e:
            print(f"[SentimentAnalyzer] {symbol} Global L/S 失敗：{e}")
            raise

    async def _get_taker_longshort_ratio(self, symbol: str) -> float:
        await self._ensure_client()
        try:
            data = await self._client.futures_taker_longshort_ratio(
                symbol=symbol, period="5m"
            )
            if data and len(data) > 0:
                return float(data[-1].get('buySellRatio', 1.0))
            return 1.0
        except Exception as e:
            print(f"[SentimentAnalyzer] {symbol} Taker L/S 失敗：{e}")
            raise

    async def _get_mark_price(self, symbol: str) -> float:
        await self._ensure_client()
        try:
            data = await self._client.futures_mark_price(symbol=symbol)
            if data:
                return float(data.get('markPrice', 0))
            return 0.0
        except Exception as e:
            print(f"[SentimentAnalyzer] {symbol} Mark Price 失敗：{e}")
            raise

    # ========== 對外介面 ==========

    def get_sentiment_sync(self, symbol: str) -> Dict:
        """
        同步方法 - 在長壽命 loop 執行緒上執行，
        供 screener.screen()（同步）調用。
        """
        self._ensure_started()

        async def _work():
            await self._ensure_client()
            results = await asyncio.gather(
                self._get_funding_rate(symbol),
                self._get_open_interest(symbol),
                self._get_top_account_ratio(symbol),
                self._get_global_longshort_ratio(symbol),
                self._get_taker_longshort_ratio(symbol),
                self._get_mark_price(symbol),
                return_exceptions=True
            )
            return results

        future = asyncio.run_coroutine_threadsafe(_work(), self._loop)
        results = future.result(timeout=30)

        funding_rate, oi, top_account_ratio, global_ratio, taker_ratio, mark_price = results

        # 處理異常
        defaults = [0.0, 0.0, 1.0, 1.0, 1.0, 0.0]
        vals = [funding_rate, oi, top_account_ratio, global_ratio, taker_ratio, mark_price]
        names = ['funding_rate', 'oi', 'top_account_ratio', 'global_ratio', 'taker_ratio', 'mark_price']

        for i, (name, val) in enumerate(zip(names, vals)):
            if isinstance(val, Exception):
                print(f"[Debug] {symbol} {name} 失敗：{type(val).__name__}: {val}")
                if name in ('top_account_ratio', 'global_ratio', 'taker_ratio'):
                    vals[i] = 1.0
                elif name in ('oi', 'funding_rate'):
                    vals[i] = 0.0
                else:
                    vals[i] = 0.0

        funding_rate, oi, top_account_ratio, global_ratio, taker_ratio, mark_price = vals

        print(f"[Debug] {symbol} 情緒數據：fr={funding_rate}, oi={oi}, "
              f"top={top_account_ratio}, global={global_ratio}, "
              f"taker={taker_ratio}, mark={mark_price}")

        # ========== 計算情緒分數（0-100）==========
        score = 50

        if funding_rate > 0.001:
            score += 15
        elif funding_rate > 0.0005:
            score += 8
        elif funding_rate < -0.001:
            score -= 15
        elif funding_rate < -0.0005:
            score -= 8

        if oi > 100_000_000:
            score += 10
        elif oi > 10_000_000:
            score += 5
        elif oi > 1_000_000:
            score += 2

        if top_account_ratio > 1.5:
            score += 15
        elif top_account_ratio > 1.2:
            score += 10
        elif top_account_ratio > 1.0:
            score += 5
        elif top_account_ratio < 0.67:
            score -= 10
        elif top_account_ratio < 0.8:
            score -= 5

        if global_ratio > 1.5:
            score += 10
        elif global_ratio > 1.2:
            score += 5
        elif global_ratio < 0.67:
            score -= 10
        elif global_ratio < 0.8:
            score -= 5

        if taker_ratio > 1.5:
            score += 10
        elif taker_ratio > 1.2:
            score += 5
        elif taker_ratio < 0.67:
            score -= 10
        elif taker_ratio < 0.8:
            score -= 5

        score = max(0, min(100, score))

        return {
            'score': score,
            'funding_rate': funding_rate,
            'open_interest': oi,
            'top_account_ratio': top_account_ratio,
            'global_ratio': global_ratio,
            'taker_ratio': taker_ratio,
            'mark_price': mark_price
        }

    async def get_sentiment_async(self, symbol: str) -> Dict:
        """
        異步方法 - 在長壽命 loop 執行緒上執行（供 screen_async 調用）
        """
        self._ensure_started()

        async def _work():
            await self._ensure_client()
            results = await asyncio.gather(
                self._get_funding_rate(symbol),
                self._get_open_interest(symbol),
                self._get_top_account_ratio(symbol),
                self._get_global_longshort_ratio(symbol),
                self._get_taker_longshort_ratio(symbol),
                self._get_mark_price(symbol),
                return_exceptions=True
            )
            return results

        future = asyncio.run_coroutine_threadsafe(_work(), self._loop)
        results = future.result(timeout=30)

        funding_rate, oi, top_account_ratio, global_ratio, taker_ratio, mark_price = results

        defaults = [0.0, 0.0, 1.0, 1.0, 1.0, 0.0]
        vals = [funding_rate, oi, top_account_ratio, global_ratio, taker_ratio, mark_price]
        names = ['funding_rate', 'oi', 'top_account_ratio', 'global_ratio', 'taker_ratio', 'mark_price']

        for i, (name, val) in enumerate(zip(names, vals)):
            if isinstance(val, Exception):
                print(f"[Debug] {symbol} {name} 失敗：{type(val).__name__}: {val}")
                if name in ('top_account_ratio', 'global_ratio', 'taker_ratio'):
                    vals[i] = 1.0
                elif name in ('oi', 'funding_rate'):
                    vals[i] = 0.0
                else:
                    vals[i] = 0.0

        funding_rate, oi, top_account_ratio, global_ratio, taker_ratio, mark_price = vals

        print(f"[Debug] {symbol} 情緒數據：fr={funding_rate}, oi={oi}, "
              f"top={top_account_ratio}, global={global_ratio}, "
              f"taker={taker_ratio}, mark={mark_price}")

        score = 50
        if funding_rate > 0.001: score += 15
        elif funding_rate > 0.0005: score += 8
        elif funding_rate < -0.001: score -= 15
        elif funding_rate < -0.0005: score -= 8

        if oi > 100_000_000: score += 10
        elif oi > 10_000_000: score += 5
        elif oi > 1_000_000: score += 2

        if top_account_ratio > 1.5: score += 15
        elif top_account_ratio > 1.2: score += 10
        elif top_account_ratio > 1.0: score += 5
        elif top_account_ratio < 0.67: score -= 10
        elif top_account_ratio < 0.8: score -= 5

        if global_ratio > 1.5: score += 10
        elif global_ratio > 1.2: score += 5
        elif global_ratio < 0.67: score -= 10
        elif global_ratio < 0.8: score -= 5

        if taker_ratio > 1.5: score += 10
        elif taker_ratio > 1.2: score += 5
        elif taker_ratio < 0.67: score -= 10
        elif taker_ratio < 0.8: score -= 5

        score = max(0, min(100, score))

        return {
            'score': score,
            'funding_rate': funding_rate,
            'open_interest': oi,
            'top_account_ratio': top_account_ratio,
            'global_ratio': global_ratio,
            'taker_ratio': taker_ratio,
            'mark_price': mark_price
        }

    def close(self):
        """關閉連接和執行緒（同步介面）"""
        if self._loop is None:
            return
        
        async def _close_async():
            """在正確的 event loop 上關閉 client"""
            if self._client is not None:
                await self._client.close_connection()
                print("[SentimentAnalyzer] Client 連接已關閉")
            
            if self._loop is not None:
                self._loop.stop()
                print("[SentimentAnalyzer] Event loop 已停止")
        
        future = asyncio.run_coroutine_threadsafe(_close_async(), self._loop)
        try:
            future.result(timeout=10)
        except Exception as e:
            print(f"[SentimentAnalyzer] 關閉時出錯：{e}")
        
        if self._thread is not None:
            self._thread.join(timeout=5)
        print("[SentimentAnalyzer] 執行緒已關閉")