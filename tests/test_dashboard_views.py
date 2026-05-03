from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from ashare_evidence.dashboard import (
    _candidate_primary_risk,
    get_glossary_entries,
    get_stock_dashboard,
    list_candidate_recommendations,
)
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.manual_research_contract import EXECUTOR_KIND_BUILTIN_GPT
from ashare_evidence.manual_research_workflow import (
    complete_manual_research_request,
    create_manual_research_request,
    fail_manual_research_request,
)
from ashare_evidence.models import Recommendation, Stock
from ashare_evidence.operations import build_operations_dashboard
from ashare_evidence.phase2 import PHASE2_WINDOW_DEFINITION, phase2_target_horizon_label
from ashare_evidence.release_verifier import audit_user_visible_operations_text
from ashare_evidence.research_artifact_store import artifact_root_from_database_url
from ashare_evidence.watchlist import (
    add_watchlist_symbol,
    list_watchlist_entries,
    refresh_watchlist_symbol,
    remove_watchlist_symbol,
)
from tests.fixtures import inject_market_data_stale_backfill, seed_recommendation_fixture, seed_watchlist_fixture


class DashboardViewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "dashboard.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_seeded_watchlist_builds_multi_stock_candidates(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)

        self.assertEqual(len(candidates["items"]), 4)
        self.assertEqual([item["rank"] for item in candidates["items"]], [1, 2, 3, 4])
        candidate_symbols = {item["symbol"] for item in candidates["items"]}
        self.assertEqual(candidate_symbols, {"600519.SH", "300750.SZ", "601318.SH", "002594.SZ"})
        self.assertTrue(all(item["change_summary"] for item in candidates["items"]))
        first_candidate = candidates["items"][0]
        self.assertEqual(first_candidate["window_definition"], PHASE2_WINDOW_DEFINITION)
        self.assertEqual(first_candidate["target_horizon_label"], phase2_target_horizon_label())
        self.assertEqual(first_candidate["validation_status"], "pending_rebuild")
        self.assertTrue(first_candidate["validation_note"])
        self.assertTrue(first_candidate["validation_artifact_id"])
        self.assertTrue(first_candidate["validation_manifest_id"])
        self.assertEqual(first_candidate["validation_sample_count"], 3)
        self.assertIn("validation-metrics:", first_candidate["validation_artifact_id"])
        self.assertIn("rolling-validation:", first_candidate["validation_manifest_id"])
        self.assertIsNotNone(first_candidate["validation_rank_ic_mean"])
        self.assertIsNotNone(first_candidate["validation_positive_excess_rate"])
        self.assertEqual(first_candidate["source_classification"], "artifact_backed")
        self.assertEqual(first_candidate["validation_mode"], "migration_placeholder")
        self.assertEqual(first_candidate["claim_gate"]["status"], "observe_only")
        self.assertEqual(first_candidate["display_direction"], "watch")
        self.assertEqual(first_candidate["display_direction_label"], "继续观察")
        self.assertGreaterEqual(len(first_candidate["claim_gate"]["blocking_reasons"]), 1)

    def test_candidate_serialization_tolerates_null_factor_cards(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            recommendation = session.scalar(
                select(Recommendation).order_by(Recommendation.generated_at.desc())
            )
            assert recommendation is not None
            payload = dict(recommendation.recommendation_payload or {})
            evidence = dict(payload.get("evidence") or {})
            evidence["factor_cards"] = None
            evidence["degrade_flags"] = None
            payload["evidence"] = evidence
            recommendation.recommendation_payload = payload
            session.flush()

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)
            dashboard = get_stock_dashboard(session, "600519.SH")

        self.assertTrue(candidates["items"])
        first_candidate = candidates["items"][0]
        self.assertTrue(first_candidate["why_now"])
        self.assertTrue(first_candidate["primary_risk"])
        self.assertGreaterEqual(len(dashboard["recommendation"]["evidence"]["factor_cards"]), 1)
        self.assertIsInstance(dashboard["recommendation"]["evidence"]["degrade_flags"], list)
        fusion_card = next(
            card for card in dashboard["recommendation"]["evidence"]["factor_cards"] if card["factor_key"] == "fusion"
        )
        self.assertNotIn("用于汇总价格、事件与降级状态的融合层", fusion_card["headline"])
        self.assertNotEqual(first_candidate["why_now"], "用于汇总价格、事件与降级状态的融合层。")

    def test_candidate_primary_risk_prioritizes_specific_risk_over_news_template(self) -> None:
        generic_news_risk = "若 7 日内出现负向公告或行业监管扰动，新闻因子会优先转负。"

        risk = _candidate_primary_risk(
            {
                "historical_validation": {
                    "metrics": {
                        "rank_ic_mean": -0.147,
                        "positive_excess_rate": 0.758,
                    }
                },
                "risk": {
                    "risk_flags": [
                        generic_news_risk,
                        "基本面风险：现金流质量-0.70，经营现金流严重不足。",
                    ]
                },
            }
        )

        assert risk is not None
        self.assertIn("验证冲突", risk)
        self.assertIn("RankIC -0.147", risk)
        self.assertNotEqual(risk, generic_news_risk)

        fallback_risk = _candidate_primary_risk(
            {
                "historical_validation": {"metrics": {}},
                "risk": {
                    "risk_flags": [
                        generic_news_risk,
                        "基本面风险：盈利能力评分0.15，盈利水平极其孱弱。",
                    ]
                },
            }
        )

        self.assertEqual(fallback_risk, "基本面风险：盈利能力评分0.15，盈利水平极其孱弱。")

    def test_dashboard_normalizes_legacy_placeholder_explanations(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            recommendation = session.scalar(
                select(Recommendation)
                .join(Stock)
                .where(Stock.symbol == "600519.SH")
                .order_by(Recommendation.generated_at.desc())
            )
            assert recommendation is not None
            payload = dict(recommendation.recommendation_payload or {})
            evidence = dict(payload.get("evidence") or {})
            factor_cards = list(evidence.get("factor_cards") or [])
            for card in factor_cards:
                if card.get("factor_key") == "fusion":
                    card["headline"] = "用于汇总价格、事件与降级状态的融合层。"
                    card["risk_note"] = None
            evidence["primary_drivers"] = ["用于汇总价格、事件与降级状态的融合层。"]
            evidence["supporting_context"] = ["价格趋势、确认项和事件冲突共同构成当前 Phase 2 规则基线的结构化输入。"]
            evidence["conflicts"] = ["event_conflict_high", "missing_news_evidence"]
            evidence["degrade_flags"] = ["event_conflict_high", "missing_news_evidence", "market_data_stale"]
            evidence["factor_cards"] = factor_cards
            payload["evidence"] = evidence
            recommendation.recommendation_payload = payload
            session.flush()

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")
            candidates = list_candidate_recommendations(session, limit=8)

        dashboard_evidence = dashboard["recommendation"]["evidence"]
        fusion_card = next(card for card in dashboard_evidence["factor_cards"] if card["factor_key"] == "fusion")
        first_candidate = next(item for item in candidates["items"] if item["symbol"] == "600519.SH")

        self.assertNotIn("用于汇总价格、事件与降级状态的融合层", fusion_card["headline"])
        self.assertTrue(all("Phase 2 规则基线" not in item for item in dashboard_evidence["supporting_context"]))
        self.assertIn("价格与事件方向冲突较高，系统已主动下调对外表达。", dashboard_evidence["conflicts"])
        self.assertIn("近期缺少新增事件证据，当前更多依赖价格趋势观察。", dashboard_evidence["conflicts"])
        self.assertIn("最新行情刷新偏旧，短线结论需要谨慎使用。", dashboard_evidence["conflicts"])
        self.assertNotEqual(first_candidate["why_now"], "用于汇总价格、事件与降级状态的融合层。")
        self.assertTrue(all("用于汇总价格、事件与降级状态的融合层" not in item for item in dashboard_evidence["primary_drivers"]))

    def test_stock_dashboard_contains_change_trace_and_follow_up_context(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")

        self.assertEqual(dashboard["stock"]["symbol"], "600519.SH")
        self.assertTrue(dashboard["change"]["has_previous"])
        self.assertGreaterEqual(len(dashboard["price_chart"]), 24)
        self.assertGreaterEqual(len(dashboard["today_price_chart"]), 2)
        latest_chart_day = dashboard["today_price_chart"][-1]["observed_at"].date()
        self.assertGreater(
            sum(1 for point in dashboard["today_price_chart"] if point["observed_at"].date() == latest_chart_day),
            1,
        )
        self.assertGreaterEqual(len(dashboard["recent_news"]), 3)
        self.assertGreaterEqual(len(dashboard["glossary"]), 5)
        self.assertGreaterEqual(len(dashboard["follow_up"]["suggested_questions"]), 4)
        self.assertIn("请回答这个问题", dashboard["follow_up"]["copy_prompt"])
        self.assertIn(f"目标周期：{phase2_target_horizon_label()}", dashboard["follow_up"]["copy_prompt"])
        self.assertIn("回测样本量：3", dashboard["follow_up"]["copy_prompt"])
        self.assertIn("系统当前建议（仅供参考，不是必须采纳）", dashboard["follow_up"]["copy_prompt"])
        self.assertIn("如果验证指标之间存在张力或冲突，必须先解释冲突", dashboard["follow_up"]["copy_prompt"])
        self.assertIn("如果证据不足以支持买入/卖出/强化动作，要直接说明", dashboard["follow_up"]["copy_prompt"])
        self.assertTrue(dashboard["follow_up"]["research_packet"]["validation_artifact_id"])
        self.assertEqual(dashboard["follow_up"]["research_packet"]["validation_sample_count"], 3)
        self.assertEqual(dashboard["follow_up"]["research_packet"]["manual_review_trigger_mode"], "manual")
        self.assertIsNone(dashboard["follow_up"]["research_packet"]["manual_review_artifact_id"])

    def test_stock_dashboard_embeds_latest_event_deep_analysis(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        artifact_root = artifact_root_from_database_url(self.database_url)
        event_dir = artifact_root / "event_analysis" / "600519.SH"
        event_dir.mkdir(parents=True, exist_ok=True)
        filename = "20260430T090527_direction_switch.json"
        detail = {
            "symbol": "600519.SH",
            "trigger_type": "direction_switch",
            "trigger_detail": "方向从观察切换到风险提示，需要独立复核。",
            "triggered_at": "2026-04-30T09:05:27+08:00",
            "generated_at": "2026-04-30T09:06:10+08:00",
            "status": "completed",
            "independent_direction": "partial_agree",
            "confidence": 0.62,
            "key_evidence": [
                {"source": "内部因子", "content": "价格基线转弱但事件因子仍有支撑。"},
            ],
            "risks": ["验证样本不足，不能直接强化方向。"],
            "information_gaps": ["缺少最新公告全文。"],
            "next_checkpoint": "等待下一根日线确认。",
            "correction_suggestion": "维持研究候选，不提升为买入表达。",
            "model_used": "deepseek-flash",
        }
        (event_dir / filename).write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")
        (event_dir / "index.json").write_text(
            json.dumps(
                [
                    {
                        "file": filename,
                        "trigger_type": detail["trigger_type"],
                        "triggered_at": detail["triggered_at"],
                        "generated_at": detail["generated_at"],
                        "status": detail["status"],
                        "independent_direction": detail["independent_direction"],
                        "confidence": detail["confidence"],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with session_scope(self.database_url) as session:
            dashboard = get_stock_dashboard(session, "600519.SH")

        self.assertEqual(len(dashboard["event_analyses"]), 1)
        analysis = dashboard["event_analyses"][0]
        self.assertEqual(analysis["trigger_type"], "direction_switch")
        self.assertEqual(analysis["independent_direction"], "partial_agree")
        self.assertEqual(analysis["confidence"], 0.62)
        self.assertEqual(analysis["key_evidence"][0]["source"], "内部因子")
        self.assertIn("维持研究候选", analysis["correction_suggestion"])

    def test_dashboard_candidates_operations_and_watchlist_ignore_stale_same_as_of_backfill(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))
            fresh, stale = inject_market_data_stale_backfill(session, "600519.SH")

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=8)
            dashboard = get_stock_dashboard(session, "600519.SH")
            build_operations_dashboard(session, sample_symbol="600519.SH")
            watchlist = list_watchlist_entries(session)

        self.assertEqual(candidates["items"][0]["as_of_data_time"], fresh.as_of_data_time)
        self.assertNotEqual(candidates["items"][0]["generated_at"], stale.generated_at)
        self.assertEqual(dashboard["recommendation"]["id"], fresh.id)
        self.assertNotEqual(dashboard["recommendation"]["id"], stale.id)
        watchlist_item = next(item for item in watchlist["items"] if item["symbol"] == "600519.SH")
        self.assertEqual(watchlist_item["latest_direction"], fresh.direction)
        self.assertIsNone(dashboard["follow_up"]["research_packet"]["manual_review_generated_at"])
        self.assertEqual(dashboard["recommendation"]["historical_validation"]["metrics"]["sample_count"], 3)
        self.assertIn("rank_ic_mean", dashboard["recommendation"]["historical_validation"]["metrics"])
        self.assertEqual(dashboard["recommendation"]["claim_gate"]["status"], "observe_only")
        self.assertEqual(dashboard["recommendation"]["claim_gate"]["public_direction"], "watch")
        self.assertGreaterEqual(len(dashboard["recommendation"]["claim_gate"]["blocking_reasons"]), 1)
        self.assertEqual(dashboard["hero"]["direction_label"], "继续观察")
        self.assertTrue(dashboard["risk_panel"]["disclaimer"])
        self.assertGreaterEqual(len(dashboard["evidence"]), 6)
        self.assertEqual(len(dashboard["simulation_orders"]), 2)

    def test_operations_dashboard_contains_portfolios_replay_and_launch_gates(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(
                session,
                sample_symbol="600519.SH",
                include_simulation_workspace=True,
            )

        self.assertEqual(operations["market_data_timeframe"], "5min")
        self.assertEqual(operations["intraday_source_status"]["timeframe"], "5min")
        self.assertEqual(operations["overview"]["manual_portfolio_count"], 1)
        self.assertEqual(operations["overview"]["auto_portfolio_count"], 1)
        self.assertEqual(operations["overview"]["research_validation"]["status"], "pending_rebuild")
        self.assertEqual(operations["overview"]["run_health"]["market_data_timeframe"], "5min")
        self.assertGreaterEqual(operations["overview"]["launch_readiness"]["warning_gate_count"], 1)
        self.assertIsNone(operations["overview"]["recommendation_replay_hit_rate"])
        self.assertGreaterEqual(operations["overview"]["research_validation"]["manifest_bound_count"], 1)
        self.assertGreaterEqual(operations["overview"]["research_validation"]["metrics_artifact_count"], 1)
        self.assertGreaterEqual(operations["overview"]["research_validation"]["artifact_sample_count"], 1)
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_horizon_selection"]["approval_state"],
            "insufficient_phase5_evidence",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["approval_state"],
            "research_candidate_only",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["gate_status"],
            "draft_gate_blocked",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["governance_status"],
            "maintain_non_promotion_until_gate_passes",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["governance_action"],
            "continue_gate_research_without_promotion",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["redesign_status"],
            "no_structured_redesign_signal",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"][
                "redesign_primary_experiment_ids"
            ],
            [],
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["redesign_focus_areas"],
            [],
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"][
                "redesign_triggered_signal_ids"
            ],
            [],
        )
        self.assertIn(
            "included_portfolio_count",
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["failing_gate_ids"],
        )
        self.assertFalse(
            operations["overview"]["research_validation"]["phase5_horizon_selection"]["artifact_available"]
        )
        self.assertFalse(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["artifact_available"]
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["included_portfolio_count"],
            1,
        )
        self.assertIsNotNone(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["mean_turnover"]
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_artifact_bound_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_artifact_manifest_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_artifact_nonverified_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_artifact_backed_projection_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_migration_placeholder_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_bound_count"], 2)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_manifest_count"], 2)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_verified_count"], 0)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_pending_rebuild_count"], 2)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_artifact_backed_projection_count"], 2)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_migration_placeholder_count"], 2)
        self.assertEqual(len(operations["portfolios"]), 2)
        self.assertGreaterEqual(len(operations["recommendation_replay"]), 4)
        self.assertGreaterEqual(len(operations["launch_gates"]), 6)
        self.assertTrue(all(portfolio["nav_history"] for portfolio in operations["portfolios"]))
        self.assertTrue(all(portfolio["recent_orders"] for portfolio in operations["portfolios"]))
        self.assertTrue(all(portfolio["rules"] for portfolio in operations["portfolios"]))
        self.assertTrue(all(portfolio["market_data_timeframe"] == "5min" for portfolio in operations["portfolios"]))
        first_portfolio = operations["portfolios"][0]
        self.assertEqual(first_portfolio["validation_status"], "pending_rebuild")
        self.assertEqual(first_portfolio["execution_policy"]["status"], "research_candidate")
        self.assertEqual(first_portfolio["execution_policy"]["policy_type"], "phase5_simulation_topk_equal_weight_v1")
        self.assertEqual(first_portfolio["benchmark_context"]["status"], "pending_rebuild")
        self.assertEqual(first_portfolio["benchmark_note"], first_portfolio["benchmark_context"]["note"])
        self.assertEqual(first_portfolio["benchmark_context"]["source_classification"], "artifact_backed")
        self.assertIsNone(first_portfolio["recommendation_hit_rate"])
        self.assertTrue(first_portfolio["validation_artifact_id"])
        self.assertTrue(first_portfolio["validation_manifest_id"])
        self.assertEqual(first_portfolio["benchmark_context"]["source"], "portfolio_backtest_artifact")
        self.assertEqual(first_portfolio["benchmark_context"]["artifact_id"], first_portfolio["validation_artifact_id"])
        self.assertEqual(first_portfolio["benchmark_context"]["manifest_id"], first_portfolio["validation_manifest_id"])
        self.assertEqual(first_portfolio["benchmark_context"]["benchmark_definition"], "active_watchlist_equal_weight_proxy")
        self.assertIsNotNone(first_portfolio["performance"]["annualized_return"])
        self.assertIsNotNone(first_portfolio["performance"]["annualized_excess_return"])
        self.assertIsNotNone(first_portfolio["performance"]["turnover"])
        self.assertTrue(first_portfolio["performance"]["win_rate_definition"])
        self.assertEqual(first_portfolio["performance"]["artifact_id"], first_portfolio["validation_artifact_id"])
        self.assertEqual(first_portfolio["performance"]["validation_mode"], "migration_placeholder")
        self.assertEqual(first_portfolio["performance"]["benchmark_definition"], "active_watchlist_equal_weight_proxy")
        self.assertEqual(first_portfolio["performance"]["cost_source"], "artifact_backed")
        first_replay = operations["recommendation_replay"][0]
        self.assertEqual(first_replay["source"], "replay_alignment_artifact")
        self.assertEqual(first_replay["source_classification"], "artifact_backed")
        self.assertEqual(first_replay["artifact_type"], "replay_alignment")
        self.assertTrue(first_replay["artifact_id"])
        self.assertTrue(first_replay["recommendation_key"])
        self.assertEqual(first_replay["label_definition"], "migration_directional_replay_pending")
        self.assertEqual(
            first_replay["review_window_definition"],
            "migration_latest_available_close_vs_watchlist_equal_weight_proxy",
        )
        self.assertEqual(first_replay["benchmark_definition"], "active_watchlist_equal_weight_proxy")
        self.assertEqual(first_replay["benchmark_source"], "artifact_backed")
        self.assertEqual(first_replay["validation_mode"], "migration_placeholder")
        self.assertTrue(first_replay["hit_definition"])
        self.assertLessEqual(first_replay["entry_time"], first_replay["exit_time"])
        launch_gates = {gate["gate"]: gate for gate in operations["launch_gates"]}
        first_gate = set(launch_gates)
        self.assertIn("分离式模拟交易", first_gate)
        self.assertIn("组合回测产物绑定", first_gate)
        self.assertIn("A 股规则合规", first_gate)
        self.assertEqual(launch_gates["组合回测产物绑定"]["status"], "warn")
        self.assertIn("verified=0", launch_gates["组合回测产物绑定"]["current_value"])

    def test_operations_dashboard_can_embed_simulation_workspace(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(
                session,
                sample_symbol="600519.SH",
                include_simulation_workspace=True,
            )

        workspace = operations["simulation_workspace"]
        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace["session"]["status"], "draft")
        self.assertEqual(workspace["session"]["market_data_timeframe"], "5min")
        self.assertEqual(workspace["session"]["market_data_interval_seconds"], 300)
        self.assertTrue(workspace["controls"]["can_start"])
        self.assertGreaterEqual(len(workspace["kline"]["points"]), 24)
        self.assertEqual(workspace["manual_track"]["label"], "用户轨道")
        self.assertEqual(workspace["model_track"]["label"], "模型轨道")
        self.assertEqual(workspace["manual_track"]["portfolio"]["starting_cash"], workspace["session"]["initial_cash"])

    def test_operations_dashboard_user_visible_projection_blocks_migration_terms(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(
                session,
                sample_symbol="600519.SH",
                include_simulation_workspace=True,
            )

        audit = audit_user_visible_operations_text(operations)

        self.assertTrue(audit["passed"])
        self.assertIn("用户轨道", audit["combined_text"])
        self.assertIn("模型轨道", audit["combined_text"])
        self.assertNotIn("Phase 5 baseline", audit["combined_text"])
        self.assertNotIn("research contract", audit["combined_text"])
        self.assertNotIn("运营复盘口径仍在迁移", audit["combined_text"])

    def test_operations_dashboard_audit_sanitizes_manual_review_internal_terms(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            request = create_manual_research_request(
                session,
                symbol="600519.SH",
                question="请解释当前建议为什么需要人工研究。",
                trigger_source="manual_research_ui",
                requested_by="operator:test",
                executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
            )
            complete_manual_research_request(
                session,
                request_id=int(request["id"]),
                summary="pending_rebuild：research contract 仍引用 Phase 5 baseline。",
                review_verdict="mixed",
                risks=[
                    "manual-review:case-1 仍写着 pending_rebuild。",
                    "validation-metrics:case-1 需要和 research contract 对齐。",
                ],
                disagreements=["rolling-validation:case-1 仍在 Phase 5 baseline 口径。"],
                decision_note="建议把 pending_rebuild 改成面向用户的说明。",
                citations=["portfolio-backtest:case-1"],
                answer="当前结论引用了 forward_excess_return_20d 与 14-56 trade days。",
            )

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(
                session,
                sample_symbol="600519.SH",
                include_simulation_workspace=True,
            )

        audit = audit_user_visible_operations_text(operations)
        review = operations["manual_research_queue"]["recent_items"][0]["manual_llm_review"]

        self.assertTrue(audit["passed"])
        self.assertEqual(audit["banned_hits"], [])
        self.assertIn("口径校准中", review["summary"])
        self.assertIn("研究口径", review["summary"])
        self.assertIn("等权组合研究策略", review["summary"])
        self.assertIn("人工研究记录", review["risks"][0])
        self.assertIn("验证指标记录", review["risks"][1])
        self.assertIn("滚动验证记录", review["disagreements"][0])
        self.assertEqual(review["citations"], ["组合回测记录"])
        self.assertIn("20日超额收益", review["raw_answer"])
        self.assertIn("the window under rolling validation", review["raw_answer"])

    def test_operations_dashboard_audit_blocks_placeholder_professionalism_terms(self) -> None:
        audit = audit_user_visible_operations_text(
            {
                "overview": {
                    "title": "用户轨道",
                    "summary": "模型轨道",
                    "note": "用于汇总价格、事件与降级状态的融合层。",
                    "risk_flags": ["event_conflict_high", "missing_news_evidence"],
                }
            }
        )

        self.assertFalse(audit["passed"])
        self.assertIn("event_conflict_high", audit["banned_hits"])
        self.assertIn("missing_news_evidence", audit["banned_hits"])
        self.assertIn("用于汇总价格、事件与降级状态的融合层", audit["banned_hits"])

    def test_frontend_manual_research_projection_sanitizes_user_visible_fields(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "description={sanitizeDisplayText(dashboard.recommendation.manual_llm_review.stale_reason)}",
            source,
        )
        self.assertIn(
            "sanitizeDisplayText(dashboard.recommendation.manual_llm_review.summary)",
            source,
        )
        self.assertIn(
            "sanitizeDisplayText(dashboard.recommendation.manual_llm_review.decision_note)",
            source,
        )
        self.assertIn(
            "<li key={item}>{sanitizeDisplayText(item)}</li>",
            source,
        )
        self.assertIn(
            '<Tag color="blue">已生成研究记录</Tag>',
            source,
        )
        self.assertNotIn(
            "description={dashboard.recommendation.manual_llm_review.stale_reason}",
            source,
        )
        self.assertNotIn(
            "<Tag>{analysisAnswer.artifact_id}</Tag>",
            source,
        )

    def test_frontend_manual_research_display_fallback_sanitizes_timeout_related_internal_terms(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "utils" / "labels.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('.replace(/pending_rebuild/g, "口径校准中")', source)
        self.assertIn('.replace(/research_rebuild_pending/g, "滚动验证口径校准中")', source)
        self.assertIn('.replace(/forward_excess_return_(\\d+)d/g, "$1日超额收益")', source)
        self.assertIn('.replace(/14-56 trade days/g, "the window under rolling validation")', source)
        self.assertIn('.replace(/missing_news_evidence/g, "近期缺少新增事件证据，当前更多依赖价格趋势观察")', source)
        self.assertIn('.replace(/event_conflict_high/g, "价格与事件方向冲突较高，系统已主动下调对外表达")', source)
        self.assertIn('.replace(/market_data_stale/g, "最新行情刷新偏旧，短线结论需要谨慎使用")', source)
        self.assertIn('.replace(/用于汇总价格、事件与降级状态的融合层。?/g, "价格与事件综合后，当前先看趋势是否得到新增证据确认")', source)

    def test_frontend_operations_track_tables_keep_overflow_scoped_to_card(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        track_table_source = (frontend_root / "components" / "TrackHoldingsTable.tsx").read_text(encoding="utf-8")
        track_card_source = (frontend_root / "components" / "SimulationTrackCard.tsx").read_text(encoding="utf-8")
        style_source = (frontend_root / "styles.css").read_text(encoding="utf-8")
        focus_change_section = app_source.split("async function handleSimulationFocusChange(symbol: string) {", 1)[1]
        focus_change_body = focus_change_section.split("function openManualOrderModal", 1)[0]

        self.assertIn('const [operationsFocusSymbol, setOperationsFocusSymbol] = useState<string | null>(null);', app_source)
        self.assertIn("const response = await api.updateSimulationConfig({", app_source)
        self.assertIn("setOperationsFocusSymbol(nextFocusSymbol);", app_source)
        self.assertNotIn("setSelectedSymbol(symbol);", focus_change_body)
        self.assertIn('<div className="track-holdings-shell">', track_table_source)
        self.assertIn('className="track-holdings-table"', track_table_source)
        self.assertIn('scroll={{ x: "max-content" }}', track_table_source)
        self.assertIn("event.stopPropagation();", track_table_source)
        self.assertIn('className="panel-card simulation-track-card"', track_card_source)
        self.assertNotIn('scroll={{ x: 980 }}', app_source)
        self.assertEqual(app_source.count("<Col xs={24} xxl={12}>"), 2)
        self.assertIn('<Col xs={24} xxl={12}>\n                        <SimulationTrackCard', app_source)
        self.assertIn("当前表格默认展示当前模拟股票池。", app_source)
        self.assertIn('`模拟池 ${simulation.session.watch_symbols.length} 只`', app_source)

        self.assertIn(".track-holdings-shell {", style_source)
        self.assertIn(".track-holdings-table .ant-table-content {", style_source)
        self.assertIn("overflow-x: auto !important;", style_source)
        self.assertIn("overscroll-behavior-x: contain;", style_source)
        self.assertIn(".simulation-track-card .ant-card-extra {", style_source)
        self.assertIn(".panel-card > .ant-card-body > *,", style_source)
        self.assertIn("min-width: 0;", style_source)

    def test_frontend_candidate_return_color_and_operations_report_button_follow_current_contract(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        candidate_columns_source = (frontend_root / "components" / "CandidateColumns.tsx").read_text(encoding="utf-8")
        mobile_stock_row_source = (frontend_root / "components" / "mobile" / "MobileStockRow.tsx").read_text(encoding="utf-8")

        self.assertIn('className={`value-${valueTone(record.candidate.price_return_20d)}`}', candidate_columns_source)
        self.assertIn('className={`value-${valueTone(candidate?.price_return_20d)}`}', mobile_stock_row_source)
        self.assertNotIn('type={record.candidate.price_return_20d >= 0 ? "success" : "danger"}', candidate_columns_source)
        self.assertIn("运营复盘分析报告", app_source)
        self.assertIn("onOpenReport={(symbol) => void openAnalysisReportModal(symbol)}", app_source)

    def test_frontend_manual_research_entry_exposes_visible_jump_to_workspace(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        style_source = (frontend_root / "styles.css").read_text(encoding="utf-8")

        self.assertIn('const [stockActiveTab, setStockActiveTab] = useState("signals");', app_source)
        self.assertIn("function openManualResearchWorkspace()", app_source)
        self.assertIn('setStockActiveTab("followup");', app_source)
        self.assertIn('<Button type="primary" size="small" onClick={openManualResearchWorkspace}>', app_source)
        self.assertIn("发起人工研究", app_source)
        self.assertIn('入口在下方"追问与模拟"标签。', app_source)
        self.assertIn("留空不选模型 Key 时会直接调用本机 Codex，用 `gpt-5.5` 执行 builtin 研究；选择已配置 Key 时则走对应的外部模型 Key。", app_source)
        self.assertIn('<Tabs activeKey={stockActiveTab} onChange={setStockActiveTab} items={visibleStockTabItems} />', app_source)
        self.assertIn(".manual-research-entry-actions {", style_source)

    def test_frontend_stock_page_exposes_event_deep_analysis(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        mobile_source = (frontend_root / "components" / "mobile" / "MobileStockDetail.tsx").read_text(encoding="utf-8")
        type_source = (frontend_root / "types" / "stock.ts").read_text(encoding="utf-8")
        label_source = (frontend_root / "utils" / "labels.ts").read_text(encoding="utf-8")

        self.assertIn('title="事件深度分析"', app_source)
        self.assertIn("dashboard.event_analyses", app_source)
        self.assertIn("eventEvidenceText(item.key_evidence[0])", mobile_source)
        self.assertIn("export interface EventAnalysisView", type_source)
        self.assertIn("event_analyses: EventAnalysisView[];", type_source)
        self.assertIn('if (trigger === "weekly_review") return "周度例行复盘";', label_source)
        self.assertIn('if (direction === "disagree") return "独立判断不一致";', label_source)

    def test_frontend_operations_exposes_improvement_suggestion_audit_without_auto_apply(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        operations_source = (frontend_root / "components" / "OperationsTabs.tsx").read_text(encoding="utf-8")
        api_source = (frontend_root / "api" / "dashboard.ts").read_text(encoding="utf-8")
        type_source = (frontend_root / "types" / "operations.ts").read_text(encoding="utf-8")

        self.assertIn("改进建议审计台", operations_source)
        self.assertIn("GPT", operations_source)
        self.assertIn("DeepSeek", operations_source)
        self.assertIn("进入计划池", operations_source)
        self.assertIn("选择执行模型", operations_source)
        self.assertIn("GPT-5.5 高级审计 / 仲裁", operations_source)
        self.assertIn("进入计划池并创建中台任务", operations_source)
        self.assertIn("Plan 模式", operations_source)
        self.assertIn("中台任务", operations_source)
        self.assertIn("标记观察", operations_source)
        self.assertIn("重新审计", operations_source)
        self.assertIn("suggestion-stat-button", operations_source)
        self.assertIn("filterImprovementSuggestions", operations_source)
        self.assertIn("当前筛选", operations_source)
        self.assertIn("暂无可审计建议", operations_source)
        self.assertNotIn("自动实现", operations_source)
        self.assertNotIn("自动发布", operations_source)
        self.assertIn("getImprovementSuggestionDetails", api_source)
        self.assertIn("runImprovementSuggestionReview", api_source)
        self.assertIn("acceptImprovementSuggestionForPlan", api_source)
        self.assertIn("export interface ImprovementSuggestionView", type_source)
        self.assertIn("ImprovementSuggestionControlTask", type_source)

    def test_frontend_manual_research_default_submit_executes_builtin_codex(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        api_core_source = (frontend_root / "api" / "core.ts").read_text(encoding="utf-8")
        api_manual_research_source = (frontend_root / "api" / "manual-research.ts").read_text(encoding="utf-8")
        submit_section = app_source.split("async function handleSubmitManualResearch()", 1)[1]
        submit_body = submit_section.split("async function handleExecuteManualResearch", 1)[0]

        self.assertIn("const created = await api.createManualResearchRequest({", submit_body)
        self.assertIn("const result = await api.executeManualResearchRequest(created.id, {", submit_body)
        self.assertNotIn("? await api.executeManualResearchRequest", submit_body)
        self.assertIn("const longRunningRequestTimeoutMs = 180000;", api_core_source)
        self.assertIn("const longRunningRequestAttemptTimeoutMs = 60000;", api_core_source)
        self.assertIn("export const manualResearchRequestBehavior: RequestBehavior = {", api_core_source)
        self.assertIn("timeoutMs: longRunningRequestTimeoutMs,", api_core_source)
        self.assertIn("attemptTimeoutMs: longRunningRequestAttemptTimeoutMs,", api_core_source)
        self.assertIn("}, manualResearchRequestBehavior);", api_manual_research_source)
        self.assertIn('placeholder="可选：选择要执行的模型 Key；留空则使用本机 Codex builtin GPT"', app_source)
        self.assertIn('{analysisKeyId ? "提交并执行" : "使用 builtin GPT 执行"}', app_source)
        self.assertIn(
            "这里的默认动作已经改成 durable manual research request。选择模型 Key 时会立即执行；不选时会直接调用本机 Codex 的 builtin `gpt-5.5` 执行。只有本机 Codex 不可用时，才会保留请求并提示当前环境尚未配置 builtin executor。",
            app_source,
        )

    def test_frontend_base_entrypoint_checks_for_new_release_without_cache_buster(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend"
        index_source = (frontend_root / "index.html").read_text(encoding="utf-8")
        main_source = (frontend_root / "src" / "main.tsx").read_text(encoding="utf-8")

        self.assertIn('<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />', index_source)
        self.assertIn('<meta http-equiv="Pragma" content="no-cache" />', index_source)
        self.assertIn('<meta http-equiv="Expires" content="0" />', index_source)
        self.assertIn('const releaseReloadMarkerKey = "ashare-dashboard-release-reload";', main_source)
        self.assertIn('const releaseCheckIntervalMs = 60_000;', main_source)
        self.assertIn('const response = await fetch(window.location.href, {', main_source)
        self.assertIn('cache: "no-store",', main_source)
        self.assertIn('window.location.reload();', main_source)
        self.assertIn('window.addEventListener("focus", handleFocus);', main_source)
        self.assertIn('document.addEventListener("visibilitychange", handleVisibilityChange);', main_source)

    def test_operations_dashboard_exposes_manual_research_queue(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            queued = create_manual_research_request(
                session,
                symbol="600519.SH",
                question="请解释当前建议最容易失效的条件。",
                trigger_source="manual_research_ui",
                requested_by="operator:test",
                executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
            )

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="600519.SH")

        queue = operations["manual_research_queue"]
        self.assertEqual(queue["focus_symbol"], "600519.SH")
        self.assertEqual(queue["counts"]["queued"], 1)
        self.assertEqual(queue["counts"]["in_progress"], 0)
        self.assertEqual(queue["focus_request"]["id"], queued["id"])
        self.assertEqual(queue["focus_request"]["symbol"], "600519.SH")
        self.assertEqual(queue["focus_request"]["status"], "queued")
        self.assertEqual(queue["recent_items"][0]["request_key"], queued["request_key"])
        self.assertEqual(
            queue["recent_items"][0]["manual_llm_review"]["request_key"],
            queued["request_key"],
        )

    def test_operations_dashboard_classifies_manual_research_terminal_states(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            completed_request = create_manual_research_request(
                session,
                symbol="600519.SH",
                question="请人工完成当前建议复核。",
                trigger_source="manual_research_ui",
                requested_by="operator:test",
                executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
            )
            complete_manual_research_request(
                session,
                request_id=int(completed_request["id"]),
                summary="人工研究已完成。",
                review_verdict="supports_current_recommendation",
            )
            failed_request = create_manual_research_request(
                session,
                symbol="300750.SZ",
                question="请解释当前建议为什么需要回退。",
                trigger_source="manual_research_ui",
                requested_by="operator:test",
                executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
            )
            fail_manual_research_request(
                session,
                request_id=int(failed_request["id"]),
                failure_reason="外部证据暂时不完整。",
            )

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="600519.SH")

        queue = operations["manual_research_queue"]
        self.assertEqual(queue["counts"]["queued"], 0)
        self.assertEqual(queue["counts"]["failed"], 1)
        self.assertEqual(queue["counts"]["completed_current"], 1)
        self.assertEqual(queue["focus_request"]["id"], completed_request["id"])
        recent_by_symbol = {item["symbol"]: item for item in queue["recent_items"]}
        self.assertEqual(recent_by_symbol["600519.SH"]["status"], "completed")
        self.assertEqual(recent_by_symbol["300750.SZ"]["status"], "failed")

    def test_operations_dashboard_scopes_simulation_to_active_watchlist(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "688981.SH")
            add_watchlist_symbol(session, "688981", stock_name="中芯国际")
            remove_watchlist_symbol(session, "600519")

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="688981.SH")

        active_watchlist_symbols = {"300750.SZ", "601318.SH", "002594.SZ", "688981.SH"}
        replay_symbols = {item["symbol"] for item in operations["recommendation_replay"]}
        portfolio_symbols = {
            item["symbol"]
            for portfolio in operations["portfolios"]
            for item in [*portfolio["holdings"], *portfolio["recent_orders"]]
        }

        self.assertIn("688981.SH", replay_symbols)
        self.assertNotIn("600519.SH", replay_symbols)
        self.assertTrue(replay_symbols.issubset(active_watchlist_symbols))
        self.assertNotIn("600519.SH", portfolio_symbols)
        self.assertTrue(portfolio_symbols.issubset(active_watchlist_symbols))

    def test_operations_dashboard_tolerates_missing_sample_symbol(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "688981.SH")
            add_watchlist_symbol(session, "688981", stock_name="中芯国际")
            remove_watchlist_symbol(session, "600519")

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="000001.SZ")

        replay_symbols = {item["symbol"] for item in operations["recommendation_replay"]}
        portfolio_symbols = {
            item["symbol"]
            for portfolio in operations["portfolios"]
            for item in [*portfolio["holdings"], *portfolio["recent_orders"]]
        }
        self.assertIn("688981.SH", replay_symbols)
        self.assertNotIn("600519.SH", replay_symbols)
        self.assertNotIn("600519.SH", portfolio_symbols)
        self.assertEqual(len(operations["portfolios"]), 2)

    def test_glossary_entries_cover_key_user_terms(self) -> None:
        glossary = get_glossary_entries()
        terms = {item["term"] for item in glossary}
        self.assertIn("滚动验证", terms)
        self.assertIn("降级条件", terms)
        self.assertIn("人工研究层", terms)

    def test_watchlist_can_add_custom_symbol_and_remove_it(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "688981.SH")
            item = add_watchlist_symbol(session, "688981", stock_name="中芯国际")

        self.assertEqual(item["symbol"], "688981.SH")
        self.assertEqual(item["name"], "中芯国际")

        with session_scope(self.database_url) as session:
            watchlist = list_watchlist_entries(session)
            candidates = list_candidate_recommendations(session, limit=10)
            dashboard = get_stock_dashboard(session, "688981.SH")

        self.assertIn("688981.SH", {entry["symbol"] for entry in watchlist["items"]})
        self.assertIn("688981.SH", {entry["symbol"] for entry in candidates["items"]})
        self.assertEqual(dashboard["stock"]["name"], "中芯国际")
        self.assertGreaterEqual(len(dashboard["price_chart"]), 24)

        with session_scope(self.database_url) as session:
            removal = remove_watchlist_symbol(session, "688981")

        self.assertTrue(removal["removed"])

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=10)

        self.assertNotIn("688981.SH", {entry["symbol"] for entry in candidates["items"]})

    def test_watchlist_resolves_known_stock_name_and_sector(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "002028.SZ")
            item = add_watchlist_symbol(session, "002028")

        self.assertEqual(item["symbol"], "002028.SZ")
        self.assertEqual(item["name"], "思源电气")

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=10)
            dashboard = get_stock_dashboard(session, "002028.SZ")

        candidate = next(entry for entry in candidates["items"] if entry["symbol"] == "002028.SZ")
        self.assertEqual(candidate["name"], "思源电气")
        self.assertEqual(candidate["sector"], "电力设备")
        self.assertEqual(dashboard["stock"]["name"], "思源电气")
        self.assertIn("电力设备", dashboard["hero"]["sector_tags"])
        self.assertNotIn("医药生物", dashboard["hero"]["sector_tags"])

    def test_refresh_watchlist_rebuilds_real_analysis_when_sources_are_available(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "002028.SZ")
            added = add_watchlist_symbol(session, "002028")
            latest_before = added["latest_generated_at"]

        with session_scope(self.database_url) as session:
            refreshed = refresh_watchlist_symbol(session, "002028")
        self.assertEqual(refreshed["name"], "思源电气")
        self.assertGreaterEqual(refreshed["latest_generated_at"], latest_before)
        self.assertEqual(refreshed["analysis_status"], "ready")

    def test_refresh_watchlist_repairs_profile_snapshot_when_full_rebuild_fails(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "002028.SZ")
            add_watchlist_symbol(session, "002028")

        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.watchlist.refresh_real_analysis", side_effect=RuntimeError("缺少足够日线")):
                with patch("ashare_evidence.watchlist.repair_stock_profile_snapshot") as repair_mock:
                    refreshed = refresh_watchlist_symbol(session, "002028")

        repair_mock.assert_called_once()
        self.assertEqual(refreshed["analysis_status"], "ready")
        self.assertIn("真实数据刷新失败", refreshed["last_error"] or "")


if __name__ == "__main__":
    unittest.main()
