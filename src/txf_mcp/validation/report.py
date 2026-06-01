def format_stats(stats: dict) -> str:
    """Render backtest stats dict into a short human-readable report."""
    if stats.get("sample_size", 0) == 0:
        return f"{stats.get('feature', 'feature')}: no samples"
    return (
        f"{stats.get('feature', 'feature')} "
        f"(n={stats['sample_size']}, +{stats['lookforward_bars']} bars): "
        f"up={stats['up_probability']:.0%}, "
        f"avg={stats['avg_return_pct']:+.2f}%, "
        f"max={stats['max_return_pct']:+.2f}%, "
        f"min={stats['max_drawdown_pct']:+.2f}%"
    )
