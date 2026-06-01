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
