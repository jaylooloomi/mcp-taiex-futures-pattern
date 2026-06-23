"""Generate a standalone multi-date, multi-timeframe HTML candlestick chart.

Embeds 1-minute OHLCV per day (the base resolution) and resamples every other
timeframe in the browser, so adding timeframes never requires regenerating data.

Timeframes (mutually exclusive):
  intraday (one selected day):  1/2/3/5/8/10/15/30/60 min
  multi-day overview:
    日K      one candle per trading day (night + day sessions merged)
    日夜2根  two candles per trading day (night session, then day session)

Price + volume are two vertically-stacked, time-synced panes. Date / session
(全日盤/日盤/夜盤) / red-black filters and the 策略1/策略2 feature annotations
are preserved for intraday timeframes; annotations auto-hide in multi-day modes.
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


def build(data_dir: str, out_path: str, base_tf: str = "1min") -> None:
    files = sorted(Path(data_dir).glob(f"TX_*_{base_tf}.json"))
    if not files:
        raise SystemExit(f"no TX_*_{base_tf}.json files in {data_dir}")
    data = {}
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        data[doc["meta"]["trade_date"]] = _build_day(doc)
    dates = sorted(data)
    default = dates[-1]  # latest trading day

    html = (_TEMPLATE
            .replace("__DEFAULT__", default)
            .replace("__DATES__", json.dumps(dates))
            .replace("__DATA__", json.dumps(data)))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({len(dates)} dates, base {base_tf}, default {default})")


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>TX K線</title>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body { margin:0; height:100vh; display:flex; flex-direction:column; overflow:hidden;
         background:#161a25; color:#d1d4dc; font-family:system-ui,"Segoe UI",sans-serif; }
  header { flex:0 0 auto; display:flex; align-items:center; justify-content:space-between;
           padding:10px 16px; border-bottom:1px solid #2a2e39; gap:16px; flex-wrap:wrap; }
  #tfBar { flex:0 0 auto; display:flex; align-items:center; gap:4px; flex-wrap:wrap;
           padding:8px 16px; border-bottom:1px solid #2a2e39; }
  #strategies { flex:0 0 auto; display:flex; flex-direction:column; gap:6px;
           padding:8px 16px; border-bottom:1px solid #2a2e39; }
  .strat { display:flex; align-items:center; justify-content:flex-end; gap:12px; flex-wrap:wrap; }
  .strat-name { font-size:13px; font-weight:600; color:#ffd400; }
  h1 { font-size:15px; font-weight:500; margin:0; white-space:nowrap; }
  .controls { display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
  .grp { display:flex; gap:4px; align-items:center; }
  .grp .lbl { font-size:12px; color:#6b7280; margin-right:2px; }
  .grp button { background:#222632; color:#9aa0ab; border:1px solid #2a2e39;
           padding:5px 12px; font-size:13px; border-radius:4px; cursor:pointer; }
  .grp button:hover { color:#d1d4dc; }
  .grp button.active { background:#e53935; color:#fff; border-color:#e53935; }
  #tfBar .lbl { font-size:12px; color:#6b7280; margin-right:4px; }
  #tfBar button { background:#222632; color:#9aa0ab; border:1px solid #2a2e39;
           padding:5px 12px; font-size:13px; border-radius:4px; cursor:pointer; }
  #tfBar button:hover { color:#d1d4dc; }
  #tfBar button.active { background:#2962ff; color:#fff; border-color:#2962ff; }
  #tfBar button.multi.active { background:#9c27b0; border-color:#9c27b0; }
  #tfBar .sep { width:1px; align-self:stretch; background:#2a2e39; margin:0 6px; }
  select { background:#222632; color:#d1d4dc; border:1px solid #2a2e39;
           padding:5px 10px; font-size:13px; border-radius:4px; cursor:pointer; }
  #wrap { flex:1 1 0; min-height:0; display:flex; flex-direction:column; width:100vw; }
  #pricePane { position:relative; flex:3 1 0; min-height:0; }
  #volPane { flex:1 1 0; min-height:0; border-top:1px solid #2a2e39; }
  #legend { position:absolute; top:8px; left:12px; z-index:4; pointer-events:none;
            font-size:13px; background:rgba(22,26,37,0.85); padding:6px 10px;
            border-radius:4px; border:1px solid #2a2e39; white-space:nowrap; }
  #legend .k { color:#6b7280; margin:0 2px 0 8px; }
  #legend .t { color:#d1d4dc; font-weight:600; }
  #numLayer { position:absolute; inset:0; overflow:hidden; pointer-events:none; z-index:3; }
  #numLayer span { position:absolute; font-size:12px; font-weight:700; white-space:nowrap; }
  #numLayer .num-red { transform:translate(-50%,-100%); color:#e53935; }    /* 紅線段順序編號(在上方) */
  #numLayer .num-count { transform:translate(-50%,-100%); color:#ffd400; }  /* 紅線段計數器(黃色粗體,疊在編號上方) */
  #numLayer .num-black { transform:translate(-50%,0); color:#ffffff; }      /* 黑線段編號(在下方) */
  #numLayer .num-count-dn { transform:translate(-50%,0); color:#ffd400; }   /* 黑線段計數器(黃色粗體,疊在編號下方) */
  #numLayer .star { transform:translate(-50%,0); color:#4fc3f7; font-size:13px; }  /* 低點轉折小星星(下方) */
  #numLayer .star-count { transform:translate(-50%,0); color:#4fc3f7; }             /* 低點星星計數器(在星星下方) */
  #numLayer .star-hi { transform:translate(-50%,-100%); color:#ff9800; font-size:13px; }  /* 高點轉折小星星(上方) */
  #numLayer .star-hi-count { transform:translate(-50%,-100%); color:#ff9800; }             /* 高點星星計數器(在星星上方) */
  #numLayer .sess-icon { transform:translate(-50%,-50%); font-size:15px;
                         filter:drop-shadow(0 0 2px #000); }  /* 日夜2根:☀️/🌙 標在高低中央 */

  /* --- RWD: 手機/小螢幕 (桌機樣式不受影響) --- */
  @media (max-width: 640px) {
    header { padding:8px 10px; gap:8px; }
    h1 { font-size:12px; flex:1 1 100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .controls { gap:8px; width:100%; justify-content:flex-start; }
    .grp { gap:4px; flex-wrap:wrap; }
    .grp .lbl { font-size:11px; }
    .grp button, select, #tfBar button { padding:7px 10px; font-size:13px; }
    #tfBar { padding:6px 10px; }
    #strategies { padding:6px 10px; gap:6px; }
    .strat { justify-content:flex-start; }
    .strat-name { font-size:12px; }
    #legend { font-size:11px; left:6px; top:6px; padding:4px 6px; line-height:1.6;
              white-space:normal; max-width:calc(100vw - 12px); }
    #legend .k { margin:0 1px 0 5px; }
  }
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
      <button data-session="all">全日盤</button>
      <button data-session="day" class="active">日盤</button>
      <button data-session="night">夜盤</button>
    </div>
    <div class="grp" id="colorSel">
      <span class="lbl">漲跌</span>
      <button data-dir="red" class="active" title="顯示紅(關閉則隱藏紅)">紅</button>
      <button data-dir="black" class="active" title="顯示黑(關閉則隱藏黑)">黑</button>
    </div>
    <div class="grp" id="iconSel" style="display:none">
      <span class="lbl">標示</span>
      <button data-icon="sess" class="active" title="日盤☀️ / 夜盤🌙 標在每根高低中央">☀️/🌙</button>
    </div>
  </div>
</header>
<div id="tfBar">
  <span class="lbl">框架</span>
  <button data-tf="1min" class="active">1分</button>
  <button data-tf="2min">2分</button>
  <button data-tf="3min">3分</button>
  <button data-tf="5min">5分</button>
  <button data-tf="8min">8分</button>
  <button data-tf="10min">10分</button>
  <button data-tf="15min">15分</button>
  <button data-tf="30min">30分</button>
  <button data-tf="60min">60分</button>
  <span class="sep"></span>
  <button data-tf="daily" class="multi">日K</button>
  <button data-tf="session" class="multi" title="每個交易日畫成兩根:夜盤一根、日盤一根">日夜2根</button>
</div>
<div id="strategies">
  <div class="strat">
    <span class="strat-name">策略1</span>
    <div class="grp" id="labelSel">
      <button data-label="redSeq" title="紅K 紅色順序編號">紅K紅</button>
      <button data-label="redCount" title="紅K 黃色計數器">上漲波(紅K黃)</button>
      <button data-label="blackSeq" title="黑K 白色順序編號">黑K黑</button>
      <button data-label="blackCount" title="黑K 黃色計數器">下跌波(黑K黃)</button>
    </div>
  </div>
  <div class="strat">
    <span class="strat-name">策略2</span>
    <div class="grp" id="starSel">
      <button data-star="low" title="低點轉折星星與計數(一起開關)">數低=下穿(低點星星+數字)</button>
      <button data-star="high" title="高點轉折星星與計數(一起開關)">數高=上穿(高點星星+數字)</button>
    </div>
  </div>
</div>
<div id="wrap">
  <div id="pricePane">
    <div id="legend"></div>
    <div id="numLayer"></div>
  </div>
  <div id="volPane"></div>
</div>
<script>
  const DATA = __DATA__;
  const DATES = __DATES__;
  let curDate = "__DEFAULT__";
  let curTf = '1min';            // one of INTRADAY keys, 'daily', 'session'
  let curSession = 'day';
  const curDirs = new Set(['red', 'black']);

  const INTRADAY = { '1min':1,'2min':2,'3min':3,'5min':5,'8min':8,
                     '10min':10,'15min':15,'30min':30,'60min':60 };
  const TF_LABEL = { ...Object.fromEntries(Object.keys(INTRADAY).map(k=>[k,k])),
                     daily:'日K (一天一根)', session:'日夜2根 (一天兩根)' };

  const pad = (n) => String(n).padStart(2, '0');
  let view = null;       // { candles, volumes, multiDay }
  let labelMap = new Map();  // synthetic-time -> display label (multi-day modes)

  const fmtTime = (t) => {
    if (view && view.multiDay && labelMap.has(t)) return labelMap.get(t);
    const d = new Date(t * 1000);
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())} `
         + `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  };
  const tickMark = (t) => {
    if (view && view.multiDay && labelMap.has(t)) return labelMap.get(t).slice(5); // MM-DD[ 夜/日]
    const d = new Date(t * 1000);
    return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  };
  const localization = { timeFormatter: fmtTime };
  const layout = { background: { color: '#161a25' }, textColor: '#d1d4dc' };
  const grid = { vertLines: { color: '#2a2e39' }, horzLines: { color: '#2a2e39' } };

  // ============================================================
  //  Resampling — everything is derived from the embedded 1-min base
  // ============================================================
  function dateEpoch(dateStr, h) {                 // local-wall-clock-as-UTC epoch
    const [y, m, d] = dateStr.split('-').map(Number);
    return Math.floor(Date.UTC(y, m - 1, d, h, 0, 0) / 1000);
  }
  // Merge a day's parallel candle/volume arrays into working bars with volume.
  function dayBars(date) {
    const day = DATA[date];
    if (!day) return [];
    return day.candles.map((c, i) => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
      session: c.session, vol: day.volumes[i].value,
    }));
  }
  const colorOf = (dir) => dir === 'red' ? 'rgba(229,57,53,0.6)' : 'rgba(220,220,220,0.6)';
  function emit(bars, b) {                          // push finalized candle + volume
    const dir = b.close >= b.open ? 'red' : 'black';
    bars.candles.push({ time: b.time, open: b.open, high: b.high, low: b.low,
                        close: b.close, session: b.session, dir });
    bars.volumes.push({ time: b.time, value: b.vol, session: b.session,
                        dir, color: colorOf(dir) });
  }
  // Intraday: bucket 1-min bars into N-min bars, aligned to each session
  // segment's start, never spanning the day/night boundary.
  function resampleIntraday(src, N) {
    const secs = N * 60, out = { candles: [], volumes: [] };
    let segStart = null, prevSes = null, bk = null, agg = null;
    const flush = () => { if (agg) { emit(out, agg); agg = null; } };
    for (const c of src) {
      if (c.session !== prevSes) { flush(); segStart = c.time; prevSes = c.session; bk = null; }
      const b = Math.floor((c.time - segStart) / secs);
      if (b !== bk) {
        flush();
        agg = { time: segStart + b * secs, open: c.open, high: c.high,
                low: c.low, close: c.close, session: c.session, vol: c.vol };
        bk = b;
      } else {
        if (c.high > agg.high) agg.high = c.high;
        if (c.low < agg.low) agg.low = c.low;
        agg.close = c.close; agg.vol += c.vol;
      }
    }
    flush();
    return out;
  }
  // Aggregate many bars into one OHLCV (no time/session).
  function aggregate(src) {
    if (!src.length) return null;
    let o = src[0].open, h = -Infinity, l = Infinity, v = 0, c = src[src.length - 1].close;
    for (const b of src) { if (b.high > h) h = b.high; if (b.low < l) l = b.low; v += b.vol; }
    return { open: o, high: h, low: l, close: c, vol: v };
  }

  function buildView() {
    labelMap = new Map();
    if (curTf in INTRADAY) {
      const out = resampleIntraday(dayBars(curDate), INTRADAY[curTf]);
      return { candles: out.candles, volumes: out.volumes, multiDay: false };
    }
    const out = { candles: [], volumes: [] };
    for (const date of DATES) {
      const src = dayBars(date);
      if (!src.length) continue;
      if (curTf === 'daily') {
        const a = aggregate(src); if (!a) continue;
        const t = dateEpoch(date, 12);
        labelMap.set(t, date);
        emit(out, { time: t, session: 'day', ...a });
      } else {                                       // session: 夜盤 then 日盤
        const night = aggregate(src.filter(b => b.session === 'night'));
        const day = aggregate(src.filter(b => b.session === 'day'));
        if (night) { const t = dateEpoch(date, 3);  labelMap.set(t, date + ' 夜'); emit(out, { time: t, session: 'night', ...night }); }
        if (day)   { const t = dateEpoch(date, 11); labelMap.set(t, date + ' 日'); emit(out, { time: t, session: 'day', ...day }); }
      }
    }
    return { candles: out.candles, volumes: out.volumes, multiDay: true };
  }

  // ---- price pane (candles) ----
  const priceChart = LightweightCharts.createChart(document.getElementById('pricePane'), {
    autoSize: true, layout, grid, localization,
    rightPriceScale: { borderColor: '#2a2e39', minimumWidth: 72 },
    timeScale: { visible: false, borderColor: '#2a2e39' },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  // Price scale follows ALL candles in the visible window (including ones hidden
  // by the red/black filter), so toggling filters never rescales the axis.
  function priceAutoscale() {
    const lr = priceChart.timeScale().getVisibleLogicalRange();
    if (!lr || !view) return null;
    const from = Math.max(0, Math.floor(lr.from));
    const to = Math.min(view.candles.length - 1, Math.ceil(lr.to));
    let lo = Infinity, hi = -Infinity;
    for (let i = from; i <= to; i++) {
      const c = view.candles[i]; if (!c) continue;
      if (c.low < lo) lo = c.low;
      if (c.high > hi) hi = c.high;
    }
    if (!isFinite(lo) || !isFinite(hi)) return null;
    return { priceRange: { minValue: lo, maxValue: hi } };
  }
  const candleSeries = priceChart.addCandlestickSeries({
    upColor: '#e53935', downColor: '#ffffff',
    borderUpColor: '#e53935', borderDownColor: '#cfcfcf',
    wickUpColor: '#e53935', wickDownColor: '#cfcfcf',
    autoscaleInfoProvider: priceAutoscale,
  });

  // ---- volume pane (own block) ----
  const volChart = LightweightCharts.createChart(document.getElementById('volPane'), {
    autoSize: true, layout, grid, localization,
    rightPriceScale: { borderColor: '#2a2e39', minimumWidth: 72 },
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2a2e39',
                 tickMarkFormatter: tickMark },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  function volAutoscale() {
    const lr = priceChart.timeScale().getVisibleLogicalRange();
    if (!lr || !view) return null;
    const from = Math.max(0, Math.floor(lr.from));
    const to = Math.min(view.volumes.length - 1, Math.ceil(lr.to));
    let hi = 0;
    for (let i = from; i <= to; i++) if (view.volumes[i] && view.volumes[i].value > hi) hi = view.volumes[i].value;
    return hi > 0 ? { priceRange: { minValue: 0, maxValue: hi } } : null;
  }
  const volSeries = volChart.addHistogramSeries({
    priceFormat: { type: 'volume' }, autoscaleInfoProvider: volAutoscale,
  });
  volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.15, bottom: 0 } });

  // ---- keep the two time scales in sync ----
  let syncing = false;
  function link(src, dst) {
    src.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (syncing || !r) return;
      syncing = true;
      dst.timeScale().setVisibleLogicalRange(r);
      syncing = false;
      positionNumbers();
    });
  }
  link(priceChart, volChart);
  link(volChart, priceChart);

  // ---- OHLCV legend ----
  const legend = document.getElementById('legend');
  let volByTime = new Map();
  const fmtN = (n) => (n == null ? '-' : n.toLocaleString());
  function renderLegend(c, vol) {
    if (!c || c.open == null) { legend.innerHTML = ''; return; }
    const col = c.close >= c.open ? '#e53935' : '#ffffff';
    legend.innerHTML =
      `<span class="t">${fmtTime(c.time)}</span>`
      + `<span class="k">開</span>${fmtN(c.open)}`
      + `<span class="k">高</span>${fmtN(c.high)}`
      + `<span class="k">低</span>${fmtN(c.low)}`
      + `<span class="k">收</span><span style="color:${col}">${fmtN(c.close)}</span>`
      + `<span class="k">量</span>${fmtN(vol)}`;
  }
  const pass = (d) =>
    (curTf === 'daily' || curSession === 'all' || d.session === curSession) && curDirs.has(d.dir);
  function setDefaultLegend() {
    if (!view) { legend.innerHTML = ''; return; }
    for (let i = view.candles.length - 1; i >= 0; i--) {
      if (pass(view.candles[i])) {
        renderLegend(view.candles[i], view.volumes[i].value);
        return;
      }
    }
    legend.innerHTML = '';
  }
  priceChart.subscribeCrosshairMove((param) => {
    if (param.time && param.seriesData) {
      const c = param.seriesData.get(candleSeries);
      const vol = volByTime.get(param.time);
      if (c && c.open != null) {
        renderLegend({ ...c, time: param.time }, vol == null ? null : vol);
        if (vol != null) volChart.setCrosshairPosition(vol, param.time, volSeries);
        else volChart.clearCrosshairPosition();
        return;
      }
    }
    volChart.clearCrosshairPosition();
    setDefaultLegend();
  });

  // ============================================================
  //  Feature annotations (策略1/策略2) — intraday day-session only
  // ============================================================
  // Returns the LAST candle of each maximal run of the given direction.
  function runGroups(cs, dir) {
    const out = [];
    let runLast = null;
    for (const c of cs) {
      if (c.session !== 'day') continue;
      if (c.dir === dir) runLast = c;
      else if (runLast) { out.push(runLast); runLast = null; }
    }
    if (runLast) out.push(runLast);
    return out;
  }
  function buildRedMarkers(cs) {
    let counter = 0, prevClose = null;
    return runGroups(cs, 'red').map((c, i) => {
      if (prevClose === null) counter = 0;
      else if (c.close > prevClose) counter += 1;
      else if (c.close < prevClose) counter = 0;
      prevClose = c.close;
      return { time: c.time, high: c.high, low: c.low,
               seq: String(i + 1), counter: counter === 0 ? '0' : (counter + 1) + '波' };
    });
  }
  function buildBlackMarkers(cs) {
    let counter = 0, prevClose = null;
    return runGroups(cs, 'black').map((c, i) => {
      if (prevClose === null) counter = 0;
      else if (c.close < prevClose) counter += 1;
      else if (c.close > prevClose) counter = 0;
      prevClose = c.close;
      return { time: c.time, high: c.high, low: c.low,
               seq: String(i + 1), counter: counter === 0 ? '0' : (counter + 1) + '波' };
    });
  }
  function lowPivotStars(cs) {
    const out = [];
    let counter = 0, prevLow = null;
    for (let i = 2; i < cs.length; i++) {
      if (cs[i].low < cs[i - 1].low && cs[i - 1].low > cs[i - 2].low) {
        const low = cs[i - 1].low;
        if (prevLow === null) counter = 0;
        else if (low > prevLow) counter += 1;
        else if (low < prevLow) counter = 0;
        prevLow = low;
        out.push({ time: cs[i - 1].time, low, counter });
      }
    }
    return out;
  }
  function highPivotStars(cs) {
    const out = [];
    let counter = 0, prevHigh = null;
    for (let i = 2; i < cs.length; i++) {
      if (cs[i].high > cs[i - 1].high && cs[i - 1].high < cs[i - 2].high) {
        const high = cs[i - 1].high;
        if (prevHigh === null) counter = 0;
        else if (high < prevHigh) counter += 1;
        else if (high > prevHigh) counter = 0;
        prevHigh = high;
        out.push({ time: cs[i - 1].time, high, counter });
      }
    }
    return out;
  }

  let curRedMarkers = [], curBlackMarkers = [], curStars = [], curHighStars = [];
  const showLabel = { redSeq: false, redCount: false, blackSeq: false, blackCount: false };
  let showStars = false, showHighStars = false;
  let showSessionIcons = true;   // 日夜2根:☀️/🌙 標示(預設開,可關)
  function placeNumbers(layer, ts, markers, above, cls, key, dy) {
    for (const m of markers) {
      if (m[key] == null || m[key] === '0') continue;
      const x = ts.timeToCoordinate(m.time);
      const y = candleSeries.priceToCoordinate(above ? m.high : m.low);
      if (x == null || y == null) continue;
      const el = document.createElement('span');
      el.className = cls;
      el.textContent = m[key];
      el.style.left = x + 'px';
      el.style.top = (y + dy) + 'px';
      layer.appendChild(el);
    }
  }
  function positionNumbers() {
    const layer = document.getElementById('numLayer');
    layer.innerHTML = '';
    const ts = priceChart.timeScale();
    if (showLabel.redSeq)   placeNumbers(layer, ts, curRedMarkers, true, 'num-red', 'seq', -4);
    if (showLabel.redCount) placeNumbers(layer, ts, curRedMarkers, true, 'num-count', 'counter', -22);
    if (showLabel.blackSeq) placeNumbers(layer, ts, curBlackMarkers, false, 'num-black', 'seq', 4);
    if (showLabel.blackCount) placeNumbers(layer, ts, curBlackMarkers, false, 'num-count-dn', 'counter', 22);
    if (showStars) for (const s of curStars) {
      const x = ts.timeToCoordinate(s.time);
      const y = candleSeries.priceToCoordinate(s.low);
      if (x == null || y == null) continue;
      const el = document.createElement('span');
      el.className = 'star'; el.textContent = '☆';
      el.style.left = x + 'px'; el.style.top = (y + 2) + 'px';
      layer.appendChild(el);
      if (s.counter >= 1) {
        const cnt = document.createElement('span');
        cnt.className = 'star-count'; cnt.textContent = String(s.counter);
        cnt.style.left = x + 'px'; cnt.style.top = (y + 18) + 'px';
        layer.appendChild(cnt);
      }
    }
    if (showHighStars) for (const s of curHighStars) {
      const x = ts.timeToCoordinate(s.time);
      const y = candleSeries.priceToCoordinate(s.high);
      if (x == null || y == null) continue;
      const el = document.createElement('span');
      el.className = 'star-hi'; el.textContent = '☆';
      el.style.left = x + 'px'; el.style.top = (y - 2) + 'px';
      layer.appendChild(el);
      if (s.counter >= 1) {
        const cnt = document.createElement('span');
        cnt.className = 'star-hi-count'; cnt.textContent = String(s.counter);
        cnt.style.left = x + 'px'; cnt.style.top = (y - 18) + 'px';
        layer.appendChild(cnt);
      }
    }
    // 日夜2根:在每根可見 K 棒高低中央標 ☀️(日盤) / 🌙(夜盤)
    if (curTf === 'session' && showSessionIcons && view) {
      for (const c of view.candles) {
        if (!pass(c)) continue;
        const x = ts.timeToCoordinate(c.time);
        const y = candleSeries.priceToCoordinate((c.high + c.low) / 2);
        if (x == null || y == null) continue;
        const el = document.createElement('span');
        el.className = 'sess-icon';
        el.textContent = c.session === 'day' ? '☀️' : '🌙';
        el.style.left = x + 'px';
        el.style.top = y + 'px';
        layer.appendChild(el);
      }
    }
  }

  // ---- date dropdown ----
  const dateSel = document.getElementById('dateSel');
  DATES.forEach((d) => {
    const o = document.createElement('option');
    o.value = d; o.textContent = d;
    if (d === curDate) o.selected = true;
    dateSel.appendChild(o);
  });

  function recenterToDate(date) {                    // scroll multi-day view to a date
    let idx = -1;
    for (let i = 0; i < view.candles.length; i++) {
      const lab = labelMap.get(view.candles[i].time) || '';
      if (lab.startsWith(date)) { idx = i; break; }
    }
    if (idx < 0) return;
    const half = curTf === 'session' ? 16 : 25;
    priceChart.timeScale().setVisibleLogicalRange({ from: idx - half, to: idx + half });
  }

  // refit=true only on date / timeframe change. Filter toggles keep current zoom.
  function applyFilter(refit) {
    view = buildView();
    volByTime = new Map();
    const candleData = view.candles.map((d) => {
      if (!pass(d)) return { time: d.time };
      return { time: d.time, open: d.open, high: d.high, low: d.low, close: d.close };
    });
    const volData = view.volumes.map((d) => {
      if (!pass(d)) return { time: d.time };
      volByTime.set(d.time, d.value);
      return { time: d.time, value: d.value, color: d.color };
    });
    // feature annotations: intraday day-session only
    const intraday = !view.multiDay;
    document.getElementById('strategies').style.display = intraday ? '' : 'none';
    document.getElementById('iconSel').style.display = (curTf === 'session') ? '' : 'none';
    const dayOk = intraday && curSession !== 'night';
    curRedMarkers = (dayOk && curDirs.has('red')) ? buildRedMarkers(view.candles) : [];
    curBlackMarkers = (dayOk && curDirs.has('black')) ? buildBlackMarkers(view.candles) : [];
    curStars = intraday ? lowPivotStars(view.candles) : [];
    curHighStars = intraday ? highPivotStars(view.candles) : [];

    const range = priceChart.timeScale().getVisibleLogicalRange();
    candleSeries.setData(candleData);
    volSeries.setData(volData);
    if (refit) {
      let first = -1, last = -1;
      for (let i = 0; i < view.candles.length; i++) {
        if (pass(view.candles[i])) { if (first < 0) first = i; last = i; }
      }
      if (first >= 0) priceChart.timeScale().setVisibleLogicalRange({ from: first - 0.5, to: last + 0.5 });
      else priceChart.timeScale().fitContent();
    } else if (range) {
      priceChart.timeScale().setVisibleLogicalRange(range);
    }
    positionNumbers();

    const contract = (DATA[curDate] || DATA[DATES[DATES.length - 1]]).contract;
    if (view.multiDay) {
      document.getElementById('title').textContent =
        `TX ${contract} — ${TF_LABEL[curTf]} · ${DATES.length} 天 (${view.candles.length} 根)`;
    } else {
      const day = DATA[curDate];
      document.getElementById('title').textContent =
        `TX ${contract} — ${curDate} ${TF_LABEL[curTf]} (${view.candles.length} 根, 量 ${day.vol})`;
    }
    setDefaultLegend();
  }

  dateSel.addEventListener('change', () => {
    curDate = dateSel.value;
    if (view && view.multiDay) recenterToDate(curDate);
    else applyFilter(true);
  });

  document.querySelectorAll('#tfBar button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#tfBar button').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      curTf = btn.dataset.tf;
      // entering a multi-day mode: show every bar by default (日夜2根 needs both
      // sessions visible), but the session filter still works afterwards.
      if (curTf === 'daily' || curTf === 'session') {
        curSession = 'all';
        document.querySelectorAll('#sessionSel button')
          .forEach((b) => b.classList.toggle('active', b.dataset.session === 'all'));
      }
      applyFilter(true);
    });
  });

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
        if (curDirs.size === 1) return;
        curDirs.delete(dir); btn.classList.remove('active');
      } else {
        curDirs.add(dir); btn.classList.add('active');
      }
      applyFilter(false);
    });
  });

  document.querySelectorAll('#labelSel button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.label;
      showLabel[k] = !showLabel[k];
      btn.classList.toggle('active', showLabel[k]);
      positionNumbers();
    });
  });

  document.querySelectorAll('#starSel button').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.dataset.star === 'low') { showStars = !showStars; btn.classList.toggle('active', showStars); }
      else { showHighStars = !showHighStars; btn.classList.toggle('active', showHighStars); }
      positionNumbers();
    });
  });

  document.querySelectorAll('#iconSel button').forEach((btn) => {
    btn.addEventListener('click', () => {
      showSessionIcons = !showSessionIcons;
      btn.classList.toggle('active', showSessionIcons);
      positionNumbers();
    });
  });

  window.addEventListener('resize', () => setTimeout(positionNumbers, 50));

  applyFilter(true);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "data/ohlcv"
    out = sys.argv[2] if len(sys.argv) > 2 else "docs/index.html"
    build(data_dir, out)
