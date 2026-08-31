#!/usr/bin/env python3
"""Unit tests for aasp-metrics-adapter (no network)."""

from __future__ import annotations

import importlib
import json
import os
import unittest
from datetime import datetime, timezone
from unittest import mock


def load_adapter(env: dict[str, str] | None = None):
    env = env or {}
    base = {
        "PROJECT_ID": "proj-1",
        "SERVICE_GROUP_ID": "sg-1",
        "REGION": "cn-east-204-dev",
        "TOKEN": "test-token",
        "MOCK": "0",
        "LEADER_ELECTION": "0",
        "POD_NAME": "test-pod",
    }
    base.update(env)
    with mock.patch.dict(os.environ, base, clear=False):
        import adapter as mod

        return importlib.reload(mod)


class AdapterTests(unittest.TestCase):
    def test_build_url_contains_path_and_query(self):
        mod = load_adapter()
        url = mod.build_url(datetime(2026, 3, 30, 8, 0, 0))
        self.assertIn("/v1/proj-1/sg-1/infer-recommendations?", url)
        self.assertIn("start_time=2026-03-30T08:00:00", url)
        self.assertIn("end_time=2026-03-30T08:05:00", url)
        self.assertIn("region=cn-east-204-dev", url)

    def test_build_url_instance_path_and_backward_range(self):
        mod = load_adapter(
            {
                "INSTANCE_ID": "922ae983-addb-46e8-8096-5092de62af13",
                "SERVICE_GROUP_ID": "",
                "TIME_RANGE_MODE": "backward",
                "WINDOW_MINUTES": "60",
                "REGION": "cn-north-5",
            }
        )
        url = mod.build_url(datetime(2026, 8, 31, 18, 0, 0))
        self.assertIn(
            "/v1/proj-1/instance/922ae983-addb-46e8-8096-5092de62af13/infer-recommendations?",
            url,
        )
        self.assertIn("start_time=2026-08-31T17:00:00", url)
        self.assertIn("end_time=2026-08-31T18:00:00", url)
        self.assertIn("region=cn-north-5", url)

    def test_auth_headers_x_auth_token(self):
        mod = load_adapter({"AUTH_HEADER": "x-auth-token", "TOKEN": "abc"})
        headers = mod.auth_headers()
        self.assertEqual(headers.get("X-Auth-Token"), "abc")
        self.assertNotIn("Authorization", headers)

    def test_pick_resources_object(self):
        mod = load_adapter()
        body = {"resources": {"service_group_id": "sg-1", "predictions": []}}
        self.assertEqual(mod.pick_resources(body)["service_group_id"], "sg-1")

    def test_pick_resources_list_filters_region(self):
        mod = load_adapter({"REGION": "cn-east-204-dev"})
        body = {
            "resources": [
                {"region": "cn-north-4", "predictions": []},
                {"region": "cn-east-204-dev", "predictions": [{"rpm": 1}]},
            ]
        }
        picked = mod.pick_resources(body)
        self.assertEqual(picked["region"], "cn-east-204-dev")

    def test_max_from_predictions(self):
        mod = load_adapter()
        preds = [
            {"rpm": 10, "prompt_tpm": 5},
            {"rpm": 40, "prompt_tpm": 3},
            {"rpm": 20, "prompt_tpm": 9},
        ]
        self.assertEqual(mod.max_from_predictions(preds, "rpm"), 40.0)
        self.assertEqual(mod.max_from_predictions(preds, "prompt_tpm"), 9.0)
        self.assertEqual(mod.max_from_predictions(preds, "missing"), 0.0)

    def test_max_from_predictions_token_aliases(self):
        mod = load_adapter()
        preds = [{"rpm": 1, "prompt_token": 100, "completion_token": 50}]
        self.assertEqual(
            mod.max_from_predictions(preds, "prompt_tpm", "prompt_token"), 100.0
        )
        self.assertEqual(
            mod.max_from_predictions(preds, "completion_tpm", "completion_token"), 50.0
        )

    def test_collect_predictions_lab_map_shape(self):
        mod = load_adapter({"REGION": "cn-north-5"})
        body = {
            "resources": {
                "infer_service_group_id_test": {
                    "region": "cn-north-5",
                    "prediction": [
                        {
                            "rpm": 2976.7,
                            "prompt_token": 100709.3,
                            "completion_token": 49938.1,
                        }
                    ],
                },
                "service_group_id_test2": {
                    "region": "cn-north-5",
                    "prediction": [
                        {
                            "rpm": 2992.7,
                            "prompt_token": 102282.0,
                            "completion_token": 51007.0,
                        }
                    ],
                },
            }
        }
        preds = mod.collect_predictions(body)
        self.assertEqual(len(preds), 2)
        self.assertEqual(mod.max_from_predictions(preds, "rpm"), 2992.7)
        self.assertEqual(
            mod.max_from_predictions(preds, "prompt_tpm", "prompt_token"), 102282.0
        )

    def test_fetch_once_parses_lab_response(self):
        mod = load_adapter(
            {
                "INSTANCE_ID": "922ae983-addb-46e8-8096-5092de62af13",
                "SERVICE_GROUP_ID": "",
                "AUTH_HEADER": "x-auth-token",
                "REGION": "cn-north-5",
                "TIME_RANGE_MODE": "backward",
            }
        )
        payload = {
            "resources": {
                "g1": {
                    "region": "cn-north-5",
                    "prediction": [
                        {
                            "rpm": 2976.7,
                            "prompt_token": 100.0,
                            "completion_token": 50.0,
                        }
                    ],
                },
                "g2": {
                    "region": "cn-north-5",
                    "prediction": [
                        {
                            "rpm": 2992.7,
                            "prompt_token": 200.0,
                            "completion_token": 80.0,
                        }
                    ],
                },
            }
        }
        raw = json.dumps(payload).encode("utf-8")

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return raw

        with mock.patch.object(mod, "urlopen", return_value=FakeResp()):
            mod.fetch_once()
        with mod.state_lock:
            self.assertEqual(mod.state["adapter_up"], 1)
            self.assertEqual(mod.state["rpm"], 2992.7)
            self.assertEqual(mod.state["prompt_tpm"], 200.0)
            self.assertEqual(mod.state["completion_tpm"], 80.0)
            self.assertEqual(mod.state["total_tpm"], 280.0)

    def test_fetch_mock_updates_state(self):
        mod = load_adapter(
            {
                "MOCK": "1",
                "MOCK_RPM": "300",
                "MOCK_PROMPT_TPM": "180000",
                "MOCK_COMPLETION_TPM": "90000",
            }
        )
        mod.fetch_once()
        with mod.state_lock:
            self.assertEqual(mod.state["rpm"], 300.0)
            self.assertEqual(mod.state["prompt_tpm"], 180000.0)
            self.assertEqual(mod.state["completion_tpm"], 90000.0)
            self.assertEqual(mod.state["adapter_up"], 1)

    def test_render_metrics_contains_gauges(self):
        mod = load_adapter({"MOCK": "1", "MOCK_RPM": "12"})
        mod.fetch_once()
        text = mod.render_metrics().decode("utf-8")
        self.assertIn("aasp_predicted_rpm{", text)
        self.assertIn("aasp_predicted_prompt_tpm{", text)
        self.assertIn("aasp_predicted_completion_tpm{", text)
        self.assertIn("} 12.0", text)
        self.assertIn("aasp_adapter_is_leader{", text)

    def test_follower_renders_zero_predicted_metrics(self):
        mod = load_adapter({"MOCK": "1", "MOCK_RPM": "99", "POD_NAME": "follower-pod"})
        mod.fetch_once()

        class FakeElection:
            def is_leader(self):
                return False

        mod._election = FakeElection()
        text = mod.render_metrics().decode("utf-8")
        self.assertRegex(text, r"aasp_predicted_rpm\{[^}]+\} 0\.0")
        self.assertRegex(text, r"aasp_adapter_is_leader\{[^}]+\} 0")

    def test_keep_last_value_on_error(self):
        mod = load_adapter({"MOCK": "1", "MOCK_RPM": "55"})
        mod.fetch_once()
        mod.apply_peaks(0, 0, 0, error="boom")
        with mod.state_lock:
            self.assertEqual(mod.state["rpm"], 55.0)
            self.assertEqual(mod.state["adapter_up"], 0)
            self.assertEqual(mod.state["last_error"], "boom")


class LeaseHelpersTests(unittest.TestCase):
    def test_lease_expired_without_renew(self):
        from leader_election import LeaseLeaderElection

        elec = LeaseLeaderElection.__new__(LeaseLeaderElection)
        elec.lease_duration_seconds = 15
        self.assertTrue(elec._lease_expired({"spec": {}}))

    def test_lease_not_expired_recent_renew(self):
        from leader_election import LeaseLeaderElection

        elec = LeaseLeaderElection.__new__(LeaseLeaderElection)
        elec.lease_duration_seconds = 15
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self.assertFalse(
            elec._lease_expired({"spec": {"renewTime": now, "leaseDurationSeconds": 15}})
        )


if __name__ == "__main__":
    unittest.main()
