"""Generate a standalone HTML candlestick chart from an OHLCV JSON file."""
import json
import sys
from datetime import datetime
from pathlib import Path


def to_epoch_local(iso: str) -> int:
    """Parse ISO time and return epoch seconds of the wall-clock treated as UTC,
    so lightweight-charts' UTC axis displays Taipei local time."""
    dt = datetime.fromisoformat(iso).replace(tzinfo=None)
    epoch = datetime(1970, 1, 1)
    return int((dt - epoch).total_seconds())


def build(json_path: str, out_path: str) -> None:
    doc = json.loads(Path(json_path).read_text(encoding="utf-8"))
    meta = doc["meta"]
    candles, volumes = [], []
    for b in doc["bars"]:
        t = to_epoch_local(b["t"])
        candles.append({"time": t, "open": b["o"], "high": b["h"],
                        "low": b["l"], "close": b["c"]})
        up = b["c"] >= b["o"]
        # Taiwan convention: up = red, down = white (on dark background)
        volumes.append({"time": t, "value": b["v"],
                        "color": "rgba(229,57,53,0.6)" if up else "rgba(220,220,220,0.6)"})

    title = (f"{meta['product']} {meta['contract']} — {meta['trade_date']} "
             f"{meta['timeframe']} ({meta['bar_count']} bars, vol {meta['total_volume']})")
    html = _TEMPLATE.replace("__TITLE__", title) \
        .replace("__CANDLES__", json.dumps(candles)) \
        .replace("__VOLUMES__", json.dumps(volumes))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({len(candles)} candles)")


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body { margin:0; background:#161a25; color:#d1d4dc; font-family:system-ui,"Segoe UI",sans-serif; }
  h1 { font-size:15px; font-weight:500; padding:12px 16px; margin:0; border-bottom:1px solid #2a2e39; }
  #chart { width:100vw; height:calc(100vh - 46px); }
</style>
</head>
<body>
<h1>__TITLE__</h1>
<div id="chart"></div>
<script>
  const chart = LightweightCharts.createChart(document.getElementById('chart'), {
    layout: { background: { color: '#161a25' }, textColor: '#d1d4dc' },
    grid: { vertLines: { color: '#2a2e39' }, horzLines: { color: '#2a2e39' } },
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2a2e39' },
    rightPriceScale: { borderColor: '#2a2e39' },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    localization: {
      timeFormatter: (t) => {
        const d = new Date(t * 1000);
        const p = (n) => String(n).padStart(2, '0');
        return `${d.getUTCFullYear()}-${p(d.getUTCMonth()+1)}-${p(d.getUTCDate())} `
             + `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
      },
    },
  });
  const candleSeries = chart.addCandlestickSeries({
    upColor: '#e53935', downColor: '#ffffff',
    borderUpColor: '#e53935', borderDownColor: '#cfcfcf',
    wickUpColor: '#e53935', wickDownColor: '#cfcfcf',
  });
  candleSeries.setData(__CANDLES__);
  const volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' },
    priceScaleId: 'vol',
  });
  volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
  volumeSeries.setData(__VOLUMES__);
  chart.timeScale().fitContent();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "data/ohlcv/TX_2026-05-29_1min.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else "charts/TX_2026-05-29_1min.html"
    build(src, dst)
