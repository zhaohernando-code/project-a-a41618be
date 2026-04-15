from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from ashare_evidence.api import create_app


class BetaAccessApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "api-access.db"
        self.database_url = f"sqlite:///{database_path}"
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

    def test_dashboard_routes_require_beta_key_when_allowlist_enabled(self) -> None:
        os.environ["ASHARE_BETA_ACCESS_MODE"] = "allowlist"
        os.environ["ASHARE_BETA_ALLOWLIST"] = "viewer-token:viewer,operator-token:operator"
        os.environ["ASHARE_BETA_ACCESS_HEADER"] = "X-Ashare-Beta-Key"

        client = TestClient(create_app(self.database_url))
        bootstrap = client.post("/bootstrap/dashboard-demo", headers={"X-Ashare-Beta-Key": "operator-token"})
        self.assertEqual(bootstrap.status_code, 200)

        denied = client.get("/dashboard/candidates")
        self.assertEqual(denied.status_code, 403)
        self.assertIn("beta access denied", denied.json()["detail"])

        allowed = client.get("/dashboard/candidates", headers={"X-Ashare-Beta-Key": "viewer-token"})
        self.assertEqual(allowed.status_code, 200)
        self.assertGreaterEqual(len(allowed.json()["items"]), 1)

        viewer_write = client.post(
            "/watchlist",
            headers={"X-Ashare-Beta-Key": "viewer-token"},
            json={"symbol": "688981", "name": "中芯国际"},
        )
        self.assertEqual(viewer_write.status_code, 403)

        operator_write = client.post(
            "/watchlist",
            headers={"X-Ashare-Beta-Key": "operator-token"},
            json={"symbol": "688981", "name": "中芯国际"},
        )
        self.assertEqual(operator_write.status_code, 200)
        self.assertEqual(operator_write.json()["item"]["symbol"], "688981.SH")

        watchlist = client.get("/watchlist", headers={"X-Ashare-Beta-Key": "viewer-token"})
        self.assertEqual(watchlist.status_code, 200)
        self.assertIn("688981.SH", {item["symbol"] for item in watchlist.json()["items"]})


if __name__ == "__main__":
    unittest.main()
