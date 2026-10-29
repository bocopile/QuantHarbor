"""Q21 수학·Q17/Q20 실제 로컬 API 통합. 독립 상수로 기대값을 검증한다."""
from dataclasses import replace
from decimal import localcontext
from fractions import Fraction
import unittest
from unittest.mock import patch

from quantharbor.application.valuation import value_projection
from quantharbor.domain.ledger import CashBalance, LedgerCompleteness, PositionDelta
from quantharbor.domain.market_data import Adjustment, ActionRef, RecordRefSet, item_ref, record_hash
from quantharbor.domain.primitives import ContractError, Price, utc_instant
from quantharbor.domain.valuation import CurrencyQuantum, FXSelection, PriceSelection, quantize
from synthetic_ledger import cash_pair, submission
from synthetic_market import END, NOW, START, LATER, bar, item, revision, rights, context
from synthetic_valuation import (ACCOUNT, HOLDING, KEY, SERIES, FX_SERIES, fx_item, ledger,
                                market, policy, price_item, projection, request)


class ValuationTests(unittest.TestCase):
    def value(self, p=None, req=None, inputs=None, pol=None):
        p = projection() if p is None else p
        return value_projection(p, request(ledger_cursor=p.ledger_cursor) if req is None else req,
            (market(),) if inputs is None else inputs, policy() if pol is None else pol)

    def test_exact_native_cash_and_unknown_costs(self):
        v = self.value()
        self.assertEqual(v.holdings[0].native_value, '22')
        self.assertEqual(v.cash_by_currency[0].economic_cash, '1000')
        self.assertEqual(v.native_totals[0].known_subtotal, '1022')
        self.assertEqual(v.nav, '1022')
        self.assertTrue(v.complete)
        self.assertEqual(v.holdings[0].costing_reason, 'costing_spec_pending_q23')
        self.assertEqual((v.holdings[0].cost_basis, v.holdings[0].price_pnl, v.holdings[0].fx_pnl,
            v.holdings[0].unrealized_pnl), (None, None, None, None))
        self.assertEqual((v.cash_by_currency[0].available_cash, v.cash_by_currency[0].reserved_cash,
            v.cash_by_currency[0].source_total, v.cash_by_currency[0].broker_buy_capacity), (None,) * 4)

    def test_buy_and_settlement_keep_nav_without_counteraccounts(self):
        store = ledger(holdings=())
        before = store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW)
        buy = replace(submission('buy', 'trade', effective_at=END), account_ref=ACCOUNT,
            cash_legs=cash_pair('unsettled_payable', '-22', 'trade_clearing', basis='trade'),
            position_deltas=(HOLDING,))
        accepted = store.append(buy, recorded_at=END)
        self.assertEqual(accepted.status, 'accepted')
        after_buy = store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW)
        settle = replace(submission('settle', 'settlement', effective_at=END), account_ref=ACCOUNT,
            cash_legs=cash_pair('settled_cash', '-22', 'unsettled_payable'), dependency_refs=accepted.event_ids)
        self.assertEqual(store.append(settle, recorded_at=NOW).status, 'accepted')
        after_settlement = store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW)
        self.assertEqual([self.value(p=x).nav for x in (before, after_buy, after_settlement)], ['1000'] * 3)
        self.assertEqual(self.value(p=after_buy).cash_by_currency[0].unsettled_payable, '-22')
        self.assertEqual(self.value(p=after_settlement).cash_by_currency[0].settled_cash, '978')

    def test_sell_and_settlement_keep_nav(self):
        store = ledger()
        sell = replace(submission('sell', 'trade', effective_at=END), account_ref=ACCOUNT,
            cash_legs=cash_pair('unsettled_receivable', '11', 'trade_clearing', basis='trade'),
            position_deltas=(replace(HOLDING, amount='-1'),))
        accepted = store.append(sell, recorded_at=END)
        after_sell = store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW)
        settle = replace(submission('settle', 'settlement', effective_at=END), account_ref=ACCOUNT,
            cash_legs=cash_pair('settled_cash', '11', 'unsettled_receivable'), dependency_refs=accepted.event_ids)
        self.assertEqual(store.append(settle, recorded_at=NOW).status, 'accepted')
        self.assertEqual(self.value(p=after_sell).nav, '1022')
        self.assertEqual(self.value(p=store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW)).nav, '1022')

    def test_normal_and_inverse_fx_exact(self):
        for observation, direction in ((fx_item(rate='1300'), 'multiply'), (fx_item(inverse=True, rate='0.0008'), 'divide')):
            with self.subTest(direction=direction):
                v = self.value(req=request(base_currency='KRW'), inputs=(market(records=(price_item(), observation)),), pol=policy(fx=True))
                self.assertEqual(v.native_totals[0].fx_direction, direction)
                self.assertEqual(v.nav, '1328600' if direction == 'multiply' else '1277500')

    def test_no_triangular_or_provider_fallback(self):
        v = self.value(req=request(base_currency='KRW'))
        self.assertIsNone(v.nav)
        self.assertEqual(v.known_subtotal, '0')
        self.assertEqual(v.holdings[0].native_value, '22')
        self.assertIn('fx_selection_missing', v.reason_codes)

    def test_missing_price_preserves_every_holding_and_known_cash(self):
        v = self.value(inputs=())
        self.assertEqual(tuple(x.position for x in v.holdings), (HOLDING,))
        self.assertIsNone(v.holdings[0].native_value)
        self.assertIsNone(v.holdings[0].currency)
        self.assertEqual(v.known_subtotal, '1000')
        self.assertIsNone(v.nav)

    def test_unknown_mapping_and_unit_are_not_silently_priced(self):
        for h in (replace(HOLDING, mapping_version='mapping-other'), replace(HOLDING, unit='lot'),
                  replace(HOLDING, instrument_id='unknown-stock')):
            with self.subTest(holding=h):
                p = replace(projection(), holdings=(h,))
                pol = policy(prices=(PriceSelection(replace(KEY, instrument_id=h.instrument_id,
                    mapping_version=h.mapping_version, unit=h.unit), SERIES),))
                v = self.value(p=p, pol=pol)
                self.assertEqual(v.holdings[0].position, h)
                self.assertIsNone(v.holdings[0].native_value)
                self.assertIsNone(v.nav)

    def test_zero_known_and_unknown_price_stay_distinct(self):
        p = replace(projection(), holdings=(replace(HOLDING, amount='0'),))
        self.assertEqual(self.value(p=p).holdings[0].native_value, '0')
        v = self.value(p=p, inputs=())
        self.assertIsNone(v.holdings[0].native_value)
        self.assertIsNone(v.nav)

    def test_every_ledger_incomplete_reason_propagates(self):
        for why in ('baseline_missing', 'quarantined_observation', 'economic_balance_invalid', 'correction_consequences_unresolved'):
            p = replace(projection(), baseline_known=why != 'baseline_missing', complete=False, reason_codes=(why,))
            v = self.value(p=p)
            self.assertFalse(v.complete)
            self.assertIsNone(v.nav)
            self.assertIn(why, v.reason_codes)
            self.assertFalse(v.cash_by_currency[0].complete)

    def test_actual_missing_baseline_and_quarantine_from_q20(self):
        store = ledger(seed=False)
        deposit = replace(submission(effective_at=START), account_ref=ACCOUNT)
        store.append(deposit, recorded_at=START)
        p = store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW)
        self.assertIn('baseline_missing', self.value(p=p).reason_codes)
        store = ledger()
        bad = replace(deposit, source_event_key='bad', completeness=LedgerCompleteness(False, False, False))
        self.assertEqual(store.append(bad, recorded_at=END).status, 'quarantined')
        self.assertIn('quarantined_observation', self.value(p=store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW)).reason_codes)

    def test_half_even_both_signs_and_real_quantum(self):
        expected = {'1.025': '1', '1.075': '1.1', '-1.025': '-1', '-1.075': '-1.1',
                    '0.025': '0', '-0.025': '0', '0.075': '0.1', '-0.075': '-0.1'}
        for amount, result in expected.items():
            self.assertEqual(quantize(Fraction(amount), '0.05'), result)
        pol = policy(quantums=(CurrencyQuantum('KRW', '1'), CurrencyQuantum('USD', '0.05')))
        for amount, result in (('1', '1'), ('-1', '-1')):
            p = replace(projection(), holdings=(replace(HOLDING, amount=amount),))
            v = self.value(p=p, inputs=(market(records=(price_item('1.025'),)),), pol=pol)
            self.assertEqual(v.holdings[0].native_value, result)

    def test_fixed_stages_round_each_holding_then_currency_fx(self):
        # 3 * 1.025 = 3.075 -> USD3.10, plus USD1000.01 -> 1003.11;
        # FX1.5 gives 1504.665 -> KRW1504.65 on actual .05 quantum.
        p = replace(projection(), holdings=(replace(HOLDING, amount='3'),), cash_balances=(
            CashBalance('settled_cash', 'USD', '1000.01'),))
        pol = policy(fx=True, quantums=(CurrencyQuantum('KRW', '0.05'), CurrencyQuantum('USD', '0.05')))
        v = self.value(p=p, req=request(base_currency='KRW'),
            inputs=(market(records=(price_item('1.025'), fx_item(rate='1.5'))),), pol=pol)
        self.assertEqual(v.holdings[0].native_value, '3.1')
        self.assertEqual(v.native_totals[0].known_subtotal, '1003.11')
        self.assertEqual(v.nav, '1504.65')

    def test_low_decimal_context_does_not_change_any_result(self):
        inp = (market(records=(price_item('11.123456789012345678'), fx_item(inverse=True, rate='3'))),)
        p = replace(projection(), holdings=(replace(HOLDING, amount='1.123456789012345678'),))
        req, pol = request(base_currency='KRW'), policy(fx=True)
        normal = self.value(p=p, req=req, inputs=inp, pol=pol)
        self.assertEqual(normal.holdings[0].native_value, '12.5')
        self.assertEqual(normal.nav, '338')  # (USD1000 + USD12.50) / 3 = KRW337.5, half-even
        with localcontext() as ctx:
            ctx.prec = 2
            self.assertEqual(self.value(p=p, req=req, inputs=inp, pol=pol), normal)

    def test_storage_overflow_rejected(self):
        p = replace(projection(), holdings=(replace(HOLDING, amount='99999999999999999999'),))
        with self.assertRaises(ContractError):
            self.value(p=p)

    def test_future_unknown_publication_and_stale_hold_price(self):
        inp = market(records=(price_item(published_at=None, publication_unknown_reason='unknown'),))
        self.assertIsNone(self.value(inputs=(inp,)).nav)
        v = self.value(req=request(as_of='2024-03-08T15:31:01Z', evaluated_at='2024-03-08T15:31:01Z'),
            p=projection(as_of='2024-03-08T15:31:01Z'))
        self.assertIn('price_stale', v.reason_codes)
        p = projection(as_of=START)
        self.assertIsNone(self.value(p=p, req=request(as_of=START)).nav)

    def test_rights_revoked_wrong_purpose_and_store_required(self):
        for grant in (rights(revoked_at=NOW), rights(purposes=('store',)), rights(purposes=('research',))):
            v = self.value(inputs=(market(current_rights=grant),))
            self.assertIsNone(v.nav)
            self.assertIsNone(v.holdings[0].native_value)

    def test_raw_adjusted_rejected_even_with_action_metadata(self):
        # Q17 may hold this first for missing action evidence; either path preserves the row.
        ref = ActionRef('synthetic', 'syn.source', 'syn.dataset', 'syn.action', 'action', 'v1', '0' * 64)
        adj = Adjustment('split', 'v1', END, (ref,), END, 'adjustment-evidence')
        inp = market(records=(item(revision(payload=bar(adjustment='adjusted', adjustment_details=adj))),))
        v = self.value(inputs=(inp,))
        self.assertIsNone(v.nav)
        self.assertEqual(v.holdings[0].position, HOLDING)

    def test_valid_q17_adjustment_still_rejected_for_portfolio_raw_close(self):
        from quantharbor.domain.market_data import CorporateAction
        action = CorporateAction('syn.instrument', 'syn.listing', 'syn.venue', 'SYN', 'split', 'share',
            '2024-03-08', None, None, 'dates_unknown', '2', '1', None)
        action_revision = revision(series_id='syn.action', event_id='action-event', payload=action)
        action_item = item(action_revision, observation_id='action-observation')
        ref = ActionRef(*action_revision.key, record_hash(action_revision))
        from synthetic_market import INGESTED
        adj = Adjustment('split', 'v1', END, (ref,), INGESTED, 'adjustment-evidence')
        adjusted = item(revision(payload=bar(adjustment='adjusted', adjustment_details=adj),
            published_at=INGESTED), observed_at=INGESTED)
        inp = market(records=(adjusted, action_item))
        self.assertEqual(inp.bundle.envelope.quality.status, 'complete')
        v = self.value(inputs=(inp,))
        self.assertIn('adjusted_price_rejected', v.reason_codes)
        self.assertIsNone(v.nav)

    def test_fx_stale_and_inverse_repeating_fraction_round_only_at_currency_stage(self):
        at = '2024-03-08T15:31:01Z'
        v = self.value(p=projection(as_of=at), req=request(as_of=at, evaluated_at=at, base_currency='KRW'),
            inputs=(market(records=(price_item(), fx_item())),), pol=policy(fx=True, max_price_age_seconds=7200))
        self.assertIn('fx_stale', v.reason_codes)
        self.assertIsNone(v.nav)
        v = self.value(req=request(base_currency='KRW'),
            inputs=(market(records=(price_item(), fx_item(inverse=True, rate='3'))),), pol=policy(fx=True))
        self.assertEqual(v.nav, '341')  # USD1022 / 3 = KRW340.666... -> 341

    def test_raw_evidence_hash_tamper_and_timezone_context_tamper_rejected(self):
        inp = market()
        evidence = inp.bundle.evidence[0]
        object.__setattr__(evidence.revision.payload.close, 'amount', '12')
        with self.assertRaises(ContractError):
            self.value(inputs=(inp,))
        inp = market()
        object.__setattr__(inp.timezone, 'content_sha256', '0' * 64)
        with self.assertRaises(ContractError):
            self.value(inputs=(inp,))

    def test_numeric_inputs_unknown_schema_policy_and_limits_rejected(self):
        for bad in (True, 0.05, 'NaN', '1e-2', '0', '-0.05'):
            with self.assertRaises(ContractError):
                CurrencyQuantum('USD', bad)
        for changes in (dict(schema_version=True), dict(schema_version=2), dict(environment='paper'),
                        dict(rounding='half_up'), dict(stages=('currency_sum', 'holding_native')),
                        dict(max_price_age_seconds=True)):
            with self.assertRaises(ContractError):
                policy(**changes)
        with self.assertRaises(ContractError):
            self.value(inputs=(market(),) * 129)
        many = tuple(replace(HOLDING, instrument_id='stock-' + str(i)) for i in range(129))
        with self.assertRaises(ContractError):
            self.value(p=replace(projection(), holdings=tuple(sorted(many, key=lambda x: x.key))))

    def test_partial_scope_cannot_be_priced(self):
        from quantharbor.domain.market_data import ExpectedEvent
        missing = ExpectedEvent('syn.raw', 'missing-event', END)
        inp = market(scope_changes={'expected': (ExpectedEvent('syn.raw', 'syn.event', END), missing)})
        v = self.value(inputs=(inp,))
        self.assertIn('missing_expected', v.reason_codes)
        self.assertIsNone(v.nav)

    def test_replay_detects_forged_quality_summary_and_state(self):
        inp = market()
        forged = replace(inp.bundle.envelope.quality, reasons=('fake',), status='partial')
        # Even coordinated state/envelope summary edits are checked against receipts/evidence.
        envelope = replace(inp.bundle.envelope, quality=forged)
        summary = replace(inp.bundle.summary, quality=forged)
        bad = replace(inp, bundle=replace(inp.bundle, envelope=envelope, summary=summary))
        with self.assertRaises(ContractError):
            self.value(inputs=(bad,))
        hidden = replace(inp.bundle.state, revisions=replace(inp.bundle.state.revisions, items=()))
        from quantharbor.domain.market_storage import summary_for
        bad_bundle = replace(inp.bundle, state=hidden, summary=summary_for(hidden, inp.bundle.envelope))
        with self.assertRaises(ContractError):
            self.value(inputs=(replace(inp, bundle=bad_bundle),))

    def test_arbitrary_view_and_boolean_input_are_rejected(self):
        from quantharbor.application.market_ingest import select_view
        inp = market()
        view = select_view(inp.bundle.state.revisions, as_of=END, knowledge_cutoff=NOW, rights=rights(),
            at=NOW, dataset_version='dataset-v1', **context())
        self.assertTrue(view.context_validated)
        for bad in (view, True, {'quality': True, 'price': '11'}):
            with self.assertRaises(ContractError):
                self.value(inputs=(bad,))

    def test_actual_select_view_is_called_during_consumption(self):
        from quantharbor.application.market_ingest import select_view
        inp = market()
        with patch('quantharbor.application.valuation.select_view', wraps=select_view) as used:
            self.value(inputs=(inp,))
        self.assertEqual(used.call_count, 1)

    def test_wrong_source_series_context_and_duplicate_datasets(self):
        with self.assertRaises(ContractError):
            self.value(pol=policy(prices=(PriceSelection(KEY, replace(SERIES, source_id='wrong-source')),)))
        self.assertIsNone(self.value(pol=policy(prices=(PriceSelection(KEY, replace(SERIES, series_id='wrong-series')),))).nav)
        inp = market()
        with self.assertRaises(ContractError):
            self.value(inputs=(inp, inp))
        ctx = context()
        with self.assertRaises(ContractError):
            self.value(inputs=(replace(inp, catalog=replace(ctx['catalog'], catalog_version='other-version')),))

    def test_account_time_mode_policy_binding(self):
        for req in (request(account_ref='synthetic-account:wrong'), request(as_of=START),
                    request(knowledge_cutoff=LATER, evaluated_at=LATER), request(valuation_policy_version='wrong'),
                    request(ledger_cursor=0)):
            with self.assertRaises(ContractError):
                self.value(req=req)
        with self.assertRaises(ContractError):
            request(knowledge_cutoff=LATER)

    def test_ambiguous_latest_bar_is_not_arbitrarily_chosen(self):
        other = item(revision(event_id='other-event'), observation_id='other-observation')
        v = self.value(inputs=(market(records=(price_item(), other)),))
        self.assertIn('latest_record_ambiguous', v.reason_codes)
        self.assertIsNone(v.nav)

    def test_explicit_negative_payable_not_absolute_or_subtracted_twice(self):
        p = replace(projection(), cash_balances=tuple(sorted((CashBalance('settled_cash', 'USD', '100'),
            CashBalance('unsettled_receivable', 'USD', '10'), CashBalance('unsettled_payable', 'USD', '-20'),
            CashBalance('trade_clearing', 'USD', '999')), key=lambda x: (x.account, x.currency))))
        self.assertEqual(self.value(p=p).nav, '112')
        invalid = replace(p, cash_balances=(CashBalance('unsettled_payable', 'USD', '20'),))
        self.assertIsNone(self.value(p=invalid).nav)

    def test_mixed_known_and_unknown_rows_and_currency_totals_are_preserved(self):
        unknown = replace(HOLDING, instrument_id='unmapped-stock', amount='7')
        p = replace(projection(), holdings=(HOLDING, unknown), cash_balances=(
            CashBalance('settled_cash', 'KRW', '500'), CashBalance('settled_cash', 'USD', '1000')))
        v = self.value(p=p, req=request(base_currency='KRW'),
            inputs=(market(records=(price_item(), fx_item(rate='1300'))),), pol=policy(fx=True))
        self.assertEqual(tuple(x.position for x in v.holdings), (HOLDING, unknown))
        self.assertEqual([x.native_value for x in v.holdings], ['22', None])
        self.assertEqual([(x.currency, x.known_subtotal, x.base_value) for x in v.native_totals],
            [('KRW', '500', '500'), ('USD', '1022', '1328600')])
        self.assertEqual(v.known_subtotal, '1329100')
        self.assertIsNone(v.nav)

    def test_inconsistent_complete_flag_does_not_hide_invalid_balances(self):
        # Frozen Q20 constructor checks flags/reasons; Q21 also checks the numeric economics.
        p = replace(projection(), holdings=(replace(HOLDING, amount='-1'),))
        v = self.value(p=p)
        self.assertEqual(v.holdings[0].native_value, '-11')
        self.assertIn('economic_balance_invalid', v.reason_codes)
        self.assertIsNone(v.nav)


if __name__ == '__main__':
    unittest.main()
