# 台指期特徵分析 MCP Server — 設計規格

> 版本：v2.0（取代原始 `TXF_Feature_MCP_需求文件.md` 中與實際資料不符的假設）
> 日期：2026-06-02
> 語言：Python 3.10+
> 套件管理：uv
> 部署形式：MCP (Model Context Protocol) Server

---

## 1. 目標

建立一個 MCP Server，把人工看盤的「形態識別」自動化：

1. 從台灣期交所（TAIFEX）下載台指期逐筆成交資料
2. 轉換成 6 個時間框架的 OHLCV，並以 **JSON 檔**持久化
3. 對每個框架套用可擴充的特徵演算法，產生特徵序列
4. 透過 MCP 介面提供 Claude / 其他 LLM 分析查詢
5. 內建回測驗證，量化特徵預測力

**核心價值**：讓 AI 助手基於結構化特徵序列做跨時間框架分析。

---

## 2. 實際資料來源（已實測，2026-05-29 樣本）

### 2.1 下載

固定 URL 規則，zip 內含單一 CSV（單日約 2.3MB，解壓約 52MB，含全部 330 種期貨商品）：

```
https://www.taifex.com.tw/file/taifex/Dailydownload/DailydownloadCSV/Daily_YYYY_MM_DD.zip
```

### 2.2 CSV 格式（Big5/CP950 編碼，9 欄）

```
成交日期,商品代號,到期月份(週別),成交時間,成交價格,成交數量(B+S),近月價格,遠月價格,開盤集合競價
20260529,TX     ,202606     ,084500,43964,146,-,-,*
```

### 2.3 與原始需求文件的關鍵差異（實測修正）

| 項目 | 原文件假設 | 實際資料 |
|---|---|---|
| 商品代號 | `TXF` | **`TX`**（大台），`MTX`（小台） |
| 編碼 | Big5/CP950 | ✅ 確實 Big5 |
| 時間精度 | 可能到毫秒 | **只到秒**（HHMMSS） |
| 日期欄位 | 需從檔名補 | **資料內含成交日期欄** |
| 成交量 | 未說明 | **B+S 雙邊合計，須 ÷2** 才是真實口數 |
| 集合競價 | 需自行判斷 | **第 9 欄 `*` 標記** |
| 價差單 | 未提 | 有跨月價差單（到期月份如 `202606/202607`），須濾掉 |

### 2.4 盤別結構

一個交易日檔案橫跨兩個日曆日：
- **夜盤**：前一交易日 15:00 開盤 → 跨午夜 → 隔日 05:00
- **日盤**：08:45 開盤 → 13:45 收盤
- 資料用「成交日期」欄在午夜換日（夜盤跨日陷阱）

---

## 3. 技術規格

| 項目 | 規格 |
|---|---|
| 程式語言 | Python 3.10+ |
| 執行環境 | Windows 10（原生，非 WSL2） |
| 套件管理 | uv |
| MCP SDK | `mcp`（官方 Python SDK） |
| 資料處理 | pandas, numpy |
| 測試 | pytest |
| 持久化格式 | JSON（OHLCV 中繼檔） |

---

## 4. 架構與資料流

```
TAIFEX downloader (抓 zip → 解壓 → 快取 data/raw/)
        ↓
loader (Big5 解碼 / 篩 TX 近月 / 濾價差單 / 量 ÷2 / 解析 9 欄)
        ↓
cleaner (時間排序 / 去重 / 異常值過濾)
        ↓
session (日盤 / 夜盤切割，含跨午夜處理)
        ↓
resampler (tick → 6 框架 OHLCV) → JSON 持久化 (data/ohlcv/)
        ↓
feature engine (plugin registry，掃描 patterns/ 自動載入)
        ↓
validation (backtest 後續N根統計 / resonance 多框架共振)
        ↓
MCP server (4 tools)
```

---

## 5. 專案結構

```
trading-pattern/
├── pyproject.toml              # uv 管理, Python 3.10+
├── README.md
├── src/txf_mcp/
│   ├── data/
│   │   ├── downloader.py       # 抓 TAIFEX zip → 解壓 → 快取 data/raw/
│   │   ├── loader.py           # Big5 解碼, 篩 TX 近月, 濾價差單, 量 ÷2
│   │   ├── cleaner.py          # 時間排序 / 去重 / 異常值(0/負/漲跌停)過濾
│   │   └── session.py          # 日盤 08:45-13:45 / 夜盤 15:00-次日 05:00
│   ├── klines/
│   │   ├── resampler.py        # tick → 1s/1/3/5/10/15min OHLCV (向量化)
│   │   └── ohlcv_json.py       # OHLCV ↔ JSON 讀寫
│   ├── features/
│   │   ├── base.py             # FeaturePattern 抽象基底
│   │   ├── registry.py         # 自動掃描 patterns/ 載入
│   │   └── patterns/
│   │       ├── deep_pit.py     # 深坑K (範例量化定義)
│   │       ├── high_point.py   # 高點K (範例)
│   │       └── low_point.py    # 低點K (範例)
│   ├── validation/
│   │   ├── backtest.py         # 特徵後續 N 根統計
│   │   ├── resonance.py        # 多框架共振分數 (0-5)
│   │   └── report.py           # 統計報告
│   └── mcp_server/
│       ├── server.py           # MCP Server 主程式
│       └── tools.py            # 4 個工具定義
├── tests/
│   ├── fixtures/
│   │   └── Daily_2026_05_29.csv
│   └── test_*.py
├── data/
│   ├── raw/                    # 下載快取 (gitignore)
│   └── ohlcv/                  # JSON 輸出 (gitignore)
└── docs/superpowers/specs/
```

