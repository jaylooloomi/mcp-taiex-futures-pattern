# 台指期特徵分析 MCP 工具 — 需求文件

> 版本：v1.0
> 用途：交付給 AI agent 進行開發實作
> 語言：Python 3.10+
> 部署形式：MCP (Model Context Protocol) Server

---

## 1. 專案目標

建立一個 MCP Server，能夠：

1. 讀取台指期（TXF）tick data（資料來源：PChome 歷史下載）
2. 自動 resample 成多個時間框架的 K 棒序列
3. 對每個時間框架套用使用者定義的特徵演算法，產生特徵序列
4. 透過 MCP 介面提供 Claude / 其他 LLM 進行分析查詢
5. 內建回測驗證模組，量化特徵的預測力

**核心價值**：把人工看盤的「形態識別」過程自動化，讓 AI 助手可以基於結構化特徵序列做跨時間框架分析。

---

## 2. 技術規格

| 項目 | 規格 |
|---|---|
| 程式語言 | Python 3.10+ |
| MCP SDK | `mcp` (官方 Python SDK) |
| 資料處理 | pandas, numpy |
| 編碼處理 | 必須支援 Big5 / CP950 / UTF-8 自動偵測 |
| 開發環境 | Windows 11 + WSL2 |
| 套件管理 | uv 或 poetry |

---

## 3. 輸入規範

### 3.1 Tick Data 格式（PChome 來源）

預期 CSV 格式（實際格式以使用者提供樣本為準）：

```
時間,成交價,成交量,買價,賣價
09:00:00.123,17850,5,17849,17851
09:00:00.456,17851,3,17850,17852
...
```

**重要注意事項：**
- 編碼可能為 Big5 / CP950 / UTF-8，需要自動偵測或允許參數指定
- 時間戳精度可能到毫秒，需保留
- 必須處理跳空、開盤集合競價、收盤試撮等特殊時段

### 3.2 期望支援的查詢輸入

```python
{
    "date": "2024-01-15",           # 指定日期
    "timeframes": ["1min", "5min", "15min"],  # 可選的時間框架
    "session": "day",                # day / night / all
    "features": ["all"]              # 或指定特定特徵
}
```

---

## 4. 核心架構

```
┌─────────────────────────────────────────────┐
│              Tick Data (PChome)              │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│         Encoding Detection & Loading         │
│         (chardet / 手動指定)                  │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│              Tick Cleaner                    │
│  (時間排序、去重、異常值過濾、時段切割)        │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│        Multi-Timeframe Resampler             │
│  1min / 3min / 5min / 10min / 15min          │
└─────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│         Feature Algorithm Engine             │
│  (套用使用者定義的演算法，跨時間框架)         │
└─────────────────────────────────────────────┘
                      ↓
┌──────────────────────┬──────────────────────┐
│    Feature Series    │   Validation Module  │
│    (結構化輸出)       │   (回測統計)          │
└──────────────────────┴──────────────────────┘
                      ↓
┌─────────────────────────────────────────────┐
│              MCP Server Interface            │
└─────────────────────────────────────────────┘
```

---

## 5. 模組設計

### 5.1 資料層 (`data/`)

- `loader.py` — Tick CSV 讀取，自動編碼偵測
- `cleaner.py` — 異常值過濾、時間排序、去重
- `session.py` — 日盤 / 夜盤切割（台指期 08:45-13:45 / 15:00-05:00）

### 5.2 K 棒層 (`klines/`)

- `resampler.py` — Tick → 多框架 K 棒（OHLCV）
- 支援框架：1, 3, 5, 10, 15 分鐘（可擴充）
- 必須正確處理：開盤、收盤、跨日、缺口

### 5.3 特徵層 (`features/`)

- `base.py` — 特徵演算法基底類別（抽象介面）
- `patterns/` — 各特徵實作（由使用者提供 Python 程式碼）
  - `deep_pit.py` — 深坑K
  - `high_point.py` — 高點K
  - `low_point.py` — 低點K
  - （其他依使用者定義擴充）
- 每個特徵需實作：
  ```python
  class FeaturePattern:
      def detect(self, klines: pd.DataFrame) -> pd.Series:
          """回傳與 klines 等長的 bool/label Series"""
  ```

### 5.4 驗證層 (`validation/`)

- `backtest.py` — 特徵後續 N 根 K 棒的統計
- `resonance.py` — 多框架共振分析
  - 定義：同時段內，不同框架同類特徵同時出現
  - 輸出共振分數（0-5）
- `report.py` — 統計報告產生器

### 5.5 MCP 層 (`mcp_server/`)

- `server.py` — MCP Server 主程式
- `tools.py` — MCP 工具定義

---

## 6. MCP 工具介面定義

### Tool 1: `analyze_txf_day`

**用途**：分析指定日期的台指期完整特徵

