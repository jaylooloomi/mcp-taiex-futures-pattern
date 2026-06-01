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
    assert res["comparisons"][0]["similarity"] == 1.0
