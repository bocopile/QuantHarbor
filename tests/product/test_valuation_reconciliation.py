"""독립 statement와 원단위 scope 비교, 현재 KIS bridge 보류 검증."""
from dataclasses import replace
import unittest

from quantharbor.application.valuation import inspect_broker_batch, reconcile
from quantharbor.domain.ledger import CashBalance, hash_record
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import parse_payload
from quantharbor.domain.valuation import BalanceScope, CashTolerance, QuantityTolerance
from synthetic_market import START, END, NOW, LATER
from synthetic_valuation import (ACCOUNT, HOLDING, KEY, WHOLE, projection, request,
                                reconciliation_policy, statement, unchecked_bytes)
import synthetic_broker as kis


class ReconciliationTests(unittest.TestCase):
    def compare(self, source=None, p=None, req=None, pol=None):
        return reconcile(projection() if p is None else p, statement() if source is None else source,
                         request() if req is None else req, reconciliation_policy() if pol is None else pol)

    def test_independent_full_source_snapshot_matches(self):
        r = self.compare()
        self.assertEqual(r.status, 'matched')
        self.assertTrue(r.scope_matched)
        self.assertTrue(r.full_account_balances_matched)
        self.assertEqual(len(r.differences), 7)  # holding plus all 3 components x 2 currencies
        self.assertEqual(r.compared_domains, ('holdings', 'settled_cash', 'unsettled_payable', 'unsettled_receivable'))

    def test_raw_numbers_difference_not_hidden_by_valuation(self):
        s = statement(holdings=(replace(HOLDING, amount='2.000000000000000001'),),
            cash=(CashBalance('settled_cash', 'USD', '1000.000000000000000001'),))
        r = self.compare(s)
        self.assertEqual(r.status, 'mismatch')
        self.assertEqual([x.difference for x in r.differences if x.status == 'mismatch'],
                         ['0.000000000000000001', '0.000000000000000001'])
        self.assertTrue(all(x.tolerance == '0' for x in r.differences))

    def test_explicit_tolerance_boundary_and_above(self):
        pol = reconciliation_policy(quantities=(QuantityTolerance('share', '0.01'),),
            cash=(CashTolerance('KRW', '0'), CashTolerance('USD', '0.05')))
        self.assertEqual(self.compare(statement(holdings=(replace(HOLDING, amount='2.01'),),
            cash=(CashBalance('settled_cash', 'USD', '1000.05'),)), pol=pol).status, 'matched')
        self.assertEqual(self.compare(statement(holdings=(replace(HOLDING, amount='2.010000000000000001'),)), pol=pol).status, 'mismatch')
        with self.assertRaises(ContractError):
            self.compare(pol=reconciliation_policy(quantities=()))

    def test_union_missing_extra_and_explicit_zero(self):
        self.assertEqual(self.compare(statement(holdings=())).status, 'mismatch')
        extra = replace(HOLDING, instrument_id='extra-stock', amount='3')
        r = self.compare(statement(holdings=(extra, HOLDING)))
        extra_row = next(x for x in r.differences if x.position and x.position.instrument_id == 'extra-stock')
        self.assertEqual((extra_row.ledger_amount, extra_row.statement_amount, extra_row.difference), ('0', '3', '3'))
        zero = replace(extra, amount='0')
        self.assertEqual(self.compare(statement(holdings=(zero, HOLDING))).status, 'matched')
        r = self.compare(statement(cash=(CashBalance('settled_cash', 'KRW', '1'), CashBalance('settled_cash', 'USD', '1000'))))
        self.assertEqual(r.status, 'mismatch')
        self.assertEqual(next(x.difference for x in r.differences if x.currency == 'KRW' and x.domain == 'settled_cash'), '1')

    def test_omission_is_unknown_without_explicit_zero_semantics(self):
        r = self.compare(statement(holdings=(), omitted_means_zero=False))
        self.assertEqual(r.status, 'incomplete')
        h = next(x for x in r.differences if x.domain == 'holdings')
        self.assertEqual((h.statement_amount, h.difference, h.status), (None, None, 'unknown'))

    def test_complete_explicit_zero_differs_from_unknown(self):
        zero_p = replace(projection(), holdings=(replace(HOLDING, amount='0'),))
        zero_s = statement(holdings=(replace(HOLDING, amount='0'),))
        self.assertEqual(self.compare(zero_s, p=zero_p).status, 'matched')
        self.assertEqual(self.compare(statement(holdings=(), omitted_means_zero=False), p=zero_p).status, 'incomplete')

    def test_subset_match_only_and_strict_source_scope(self):
        subset = BalanceScope('subset', (KEY,), (), ('holdings',))
        source = statement(cash=(), source_changes={'scope': subset}, requested_scope=subset)
        r = self.compare(source, req=request(scope=subset))
        self.assertEqual(r.status, 'matched')
        self.assertTrue(r.scope_matched)
        self.assertFalse(r.full_account_balances_matched)
        with self.assertRaises(ContractError):
            self.compare(source)
        with self.assertRaises(ContractError):
            statement(source_changes={'scope': subset}, requested_scope=subset)

    def test_covered_subset_of_whole_is_incomplete(self):
        subset = BalanceScope('subset', (KEY,), (), ('holdings',))
        source = statement(cash=(), source_changes={'scope': subset}, complete=False, status='partial')
        r = self.compare(source)
        self.assertEqual(r.status, 'incomplete')
        self.assertIn('scope_incomplete', r.reason_codes)
        self.assertIn('holdings:entire_account', r.missing_scope)
        self.assertFalse(r.full_account_balances_matched)
        self.assertEqual(next(x.status for x in r.differences if x.domain == 'holdings'), 'matched')

    def test_partial_errors_empty_never_infer_zeros(self):
        for changes in (dict(status='partial', complete=False),
                        dict(status='error', complete=False, reason_codes=('source_failure',))):
            r = self.compare(statement(holdings=(), cash=(), **changes))
            self.assertEqual(r.status, 'incomplete')
            self.assertTrue(all(x.statement_amount is None for x in r.differences))
            self.assertFalse(r.scope_matched)
        # Independent complete empty statement on nonempty account gives actual mismatch.
        self.assertEqual(self.compare(statement(holdings=(), cash=())).status, 'mismatch')
        empty = replace(projection(), holdings=(), cash_balances=())
        self.assertEqual(self.compare(statement(holdings=(), cash=()), p=empty).status, 'matched')

    def test_complete_but_temporally_wrong_stays_incomplete(self):
        cases = (statement(source_changes={'source_as_of': START}),
                 statement(source_changes={'ingested_at': LATER}),
                 statement(temporal_consistency='bounded_observation'),
                 statement(temporal_consistency='unknown'))
        for source in cases:
            self.assertEqual(self.compare(source).status, 'incomplete')

    def test_mapping_unknown_and_different_mapping_do_not_invent_mismatch(self):
        self.assertEqual(self.compare(statement(mapping_status='unknown')).status, 'incomplete')
        p = replace(projection(), holdings=(replace(HOLDING, mapping_version='another-mapping'),))
        r = self.compare(p=p)
        self.assertIn('mapping_unknown', r.reason_codes)
        self.assertTrue(all(x.status == 'unknown' for x in r.differences if x.domain == 'holdings'))
        self.assertEqual(self.compare(statement(source_changes={'semantics_version': 'unknown'})).status, 'incomplete')

    def test_incomplete_ledger_cannot_be_matched(self):
        for reason in ('baseline_missing', 'quarantined_observation', 'correction_consequences_unresolved'):
            p = replace(projection(), complete=False, baseline_known=reason != 'baseline_missing', reason_codes=(reason,))
            r = self.compare(p=p)
            self.assertEqual(r.status, 'incomplete')
            self.assertIn(reason, r.reason_codes)

    def test_known_difference_preserved_when_source_incomplete(self):
        source = statement(holdings=(replace(HOLDING, amount='4'),), status='partial', complete=False)
        r = self.compare(source)
        self.assertEqual(r.status, 'incomplete')
        self.assertEqual(next(x.difference for x in r.differences if x.domain == 'holdings'), '2')

    def test_statement_hash_account_scope_and_policy_rejection(self):
        source = statement()
        with self.assertRaises(ContractError):
            replace(source, source_snapshot_hash='0' * 64)
        with self.assertRaises(ContractError):
            self.compare(statement(source_changes={'account_ref': 'synthetic-account:other'}))
        with self.assertRaises(ContractError):
            self.compare(pol=reconciliation_policy(version='other-policy'))
        with self.assertRaises(ContractError):
            statement(cash=(CashBalance('trade_clearing', 'USD', '1000'),))

    def test_absent_statement_unreconciled(self):
        r = reconcile(projection(), None, request(), reconciliation_policy())
        self.assertEqual(r.status, 'unreconciled')
        self.assertFalse(r.scope_matched)

    def assert_result_rejected(self, result, **changes):
        with self.subTest(boundary='constructor'), self.assertRaises(ContractError):
            replace(result, **changes)
        for key, value in changes.items():
            object.__setattr__(result, key, value)
        with self.subTest(boundary='canonical'), self.assertRaises(ContractError):
            parse_payload(unchecked_bytes(result))

    def test_v3_absent_statement_cannot_become_standalone_matched(self):
        r = reconcile(projection(), None, request(), reconciliation_policy())
        self.assert_result_rejected(r, status='matched', missing_scope=(), reason_codes=(),
            scope_matched=True, full_account_balances_matched=True)

    def test_v3_matched_requires_bound_covered_and_requested_scope(self):
        subset = BalanceScope('subset', (KEY,), (), ('holdings',))
        for changes in (dict(covered_scope=None), dict(covered_scope=subset),
                        dict(requested_scope=subset, full_account_balances_matched=False)):
            with self.subTest(changes=changes):
                self.assert_result_rejected(self.compare(), **changes)

    def test_v3_matched_requires_comparison_domains_and_rows(self):
        r = self.compare()
        cases = (dict(compared_domains=()), dict(differences=()),
                 dict(differences=tuple(x for x in r.differences if x.domain != 'holdings')),
                 dict(differences=tuple(x for x in r.differences if x.domain != 'settled_cash')),
                 dict(differences=tuple(x for x in r.differences if x.domain != 'holdings'),
                      compared_domains=tuple(x for x in r.compared_domains if x != 'holdings')),
                 dict(differences=tuple(x for x in r.differences if x.domain != 'settled_cash'),
                      compared_domains=tuple(x for x in r.compared_domains if x != 'settled_cash')))
        for changes in cases:
            with self.subTest(changes=changes):
                self.assert_result_rejected(self.compare(), **changes)

    def test_v3_matched_requires_statement_eligibility_and_amount_binding(self):
        for source in (statement(temporal_consistency='unknown'), statement(mapping_status='unknown'),
                       statement(source_changes={'semantics_version': 'unknown'}),
                       statement(status='partial', complete=False),
                       statement(holdings=(replace(HOLDING, amount='3'),))):
            with self.subTest(source=source):
                self.assert_result_rejected(self.compare(), statement=source)

    def test_v3_valid_standalone_full_subset_and_empty_roundtrip(self):
        subset = BalanceScope('subset', (KEY,), (), ('holdings',))
        results = (self.compare(), self.compare(statement(cash=(), source_changes={'scope': subset},
            requested_scope=subset), req=request(scope=subset)),
            self.compare(statement(holdings=(), cash=()), p=replace(projection(), holdings=(), cash_balances=())))
        for result in results:
            self.assertEqual(result.status, 'matched')
            self.assertEqual(parse_payload(unchecked_bytes(result)).payload, result)

    def test_kis_complete_empty_failure_all_remain_unresolved_and_preserve_scope(self):
        req = kis.request('us_balance')
        vreq = request(account_ref=req.binding.account_ref, as_of=kis.START,
            knowledge_cutoff=kis.NOW, evaluated_at=kis.NOW)
        batches = (kis.run(req=req), kis.run((kis.page(req, data=kis.body('us_balance', empty=True)),), req=req),
                   kis.run((), req=req))
        for batch in batches:
            r = inspect_broker_batch(batch, vreq)
            self.assertEqual(r.status, 'incomplete')
            self.assertEqual(r.source_scope, req.scope)
            self.assertEqual(r.source_missing_scope, batch.missing_scope)
            self.assertEqual(r.source_reason_codes, batch.reason_codes)
            self.assertEqual(r.source_error, batch.result.source_error)
            self.assertEqual(r.query_hash, hash_record(req))
            self.assertEqual(r.batch_hash, hash_record(batch))
            self.assertIn('mapping_unknown', r.reason_codes)
            self.assertIn('source_as_of_unknown', r.reason_codes)
        with self.assertRaises(ContractError):
            inspect_broker_batch(batches[0], request(as_of=kis.START, knowledge_cutoff=kis.NOW, evaluated_at=kis.NOW))


if __name__ == '__main__':
    unittest.main()
