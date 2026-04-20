from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ashare_evidence.dashboard import bootstrap_dashboard_demo
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.llm_service import run_follow_up_analysis
from ashare_evidence.runtime_config import (
    create_model_api_key,
    get_runtime_settings,
    upsert_provider_credential,
)


class _FailoverTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, base_url: str, api_key: str, model_name: str, prompt: str) -> str:
        self.calls.append((base_url, model_name))
        if len(self.calls) == 1:
            raise RuntimeError("primary key upstream timeout")
        return f"{model_name}: 已基于结构化证据生成回答。"


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
                access_token="tushare-demo-token",
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

    def test_follow_up_analysis_supports_default_key_and_failover(self) -> None:
        transport = _FailoverTransport()
        with session_scope(self.database_url) as session:
            bootstrap_dashboard_demo(session)
            create_model_api_key(
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
                failover_enabled=True,
                transport=transport,
            )

        self.assertTrue(result["failover_used"])
        self.assertEqual(result["selected_key"]["name"], "backup-key")
        self.assertEqual(len(result["attempted_keys"]), 2)
        self.assertEqual(result["attempted_keys"][0]["status"], "failed")
        self.assertEqual(result["attempted_keys"][1]["status"], "success")
        self.assertEqual(transport.calls[0][0], "https://primary.example.com/v1")
        self.assertEqual(transport.calls[1][0], "https://backup.example.com/v1")


if __name__ == "__main__":
    unittest.main()
