"""Download and process a date range of TAIFEX daily data into OHLCV JSON.

Weekends are skipped; non-trading days (holidays) fail to download and are
reported as skipped. Large raw CSV/zip files are deleted after processing
unless --keep-raw is passed.
"""
import datetime
import sys
from pathlib import Path
from txf_mcp.data.downloader import download
from txf_mcp.pipeline import build_ohlcv_from_csv


def _daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += datetime.timedelta(days=1)


def main(start_s: str, end_s: str, keep_raw: bool = False) -> None:
    start = datetime.date.fromisoformat(start_s)
    end = datetime.date.fromisoformat(end_s)
    ok, skipped = [], []
    for d in _daterange(start, end):
        if d.weekday() >= 5:  # Saturday / Sunday
            continue
        ds = d.isoformat()
        try:
            csv = download(ds)
        except Exception as e:
            skipped.append((ds, f"download failed ({type(e).__name__})"))
            continue
        try:
            build_ohlcv_from_csv(csv, ds)
            ok.append(ds)
            print(f"  processed {ds}")
        except Exception as e:
            skipped.append((ds, f"process failed: {e}"))
        finally:
            if not keep_raw:
                for f in Path("data/raw").glob(f"Daily_{ds.replace('-', '_')}.*"):
                    f.unlink(missing_ok=True)
    print(f"\nDONE. processed {len(ok)} days: {ok}")
    if skipped:
        print(f"skipped {len(skipped)}:")
        for ds, why in skipped:
            print(f"  {ds}: {why}")


if __name__ == "__main__":
    keep = "--keep-raw" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0], args[1], keep_raw=keep)
