#!/usr/bin/env python3
"""Q13 deterministic checks in newly created synthetic-only local containers.

Never accepts an existing project, database, SQL file or credential. Cleans up
only its UUID-named Compose project. It is not a product/operational DB tool.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / 'containers/compose.synthetic.yaml'
MIGRATION = ROOT / 'migrations/0001_synthetic_foundation.sql'


class CheckFailure(Exception):
    pass


def main() -> int:
    if len(sys.argv) != 1:
        print('foundation: arguments are not accepted', file=sys.stderr)
        return 2
    # Preserve installed Docker config/context; disallow remote endpoints below.
    env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'DOCKER_CONFIG') if key in os.environ}
    env['COMPOSE_DISABLE_ENV_FILE'] = '1'
    builder_state = tempfile.TemporaryDirectory(prefix='qh-buildx-')
    env['BUILDX_CONFIG'] = builder_state.name
    project = 'qh-foundation-' + uuid.uuid4().hex[:12]
    checks = []
    started = time.monotonic()
    compose = None
    report = {}
    exit_code = 1

    def run(args, *, data=None, timeout=60, expected=0, error_marker=None):
        try:
            result = subprocess.run(args, input=data, capture_output=True, env=env, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise CheckFailure('command_start_or_timeout') from None
        if result.returncode != expected:
            # Deliberately never copy raw command/SQL/daemon error text into evidence.
            raise CheckFailure('command_exit_mismatch')
        if error_marker is not None and error_marker not in result.stderr:
            raise CheckFailure('expected_failure_reason_mismatch')
        return result.stdout

    def sql(statement, database='qh_synthetic', expected=0, error_marker=None):
        return run(compose + ['exec', '-T', 'db', 'psql', '-X', '-q', '-A', '-t',
                              '-v', 'ON_ERROR_STOP=1', '-U', 'qh_synthetic', '-d', database],
                   data=statement.encode(), expected=expected, error_marker=error_marker).decode().strip()

    def migration_script(checksum):
        body = MIGRATION.read_text()
        return f"""BEGIN;
SELECT pg_advisory_xact_lock(5130001);
CREATE SCHEMA IF NOT EXISTS qh;
CREATE TABLE IF NOT EXISTS qh.schema_migrations (
 version integer PRIMARY KEY, checksum text NOT NULL,
 applied_at timestamptz NOT NULL DEFAULT now());
DO $guard$ BEGIN
 IF EXISTS (SELECT 1 FROM qh.schema_migrations WHERE version=1 AND checksum <> '{checksum}')
 THEN RAISE EXCEPTION 'migration_checksum_mismatch'; END IF;
