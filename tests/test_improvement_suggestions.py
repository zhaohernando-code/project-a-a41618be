from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from ashare_evidence.api import create_app
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.improvement_suggestions import (
    _run_reviewer,
    _snapshot_counts,
    _transport_for_model_key,
    _write_snapshot,
    accept_suggestion_for_plan,
    collect_improvement_suggestions,
    parse_reviewer_json,
    run_improvement_suggestion_review,
    suggestion_details,
    summarize_suggestion_review,
    update_suggestion_status,
)
from ashare_evidence.llm_service import AnthropicCompatibleTransport, OpenAICompatibleTransport
from ashare_evidence.models import FeatureSnapshot, ModelApiKey, Stock
from ashare_evidence.research_artifact_store import artifact_root_from_database_url
from tests.fixtures import seed_watchlist_fixture


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class ImprovementSuggestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "suggestions.db"
        self.database_url = f"sqlite:///{self.database_path}"
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

    def _write_event_analysis(self, symbol: str = "600519.SH", suggestion: str = "首页风险展示应优先解释 RankIC 冲突。") -> None:
        artifact_root = artifact_root_from_database_url(self.database_url)
        event_dir = artifact_root / "event_analysis" / symbol
        event_dir.mkdir(parents=True, exist_ok=True)
        filename = "20260501T090000_factor_conflict.json"
        payload = {
            "symbol": symbol,
            "trigger_type": "factor_conflict",
            "triggered_at": "2026-05-01T09:00:00+08:00",
            "generated_at": "2026-05-01T09:01:00+08:00",
            "status": "completed",
            "independent_direction": "partial_agree",
            "confidence": 0.62,
            "correction_suggestion": suggestion,
        }
        (event_dir / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        (event_dir / "index.json").write_text(
            json.dumps(
                [
                    {
                        "file": filename,
                        "trigger_type": "factor_conflict",
                        "generated_at": payload["generated_at"],
                        "status": "completed",
                        "independent_direction": "partial_agree",
                        "confidence": 0.62,
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_collects_event_and_validation_suggestions_with_dedupe(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
        self._write_event_analysis()
        self._write_event_analysis(suggestion="首页风险展示应优先解释 RankIC 冲突。")

        with session_scope(self.database_url) as session:
            suggestions = collect_improvement_suggestions(session, window_days=30)

        claims = [item["claim"] for item in suggestions]
        self.assertTrue(any("首页风险展示" in claim for claim in claims))
        ids = [item["suggestion_id"] for item in suggestions]
        self.assertEqual(len(ids), len(set(ids)))

    def test_data_quality_suggestions_are_grouped_by_degraded_sources(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))
            session.execute(delete(FeatureSnapshot))
            for stock in session.scalars(select(Stock).where(Stock.symbol.in_(("600519.SH", "300750.SZ")))):
                stock.listed_date = None
                stock.provider_symbol = ""
                stock.profile_payload = {
                    key: value
                    for key, value in stock.profile_payload.items()
                    if key not in {"financial_snapshot", "board", "market_board", "board_name"}
                }
            session.commit()

        with session_scope(self.database_url) as session:
            suggestions = collect_improvement_suggestions(session, window_days=30)

        data_quality_items = [item for item in suggestions if item["source_type"] == "data_quality"]
        self.assertEqual(len(data_quality_items), 1)
        grouped = data_quality_items[0]
        self.assertIsNone(grouped["symbol"])
        self.assertTrue(grouped["source_ref"].startswith("data_quality/group/"))
        self.assertIn("2 只股票数据质量为 warn", grouped["claim"])
        self.assertIn("共同降级来源：financial_data_stale, profile_incomplete", grouped["claim"])
        self.assertIn("重新运行数据质量与改进建议审计", grouped["proposed_change"])
        self.assertEqual(grouped["raw_source"]["aggregation"], "degraded_source_group")
        self.assertEqual(grouped["raw_source"]["symbol_count"], 2)
        self.assertEqual(grouped["raw_source"]["symbols"], ["300750.SZ", "600519.SH"])
        self.assertEqual(
            sorted(grouped["evidence_refs"]),
            ["data_quality/300750.SZ", "data_quality/600519.SH"],
        )

    def test_legacy_data_quality_snapshot_is_grouped_on_read(self) -> None:
        root = artifact_root_from_database_url(self.database_url)
        suggestions = [
            {
                "suggestion_id": "suggestion:old-a",
                "source_type": "data_quality",
                "source_ref": "data_quality/600519.SH/latest",
                "symbol": "600519.SH",
                "category": "data_quality",
                "claim": "600519.SH 数据质量为 warn，降级来源：financial_data_stale, profile_incomplete。",
                "proposed_change": "优先补齐或突出该股票的数据覆盖缺口。",
                "evidence_refs": ["data_quality/600519.SH"],
                "status": "reviewed",
                "created_at": "2026-05-01T04:00:00+00:00",
                "raw_source": {
                    "symbol": "600519.SH",
                    "status": "warn",
                    "degraded_sources": ["financial_data_stale", "profile_incomplete"],
                },
                "final_confidence": "moderate",
                "reviews": {"gpt": {"status": "completed"}},
            },
            {
                "suggestion_id": "suggestion:old-b",
                "source_type": "data_quality",
                "source_ref": "data_quality/300750.SZ/latest",
                "symbol": "300750.SZ",
                "category": "data_quality",
                "claim": "300750.SZ 数据质量为 warn，降级来源：profile_incomplete, financial_data_stale。",
                "proposed_change": "优先补齐或突出该股票的数据覆盖缺口。",
                "evidence_refs": ["data_quality/300750.SZ"],
                "status": "reviewed",
                "created_at": "2026-05-01T04:01:00+00:00",
                "raw_source": {
                    "symbol": "300750.SZ",
                    "status": "warn",
                    "degraded_sources": ["profile_incomplete", "financial_data_stale"],
                },
                "final_confidence": "low",
                "reviews": {"gpt": {"status": "completed"}},
            },
        ]
        snapshot = {
            "artifact_type": "suggestion_review_snapshot",
            "generated_at": "2026-05-01T04:02:00+00:00",
            "status": "ok",
            "window_days": 7,
            "model_status": {"gpt": "ok", "deepseek": "ok", "overall": "ok"},
            "summary": _snapshot_counts(suggestions),
            "suggestions": suggestions,
        }
        _write_snapshot(root, snapshot)

        with session_scope(self.database_url) as session:
            payload = suggestion_details(session, category="data_quality")

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(len(payload["suggestions"]), 1)
        grouped = payload["suggestions"][0]
        self.assertIsNone(grouped["symbol"])
        self.assertTrue(grouped["source_ref"].startswith("data_quality/group/"))
        self.assertIn("2 只股票数据质量为 warn", grouped["claim"])
        self.assertIn("共同降级来源：financial_data_stale, profile_incomplete", grouped["claim"])
        self.assertEqual(grouped["raw_source"]["symbols"], ["300750.SZ", "600519.SH"])
        self.assertEqual(
            sorted(grouped["evidence_refs"]),
            ["data_quality/300750.SZ", "data_quality/600519.SH"],
        )

    def test_suggestion_details_refreshes_control_plane_task_status(self) -> None:
        root = artifact_root_from_database_url(self.database_url)
        suggestions = [
            {
                "suggestion_id": "suggestion:control-task",
                "source_type": "launch_gate",
                "source_ref": "launch_gate/建议命中复盘覆盖",
                "symbol": None,
                "category": "operations_workflow",
                "claim": "运营门禁 建议命中复盘覆盖 当前为 warn，需要形成改进计划。",
                "proposed_change": "真实 benchmark 与正式复盘口径完成重建后，才允许恢复该门槛。",
                "evidence_refs": ["launch_gate/建议命中复盘覆盖"],
                "status": "completed",
                "created_at": "2026-05-01T04:00:00+00:00",
                "final_confidence": "moderate",
                "control_plane_task": {
                    "id": "task-live-status",
                    "title": "旧任务标题",
                    "status": "blocked",
                    "model": "gpt-5.5",
                    "project_id": "ashare-dashboard",
                    "plan_mode": True,
                    "api_base": "http://control.test",
                },
            }
        ]
        _write_snapshot(
            root,
            {
                "artifact_type": "suggestion_review_snapshot",
                "generated_at": "2026-05-01T04:02:00+00:00",
                "status": "ok",
                "window_days": 7,
                "model_status": {"gpt": "ok", "deepseek": "ok", "overall": "ok"},
                "summary": _snapshot_counts(suggestions),
                "suggestions": suggestions,
            },
        )

        def fake_urlopen(target, *, timeout: int, disable_proxies: bool = False):
            self.assertEqual(str(target), "http://control.test/api/tasks/task-live-status")
            self.assertEqual(timeout, 2)
            self.assertTrue(disable_proxies)
            return _FakeResponse(
                json.dumps(
                    {
                        "task": {
                            "id": "task-live-status",
                            "status": "succeeded",
                            "rawStatus": "succeeded",
                            "publishStatus": "published",
                            "publishVerified": True,
                            "workflowGates": {"status": "satisfied", "missingEvidence": []},
                            "updatedAt": "2026-05-04T12:00:00.000Z",
                        }
                    }
                )
            )

        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.improvement_suggestions.urlopen", side_effect=fake_urlopen):
                payload = suggestion_details(session, status="completed")

        task = payload["suggestions"][0]["control_plane_task"]
        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["publish_status"], "published")
        self.assertTrue(task["publish_verified"])
        self.assertEqual(task["workflow_gates"]["status"], "satisfied")
        self.assertEqual(task["status_source"], "control_plane")
        self.assertFalse(task["status_stale"])

    def test_review_summary_caps_missing_evidence_and_experiment_actions(self) -> None:
        suggestion = {
            "suggestion_id": "suggestion:test",
            "category": "factor_weight_experiment",
            "claim": "权重需要调整。",
            "proposed_change": "新增权重实验。",
            "evidence_refs": ["validation-metrics:test"],
        }
        reviews = {
            "gpt": {
                "status": "completed",
                "stance": "support",
                "confidence": 0.9,
                "missing_evidence": [],
            },
            "deepseek": {
                "status": "completed",
                "stance": "support",
                "confidence": 0.9,
                "missing_evidence": [],
            },
        }

        result = summarize_suggestion_review(suggestion, reviews)

        self.assertEqual(result["final_confidence"], "high")
        self.assertEqual(result["recommended_action"], "create_experiment")

        reviews["deepseek"]["missing_evidence"] = ["样本外验证"]
        capped = summarize_suggestion_review(suggestion, reviews)
        self.assertEqual(capped["final_confidence"], "moderate")

    def test_non_json_reviewer_output_is_recorded_as_failed(self) -> None:
        parsed = parse_reviewer_json("这不是 JSON", reviewer="gpt")

        self.assertEqual(parsed["status"], "review_failed")
        self.assertEqual(parsed["stance"], "insufficient_evidence")
        self.assertFalse(parsed["safe_to_plan"])

    def test_deepseek_key_uses_openai_compatible_transport_by_default(self) -> None:
        deepseek_key = ModelApiKey(
            name="deepseek",
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
            metadata_payload={},
        )
        anthropic_path_key = ModelApiKey(
            name="deepseek-anthropic",
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com/anthropic",
            api_key="secret",
            metadata_payload={},
        )

        self.assertIsInstance(_transport_for_model_key(deepseek_key), OpenAICompatibleTransport)
        self.assertIsInstance(_transport_for_model_key(anthropic_path_key), AnthropicCompatibleTransport)

    def test_gpt_reviewer_falls_back_to_builtin_codex_when_key_missing(self) -> None:
        suggestion = {
            "suggestion_id": "suggestion:test",
            "category": "operations_workflow",
            "claim": "需要优化 Operations 首屏。",
            "proposed_change": "新增轻量 summary。",
            "evidence_refs": ["launch_gate/test"],
        }
        builtin = {
            "enabled": True,
            "transport_kind": "codex_cli",
            "codex_bin": "/usr/local/bin/codex",
            "model_name": "gpt-5.5",
            "base_url": "codex-cli://local",
            "api_key": "",
        }
        answer = json.dumps(
            {
                "reviewer": "gpt",
                "stance": "support",
                "confidence": 0.7,
                "main_reason": "可转成明确任务。",
                "evidence_refs_used": ["launch_gate/test"],
                "missing_evidence": [],
                "implementation_notes": ["加 summary endpoint"],
                "red_flags": [],
                "safe_to_plan": True,
                "safe_to_auto_apply": False,
            }
        )

        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.runtime_config.get_builtin_llm_executor_config", return_value=builtin), patch(
                "ashare_evidence.manual_research_workflow._run_builtin_codex_completion",
                return_value=answer,
            ) as codex:
                result = _run_reviewer(session, suggestion, "gpt")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["transport_source"], "builtin_codex_gpt")
        codex.assert_called_once()

    def test_runner_writes_snapshot_and_status_update_requires_reason(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
        self._write_event_analysis()
        reviewer = {
            "stance": "support",
            "confidence": 0.72,
            "main_reason": "建议可转成清晰开发任务。",
            "evidence_refs_used": ["event_analysis/600519.SH/20260501T090000_factor_conflict.json"],
            "missing_evidence": [],
            "implementation_notes": ["在 Operations 展示。"],
            "red_flags": [],
            "safe_to_plan": True,
            "safe_to_auto_apply": False,
        }

        with session_scope(self.database_url) as session:
            snapshot = run_improvement_suggestion_review(
                session,
                window_days=30,
                reviewer_overrides={"gpt": reviewer, "deepseek": reviewer},
            )
            first_id = snapshot["suggestions"][0]["suggestion_id"]
            with self.assertRaises(ValueError):
                update_suggestion_status(session, suggestion_id=first_id, status="monitoring", reason="")
            updated = update_suggestion_status(session, suggestion_id=first_id, status="monitoring", reason="观察一周")

        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(updated["status"], "monitoring")
        self.assertEqual(updated["status_history"][-1]["reason"], "观察一周")

    def test_accept_suggestion_for_plan_creates_control_plane_plan_task(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
        self._write_event_analysis()
        reviewer = {
            "stance": "support",
            "confidence": 0.72,
            "main_reason": "建议可转成清晰开发任务。",
            "evidence_refs_used": ["event_analysis/600519.SH/20260501T090000_factor_conflict.json"],
            "missing_evidence": [],
            "implementation_notes": ["在 Operations 展示。"],
            "red_flags": [],
            "safe_to_plan": True,
            "safe_to_auto_apply": False,
        }
        captured: dict[str, object] = {}

        def fake_urlopen(target, *, timeout: int, disable_proxies: bool = False):
            captured["url"] = target.full_url
            captured["timeout"] = timeout
            captured["disable_proxies"] = disable_proxies
            captured["payload"] = json.loads(target.data.decode("utf-8"))
            return _FakeResponse(
                json.dumps(
                    {
                        "task": {
                            "id": "task-plan-1",
                            "title": "[股票看板计划池] 首页风险展示应优先解释 RankIC 冲突。",
                            "status": "blocked",
                        }
                    }
                )
            )

        with session_scope(self.database_url) as session:
            snapshot = run_improvement_suggestion_review(
                session,
                window_days=30,
                reviewer_overrides={"gpt": reviewer, "deepseek": reviewer},
            )
            first_id = snapshot["suggestions"][0]["suggestion_id"]
            with patch("ashare_evidence.improvement_suggestions.urlopen", side_effect=fake_urlopen):
                accepted = accept_suggestion_for_plan(
                    session,
                    suggestion_id=first_id,
                    model="gpt-5.5",
                    reason="进入计划池",
                    api_base="http://control.test",
                )

        payload = captured["payload"]
        self.assertEqual(captured["url"], "http://control.test/api/tasks")
        self.assertEqual(payload["projectId"], "ashare-dashboard")
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertNotIn("provider", payload)
        self.assertTrue(payload["planMode"])
        self.assertTrue(payload["approvalRequired"])
        self.assertIn("在用户审视并确认 plan 前不得开始实现", payload["description"])
        self.assertEqual(accepted["status"], "accepted_for_plan")
        self.assertEqual(accepted["control_plane_task"]["id"], "task-plan-1")
        self.assertEqual(accepted["status_history"][-1]["model"], "gpt-5.5")

    def test_api_permissions_and_degraded_run(self) -> None:
        os.environ["ASHARE_BETA_ACCESS_MODE"] = "allowlist"
        os.environ["ASHARE_BETA_ALLOWLIST"] = "member-token:viewer,operator-token:operator"
        os.environ["ASHARE_BETA_ACCESS_HEADER"] = "X-Ashare-Beta-Key"
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
        self._write_event_analysis()

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        denied = client.get("/dashboard/improvement-suggestions/summary", headers={"X-Ashare-Beta-Key": "member-token"})
        self.assertEqual(denied.status_code, 403)

        with patch(
            "ashare_evidence.runtime_config.get_builtin_llm_executor_config",
            return_value={"enabled": False},
        ):
            run_response = client.post(
                "/dashboard/improvement-suggestions/run",
                headers={"X-Ashare-Beta-Key": "operator-token"},
            )
        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        self.assertEqual(payload["status"], "degraded_missing_reviewer")
        self.assertGreaterEqual(payload["summary"]["total"], 1)

        detail_response = client.get(
            "/dashboard/improvement-suggestions/details?category=research_validation",
            headers={"X-Ashare-Beta-Key": "operator-token"},
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("suggestions", detail_response.json())

    def test_accept_plan_endpoint_requires_operator_and_returns_control_task(self) -> None:
        os.environ["ASHARE_BETA_ACCESS_MODE"] = "allowlist"
        os.environ["ASHARE_BETA_ALLOWLIST"] = "member-token:viewer,operator-token:operator"
        os.environ["ASHARE_BETA_ACCESS_HEADER"] = "X-Ashare-Beta-Key"
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
        self._write_event_analysis()
        reviewer = {
            "stance": "support",
            "confidence": 0.72,
            "main_reason": "建议可转成清晰开发任务。",
            "evidence_refs_used": ["event_analysis/600519.SH/20260501T090000_factor_conflict.json"],
            "missing_evidence": [],
            "implementation_notes": ["在 Operations 展示。"],
            "red_flags": [],
            "safe_to_plan": True,
            "safe_to_auto_apply": False,
        }
        with session_scope(self.database_url) as session:
            snapshot = run_improvement_suggestion_review(
                session,
                window_days=30,
                reviewer_overrides={"gpt": reviewer, "deepseek": reviewer},
            )
            first_id = snapshot["suggestions"][0]["suggestion_id"]

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        denied = client.post(
            f"/dashboard/improvement-suggestions/{first_id}/accept-plan",
            json={"model": "gpt-5.4", "reason": "进入计划池"},
            headers={"X-Ashare-Beta-Key": "member-token"},
        )
        self.assertEqual(denied.status_code, 403)

        with patch(
            "ashare_evidence.improvement_suggestions.urlopen",
            return_value=_FakeResponse(json.dumps({"task": {"id": "task-plan-api", "status": "blocked"}})),
        ):
            accepted = client.post(
                f"/dashboard/improvement-suggestions/{first_id}/accept-plan",
                json={"model": "gpt-5.4", "reason": "进入计划池"},
                headers={"X-Ashare-Beta-Key": "operator-token"},
            )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["control_plane_task"]["id"], "task-plan-api")


if __name__ == "__main__":
    unittest.main()
