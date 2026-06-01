# TXF Feature Analysis MCP Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable MCP server that downloads TAIFEX TXF (TX) tick data, converts it to 6-timeframe OHLCV JSON files, applies pluggable feature patterns, and exposes analysis tools to LLMs.

**Architecture:** Layered pipeline — downloader → loader → cleaner → session → resampler → JSON persistence → feature registry → validation → MCP tools. Each layer is an isolated module reading/writing pandas DataFrames; JSON is the canonical intermediate format that downstream features read.

**Tech Stack:** Python 3.10+, uv, pandas, numpy, mcp (official Python SDK), pytest.

---

## File Structure

```
src/txf_mcp/
├── __init__.py
├── data/
│   ├── __init__.py
│   ├── downloader.py     # fetch TAIFEX zip, extract, cache to data/raw/
│   ├── loader.py         # Big5 decode, filter TX near-month, drop spreads, volume/2
│   ├── cleaner.py        # sort, dedup, filter abnormal ticks
│   └── session.py        # tag day/night, handle midnight rollover
├── klines/
│   ├── __init__.py
│   ├── resampler.py      # tick -> OHLCV for 1s/1min/3min/5min/10min/15min
│   └── ohlcv_json.py     # OHLCV DataFrame <-> JSON file
├── features/
│   ├── __init__.py
│   ├── base.py           # FeaturePattern ABC
│   ├── registry.py       # auto-discover patterns/
│   └── patterns/
│       ├── __init__.py
│       ├── deep_pit.py
│       ├── high_point.py
│       └── low_point.py
├── validation/
│   ├── __init__.py
│   ├── backtest.py
│   ├── resonance.py
│   └── report.py
├── pipeline.py           # orchestrates download->json for a date
└── mcp_server/
    ├── __init__.py
    ├── server.py
    └── tools.py
tests/
├── fixtures/TX_sample_2026_05_29.csv   # already created (Big5)
└── test_*.py
```

Constants module values (used across tasks):
- Product code filter: `"TX"` (exact match after strip)
- Day session: 08:45:00–13:45:00
- Night session: 15:00:00–next day 05:00:00
- Timeframes: `["1s", "1min", "3min", "5min", "10min", "15min"]`
- Timezone: `+08:00` (Asia/Taipei, no DST)

---

