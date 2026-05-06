from utils.logger import CryptoLogger
"""
CryptoAI 自動交易系統主程式
完整混合策略：固定止損、移動止損、分批出場、時間止損、技術出場
"""
import os
import sys
import time
import yaml
import random
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, Set

# 加入路徑
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_PATH)

from services.binance_client import BinanceFuturesClient
from analyzer.screener import Screener
from analyzer.trend import TrendAnalyzer
from analyzer.signal import SignalGenerator
from executor.position import PositionManager, CooldownManager
from executor.risk import RiskManager
from executor.order import OrderExecutor


def load_config(config_path: str = None) -> Dict:
    """載入配置文件"""
    if config_path is None:
        config_path = os.path.join(BASE_PATH, 'config.yaml')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_api_input() -> tuple:
    """取得用戶 API 輸入"""
    print("\n" + "=" * 60)
    print(" CryptoAI 自動交易系統")
    print("=" * 60)
    
    # 選擇模式
    while True:
        print("\n請選擇交易模式:")
        print(" 1. 模擬交易 (測試網)")
        print(" 2. 實盤交易 (正式網)")
        print(" 3. 本地模擬盤 (使用實盤數據 + 本地撮合)")
        print(" 4. 離開")
        
        choice = input("\n請輸入選項 (1/2/3/4): ").strip()
        
        if choice == '1':
            testnet = True
            break
        elif choice == '2':
            testnet = False
            break
        elif choice == '3':
            # 本地模擬盤模式 - 不需要 API Key
            print("\n[本地模擬盤] 將使用 Binance 實盤數據進行本地撮合")
            print("提示：此模式不需要 API Key，交易完全在本地模擬")
            return None, None, 'paper'
        elif choice == '4':
            print("再見！")
            sys.exit(0)
        else:
            print("無效輸入，請重新選擇")
    
    mode_name = "模擬交易" if testnet else "實盤交易"
    print(f"\n已選擇：{mode_name}")
    
    # 輸入 API Key
    print("\n" + "-" * 60)
    print("請輸入 Binance API 金鑰")
    print("提示：可在 Binance 官網 -> 個人中心 -> API 管理 建立")
    print("-" * 60)
    
    api_key = input("\nAPI Key: ").strip()
    api_secret = input("API Secret: ").strip()
    
    # 驗證輸入
    if not api_key or not api_secret:
        print("\n[錯誤] API Key 或 Secret 不能為空")
        print("重新開始設定...")
        return get_api_input()
    
    # 簡單驗證格式
    if len(api_key) < 10 or len(api_secret) < 10:
        print("\n[警告] API Key 格式似乎有誤，請確認是否正確複製")
        retry = input("是否重新輸入？(y/n): ").strip().lower()
        if retry == 'y':
            return get_api_input()
    
    return api_key, api_secret, testnet


