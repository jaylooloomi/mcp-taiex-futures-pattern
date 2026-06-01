from mcp.server.fastmcp import FastMCP
from . import tools

mcp = FastMCP("txf-feature-analysis")


@mcp.tool()
def analyze_txf_day(date: str, timeframes: list[str], session: str = "all") -> dict:
    """Analyze a TXF trading day: feature series per timeframe + resonance."""
    return tools.analyze_txf_day(date, timeframes, session)


@mcp.tool()
def query_feature_statistics(feature: str, timeframe: str,
                             date_range: list[str], lookforward_bars: int = 10) -> dict:
    """Statistics of price moves after a feature fires."""
    return tools.query_feature_statistics(feature, timeframe, date_range, lookforward_bars)


@mcp.tool()
def compare_days(target_date: str, compare_dates: list[str], timeframe: str) -> dict:
    """Similarity score between a target day and other days."""
    return tools.compare_days(target_date, compare_dates, timeframe)


@mcp.tool()
def list_available_dates() -> list[str]:
    """List trade dates available in the local OHLCV cache."""
    return tools.list_available_dates()


def main():
    mcp.run()


if __name__ == "__main__":
    main()
