from pathlib import Path
from .data.loader import load_tx_ticks
from .data.cleaner import clean_ticks
from .data.session import tag_session
from .klines.resampler import resample
from .klines.ohlcv_json import write_ohlcv_json
from .constants import TIMEFRAMES


def build_ohlcv_from_csv(csv_path, trade_date: str, out_dir="data/ohlcv") -> dict:
    """Full pipeline: load -> clean -> session -> resample -> write 6 JSON files.
    Returns {timeframe: json_path}."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ticks = tag_session(clean_ticks(load_tx_ticks(csv_path)))
    contract = ticks["expiry"].iloc[0] if len(ticks) else ""
    paths = {}
    for tf in TIMEFRAMES:
        bars = resample(ticks, tf)
        p = out / f"TX_{trade_date}_{tf}.json"
        write_ohlcv_json(bars, p, product="TX", contract=contract,
                         trade_date=trade_date, timeframe=tf,
                         source_file=Path(csv_path).name)
        paths[tf] = str(p)
    return paths
