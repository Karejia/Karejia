"""
倉位管理模組
管理持倉記錄、計算 PnL、追蹤最大/最小未實現損益
"""
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta


class Position:
    """單一持倉類別 - 增強版（完整追蹤 MAE/MFE）"""
    
    def __init__(self, symbol: str, entry_price: float, quantity: float,
                 leverage: int = 10, side: str = 'LONG',
                 entry_reason: str = '', entry_score: float = 0.0):
        """
        初始化持倉
        
        Args:
            symbol: 交易對
            entry_price: 進場價格
            quantity: 數量
            leverage: 槓桿
            side: 方向 (LONG/SHORT)
            entry_reason: 進場原因
            entry_score: 進場分數（來自信號）
        """
        self.symbol = symbol
        self.entry_price = entry_price
        self.quantity = quantity
        self.original_quantity = quantity  # 原始數量（用於部分平倉追蹤）
        self.leverage = leverage
        self.side = side
        self.open_time = datetime.now()
        self.entry_reason = entry_reason
        self.entry_score = entry_score
        
        # 價格追蹤
        self.highest_price = entry_price  # 持倉期間最高價
        self.lowest_price = entry_price  # 持倉期間最低價
        
        # 損益追蹤
        self.max_unrealized_pnl = 0.0  # 最大未實現利潤
        self.max_unrealized_loss = 0.0  # 最大未實現虧損（正數）
        self.min_pnl_percent = 0.0  # 最小收益率
        self.max_pnl_percent = 0.0  # 最大收益率
        self.highest_pnl_percent = 0.0  # 持倉期間最高收益率（用於移動止損）
        
        # 出場記錄
        self.partial_exits = []  # 部分平倉記錄
        self.exit_reason = None
        self.exit_type = None
        self.exit_time = None
        self.exit_price = None
        
        # 市場環境快照
        self.market_condition = 'UNKNOWN'  # BULL/BEAR/SIDEWAY
        self.volatility_atr = 0.0
        self.volume_ratio = 1.0
    
    def update_price(self, price: float):
        """更新價格並追蹤最高/最低價、最大未實現損益"""
        # 更新最高/最低價
        if self.side == 'LONG':
            self.highest_price = max(self.highest_price, price)
            self.lowest_price = min(self.lowest_price, price) if self.lowest_price == self.entry_price else self.lowest_price
        else:
            self.lowest_price = min(self.lowest_price, price)
            self.highest_price = max(self.highest_price, price) if self.highest_price == self.entry_price else self.highest_price
        
        # 計算當前 PnL
        current_pnl = self.get_pnl(price)
        current_pnl_percent = self.get_pnl_percent(price)
        
        # 更新最大未實現利潤
        if current_pnl > self.max_unrealized_pnl:
            self.max_unrealized_pnl = current_pnl
        
        # 更新最大未實現虧損
        if current_pnl < 0:
            unrealized_loss = abs(current_pnl)
            if unrealized_loss > self.max_unrealized_loss:
                self.max_unrealized_loss = unrealized_loss
        
        # 更新最大/最小收益率
        if current_pnl_percent > self.max_pnl_percent:
            self.max_pnl_percent = current_pnl_percent
        if current_pnl_percent < self.min_pnl_percent:
            self.min_pnl_percent = current_pnl_percent
        
        # 【新增】追蹤最高收益率（用於收益率版移動止損）
        if current_pnl_percent > self.highest_pnl_percent:
            self.highest_pnl_percent = current_pnl_percent
    
    def get_pnl(self, current_price: float) -> float:
        """計算未平倉損益 (PnL)"""
        if self.side == 'LONG':
            return (current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - current_price) * self.quantity
    
    def get_pnl_percent(self, current_price: float) -> float:
        """計算收益率 (%)"""
        margin = self.get_margin()
        if margin == 0:
            return 0.0
        return (self.get_pnl(current_price) / margin) * 100
    
    def get_margin(self) -> float:
        """計算保證金"""
        return (self.entry_price * self.quantity) / self.leverage
    
    def get_position_value(self, current_price: float) -> float:
        """計算持倉價值"""
        return current_price * self.quantity
    
    def get_holding_minutes(self) -> int:
        """獲取持倉分鐘數"""
        return int((datetime.now() - self.open_time).total_seconds() / 60)
    
    def get_holding_seconds(self) -> int:
        """獲取持倉秒數"""
        return int((datetime.now() - self.open_time).total_seconds())
    
    def add_partial_exit(self, exit_price: float, exit_quantity: float, pnl: float):
        """記錄部分平倉"""
        self.partial_exits.append({
            'price': exit_price,
            'quantity': exit_quantity,
            'pnl': pnl,
            'timestamp': datetime.now()
        })
    
    def set_exit(self, exit_price: float, exit_reason: str, exit_type: str):
        """設定向平倉資訊"""
        self.exit_price = exit_price
        self.exit_reason = exit_reason
        self.exit_type = exit_type
        self.exit_time = datetime.now()
    
    def get_mae(self) -> float:
        """獲取最大回撤 (Maximum Adverse Excursion)"""
        return self.max_unrealized_loss
    
    def get_mfe(self) -> float:
        """獲取最大盈利 (Maximum Favorable Excursion)"""
        return self.max_unrealized_pnl
    
    def to_dict(self) -> Dict:
        """轉為字典"""
        return {
            'symbol': self.symbol,
            'side': self.side,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'highest_price': self.highest_price,
            'lowest_price': self.lowest_price,
            'max_unrealized_pnl': self.max_unrealized_pnl,
            'max_unrealized_loss': self.max_unrealized_loss,
            'max_pnl_percent': self.max_pnl_percent,
            'min_pnl_percent': self.min_pnl_percent,
            'holding_minutes': self.get_holding_minutes()
        }


