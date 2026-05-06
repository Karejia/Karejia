"""
本地模擬交易引擎 (Paper Trading Engine)
使用實盤數據進行本地虛擬撮合，不經過 Binance API
"""
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import csv
import os

class PaperTradingEngine:
    """
    本地模擬交易引擎
    - 模擬保證金、槓桿、止損止盈
    - 使用實盤價格數據進行撮合
    - 記錄完整交易歷史
    """
    
    def __init__(self, initial_balance: float = 10000.0, leverage: int = 10):
        """
        初始化模擬引擎
        
        Args:
            initial_balance: 初始資金 (USDT)
            leverage: 預設槓桿倍數
        """
        self.initial_balance = initial_balance
        self.balance = initial_balance  # 可用餘額
        self.frozen_balance = 0.0       # 凍結保證金
        self.leverage = leverage
        self.positions: Dict[str, Dict] = {}  # symbol -> position info
        self.orders: List[Dict] = []          # 掛單記錄 (本模擬器主要用市價單，此處簡化)
        self.trades_log: List[Dict] = []      # 成交記錄
        self.trade_counter = 0
        
        # 交易記錄文件
        self.log_file = 'paper_trades.csv'
        self._init_trade_log()
        
    def _init_trade_log(self):
        """初始化交易日誌"""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'trade_id', 'timestamp_open', 'timestamp_close', 'symbol', 'side',
                    'leverage', 'quantity', 'entry_price', 'exit_price', 
                    'position_value', 'margin', 'pnl_usdt', 'pnl_percent', 
                    'roi_percent', 'fee_usdt', 'net_pnl', 'exit_reason', 'holding_time'
                ])
    
    # ========== 賬戶資訊 ==========
    
    def get_account_balance(self) -> Dict:
        """模擬 get_account_info 返回"""
        return {
            'availableBalance': str(self.balance),
            'totalWalletBalance': str(self.balance + self.frozen_balance),
            'totalUnrealizedProfit': str(self.get_total_unrealized_pnl()),
            'totalMarginBalance': str(self.balance + self.frozen_balance)
        }
    
    def get_total_unrealized_pnl(self) -> float:
        """計算所有持倉的未實現損益"""
        total_pnl = 0.0
        # 這裡需要外部傳入最新價格，否則無法準確計算
        # 在實際使用中，應在 update_positions 中計算
        return total_pnl

    # ========== 下單與持倉 ==========
    
    def place_order(self, symbol: str, side: str, quantity: float, 
                    price: float, leverage: int = None, order_type: str = "MARKET") -> Dict:
        """
        模擬下單 (市價單立即成交)
        
        Args:
            symbol: 交易對 (e.g., 'BTCUSDT')
            side: 'BUY' (做多) 或 'SELL' (做空)
            quantity: 數量
            price: 成交價格
            leverage: 槓桿倍數
            order_type: 訂單類型
            
        Returns:
            訂單結果
        """
        if leverage is None:
            leverage = self.leverage
            
        # 計算所需保證金
        position_value = price * quantity
        required_margin = position_value / leverage
        
        # 檢查餘額
        if required_margin > self.balance:
            return {
                'error': True,
                'code': -4028,
                'msg': f"餘額不足: 需要 {required_margin:.2f} USDT, 可用 {self.balance:.2f} USDT"
            }
        
        # 扣除保證金
        self.balance -= required_margin
        self.frozen_balance += required_margin
        
        # 建立持倉
        position_id = symbol
        is_new_position = position_id not in self.positions
        
        if is_new_position:
            self.positions[position_id] = {
                'symbol': symbol,
                'side': side,
                'quantity': quantity,
                'entry_price': price,
                'leverage': leverage,
                'margin': required_margin,
                'timestamp': datetime.now(),
                'stop_loss': None,
                'take_profit': None,
                'highest_price': price,
                'lowest_price': price
            }
        else:
            # 加倉邏輯 (簡化：平均價)
            pos = self.positions[position_id]
            total_qty = pos['quantity'] + quantity
            avg_price = (pos['entry_price'] * pos['quantity'] + price * quantity) / total_qty
            pos['quantity'] = total_qty
            pos['entry_price'] = avg_price
            pos['margin'] += required_margin
            pos['leverage'] = leverage
        
        self.trade_counter += 1
        order_id = f"PAPER_{int(time.time() * 1000)}_{self.trade_counter}"
        
        print(f"[模擬下單] {side} {quantity} {symbol} @ {price} (槓桿 {leverage}x, 保證金 {required_margin:.2f} USDT)")
        
        return {
            'orderId': order_id,
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'origQty': quantity,
            'price': str(price),
            'status': 'FILLED',
            'executedQty': quantity,
            'avgPrice': str(price)
        }
    
    def close_position(self, symbol: str, current_price: float, 
                       exit_reason: str = "MANUAL") -> Dict:
        """
        平倉
        
        Args:
            symbol: 交易對
            current_price: 當前價格
            exit_reason: 平倉原因
            
        Returns:
            平倉結果
        """
        if symbol not in self.positions:
            return {'error': True, 'msg': f"無 {symbol} 持倉"}
        
        pos = self.positions[symbol]
        side = pos['side'].upper()  # 轉為大寫
        quantity = pos['quantity']
        entry_price = pos['entry_price']
        margin = pos['margin']
        
        # 計算損益 (BUY=做多，SELL=做空)
        is_long = (side == 'BUY' or side == 'LONG')
        if is_long:
            pnl = (current_price - entry_price) * quantity
        else:
            pnl = (entry_price - current_price) * quantity
        
        pnl_percent = (pnl / margin) * 100 if margin > 0 else 0
        roi_percent = pnl_percent  # 簡化
        
        # 計算手續費 (假設 0.02%)
        fee_rate = 0.0002
        position_value = current_price * quantity
        fee = position_value * fee_rate
        net_pnl = pnl - fee
        
        # 退回保證金 + 損益
        self.frozen_balance -= margin
        self.balance += (margin + net_pnl)
        
        # 計算持倉時間
        hold_time = datetime.now() - pos['timestamp']
        hold_minutes = int(hold_time.total_seconds() / 60)
        
        # 記錄交易
        self.trade_counter += 1
        trade_record = {
            'trade_id': f"T{self.trade_counter:06d}",
            'timestamp_open': pos['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
            'timestamp_close': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': symbol,
            'side': side,
            'leverage': pos['leverage'],
            'quantity': quantity,
            'entry_price': entry_price,
            'exit_price': current_price,
            'position_value': position_value,
            'margin': margin,
            'pnl_usdt': pnl,
            'pnl_percent': pnl_percent,
            'roi_percent': roi_percent,
            'fee_usdt': fee,
            'net_pnl': net_pnl,
            'exit_reason': exit_reason,
            'holding_time': f"{hold_minutes}m"
        }
        self._log_trade(trade_record)
        self.trades_log.append(trade_record)
        
        # 移除持倉
        del self.positions[symbol]
        
        print(f"[模擬平倉] {symbol} 價格 {current_price} | 損益: {pnl:+.2f} USDT ({pnl_percent:.2f}%) | 原因: {exit_reason}")
        
        return trade_record
    
    def _log_trade(self, record: Dict):
        """記錄交易到 CSV"""
        try:
            with open(self.log_file, 'a', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    record['trade_id'], record['timestamp_open'], record['timestamp_close'],
                    record['symbol'], record['side'], record['leverage'], record['quantity'],
                    record['entry_price'], record['exit_price'], record['position_value'],
                    record['margin'], record['pnl_usdt'], record['pnl_percent'],
                    record['roi_percent'], record['fee_usdt'], record['net_pnl'],
                    record['exit_reason'], record['holding_time']
                ])
        except Exception as e:
            print(f"記錄交易日誌失敗: {e}")
    
    # ========== 持倉管理 ==========
    
    def get_all_positions(self) -> List[Dict]:
        """獲取所有持倉 (模擬 Binance API 格式)"""
        result = []
        for pos_id, pos in self.positions.items():
            # 將 BUY/SELL 轉換為 LONG/SHORT
            side = pos['side'].upper()
            is_long = (side == 'BUY' or side == 'LONG')
            position_amt = str(pos['quantity']) if is_long else str(-pos['quantity'])
            
            # 這裡的 markPrice 需要外部更新，暫時用 entry_price 佔位
            result.append({
                'symbol': pos['symbol'],
                'positionAmt': position_amt,
                'entryPrice': str(pos['entry_price']),
                'markPrice': str(pos.get('last_price', pos['entry_price'])),
                'leverage': str(pos['leverage']),
                'unRealizedProfit': '0.0',  # 需動態計算
                'side': side
            })
        return result
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """獲取單一持倉"""
        return self.positions.get(symbol, None)
    
    def update_position_price(self, symbol: str, current_price: float):
        """
        更新持倉的最新價格 (用於計算未實現損益和觸發止損止盈)
        此方法應在每次收到新 K 線時調用
        """
        if symbol not in self.positions:
            return
        
        pos = self.positions[symbol]
        pos['last_price'] = current_price
        
        # 更新最高/最低價
        if current_price > pos['highest_price']:
            pos['highest_price'] = current_price
        if current_price < pos['lowest_price']:
            pos['lowest_price'] = current_price
        
        # 自動觸發止損/止盈 (如果需要)
        # 這裡可以加入邏輯：如果 current_price <= stop_loss，則自動平倉
        # 但為了讓主策略邏輯控制，這裡只做價格更新
