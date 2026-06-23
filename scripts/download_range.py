"""Bulk-download TAIFEX daily tick data for a date range, keeping ONLY the
big-TX (product == 'TX') rows to save disk space.

Each day's TAIFEX `Daily_YYYY_MM_DD.zip` bundles every futures product
(~45-60 MB uncompressed). We download the zip into memory, extract the CSV,
filter to TX rows (raw Big5 bytes preserved), and write a compact per-day
file to data/raw/Daily_YYYY_MM_DD.csv -- the exact name/encoding the project's
loader.py expects, so the rest of the pipeline works unchanged.

Robust: skips weekends, skips holidays (non-zip / 404 responses), and is
idempotent -- already-downloaded days are skipped, so it can resume.

Usage:
    python scripts/download_range.py 2026-01-01 2026-06-23
"""
import datetime as dt
import io
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE = ("https://www.taifex.com.tw/file/taifex/Dailydownload/"
        "DailydownloadCSV/Daily_{y}_{m}_{d}.zip")
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
PRODUCT = b"TX"          # big-TX only (exact match, excludes MTX/TXO/etc.)
POLITE_DELAY = 0.5       # seconds between requests


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def filter_tx(csv_bytes: bytes) -> tuple[bytes, int]:
    """Keep header + rows whose product field (col 1) == 'TX'. Returns
    (filtered_bytes, tx_row_count). Operates on raw Big5 bytes -- lossless."""
    lines = csv_bytes.split(b"\n")
    header, body = lines[0], lines[1:]
    kept = [header]
    n = 0
    for ln in body:
        if not ln.strip():
            continue
        parts = ln.split(b",")
        if len(parts) > 1 and parts[1].strip() == PRODUCT:
            kept.append(ln)
            n += 1
    return b"\n".join(kept) + b"\n", n


def fetch(trade_date: dt.date) -> bytes | None:
    """Download + unzip the daily CSV. Returns CSV bytes, or None if the day
    has no data (holiday / not published yet)."""
    url = BASE.format(y=trade_date.year, m=f"{trade_date.month:02d}",
                      d=f"{trade_date.day:02d}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None  # holiday -> server returns an HTML page, not a zip
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    return z.read(name)


def main(start_s: str, end_s: str) -> None:
    start = dt.date.fromisoformat(start_s)
    end = dt.date.fromisoformat(end_s)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    done = skipped = holiday = failed = 0
    total_bytes = 0
    for d in daterange(start, end):
        tag = d.isoformat()
        if d.weekday() >= 5:                       # Sat/Sun
            continue
        out = OUT_DIR / f"Daily_{d.year}_{d.month:02d}_{d.day:02d}.csv"
        if out.exists():
            skipped += 1
            print(f"[skip ] {tag}  already have {out.name}", flush=True)
            continue
        try:
            csv_bytes = fetch(d)
        except Exception as e:                     # noqa: BLE001
            failed += 1
            print(f"[FAIL ] {tag}  {type(e).__name__}: {e}", flush=True)
            time.sleep(POLITE_DELAY)
            continue
        if csv_bytes is None:
            holiday += 1
            print(f"[holid] {tag}  no data (weekday holiday)", flush=True)
            time.sleep(POLITE_DELAY)
            continue
        tx_bytes, n = filter_tx(csv_bytes)
        out.write_bytes(tx_bytes)
        done += 1
        total_bytes += len(tx_bytes)
        print(f"[ok   ] {tag}  TX rows={n:>7}  {len(tx_bytes)/1e6:5.2f} MB "
              f"-> {out.name}", flush=True)
        time.sleep(POLITE_DELAY)

    print("\n=== summary ===", flush=True)
    print(f"downloaded : {done} days  ({total_bytes/1e6:.1f} MB TX-only)")
    print(f"already had: {skipped} days")
    print(f"holidays   : {holiday} days (no data)")
    print(f"failed     : {failed} days")
    print(f"output dir : {OUT_DIR}")


if __name__ == "__main__":
    s = sys.argv[1] if len(sys.argv) > 1 else "2026-01-01"
    e = sys.argv[2] if len(sys.argv) > 2 else dt.date.today().isoformat()
    main(s, e)
