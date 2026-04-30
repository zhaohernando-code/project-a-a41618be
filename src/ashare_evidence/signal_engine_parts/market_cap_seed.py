"""Market cap seed data for watchlist stocks when API is unavailable.

Values are in CNY (total market cap). Updated periodically via akshare.
Format: {symbol: total_market_cap_in_yuan}
"""

SEED_MARKET_CAP: dict[str, float] = {
    "002028.SZ": 152006791127.14,  # 思源电气 ~1520亿
    "002270.SZ": 17000000000.0,     # 华明装备 ~170亿 (estimated)
    "600522.SH": 75000000000.0,     # 中天科技 ~750亿 (estimated)
    "600589.SH": 5000000000.0,      # 大位科技 ~50亿 (estimated)
}
