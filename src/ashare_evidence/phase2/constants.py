PHASE2_HORIZONS = (10, 20, 40)
PHASE2_PRIMARY_HORIZON = 20
PHASE2_FEATURE_VERSION = "phase2-research-v1"
PHASE2_RULE_BASELINE = "phase2-rule-baseline-v1"
PHASE2_POLICY_VERSION = "phase2-walk-forward-research-candidate-v1"
PHASE2_LABEL_DEFINITION = "forward_excess_return_ranking_10d_20d_40d"
PHASE2_WINDOW_DEFINITION = "10/20/40 交易日前瞻超额收益排序（walk-forward / research candidate）"
PHASE2_COST_DEFINITION = "双边 35 bps，含交易费与滑点占位；A 股 T+1、涨跌停、停牌约束进入研究契约。"
PHASE2_COST_MODEL = {
    "round_trip_cost_bps": 35.0,
    "t_plus_one": True,
    "price_limit": True,
    "suspension_blocking": True,
}
PHASE2_MANUAL_REVIEW_NOTE = "人工研究助手当前仅作为补充解释，不参与训练、评分或自动晋级。"


def phase2_target_horizon_label(horizon: int = PHASE2_PRIMARY_HORIZON) -> str:
    return f"forward_excess_return_{horizon}d"


def phase2_benchmark_definition(*, market_proxy: bool, sector_proxy: bool) -> str:
    if market_proxy and sector_proxy:
        return "phase2_equal_weight_market_proxy + primary_sector_equal_weight_proxy"
    if market_proxy:
        return "phase2_equal_weight_market_proxy"
    return "phase2_single_symbol_absolute_return_fallback"
