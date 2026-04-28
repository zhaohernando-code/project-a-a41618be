from __future__ import annotations

import unittest
from pathlib import Path

from ashare_evidence.release_verifier import (
    BANNED_USER_VISIBLE_TERMS,
    REQUIRED_TRACK_TERMS,
    audit_user_visible_operations_text,
    build_release_manifest,
    extract_asset_references,
    fingerprint_payload,
    normalize_payload_for_fingerprint,
)


class ReleaseVerifierTests(unittest.TestCase):
    def test_extract_asset_references_parses_index_assets(self) -> None:
        html = """
        <html>
          <head>
            <link rel="stylesheet" href="/projects/ashare-dashboard/assets/index-abc123.css" />
            <script type="module" src="/projects/ashare-dashboard/assets/index-def456.js"></script>
            <script type="module" src="/projects/ashare-dashboard/assets/index-def456.js"></script>
          </head>
        </html>
        """

        assets = extract_asset_references(html)

        self.assertEqual(
            assets,
            [
                {
                    "name": "assets/index-abc123.css",
                    "ref": "/projects/ashare-dashboard/assets/index-abc123.css",
                },
                {
                    "name": "assets/index-def456.js",
                    "ref": "/projects/ashare-dashboard/assets/index-def456.js",
                },
            ],
        )

    def test_normalize_payload_for_fingerprint_ignores_runtime_noise(self) -> None:
        left = {
            "generated_at": "2026-04-26T00:00:00+00:00",
            "session_key": "left",
            "overview": {
                "last_market_data_at": "2026-04-26T08:00:00+08:00",
                "note": "same",
            },
            "items": [{"symbol": "600519.SH", "updated_at": "2026-04-26T01:00:00+00:00"}],
        }
        right = {
            "generated_at": "2026-04-27T00:00:00+00:00",
            "session_key": "right",
            "overview": {
                "last_market_data_at": "2026-04-27T08:00:00+08:00",
                "note": "same",
            },
            "items": [{"symbol": "600519.SH", "updated_at": "2026-04-27T01:00:00+00:00"}],
        }

        self.assertEqual(
            normalize_payload_for_fingerprint(left),
            normalize_payload_for_fingerprint(right),
        )
        self.assertEqual(fingerprint_payload(left), fingerprint_payload(right))

    def test_normalize_payload_for_fingerprint_ignores_data_latency_seconds(self) -> None:
        left = {
            "simulation_workspace": {
                "session": {
                    "data_latency_seconds": 32889,
                    "intraday_source_status": {
                        "data_latency_seconds": 32889,
                        "status": "stale",
                    },
                }
            }
        }
        right = {
            "simulation_workspace": {
                "session": {
                    "data_latency_seconds": 32890,
                    "intraday_source_status": {
                        "data_latency_seconds": 32890,
                        "status": "stale",
                    },
                }
            }
        }

        self.assertEqual(
            normalize_payload_for_fingerprint(left),
            normalize_payload_for_fingerprint(right),
        )
        self.assertEqual(fingerprint_payload(left), fingerprint_payload(right))

    def test_normalize_payload_for_fingerprint_ignores_performance_launch_gate_current_value(self) -> None:
        left = {
            "overview": {"launch_readiness": {"warning_gate_count": 4}},
            "launch_gates": [
                {
                    "gate": "刷新与性能预算",
                    "status": "warn",
                    "current_value": "stock 19.4ms / ops 213.0ms / ops payload 153.2kb",
                }
            ]
        }
        right = {
            "overview": {"launch_readiness": {"warning_gate_count": 3}},
            "launch_gates": [
                {
                    "gate": "刷新与性能预算",
                    "status": "pass",
                    "current_value": "stock 5.3ms / ops 131.2ms / ops payload 153.2kb",
                }
            ]
        }

        self.assertEqual(
            normalize_payload_for_fingerprint(left),
            normalize_payload_for_fingerprint(right),
        )
        self.assertEqual(fingerprint_payload(left), fingerprint_payload(right))

    def test_normalize_payload_for_fingerprint_ignores_performance_threshold_observed(self) -> None:
        left = {
            "performance_thresholds": [
                {
                    "metric": "模拟交易运营面板构建延迟",
                    "observed": 236.1,
                    "status": "warn",
                    "target": 320.0,
                    "unit": "ms",
                }
            ]
        }
        right = {
            "performance_thresholds": [
                {
                    "metric": "模拟交易运营面板构建延迟",
                    "observed": 131.2,
                    "status": "pass",
                    "target": 320.0,
                    "unit": "ms",
                }
            ]
        }

        self.assertEqual(
            normalize_payload_for_fingerprint(left),
            normalize_payload_for_fingerprint(right),
        )
        self.assertEqual(fingerprint_payload(left), fingerprint_payload(right))

    def test_operations_text_audit_requires_dual_track_and_blocks_regression_terms(self) -> None:
        good_payload = {
            "simulation_workspace": {
                "manual_track": {"label": "用户轨道"},
                "model_track": {"label": "模型轨道"},
                "session": {"auto_execute_note": "当前仅 Web 模拟盘支持自动执行，不会触发真实交易。"},
                "model_advices": [{"policy_note": "模型轨道会先生成研究建议，再进入模拟复盘。"}],
            }
        }

        good_audit = audit_user_visible_operations_text(good_payload)
        self.assertTrue(good_audit["passed"])
        self.assertEqual(good_audit["missing_required_terms"], [])
        self.assertEqual(good_audit["banned_hits"], [])

        bad_payload = {
            "simulation_workspace": {
                "manual_track": {"label": "用户轨道"},
                "session": {"auto_execute_note": "模型轨道建议（Phase 5 baseline）仍在迁移，manifest 待核对。"},
            }
        }
        bad_audit = audit_user_visible_operations_text(bad_payload)
        self.assertFalse(bad_audit["passed"])
        self.assertIn("模型轨道", bad_audit["combined_text"])
        self.assertIn("模型轨道", REQUIRED_TRACK_TERMS)
        self.assertIn("Phase 5 baseline", bad_audit["banned_hits"])
        self.assertIn("manifest", BANNED_USER_VISIBLE_TERMS)

    def test_build_release_manifest_records_previous_successful_manifest(self) -> None:
        manifest = build_release_manifest(
            release_id="20260426T123000Z-abcdef123456",
            commit_sha="abcdef1234567890",
            released_at="2026-04-26T12:30:00+00:00",
            repo_root=Path("/repo"),
            runtime_root=Path("/runtime"),
            local_frontend_url="http://127.0.0.1:5173/",
            local_api_base_url="http://127.0.0.1:8000/",
            canonical_base_url="https://hernando-zhao.cn/projects/ashare-dashboard/",
            artifact_root=Path("/repo/output/releases/20260426T123000Z-abcdef123456"),
            previous_successful_manifest={
                "manifest_path": "/repo/output/releases/older/manifest.json",
                "commit_sha": "oldercommit",
            },
            asset_sets={"all_match": True},
            api_fingerprints={"/dashboard/operations": {"match": True}},
            operations_text_audit={"match": True},
            artifact_paths={"local_dashboard_operations": "/tmp/local-dashboard-operations.json"},
        )

        self.assertEqual(manifest["status"], "passed")
        self.assertEqual(
            manifest["rollback"]["previous_successful_manifest_path"],
            "/repo/output/releases/older/manifest.json",
        )
        self.assertEqual(manifest["rollback"]["previous_successful_commit_sha"], "oldercommit")
        self.assertEqual(
            manifest["manifest_path"],
            "/repo/output/releases/20260426T123000Z-abcdef123456/manifest.json",
        )


if __name__ == "__main__":
    unittest.main()
