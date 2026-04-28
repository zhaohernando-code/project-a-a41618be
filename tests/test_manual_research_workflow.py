from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from ashare_evidence.dashboard import get_stock_dashboard
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.manual_research_contract import EXECUTOR_KIND_BUILTIN_GPT
from ashare_evidence.manual_research_workflow import (
    complete_manual_research_request,
    create_manual_research_request,
    execute_manual_research_request,
    fail_manual_research_request,
    list_manual_research_requests,
)
from ashare_evidence.models import Recommendation
from tests.fixtures import inject_market_data_stale_backfill, seed_recommendation_fixture


BUILTIN_EXECUTOR_CONFIG = {
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


class ManualResearchWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "manual-research.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dashboard_projection_prefers_request_state_over_payload_shell(self) -> None:
        with patch(
            "ashare_evidence.manual_research_workflow.get_builtin_llm_executor_config",
            return_value=BUILTIN_EXECUTOR_CONFIG,
        ):
            with session_scope(self.database_url) as session:
                seed_recommendation_fixture(session, "600519.SH")
                recommendation = session.scalar(
                    select(Recommendation).where(Recommendation.recommendation_key.is_not(None))
                )
                self.assertIsNotNone(recommendation)
                payload = dict(recommendation.recommendation_payload or {})
                payload["manual_llm_review"] = {
                    "status": "completed",
                    "trigger_mode": "manual",
                    "summary": "payload shell should not override request truth.",
                    "artifact_id": "manual-review:stale-payload",
                    "question": "stale payload question",
                    "raw_answer": "stale payload answer",
                }
                recommendation.recommendation_payload = payload
                request = create_manual_research_request(
                    session,
                    symbol="600519.SH",
                    question="请检查当前建议为什么需要人工研究。",
                    trigger_source="unit_test",
                    requested_by="test-operator",
                    executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
                )

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")

        manual_review = dashboard["recommendation"]["manual_llm_review"]
        self.assertEqual(manual_review["status"], "queued")
        self.assertEqual(manual_review["request_id"], request["id"])
        self.assertEqual(manual_review["request_key"], request["request_key"])
        self.assertEqual(manual_review["executor_kind"], EXECUTOR_KIND_BUILTIN_GPT)
        self.assertIsNone(manual_review["artifact_id"])
        self.assertEqual(
            manual_review["status_note"],
            "builtin_gpt request is queued for local Codex execution.",
        )
        self.assertNotEqual(manual_review["summary"], "payload shell should not override request truth.")
        research_packet = dashboard["follow_up"]["research_packet"]
        self.assertEqual(research_packet["manual_request_id"], request["id"])
        self.assertEqual(research_packet["manual_request_key"], request["request_key"])
        self.assertEqual(research_packet["manual_review_executor_kind"], EXECUTOR_KIND_BUILTIN_GPT)
        self.assertEqual(
            research_packet["manual_review_status_note"],
            "builtin_gpt request is queued for local Codex execution.",
        )

    def test_manual_completion_writes_artifact_and_updates_dashboard_projection(self) -> None:
        with patch(
            "ashare_evidence.manual_research_workflow.get_builtin_llm_executor_config",
            return_value=BUILTIN_EXECUTOR_CONFIG,
        ):
            with session_scope(self.database_url) as session:
                seed_recommendation_fixture(session, "600519.SH")
                request = create_manual_research_request(
                    session,
                    symbol="600519.SH",
                    question="请解释当前建议为什么还能继续持有。",
                    trigger_source="unit_test",
                    requested_by="test-operator",
                    executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
                )
                completed = complete_manual_research_request(
                    session,
                    request_id=int(request["id"]),
                    summary="人工核查后，当前建议仍可保留，但要盯紧估值和白酒板块情绪。",
                    review_verdict="mixed",
                    risks=["估值已经不便宜", "板块情绪切换会放大波动"],
                    disagreements=["量化层没有显式刻画板块风险偏好"],
                    decision_note="保留当前建议，但降低对短期继续扩张的信心。",
                    citations=["经营质量稳定", "现金流没有恶化"],
                    answer="综合基本面和风险偏好后，建议维持观察中的偏积极立场。",
                )

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["artifact_id"], f"manual-review:{request['request_key']}")
        self.assertIsNotNone(completed["started_at"])
        self.assertIsNotNone(completed["completed_at"])
        self.assertIsNone(completed["failed_at"])

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")

        manual_review = dashboard["recommendation"]["manual_llm_review"]
        self.assertEqual(manual_review["status"], "completed")
        self.assertEqual(manual_review["request_id"], request["id"])
        self.assertEqual(manual_review["artifact_id"], completed["artifact_id"])
        self.assertEqual(manual_review["review_verdict"], "mixed")
        self.assertEqual(
            manual_review["summary"],
            "人工核查后，当前建议仍可保留，但要盯紧估值和白酒板块情绪。",
        )

    def test_completed_request_stays_current_when_validation_is_hydrated_from_artifacts(self) -> None:
        with patch(
            "ashare_evidence.manual_research_workflow.get_builtin_llm_executor_config",
            return_value=BUILTIN_EXECUTOR_CONFIG,
        ):
            with session_scope(self.database_url) as session:
                seed_recommendation_fixture(session, "600519.SH")
                request = create_manual_research_request(
                    session,
                    symbol="600519.SH",
                    question="请解释当前建议是否仍然有效。",
                    trigger_source="unit_test",
                    requested_by="test-operator",
                    executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
                )
                complete_manual_research_request(
                    session,
                    request_id=int(request["id"]),
                    summary="人工核查完成。",
                    review_verdict="supports_current_recommendation",
                )
                recommendation = session.scalar(
                    select(Recommendation).where(Recommendation.recommendation_key.is_not(None))
                )
                self.assertIsNotNone(recommendation)
                payload = dict(recommendation.recommendation_payload or {})
                payload.pop("historical_validation", None)
                recommendation.recommendation_payload = payload

                requests = list_manual_research_requests(session, symbol="600519.SH")

        current = requests["items"][0]
        self.assertEqual(current["status"], "completed")
        self.assertIsNone(current["stale_reason"])
        self.assertEqual(current["validation_artifact_id"], request["validation_artifact_id"])
        self.assertEqual(current["validation_manifest_id"], request["validation_manifest_id"])

    def test_queued_request_view_does_not_borrow_completed_review_from_newer_request(self) -> None:
        with patch(
            "ashare_evidence.manual_research_workflow.get_builtin_llm_executor_config",
            return_value=BUILTIN_EXECUTOR_CONFIG,
        ):
            with session_scope(self.database_url) as session:
                seed_recommendation_fixture(session, "600519.SH")
                queued_request = create_manual_research_request(
                    session,
                    symbol="600519.SH",
                    question="请先保留这条排队请求。",
                    trigger_source="unit_test",
                    requested_by="test-operator",
                    executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
                )
                completed_request = create_manual_research_request(
                    session,
                    symbol="600519.SH",
                    question="请完成这条更新后的研究请求。",
                    trigger_source="unit_test",
                    requested_by="test-operator",
                    executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
                )
                complete_manual_research_request(
                    session,
                    request_id=int(completed_request["id"]),
                    summary="更新后的研究请求已经完成。",
                    review_verdict="mixed",
                    answer="这是属于较新请求的完整回答。",
                )

                requests = list_manual_research_requests(session, symbol="600519.SH")

        queued = next(item for item in requests["items"] if item["id"] == queued_request["id"])
        completed = next(item for item in requests["items"] if item["id"] == completed_request["id"])

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["manual_llm_review"]["request_id"], queued_request["id"])
        self.assertEqual(queued["manual_llm_review"]["request_key"], queued_request["request_key"])
        self.assertIsNone(queued["manual_llm_review"]["artifact_id"])
        self.assertIsNone(queued["manual_llm_review"]["summary"])
        self.assertIsNone(queued["manual_llm_review"]["raw_answer"])

        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["manual_llm_review"]["request_id"], completed_request["id"])
        self.assertEqual(completed["manual_llm_review"]["artifact_id"], completed["artifact_id"])

    def test_fail_keeps_terminal_fields_consistent_and_completed_artifact_is_immutable(self) -> None:
        with patch(
            "ashare_evidence.manual_research_workflow.get_builtin_llm_executor_config",
            return_value=BUILTIN_EXECUTOR_CONFIG,
        ):
            with session_scope(self.database_url) as session:
                seed_recommendation_fixture(session, "600519.SH")
                failed_request = create_manual_research_request(
                    session,
                    symbol="600519.SH",
                    question="请解释为什么这次研究无法继续。",
                    trigger_source="unit_test",
                    requested_by="test-operator",
                    executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
                )
                failed = fail_manual_research_request(
                    session,
                    request_id=int(failed_request["id"]),
                    failure_reason="外部资料无法核验，先回退到人工补充。",
                )
                completed_request = create_manual_research_request(
                    session,
                    symbol="600519.SH",
                    question="请人工给出最终治理结论。",
                    trigger_source="unit_test",
                    requested_by="test-operator",
                    executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
                )
                completed = complete_manual_research_request(
                    session,
                    request_id=int(completed_request["id"]),
                    summary="人工核查完成。",
                    review_verdict="supports_current_recommendation",
                )

                with self.assertRaisesRegex(ValueError, "use retry instead"):
                    fail_manual_research_request(
                        session,
                        request_id=int(completed_request["id"]),
                        failure_reason="不应该覆盖已生成 artifact 的请求。",
                    )

        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["failure_reason"], "外部资料无法核验，先回退到人工补充。")
        self.assertIsNone(failed["completed_at"])
        self.assertIsNone(failed["artifact_id"])
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(completed["artifact_id"])

    def test_builtin_executor_executes_via_local_codex_and_completes_request(self) -> None:
        with patch(
            "ashare_evidence.manual_research_workflow.get_builtin_llm_executor_config",
            return_value=BUILTIN_EXECUTOR_CONFIG,
        ), patch(
            "ashare_evidence.manual_research_workflow._run_builtin_codex_completion",
            return_value=(
                '{"review_verdict":"mixed","summary":"本机 Codex 已生成研究结论。",'
                '"risks":["波动仍高"],"disagreements":[],"decision_note":"继续观察。",'
                '"citations":["manual packet"],"answer":"这是完整回答。"}'
            ),
        ) as builtin_runner:
            with session_scope(self.database_url) as session:
                seed_recommendation_fixture(session, "600519.SH")
                request = create_manual_research_request(
                    session,
                    symbol="600519.SH",
                    question="请解释当前建议的主要风险。",
                    trigger_source="unit_test",
                    requested_by="test-operator",
                    executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
                )
                executed = execute_manual_research_request(session, request_id=int(request["id"]))

        builtin_runner.assert_called_once()
        self.assertEqual(executed["status"], "completed")
        self.assertEqual(executed["executor_kind"], EXECUTOR_KIND_BUILTIN_GPT)
        self.assertEqual(executed["selected_key"]["name"], "builtin-gpt")
        self.assertEqual(executed["selected_key"]["model_name"], "gpt-5.5")
        self.assertIsNone(executed["selected_key"]["id"])
        self.assertTrue(executed["attempted_keys"])
        self.assertIsNone(executed["attempted_keys"][0]["key_id"])
        self.assertEqual(executed["attempted_keys"][0]["status"], "success")
        self.assertTrue(executed["artifact_id"])

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")

        manual_review = dashboard["recommendation"]["manual_llm_review"]
        self.assertEqual(manual_review["status"], "completed")
        self.assertEqual(manual_review["model_label"], "openai:gpt-5.5")
        self.assertEqual(manual_review["summary"], "本机 Codex 已生成研究结论。")

    def test_create_manual_request_prefers_non_stale_same_as_of_version(self) -> None:
        with patch(
            "ashare_evidence.manual_research_workflow.get_builtin_llm_executor_config",
            return_value=BUILTIN_EXECUTOR_CONFIG,
        ):
            with session_scope(self.database_url) as session:
                seed_recommendation_fixture(session, "600519.SH")
                fresh, stale = inject_market_data_stale_backfill(session, "600519.SH")
                request = create_manual_research_request(
                    session,
                    symbol="600519.SH",
                    question="请解释当前建议是否仍然可信。",
                    trigger_source="unit_test",
                    requested_by="test-operator",
                    executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
                )

        self.assertEqual(request["recommendation_key"], fresh.recommendation_key)
        self.assertNotEqual(request["recommendation_key"], stale.recommendation_key)


if __name__ == "__main__":
    unittest.main()