class CryptoAITrader:
    """CryptoAI 交易器主類別"""
    
    def __init__(self, config: Dict, client: BinanceFuturesClient):
        """初始化交易器"""
        self.config = config
        self.client = client
        self.running = False
        
        self.check_interval = config.get('trading', {}).get('check_interval', 10)
        self.hour_weight = config.get('trading', {}).get('hour_weight', {
            "00-06": 0.0,
            "07-12": 0.5,
            "13-18": 0.8,
            "19-22": 2.0,
            "23-23": 1.0,
        })
        
        # 初始化冷卻管理器
        cooldown_config = config.get('cooldown', {})
        self.cooldown_enabled = cooldown_config.get('enabled', True)
        self.cooldown_duration = cooldown_config.get('duration_minutes', 3)
        # 黑名單機制參數
        self.blacklist_window = cooldown_config.get('blacklist_window_minutes', 60)
        self.blacklist_threshold = cooldown_config.get('blacklist_threshold', 2)
        self.blacklist_duration = cooldown_config.get('blacklist_duration_minutes', 60)
        
        self.cooldown_manager = CooldownManager(
            enabled=self.cooldown_enabled,
            duration_minutes=self.cooldown_duration,
            blacklist_window_minutes=self.blacklist_window,
            blacklist_threshold=self.blacklist_threshold,
            blacklist_duration_minutes=self.blacklist_duration
        )
        
        # 初始化組件
        self.position_manager = PositionManager(
            max_positions=config.get('trading', {}).get('max_position', 3)
        )
        self.logger = CryptoLogger(config=config)
        self.screener = Screener(client, config)
        self.signal_generator = SignalGenerator(client, config)
        self.risk_manager = RiskManager(config)
        self.order_executor = OrderExecutor(
            client, 
            self.position_manager, 
            config,
            self.cooldown_manager  # 傳入冷卻管理器
        )
        
        self.ws_client = None
        self._init_websocket()

        # 命令執行線程
        self.command_thread = None
        self._output_lock = threading.Lock()

        # 快/慢循環配置
        self.fast_interval = config.get('trading', {}).get('fast_check_interval', 1)  # 快：1秒
        self.slow_interval = config.get('trading', {}).get('slow_check_interval', 10)  # 慢：10秒

        # 持倉 symbol 訂閱狀態
        self._ws_subscribed: Set[str] = set()
        self._ws_subscribed_lock = threading.Lock()

    def _init_websocket(self):
        """初始化 WebSocket 客戶端"""
        try:
            from services.websocket_client import get_websocket_client
            self.ws_client = get_websocket_client()
            self.ws_client.start()
            print("[WebSocket] 已啟動")
        except Exception as e:
            print(f"[WebSocket] 初始化失敗: {e}")
            self.ws_client = None

    def _update_websocket_subscriptions(self):
        """更新 WebSocket 訂閱（訂閱當前持倉的幣種）"""
        if not self.ws_client:
            return

        positions = self.position_manager.get_all_positions()
        symbols = [pos.symbol for pos in positions]

        with self._ws_subscribed_lock:
            new_symbols = set(symbols)
            # 找出需要新增和移除的
            to_add = new_symbols - self._ws_subscribed
            to_remove = self._ws_subscribed - new_symbols

            if to_remove:
                self.ws_client.unsubscribe(list(to_remove))

            if to_add:
                self.ws_client.subscribe(list(to_add))

            self._ws_subscribed = new_symbols
    
    def _safe_print(self, *args, **kwargs):
        """執行緒安全的輸出"""
        with self._output_lock:
            print(*args, **kwargs)

    def _get_current_hour_weight(self) -> float:
        """取得當前 UTC 時段權重"""
        utc_hour = datetime.now(timezone.utc).hour
        for period, weight in self.hour_weight.items():
            start, end = period.split("-")
            start_h, end_h = int(start), int(end)
            if start_h <= utc_hour <= end_h:
                return float(weight)
        return 1.0

    def _should_skip_by_hour_weight(self) -> tuple[bool, float, int]:
        """根據時段權重判斷是否跳過本輪"""
        utc_hour = datetime.now(timezone.utc).hour
        weight = self._get_current_hour_weight()
        if weight <= 0:
            return True, weight, utc_hour
        if 0 < weight < 1.0:
            return (random.random() > weight), weight, utc_hour
        return False, weight, utc_hour

    def _get_effective_interval(self) -> float:
        """根據時段權重計算有效檢查間隔（權重>1 時縮短間隔）"""
        weight = self._get_current_hour_weight()
        if weight <= 0:
            return float(self.check_interval)
        if weight > 1.0:
            # 真加倍頻率: 2.0 => 間隔減半
            return max(1.0, float(self.check_interval) / float(weight))
        return float(self.check_interval)
    
    def start(self):
        """啟動交易器"""
        print("\n" + "=" * 60)
        print(" 啟動 CryptoAI 交易器")
        print("=" * 60)
        
        # 檢查 API 連接
        try:
            account = self.client.get_account_info()
            balance = self.client.get_usdt_balance()
            print(f"\n✓ API 連接成功")
            print(f" 帳戶餘額：{balance:.2f} USDT")
            print(f" 測試網：{'是' if self.client.testnet else '否'}")
            print(f" 冷卻機制：{'啟用' if self.cooldown_enabled else '停用'} ({self.cooldown_duration}分鐘)")
        except Exception as e:
            print(f"\n✗ API 連接失敗：{str(e)}")
            print(" 請檢查 API Key 是否正確，或是否有 IP 白名單限制")
            return
        
        # 啟動命令監聽
        self.command_thread = threading.Thread(target=self._command_listener, daemon=True)
        self.command_thread.start()

        # 開始雙層檢查架構
        self.running = True
        self._main_loop()

    def _main_loop(self):
        """雙層檢查架構主迴圈

        - 快循環 (1秒): 檢查持倉價格和風控（使用 WebSocket）
        - 慢循環 (10秒): 選幣、情緒分析、進場判斷（使用 REST API）
        """
        print("\n[系統] 開始雙層檢查架構...")
        print(f"  快循環: 每 {self.fast_interval} 秒檢查持倉價格")
        print(f"  慢循環: 每 {self.slow_interval} 秒執行選幣篩選")

        fast_last = 0
        slow_last = 0
        fast_count = 0
        slow_count = 0

        while self.running:
            try:
                current_time = time.time()

                # 快循環：檢查持倉價格（使用 WebSocket，無 API 限制）
                if current_time - fast_last >= self.fast_interval:
                    fast_count += 1
                    self._fast_loop()
                    fast_last = current_time

                # 慢循環：選幣篩選（使用 REST API，有速率限制）
                if current_time - slow_last >= self.slow_interval:
                    slow_count += 1
                    self._slow_loop()
                    slow_last = current_time

                # 休眠（避免 CPU 滿載）
                time.sleep(0.1)

            except KeyboardInterrupt:
                print("\n[系統] 收到中斷信號")
                self.stop()
                break
            except Exception as e:
                print(f"[錯誤] 主迴圈異常：{str(e)}")
                time.sleep(1)

    def _fast_loop(self):
        """快循環：每秒檢查持倉價格和風控（使用 WebSocket）"""
        positions = self.position_manager.get_all_positions()
        if not positions:
            return

        # 更新 WebSocket 訂閱
        self._update_websocket_subscriptions()

        for position in positions:
            try:
                # 優先使用 WebSocket 價格，否則用 REST fallback
                current_price = None
                if self.ws_client:
                    current_price = self.ws_client.get_price(position.symbol)

                # WebSocket 無價格時 fallback 到 REST
                if current_price is None or current_price <= 0:
                    current_price = self.order_executor.get_current_price(position.symbol)

                if current_price is None or current_price <= 0:
                    continue

                # 更新持倉價格
                position.update_price(current_price)

                # 檢查風控（止損/止盈）- 不需要 MA
                exit_signal = self.risk_manager.check_exit(
                    position, current_price, volume_ratio=1.0, ma_price=None
                )

                if exit_signal:
                    self._safe_print(
                        f"\n[⚡ 快循環 出場] {position.symbol}"
                        f" | 價格: {current_price:.4f}"
                        f" | 類型: {exit_signal['type']}"
                        f" | 原因: {exit_signal['reason']}"
                    )
                    self._execute_exit(position.symbol, exit_signal)

            except Exception as e:
                self._safe_print(f"[快循環 錯誤] {position.symbol}: {str(e)}")

    def _slow_loop(self):
        """慢循環：選幣篩選和進場（使用 REST API）"""
        # 0. 調試：輸出開始標記
        print(f"\n[慢循環 診斷] ===== 開始 =====")

        # 1. 時段篩選
        should_skip, weight, utc_hour = self._should_skip_by_hour_weight()
        if should_skip:
            print(f"[慢循環 診斷] 時段篩選跳過 (UTC {utc_hour:02d}:00)")
            return

        # 2. 清理過期冷卻
        self.cooldown_manager.cleanup()
        active_cooldowns = self.cooldown_manager.get_active_cooldowns()
        print(f"[慢循環 診斷] 活躍冷卻: {len(active_cooldowns)} 個, 持倉: {len(self.position_manager.get_all_positions())} 個")

        # 3. 清理 WebSocket 訂閱
        self._update_websocket_subscriptions()

        # 4. 檢查是否可以開新倉
        if not self.position_manager.can_open_position():
            print(f"[慢循環 診斷] 持倉已滿，跳過篩選")
            self._show_positions_summary()
            return

        # 5. 篩選候補幣種
        print("[慢循環] 篩選候補幣種...")
        candidates = self.screener.screen()

        if not candidates:
            print("[慢循環] 無符合條件的幣種")
            return

        print(f"[慢循環] 找到 {len(candidates)} 個候補")

        # 6. 依序檢查買入信號
        for candidate in candidates:
            symbol = candidate['symbol']

            if self.position_manager.has_position(symbol):
                print(f"[慢循環 診斷] 跳過 {symbol} — 已有持倉")
                continue

            # 冷卻檢查（有空位時可放寬，但黑名單不可繞過）
            in_blacklist = self.cooldown_manager.is_blacklisted(symbol)
            cooldown_remaining = self.cooldown_manager.get_cooldown_remaining(symbol)
            if in_blacklist:
                blacklist_remaining = self.cooldown_manager.get_blacklist_remaining(symbol)
                print(f"[慢循環 診斷] 跳過 {symbol} — 黑名單中 (剩餘 {blacklist_remaining:.0f} 秒)")
                continue
            if cooldown_remaining > 0:
                # 冷卻中的幣：快過期（<30秒）才允許
                if cooldown_remaining > 30:
                    print(f"[慢循環 診斷] 跳過 {symbol} — 冷卻中 (剩餘 {cooldown_remaining:.0f} 秒)")
                    continue
                print(f"[慢循環 診斷] 注意 {symbol} — 冷卻中 (僅剩 {cooldown_remaining:.0f} 秒) 仍嘗試")

            signal = self.signal_generator.generate_buy_signal(symbol)

            if signal:
                print(f"[慢循環 買入] {symbol} | 原因: {signal.get('reason')} | 信心: {signal.get('confidence', 0):.2f}")
                self._execute_buy(signal)

                if not self.position_manager.can_open_position():
                    self._show_positions_summary()
                    break
            else:
                print(f"[慢循環 診斷] {symbol} 無買入信號")
    
    def stop(self):
        """停止交易器"""
        print("\n[系統] 停止交易器...")
        self.running = False
        
        # 生成最終報告
        try:
            if hasattr(self, 'logger') and self.logger:
                self.logger.print_final_report()
        except Exception as e:
            print(f"[警告] 生成報告失敗：{str(e)}")
        
        # 清理資源
        self.cleanup()
    
    def cleanup(self):
        """清理資源（由主程式調用）"""
        print("\n[系統] 清理資源中...")
        
        # 關閉篩選器的連接
        try:
            if hasattr(self, 'screener') and self.screener:
                self.screener.close()
        except Exception as e:
            print(f"[警告] 關閉 screener 失敗：{str(e)}")
        
        # 關閉日誌
        try:
            if hasattr(self, 'logger') and self.logger:
                self.logger.close()
        except Exception as e:
            print(f"[警告] 關閉 logger 失敗：{str(e)}")
        
        print("[系統] 資源清理完成")
    
    def _command_listener(self):
        """監聽用戶命令"""
        print("\n[提示] 輸入 'help' 查看可用命令")
        
        while self.running:
            try:
                cmd = input("\n>> ").strip().lower()
                
                if not cmd:
                    continue
                
                with self._output_lock:
                    if cmd == 'help':
                        self._show_help()
                    elif cmd == 'status':
                        self._show_status()
                    elif cmd == 'positions':
                        self._show_positions()
                    elif cmd == 'balance':
                        self._show_balance()
                    elif cmd == 'cooldowns':
                        self._show_cooldowns()
                    elif cmd.startswith('close '):
                        self._manual_close(cmd.split()[1].upper())
                    elif cmd == 'closeall':
                        self._close_all()
                    elif cmd == 'exit' or cmd == 'quit':
                        self.stop()
                        break
                    else:
                        print(f"未知命令：{cmd}，輸入 'help' 查看可用命令")
                    
            except Exception as e:
                with self._output_lock:
                    print(f"[命令錯誤] {str(e)}")
    
    def _show_cooldowns(self):
        """顯示冷卻中的標的"""
        print("\n--- 冷卻清單 ---")
        cooldowns = self.cooldown_manager.get_active_cooldowns()
        
        if not cooldowns:
            print("無冷卻中的標的")
            return
        
        for symbol, remaining in cooldowns.items():
            minutes = remaining // 60
            seconds = remaining % 60
            print(f"{symbol}: {minutes}分{seconds}秒")
    
    def _show_positions_summary(self):
        """顯示持倉摘要（精簡版，用於週期檢查）"""
        positions = self.position_manager.get_all_positions()

        # 收集輸出內容
        output_lines = []
        output_lines.append(f"\n[{datetime.now().strftime('%H:%M:%S')}] === 持倉狀態 ===")
        output_lines.append(f"{'='*70}")
        output_lines.append(f"持倉總覽 ({len(positions)}/{self.position_manager.max_positions})")
        output_lines.append(f"{'='*70}")

        total_pnl = 0.0

        for pos in positions:
            try:
                current_price = self.order_executor.get_current_price(pos.symbol)
                pnl = pos.get_pnl(current_price)
                pnl_percent = pos.get_pnl_percent(current_price)
                total_pnl += pnl

                output_lines.append(f" {pos.symbol}:")
                output_lines.append(f"  進場價：{pos.entry_price:.4f} | 當前價：{current_price:.4f}")
                output_lines.append(f"  數量：{pos.quantity:.2f} | 槓桿：{pos.leverage}x")
                output_lines.append(f"  收益：{pnl:+.2f} USDT ({pnl_percent:+.2f}%)")
                output_lines.append(f"  持倉時間：{pos.get_holding_minutes()} 分鐘")
            except Exception as e:
                output_lines.append(f" {pos.symbol}: 取得數據失敗 - {str(e)}")

        output_lines.append(f"{'='*70}")
        output_lines.append(f"  總持倉數：{len(positions)}")
        output_lines.append(f"  總收益：{total_pnl:+.2f} USDT")
        output_lines.append(f"{'='*70}\n")

        # 合併並輸出
        output = '\n'.join(output_lines) + '\n'
        print(output)

        # 寫入日誌檔
        if hasattr(self, 'logger') and self.logger:
            self.logger.log_cycle_console(output)
    def _show_help(self):
        """顯示幫助"""
        print("""
可用命令:
    help - 顯示此幫助訊息
    status - 顯示系統狀態
    positions - 顯示當前持倉
    balance - 顯示帳戶餘額
    cooldowns - 顯示冷卻中的標的
    close <SYMBOL> - 平倉指定幣種 (如：close BTCUSDT)
    closeall - 平倉所有持倉
    exit/quit - 退出系統
""")
    
    def _show_status(self):
        """顯示狀態"""
        print("\n--- 系統狀態 ---")
        print(f"運行狀態：{'運行中' if self.running else '已停止'}")
        print(f"持倉數量：{self.position_manager.get_position_count()}")
        print(f"檢查間隔：{self.check_interval} 秒")
        print(f"最大持倉：{self.position_manager.max_positions}")
        print(f"冷卻機制：{'啟用' if self.cooldown_enabled else '停用'}")
        
        # 顯示冷卻中的標的
        cooldowns = self.cooldown_manager.get_active_cooldowns()
        if cooldowns:
            print(f"冷卻中標的：{len(cooldowns)} 個")
    
    def _show_positions(self):
        """顯示持倉"""
        print("\n--- 當前持倉 ---")
        positions = self.position_manager.get_all_positions()
        
        if not positions:
            print("無持倉")
            return
        
        for pos in positions:
            try:
                current_price = self.order_executor.get_current_price(pos.symbol)
                pnl = pos.get_pnl(current_price)
                pnl_pct = pos.get_pnl_percent(current_price)
                
                print(f"\n{pos.symbol}:")
                print(f"  進場價：{pos.entry_price:.4f}")
                print(f"  當前價：{current_price:.4f}")
                print(f"  數量：{pos.quantity:.6f}")
                print(f"  槓桿：{pos.leverage}x")
                print(f"  PnL: {pnl:+.2f} USDT ({pnl_pct:+.2f}%)")
                print(f"  持倉時間：{pos.get_holding_minutes()} 分鐘")
            except Exception as e:
                print(f"{pos.symbol}: 取得數據失敗 - {str(e)}")
    
    def _show_balance(self):
        """顯示餘額"""
        try:
            account = self.client.get_account_info()
            balance = self.client.get_usdt_balance()
            
            print("\n--- 帳戶資訊 ---")
            print(f"可用餘額：{float(balance):.2f} USDT")
            print(f"總資產：{float(account.get('totalWalletBalance', 0)):.2f} USDT")
            print(f"未平損益：{float(account.get('crossUnPnl', 0)):.2f} USDT")
        except Exception as e:
            print(f"[錯誤] {str(e)}")
    
    def _manual_close(self, symbol: str):
        """手動平倉"""
        symbol = symbol.upper().replace('USDT', '') + 'USDT'
        print(f"\n[手動平倉] {symbol}")
        
        position = self.position_manager.get_position(symbol)
        if not position:
            print(f"[錯誤] 無 {symbol} 持倉")
            return
        
        # 1. 先執行平倉，取得真實 PnL
        result = self.order_executor.close_position(symbol, reason='手動平倉', order_type='MANUAL')
        
        # 2. 從回傳結果取得真實 PnL
        real_pnl = result.get('pnl', 0)
        real_pnl_percent = result.get('pnl_percent', 0)
        real_exit_price = result.get('price', 0)
        close_quantity = result.get('quantity', 0)
        
        # 3. 再記錄日誌（使用真實數據）
        self.logger.log_trade(
            event_type='SELL',
            symbol=symbol,
            side='LONG',
            price=real_exit_price,
            quantity=close_quantity,
            leverage=position.leverage,
            pnl_usdt=real_pnl,
            pnl_percent=real_pnl_percent,
            reason='手動平倉',
            holding_time=position.get_holding_minutes(),
            details=f"手動平倉 | PnL: {real_pnl:+.2f} USDT ({real_pnl_percent:+.2f}%)"
        )
    
    def _close_all(self):
        """平倉所有"""
        print("\n[全部平倉]")
        positions = self.position_manager.get_all_positions()
        
        if not positions:
            print("無持倉")
            return
        
        for pos in positions:
            position_data = self.position_manager.get_position(pos.symbol)
            
            # 1. 先執行平倉，取得真實 PnL
            result = self.order_executor.close_position(pos.symbol, reason='全部平倉', order_type='MANUAL')
            
            # 2. 從回傳結果取得真實 PnL
            real_pnl = result.get('pnl', 0)
            real_pnl_percent = result.get('pnl_percent', 0)
            real_exit_price = result.get('price', 0)
            close_quantity = result.get('quantity', 0)
            
            # 3. 再記錄日誌（使用真實數據）
            if position_data:
                self.logger.log_trade(
                    event_type='SELL',
                    symbol=pos.symbol,
                    side='LONG',
                    price=real_exit_price,
                    quantity=close_quantity,
                    leverage=position_data.leverage,
                    pnl_usdt=real_pnl,
                    pnl_percent=real_pnl_percent,
                    reason='全部平倉',
                    holding_time=position_data.get_holding_minutes(),
                    details=f"手動平倉 | PnL: {real_pnl:+.2f} USDT ({real_pnl_percent:+.2f}%)"
                )
    
    
    
    def _update_positions(self):
        """更新並檢查所有持倉"""
        positions = self.position_manager.get_all_positions()
        
        for position in positions:
            try:
                # 取得當前價格
                current_price = self.order_executor.get_current_price(position.symbol)
                position.update_price(current_price)
                
                # 取得趨勢數據 (包含 MA)
                trend_data = self.signal_generator.trend_analyzer.analyze(position.symbol)
                volume_ratio = trend_data.get('volume_ratio', 1.0)
                ma_price = trend_data.get('ma', None)
                
                # 檢查出場條件 (傳入 MA 供技術出場使用)
                exit_signal = self.risk_manager.check_exit(
                    position, current_price, volume_ratio, ma_price
                )
                
                if exit_signal:
                    self._safe_print(f"\n[出場信號] {position.symbol}")
                    self._safe_print(f" 類型：{exit_signal['type']}")
                    self._safe_print(f" 原因：{exit_signal['reason']}")
                    
                    # 執行出場
                    self._execute_exit(position.symbol, exit_signal)
                    # 跳出，讓主迴圈重新獲取持倉列表（避免無限迴圈）
                    return
                
            except Exception as e:
                self._safe_print(f"[錯誤] 更新持倉失敗 {position.symbol}: {str(e)}")


    def _execute_buy(self, signal: Dict):
        """執行買入 - 保守配置：固定金額模式"""
        symbol = signal['symbol']
        
        try:
            # 取得帳戶餘額
            account_info = self.client.get_account_info()
            balance = float(account_info.get('totalWalletBalance', 1000))
            
            # 取得槓桿
            leverage = self.config.get('trading', {}).get('leverage', 10)
            
            # 取得資金配置模式
            capital_mode = self.config.get('trading', {}).get('capital_mode', 'fixed')
            
            # 計算每倉保證金
            if capital_mode == 'fixed':
                # 固定金額模式：每倉固定 USDT 金額
                capital_per_position = self.config.get('trading', {}).get('fixed_capital_per_position', 10)
                mode_desc = f"固定金額 {capital_per_position} USDT"
            else:
                # 百分比模式：每倉固定百分比
                percent = self.config.get('trading', {}).get('percent_capital_per_position', 10)
                capital_per_position = balance * (percent / 100)
                mode_desc = f"百分比 {percent}% = {capital_per_position:.2f} USDT"
            
            # 計算持倉大小（數量）
            # 公式：數量 = (保證金 × 槓桿) / 價格
            quantity = (capital_per_position * leverage) / signal['price']
            
            # 顯示資金資訊
            print(f"  帳戶餘額：{balance:.2f} USDT")
            print(f"  資金模式：{mode_desc}")
            print(f"  槓桿：{leverage}x")
            print(f"  保證金：{capital_per_position:.2f} USDT")
            print(f"  交易金額：{capital_per_position * leverage:.2f} USDT")
            print(f"  數量：{quantity:.6f}")
            
            # 【日誌記錄】買入前記錄到 CryptoLogger
            self.logger.log_trade(
            event_type='BUY',
            symbol=symbol,
            side='LONG',
            price=signal.get('price', 0),
            quantity=quantity,
            leverage=leverage,
            pnl_usdt=0,
            pnl_percent=0,
            reason=signal.get('reason', ''),
            holding_time=0,
            details=f"信心指數：{signal.get('confidence', 0):.2f}"
            )
        
            # 下單
            result = self.order_executor.open_long(symbol, quantity)
            
            if result.get('success'):
                print(f"[成功] 建立持倉 {symbol}")
            else:
                print(f"[失敗] {result.get('error')}")
            
        except Exception as e:
            print(f"[錯誤] 買入失敗：{str(e)}")
    
    def _execute_exit(self, symbol: str, exit_signal: Dict):
        """執行出金"""
        try:
            position = self.position_manager.get_position(symbol)
            if not position:
                return
            
            quantity_ratio = exit_signal.get('quantity_ratio', 1.0)
            exit_type = exit_signal.get('type', '')
            reason = exit_signal.get('reason', '')
            
            # 對於分批出金，記錄目標水平
            exited_pnl_percent = None
            if exit_type == 'SCALING_OUT':
                target_level = exit_signal.get('target_level')
                if target_level:
                    exited_pnl_percent = target_level
            
            # 1. 先執行平倉，取得真實 PnL
            if quantity_ratio >= 1.0:
                result = self.order_executor.close_position(
                    symbol,
                    reason=reason,
                    order_type=exit_type,
                )
            else:
                result = self.order_executor.reduce_position(
                    symbol,
                    quantity_ratio,
                    reason=reason,
                )
            
            # 2. 從回傳結果取得真實 PnL
            real_pnl = result.get('pnl', 0)
            real_pnl_percent = result.get('pnl_percent', 0)
            real_exit_price = result.get('price', 0)
            close_quantity = result.get('quantity', 0)
            
            # 3. 取得持倉時間
            holding_time = 0
            if position:
                holding_time = position.get_holding_minutes()
            
            # 4. 再記錄日誌（使用真實數據）
            self.logger.log_trade(
                event_type='SELL',
                symbol=symbol,
                side='LONG',
                price=real_exit_price,
                quantity=close_quantity,
                leverage=self.config.get('trading', {}).get('leverage', 10),
                pnl_usdt=real_pnl,
                pnl_percent=real_pnl_percent,
                reason=reason,
                holding_time=holding_time,
                details=f"出金原因：{reason} | PnL: {real_pnl:+.2f} USDT ({real_pnl_percent:+.2f}%)"
            )
            
        except Exception as e:
            self._safe_print(f"[錯誤] 出金失敗：{str(e)}")


