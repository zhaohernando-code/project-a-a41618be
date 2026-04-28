from __future__ import annotations

import json
from typing import Any, Protocol
from urllib import request
from urllib.error import HTTPError, URLError

from sqlalchemy.orm import Session

from ashare_evidence.http_client import urlopen

OPENAI_COMPATIBLE_TIMEOUT_SECONDS = 75


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
            with urlopen(http_request, timeout=OPENAI_COMPATIBLE_TIMEOUT_SECONDS) as response:
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
    from ashare_evidence.manual_research_workflow import run_follow_up_analysis_compat

    return run_follow_up_analysis_compat(
        session,
        symbol=symbol,
        question=question,
        model_api_key_id=model_api_key_id,
        failover_enabled=failover_enabled,
        transport=transport if transport is not None else OpenAICompatibleTransport(),
    )
