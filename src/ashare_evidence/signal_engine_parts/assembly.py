from __future__ import annotations

from datetime import datetime, timedelta

from ashare_evidence.phase2 import (
    PHASE2_FEATURE_VERSION,
    PHASE2_LABEL_DEFINITION,
    PHASE2_POLICY_VERSION,
    PHASE2_RULE_BASELINE,
)
from ashare_evidence.signal_engine_parts.base import (
    HORIZONS,
    PRIMARY_HORIZON,
    TRANSACTION_COST_BPS,
    VALIDATION_PENDING,
    SignalArtifacts,
    with_internal_lineage,
)
from ashare_evidence.signal_engine_parts.factors import (
    active_sector_codes,
    compute_fundamental_factor,
    compute_manual_review_layer,
    compute_news_factor,
    compute_price_factor,
    primary_sector_membership,
)
from ashare_evidence.signal_engine_parts.factors_extended import (
    compute_liquidity_factor,
    compute_reversal_factor,
    compute_size_factor,
)
from ashare_evidence.signal_engine_parts.recommendation import (
    _fusion_state,
    build_recommendation,
    compute_model_results,
)


def build_signal_artifacts(
    *,
    symbol: str,
    stock_name: str,
    market_bars: list[dict[str, object]],
    news_items: list[dict[str, object]],
    news_links: list[dict[str, object]],
    sector_memberships: list[dict[str, object]],
    financial_snapshot: dict[str, object] | None = None,
    financial_trends: dict[str, object] | None = None,
    financial_llm: dict[str, object] | None = None,
    generated_at: datetime,
) -> SignalArtifacts:
    minimum_bars = max(HORIZONS)
    if len(market_bars) < minimum_bars:
        raise ValueError(f"At least {minimum_bars} daily bars are required to build the signal bundle.")

    market_bars = sorted(market_bars, key=lambda item: item["observed_at"])
    as_of_data_time = market_bars[-1]["observed_at"]
    sector_codes = active_sector_codes(sector_memberships, as_of_data_time)
    primary_membership = primary_sector_membership(sector_memberships, as_of_data_time)

    price_factor = compute_price_factor(market_bars)
    news_factor = compute_news_factor(
        symbol=symbol,
        as_of_data_time=as_of_data_time,
        news_items=news_items,
        news_links=news_links,
        sector_codes=sector_codes,
    )
    fundamental_factor = compute_fundamental_factor(
        financial_snapshot=financial_snapshot,
        financial_trends=financial_trends,
        financial_llm=financial_llm,
    )
    manual_review_layer = compute_manual_review_layer(price_factor, news_factor)
    size_factor = compute_size_factor(market_bars)
    reversal_factor = compute_reversal_factor(market_bars)
    liquidity_factor = compute_liquidity_factor(market_bars)
    fusion_state = _fusion_state(
        as_of_data_time=as_of_data_time,
        generated_at=generated_at,
        price_factor=price_factor,
        news_factor=news_factor,
        fundamental_factor=fundamental_factor,
        size_factor=size_factor,
        reversal_factor=reversal_factor,
        liquidity_factor=liquidity_factor,
    )
    model_results = compute_model_results(
        symbol=symbol,
        as_of_data_time=as_of_data_time,
        price_factor=price_factor,
        news_factor=news_factor,
        manual_review_layer=manual_review_layer,
        fusion_state=fusion_state,
    )
    recommendation, fusion_snapshot = build_recommendation(
        symbol=symbol,
        stock_name=stock_name,
        as_of_data_time=as_of_data_time,
        generated_at=generated_at,
        price_factor=price_factor,
        news_factor=news_factor,
        fundamental_factor=fundamental_factor,
        size_factor=size_factor,
        reversal_factor=reversal_factor,
        liquidity_factor=liquidity_factor,
        manual_review_layer=manual_review_layer,
        model_results=model_results,
        fusion_state=fusion_state,
        sector_proxy_available=primary_membership is not None,
    )
    price_snapshot = with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-price-baseline-v1",
            "stock_symbol": symbol,
            "feature_set_name": "price_baseline_factor",
            "feature_set_version": PHASE2_FEATURE_VERSION,
            "as_of": as_of_data_time,
            "window_start": price_factor["window_start"],
            "window_end": price_factor["window_end"],
            "feature_values": price_factor["feature_values"],
            "upstream_refs": [{"type": "market_bar", "key": item["bar_key"]} for item in market_bars[-5:]],
        },
        source_uri=f"pipeline://signal-engine/price-baseline/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    news_snapshot = with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-news-event-v1",
            "stock_symbol": symbol,
            "feature_set_name": "news_event_factor",
            "feature_set_version": PHASE2_FEATURE_VERSION,
            "as_of": as_of_data_time,
            "window_start": news_factor["window_start"],
            "window_end": news_factor["window_end"],
            "feature_values": news_factor["feature_values"],
            "upstream_refs": [
                {"type": "news_item", "key": item["news_key"]}
                for item in sorted(news_items, key=lambda value: value["published_at"], reverse=True)[:4]
            ],
        },
        source_uri=f"pipeline://signal-engine/news-event/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    manual_review_snapshot = with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-manual-review-layer-v1",
            "stock_symbol": symbol,
            "feature_set_name": "manual_review_placeholder_layer",
            "feature_set_version": PHASE2_FEATURE_VERSION,
            "as_of": as_of_data_time,
            "window_start": news_factor["window_start"],
            "window_end": as_of_data_time,
            "feature_values": manual_review_layer["feature_values"],
            "upstream_refs": [
                {"type": "feature_snapshot", "key": price_snapshot["snapshot_key"]},
                {"type": "feature_snapshot", "key": news_snapshot["snapshot_key"]},
            ],
        },
        source_uri=f"pipeline://signal-engine/manual-review-layer/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    size_snapshot = with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-size-factor-v1",
            "stock_symbol": symbol,
            "feature_set_name": "size_factor",
            "feature_set_version": PHASE2_FEATURE_VERSION,
            "as_of": as_of_data_time,
            "window_start": market_bars[0]["observed_at"],
            "window_end": market_bars[-1]["observed_at"],
            "feature_values": size_factor["feature_values"],
            "upstream_refs": [{"type": "market_bar", "key": item["bar_key"]} for item in market_bars[-1:]],
        },
        source_uri=f"pipeline://signal-engine/size-factor/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    reversal_snapshot = with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-reversal-factor-v1",
            "stock_symbol": symbol,
            "feature_set_name": "reversal_factor",
            "feature_set_version": PHASE2_FEATURE_VERSION,
            "as_of": as_of_data_time,
            "window_start": reversal_factor["window_start"],
            "window_end": reversal_factor["window_end"],
            "feature_values": reversal_factor["feature_values"],
            "upstream_refs": [{"type": "market_bar", "key": item["bar_key"]} for item in market_bars[-6:]],
        },
        source_uri=f"pipeline://signal-engine/reversal-factor/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    liquidity_snapshot = with_internal_lineage(
        {
            "snapshot_key": f"feature-{symbol}-{as_of_data_time:%Y%m%d}-liquidity-factor-v1",
            "stock_symbol": symbol,
            "feature_set_name": "liquidity_factor",
            "feature_set_version": PHASE2_FEATURE_VERSION,
            "as_of": as_of_data_time,
            "window_start": liquidity_factor["window_start"],
            "window_end": liquidity_factor["window_end"],
            "feature_values": liquidity_factor["feature_values"],
            "upstream_refs": [{"type": "market_bar", "key": item["bar_key"]} for item in market_bars[-1:]],
        },
        source_uri=f"pipeline://signal-engine/liquidity-factor/{symbol}/{as_of_data_time:%Y%m%d}",
    )
    model_registry = with_internal_lineage(
        {
            "name": "wave_advice_fusion",
            "family": "hybrid_score_fusion",
            "description": "Phase 2 规则基线：融合价格趋势、确认项、新闻事件、市值因子、反转因子与流动性因子，手动研究层只保留为解释层。",
            "registry_payload": {
                "baseline": f"price_baseline_factor:{PHASE2_FEATURE_VERSION}",
                "news_factor": f"news_event_factor:{PHASE2_FEATURE_VERSION}",
                "fundamental_factor": f"fundamental_factor:{PHASE2_FEATURE_VERSION}",
                "size_factor": f"size_factor:{PHASE2_FEATURE_VERSION}",
                "reversal_factor": f"reversal_factor:{PHASE2_FEATURE_VERSION}",
                "liquidity_factor": f"liquidity_factor:{PHASE2_FEATURE_VERSION}",
                "manual_review_layer": "manual_review_artifact:v1",
                "policy_version": PHASE2_POLICY_VERSION,
            },
        },
        source_uri="model://registry/wave_advice_fusion",
    )
    model_version = with_internal_lineage(
        {
            "version": f"{as_of_data_time:%Y.%m.%d}-phase2",
            "validation_scheme": PHASE2_LABEL_DEFINITION,
            "training_window_start": datetime(2022, 1, 1, tzinfo=as_of_data_time.tzinfo),
            "training_window_end": datetime(2026, 3, 31, tzinfo=as_of_data_time.tzinfo),
            "artifact_uri": f"s3://artifacts/models/wave_advice_fusion/{as_of_data_time:%Y.%m.%d}-phase2",
            "config_payload": {
                "horizon_days": list(HORIZONS),
                "universe": "watchlist",
                "rule_baseline": PHASE2_RULE_BASELINE,
                "weights": {"price_baseline": 0.35, "news_event": 0.20, "fundamental": 0.15,
                           "size_factor": 0.10, "reversal": 0.10, "liquidity": 0.10},
                "manual_review_layer": "artifact_backed_only_not_scored",
                "degrade_policy": PHASE2_POLICY_VERSION,
            },
        },
        source_uri=f"model://version/wave_advice_fusion/{as_of_data_time:%Y.%m.%d}-phase2",
    )
    prompt_version = with_internal_lineage(
        {
            "name": "balanced_advice_prompt",
            "version": "phase2-v1",
            "risk_disclaimer": "仅当结构化证据充足且冲突可控时输出方向性建议，否则自动降级为风险提示。",
            "prompt_payload": {
                "system_prompt": "你是一名审慎的 A 股波段研究助手，必须先引用结构化证据，再给出方向和失效条件。",
                "user_template": "结合价格趋势、确认项与新闻事件因子，为股票输出 Phase 2 观察建议。",
            },
        },
        source_uri="prompt://balanced_advice_prompt/phase2-v1",
        license_tag="internal-prompt",
    )
    model_run = with_internal_lineage(
        {
            "run_key": f"run-wave-advice-{as_of_data_time:%Y%m%d}-phase2-close",
            "started_at": as_of_data_time + timedelta(minutes=10),
            "finished_at": as_of_data_time + timedelta(minutes=25),
            "run_status": "completed",
            "target_scope": "watchlist",
            "metrics_payload": {
                "validation_scheme": PHASE2_LABEL_DEFINITION,
                "primary_horizon_days": PRIMARY_HORIZON,
                "transaction_cost_bps": TRANSACTION_COST_BPS,
                "validation_status": VALIDATION_PENDING["status"],
                "validation_note": VALIDATION_PENDING["note"],
            },
            "input_refs": [
                {"type": "feature_snapshot", "key": price_snapshot["snapshot_key"]},
                {"type": "feature_snapshot", "key": news_snapshot["snapshot_key"]},
                {"type": "feature_snapshot", "key": manual_review_snapshot["snapshot_key"]},
                {"type": "feature_snapshot", "key": size_snapshot["snapshot_key"]},
                {"type": "feature_snapshot", "key": reversal_snapshot["snapshot_key"]},
                {"type": "feature_snapshot", "key": liquidity_snapshot["snapshot_key"]},
            ],
        },
        source_uri=f"model://run/wave_advice_fusion/run-wave-advice-{as_of_data_time:%Y%m%d}-phase2-close",
    )
    primary_result = next(result for result in model_results if result["forecast_horizon_days"] == PRIMARY_HORIZON)
    evidence = [
        with_internal_lineage(
            {
                "evidence_type": "model_result",
                "reference_key": primary_result["result_key"],
                "role": "primary_driver",
                "rank": 1,
                "evidence_label": f"{PRIMARY_HORIZON} 日融合预测",
                "snippet": "价格趋势、确认项与新闻事件融合后形成当前 Phase 2 判断。",
                "reference_payload": {"component": "fusion_primary"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/model-result",
        ),
        with_internal_lineage(
            {
                "evidence_type": "feature_snapshot",
                "reference_key": price_snapshot["snapshot_key"],
                "role": "primary_driver",
                "rank": 2,
                "evidence_label": "价格基线因子",
                "snippet": "近 10/20/40 日趋势、确认项和风险压力共同决定价格基线。",
                "reference_payload": {"component": "price_baseline"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/price",
        ),
        with_internal_lineage(
            {
                "evidence_type": "feature_snapshot",
                "reference_key": news_snapshot["snapshot_key"],
                "role": "primary_driver",
                "rank": 3,
                "evidence_label": "新闻事件因子",
                "snippet": "正向事件、冲突度和时效性共同决定新闻层是否加分。",
                "reference_payload": {"component": "news_event"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/news",
        ),
        with_internal_lineage(
            {
                "evidence_type": "feature_snapshot",
                "reference_key": manual_review_snapshot["snapshot_key"],
                "role": "supporting_context",
                "rank": 4,
                "evidence_label": "人工研究层",
                "snippet": "手动研究链路保留为独立层，不参与核心评分。",
                "reference_payload": {"component": "manual_review_layer"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/manual-review",
        ),
        with_internal_lineage(
            {
                "evidence_type": "feature_snapshot",
                "reference_key": fusion_snapshot["snapshot_key"],
                "role": "supporting_context",
                "rank": 5,
                "evidence_label": "融合评分卡",
                "snippet": "展示当前权重、冲突惩罚和降级状态。",
                "reference_payload": {"component": "fusion_scorecard"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/fusion",
        ),
        with_internal_lineage(
            {
                "evidence_type": "market_bar",
                "reference_key": price_factor["latest_bar_key"],
                "role": "supporting_context",
                "rank": 6,
                "evidence_label": "最新日线行情",
                "snippet": "最新价格与量能状态作为波段建议的直接上下文。",
                "reference_payload": {"component": "market_context"},
            },
            source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/market",
        ),
    ]
    if news_factor["primary_news_key"] is not None:
        evidence.append(
            with_internal_lineage(
                {
                    "evidence_type": "news_item",
                    "reference_key": news_factor["primary_news_key"],
                    "role": "supporting_context",
                    "rank": 7,
                    "evidence_label": "核心新闻证据",
                    "snippet": "最新高相关事件用于解释新闻因子为何转强。",
                    "reference_payload": {"component": "primary_news_event"},
                },
                source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/primary-news",
            )
        )
    if primary_membership is not None:
        evidence.append(
            with_internal_lineage(
                {
                    "evidence_type": "sector_membership",
                    "reference_key": primary_membership["membership_key"],
                    "role": "supporting_context",
                    "rank": 8,
                    "evidence_label": "主行业归属",
                    "snippet": "行业映射用于板块新闻与风险归因。",
                    "reference_payload": {"component": "primary_sector"},
                },
                source_uri=f"pipeline://signal-engine/evidence/{symbol}/{as_of_data_time:%Y%m%d}/sector",
            )
        )
    return SignalArtifacts(
        feature_snapshots=[price_snapshot, news_snapshot, manual_review_snapshot, size_snapshot,
                           reversal_snapshot, liquidity_snapshot, fusion_snapshot],
        model_registry=model_registry,
        model_version=model_version,
        prompt_version=prompt_version,
        model_run=model_run,
        model_results=model_results,
        recommendation=recommendation,
        recommendation_evidence=evidence,
    )


__all__ = ["build_signal_artifacts"]