END $guard$;
SELECT NOT EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version=1) AS apply_one \\gset
\\if :apply_one
{body}
INSERT INTO qh.schema_migrations(version,checksum) VALUES(1,'{checksum}');
\\endif
COMMIT;
"""

    try:
        context = run(['docker', 'context', 'show']).decode().strip()
        metadata = json.loads(run(['docker', 'context', 'inspect', context]))
        if not metadata[0]['Endpoints']['docker']['Host'].startswith('unix://'):
            raise CheckFailure('nonlocal_docker_context')
        compose = ['docker', '--context', context, 'compose', '--env-file', '/dev/null',
                   '-p', project, '-f', str(COMPOSE)]
        run(compose + ['config', '--quiet'])
        run(compose + ['build', 'app'], timeout=120)
        out = run(compose + ['run', '--rm', '--no-deps', 'app', 'python', '--version'])
        if out.strip() != b'Python 3.13.17':
            raise CheckFailure('runtime_version_mismatch')
        checks.append('pinned_python_runtime')
        test_program = "import unittest,json,sys; s=unittest.defaultTestLoader.discover('tests/product'); n=s.countTestCases(); r=unittest.TextTestRunner(verbosity=2).run(s); print(json.dumps({'discovered':n,'run':r.testsRun})); sys.exit(0 if n>=22 and r.testsRun==n and r.wasSuccessful() else 1)"
        test_counts = json.loads(run(compose + ['run', '--rm', '--no-deps', 'app', 'python', '-c', test_program]))
        checks.append('product_unit_tests')
        run(compose + ['run', '--rm', '--no-deps', 'app', 'python', '-m', 'quantharbor',
                       'validate-config', 'config/runtime.synthetic.toml'])
        checks.append('synthetic_config_startup')
        run(compose + ['up', '-d', '--no-build', '--pull', 'never', 'db'])
        ready = False
        for _ in range(30):
            try:
                run(compose + ['exec', '-T', 'db', 'pg_isready', '-U', 'qh_synthetic', '-d', 'qh_synthetic'], timeout=5)
                ready = True
                break
            except CheckFailure:
                time.sleep(0.2)
        if not ready:
            raise CheckFailure('synthetic_db_not_ready')
        if sql('SHOW server_version;').split()[0] != '18.6':
            raise CheckFailure('postgres_version_mismatch')
        checks.append('pinned_postgres_startup')
        checksum = hashlib.sha256(MIGRATION.read_bytes()).hexdigest()
        sql(migration_script(checksum))
        sql(migration_script(checksum))
        if sql('SELECT count(*) FROM qh.schema_migrations;') != '1':
            raise CheckFailure('migration_idempotency')
        checks.append('migration_apply_and_idempotency')
        sql(migration_script('0' * 64), expected=3, error_marker=b'migration_checksum_mismatch')
        if sql('SELECT checksum FROM qh.schema_migrations;') != checksum:
            raise CheckFailure('migration_tamper_effect')
        checks.append('migration_checksum_change_rejected')
        sql("INSERT INTO qh.synthetic_probe VALUES(1, 123.000000000000000001, 'synthetic');")
        expected_value = '1|123.000000000000000001|synthetic'
        query = "SELECT probe_id,exact_value,description FROM qh.synthetic_probe ORDER BY probe_id;"
        if sql(query) != expected_value:
            raise CheckFailure('stored_exact_value_mismatch')
        sql("BEGIN; INSERT INTO qh.synthetic_probe VALUES(2, 1, 'rolled-back'); SELECT 1/0; COMMIT;", expected=3, error_marker=b'division by zero')
        if sql('SELECT count(*) FROM qh.synthetic_probe;') != '1':
            raise CheckFailure('transaction_rollback')
        checks.append('failed_transaction_rollback')
        dump = run(compose + ['exec', '-T', 'db', 'pg_dump', '-U', 'qh_synthetic', '-d',
                             'qh_synthetic', '--no-owner', '--no-privileges'])
        sql('CREATE DATABASE qh_restore;')
        run(compose + ['exec', '-T', 'db', 'psql', '-X', '-q', '-v', 'ON_ERROR_STOP=1',
                       '-U', 'qh_synthetic', '-d', 'qh_restore'], data=dump)
        if sql(query) != expected_value or sql(query, 'qh_restore') != expected_value:
            raise CheckFailure('restore_value_mismatch')
        if sql('SELECT checksum FROM qh.schema_migrations;', 'qh_restore') != checksum:
            raise CheckFailure('restore_migration_mismatch')
        checks.append('synthetic_dump_restore_exact_values')
        report = {'scope': 'Q13_synthetic_foundation', 'result': 'pass',
                  'checks': checks, 'product_tests': test_counts, 'migration_sha256': checksum}
        exit_code = 0
    except (CheckFailure, ValueError, KeyError, IndexError) as exc:
        report = {'scope': 'Q13_synthetic_foundation', 'result': 'fail', 'passed_checks': checks,
                  'reason': str(exc) if isinstance(exc, CheckFailure) else 'invalid_metadata'}
    finally:
        if compose:
            try:
                run(compose + ['down', '--volumes', '--remove-orphans'], timeout=30)
                report['cleanup'] = 'own_project_removed'
            except CheckFailure:
                report['result'] = 'fail'
                report['cleanup'] = 'failed'
                exit_code = 1
        builder_state.cleanup()
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    print(json.dumps(report))
    return exit_code



if __name__ == '__main__':
    raise SystemExit(main())
