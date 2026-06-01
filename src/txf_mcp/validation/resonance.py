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
