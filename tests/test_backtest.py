import pandas as pd
from txf_mcp.validation.backtest import backtest_feature


def test_basic_stats():
    bars = pd.DataFrame({"close": [100, 102, 104, 103, 101]})
    signal = pd.Series([True, False, False, False, False])
    stats = backtest_feature(bars, signal, lookforward_bars=2)
    assert stats["sample_size"] == 1
    assert round(stats["avg_return_pct"], 2) == 4.0
    assert stats["up_probability"] == 1.0


def test_no_signal_returns_zero_sample():
    bars = pd.DataFrame({"close": [100, 101]})
    signal = pd.Series([False, False])
    stats = backtest_feature(bars, signal, lookforward_bars=1)
    assert stats["sample_size"] == 0
