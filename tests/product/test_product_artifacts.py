"""Focused command-boundary doubles. These are NOT actual PostgreSQL evidence."""
from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
from hashlib import sha256
import json
import re
import subprocess
import threading
import unittest
from unittest.mock import patch

from quantharbor.adapters.postgres_ledger import PostgresLedger, LedgerStorageError
from quantharbor.adapters.product_database import ProductDatabase
from quantharbor.adapters.product_artifacts import ProductArtifacts, _metadata
from quantharbor.adapters.synthetic_reporting import SyntheticReportRepository
from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
from quantharbor.adapters.synthetic_research import SyntheticExperimentRepository
from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
from quantharbor.application.research import build_experiment
from quantharbor.domain.ledger import hash_record
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.research import known
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes
from quantharbor.domain.target import ref
from quantharbor.ports.target import TargetArtifacts
from synthetic_reporting import report, snapshot, encoded, correction, report_request, LATER
from synthetic_target import fixture, build
from synthetic_research import fixed_inputs

REPOSITORIES = (SyntheticReportRepository, SyntheticSnapshotRepository, SyntheticExperimentRepository, SyntheticTargetRepository)


@lru_cache(maxsize=1)
def examples():
    request, inputs = fixture()
    target = build(request, inputs)
    runs = fixed_inputs()
    run = runs[0]
    same = [x for x in runs if (x.market_id, x.scenario_id, x.fold_id) == (run.market_id, run.scenario_id, run.fold_id)]
    benchmark = next(x for x in same if x.strategy == 'buy_hold')
    cash = next(x for x in same if x.strategy == 'cash')
    experiment = build_experiment(run, SyntheticExperimentRepository(), benchmark=benchmark, cash_benchmark=cash)
    return report(), snapshot(), experiment, target


class Store:
    """Shared committed rows, with atomic copy-on-commit and injected outcomes.

    This intentionally models storage behavior, not PostgreSQL execution of DDL.
    """
    def __init__(self):
        self.rows = []
        self.mode = 'ok'
        self.installs = 0
        self.schema = 'absent'
        self.schema_versions = ()
        self.schema_fault = None
        self.calls = 0
        self.row_limit = 512
        self.byte_limit = 33554432
        self.namespace_bytes = 8388608
        self.entered = None
        self.release = None

    def query(self, sql, **kwargs):
        self.calls += 1
        if 'install_artifacts' in sql:
            if self.schema not in ('absent', 'valid') or self.schema_fault is not None:
                raise LedgerStorageError()
            if self.schema == 'valid' and self.schema_versions not in ((1,), (1, 2)):
                raise LedgerStorageError()
            if self.schema == 'absent':
                self.installs += 1
                self.schema = 'valid'
            self.schema_versions = (1, 2)
            return ''
        namespace = bytes.fromhex(re.search("WHERE namespace=convert_from\\(decode\\('([0-9a-f]+)'", sql)[1]).decode()
        return json.dumps(sorted((deepcopy(r) for r in self.rows if r['namespace'] == namespace),
                                 key=lambda r: (r['created_at'], r['kind'], r['artifact_id']))[:129])

    def run(self, args, *, input, **kwargs):
        if self.entered:
            self.entered.set()
            if not self.release.wait(5):
                raise AssertionError('gate test release missing')
        sql = input.decode()
        match = re.search("append_artifacts\\(convert_from\\(decode\\('([0-9a-f]+)','hex'\\),'UTF8'\\)::jsonb,([0-9]+)", sql)
        if match is None:
            raise AssertionError('unexpected write command')
        rows, capacity = json.loads(bytes.fromhex(match[1])), int(match[2])
        staged = deepcopy(self.rows)
        for row in rows:
            key = tuple(row[x] for x in ('namespace', 'kind', 'artifact_id'))
            prior = next((r for r in staged if tuple(r[x] for x in ('namespace', 'kind', 'artifact_id')) == key), None)
            if prior is not None:
                if prior != row:
                    return subprocess.CompletedProcess(args, 1, b'', b'ERROR: immutable conflict')
            else:
                staged.append(row)
        ns = rows[0]['namespace']
        subset = [r for r in staged if r['namespace'] == ns]
        if (len(subset)>capacity or len(subset)>128 or len(staged)>self.row_limit
                or sum(len(bytes.fromhex(r['payload'])) for r in subset)>self.namespace_bytes
                or sum(len(bytes.fromhex(r['payload'])) for r in staged)>self.byte_limit or self.mode == 'rollback'):
            return subprocess.CompletedProcess(args, 1, b'', b'ERROR: rolled back')
        if self.mode != 'unknown_absent':
            self.rows = staged
        if self.mode in ('unknown_saved', 'unknown_absent'):
            raise subprocess.TimeoutExpired(args, 60)
        return subprocess.CompletedProcess(args, 0, b'\nproduct_artifacts_committed\n', b'')


