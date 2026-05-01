from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ashare_evidence.cli_event import add_event_check_parser, handle_event_check, run_refresh_event_checks
from ashare_evidence.cli_research import add_research_parsers, handle_factor_observation, handle_weight_sweep
from ashare_evidence.dashboard import get_glossary_entries, get_stock_dashboard, list_candidate_recommendations
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.improvement_suggestions import run_improvement_suggestion_review
from ashare_evidence.intraday_market import sync_intraday_market
from ashare_evidence.operations import build_operations_dashboard
from ashare_evidence.phase2 import rebuild_phase2_research_state
from ashare_evidence.phase2.holding_policy_experiments import (
    build_phase5_holding_policy_experiment,
    build_phase5_holding_policy_experiment_artifact,
)
from ashare_evidence.phase2.holding_policy_study import (
    build_phase5_holding_policy_study,
    build_phase5_holding_policy_study_artifact,
)
from ashare_evidence.phase2.horizon_study import build_phase5_horizon_study, build_phase5_horizon_study_artifact
from ashare_evidence.phase2.producer_contract_study import (
    build_phase5_producer_contract_study,
    build_phase5_producer_contract_study_artifact,
)
from ashare_evidence.research_artifact_store import (
    artifact_root_from_database_url,
    read_phase5_holding_policy_experiment_artifact_if_exists,
    read_phase5_holding_policy_study_artifact_if_exists,
    read_phase5_horizon_study_artifact_if_exists,
    read_phase5_producer_contract_study_artifact_if_exists,
    write_phase5_holding_policy_experiment_artifact,
    write_phase5_holding_policy_study_artifact,
    write_phase5_horizon_study_artifact,
    write_phase5_producer_contract_study_artifact,
)
from ashare_evidence.services import get_latest_recommendation_summary, get_recommendation_trace
from ashare_evidence.simulation import restart_simulation_session, step_simulation_session
from ashare_evidence.watchlist import active_watchlist_symbols, refresh_watchlist_symbol


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

def _should_initialize_database(database_url: str | None) -> bool:
    if not database_url:
        return True
    if not database_url.startswith("sqlite:///") or database_url == "sqlite:///:memory:":
        return True
    return not Path(database_url.removeprefix("sqlite:///")).exists()

def _phase5_horizon_study_output(
    session,
    *,
    database_url: str | None,
    symbols: list[str] | None = None,
    include_history: bool,
    write_artifact: bool,
) -> dict[str, Any]:
    payload = build_phase5_horizon_study(
        session,
        symbols=symbols,
        include_history=include_history,
    )
    if not write_artifact:
        return payload
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(
        bind.url.render_as_string(hide_password=False) if bind else database_url
    )
    artifact = build_phase5_horizon_study_artifact(payload)
    prior_artifact = read_phase5_horizon_study_artifact_if_exists(artifact.artifact_id, root=artifact_root)
    artifact_path = write_phase5_horizon_study_artifact(artifact, root=artifact_root)
    return {
        **payload,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "path": str(artifact_path),
            "reused_existing_snapshot": prior_artifact is not None,
        },
    }

def _phase5_holding_policy_study_output(
    session,
    *,
    database_url: str | None,
    portfolio_keys: list[str] | None = None,
    write_artifact: bool,
) -> dict[str, Any]:
    payload = build_phase5_holding_policy_study(
        session,
        portfolio_keys=portfolio_keys,
    )
    if not write_artifact:
        return payload
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(
        bind.url.render_as_string(hide_password=False) if bind else database_url
    )
    artifact = build_phase5_holding_policy_study_artifact(payload)
    prior_artifact = read_phase5_holding_policy_study_artifact_if_exists(artifact.artifact_id, root=artifact_root)
    artifact_path = write_phase5_holding_policy_study_artifact(artifact, root=artifact_root)
    return {
        **payload,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "path": str(artifact_path),
            "reused_existing_snapshot": prior_artifact is not None,
        },
    }
def _phase5_holding_policy_experiment_output(
    session,
    *,
    database_url: str | None,
    experiment_id: str,
    symbols: list[str] | None = None,
    write_artifact: bool,
) -> dict[str, Any]:
    payload = build_phase5_holding_policy_experiment(
        session,
        experiment_id=experiment_id,
        symbols=symbols,
    )
    if not write_artifact:
        return payload
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(
        bind.url.render_as_string(hide_password=False) if bind else database_url
    )
    artifact = build_phase5_holding_policy_experiment_artifact(payload)
    prior_artifact = read_phase5_holding_policy_experiment_artifact_if_exists(
        artifact.artifact_id,
        root=artifact_root,
    )
    artifact_path = write_phase5_holding_policy_experiment_artifact(artifact, root=artifact_root)
    return {
        **payload,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "path": str(artifact_path),
            "reused_existing_snapshot": prior_artifact is not None,
        },
    }