class CooldownManager:
    """冷卻與黑名單管理器"""
    
    def __init__(self, enabled: bool = True, duration_minutes: int = 3,
                 blacklist_window_minutes: int = 60,
                 blacklist_threshold: int = 2,
                 blacklist_duration_minutes: int = 60):
        """
        初始化冷卻管理器
        
        Args:
            enabled: 是否啟用冷卻
            duration_minutes: 冷卻持續時間（分鐘）
            blacklist_window_minutes: 黑名單統計視窗（分鐘）
            blacklist_threshold: 觸發黑名單的虧損次數
            blacklist_duration_minutes: 黑名單持續時間（分鐘）
        """
        self.enabled = enabled
        self.duration = duration_minutes
        self.blacklist_window = blacklist_window_minutes
        self.blacklist_threshold = blacklist_threshold
        self.blacklist_duration = blacklist_duration_minutes
        
        # 冷卻記錄：{symbol: expiry_datetime}
        self.cooldowns: Dict[str, datetime] = {}
        
        # 黑名單：{symbol: expiry_datetime}
        self.blacklist: Dict[str, datetime] = {}
        
        # 交易歷史：[(symbol, timestamp, pnl)]
        self.trade_history: List[tuple] = []
    
    def add_cooldown(self, symbol: str, duration_minutes: int = None):
        """添加冷卻"""
        if not self.enabled:
            return
        
        duration = duration_minutes or self.duration
        expiry = datetime.now() + timedelta(minutes=duration)
        self.cooldowns[symbol] = expiry
    
    def record_trade(self, symbol: str, pnl: float):
        """
        記錄交易（用於黑名單判斷）
        
        Args:
            symbol: 交易對
            pnl: 損益 (USDT)
        """
        now = datetime.now()
        self.trade_history.append((symbol, now, pnl))
        
        # 清理舊的交易記錄
        window_start = now - timedelta(minutes=self.blacklist_window)
        self.trade_history = [
            (s, t, p) for s, t, p in self.trade_history
            if t > window_start
        ]
        
        # 統計指定標的在視窗內的交易次數和虧損次數
        recent_trades = [
            (s, t, p) for s, t, p in self.trade_history
            if s == symbol
        ]
        
        loss_count = sum(1 for _, _, p in recent_trades if p < 0)
        
        # 如果虧損次數超過門檻，加入黑名單
        if loss_count >= self.blacklist_threshold:
            expiry = now + timedelta(minutes=self.blacklist_duration)
            self.blacklist[symbol] = expiry
            print(f"[黑名單] {symbol} 進入黑名單！{self.blacklist_window} 分鐘內交易 {len(recent_trades)} 次，虧損 {loss_count} 次，冷卻 {self.blacklist_duration} 分鐘")
    
    def is_blacklisted(self, symbol: str) -> bool:
        """檢查標的是否在黑名單中"""
        if symbol not in self.blacklist:
            return False

        # 檢查是否過期
        if datetime.now() > self.blacklist[symbol]:
            del self.blacklist[symbol]
            return False

        return True

    def get_blacklist_remaining(self, symbol: str) -> int:
        """取得黑名單剩餘時間（秒）"""
        if symbol not in self.blacklist:
            return 0
        if datetime.now() > self.blacklist[symbol]:
            return 0
        remaining = self.blacklist[symbol] - datetime.now()
        return max(0, int(remaining.total_seconds()))
    
    def is_in_cooldown(self, symbol: str) -> bool:
        """檢查標的是否在冷卻中（包含一般冷卻和黑名單）"""
        # 檢查黑名單（優先級最高）
        if self.is_blacklisted(symbol):
            return True
        
        if not self.enabled:
            return False
        
        if symbol not in self.cooldowns:
            return False
        
        # 檢查是否過期
        if datetime.now() > self.cooldowns[symbol]:
            del self.cooldowns[symbol]
            return False
        
        return True
    
    def get_cooldown_remaining(self, symbol: str) -> int:
        """
        取得冷卻剩餘時間（秒）
        
        Args:
            symbol: 交易對
        
        Returns:
            剩餘秒數，不在冷卻中則為 0
        """
        if not self.enabled or symbol not in self.cooldowns:
            return 0
        
        # 【關鍵修復】先檢查是否過期
        if datetime.now() > self.cooldowns[symbol]:
            return 0  # 已過期，返回 0
        
        remaining = self.cooldowns[symbol] - datetime.now()
        return max(0, int(remaining.total_seconds()))
    
    def cleanup(self):
        """清理過期的冷卻記錄"""
        if not self.enabled:
            return
        
        expired = [
            symbol for symbol, expiry in self.cooldowns.items()
            if datetime.now() > expiry
        ]
        for symbol in expired:
            del self.cooldowns[symbol]
    
    def get_active_cooldowns(self) -> Dict[str, int]:
        """
        取得所有生效中的冷卻
        
        Returns:
            {symbol: remaining_seconds}
        """
        self.cleanup()
        
        return {
            symbol: max(0, int((expiry - datetime.now()).total_seconds()))
            for symbol, expiry in self.cooldowns.items()
        }