def opened():
    db = PostgresLedger()
    # Internal trust seam: no real private root, Docker, or SQL is used by these units.
    p = ProductDatabase('/private/tmp/qh-synthetic-artifact-mock', 'synthetic:artifact-mock')
    p.active, p.lock, p.fd = True, 90, 91
    db._product_database, db._ready, db._compose = p, True, ['mock-psql']
    db._product_generation = object()
    return db


class ProductArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.snapshot, cls.experiment, cls.target = examples()

    def setUp(self):
        self.db, self.store = opened(), Store()
        self.query = patch.object(self.db, '_query', side_effect=self.store.query)
        self.run = patch('quantharbor.adapters.product_artifacts.subprocess.run', side_effect=self.store.run)
        self.query.start()
        self.run.start()
        self.addCleanup(self.query.stop)
        self.addCleanup(self.run.stop)

    def repo(self, cls=SyntheticReportRepository, capacity=128):
        return cls.product_synthetic(self.db, capacity=capacity)

    def read(self, repo, value):
        if type(repo) is SyntheticTargetRepository:
            return repo.get(ref('plan', value.plan.plan_id, value.plan), environment='synthetic', account_ref=value.plan.body.account_ref)
        kind = type(repo)
        key = value.report_id if kind is SyntheticReportRepository else value.snapshot_id if kind is SyntheticSnapshotRepository else value.result_id
        acct = value.manifest.account_ref if kind is SyntheticExperimentRepository else value.account_ref
        return repo.get(key, environment='synthetic', account_ref=acct)

    def test_four_exact_factories_shared_data_duplicate_and_reconnected_facade(self):
        for cls, value in zip(REPOSITORIES, examples()):
            a, b = self.repo(cls), self.repo(cls)
            self.assertIs(type(a), cls)
            self.assertIs(a._lock, b._lock)
            self.assertEqual(a.append(value), value)
            before = deepcopy(self.store.rows)
            self.assertEqual(b.append(value), value)
            self.assertEqual(self.store.rows, before)
            self.assertEqual(self.read(b, value), value.plan if cls is SyntheticTargetRepository else value)
            expected = (value.plan, *value.candidates, value.result) if cls is SyntheticTargetRepository else (value,)
            acct = value.plan.body.account_ref if cls is SyntheticTargetRepository else value.manifest.account_ref if cls is SyntheticExperimentRepository else value.account_ref
            listed = b.list_records(environment='synthetic', account_ref=acct)
            self.assertEqual(set(listed), set(expected))
            self.assertIs(type(listed), tuple)
            self.assertEqual(b.list_records(environment='synthetic', account_ref='synthetic-account:other'), ())
        self.assertEqual(self.store.installs, 1)

    def test_common_registry_upgrade_and_known_v2_preserve_artifact_rows(self):
        # Command-boundary schema state simulation, not actual DDL evidence.
        self.store.schema, self.store.schema_versions = 'valid', (1,)
        repo = self.repo()
        self.assertEqual(self.store.schema_versions, (1, 2))
        repo.append(self.report)
        before = deepcopy(self.store.rows)
        self.assertEqual(self.read(self.repo(), self.report), self.report)
        self.assertEqual(self.store.rows, before)
        self.assertEqual(self.store.installs, 0)

    def test_common_registry_failure_keeps_existing_rows_and_v1_record(self):
        self.repo().append(self.report)
        before = deepcopy(self.store.rows)
        self.store.schema_versions, self.store.schema_fault = (1,), 'ddl_rollback'
        with self.assertRaises(LedgerStorageError):
            self.repo()
        self.assertEqual(self.store.rows, before)
        self.assertEqual(self.store.schema_versions, (1,))

    def test_common_registry_missing_and_future_versions_are_not_reinstalled(self):
        self.store.schema = 'valid'
        for versions in ((), (2,), (1, 3), (1, 2, 3)):
            self.store.schema_versions = versions
            with self.subTest(versions=versions), self.assertRaises(LedgerStorageError):
                self.repo()
        self.assertEqual(self.store.installs, 0)

    def test_backend_constructor_is_io_free_and_explicit_factory_is_required(self):
        count = self.store.calls
        ProductArtifacts(self.db, 'report')
        self.assertEqual(self.store.calls, count)

    def test_foreign_unready_disposable_closed_and_old_generation_rejected(self):
        class Foreign(PostgresLedger):
            pass
        for db in (object(), Foreign(), PostgresLedger()):
            for cls in REPOSITORIES:
                with self.subTest(type=type(db), repo=cls), self.assertRaises((ContractError, LedgerStorageError)):
                    cls.product_synthetic(db)
        for attr, val in (('_ready', False), ('_product_generation', None)):
            old = getattr(self.db, attr)
            setattr(self.db, attr, val)
            with self.assertRaises(LedgerStorageError):
                self.repo()
            setattr(self.db, attr, old)
        repo = self.repo()
        repo.append(self.report)
        self.db._ready = False
        with self.assertRaises(LedgerStorageError):
            self.read(repo, self.report)
        self.db._ready, self.db._product_generation = True, object()
        with self.assertRaises(LedgerStorageError):
            self.read(repo, self.report)
        self.assertEqual(self.read(self.repo(), self.report), self.report)

    def test_inactive_or_missing_owner_lock_rejected(self):
        p = self.db._product_database
        for attr, value in (('active', False), ('lock', None), ('fd', None)):
            prior = getattr(p, attr)
            setattr(p, attr, value)
            with self.assertRaises(LedgerStorageError):
                self.repo()
            setattr(p, attr, prior)

    def test_every_explicit_factory_rechecks_schema_and_rejects_damage(self):
        self.repo()
        for damage in ('checksum', 'future', 'missing_version', 'missing_column', 'missing_index'):
            self.store.schema = damage
            with self.subTest(damage=damage), self.assertRaises(LedgerStorageError) as caught:
                self.repo()
            self.assertEqual(caught.exception.reason, 'product_artifact_schema_invalid')
        self.assertEqual(self.store.installs, 1)

    def test_read_rejects_wire_hash_record_hash_id_account_environment_and_index_tampering(self):
        repo = self.repo()
        repo.append(self.report)
        original = deepcopy(self.store.rows)
        for field, value in (('record_hash', '0'*64), ('wire_sha256', '0'*64), ('artifact_id', 'other'),
                ('account_ref', 'synthetic-account:other'), ('environment', 'paper'), ('created_at', LATER),
                ('predecessor', 'missing'), ('kind', 'ExperimentResult')):
            self.store.rows = deepcopy(original)
            self.store.rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(LedgerStorageError):
                self.read(repo, self.report)
        self.store.rows = deepcopy(original)
        raw = bytes.fromhex(original[0]['payload']) + b' '
        self.store.rows[0].update(payload=raw.hex(), wire_sha256=sha256(raw).hexdigest())
        with self.assertRaises(LedgerStorageError):
            self.read(repo, self.report)

    def test_target_get_checks_whole_bundle_and_evaluated_at_metadata(self):
        repo = self.repo(SyntheticTargetRepository)
        repo.append(self.target)
        expected = self.target.plan.body.request.evaluated_at
        self.assertTrue(all(r['created_at'] == expected for r in self.store.rows))
        original = deepcopy(self.store.rows)
        for kind in ('candidate', 'result', 'plan'):
            self.store.rows = [r for r in deepcopy(original) if r['kind'] != kind]
            with self.subTest(kind=kind), self.assertRaises(LedgerStorageError):
                self.read(repo, self.target)
        self.store.rows = original
        self.store.rows[-1]['created_at'] = LATER
        with self.assertRaises(LedgerStorageError):
            repo.get(ref('candidate', self.target.candidates[0].candidate_id, self.target.candidates[0]),
                     environment='synthetic', account_ref=self.target.plan.body.account_ref)

    def test_conflict_and_low_facade_capacity_are_shared_no_eviction(self):
        repo = self.repo()
        repo.append(self.report)
        low = self.repo(capacity=1)
        from quantharbor.application.reporting import build_report
        from synthetic_valuation import rights
        other = build_report(self.report.snapshot, report_request(created_at=LATER), (rights(),), SyntheticReportRepository())
        before = deepcopy(self.store.rows)
        with self.assertRaises(ContractError):
            low.append(other)
        self.assertEqual(self.store.rows, before)
        self.assertEqual(low.append(self.report), self.report)
        bad = deepcopy(self.report)
        object.__setattr__(bad, 'status', 'other')
        with self.assertRaises(ContractError):
            repo.append(bad)
        self.assertEqual(self.store.rows, before)

    def test_target_middle_conflict_and_quota_rollback_leave_no_partial_rows(self):
        repo = self.repo(SyntheticTargetRepository)
        # Simulate a database race at the command boundary after Python validation.
        real_run = self.store.run
        def conflict(args, **kwargs):
            candidate = self.target.candidates[0]
            raw = canonical_bytes(CanonicalPayload('OrderCandidate', 1, 'synthetic', candidate))
            _, row = _metadata('target', raw, self.target.plan)
            row['record_hash'] = '0'*64
            self.store.rows.append(row)
            return real_run(args, **kwargs)
        with patch('quantharbor.adapters.product_artifacts.subprocess.run', side_effect=conflict):
            with self.assertRaises(LedgerStorageError) as caught:
                repo.append(self.target)
        # The injected external row is corrupt/incomplete, so the follow-up read
        # cannot establish the transaction outcome even though no plan was added.
        self.assertEqual(caught.exception.reason, 'product_artifact_commit_unknown')
        self.assertEqual(len(self.store.rows), 1)
        self.assertFalse(any(r['kind'] == 'plan' for r in self.store.rows))
        self.store.rows = []
        for attr, limit in (('namespace_bytes', 1), ('byte_limit', 1), ('row_limit', 1)):
            old = getattr(self.store, attr)
            setattr(self.store, attr, limit)
            with self.subTest(quota=attr), self.assertRaises(LedgerStorageError):
                repo.append(self.target)
            self.assertEqual(self.store.rows, [])
            setattr(self.store, attr, old)

    def test_commit_rollback_and_lost_ack_are_distinct_and_same_append_can_resolve(self):
        repo = self.repo()
        self.store.mode = 'rollback'
        with self.assertRaises(LedgerStorageError) as caught:
            repo.append(self.report)
        self.assertEqual(caught.exception.reason, 'product_artifact_write_rolled_back')
        self.assertEqual(self.store.rows, [])
        self.store.mode = 'unknown_absent'
        with self.assertRaises(LedgerStorageError) as caught:
            repo.append(self.report)
        self.assertEqual(caught.exception.reason, 'product_artifact_commit_unknown')
        self.store.mode = 'unknown_saved'
        self.assertEqual(repo.append(self.report), self.report)
        self.assertEqual(repo.append(self.report), self.report)
        self.assertEqual(len(self.store.rows), 1)

    def test_report_snapshot_corrections_allow_existing_branch_semantics(self):
        from quantharbor.application.reporting import build_report
        from synthetic_valuation import rights, request
        snapshots = SyntheticSnapshotRepository()
        first = snapshot(repository=snapshots)
        second = correction(snapshots, first)
        third = correction(snapshots, first, request=replace(second.valuation.request, request_id='another-correction'))
        reports = SyntheticReportRepository()
        initial = report(value=first, repository=reports)
        next_report = build_report(second, report_request(created_at=LATER, supersedes_report_id=initial.report_id),
                                   (rights(),), reports)
        branch = build_report(third, report_request(created_at=LATER, supersedes_report_id=initial.report_id),
                              (rights(),), reports)
        for cls, values in ((SyntheticSnapshotRepository, (first, second, third)),
                            (SyntheticReportRepository, (initial, next_report, branch))):
            persistent = self.repo(cls)
            with self.assertRaises(ContractError):
                persistent.append(values[1])
            for value in values:
                self.assertEqual(persistent.append(value), value)
            self.assertEqual(len(persistent.list_records(environment='synthetic', account_ref=first.account_ref)), 3)

    def test_target_predecessor_and_history_preserve_old_generation(self):
        from quantharbor.application.target import build_target
        request, inputs = fixture(targets=('3', None))
        memory = SyntheticTargetRepository()
        original = build_target(request, inputs, memory)
        revised_request = replace(request, request_id='persistent-revision',
            predecessor_plan_ref=ref('plan', original.plan.plan_id, original.plan),
            targets=(replace(request.targets[0], value='4'),))
        revised = build_target(revised_request, inputs, memory)
        persistent = self.repo(SyntheticTargetRepository)
        with self.assertRaises(ContractError):
            persistent.append(revised)
        persistent.append(original)
        persistent.append(revised)
        self.db._product_generation = object()
        fresh = self.repo(SyntheticTargetRepository)
        restored = self.read(fresh, original)
        self.assertEqual(restored.body.request.authority_generation, request.authority_generation)
        self.assertEqual(restored, original.plan)

    def test_target_partial_backend_update_and_payload_oversize_rejected(self):
        repo = self.repo(SyntheticTargetRepository)
        with self.assertRaises(ContractError):
            repo._records[('plan', self.target.plan.plan_id)] = encoded(self.target.plan)
        self.assertEqual(self.store.rows, [])
        with self.assertRaises(ContractError):
            _metadata('report', b'x' * 65537)
        for capacity in (0, 129, True):
            with self.assertRaises(ContractError):
                self.repo(capacity=capacity)

    def test_experiment_predecessor_comparison_fork_scope_and_conflict(self):
        repo = self.repo(SyntheticExperimentRepository)
        original = self.experiment
        manifest = replace(original.manifest, predecessor=original.result_id)
        revised = replace(original, manifest=manifest, result_id='experiment:' + hash_record(manifest))
        with self.assertRaises(ContractError):
            repo.append(revised)
        repo.append(original)
        self.assertEqual(repo.append(revised), revised)
        later = replace(manifest, created_at='2026-10-30T00:00:00Z')
        fork = replace(revised, manifest=later, result_id='experiment:' + hash_record(later))
        before = deepcopy(self.store.rows)
        with self.assertRaises(ContractError):
            repo.append(fork)
        conflicting = replace(original, cash_benchmark_return=known(1))
        with self.assertRaises(ContractError):
            repo.append(conflicting)
        with self.assertRaises(ContractError):
            repo.get(original.result_id, environment='synthetic', account_ref='synthetic-account:other')
        self.assertEqual(self.store.rows, before)

    def test_concurrent_facades_do_not_double_append(self):
        a, b = self.repo(), self.repo()
        barrier, results, errors = threading.Barrier(2), [], []
        def append(repo):
            try:
                barrier.wait(5)
                results.append(repo.append(self.report))
            except BaseException as error:
                errors.append(type(error).__name__)
        threads = [threading.Thread(target=append, args=(r,)) for r in (a,b)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        self.assertEqual(errors, [])
        self.assertEqual(results, [self.report, self.report])
        self.assertEqual(len(self.store.rows), 1)

    def test_close_waits_for_inflight_write_and_permanently_invalidates_old_facade(self):
        repo = self.repo()
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        self.store.entered, self.store.release = entered, release
        errors = []
        def append():
            try:
                repo.append(self.report)
            except BaseException as error:
                errors.append(type(error).__name__)
        def close():
            self.db.close()
            closed.set()
        def fake_close(p, db):
            db._ready, p.active = False, False
        with patch.object(ProductDatabase, 'close', fake_close):
            writer = threading.Thread(target=append)
            writer.start()
            self.assertTrue(entered.wait(5))
            closer = threading.Thread(target=close)
            closer.start()
            self.assertFalse(closed.wait(0.05))
            release.set()
            writer.join(5)
            closer.join(5)
        self.assertEqual(errors, [])
        self.assertTrue(closed.is_set())
        with self.assertRaises(LedgerStorageError):
            self.read(repo, self.report)


class CommitOutcomeTests(unittest.TestCase):
    def backend(self):
        backend = ProductArtifacts.__new__(ProductArtifacts)
        backend._database = PostgresLedger()
        backend._database._compose = ['mock-psql']
        return backend

    def test_error_after_commit_is_confirmed_from_immutable_rows_before_classification(self):
        response = subprocess.CompletedProcess([], 3, b'', b'ERROR: confirmation query cancelled')
        expected = {'immutable-key': b'canonical'}
        backend = self.backend()
        with patch('quantharbor.adapters.product_artifacts.subprocess.run', return_value=response) as run, patch.object(backend, '_load', return_value=expected) as read:
            backend._commit('fixed internal SQL', expected)
            self.assertEqual(run.call_count, 1)
            read.assert_called_once_with()
        with patch('quantharbor.adapters.product_artifacts.subprocess.run', return_value=response), patch.object(backend, '_load', side_effect=LedgerStorageError('product_artifact_database_unavailable')):
            with self.assertRaises(LedgerStorageError) as caught:
                backend._commit('fixed internal SQL', expected)
            self.assertEqual(caught.exception.reason, 'product_artifact_commit_unknown')

    def test_os_failure_after_start_requires_confirmation_and_never_retries(self):
        for error in (OSError('synthetic pipe lost'), subprocess.TimeoutExpired('mock', 60)):
            backend = self.backend()
            with patch('quantharbor.adapters.product_artifacts.subprocess.run', side_effect=error) as run, patch.object(backend, '_load', return_value={}):
                with self.assertRaises(LedgerStorageError) as caught:
                    backend._commit('fixed internal SQL', {'immutable-key': b'canonical'})
                self.assertEqual(caught.exception.reason, 'product_artifact_commit_unknown')
                self.assertEqual(run.call_count, 1)
            with patch('quantharbor.adapters.product_artifacts.subprocess.run', side_effect=error) as run, patch.object(backend, '_load', return_value={'immutable-key': b'canonical'}):
                backend._commit('fixed internal SQL', {'immutable-key': b'canonical'})
                self.assertEqual(run.call_count, 1)

    def test_known_start_failure_and_server_rollback_do_not_claim_success(self):
        backend = self.backend()
        for failure in (FileNotFoundError(), subprocess.CompletedProcess([], 1, b'', b'ERROR: transaction aborted')):
            kwargs = {'side_effect': failure} if isinstance(failure, BaseException) else {'return_value': failure}
            with patch('quantharbor.adapters.product_artifacts.subprocess.run', **kwargs), patch.object(backend, '_load', return_value={}) as read:
                with self.assertRaises(LedgerStorageError) as caught:
                    backend._commit('fixed internal SQL', {'id': b'canonical'})
                self.assertEqual(caught.exception.reason, 'product_artifact_write_rolled_back')
                if isinstance(failure, FileNotFoundError):
                    read.assert_not_called()
                else:
                    read.assert_called_once_with()

    def test_unacknowledged_or_invalid_utf8_output_needs_exact_immutable_match(self):
        backend = self.backend()
        response = subprocess.CompletedProcess([], 0, b'\xff', b'')
        with patch('quantharbor.adapters.product_artifacts.subprocess.run', return_value=response), patch.object(backend, '_load', return_value={'id': b'conflicting'}):
            with self.assertRaises(LedgerStorageError) as caught:
                backend._commit('fixed internal SQL', {'id': b'canonical'})
            self.assertEqual(caught.exception.reason, 'product_artifact_commit_unknown')


if __name__ == '__main__':
    unittest.main()
