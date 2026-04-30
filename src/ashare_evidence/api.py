from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import asynccontextmanager
import contextlib
import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from ashare_evidence.account_space import visible_account_spaces
from ashare_evidence.dashboard import (
    get_glossary_entries,
    get_stock_dashboard,
    list_candidate_recommendations,
)
from ashare_evidence.db import get_database_url, get_session_factory, init_database
from ashare_evidence.llm_service import run_follow_up_analysis
from ashare_evidence.manual_research_workflow import (
    complete_manual_research_request,
    create_manual_research_request,
    execute_manual_research_request,
    fail_manual_research_request,
    get_manual_research_request,
    list_manual_research_requests,
    retry_manual_research_request,
)
from ashare_evidence.operations import build_operations_dashboard
from ashare_evidence.runtime_ops import run_operations_tick
from ashare_evidence.runtime_config import (
    create_model_api_key,
    delete_model_api_key,
    ensure_runtime_defaults,
    get_runtime_overview,
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
from ashare_evidence.stock_auth import StockAccessContext, require_stock_access, require_stock_root
from ashare_evidence.schemas import (
    AuthContextResponse,
    FollowUpAnalysisRequest,
    FollowUpAnalysisResponse,
    CandidateListResponse,
    ManualSimulationOrderRequest,
    LatestRecommendationResponse,
    ManualResearchRequestCompleteRequest,
    ManualResearchRequestCreateRequest,
    ManualResearchRequestExecuteRequest,
    ManualResearchRequestFailRequest,
    ManualResearchRequestListResponse,
    ManualResearchRequestRetryRequest,
    ManualResearchRequestView,
    ModelApiKeyCreateRequest,
    ModelApiKeyDeleteResponse,
    ModelApiKeyUpdateRequest,
    OperationsDashboardResponse,
    ProviderCredentialUpsertRequest,
    RecommendationTraceResponse,
    RuntimeOverviewResponse,
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
from ashare_evidence.services import get_latest_recommendation_summary, get_recommendation_trace
from ashare_evidence.watchlist import (
    add_watchlist_symbol,
    list_watchlist_entries,
    refresh_watchlist_symbol,
    remove_watchlist_symbol,
)

LOGGER = logging.getLogger(__name__)


def create_app(
    database_url: str | None = None,
    *,
    enable_background_ops_tick: bool | None = None,
) -> FastAPI:
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

    tick_interval_seconds = max(int(os.getenv("ASHARE_BACKGROUND_OPS_TICK_SECONDS", "60")), 15)
    background_ops_enabled = (
        enable_background_ops_tick
        if enable_background_ops_tick is not None
        else os.getenv("ASHARE_DISABLE_BACKGROUND_OPS_TICK", "").strip().lower() not in {"1", "true", "yes", "on"}
    )

    async def background_operations_loop(stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                with session_factory() as session:
                    run_operations_tick(session)
            except Exception:
                LOGGER.exception("background operations tick failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=tick_interval_seconds)
            except TimeoutError:
                continue

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not background_ops_enabled:
            yield
            return
        stop_event = asyncio.Event()
        task = asyncio.create_task(background_operations_loop(stop_event))
        app.state.background_ops_stop_event = stop_event
        app.state.background_ops_task = task
        try:
            yield
        finally:
            stop_event.set()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="A-share Evidence Foundation",
        version="0.1.0",
        summary="Evidence-first market/news/model/recommendation data layer.",
        lifespan=lifespan,
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

    @app.get("/auth/context", response_model=AuthContextResponse)
    def auth_context(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = {
            "actor_login": access.actor_login,
            "actor_role": access.actor_role,
            "target_login": access.target_login,
            "can_act_as": access.can_act_as,
            "auth_mode": access.auth_mode,
            "visible_account_spaces": visible_account_spaces(
                session,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            ),
        }
        session.commit()
        return payload

    @app.get("/runtime/overview", response_model=RuntimeOverviewResponse)
    def runtime_overview(
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return get_runtime_overview(session)

    @app.get("/settings/runtime", response_model=RuntimeSettingsResponse)
    def runtime_settings(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        return get_runtime_settings(session)

    @app.put("/settings/provider-credentials/{provider_name}")
    def provider_credential_upsert(
        provider_name: str,
        payload: ProviderCredentialUpsertRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
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
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
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
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
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
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            record = set_default_model_api_key(session, key_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return record

    @app.delete("/settings/model-api-keys/{key_id}", response_model=ModelApiKeyDeleteResponse)
    def model_api_key_remove(
        key_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            payload = delete_model_api_key(session, key_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return payload

    @app.post("/analysis/follow-up", response_model=FollowUpAnalysisResponse)
    def follow_up_analysis(
        payload: FollowUpAnalysisRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
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

    @app.post("/manual-research/requests", response_model=ManualResearchRequestView)
    def manual_research_request_create(
        payload: ManualResearchRequestCreateRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = create_manual_research_request(
                session,
                symbol=payload.symbol,
                question=payload.question,
                trigger_source=payload.trigger_source,
                requested_by=access.actor_login,
                executor_kind=payload.executor_kind,
                model_api_key_id=payload.model_api_key_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.get("/manual-research/requests", response_model=ManualResearchRequestListResponse)
    def manual_research_request_list(
        symbol: str | None = Query(default=None),
        status: str | None = Query(default=None),
        executor_kind: str | None = Query(default=None),
        include_superseded: bool = Query(default=False),
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        return list_manual_research_requests(
            session,
            symbol=symbol,
            status=status,
            executor_kind=executor_kind,
            include_superseded=include_superseded,
        )

    @app.get("/manual-research/requests/{request_id}", response_model=ManualResearchRequestView)
    def manual_research_request_detail(
        request_id: int,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            return get_manual_research_request(session, request_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/manual-research/requests/{request_id}/execute", response_model=ManualResearchRequestView)
    def manual_research_request_execute(
        request_id: int,
        payload: ManualResearchRequestExecuteRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = execute_manual_research_request(
                session,
                request_id=request_id,
                failover_enabled=payload.failover_enabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        session.commit()
        return result

    @app.post("/manual-research/requests/{request_id}/complete", response_model=ManualResearchRequestView)
    def manual_research_request_complete(
        request_id: int,
        payload: ManualResearchRequestCompleteRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = complete_manual_research_request(
                session,
                request_id=request_id,
                summary=payload.summary,
                review_verdict=payload.review_verdict,
                risks=payload.risks,
                disagreements=payload.disagreements,
                decision_note=payload.decision_note,
                citations=payload.citations,
                answer=payload.answer,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.post("/manual-research/requests/{request_id}/fail", response_model=ManualResearchRequestView)
    def manual_research_request_fail(
        request_id: int,
        payload: ManualResearchRequestFailRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = fail_manual_research_request(
                session,
                request_id=request_id,
                failure_reason=payload.failure_reason,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.post("/manual-research/requests/{request_id}/retry", response_model=ManualResearchRequestView)
    def manual_research_request_retry(
        request_id: int,
        payload: ManualResearchRequestRetryRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        try:
            result = retry_manual_research_request(
                session,
                request_id=request_id,
                requested_by=payload.requested_by or access.actor_login,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session.commit()
        return result

    @app.get("/watchlist", response_model=WatchlistResponse)
    def watchlist(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = list_watchlist_entries(
            session,
            target_login=access.target_login,
            actor_login=access.actor_login,
            actor_role=access.actor_role,
        )
        session.commit()
        return payload

    @app.post("/watchlist", response_model=WatchlistMutationResponse)
    def watchlist_add(
        payload: WatchlistCreateRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            item = add_watchlist_symbol(
                session,
                payload.symbol,
                stock_name=payload.name,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                target_login=access.target_login,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        message = (
            f"已将 {item['name']}（{item['symbol']}）加入自选池并完成真实数据分析。"
            if item["analysis_status"] == "ready" and not item.get("last_error")
            else f"已将 {item['name']}（{item['symbol']}）加入自选池，但当前未能完成最新真实分析。"
        )
        return {
            "item": item,
            "message": message,
        }

    @app.post("/watchlist/{symbol}/refresh", response_model=WatchlistMutationResponse)
    def watchlist_refresh(
        symbol: str,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            item = refresh_watchlist_symbol(
                session,
                symbol,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                target_login=access.target_login,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        message = (
            f"已用最新真实数据刷新 {item['name']}（{item['symbol']}）。"
            if item["analysis_status"] == "ready" and not item.get("last_error")
            else f"已尝试刷新 {item['name']}（{item['symbol']}），当前继续保留已有真实结果或等待数据补齐。"
        )
        return {
            "item": item,
            "message": message,
        }

    @app.delete("/watchlist/{symbol}", response_model=WatchlistDeleteResponse)
    def watchlist_remove(
        symbol: str,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return remove_watchlist_symbol(
                session,
                symbol,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                target_login=access.target_login,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/stocks/{symbol}/recommendations/latest", response_model=LatestRecommendationResponse)
    def latest_recommendation(
        symbol: str,
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = get_latest_recommendation_summary(session, symbol)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"No recommendation found for {symbol}.")
        return payload

    @app.get("/stocks/{symbol}/dashboard", response_model=StockDashboardResponse)
    def stock_dashboard(
        symbol: str,
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_stock_dashboard(session, symbol)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/dashboard/candidates", response_model=CandidateListResponse)
    def dashboard_candidates(
        limit: int = Query(default=8, ge=1, le=20),
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return list_candidate_recommendations(session, limit=limit)

    @app.get("/dashboard/glossary")
    def dashboard_glossary(_access: StockAccessContext = Depends(require_stock_access)) -> list[dict[str, str]]:
        return get_glossary_entries()

    @app.get("/dashboard/operations", response_model=OperationsDashboardResponse)
    def dashboard_operations(
        access: StockAccessContext = Depends(require_stock_access),
        sample_symbol: str = Query(default="600519.SH"),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        require_stock_root(access)
        run_operations_tick(session)
        return build_operations_dashboard(
            session,
            sample_symbol,
            include_simulation_workspace=True,
            target_login=access.target_login,
        )

    @app.get("/simulation/workspace", response_model=SimulationWorkspaceResponse)
    def simulation_workspace(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        payload = get_simulation_workspace(
            session,
            owner_login=access.target_login,
            actor_login=access.actor_login,
            actor_role=access.actor_role,
        )
        session.commit()
        return payload

    @app.put("/simulation/config", response_model=SimulationControlActionResponse)
    def simulation_config(
        payload: SimulationConfigRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = update_simulation_config(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
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
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = start_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已启动。"}

    @app.post("/simulation/pause", response_model=SimulationControlActionResponse)
    def simulation_pause(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = pause_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已暂停。"}

    @app.post("/simulation/resume", response_model=SimulationControlActionResponse)
    def simulation_resume(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = resume_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已恢复。"}

    @app.post("/simulation/step", response_model=SimulationControlActionResponse)
    def simulation_step(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = step_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "已推进一个刷新步。"}

    @app.post("/simulation/restart", response_model=SimulationControlActionResponse)
    def simulation_restart(
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        workspace = restart_simulation_session(
            session,
            owner_login=access.target_login,
            actor_login=access.actor_login,
            actor_role=access.actor_role,
        )
        session.commit()
        return {"workspace": workspace, "message": "已重启为新的双轨模拟进程。"}

    @app.post("/simulation/end", response_model=SimulationControlActionResponse)
    def simulation_end(
        payload: SimulationEndRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = end_simulation_session(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
                confirm=payload.confirm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        session.commit()
        return {"workspace": workspace, "message": "双轨模拟已结束。"}

    @app.post("/simulation/manual-order", response_model=SimulationControlActionResponse)
    def simulation_manual_order(
        payload: ManualSimulationOrderRequest,
        access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            workspace = place_manual_order(
                session,
                owner_login=access.target_login,
                actor_login=access.actor_login,
                actor_role=access.actor_role,
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
        _access: StockAccessContext = Depends(require_stock_access),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        try:
            return get_recommendation_trace(session, recommendation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
