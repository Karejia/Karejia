"""
CryptoAI 日誌管理模組
- 支援多級別日誌（INFO/TRADE/PERIODIC）
- 自動記錄到文件和記憶體
- 退出時輸出完整報告
"""
import os
import csv
import json
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque


class CryptoLogger:
    """加密交易日誌管理器"""

    def __init__(self, log_dir: str = 'logs', config: Dict = None):
        """
        初始化日誌管理器

        Args:
            log_dir: 日誌目錄
            config: 配置字典（可選）
        """
        self.log_dir = log_dir
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.config = config or {}

        # 確保日誌目錄存在
        os.makedirs(log_dir, exist_ok=True)

        # 日誌文件路徑
        self.trade_log_path = os.path.join(log_dir, f'trades_{self.timestamp}.csv')
        self.periodic_log_path = os.path.join(log_dir, f'periodic_{self.timestamp}.csv')
        self.summary_path = os.path.join(log_dir, f'summary_{self.timestamp}.json')
        self.full_log_path = os.path.join(log_dir, f'full_{self.timestamp}.txt')
        self.console_log_path = os.path.join(log_dir, f'console_{self.timestamp}.txt')

        # 記憶體緩存（環形緩存，避免記憶體爆炸）
        self.trade_history = []  # 所有交易記錄
        self.periodic_snapshots = deque(maxlen=1000)  # 最近 1000 筆週期快照
        self.periodic_count = 0  # 總週期數

        # 統計數據
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.largest_win = 0.0
        self.largest_loss = 0.0
        self.session_start = datetime.now()

        # 初始化 CSV 檔頭
        self._init_trade_log()
        self._init_periodic_log()
        self._init_full_log()
        self._init_console_log()

    def _init_trade_log(self):
        """初始化交易日誌 CSV"""
        with open(self.trade_log_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'event_type', 'symbol', 'side', 'price', 'quantity',
                'leverage', 'pnl_usdt', 'pnl_percent', 'reason', 'holding_time', 'details'
            ])

    def _init_periodic_log(self):
        """初始化週期快照 CSV"""
        with open(self.periodic_log_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'period_index', 'total_positions', 'total_pnl_usdt',
                'symbols', 'details_json'
            ])

    def _init_full_log(self):
        """初始化完整日誌檔"""
        with open(self.full_log_path, 'w', encoding='utf-8') as f:
            f.write(f"CryptoAI 交易日誌 - 開始於 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

    def _init_console_log(self):
        """初始化終端機輸出日誌檔"""
        with open(self.console_log_path, 'w', encoding='utf-8') as f:
            f.write(f"CryptoAI 終端機日誌 - 開始於 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

    def log_trade(self, event_type: str, symbol: str = '', side: str = '',
                  price: float = 0, quantity: float = 0, leverage: int = 10,
                  pnl_usdt: float = 0, pnl_percent: float = 0,
                  reason: str = '', holding_time: int = 0, details: str = ''):
        """
        記錄交易事件

        Args:
            event_type: 事件類型 (BUY, SELL, PARTIAL_EXIT, FULL_EXIT, STOP_LOSS, etc.)
            symbol: 交易對
            side: 方向 (BUY/SELL)
            price: 價格
            quantity: 數量
            leverage: 槓桿
            pnl_usdt: 損益 (USDT)
            pnl_percent: 損益 (%)
            reason: 原因
            holding_time: 持倉時間 (分鐘)
            details: 詳細資訊
        """
        timestamp = datetime.now()
        record = {
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'event_type': event_type,
            'symbol': symbol,
            'side': side,
            'price': price,
            'quantity': quantity,
            'leverage': leverage,
            'pnl_usdt': pnl_usdt,
            'pnl_percent': pnl_percent,
            'reason': reason,
            'holding_time': holding_time,
            'details': details
        }

        self.trade_history.append(record)

        # 更新統計
        if event_type in ['BUY', 'SELL']:
            self.total_trades += 1

        if event_type == 'SELL':
            if pnl_usdt > 0:
                self.winning_trades += 1
                if pnl_usdt > self.largest_win:
                    self.largest_win = pnl_usdt
            else:
                self.losing_trades += 1
                if pnl_usdt < self.largest_loss:
                    self.largest_loss = pnl_usdt
            self.total_pnl += pnl_usdt

        # 寫入 CSV
        with open(self.trade_log_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                record['timestamp'],
                record['event_type'],
                record['symbol'],
                record['side'],
                f"{record['price']:.8f}" if record['price'] else '',
                f"{record['quantity']:.8f}" if record['quantity'] else '',
                record['leverage'],
                f"{record['pnl_usdt']:.2f}",
                f"{record['pnl_percent']:.2f}",
                record['reason'],
                record['holding_time'],
                record['details']
            ])

        # 同步輸出到完整日誌
        if event_type == 'BUY':
            msg = f"[{record['timestamp']}] 🟢 買入 {symbol} {side} @ {price} | " \
                  f"數量：{quantity} | 槓桿：{leverage}x | {reason}"
        elif event_type == 'SELL':
            msg = f"[{record['timestamp']}] 🔴 賣出 {symbol} | " \
                  f"價格：{price} | PnL: {pnl_usdt:+.2f} USDT ({pnl_percent:+.2f}%) | " \
                  f"持倉：{holding_time}分鐘 | {reason}"
        elif event_type == 'PARTIAL_EXIT':
            msg = f"[{record['timestamp']}] 🟡 部分平倉 {symbol} | " \
                  f"價格：{price} | PnL: {pnl_usdt:+.2f} USDT | {reason}"
        else:
            msg = f"[{record['timestamp']}] {event_type} {symbol} | {reason}"

        self._write_to_full_log(msg)

    def log_periodic_snapshot(self, positions: List[Dict], total_pnl: float,
                              current_prices: Dict[str, float] = None):
        """
        記錄週期快照

        Args:
            positions: 持倉列表
            total_pnl: 總損益
            current_prices: 當前價格字典
        """
        timestamp = datetime.now()
        self.periodic_count += 1

        # 建立快照
        snapshot = {
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'period_index': self.periodic_count,
            'total_positions': len(positions),
            'total_pnl_usdt': total_pnl,
            'positions': []
        }

        pos_summary = []
        for pos in positions:
            symbol = pos.symbol if hasattr(pos, 'symbol') else pos.get('symbol', '')
            entry_price = pos.entry_price if hasattr(pos, 'entry_price') else pos.get('entry_price', 0)
            quantity = pos.quantity if hasattr(pos, 'quantity') else pos.get('quantity', 0)
            leverage = pos.leverage if hasattr(pos, 'leverage') else pos.get('leverage', 10)

            # 獲取當前價格
            if current_prices and symbol in current_prices:
                current_price = current_prices[symbol]
            elif hasattr(pos, 'get_current_price'):
                current_price = pos.get_current_price()
            elif hasattr(pos, 'current_price'):
                current_price = pos.current_price
            else:
                current_price = entry_price

            # 計算損益
            if hasattr(pos, 'get_pnl'):
                pnl_usdt = pos.get_pnl(current_price)
                pnl_percent = pos.get_pnl_percent(current_price)
            elif hasattr(pos, 'get_pnl_percent'):
                pnl_percent = pos.get_pnl_percent(current_price)
                pnl_usdt = pnl_percent * pos.margin / 100 if hasattr(pos, 'margin') else 0
            else:
                pnl_usdt = 0
                pnl_percent = 0

            # 獲取持倉時間
            if hasattr(pos, 'get_holding_minutes'):
                holding_minutes = pos.get_holding_minutes()
            elif hasattr(pos, 'holding_minutes'):
                holding_minutes = pos.holding_minutes
            else:
                holding_minutes = 0

            pos_info = {
                'symbol': symbol,
                'entry_price': entry_price,
                'current_price': current_price,
                'quantity': quantity,
                'leverage': leverage,
                'pnl_usdt': pnl_usdt,
                'pnl_percent': pnl_percent,
                'holding_minutes': holding_minutes
            }
            snapshot['positions'].append(pos_info)

            # 建立摘要字串
            pos_summary.append(
                f"{symbol}: {pnl_usdt:+.2f} USDT ({pnl_percent:+.2f}%) "
                f"[{holding_minutes}分鐘]"
            )

        self.periodic_snapshots.append(snapshot)

        # 寫入 CSV
        symbols = ','.join([p['symbol'] for p in snapshot['positions']])
        details_json = json.dumps(snapshot['positions'], ensure_ascii=False)

        with open(self.periodic_log_path, 'a', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                snapshot['timestamp'],
                snapshot['period_index'],
                snapshot['total_positions'],
                f"{total_pnl:.2f}",
                symbols,
                details_json
            ])

        # 輸出到完整日誌（精簡版）
        if snapshot['positions']:
            summary_text = ' | '.join(pos_summary)
            self._write_to_full_log(
                f"\n[{snapshot['timestamp']}] === 檢查週期 #{snapshot['period_index']} ===\n"
                f"持倉數：{snapshot['total_positions']} | 總 PnL: {total_pnl:+.2f} USDT\n"
                f"{summary_text}"
            )

    def _write_to_full_log(self, message: str):
        """寫入完整日誌檔"""
        with open(self.full_log_path, 'a', encoding='utf-8') as f:
            f.write(message + '\n')

    def log_cycle_console(self, content: str):
        """記錄週期檢查的終端機輸出"""
        with open(self.console_log_path, 'a', encoding='utf-8') as f:
            f.write(content)

    def generate_summary(self) -> Dict:
        """生成交易摘要報告"""
        win_rate = (self.winning_trades / (self.winning_trades + self.losing_trades) * 100) \
            if (self.winning_trades + self.losing_trades) > 0 else 0

        avg_pnl = (self.total_pnl / (self.winning_trades + self.losing_trades)) \
            if (self.winning_trades + self.losing_trades) > 0 else 0

        session_duration = datetime.now() - self.session_start

        summary = {
            'report_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'session_start': self.session_start.strftime('%Y-%m-%d %H:%M:%S'),
            'session_duration_seconds': int(session_duration.total_seconds()),
            'total_periods': self.periodic_count,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'total_pnl_usdt': self.total_pnl,
            'avg_pnl_per_trade': avg_pnl,
            'largest_win': self.largest_win,
            'largest_loss': self.largest_loss,
            'trade_log_file': self.trade_log_path,
            'periodic_log_file': self.periodic_log_path,
            'full_log_file': self.full_log_path,
            'console_log_file': self.console_log_path,
            'summary_file': self.summary_path
        }

        # 儲存 JSON 摘要
        with open(self.summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False, default=str)

        return summary

    def print_final_report(self):
        """打印最終報告"""
        # 記錄 Session 結束
        self.log_trade(
            event_type='SESSION_END',
            details=f"運行 {self.periodic_count} 個週期 | 交易 {self.total_trades} 筆 | 總損益：{self.total_pnl:+.2f} USDT"
        )

        summary = self.generate_summary()

        duration_mins = summary['session_duration_seconds'] // 60
        duration_secs = summary['session_duration_seconds'] % 60

        print("\n" + "=" * 80)
        print(" CryptoAI 交易 Session 報告")
        print("=" * 80)
        print(f"報告時間：{summary['report_time']}")
        print(f"Session 開始：{summary['session_start']}")
        print(f"運行時間：{duration_mins}分{duration_secs}秒")
        print("-" * 80)
        print(f"檢查週期數：{summary['total_periods']} 次")
        print(f"總交易數：{summary['total_trades']} 筆")
        print(f" - 買入：{summary['total_trades']} 筆（假設所有交易都是成對的）")
        print(f" - 賣出：{summary['winning_trades'] + summary['losing_trades']} 筆")
        print("-" * 80)
        print(f"獲利單數：{summary['winning_trades']}")
        print(f"虧損單數：{summary['losing_trades']}")
        print(f"勝率：{summary['win_rate']:.2f}%")
        print("-" * 80)
        print(f"總損益：{summary['total_pnl_usdt']:+.2f} USDT")
        print(f"平均每筆：{summary['avg_pnl_per_trade']:+.2f} USDT")
        print(f"最大獲利：{summary['largest_win']:+.2f} USDT")
        print(f"最大虧損：{summary['largest_loss']:+.2f} USDT")
        print("-" * 80)
        print(f"📁 交易日誌：{summary['trade_log_file']}")
        print(f"📁 週期快照：{summary['periodic_log_file']}")
        print(f"📁 完整日誌：{summary['full_log_file']}")
        print(f"📁 終端機輸出：{summary['console_log_file']}")
        print(f"📁 JSON 摘要：{summary['summary_file']}")
        print("=" * 80)

    def get_trade_history(self) -> List[Dict]:
        """獲取交易歷史"""
        return self.trade_history

    def get_periodic_snapshots(self) -> List[Dict]:
        """獲取週期快照（從環形緩存中）"""
        return list(self.periodic_snapshots)

    def close(self):
        """關閉日誌管理器（供主程式調用）"""
        pass