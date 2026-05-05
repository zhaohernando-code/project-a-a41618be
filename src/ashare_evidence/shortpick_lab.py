from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Protocol
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ashare_evidence.analysis_pipeline import _fetch_daily_bars_akshare, _fetch_daily_bars_tushare
from ashare_evidence.benchmark import CSI_BENCHMARKS, benchmark_close_maps, sync_benchmark_index_bars
from ashare_evidence.db import utcnow
from ashare_evidence.http_client import urlopen
from ashare_evidence.lineage import build_lineage
from ashare_evidence.llm_service import OpenAICompatibleTransport
from ashare_evidence.models import (
    MarketBar,
    ModelApiKey,
    Recommendation,
    ShortpickCandidate,
    ShortpickConsensusSnapshot,
    ShortpickExperimentRun,
    ShortpickModelRound,
    ShortpickValidationSnapshot,
    Stock,
    WatchlistFollow,
)
from ashare_evidence.recommendation_selection import recommendation_recency_ordering
from ashare_evidence.research_artifact_store import artifact_root_from_database_url, write_shortpick_lab_artifact
from ashare_evidence.runtime_config import get_builtin_llm_executor_config, resolve_llm_key_candidates
from ashare_evidence.stock_master import resolve_stock_profile

SHORTPICK_PROMPT_VERSION = "native_web_open_discovery_v1"
SHORTPICK_INFORMATION_MODE = "native_web_open_discovery"
SHORTPICK_DEFAULT_HORIZONS = [1, 3, 5, 10, 20]
SHORTPICK_PRIMARY_BENCHMARK_ID = "CSI300"
SHORTPICK_RESEARCH_BENCHMARK_IDS = ["CSI1000"]
SHORTPICK_CODEX_TIMEOUT_SECONDS = 240
SHORTPICK_SOURCE_CHECK_TIMEOUT_SECONDS = 3
SHORTPICK_SEARXNG_TIMEOUT_SECONDS = 12
SHORTPICK_DEEPSEEK_SEARCH_TIMEOUT_SECONDS = 180
SHORTPICK_LOBECHAT_SEARXNG_URL_ENV = "SHORTPICK_LOBECHAT_SEARXNG_URL"
SHORTPICK_LOBECHAT_SEARXNG_DEFAULT_URL = "http://127.0.0.1:18080"
SUSPICIOUS_SOURCE_PATTERNS = (
    re.compile(r"(?:123456|234567|345678|456789|987654|876543)"),
    re.compile(r"(.)\1{5,}"),
    re.compile(r"(?:xxxx|abc123|example|placeholder|dummy)", re.IGNORECASE),
)


class ShortpickExecutor(Protocol):
    provider_name: str
    model_name: str
    executor_kind: str

    def complete(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class StaticShortpickExecutor:
    provider_name: str
    model_name: str
    executor_kind: str
    answer: str

    def complete(self, prompt: str) -> str:
        return self.answer


@dataclass(frozen=True)
class CodexCliShortpickExecutor:
    codex_bin: str
    model_name: str
    provider_name: str = "openai"
    executor_kind: str = "isolated_codex_cli"

    def complete(self, prompt: str) -> str:
        with tempfile.TemporaryDirectory(prefix="ashare-shortpick-codex-") as cwd:
            output_path = Path(cwd) / "answer.txt"
            command = [
                self.codex_bin,
                "exec",
                "-C",
                cwd,
                "--skip-git-repo-check",
                "-s",
                "read-only",
                "-m",
                self.model_name,
                "-o",
                str(output_path),
                "-",
            ]
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                check=False,
                timeout=SHORTPICK_CODEX_TIMEOUT_SECONDS,
                env=_isolated_codex_env(),
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "unknown codex execution error").strip()
                raise RuntimeError(f"isolated Codex shortpick execution failed: {detail}")
            answer = output_path.read_text(encoding="utf-8").strip()
        if not answer:
            raise RuntimeError("isolated Codex shortpick execution returned an empty answer.")
        return answer


@dataclass(frozen=True)
class SearxngSearchClient:
    base_url: str
    timeout_seconds: int = SHORTPICK_SEARXNG_TIMEOUT_SECONDS
    result_limit: int = 5

    def search(self, query: str) -> list[dict[str, Any]]:
        trimmed = query.strip()
        if not trimmed:
            return []
        params = urlencode({"q": trimmed, "format": "json", "language": "zh-CN"})
        http_request = request.Request(
            f"{self.base_url.rstrip('/')}/search?{params}",
            headers={"User-Agent": "ashare-shortpick-lab-lobechat-searxng/1.0"},
        )
        with urlopen(http_request, timeout=self.timeout_seconds, disable_proxies=True) as response:
            payload = json.loads(response.read().decode("utf-8"))
        results: list[dict[str, Any]] = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            url = _coerce_text(item.get("url"))
            if not url:
                continue
            results.append(
                {
                    "title": _coerce_text(item.get("title")) or url,
                    "url": url,
                    "published_at": _coerce_text(item.get("publishedDate") or item.get("pubdate") or item.get("published_at")),
                    "why_it_matters": _coerce_text(item.get("content") or item.get("metadata") or ""),
                    "search_query": trimmed,
                    "search_engine": _coerce_text(item.get("engine") or ""),
                    "search_score": item.get("score"),
                }
            )
            if len(results) >= self.result_limit:
                break
        return results


