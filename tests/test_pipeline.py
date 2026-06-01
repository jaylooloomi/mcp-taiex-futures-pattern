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
    assert len(set(totals.values())) == 1
