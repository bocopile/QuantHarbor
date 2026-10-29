"""Docker를 실행하지 않는 합성 runner 경계 검사."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests/product'))
from quantharbor.adapters.postgres_ledger import PostgresLedger, LedgerStorageError, _append_sql, _text
from quantharbor.domain.primitives import ContractError
from synthetic_ledger import T0, submission

spec = importlib.util.spec_from_file_location('qh_check_ledger', ROOT / 'scripts/check_ledger.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class LedgerRunnerTests(unittest.TestCase):
    def test_constructor_has_no_process_or_environment_secret_copy(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic-secret', 'PGPASSWORD': 'synthetic-secret',
                                    'DOCKER_HOST': 'tcp://remote:2375'}), patch('subprocess.run') as run:
            db = PostgresLedger()
        run.assert_not_called()
        self.assertNotIn('PGPASSWORD', db._env)
        self.assertNotIn('ANTHROPIC_API_KEY', db._env)
        self.assertNotIn('DOCKER_HOST', db._env)
        self.assertTrue(db._project.startswith('qh-ledger-'))
        self.assertNotEqual(db._project, PostgresLedger()._project)

    def test_constructor_rejects_existing_database_and_sql_arguments(self):
        for kwargs in ({'database': 'existing'}, {'dsn': 'secret'}, {'sql': 'SELECT 1'}, {'project': 'existing'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(TypeError):
                PostgresLedger(**kwargs)

    def test_remote_context_rejected_before_compose(self):
        db = PostgresLedger()
        responses = [b'remote', json.dumps([{'Endpoints': {'docker': {'Host': 'tcp://remote:2375'}}}]).encode()]
        with patch.object(db, '_run', side_effect=responses) as run, self.assertRaises(LedgerStorageError) as caught:
            db.__enter__()
        self.assertEqual(caught.exception.reason, 'nonlocal_docker_context')
        self.assertEqual(run.call_count, 2)
        self.assertIsNone(db._compose)

    def test_init_server_cannot_be_mistaken_for_final_server(self):
        db = PostgresLedger()
        processes = iter((b'docker-entrypoi\n', b'postgres\n'))
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if args == ['docker', 'context', 'show']:
                return b'local'
            if args[:3] == ['docker', 'context', 'inspect']:
                return json.dumps([{'Endpoints': {'docker': {'Host': 'unix:///synthetic.sock'}}}]).encode()
            if args[-2:] == ['cat', '/proc/1/comm']:
                return next(processes)
            return b''
        with patch.object(db, '_run', side_effect=run), patch.object(db, '_query', return_value='18.6'), patch('time.sleep') as sleep:
            with db:
                self.assertTrue(db._ready)
        sleep.assert_called_once_with(0.2)
        self.assertEqual(sum('pg_isready' in args for args in calls), 1)
        self.assertEqual(db.cleanup, 'own_project_removed')

    def test_sql_data_uses_hex_not_quoted_interpolation(self):
        hostile = "'); SELECT pg_sleep(100); --\n$unsafe`echo ignored`"
        sql = _text(hostile)
        self.assertNotIn('pg_sleep', sql)
        self.assertNotIn('$unsafe', sql)
        self.assertIn(hostile.encode().hex(), sql)
        normal = _append_sql(submission(), T0)
        self.assertEqual(normal.count('SELECT'), 1)
        self.assertIn('qh.ledger_append', normal)
        self.assertNotIn('synthetic-account:', normal)

    def test_psql_database_allowlist_and_no_host_credentials(self):
        db = PostgresLedger()
        db._compose = ['docker', '--context', 'local', 'compose', '-p', db._project]
        with self.assertRaises(LedgerStorageError):
            db._psql('existing-db')
        args = db._psql()
        self.assertIn('-X', args)
        self.assertIn('ON_ERROR_STOP=1', args)
        self.assertNotIn('-h', args)
        self.assertNotIn('--password', args)
        self.assertIn('qh_synthetic', args)

    def test_append_one_session_transaction_and_unstarted_rejected(self):
        db = PostgresLedger()
        with self.assertRaises(LedgerStorageError):
            db.append(submission(), recorded_at=T0)
        db._ready = True
        result = dict(status='accepted', reason=None, cursor=1, event_ids=['ledger:synthetic:1'],
                      submission_hash='0'*64, projection_id='projection:synthetic')
        with patch.object(db, '_query', return_value=json.dumps(result)) as query:
            self.assertEqual(db.append(submission(), recorded_at=T0).status, 'accepted')
        query.assert_called_once()
        sql = query.call_args.args[0]
        self.assertTrue(sql.startswith('BEGIN;'))
        self.assertTrue(sql.endswith('COMMIT;'))
        self.assertIn('qh.ledger_append', sql)

    def test_raw_daemon_and_sql_errors_never_escape(self):
        db = PostgresLedger()
        result = subprocess.CompletedProcess([], 1, stdout=b'synthetic-private-output', stderr=b'synthetic-secret-error')
        with patch('subprocess.run', return_value=result), self.assertRaises(LedgerStorageError) as caught:
            db._run(['docker'])
        self.assertEqual(str(caught.exception), 'command_exit_mismatch')
        self.assertNotIn('synthetic-secret', str(caught.exception))

    def test_expected_failure_requires_specific_reason(self):
        db = PostgresLedger()
        result = subprocess.CompletedProcess([], 3, stdout=b'', stderr=b'unrelated SQL error')
        with patch('subprocess.run', return_value=result), self.assertRaises(LedgerStorageError) as caught:
            db._run(['docker'], expected=3, error_marker=b'ledger_contract')
        self.assertEqual(caught.exception.reason, 'expected_failure_reason_mismatch')

    def test_cleanup_only_own_project_and_failure_recorded(self):
        db = PostgresLedger()
        db._compose = ['docker', 'compose', '-p', db._project]
        with patch.object(db, '_run', return_value=b'') as run:
            db.close()
        self.assertEqual(run.call_args.args[0], ['docker', 'compose', '-p', db._project, 'down', '--volumes', '--remove-orphans'])
        self.assertEqual(db.cleanup, 'own_project_removed')
        db._compose = ['docker', 'compose', '-p', db._project]
        with patch.object(db, '_run', side_effect=LedgerStorageError()), self.assertRaises(LedgerStorageError):
            db.close()
        self.assertEqual(db.cleanup, 'failed')

    def test_cli_rejects_arguments_before_constructing_db(self):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['check_ledger.py', 'existing-db']), patch.object(runner, 'PostgresLedger') as db, contextlib.redirect_stdout(output):
            self.assertEqual(runner.main(), 2)
        db.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['reason'], 'arguments_not_accepted')

    def test_migration_guard_tracks_prerequisite_and_checksum(self):
        db = PostgresLedger()
        db.migration_checksums[1] = '1'*64
        script = db._migration_script(2)
        self.assertIn('migration_checksum_mismatch', script)
        self.assertIn('migration_order', script)
        self.assertIn("version=1 AND checksum='"+'1'*64+"'", script)
        with self.assertRaises(ContractError):
            db._migration_script(2, "'; invalid")


if __name__ == '__main__':
    unittest.main()
