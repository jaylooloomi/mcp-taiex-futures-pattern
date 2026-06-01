import pandas as pd
from txf_mcp.validation.resonance import find_resonance


def _fire(times):
    return pd.DataFrame({
        "datetime": pd.to_datetime(times).tz_localize("+08:00"),
    })


def test_resonance_when_two_frames_fire_same_minute():
    fires = {
        "1min": _fire(["2026-05-29 09:05:00"]),
        "5min": _fire(["2026-05-29 09:05:30"]),
        "15min": _fire(["2026-05-29 10:00:00"]),
    }
    events = find_resonance(fires, "high_point")
    minutes = {e["time"] for e in events}
    assert "2026-05-29T09:05" in minutes
    ev = next(e for e in events if e["time"] == "2026-05-29T09:05")
    assert ev["score"] == 2
    assert set(ev["frameworks"]) == {"1min", "5min"}


def test_no_resonance_single_frame():
    fires = {"1min": _fire(["2026-05-29 09:05:00"])}
    assert find_resonance(fires, "high_point") == []
