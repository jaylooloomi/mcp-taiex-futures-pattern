"""Generate a standalone multi-date HTML candlestick chart from OHLCV JSON.

Scans a directory for TX_<date>_<timeframe>.json files and embeds every date
into one HTML with a date dropdown, session selector, and red/black filter.
"""
import json
import sys
from datetime import datetime
from pathlib import Path


def to_epoch_local(iso: str) -> int:
    """Parse ISO time and return epoch seconds of the wall-clock treated as UTC,
    so lightweight-charts' UTC axis displays Taipei local time."""
    dt = datetime.fromisoformat(iso).replace(tzinfo=None)
    return int((dt - datetime(1970, 1, 1)).total_seconds())


def _build_day(doc: dict) -> dict:
    candles, volumes = [], []
    for b in doc["bars"]:
        t = to_epoch_local(b["t"])
        direction = "red" if b["c"] >= b["o"] else "black"  # 紅=漲, 黑=跌
        candles.append({"time": t, "open": b["o"], "high": b["h"],
                        "low": b["l"], "close": b["c"],
                        "session": b["session"], "dir": direction})
        volumes.append({"time": t, "value": b["v"],
                        "session": b["session"], "dir": direction,
                        "color": "rgba(229,57,53,0.6)" if direction == "red"
                        else "rgba(220,220,220,0.6)"})
    m = doc["meta"]
    return {"candles": candles, "volumes": volumes,
            "bars": m["bar_count"], "vol": m["total_volume"],
            "contract": m["contract"]}


