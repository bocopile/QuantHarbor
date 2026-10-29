from dataclasses import asdict, replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quantharbor.runtime.boundary import (
    BoundaryError, SyntheticController, authorize, binding_from_mapping,
    synthetic_binding, validate_private_path,
)


class BindingTests(unittest.TestCase):
    def test_role_actions_are_explicit_and_financial_paths_disabled(self):
        binding = synthetic_binding("research")
        authorize(binding, "synthetic.compute")
        for action in ("broker.submit", "broker.query", "ledger.write", "approval.write",
                       "external.report", "model.invoke", "synthetic.session"):
            with self.subTest(action=action), self.assertRaises(BoundaryError):
                authorize(binding, action)
        with self.assertRaises(BoundaryError):
            authorize(synthetic_binding("reporting"), "synthetic.compute")
        with self.assertRaises(BoundaryError):
            synthetic_binding("egress")

    def test_binding_fields_versions_environment_and_types_fail_closed(self):
        valid = asdict(synthetic_binding("research"))
        self.assertEqual(binding_from_mapping(valid).role, "research")
        for key in valid:
            for invalid in (None, True, "live", "paper", "other-synthetic"):
                changed = valid | {key: invalid}
                with self.subTest(key=key, invalid=invalid), self.assertRaises(BoundaryError):
                    binding_from_mapping(changed)
            missing = valid.copy()
            del missing[key]
            with self.subTest(missing=key), self.assertRaises(BoundaryError):
                binding_from_mapping(missing)
        with self.assertRaises(BoundaryError):
            binding_from_mapping(valid | {"override": "disabled"})
        forged = replace(synthetic_binding("research"))
        object.__setattr__(forged, "host", "live-host")
        with self.assertRaises(BoundaryError):
            authorize(forged, "synthetic.compute")


class PrivatePathTests(unittest.TestCase):
    def test_metadata_only_directory_file_and_permission_checks(self):
        with tempfile.TemporaryDirectory(prefix="qh-synthetic-private-") as raw:
            directory = Path(raw).resolve()
            directory.chmod(0o700)
            file = directory / "synthetic.txt"
            file.write_text("SYNTHETIC_ONLY", encoding="utf-8")
            file.chmod(0o600)
            with patch("builtins.open", side_effect=AssertionError("content_must_not_be_read")):
                validate_private_path(directory)
                validate_private_path(file, kind="file")
            file.chmod(0o644)
            with self.assertRaises(BoundaryError):
                validate_private_path(file, kind="file")
            file.chmod(0o600)
            directory.chmod(0o755)
            with self.assertRaises(BoundaryError):
                validate_private_path(directory)
            with self.assertRaises(BoundaryError):
                validate_private_path(file, kind="file")

    def test_symlinks_hardlinks_repository_and_traversal_are_rejected(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix="qh-synthetic-private-") as raw:
            directory = Path(raw).resolve()
            file = directory / "synthetic.txt"
            file.write_text("SYNTHETIC_ONLY", encoding="utf-8")
            file.chmod(0o600)
            link = directory / "alias"
            link.symlink_to(file)
            for value, kind in ((link, "file"), (root, "directory"),
                                ("/" + str(root), "directory"), (directory / "..", "directory"),
                                ("relative", "directory"), (directory / "absent", "directory")):
                with self.subTest(kind=kind), self.assertRaises(BoundaryError):
                    validate_private_path(value, kind=kind)
            link.unlink()
            link.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(BoundaryError):
                validate_private_path(link / "synthetic.txt", kind="file")
            os.link(file, directory / "hardlink")
            with self.assertRaises(BoundaryError):
                validate_private_path(file, kind="file")
            with patch("quantharbor.runtime.boundary.os.getuid", return_value=os.getuid() + 1):
                with self.assertRaises(BoundaryError):
                    validate_private_path(directory)


class LivenessTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.controller = SyntheticController(synthetic_binding("controller"))
        self.session = self.controller.new_liveness(clock=lambda: self.now)

    def test_renewal_requires_own_controller_and_fresh_running_session(self):
        self.assertFalse(self.session.check())
        self.session.resume(self.controller)
        self.assertTrue(self.session.check())
        with self.assertRaises(BoundaryError):
            self.session.renew(SyntheticController(synthetic_binding("controller")))
        self.now += 29
        self.session.renew(self.controller)
        self.now += 29
        self.assertTrue(self.session.check())
        with self.assertRaises(BoundaryError):
            SyntheticController(synthetic_binding("research"))

    def test_timeout_and_disconnect_do_not_automatically_resume(self):
        self.session.resume(self.controller)
        self.now += 30
        self.assertFalse(self.session.check())
        self.assertEqual(self.session.state, "faulted")
        with self.assertRaises(BoundaryError):
            self.session.renew(self.controller)
        self.session.resume(self.controller)
        self.session.disconnect(self.controller)
        with self.assertRaises(BoundaryError):
            self.session.renew(self.controller)
        self.assertFalse(self.session.check())
        self.session.resume(self.controller)
        self.assertTrue(self.session.check())

    def test_invalid_or_backward_clock_faults_closed(self):
        for value in (float("nan"), float("inf"), -1, True, None, "100", 99.9):
            session = self.controller.new_liveness(clock=lambda: self.now)
            self.now = 100.0
            session.resume(self.controller)
            self.now = value
            with self.subTest(value=value), self.assertRaises(BoundaryError):
                session.check()
            self.assertEqual(session.state, "faulted")


if __name__ == "__main__":
    unittest.main()
