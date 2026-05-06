"""
Binance USDT-M Futures API 客戶端
支援測試網和正式網
"""
import hmac
import hashlib
import time
import requests
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode


class BinanceFuturesClient:
    """Binance USDT-M Futures API 客戶端"""
    
    # 正式網
    BASE_URL = "https://fapi.binance.com"
    # 測試網（官方當前 URL）
    TESTNET_URL = "https://demo-fapi.binance.com"
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        初始化 Binance Futures 客戶端
        
        Args:
            api_key: API Key
            api_secret: API Secret
            testnet: 是否使用測試網
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.base_url = self.TESTNET_URL if testnet else self.BASE_URL
        
        self.session = requests.Session()
        self.session.headers.update({
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        })
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """生成簽名"""
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, 
                 signed: bool = False) -> Dict:
        """
        發送請求
        
        Args:
            method: HTTP 方法
            endpoint: API 端點
            params: 請求參數
            signed: 是否需要簽名
            
        Returns:
            API 回應
        """
        url = f"{self.base_url}{endpoint}"
        
        if params is None:
            params = {}
        
        # 添加時間戳
        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._generate_signature(params)
        
        try:
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=10)
            elif method == 'POST':
                response = self.session.post(url, params=params, timeout=10)
            elif method == 'DELETE':
                response = self.session.delete(url, params=params, timeout=10)
            else:
                raise ValueError(f"不支持的 HTTP 方法：{method}")
            
            data = response.json()
            
            # 檢查錯誤
            if 'code' in data and data['code'] != 0:
                if data['code'] == -2014:
                    raise Exception(f"API 認證失敗：請檢查 API Key 權限 (Code: {data['code']})")
                elif data['code'] == -1001:
                    raise Exception(f"內部錯誤：{data.get('msg', 'Unknown')}")
                elif data['code'] == -1013:
                    raise Exception(f"交易對無效：{params.get('symbol', 'Unknown')}")
                elif data['code'] == -2028:
                    raise Exception(f"持倉數量超過限制：{data.get('msg', 'Unknown')}")
                else:
                    raise Exception(f"API 錯誤 {data['code']}: {data.get('msg', 'Unknown')}")
            
            return data
            
        except requests.exceptions.Timeout:
            raise Exception("API 請求超時，請檢查網路連接")
        except requests.exceptions.RequestException as e:
            raise Exception(f"網路錯誤：{str(e)}")
    
    # ========== 帳戶資訊 ==========
    
    def get_account_balance(self) -> Dict:
        """取得帳戶餘額"""
        return self._request('GET', '/fapi/v2/balance', signed=True)
    
    def get_account_info(self) -> Dict:
        """取得帳戶資訊"""
        return self._request('GET', '/fapi/v2/account', signed=True)
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """
        取得特定交易對的持倉
        
        Args:
            symbol: 交易對 (如 BTCUSDT)
            
        Returns:
            持倉資訊，無持倉則回傳 None
        """
        positions = self._request('GET', '/fapi/v2/positionRisk', signed=True)
        for pos in positions:
            if pos['symbol'] == symbol:
                # 檢查是否有持倉
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    return pos
        return None
    
    def get_all_positions(self) -> List[Dict]:
        """
        取得所有持倉
        
        Returns:
            持倉列表
        """
        positions = self._request('GET', '/fapi/v2/positionRisk', signed=True)
        # 只回傳有持倉的
        return [pos for pos in positions if float(pos.get('positionAmt', 0)) != 0]
    
    # ========== 交易 ==========
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """
        取得交易對資訊
        
        Args:
            symbol: 交易對 (如 BTCUSDT)
            
        Returns:
            交易對資訊
        """
        all_symbols = self._request('GET', '/fapi/v1/exchangeInfo')
        for s in all_symbols.get('symbols', []):
            if s['symbol'] == symbol:
                return s
        raise Exception(f"找不到交易對：{symbol}")
    
    def place_order(self, symbol: str, side: str, type: str = "MARKET",
                    quantity: Optional[float] = None,
                    price: Optional[float] = None,
                    leverage: Optional[int] = None) -> Dict:
        """
        下單
        
        Args:
            symbol: 交易對
            side: BUY/SELL
            type: 訂單類型 (MARKET, LIMIT)
            quantity: 數量
            price: 價格 (限價單需要)
            leverage: 槓桿倍數 (會先設定槓桿)
            
        Returns:
            訂單結果
        """
        # 設定槓桿
        if leverage:
            self.set_leverage(symbol, leverage)
        
        params = {
            'symbol': symbol,
            'side': side.upper(),
            'type': type.upper(),
        }
        
        # 市價單使用市價單專用參數
        if type.upper() == "MARKET":
            if quantity:
                params['quantity'] = self._format_quantity(symbol, quantity)
            else:
                raise Exception("市價單需要指定數量")
        else:
            # 限價單
            if not price:
                raise Exception("限價單需要指定價格")
            params['price'] = self._format_price(symbol, price)
            if quantity:
                params['quantity'] = self._format_quantity(symbol, quantity)
        
        # 市價單可以指定 closePosition 來平倉
        if quantity is None and type.upper() == "MARKET":
            params['closePosition'] = 'true'
        
        return self._request('POST', '/fapi/v1/order', params=params, signed=True)
    
    def cancel_order(self, symbol: str, order_id: Optional[int] = None, 
                     orig_client_order_id: Optional[str] = None) -> Dict:
        """
        取消訂單
        
        Args:
            symbol: 交易對
            order_id: 訂單 ID
            orig_client_order_id: 客戶自定義訂單 ID
        """
        params = {'symbol': symbol}
        if order_id:
            params['orderId'] = order_id
        if orig_client_order_id:
            params['origClientOrderId'] = orig_client_order_id
        
        return self._request('DELETE', '/fapi/v1/order', params=params, signed=True)
    
    def cancel_all_orders(self, symbol: str) -> Dict:
        """取消所有掛單"""
        params = {'symbol': symbol}
        return self._request('DELETE', '/fapi/v1/allOpenOrders', params=params, signed=True)
    
    def _format_quantity(self, symbol: str, quantity: float) -> str:
        """根據交易對精度格式化數量"""
        try:
            info = self.get_symbol_info(symbol)
            for f in info.get('filters', []):
                if f.get('filterType') == 'LOT_SIZE':
                    step_size = float(f.get('stepSize', 1))
                    decimal_places = len(str(step_size).split('.')[-1].rstrip('0'))
                    return f"{quantity:.{decimal_places}f}"
        except:
            pass
        return str(quantity)
    
    def _format_price(self, symbol: str, price: float) -> str:
        """根據交易對精度格式化價格"""
        try:
            info = self.get_symbol_info(symbol)
            for f in info.get('filters', []):
                if f.get('filterType') == 'PRICE_FILTER':
                    tick_size = float(f.get('tickSize', 1))
                    decimal_places = len(str(tick_size).split('.')[-1].rstrip('0'))
                    return f"{price:.{decimal_places}f}"
        except:
            pass
        return str(price)
    
    # ========== 槓桿設定 ==========
    
    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """
        設定槓桿
        
        Args:
        symbol: 交易對
        leverage: 槓桿倍數 (1-125)
        """
        if leverage < 1 or leverage > 125:
            raise Exception("槓桿倍數必須在 1-125 之間")
        
        params = {
            'symbol': symbol,
            'leverage': leverage
        }
        
        try:
            return self._request('POST', '/fapi/v1/leverage', params=params, signed=True)
        except Exception as e:
            # 如果是槓桿不支持的錯誤，嘗試降低槓桿
            error_msg = str(e)
            if 'not valid' in error_msg or 'LEVERAGE' in error_msg:
                # 嘗試從 20x 開始遞減測試
                for test_leverage in [20, 10, 5, 3, 2, 1]:
                    try:
                        params['leverage'] = test_leverage
                        print(f"[槓桿調整] {symbol}: 10x -> {test_leverage}x")
                        return self._request('POST', '/fapi/v1/leverage', params=params, signed=True)
                    except:
                        continue
                # 如果所有槓桿都失敗，拋出原始錯誤
                raise Exception(f"{symbol} 不支持任何槓桿倍數")
            else:
                raise
    
    def get_leverage(self, symbol: str) -> int:
        """取得槓桿倍數"""
        pos = self.get_position(symbol)
        if pos:
            return int(pos.get('leverage', 1))
        return 1
    
    # ========== 市場數據 ==========
    
    def get_ticker(self, symbol: str) -> Dict:
        """取得 24 小時價格變動"""
        params = {'symbol': symbol}
        return self._request('GET', '/fapi/v1/ticker/24hr', params=params)
    
    def get_all_tickers(self) -> List[Dict]:
        """取得所有交易對的 24 小時價格變動"""
        return self._request('GET', '/fapi/v1/ticker/24hr')
    
    def get_klines(self, symbol: str, interval: str = "1m", 
                   limit: int = 100) -> List[List]:
        """
        取得 K 線數據
        
        Args:
            symbol: 交易對
            interval: 時間間隔 (1m, 5m, 15m, 1h, 4h, 1d)
            limit: 返回筆數
        """
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        return self._request('GET', '/fapi/v1/klines', params=params)
    
    def get_mark_price(self, symbol: str) -> Dict:
        """取得標記價格"""
        params = {'symbol': symbol}
        return self._request('GET', '/fapi/v1/premiumIndex', params=params)
    
    def get_all_mark_prices(self) -> List[Dict]:
        """取得所有交易對標記價格"""
        return self._request('GET', '/fapi/v1/premiumIndex')
    
    def get_mainnet_klines(self, symbol: str, interval: str = "1m", 
    limit: int = 100) -> List[List]:
        """
        從實盤獲取 K 線數據（用於測試網交易但需要實盤數據的場景）
        
        Args:
        symbol: 交易對
        interval: 時間間隔 (1m, 5m, 15m, 1h, 4h, 1d)
        limit: 返回筆數
        """
        # 強制使用實盤 URL
        url = f"{self.BASE_URL}/fapi/v1/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            return response.json()
        except Exception as e:
            raise Exception(f"獲取實盤 K 線失敗：{str(e)}")
    
    def get_mainnet_all_tickers(self) -> List[Dict]:
        """
        從實盤獲取所有交易對的 24 小時價格變動（用於測試網交易但需要實盤數據的場景）
        """
        # 強制使用實盤 URL
        url = f"{self.BASE_URL}/fapi/v1/ticker/24hr"
        
        try:
            response = self.session.get(url, timeout=10)
            return response.json()
        except Exception as e:
            raise Exception(f"獲取實盤行情失敗：{str(e)}")
    
    # ========== 工具方法 ==========
    
    def get_usdt_balance(self) -> float:
        """取得 USDT 可用餘額"""
        account = self.get_account_info()
        for asset in account.get('assets', []):
            if asset.get('asset') == 'USDT':
                return float(asset.get('availableBalance', 0))
        return 0.0
    
    def get_total_balance(self) -> float:
        """取得總資產 (USDT 本位)"""
        account = self.get_account_info()
        return float(account.get('totalWalletBalance', 0))
