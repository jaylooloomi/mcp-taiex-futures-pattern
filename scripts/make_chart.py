"""Generate a standalone multi-date HTML candlestick chart from OHLCV JSON.

Scans a directory for TX_<date>_<timeframe>.json files and embeds every date
into one HTML with a date dropdown, session selector, and red/black filter.
Price and volume are drawn in two vertically-stacked, time-synced panes so
toggling filters never shifts the price candles. Consecutive-red runs in the
day session are numbered (plain numbers, no marker shape) above the last red
candle of each run.
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
    # default to 2026-05-14 if present, else the latest date
    default = "2026-05-14" if "2026-05-14" in data else dates[-1]

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
  body { margin:0; height:100vh; display:flex; flex-direction:column; overflow:hidden;
         background:#161a25; color:#d1d4dc; font-family:system-ui,"Segoe UI",sans-serif; }
  header { flex:0 0 auto; display:flex; align-items:center; justify-content:space-between;
           padding:10px 16px; border-bottom:1px solid #2a2e39; gap:16px; flex-wrap:wrap; }
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
  </div>
</header>
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
  const TF = "__TF__";
  let curDate = "__DEFAULT__";
  let curSession = 'day';
  const curDirs = new Set(['red', 'black']);

  const pad = (n) => String(n).padStart(2, '0');
  const fmtTime = (t) => {
    const d = new Date(t * 1000);
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())} `
         + `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  };
  const localization = { timeFormatter: fmtTime };
  const layout = { background: { color: '#161a25' }, textColor: '#d1d4dc' };
  const grid = { vertLines: { color: '#2a2e39' }, horzLines: { color: '#2a2e39' } };

  // ---- price pane (candles) ----
  const priceChart = LightweightCharts.createChart(document.getElementById('pricePane'), {
    autoSize: true, layout, grid, localization,
    rightPriceScale: { borderColor: '#2a2e39', minimumWidth: 72 },
    timeScale: { visible: false, borderColor: '#2a2e39' },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  // Price scale follows ALL candles in the visible time window (including
  // ones hidden by the red/black filter), so toggling filters never rescales
  // the right axis and the candles stay put vertically.
  function priceAutoscale() {
    const day = DATA[curDate];
    const lr = priceChart.timeScale().getVisibleLogicalRange();
    if (!lr || !day) return null;
    const from = Math.max(0, Math.floor(lr.from));
    const to = Math.min(day.candles.length - 1, Math.ceil(lr.to));
    let lo = Infinity, hi = -Infinity;
    for (let i = from; i <= to; i++) {
      const c = day.candles[i];
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
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2a2e39' },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  function volAutoscale() {
    const day = DATA[curDate];
    const lr = priceChart.timeScale().getVisibleLogicalRange();
    if (!lr || !day) return null;
    const from = Math.max(0, Math.floor(lr.from));
    const to = Math.min(day.volumes.length - 1, Math.ceil(lr.to));
    let hi = 0;
    for (let i = from; i <= to; i++) if (day.volumes[i].value > hi) hi = day.volumes[i].value;
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
  priceChart.subscribeCrosshairMove((param) => {
    if (param.time && param.seriesData) {
      const c = param.seriesData.get(candleSeries);
      const vol = volByTime.get(param.time);
      if (c && c.open != null) {
        renderLegend({ ...c, time: param.time }, vol == null ? null : vol);
        const vy = vol == null ? null : vol;
        if (vy != null) volChart.setCrosshairPosition(vy, param.time, volSeries);
        else volChart.clearCrosshairPosition();
        return;
      }
    }
    volChart.clearCrosshairPosition();
    setDefaultLegend();
  });

  // ---- consecutive-run segments (day session, from 08:45) ----
  // Returns the LAST candle of each maximal run of the given direction.
  function runGroups(day, dir) {
    const out = [];
    let runLast = null;
    for (const c of day.candles) {
      if (c.session !== 'day') continue;
      if (c.dir === dir) runLast = c;
      else if (runLast) { out.push(runLast); runLast = null; }
    }
    if (runLast) out.push(runLast);
    return out;
  }
  // Red segments carry both a sequential number (seq) and a momentum counter:
  // counter +1 when this segment's last close > previous red segment's last
  // close, reset to 0 when lower, unchanged on equal; first segment is 0.
  function buildRedMarkers(day) {
    let counter = 0, prevClose = null;
    return runGroups(day, 'red').map((c, i) => {
      if (prevClose === null) counter = 0;
      else if (c.close > prevClose) counter += 1;
      else if (c.close < prevClose) counter = 0;
      prevClose = c.close;
      return { time: c.time, high: c.high, low: c.low,
               seq: String(i + 1), counter: counter === 0 ? '0' : (counter + 1) + '波' };
    });
  }
  // Black segments mirror red: counter +1 when this segment's last close <
  // previous black segment's last close (lower low), reset to 0 when higher,
  // unchanged on equal; first segment is 0.
  function buildBlackMarkers(day) {
    let counter = 0, prevClose = null;
    return runGroups(day, 'black').map((c, i) => {
      if (prevClose === null) counter = 0;
      else if (c.close < prevClose) counter += 1;
      else if (c.close > prevClose) counter = 0;
      prevClose = c.close;
      return { time: c.time, high: c.high, low: c.low,
               seq: String(i + 1), counter: counter === 0 ? '0' : (counter + 1) + '波' };
    });
  }
  // Low-pivot star: mark the previous candle's low when its low is higher than
  // the one before it AND the current candle's low drops below it (a local
  // swing-high of lows at K[i-1]).
  // Each star also carries a counter: +1 when this star's low > previous
  // star's low, reset to 0 when lower (unchanged on equal; first star is 0).
  function lowPivotStars(day) {
    const out = [];
    const c = day.candles;
    let counter = 0, prevLow = null;
    for (let i = 2; i < c.length; i++) {
      if (c[i].low < c[i - 1].low && c[i - 1].low > c[i - 2].low) {
        const low = c[i - 1].low;
        if (prevLow === null) counter = 0;
        else if (low > prevLow) counter += 1;
        else if (low < prevLow) counter = 0;
        prevLow = low;
        out.push({ time: c[i - 1].time, low, counter });
      }
    }
    return out;
  }

  // High-pivot star (mirror of low pivot): mark the previous candle's high when
  // its high is lower than the one before it AND the current candle's high rises
  // above it (a local swing-low of highs at K[i-1]).
  function highPivotStars(day) {
    const out = [];
    const c = day.candles;
    let counter = 0, prevHigh = null;
    for (let i = 2; i < c.length; i++) {
      if (c[i].high > c[i - 1].high && c[i - 1].high < c[i - 2].high) {
        const high = c[i - 1].high;
        if (prevHigh === null) counter = 0;
        else if (high < prevHigh) counter += 1;  // 高點走低 → +1
        else if (high > prevHigh) counter = 0;    // 高點走高 → 歸零
        prevHigh = high;
        out.push({ time: c[i - 1].time, high, counter });
      }
    }
    return out;
  }

  let curRedMarkers = [];   // shown above (high)
  let curBlackMarkers = []; // shown below (low)
  let curStars = [];        // low-pivot stars
  let curHighStars = [];    // high-pivot stars
  const showLabel = { redSeq: false, redCount: false, blackSeq: false, blackCount: false };
  let showStars = false;     // 策略2: low-pivot stars + their counters
  let showHighStars = false; // high-pivot stars
  function placeNumbers(layer, ts, markers, above, cls, key, dy) {
    for (const m of markers) {
      if (m[key] == null || m[key] === '0') continue;  // hide counter 0 (seq is 1-based)
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
      el.className = 'star';
      el.textContent = '☆';
      el.style.left = x + 'px';
      el.style.top = (y + 2) + 'px';
      layer.appendChild(el);
      if (s.counter >= 1) {  // 0 不顯示
        const cnt = document.createElement('span');
        cnt.className = 'star-count';
        cnt.textContent = String(s.counter);
        cnt.style.left = x + 'px';
        cnt.style.top = (y + 18) + 'px';
        layer.appendChild(cnt);
      }
    }
    if (showHighStars) for (const s of curHighStars) {
      const x = ts.timeToCoordinate(s.time);
      const y = candleSeries.priceToCoordinate(s.high);
      if (x == null || y == null) continue;
      const el = document.createElement('span');
      el.className = 'star-hi';
      el.textContent = '☆';
      el.style.left = x + 'px';
      el.style.top = (y - 2) + 'px';
      layer.appendChild(el);
      if (s.counter >= 1) {  // 0 不顯示
        const cnt = document.createElement('span');
        cnt.className = 'star-hi-count';
        cnt.textContent = String(s.counter);
        cnt.style.left = x + 'px';
        cnt.style.top = (y - 18) + 'px';
        layer.appendChild(cnt);
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

  // refit=true only on date change / initial load. Filters keep current zoom.
  function applyFilter(refit) {
    const day = DATA[curDate];
    const pass = (d) =>
      (curSession === 'all' || d.session === curSession) && curDirs.has(d.dir);
    volByTime = new Map();
    const candleData = day.candles.map((d) => {
      if (!pass(d)) return { time: d.time };
      return { time: d.time, open: d.open, high: d.high, low: d.low, close: d.close };
    });
    const volData = day.volumes.map((d) => {
      if (!pass(d)) return { time: d.time };
      volByTime.set(d.time, d.value);
      return { time: d.time, value: d.value, color: d.color };
    });
    // numbering only for visible direction(s) and not viewing night-only
    const dayOk = curSession !== 'night';
    curRedMarkers = (dayOk && curDirs.has('red')) ? buildRedMarkers(day) : [];
    curBlackMarkers = (dayOk && curDirs.has('black')) ? buildBlackMarkers(day) : [];
    curStars = lowPivotStars(day);
    curHighStars = highPivotStars(day);

    const range = priceChart.timeScale().getVisibleLogicalRange();
    candleSeries.setData(candleData);
    volSeries.setData(volData);
    if (refit) {
      // fit to the passing (visible) bars, not the whitespace-padded full range
      let first = -1, last = -1;
      for (let i = 0; i < day.candles.length; i++) {
        if (pass(day.candles[i])) { if (first < 0) first = i; last = i; }
      }
      if (first >= 0) priceChart.timeScale().setVisibleLogicalRange({ from: first - 0.5, to: last + 0.5 });
      else priceChart.timeScale().fitContent();
    } else if (range) {
      priceChart.timeScale().setVisibleLogicalRange(range);
    }
    positionNumbers();
    document.getElementById('title').textContent =
      `TX ${day.contract} — ${curDate} ${TF} (${day.bars} bars, vol ${day.vol})`;
    setDefaultLegend();
  }

  dateSel.addEventListener('change', () => { curDate = dateSel.value; applyFilter(true); });

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

  // 數字顯示/隱藏（可複選，即時切換不影響縮放）
  document.querySelectorAll('#labelSel button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.label;
      showLabel[k] = !showLabel[k];
      btn.classList.toggle('active', showLabel[k]);
      positionNumbers();
    });
  });

  // 策略2: 一鍵開關低點 / 高點星星 + 計數
  document.querySelectorAll('#starSel button').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.dataset.star === 'low') {
        showStars = !showStars;
        btn.classList.toggle('active', showStars);
      } else {
        showHighStars = !showHighStars;
        btn.classList.toggle('active', showHighStars);
      }
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
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "1min"
    out = sys.argv[3] if len(sys.argv) > 3 else f"charts/TX_{timeframe}.html"
    build(data_dir, timeframe, out)
