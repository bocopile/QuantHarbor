"""제품 unit suite의 runner 경계. Docker/실제 DB를 실행하지 않는다."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from quantharbor.adapters.postgres_ledger import PostgresLedger
from quantharbor.adapters.execution_uow import ExecutionUnitOfWork,MAX_FRAME
from quantharbor.adapters.postgres_execution import PostgresExecutionRepository,_pack,_unpack
from quantharbor.application.approval import ApprovalApplication
from quantharbor.domain import approval as a
from quantharbor.domain import execution as d
from synthetic_execution import composition

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('qh_check_execution',ROOT/'scripts/check_execution.py')
runner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ExecutionRunnerBoundaryTests(unittest.TestCase):
    def test_EX36_no_memory_approval_or_arbitrary_adapter_composition(self):
        with self.assertRaises(a.ApprovalDenied):
            PostgresExecutionRepository(object(),object(),object(),object(),object(),object())
        with self.assertRaises(a.ApprovalDenied): ApprovalApplication(object())
        class Fake(PostgresExecutionRepository): pass
        with self.assertRaises(a.ApprovalDenied): ApprovalApplication(object.__new__(Fake))

    def test_EX37_unstarted_database_no_process_and_SQL_function_allowlist(self):
        db=PostgresLedger()
        with patch('subprocess.Popen') as popen:
            with self.assertRaises(d.ExecutionDenied): ExecutionUnitOfWork(db,'synthetic-account:test')
        popen.assert_not_called()
        db._ready=True
        uow=ExecutionUnitOfWork(db,'synthetic-account:test')
        with self.assertRaises(d.ExecutionDenied): uow.call('arbitrary_sql','SELECT 1')
        self.assertEqual(MAX_FRAME,8388608)

    def test_EX37_durable_codec_preserves_typed_refs_exactly_without_capabilities(self):
        source,inputs,broker=composition()
        obj={'records':{d.ref('query',inputs.query.query_id,inputs.query):d.encoded(inputs.query)},
             'permissions':{'principal':('runtime','cancel')},'nothing':None,'version':1}
        self.assertEqual(_unpack(json.loads(json.dumps(_pack(obj)))),obj)
        with self.assertRaises(d.ExecutionDenied): _pack(object())
        with self.assertRaises(d.ExecutionDenied): _unpack({'foreign':'payload'})

    def test_EX40_cli_arguments_rejected_before_database_or_process(self):
        output=io.StringIO()
        with patch.object(sys,'argv',['check_execution.py','existing-db']),patch.object(runner,'PostgresLedger') as db,contextlib.redirect_stdout(output):
            result=runner.main()
        self.assertEqual(result,2)
        self.assertEqual(json.loads(output.getvalue())['reason'],'arguments_not_accepted')
        db.assert_not_called()

    def test_EX40_migration_guard_contains_exact_predecessor_and_idempotence(self):
        db=PostgresLedger()
        db.migration_checksums[2]='2'*64
        script=runner.migration_script(db)
        self.assertIn("version=2 AND checksum='"+'2'*64+"'",script)
        self.assertIn('migration_checksum_mismatch',script)
        self.assertIn('apply_execution',script)
        self.assertNotIn('CREATE TABLE qh.ledger_stream',script)

    def test_runner_explicitly_reports_unimplemented_work_not_complete(self):
        self.assertGreater(len(runner.REMAINING),0)
        self.assertTrue(any('cancel_handoff' in r for r in runner.REMAINING))
        self.assertTrue(any('exact_per_intent' in r for r in runner.REMAINING))
