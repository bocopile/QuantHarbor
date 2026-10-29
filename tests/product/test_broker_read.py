from dataclasses import replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from quantharbor.adapters.kis_read import WirePlan
from quantharbor.adapters.synthetic_broker import FixtureTransport
from quantharbor.application.broker_read import connection_readiness, read_broker
from quantharbor.domain.broker_read import BrokerCursor, SourceNumber
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, canonical_hash, parse_payload
from quantharbor.ports.broker_read import FixtureAccountIdentity
from synthetic_broker import DEADLINE, NOW, binding, body, capability, holding, order, page, request, run

OPS = ('kr_balance', 'kr_orders', 'kr_buy_capacity', 'us_balance', 'us_orders', 'us_present_balance')


class BrokerReadTests(unittest.TestCase):
    def test_six_operations_success_exact_scope_and_source_only(self):
        for op in OPS:
            with self.subTest(op=op):
                req = request(op)
                batch = run(req=req)
                self.assertEqual((batch.result.status, batch.result.complete), ('success', True))
                self.assertEqual(batch.result.queried_scope, req.scope)
                self.assertIsNone(batch.result.source_as_of)
                self.assertEqual(batch.result.temporal_consistency, 'bounded_observation')
                self.assertTrue(all(not x.usable_for_internal_available_cash and x.instrument_id is None for x in batch.result.items))
                for item in batch.result.items:
                    if item.kind == 'order_cumulative':
                        self.assertEqual(item.execution_granularity, 'order_cumulative')
                        self.assertIsNone(item.individual_execution_id)

    def test_empty_scope_results_do_not_invent_zero_capacity(self):
        for op in OPS:
            req = request(op)
            batch = run((page(req, data=body(op, empty=True)),), req=req)
            with self.subTest(op=op):
                self.assertEqual(batch.result.complete, op != 'kr_buy_capacity')
                if op == 'kr_buy_capacity':
                    self.assertIn('missing_fact', batch.reason_codes)
                    self.assertTrue(all(n.value is None for n in batch.result.items[0].numbers))
                elif op != 'kr_orders':
                    self.assertEqual(batch.result.items, ())
                else:
                    self.assertFalse(any(i.kind == 'order_cumulative' for i in batch.result.items))

    def test_unsupported_and_unconfirmed_never_fetch(self):
        with patch.object(FixtureTransport, 'fetch', side_effect=AssertionError('must not fetch')):
            for op in ('kr_amendable_orders', 'us_open_orders', 'us_settlement_balance', 'individual_executions'):
                batch = run((), req=request(op))
                self.assertEqual((batch.result.status, batch.result.pages_fetched), ('unsupported', 0))
            for op in OPS:
                req = request(op)
                batch = run((), req=req, cap=capability(req, support='unconfirmed'))
                self.assertEqual(batch.result.status, 'unsupported')

    def test_cross_binding_version_scope_expiry_and_time_rejected_before_fetch(self):
        req = request('us_balance')
        caps = [capability(req, binding=replace(req.binding, account_ref='synthetic-account:other')),
                capability(req, binding=replace(req.binding, capability_version='capability-v2')),
                capability(req, binding=replace(req.binding, catalog_version='catalog-v2')),
                capability(req, scope=replace(req.scope, exchange='NYSE')),
                capability(req, expires_at='2026-10-24T00:00:05Z'),
                capability(req, valid_from='2026-10-24T00:00:01Z')]
        with patch.object(FixtureTransport, 'fetch', side_effect=AssertionError('must not fetch')):
            for cap in caps:
                with self.assertRaises(ContractError):
                    run((), req=req, cap=cap)
            for now in ('2026-10-23T23:59:59Z', '2026-10-24T00:00:31Z', '2026-10-24T00:00:00'):
                with self.assertRaises(ContractError):
                    run((), req=req, now=now)

    def test_environment_version_types_irrelevant_filters_and_forged_objects_rejected(self):
        req = request()
        for obj, changes in ((req, {'environment': 'paper'}), (req, {'schema_version': True}),
                              (req.binding, {'wire_profile': 'live'}),
                              (req.binding, {'endpoint_registry_version': 'other'}),
                              (capability(), {'max_pages': True}), (capability(), {'max_rows': 33}),
                              (req, {'scope': replace(req.scope, symbol='EXTRA')})):
            with self.assertRaises(ContractError):
                replace(obj, **changes)
        forged = replace(req)
        object.__setattr__(forged, 'environment', 'paper')
        with self.assertRaises(ContractError):
            run((), req=forged)
        for field, value in (('raw_body', 'not-bytes'), ('expected_identity', object())):
            forged_page = page()
            object.__setattr__(forged_page, field, value)
            with self.assertRaises(ContractError):
                FixtureTransport((forged_page,))

    def test_only_fixed_transport_and_readiness_never_enables_real_connection(self):
        class FakeTransport:
            def fetch(self, *args):
                raise AssertionError('must not call')
        with self.assertRaises(ContractError):
            read_broker(request(), capability(), FakeTransport(), evaluated_at=NOW)
        report = connection_readiness(binding(), checked_at=NOW)
        self.assertEqual(report.target_environment, 'paper')
        self.assertTrue({'PG01', 'SG01', 'SG02', 'AP05'} <= set(report.missing_requirements))
        self.assertFalse(report.connectable or report.real_transport_available)
        for changes in ({'connectable': True}, {'real_transport_available': True}, {'missing_requirements': ()}):
            with self.assertRaises(ContractError):
                replace(report, **changes)

    def test_two_pages_then_error_or_absence_preserves_first_observations(self):
        c = BrokerCursor('cursor-f', 'cursor-n')
        first = page(marker='M', terminal=False, out=c)
        failed = page(index=1, cursor=c, data={'rt_cd': '1', 'msg1': 'untrusted-payload-canary'})
        for pages in ((first, failed), (first,)):
            batch = run(pages)
            self.assertEqual(batch.result.status, 'partial')
            self.assertFalse(batch.result.complete)
            self.assertEqual(len(batch.result.items), 2)
            self.assertEqual(batch.result.continuation, c)
        failed_only = run((page(data={'rt_cd': '1', 'msg1': 'untrusted-payload-canary'}),))
        self.assertEqual((failed_only.result.status, failed_only.result.items), ('error', ()))
        self.assertEqual(run(()).result.status, 'unknown')

    def test_cursor_chain_repeat_missing_and_unknown_terminal_are_incomplete(self):
        c = BrokerCursor('cursor-f', 'cursor-n')
        first = page(marker='F', terminal=False, out=c)
        repeated = page(index=1, cursor=c, marker='M', terminal=False, out=c, at='2026-10-24T00:00:02Z')
        self.assertIn('cursor_repeated', run((first, repeated)).reason_codes)
        self.assertIn('cursor_missing', run((page(marker='M', terminal=False),)).reason_codes)
        for fixture in (page(terminal=False), page(marker='unexpected', terminal=True)):
            batch = run((fixture,))
            self.assertEqual(batch.result.status, 'unknown')
            self.assertIn('terminal_unverified', batch.reason_codes)
        req = request('us_present_balance')
        self.assertIn('continuation_unverified', run((page(req, marker='M', terminal=False),), req=req).reason_codes)

    def test_four_page_and_reduced_call_limits_are_not_terminal_success(self):
        pages = []
        cursor = BrokerCursor('', '')
        for i in range(4):
            out = BrokerCursor('f' + str(i), 'n' + str(i))
            data = body(empty=True)
            pages.append(page(data=data, index=i, cursor=cursor, out=out,
                              marker='M' if i < 3 else '', terminal=i == 3,
                              at=f'2026-10-24T00:00:0{i + 1}Z'))
            cursor = out
        batch = run(tuple(pages))
        self.assertEqual(batch.result.pages_fetched, 4)
        self.assertIn('page_limit', batch.reason_codes)
        self.assertIn('page_limit', run(cap=capability(max_calls=1)).reason_codes)

    def test_received_rows_include_duplicates_and_rejected_page_not_truncated(self):
        data = body(empty=True)
        data['output1'] = [holding('S' + str(i)) for i in range(32)]
        batch = run((page(data=data),))
        self.assertEqual(batch.page_receipts[0].received_rows, 32)
        self.assertIn('row_limit', batch.reason_codes)
        data['output1'].append(holding('S32'))
        rejected = run((page(data=data),))
        self.assertEqual(rejected.page_receipts[0].received_rows, 33)
        self.assertEqual(rejected.result.items, ())
        small = run((page(),), cap=capability(max_rows=1))
        self.assertIn('row_limit', small.reason_codes)
        self.assertEqual(small.result.items, ())

    def test_page_bytes_total_bytes_and_30_second_equality_fail_closed(self):
        raw = page().raw_body
        self.assertIn('byte_limit', run((page(raw=raw),), cap=capability(max_bytes=len(raw))).reason_codes)
        self.assertIn('byte_limit', run((page(raw=raw),), cap=capability(max_bytes=len(raw) - 1)).reason_codes)
        padded = raw + b' ' * (65536 - len(raw))
        self.assertIn('byte_limit', run((page(raw=padded),)).reason_codes)
        self.assertIn('byte_limit', run((page(raw=padded + b' '),)).reason_codes)
        exact_time = run((page(at=DEADLINE),), now=DEADLINE)
        self.assertFalse(exact_time.result.complete)
        self.assertIn('time_limit', exact_time.reason_codes)
        self.assertIn('time_limit', run(cap=capability(max_seconds=1)).reason_codes)

    def test_future_backward_and_before_start_receipt_clocks(self):
        for at in ('2026-10-24T00:00:11Z', '2026-10-23T23:59:59Z', '2026-10-24T00:00:31Z'):
            batch = run((page(at=at),))
            self.assertIn('clock_invalid', batch.reason_codes)
            self.assertEqual(batch.result.status, 'error')
        c = BrokerCursor('next-f', 'next-n')
        first = page(at='2026-10-24T00:00:05Z', marker='M', terminal=False, out=c)
        second = page(index=1, cursor=c, at='2026-10-24T00:00:04Z')
        batch = run((first, second))
        self.assertEqual(batch.result.status, 'partial')
        self.assertIn('clock_invalid', batch.reason_codes)
        self.assertEqual(batch.page_receipts[1].validation, 'rejected')

    def test_same_holding_at_different_positions_and_pages_is_not_silently_deduplicated(self):
        data = body(empty=True)
        data['output1'] = [holding('A'), holding('B'), holding('A')]
        batch = run((page(data=data),))
        self.assertIn('duplicate_observation', batch.reason_codes)
        self.assertEqual(len(batch.result.items), 3)
        c = BrokerCursor('next-f', 'next-n')
        second_data = body(empty=True)
        second_data['output1'] = [holding('B'), holding('A')]
        first = page(data=body() | {'output1': [holding('A')]}, marker='M', terminal=False, out=c)
        second = page(data=second_data, index=1, cursor=c, at='2026-10-24T00:00:02Z')
        self.assertIn('duplicate_observation', run((first, second)).reason_codes)

    def test_order_cumulative_changes_are_preserved_without_individual_execution(self):
        for op in ('kr_orders', 'us_orders'):
            req = request(op)
            data = body(op)
            section = 'output' if op == 'us_orders' else 'output1'
            data[section] = [order('3', overseas=op == 'us_orders'), order('5', overseas=op == 'us_orders')]
            batch = run((page(req, data=data),), req=req)
            rows = [i for i in batch.result.items if i.kind == 'order_cumulative']
            quantity = 'ft_ccld_qty' if op == 'us_orders' else 'tot_ccld_qty'
            self.assertEqual([next(n.value for n in i.numbers if n.source_field == quantity) for i in rows], ['3', '5'])
            self.assertIn('conflicting_observation', batch.reason_codes)
            self.assertTrue(all(i.individual_execution_id is None for i in rows))
            data[section][1] = data[section][0].copy()
            self.assertIn('duplicate_observation', run((page(req, data=data),), req=req).reason_codes)

    def test_numeric_account_echo_and_payload_canaries_never_escape_public_objects(self):
        req = request('us_balance')
        data = body(req.operation)
        data['output1'][0].update(cano='12345678', acnt_prdt_cd='00')
        data['msg1'] = 'untrusted-payload-canary'
        batch = run((page(req, data=data, identity=FixtureAccountIdentity()),), req=req)
        public = canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch)).decode() + repr(batch)
        self.assertNotIn('12345678', public)
        self.assertNotIn('untrusted-payload-canary', public)
        self.assertIn('account_mismatch', batch.reason_codes)
        data['output1'][0]['cano'] = '00000000'
        unverified = run((page(req, data=data),), req=req)
        self.assertFalse(unverified.result.complete)
        self.assertIn('account_unverified', unverified.reason_codes)

    def test_whole_result_oversize_is_explicit_failure_not_successful_truncation(self):
        long_binding = binding(account_ref='synthetic-account:' + 'a' * 110,
                               capability_version='c' * 128, catalog_version='v' * 128)
        req = request('us_balance', query_id='q' * 128, binding=long_binding)
        data = body('us_balance', empty=True)
        fields = ('ovrs_rlzt_pfls_amt', 'ovrs_tot_pfls', 'rlzt_erng_rt', 'tot_evlu_pfls_amt',
                  'tot_pftrt', 'frcr_buy_amt_smtl1', 'ovrs_rlzt_pfls_amt2', 'frcr_buy_amt_smtl2')
        data['output2'] = [{f: '9' * 20 + '.' + '1' * 18 for f in fields} for _ in range(31)]
        batch = run((page(req, data=data),), req=req)
        self.assertEqual((batch.result.status, batch.result.complete, batch.result.items), ('error', False, ()))
        self.assertEqual(batch.reason_codes, ('output_oversize',))
        self.assertEqual(batch.page_receipts[0].received_rows, 31)


