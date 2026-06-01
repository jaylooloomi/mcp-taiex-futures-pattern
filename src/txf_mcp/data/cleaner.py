import sys
import pandas as pd


def clean_ticks(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by time and filter abnormal prices (<=0).

    Tick data is NOT de-duplicated: multiple trades at the same second with
    identical price and volume are separate real transactions, not duplicates.
    Removing them would undercount volume.
    """
    before = len(df)
    out = df[df["price"] > 0].copy()
    out = out.sort_values("datetime", kind="stable").reset_index(drop=True)
    dropped = before - len(out)
    if dropped:
        print(f"cleaner: filtered {dropped} abnormal ticks", file=sys.stderr)
    return out
