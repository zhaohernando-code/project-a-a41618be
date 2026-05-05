from __future__ import annotations

import json
import os
from typing import Any, Protocol
from urllib import request
from urllib.error import HTTPError, URLError

from ashare_evidence.http_client import urlopen

OPENAI_COMPATIBLE_TIMEOUT_SECONDS = 75
ANTHROPIC_COMPATIBLE_TIMEOUT_SECONDS = 90

DEEPSEEK_ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
DEEPSEEK_V4_PRO = "deepseek-v4-pro[1m]"
DEEPSEEK_V4_FLASH = "deepseek-v4-flash"


class LLMTransport(Protocol):
    def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        prompt: str,
        system: str | None = None,
        enable_search: bool = False,
    ) -> str:
        ...


class OpenAICompatibleTransport:
    def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        prompt: str,
        system: str | None = None,
        enable_search: bool = False,
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.1,
        }
        if enable_search:
            body["enable_search"] = True
        payload = json.dumps(body).encode("utf-8")
        endpoint = f"{base_url.rstrip('/')}/chat/completions"
        http_request = request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=OPENAI_COMPATIBLE_TIMEOUT_SECONDS, disable_proxies=True) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") or str(exc)
            raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"LLM request failed: {exc.reason}") from exc

        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError("LLM response missing choices.")
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                str(part.get("text", "")).strip()
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            joined = "\n".join(part for part in text_parts if part)
            if joined:
                return joined
        raise RuntimeError("LLM response did not contain text content.")


class AnthropicCompatibleTransport:
    def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        prompt: str,
        system: str | None = None,
        enable_search: bool = False,
    ) -> str:
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        body: dict[str, Any] = {
            "model": model_name,
            "max_tokens": 2048,
            "messages": messages,
        }
        if system:
            body["system"] = system
        payload = json.dumps(body).encode("utf-8")
        endpoint = f"{base_url.rstrip('/')}/messages"
        http_request = request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=ANTHROPIC_COMPATIBLE_TIMEOUT_SECONDS, disable_proxies=True) as response:
                resp_body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") or str(exc)
            raise RuntimeError(f"Anthropic request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Anthropic request failed: {exc.reason}") from exc

        content_blocks = resp_body.get("content", [])
        text_parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
        result = "\n".join(part.strip() for part in text_parts if part.strip())
        if not result:
            raise RuntimeError("Anthropic response did not contain text content.")
        return result


def _resolve_deepseek_config() -> tuple[str, str]:
    api_key = os.getenv("ANTHROPIC_AUTH_TOKEN", "").strip()
    base_url = os.getenv("ANTHROPIC_BASE_URL", DEEPSEEK_ANTHROPIC_BASE_URL).strip().rstrip("/")
    return base_url, api_key


def route_model(task: str) -> tuple[LLMTransport, str, str, str]:
    base_url, api_key = _resolve_deepseek_config()
    if api_key and "deepseek" in base_url.lower():
        transport: LLMTransport = AnthropicCompatibleTransport()
        if task in ("announcement_earnings", "announcement_capital_action", "financial_analysis"):
            return transport, base_url, api_key, DEEPSEEK_V4_PRO
        return transport, base_url, api_key, DEEPSEEK_V4_FLASH
    from ashare_evidence.runtime_config import get_builtin_llm_executor_config

    cfg = get_builtin_llm_executor_config()
    if not cfg["enabled"]:
        raise RuntimeError("No LLM transport available: neither DeepSeek nor builtin config is enabled.")
    if cfg["transport_kind"] == "codex_cli":
        raise RuntimeError(
            "codex_cli transport does not support structured analysis. "
            "Set ANTHROPIC_AUTH_TOKEN to use DeepSeek or configure an OpenAI-compatible API key."
        )
    return OpenAICompatibleTransport(), cfg["base_url"], cfg["api_key"], cfg["model_name"]


def _build_follow_up_prompt(summary: dict[str, Any], question: str) -> str:
    template = summary["follow_up"]["copy_prompt"]
    return template.replace(
        "<在这里替换成你的追问>",
        question.strip() or "请解释当前建议最容易失效的条件。",
    )


def run_follow_up_analysis(
    session: Any,
    *,
    symbol: str,
    question: str,
    model_api_key_id: int | None = None,
    failover_enabled: bool = True,
    transport: LLMTransport | None = None,
) -> dict[str, Any]:
    from ashare_evidence.manual_research_workflow import run_follow_up_analysis_compat

    return run_follow_up_analysis_compat(
        session,
        symbol=symbol,
        question=question,
        model_api_key_id=model_api_key_id,
        failover_enabled=failover_enabled,
        transport=transport if transport is not None else OpenAICompatibleTransport(),
    )
