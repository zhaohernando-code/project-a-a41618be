from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from fastapi import HTTPException
from starlette.requests import Request

from ashare_evidence.access import require_beta_access, require_beta_write_access
from ashare_evidence.api import create_app
from ashare_evidence.dashboard import list_candidate_recommendations
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.watchlist import add_watchlist_symbol, list_watchlist_entries
from tests.fixtures import seed_recommendation_fixture, seed_watchlist_fixture


class BetaAccessApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "api-access.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)
        self.original_mode = os.environ.get("ASHARE_BETA_ACCESS_MODE")
        self.original_allowlist = os.environ.get("ASHARE_BETA_ALLOWLIST")
        self.original_header = os.environ.get("ASHARE_BETA_ACCESS_HEADER")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        self._restore_env("ASHARE_BETA_ACCESS_MODE", self.original_mode)
        self._restore_env("ASHARE_BETA_ALLOWLIST", self.original_allowlist)
        self._restore_env("ASHARE_BETA_ACCESS_HEADER", self.original_header)

    @staticmethod
    def _restore_env(key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    @staticmethod
    def _build_request(headers: dict[str, str] | None = None) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/",
                "headers": [
                    (key.lower().encode("utf-8"), value.encode("utf-8"))
                    for key, value in (headers or {}).items()
                ],
            }
        )

    def test_dashboard_routes_require_beta_key_when_allowlist_enabled(self) -> None:
        os.environ["ASHARE_BETA_ACCESS_MODE"] = "allowlist"
        os.environ["ASHARE_BETA_ALLOWLIST"] = "viewer-token:viewer,operator-token:operator"
        os.environ["ASHARE_BETA_ACCESS_HEADER"] = "X-Ashare-Beta-Key"

        with self.assertRaises(HTTPException) as denied:
            require_beta_access(self._build_request())
        self.assertEqual(denied.exception.status_code, 403)
        self.assertIn("beta access denied", denied.exception.detail)

        viewer_access = require_beta_access(self._build_request({"X-Ashare-Beta-Key": "viewer-token"}))
        self.assertEqual(viewer_access.role, "viewer")
        with self.assertRaises(HTTPException) as viewer_write_denied:
            require_beta_write_access(viewer_access)
        self.assertEqual(viewer_write_denied.exception.status_code, 403)

        operator_access = require_beta_access(self._build_request({"X-Ashare-Beta-Key": "operator-token"}))
        self.assertEqual(operator_access.role, "operator")
        self.assertEqual(require_beta_write_access(operator_access), operator_access)

        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            allowed = list_candidate_recommendations(session, limit=8)
        self.assertGreaterEqual(len(allowed["items"]), 1)

        with session_scope(self.database_url) as session:
            seed_recommendation_fixture(session, "688981.SH")
            operator_write = add_watchlist_symbol(session, "688981", stock_name="中芯国际")
        self.assertEqual(operator_write["symbol"], "688981.SH")

        with session_scope(self.database_url) as session:
            watchlist = list_watchlist_entries(session)
        self.assertIn("688981.SH", {item["symbol"] for item in watchlist["items"]})

    def test_manual_research_create_and_execute_allow_analyst_but_governance_actions_stay_operator_only(self) -> None:
        os.environ["ASHARE_BETA_ACCESS_MODE"] = "allowlist"
        os.environ["ASHARE_BETA_ALLOWLIST"] = "analyst-token:analyst,operator-token:operator"
        os.environ["ASHARE_BETA_ACCESS_HEADER"] = "X-Ashare-Beta-Key"

        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        builtin_config = {
            "id": None,
            "name": "builtin-gpt",
            "provider_name": "openai",
            "model_name": "gpt-5.5",
            "base_url": "codex-cli://local",
            "api_key": "",
            "codex_bin": "/usr/local/bin/codex",
            "transport_kind": "codex_cli",
            "enabled": True,
        }

        with patch(
            "ashare_evidence.manual_research_workflow.get_builtin_llm_executor_config",
            return_value=builtin_config,
        ), patch(
            "ashare_evidence.manual_research_workflow._run_builtin_codex_completion",
            return_value=(
                '{"review_verdict":"mixed","summary":"自动人工研究已完成。",'
                '"risks":[],"disagreements":[],"decision_note":"继续人工复核。",'
                '"citations":["packet"],"answer":"自动人工研究已完成。"}'
            ),
        ):
            client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
            analyst_headers = {"X-Ashare-Beta-Key": "analyst-token"}
            create_response = client.post(
                "/manual-research/requests",
                headers=analyst_headers,
                json={
                    "symbol": "600519.SH",
                    "question": "请解释当前建议最容易失效的条件。",
                    "trigger_source": "test",
                    "executor_kind": "builtin_gpt",
                    "model_api_key_id": None,
                },
            )
            self.assertEqual(create_response.status_code, 200)
            request_id = create_response.json()["id"]

            execute_response = client.post(
                f"/manual-research/requests/{request_id}/execute",
                headers=analyst_headers,
                json={"failover_enabled": True},
            )
            self.assertEqual(execute_response.status_code, 200)
            self.assertEqual(execute_response.json()["status"], "completed")
            self.assertEqual(execute_response.json()["selected_key"]["model_name"], "gpt-5.5")

            complete_response = client.post(
                f"/manual-research/requests/{request_id}/complete",
                headers=analyst_headers,
                json={
                    "summary": "人工补充结论。",
                    "review_verdict": "mixed",
                    "risks": [],
                    "disagreements": [],
                    "decision_note": "",
                    "citations": [],
                    "answer": "人工补充结论。",
                },
            )
            self.assertEqual(complete_response.status_code, 403)
            self.assertIn("operator-only", complete_response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
