"""
模擬交易客戶端 (Paper Trading Client)
提供與 BinanceFuturesClient 完全一致的接口，但實際在本地模擬撮合
"""
from typing import Dict, List, Optional, Any
from services.paper_engine import PaperTradingEngine

class PaperTradingClient:
    """
    模擬交易客戶端
    封裝 PaperTradingEngine，提供與 BinanceFuturesClient 一致的接口
    """
    
    def __init__(self, initial_balance: float = 10000.0, leverage: int = 10):
        """
        初始化模擬客戶端
        
        Args:
        initial_balance: 初始資金
        leverage: 預設槓桿
        """
        self.engine = PaperTradingEngine(initial_balance=initial_balance, leverage=leverage)
        self.testnet = False # 標記為非測試網
        self.base_url = "PAPER_TRADING" # 標記
        self.initial_balance = initial_balance  # 添加此屬性
        self.leverage = leverage  # 添加此屬性
        
        print(f"[模擬模式] 初始化成功 | 初始資金：{initial_balance} USDT | 槓桿：{leverage}x")
    
    # ========== 賬戶資訊 (適配 Binance API) ==========
    
    def get_account_balance(self) -> Dict:
        """模擬 get_account_balance"""
        return self.engine.get_account_balance()
    
    def get_account_info(self) -> Dict:
        """模擬 get_account_info"""
        balance_info = self.engine.get_account_balance()
        return {
            'availableBalance': balance_info['availableBalance'],
            'totalWalletBalance': balance_info['totalWalletBalance'],
            'totalUnrealizedProfit': balance_info['totalUnrealizedProfit'],
            'totalMarginBalance': balance_info['totalMarginBalance'],
            'assets': [
                {'asset': 'USDT', 'availableBalance': balance_info['availableBalance']}
            ]
        }
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """模擬 get_position"""
        return self.engine.get_position(symbol)
    
    def get_all_positions(self) -> List[Dict]:
        """模擬 get_all_positions"""
        return self.engine.get_all_positions()
    
    # ========== 交易 (適配 Binance API) ==========
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """
        模擬 get_symbol_info
        返回一個預設的交易對資訊
        """
        return {
            'symbol': symbol,
            'status': 'TRADING',
            'filters': [
                {'filterType': 'LOT_SIZE', 'stepSize': '0.001'},
                {'filterType': 'PRICE_FILTER', 'tickSize': '0.01'}
            ]
        }
    
    def place_order(self, symbol: str, side: str, type: str = "MARKET",
                    quantity: Optional[float] = None,
                    price: Optional[float] = None,
                    leverage: Optional[int] = None) -> Dict:
        """
        模擬 place_order
        
        Args:
            symbol: 交易對
            side: BUY/SELL
            type: MARKET/LIMIT
            quantity: 數量
            price: 價格 (限價單需要)
            leverage: 槓桿
            
        Returns:
            訂單結果
        """
        # 如果是市價單且沒有指定價格，使用一個預設價格 (實際應由上層傳入最新價)
        if type.upper() == "MARKET" and price is None:
            # 不應該發生，上層應該傳入價格
            print(f"[警告] place_order 未傳入價格，使用 0.0 | symbol={symbol}, side={side}")
            price = 0.0
        
        if quantity is None:
            return {'error': True, 'msg': "數量不能為空"}
            
        # 調用引擎下單
        return self.engine.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price if price else 0.0,
            leverage=leverage or self.engine.leverage,
            order_type=type
        )
    
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, 
                     orig_client_order_id: Optional[str] = None) -> Dict:
        """模擬 cancel_order (模擬模式無掛單)"""
        return {'status': 'OK', 'msg': '模擬模式無掛單'}
    
    def cancel_all_orders(self, symbol: str) -> Dict:
        """模擬 cancel_all_orders"""
        return {'status': 'OK', 'msg': '模擬模式無掛單'}
    
    # ========== 槓桿設定 ==========
    
    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """模擬 set_leverage"""
        self.engine.leverage = leverage
        return {'leverage': leverage, 'symbol': symbol}
    
    def get_leverage(self, symbol: str) -> int:
        """模擬 get_leverage"""
        return self.engine.leverage
    
    # ========== 市場數據 (轉發到實盤 API) ==========
    # 注意：模擬模式下，市場數據仍應來自 Binance 實盤
    
    def get_ticker(self, symbol: str) -> Dict:
        """
        獲取 24hr Ticker
        注意：模擬模式下應直接調用 Binance 實盤 API
        這裡需要一個真實的 client 來獲取數據，或者在上層處理
        """
        # 這個方法需要依賴真實的 Binance API
        # 建議在 main.py 中通過真實 client 獲取後傳入
        if hasattr(self, 'data_client'):
            return self.data_client.get_ticker(symbol)
        raise NotImplementedError("模擬模式下請使用真實 client 獲取市場數據")
    
    def get_all_tickers(self) -> List[Dict]:
        """獲取所有交易對 24hr 數據 (需依賴真實 API)"""
        if hasattr(self, 'data_client'):
            return self.data_client.get_all_tickers()
        raise NotImplementedError("模擬模式下請使用真實 client 獲取市場數據")
    
    def get_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> List[List]:
        """獲取 K 線 (需依賴真實 API)"""
        if hasattr(self, 'data_client'):
            return self.data_client.get_klines(symbol, interval, limit)
        raise NotImplementedError("模擬模式下請使用真實 client 獲取市場數據")
    
    def get_mainnet_all_tickers(self) -> List[Dict]:
        """獲取實盤所有交易對數據 (需依賴真實 API)"""
        if hasattr(self, 'data_client'):
            return self.data_client.get_mainnet_all_tickers()
        raise NotImplementedError("模擬模式下請使用真實 client 獲取市場數據")
    
    def get_mainnet_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> List[List]:
        """獲取實盤 K 線 (需依賴真實 API)"""
        if hasattr(self, 'data_client'):
            return self.data_client.get_mainnet_klines(symbol, interval, limit)
        raise NotImplementedError("模擬模式下請使用真實 client 獲取市場數據")
    
    # ========== 工具方法 ==========
    
    def _request(self, method: str, endpoint: str, params: dict = None) -> dict:
        """
        模擬 _request 方法
        在模擬模式下，這個方法應該被 data_client 取代
        如果調用這個方法，表示上層沒有正確使用 data_client
        """
        if hasattr(self, 'data_client'):
            # 如果有綁定 data_client，轉發請求
            return self.data_client._request(method, endpoint, params)
        else:
            # 否則返回空或拋出錯誤
            raise NotImplementedError("模擬模式下請使用 data_client 獲取市場數據")
    
    def get_usdt_balance(self) -> float:
        """獲取 USDT 可用餘額"""
        return float(self.engine.get_account_balance()['availableBalance'])
    
    def get_total_balance(self) -> float:
        """獲取總資產"""
        return float(self.engine.get_account_balance()['totalWalletBalance'])
    
    def update_position_price(self, symbol: str, price: float):
        """
        更新持倉的最新價格
        用於計算未實現損益和觸發止損止盈
        """
        self.engine.update_position_price(symbol, price)
    
    def close_position(self, symbol: str, current_price: float, exit_reason: str = "MANUAL") -> Dict:
        """
        平倉
        
        Args:
            symbol: 交易對
            current_price: 當前價格
            exit_reason: 平倉原因
            
        Returns:
            平倉結果
        """
        return self.engine.close_position(symbol, current_price, exit_reason)
