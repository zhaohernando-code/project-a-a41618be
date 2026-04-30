from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from ashare_evidence.contract_status import STATUS_RESEARCH_CANDIDATE
from ashare_evidence.models import PaperOrder, PaperPortfolio, Recommendation
from ashare_evidence.phase2.constants import PHASE2_COST_DEFINITION, PHASE2_COST_MODEL, PHASE2_FEATURE_VERSION, PHASE2_POLICY_VERSION, PHASE2_RULE_BASELINE
from ashare_evidence.phase2.data import portfolio_price_history
from ashare_evidence.phase2.phase5_contract import (
    PHASE5_MARKET_REFERENCE_BENCHMARK,
    PHASE5_PRIMARY_RESEARCH_BENCHMARK,
    phase5_benchmark_context,
    phase5_benchmark_definition,
    phase5_research_contract_context,
)
from ashare_evidence.research_artifacts import BacktestArtifactView, ResearchArtifactManifestView


def build_portfolio_backtest_artifacts(
    session: Session,
    *,
    active_symbols: set[str],
    market_proxy: dict[date, float],
    market_proxy_context: dict[str, object] | None = None,
) -> tuple[ResearchArtifactManifestView, list[BacktestArtifactView]]:
    from ashare_evidence.operations import _portfolio_payload

    price_history, stock_names, timeline_points = portfolio_price_history(session, active_symbols)
    portfolios = session.scalars(
        select(PaperPortfolio)
        .options(
            selectinload(PaperPortfolio.orders).selectinload(PaperOrder.fills),
            selectinload(PaperPortfolio.orders).joinedload(PaperOrder.stock),
            selectinload(PaperPortfolio.orders).joinedload(PaperOrder.portfolio),
            selectinload(PaperPortfolio.orders).joinedload(PaperOrder.recommendation).joinedload(Recommendation.stock),
        )
        .order_by(PaperPortfolio.mode.asc(), PaperPortfolio.name.asc())
    ).all()
    generated_at = datetime.now().astimezone()
    manifest = ResearchArtifactManifestView(
        artifact_id="rolling-validation:phase2-portfolio-backtests",
        artifact_type="rolling_validation",
        created_at=generated_at,
        generated_at=generated_at,
        experiment_id="experiment:phase2:portfolio-backtests",
        experiment_version=PHASE2_RULE_BASELINE,
        model_version=PHASE2_RULE_BASELINE,
        policy_version=PHASE2_POLICY_VERSION,
        data_snapshot_id=f"phase2-portfolio:{generated_at:%Y%m%d%H%M}",
        data_snapshot_ids=[],
        universe_definition="active_watchlist_paper_portfolios",
        universe_rule="manual_and_auto_portfolio_tracks",
        availability_rule="orders_and_fills_only_use_observed_daily_closes",
        feature_set_version=PHASE2_FEATURE_VERSION,
        feature_version=PHASE2_FEATURE_VERSION,
        label_definition="portfolio_total_and_excess_return",
        benchmark_definition=phase5_benchmark_definition(market_proxy=bool(market_proxy), sector_proxy=False),
        benchmark_context={
            **phase5_benchmark_context(market_proxy=bool(market_proxy), sector_proxy=False),
            **(market_proxy_context or {}),
            "symbol_scope": sorted(active_symbols),
        },
        research_contract=phase5_research_contract_context(),
        cost_definition=PHASE2_COST_DEFINITION,
        cost_model=PHASE2_COST_DEFINITION,
        rebalance_definition="paper_order_timeline",
        rolling_windows=[],
        leakage_checks=[{"name": "paper_orders_only", "status": "pass"}],
        split_plan=[],
    )

    artifacts: list[BacktestArtifactView] = []
    for portfolio in portfolios:
        payload = _portfolio_payload(
            portfolio,
            active_symbols=active_symbols,
            stock_names=stock_names,
            price_history=price_history,
            timeline_points=timeline_points,
            benchmark_close_map=market_proxy,
            recommendation_hit_rate=0.0,
            market_data_timeframe="1d",
            artifact_root=None,
        )
        performance = payload.get("performance") or {}
        nav_history = payload.get("nav_history") or []
        annualized_return = float(performance.get("total_return") or 0.0)
        annualized_excess_return = float(performance.get("excess_return") or 0.0)
        max_drawdown = float(performance.get("max_drawdown") or 0.0)
        turnover = round(min(float(payload.get("order_count") or 0) / 12.0, 1.0), 6)
        artifacts.append(
            BacktestArtifactView(
                artifact_id=f"portfolio-backtest:{portfolio.portfolio_key}",
                manifest_id=manifest.artifact_id,
                status=STATUS_RESEARCH_CANDIDATE,
                status_note="组合回测已切到真实 daily 价格与 proxy benchmark；模型轨道的 simulation baseline 已升级为 constrained TopK，但仍处于 research candidate。",
                strategy_definition=str(payload.get("strategy_summary") or portfolio.name),
                rebalance_rule="paper_orders_as_executed",
                position_limit_definition="manual=35% / auto=20%",
                position_constraints={"max_single_weight": 0.35 if portfolio.mode == "manual" else 0.20},
                execution_assumptions="daily_close_marking + paper_fills + T+1 + price_limit_checks",
                benchmark_definition=manifest.benchmark_definition,
                benchmark={"definition": manifest.benchmark_definition},
                cost_definition=PHASE2_COST_DEFINITION,
                cost_model=PHASE2_COST_MODEL,
                equity_curve=nav_history,
                drawdown_stats={"max_drawdown": round(max_drawdown, 6), "current_drawdown": performance.get("current_drawdown")},
                risk_stats={"active_position_count": payload.get("active_position_count"), "rule_pass_rate": payload.get("rule_pass_rate")},
                turnover_stats={"turnover": turnover},
                annualized_return=round(annualized_return, 6),
                annualized_excess_return=round(annualized_excess_return, 6),
                max_drawdown=round(max_drawdown, 6),
                sharpe_like_ratio=round(annualized_excess_return / max(abs(max_drawdown), 0.01), 6),
                turnover=turnover,
                win_rate_definition="positive_excess_nav_point_ratio_against_phase2_proxy",
                win_rate=round(sum(1 for point in nav_history if point["nav"] >= point["benchmark_nav"]) / max(len(nav_history), 1), 6),
                capacity_note="paper-trade track only; auto execution approval remains limited to simulation track and does not extend to real trading.",
                nav_series_ref=f"phase2-nav:{portfolio.portfolio_key}",
                drawdown_series_ref=f"phase2-drawdown:{portfolio.portfolio_key}",
                trade_log_ref=f"phase2-trades:{portfolio.portfolio_key}",
                exposure_summary={"invested_ratio": payload.get("invested_ratio"), "active_position_count": payload.get("active_position_count")},
                stress_period_summary=[{"period": "phase2_fixture_window", "max_drawdown": round(max_drawdown, 6), "excess_return": round(annualized_excess_return, 6)}],
            )
        )
    return manifest, artifacts
