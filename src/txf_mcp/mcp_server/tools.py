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
    return [float(p.detect(bars).mean()) for p in patterns]


def compare_days(target_date, compare_dates, timeframe, data_dir="data/ohlcv") -> dict:
    patterns = discover_patterns()
    tgt = read_ohlcv_json(_json_path(data_dir, target_date, timeframe))
    tgt_sig = _signature(tgt, patterns)
    comparisons = []
    for d in compare_dates:
        other = read_ohlcv_json(_json_path(data_dir, d, timeframe))
        sig = _signature(other, patterns)
        num = sum(a * b for a, b in zip(tgt_sig, sig))
        da = sum(a * a for a in tgt_sig) ** 0.5
        db = sum(b * b for b in sig) ** 0.5
        sim = 1.0 if (da == 0 and db == 0) else (
            0.0 if da == 0 or db == 0 else round(num / (da * db), 4))
        comparisons.append({"date": d, "similarity": sim})
    return {"target_date": target_date, "timeframe": timeframe,
            "comparisons": comparisons}
