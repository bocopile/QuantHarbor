"""P28-03/2b-2a command-boundary synthetic evidence; actual PG is root-owned."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import threading
import time
import unittest
from unittest.mock import Mock, patch

from quantharbor.adapters import product_ai as s
from quantharbor.adapters.postgres_ledger import LedgerStorageError, PostgresLedger
from quantharbor.adapters.synthetic_investment_ai import SyntheticAIRepository, AIDenied
from quantharbor.application.investment_ai import Sources
from quantharbor.domain import investment_ai as d
from quantharbor.domain.primitives import ContractError, utc_instant
from test_product_ai import MemoryWire, opened, policy, request, record, sample, NOW, LATER


class ProductCoreTests(unittest.TestCase):
    def setUp(self):
        self.db, self.wire = opened(), MemoryWire()
        self.schema = patch.object(s, 'ensure_schema')
        self.pipe = patch.object(s, '_Pipe', return_value=self.wire)
        self.schema.start()
        self.pipe_mock = self.pipe.start()
        self.addCleanup(self.schema.stop)
        self.addCleanup(self.pipe.stop)

    def factory(self, **kwargs):
        return SyntheticAIRepository.product_synthetic(self.db, **kwargs)

    def seed(self, book, markers=()):
        self.wire.raw = s._json(s._wire(book))
        self.wire.revision = 3
        self.wire.markers = markers
        self.wire.operation_id = 'a'*32
        self.wire.digest = 'b'*64
        self.wire.opcode = 'append'

    def book(self):
        return s._decode(self.wire.raw, self.wire.markers, self.wire.revision)

    def reserve(self, repo, identity='attempt:1', r=None, p=None, usage=None):
        return repo.reserve(r or request(p), p or policy(), identity, usage or d.priced(9, 20), at=NOW)

    def test_factory_has_one_deadline_across_schema_and_recovery(self):
        metadata = self.wire.metadata
        calls = []
        def delayed(deadline):
            calls.append(True)
            if len(calls) == 2:
                time.sleep(0.06)
            return metadata(deadline)
        with patch.object(s, '_DEADLINE', 0.1), patch.object(s, 'ensure_schema', side_effect=lambda *a, **k: time.sleep(0.06)), patch.object(self.wire, 'metadata', side_effect=delayed):
            with self.assertRaises(LedgerStorageError) as caught:
                self.factory()
        self.assertEqual(caught.exception.reason, 'product_ai_timeout')
        self.assertEqual(self.wire.writes, 0)

    def test_reserve_deadline_includes_input_encoding(self):
        repo = self.factory()
        original, calls = d.encoded, []
        def delayed(obj):
            if type(obj) is d.ResearchRequest and not calls:
                calls.append(True)
                time.sleep(0.12)
            return original(obj)
        r, p = request(), policy()
        with patch.object(s, '_DEADLINE', 0.1), patch.object(d, 'encoded', side_effect=delayed):
            with self.assertRaises(LedgerStorageError) as caught:
                self.reserve(repo, r=r, p=p)
        self.assertEqual(caught.exception.reason, 'product_ai_timeout')
        self.assertEqual(self.wire.writes, 0)

    def test_balance_rejects_changed_overlapping_window_and_cap(self):
        caps = d.Usage(100, 100, 1, 100)
        p = policy(window_caps=caps, role_caps=caps, request_caps=caps, attempt_caps=caps)
        repo = self.factory()
        self.reserve(repo, p=p, r=request(p, caps=caps))
        self.assertEqual(repo.balance(p), 50)
        changed = replace(p, window_end='2025-02-01T00:00:00Z', window_caps=replace(caps, charge=200))
        with self.assertRaises(ContractError):
            repo.balance(changed)
        self.assertEqual(repo.balance(p), 50)

    def test_exact_factory_default_memory_and_no_import_seam(self):
        repo = self.factory()
        self.assertIs(type(repo), SyntheticAIRepository)
        for name in ('restore', 'from_repository', 'import_mapping', 'import_json'):
            self.assertFalse(hasattr(repo, name))
        for invalid in ({}, s._Book(), SyntheticAIRepository(), b'{}', PostgresLedger()):
            with self.assertRaises((ContractError, LedgerStorageError)):
                SyntheticAIRepository.product_synthetic(invalid)
        class Subclass(SyntheticAIRepository):
            pass
        with self.assertRaises(ContractError):
            Subclass.product_synthetic(self.db)
        memory = SyntheticAIRepository()
        a, new = self.reserve(memory)
        self.assertTrue(new)
        memory.dispatch(a.attempt_id, at=NOW)
        self.assertEqual(memory.settle(a.attempt_id, d.priced(9, 20), at=LATER).state, 'settled')
        self.assertFalse(hasattr(memory, '_product_store'))
        self.assertEqual(self.wire.writes, 0)

    def test_typed_database_history_hydration_and_missing_result(self):
        book, _ = sample('settled')
        self.seed(book)
        repo = self.factory()
        a = s._dto(book.records[2][2], d.AIBudgetAttempt)
        self.assertEqual(repo.attempt(a.attempt_id), a)
        self.assertEqual(repo.get(a.request_ref), request())
        self.assertEqual(repo.balance(policy()), policy().window_caps.charge-50)
        self.assertIsNone(repo.result_for(a.attempt_id))
        self.assertEqual(repo.hypotheses(), ())
        self.assertEqual(self.book().holds, book.holds)
        self.assertEqual(self.wire.writes, 0)

    def test_every_read_loads_current_revision_not_facade_memory(self):
        a, b = self.factory(), self.factory()
        self.reserve(a)
        self.assertEqual(b.attempt('attempt:1').state, 'reserved')
        b.cancel('attempt:1', at=LATER)
        self.assertEqual(a.attempt('attempt:1').state, 'cancelled_before_dispatch')
        self.assertEqual(a.balance(policy()), policy().window_caps.charge)
        self.assertEqual(a._records, {})
        self.assertEqual(b._attempts, {})

    def test_exact_source_binding_is_per_facade_and_never_restored(self):
        a, b = self.factory(), self.factory()
        with patch.object(Sources, 'validate', side_effect=AssertionError('source access')) as validate:
            source = Sources(repository=a)
            self.assertIs(a._current_sources, source)
            self.assertIsNone(b._current_sources)
            with self.assertRaises(ContractError):
                b.bind_sources(source)
            with self.assertRaises(ContractError):
                a.bind_sources(object())
            self.assertIsNone(self.factory()._current_sources)
            validate.assert_not_called()
        self.assertEqual(self.wire.writes, 0)

    def test_shared_facade_race_reserves_once_and_only_winner_is_new(self):
        a, b = self.factory(), self.factory()
        barrier = threading.Barrier(2)
        def work(repo):
            barrier.wait(timeout=2)
            return self.reserve(repo)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(work, (a, b)))
        self.assertEqual(sorted(new for _, new in results), [False, True])
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(self.wire.writes, 1)
        self.assertEqual(len(self.book().records), 3)
        self.assertEqual(len(self.book().holds), 1)
        self.assertIs(a._product_store._shared, b._product_store._shared)

    def test_same_payload_idempotent_different_payload_conflicts_even_terminal(self):
        repo = self.factory()
        a, new = self.reserve(repo)
        self.assertTrue(new)
        self.assertEqual(self.reserve(repo), (a, False))
        with self.assertRaises(ContractError):
            self.reserve(repo, usage=d.priced(10, 20))
        with self.assertRaises(ContractError):
            self.reserve(repo, r=request(run_id='different'))
        terminal = repo.cancel(a.attempt_id, at=LATER)
        self.assertEqual(self.reserve(repo), (terminal, False))
        self.assertEqual(self.wire.writes, 2)

    def test_budget_scope_window_role_request_attempt_and_concurrency_not_bypassed(self):
        for which in ('window_caps', 'role_caps', 'request_caps', 'attempt_caps', 'request', 'concurrency'):
            with self.subTest(limit=which):
                self.db._product_generation = object()
                self.wire = MemoryWire()
                self.pipe_mock.return_value = self.wire
                caps = d.Usage(100, 100, 4, 100)
                kw = {k: caps for k in ('window_caps', 'role_caps', 'request_caps')}
                kw['attempt_caps'] = replace(caps, calls=1)
                if which != 'request' and which != 'concurrency':
                    kw[which] = replace(kw[which], charge=60)
                if which == 'request_caps':
                    kw['role_caps'] = replace(caps, charge=60)
                p = policy(**kw, concurrency_cap=1 if which == 'concurrency' else 2)
                r = request(p, caps=replace(caps, charge=60) if which == 'request' else caps)
                repo = self.factory()
                if which == 'attempt_caps':
                    with self.assertRaises(AIDenied):
                        self.reserve(repo, p=p, r=r, usage=d.priced(69, 0))
                    self.assertEqual(self.wire.writes, 0)
                else:
                    self.reserve(repo, p=p, r=r, usage=d.priced(39, 0))
                    with self.assertRaises(AIDenied) as caught:
                        self.reserve(self.factory(), identity='attempt:2', p=p, r=r, usage=d.priced(29, 0))
                    self.assertEqual(caught.exception.reason, 'budget')
                    self.assertEqual(self.wire.writes, 1)

    def test_changed_policy_same_window_and_overlap_are_rejected(self):
        repo = self.factory()
        self.reserve(repo)
        for p in (policy(policy_id='budget:2', concurrency_cap=1),
                  policy(policy_id='budget:2', window_start='2024-02-01T00:00:00Z')):
            with self.subTest(policy=p.policy_id), self.assertRaises(ContractError):
                self.reserve(self.factory(), identity='attempt:2', p=p, r=request(p, request_id='request:2'))
        with self.assertRaises(ContractError):
            repo.balance(policy(concurrency_cap=1))
        self.assertEqual(self.wire.writes, 1)

    def test_deadline_retry_actual_and_exact_usage_denied_without_write(self):
        repo = self.factory()
        variants = [
            (policy(retry_policy=d.RetryPolicy(0, (), 0, 1, ('synthetic-to-actual',))), None, 'retry_disabled'),
            (policy(), request(client_profile='actual'), 'actual_disabled')]
        for p, r, reason in variants:
            with self.subTest(reason=reason), self.assertRaises(AIDenied) as caught:
                self.reserve(repo, p=p, r=r or request(p))
            self.assertEqual(caught.exception.reason, reason)
        with self.assertRaises(AIDenied) as caught:
            repo.reserve(request(), policy(), 'late:1', d.priced(9, 20), at=request().deadline)
        self.assertEqual(caught.exception.reason, 'deadline')
        with self.assertRaises(ContractError):
            self.reserve(repo, usage=d.Usage(9, 20, 1, 1))
        self.assertEqual(self.wire.writes, 0)

    def test_atomic_reserve_and_cancel_do_not_publish_intermediate_records(self):
        repo = self.factory()
        published = []
        original = self.wire.publish
        def publish(*args):
            book = s._decode(args[4], args[6], args[0]+1)
            published.append((args[1], book))
            return original(*args)
        with patch.object(self.wire, 'publish', side_effect=publish):
            self.reserve(repo)
            repo.cancel('attempt:1', at=LATER)
        self.assertEqual([op for op, _ in published], [s.Opcode.RESERVE, s.Opcode.CANCEL])
        b = published[0][1]
        self.assertEqual(len(b.records), 3)
        self.assertEqual(len(b.payloads), 1)
        self.assertEqual(len(b.policies), 1)
        self.assertEqual(len(b.holds), 1)
        self.assertEqual(published[1][1].holds, ())
        self.assertEqual(published[1][1].processed, ())

    def test_cancel_only_reserved_and_retain_result_preserves_hold(self):
        repo = self.factory()
        old, _ = self.reserve(repo)
        a = repo.cancel('attempt:1', at=LATER, retain_result=True)
        b = self.book()
        h = d.ref('attempt', a.attempt_id, a).sha256
        self.assertNotEqual(h, d.ref('attempt', old.attempt_id, old).sha256)
        self.assertEqual(b.holds, (h,))
        self.assertEqual(b.payloads[0][0], h)
        self.assertIsNone(repo.result_for(a.attempt_id))
        with self.assertRaises(ContractError):
            repo.cancel(a.attempt_id, at=LATER)
        self.assertEqual(self.wire.writes, 2)

    def test_future_attempt_headroom_rejects_tight_reserve_without_partial_write(self):
        b, _ = sample()
        current = sum(len(raw) for _, _, raw in b.records)+196608
        repo = self.factory(byte_capacity=current+4096)
        with self.assertRaises(AIDenied) as caught:
            self.reserve(repo)
        self.assertEqual(caught.exception.reason, 'capacity')
        self.assertEqual(self.wire.writes, 0)
        self.assertIsNone(repo.get(d.ref('request', request().request_id, request())))

    def test_additional_reserve_cannot_spend_existing_attempt_growth_headroom(self):
        p = policy()
        b, _ = sample()
        first_bound = sum(len(raw) for k, _, raw in b.records if k != 'attempt')+196608+65536
        repo = self.factory(byte_capacity=first_bound+200000)
        self.reserve(repo)
        raw, revision = self.wire.raw, self.wire.revision
        with self.assertRaises(AIDenied) as caught:
            self.reserve(repo, identity='attempt:2', r=request(p, request_id='request:2'))
        self.assertEqual(caught.exception.reason, 'capacity')
        self.assertEqual((self.wire.raw, self.wire.revision), (raw, revision))
        self.assertEqual(repo.cancel('attempt:1', at=LATER).state, 'cancelled_before_dispatch')
        self.assertEqual(self.wire.writes, 2)

    def test_unprovable_future_auxiliary_slot_blocks_admission_without_client(self):
        repo = self.factory()
        for name, value in (('_SLOT', 81919), ('_GLOBAL', 4096), ('_ENCODED', 4096)):
            with self.subTest(bound=name), patch.object(s, name, value), self.assertRaises(AIDenied) as caught:
                self.reserve(repo)
            self.assertEqual(caught.exception.reason, 'capacity')
            self.assertEqual(self.wire.writes, 0)
        self.assertFalse(repo._product_store._shared.failed)

    def test_malformed_cancel_and_reserve_do_not_poison_shared_generation(self):
        repo = self.factory()
        for bad in ([], {}, True, 'x'*129):
            with self.subTest(identity=type(bad)), self.assertRaises(ContractError):
                self.reserve(repo, identity=bad)
        self.reserve(repo)
        for at, retain in ((object(), False), (LATER, 1)):
            with self.assertRaises(ContractError):
                repo.cancel('attempt:1', at=at, retain_result=retain)
        self.assertEqual(repo.attempt('attempt:1').state, 'reserved')
        self.assertFalse(repo._product_store._shared.failed)
        self.assertEqual(self.wire.writes, 1)

    def test_two_first_factories_share_one_recovery_barrier(self):
        b, _ = sample('dispatched')
        self.seed(b)
        barrier = threading.Barrier(2)
        def factory(_):
            barrier.wait(timeout=2)
            return self.factory()
        with ThreadPoolExecutor(max_workers=2) as pool:
            facades = list(pool.map(factory, range(2)))
        self.assertEqual(self.wire.writes, 1)
        self.assertEqual([r.attempt('attempt:1').state for r in facades], ['unknown_charge']*2)
        self.assertIs(facades[0]._product_store._shared, facades[1]._product_store._shared)

    def test_saturated_byte_and_record_capacity_still_cancel(self):
        b, _ = sample()
        size = sum(len(raw) for k, _, raw in b.records if k != 'attempt')+196608+65536
        repo = self.factory(capacity=7, byte_capacity=size)
        self.reserve(repo)
        before = s._quota(self.book(), ())[0]
        with self.assertRaises(AIDenied):
            repo.append('request', 'request:2', request(request_id='request:2'))
        self.assertEqual(repo.cancel('attempt:1', at=LATER, retain_result=True).state, 'cancelled_before_dispatch')
        self.assertEqual(s._quota(self.book(), ())[0], before)
        self.assertEqual(self.wire.writes, 2)

    def test_full_record_closing_hold_and_cancel_release(self):
        repo = self.factory(capacity=6)
        self.reserve(repo)
        with self.assertRaises(AIDenied):
            repo.append('request', 'request:2', request(request_id='request:2'))
        repo.cancel('attempt:1', at=LATER)
        repo.append('request', 'request:2', request(request_id='request:2'))
        self.assertEqual(len(self.book().records), 4)

    def test_first_factory_recovery_reserved_uses_reserved_time_and_no_result_marker(self):
        b, _ = sample()
        self.seed(b)
        repo = self.factory()
        a = repo.attempt('attempt:1')
        self.assertEqual((a.state, a.settled_at), ('cancelled_before_dispatch', utc_instant(NOW)))
        self.assertEqual(self.book().holds, ())
        self.assertEqual(self.book().processed, ())
        self.assertEqual(self.wire.markers, ())
        self.assertIsNone(repo.result_for(a.attempt_id))
        self.assertEqual(repo.balance(policy()), policy().window_caps.charge)
        self.assertEqual(self.wire.opcode, 'restart_reconcile')
        self.assertEqual(self.wire.writes, 1)

    def test_dispatched_recovery_rebinds_all_hash_keys_preserves_receipts_and_query16(self):
        b, _ = sample('dispatched')
        source = d.AIRef('document', 'historical:doc', 1, d.CANONICAL, 'a'*64)
        r = request(source_refs=(source,))
        a = replace(s._dto(b.records[2][2], d.AIBudgetAttempt), request_ref=d.ref('request', r.request_id, r))
        ah = d.ref('attempt', a.attempt_id, a).sha256
        receipt = d.QueryReceipt(d.Query('document_view', source), (source,), LATER)
        b = replace(b, records=(record('request', r), b.records[1], record('attempt', a)),
            payloads=((ah, a.request_ref.sha256, a.policy_ref.sha256, a.reserved_usage),),
            holds=(ah,), queries=((a.request_ref.sha256, 16),), receipts=((ah, (receipt,)),),
            denials=((ah, ('capacity', 'query_denied')),))
        self.seed(b)
        with patch.object(Sources, 'validate', side_effect=AssertionError('source access')) as validate:
            repo = self.factory()
            unknown = repo.attempt(a.attempt_id)
            self.assertEqual((unknown.state, unknown.settled_at, unknown.reasons), ('unknown_charge', utc_instant(NOW), ('unknown_charge',)))
            self.assertEqual(repo.query_count(a.request_ref), 16)
            self.assertEqual(repo.query_denials(a.attempt_id), ('capacity', 'query_denied'))
            new = self.book()
            h = d.ref('attempt', unknown.attempt_id, unknown).sha256
            self.assertNotEqual(h, ah)
            self.assertEqual(new.payloads[0][0], h)
            self.assertEqual(new.receipts, ((h, (receipt,)),))
            self.assertEqual(new.holds, (h,))
            self.assertEqual(new.denials[0][0], h)
            self.assertEqual(repo.balance(policy()), policy().window_caps.charge-50)
            with self.assertRaises(AIDenied) as caught:
                self.reserve(repo, identity='attempt:2', r=request(request_id='request:2'))
            self.assertEqual(caught.exception.reason, 'unknown_charge')
            self.assertIsNone(repo.result_for(a.attempt_id))
            validate.assert_not_called()

    def test_terminal_settlement_overrun_unknown_and_retain_hold_are_unchanged(self):
        for state in ('settled', 'unknown_charge', 'cancelled_before_dispatch'):
            with self.subTest(state=state):
                self.db._product_generation = object()
                b, _ = sample(state)
                if state == 'settled':
                    a = replace(s._dto(b.records[2][2], d.AIBudgetAttempt), actual_usage=d.priced(99, 20), reasons=('usage_overrun',))
                    h = d.ref('attempt', a.attempt_id, a).sha256
                    b = replace(b, records=(*b.records[:2], record('attempt', a)),
                        payloads=((h, *b.payloads[0][1:]),), holds=(h,), blocked=b.policies)
                elif state == 'cancelled_before_dispatch':
                    b = replace(b, holds=(b.payloads[0][0],))
                self.seed(b)
                prior = self.wire.raw
                repo = self.factory()
                self.assertEqual(self.wire.raw, prior)
                self.assertIsNone(repo.result_for('attempt:1'))
                self.assertEqual(self.wire.writes, 0)

    def test_validated_processed_creation_revision_preserved_never_synthesized(self):
        b, markers = sample('settled', finished=True)
        self.seed(b, markers)
        repo = self.factory()
        result = s._dto(b.records[-1][2], d.ResearchResult)
        self.assertEqual(repo.result_for('attempt:1'), result)
        self.assertEqual(repo.get(d.ref('result', result.result_id, result)), result)
        self.assertEqual(self.book().processed, b.processed)
        self.assertEqual(self.wire.writes, 0)
        self.db._product_generation = object()
        self.seed(replace(b, processed=()), ())
        with self.assertRaises(LedgerStorageError):
            self.factory()
        self.assertEqual(self.wire.writes, 0)

    def test_additional_same_generation_facade_does_not_cancel_live_reservation(self):
        repo = self.factory()
        self.reserve(repo)
        another = self.factory()
        self.assertEqual(another.attempt('attempt:1').state, 'reserved')
        self.assertEqual(self.wire.writes, 1)
        self.db._product_generation = object()
        reopened = self.factory()
        self.assertEqual(reopened.attempt('attempt:1').state, 'cancelled_before_dispatch')
        self.assertEqual(self.wire.writes, 2)
        for old in (repo, another):
            with self.assertRaises(LedgerStorageError):
                old.attempt('attempt:1')

    def test_exact_binding_and_ready_generation_checked_on_each_public_path(self):
        repo = self.factory()
        self.reserve(repo)
        original = self.db._product_database
        foreign = opened()._product_database
        self.db._product_database = foreign
        with self.assertRaises(LedgerStorageError):
            repo.attempt('attempt:1')
        self.db._product_database = original
        for attribute in ('active', 'lock', 'fd'):
            value = getattr(original, attribute)
            setattr(original, attribute, False if attribute == 'active' else None)
            with self.assertRaises(LedgerStorageError):
                repo.balance(policy())
            setattr(original, attribute, value)
        self.assertEqual(self.wire.writes, 1)

    def test_lost_commit_ack_exact_readback_success_without_write_replay(self):
        repo = self.factory()
        self.wire.mode = 'lost_ack'
        self.assertTrue(self.reserve(repo)[1])
        self.assertEqual(self.wire.writes, 1)
        repo.cancel('attempt:1', at=LATER)
        self.assertEqual(self.wire.writes, 2)
        self.assertFalse(self.reserve(repo)[1])
        self.assertEqual(self.wire.writes, 2)

    def test_unknown_commit_no_replay_shared_latch_and_new_generation_db_recovery(self):
        for mode in ('saved_unreadable', 'absent'):
            with self.subTest(mode=mode):
                self.db._product_generation = object()
                self.wire = MemoryWire()
                self.pipe_mock.return_value = self.wire
                a, b = self.factory(), self.factory()
                self.wire.mode = mode
                with self.assertRaises(LedgerStorageError):
                    self.reserve(a)
                self.assertEqual(self.wire.writes, 1)
                self.wire.mode = 'ok'
                with self.assertRaises(LedgerStorageError) as caught:
                    b.hypotheses()
                self.assertEqual(caught.exception.reason, 'product_ai_failed_latch')
                with self.assertRaises(LedgerStorageError):
                    self.factory()
                self.assertEqual(self.wire.writes, 1)
                self.db._product_generation = object()
                reopened = self.factory()
                if mode == 'saved_unreadable':
                    self.assertEqual(reopened.attempt('attempt:1').state, 'cancelled_before_dispatch')
                    self.assertEqual(self.wire.writes, 2)
                else:
                    self.assertEqual(reopened.hypotheses(), ())
                    self.assertEqual(self.wire.writes, 1)
                with self.assertRaises(LedgerStorageError):
                    a.hypotheses()

    def test_cas_collision_does_not_recompute_or_replay(self):
        repo = self.factory()
        original = self.wire.publish
        def collide(*args):
            self.wire.revision += 1
            return original(*args)
        with patch.object(self.wire, 'publish', side_effect=collide):
            with self.assertRaises(LedgerStorageError):
                self.reserve(repo)
        self.assertEqual(self.wire.writes, 1)
        self.assertTrue(repo._product_store._shared.failed)

    def test_all_unconnected_paths_block_before_any_client_or_source_access(self):
        repo = self.factory()
        source = Sources(repository=repo)
        client = Mock()
        with patch.object(Sources, 'validate', side_effect=AssertionError('source access')) as validate:
            calls = [lambda: repo.execute(request(), policy(), source, client, attempt_id='a', reserved=d.priced(1, 1), clock=lambda: NOW),
                lambda: repo.execute_review(request(), None, client, source),
                lambda: repo.execute_query(request(), None, source, at=NOW),
                lambda: repo.dispatch('a', at=NOW), lambda: repo.settle('a', None, at=NOW),
                lambda: repo.settle_unknown('a'), lambda: repo.finish('a', object()),
                lambda: repo.append('hypothesis', 'h', object()),
                lambda: repo.append('result', 'r', object()), lambda: repo.append('review', 'v', object())]
            for call in calls:
                with self.assertRaises(LedgerStorageError) as caught:
                    call()
                self.assertEqual(caught.exception.reason, 'product_ai_bridge_required')
            validate.assert_not_called()
        client.assert_not_called()
        client.invoke.assert_not_called()
        self.assertEqual(self.wire.writes, 0)
        self.assertEqual(repo.hypotheses(), ())

    def test_external_memory_repository_cannot_become_product_authority(self):
        repo = self.factory()
        external = SyntheticAIRepository()
        self.reserve(external)
        external._product_store = repo._product_store
        with self.assertRaises(LedgerStorageError):
            external.attempt('attempt:1')
        self.assertEqual(self.wire.writes, 0)
        self.assertIsNone(repo.get(d.ref('request', request().request_id, request())))

    def test_phase_identity_owner_generation_opcode_and_append_restrictions(self):
        repo = self.factory()
        store = repo._product_store
        with store._phase(s.Opcode.CANCEL, ('attempt:1', LATER, False)) as (phase, deadline):
            for fake in (replace(phase), replace(phase, owner=object()),
                         replace(phase, generation=object()), replace(phase, opcode=s.Opcode.FINISH_PROCESSED)):
                with self.assertRaises(LedgerStorageError):
                    store._commit(fake, phase.book, deadline)
        with store._phase(s.Opcode.APPEND) as (phase, deadline):
            b, _ = sample()
            with self.assertRaises(LedgerStorageError):
                store._commit(phase, b, deadline)
        self.assertEqual(self.wire.writes, 0)


if __name__ == '__main__':
    unittest.main()
