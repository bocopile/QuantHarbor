from dataclasses import replace
import json
import unittest

from quantharbor.adapters.kis_read import DecodeError, WirePlan, decode_page
from quantharbor.domain.broker_read import BrokerCursor
from quantharbor.domain.primitives import ContractError
from quantharbor.ports.broker_read import FixtureAccountIdentity
from synthetic_broker import body, page, request


class KisReadTests(unittest.TestCase):
    def test_six_plans_exact_paths_tr_and_private_symbolic_slots(self):
        expected = {
            'kr_balance': ('domestic-stock', 'inquire-balance', 'VTTC8434R'),
            'kr_orders': ('domestic-stock', 'inquire-daily-ccld', 'VTTC0081R'),
            'kr_buy_capacity': ('domestic-stock', 'inquire-psbl-order', 'VTTC8908R'),
            'us_balance': ('overseas-stock', 'inquire-balance', 'VTTS3012R'),
            'us_orders': ('overseas-stock', 'inquire-ccnl', 'VTTS3035R'),
            'us_present_balance': ('overseas-stock', 'inquire-present-balance', 'VTRP6504R'),
        }
        for op, (market, endpoint, tr) in expected.items():
            with self.subTest(op=op):
                plan = WirePlan(request(op))
                self.assertEqual((plan.method, plan.path, plan.tr_id, plan.tr_cont),
                    ('GET', f'/uapi/{market}/v1/trading/{endpoint}', tr, ''))
                self.assertEqual(dict(plan.params)['CANO'], '<private-binding:cano>')
                self.assertFalse(hasattr(plan, 'host') or hasattr(plan, 'headers'))
        kr = dict(WirePlan(request('kr_orders')).params)
        self.assertEqual((kr['INQR_DVSN_3'], kr['EXCG_ID_DVSN_CD'], kr['INQR_STRT_DT']), ('01', 'KRX', '20261023'))
        us = dict(WirePlan(request('us_orders')).params)
        self.assertEqual((us['PDNO'], us['OVRS_EXCG_CD'], us['SORT_SQN']), ('', '', 'DS'))
        earlier = request('kr_orders')
        self.assertEqual(WirePlan(replace(earlier, scope=replace(earlier.scope, period_class='before'))).tr_id, 'VTSC9215R')
        next_plan = WirePlan(request(), BrokerCursor('next-f', 'next-n'))
        self.assertEqual((next_plan.tr_cont, dict(next_plan.params)['CTX_AREA_FK100']), ('N', 'next-f'))
        for op in ('kr_amendable_orders', 'us_open_orders', 'us_settlement_balance', 'individual_executions'):
            with self.assertRaises(ContractError):
                WirePlan(request(op))

    def test_exact_decimal_missing_null_empty_zero_and_invalid_numbers(self):
        for value, missing in ((None, 'null'), ('', 'empty'), ('0', None), ('1.2300', None)):
            data = body()
            data['output1'][0]['hldg_qty'] = value
            number = decode_page(page(data=data)).items[0].numbers[0]
            self.assertEqual(number.missing_reason, missing)
            self.assertEqual(number.value, None if missing else '0' if value == '0' else '1.23')
        data = body()
        del data['output1'][0]['hldg_qty']
        self.assertEqual(decode_page(page(data=data)).items[0].numbers[0].missing_reason, 'absent')
        for value in (1, 0.5, True, 'NaN', 'Infinity', '1e2', ' 3', '3 ', '1' * 21, '0.' + '1' * 19):
            data = body()
            data['output1'][0]['hldg_qty'] = value
            with self.subTest(value_type=type(value).__name__), self.assertRaises(DecodeError):
                decode_page(page(data=data))

    def test_json_duplicate_unknown_fields_and_structural_drift(self):
        bad = [b'{"rt_cd":"0","rt_cd":"0"}', b'{"rt_cd":"0","output1":[{"pdno":"A","pdno":"B"}]}']
        for raw in bad:
            with self.assertRaises(DecodeError):
                decode_page(page(raw=raw))
        for mutate in (
            lambda x: x.update(unknown='payload-canary'),
            lambda x: x['output1'][0].update(unknown='payload-canary'),
            lambda x: x.update(output1={}),
            lambda x: x.update(output2=None),
            lambda x: x.update(output1=[{'pdno': ['nested']}]),
            lambda x: x.update(msg1='x' * 513),
            lambda x: x.update(msg1='\ud800'),
        ):
            data = body()
            mutate(data)
            with self.assertRaises(DecodeError):
                decode_page(page(raw=json.dumps(data, ensure_ascii=True).encode()))
        raw = b'{"rt_cd":"0","output1":' + b'[' * 20 + b']' * 20 + b'}'
        with self.assertRaises(DecodeError):
            decode_page(page(raw=raw))

    def test_account_echo_requires_fixed_identity_and_does_not_escape(self):
        req = request('us_balance')
        data = body(req.operation)
        data['output1'][0].update(cano='00000000', acnt_prdt_cd='00')
        self.assertEqual(decode_page(page(req, data=data)).account_evidence, 'unverified')
        self.assertEqual(decode_page(page(req, data=data, identity=FixtureAccountIdentity())).account_evidence,
                         'synthetic_echo_verified')
        data['output1'][0]['cano'] = '12345678'  # generated numeric canary, never a real account
        fixture = page(req, data=data, identity=FixtureAccountIdentity())
        with self.assertRaises(DecodeError) as caught:
            decode_page(fixture)
        self.assertEqual(caught.exception.reason, 'account_mismatch')
        self.assertNotIn('12345678', repr(fixture) + repr(caught.exception) + str(caught.exception))
        self.assertEqual(decode_page(page(req)).account_evidence, 'request_bound_only')

    def test_exact_scope_date_currency_and_exchange_mismatch_fail(self):
        for op, field, value in (('us_balance', 'tr_crcy_cd', 'KRW'), ('us_balance', 'ovrs_excg_cd', 'NYSE'),
                                 ('us_present_balance', 'buy_crcy_cd', 'KRW'), ('kr_orders', 'ord_dt', '20261022')):
            req = request(op)
            data = body(op)
            data['output1'][0][field] = value
            with self.subTest(op=op, field=field), self.assertRaises(DecodeError):
                decode_page(page(req, data=data))

    def test_source_shapes_are_explicit_and_ambiguous_amount_stays_unknown(self):
        req = request('us_balance')
        data = body(req.operation)
        data['output1'] = data['output1'][0]
        self.assertEqual(len(decode_page(page(req, data=data)).items), 1)
        req = request('us_present_balance')
        decoded = decode_page(page(req))
        number = next(n for item in decoded.items for n in item.numbers if n.source_field == 'frcr_evlu_amt2')
        self.assertEqual((number.semantic_status, number.currency, number.unit), ('unknown', None, None))
        self.assertFalse(any(i.usable_for_internal_available_cash for i in decoded.items))
        self.assertTrue(all(i.instrument_id is None and i.mapping_status == 'mapping_unknown' for i in decoded.items))
