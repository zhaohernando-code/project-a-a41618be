from __future__ import annotations

import json
from typing import Any, Protocol
from urllib import request
from urllib.error import HTTPError, URLError

from sqlalchemy.orm import Session

from ashare_evidence.dashboard import get_stock_dashboard
from ashare_evidence.runtime_config import record_model_api_key_result, resolve_llm_key_candidates


class LLMTransport(Protocol):
    def complete(self, *, base_url: str, api_key: str, model_name: str, prompt: str) -> str:
        ...


class OpenAICompatibleTransport:
    def complete(self, *, base_url: str, api_key: str, model_name: str, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "temperature": 0.2,
            }
        ).encode("utf-8")
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
            with request.urlopen(http_request, timeout=30) as response:
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


def _build_follow_up_prompt(summary: dict[str, Any], question: str) -> str:
    template = summary["follow_up"]["copy_prompt"]
    return template.replace(
        "<在这里替换成你的追问>",
        question.strip() or "请解释当前建议最容易失效的条件。",
    )


def run_follow_up_analysis(
    session: Session,
    *,
    symbol: str,
    question: str,
    model_api_key_id: int | None = None,
    failover_enabled: bool = True,
    transport: LLMTransport | None = None,
) -> dict[str, Any]:
    transport = transport or OpenAICompatibleTransport()
    summary = get_stock_dashboard(session, symbol)
    prompt = _build_follow_up_prompt(summary, question)
    candidates = resolve_llm_key_candidates(session, model_api_key_id)
    if not candidates:
        raise ValueError("尚未配置可用的大模型 API Key。")

    attempted: list[dict[str, Any]] = []
    last_error: str | None = None
    for index, key in enumerate(candidates):
        try:
            answer = transport.complete(
                base_url=key.base_url,
                api_key=key.api_key,
                model_name=key.model_name,
                prompt=prompt,
            )
            record_model_api_key_result(session, key.id, status="healthy", error_message=None)
            session.commit()
            attempted.append(
                {
                    "key_id": key.id,
                    "name": key.name,
                    "provider_name": key.provider_name,
                    "model_name": key.model_name,
                    "status": "success",
                    "error": None,
                }
            )
            return {
                "symbol": symbol,
                "question": question.strip() or "请解释当前建议最容易失效的条件。",
                "answer": answer,
                "selected_key": {
                    "id": key.id,
                    "name": key.name,
                    "provider_name": key.provider_name,
                    "model_name": key.model_name,
                    "base_url": key.base_url,
                },
                "failover_used": index > 0,
                "attempted_keys": attempted,
            }
        except Exception as exc:
            last_error = str(exc)
            record_model_api_key_result(session, key.id, status="failed", error_message=last_error)
            session.commit()
            attempted.append(
                {
                    "key_id": key.id,
                    "name": key.name,
                    "provider_name": key.provider_name,
                    "model_name": key.model_name,
                    "status": "failed",
                    "error": last_error,
                }
            )
            if not failover_enabled:
                break

    raise RuntimeError(last_error or "所有可用的大模型 API Key 都调用失败。")
