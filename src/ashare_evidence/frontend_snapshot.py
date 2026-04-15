from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import tempfile
from typing import Any

from ashare_evidence.dashboard import (
    bootstrap_dashboard_demo,
    get_glossary_entries,
    get_stock_dashboard,
    list_candidate_recommendations,
)
from ashare_evidence.dashboard_demo import WATCHLIST_SYMBOLS
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.operations import build_operations_dashboard
from ashare_evidence.watchlist import list_watchlist_entries


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def build_frontend_snapshot(database_url: str | None = None) -> dict[str, Any]:
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    resolved_database_url = database_url
    if resolved_database_url is None:
        temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(temp_dir.name) / "frontend-snapshot.db"
        resolved_database_url = f"sqlite:///{database_path}"

    try:
        init_database(resolved_database_url)
        with session_scope(resolved_database_url) as session:
            bootstrap = bootstrap_dashboard_demo(session)

        with session_scope(resolved_database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)

        with session_scope(resolved_database_url) as session:
            watchlist = list_watchlist_entries(session)

        stock_dashboards: dict[str, dict[str, Any]] = {}
        operations_dashboards: dict[str, dict[str, Any]] = {}
        for symbol in WATCHLIST_SYMBOLS:
            with session_scope(resolved_database_url) as session:
                stock_dashboards[symbol] = get_stock_dashboard(session, symbol)
            with session_scope(resolved_database_url) as session:
                operations_dashboards[symbol] = build_operations_dashboard(session, sample_symbol=symbol)

        return _json_ready(
            {
            "generated_at": datetime.now().astimezone(),
            "bootstrap": bootstrap,
            "watchlist": watchlist,
            "candidates": candidates,
            "glossary": get_glossary_entries(),
            "stock_dashboards": stock_dashboards,
            "operations_dashboards": operations_dashboards,
            }
        )
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


def export_frontend_snapshot(output_path: str, database_url: str | None = None) -> str:
    snapshot = build_frontend_snapshot(database_url)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return str(destination)