def main():
    """主函數"""
    print("""
╔══════════════════════════════════════════════════╗
║ ║
║ CryptoAI 自動交易系統 v2.0 ║
║ 完整混合策略：固定止損 + 移動止損 + 分批出場 ║
║ + 時間止損 + 技術出場 ║
║ ║
╚══════════════════════════════════════════════════╝
    """)
    
    # 載入配置
    config = load_config()
    
    # 取得 API 輸入
    api_key, api_secret, mode = get_api_input()
    
    # 根據模式建立客戶端
    if mode == 'paper':
        # 本地模擬盤模式
        from services.paper_client import PaperTradingClient
        initial_balance = config.get('trading', {}).get('initial_capital', 10000)
        leverage = config.get('trading', {}).get('leverage', 10)
        print(f"\n[本地模擬盤] 初始資金：{initial_balance} USDT | 槓桿：{leverage}x")
        
        # 建立模擬交易客戶端
        client = PaperTradingClient(initial_balance=initial_balance, leverage=leverage)
        
        # 建立一個只讀的實盤客戶端用於獲取市場數據 (Screener 專用)
        print("[數據模式] 使用 Binance 實盤數據源 (只讀)")
        data_client = BinanceFuturesClient(api_key='dummy', api_secret='dummy', testnet=False)
        # 將 data_client 綁定到 client 上，供 Screener 使用
        client.data_client = data_client
        
    elif mode == 'testnet' or mode is True:
        # 測試網模式
        client = BinanceFuturesClient(api_key, api_secret, testnet=True)
    else:
        # 實盤模式
        client = BinanceFuturesClient(api_key, api_secret, testnet=False)
    
    # 建立交易器
    trader = CryptoAITrader(config, client)
    
    # 啟動
    trader.start()
    
    print("\n[系統] 交易器已停止")


if __name__ == '__main__':
    main()
