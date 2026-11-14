"""Synthetic command/pipe/codec evidence only; no PostgreSQL or Docker access."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

from quantharbor.adapters import product_ai as s
from quantharbor.adapters.postgres_ledger import LedgerStorageError, PostgresLedger
from quantharbor.adapters.product_database import ProductDatabase
from quantharbor.domain import investment_ai as d
from quantharbor.domain.primitives import ContractError

NOW = '2024-03-08T14:31:08Z'
LATER = '2024-03-08T14:31:09Z'


class ProcessedRevisionRegression(unittest.TestCase):
    def test_checkpoint_processed_revision_rejects_bool_matching_integer_marker(self):
        book, markers = sample('settled', finished=True)
        marker = replace(markers[0], revision=1)
        malformed = replace(book, processed=((marker.record_hash, marker.transition, True),))
        raw = s._json(s._wire(malformed))
        with self.assertRaises(LedgerStorageError):
            s._decode(raw, (marker,), 2)

    def test_processed_result_receipts_require_valid_time_and_resolved_source(self):
        book, _ = sample('settled', finished=True)
        external = d.AIRef('document', 'document:terminal', 1, d.CANONICAL, 'a'*64)
        r = request(source_refs=(external,))
        a = replace(s._dto(book.records[2][2], d.AIBudgetAttempt), request_ref=d.ref('request', r.request_id, r))
        origin = s._dto(book.records[3][2], d.ResearchResult)
        ah, rh = d.ref('attempt', a.attempt_id, a).sha256, a.request_ref.sha256
        for at, resolved in ((LATER, (external,)), (r.deadline, (external,)), (LATER, ()), ('2024-03-08T14:31:07Z', (external,))):
            with self.subTest(at=at, resolved=bool(resolved)):
                receipt = d.QueryReceipt(d.Query('document_view', external), resolved, at)
                result = replace(origin, request_ref=a.request_ref, budget_attempt_refs=(d.ref('attempt', a.attempt_id, a),), query_receipts=(receipt,))
                h = d.ref('result', result.result_id, result).sha256
                marker = s._Marker(h, 'result', 'finish_processed', 2)
                candidate = replace(book, records=(record('request', r), book.records[1], record('attempt', a), record('result', result)), payloads=((ah, rh, a.policy_ref.sha256, a.reserved_usage),), queries=((rh, 1),), processed=((h, marker.transition, 2),))
                raw = s._json(s._wire(candidate))
                if at == LATER and resolved:
                    self.assertEqual(s._decode(raw, (marker,), 2), candidate)
                else:
                    with self.assertRaises(LedgerStorageError):
                        s._decode(raw, (marker,), 2)


def policy(**changes):
    p = d.AIBudgetPolicy(1, 'synthetic', 'budget:1', 1, 'shared:1',
        '2024-01-01T00:00:00Z', '2025-01-01T00:00:00Z', 'synthetic_microcredit',
        'synthetic-unit-v1', 1, 2, 1, d.Usage(131072, 32768, 16, 196624),
        d.Usage(32768, 8192, 4, 49156), d.Usage(32768, 8192, 4, 49156),
        d.Usage(8192, 2048, 1, 12289), 2, d.RetryPolicy(0, (), 0, 0, ()))
    return replace(p, **changes)


def request(p=None, **changes):
    p = p or policy()
    r = d.ResearchRequest(1, 'synthetic', 'request:1', 'run:1', 'idem:1', 'risk',
        'ai_research', None, (), NOW, NOW, NOW, '2024-03-08T14:32:08Z', 'ko-KR', (), (),
        d.QUERIES, 'procedure:1', 'instructions:1', 'tools:1', 'synthetic',
        d.ref('budget_policy', p.policy_id, p), d.Usage(8192, 2048, 1, 12289), None, None)
    return replace(r, **changes)


def record(kind, obj):
    return kind, getattr(obj, s._IDS[kind]), d.encoded(obj)


def sample(state='reserved', *, finished=False):
    """Typed codec samples exist only in tests, never a production import seam."""
    p, r = policy(), request()
    a = d.AIBudgetAttempt(1, 'synthetic', 'attempt:1', d.ref('request', r.request_id, r),
        r.role, 1, 'synthetic', r.budget_policy_ref, d.priced(9, 20), state, NOW,
        NOW if state in ('dispatched', 'settled', 'unknown_charge') else None,
        LATER if state in ('settled', 'unknown_charge', 'cancelled_before_dispatch') else None,
        d.priced(9, 20) if state == 'settled' else None,
        ('unknown_charge',) if state == 'unknown_charge' else ())
    ah, rh, ph = (d.ref(k, getattr(o, s._IDS[k]), o).sha256 for k, o in (('attempt', a), ('request', r), ('budget_policy', p)))
    rows = (record('request', r), record('budget_policy', p), record('attempt', a))
    markers, processed = (), ()
    if finished:
        result = d.ResearchResult(1, 'synthetic', 'result:attempt:1', a.request_ref, (),
            d.ClientIdentity('invocation:1', 'synthetic', None), r.procedure_version,
            r.instruction_version, r.tool_schema_version, NOW, LATER, None, (),
            (d.ref('attempt', a.attempt_id, a),), (), 'failed', ('client_failure',), None)
        rows += (record('result', result),)
        h = d.ref('result', result.result_id, result).sha256
        markers = (s._Marker(h, 'result', 'finish_processed', 2),)
        processed = ((h, 'finish_processed', 2),)
    b = s._Book(records=rows, payloads=((ah, rh, ph, a.reserved_usage),), policies=(ph,),
        blocked=(ph,) if state == 'unknown_charge' else (),
        holds=() if finished or state == 'cancelled_before_dispatch' else (ah,), processed=processed)
    return b, markers


def opened():
    db = PostgresLedger()
    p = ProductDatabase('/private/tmp/qh-ai-command-double', 'synthetic:ai-double')
    p.active, p.lock, p.fd = True, 90, 91
    db._product_database, db._ready, db._compose = p, True, ['mock-psql']
    db._product_generation = object()
    return db


class MemoryWire:
    """Atomic CAS command-boundary double, with no production SQL evaluation."""
    def __init__(self):
        self.raw = None
        self.revision = 0
        self.operation_id = self.digest = self.opcode = None
        self.markers = ()
        self.mode = 'ok'
        self.writes = self.reads = 0
        self.bad = None
        self.deadlines = []

    def metadata(self, deadline):
        self.deadlines.append(deadline)
        self.reads += 1
        if self.mode == 'unreadable' or self.mode == 'saved_unreadable' and self.writes:
            raise LedgerStorageError('synthetic_read_failure')
        m = dict(codec=1, record_count=len(json.loads(self.raw)['records']) if self.raw else 0,
            chunk_count=(len(self.raw)+32767)//32768 if self.raw else 0, marker_count=len(self.markers), revision=self.revision, length=len(self.raw) if self.raw else 0,
            hash=sha256(self.raw).hexdigest() if self.raw else None,
            operation_id=self.operation_id, input_digest=self.digest, opcode=self.opcode,
            markers=[[x.record_hash, x.kind, x.transition, x.revision] for x in self.markers])
        if self.bad:
            self.bad(m)
        return s._json(m)

    def chunk(self, revision, digest, index, deadline):
        self.deadlines.append(deadline)
        return s._json([self.revision, sha256(self.raw).hexdigest(), index,
                        self.raw[index*s._CHUNK:(index+1)*s._CHUNK].hex()])

    def publish(self, revision, opcode, operation_id, digest, raw, record_count, markers, deadline):
        self.deadlines.append(deadline)
        self.writes += 1
        if revision != self.revision:
            raise LedgerStorageError('ai_stale_revision')
        if self.mode != 'absent':
            self.raw, self.revision = raw, revision+1
            self.operation_id, self.digest, self.opcode = operation_id, digest, opcode.value
        if self.mode in ('lost_ack', 'saved_unreadable', 'absent'):
            raise LedgerStorageError('pipe_lost')
        return ('ai_ack:' + operation_id + ':' + str(revision+1) + ':' + sha256(raw).hexdigest()).encode()


class CodecTests(unittest.TestCase):
    def decode(self, book, markers=(), revision=3):
        return s._decode(s._json(s._wire(book)), markers, revision)

    def reject_wire(self, book, mutate, markers=()):
        wire = s._wire(book)
        mutate(wire)
        with self.assertRaises(LedgerStorageError):
            s._decode(s._json(wire), markers, 3)

    def test_fresh_empty_closed_book_roundtrip(self):
        self.assertEqual(self.decode(s._Book()), s._Book())

    def test_all_five_attempt_states_and_payload_usage_roundtrip(self):
        for state in ('reserved', 'dispatched', 'settled', 'unknown_charge', 'cancelled_before_dispatch'):
            b, m = sample(state)
            self.assertEqual(self.decode(b, m), b)

    def test_processed_requires_exact_server_marker_and_creation_binding(self):
        b, m = sample('settled', finished=True)
        self.assertEqual(self.decode(b, m), b)
        for wrong in ((), (replace(m[0], record_hash='0'*64),),
                (replace(m[0], transition='review_processed'),), (replace(m[0], revision=1),),
                (replace(m[0], revision=4),), (replace(m[0], kind='review'),), (m[0], m[0])):
            with self.subTest(marker=wrong), self.assertRaises(LedgerStorageError):
                self.decode(b, wrong)

    def test_result_only_and_orphan_marker_rejected(self):
        b, m = sample('settled', finished=True)
        with self.assertRaises(LedgerStorageError):
            self.decode(replace(b, processed=()))
        with self.assertRaises(LedgerStorageError):
            self.decode(s._Book(), m)

    def test_unknown_fields_version_bool_and_duplicate_json(self):
        b, _ = sample()
        for key, value in (('future', []), ('version', True), ('version', 2), ('version', 0)):
            self.reject_wire(b, lambda w: w.__setitem__(key, value))
        raw = s._json(s._wire(b))
        with self.assertRaises(LedgerStorageError):
            s._decode(b'{"version":1,' + raw[1:], (), 3)

    def test_noncanonical_outer_and_raw_dto_rejected(self):
        b, _ = sample()
        with self.assertRaises(LedgerStorageError):
            s._decode(s._json(s._wire(b)) + b' ', (), 3)
        self.reject_wire(b, lambda w: w['records'][0].__setitem__(2, s._b64(b.records[0][2]+b' ')))

    def test_closed_dto_kind_identity_hash_and_duplicate_records(self):
        b, _ = sample()
        for field, value in ((0, 'client'), (0, 'result'), (1, 'wrong-id'), (2, s._b64(b'{}'))):
            self.reject_wire(b, lambda w: w['records'][0].__setitem__(field, value))
        self.reject_wire(b, lambda w: w['records'].append(w['records'][0]))
        self.reject_wire(b, lambda w: w['payloads'][0].__setitem__(1, '0'*64))
        self.reject_wire(b, lambda w: w['payloads'][0].__setitem__(3, [True, 20, 1, 50]))

    def test_payload_missing_usage_mismatch_and_unbound_policy_rejected(self):
        b, _ = sample()
        for key, value in (('payloads', []), ('policies', []), ('holds', []), ('blocked', ['0'*64])):
            self.reject_wire(b, lambda w: w.__setitem__(key, value))
        self.reject_wire(b, lambda w: w['payloads'][0].__setitem__(3, [9, 20, 1, 999]))

    def test_runtime_objects_cannot_be_serialized_or_imported(self):
        for value in (object(), {}, PostgresLedger()):
            with self.assertRaises(ContractError):
                s._wire(value)
        self.assertFalse(hasattr(s.ProductAIStore, 'restore'))
        self.assertFalse(hasattr(s.ProductAIStore, 'from_repository'))

    def test_raw_base64_is_preserved_and_ambiguous_encoding_rejected(self):
        b = s._Book(records=(record('request', request()),))
        decoded = self.decode(b)
        self.assertEqual(decoded.records[0][2], b.records[0][2])
        self.reject_wire(b, lambda w: w['records'][0].__setitem__(2, w['records'][0][2]+'\n'))

    def test_historical_source_refs_need_no_current_resolver(self):
        external = d.AIRef('document', 'external:1', 1, d.CANONICAL, 'a'*64)
        b = s._Book(records=(record('request', request(source_refs=(external,))),))
        self.assertEqual(self.decode(b), b)
        self.assertNotIn('sources', s._wire(b))

    def test_query_count_bounds_exact_int_and_duplicate_rejected(self):
        r = request()
        h = d.ref('request', r.request_id, r).sha256
        b = s._Book(records=(record('request', r),), queries=((h, 16),))
        self.assertEqual(self.decode(b), b)
        for n in (-1, True, 17, 1.5):
            self.reject_wire(b, lambda w: w['queries'][0].__setitem__(1, n))
        self.reject_wire(b, lambda w: w['queries'].append(w['queries'][0]))

    def test_denials_closed_reasons_and_attempt_binding(self):
        b, _ = sample('dispatched')
        ah = b.payloads[0][0]
        b = replace(b, denials=((ah, ('query_denied', 'capacity')),))
        self.assertEqual(self.decode(b), b)
        self.reject_wire(b, lambda w: w['denials'][0][1].append('unknown-new-reason'))
        self.reject_wire(b, lambda w: w['denials'][0][1].append('capacity'))

    def test_receipts_roundtrip_binding_and_32k_cap(self):
        external = d.AIRef('document', 'document:1', 1, d.CANONICAL, 'a'*64)
        p = policy()
        r = request(source_refs=(external,))
        a = d.AIBudgetAttempt(1, 'synthetic', 'attempt:1', d.ref('request', r.request_id, r),
            'risk', 1, 'synthetic', r.budget_policy_ref, d.priced(9, 20), 'dispatched', NOW, NOW, None, None, ())
        ah = d.ref('attempt', a.attempt_id, a).sha256
        rh = a.request_ref.sha256
        ph = r.budget_policy_ref.sha256
        receipt = d.QueryReceipt(d.Query('document_view', external), (external,), LATER)
        b = s._Book(records=(record('request', r), record('budget_policy', p), record('attempt', a)),
            payloads=((ah, rh, ph, a.reserved_usage),), policies=(ph,), holds=(ah,),
            queries=((rh, 1),), receipts=((ah, (receipt,)),))
        self.assertEqual(self.decode(b), b)
        with self.assertRaises(LedgerStorageError):
            self.decode(replace(b, queries=()))
        many = tuple(d.AIRef('document', 'x'*120+str(n), 1, d.CANONICAL, 'b'*64) for n in range(128))
        large = replace(receipt, resolved_refs=(external, *many[:127]))
        with self.assertRaises(LedgerStorageError):
            self.decode(replace(b, queries=((rh, 16),), receipts=((ah, (large, large)),)))

    def test_quota_current_and_reserved_closing_records_bytes_no_eviction(self):
        b, _ = sample()
        raw = s._json(s._wire(b))
        for kw in ({'capacity': 5}, {'byte_capacity': 196608}, {'capacity': True}):
            with self.assertRaises(LedgerStorageError):
                s._decode(raw, (), 1, **kw)
        self.assertEqual(self.decode(b).holds, b.holds)

    def test_auxiliary_fixed_global_and_slot_future_bound(self):
        b, _ = sample()
        used, worst = s._quota(b, ())
        self.assertEqual(used, 1048576+131072)
        self.assertLess(worst, 33554432)
        ah = b.payloads[0][0]
        changed = replace(b, denials=((ah, ('capacity',)),))
        self.assertEqual(s._quota(changed, ())[0], used)
        with patch.object(s, '_SLOT', 1), self.assertRaises(ContractError):
            s._quota(changed, ())

    def test_encoded_cap_and_record_cap_checked_before_decode(self):
        with self.assertRaises(LedgerStorageError):
            s._decode(b'x'*(33554432+1), (), 1)
        b = s._Book(records=tuple(record('request', request(request_id='r:'+str(i))) for i in range(128)))
        self.assertEqual(len(self.decode(b).records), 128)
        self.reject_wire(b, lambda w: w['records'].append(w['records'][0]))

    def test_review_codec_has_exact_request_result_and_distinct_invocation(self):
        b, markers = sample('settled', finished=True)
        origin = s._dto(b.records[-1][2], d.ResearchResult)
        rr = d.ref('result', origin.result_id, origin)
        r = request(request_id='review-request:1', review_subject_ref=rr)
        review = d.ResearchReview(1, 'synthetic', 'review:1', d.ref('request', r.request_id, r), rr,
            d.ClientIdentity('reviewer:2', 'synthetic', None), LATER, (), (),
            ('client_failure',), 'blocked', None)
        h = d.ref('review', review.review_id, review).sha256
        m = s._Marker(h, 'review', 'review_processed', 3)
        book = replace(b, records=(*b.records, record('request', r), record('review', review)),
            processed=(*b.processed, (h, 'review_processed', 3)))
        self.assertEqual(self.decode(book, (*markers, m)), book)
        wrong = replace(review, reviewer_identity=origin.client_identity)
        wrong_h = d.ref('review', wrong.review_id, wrong).sha256
        forged = replace(book, records=(*book.records[:-1], record('review', wrong)),
            processed=(*b.processed, (wrong_h, 'review_processed', 3)))
        with self.assertRaises(LedgerStorageError):
            self.decode(forged, (*markers, replace(m, record_hash=wrong_h)))

    def test_hypothesis_closed_historical_dependencies_and_predecessor(self):
        b, _ = sample('settled', finished=True)
        origin = s._dto(b.records[-1][2], d.ResearchResult)
        external = d.AIRef('document', 'document:1', 1, d.CANONICAL, 'a'*64)
        origin = replace(origin, input_manifest=(external,), status='partial', reasons=('missing_source',))
        rr = d.ref('result', origin.result_id, origin)
        h = d.Hypothesis(1, 'synthetic', 'hypothesis:1', rr, 'historical proposition', (), (), (),
            'refutable condition', None, (external,), LATER, '2024-03-09T14:31:09Z', 'proposed', None, None)
        marker = s._Marker(rr.sha256, 'result', 'finish_processed', 2)
        book = replace(b, records=(*b.records[:-1], record('result', origin), record('hypothesis', h)),
            processed=((rr.sha256, 'finish_processed', 2),))
        self.assertEqual(self.decode(book, (marker,)), book)
        other = replace(external, id='wrong-dependency')
        invalid = replace(h, dependencies=(other,))
        with self.assertRaises(LedgerStorageError):
            self.decode(replace(book, records=(*book.records[:-1], record('hypothesis', invalid))), (marker,))

    def test_duplicate_keys_inside_raw_record_and_wrong_raw_version(self):
        b, _ = sample()
        raw = b.records[0][2]
        duplicate = b'{"schema_version":1,' + raw[1:]
        self.reject_wire(b, lambda w: w['records'][0].__setitem__(2, s._b64(duplicate)))
        data = json.loads(raw)
        data['schema_version'] = True
        self.reject_wire(b, lambda w: w['records'][0].__setitem__(2, s._b64(s._json(data))))

    def test_attempt_sequence_gap_and_missing_terminal_block_are_rejected(self):
        b, _ = sample('unknown_charge')
        self.reject_wire(b, lambda w: w.__setitem__('blocked', []))
        a = s._dto(b.records[2][2], d.AIBudgetAttempt)
        a = replace(a, sequence=2)
        ah = d.ref('attempt', a.attempt_id, a).sha256
        book = replace(b, records=(*b.records[:2], record('attempt', a)), holds=(ah,),
            payloads=((ah, *b.payloads[0][1:]),))
        with self.assertRaises(LedgerStorageError):
            self.decode(book)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.db, self.wire = opened(), MemoryWire()
        self.schema = patch.object(s, 'ensure_schema')
        self.pipe = patch.object(s, '_Pipe', return_value=self.wire)
        self.schema.start()
        self.pipe.start()
        self.addCleanup(self.schema.stop)
        self.addCleanup(self.pipe.stop)

    def store(self, **kw):
        return s.ProductAIStore.product_synthetic(self.db, **kw)

    def test_whole_operation_deadline_bounds_gate_wait(self):
        st = self.store()
        held, release = threading.Event(), threading.Event()
        def holder():
            with self.db._product_gate:
                held.set()
                release.wait(0.3)
        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(held.wait(1))
        start = time.monotonic()
        try:
            with patch.object(s, '_DEADLINE', 0.03), self.assertRaises(LedgerStorageError) as caught:
                st.read_records()
            self.assertEqual(caught.exception.reason, 'product_ai_timeout')
            self.assertLess(time.monotonic()-start, 0.2)
        finally:
            release.set()
            thread.join(1)

    def test_whole_operation_deadline_checked_after_final_decode(self):
        st = self.store()
        st.append('request', request(), expected_revision=0)
        decode = s._decode
        def slow_decode(*args, **kwargs):
            time.sleep(0.04)
            return decode(*args, **kwargs)
        with patch.object(s, '_DEADLINE', 0.02), patch.object(s, '_decode', side_effect=slow_decode), self.assertRaises(LedgerStorageError) as caught:
            st.read_records()
        self.assertEqual(caught.exception.reason, 'product_ai_timeout')

    def test_factory_schema_uses_remaining_operation_deadline(self):
        with patch.object(s, '_DEADLINE', 0.02), patch.object(s, 'ensure_schema', side_effect=lambda *a, **k: time.sleep(0.04)), self.assertRaises(LedgerStorageError) as caught:
            self.store()
        self.assertEqual(caught.exception.reason, 'product_ai_timeout')
        self.assertEqual(self.wire.reads, 0)

    def test_explicit_factory_io_and_constructor_no_io(self):
        instance = s.ProductAIStore(self.db)
        self.assertEqual(self.wire.reads, 0)
        with self.assertRaises(LedgerStorageError):
            instance.read_records()
        self.assertEqual(self.store().read_records(), (0, ()))

    def test_exact_type_disposable_foreign_and_unready_rejected(self):
        class Foreign(PostgresLedger):
            pass
        for db in (object(), Foreign(), PostgresLedger()):
            with self.assertRaises((ContractError, LedgerStorageError)):
                s.ProductAIStore.product_synthetic(db)
        for attr, value in (('_ready', False), ('_product_generation', None), ('_compose', None)):
            prior = getattr(self.db, attr)
            setattr(self.db, attr, value)
            with self.assertRaises(LedgerStorageError):
                self.store()
            setattr(self.db, attr, prior)

    def test_active_private_binding_lock_fd_checked_every_phase(self):
        st = self.store()
        p = self.db._product_database
        for attr, value in (('active', False), ('lock', None), ('fd', None)):
            old = getattr(p, attr)
            setattr(p, attr, value)
            with self.assertRaises(LedgerStorageError):
                st.read_records()
            setattr(p, attr, old)

    def test_close_and_reopen_reject_old_generation(self):
        st = self.store()
        self.db._ready = False
        with self.assertRaises(LedgerStorageError):
            st.append('request', request(), expected_revision=0)
        self.db._ready = True
        self.db._product_generation = object()
        with self.assertRaises(LedgerStorageError):
            st.read_records()
        self.assertEqual(self.store().read_records(), (0, ()))

    def test_shared_book_revision_and_no_eviction_lower_capacity(self):
        a, b = self.store(), self.store(capacity=1)
        self.assertIs(a._shared, b._shared)
        self.assertEqual(a.append('request', request(), expected_revision=0), 1)
        self.assertEqual(b.read_records(), a.read_records())
        with self.assertRaises(ContractError):
            b.append('budget_policy', policy(), expected_revision=1)
        self.assertEqual(len(a.read_records()[1]), 1)
        self.assertEqual(self.wire.writes, 1)

    def test_same_value_idempotent_different_value_conflicts(self):
        st = self.store()
        st.append('request', request(), expected_revision=0)
        self.assertEqual(st.append('request', request(), expected_revision=1), 1)
        with self.assertRaises(ContractError):
            st.append('request', request(run_id='different'), expected_revision=1)
        self.assertEqual(self.wire.writes, 1)

    def test_stale_cas_has_no_recompute_or_replay(self):
        st = self.store()
        st.append('request', request(), expected_revision=0)
        with self.assertRaises(LedgerStorageError) as caught:
            st.append('budget_policy', policy(), expected_revision=0)
        self.assertEqual(caught.exception.reason, 'product_ai_stale_revision')
        self.assertEqual(self.wire.writes, 1)
        self.assertEqual(st.read_records()[0], 1)

    def test_lost_ack_exact_readback_confirms_once_and_same_deadline(self):
        st = self.store()
        self.wire.mode = 'lost_ack'
        self.wire.deadlines.clear()
        self.assertEqual(st.append('request', request(), expected_revision=0), 1)
        self.assertEqual(self.wire.writes, 1)
        self.assertEqual(len(set(self.wire.deadlines)), 1)

    def test_readback_checks_exact_operation_id_digest_opcode_and_checkpoint(self):
        for key, value in (('operation_id', 'c'*32), ('input_digest', 'd'*64),
                ('opcode', 'settle'), ('hash', 'e'*64)):
            self.db._product_generation = object()
            wire = MemoryWire()
            with patch.object(s, '_Pipe', return_value=wire):
                st = self.store()
                wire.bad = lambda meta: meta.__setitem__(key, value) if wire.writes else None
                with self.subTest(field=key), self.assertRaises(LedgerStorageError):
                    st.append('request', request(), expected_revision=0)
                self.assertTrue(st._shared.failed)
                self.assertEqual(wire.writes, 1)

    def test_readback_rejects_changed_payload_with_same_length(self):
        st = self.store()
        st.append('request', request(), expected_revision=0)
        good = self.wire.chunk
        def corrupt(*args):
            row = json.loads(good(*args))
            row[3] = ('00' if row[3][:2] != '00' else '01') + row[3][2:]
            return s._json(row)
        with patch.object(self.wire, 'chunk', side_effect=corrupt), self.assertRaises(LedgerStorageError):
            st._read(time.monotonic()+1)

    def test_absent_commit_latches_all_facades_without_retry(self):
        a, b = self.store(), self.store()
        self.wire.mode = 'absent'
        with self.assertRaises(LedgerStorageError) as caught:
            a.append('request', request(), expected_revision=0)
        self.assertEqual(caught.exception.reason, 'product_ai_commit_unknown')
        for st in (a, b):
            with self.assertRaises(LedgerStorageError) as caught:
                st.read_records()
            self.assertEqual(caught.exception.reason, 'product_ai_failed_latch')
        self.assertEqual(self.wire.writes, 1)

    def test_commit_confirmation_failure_is_generation_shared(self):
        a = self.store()
        self.wire.mode = 'saved_unreadable'
        with self.assertRaises(LedgerStorageError):
            a.append('request', request(), expected_revision=0)
        self.wire.mode = 'ok'
        with self.assertRaises(LedgerStorageError):
            self.store()
        self.db._product_generation = object()
        self.assertEqual(self.store().read_records()[0], 1)

    def test_append_cannot_generate_processed_marker_or_import_book(self):
        st = self.store()
        b, _ = sample('settled', finished=True)
        obj = s._dto(b.records[-1][2], d.ResearchResult)
        for kind, value in (('result', obj), ('request', {}), ('attempt', object()), ('book', b)):
            with self.assertRaises(ContractError):
                st.append(kind, value, expected_revision=0)
        self.assertEqual(self.wire.writes, 0)

    def test_foreign_or_serialized_phase_owner_rejected(self):
        a, b = self.store(), self.store()
        phase = s._Phase(a, a._owner, a._generation, s.Opcode.APPEND, 'a'*32, 'b'*64, 0, s._Book(), ())
        proposed = s._Book(records=(record('request', request()),))
        for wrong in ({}, replace(phase, store=b), replace(phase, owner=object()),
                replace(phase, generation=object()), replace(phase, opcode=s.Opcode.FINISH_PROCESSED)):
            with self.assertRaises(LedgerStorageError):
                a._commit(wrong, proposed, time.monotonic()+1)
        self.assertEqual(self.wire.writes, 0)

    def test_append_phase_cannot_change_holds_queries_or_processed(self):
        st = self.store()
        phase = s._Phase(st, st._owner, st._generation, s.Opcode.APPEND, 'a'*32, 'b'*64, 0, s._Book(), ())
        b = s._Book(records=(record('request', request()),), holds=('a'*64,))
        with self.assertRaises(LedgerStorageError):
            st._commit(phase, b, time.monotonic()+1)
        self.assertEqual(self.wire.writes, 0)

    def test_metadata_length_revision_hash_and_count_bounds_before_chunk(self):
        for key, value in (('length', 33554433), ('revision', True), ('revision', -1), ('markers', [[]]*129), ('record_count', 129), ('record_count', True), ('chunk_count', 1), ('codec', 2), ('future', 1)):
            wire = MemoryWire()
            wire.bad = lambda m: m.__setitem__(key, value)
            with patch.object(s, '_Pipe', return_value=wire), self.assertRaises(LedgerStorageError):
                self.store()
            self.db._product_generation = object()

    def test_chunk_changed_revision_hash_order_repeated_partial_eof_rejected(self):
        st = self.store()
        st.append('request', request(), expected_revision=0)
        good = self.wire.chunk
        for field, value in ((0, 2), (1, '0'*64), (2, 1), (3, ''), (3, '00'), (0, True)):
            def corrupt(*args):
                row = json.loads(good(*args))
                row[field] = value
                return s._json(row)
            with patch.object(self.wire, 'chunk', side_effect=corrupt), self.assertRaises(LedgerStorageError):
                st._read(time.monotonic()+1)

    def test_multi_chunk_reassembly_total_hash_and_no_silent_truncation(self):
        b = s._Book(records=tuple(record('request', request(request_id='r:'+str(i))) for i in range(32)))
        self.wire.raw = s._json(s._wire(b))
        self.assertGreater(len(self.wire.raw), 32768)
        self.wire.revision, self.wire.operation_id = 1, 'a'*32
        self.wire.digest, self.wire.opcode = 'b'*64, 'append'
        st = self.store()
        self.assertEqual(len(st.read_records()[1]), 32)
        good = self.wire.chunk
        def repeat(revision, digest, index, deadline):
            return good(revision, digest, 0, deadline)
        with patch.object(self.wire, 'chunk', side_effect=repeat), self.assertRaises(LedgerStorageError):
            st._read(time.monotonic()+1)

    def test_concurrent_facades_one_expected_revision_wins(self):
        a, b = self.store(), self.store()
        barrier, outcomes = threading.Barrier(2), []
        def write(st, obj):
            barrier.wait(2)
            try:
                outcomes.append(st.append('request', obj, expected_revision=0))
            except LedgerStorageError as e:
                outcomes.append(e.reason)
        threads = [threading.Thread(target=write, args=(st, request(request_id='r:'+str(i)))) for i, st in enumerate((a,b))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(3)
        self.assertCountEqual(outcomes, (1, 'product_ai_stale_revision'))
        self.assertEqual(self.wire.writes, 1)

    def test_smaller_facade_can_read_shared_data_without_poisoning_generation(self):
        st = self.store()
        st.append('request', request(), expected_revision=0)
        st.append('budget_policy', policy(), expected_revision=1)
        lower = self.store(capacity=1)
        self.assertEqual(len(lower.read_records()[1]), 2)
        self.assertFalse(st._shared.failed)
        with self.assertRaises(ContractError):
            lower.append('request', request(request_id='request:2'), expected_revision=2)
        self.assertEqual(len(st.read_records()[1]), 2)

    def test_forged_exact_phase_copy_cannot_be_committed(self):
        st = self.store()
        phase = s._Phase(st, st._owner, st._generation, s.Opcode.APPEND, 'a'*32, 'b'*64, 0, s._Book(), ())
        st._active_phase = phase
        with self.assertRaises(LedgerStorageError):
            st._commit(replace(phase), s._Book(records=(record('request', request()),)), time.monotonic()+1)
        self.assertEqual(self.wire.writes, 0)
        st._active_phase = None

    def test_new_factory_checks_latch_before_any_schema_or_data_io(self):
        self.store()._shared.failed = True
        with patch.object(s, 'ensure_schema') as schema:
            before = self.wire.reads
            with self.assertRaises(LedgerStorageError):
                self.store()
            schema.assert_not_called()
            self.assertEqual(self.wire.reads, before)

    def test_close_waits_for_sql_phase_and_invalidates_old_store(self):
        st = self.store()
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()
        original = self.wire.publish
        failures = []
        def publish(*args):
            entered.set()
            if not release.wait(2):
                raise AssertionError('test did not release writer')
            return original(*args)
        def write():
            try:
                st.append('request', request(), expected_revision=0)
            except BaseException as e:
                failures.append(type(e).__name__)
        def close():
            self.db.close()
            closed.set()
        def fake_close(p, db):
            p.active, db._ready = False, False
        with patch.object(self.wire, 'publish', side_effect=publish), patch.object(ProductDatabase, 'close', fake_close):
            writer = threading.Thread(target=write)
            writer.start()
            self.assertTrue(entered.wait(2))
            closer = threading.Thread(target=close)
            closer.start()
            self.assertFalse(closed.wait(0.02))
            release.set()
            writer.join(3)
            closer.join(3)
        self.assertEqual(failures, [])
        self.assertTrue(closed.is_set())
        with self.assertRaises(LedgerStorageError):
            st.read_records()


class SchemaRegistryTests(unittest.TestCase):
    def test_v1_bytes_pin_and_function_guards_precede_atomic_upgrade(self):
        from quantharbor.adapters import product_schema as registry
        from quantharbor.adapters.postgres_ledger import ROOT, _text
        first = (ROOT / 'migrations/product/0001_artifacts.sql').read_bytes()
        second = (ROOT / 'migrations/product/0002_ai.sql').read_bytes()
        self.assertEqual(sha256(first).hexdigest(), registry.V1_SHA)
        self.assertEqual(sha256(second).hexdigest(), registry.V2_SHA)
        db = PostgresLedger()
        with patch.object(db, '_query') as execute:
            registry.ensure_schema(db)
        self.assertEqual(execute.call_count, 1)
        sql = execute.call_args.args[0]
        self.assertTrue(sql.startswith('BEGIN;'))
        self.assertTrue(sql.endswith('COMMIT;'))
        self.assertLess(sql.index('END $guard$'), sql.index(second.decode()))
        self.assertIn('p.prosrc='+_text(first.decode().split('$fn$')[1]), sql)
        for tag in ('meta', 'chunk', 'publish'):
            self.assertIn('p.prosrc='+_text(second.decode().split('$'+tag+'$')[1]), sql)
        # This verifies the generated guard, not actual PostgreSQL rollback.

    def test_modified_local_migration_rejected_before_database_io(self):
        from quantharbor.adapters import product_schema as registry
        original = Path.read_bytes
        for filename in ('0001_artifacts.sql', '0002_ai.sql'):
            def read(path):
                body = original(path)
                return body+b'-- altered' if path.name == filename else body
            db = PostgresLedger()
            with patch.object(Path, 'read_bytes', read), patch.object(db, '_query') as query:
                with self.assertRaises(LedgerStorageError):
                    registry.ensure_schema(db)
                query.assert_not_called()


class PipeTests(unittest.TestCase):
    def pipe(self, script):
        db = PostgresLedger()
        db._psql = lambda: [sys.executable, '-I', '-S', '-B', '-c', script]
        return s._Pipe(db)

    def test_real_pipe_partial_writes_reads_and_eof(self):
        p = self.pipe("import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(str(len(data)).encode())")
        self.assertEqual(p._exchange((b'a'*32768 for _ in range(5)), time.monotonic()+2), b'163840')

    def test_real_pipe_response_hard_cap(self):
        p = self.pipe("import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write(b'a'*300000)")
        with self.assertRaises(LedgerStorageError) as caught:
            p._exchange((b'input',), time.monotonic()+2)
        self.assertEqual(caught.exception.reason, 'product_ai_response_capacity')

    def test_real_pipe_stderr_is_bounded_and_never_reflected(self):
        p = self.pipe("import sys; sys.stdin.buffer.read(); sys.stderr.buffer.write(b'private-synthetic'*30000)")
        with self.assertRaises(LedgerStorageError) as caught:
            p._exchange((b'input',), time.monotonic()+2)
        self.assertNotIn('private-synthetic', str(caught.exception))
        self.assertEqual(caught.exception.reason, 'product_ai_response_capacity')

    def test_real_pipe_deadline_hard_cap(self):
        p = self.pipe('import time; time.sleep(5)')
        start = time.monotonic()
        with self.assertRaises(LedgerStorageError) as caught:
            p._exchange((b'input',), start+0.05)
        self.assertEqual(caught.exception.reason, 'product_ai_timeout')
        self.assertLess(time.monotonic()-start, 1.5)

    def test_expired_deadline_starts_no_process(self):
        p = self.pipe('raise AssertionError()')
        with patch.object(s.subprocess, 'Popen') as create, self.assertRaises(LedgerStorageError):
            p._exchange((), time.monotonic()-1)
        create.assert_not_called()

    def test_nonzero_exit_and_early_pipe_close_are_failures(self):
        for script in ('raise SystemExit(2)', 'import os; os.close(0); raise SystemExit(1)'):
            p = self.pipe(script)
            with self.assertRaises(LedgerStorageError):
                p._exchange((b'input'*10000,), time.monotonic()+2)

    def test_oversize_input_fragment_is_rejected(self):
        p = self.pipe('import sys; sys.stdin.buffer.read()')
        with self.assertRaises(LedgerStorageError):
            p._exchange((b'x'*70000,), time.monotonic()+2)

    def test_processed_publish_fails_closed_until_core_proof_bridge(self):
        p = self.pipe('raise AssertionError()')
        for opcode in (s.Opcode.DISPATCH, s.Opcode.FINISH_PROCESSED, s.Opcode.REVIEW_PROCESSED):
            with self.assertRaises(LedgerStorageError) as caught:
                p.publish(0, opcode, 'a'*32, 'b'*64, b'{}', 0, (), time.monotonic()+1)
            self.assertEqual(caught.exception.reason, 'product_ai_bridge_required')


if __name__ == '__main__':
    unittest.main()
