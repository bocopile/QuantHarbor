from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import FrozenInstanceError
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from quantharbor.__main__ import main
from quantharbor.runtime.settings import SettingsError, load_settings, settings_from_mapping


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/runtime.synthetic.toml"


def config_mapping():
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))


class SettingsTests(unittest.TestCase):
    def test_example_loads_without_starting_any_service(self):
        value = load_settings(CONFIG)
        self.assertEqual(value.environment, "synthetic")
        self.assertEqual(value.new_cost_budget, 0)
        self.assertEqual(value.limits.max_retries, 0)
        with self.assertRaises(FrozenInstanceError):
            value.environment = "live"

    def test_flags_cannot_enable_external_or_paper_live_or_automation(self):
        for key in ("live_enabled", "paper_enabled", "automation_enabled", "external_broker_enabled",
                    "external_model_enabled", "external_reporting_enabled"):
            for attempted in (True, "false", 0, 1, None):
                value = config_mapping()
                value[key] = attempted
                with self.subTest(key=key, attempted=attempted), self.assertRaises(SettingsError):
                    settings_from_mapping(value)
        for key, attempted in (("environment", "paper"), ("environment", "live"),
                               ("binding_version", "live-v1"), ("database_namespace", "qh_live"),
                               ("queue_namespace", "qh_paper"), ("new_cost_budget", 1),
                               ("new_cost_budget", False), ("new_cost_budget", 0.0),
                               ("schema_version", True), ("schema_version", 2)):
            value = config_mapping()
            value[key] = attempted
            with self.subTest(key=key, attempted=attempted), self.assertRaises(SettingsError):
                settings_from_mapping(value)

    def test_required_keys_types_and_limits_fail_closed(self):
        baseline = config_mapping()
        for key in baseline:
            value = deepcopy(baseline)
            del value[key]
            with self.subTest(missing=key), self.assertRaises(SettingsError):
                settings_from_mapping(value)
        for key in baseline["limits"]:
            value = deepcopy(baseline)
            del value["limits"][key]
            with self.subTest(limit_missing=key), self.assertRaises(SettingsError):
                settings_from_mapping(value)
            for invalid in (None, True, 1.0, "1", -1, 999999999999):
                value = deepcopy(baseline)
                value["limits"][key] = invalid
                with self.subTest(limit=key, invalid=invalid), self.assertRaises(SettingsError):
                    settings_from_mapping(value)
        for level in ("wrapper", "limits"):
            value = deepcopy(baseline)
            target = value if level == "wrapper" else value["limits"]
            target["unexpected_override"] = "synthetic-only"
            with self.subTest(level=level), self.assertRaises(SettingsError):
                settings_from_mapping(value)
        for invalid in (None, [], "synthetic", True):
            with self.subTest(invalid=invalid), self.assertRaises(SettingsError):
                settings_from_mapping(invalid)
        value = deepcopy(baseline)
        value["limits"] = []
        with self.assertRaises(SettingsError):
            settings_from_mapping(value)

    def test_invalid_files_produce_fixed_errors_without_input(self):
        canary = "SYNTHETIC_CANARY_NOT_A_SECRET"
        with tempfile.TemporaryDirectory(prefix="qh-synthetic-") as directory:
            path = Path(directory) / "config.toml"
            for raw in (f'{canary} = "unterminated'.encode(), b"\xff", b"x" * 65537,
                        b"schema_version = 1\nschema_version = 1"):
                path.write_bytes(raw)
                with self.subTest(size=len(raw)), self.assertRaises(SettingsError) as caught:
                    load_settings(path)
                self.assertEqual(str(caught.exception), "Invalid synthetic configuration.")
            with self.assertRaises(SettingsError) as caught:
                load_settings(Path(directory) / canary)
            self.assertNotIn(canary, str(caught.exception))


class CLITests(unittest.TestCase):
    def invoke(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_explicit_version_status_help_and_config(self):
        for args, marker in ((["--version"], "QuantHarbor 0.1.0"),
                             (["status"], "inactive; synthetic only; external disabled"),
                             (["--help"], "Usage:"),
                             (["validate-config", str(CONFIG)], "no services started")):
            with self.subTest(args=args):
                code, stdout, stderr = self.invoke(args)
                self.assertEqual(code, 0)
                self.assertIn(marker, stdout)
                self.assertEqual(stderr, "")

    def test_unrecognized_commands_and_arguments_are_redacted(self):
        canary = "SYNTHETIC_CLI_CANARY"
        for args in ([], [canary], ["start"], ["status", canary],
                     ["validate-config"], ["validate-config", canary, "extra"], [True]):
            with self.subTest(args=args):
                self.assertEqual(self.invoke(args), (2, "", "QuantHarbor: invalid command.\n"))
        code, stdout, stderr = self.invoke(["validate-config", "/nonexistent/" + canary])
        self.assertEqual((code, stdout, stderr),
                         (2, "", "QuantHarbor: invalid synthetic configuration.\n"))

    def test_unexpected_loader_failure_is_redacted(self):
        with patch("quantharbor.__main__.load_settings",
                   side_effect=RuntimeError("SYNTHETIC_PRIVATE_CANARY")):
            self.assertEqual(self.invoke(["validate-config", "synthetic.toml"]),
                             (2, "", "QuantHarbor: invalid synthetic configuration.\n"))

    def test_module_entrypoint_uses_no_environment_enable_override(self):
        for args, code in ((["status"], 0), (["validate-config", str(CONFIG)], 0),
                           (["start", "SYNTHETIC_CLI_CANARY"], 2)):
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, "-m", "quantharbor", *args],
                    cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1",
                                   "QH_ENVIRONMENT": "live", "QH_EXTERNAL_BROKER_ENABLED": "true"},
                    capture_output=True, text=True, timeout=5, check=False,
                )
                self.assertEqual(result.returncode, code)
                self.assertNotIn("SYNTHETIC_CLI_CANARY", result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
