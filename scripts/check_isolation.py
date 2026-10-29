#!/usr/bin/env python3
"""Q14 실제 Docker 합성 검증. 원시 stdout/stderr/예외는 출력하지 않는다."""

import io
import json
from pathlib import Path
import sys
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main():
    if len(sys.argv) != 1:
        print(json.dumps({"scope": "Q14_synthetic_isolation", "result": "fail", "reason": "arguments_denied"}))
        return 2
    started = time.monotonic()
    try:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests/isolation"), pattern="test_*.py")
        discovered = suite.countTestCases()
        if discovered < 13:
            raise ValueError()
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
        passed = result.wasSuccessful() and result.testsRun == discovered and not result.skipped
        report = {"scope": "Q14_synthetic_isolation", "result": "pass" if passed else "fail",
                  "discovered": discovered, "run": result.testsRun, "skipped": len(result.skipped),
                  "failed_tests": [case.id() for case, _ in result.failures + result.errors],
                  "elapsed_seconds": round(time.monotonic() - started, 3),
                  "limits_scope": "CPU2s_per_process;CPU_quota1;wall5s;memory128MiB;tmpfs16MiB;pids16",
                  "created_policy": "network_none;readonly;nonprivileged;logging_none;image_plus_explicit_env_exact",
                  "stale_scope": "endpoint_daemon_fingerprint_fail_closed",
                  "scope_excludes": "host_admin_daemon_compromise;actual_financial_authentication_or_orders"}
        print(json.dumps(report))
        return 0 if passed else 1
    except Exception:
        print(json.dumps({"scope": "Q14_synthetic_isolation", "result": "fail", "reason": "check_setup_failure"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
