from __future__ import annotations

from collections.abc import Iterator
import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from ashare_evidence.access import BetaAccessContext, require_beta_access
from ashare_evidence.dashboard import (
    bootstrap_dashboard_demo,
    get_glossary_entries,
    get_stock_dashboard,
    list_candidate_recommendations,
)
from ashare_evidence.db import get_database_url, get_session_factory, init_database
from ashare_evidence.operations import build_operations_dashboard
from ashare_evidence.schemas import (
    CandidateListResponse,
    DashboardBootstrapResponse,
    LatestRecommendationResponse,
    OperationsDashboardResponse,
    RecommendationTraceResponse,
    StockDashboardResponse,
    WatchlistCreateRequest,
    WatchlistDeleteResponse,
    WatchlistMutationResponse,
    WatchlistResponse,
)
from ashare_evidence.services import bootstrap_demo_data, get_latest_recommendation_summary, get_recommendation_trace
from ashare_evidence.watchlist import (
    add_watchlist_symbol,
    list_watchlist_entries,
    refresh_watchlist_symbol,
    remove_watchlist_symbol,
)


def create_app(database_url: str | None = None) -> FastAPI:
    resolved_database_url = get_database_url(database_url)
    init_database(resolved_database_url)
    session_factory = get_session_factory(resolved_database_url)

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI(
        title="A-share Evidence Foundation",
        version="0.1.0",
        summary="Evidence-first market/news/model/recommendation data layer.",
    )
    cors_origins = [
        origin.strip()
        for origin in os.getenv("ASHARE_CORS_ALLOW_ORIGINS", "*").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def require_beta_write_access(access: BetaAccessContext = Depends(require_beta_access)) -> BetaAccessContext:
        if access.role == "viewer":
            raise HTTPException(status_code=403, detail="viewer key is read-only for watchlist mutations")
        return access

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "database_url": resolved_database_url}

    @app.post("/bootstrap/demo")
    def bootstrap_demo(
        symbol: str = Query(default="600519.SH"),
        _access: BetaAccessContext = Depends(require_beta_write_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return bootstrap_demo_data(session, symbol)

    @app.post("/bootstrap/dashboard-demo", response_model=DashboardBootstrapResponse)
    def bootstrap_dashboard_demo_route(
        _access: BetaAccessContext = Depends(require_beta_write_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return bootstrap_dashboard_demo(session)

    @app.get("/watchlist", response_model=WatchlistResponse)
    def watchlist(
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return list_watchlist_entries(session)

    @app.post("/watchlist", response_model=WatchlistMutationResponse)
    def watchlist_add(
        payload: WatchlistCreateRequest,
        _access: BetaAccessContext = Depends(require_beta_write_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            item = add_watchlist_symbol(session, payload.symbol, stock_name=payload.name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "item": item,
            "message": f"已将 {item['name']}（{item['symbol']}）加入自选池并完成分析。",
        }

    @app.post("/watchlist/{symbol}/refresh", response_model=WatchlistMutationResponse)
    def watchlist_refresh(
        symbol: str,
        _access: BetaAccessContext = Depends(require_beta_write_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            item = refresh_watchlist_symbol(session, symbol)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "item": item,
            "message": f"已重新分析 {item['name']}（{item['symbol']}）。",
        }

    @app.delete("/watchlist/{symbol}", response_model=WatchlistDeleteResponse)
    def watchlist_remove(
        symbol: str,
        _access: BetaAccessContext = Depends(require_beta_write_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return remove_watchlist_symbol(session, symbol)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/stocks/{symbol}/recommendations/latest", response_model=LatestRecommendationResponse)
    def latest_recommendation(
        symbol: str,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = get_latest_recommendation_summary(session, symbol)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"No recommendation found for {symbol}.")
        return payload

    @app.get("/stocks/{symbol}/dashboard", response_model=StockDashboardResponse)
    def stock_dashboard(
        symbol: str,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_stock_dashboard(session, symbol)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/dashboard/candidates", response_model=CandidateListResponse)
    def dashboard_candidates(
        limit: int = Query(default=8, ge=1, le=20),
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return list_candidate_recommendations(session, limit=limit)

    @app.get("/dashboard/glossary")
    def dashboard_glossary(_access: BetaAccessContext = Depends(require_beta_access)) -> list[dict[str, str]]:
        return get_glossary_entries()

    @app.get("/dashboard/operations", response_model=OperationsDashboardResponse)
    def dashboard_operations(
        _access: BetaAccessContext = Depends(require_beta_access),
        sample_symbol: str = Query(default="600519.SH"),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return build_operations_dashboard(session, sample_symbol)

    @app.get("/recommendations/{recommendation_id}/trace", response_model=RecommendationTraceResponse)
    def recommendation_trace(
        recommendation_id: int,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_recommendation_trace(session, recommendation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
