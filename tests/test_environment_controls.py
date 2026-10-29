"""Failure-path checks for the local ENV validator; no real sandbox is started."""

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "scripts/validate_environment.py"
SPEC = importlib.util.spec_from_file_location("environment_validator", SOURCE)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


class EnvironmentControlsTests(unittest.TestCase):
    def test_expired_budget_does_not_launch_a_process(self):
        with patch.object(validator.subprocess, "run") as run:
            result = validator.probe("qh_review", "read", "synthetic", timeout=0)
        run.assert_not_called()
        self.assertEqual(result["outcome"], "not_run")

    def test_timeout_is_not_a_permission_denial_or_retry(self):
        with patch.object(
            validator.subprocess, "run",
            side_effect=subprocess.TimeoutExpired("synthetic", 0.5),
        ) as run:
            result = validator.probe("qh_review", "read", "synthetic", timeout=0.5)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.kwargs["timeout"], 0.5)
        self.assertEqual(result, {"outcome": "execution_error", "reason": "timeout"})

    def test_startup_failure_does_not_report_access_denied_or_raw_output(self):
        process = subprocess.CompletedProcess([], 71, "SYNTHETIC_RAW", "SYNTHETIC_RAW")
        with patch.object(validator.subprocess, "run", return_value=process):
            result = validator.probe("qh_review", "read", "synthetic")
        self.assertEqual(result, {"outcome": "startup_error", "exit_code": 71})
        self.assertNotIn("SYNTHETIC_RAW", str(result))

    def test_child_output_is_filtered_and_invalid_payload_rejected(self):
        for output in (
            '{"outcome":"allowed","raw":"SYNTHETIC_RAW"}',
            '{"outcome":"denied","errno":"SYNTHETIC_RAW"}',
            "SYNTHETIC_RAW",
            "[]",
            '{"outcome":[]}',
        ):
            with self.subTest(output=output), patch.object(
                validator.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0, output, ""),
            ):
                result = validator.probe("qh_review", "read", "synthetic")
                self.assertNotIn("SYNTHETIC_RAW", str(result))
                if output.startswith('{"outcome":"allowed"'):
                    self.assertEqual(result, {"outcome": "allowed"})
                else:
                    self.assertNotIn(result["outcome"], ("allowed", "denied"))

    def test_invalid_limits_rejected_before_execution(self):
        good = {"probe_timeout_seconds": 15, "probe_batch_timeout_seconds": 120,
                "automatic_retries": 0}
        self.assertEqual(validator.validation_limits({"validation": good}), (15, 120))
        for field, value in (
            ("probe_timeout_seconds", True), ("probe_timeout_seconds", 0),
            ("probe_batch_timeout_seconds", 10), ("probe_batch_timeout_seconds", 301),
            ("automatic_retries", 1),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validator.validation_limits({"validation": {**good, field: value}})


if __name__ == "__main__":
    unittest.main()
