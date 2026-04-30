from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from ashare_evidence.api import create_app
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.simulation import get_simulation_workspace, start_simulation_session
from ashare_evidence.watchlist import (
    active_watchlist_symbols,
    add_watchlist_symbol,
    list_watchlist_entries,
    remove_watchlist_symbol,
)


class MultiAccountIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "multi-account.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_watchlist_follows_are_isolated_and_union_scope_survives_until_last_follower(self) -> None:
        with session_scope(self.database_url) as session:
            add_watchlist_symbol(
                session,
                "688981",
                stock_name="中芯国际",
                actor_login="member-a",
                actor_role="member",
                target_login="member-a",
            )
            add_watchlist_symbol(
                session,
                "688981",
                stock_name="中芯国际",
                actor_login="member-b",
                actor_role="member",
                target_login="member-b",
            )

            root_watchlist = list_watchlist_entries(session, actor_login="root", actor_role="root", target_login="root")
            member_a_watchlist = list_watchlist_entries(
                session,
                actor_login="member-a",
                actor_role="member",
                target_login="member-a",
            )
            member_b_watchlist = list_watchlist_entries(
                session,
                actor_login="member-b",
                actor_role="member",
                target_login="member-b",
            )

            self.assertNotIn("688981.SH", {item["symbol"] for item in root_watchlist["items"]})
            self.assertEqual({item["symbol"] for item in member_a_watchlist["items"]}, {"688981.SH"})
            self.assertEqual({item["symbol"] for item in member_b_watchlist["items"]}, {"688981.SH"})
            self.assertIn("688981.SH", set(active_watchlist_symbols(session)))

            remove_watchlist_symbol(
                session,
                "688981",
                actor_login="member-a",
                actor_role="member",
                target_login="member-a",
            )
            self.assertIn("688981.SH", set(active_watchlist_symbols(session)))

            remove_watchlist_symbol(
                session,
                "688981",
                actor_login="member-b",
                actor_role="member",
                target_login="member-b",
            )
            self.assertNotIn("688981.SH", set(active_watchlist_symbols(session)))

    def test_simulation_workspace_is_isolated_per_owner_and_blank_member_cannot_start(self) -> None:
        with session_scope(self.database_url) as session:
            add_watchlist_symbol(session, "600519", stock_name="贵州茅台")

            root_workspace = get_simulation_workspace(session, owner_login="root", actor_login="root", actor_role="root")
            member_workspace = get_simulation_workspace(
                session,
                owner_login="member-a",
                actor_login="member-a",
                actor_role="member",
            )

            self.assertGreaterEqual(len(root_workspace["session"]["watch_symbols"]), 1)
            self.assertNotEqual(root_workspace["session"]["session_key"], member_workspace["session"]["session_key"])
            self.assertEqual(member_workspace["session"]["watch_symbols"], [])
            self.assertFalse(member_workspace["controls"]["can_start"])

            with self.assertRaisesRegex(ValueError, "请先至少关注一只股票"):
                start_simulation_session(
                    session,
                    owner_login="member-a",
                    actor_login="member-a",
                    actor_role="member",
                )

            add_watchlist_symbol(
                session,
                "688981",
                stock_name="中芯国际",
                actor_login="member-a",
                actor_role="member",
                target_login="member-a",
            )
            member_workspace = get_simulation_workspace(
                session,
                owner_login="member-a",
                actor_login="member-a",
                actor_role="member",
            )
            self.assertEqual(member_workspace["session"]["watch_symbols"], ["688981.SH"])
            self.assertTrue(member_workspace["controls"]["can_start"])


class MultiAccountApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "multi-account-api.db"
        self.database_url = f"sqlite:///{database_path}"
        init_database(self.database_url)
        self.client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _headers(login: str, role: str, *, act_as: str | None = None) -> dict[str, str]:
        headers = {
            "X-HZ-User-Login": login,
            "X-HZ-User-Role": role,
        }
        if act_as:
            headers["X-Ashare-Act-As-Login"] = act_as
        return headers

    def test_member_routes_are_limited_and_root_can_act_as_other_account_space(self) -> None:
        member_headers = self._headers("member-a", "member")
        root_headers = self._headers("root", "root")

        watchlist_response = self.client.get("/watchlist", headers=member_headers)
        self.assertEqual(watchlist_response.status_code, 200)
        self.assertEqual(watchlist_response.json()["items"], [])

        runtime_overview = self.client.get("/runtime/overview", headers=member_headers)
        self.assertEqual(runtime_overview.status_code, 200)
        self.assertNotIn("provider_credentials", runtime_overview.json())

        runtime_settings = self.client.get("/settings/runtime", headers=member_headers)
        self.assertEqual(runtime_settings.status_code, 403)

        operations = self.client.get("/dashboard/operations?sample_symbol=600519.SH", headers=member_headers)
        self.assertEqual(operations.status_code, 403)

        manual_research = self.client.get("/manual-research/requests", headers=member_headers)
        self.assertEqual(manual_research.status_code, 403)

        follow_up = self.client.post(
            "/analysis/follow-up",
            headers=member_headers,
            json={"symbol": "600519.SH", "question": "test"},
        )
        self.assertEqual(follow_up.status_code, 403)

        root_context = self.client.get("/auth/context", headers=root_headers)
        self.assertEqual(root_context.status_code, 200)
        self.assertTrue(root_context.json()["can_act_as"])

        act_as_add = self.client.post(
            "/watchlist",
            headers=self._headers("root", "root", act_as="member-a"),
            json={"symbol": "688981", "name": "中芯国际"},
        )
        self.assertEqual(act_as_add.status_code, 200)

        act_as_watchlist = self.client.get("/watchlist", headers=self._headers("root", "root", act_as="member-a"))
        self.assertEqual(act_as_watchlist.status_code, 200)
        self.assertEqual({item["symbol"] for item in act_as_watchlist.json()["items"]}, {"688981.SH"})

        root_watchlist = self.client.get("/watchlist", headers=root_headers)
        self.assertEqual(root_watchlist.status_code, 200)
        self.assertNotIn("688981.SH", {item["symbol"] for item in root_watchlist.json()["items"]})

        member_cannot_act_as = self.client.get(
            "/auth/context",
            headers=self._headers("member-a", "member", act_as="root"),
        )
        self.assertEqual(member_cannot_act_as.status_code, 403)

    def test_authenticated_cookie_without_trusted_headers_is_rejected(self) -> None:
        response = self.client.get(
            "/auth/context",
            headers={"cookie": "hz_auth_session=fake-session"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("missing trusted identity headers", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
