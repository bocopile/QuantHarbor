"""임시 합성 입력·자식 프로세스만 사용한다. 실제 profile 검사는 실행하지 않는다."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid


SPEC = importlib.util.spec_from_file_location(
    "qh_run_local_check", Path(__file__).resolve().parents[1] / "scripts/run_local_check.py")
local = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = local
SPEC.loader.exec_module(local)
TEAM_INPUTS = local.CHECKS["team-config"].inputs


@unittest.skipUnless(os.name == "posix" and hasattr(os, "fork"), "POSIX 전용")
class LocalCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="qh-local-audit-test-")
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.root = self.home / "synthetic-repository"
        self.base = self.home / "audit-base"
        self.root.mkdir(mode=0o700)
        self.base.mkdir(mode=0o700)
        (self.root / "synthetic.py").write_text("# synthetic public input\n", encoding="utf-8")
        self.namespace = f"quantharbor-local-checks-{os.getuid()}"
        self.directory = self.base / self.namespace / "synthetic-root-hash"
        self.checks = {}
        for name, value in (("ROOT", self.root), ("CHECKS", self.checks)):
            manager = patch.object(local, name, value)
            manager.start()
            self.addCleanup(manager.stop)
        manager = patch.object(local, "_audit_location", return_value=(self.base, self.namespace, "synthetic-root-hash"))
        manager.start()
        self.addCleanup(manager.stop)
        self.set_code("pass")

    def set_code(self, code, timeout=3):
        self.checks["team-config"] = local.Check(
            (local.PYTHON, "-B", "-c", code), timeout, (("wrapper", "synthetic.py"),))

    def audit_path(self, result):
        return self.directory / f"{result.run_id}.jsonl"

    def records(self, result):
        return [json.loads(line) for line in self.audit_path(result).read_bytes().splitlines()]

    def wait_until(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("synthetic process deadline exceeded")
            time.sleep(0.01)

    def test_start_file_and_directory_fsync_finish_before_spawn(self):
        events = []
        original_sync, original_spawn = local.os.fsync, local.subprocess.Popen

        def synced(fd):
            original_sync(fd)
            events.append("file" if stat.S_ISREG(os.fstat(fd).st_mode) else "directory")

        def spawn(*args, **kwargs):
            self.assertEqual(["file", "directory"], events[-2:])
            files = list(self.directory.glob("*.jsonl"))
            self.assertEqual(1, len(files))
            self.assertEqual("start", json.loads(files[0].read_bytes())["event"])
            self.assertEqual(0o600, stat.S_IMODE(files[0].stat().st_mode))
            self.assertEqual(0o700, stat.S_IMODE(self.directory.stat().st_mode))
            self.assertIs(kwargs["shell"], False)
            self.assertTrue(kwargs["start_new_session"])
            self.assertEqual(self.root, kwargs["cwd"])
            for stream in ("stdin", "stdout", "stderr"):
                self.assertEqual(local.subprocess.DEVNULL, kwargs[stream])
            self.assertTrue(Path(args[0][0]).is_absolute())
            return original_spawn(*args, **kwargs)

        with patch.object(local.os, "fsync", side_effect=synced), patch.object(local.subprocess, "Popen", side_effect=spawn):
            result = local.run_check("team-config")
        self.assertEqual("success", result.status)
        self.assertEqual(0, result.exit_code)
        self.assertEqual(result, local.inspect_run(result.run_id))

    def test_start_fsync_failure_prevents_spawn(self):
        original_sync = local.os.fsync

        def fail_file_sync(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("synthetic secret must not escape")
            original_sync(fd)

        with patch.object(local.os, "fsync", side_effect=fail_file_sync), patch.object(local.subprocess, "Popen") as spawn:
            result = local.run_check("team-config")
        spawn.assert_not_called()
        self.assertEqual("audit_start_failed", result.reason)
        self.assertNotEqual(0, result.exit_code)

    def test_document_changes_update_the_recorded_input_hashes(self):
        inputs = dict(TEAM_INPUTS)
        self.assertEqual("docs/execution-checklist.md", inputs["execution_checklist"])
        self.assertEqual("docs/approval-register.md", inputs["approval_register"])
        for relative in inputs.values():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic public input\n", encoding="utf-8")
        synthetic = self.checks["team-config"]
        self.checks["team-config"] = local.Check(synthetic.argv, synthetic.timeout, TEAM_INPUTS)
        result = local.run_check("team-config")
        self.assertEqual("success", result.status)
        previous = self.records(result)[0]["input_sha256"]
        for label in ("execution_checklist", "approval_register"):
            with self.subTest(document=label):
                (self.root / inputs[label]).write_text("synthetic document changed\n", encoding="utf-8")
                result = local.run_check("team-config")
                self.assertEqual("success", result.status)
                current = self.records(result)[0]["input_sha256"]
                self.assertNotEqual(previous[label], current[label])
                self.assertEqual({key: value for key, value in previous.items() if key != label},
                                 {key: value for key, value in current.items() if key != label})
                previous = current

    def test_nonzero_exit_and_spawn_failure_have_terminal(self):
        self.set_code("raise SystemExit(7)")
        result = local.run_check("team-config")
        self.assertEqual(("failed", "exit_nonzero"), (result.status, result.reason))
        self.assertEqual(7, self.records(result)[1]["exit_code"])
        self.assertEqual(result, local.inspect_run(result.run_id))
        with patch.object(local.subprocess, "Popen", side_effect=OSError("synthetic-private-error")):
            result = local.run_check("team-config")
        self.assertEqual(("startup_error", "spawn_failed"), (result.status, result.reason))
        self.assertIsNone(self.records(result)[1]["exit_code"])
        self.assertEqual(result, local.inspect_run(result.run_id))

    def test_large_stdout_stderr_and_fake_environment_secret_are_discarded(self):
        secret = "QH_SYNTHETIC_FAKE_SECRET_286771"
        self.set_code("import os\nchunk = os.environ['QH_SYNTHETIC_SECRET'].encode() * 2048\n"
                      "for _ in range(128):\n os.write(1, chunk)\n os.write(2, chunk)\n", timeout=5)
        output = io.StringIO()
        with patch.dict(os.environ, {"QH_SYNTHETIC_SECRET": secret}), redirect_stdout(output), redirect_stderr(output):
            code = local.main(["run", "team-config"])
        self.assertEqual(0, code)
        audit = next(self.directory.glob("*.jsonl")).read_text(encoding="ascii")
        for forbidden in (secret, "QH_SYNTHETIC_SECRET", str(self.root), "os.write", "argv", "stderr"):
            self.assertNotIn(forbidden, audit + output.getvalue())

    def test_unknown_id_extra_arguments_and_path_ids_never_spawn(self):
        invalid = (["run", "unknown"], ["run", "team-config", "--root", "/tmp"],
                   ["run", "../team-config"], ["inspect", "../../outside"],
                   ["inspect", str(uuid.uuid4()), "--output", "elsewhere"], ["run"], ["--help"])
        with patch.object(local.subprocess, "Popen") as spawn:
            for args in invalid:
                output = io.StringIO()
                with self.subTest(args=args), redirect_stdout(output):
                    self.assertEqual(2, local.main(args))
                    self.assertEqual("invalid_request\n", output.getvalue())
        spawn.assert_not_called()
        self.assertFalse(self.directory.exists())

    def test_unsafe_existing_directory_is_rejected(self):
        with local._open_audit_directory(create=True):
            pass
        self.directory.chmod(0o755)
        with patch.object(local.subprocess, "Popen") as spawn:
            result = local.run_check("team-config")
        spawn.assert_not_called()
        self.assertEqual("audit_start_failed", result.reason)
        self.directory.chmod(0o700)

    def test_symlink_directory_does_not_change_external_files(self):
        outside = self.home / "synthetic-outside"
        outside.mkdir(mode=0o700)
        sentinel = outside / "sentinel"
        sentinel.write_bytes(b"unchanged")
        (self.base / self.namespace).symlink_to(outside, target_is_directory=True)
        with patch.object(local.subprocess, "Popen") as spawn:
            result = local.run_check("team-config")
        spawn.assert_not_called()
        self.assertEqual("audit_start_failed", result.reason)
        self.assertEqual([sentinel], list(outside.iterdir()))
        self.assertEqual(b"unchanged", sentinel.read_bytes())

    def test_file_collision_and_symlink_are_not_overwritten(self):
        with local._open_audit_directory(create=True):
            pass
        identifier = uuid.uuid4()
        collision = self.directory / f"{identifier}.jsonl"
        outside = self.home / "synthetic-sentinel"
        outside.write_bytes(b"unchanged")
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                if symlink:
                    collision.symlink_to(outside)
                else:
                    collision.write_bytes(b"unchanged")
                    collision.chmod(0o600)
                with patch.object(local.uuid, "uuid4", return_value=identifier), patch.object(local.subprocess, "Popen") as spawn:
                    result = local.run_check("team-config")
                spawn.assert_not_called()
                self.assertEqual("audit_start_failed", result.reason)
                self.assertEqual(b"unchanged", collision.read_bytes())
                self.assertEqual(b"unchanged", outside.read_bytes())
                collision.unlink()

    def test_terminal_write_or_fsync_failure_is_not_success(self):
        append = local._append

        def fail_terminal(stream, directory, record):
            append(stream, directory, record)
            if record["event"] == "terminal":
                raise OSError("synthetic terminal persistence failure")

        with patch.object(local, "_append", side_effect=fail_terminal):
            result = local.run_check("team-config")
        self.assertEqual("audit_terminal_failed", result.reason)
        self.assertNotEqual(0, result.exit_code)
        self.assertEqual("incomplete", local.inspect_run(result.run_id).status)

    def test_truncated_or_inconsistent_audit_is_not_success(self):
        result = local.run_check("team-config")
        original = self.audit_path(result).read_bytes()
        self.audit_path(result).write_bytes(original.splitlines(keepends=True)[0] + b'{"event":"term')
        inspected = local.inspect_run(result.run_id)
        self.assertEqual("incomplete", inspected.status)
        self.assertNotEqual(0, inspected.exit_code)
        records = [json.loads(line) for line in original.splitlines()]
        records[1]["exit_code"] = 7
        self.audit_path(result).write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="ascii")
        self.assertEqual("invalid", local.inspect_run(result.run_id).status)

    def test_inspect_refuses_symlink_nonregular_and_oversized_files(self):
        with local._open_audit_directory(create=True):
            pass
        identifier = str(uuid.uuid4())
        path = self.directory / f"{identifier}.jsonl"
        outside = self.home / "synthetic-sentinel"
        outside.write_bytes(b"unchanged")
        path.symlink_to(outside)
        self.assertEqual("invalid", local.inspect_run(identifier).status)
        path.unlink()
        os.mkfifo(path, 0o600)
        self.assertEqual("invalid", local.inspect_run(identifier).status)
        path.unlink()
        path.write_bytes(b"x" * (local.MAX_AUDIT_BYTES + 1))
        path.chmod(0o600)
        self.assertEqual("invalid", local.inspect_run(identifier).status)
        self.assertEqual(b"unchanged", outside.read_bytes())

    def tree_code(self, marker, parent_exits=False):
        ready = marker.with_suffix(".ready")
        grandchild = ("import signal,time\nfrom pathlib import Path\n"
                      "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                      f"Path({str(ready)!r}).write_text('synthetic-ready')\n"
                      "while True: time.sleep(1)\n")
        return ("import json,os,signal,subprocess,sys,time\nfrom pathlib import Path\n"
                "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                f"grandchild = subprocess.Popen([sys.executable, '-B', '-c', {grandchild!r}])\n"
                f"while not Path({str(ready)!r}).exists(): time.sleep(0.005)\n"
                f"Path({str(marker)!r}).write_text(json.dumps([os.getpid(), grandchild.pid]))\n"
                + ("raise SystemExit(0)\n" if parent_exits else "while True: time.sleep(1)\n"))

    def kill_synthetic_tree(self, marker):
        if marker.exists():
            pids = json.loads(marker.read_text())
            try:
                os.killpg(pids[0], signal.SIGKILL)
            except ProcessLookupError:
                pass

    def assert_tree_gone(self, marker):
        self.assertTrue(marker.exists())
        pids = json.loads(marker.read_text())

        def gone(pid):
            try:
                os.kill(pid, 0)
                return False
            except ProcessLookupError:
                return True

        for pid in pids:
            self.wait_until(lambda: gone(pid))

    def test_timeout_kills_stubborn_child_and_grandchild(self):
        marker = self.home / "timeout-pids.json"
        self.addCleanup(self.kill_synthetic_tree, marker)
        self.set_code(self.tree_code(marker), timeout=0.8)
        result = local.run_check("team-config")
        self.assertEqual("timeout", result.status)
        self.assertEqual("deadline_exceeded", result.reason)
        self.assertEqual(result, local.inspect_run(result.run_id))
        self.assert_tree_gone(marker)

    def test_normal_exit_still_cleans_remaining_process_group(self):
        marker = self.home / "normal-pids.json"
        self.addCleanup(self.kill_synthetic_tree, marker)
        self.set_code(self.tree_code(marker, parent_exits=True))
        result = local.run_check("team-config")
        self.assertEqual("success", result.status)
        self.assert_tree_gone(marker)

    def start_harness(self, marker):
        self.set_code(self.tree_code(marker), timeout=10)
        harness = os.fork()
        if harness == 0:
            try:
                result = local.run_check("team-config")
                os._exit(result.exit_code)
            except BaseException:
                os._exit(99)
        reaped = []

        def cleanup():
            if not reaped:
                try:
                    os.kill(harness, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(harness, 0)
                except ChildProcessError:
                    pass
            self.kill_synthetic_tree(marker)

        self.addCleanup(cleanup)
        self.wait_until(marker.exists)
        return harness, reaped

    def reap_harness(self, harness, reaped):
        def finished():
            pid, status = os.waitpid(harness, os.WNOHANG)
            if pid:
                reaped.append(status)
                return True
            return False

        self.wait_until(finished)
        return reaped[0]

    def test_sigint_and_sigterm_persist_interruption_and_clean_process_group(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            with self.subTest(signal=sig):
                marker = self.home / f"signal-{sig}-pids.json"
                existing = set(self.directory.glob("*.jsonl")) if self.directory.exists() else set()
                harness, reaped = self.start_harness(marker)
                os.kill(harness, sig)
                status = self.reap_harness(harness, reaped)
                self.assertEqual(1, os.waitstatus_to_exitcode(status))
                new_file = (set(self.directory.glob("*.jsonl")) - existing).pop()
                inspected = local.inspect_run(new_file.stem)
                self.assertEqual(("interrupted", "signal_received"), (inspected.status, inspected.reason))
                self.assert_tree_gone(marker)

    def test_sigkill_retains_start_and_inspect_reports_incomplete(self):
        marker = self.home / "killed-pids.json"
        harness, reaped = self.start_harness(marker)
        files = list(self.directory.glob("*.jsonl"))
        self.assertEqual(1, len(files))
        self.assertEqual("start", json.loads(files[0].read_bytes())["event"])
        os.kill(harness, signal.SIGKILL)
        self.assertEqual(-signal.SIGKILL, os.waitstatus_to_exitcode(self.reap_harness(harness, reaped)))
        inspected = local.inspect_run(files[0].stem)
        self.assertEqual(("incomplete", "terminal_missing"), (inspected.status, inspected.reason))
        self.assertNotEqual(0, inspected.exit_code)
        # 운영 실행기는 자동 복구하지 않는다. 이 harness가 자기 합성 group을 정리한다.
        self.kill_synthetic_tree(marker)
        self.assert_tree_gone(marker)


if __name__ == "__main__":
    unittest.main()
