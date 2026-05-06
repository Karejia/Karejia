"""
交易分析工具
計算盈利因子、勝率、盈虧比等關鍵指標
"""
import csv
import os
from typing import Dict, List, Optional
from datetime import datetime
from collections import defaultdict


class TradeAnalyzer:
    """交易分析器 - 計算關鍵交易指標"""
    
    def __init__(self, csv_path: str):
        """
        初始化分析器
        
        Args:
            csv_path: trades.csv 路徑
        """
        self.csv_path = csv_path
        self.trades = []
        self._load_trades()
    
    def _load_trades(self):
        """載入 CSV 中的交易記錄"""
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"找不到交易記錄檔：{self.csv_path}")
        
        with open(self.csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 只處理有進場和出場的完整交易
                if row.get('entry_price') and row.get('exit_price'):
                    try:
                        # 轉換數值欄位
                        for field in ['leverage', 'quantity', 'entry_price', 'exit_price',
                                     'position_value_usdt', 'margin_used_usdt',
                                     'pnl_usdt', 'pnl_percent', 'roi_percent',
                                     'fee_usdt', 'net_pnl_usdt', 'highest_price',
                                     'lowest_price', 'max_unrealized_pnl',
                                     'max_unrealized_loss', 'mae_percent',
                                     'mfe_percent', 'holding_minutes',
                                     'holding_seconds', 'volatility_atr',
                                     'entry_score', 'ma_distance_percent', 'fee_rate']:
                            try:
                                row[field] = float(row[field]) if row[field] else 0.0
                            except (ValueError, TypeError):
                                row[field] = 0.0
                        
                        self.trades.append(row)
                    except Exception as e:
                        print(f"[警告] 跳過無效交易記錄：{e}")
    
    def get_summary(self) -> Dict:
        """
        取得交易摘要
        
        Returns:
            包含所有關鍵指標的字典
        """
        if not self.trades:
            return {'error': '無交易記錄'}
        
        # 分離獲利和虧損交易
        winning_trades = [t for t in self.trades if t['net_pnl_usdt'] > 0]
        losing_trades = [t for t in self.trades if t['net_pnl_usdt'] <= 0]
        
        # 計算總和
        gross_profit = sum(t['net_pnl_usdt'] for t in winning_trades)
        gross_loss = abs(sum(t['net_pnl_usdt'] for t in losing_trades))
        
        # 計算平均值
        avg_win = gross_profit / len(winning_trades) if winning_trades else 0
        avg_loss = gross_loss / len(losing_trades) if losing_trades else 0
        
        # 關鍵指標
        total_trades = len(self.trades)
        win_rate = len(winning_trades) / total_trades if total_trades > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
        profit_loss_ratio = avg_win / abs(avg_loss) if avg_loss != 0 else float('inf') if avg_win > 0 else 0
        
        # 期望值
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * abs(avg_loss)) if avg_loss != 0 else avg_win
        
        # 最大連續虧損
        max_consecutive_losses = self._max_consecutive_losses()
        
        # 最大回撤
        max_drawdown = self._calculate_max_drawdown()
        
        # 平均持倉時間
        avg_holding_minutes = sum(t['holding_minutes'] for t in self.trades) / total_trades if total_trades > 0 else 0
        
        # 總手續費
        total_fees = sum(t['fee_usdt'] for t in self.trades)
        
        return {
            '總交易次數': total_trades,
            '獲利交易': len(winning_trades),
            '虧損交易': len(losing_trades),
            '勝率 (%)': round(win_rate * 100, 2),
            '總獲利 (USDT)': round(gross_profit, 2),
            '總虧損 (USDT)': round(gross_loss, 2),
            '盈利因子': round(profit_factor, 2) if profit_factor != float('inf') else '∞',
            '平均獲利 (USDT)': round(avg_win, 2),
            '平均虧損 (USDT)': round(abs(avg_loss), 2),
            '盈虧比': round(profit_loss_ratio, 2) if profit_loss_ratio != float('inf') else '∞',
            '期望值 (USDT)': round(expectancy, 2),
            '最大連續虧損': max_consecutive_losses,
            '最大回撤 (%)': round(max_drawdown, 2),
            '平均持倉時間 (分鐘)': round(avg_holding_minutes, 1),
            '總手續費 (USDT)': round(total_fees, 2),
            '淨損益 (USDT)': round(sum(t['net_pnl_usdt'] for t in self.trades), 2)
        }
    
    def _max_consecutive_losses(self) -> int:
        """計算最大連續虧損次數"""
        max_consecutive = 0
        current_consecutive = 0
        
        for trade in self.trades:
            if trade['net_pnl_usdt'] <= 0:
                current_consecutive += 1
                max_consecutive = max(max_consecutive, current_consecutive)
            else:
                current_consecutive = 0
        
        return max_consecutive
    
    def _calculate_max_drawdown(self) -> float:
        """計算最大回撤百分比"""
        if not self.trades:
            return 0.0
        
        peak = 0.0
        max_dd = 0.0
        cumulative = 0.0
        
        for trade in self.trades:
            cumulative += trade['net_pnl_usdt']
            if cumulative > peak:
                peak = cumulative
            
            drawdown = (peak - cumulative) if peak > 0 else 0
            if drawdown > max_dd:
                max_dd = drawdown
        
        # 計算為初始資金的百分比（假設初始資金為總倉位價值）
        total_value = sum(t['position_value_usdt'] for t in self.trades[:1]) if self.trades else 1
        return (max_dd / total_value * 100) if total_value > 0 else 0.0
    
    def get_exit_type_performance(self) -> Dict[str, Dict]:
        """
        分析不同出場類型的表現
        
        Returns:
            {exit_type: {指標}}
        """
        exit_types = defaultdict(list)
        
        for trade in self.trades:
            exit_type = trade.get('exit_type', 'UNKNOWN')
            exit_types[exit_type].append(trade)
        
        result = {}
        for exit_type, trades in exit_types.items():
            net_pnls = [t['net_pnl_usdt'] for t in trades]
            wins = [p for p in net_pnls if p > 0]
            losses = [p for p in net_pnl if p <= 0]
            
            result[exit_type] = {
                '交易次數': len(trades),
                '勝率 (%)': round(len(wins) / len(trades) * 100, 2) if trades else 0,
                '平均 PnL': round(sum(net_pnls) / len(net_pnls), 2) if net_pnls else 0,
                '總 PnL': round(sum(net_pnls), 2)
            }
        
        return result
    
    def get_symbol_performance(self) -> Dict[str, Dict]:
        """
        分析各交易對的表現
        
        Returns:
            {symbol: {指標}}
        """
        symbols = defaultdict(list)
        
        for trade in self.trades:
            symbols[trade['symbol']].append(trade)
        
        result = {}
        for symbol, trades in symbols.items():
            net_pnls = [t['net_pnl_usdt'] for t in trades]
            wins = [p for p in net_pnls if p > 0]
            
            result[symbol] = {
                '交易次數': len(trades),
                '勝率 (%)': round(len(wins) / len(trades) * 100, 2) if trades else 0,
                '總 PnL (USDT)': round(sum(net_pnls), 2),
                '平均 PnL': round(sum(net_pnls) / len(net_pnls), 2) if net_pnls else 0
            }
        
        return result
    
    def generate_report(self) -> str:
        """
        生成文字報告
        
        Returns:
            格式化的文字報告
        """
        summary = self.get_summary()
        
        if 'error' in summary:
            return summary['error']
        
        # 使用簡單格式避免 f-string 問題
        report = "\n" + "=" * 60 + "\n"
        report += "         CryptoAI 交易績效報告\n"
        report += "=" * 60 + "\n\n"
        
        report += "總交易次數：" + str(summary['總交易次數']) + "\n"
        report += "  獲利：" + str(summary['獲利交易']) + " 筆 | 虧損：" + str(summary['虧損交易']) + " 筆\n"
        report += "  勝率：" + str(summary['勝率']) + "%\n"
        report += "  盈利因子：" + str(summary['盈利因子']) + "\n"
        report += "  盈虧比：" + str(summary['盈虧比']) + "\n"
        report += "  期望值：" + str(summary['期望值 (USDT)']) + " USDT\n"
        report += "  最大回撤：" + str(summary['最大回撤 (%)']) + "%\n"
        report += "  淨損益：" + str(summary['淨損益 (USDT)']) + " USDT\n"
        report += "  手續費：" + str(summary['總手續費 (USDT)']) + " USDT\n\n"
        
        # 出場類型分析
        report += "\n【出場類型分析】\n"
        exit_perf = self.get_exit_type_performance()
        for exit_type, stats in exit_perf.items():
            report += "  " + str(exit_type) + ": " + str(stats['交易次數']) + "筆 | 勝率" + str(stats['勝率']) + "% | 總PnL: " + str(stats['總 PnL']) + " USDT\n"
        
        # 交易對分析
        report += "\n【交易對分析 (Top 5)】\n"
        symbol_perf = self.get_symbol_performance()
        sorted_symbols = sorted(symbol_perf.items(), key=lambda x: x[1]['總 PnL (USDT)'], reverse=True)[:5]
        for symbol, stats in sorted_symbols:
            report += "  " + str(symbol) + ": " + str(stats['交易次數']) + "筆 | 勝率" + str(stats['勝率']) + "% | 總PnL: " + str(stats['總 PnL (USDT)']) + " USDT\n"
        
        return report


