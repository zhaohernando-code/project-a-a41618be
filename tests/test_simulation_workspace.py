from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.models import MarketBar, PaperPortfolio, Recommendation, SimulationSession
from ashare_evidence.release_verifier import collect_user_visible_text_fragments, find_banned_terms_in_text
from ashare_evidence.simulation import (
    advance_running_simulation_session,
    end_simulation_session,
    get_simulation_workspace,
    pause_simulation_session,
    place_manual_order,
    restart_simulation_session,
    resume_simulation_session,
    start_simulation_session,
    step_simulation_session,
    update_simulation_config,
)
from ashare_evidence.watchlist import add_watchlist_symbol
from tests.fixtures import inject_market_data_stale_backfill, seed_recommendation_fixture, seed_watchlist_fixture


class SimulationWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "simulation.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_workspace_bootstrap_exposes_dual_track_session(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            legacy_reason = "LEGACY_TOP_LEVEL_DRIVER_SHOULD_NOT_APPEAR"
            legacy_risk = "LEGACY_TOP_LEVEL_RISK_SHOULD_NOT_APPEAR"
            for recommendation in session.scalars(select(Recommendation)).all():
                payload = dict(recommendation.recommendation_payload or {})
                payload["core_drivers"] = [legacy_reason]
                payload["reverse_risks"] = [legacy_risk]
                recommendation.recommendation_payload = payload
            session.commit()

        with session_scope(self.database_url) as session:
            workspace = get_simulation_workspace(session)

        self.assertEqual(workspace["session"]["status"], "draft")
        self.assertTrue(workspace["controls"]["can_start"])
        self.assertGreaterEqual(len(workspace["session"]["watch_symbols"]), 4)
        self.assertFalse(workspace["session"]["auto_execute_model"])
        self.assertEqual(workspace["session"]["auto_execute_status"], "research_candidate")
        self.assertTrue(workspace["session"]["auto_execute_note"])
        self.assertFalse(workspace["configuration"]["auto_execute_model"])
        self.assertEqual(workspace["configuration"]["auto_execute_status"], "research_candidate")
        self.assertTrue(workspace["kline"]["points"])
        self.assertEqual(workspace["manual_track"]["label"], "用户轨道")
        self.assertEqual(workspace["model_track"]["label"], "模型轨道")
        self.assertEqual(workspace["manual_track"]["portfolio"]["starting_cash"], workspace["session"]["initial_cash"])
        self.assertEqual(workspace["model_track"]["portfolio"]["starting_cash"], workspace["session"]["initial_cash"])
        self.assertIsNone(workspace["manual_track"]["portfolio"]["validation_artifact_id"])
        self.assertIsNone(workspace["model_track"]["portfolio"]["validation_artifact_id"])
        self.assertEqual(
            workspace["manual_track"]["portfolio"]["benchmark_context"]["source"],
            "active_watchlist_equal_weight_proxy",
        )
        self.assertEqual(
            workspace["manual_track"]["portfolio"]["benchmark_context"]["source_classification"],
            "migration_placeholder",
        )
        self.assertEqual(
            workspace["model_track"]["portfolio"]["benchmark_context"]["source"],
            "active_watchlist_equal_weight_proxy",
        )
        self.assertEqual(
            workspace["model_track"]["portfolio"]["performance"]["validation_mode"],
            "migration_placeholder",
        )
        self.assertTrue(workspace["model_advices"])
        first_advice = next((item for item in workspace["model_advices"] if item["action"] == "buy"), workspace["model_advices"][0])
        self.assertTrue(first_advice["reason"])
        self.assertIsInstance(first_advice["risk_flags"], list)
        self.assertEqual(first_advice["policy_status"], "research_candidate")
        self.assertEqual(first_advice["policy_type"], "phase5_simulation_topk_equal_weight_v1")
        self.assertTrue(first_advice["policy_note"])
        self.assertEqual(first_advice["action_definition"], "delta_to_constrained_target_weight_portfolio")
        self.assertEqual(
            first_advice["quantity_definition"],
            "board_lot_delta_to_target_weight",
        )
        self.assertGreaterEqual(first_advice.get("target_weight") or 0.0, 0.0)
        self.assertTrue(all(item["reason"] != legacy_reason for item in workspace["model_advices"]))
        self.assertTrue(all(legacy_risk not in item["risk_flags"] for item in workspace["model_advices"]))
        visible_text = "\n".join(collect_user_visible_text_fragments(workspace))
        self.assertIn("用户轨道", visible_text)
        self.assertIn("模型轨道", visible_text)
        self.assertEqual(find_banned_terms_in_text(visible_text), [])

    def test_session_can_start_step_trade_pause_resume_and_end(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            started = start_simulation_session(session)
            self.assertEqual(started["session"]["status"], "running")

            stepped = step_simulation_session(session)
            self.assertEqual(stepped["session"]["current_step"], 1)
            self.assertGreaterEqual(len(stepped["timeline"]), 3)
            self.assertEqual(stepped["model_track"]["portfolio"]["order_count"], 0)

            traded = place_manual_order(
                session,
                symbol=stepped["session"]["focus_symbol"] or stepped["session"]["watch_symbols"][0],
                side="buy",
                quantity=100,
                reason="参考模型建议后做人工确认买入。",
            )
            self.assertEqual(traded["manual_track"]["portfolio"]["order_count"], 1)
            self.assertTrue(any(item["manual_action"] != "未操作" for item in traded["decision_differences"]))

            paused = pause_simulation_session(session)
            self.assertEqual(paused["session"]["status"], "paused")

            resumed = resume_simulation_session(session)
            self.assertEqual(resumed["session"]["status"], "running")

            ended = end_simulation_session(session, confirm=True)
            self.assertEqual(ended["session"]["status"], "ended")
            self.assertFalse(ended["controls"]["can_end"])

    def test_auto_execute_can_drive_model_track_fills_in_simulation_only(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            workspace = get_simulation_workspace(session)
            self.assertFalse(workspace["session"]["auto_execute_model"])
            simulation_session = session.scalar(select(SimulationSession))
            assert simulation_session is not None
            simulation_session.auto_execute_model = True
            simulation_session.session_payload = {
                **(simulation_session.session_payload or {}),
                "requested_auto_execute_model": True,
            }
            session.commit()

        with session_scope(self.database_url) as session:
            workspace = get_simulation_workspace(session)
            self.assertTrue(workspace["session"]["auto_execute_model"])
            self.assertTrue(workspace["session"]["auto_execute_model_requested"])
            stepped = start_simulation_session(session)
            stepped = step_simulation_session(session)
            self.assertGreaterEqual(stepped["model_track"]["portfolio"]["order_count"], 1)
            self.assertTrue(
                any(item["track"] == "model" and item["event_type"] == "order_filled" for item in stepped["timeline"])
            )
            self.assertTrue(stepped["model_track"]["portfolio"]["recent_orders"])
            self.assertTrue(
                any(item["quantity"] > 0 for item in stepped["model_track"]["portfolio"]["holdings"])
            )

    def test_advance_running_session_catches_up_to_latest_market_bar_once(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            start_simulation_session(session)
            simulation_session = session.scalar(select(SimulationSession))
            assert simulation_session is not None
            latest_bar = session.scalar(select(MarketBar).order_by(MarketBar.observed_at.desc()).limit(1))
            assert latest_bar is not None
            simulation_session.last_data_time = latest_bar.observed_at - timedelta(minutes=5)
            session.commit()

        with session_scope(self.database_url) as session:
            workspace = advance_running_simulation_session(session)
            self.assertIsNotNone(workspace)
            assert workspace is not None
            self.assertEqual(workspace["session"]["current_step"], 1)
            self.assertEqual(workspace["session"]["last_data_time"], latest_bar.observed_at)

            second = advance_running_simulation_session(session)
            self.assertIsNone(second)

    def test_restart_creates_new_session_key(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            initial = get_simulation_workspace(session)
            initial_key = initial["session"]["session_key"]
            restarted = restart_simulation_session(session)

        self.assertNotEqual(restarted["session"]["session_key"], initial_key)
        self.assertEqual(restarted["session"]["status"], "running")
        self.assertEqual(restarted["session"]["restart_count"], 1)

    def test_kline_falls_back_to_daily_bars_when_intraday_is_missing(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            session.execute(delete(MarketBar).where(MarketBar.timeframe == "5min"))

        with session_scope(self.database_url) as session:
            workspace = get_simulation_workspace(session)

        self.assertTrue(workspace["kline"]["points"])
        self.assertGreaterEqual(len(workspace["kline"]["points"]), 20)

    def test_default_watchlist_scope_picks_up_new_active_symbols(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            initial = get_simulation_workspace(session)
            seed_recommendation_fixture(session, "688981.SH")
            add_watchlist_symbol(session, "688981", stock_name="中芯国际")
            updated = get_simulation_workspace(session)

        self.assertNotIn("688981.SH", initial["session"]["watch_symbols"])
        self.assertIn("688981.SH", updated["session"]["watch_symbols"])
        self.assertIn("688981.SH", updated["configuration"]["watch_symbols"])

    def test_workspace_bootstrap_normalizes_track_backtest_artifact_ids(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            get_simulation_workspace(session)
            portfolios = session.scalars(select(PaperPortfolio).order_by(PaperPortfolio.mode.asc())).all()

        self.assertTrue(portfolios)
        for portfolio in portfolios:
            payload = dict(portfolio.portfolio_payload or {})
            self.assertEqual(
                payload.get("backtest_artifact_id"),
                f"portfolio-backtest:{portfolio.portfolio_key}",
            )

    def test_custom_watchlist_scope_remains_custom_after_active_watchlist_changes(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            workspace = get_simulation_workspace(session)
            custom_watch_symbols = workspace["session"]["watch_symbols"][:2]
            updated = update_simulation_config(
                session,
                initial_cash=workspace["configuration"]["initial_cash"],
                watch_symbols=custom_watch_symbols,
                focus_symbol=custom_watch_symbols[0],
                step_interval_seconds=workspace["configuration"]["step_interval_seconds"],
                auto_execute_model=workspace["configuration"]["auto_execute_model"],
            )
            seed_recommendation_fixture(session, "688981.SH")
            add_watchlist_symbol(session, "688981", stock_name="中芯国际")
            after_watchlist_change = get_simulation_workspace(session)

        self.assertEqual(updated["session"]["watch_symbols"], custom_watch_symbols)
        self.assertEqual(after_watchlist_change["session"]["watch_symbols"], custom_watch_symbols)
        self.assertNotIn("688981.SH", after_watchlist_change["session"]["watch_symbols"])

    def test_workspace_model_advices_ignore_stale_same_as_of_backfill(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH",))
            fresh, stale = inject_market_data_stale_backfill(session, "600519.SH")

        with session_scope(self.database_url) as session:
            workspace = get_simulation_workspace(session)

        advice = next(item for item in workspace["model_advices"] if item["symbol"] == "600519.SH")
        self.assertEqual(advice["generated_at"], fresh.generated_at)
        self.assertNotEqual(advice["generated_at"], stale.generated_at)


if __name__ == "__main__":
    unittest.main()
