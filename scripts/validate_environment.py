"""Validate Codex command profiles using only freshly created synthetic fixtures.

Run from the repository root: python3 scripts/validate_environment.py
Requires a host that permits starting Codex's macOS sandbox.
Prints sanitized JSON; never prints subprocess stderr or private file contents.
Does not activate profiles for other sessions, invoke models, or trust hooks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid


ROOT = Path(__file__).resolve().parents[1]

# The child emits only fixed statuses, never file contents or exception messages.
PROBE = """
import errno, json, pathlib, socket, sys
operation, target = sys.argv[1:3]
try:
    if operation == "read":
        pathlib.Path(target).read_bytes()
    elif operation == "write":
        with open(target, "x") as stream:
            stream.write("SYNTHETIC ENV VALIDATION ONLY\\n")
    elif operation == "network":
        with socket.create_connection(("127.0.0.1", int(target)), timeout=2):
            pass
    else:
        raise ValueError("unknown operation")
    result = {"outcome": "allowed"}
except OSError as exc:
    result = {"outcome": "denied" if exc.errno in (errno.EPERM, errno.EACCES) else "error",
              "errno": exc.errno}
print(json.dumps(result))
"""


def validation_limits(policy: dict) -> tuple[int, int]:
    limits = policy["validation"]
    timeout = limits["probe_timeout_seconds"]
    batch = limits["probe_batch_timeout_seconds"]
    retries = limits["automatic_retries"]
    if (type(timeout) is not int or not 1 <= timeout <= 60
            or type(batch) is not int or not timeout <= batch <= 300
            or type(retries) is not int or retries != 0):
        raise ValueError("Invalid local validation limits")
    return timeout, batch


def probe(profile: str, operation: str, target: str, timeout: float = 15) -> dict:
    if timeout <= 0:
        return {"outcome": "not_run", "reason": "batch_budget_exhausted"}
    try:
        result = subprocess.run(
            ["codex", "sandbox", "-C", str(ROOT), "-P", profile, "--",
             sys.executable, "-c", PROBE, operation, target],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
            cwd=ROOT,
        )
    except subprocess.TimeoutExpired:
        return {"outcome": "execution_error", "reason": "timeout"}
    except OSError:
        return {"outcome": "startup_error", "reason": "process_unavailable"}
    if result.returncode != 0:
        return {"outcome": "startup_error", "exit_code": result.returncode}
    try:
        value = json.loads(result.stdout)
        if (isinstance(value, dict) and isinstance(value.get("outcome"), str)
                and value["outcome"] in {"allowed", "denied", "error"}):
            if "errno" in value and type(value["errno"]) is not int:
                return {"outcome": "execution_error", "reason": "invalid_probe_output"}
            return {key: value[key] for key in ("outcome", "errno") if key in value}
    except (ValueError, AttributeError):
        pass
    return {"outcome": "startup_error", "reason": "invalid_probe_output"}


def main() -> int:
    config_path = ROOT / ".codex/config.toml"
    config_bytes = config_path.read_bytes()
    config = tomllib.loads(config_bytes.decode())
    policy_bytes = (ROOT / "config/ai/development-policy.toml").read_bytes()
    timeout, batch_timeout = validation_limits(tomllib.loads(policy_bytes.decode()))
    run_id = uuid.uuid4().hex
    for profile in ("qh_review", "qh_development"):
        if config["permissions"][profile]["filesystem"][":workspace_roots"]["logs"] != "deny":
            raise RuntimeError("Expected logs deny fixture rule is missing")

    # Refuse existing symlinks. Never inspect pre-existing log files.
    logs = ROOT / "logs"
    if logs.is_symlink() or (logs.exists() and not logs.is_dir()):
        raise RuntimeError("Synthetic fixture parent is not a regular directory")
    created_logs = not logs.exists()
    if created_logs:
        logs.mkdir()
    fixture = logs / ("qh-synthetic-" + uuid.uuid4().hex)
    protected_targets: list[Path] = []
    results: list[dict] = []
    try:
        with fixture.open("x") as stream:
            stream.write("SYNTHETIC ENV VALIDATION ONLY\n")
        with tempfile.TemporaryDirectory(prefix=".qh-validation-", dir=ROOT) as work:
            public = Path(work) / "public.txt"
            public.write_text("SYNTHETIC ENV VALIDATION ONLY\n")
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(8)
                port = str(listener.getsockname()[1])
                # Positive control: endpoint is reachable before sandbox probes.
                with socket.create_connection(("127.0.0.1", int(port)), timeout=2):
                    pass
                deadline = time.monotonic() + batch_timeout
                for profile in ("qh_review", "qh_development"):
                    protected = ROOT / ".codex" / ("qh-probe-" + uuid.uuid4().hex)
                    protected_targets.append(protected)
                    cases = [
                        ("public_read", "read", str(public), "allowed"),
                        ("workspace_write", "write", str(Path(work) / profile),
                         "allowed" if profile == "qh_development" else "denied"),
                        ("private_read", "read", str(fixture), "denied"),
                        ("protected_config_write", "write", str(protected), "denied"),
                        ("loopback_connect", "network", port, "denied"),
                    ]
                    for name, operation, target, expected in cases:
                        started = time.monotonic()
                        observed = probe(
                            profile, operation, target,
                            timeout=min(timeout, deadline - started),
                        )
                        results.append({
                            "profile": profile, "case": name, "expected": expected,
                            "attempt": 0 if observed["outcome"] == "not_run" else 1,
                            "duration_ms": round((time.monotonic() - started) * 1000),
                            **observed, "passed": observed["outcome"] == expected,
                        })
    finally:
        fixture.unlink(missing_ok=True)
        for target in protected_targets:
            target.unlink(missing_ok=True)
        if created_logs:
            logs.rmdir()
    report = {
        "schema_version": 2,
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "synthetic_command_profile_behavior",
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
        "validator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "enforced_limits": {
            "probe_timeout_seconds": timeout,
            "probe_batch_timeout_seconds": batch_timeout,
            "automatic_retries": 0,
        },
        "audit_scope": "completed_report_of_synthetic_profile_probes_only",
        "network_positive_control": "loopback_reachable",
        "results": results,
        "passed": all(result["passed"] for result in results),
        "limitations": [
            "Not a test of MCP, connectors, models, or the active app session.",
            "No actual credentials read; only the configured logs rule was probed.",
            "No hook trust, subagent, independent review, or broker validation.",
            "Audit is emitted at completion; it is not a crash-durable global tool log.",
        ],
    }
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