class BrokerCanonicalTests(unittest.TestCase):
    def test_three_registered_schemas_exact_decimal_time_and_hash_roundtrip(self):
        req = request('kr_buy_capacity')
        batch = run(req=req)
        for obj in (capability(req), req, batch):
            wrapper = CanonicalPayload(type(obj).__name__, 1, 'synthetic', obj)
            raw = canonical_bytes(wrapper)
            self.assertEqual(parse_payload(raw), wrapper)
            self.assertEqual(canonical_hash(wrapper), sha256(b'QuantHarbor/qh-canonical-json-v1\n' + raw).hexdigest())
            self.assertEqual(parse_payload(json.dumps(json.loads(raw), sort_keys=False)).payload, obj)
        alternate = replace(req, scope=replace(req.scope, price='100.0000'), requested_at='2026-10-24T09:00:00+09:00')
        self.assertEqual(canonical_hash(CanonicalPayload('BrokerReadRequest', 1, 'synthetic', req)),
                         canonical_hash(CanonicalPayload('BrokerReadRequest', 1, 'synthetic', alternate)))

    def test_nested_unknown_missing_boolean_versions_and_environment_forgery_rejected(self):
        batch = run()
        raw = canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch))
        for mutate in (
            lambda x: x.update(environment='paper'),
            lambda x: x['payload'].update(schema_version=True),
            lambda x: x['payload']['request']['binding'].update(environment='paper'),
            lambda x: x['payload']['request']['scope'].update(extra='untrusted'),
            lambda x: x['payload']['result']['items'][0]['numbers'][0].update(value=1.5),
            lambda x: x['payload']['result'].update(account_ref='synthetic-account:other'),
            lambda x: x['payload']['page_receipts'][0].update(request_hash='0' * 64),
            lambda x: x['payload'].pop('missing_scope'),
        ):
            value = json.loads(raw)
            mutate(value)
            with self.assertRaises(ContractError):
                parse_payload(json.dumps(value))
        with self.assertRaises(ContractError):
            parse_payload(raw.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1', 1))
        with self.assertRaises(ContractError):
            CanonicalPayload('BrokerQueryResult', 1, 'synthetic', batch.result)

    def test_complete_claim_rejects_missing_numbers_duplicate_facts_and_bad_cursor_chain(self):
        batch = run()
        item = batch.result.items[0]
        missing = replace(item, numbers=(SourceNumber('hldg_qty', None, 'absent', None, None),))
        with self.assertRaises(ContractError):
            replace(batch, result=replace(batch.result, items=(missing,)))
        with self.assertRaises(ContractError):
            replace(batch, result=replace(batch.result, items=(item, item)))
        with self.assertRaises(ContractError):
            replace(batch, page_receipts=(replace(batch.page_receipts[0], request_cursor=BrokerCursor('unexpected-f', 'unexpected-n')),))

    def test_security_s1_direct_scope_mutation_cannot_keep_complete(self):
        batch = run(req=request('us_balance'))
        with self.assertRaises(ContractError):
            row = replace(batch.result.items[0], venue='NYSE', currency='KRW')
            replace(batch, result=replace(batch.result, items=(row,)))

    def test_security_s1_canonical_scope_mutation_cannot_keep_complete(self):
        batch = run(req=request('us_balance'))
        value = json.loads(canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch)))
        value['payload']['result']['items'][0].update(venue='NYSE', currency='KRW')
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(value))

    def test_security_s2_direct_required_numeric_omission_cannot_keep_complete(self):
        batch = run()
        with self.assertRaises(ContractError):
            row = replace(batch.result.items[0], numbers=batch.result.items[0].numbers[:1])
            replace(batch, result=replace(batch.result, items=(row, batch.result.items[1])))

    def test_security_s2_canonical_required_numeric_omission_cannot_keep_complete(self):
        batch = run()
        value = json.loads(canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch)))
        value['payload']['result']['items'][0]['numbers'].pop()
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(value))
        value = json.loads(canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch)))
        value['payload']['result']['items'][0]['numbers'][1]['source_field'] = 'arbitrary_numeric'
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(value))

    def test_security_all_sections_required_numeric_and_identity_fields_are_bound(self):
        from quantharbor.adapters.kis_read import SECTIONS
        from quantharbor.domain.broker_read import SOURCE_FIELDS, numeric_fields
        for op in OPS:
            batch = run(req=request(op))
            raw = canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch))
            for section in SECTIONS[op]:
                self.assertEqual(section.numbers, numeric_fields(op, section.name))
            for index, row in enumerate(batch.result.items):
                profile = SOURCE_FIELDS[(op, row.source_section)]
                for required in profile[1]:
                    with self.subTest(op=op, section=row.source_section, missing_numeric=required):
                        mutated = json.loads(raw)
                        numbers = mutated['payload']['result']['items'][index]['numbers']
                        numbers[:] = [n for n in numbers if n['source_field'] != required]
                        with self.assertRaises(ContractError):
                            parse_payload(json.dumps(mutated))
                for identity in profile[3]:
                    with self.subTest(op=op, section=row.source_section, missing_identity=identity):
                        mutated = json.loads(raw)
                        mutated['payload']['result']['items'][index][identity] = None
                        with self.assertRaises(ContractError):
                            parse_payload(json.dumps(mutated))
                with self.assertRaises(ContractError):
                    replace(row, numbers=(replace(row.numbers[0], source_field='arbitrary_numeric'),))

    def test_security_incomplete_facts_preserved_and_optional_ambiguous_numeric_may_be_absent(self):
        batch = run(req=request('us_balance'))
        row = replace(batch.result.items[0], source_symbol=None, venue=None, currency=None, numbers=())
        partial = replace(batch, result=replace(batch.result, items=(row,), status='partial',
            complete=False, source_error='missing_fact'), missing_scope=(batch.request.scope.coverage,),
            reason_codes=('missing_fact',))
        wrapper = CanonicalPayload('BrokerReadBatch', 1, 'synthetic', partial)
        self.assertEqual(parse_payload(canonical_bytes(wrapper)), wrapper)
        self.assertFalse(partial.result.complete)
        req = request('us_present_balance')
        data = body(req.operation)
        del data['output2'][0]['frcr_evlu_amt2']
        optional_absent = run((page(req, data=data),), req=req)
        self.assertTrue(optional_absent.result.complete)
        wrapper = CanonicalPayload('BrokerReadBatch', 1, 'synthetic', optional_absent)
        self.assertEqual(parse_payload(canonical_bytes(wrapper)), wrapper)

    def test_review_r1_required_object_rows_cannot_be_jointly_deleted_direct(self):
        for op, section in (('kr_buy_capacity', 'output'), ('kr_orders', 'output2')):
            batch = run(req=request(op))
            items = tuple(i for i in batch.result.items if i.source_section != section)
            with self.assertRaises(ContractError):
                replace(batch, result=replace(batch.result, items=items),
                    page_receipts=(replace(batch.page_receipts[0], received_rows=len(items)),))

    def test_review_r1_required_object_rows_cannot_be_jointly_deleted_canonical(self):
        for op, section in (('kr_buy_capacity', 'output'), ('kr_orders', 'output2')):
            batch = run(req=request(op))
            value = json.loads(canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch)))
            payload = value['payload']
            payload['result']['items'] = [i for i in payload['result']['items'] if i['source_section'] != section]
            payload['page_receipts'][0]['received_rows'] = len(payload['result']['items'])
            with self.assertRaises(ContractError):
                parse_payload(json.dumps(value))

    def test_review_r1_unsupported_complete_rejected_direct_and_canonical(self):
        batch = run((), req=request('individual_executions'))
        receipt = replace(run().page_receipts[0], request_hash=batch.request_hash, received_rows=0)
        result = replace(batch.result, status='success', complete=True, source_error=None, pages_fetched=1)
        with self.assertRaises(ContractError):
            replace(batch, result=result, page_receipts=(receipt,), missing_scope=(), reason_codes=())
        value = json.loads(canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch)))
        from dataclasses import asdict
        value['payload'].update(result=asdict(result), page_receipts=[asdict(receipt)], missing_scope=[], reason_codes=[])
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(value))

    def test_review_r2_complete_observation_times_bind_receipt_row_counts(self):
        req = request('us_balance')
        cursor = BrokerCursor('f-next', 'n-next')
        first = page(req, marker='M', terminal=False, out=cursor)
        data = body(req.operation)
        data['output1'][0]['ovrs_pdno'] = 'OTHER'
        second = page(req, data=data, index=1, cursor=cursor, at='2026-10-24T00:00:02Z')
        batch = run((first, second), req=req)
        self.assertTrue(batch.result.complete)
        moved = replace(batch.result.items[1], observed_at=batch.result.items[0].observed_at)
        with self.assertRaises(ContractError):
            replace(batch, result=replace(batch.result, items=(batch.result.items[0], moved)))
        value = json.loads(canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch)))
        value['payload']['result']['items'][1]['observed_at'] = value['payload']['result']['items'][0]['observed_at']
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(value))

    def test_review_equal_timestamp_pages_are_valid_but_each_requires_its_object_section(self):
        req = request('us_balance')
        cursor = BrokerCursor('f-next', 'n-next')
        data = body(req.operation)
        data['output1'][0]['ovrs_pdno'] = 'OTHER'
        first = page(req, marker='M', terminal=False, out=cursor)
        second = page(req, data=data, index=1, cursor=cursor)
        valid = run((first, second), req=req)
        self.assertTrue(valid.result.complete)
        wrapper = CanonicalPayload('BrokerReadBatch', 1, 'synthetic', valid)
        self.assertEqual(parse_payload(canonical_bytes(wrapper)), wrapper)
        # Two equal-time domestic pages need two summaries, even if total rows agree.
        batch = run(req=request('kr_orders'))
        extra_order = replace(batch.result.items[0], order_number='order-2')
        receipts = (replace(batch.page_receipts[0], wire_marker='M', response_cursor=cursor, terminal_evidence=None),
                    replace(batch.page_receipts[0], page_index=1, request_cursor=cursor, received_rows=1))
        result = replace(batch.result, pages_fetched=2, items=batch.result.items + (extra_order,))
        with self.assertRaises(ContractError):
            replace(batch, result=result, page_receipts=receipts)
        from dataclasses import asdict
        value = json.loads(canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch)))
        value['payload'].update(result=asdict(result), page_receipts=[asdict(r) for r in receipts])
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(value))

    def test_review_nonpaginated_endpoints_cannot_claim_multiple_accepted_pages(self):
        cursor = BrokerCursor('f-next', 'n-next')
        for op in ('kr_buy_capacity', 'us_present_balance'):
            req = request(op)
            batch = run((page(req, data=body(op, empty=op == 'us_present_balance')),), req=req)
            receipts = (replace(batch.page_receipts[0], wire_marker='M', response_cursor=cursor, terminal_evidence=None),
                        replace(batch.page_receipts[0], page_index=1, request_cursor=cursor, received_rows=0))
            result = replace(batch.result, pages_fetched=2)
            with self.assertRaises(ContractError):
                replace(batch, result=result, page_receipts=receipts)
            from dataclasses import asdict
            value = json.loads(canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch)))
            value['payload'].update(result=asdict(result), page_receipts=[asdict(r) for r in receipts])
            with self.assertRaises(ContractError):
                parse_payload(json.dumps(value))