**輸入：**
```json
{
  "date": "2024-01-15",
  "timeframes": ["1min", "5min", "15min"],
  "session": "day"
}
```

**輸出：**
```json
{
  "date": "2024-01-15",
  "session": "day",
  "timeframes": {
    "1min": {
      "klines": [...],
      "feature_series": {
        "deep_pit": [false, false, true, ...],
        "high_point": [...],
        "low_point": [...]
      },
      "summary": {
        "deep_pit_count": 3,
        "high_point_count": 2,
        "low_point_count": 4
      }
    },
    "5min": { ... },
    "15min": { ... }
  },
  "resonance": [
    {
      "time": "10:23:00",
      "feature": "high_point",
      "frameworks": ["1min", "5min", "15min"],
      "score": 3
    }
  ]
}
```

### Tool 2: `query_feature_statistics`

**用途**：查詢某特徵出現後的後續走勢統計

**輸入：**
```json
{
  "feature": "deep_pit",
  "timeframe": "5min",
  "date_range": ["2023-01-01", "2024-12-31"],
  "lookforward_bars": 10
}
```

**輸出：**
```json
{
  "feature": "deep_pit",
  "sample_size": 142,
  "lookforward_bars": 10,
  "stats": {
    "up_probability": 0.58,
    "avg_return_pct": 0.32,
    "max_return_pct": 2.41,
    "max_drawdown_pct": -1.18,
    "win_rate_by_bar": [0.51, 0.55, 0.58, ...]
  }
}
```

### Tool 3: `compare_days`

**用途**：比對多個日期的特徵序列相似度

**輸入：**
```json
{
  "target_date": "2024-01-15",
  "compare_dates": ["2023-05-10", "2023-09-22"],
  "timeframe": "5min"
}
```

**輸出：**特徵序列相似度評分與圖示

### Tool 4: `list_available_dates`

**用途**：列出資料庫中可查詢的日期

---

## 7. 待使用者提供的內容

> **以下需要使用者後續提供，AI agent 開發時請預留擴充介面：**

1. **特徵演算法 Python 程式碼**
   - 深坑K 的量化定義
   - 高點K 的量化定義
   - 低點K 的量化定義
   - 其他自定義特徵

2. **PChome tick data 範例檔案**
   - 用於確認實際 CSV 格式、欄位順序、編碼
   - 一週左右資料即可

3. **特徵命名規範與分類**
   - 是否有上漲類、下跌類、轉折類等分組

---

## 8. 非功能性需求

### 8.1 效能
- 單日 tick data 處理（約 50,000-200,000 筆）應在 5 秒內完成
- 特徵計算需向量化（pandas / numpy），避免 for-loop

### 8.2 資料儲存
- 處理過的 K 棒與特徵序列建議快取（Parquet 格式）
- 避免每次查詢都重新從 tick 計算

### 8.3 錯誤處理
- 缺資料日期需明確回報
- 編碼錯誤需詳細日誌
- 異常 tick（價格 0、負數、超過漲跌停）需過濾並記錄

### 8.4 可擴充性
- 新增特徵不應修改核心程式碼，僅在 `features/patterns/` 加檔案
- 新增時間框架不應修改 resampler 主邏輯

---

## 9. 驗證與測試需求

1. **單元測試**：每個特徵演算法都需有對應測試案例
2. **資料完整性測試**：resample 後的 K 棒總成交量需等於原 tick 總和
3. **回測驗證**：每個特徵需提供至少 1 年歷史資料的統計勝率
4. **邊界測試**：開盤、收盤、跨日、停盤、停板情境

---

## 10. 交付物

1. 完整 Python 專案（含 `pyproject.toml` / `requirements.txt`）
2. MCP Server 可執行檔
3. Claude Desktop 設定範例 (`claude_desktop_config.json` 片段)
4. README.md（安裝、設定、使用範例）
5. 特徵新增指南（如何擴充新特徵）
6. 單元測試套件

---

## 11. 開發者注意事項

1. **編碼坑**：PChome 資料極可能是 Big5/CP950，預設用 UTF-8 會失敗
2. **時間欄位**：台指期 tick 時間戳通常不含日期，需從檔名或外部資訊補上
3. **夜盤跨日**：夜盤 15:00 開始到次日 05:00，日期處理要特別小心
4. **試撮資料**：08:30-08:44:59 是試撮階段，`isTrial=true`，不是真實成交
5. **碎形特徵假設**：使用者強調特徵定義可跨時間框架，演算法引擎需確認此假設在實作上成立（同一份 `detect()` 函數能套用到 1min 也能套用到 15min）

---

## 12. 後續擴充方向（非本期需求）

- 接 Fubon Neo API 做即時特徵偵測
- 整合 LINE Notify / Discord 警示
- Web 介面視覺化（FastAPI + Vue）
- 多商品支援（小台、微台、選擇權）

---

**文件結束**