def build(data_dir: str, timeframe: str, out_path: str) -> None:
    files = sorted(Path(data_dir).glob(f"TX_*_{timeframe}.json"))
    if not files:
        raise SystemExit(f"no TX_*_{timeframe}.json files in {data_dir}")
    data = {}
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        data[doc["meta"]["trade_date"]] = _build_day(doc)
    dates = sorted(data)
    default = dates[-1]

    html = (_TEMPLATE
            .replace("__TF__", timeframe)
            .replace("__DEFAULT__", default)
            .replace("__DATES__", json.dumps(dates))
            .replace("__DATA__", json.dumps(data)))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({len(dates)} dates, default {default})")


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>TX __TF__</title>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body { margin:0; background:#161a25; color:#d1d4dc; font-family:system-ui,"Segoe UI",sans-serif; }
  header { display:flex; align-items:center; justify-content:space-between;
           padding:10px 16px; border-bottom:1px solid #2a2e39; gap:16px; flex-wrap:wrap; }
  h1 { font-size:15px; font-weight:500; margin:0; white-space:nowrap; }
  .controls { display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  .grp { display:flex; gap:4px; align-items:center; }
  .grp .lbl { font-size:12px; color:#6b7280; margin-right:2px; }
  .grp button { background:#222632; color:#9aa0ab; border:1px solid #2a2e39;
           padding:5px 12px; font-size:13px; border-radius:4px; cursor:pointer; }
  .grp button:hover { color:#d1d4dc; }
  .grp button.active { background:#e53935; color:#fff; border-color:#e53935; }
  select { background:#222632; color:#d1d4dc; border:1px solid #2a2e39;
           padding:5px 10px; font-size:13px; border-radius:4px; cursor:pointer; }
  #wrap { position:relative; width:100vw; height:calc(100vh - 54px); }
  #chart { width:100%; height:100%; }
  #legend { position:absolute; top:8px; left:12px; z-index:3; pointer-events:none;
            font-size:13px; background:rgba(22,26,37,0.85); padding:6px 10px;
            border-radius:4px; border:1px solid #2a2e39; white-space:nowrap; }
  #legend .k { color:#6b7280; margin:0 2px 0 8px; }
  #legend .t { color:#d1d4dc; font-weight:600; }
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <div class="controls">
    <div class="grp">
      <span class="lbl">日期</span>
      <select id="dateSel"></select>
    </div>
    <div class="grp" id="sessionSel">
      <span class="lbl">盤別</span>
      <button data-session="all" class="active">全日盤</button>
      <button data-session="day">日盤</button>
      <button data-session="night">夜盤</button>
    </div>
    <div class="grp" id="colorSel">
      <span class="lbl">漲跌</span>
      <button data-dir="red" class="active" title="顯示紅(關閉則隱藏紅)">紅</button>
      <button data-dir="black" class="active" title="顯示黑(關閉則隱藏黑)">黑</button>
    </div>
  </div>
</header>
<div id="wrap">
  <div id="legend"></div>
  <div id="chart"></div>
</div>
<script>
  const DATA = __DATA__;
  const DATES = __DATES__;
  const TF = "__TF__";
  let curDate = "__DEFAULT__";
  let curSession = 'all';
  const curDirs = new Set(['red', 'black']);

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
  const volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: 'volume' }, priceScaleId: 'vol',
  });
  volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

  // ---- OHLCV legend (updates on crosshair move) ----
  const legend = document.getElementById('legend');
  const pad = (n) => String(n).padStart(2, '0');
  function fmtTime(t) {
    const d = new Date(t * 1000);
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())} `
         + `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  }
  const fmtN = (n) => (n == null ? '-' : n.toLocaleString());
  function renderLegend(c, vol) {
    if (!c || c.open == null) { legend.innerHTML = ''; return; }
    const up = c.close >= c.open;
    const col = up ? '#e53935' : '#ffffff';
    legend.innerHTML =
      `<span class="t">${fmtTime(c.time)}</span>`
      + `<span class="k">開</span>${fmtN(c.open)}`
      + `<span class="k">高</span>${fmtN(c.high)}`
      + `<span class="k">低</span>${fmtN(c.low)}`
      + `<span class="k">收</span><span style="color:${col}">${fmtN(c.close)}</span>`
      + `<span class="k">量</span>${fmtN(vol)}`;
  }
  // default: latest visible bar of the current day
  let lastBar = null;
  function setDefaultLegend() {
    const day = DATA[curDate];
    const pass = (d) =>
      (curSession === 'all' || d.session === curSession) && curDirs.has(d.dir);
    for (let i = day.candles.length - 1; i >= 0; i--) {
      if (pass(day.candles[i])) {
        renderLegend(day.candles[i], day.volumes[i].value);
        return;
      }
    }
    legend.innerHTML = '';
  }
  chart.subscribeCrosshairMove((param) => {
    if (!param.time || !param.seriesData) { setDefaultLegend(); return; }
    const c = param.seriesData.get(candleSeries);
    const v = param.seriesData.get(volumeSeries);
    if (c && c.open != null) renderLegend({ ...c, time: param.time }, v ? v.value : null);
    else setDefaultLegend();
  });

  // populate date dropdown
  const dateSel = document.getElementById('dateSel');
  DATES.forEach((d) => {
    const o = document.createElement('option');
    o.value = d; o.textContent = d;
    if (d === curDate) o.selected = true;
    dateSel.appendChild(o);
  });

  // refit=true only on date change / initial load. Session & color filters
  // keep the current zoom/scroll so candle size does NOT jump.
  function applyFilter(refit) {
    const day = DATA[curDate];
    const pass = (d) =>
      (curSession === 'all' || d.session === curSession) && curDirs.has(d.dir);
    // Hidden bars become whitespace ({time} only) so visible bars keep their
    // original time position and do NOT shift/pack forward.
    candleSeries.setData(day.candles.map((d) => pass(d)
      ? { time: d.time, open: d.open, high: d.high, low: d.low, close: d.close }
      : { time: d.time }));
    volumeSeries.setData(day.volumes.map((d) => pass(d)
      ? { time: d.time, value: d.value, color: d.color }
      : { time: d.time }));
    if (refit) chart.timeScale().fitContent();
    document.getElementById('title').textContent =
      `TX ${day.contract} — ${curDate} ${TF} (${day.bars} bars, vol ${day.vol})`;
    setDefaultLegend();
  }

  // 換日期：重新貼合畫面 (refit)
  dateSel.addEventListener('change', () => { curDate = dateSel.value; applyFilter(true); });

  // 盤別 / 漲跌：保留當前縮放 (不 refit)
  document.querySelectorAll('#sessionSel button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#sessionSel button').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      curSession = btn.dataset.session;
      applyFilter(false);
    });
  });

  document.querySelectorAll('#colorSel button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const dir = btn.dataset.dir;
      if (curDirs.has(dir)) {
        if (curDirs.size === 1) return;  // 不可全部取消
        curDirs.delete(dir);
        btn.classList.remove('active');
      } else {
        curDirs.add(dir);
        btn.classList.add('active');
      }
      applyFilter(false);
    });
  });

  applyFilter(true);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data/ohlcv"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "1min"
    out = sys.argv[3] if len(sys.argv) > 3 else f"charts/TX_{timeframe}.html"
    build(data_dir, timeframe, out)
