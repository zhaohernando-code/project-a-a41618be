from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from ashare_evidence.dashboard import get_stock_dashboard
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.llm_service import (
    OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
    OpenAICompatibleTransport,
    run_follow_up_analysis,
)
from ashare_evidence.research_artifact_store import artifact_root_from_database_url, read_manual_research_artifact
from ashare_evidence.runtime_config import (
    create_model_api_key,
    get_builtin_llm_executor_config,
    get_runtime_settings,
    upsert_provider_credential,
)
from tests.fixtures import seed_recommendation_fixture


class _FailoverTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, base_url: str, api_key: str, model_name: str, prompt: str) -> str:
        self.calls.append((base_url, model_name))
        if len(self.calls) == 1:
            raise RuntimeError("primary key upstream timeout")
        return f"{model_name}: 已基于结构化证据生成回答。"


class _FakeResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload.encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class RuntimeConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "runtime.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_runtime_defaults_expose_self_hosted_cache_policy(self) -> None:
        with session_scope(self.database_url) as session:
            payload = get_runtime_settings(session)

        self.assertEqual(payload["deployment_mode"], "self_hosted_server")
        self.assertEqual(payload["storage_engine"], "SQLite")
        self.assertEqual(payload["cache_backend"], "Redis")
        self.assertTrue(payload["watchlist_cache_only"])
        ttl_by_dataset = {item["dataset"]: item["ttl_seconds"] for item in payload["cache_policies"]}
        self.assertEqual(ttl_by_dataset["quote"], 5)
        self.assertEqual(ttl_by_dataset["kline"], 60)
        self.assertEqual(ttl_by_dataset["financial_report"], 86400)
        field_names = {item["canonical_field"] for item in payload["field_mappings"]}
        self.assertIn("last_price", field_names)
        self.assertIn("report_period", field_names)

    def test_provider_credentials_flow_into_runtime_status(self) -> None:
        with session_scope(self.database_url) as session:
            upsert_provider_credential(
                session,
                "tushare",
                access_token="tushare-live-token",
                base_url="https://api.tushare.pro",
                enabled=True,
                notes="一期使用结构化财报与日线。",
            )

        with session_scope(self.database_url) as session:
            payload = get_runtime_settings(session)

        tushare = next(item for item in payload["provider_credentials"] if item["provider_name"] == "tushare")
        self.assertTrue(tushare["token_configured"])
        self.assertEqual(tushare["masked_token"], "tush...oken")
        source_view = next(item for item in payload["data_sources"] if item["provider_name"] == "tushare")
        self.assertTrue(source_view["credential_configured"])
        self.assertEqual(source_view["base_url"], "https://api.tushare.pro")
        self.assertTrue(source_view["supports_intraday"])
        self.assertTrue(source_view["intraday_runtime_ready"])

    def test_akshare_runtime_status_reflects_real_adapter_readiness(self) -> None:
        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.runtime_config.akshare_runtime_ready", return_value=True):
                payload = get_runtime_settings(session)

        source_view = next(item for item in payload["data_sources"] if item["provider_name"] == "akshare")
        self.assertFalse(source_view["credential_required"])
        self.assertTrue(source_view["runtime_ready"])
        self.assertEqual(source_view["status_label"], "已接入")

    def test_builtin_llm_executor_prefers_local_codex_cli_when_available(self) -> None:
        with patch.dict("os.environ", {}, clear=False), patch(
            "ashare_evidence.runtime_config.shutil.which",
            return_value="/usr/local/bin/codex",
        ), patch(
            "ashare_evidence.runtime_config.Path.is_file",
            return_value=True,
        ), patch(
            "ashare_evidence.runtime_config.os.access",
            return_value=True,
        ):
            builtin = get_builtin_llm_executor_config()

        self.assertTrue(builtin["enabled"])
        self.assertEqual(builtin["transport_kind"], "codex_cli")
        self.assertEqual(builtin["model_name"], "gpt-5.5")
        self.assertEqual(builtin["codex_bin"], "/usr/local/bin/codex")
        self.assertEqual(builtin["base_url"], "codex-cli://local")

    def test_follow_up_analysis_supports_default_key_and_failover(self) -> None:
        transport = _FailoverTransport()
        with session_scope(self.database_url) as session:
            seed_recommendation_fixture(session, "600519.SH")
            primary_key = create_model_api_key(
                session,
                name="primary-key",
                provider_name="openai",
                model_name="gpt-4.1-mini",
                base_url="https://primary.example.com/v1",
                api_key="primary-secret",
                enabled=True,
                priority=10,
                make_default=True,
            )
            create_model_api_key(
                session,
                name="backup-key",
                provider_name="openai",
                model_name="gpt-4.1",
                base_url="https://backup.example.com/v1",
                api_key="backup-secret",
                enabled=True,
                priority=20,
                make_default=False,
            )

        with session_scope(self.database_url) as session:
            result = run_follow_up_analysis(
                session,
                symbol="600519.SH",
                question="请解释当前建议的主要风险。",
                model_api_key_id=primary_key["id"],
                failover_enabled=True,
                transport=transport,
            )

        self.assertIsInstance(result["request_id"], int)
        self.assertTrue(result["request_key"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["executor_kind"], "configured_api_key")
        self.assertTrue(result["failover_used"])
        self.assertEqual(result["selected_key"]["name"], "backup-key")
        self.assertEqual(len(result["attempted_keys"]), 2)
        self.assertEqual(result["attempted_keys"][0]["status"], "failed")
        self.assertEqual(result["attempted_keys"][1]["status"], "success")
        self.assertEqual(transport.calls[0][0], "https://primary.example.com/v1")
        self.assertEqual(transport.calls[1][0], "https://backup.example.com/v1")
        self.assertTrue(result["manual_review_artifact_id"])

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")
            manual_review = dashboard["recommendation"]["manual_llm_review"]
            self.assertEqual(manual_review["status"], "completed")
            self.assertEqual(manual_review["request_id"], result["request_id"])
            self.assertEqual(manual_review["request_key"], result["request_key"])
            self.assertEqual(manual_review["executor_kind"], "configured_api_key")
            self.assertEqual(manual_review["artifact_id"], result["manual_review_artifact_id"])
            self.assertEqual(dashboard["follow_up"]["research_packet"]["manual_request_id"], result["request_id"])
            self.assertEqual(dashboard["follow_up"]["research_packet"]["manual_request_key"], result["request_key"])
            self.assertEqual(dashboard["follow_up"]["research_packet"]["manual_review_artifact_id"], result["manual_review_artifact_id"])
            bind = session.get_bind()
            artifact_root = artifact_root_from_database_url(bind.url.render_as_string(hide_password=False) if bind else None)
            artifact = read_manual_research_artifact(result["manual_review_artifact_id"], root=artifact_root)
            self.assertEqual(artifact.stock_symbol, "600519.SH")
            self.assertEqual(artifact.question, "请解释当前建议的主要风险。")
            self.assertEqual(artifact.request_key, result["request_key"])

    def test_openai_compatible_transport_uses_extended_timeout(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(target, *, timeout: int, disable_proxies: bool = False):
            captured["timeout"] = timeout
            captured["disable_proxies"] = disable_proxies
            captured["payload"] = json.loads(target.data.decode("utf-8"))
            return _FakeResponse('{"choices":[{"message":{"content":"ok"}}]}')

        with patch("ashare_evidence.llm_service.urlopen", side_effect=fake_urlopen):
            answer = OpenAICompatibleTransport().complete(
                base_url="https://api.deepseek.com",
                api_key="secret",
                model_name="deepseek-v4-pro",
                prompt="请给出一个简短回答。",
            )

        self.assertEqual(answer, "ok")
        self.assertEqual(captured["timeout"], OPENAI_COMPATIBLE_TIMEOUT_SECONDS)
        self.assertTrue(bool(captured["disable_proxies"]))
        self.assertNotIn("enable_search", captured["payload"])

    def test_openai_compatible_transport_can_enable_search(self) -> None:
        captured: dict[str, object] = {}

        def fake_urlopen(target, *, timeout: int, disable_proxies: bool = False):
            captured["payload"] = json.loads(target.data.decode("utf-8"))
            return _FakeResponse('{"choices":[{"message":{"content":"ok"}}]}')

        with patch("ashare_evidence.llm_service.urlopen", side_effect=fake_urlopen):
            OpenAICompatibleTransport().complete(
                base_url="https://api.deepseek.com",
                api_key="secret",
                model_name="deepseek-v4-pro",
                prompt="请联网搜索。",
                enable_search=True,
            )

        self.assertEqual(captured["payload"]["enable_search"], True)


if __name__ == "__main__":
    unittest.main()
