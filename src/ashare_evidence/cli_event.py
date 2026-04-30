from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.event_analyzer import list_event_analyses, run_event_analysis
from ashare_evidence.event_triggers import check_triggers
from ashare_evidence.research_artifact_store import artifact_root_from_database_url
from ashare_evidence.watchlist import active_watchlist_symbols


def add_event_check_parser(subparsers: Any) -> None:
    parser = subparsers.add_parser(
        "event-check",
        help="Check event triggers and optionally run event-driven analysis for a symbol or the full watchlist.",
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--symbol", default=None, help="Check a single symbol; omit to check entire watchlist.")
    parser.add_argument("--run", action="store_true", help="Execute analysis if triggers fire (default: dry-run).")


def handle_event_check(session: Session, *, symbol: str | None, run: bool, database_url: str | None = None) -> list[dict[str, Any]]:
    symbols = [symbol] if symbol else active_watchlist_symbols(session)
    bind = session.get_bind()
    artifact_root = str(
        artifact_root_from_database_url(bind.url.render_as_string(hide_password=False)) if bind else ""
    )
    collected: list[dict[str, Any]] = []
    for sym in symbols:
        existing = list_event_analyses(sym, artifact_root=artifact_root, limit=20)
        triggers = check_triggers(session, symbol=sym, artifact_root=artifact_root, existing_analyses=existing)
        entry: dict[str, Any] = {
            "symbol": sym,
            "trigger_count": len(triggers),
            "triggers": [{"type": t.trigger_type, "detail": t.detail} for t in triggers],
        }
        if run and triggers:
            results = []
            for t in triggers:
                try:
                    r = run_event_analysis(session, symbol=sym, trigger=t, artifact_root=artifact_root)
                    results.append({
                        "type": t.trigger_type,
                        "status": r.get("status"),
                        "direction": r.get("independent_direction"),
                    })
                except Exception as exc:
                    results.append({"type": t.trigger_type, "status": "error", "error": str(exc)})
            entry["results"] = results
        collected.append(entry)
    return collected


def run_refresh_event_checks(session: Session, symbols: list[str]) -> list[dict[str, Any]]:
    bind = session.get_bind()
    artifact_root = str(
        artifact_root_from_database_url(bind.url.render_as_string(hide_password=False)) if bind else ""
    )
    event_results: list[dict[str, Any]] = []
    for sym in symbols:
        try:
            existing = list_event_analyses(sym, artifact_root=artifact_root, limit=20)
            triggers = check_triggers(session, symbol=sym, artifact_root=artifact_root, existing_analyses=existing)
            for trigger in triggers:
                try:
                    result = run_event_analysis(session, symbol=sym, trigger=trigger, artifact_root=artifact_root)
                    event_results.append(result)
                except Exception:
                    pass
        except Exception:
            pass
    return event_results
