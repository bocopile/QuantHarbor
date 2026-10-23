"""Codex·모델 호출 없이 mock event와 합성 process group으로 검증한다."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "qh_validate_role_boundary", Path(__file__).resolve().parents[1] / "scripts/validate_role_boundary.py")
boundary = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = boundary
SPEC.loader.exec_module(boundary)

EXPECTED = {"public_read": "allowed", "private_read": "denied", "workspace_write": "denied"}


def events(command="synthetic-exact-command", nonce="synthetic-nonce", values=None):
    item = {"id": "synthetic-command-1", "type": "command_execution", "command": command}
    return [
        {"type": "thread.started", "thread_id": "synthetic-thread"},
        {"type": "turn.started"},
        {"type": "item.started", "item": dict(item)},
        {"type": "item.completed", "item": {**item, "exit_code": 0,
            "aggregated_output": json.dumps({"probe_nonce": nonce, "results": EXPECTED if values is None else values})}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "Probe finished"}},
        {"type": "turn.completed"},
    ]


def encoded(rows):
    return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()


@unittest.skipUnless(os.name == "posix", "POSIX 전용")
class RoleBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="qh-role-boundary-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / ".codex").mkdir()
        (self.root / "config/ai").mkdir(parents=True)
        (self.root / ".codex/config.toml").write_text(
            '[permissions.qh_review]\nextends = ":read-only"\n'
            '[permissions.qh_development]\nextends = ":workspace"\n')
        (self.root / "config/ai/team.toml").write_text(
            '[[members]]\nname="qh_validator"\nmodel="synthetic-model"\nreasoning_effort="high"\n'
            '[[members]]\nname="qh_implementer"\nmodel="synthetic-model"\nreasoning_effort="high"\n')
        manager = patch.object(boundary, "ROOT", self.root)
        manager.start()
        self.addCleanup(manager.stop)

    def fixture_run(self, transform=None, mode="review"):
        """CLI 응답만 합성한다. CLI·모델·프로브 명령을 실제 실행하지 않는다."""
        def fake_capture(command, timeout, pending):
            if command == ["codex", "login", "status"]:
                return boundary.Capture(0, b"Logged in using ChatGPT", b"")
            self.assertEqual(["codex", "exec", "--ephemeral", "--ignore-user-config"], command[:4])
            self.assertIn("forced_login_method=\"chatgpt\"", command)
            mcp_override = next(value for value in command
                                if value.startswith("mcp_servers.codebase-memory-mcp="))
            mcp_config = boundary.tomllib.loads(mcp_override)["mcp_servers"]["codebase-memory-mcp"]
            self.assertEqual({"command": "codebase-memory-mcp", "enabled": False}, mcp_config)
            exact = command[-1].split("subagents: ", 1)[1].split("\n", 1)[0]
            work = Path(shlex.split(exact)[-1]).parent
            nonce = json.loads((work / "fixture.json").read_text())["nonce"]
            values = dict(EXPECTED)
            if mode == "development":
                values["workspace_write"] = "allowed"
                (work / "created.txt").write_text(boundary.MARKER)
            rows = events(exact, nonce, values)
            if transform:
                transform(rows, work)
            return boundary.Capture(0, encoded(rows), b"synthetic stderr never reported")
        with patch.object(boundary, "capture", side_effect=fake_capture) as captured:
            report = boundary.run(mode)
        self.assertEqual(2, captured.call_count)
        self.assertFalse((self.root / "logs").exists())
        self.assertFalse(list(self.root.glob(".qh-role-validation-*")))
        return report

    def test_started_completed_same_id_counts_once_and_valid_payload_passes(self):
        for mode in ("review", "development"):
            with self.subTest(mode=mode):
                report = self.fixture_run(mode=mode)
                self.assertTrue(report["passed"])
                self.assertEqual("verified", report["reason"])
                self.assertEqual(1, report["verified_tool_probe_count"])

    def test_extra_commands_tools_unknown_events_and_lifecycle_are_rejected(self):
        def extra_command(rows):
            rows.insert(4, {"type": "item.started", "item": {
                "id": "second-command", "type": "command_execution", "command": "unexpected synthetic command"}})
        variants = [
            extra_command,
            lambda rows: rows.insert(4, {"type": "item.started", "item": {"id": "tool", "type": "mcp_tool_call"}}),
            lambda rows: rows.append({"type": "unknown.future.event"}),
            lambda rows: rows[2]["item"].update(command="changed command"),
            lambda rows: rows[3]["item"].update(id="different-command"),
            lambda rows: rows.insert(3, rows[2]),
            lambda rows: rows.pop(2),
        ]
        for transform in variants:
            with self.subTest(transform=transform):
                report = self.fixture_run(lambda rows, _work: transform(rows))
                self.assertFalse(report["passed"])
                self.assertIsNone(report["observed"])

    def test_observed_zsh_wrapper_requires_exact_inner_command_and_no_extra_arguments(self):
        def wrapped(rows, _work):
            for row in rows[2:4]:
                row["item"]["command"] = shlex.join(
                    ["/bin/zsh", "-lc", row["item"]["command"]])
        self.assertTrue(self.fixture_run(wrapped)["passed"])
        for suffix, extra in (("; true", []), ("\ntrue", []), ("", ["extra"])):
            def changed(rows, _work):
                for row in rows[2:4]:
                    row["item"]["command"] = shlex.join(
                        ["/bin/zsh", "-lc", row["item"]["command"] + suffix] + extra)
            with self.subTest(suffix=suffix, extra=extra):
                self.assertFalse(self.fixture_run(changed)["passed"])

    def test_original_public_fixture_and_probe_bytes_are_verified_outside(self):
        for filename in ("public.txt", "fixture.json", "probe.py"):
            def tamper(_rows, work):
                path = work / filename
                path.write_bytes(path.read_bytes() + b"\nsynthetic-tampering")
            with self.subTest(filename=filename):
                report = self.fixture_run(tamper)
                self.assertFalse(report["outside_fixture_verification"])
                self.assertFalse(report["passed"])

    def test_nonce_alone_cannot_authorize_raw_or_extra_probe_results(self):
        secret = "QH_FAKE_SECRET_MUST_NOT_APPEAR_47291"
        variants = [
            {**EXPECTED, "private_read": secret},
            {**EXPECTED, "extra": secret},
            {key: value for key, value in EXPECTED.items() if key != "public_read"},
            [secret],
        ]
        for values in variants:
            def tamper(rows, _work):
                result = json.loads(rows[3]["item"]["aggregated_output"])
                result["results"] = values
                rows[3]["item"]["aggregated_output"] = json.dumps(result)
            with self.subTest(values=values):
                report = self.fixture_run(tamper)
                self.assertFalse(report["passed"])
                self.assertEqual("invalid_probe_output", report["reason"])
                self.assertIsNone(report["observed"])
                self.assertNotIn(secret, json.dumps(report))

    def test_nonzero_stderr_gets_only_fixed_classification(self):
        cases = (
            (b"private value: default_permissions conflicts with sandbox_mode", "config_conflict"),
            (b"private value: operation not permitted", "host_sandbox_blocked"),
            (b"private value: authentication needed", "auth_required"),
        )
        for stderr, reason in cases:
            with self.subTest(reason=reason), patch.object(boundary, "capture", side_effect=[
                    boundary.Capture(0, b"Logged in using ChatGPT", b""), boundary.Capture(1, b"", stderr)]):
                report = boundary.run("review")
                self.assertFalse(report["passed"])
                self.assertEqual(reason, report["reason"])
                self.assertNotIn("private value", json.dumps(report))

    def test_stdout_and_stderr_limits_stop_without_storing_overflow(self):
        for fd, reason in ((1, "cli_stdout_limit"), (2, "cli_stderr_limit")):
            code = f"import os,time\nos.write({fd}, b'QH_SYNTHETIC_SECRET' * 2048)\ntime.sleep(10)"
            with self.subTest(fd=fd), patch.object(boundary, "STDOUT_LIMIT", 1024), patch.object(boundary, "STDERR_LIMIT", 128):
                result = boundary.capture([sys.executable, "-B", "-c", code], 3, [])
                self.assertEqual(reason, result.reason)
                self.assertLessEqual(len(result.stdout), 1024)
                self.assertLessEqual(len(result.stderr), 128)
                self.assertIsNotNone(result.exit_code)

    def wait_until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("synthetic process deadline exceeded")
            time.sleep(0.01)

    def tree_code(self, marker, parent_exits=False):
        ready = marker.with_suffix(".ready")
        grandchild = ("import signal,time\nfrom pathlib import Path\n"
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                      f"Path({str(ready)!r}).write_text('synthetic-ready')\n"
                      "while True: time.sleep(1)\n")
        return ("import json,os,signal,subprocess,sys,time\nfrom pathlib import Path\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                f"descendant = subprocess.Popen([sys.executable, '-B', '-c', {grandchild!r}])\n"
                f"while not Path({str(ready)!r}).exists(): time.sleep(0.005)\n"
                f"Path({str(marker)!r}).write_text(json.dumps([os.getpid(), descendant.pid]))\n"
                + ("raise SystemExit(0)\n" if parent_exits else "while True: time.sleep(1)\n"))

    def kill_tree(self, marker):
        if marker.exists():
            try:
                os.killpg(json.loads(marker.read_text())[0], signal.SIGKILL)
            except ProcessLookupError:
                pass

    def assert_tree_gone(self, marker):
        self.assertTrue(marker.exists())
        for pid in json.loads(marker.read_text()):
            def gone():
                try:
                    os.kill(pid, 0)
                    return False
                except ProcessLookupError:
                    return True
            self.wait_until(gone)

    def test_timeout_and_normal_parent_exit_clean_stubborn_descendants(self):
        for parent_exits in (False, True):
            marker = self.root / f"tree-{parent_exits}.json"
            self.addCleanup(self.kill_tree, marker)
            with self.subTest(parent_exits=parent_exits):
                result = boundary.capture([sys.executable, "-B", "-c", self.tree_code(marker, parent_exits)],
                                          0.7 if not parent_exits else 3, [])
                self.assertEqual(None if parent_exits else "cli_timeout", result.reason)
                self.assert_tree_gone(marker)

    def test_unexpected_capture_exception_still_cleans_child_group(self):
        marker = self.root / "exception-tree.json"
        self.addCleanup(self.kill_tree, marker)
        selector = boundary.selectors.DefaultSelector()
        def fail_select(timeout):
            self.wait_until(marker.exists)
            raise RuntimeError("synthetic private exception")
        with patch.object(boundary.selectors, "DefaultSelector", return_value=selector), patch.object(selector, "select", side_effect=fail_select):
            with self.assertRaises(RuntimeError):
                boundary.capture([sys.executable, "-B", "-c", self.tree_code(marker)], 3, [])
        self.assert_tree_gone(marker)

    def test_cleanup_failure_never_reports_a_successful_capture(self):
        original = boundary._cleanup
        def clean_but_report_failure(child):
            original(child)
            return False
        with patch.object(boundary, "_cleanup", side_effect=clean_but_report_failure):
            result = boundary.capture([sys.executable, "-B", "-c", "pass"], 3, [])
        self.assertEqual("cli_cleanup_failed", result.reason)

    @unittest.skipUnless(hasattr(os, "fork"), "fork 전용")
    def test_sigint_and_sigterm_clean_group_and_cannot_pass(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            marker = self.root / f"signal-{sig}.json"
            result_file = self.root / f"signal-result-{sig}.json"
            reaped = []
            harness = os.fork()
            if harness == 0:
                try:
                    with boundary._interrupts() as pending:
                        result = boundary.capture([sys.executable, "-B", "-c", self.tree_code(marker)], 10, pending)
                    result_file.write_text(json.dumps({"reason": result.reason, "exit_code": result.exit_code}))
                    os._exit(0)
                except BaseException:
                    os._exit(99)
            def cleanup(pid=harness, finished=reaped, path=marker):
                if not finished:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    try:
                        os.waitpid(pid, 0)
                    except ChildProcessError:
                        pass
                self.kill_tree(path)
            self.addCleanup(cleanup)
            with self.subTest(signal=sig):
                self.wait_until(marker.exists)
                os.kill(harness, sig)
                def finished():
                    pid, status = os.waitpid(harness, os.WNOHANG)
                    if pid:
                        reaped.append(status)
                    return bool(pid)
                self.wait_until(finished)
                self.assertEqual(0, os.waitstatus_to_exitcode(reaped[0]))
                result = json.loads(result_file.read_text())
                self.assertEqual("cli_interrupted", result["reason"])
                self.assertNotEqual(0, result["exit_code"])
                self.assert_tree_gone(marker)

    def test_pending_signal_overrides_a_successful_report(self):
        from contextlib import contextmanager
        @contextmanager
        def pending_interrupt():
            yield [signal.SIGINT]
        with patch.object(boundary, "_interrupts", pending_interrupt), patch.object(boundary, "_run", return_value={"passed": True, "reason": "verified"}):
            report = boundary.run("review")
        self.assertEqual({"passed": False, "reason": "cli_interrupted"}, report)

    def test_main_never_prints_unexpected_exception_text(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["validate_role_boundary.py", "review"]), patch.object(boundary, "run", side_effect=RuntimeError("QH_FAKE_SECRET")), redirect_stdout(output):
            self.assertEqual(1, boundary.main())
        self.assertEqual({"passed": False, "reason": "harness_error"}, json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
