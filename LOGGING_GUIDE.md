# CryptoAI 完整日誌系統使用說明

## 📋 功能概述

已實作完整的日誌記錄系統，支援：

1. **交易日誌** (`trades_YYYYMMDD_HHMMSS.csv`)
   - 記錄所有買入/賣出/部分平倉事件
   - 包含價格、數量、損益、原因等詳細資訊

2. **週期快照** (`periodic_YYYYMMDD_HHMMSS.csv`)
   - 每個檢查週期自動記錄持倉狀態
   - 包含每個持倉的進場價、當前價、PnL、持倉時間

3. **完整日誌** (`full_YYYYMMDD_HHMMSS.txt`)
   - 人類可讀的文字日誌
   - 按時間順序記錄所有事件

4. **JSON 摘要** (`summary_YYYYMMDD_HHMMSS.json`)
   - Session 結束時生成統計數據
   - 包含勝率、總損益、最大獲利/虧損等

## 🚀 使用方式

### 1. 啟動程式
```bash
cd "/mnt/c/Users/ljes9/OneDrive/Desktop/CryptoAI - 複製 (2) - 複製 - 複製"
python3 main.py
```

### 2. 選擇模式
選擇 `3. 本地模擬盤` 進行測試（不需 API Key）

### 3. 使用命令
運行期間可輸入以下命令：
- `help` - 顯示可用命令
- `status` - 顯示系統狀態
- `positions` - 顯示持倉詳情
- `logstatus` - **新增**：顯示日誌狀態
- `close BTCUSDT` - 平倉指定幣種
- `exit` - 退出並輸出報告

### 4. 退出時自動輸出報告
退出時會自動顯示：
- Session 運行時間
- 總交易數、勝率
- 總損益、平均每筆損益
- 最大獲利/虧損
- 所有日誌檔案路徑

## 📁 輸出的檔案

執行後會在 `logs/` 目錄生成：

```
logs/
├── trades_20260424_150000.csv      # 所有交易記錄
├── periodic_20260424_150000.csv    # 每個週期的持倉快照
├── full_20260424_150000.txt        # 完整文字日誌
└── summary_20260424_150000.json    # JSON 格式摘要
```

## 📊 分析範例

### 使用 Excel 分析
1. 打開 `periodic_*.csv`
2. 使用樞紐分析表分析持倉時間與損益關係
3. 可視化 PnL 走勢

### 使用 Python 分析
```python
import pandas as pd

# 讀取交易日誌
trades = pd.read_csv('logs/trades_20260424_150000.csv')
print(trades.describe())

# 讀取週期快照
periodic = pd.read_csv('logs/periodic_20260424_150000.csv')
print(periodic['total_pnl_usdt'].cumsum().plot())
```

## 🔧 自定義配置

在 `config.yaml` 中加入：
```yaml
logging:
  enabled: true
  level: "INFO"
  save_periodic: true
  periodic_interval: 1  # 每個週期都記錄
```

## 📈 日誌格式說明

### 交易日誌欄位
- `timestamp`: 時間戳
- `event_type`: 事件類型（BUY/SELL/PARTIAL_EXIT/SESSION_START/SESSION_END）
- `symbol`: 交易對
- `side`: 方向
- `price`: 價格
- `quantity`: 數量
- `leverage`: 槓桿
- `pnl_usdt`: 損益（USDT）
- `pnl_percent`: 損益（%）
- `reason`: 原因
- `holding_time`: 持倉時間（分鐘）
- `details`: 詳細資訊

### 週期快照欄位
- `timestamp`: 時間戳
- `period_index`: 週期編號
- `total_positions`: 持倉數量
- `total_pnl_usdt`: 總損益
- `symbols`: 持倉的幣種列表
- `details_json`: 每個持倉的詳細資訊（JSON 格式）

## ⚠️ 注意事項

1. 日誌檔案會持續累積，建議定期清理
2. 預設保留最近 1000 筆週期快照（避免記憶體溢出）
3. 所有日誌檔使用 UTF-8 編碼，支援中文
4. CSV 使用 UTF-8-sig 編碼，與 Excel 相容
