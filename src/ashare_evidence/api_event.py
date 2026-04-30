from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ashare_evidence.event_analyzer import list_event_analyses, read_event_analysis
from ashare_evidence.research_artifact_store import artifact_root_from_database_url


def register_event_routes(app: Any, get_session: Any, require_stock_access: Any, _stock_access_context: Any) -> None:
    @app.get("/stocks/{symbol}/event-analyses")
    def stock_event_analyses(
        symbol: str,
        limit: int = Query(default=5, ge=1, le=30),
        _access: Any = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> list[dict[str, object]]:
        bind = session.get_bind()
        artifact_root = artifact_root_from_database_url(
            bind.url.render_as_string(hide_password=False) if bind else ""
        )
        items = list_event_analyses(symbol, artifact_root=str(artifact_root), limit=limit)
        return [dict(item) for item in items]

    @app.get("/stocks/{symbol}/event-analyses/{filename}")
    def stock_event_analysis_detail(
        symbol: str,
        filename: str,
        _access: Any = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        bind = session.get_bind()
        artifact_root = artifact_root_from_database_url(
            bind.url.render_as_string(hide_password=False) if bind else ""
        )
        artifact = read_event_analysis(symbol, filename, artifact_root=str(artifact_root))
        if artifact is None:
            raise HTTPException(status_code=404, detail=f"Event analysis {filename} not found for {symbol}")
        return dict(artifact)
