#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket 客戶端 - 用於即時價格訂閱
Binance USDT-M Futures WebSocket API
"""
import json
import threading
import time
from typing import Dict, Callable, Optional, Set
import websocket


class BinanceWebSocketClient:
    """Binance 期貨 WebSocket 客戶端"""

    # WebSocket 端點
    STREAM_URL = "wss://fstream.binance.com/ws"

    def __init__(self):
        self.ws_app: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.running = False

        # 訂閱的幣種價格快取
        self._price_cache: Dict[str, float] = {}
        self._price_cache_lock = threading.Lock()

        # 訂閱的 symbols
        self._subscribed: Set[str] = set()

        # 回調函數：symbol -> (price, timestamp)
        self._callbacks: Dict[str, Callable] = {}

        # 連接狀態
        self._connected = False
        self._connect_lock = threading.Lock()
        self._reconnect_delay = 3

    def subscribe(self, symbols: list, callback: Optional[Callable] = None):
        """
        訂閱幣種價格

        Args:
            symbols: 幣種列表，如 ['BTCUSDT', 'ETHUSDT']
            callback: 回調函數，簽名: callback(symbol: str, price: float)
        """
        if not symbols:
            return

        symbols = [s.upper() if not s.endswith('USDT') else s.upper()
                   for s in symbols]

        with self._price_cache_lock:
            for symbol in symbols:
                self._subscribed.add(symbol)
                if callback:
                    self._callbacks[symbol] = callback

        # 如果已連接，發送訂閱訊息
        if self._connected and self.ws_app:
            self._send_subscribe(symbols)

    def unsubscribe(self, symbols: list):
        """取消訂閱"""
        if not symbols:
            return

        symbols = [s.upper() if not s.endswith('USDT') else s.upper()
                   for s in symbols]

        with self._price_cache_lock:
            for symbol in symbols:
                self._subscribed.discard(symbol)
                self._callbacks.pop(symbol, None)
                self._price_cache.pop(symbol, None)

        if self._connected and self.ws_app:
            self._send_unsubscribe(symbols)

    def get_price(self, symbol: str) -> Optional[float]:
        """取得幣種最新價格"""
        with self._price_cache_lock:
            return self._price_cache.get(symbol.upper())

    def get_all_prices(self) -> Dict[str, float]:
        """取得所有訂閱幣種的價格"""
        with self._price_cache_lock:
            return self._price_cache.copy()

    def start(self):
        """啟動 WebSocket 連線（在背景執行緒）"""
        if self.running:
            return

        self.running = True
        self.ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
        self.ws_thread.start()

        # 等待連接成功
        for _ in range(50):  # 最多等 5 秒
            if self._connected:
                break
            time.sleep(0.1)

    def stop(self):
        """停止 WebSocket 連線"""
        self.running = False
        if self.ws_app:
            try:
                self.ws_app.close()
            except:
                pass
        self._connected = False

    def _run_websocket(self):
        """WebSocket 執行緒 - 自動重連"""
        while self.running:
            try:
                self._connect()
                # run_forever 會一直運行直到連接關閉
                # 當它返回時說明連接已斷開，需要重連
            except Exception as e:
                if self.running:
                    print(f"[WebSocket] 連線異常: {e}")
                self._connected = False

            if self.running:
                time.sleep(self._reconnect_delay)

    def _connect(self):
        """建立連線"""
        with self._connect_lock:
            if self._connected:
                return

            # 創建 WebSocketApp
            self.ws_app = websocket.WebSocketApp(
                self.STREAM_URL,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                on_open=self._on_open,
            )

            # 在新執行緒執行 run_forever
            thread = threading.Thread(target=self.ws_app.run_forever, daemon=True)
            thread.start()

            # 等待連線完成或超時
            for _ in range(100):  # 最多等 10 秒
                if self._connected:
                    break
                time.sleep(0.1)

            if not self._connected:
                raise Exception("WebSocket 連線超時")

    def _on_open(self, ws_app):
        """連線開啟"""
        print("[WebSocket] 已連接")
        self._connected = True

        # 發送訂閱訊息
        if self._subscribed:
            self._send_subscribe(list(self._subscribed))

    def _on_message(self, ws_app, message):
        """收到訊息"""
        try:
            data = json.loads(message)

            # 處理價格更新 (mark price or ticker)
            if 'e' in data:
                event_type = data.get('e')

                if event_type == 'markPriceUpdate':
                    symbol = data.get('s')
                    price = float(data.get('p', 0))
                    self._update_price(symbol, price)

                elif event_type == '24hrTicker':
                    symbol = data.get('s')
                    price = float(data.get('c', 0))
                    self._update_price(symbol, price)

            # 處理訂閱確認
            elif 'result' in data and data.get('id'):
                # 訂閱回應
                pass

        except Exception as e:
            print(f"[WebSocket] 解析訊息失敗: {e}")

    def _update_price(self, symbol: str, price: float):
        """更新價格並觸發回調"""
        if not symbol or price <= 0:
            return

        with self._price_cache_lock:
            self._price_cache[symbol] = price

        # 觸發回調
        callback = None
        with self._price_cache_lock:
            callback = self._callbacks.get(symbol)

        if callback:
            try:
                callback(symbol, price)
            except Exception as e:
                print(f"[WebSocket] 回調錯誤 {symbol}: {e}")

    def _on_error(self, ws_app, error):
        """錯誤處理"""
        print(f"[WebSocket] 錯誤: {error}")
        self._connected = False

    def _on_close(self, ws_app, code, reason):
        """連線關閉"""
        print(f"[WebSocket] 連線關閉: {code} {reason}")
        self._connected = False

    def _send_subscribe(self, symbols: list):
        """發送訂閱請求"""
        if not self.ws_app or not self._connected:
            return

        for i, symbol in enumerate(symbols):
            # 訂閱 mark price stream
            stream_name = f"{symbol.lower()}@markPrice"
            subscribe_msg = {
                "method": "SUBSCRIBE",
                "params": [stream_name],
                "id": i + 1
            }
            try:
                self.ws_app.send(json.dumps(subscribe_msg))
            except Exception as e:
                print(f"[WebSocket] 訂閱失敗 {symbol}: {e}")

    def _send_unsubscribe(self, symbols: list):
        """發送取消訂閱請求"""
        if not self.ws_app or not self._connected:
            return

        for i, symbol in enumerate(symbols):
            stream_name = f"{symbol.lower()}@markPrice"
            unsubscribe_msg = {
                "method": "UNSUBSCRIBE",
                "params": [stream_name],
                "id": i + 100
            }
            try:
                self.ws_app.send(json.dumps(unsubscribe_msg))
            except Exception as e:
                print(f"[WebSocket] 取消訂閱失敗 {symbol}: {e}")


# 單例模式
_ws_client: Optional[BinanceWebSocketClient] = None
_ws_lock = threading.Lock()


def get_websocket_client() -> BinanceWebSocketClient:
    """取得全域 WebSocket 客戶端"""
    global _ws_client
    with _ws_lock:
        if _ws_client is None:
            _ws_client = BinanceWebSocketClient()
        return _ws_client