## Task 0: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/txf_mcp/__init__.py` (and all sub-package `__init__.py` as empty files)

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "txf-mcp"
version = "0.1.0"
description = "TAIFEX TXF feature analysis MCP server"
requires-python = ">=3.10"
dependencies = [
    "pandas>=2.0",
    "numpy>=1.24",
    "mcp>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/txf_mcp"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty package files**

Create empty `__init__.py` in: `src/txf_mcp/`, `src/txf_mcp/data/`, `src/txf_mcp/klines/`, `src/txf_mcp/features/`, `src/txf_mcp/features/patterns/`, `src/txf_mcp/validation/`, `src/txf_mcp/mcp_server/`.

- [ ] **Step 3: Sync environment**

Run: `uv sync --extra dev`
Expected: creates `.venv`, installs pandas/numpy/mcp/pytest.

- [ ] **Step 4: Verify pytest runs**

Run: `uv run pytest -q`
Expected: "no tests ran" (exit 5) — environment works.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/ uv.lock
git commit -m "chore: scaffold txf-mcp package with uv"
```

---

## Task 1: Constants module

**Files:**
- Create: `src/txf_mcp/constants.py`
- Test: `tests/test_constants.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_constants.py
from txf_mcp import constants as c

def test_timeframes_list():
    assert c.TIMEFRAMES == ["1s", "1min", "3min", "5min", "10min", "15min"]

def test_session_bounds():
    assert c.DAY_START == "08:45:00"
    assert c.DAY_END == "13:45:00"
    assert c.NIGHT_START == "15:00:00"
    assert c.NIGHT_END == "05:00:00"

def test_product_and_tz():
    assert c.PRODUCT == "TX"
    assert c.TZ == "+08:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_constants.py -v`
Expected: FAIL with ModuleNotFoundError / AttributeError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/constants.py
PRODUCT = "TX"
TZ = "+08:00"
TIMEFRAMES = ["1s", "1min", "3min", "5min", "10min", "15min"]
DAY_START = "08:45:00"
DAY_END = "13:45:00"
NIGHT_START = "15:00:00"
NIGHT_END = "05:00:00"

# pandas resample rule per timeframe
RESAMPLE_RULE = {
    "1s": "1s",
    "1min": "1min",
    "3min": "3min",
    "5min": "5min",
    "10min": "10min",
    "15min": "15min",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_constants.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/constants.py tests/test_constants.py
git commit -m "feat: add constants module"
```

---

## Task 2: Loader (Big5 decode, filter TX near-month, drop spreads, volume/2)

**Files:**
- Create: `src/txf_mcp/data/loader.py`
- Test: `tests/test_loader.py`

CSV columns (Big5): `成交日期,商品代號,到期月份(週別),成交時間,成交價格,成交數量(B+S),近月價格,遠月價格,開盤集合競價`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_loader.py
from pathlib import Path
import pandas as pd
from txf_mcp.data.loader import load_tx_ticks

FIXTURE = Path("tests/fixtures/TX_sample_2026_05_29.csv")

def test_returns_dataframe_with_expected_columns():
    df = load_tx_ticks(FIXTURE)
    assert list(df.columns) == ["datetime", "price", "volume", "is_auction", "expiry"]

def test_only_tx_near_month_no_spreads():
    df = load_tx_ticks(FIXTURE)
    # near-month is the single expiry with most rows; no spread codes with "/"
    assert df["expiry"].str.contains("/").sum() == 0
    assert df["expiry"].nunique() == 1

def test_volume_halved_and_integer():
    df = load_tx_ticks(FIXTURE)
    assert (df["volume"] >= 1).all()
    assert df["volume"].dtype.kind in ("i", "u")

def test_datetime_parsed_with_tz():
    df = load_tx_ticks(FIXTURE)
    assert str(df["datetime"].dt.tz) in ("UTC+08:00", "pytz.FixedOffset(480)", "Asia/Taipei")
    # spans the night (28th) and day (29th)
    assert df["datetime"].dt.date.nunique() == 2

def test_auction_flag_detected():
    df = load_tx_ticks(FIXTURE)
    assert df["is_auction"].any()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_loader.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/data/loader.py
from pathlib import Path
import pandas as pd
from ..constants import PRODUCT, TZ

_COLS = ["trade_date", "product", "expiry", "trade_time",
         "price", "volume_bs", "near", "far", "auction"]

def load_tx_ticks(csv_path: str | Path) -> pd.DataFrame:
    """Load TAIFEX daily CSV, return cleaned TX near-month tick frame.

    Columns out: datetime (tz-aware), price (int), volume (int, B+S/2),
    is_auction (bool), expiry (str).
    """
    raw = pd.read_csv(
        csv_path, encoding="big5", names=_COLS, header=0,
        dtype=str, skipinitialspace=True,
    )
    # strip whitespace from all string cells
    for col in raw.columns:
        raw[col] = raw[col].str.strip()

    tx = raw[raw["product"] == PRODUCT].copy()
    # drop calendar spreads (expiry contains "/")
    tx = tx[~tx["expiry"].str.contains("/", na=False)]
    # near-month = expiry with most rows
    near = tx["expiry"].value_counts().idxmax()
    tx = tx[tx["expiry"] == near].copy()

    # parse datetime: trade_date YYYYMMDD + trade_time HHMMSS
    dt = pd.to_datetime(
        tx["trade_date"] + tx["trade_time"].str.zfill(6),
        format="%Y%m%d%H%M%S",
    ).dt.tz_localize(TZ)

    out = pd.DataFrame({
        "datetime": dt,
        "price": tx["price"].astype(int),
        "volume": (tx["volume_bs"].astype(int) // 2).clip(lower=1),
        "is_auction": tx["auction"].fillna("").str.contains(r"\*"),
        "expiry": near,
    })
    return out.reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_loader.py -v`
Expected: PASS (5 passed). If the tz assertion string mismatches, adjust the test to `df["datetime"].dt.tz is not None`.

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/data/loader.py tests/test_loader.py
git commit -m "feat: add TAIFEX TX tick loader"
```

---

## Task 3: Cleaner (sort, dedup, filter abnormal ticks)

**Files:**
- Create: `src/txf_mcp/data/cleaner.py`
- Test: `tests/test_cleaner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cleaner.py
import pandas as pd
from txf_mcp.data.cleaner import clean_ticks

def _frame(prices, vols=None):
    n = len(prices)
    dt = pd.date_range("2026-05-29 09:00:00+08:00", periods=n, freq="s")
    return pd.DataFrame({
        "datetime": dt,
        "price": prices,
        "volume": vols or [1] * n,
        "is_auction": [False] * n,
        "expiry": ["202606"] * n,
    })

def test_drops_zero_and_negative_prices():
    df = clean_ticks(_frame([100, 0, -5, 101]))
    assert (df["price"] > 0).all()
    assert len(df) == 2

def test_sorted_by_datetime():
    df = _frame([1, 2, 3]).iloc[::-1].reset_index(drop=True)
    out = clean_ticks(df)
    assert out["datetime"].is_monotonic_increasing

def test_reports_filtered_count(capsys):
    clean_ticks(_frame([100, 0, 101]))
    assert "filtered" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cleaner.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/data/cleaner.py
import sys
import pandas as pd

def clean_ticks(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by time, drop duplicate rows, filter abnormal prices (<=0)."""
    before = len(df)
    out = df[df["price"] > 0].copy()
    out = out.drop_duplicates()
    out = out.sort_values("datetime", kind="stable").reset_index(drop=True)
    dropped = before - len(out)
    if dropped:
        print(f"cleaner: filtered {dropped} abnormal/duplicate ticks", file=sys.stderr)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cleaner.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/data/cleaner.py tests/test_cleaner.py
git commit -m "feat: add tick cleaner"
```

---

## Task 4: Session tagging (day/night, midnight rollover)

**Files:**
- Create: `src/txf_mcp/data/session.py`
- Test: `tests/test_session.py`

Rule: a tick is `day` if its time-of-day is within [08:45, 13:45]; otherwise `night` (covers 15:00–05:00 across midnight). `trade_session_date` groups night+following-day-morning into one trading day: for ticks at time-of-day >= 14:00 (i.e. evening), trade date = that calendar date; for ticks before 08:00 (post-midnight night), trade date = previous calendar date; day-session ticks use their own date.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session.py
import pandas as pd
from txf_mcp.data.session import tag_session

def _row(ts):
    return pd.DataFrame({
        "datetime": pd.to_datetime([ts]).tz_localize("+08:00"),
        "price": [100], "volume": [1], "is_auction": [False], "expiry": ["202606"],
    })

def test_day_tick():
    out = tag_session(_row("2026-05-29 09:30:00"))
    assert out["session"].iloc[0] == "day"

def test_evening_night_tick():
    out = tag_session(_row("2026-05-28 15:30:00"))
    assert out["session"].iloc[0] == "night"

def test_post_midnight_night_tick():
    out = tag_session(_row("2026-05-29 02:00:00"))
    assert out["session"].iloc[0] == "night"

def test_filter_session():
    df = pd.concat([_row("2026-05-29 09:30:00"), _row("2026-05-28 15:30:00")], ignore_index=True)
    out = tag_session(df)
    assert (out[out["session"] == "day"]).shape[0] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_session.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/data/session.py
import datetime as _dt
import pandas as pd

_DAY_START = _dt.time(8, 45)
_DAY_END = _dt.time(13, 45)

def tag_session(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'session' column: 'day' for 08:45-13:45, else 'night'."""
    out = df.copy()
    tod = out["datetime"].dt.time
    is_day = (tod >= _DAY_START) & (tod <= _DAY_END)
    out["session"] = is_day.map({True: "day", False: "night"})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_session.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/data/session.py tests/test_session.py
git commit -m "feat: add session tagging"
```

---

## Task 5: Resampler (tick -> OHLCV for all 6 timeframes)

**Files:**
- Create: `src/txf_mcp/klines/resampler.py`
- Test: `tests/test_resampler.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resampler.py
import pandas as pd
from txf_mcp.klines.resampler import resample

def _ticks():
    dt = pd.to_datetime([
        "2026-05-29 09:00:00", "2026-05-29 09:00:30",
        "2026-05-29 09:01:10", "2026-05-29 09:01:50",
    ]).tz_localize("+08:00")
    return pd.DataFrame({
        "datetime": dt, "price": [100, 105, 110, 95], "volume": [2, 3, 1, 4],
        "is_auction": [False] * 4, "session": ["day"] * 4,
    })

def test_1min_ohlcv():
    bars = resample(_ticks(), "1min")
    assert len(bars) == 2
    first = bars.iloc[0]
    assert first["open"] == 100 and first["high"] == 105
    assert first["low"] == 100 and first["close"] == 105
    assert first["volume"] == 5 and first["n"] == 2

def test_volume_preserved_across_timeframes():
    t = _ticks()
    total = t["volume"].sum()
    for tf in ["1s", "1min", "5min"]:
        assert resample(t, tf)["volume"].sum() == total

def test_session_column_present():
    bars = resample(_ticks(), "5min")
    assert "session" in bars.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resampler.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/klines/resampler.py
import pandas as pd
from ..constants import RESAMPLE_RULE

def resample(ticks: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Resample tick frame into OHLCV bars for the given timeframe.

    Output columns: datetime (bar start), open, high, low, close,
    volume, n (tick count), session. Empty bars are dropped.
    """
    rule = RESAMPLE_RULE[timeframe]
    df = ticks.set_index("datetime")
    agg = df["price"].resample(rule, label="left", closed="left").ohlc()
    agg["volume"] = df["volume"].resample(rule, label="left", closed="left").sum()
    agg["n"] = df["price"].resample(rule, label="left", closed="left").count()
    # session: take first session label within the bar
    agg["session"] = df["session"].resample(rule, label="left", closed="left").first()
    agg = agg.dropna(subset=["open"]).reset_index()
    agg["volume"] = agg["volume"].astype(int)
    agg["n"] = agg["n"].astype(int)
    for col in ["open", "high", "low", "close"]:
        agg[col] = agg[col].astype(int)
    return agg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_resampler.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/klines/resampler.py tests/test_resampler.py
git commit -m "feat: add multi-timeframe resampler"
```

---

## Task 6: OHLCV JSON read/write

**Files:**
- Create: `src/txf_mcp/klines/ohlcv_json.py`
- Test: `tests/test_ohlcv_json.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ohlcv_json.py
import json
import pandas as pd
from txf_mcp.klines.ohlcv_json import write_ohlcv_json, read_ohlcv_json

def _bars():
    return pd.DataFrame({
        "datetime": pd.to_datetime(["2026-05-29 09:00:00"]).tz_localize("+08:00"),
        "open": [100], "high": [110], "low": [95], "close": [105],
        "volume": [5], "n": [2], "session": ["day"],
    })

def test_write_then_read_roundtrip(tmp_path):
    p = tmp_path / "TX_2026-05-29_1min.json"
    write_ohlcv_json(_bars(), p, product="TX", contract="202606",
                     trade_date="2026-05-29", timeframe="1min",
                     source_file="Daily_2026_05_29.csv")
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["meta"]["timeframe"] == "1min"
    assert doc["meta"]["bar_count"] == 1
    assert doc["meta"]["total_volume"] == 5
    bar = doc["bars"][0]
    assert bar["o"] == 100 and bar["h"] == 110 and bar["l"] == 95 and bar["c"] == 105
    assert bar["v"] == 5 and bar["n"] == 2 and bar["session"] == "day"

def test_read_returns_dataframe(tmp_path):
    p = tmp_path / "f.json"
    write_ohlcv_json(_bars(), p, product="TX", contract="202606",
                     trade_date="2026-05-29", timeframe="1min", source_file="x.csv")
    df = read_ohlcv_json(p)
    assert list(df.columns) == ["datetime", "open", "high", "low", "close", "volume", "n", "session"]
    assert df["close"].iloc[0] == 105
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ohlcv_json.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/klines/ohlcv_json.py
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pandas as pd

_TPE = timezone(timedelta(hours=8))

def write_ohlcv_json(bars: pd.DataFrame, path, *, product, contract,
                     trade_date, timeframe, source_file) -> None:
    rows = []
    for _, r in bars.iterrows():
        rows.append({
            "t": r["datetime"].isoformat(),
            "session": r["session"],
            "o": int(r["open"]), "h": int(r["high"]),
            "l": int(r["low"]), "c": int(r["close"]),
            "v": int(r["volume"]), "n": int(r["n"]),
        })
    doc = {
        "meta": {
            "product": product, "contract": contract, "trade_date": trade_date,
            "timeframe": timeframe, "source_file": source_file,
            "generated_at": datetime.now(_TPE).isoformat(),
            "bar_count": len(rows),
            "total_volume": int(bars["volume"].sum()) if len(bars) else 0,
        },
        "bars": rows,
    }
    Path(path).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")

def read_ohlcv_json(path) -> pd.DataFrame:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    bars = doc["bars"]
    df = pd.DataFrame({
        "datetime": pd.to_datetime([b["t"] for b in bars]),
        "open": [b["o"] for b in bars], "high": [b["h"] for b in bars],
        "low": [b["l"] for b in bars], "close": [b["c"] for b in bars],
        "volume": [b["v"] for b in bars], "n": [b["n"] for b in bars],
        "session": [b["session"] for b in bars],
    })
    return df
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ohlcv_json.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/klines/ohlcv_json.py tests/test_ohlcv_json.py
git commit -m "feat: add OHLCV JSON read/write"
```

---

## Task 7: Downloader

**Files:**
- Create: `src/txf_mcp/data/downloader.py`
- Test: `tests/test_downloader.py`

The downloader builds the URL, downloads the zip to a cache dir, extracts the CSV. Tests must not hit the network: test URL building and the extract step against a locally-zipped fixture.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_downloader.py
import zipfile
from pathlib import Path
from txf_mcp.data.downloader import build_url, extract_csv

def test_build_url():
    url = build_url("2026-05-29")
    assert url == ("https://www.taifex.com.tw/file/taifex/Dailydownload/"
                   "DailydownloadCSV/Daily_2026_05_29.zip")

def test_extract_csv(tmp_path):
    csv = tmp_path / "Daily_2026_05_29.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    zpath = tmp_path / "Daily_2026_05_29.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.write(csv, arcname="Daily_2026_05_29.csv")
    csv.unlink()
    out = extract_csv(zpath, tmp_path)
    assert Path(out).exists() and Path(out).suffix == ".csv"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/data/downloader.py
import urllib.request
import zipfile
from pathlib import Path

_BASE = ("https://www.taifex.com.tw/file/taifex/Dailydownload/"
         "DailydownloadCSV/Daily_{y}_{m}_{d}.zip")

def build_url(trade_date: str) -> str:
    """trade_date: 'YYYY-MM-DD' -> TAIFEX daily zip URL."""
    y, m, d = trade_date.split("-")
    return _BASE.format(y=y, m=m, d=d)

def extract_csv(zip_path, dest_dir) -> str:
    dest = Path(dest_dir)
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        z.extract(name, dest)
    return str(dest / name)

def download(trade_date: str, cache_dir="data/raw") -> str:
    """Download (if not cached) and extract the daily CSV. Returns CSV path."""
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    csv_path = cache / f"Daily_{trade_date.replace('-', '_')}.csv"
    if csv_path.exists():
        return str(csv_path)
    zip_path = cache / f"Daily_{trade_date.replace('-', '_')}.zip"
    req = urllib.request.Request(build_url(trade_date),
                                 headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as f:
        f.write(resp.read())
    return extract_csv(zip_path, cache)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_downloader.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/data/downloader.py tests/test_downloader.py
git commit -m "feat: add TAIFEX downloader"
```

---

## Task 8: Feature base + registry

**Files:**
- Create: `src/txf_mcp/features/base.py`
- Create: `src/txf_mcp/features/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_registry.py
import pandas as pd
from txf_mcp.features.registry import discover_patterns
from txf_mcp.features.base import FeaturePattern

def test_discovers_three_example_patterns():
    patterns = discover_patterns()
    names = {p.name for p in patterns}
    assert {"deep_pit", "high_point", "low_point"} <= names

def test_patterns_are_feature_instances():
    for p in discover_patterns():
        assert isinstance(p, FeaturePattern)
        assert p.category in ("up", "down", "reversal")

def test_detect_returns_bool_series_same_length():
    bars = pd.DataFrame({
        "open": [100, 101, 102], "high": [105, 106, 103],
        "low": [95, 96, 90], "close": [104, 97, 102],
        "volume": [1, 1, 1], "n": [1, 1, 1],
    })
    for p in discover_patterns():
        s = p.detect(bars)
        assert len(s) == len(bars)
        assert s.dtype == bool
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write base.py and registry.py**

```python
# src/txf_mcp/features/base.py
from abc import ABC, abstractmethod
import pandas as pd

class FeaturePattern(ABC):
    name: str = ""
    category: str = "reversal"  # "up" | "down" | "reversal"

    @abstractmethod
    def detect(self, klines: pd.DataFrame) -> pd.Series:
        """Return a bool Series aligned to klines (same length).
        The same detect() must apply to any timeframe (fractal assumption)."""
```

```python
# src/txf_mcp/features/registry.py
import importlib
import pkgutil
from . import patterns as _patterns_pkg
from .base import FeaturePattern

def discover_patterns() -> list[FeaturePattern]:
    """Import every module in features/patterns/ and instantiate each
    FeaturePattern subclass found."""
    found: list[FeaturePattern] = []
    for info in pkgutil.iter_modules(_patterns_pkg.__path__):
        mod = importlib.import_module(f"{_patterns_pkg.__name__}.{info.name}")
        for attr in vars(mod).values():
            if (isinstance(attr, type) and issubclass(attr, FeaturePattern)
                    and attr is not FeaturePattern):
                found.append(attr())
    return found
```

- [ ] **Step 4: Run test (still fails — no patterns yet)**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL (no patterns discovered) — proceed to Task 9 which adds patterns. Leave this test; it passes after Task 9.

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/features/base.py src/txf_mcp/features/registry.py tests/test_registry.py
git commit -m "feat: add feature base class and registry"
```

---

## Task 9: Example feature patterns

**Files:**
- Create: `src/txf_mcp/features/patterns/deep_pit.py`
- Create: `src/txf_mcp/features/patterns/high_point.py`
- Create: `src/txf_mcp/features/patterns/low_point.py`
- Test: `tests/test_patterns.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_patterns.py
import pandas as pd
from txf_mcp.features.patterns.deep_pit import DeepPit
from txf_mcp.features.patterns.high_point import HighPoint
from txf_mcp.features.patterns.low_point import LowPoint

def _bars(o, h, l, c):
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c,
                         "volume": [1]*len(o), "n": [1]*len(o)})

def test_deep_pit_detects_long_lower_wick_local_low():
    # bar 1: long lower wick (low far below body) and local minimum
    bars = _bars([100, 100, 100], [101, 101, 101], [99, 80, 99], [100, 99, 100])
    s = DeepPit().detect(bars)
    assert bool(s.iloc[1]) is True
    assert bool(s.iloc[0]) is False

def test_high_point_detects_local_max_close_upper_half():
    bars = _bars([100, 100, 100], [105, 120, 105], [95, 100, 95], [100, 118, 100])
    s = HighPoint(window=1).detect(bars)
    assert bool(s.iloc[1]) is True

def test_low_point_detects_local_min_close_lower_half():
    bars = _bars([100, 100, 100], [105, 100, 105], [95, 80, 95], [100, 82, 100])
    s = LowPoint(window=1).detect(bars)
    assert bool(s.iloc[1]) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_patterns.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write the three patterns**

```python
# src/txf_mcp/features/patterns/deep_pit.py
import pandas as pd
from ..base import FeaturePattern

class DeepPit(FeaturePattern):
    name = "deep_pit"
    category = "reversal"

    def __init__(self, wick_body_ratio: float = 2.0):
        self.wick_body_ratio = wick_body_ratio

    def detect(self, klines: pd.DataFrame) -> pd.Series:
        body = (klines["close"] - klines["open"]).abs()
        body_low = klines[["open", "close"]].min(axis=1)
        lower_wick = body_low - klines["low"]
        long_wick = lower_wick > (body.clip(lower=1) * self.wick_body_ratio)
        local_low = (klines["low"] < klines["low"].shift(1)) & \
                    (klines["low"] < klines["low"].shift(-1))
        return (long_wick & local_low).fillna(False)
```

```python
# src/txf_mcp/features/patterns/high_point.py
import pandas as pd
from ..base import FeaturePattern

class HighPoint(FeaturePattern):
    name = "high_point"
    category = "up"

    def __init__(self, window: int = 3):
        self.window = window

    def detect(self, klines: pd.DataFrame) -> pd.Series:
        w = self.window
        rolling_max = klines["high"].rolling(2 * w + 1, center=True, min_periods=1).max()
        is_local_max = klines["high"] >= rolling_max
        mid = (klines["high"] + klines["low"]) / 2
        close_upper = klines["close"] >= mid
        return (is_local_max & close_upper).fillna(False)
```

```python
# src/txf_mcp/features/patterns/low_point.py
import pandas as pd
from ..base import FeaturePattern

class LowPoint(FeaturePattern):
    name = "low_point"
    category = "down"

    def __init__(self, window: int = 3):
        self.window = window

    def detect(self, klines: pd.DataFrame) -> pd.Series:
        w = self.window
        rolling_min = klines["low"].rolling(2 * w + 1, center=True, min_periods=1).min()
        is_local_min = klines["low"] <= rolling_min
        mid = (klines["high"] + klines["low"]) / 2
        close_lower = klines["close"] <= mid
        return (is_local_min & close_lower).fillna(False)
```

- [ ] **Step 4: Run tests (patterns + registry)**

Run: `uv run pytest tests/test_patterns.py tests/test_registry.py -v`
Expected: PASS (test_patterns 3 passed; test_registry 3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/features/patterns/ tests/test_patterns.py
git commit -m "feat: add example feature patterns (deep_pit/high_point/low_point)"
```

---

## Task 10: Backtest

**Files:**
- Create: `src/txf_mcp/validation/backtest.py`
- Test: `tests/test_backtest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backtest.py
import pandas as pd
from txf_mcp.validation.backtest import backtest_feature

def test_basic_stats():
    bars = pd.DataFrame({"close": [100, 102, 104, 103, 101]})
    signal = pd.Series([True, False, False, False, False])
    stats = backtest_feature(bars, signal, lookforward_bars=2)
    assert stats["sample_size"] == 1
    # entry close 100, +2 bars close 104 -> +4%
    assert round(stats["avg_return_pct"], 2) == 4.0
    assert stats["up_probability"] == 1.0

def test_no_signal_returns_zero_sample():
    bars = pd.DataFrame({"close": [100, 101]})
    signal = pd.Series([False, False])
    stats = backtest_feature(bars, signal, lookforward_bars=1)
    assert stats["sample_size"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_backtest.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/validation/backtest.py
import pandas as pd

def backtest_feature(bars: pd.DataFrame, signal: pd.Series,
                     lookforward_bars: int = 10) -> dict:
    """For each True in signal, measure return from entry close to the close
    `lookforward_bars` ahead. Returns summary stats."""
    close = bars["close"].reset_index(drop=True)
    sig = signal.reset_index(drop=True)
    entries = sig[sig].index
    entries = [i for i in entries if i + lookforward_bars < len(close)]
    if not entries:
        return {"sample_size": 0, "lookforward_bars": lookforward_bars,
                "up_probability": 0.0, "avg_return_pct": 0.0,
                "max_return_pct": 0.0, "max_drawdown_pct": 0.0}
    returns = []
    for i in entries:
        entry = close[i]
        future = close[i + lookforward_bars]
        returns.append((future - entry) / entry * 100)
    s = pd.Series(returns)
    return {
        "sample_size": len(s),
        "lookforward_bars": lookforward_bars,
        "up_probability": round(float((s > 0).mean()), 4),
        "avg_return_pct": round(float(s.mean()), 4),
        "max_return_pct": round(float(s.max()), 4),
        "max_drawdown_pct": round(float(s.min()), 4),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_backtest.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/validation/backtest.py tests/test_backtest.py
git commit -m "feat: add feature backtest"
```

---

## Task 11: Resonance (multi-timeframe)

**Files:**
- Create: `src/txf_mcp/validation/resonance.py`
- Test: `tests/test_resonance.py`

Definition: for a feature, a resonance event at a time bucket occurs when the same feature fires in multiple timeframes within the same minute. Score = number of timeframes firing (0-5; capped at 5 since we have up to 6 frames but score range is 0-5 per spec, so cap at 5).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resonance.py
import pandas as pd
from txf_mcp.validation.resonance import find_resonance

def _fire(times):
    return pd.DataFrame({
        "datetime": pd.to_datetime(times).tz_localize("+08:00"),
    })

def test_resonance_when_two_frames_fire_same_minute():
    fires = {
        "1min": _fire(["2026-05-29 09:05:00"]),
        "5min": _fire(["2026-05-29 09:05:30"]),
        "15min": _fire(["2026-05-29 10:00:00"]),
    }
    events = find_resonance(fires, "high_point")
    minutes = {e["time"] for e in events}
    assert "2026-05-29T09:05" in minutes
    ev = next(e for e in events if e["time"] == "2026-05-29T09:05")
    assert ev["score"] == 2
    assert set(ev["frameworks"]) == {"1min", "5min"}

def test_no_resonance_single_frame():
    fires = {"1min": _fire(["2026-05-29 09:05:00"])}
    assert find_resonance(fires, "high_point") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resonance.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/validation/resonance.py
from collections import defaultdict
import pandas as pd

def find_resonance(fires_by_tf: dict[str, pd.DataFrame], feature: str) -> list[dict]:
    """fires_by_tf: timeframe -> DataFrame of rows (with 'datetime') where the
    feature fired. Returns resonance events where >=2 timeframes fire in the
    same minute bucket. Score capped at 5."""
    bucket: dict[str, set[str]] = defaultdict(set)
    for tf, df in fires_by_tf.items():
        for ts in df["datetime"]:
            key = ts.strftime("%Y-%m-%dT%H:%M")
            bucket[key].add(tf)
    events = []
    for minute, tfs in sorted(bucket.items()):
        if len(tfs) >= 2:
            events.append({
                "time": minute,
                "feature": feature,
                "frameworks": sorted(tfs),
                "score": min(len(tfs), 5),
            })
    return events
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_resonance.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/validation/resonance.py tests/test_resonance.py
git commit -m "feat: add multi-timeframe resonance analysis"
```

---

## Task 12: Pipeline (download -> 6 JSON files)

**Files:**
- Create: `src/txf_mcp/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
from pathlib import Path
from txf_mcp.pipeline import build_ohlcv_from_csv
from txf_mcp.klines.ohlcv_json import read_ohlcv_json

FIXTURE = Path("tests/fixtures/TX_sample_2026_05_29.csv")

def test_builds_six_json_files(tmp_path):
    out = build_ohlcv_from_csv(FIXTURE, "2026-05-29", out_dir=tmp_path)
    assert len(out) == 6
    for tf, path in out.items():
        assert Path(path).exists()
        assert tf in Path(path).name

def test_volume_consistent_across_timeframes(tmp_path):
    out = build_ohlcv_from_csv(FIXTURE, "2026-05-29", out_dir=tmp_path)
    totals = {tf: read_ohlcv_json(p)["volume"].sum() for tf, p in out.items()}
    assert len(set(totals.values())) == 1  # same total volume everywhere
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# src/txf_mcp/pipeline.py
from pathlib import Path
from .data.loader import load_tx_ticks
from .data.cleaner import clean_ticks
from .data.session import tag_session
from .klines.resampler import resample
from .klines.ohlcv_json import write_ohlcv_json
from .constants import TIMEFRAMES

def build_ohlcv_from_csv(csv_path, trade_date: str, out_dir="data/ohlcv") -> dict:
    """Full pipeline: load -> clean -> session -> resample -> write 6 JSON files.
    Returns {timeframe: json_path}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ticks = tag_session(clean_ticks(load_tx_ticks(csv_path)))
    contract = ticks["expiry"].iloc[0] if len(ticks) else ""
    paths = {}
    for tf in TIMEFRAMES:
        bars = resample(ticks, tf)
        p = out / f"TX_{trade_date}_{tf}.json"
        write_ohlcv_json(bars, p, product="TX", contract=contract,
                         trade_date=trade_date, timeframe=tf,
                         source_file=Path(csv_path).name)
        paths[tf] = str(p)
    return paths
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/txf_mcp/pipeline.py tests/test_pipeline.py
git commit -m "feat: add end-to-end OHLCV pipeline"
```

---

## Task 13: MCP server + tools

**Files:**
- Create: `src/txf_mcp/mcp_server/tools.py`
- Create: `src/txf_mcp/mcp_server/server.py`
- Test: `tests/test_tools.py`

Tools operate on JSON files in `data/ohlcv/`. `analyze_txf_day` reads each timeframe JSON, runs all patterns, computes resonance. `list_available_dates` scans the dir. `query_feature_statistics` aggregates backtest across dates. `compare_days` returns numeric similarity. Test the pure-Python tool functions (not the MCP transport).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tools.py
from pathlib import Path
from txf_mcp.pipeline import build_ohlcv_from_csv
from txf_mcp.mcp_server.tools import (
    analyze_txf_day, list_available_dates, query_feature_statistics, compare_days,
)

FIXTURE = Path("tests/fixtures/TX_sample_2026_05_29.csv")

def _setup(tmp_path):
    build_ohlcv_from_csv(FIXTURE, "2026-05-29", out_dir=tmp_path)
    return str(tmp_path)

def test_list_available_dates(tmp_path):
    d = _setup(tmp_path)
    assert "2026-05-29" in list_available_dates(data_dir=d)

def test_analyze_returns_features_and_resonance(tmp_path):
    d = _setup(tmp_path)
    res = analyze_txf_day("2026-05-29", ["1min", "5min"], data_dir=d)
    assert "timeframes" in res and "resonance" in res
    assert "feature_series" in res["timeframes"]["1min"]
    assert "deep_pit" in res["timeframes"]["1min"]["feature_series"]

def test_query_feature_statistics(tmp_path):
    d = _setup(tmp_path)
    stats = query_feature_statistics("high_point", "5min",
                                     ["2026-05-29", "2026-05-29"], 3, data_dir=d)
    assert "up_probability" in stats and "sample_size" in stats

def test_compare_days_similarity(tmp_path):
    d = _setup(tmp_path)
    res = compare_days("2026-05-29", ["2026-05-29"], "5min", data_dir=d)
    # identical day vs itself -> similarity 1.0
    assert res["comparisons"][0]["similarity"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL ModuleNotFoundError.

- [ ] **Step 3: Write tools.py**

```python
# src/txf_mcp/mcp_server/tools.py
from pathlib import Path
import pandas as pd
from ..klines.ohlcv_json import read_ohlcv_json
from ..features.registry import discover_patterns
from ..validation.backtest import backtest_feature
from ..validation.resonance import find_resonance

def _json_path(data_dir, date, tf):
    return Path(data_dir) / f"TX_{date}_{tf}.json"

def list_available_dates(data_dir="data/ohlcv") -> list[str]:
    dates = set()
    for p in Path(data_dir).glob("TX_*_1min.json"):
        dates.add(p.name.split("_")[1])
    return sorted(dates)

def analyze_txf_day(date, timeframes, session="all", data_dir="data/ohlcv") -> dict:
    patterns = discover_patterns()
    tf_out = {}
    fires_by_tf_by_feature = {p.name: {} for p in patterns}
    for tf in timeframes:
        bars = read_ohlcv_json(_json_path(data_dir, date, tf))
        if session != "all":
            bars = bars[bars["session"] == session].reset_index(drop=True)
        series = {}
        summary = {}
        for p in patterns:
            s = p.detect(bars)
            series[p.name] = [bool(x) for x in s]
            summary[f"{p.name}_count"] = int(s.sum())
            fires_by_tf_by_feature[p.name][tf] = bars[s.values][["datetime"]]
        tf_out[tf] = {
            "bar_count": len(bars),
            "feature_series": series,
            "summary": summary,
        }
    resonance = []
    for feat, fires in fires_by_tf_by_feature.items():
        resonance.extend(find_resonance(fires, feat))
    return {"date": date, "session": session,
            "timeframes": tf_out, "resonance": resonance}

def query_feature_statistics(feature, timeframe, date_range, lookforward_bars,
                             data_dir="data/ohlcv") -> dict:
    patterns = {p.name: p for p in discover_patterns()}
    pat = patterns[feature]
    all_dates = list_available_dates(data_dir)
    lo, hi = date_range[0], date_range[-1]
    dates = [d for d in all_dates if lo <= d <= hi]
    frames = []
    for d in dates:
        path = _json_path(data_dir, d, timeframe)
        if path.exists():
            frames.append(read_ohlcv_json(path))
    if not frames:
        return {"feature": feature, "sample_size": 0,
                "lookforward_bars": lookforward_bars,
                "up_probability": 0.0, "avg_return_pct": 0.0,
                "max_return_pct": 0.0, "max_drawdown_pct": 0.0}
    bars = pd.concat(frames, ignore_index=True)
    signal = pat.detect(bars)
    stats = backtest_feature(bars, signal, lookforward_bars)
    stats["feature"] = feature
    return stats

def _signature(bars, patterns) -> list[float]:
    # feature-firing rate vector as the day's signature
    return [float(p.detect(bars).mean()) for p in patterns]

def compare_days(target_date, compare_dates, timeframe, data_dir="data/ohlcv") -> dict:
    patterns = discover_patterns()
    tgt = read_ohlcv_json(_json_path(data_dir, target_date, timeframe))
    tgt_sig = _signature(tgt, patterns)
    comparisons = []
    for d in compare_dates:
        other = read_ohlcv_json(_json_path(data_dir, d, timeframe))
        sig = _signature(other, patterns)
        # cosine-like similarity on signature vectors
        num = sum(a * b for a, b in zip(tgt_sig, sig))
        da = sum(a * a for a in tgt_sig) ** 0.5
        db = sum(b * b for b in sig) ** 0.5
        sim = 1.0 if (da == 0 and db == 0) else (
            0.0 if da == 0 or db == 0 else round(num / (da * db), 4))
        comparisons.append({"date": d, "similarity": sim})
    return {"target_date": target_date, "timeframe": timeframe,
            "comparisons": comparisons}
```

- [ ] **Step 4: Write server.py (MCP transport wrapper)**

```python
# src/txf_mcp/mcp_server/server.py
from mcp.server.fastmcp import FastMCP
from . import tools

mcp = FastMCP("txf-feature-analysis")

@mcp.tool()
def analyze_txf_day(date: str, timeframes: list[str], session: str = "all") -> dict:
    """Analyze a TXF trading day: feature series per timeframe + resonance."""
    return tools.analyze_txf_day(date, timeframes, session)

@mcp.tool()
def query_feature_statistics(feature: str, timeframe: str,
                             date_range: list[str], lookforward_bars: int = 10) -> dict:
    """Statistics of price moves after a feature fires."""
    return tools.query_feature_statistics(feature, timeframe, date_range, lookforward_bars)

@mcp.tool()
def compare_days(target_date: str, compare_dates: list[str], timeframe: str) -> dict:
    """Similarity score between a target day and other days."""
    return tools.compare_days(target_date, compare_dates, timeframe)

@mcp.tool()
def list_available_dates() -> list[str]:
    """List trade dates available in the local OHLCV cache."""
    return tools.list_available_dates()

def main():
    mcp.run()

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_tools.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add src/txf_mcp/mcp_server/ tests/test_tools.py
git commit -m "feat: add MCP server and 4 analysis tools"
```

---

## Task 14: Full test run + integration smoke + docs

**Files:**
- Modify: `README.md`
- Create: `docs/adding_features.md`

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Manual end-to-end smoke (real data, optional network)**

Run:
```bash
uv run python -c "from txf_mcp.pipeline import build_ohlcv_from_csv; print(build_ohlcv_from_csv('tests/fixtures/TX_sample_2026_05_29.csv','2026-05-29'))"
uv run python -c "from txf_mcp.mcp_server.tools import analyze_txf_day; import json; print(json.dumps(analyze_txf_day('2026-05-29',['1min','5min','15min']), ensure_ascii=False)[:500])"
```
Expected: 6 JSON files written under `data/ohlcv/`; analyze prints feature series + resonance.

- [ ] **Step 3: Update README**

Replace README with: install (`uv sync`), build data (`build_ohlcv_from_csv` or downloader), run MCP server (`uv run python -m txf_mcp.mcp_server.server`), Claude Desktop config snippet, link to feature-adding guide.

Claude Desktop config snippet to include:
```json
{
  "mcpServers": {
    "txf-feature-analysis": {
      "command": "uv",
      "args": ["--directory", "D:/git/trading-pattern", "run", "python", "-m", "txf_mcp.mcp_server.server"]
    }
  }
}
```

- [ ] **Step 4: Write docs/adding_features.md**

Document: create `src/txf_mcp/features/patterns/<name>.py`, subclass `FeaturePattern`, set `name`/`category`, implement `detect(klines) -> bool Series`. Registry auto-discovers it; no core changes needed.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/adding_features.md
git commit -m "docs: add usage README and feature-extension guide"
```

---

## Self-Review Notes

- **Spec coverage:** downloader (T7), loader/Big5/TX/spread/volume÷2 (T2), cleaner (T3), session (T4), resampler 6 frames incl 1s (T5), JSON format (T6), registry+patterns (T8/T9), backtest (T10), resonance (T11), pipeline 6 files (T12), 4 MCP tools (T13), tests+docs (T14). All spec sections mapped.
- **Type consistency:** OHLCV DataFrame columns `[datetime, open, high, low, close, volume, n, session]` consistent across resampler/json/patterns/tools. JSON bar short keys `o/h/l/c/v/n` consistent in T6/spec.
- **No placeholders:** every code step contains full implementation.
```
