import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("qh_hook_audit",
    Path(__file__).resolve().parents[1] / "scripts/qh_hook_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class HookAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        mock = patch.object(audit.tempfile, "gettempdir", return_value=str(self.base))
        mock.start()
        self.addCleanup(mock.stop)

    def payload(self, event):
        return {"hook_event_name": event, "session_id": "synthetic-session",
                "turn_id": "synthetic-turn", "tool_use_id": "synthetic-call",
                "tool_name": "Bash", "tool_input": {"command": "SYNTHETIC_SECRET"},
                "tool_response": {"exit_code": 1, "stderr": "SYNTHETIC_SECRET"}}

    def test_lifecycle_records_only_fixed_metadata_and_correlates_calls(self):
        for event in sorted(audit.EVENTS):
            output, status = audit.process(json.dumps(self.payload(event)).encode(), event)
            self.assertEqual(0, status)
            self.assertNotIn("SYNTHETIC_SECRET", json.dumps(output))
        records = [json.loads(p.read_text()) for p in self.base.rglob("*.json")]
        self.assertEqual(len(audit.EVENTS), len(records))
        serialized = json.dumps(records)
        for raw in ("SYNTHETIC_SECRET", "synthetic-session", "synthetic-turn", "synthetic-call"):
            self.assertNotIn(raw, serialized)
        calls = [r["call_hash"] for r in records if "call_hash" in r]
        self.assertEqual(calls[0], calls[1])
        for p in self.base.rglob("*.json"):
            self.assertEqual(0o600, p.stat().st_mode & 0o777)
        self.assertEqual("failed", next(r["outcome"] for r in records if "outcome" in r))

    def test_unknown_response_never_becomes_success(self):
        for response, expected in [
            ({}, "unknown"), ("exit_code: 0", "unknown"),
            ({"exit_code": True}, "unknown"), ({"exit_code": 0}, "success"),
            ({"exit_code": 0, "isError": True}, "failed")]:
            payload = self.payload("PostToolUse")
            payload["tool_response"] = response
            self.assertEqual(expected, audit.metadata(payload, "PostToolUse")["outcome"])

    def test_invalid_payload_and_oversize_pretool_deny_without_raw_output(self):
        for raw in (b"invalid SYNTHETIC_SECRET", b"{" * (audit.LIMIT + 1),
                    json.dumps(self.payload("Stop")).encode()):
            output, status = audit.process(raw, "PreToolUse")
            self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
            self.assertEqual(0, status)
            self.assertNotIn("SYNTHETIC_SECRET", json.dumps(output))
        self.assertFalse(list(self.base.rglob("*.json")))

    def test_storage_failure_cannot_allow_pretool_or_claim_other_success(self):
        for event in audit.EVENTS:
            with patch.object(audit, "persist", side_effect=OSError("SYNTHETIC_SECRET")):
                output, status = audit.process(json.dumps(self.payload(event)).encode(), event)
            self.assertNotIn("SYNTHETIC_SECRET", json.dumps(output))
            if event == "PreToolUse":
                self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
            else:
                self.assertEqual(1, status)

    def test_symlink_audit_parent_and_insecure_directory_are_refused(self):
        user = self.base / ("quantharbor-hook-audit-" + str(os.getuid()))
        outside = self.base / "outside"
        outside.mkdir()
        user.symlink_to(outside, target_is_directory=True)
        output, _ = audit.process(json.dumps(self.payload("PreToolUse")).encode(), "PreToolUse")
        self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
        self.assertFalse(list(outside.iterdir()))
        user.unlink()
        user.mkdir(mode=0o755)
        output, _ = audit.process(json.dumps(self.payload("PreToolUse")).encode(), "PreToolUse")
        self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])

    def test_pinned_launcher_accepts_exact_source_and_rejects_changed_source(self):
        definition = json.loads((Path(__file__).resolve().parents[1] / ".codex/hooks.json").read_text())
        command = definition["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        tokens = shlex.split(command)
        self.assertEqual(["/usr/bin/python3", "-I", "-S", "-c"], tokens[:4])
        source = self.base / "project/scripts/script.py"
        source.parent.mkdir(parents=True)
        source.write_bytes(Path(audit.__file__).read_bytes())
        argv = tokens[:5] + [str(source), "PreToolUse"]
        # Neither CWD nor PYTHONPATH may shadow modules before source validation.
        for name in ("hashlib", "pathlib", "sitecustomize"):
            (self.base / (name + ".py")).write_text('raise RuntimeError("SYNTHETIC_SECRET")\n')
        environment = dict(os.environ, TMPDIR=str(self.base), PYTHONPATH=str(self.base))
        payload = json.dumps(self.payload("PreToolUse")).encode()
        valid = subprocess.run(argv, input=payload, capture_output=True, env=environment,
                               cwd=self.base, timeout=3)
        self.assertEqual(0, valid.returncode)
        self.assertEqual({}, json.loads(valid.stdout))
        source.write_bytes(source.read_bytes() + b"\n# changed fixture\n")
        rejected = subprocess.run(argv, input=payload, capture_output=True, env=environment, timeout=3)
        self.assertEqual(2, rejected.returncode)
        self.assertEqual(b"", rejected.stdout)
        self.assertNotIn(b"SYNTHETIC_SECRET", rejected.stderr)

    def test_temp_directory_inside_workspace_is_rejected(self):
        with patch.object(audit, "ROOT", self.base):
            output, _ = audit.process(json.dumps(self.payload("PreToolUse")).encode(), "PreToolUse")
        self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
        self.assertFalse(list(self.base.rglob("*.json")))

    def test_nonsticky_writable_ancestor_is_rejected(self):
        self.base.chmod(0o777)
        try:
            output, _ = audit.process(json.dumps(self.payload("PreToolUse")).encode(), "PreToolUse")
            self.assertEqual("deny", output["hookSpecificOutput"]["permissionDecision"])
        finally:
            self.base.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