def _phase5_producer_contract_study_output(
    session,
    *,
    database_url: str | None,
    symbols: list[str] | None,
    include_history: bool,
    write_artifact: bool,
) -> dict[str, Any]:
    payload = build_phase5_producer_contract_study(
        session,
        symbols=symbols,
        include_history=include_history,
    )
    if not write_artifact:
        return payload
    bind = session.get_bind()
    artifact_root = artifact_root_from_database_url(
        bind.url.render_as_string(hide_password=False) if bind else database_url
    )
    artifact = build_phase5_producer_contract_study_artifact(payload)
    prior_artifact = read_phase5_producer_contract_study_artifact_if_exists(artifact.artifact_id, root=artifact_root)
    artifact_path = write_phase5_producer_contract_study_artifact(artifact, root=artifact_root)
    return {
        **payload,
        "artifact": {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type,
            "path": str(artifact_path),
            "reused_existing_snapshot": prior_artifact is not None,
        },
    }

def _refresh_runtime_data_output(
    session,
    *,
    analysis_only: bool,
    ops_only: bool,
    skip_simulation: bool,
) -> dict[str, Any]:
    symbols = active_watchlist_symbols(session)
    run_analysis_refresh = not ops_only
    run_ops_refresh = not analysis_only
    refreshed = [refresh_watchlist_symbol(session, symbol) for symbol in symbols] if run_analysis_refresh else []
    event_results = run_refresh_event_checks(session, [item["symbol"] for item in refreshed]) if run_analysis_refresh and refreshed else []
    intraday = sync_intraday_market(session, symbols) if run_ops_refresh else None
    simulation = None
    if not skip_simulation and run_analysis_refresh:
        restart_simulation_session(session)
        simulation = step_simulation_session(session)
        if symbols:
            rebuild_phase2_research_state(
                session,
                symbols=set(symbols),
                active_symbols=set(symbols),
            )
    return {
        "analysis_refreshed": run_analysis_refresh,
        "ops_refreshed": run_ops_refresh,
        "refreshed_symbols": [item["symbol"] for item in refreshed],
        "latest_generated_at": {
            item["symbol"]: item.get("latest_generated_at")
            for item in refreshed
        },
        "intraday_market": intraday,
        "simulation_last_data_time": None if simulation is None else simulation["session"]["last_data_time"],
        "simulation_current_step": None if simulation is None else simulation["session"]["current_step"], "event_analyses_triggered": len(event_results), "event_analyses": event_results[:3] if event_results else [],
    }

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evidence-first data foundation CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser("init-db", help="Create database tables.")
    init_db.add_argument("--database-url", default=None)

    latest = subparsers.add_parser("latest", help="Show the latest recommendation for a stock.")
    latest.add_argument("--database-url", default=None)
    latest.add_argument("--symbol", default="600519.SH")

    candidates = subparsers.add_parser("candidates", help="Show ranked dashboard candidates.")
    candidates.add_argument("--database-url", default=None)
    candidates.add_argument("--limit", type=int, default=8)

    stock_dashboard = subparsers.add_parser("stock-dashboard", help="Show the user-facing dashboard payload for a stock.")
    stock_dashboard.add_argument("--database-url", default=None)
    stock_dashboard.add_argument("--symbol", default="600519.SH")

    operations = subparsers.add_parser("operations", help="Show paper trading, replay, and beta-readiness payload.")
    operations.add_argument("--database-url", default=None)
    operations.add_argument("--sample-symbol", default="600519.SH")

    horizon_study = subparsers.add_parser(
        "phase5-horizon-study",
        help="Aggregate Phase 5 candidate-horizon comparison across the active watchlist or a custom symbol scope.",
    )
    horizon_study.add_argument("--database-url", default=None)
    horizon_study.add_argument("--symbol", action="append", default=None)
    horizon_study.add_argument(
        "--include-history",
        action="store_true",
        help="Use the latest recommendation for each symbol + as-of day instead of only the current latest recommendation.",
    )
    horizon_study.add_argument(
        "--write-artifact",
        action="store_true",
        help="Persist the current Phase 5 horizon-study snapshot under the database-linked artifacts root.",
    )

    holding_policy_study = subparsers.add_parser(
        "phase5-holding-policy-study",
        help="Aggregate Phase 5 simulation holding-policy turnover, cost, and stability evidence across auto-model portfolios.",
    )
    holding_policy_study.add_argument("--database-url", default=None)
    holding_policy_study.add_argument("--portfolio-key", action="append", default=None)
    holding_policy_study.add_argument(
        "--write-artifact",
        action="store_true",
        help="Persist the current Phase 5 holding-policy study snapshot under the database-linked artifacts root.",
    )

    holding_policy_experiment = subparsers.add_parser(
        "phase5-holding-policy-experiment",
        help="Replay a Phase 5 holding-policy redesign experiment across recommendation history and daily closes.",
    )
    holding_policy_experiment.add_argument("--database-url", default=None)
    holding_policy_experiment.add_argument("--experiment-id", required=True)
    holding_policy_experiment.add_argument("--symbol", action="append", default=None)
    holding_policy_experiment.add_argument(
        "--write-artifact",
        action="store_true",
        help="Persist the current Phase 5 holding-policy experiment snapshot under the database-linked artifacts root.",
    )

    producer_contract_study = subparsers.add_parser(
        "phase5-producer-contract-study",
        help="Compare narrow Phase 5 producer-contract alternatives for zero-news-evidence recommendations.",
    )
    producer_contract_study.add_argument("--database-url", default=None)
    producer_contract_study.add_argument("--symbol", action="append", default=None)
    producer_contract_study.add_argument(
        "--latest-only",
        action="store_true",
        help="Use only the latest preferred recommendation per symbol instead of the full preferred history.",
    )
    producer_contract_study.add_argument(
        "--write-artifact",
        action="store_true",
        help="Persist the current Phase 5 producer-contract study snapshot under the database-linked artifacts root.",
    )

    trace = subparsers.add_parser("trace", help="Show a full evidence trace for a recommendation ID.")
    trace.add_argument("--database-url", default=None)
    trace.add_argument("--recommendation-id", type=int, required=True)

    glossary = subparsers.add_parser("glossary", help="Show the dashboard glossary entries.")
    glossary.add_argument("--database-url", default=None)
    add_event_check_parser(subparsers)
    add_research_parsers(subparsers)

    refresh_runtime = subparsers.add_parser(
        "refresh-runtime-data",
        help="Refresh analysis and/or ops intraday market data for the current watchlist.",
    )
    refresh_runtime.add_argument("--database-url", default=None)
    refresh_runtime.add_argument("--analysis-only", action="store_true")
    refresh_runtime.add_argument("--ops-only", action="store_true")
    refresh_runtime.add_argument("--skip-simulation", action="store_true")

    suggestion_review = subparsers.add_parser(
        "review-improvement-suggestions",
        help="Collect improvement suggestions and run the multi-model audit.",
    )
    suggestion_review.add_argument("--database-url", default=None)
    suggestion_review.add_argument("--window-days", type=int, default=7)

    phase5_daily = subparsers.add_parser(
        "phase5-daily-refresh",
        help="Run the daily Phase 5 refresh workflow: refresh runtime data, then write latest/history horizon-study snapshots.",
    )
    phase5_daily.add_argument("--database-url", default=None)
    phase5_daily.add_argument("--analysis-only", action="store_true")
    phase5_daily.add_argument("--ops-only", action="store_true")
    phase5_daily.add_argument("--skip-simulation", action="store_true")

    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "init-db":
        init_database(args.database_url)
        print("database initialized")
        return 0

    if _should_initialize_database(args.database_url):
        init_database(args.database_url)
    if args.command == "latest":
        with session_scope(args.database_url) as session:
            payload = get_latest_recommendation_summary(session, args.symbol)
        if payload is None:
            print(f"no recommendation found for {args.symbol}")
            return 1
        _print_json(payload)
        return 0
    if args.command == "candidates":
        with session_scope(args.database_url) as session:
            payload = list_candidate_recommendations(session, limit=args.limit)
        _print_json(payload)
        return 0
    if args.command == "stock-dashboard":
        with session_scope(args.database_url) as session:
            payload = get_stock_dashboard(session, args.symbol)
        _print_json(payload)
        return 0
    if args.command == "operations":
        with session_scope(args.database_url) as session:
            payload = build_operations_dashboard(session, sample_symbol=args.sample_symbol)
        _print_json(payload)
        return 0
    if args.command == "phase5-horizon-study":
        with session_scope(args.database_url) as session:
            payload = _phase5_horizon_study_output(
                session,
                database_url=args.database_url,
                symbols=args.symbol,
                include_history=args.include_history,
                write_artifact=args.write_artifact,
            )
        _print_json(payload)
        return 0
    if args.command == "phase5-holding-policy-study":
        with session_scope(args.database_url) as session:
            payload = _phase5_holding_policy_study_output(
                session,
                database_url=args.database_url,
                portfolio_keys=args.portfolio_key,
                write_artifact=args.write_artifact,
            )
        _print_json(payload)
        return 0
    if args.command == "phase5-holding-policy-experiment":
        with session_scope(args.database_url) as session:
            payload = _phase5_holding_policy_experiment_output(
                session,
                database_url=args.database_url,
                experiment_id=args.experiment_id,
                symbols=args.symbol,
                write_artifact=args.write_artifact,
            )
        _print_json(payload)
        return 0
    if args.command == "phase5-producer-contract-study":
        with session_scope(args.database_url) as session:
            payload = _phase5_producer_contract_study_output(
                session,
                database_url=args.database_url,
                symbols=args.symbol,
                include_history=not args.latest_only,
                write_artifact=args.write_artifact,
            )
        _print_json(payload)
        return 0
    if args.command == "trace":
        with session_scope(args.database_url) as session:
            payload = get_recommendation_trace(session, args.recommendation_id)
        _print_json(payload)
        return 0
    if args.command == "glossary":
        _print_json(get_glossary_entries())
        return 0

    if args.command == "event-check":
        with session_scope(args.database_url) as session:
            collected = handle_event_check(session, symbol=args.symbol, run=args.run, database_url=args.database_url)
        _print_json(collected)
        return 0

    if args.command == "factor-observation":
        with session_scope(args.database_url) as session:
            _print_json(handle_factor_observation(session, database_url=args.database_url))
        return 0

    if args.command == "weight-sweep":
        with session_scope(args.database_url) as session:
            _print_json(handle_weight_sweep(session, database_url=args.database_url))
        return 0

    if args.command == "refresh-runtime-data":
        if args.analysis_only and args.ops_only:
            parser.error("--analysis-only 和 --ops-only 不能同时传入")
        with session_scope(args.database_url) as session:
            payload = _refresh_runtime_data_output(
                session,
                analysis_only=args.analysis_only,
                ops_only=args.ops_only,
                skip_simulation=args.skip_simulation,
            )
        _print_json(payload)
        return 0

    if args.command == "review-improvement-suggestions":
        with session_scope(args.database_url) as session:
            payload = run_improvement_suggestion_review(session, window_days=args.window_days)
        _print_json(payload)
        return 0

    if args.command == "phase5-daily-refresh":
        if args.analysis_only and args.ops_only:
            parser.error("--analysis-only 和 --ops-only 不能同时传入")
        with session_scope(args.database_url) as session:
            refresh_payload = _refresh_runtime_data_output(
                session,
                analysis_only=args.analysis_only,
                ops_only=args.ops_only,
                skip_simulation=args.skip_simulation,
            )
            latest_study = _phase5_horizon_study_output(
                session,
                database_url=args.database_url,
                include_history=False,
                write_artifact=True,
            )
            history_study = _phase5_horizon_study_output(
                session,
                database_url=args.database_url,
                include_history=True,
                write_artifact=True,
            )
            holding_policy_study = _phase5_holding_policy_study_output(
                session,
                database_url=args.database_url,
                write_artifact=True,
            )
        _print_json({
            "refresh": refresh_payload,
            "phase5_horizon_studies": {
                "latest": {
                    "approval_state": latest_study["decision"]["approval_state"],
                    "candidate_frontier": latest_study["decision"]["candidate_frontier"],
                    "lagging_horizons": latest_study["decision"]["lagging_horizons"],
                    "included_record_count": latest_study["summary"]["included_record_count"],
                    "included_as_of_date_count": latest_study["summary"]["included_as_of_date_count"],
                    "artifact": latest_study.get("artifact"),
                },
                "history": {
                    "approval_state": history_study["decision"]["approval_state"],
                    "candidate_frontier": history_study["decision"]["candidate_frontier"],
                    "lagging_horizons": history_study["decision"]["lagging_horizons"],
                    "included_record_count": history_study["summary"]["included_record_count"],
                    "included_as_of_date_count": history_study["summary"]["included_as_of_date_count"],
                    "artifact": history_study.get("artifact"),
                },
            },
            "phase5_holding_policy_study": {
                "approval_state": holding_policy_study["decision"]["approval_state"],
                "included_portfolio_count": holding_policy_study["summary"]["included_portfolio_count"],
                "mean_turnover": holding_policy_study["summary"].get("mean_turnover"),
                "mean_annualized_excess_return_after_baseline_cost": holding_policy_study["cost_sensitivity"].get(
                    "mean_annualized_excess_return_after_baseline_cost"
                ),
                "gate_status": holding_policy_study["decision"].get("gate_status"),
                "governance_status": holding_policy_study["decision"].get("governance_status"),
                "governance_action": holding_policy_study["decision"].get("governance_action"),
                "redesign_status": holding_policy_study["decision"].get("redesign_status"),
                "redesign_focus_areas": list(holding_policy_study["decision"].get("redesign_focus_areas") or []),
                "redesign_triggered_signal_ids": list(
                    holding_policy_study["decision"].get("redesign_triggered_signal_ids") or []
                ),
                "redesign_primary_experiment_ids": list(
                    holding_policy_study["decision"].get("redesign_primary_experiment_ids") or []
                ),
                "failing_gate_ids": list(holding_policy_study["decision"].get("failing_gate_ids") or []),
                "artifact": holding_policy_study.get("artifact"),
            },
        })
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
