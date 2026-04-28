from __future__ import annotations


def _infer_market_suffix(ticker: str) -> str:
    if ticker[0] in {"5", "6", "9"}:
        return "SH"
    if ticker[0] in {"0", "2", "3"}:
        return "SZ"
    if ticker[0] in {"4", "8"}:
        return "BJ"
    raise ValueError("暂不支持该证券代码。请输入 6 位 A 股代码。")


def normalize_symbol(symbol: str) -> str:
    raw = symbol.strip().upper().replace(" ", "")
    if not raw:
        raise ValueError("请输入股票代码。")
    if raw.startswith(("SH", "SZ", "BJ")) and len(raw) == 8 and raw[2:].isdigit():
        raw = f"{raw[2:]}.{raw[:2]}"
    if "." not in raw:
        if not raw.isdigit() or len(raw) != 6:
            raise ValueError("股票代码格式无效，请输入如 600519 或 300750.SZ。")
        return f"{raw}.{_infer_market_suffix(raw)}"
    ticker, _, suffix = raw.partition(".")
    if not ticker.isdigit() or len(ticker) != 6:
        raise ValueError("股票代码格式无效，请输入 6 位数字代码。")
    if suffix not in {"SH", "SZ", "BJ"}:
        raise ValueError("股票代码后缀仅支持 .SH / .SZ / .BJ。")
    return f"{ticker}.{suffix}"
