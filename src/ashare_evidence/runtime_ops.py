from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.db import utcnow
from ashare_evidence.intraday_market import get_intraday_market_status, sync_intraday_market
from ashare_evidence.market_clock import is_market_session_open
from ashare_evidence.models import SimulationSession
from ashare_evidence.simulation import advance_running_simulation_session
from ashare_evidence.watchlist import active_watchlist_symbols


def run_operations_tick(
    session: Session,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or utcnow()
    if not is_market_session_open(current_time):
        session.commit()
        return {
            "ran": False,
            "reason": "market_closed",
            "timestamp": current_time,
        }

    symbols = active_watchlist_symbols(session)
    if not symbols:
        session.commit()
        return {
            "ran": False,
            "reason": "no_active_watchlist_symbols",
            "timestamp": current_time,
        }

    intraday_status = get_intraday_market_status(session, symbols=symbols, now=current_time)
    intraday_refreshed = False
    if intraday_status.get("stale"):
        intraday_status = sync_intraday_market(session, symbols, now=current_time)
        intraday_refreshed = True

    simulation_workspace = None
    advanced_count = 0
    latest_workspace = None
    for owner_login in session.scalars(
        select(SimulationSession.owner_login)
        .where(SimulationSession.status == "running")
        .distinct()
        .order_by(SimulationSession.owner_login.asc())
    ).all():
        workspace = advance_running_simulation_session(session, owner_login=owner_login)
        if workspace is not None:
            advanced_count += 1
            latest_workspace = workspace
    simulation_workspace = latest_workspace
    session.commit()
    return {
        "ran": True,
        "timestamp": current_time,
        "symbols": symbols,
        "intraday_refreshed": intraday_refreshed,
        "latest_market_data_at": intraday_status.get("latest_market_data_at"),
        "simulation_advanced": simulation_workspace is not None,
        "simulation_advanced_count": advanced_count,
        "simulation_session_key": None if simulation_workspace is None else simulation_workspace["session"]["session_key"],
        "simulation_current_step": None if simulation_workspace is None else simulation_workspace["session"]["current_step"],
        "simulation_last_data_time": None if simulation_workspace is None else simulation_workspace["session"]["last_data_time"],
    }
