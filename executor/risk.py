import os
"""
風險管理模組 v2.0
混合策略：固定止損(8%)、兩階段移動止盈、全數止盈(40%)
取消：鐵三角技術出局
"""
from typing import Dict, Optional, Tuple, Set
from datetime import datetime
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from executor.position import Position


class RiskManager:
    """風險管理器 - 簡化版 v2.0"""
    
    def __init__(self, config: Dict):
        """
        初始化風險管理器
        
        Args:
            config: 配置字典
        """
        self.config = config.get('trading', {})
        self.scaling_config = config.get('scaling_out', {})
        
        # 固定止損 (8%)
        self.stop_loss_percent = self.config.get('stop_loss_percent', 8)
        
        # 移動止盈 - 兩階段
        self.trailing_stop_enabled = self.config.get('trailing_stop_enabled', True)
        self.trailing_phase1_trigger = self.config.get('trailing_phase1_trigger', 8)      # 第一階段觸發：8%
        self.trailing_phase1_retention = self.config.get('trailing_phase1_retention', 0.50)  # 保留 50%
        self.trailing_phase2_trigger = self.config.get('trailing_phase2_trigger', 10)     # 第二階段觸發：10%
        self.trailing_phase2_retention = self.config.get('trailing_phase2_retention', 0.67)  # 保留 67%
        
        # 全數止盈
        self.full_exit_percent = self.config.get('full_exit_percent', 40)
    
    def check_exit(self, position: Position, current_price: float, 
                   volume_ratio: float = 1.0, ma_price: Optional[float] = None) -> Optional[Dict]:
        """
        檢查出局條件（依優先級）
        
        優先級:
        1. 固定止損 (最高)
        2. 全數止盈 (40%)
        3. 兩階段移動止盈
        
        注意：鐵三角技術出局已移除
        """
        # 計算 PnL
        pnl = position.get_pnl(current_price)
        pnl_percent = position.get_pnl_percent(current_price)
        
        # 1. 固定止損 (最高優先級) - 8%
        if pnl_percent <= -self.stop_loss_percent:
            return {
                'action': 'EXIT',
                'type': 'STOP_LOSS',
                'reason': f'固定止損 ({pnl_percent:.1f}%)',
                'quantity_ratio': 1.0,
                'priority': 1
            }
        
        # 2. 全數止盈 40%
        if pnl_percent >= self.full_exit_percent:
            return {
                'action': 'EXIT',
                'type': 'FULL_EXIT',
                'reason': f'全數止盈 ({pnl_percent:.1f}%)',
                'quantity_ratio': 1.0,
                'priority': 2
            }
        
        # 3. 移動止盈 (兩階段)
        if self.trailing_stop_enabled:
            trailing = self._check_trailing_stop(position, current_price, pnl_percent)
            if trailing:
                return trailing
        
        return None
    
    def _check_trailing_stop(self, position: Position, current_price: float, 
                             pnl_percent: float) -> Optional[Dict]:
        """
        兩階段移動止盈：
        
        Phase 1: pnl_percent >= 8% → 啟動，保留 50%
                 (回撤門檻 = 8% × 50% = 4%)
                 
        Phase 2: pnl_percent >= 10% → 切換到保留 67%
                 (回撤門檻 = 10% × 67% = 6.7%)
        """
        highest = position.highest_pnl_percent
        
        # Phase 1: 8% 觸發，保留 50%
        if highest < self.trailing_phase1_trigger:
            return None
        
        # Phase 1: 觸發了但還沒到 Phase 2
        if highest < self.trailing_phase2_trigger:
            retention = self.trailing_phase1_retention
            phase = "1"
        else:
            # Phase 2: 到達 10% 後切換到 67%
            retention = self.trailing_phase2_retention
            phase = "2"
        
        # 計算回撤閾值
        # retention = 0.50 時，drawdown_threshold = highest * 0.50
        # 例如：highest = 10%，retention = 0.50，則 threshold = 5%
        # 當 pnl_percent 跌到 < 5% 時觸發
        drawdown_threshold = highest * retention
        
        if pnl_percent < drawdown_threshold:
            drawdown_pct = highest - pnl_percent
            return {
                'action': 'EXIT',
                'type': 'TRAILING_STOP',
                'reason': f'移動止盈 (階段{phase}, 高:{highest:.1f}% → 當前:{pnl_percent:.1f}%, 閾值:{drawdown_threshold:.1f}%, 回撤:{drawdown_pct:.1f}%)',
                'quantity_ratio': 1.0,
                'priority': 3
            }
        
        return None
    
    def _check_scaling_out(self, position: Position, current_price: float,
                           pnl_percent: float) -> Optional[Dict]:
        """
        【已停用】分批出局
        """
        return None