from __future__ import annotations

from collections.abc import Iterator
import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from ashare_evidence.access import BetaAccessContext, require_beta_access, require_beta_write_access
from ashare_evidence.dashboard import (
    bootstrap_dashboard_demo,
    get_glossary_entries,
    get_stock_dashboard,
    list_candidate_recommendations,
)
from ashare_evidence.db import get_database_url, get_session_factory, init_database
from ashare_evidence.llm_service import run_follow_up_analysis
from ashare_evidence.operations import build_operations_dashboard
from ashare_evidence.runtime_config import (
    create_model_api_key,
    delete_model_api_key,
    ensure_runtime_defaults,
    get_runtime_settings,
    set_default_model_api_key,
    upsert_provider_credential,
    update_model_api_key,
)
from ashare_evidence.simulation import (
    end_simulation_session,
    get_simulation_workspace,
    pause_simulation_session,
    place_manual_order,
    restart_simulation_session,
    resume_simulation_session,
    start_simulation_session,
    step_simulation_session,
    update_simulation_config,
)
from ashare_evidence.schemas import (
    FollowUpAnalysisRequest,
    FollowUpAnalysisResponse,
    CandidateListResponse,
    DashboardBootstrapResponse,
    ManualSimulationOrderRequest,
    LatestRecommendationResponse,
    ModelApiKeyCreateRequest,
    ModelApiKeyDeleteResponse,
    ModelApiKeyUpdateRequest,
    OperationsDashboardResponse,
    ProviderCredentialUpsertRequest,
    RecommendationTraceResponse,
    RuntimeSettingsResponse,
    SimulationConfigRequest,
    SimulationControlActionResponse,
    SimulationEndRequest,
    SimulationWorkspaceResponse,
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
    with session_factory() as session:
        ensure_runtime_defaults(session)
        session.commit()

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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "database_url": resolved_database_url}

    @app.get("/settings/runtime", response_model=RuntimeSettingsResponse)
    def runtime_settings(
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return get_runtime_settings(session)

    @app.put("/settings/provider-credentials/{provider_name}")
    def provider_credential_upsert(
        provider_name: str,
        payload: ProviderCredentialUpsertRequest,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            record = upsert_provider_credential(
                session,
                provider_name,
                access_token=payload.access_token,
                base_url=payload.base_url,
                enabled=payload.enabled,
                notes=payload.notes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return record

    @app.post("/settings/model-api-keys")
    def model_api_key_create(
        payload: ModelApiKeyCreateRequest,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            record = create_model_api_key(
                session,
                name=payload.name,
                provider_name=payload.provider_name,
                model_name=payload.model_name,
                base_url=payload.base_url,
                api_key=payload.api_key,
                enabled=payload.enabled,
                priority=payload.priority,
                make_default=payload.make_default,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return record

    @app.patch("/settings/model-api-keys/{key_id}")
    def model_api_key_update(
        key_id: int,
        payload: ModelApiKeyUpdateRequest,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            record = update_model_api_key(
                session,
                key_id,
                name=payload.name,
                provider_name=payload.provider_name,
                model_name=payload.model_name,
                base_url=payload.base_url,
                api_key=payload.api_key,
                enabled=payload.enabled,
                priority=payload.priority,
                make_default=payload.make_default,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return record

    @app.post("/settings/model-api-keys/{key_id}/default")
    def model_api_key_set_default(
        key_id: int,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            record = set_default_model_api_key(session, key_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return record

    @app.delete("/settings/model-api-keys/{key_id}", response_model=ModelApiKeyDeleteResponse)
    def model_api_key_remove(
        key_id: int,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            payload = delete_model_api_key(session, key_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return payload

    @app.post("/analysis/follow-up", response_model=FollowUpAnalysisResponse)
    def follow_up_analysis(
        payload: FollowUpAnalysisRequest,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            return run_follow_up_analysis(
                session,
                symbol=payload.symbol,
                question=payload.question,
                model_api_key_id=payload.model_api_key_id,
                failover_enabled=payload.failover_enabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/bootstrap/demo")
    def bootstrap_demo(
        symbol: str = Query(default="600519.SH"),
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        return bootstrap_demo_data(session, symbol)

    @app.post("/bootstrap/dashboard-demo", response_model=DashboardBootstrapResponse)
    def bootstrap_dashboard_demo_route(
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
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
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
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
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
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
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
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
        return build_operations_dashboard(session, sample_symbol, include_simulation_workspace=True)

    @app.get("/simulation/workspace", response_model=SimulationWorkspaceResponse)
    def simulation_workspace(
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = get_simulation_workspace(session)
        session.commit()
        return payload

    @app.put("/simulation/config", response_model=SimulationControlActionResponse)
    def simulation_config(
        payload: SimulationConfigRequest,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            workspace = update_simulation_config(
                session,
                initial_cash=payload.initial_cash,
                watch_symbols=payload.watch_symbols,
                focus_symbol=payload.focus_symbol,
                step_interval_seconds=payload.step_interval_seconds,
                auto_execute_model=payload.auto_execute_model,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "模拟参数已更新。"}

    @app.post("/simulation/start", response_model=SimulationControlActionResponse)
    def simulation_start(
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            workspace = start_simulation_session(session)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已启动。"}

    @app.post("/simulation/pause", response_model=SimulationControlActionResponse)
    def simulation_pause(
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            workspace = pause_simulation_session(session)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已暂停。"}

    @app.post("/simulation/resume", response_model=SimulationControlActionResponse)
    def simulation_resume(
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            workspace = resume_simulation_session(session)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已恢复。"}

    @app.post("/simulation/step", response_model=SimulationControlActionResponse)
    def simulation_step(
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            workspace = step_simulation_session(session)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "已推进一个刷新步。"}

    @app.post("/simulation/restart", response_model=SimulationControlActionResponse)
    def simulation_restart(
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        workspace = restart_simulation_session(session)
        session.commit()
        return {"workspace": workspace, "message": "已重启为新的双轨模拟进程。"}

    @app.post("/simulation/end", response_model=SimulationControlActionResponse)
    def simulation_end(
        payload: SimulationEndRequest,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            workspace = end_simulation_session(session, confirm=payload.confirm)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已结束。"}

    @app.post("/simulation/manual-order", response_model=SimulationControlActionResponse)
    def simulation_manual_order(
        payload: ManualSimulationOrderRequest,
        _access: BetaAccessContext = Depends(require_beta_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_beta_write_access(_access)
        try:
            workspace = place_manual_order(
                session,
                symbol=payload.symbol,
                side=payload.side,
                quantity=payload.quantity,
                reason=payload.reason,
                limit_price=payload.limit_price,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "用户轨道模拟单已成交。"}

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