---

## 6. OHLCV JSON 格式

### 6.1 輸出檔（每個交易日、每個框架一檔，共 6 檔）

```
data/ohlcv/TX_2026-05-29_1s.json     ← 逐秒K
data/ohlcv/TX_2026-05-29_1min.json
data/ohlcv/TX_2026-05-29_3min.json
data/ohlcv/TX_2026-05-29_5min.json
data/ohlcv/TX_2026-05-29_10min.json
data/ohlcv/TX_2026-05-29_15min.json
```

### 6.2 單檔結構

```json
{
  "meta": {
    "product": "TX",
    "contract": "202606",
    "trade_date": "2026-05-29",
    "timeframe": "1min",
    "source_file": "Daily_2026_05_29.csv",
    "generated_at": "2026-06-02T23:00:00+08:00",
    "bar_count": 300,
    "total_volume": 95423
  },
  "bars": [
    {
      "t": "2026-05-28T15:00:00+08:00",
      "session": "night",
      "o": 43964,
      "h": 43970,
      "l": 43958,
      "c": 43965,
      "v": 1234,
      "n": 56
    }
  ]
}
```

### 6.3 欄位定義

| 欄位 | 意義 |
|---|---|
| `t` | K棒起始時間（ISO 8601，含 +08:00；夜盤跨午夜自然遞增到隔日） |
| `session` | `day` / `night` |
| `o/h/l/c` | 開高低收（整數點數） |
| `v` | 成交量（已 ÷2 的真實口數） |
| `n` | 該根內 tick 筆數 |

### 6.4 設計決定

1. **逐秒K 只輸出有成交的秒**（稀疏），無交易的秒不產 bar。
2. **短鍵 `o/h/l/c/v/n`** 而非全名，降低逐秒檔體積。
3. **JSON 為唯一正式中繼格式**：下游特徵層、MCP 工具全部讀這 6 個 JSON，不另存 Parquet。
4. **`meta.total_volume`** 用於資料完整性測試（= 原始 tick 量總和 ÷2）。

---

## 7. 特徵插件介面

新增特徵只要在 `patterns/` 丟一個檔案，registry 自動掃描載入，不動核心程式碼：

```python
class FeaturePattern(ABC):
    name: str
    category: str  # "up" / "down" / "reversal"

    @abstractmethod
    def detect(self, klines: pd.DataFrame) -> pd.Series:
        """回傳與 klines 等長的 bool Series。
        同一份 detect() 須能套用到所有時間框架（碎形假設）。"""
```

### 範例特徵量化定義（佔位，之後由使用者替換）

- **深坑K (deep_pit)**：下影線 > 實體 2 倍且為局部低點
- **高點K (high_point)**：N 根內最高、收在上半部
- **低點K (low_point)**：N 根內最低、收在下半部

---

## 8. MCP 工具介面

| 工具 | 用途 | 主要輸入 |
|---|---|---|
| `analyze_txf_day` | 分析指定日期完整特徵 + 共振 | date, timeframes, session |
| `query_feature_statistics` | 特徵後續走勢統計（勝率/報酬/回撤） | feature, timeframe, date_range, lookforward_bars |
| `compare_days` | 多日特徵序列相似度（回傳數值分數，不畫圖） | target_date, compare_dates, timeframe |
| `list_available_dates` | 列出快取中可查詢日期 | （無） |

多框架共振：同時段內，不同框架同類特徵同時出現，輸出共振分數 0-5。

---

## 9. 錯誤處理

- 缺資料日期：明確回報，不靜默失敗
- 編碼錯誤：詳細日誌
- 異常 tick（價格 0 / 負數 / 超過漲跌停）：過濾並記錄筆數

---

## 10. 測試需求

1. **單元測試**：每個特徵演算法都有測試案例
2. **資料完整性**：resample 後各框架 `meta.total_volume` 相等，且 = 原始 tick 量總和 ÷2
3. **邊界測試**：日盤開收盤、夜盤跨午夜、集合競價標記、價差單過濾
4. **downloader 測試**：用 `tests/fixtures/Daily_2026_05_29.csv`，不打網路

---

## 11. 範圍界定（YAGNI 排除）

不在本期實作（原文件第 12 節「後續擴充」）：
- 即時 API（Fubon Neo）
- LINE / Discord 警示
- Web 視覺化
- 多商品（小台 MTX、微台、選擇權）— loader 保留參數化彈性但預設只做大台 TX 近月
- `compare_days` 不做圖示，只回數值相似度
- 不另存 Parquet 快取（JSON 即中繼格式）

---

## 12. 交付物

1. 完整可跑的 Python 專案骨架（uv 管理）
2. 端到端 pipeline：下載 → JSON OHLCV（6 框架）→ 特徵 → 驗證 → MCP
3. 範例特徵（deep_pit / high_point / low_point）
4. MCP Server 與 4 工具
5. pytest 測試套件（含 2026-05-29 fixture）
6. README（安裝、設定、使用）
7. 特徵擴充指南

---

**文件結束**