@dataclass(frozen=True)
class DeepseekLobeChatSearchShortpickExecutor:
    key_id: int | None
    provider_name: str
    model_name: str
    base_url: str
    api_key: str
    searxng_url: str | None = None
    executor_kind: str = "deepseek_tool_search_lobechat_searxng_v1"
    search_client: SearxngSearchClient | None = None

    def complete(self, prompt: str) -> str:
        transport = OpenAICompatibleTransport()
        search_client = self.search_client or SearxngSearchClient(
            self.searxng_url
            or os.environ.get(SHORTPICK_LOBECHAT_SEARXNG_URL_ENV)
            or SHORTPICK_LOBECHAT_SEARXNG_DEFAULT_URL
        )
        plan_raw = transport.complete(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            prompt=_build_deepseek_search_plan_prompt(prompt),
            system=(
                "你正在执行独立 A 股短线研究实验。你当前不能直接联网。"
                "你的任务是先自主决定需要搜索哪些公开信息，不要输出股票推荐，只输出 JSON。"
            ),
        )
        plan = extract_shortpick_json(plan_raw)
        queries = _coerce_search_queries(plan.get("search_queries") or plan.get("queries"))
        if not queries:
            raise RuntimeError("deepseek search planning produced no search queries.")

        search_results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for query in queries:
            for result in search_client.search(query):
                url = str(result.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                search_results.append(result)

        if not search_results:
            raise RuntimeError("LobeChat/SearXNG returned no usable search results for DeepSeek search plan.")

        final_raw = transport.complete(
            base_url=self.base_url,
            api_key=self.api_key,
            model_name=self.model_name,
            prompt=_build_deepseek_final_prompt(prompt=prompt, plan=plan, search_results=search_results),
            system=(
                "你正在执行独立 A 股短线研究实验。不要读取本地项目、数据库、代码库或历史推荐。"
                "你只能基于用户问题和系统提供的公开搜索结果进行分析；sources_used 必须来自这些搜索结果，不能编造 URL。只输出 JSON。"
            ),
        )
        return _attach_deepseek_search_trace(final_raw, plan=plan, search_results=search_results, executor_kind=self.executor_kind)


@dataclass(frozen=True)
class OpenAICompatibleShortpickExecutor:
    key_id: int | None
    provider_name: str
    model_name: str
    base_url: str
    api_key: str
    executor_kind: str = "configured_api_key_native_web_search"

    def complete(self, prompt: str) -> str:
        raise RuntimeError(
            "configured OpenAI-compatible DeepSeek API is not a valid shortpick native-web executor; "
            "DeepSeek official API does not provide web search. Use deepseek_tool_search_lobechat_searxng_v1."
        )


def _isolated_codex_env() -> dict[str, str]:
    keep_prefixes = ("PATH", "HOME", "LANG", "LC_", "SSL_", "HTTP_", "HTTPS_", "ALL_PROXY", "NO_PROXY")
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith("ASHARE_") or key in {"PYTHONPATH", "DATABASE_URL"}:
            continue
        if key in {"PATH", "HOME", "LANG"} or key.startswith(("LC_", "SSL_")) or key in {
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
        }:
            env[key] = value
    if "PATH" not in env:
        env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    return env


def build_shortpick_prompt(*, run_date: date, round_index: int, provider_name: str, model_name: str) -> str:
    return f"""
本会话仅用于研究不同大模型在公开网络信息环境下，对 A 股短线机会进行自由发现的能力，不作为真实交易建议或下单依据。

请不要使用任何本地项目、股票看板数据库、自选池、历史推荐或内部结构化数据。你可以自行使用公开网络信息、搜索、新闻、公告、市场热点、产业信息或其他你认为有价值的公开资料。

任务日期：{run_date.isoformat()}，时区：Asia/Shanghai。
目标市场：中国 A 股全市场。
目标周期：未来 1-10 个交易日。
模型轮次：{provider_name}:{model_name} 第 {round_index} 轮。

请尽量保持独立判断，不需要迎合常规量化框架。你可以选择热点题材、事件催化、资金关注、产业变化、政策变化、公告变化或其他你认为有短线意义的方向。

只输出 JSON，不要加代码块：
{{
  "as_of_date": "{run_date.isoformat()}",
  "information_mode": "native_web_open_discovery",
  "primary_pick": {{
    "symbol": "000000.SZ",
    "name": "...",
    "theme": "...",
    "horizon_trading_days": 5,
    "confidence": 0.0,
    "thesis": "...",
    "catalysts": ["..."],
    "invalidation": ["..."],
    "risks": ["..."]
  }},
  "sources_used": [
    {{
      "title": "...",
      "url": "...",
      "published_at": "...",
      "why_it_matters": "..."
    }}
  ],
  "alternative_picks": [],
  "novelty_note": "这个推荐与常规历史数据/量化视角相比，可能提供的新视角是什么",
  "limitations": ["..."]
}}
""".strip()


def _build_deepseek_search_plan_prompt(prompt: str) -> str:
    return f"""
你将参与一个短投推荐研究实验，但你不能直接联网，也不能读取本地项目或数据库。

请仅基于下面的研究任务，决定你为了完成任务会自主搜索哪些公开网络信息。不要推荐股票，不要编造搜索结果。

输出 JSON，不要加代码块：
{{
  "search_queries": [
    "A股 今日 短线 热点 题材 公开新闻",
    "..."
  ],
  "search_intent": "你为什么选择这些搜索方向",
  "limitations": ["当前回答只生成搜索计划，不代表最终结论"]
}}

研究任务：
{prompt}
""".strip()


def _build_deepseek_final_prompt(*, prompt: str, plan: dict[str, Any], search_results: list[dict[str, Any]]) -> str:
    evidence = {
        "search_plan": plan,
        "search_backend": "lobechat_searxng",
        "source_policy": "sources_used must be selected only from search_results urls; do not invent urls",
        "search_results": search_results[:20],
    }
    return f"""
请继续完成下面的短投推荐研究任务。

你不能直接联网。以下公开搜索结果来自你上一轮自主规划的搜索查询，由系统通过 LobeChat/SearXNG 执行。你可以自由判断哪些结果有用，也可以在 limitations 中说明搜索结果不足，但最终 sources_used 只能引用 search_results 中真实出现的 URL，不能编造 URL。

搜索证据 JSON：
{json.dumps(evidence, ensure_ascii=False, indent=2)}

研究任务：
{prompt}
""".strip()


def _coerce_search_queries(value: Any) -> list[str]:
    items = value if isinstance(value, list) else []
    queries: list[str] = []
    for item in items:
        text = _coerce_text(item)
        if not text or text in queries:
            continue
        queries.append(text[:180])
        if len(queries) >= 5:
            break
    return queries


def _attach_deepseek_search_trace(
    raw_answer: str,
    *,
    plan: dict[str, Any],
    search_results: list[dict[str, Any]],
    executor_kind: str,
) -> str:
    parsed = extract_shortpick_json(raw_answer)
    parsed["_executor_trace"] = {
        "executor_kind": executor_kind,
        "search_backend": "lobechat_searxng",
        "search_queries": _coerce_search_queries(plan.get("search_queries") or plan.get("queries")),
        "search_result_count": len(search_results),
        "search_result_urls": [str(item.get("url") or "") for item in search_results[:20] if item.get("url")],
    }
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def default_shortpick_executors(session: Session) -> list[ShortpickExecutor]:
    executors: list[ShortpickExecutor] = []
    builtin = get_builtin_llm_executor_config()
    if builtin.get("enabled") and builtin.get("transport_kind") == "codex_cli" and builtin.get("codex_bin"):
        executors.append(
            CodexCliShortpickExecutor(
                codex_bin=str(builtin["codex_bin"]),
                model_name=str(builtin["model_name"]),
                provider_name=str(builtin.get("provider_name") or "openai"),
            )
        )
    elif builtin.get("enabled") and builtin.get("transport_kind") == "openai_api":
        executors.append(
            OpenAICompatibleShortpickExecutor(
                key_id=None,
                provider_name=str(builtin.get("provider_name") or "openai"),
                model_name=str(builtin["model_name"]),
                base_url=str(builtin["base_url"]),
                api_key=str(builtin["api_key"]),
                executor_kind="builtin_openai_api_native_web",
            )
        )
    deepseek = next(
        (key for key in resolve_llm_key_candidates(session) if "deepseek" in key.provider_name.lower() or "deepseek" in key.base_url.lower()),
        None,
    )
    if deepseek is not None:
        executors.append(_executor_from_key(deepseek))
    return executors


def _executor_from_key(key: ModelApiKey) -> DeepseekLobeChatSearchShortpickExecutor:
    return DeepseekLobeChatSearchShortpickExecutor(
        key_id=key.id,
        provider_name=key.provider_name,
        model_name=key.model_name,
        base_url=key.base_url,
        api_key=key.api_key,
    )


def run_shortpick_experiment(
    session: Session,
    *,
    run_date: date | None = None,
    rounds_per_model: int = 5,
    triggered_by: str | None = None,
    trigger_source: str = "manual_api",
    executors: list[ShortpickExecutor] | None = None,
) -> dict[str, Any]:
    target_date = run_date or datetime.now(UTC).date()
    normalized_rounds = max(1, min(int(rounds_per_model), 10))
    started_at = utcnow()
    run = ShortpickExperimentRun(
        run_key=f"shortpick:{target_date.isoformat()}:{started_at:%Y%m%d%H%M%S%f}",
        run_date=target_date,
        prompt_version=SHORTPICK_PROMPT_VERSION,
        information_mode=SHORTPICK_INFORMATION_MODE,
        status="running",
        trigger_source=trigger_source,
        triggered_by=triggered_by,
        started_at=started_at,
        completed_at=None,
        failed_at=None,
        model_config={
            "rounds_per_model": normalized_rounds,
            "native_web_search": True,
            "controlled_search": False,
        },
        summary_payload={},
    )
    session.add(run)
    session.flush()

    active_executors = executors if executors is not None else default_shortpick_executors(session)
    run.model_config = {
        **dict(run.model_config or {}),
        "models": [
            {
                "provider_name": executor.provider_name,
                "model_name": executor.model_name,
                "executor_kind": executor.executor_kind,
            }
            for executor in active_executors
        ],
    }
    session.commit()
    session.refresh(run)
    if not active_executors:
        run.status = "failed"
        run.failed_at = utcnow()
        run.summary_payload = {"error": "No shortpick executor is available."}
        session.commit()
        session.refresh(run)
        return serialize_shortpick_run(session, run, include_raw=True)

    for executor in active_executors:
        for round_index in range(1, normalized_rounds + 1):
            _execute_shortpick_round(session, run, executor, round_index)

    consensus = build_shortpick_consensus(session, run)
    validation_result = validate_shortpick_run(session, run.id, horizons=SHORTPICK_DEFAULT_HORIZONS)
    completed_count = session.scalar(
        select(func.count(ShortpickModelRound.id)).where(
            ShortpickModelRound.run_id == run.id,
            ShortpickModelRound.status == "completed",
        )
    ) or 0
    failed_count = session.scalar(
        select(func.count(ShortpickModelRound.id)).where(
            ShortpickModelRound.run_id == run.id,
            ShortpickModelRound.status == "failed",
        )
    ) or 0
    parse_failed_count = session.scalar(
        select(func.count(ShortpickCandidate.id)).where(
            ShortpickCandidate.run_id == run.id,
            ShortpickCandidate.parse_status == "parse_failed",
        )
    ) or 0
    run.status = "completed" if completed_count else "failed"
    run.completed_at = utcnow() if completed_count else None
    run.failed_at = None if completed_count else utcnow()
    run.summary_payload = {
        "completed_round_count": completed_count,
        "failed_round_count": failed_count,
        "parse_failed_count": parse_failed_count,
        "candidate_count": session.scalar(select(func.count(ShortpickCandidate.id)).where(ShortpickCandidate.run_id == run.id)) or 0,
        "consensus_priority": consensus.research_priority,
        "boundary": "independent_research_lab_no_main_pool_write",
        **dict(validation_result.get("summary") or {}),
    }
    session.commit()
    session.refresh(run)
    return serialize_shortpick_run(session, run, include_raw=True)


def _execute_shortpick_round(
    session: Session,
    run: ShortpickExperimentRun,
    executor: ShortpickExecutor,
    round_index: int,
) -> None:
    started_at = utcnow()
    round_record = ShortpickModelRound(
        run_id=run.id,
        round_key=f"{run.run_key}:{executor.provider_name}:{executor.model_name}:{round_index}",
        provider_name=executor.provider_name,
        model_name=executor.model_name,
        executor_kind=executor.executor_kind,
        round_index=round_index,
        status="running",
        raw_answer=None,
        parsed_payload={},
        sources_payload=[],
        artifact_id=None,
        error_message=None,
        started_at=started_at,
        completed_at=None,
    )
    session.add(round_record)
    session.commit()
    session.refresh(run)
    prompt = build_shortpick_prompt(
        run_date=run.run_date,
        round_index=round_index,
        provider_name=executor.provider_name,
        model_name=executor.model_name,
    )
    try:
        raw_answer = executor.complete(prompt)
        round_record.raw_answer = raw_answer
        parsed = extract_shortpick_json(raw_answer)
        sources = _normalize_sources(parsed.get("sources_used"))
        source_failure = _web_source_integrity_failure(executor=executor, parsed=parsed, sources=sources)
        if source_failure:
            raise RuntimeError(source_failure)
        round_record.parsed_payload = parsed
        round_record.sources_payload = sources
        round_record.status = "completed"
        round_record.completed_at = utcnow()
        round_record.artifact_id = f"shortpick-round:{round_record.id}"
        _write_round_artifact(session, run, round_record, prompt=prompt)
        _candidate_from_round(session, run, round_record, parsed, parse_status="parsed")
    except Exception as exc:
        round_record.status = "failed"
        round_record.error_message = str(exc)
        round_record.completed_at = utcnow()
        round_record.artifact_id = f"shortpick-round:{round_record.id}"
        round_record.raw_answer = round_record.raw_answer or None
        _write_round_artifact(session, run, round_record, prompt=prompt)
        _candidate_from_round(
            session,
            run,
            round_record,
            {
                "primary_pick": {
                    "symbol": "PARSE_FAILED",
                    "name": "解析失败",
                    "theme": "parse_failed",
                    "thesis": str(exc),
                },
                "sources_used": [],
                "limitations": [str(exc)],
            },
            parse_status="parse_failed",
        )
    session.flush()


def extract_shortpick_json(raw_answer: str) -> dict[str, Any]:
    text = raw_answer.strip()
    candidates = [text]
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if not block or block.lower() == "json":
                continue
            candidates.append(block.removeprefix("json").strip())
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first : last + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("shortpick answer did not contain a JSON object")


def _web_source_integrity_failure(*, executor: ShortpickExecutor, parsed: dict[str, Any], sources: list[dict[str, Any]]) -> str | None:
    if executor.executor_kind not in {
        "isolated_codex_cli",
        "deepseek_tool_search_lobechat_searxng_v1",
        "configured_api_key_native_web_search",
        "builtin_openai_api_native_web",
    }:
        return None
    if parsed.get("unable_to_search") is True:
        return f"{executor.provider_name} reported it was unable to search."
    if not sources:
        return f"{executor.provider_name} web executor returned no sources."
    status_counts: dict[str, int] = {}
    for source in sources:
        status = str(source.get("credibility_status") or "unchecked")
        status_counts[status] = status_counts.get(status, 0) + 1
    if not any(status in {"verified", "reachable_restricted"} for status in status_counts):
        return f"{executor.provider_name} web executor returned no reachable sources: {status_counts}."
    return None


def _candidate_from_round(
    session: Session,
    run: ShortpickExperimentRun,
    round_record: ShortpickModelRound,
    parsed: dict[str, Any],
    *,
    parse_status: str,
) -> ShortpickCandidate:
    pick = parsed.get("primary_pick") if isinstance(parsed.get("primary_pick"), dict) else {}
    symbol = _normalize_symbol(str(pick.get("symbol") or "PARSE_FAILED"))
    name = str(pick.get("name") or symbol).strip()[:64] or symbol
    theme = str(pick.get("theme") or _infer_theme(pick) or "").strip() or None
    candidate = ShortpickCandidate(
        run_id=run.id,
        round_id=round_record.id,
        candidate_key=f"shortpick-candidate:{round_record.id}",
        symbol=symbol,
        name=name,
        normalized_theme=theme,
        horizon_trading_days=_coerce_int(pick.get("horizon_trading_days")),
        confidence=_coerce_float(pick.get("confidence")),
        thesis=_coerce_text(pick.get("thesis")),
        catalysts=_coerce_string_list(pick.get("catalysts")),
        invalidation=_coerce_string_list(pick.get("invalidation")),
        risks=_coerce_string_list(pick.get("risks")),
        sources_payload=list(round_record.sources_payload or _normalize_sources(parsed.get("sources_used"))),
        novelty_note=_coerce_text(parsed.get("novelty_note")),
        limitations=_coerce_string_list(parsed.get("limitations")),
        convergence_group=None,
        research_priority="pending_consensus",
        parse_status=parse_status,
        is_system_external=_is_system_external(session, symbol),
        candidate_payload={
            "information_mode": parsed.get("information_mode"),
            "alternative_picks": parsed.get("alternative_picks") if isinstance(parsed.get("alternative_picks"), list) else [],
            "model": {
                "provider_name": round_record.provider_name,
                "model_name": round_record.model_name,
                "round_index": round_record.round_index,
            },
        },
    )
    session.add(candidate)
    session.flush()
    return candidate


def build_shortpick_consensus(session: Session, run: ShortpickExperimentRun) -> ShortpickConsensusSnapshot:
    candidates = session.scalars(
        select(ShortpickCandidate).where(ShortpickCandidate.run_id == run.id).order_by(ShortpickCandidate.id.asc())
    ).all()
    parsed = [item for item in candidates if item.parse_status == "parsed" and item.symbol != "PARSE_FAILED"]
    total = max(len(parsed), 1)
    symbol_counts: dict[str, int] = {}
    theme_counts: dict[str, int] = {}
    model_by_symbol: dict[str, set[str]] = {}
    source_hosts: set[str] = set()
    all_source_urls: set[str] = set()
    source_status_counts: dict[str, int] = {}
    for candidate in parsed:
        symbol_counts[candidate.symbol] = symbol_counts.get(candidate.symbol, 0) + 1
        if candidate.normalized_theme:
            theme_counts[candidate.normalized_theme] = theme_counts.get(candidate.normalized_theme, 0) + 1
        round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
        if round_record is not None:
            model_by_symbol.setdefault(candidate.symbol, set()).add(round_record.provider_name)
        for source in candidate.sources_payload:
            credibility = str(source.get("credibility_status") or "unchecked")
            source_status_counts[credibility] = source_status_counts.get(credibility, 0) + 1
            url = str(source.get("url") or "").strip()
            if not url:
                continue
            all_source_urls.add(url)
            source_hosts.add(_host_from_url(url))
    max_symbol_count = max(symbol_counts.values(), default=0)
    max_theme_count = max(theme_counts.values(), default=0)
    stock_convergence = max_symbol_count / total
    theme_convergence = max_theme_count / total
    source_diversity = min(len(source_hosts) / max(len(all_source_urls), 1), 1.0) if all_source_urls else 0.0
    model_independence = max((len(models) for models in model_by_symbol.values()), default=0) / max(
        len({candidate.candidate_payload.get("model", {}).get("provider_name") for candidate in parsed}),
        1,
    )
    novelty_score = sum(1 for item in parsed if item.is_system_external) / total
    priority_score = (
        stock_convergence * 0.35
        + theme_convergence * 0.2
        + source_diversity * 0.15
        + model_independence * 0.15
        + novelty_score * 0.15
    )
    priority = "high_convergence" if priority_score >= 0.68 else "theme_convergence" if theme_convergence >= 0.45 else "divergent_novel"
    leader_symbols = [symbol for symbol, count in symbol_counts.items() if count == max_symbol_count and count > 0]
    leader_themes = [theme for theme, count in theme_counts.items() if count == max_theme_count and count > 0]
    for candidate in parsed:
        if candidate.symbol in leader_symbols and max_symbol_count > 1:
            candidate.convergence_group = "stock"
            candidate.research_priority = "high_convergence"
        elif candidate.normalized_theme in leader_themes and max_theme_count > 1:
            candidate.convergence_group = "theme"
            candidate.research_priority = "theme_convergence"
        elif candidate.is_system_external:
            candidate.convergence_group = "novel"
            candidate.research_priority = "divergent_novel"
        else:
            candidate.convergence_group = "low"
            candidate.research_priority = "watch_only"
    generated_at = utcnow()
    snapshot = ShortpickConsensusSnapshot(
        run_id=run.id,
        snapshot_key=f"shortpick-consensus:{run.id}",
        artifact_id=f"shortpick-consensus:{run.id}",
        generated_at=generated_at,
        status="completed" if parsed else "insufficient_parsed_rounds",
        stock_convergence=stock_convergence,
        theme_convergence=theme_convergence,
        source_diversity=source_diversity,
        model_independence=model_independence,
        novelty_score=novelty_score,
        research_priority=priority,
        summary_payload={
            "leader_symbols": leader_symbols,
            "leader_themes": leader_themes,
            "priority_score": round(priority_score, 4),
            "candidate_count": len(candidates),
            "parsed_candidate_count": len(parsed),
            "source_credibility_counts": source_status_counts,
            "interpretation": "模型一致性只代表研究优先级，不代表交易建议。",
        },
    )
    session.add(snapshot)
    session.flush()
    _write_consensus_artifact(session, run, snapshot)
    return snapshot


def validate_shortpick_run(
    session: Session,
    run_id: int,
    *,
    horizons: list[int] | None = None,
) -> dict[str, Any]:
    run = session.get(ShortpickExperimentRun, run_id)
    if run is None:
        raise LookupError(f"Shortpick run {run_id} not found.")
    target_horizons = horizons or SHORTPICK_DEFAULT_HORIZONS
    candidates = session.scalars(
        select(ShortpickCandidate).where(ShortpickCandidate.run_id == run_id).order_by(ShortpickCandidate.id.asc())
    ).all()
    parsed_candidates = [
        candidate
        for candidate in candidates
        if candidate.parse_status == "parsed" and candidate.symbol != "PARSE_FAILED"
    ]
    benchmark_sync = _sync_shortpick_benchmarks(session) if parsed_candidates else {"status": "skipped", "reason": "no_parsed_candidates"}
    updated = 0
    for candidate in parsed_candidates:
        market_sync = _sync_shortpick_candidate_market_data(session, candidate)
        benchmark_maps = benchmark_close_maps(session)
        for horizon in target_horizons:
            _upsert_validation_snapshot(
                session,
                run,
                candidate,
                int(horizon),
                benchmark_maps=benchmark_maps,
                market_sync=market_sync,
            )
            updated += 1
    summary = _shortpick_validation_summary(session, run_id=run_id)
    run.summary_payload = {
        **dict(run.summary_payload or {}),
        **summary,
        "benchmark_sync": benchmark_sync,
    }
    session.flush()
    return {"run_id": run_id, "updated_validation_count": updated, "horizons": target_horizons, "summary": summary}


def _upsert_validation_snapshot(
    session: Session,
    run: ShortpickExperimentRun,
    candidate: ShortpickCandidate,
    horizon: int,
    *,
    benchmark_maps: dict[str, dict[Any, float]] | None = None,
    market_sync: dict[str, Any] | None = None,
) -> ShortpickValidationSnapshot:
    existing = session.scalar(
        select(ShortpickValidationSnapshot).where(
            ShortpickValidationSnapshot.candidate_id == candidate.id,
            ShortpickValidationSnapshot.horizon_days == horizon,
        )
    )
    if existing is None:
        existing = ShortpickValidationSnapshot(
            candidate_id=candidate.id,
            horizon_days=horizon,
            status="pending_market_data",
            validation_payload={},
        )
        session.add(existing)
        session.flush()
    bars = _daily_bars_for_symbol(session, candidate.symbol)
    if not bars:
        existing.status = "pending_market_data"
        _clear_validation_metrics(existing)
        existing.validation_payload = {
            "reason": "No daily bars found for candidate symbol.",
            "market_data_sync": market_sync or {},
        }
        return existing
    entry_index = next((idx for idx, bar in enumerate(bars) if bar.observed_at.date() >= run.run_date), None)
    if entry_index is None:
        existing.status = "pending_entry_bar"
        _clear_validation_metrics(existing)
        existing.validation_payload = {
            "reason": "No entry bar at or after run_date.",
            "market_data_sync": market_sync or {},
        }
        return existing
    exit_index = entry_index + horizon
    if exit_index >= len(bars):
        existing.status = "pending_forward_window"
        existing.entry_at = bars[entry_index].observed_at
        existing.entry_close = bars[entry_index].close_price
        existing.exit_at = None
        existing.exit_close = None
        existing.stock_return = None
        existing.benchmark_return = None
        existing.excess_return = None
        existing.max_favorable_return = None
        existing.max_drawdown = None
        existing.validation_payload = {
            "available_forward_bars": max(len(bars) - entry_index - 1, 0),
            "market_data_sync": market_sync or {},
        }
        return existing
    window = bars[entry_index : exit_index + 1]
    entry = window[0]
    exit_bar = window[-1]
    returns = [(bar.close_price / entry.close_price) - 1 for bar in window if entry.close_price]
    stock_return = (exit_bar.close_price / entry.close_price) - 1 if entry.close_price else None
    benchmark_maps = benchmark_maps or benchmark_close_maps(session)
    benchmark_returns = _shortpick_benchmark_returns(
        benchmark_maps=benchmark_maps,
        entry_day=entry.observed_at.date(),
        exit_day=exit_bar.observed_at.date(),
    )
    primary = _shortpick_primary_benchmark()
    primary_return = benchmark_returns.get(primary["symbol"], {}).get("return")
    if primary_return is None:
        existing.status = "pending_benchmark_data"
    else:
        existing.status = "completed"
    existing.entry_at = entry.observed_at
    existing.exit_at = exit_bar.observed_at
    existing.entry_close = entry.close_price
    existing.exit_close = exit_bar.close_price
    existing.stock_return = stock_return
    existing.benchmark_return = primary_return
    existing.excess_return = None if stock_return is None or primary_return is None else stock_return - primary_return
    existing.max_favorable_return = max(returns) if returns else None
    existing.max_drawdown = min(returns) if returns else None
    existing.validation_payload = {
        "benchmark": primary,
        "benchmark_returns": benchmark_returns,
        "market_data_sync": market_sync or {},
        "note": "后验验证只读取行情，不回写主量化推荐或模拟盘。",
    }
    return existing


def _daily_bars_for_symbol(session: Session, symbol: str) -> list[MarketBar]:
    stock = session.scalar(select(Stock).where(Stock.symbol == symbol))
    if stock is None:
        return []
    return session.scalars(
        select(MarketBar)
        .where(MarketBar.stock_id == stock.id, MarketBar.timeframe == "1d")
        .order_by(MarketBar.observed_at.asc(), MarketBar.id.asc())
    ).all()


def _sync_shortpick_benchmarks(session: Session) -> dict[str, Any]:
    existing = benchmark_close_maps(session)
    today = datetime.now(UTC).date()
    current = {
        definition["symbol"]: max(existing.get(definition["symbol"], {}) or {}, default=None)
        for definition in _shortpick_benchmark_definitions()
    }
    if current and all(day is not None and day >= today for day in current.values()):
        return {
            "status": "existing_current",
            "latest_trade_days": {symbol: day.isoformat() for symbol, day in current.items() if day is not None},
        }
    try:
        return sync_benchmark_index_bars(session)
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


def _sync_shortpick_candidate_market_data(session: Session, candidate: ShortpickCandidate) -> dict[str, Any]:
    existing_bars = _daily_bars_for_symbol(session, candidate.symbol)
    latest_day = existing_bars[-1].observed_at.date() if existing_bars else None
    if latest_day is not None and latest_day >= datetime.now(UTC).date():
        return {"status": "existing_current", "bars": len(existing_bars), "latest_trade_day": latest_day.isoformat()}
    try:
        stock = _ensure_shortpick_stock(session, candidate)
        fetch = _fetch_shortpick_daily_market_data(session, candidate.symbol)
        upserted = _upsert_shortpick_market_bars(session, stock=stock, bars=fetch.bars)
    except Exception as exc:
        return {
            "status": "error",
            "reason": str(exc),
            "existing_bars": len(existing_bars),
            "latest_trade_day": latest_day.isoformat() if latest_day else None,
        }
    refreshed_bars = _daily_bars_for_symbol(session, candidate.symbol)
    refreshed_latest_day = refreshed_bars[-1].observed_at.date() if refreshed_bars else None
    return {
        "status": "ok",
        "provider_name": fetch.provider_name,
        "upserted_bars": upserted,
        "bars": len(refreshed_bars),
        "latest_trade_day": refreshed_latest_day.isoformat() if refreshed_latest_day else None,
    }


def _ensure_shortpick_stock(session: Session, candidate: ShortpickCandidate) -> Stock:
    existing = session.scalar(select(Stock).where(Stock.symbol == candidate.symbol))
    profile = resolve_stock_profile(session, symbol=candidate.symbol, preferred_name=candidate.name)
    ticker, _, market = candidate.symbol.partition(".")
    exchange = market.upper() if market else ("SH" if ticker.startswith(("5", "6", "9")) else "SZ")
    if existing is not None:
        existing.name = profile.name or candidate.name or existing.name
        existing.provider_symbol = existing.provider_symbol or candidate.symbol
        existing.listed_date = existing.listed_date or profile.listed_date
        profile_payload = dict(existing.profile_payload or {})
        profile_payload.update(
            {
                "shortpick_profile_source": profile.source,
                "industry": profile.industry or profile_payload.get("industry"),
                "template_key": profile.template_key or profile_payload.get("template_key"),
            }
        )
        existing.profile_payload = profile_payload
        session.flush()
        return existing
    stock_payload = {
        "symbol": candidate.symbol,
        "name": profile.name or candidate.name or candidate.symbol,
        "listed_date": profile.listed_date,
        "profile_source": profile.source,
    }
    lineage = build_lineage(
        stock_payload,
        source_uri=f"shortpick://stock/{candidate.symbol}",
        license_tag="internal-derived",
        usage_scope="internal_research",
        redistribution_scope="none",
    )
    stock = Stock(
        symbol=candidate.symbol,
        ticker=ticker,
        exchange=exchange,
        name=str(stock_payload["name"]),
        provider_symbol=candidate.symbol,
        listed_date=profile.listed_date,
        delisted_date=None,
        status="active",
        profile_payload={
            "industry": profile.industry,
            "template_key": profile.template_key,
            "profile_source": profile.source,
            "shortpick_lab_only": True,
        },
        **lineage,
    )
    session.add(stock)
    session.flush()
    return stock


def _fetch_shortpick_daily_market_data(session: Session, symbol: str) -> Any:
    for fetcher in (_fetch_daily_bars_tushare, lambda active_session, active_symbol: _fetch_daily_bars_akshare(active_symbol)):
        try:
            result = fetcher(session, symbol)
        except Exception:
            result = None
        if result is not None and result.bars:
            return result
    raise RuntimeError(f"{symbol} shortpick market sync returned no daily bars.")


def _upsert_shortpick_market_bars(session: Session, *, stock: Stock, bars: list[dict[str, Any]]) -> int:
    upserted = 0
    for bar_record in bars:
        bar_key = str(bar_record["bar_key"])
        existing = session.scalar(select(MarketBar).where(MarketBar.bar_key == bar_key))
        values = {
            "stock_id": stock.id,
            "timeframe": bar_record["timeframe"],
            "observed_at": bar_record["observed_at"],
            "open_price": bar_record["open_price"],
            "high_price": bar_record["high_price"],
            "low_price": bar_record["low_price"],
            "close_price": bar_record["close_price"],
            "volume": bar_record["volume"],
            "amount": bar_record["amount"],
            "turnover_rate": bar_record.get("turnover_rate"),
            "adj_factor": bar_record.get("adj_factor"),
            "total_mv": bar_record.get("total_mv"),
            "circ_mv": bar_record.get("circ_mv"),
            "pe_ttm": bar_record.get("pe_ttm"),
            "pb": bar_record.get("pb"),
            "raw_payload": {
                **dict(bar_record.get("raw_payload") or {}),
                "shortpick_lab_only": True,
            },
            "source_uri": bar_record["source_uri"],
            "license_tag": bar_record["license_tag"],
            "usage_scope": bar_record["usage_scope"],
            "redistribution_scope": bar_record["redistribution_scope"],
            "lineage_hash": bar_record["lineage_hash"],
        }
        if existing is None:
            session.add(MarketBar(bar_key=bar_key, **values))
        else:
            for key, value in values.items():
                setattr(existing, key, value)
        upserted += 1
    session.flush()
    return upserted


def _shortpick_primary_benchmark() -> dict[str, str]:
    definition = CSI_BENCHMARKS[SHORTPICK_PRIMARY_BENCHMARK_ID]
    return {
        "benchmark_id": SHORTPICK_PRIMARY_BENCHMARK_ID,
        "symbol": definition["symbol"],
        "label": definition["label"],
    }


def _shortpick_benchmark_definitions() -> list[dict[str, str]]:
    definitions = [_shortpick_primary_benchmark()]
    seen = {definitions[0]["symbol"]}
    for benchmark_id in SHORTPICK_RESEARCH_BENCHMARK_IDS:
        definition = CSI_BENCHMARKS.get(benchmark_id)
        if definition is None or definition["symbol"] in seen:
            continue
        seen.add(definition["symbol"])
        definitions.append(
            {
                "benchmark_id": benchmark_id,
                "symbol": definition["symbol"],
                "label": definition["label"],
            }
        )
    return definitions


def _shortpick_benchmark_returns(
    *,
    benchmark_maps: dict[str, dict[Any, float]],
    entry_day: date,
    exit_day: date,
) -> dict[str, dict[str, Any]]:
    returns: dict[str, dict[str, Any]] = {}
    for definition in _shortpick_benchmark_definitions():
        close_map = benchmark_maps.get(definition["symbol"], {})
        benchmark_return = _return_between_close_map(close_map, entry_day=entry_day, exit_day=exit_day)
        returns[definition["symbol"]] = {
            **definition,
            "return": benchmark_return,
            "status": "available" if benchmark_return is not None else "missing_window",
        }
    return returns


def _return_between_close_map(close_map: dict[Any, float], *, entry_day: date, exit_day: date) -> float | None:
    if not close_map:
        return None
    entry_close = _close_on_or_after(close_map, entry_day)
    exit_close = _close_on_or_after(close_map, exit_day)
    if entry_close in {None, 0} or exit_close is None:
        return None
    return float(exit_close) / float(entry_close) - 1


def _close_on_or_after(close_map: dict[Any, float], target_day: date) -> float | None:
    for trade_day in sorted(close_map):
        if trade_day >= target_day:
            return close_map[trade_day]
    return None


def _clear_validation_metrics(snapshot: ShortpickValidationSnapshot) -> None:
    snapshot.entry_at = None
    snapshot.exit_at = None
    snapshot.entry_close = None
    snapshot.exit_close = None
    snapshot.stock_return = None
    snapshot.benchmark_return = None
    snapshot.excess_return = None
    snapshot.max_favorable_return = None
    snapshot.max_drawdown = None


def _shortpick_validation_summary(session: Session, *, run_id: int) -> dict[str, Any]:
    validations = session.scalars(
        select(ShortpickValidationSnapshot)
        .join(ShortpickCandidate, ShortpickValidationSnapshot.candidate_id == ShortpickCandidate.id)
        .where(ShortpickCandidate.run_id == run_id)
        .order_by(ShortpickValidationSnapshot.horizon_days.asc(), ShortpickValidationSnapshot.id.asc())
    ).all()
    status_counts: dict[str, int] = {}
    by_horizon: dict[int, list[ShortpickValidationSnapshot]] = {}
    completed: list[ShortpickValidationSnapshot] = []
    for validation in validations:
        status_counts[validation.status] = status_counts.get(validation.status, 0) + 1
        by_horizon.setdefault(validation.horizon_days, []).append(validation)
        if validation.status == "completed":
            completed.append(validation)
    horizon_summary: dict[str, dict[str, Any]] = {}
    for horizon, items in sorted(by_horizon.items()):
        completed_items = [item for item in items if item.status == "completed"]
        stock_returns = [float(item.stock_return) for item in completed_items if item.stock_return is not None]
        excess_returns = [float(item.excess_return) for item in completed_items if item.excess_return is not None]
        horizon_summary[str(horizon)] = {
            "validation_count": len(items),
            "completed_count": len(completed_items),
            "mean_stock_return": _mean_or_none(stock_returns),
            "mean_excess_return": _mean_or_none(excess_returns),
            "positive_excess_rate": (
                round(sum(1 for item in excess_returns if item > 0) / len(excess_returns), 6)
                if excess_returns
                else None
            ),
        }
    return {
        "validation_status_counts": status_counts,
        "completed_validation_count": len(completed),
        "measured_candidate_count": len({item.candidate_id for item in completed}),
        "validation_by_horizon": horizon_summary,
        "primary_benchmark": _shortpick_primary_benchmark(),
    }


def _mean_or_none(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def serialize_shortpick_run(session: Session, run: ShortpickExperimentRun, *, include_raw: bool) -> dict[str, Any]:
    return {
        "id": run.id,
        "run_key": run.run_key,
        "run_date": run.run_date,
        "prompt_version": run.prompt_version,
        "information_mode": run.information_mode,
        "status": run.status,
        "trigger_source": run.trigger_source,
        "triggered_by": run.triggered_by,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "failed_at": run.failed_at,
        "model_config": dict(run.model_config or {}),
        "summary": dict(run.summary_payload or {}),
        "rounds": [
            serialize_shortpick_round(item, include_raw=include_raw)
            for item in session.scalars(
                select(ShortpickModelRound).where(ShortpickModelRound.run_id == run.id).order_by(ShortpickModelRound.id.asc())
            ).all()
        ],
        "consensus": _serialize_consensus(
            session.scalar(
                select(ShortpickConsensusSnapshot)
                .where(ShortpickConsensusSnapshot.run_id == run.id)
                .order_by(ShortpickConsensusSnapshot.id.desc())
            )
        ),
        "candidates": [
            serialize_shortpick_candidate(session, item, include_raw=include_raw)
            for item in session.scalars(
                select(ShortpickCandidate).where(ShortpickCandidate.run_id == run.id).order_by(ShortpickCandidate.id.asc())
            ).all()
        ],
    }


def serialize_shortpick_round(round_record: ShortpickModelRound, *, include_raw: bool) -> dict[str, Any]:
    pick = round_record.parsed_payload.get("primary_pick") if isinstance(round_record.parsed_payload, dict) else {}
    return {
        "id": round_record.id,
        "round_key": round_record.round_key,
        "provider_name": round_record.provider_name,
        "model_name": round_record.model_name,
        "executor_kind": round_record.executor_kind,
        "round_index": round_record.round_index,
        "status": round_record.status,
        "symbol": _normalize_symbol(str(pick.get("symbol") or "")) if isinstance(pick, dict) and pick.get("symbol") else None,
        "stock_name": str(pick.get("name") or "") if isinstance(pick, dict) else None,
        "theme": str(pick.get("theme") or "") if isinstance(pick, dict) else None,
        "thesis": str(pick.get("thesis") or "") if isinstance(pick, dict) else None,
        "confidence": _coerce_float(pick.get("confidence")) if isinstance(pick, dict) else None,
        "sources": round_record.sources_payload,
        "artifact_id": round_record.artifact_id,
        "error_message": round_record.error_message if include_raw else None,
        "raw_answer": round_record.raw_answer if include_raw else None,
        "started_at": round_record.started_at,
        "completed_at": round_record.completed_at,
    }


def serialize_shortpick_candidate(session: Session, candidate: ShortpickCandidate, *, include_raw: bool) -> dict[str, Any]:
    round_record = session.get(ShortpickModelRound, candidate.round_id) if candidate.round_id else None
    return {
        "id": candidate.id,
        "candidate_key": candidate.candidate_key,
        "run_id": candidate.run_id,
        "round_id": candidate.round_id,
        "symbol": candidate.symbol,
        "name": candidate.name,
        "normalized_theme": candidate.normalized_theme,
        "horizon_trading_days": candidate.horizon_trading_days,
        "confidence": candidate.confidence,
        "thesis": candidate.thesis,
        "catalysts": list(candidate.catalysts or []),
        "invalidation": list(candidate.invalidation or []),
        "risks": list(candidate.risks or []),
        "sources": list(candidate.sources_payload or []),
        "novelty_note": candidate.novelty_note,
        "limitations": list(candidate.limitations or []),
        "convergence_group": candidate.convergence_group,
        "research_priority": candidate.research_priority,
        "parse_status": candidate.parse_status,
        "is_system_external": candidate.is_system_external,
        "validations": [
            _serialize_validation(item)
            for item in session.scalars(
                select(ShortpickValidationSnapshot)
                .where(ShortpickValidationSnapshot.candidate_id == candidate.id)
                .order_by(ShortpickValidationSnapshot.horizon_days.asc())
            ).all()
        ],
        "raw_round": serialize_shortpick_round(round_record, include_raw=include_raw) if round_record is not None else None,
    }


def list_shortpick_runs(session: Session, *, limit: int = 20, include_raw: bool = False) -> dict[str, Any]:
    runs = session.scalars(
        select(ShortpickExperimentRun).order_by(ShortpickExperimentRun.started_at.desc(), ShortpickExperimentRun.id.desc()).limit(limit)
    ).all()
    return {"generated_at": utcnow(), "items": [serialize_shortpick_run(session, run, include_raw=include_raw) for run in runs]}


def get_shortpick_run(session: Session, run_id: int, *, include_raw: bool) -> dict[str, Any]:
    run = session.get(ShortpickExperimentRun, run_id)
    if run is None:
        raise LookupError(f"Shortpick run {run_id} not found.")
    return serialize_shortpick_run(session, run, include_raw=include_raw)


def list_shortpick_candidates(
    session: Session,
    *,
    run_id: int | None = None,
    model: str | None = None,
    priority: str | None = None,
    validation_status: str | None = None,
    limit: int = 100,
    include_raw: bool = False,
) -> dict[str, Any]:
    query = select(ShortpickCandidate).order_by(ShortpickCandidate.created_at.desc(), ShortpickCandidate.id.desc()).limit(limit)
    if run_id is not None:
        query = query.where(ShortpickCandidate.run_id == run_id)
    if priority:
        query = query.where(ShortpickCandidate.research_priority == priority)
    candidates = session.scalars(query).all()
    if model:
        normalized_model = model.lower()
        candidates = [
            item for item in candidates
            if (
                round_record := (session.get(ShortpickModelRound, item.round_id) if item.round_id else None)
            ) is not None
            and (normalized_model in round_record.provider_name.lower() or normalized_model in round_record.model_name.lower())
        ]
    if validation_status:
        candidates = [
            item for item in candidates
            if any(
                validation.status == validation_status
                for validation in session.scalars(
                    select(ShortpickValidationSnapshot).where(ShortpickValidationSnapshot.candidate_id == item.id)
                ).all()
            )
        ]
    return {"generated_at": utcnow(), "items": [serialize_shortpick_candidate(session, item, include_raw=include_raw) for item in candidates]}


def get_shortpick_candidate(session: Session, candidate_id: int, *, include_raw: bool) -> dict[str, Any]:
    candidate = session.get(ShortpickCandidate, candidate_id)
    if candidate is None:
        raise LookupError(f"Shortpick candidate {candidate_id} not found.")
    return serialize_shortpick_candidate(session, candidate, include_raw=include_raw)


def _serialize_consensus(snapshot: ShortpickConsensusSnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "id": snapshot.id,
        "snapshot_key": snapshot.snapshot_key,
        "artifact_id": snapshot.artifact_id,
        "generated_at": snapshot.generated_at,
        "status": snapshot.status,
        "stock_convergence": snapshot.stock_convergence,
        "theme_convergence": snapshot.theme_convergence,
        "source_diversity": snapshot.source_diversity,
        "model_independence": snapshot.model_independence,
        "novelty_score": snapshot.novelty_score,
        "research_priority": snapshot.research_priority,
        "summary": dict(snapshot.summary_payload or {}),
    }


def _serialize_validation(snapshot: ShortpickValidationSnapshot) -> dict[str, Any]:
    payload = dict(snapshot.validation_payload or {})
    benchmark = payload.get("benchmark") if isinstance(payload.get("benchmark"), dict) else _shortpick_primary_benchmark()
    benchmark_returns = payload.get("benchmark_returns") if isinstance(payload.get("benchmark_returns"), dict) else {}
    return {
        "id": snapshot.id,
        "horizon_days": snapshot.horizon_days,
        "status": snapshot.status,
        "entry_at": snapshot.entry_at,
        "exit_at": snapshot.exit_at,
        "entry_close": snapshot.entry_close,
        "exit_close": snapshot.exit_close,
        "stock_return": snapshot.stock_return,
        "benchmark_return": snapshot.benchmark_return,
        "excess_return": snapshot.excess_return,
        "max_favorable_return": snapshot.max_favorable_return,
        "max_drawdown": snapshot.max_drawdown,
        "benchmark_symbol": benchmark.get("symbol"),
        "benchmark_label": benchmark.get("label"),
        "benchmark_returns": benchmark_returns,
    }


def _write_round_artifact(
    session: Session,
    run: ShortpickExperimentRun,
    round_record: ShortpickModelRound,
    *,
    prompt: str,
) -> None:
    root = _artifact_root(session)
    write_shortpick_lab_artifact(
        artifact_id=str(round_record.artifact_id),
        root=root,
        payload={
            "artifact_id": round_record.artifact_id,
            "artifact_type": "shortpick_lab",
            "run_key": run.run_key,
            "round_key": round_record.round_key,
            "prompt_version": run.prompt_version,
            "information_mode": run.information_mode,
            "prompt": prompt,
            "provider_name": round_record.provider_name,
            "model_name": round_record.model_name,
            "executor_kind": round_record.executor_kind,
            "status": round_record.status,
            "raw_answer": round_record.raw_answer,
            "parsed_payload": round_record.parsed_payload,
            "sources": round_record.sources_payload,
            "error_message": round_record.error_message,
            "generated_at": utcnow().isoformat(),
            "boundary": "independent_research_lab_no_main_pool_write",
        },
    )


def _write_consensus_artifact(
    session: Session,
    run: ShortpickExperimentRun,
    snapshot: ShortpickConsensusSnapshot,
) -> None:
    root = _artifact_root(session)
    write_shortpick_lab_artifact(
        artifact_id=str(snapshot.artifact_id),
        root=root,
        payload={
            "artifact_id": snapshot.artifact_id,
            "artifact_type": "shortpick_lab",
            "run_key": run.run_key,
            "snapshot_key": snapshot.snapshot_key,
            "generated_at": snapshot.generated_at.isoformat(),
            "scores": {
                "stock_convergence": snapshot.stock_convergence,
                "theme_convergence": snapshot.theme_convergence,
                "source_diversity": snapshot.source_diversity,
                "model_independence": snapshot.model_independence,
                "novelty_score": snapshot.novelty_score,
            },
            "research_priority": snapshot.research_priority,
            "summary": snapshot.summary_payload,
            "boundary": "model_consensus_is_research_priority_not_trade_confidence",
        },
    )


def _artifact_root(session: Session) -> Path:
    bind = session.get_bind()
    return artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)


def _normalize_symbol(value: str) -> str:
    text = value.strip().upper()
    if text in {"", "NONE"}:
        return "PARSE_FAILED"
    match = re.search(r"(\d{6})(?:\.(SH|SZ|BJ))?", text)
    if not match:
        return text[:32]
    ticker = match.group(1)
    suffix = match.group(2)
    if not suffix:
        suffix = "SH" if ticker.startswith(("5", "6", "9")) else "SZ"
    return f"{ticker}.{suffix}"


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_sources(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sources: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source = {
            "title": _coerce_text(item.get("title")),
            "url": _coerce_text(item.get("url")),
            "published_at": _coerce_text(item.get("published_at")),
            "why_it_matters": _coerce_text(item.get("why_it_matters") or item.get("relevance")),
        }
        source.update(_source_credibility(source["url"]))
        sources.append(source)
    return sources


def _source_credibility(url: str | None) -> dict[str, Any]:
    normalized = (url or "").strip()
    checked_at = utcnow().isoformat()
    if not normalized:
        return {
            "credibility_status": "missing_url",
            "credibility_reason": "source omitted url",
            "checked_at": checked_at,
        }
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {
            "credibility_status": "suspicious",
            "credibility_reason": "invalid url format",
            "checked_at": checked_at,
        }
    if _looks_like_placeholder_url(normalized):
        return {
            "credibility_status": "suspicious",
            "credibility_reason": "placeholder-like url pattern",
            "checked_at": checked_at,
        }
    if parsed.hostname and parsed.hostname.endswith(".example"):
        return {
            "credibility_status": "suspicious",
            "credibility_reason": "reserved example domain",
            "checked_at": checked_at,
        }
    return _probe_source_url(normalized, checked_at=checked_at)


def _looks_like_placeholder_url(url: str) -> bool:
    return any(pattern.search(url) for pattern in SUSPICIOUS_SOURCE_PATTERNS)


def _probe_source_url(url: str, *, checked_at: str) -> dict[str, Any]:
    for method in ("HEAD", "GET"):
        http_request = request.Request(
            url,
            headers={
                "User-Agent": "ashare-shortpick-lab-source-check/1.0",
                **({"Range": "bytes=0-0"} if method == "GET" else {}),
            },
            method=method,
        )
        try:
            with urlopen(
                http_request,
                timeout=SHORTPICK_SOURCE_CHECK_TIMEOUT_SECONDS,
                disable_proxies=True,
            ) as response:
                status = int(getattr(response, "status", 200) or 200)
            return {
                "credibility_status": "verified" if status < 400 else "unreachable",
                "credibility_reason": f"{method} HTTP {status}",
                "http_status": status,
                "checked_at": checked_at,
            }
        except HTTPError as exc:
            if method == "HEAD" and exc.code in {403, 405}:
                continue
            if exc.code in {401, 403}:
                return {
                    "credibility_status": "reachable_restricted",
                    "credibility_reason": f"{method} HTTP {exc.code}",
                    "http_status": exc.code,
                    "checked_at": checked_at,
                }
            return {
                "credibility_status": "unreachable",
                "credibility_reason": f"{method} HTTP {exc.code}",
                "http_status": exc.code,
                "checked_at": checked_at,
            }
        except (TimeoutError, URLError, OSError) as exc:
            if method == "HEAD":
                continue
            return {
                "credibility_status": "unreachable",
                "credibility_reason": str(getattr(exc, "reason", exc))[:160],
                "checked_at": checked_at,
            }
    return {
        "credibility_status": "unchecked",
        "credibility_reason": "source check skipped",
        "checked_at": checked_at,
    }


def _infer_theme(pick: dict[str, Any]) -> str | None:
    catalysts = _coerce_string_list(pick.get("catalysts"))
    if catalysts:
        return catalysts[0][:128]
    thesis = _coerce_text(pick.get("thesis"))
    return thesis[:80] if thesis else None


def _is_system_external(session: Session, symbol: str) -> bool:
    if symbol == "PARSE_FAILED":
        return True
    active_follow = session.scalar(
        select(WatchlistFollow).where(WatchlistFollow.symbol == symbol, WatchlistFollow.status == "active")
    )
    if active_follow is not None:
        return False
    recommended = session.scalar(
        select(Recommendation.id)
        .join(Stock)
        .where(Stock.symbol == symbol)
        .order_by(*recommendation_recency_ordering())
        .limit(1)
    )
    return recommended is None


def _host_from_url(url: str) -> str:
    stripped = url.replace("https://", "").replace("http://", "")
    return stripped.split("/", 1)[0].lower()