class PositionManager:
    """持倉管理器"""
    
    def __init__(self, max_positions: int = 3):
        """
        初始化持倉管理器
        
        Args:
            max_positions: 最大持倉數量
        """
        self.max_positions = max_positions
        self.positions: Dict[str, Position] = {}
    
    def add_position(self, symbol: str, entry_price: float, quantity: float,
                     leverage: int = 10, side: str = 'LONG',
                     entry_reason: str = '', entry_score: float = 0.0) -> Position:
        """添加持倉"""
        position = Position(
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            leverage=leverage,
            side=side,
            entry_reason=entry_reason,
            entry_score=entry_score
        )
        self.positions[symbol] = position
        return position
    
    def remove_position(self, symbol: str, reason: str = '', order_type: str = ''):
        """移除持倉"""
        if symbol in self.positions:
            del self.positions[symbol]
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """獲取持倉"""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """獲取所有持倉"""
        return list(self.positions.values())
    
    def has_position(self, symbol: str) -> bool:
        """檢查是否有持倉"""
        return symbol in self.positions
    
    def get_position_count(self) -> int:
        """獲取持倉數量"""
        return len(self.positions)
    
    def can_open_position(self) -> bool:
        """是否可以開新持倉"""
        return len(self.positions) < self.max_positions
    
    def update_prices(self, prices: Dict[str, float]):
        """
        更新所有持倉的價格
        
        Args:
            prices: {symbol: price}
        """
        for symbol, position in self.positions.items():
            if symbol in prices:
                position.update_price(prices[symbol])
    
    def get_total_pnl(self) -> float:
        """獲取總 PnL"""
        total = 0.0
        for position in self.positions.values():
            # 需要當前價格，這裡簡化處理
            pass
        return total
    
    def clear_all(self):
        """清空所有持倉"""
        self.positions.clear()
