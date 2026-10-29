"""합성 원장 경계/정정/경제 의미. DB 검증은 별도 고정 runner에서 실행한다."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from decimal import localcontext
import json
import unittest

from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.application.ledger import replay, LedgerState
from quantharbor.domain.ledger import (CashLeg, ContractError, LedgerBaseline, LedgerCompleteness,
    LedgerEvent, PositionDelta, SplitRatio, hash_record, scaled, unscaled, MAX_SEQUENCE)
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from synthetic_ledger import ACCOUNT, T0, T1, T2, T3, T4, baseline, cash_pair, revision, submission, trade


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = SyntheticLedger()

    def seed(self):
        self.ledger.append(baseline(), recorded_at=T0)

    def append_trade(self):
        self.seed()
        return self.ledger.append(trade(), recorded_at=T1)

    def projection(self, *, at=T4, cutoff=T4, **kwargs):
        return self.ledger.replay(ACCOUNT, as_of=at, knowledge_cutoff=cutoff, **kwargs)

    def balance(self, projection, account='settled_cash', currency='USD'):
        return next((x.amount for x in projection.cash_balances if x.account == account and x.currency == currency), '0')

    def assert_economics(self, p, *, settled='1000', payable='-100', clearing='100',
                         holdings=None, reasons=()):
        self.assertEqual({(x.account, x.currency): x.amount for x in p.cash_balances}, {
            ('settled_cash', 'USD'): settled, ('opening_equity', 'USD'): '-1000',
            ('unsettled_payable', 'USD'): payable, ('trade_clearing', 'USD'): clearing})
        self.assertEqual(p.holdings, holdings or (replace(trade().position_deltas[0], amount='20'),))
        self.assertTrue(p.baseline_known)
        self.assertEqual(p.reason_codes, reasons)
        self.assertEqual(p.complete, not reasons)
        self.assertEqual((p.available_cash, p.reserved_cash, p.broker_buy_capacity), (None, None, None))

    def settled_pair(self):
        a = self.append_trade()
        b = self.ledger.append(replace(trade(), source_event_key='execution-b'), recorded_at=T1)
        settle = submission('settle', 'settlement', effective_at=T2, dependency_refs=a.event_ids,
            cash_legs=cash_pair('settled_cash', '-100', 'unsettled_payable'))
        first = self.ledger.append(settle, recorded_at=T2)
        migration = replace(settle, source_revision=2, predecessor_revision=1,
            correction_of=first.event_ids[-1], revision_mode='prospective', effective_at=T4,
            dependency_refs=b.event_ids)
        return settle, migration

    def split_basis(self):
        self.append_trade()
        split = submission('split', 'split', effective_at=T2, cash_legs=(),
            position_deltas=trade().position_deltas, split_ratio=SplitRatio(2, 1))
        self.assertEqual(self.ledger.append(split, recorded_at=T2).status, 'accepted')
        self.assert_economics(self.projection(at=T2, cutoff=T2))

    def test_prospective_settlement_dependency_change_quarantined(self):
        _, migration = self.settled_pair()
        history = self.projection(at=T2, cutoff=T2)
        events = self.ledger.state(ACCOUNT).events
        result = self.ledger.append(migration, recorded_at=T3)
        self.assertEqual((result.status, result.reason, result.event_ids),
            ('quarantined', 'prospective_dependency_change_unsupported', ()))
        self.assertEqual(self.ledger.state(ACCOUNT).events, events)
        self.assertEqual(self.projection(at=T2, cutoff=T2, cursor=history.ledger_cursor), history)
        self.assert_economics(self.projection(at=T3), settled='900', clearing='200')
        self.assert_economics(self.projection(at=T4), settled='900', clearing='200', reasons=('quarantined_observation',))

    def test_prospective_dependency_change_keeps_already_settled_guard(self):
        settle, migration = self.settled_pair()
        self.ledger.append(migration, recorded_at=T3)
        duplicate = self.ledger.append(replace(settle, source_event_key='settle-again', effective_at=T3), recorded_at=T3)
        # A was already paid; B remains payable. A second payment must never produce cash=800.
        for at in (T3, T4):
            self.assert_economics(self.projection(at=at), settled='900', clearing='200', reasons=('quarantined_observation',))
        self.assertEqual((duplicate.status, duplicate.reason, duplicate.event_ids), ('quarantined', 'already_settled', ()))

    def test_prospective_settlement_same_dependency_still_supported(self):
        settle, migration = self.settled_pair()
        same = replace(migration, dependency_refs=settle.dependency_refs)
        self.assertEqual(self.ledger.append(same, recorded_at=T3).status, 'accepted')
        for at in (T3, T4):
            self.assert_economics(self.projection(at=at), settled='900', clearing='200')

    def test_split_baseline_empty_positions_revision_adds_position(self):
        self.split_basis()
        history = self.projection(at=T2, cutoff=T2)
        state = self.ledger.state(ACCOUNT)
        opening = state.events[0]
        changed = replace(baseline(), source_revision=2, predecessor_revision=1,
            correction_of=opening.body.event_id, revision_mode='retroactive',
            position_deltas=(replace(trade().position_deltas[0], amount='5'),))
        self.assertEqual(self.ledger.append(changed, recorded_at=T3).status, 'accepted')
        self.assert_economics(self.projection(), holdings=(replace(trade().position_deltas[0], amount='25'),),
            reasons=('correction_consequences_unresolved',))
        self.assertEqual(self.projection(at=T2, cutoff=T2, cursor=history.ledger_cursor), history)
        self.assert_economics(self.projection(at=T2, cutoff=T2))
        self.assertEqual(self.ledger.state(ACCOUNT).projections[:len(state.projections)], state.projections)

    def test_split_late_original_effective_before_split(self):
        self.split_basis()
        history = self.projection(at=T2, cutoff=T2)
        late = replace(trade(amount='5', cash='-50'), source_event_key='late-original')
        self.assertEqual(self.ledger.append(late, recorded_at=T3).status, 'accepted')
        self.assert_economics(self.projection(), payable='-150', clearing='150',
            holdings=(replace(trade().position_deltas[0], amount='25'),),
            reasons=('correction_consequences_unresolved',))
        self.assertEqual(self.projection(at=T2, cutoff=T2, cursor=history.ledger_cursor), history)
        self.assert_economics(self.projection(at=T2, cutoff=T2))
        self.assert_economics(self.projection(at=T1), payable='-150', clearing='150',
            holdings=(replace(trade().position_deltas[0], amount='15'),))

    def test_split_late_original_effective_at_split(self):
        self.split_basis()
        late = replace(trade(amount='5', cash='-50'), source_event_key='late-at-split', effective_at=T2)
        self.assertEqual(self.ledger.append(late, recorded_at=T3).status, 'accepted')
        self.assert_economics(self.projection(), payable='-150', clearing='150',
            holdings=(replace(trade().position_deltas[0], amount='25'),),
            reasons=('correction_consequences_unresolved',))

    def test_split_late_replacement_adds_previously_absent_position_key(self):
        self.append_trade()
        other_pos = replace(trade().position_deltas[0], instrument_id='other-stock', amount='5')
        other = replace(trade(amount='5', cash='-50'), source_event_key='other-trade', position_deltas=(other_pos,))
        previous = self.ledger.append(other, recorded_at=T1)
        split = submission('split', 'split', effective_at=T2, cash_legs=(),
            position_deltas=trade().position_deltas, split_ratio=SplitRatio(2, 1))
        self.assertEqual(self.ledger.append(split, recorded_at=T2).status, 'accepted')
        changed = revision(other, previous.event_ids[-1], amount='5', cash='-50',
            position_deltas=(replace(trade().position_deltas[0], amount='5'),))
        self.assertEqual(self.ledger.append(changed, recorded_at=T3).status, 'accepted')
        self.assert_economics(self.projection(), payable='-150', clearing='150',
            holdings=(replace(other_pos, amount='0'), replace(trade().position_deltas[0], amount='25')),
            reasons=('correction_consequences_unresolved',))

    def test_split_unaffected_later_effective_original(self):
        self.split_basis()
        later = replace(trade(amount='5', cash='-50'), source_event_key='after-split', effective_at=T3)
        self.assertEqual(self.ledger.append(later, recorded_at=T3).status, 'accepted')
        self.assert_economics(self.projection(), payable='-150', clearing='150',
            holdings=(replace(trade().position_deltas[0], amount='25'),))

    def test_split_unaffected_other_position_identity(self):
        self.split_basis()
        other = replace(trade().position_deltas[0], instrument_id='other-stock', amount='5')
        late = replace(trade(amount='5', cash='-50'), source_event_key='other-late', position_deltas=(other,))
        self.assertEqual(self.ledger.append(late, recorded_at=T3).status, 'accepted')
        self.assert_economics(self.projection(), payable='-150', clearing='150',
            holdings=(other, replace(trade().position_deltas[0], amount='20')))

    def test_full_replacement_ten_to_twelve(self):
        first = self.append_trade()
        correction = revision(trade(), first.event_ids[0])
        result = self.ledger.append(correction, recorded_at=T2)
        self.assertEqual(result.cursor, 4)
        self.assertEqual(self.projection().holdings[0].amount, '12')
        events = self.ledger.state(ACCOUNT).events
        self.assertEqual(tuple(x.body.kind for x in events), ('replacement', 'replacement', 'reversal', 'replacement'))
        self.assertEqual(events[2].body.recorded_at, events[3].body.recorded_at)
        self.assertEqual(self.balance(self.projection(), 'unsettled_payable'), '-120')

    def test_same_source_same_payload_duplicate(self):
        a = self.append_trade()
        b = self.ledger.append(trade(), recorded_at=T3)
        self.assertEqual(b.status, 'duplicate')
        self.assertEqual(b.event_ids, a.event_ids)
        self.assertEqual(len(self.ledger.outbox), 2)

    def test_conflicting_payload_quarantines_without_overwrite(self):
        self.append_trade()
        conflict = self.ledger.append(trade(amount='11'), recorded_at=T2)
        self.assertEqual((conflict.status, conflict.reason), ('quarantined', 'source_collision'))
        self.assertEqual(self.projection().holdings[0].amount, '10')
        self.assertIn('quarantined_observation', self.projection().reason_codes)
        self.assertEqual(self.ledger.append(trade(amount='11'), recorded_at=T3).cursor, conflict.cursor)

    def test_revision_three_continues_chain(self):
        a = self.append_trade()
        s2 = revision(trade(), a.event_ids[-1])
        b = self.ledger.append(s2, recorded_at=T2)
        s3 = revision(s2, b.event_ids[-1], amount='14', cash='-140')
        self.assertEqual(self.ledger.append(s3, recorded_at=T3).status, 'accepted')
        self.assertEqual(self.projection().holdings[0].amount, '14')
        self.assertEqual(self.ledger.append(s2, recorded_at=T4).status, 'duplicate')
        self.assertEqual(self.projection().holdings[0].amount, '14')

    def test_missing_predecessor_quarantine_and_explicit_reprocessing(self):
        self.seed()
        expected_event = 'ledger:861e1e2b6a9b7db1:3'
        s2 = revision(trade(), expected_event)
        q = self.ledger.append(s2, recorded_at=T1)
        self.assertEqual(q.reason, 'predecessor_missing')
        a = self.ledger.append(trade(), recorded_at=T2)
        self.assertEqual(a.event_ids[-1], expected_event)
        self.assertEqual(self.ledger.append(s2, recorded_at=T3).status, 'duplicate')
        self.assertEqual(self.ledger.append(s2, recorded_at=T3, reprocess=True).status, 'accepted')
        self.assertTrue(self.projection().complete)

    def test_wrong_predecessor_reference(self):
        a = self.append_trade()
        bad = revision(trade(), a.event_ids[-1], predecessor_revision=2)
        self.assertEqual(self.ledger.append(bad, recorded_at=T2).reason, 'revision_link_invalid')

    def test_reversal_target_cannot_be_reused_by_next_revision(self):
        a = self.append_trade()
        s2 = revision(trade(), a.event_ids[-1])
        self.ledger.append(s2, recorded_at=T2)
        s3 = revision(s2, a.event_ids[-1], amount='15')
        self.assertEqual(self.ledger.append(s3, recorded_at=T3).reason, 'revision_link_invalid')
        self.assertEqual(self.projection().holdings[0].amount, '12')

    def test_effective_date_move_quarantine(self):
        a = self.append_trade()
        bad = revision(trade(), a.event_ids[-1], effective_at=T0)
        self.assertEqual(self.ledger.append(bad, recorded_at=T2).reason, 'effective_move_unsupported')

    def test_prospective_before_and_after(self):
        a = self.append_trade()
        s2 = revision(trade(), a.event_ids[-1], revision_mode='prospective', effective_at=T3)
        self.ledger.append(s2, recorded_at=T2)
        self.assertEqual(self.projection(at=T2).holdings[0].amount, '10')
        self.assertEqual(self.projection(at=T3).holdings[0].amount, '12')

    def test_not_yet_effective_correction_quarantine(self):
        a = self.append_trade()
        s2 = revision(trade(), a.event_ids[-1], revision_mode='prospective', effective_at=T4)
        b = self.ledger.append(s2, recorded_at=T2)
        s3 = revision(s2, b.event_ids[-1], amount='15')
        self.assertEqual(self.ledger.append(s3, recorded_at=T3).reason, 'uneffective_revision')

    def test_prospective_time_must_be_future(self):
        a = self.append_trade()
        s2 = revision(trade(), a.event_ids[-1], revision_mode='prospective', effective_at=T2)
        self.assertEqual(self.ledger.append(s2, recorded_at=T2).reason, 'prospective_time_invalid')

    def test_as_known_and_restated_knowledge_boundaries(self):
        a = self.append_trade()
        self.ledger.append(revision(trade(), a.event_ids[-1]), recorded_at=T2)
        self.assertEqual(self.projection(at=T1, cutoff=T1).holdings[0].amount, '10')
        p = self.projection(at=T1, cutoff=T2, mode='restated')
        self.assertEqual(p.holdings[0].amount, '12')
        self.assertEqual(p.mode, 'restated')

    def test_future_original_not_advanced(self):
        self.seed()
        self.ledger.append(replace(trade(), effective_at=T4), recorded_at=T1)
        self.assertEqual(self.projection(at=T3).holdings, ())
        self.assertEqual(self.projection(at=T4).holdings[0].amount, '10')

    def test_cursor_inside_correction_bundle_rejected(self):
        a = self.append_trade()
        self.ledger.append(revision(trade(), a.event_ids[-1]), recorded_at=T2)
        with self.assertRaises(ContractError):
            self.projection(cursor=3)
        self.assertEqual(self.projection(cursor=2).holdings[0].amount, '10')

    def test_invalid_cursor_bool_unknown_reducer(self):
        self.seed()
        for kwargs in ({'cursor': True}, {'cursor': 2}, {'mode': 'latest'}, {'reducer_version': 'unknown'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ContractError):
                self.projection(**kwargs)

    def test_recording_clock_cannot_regress(self):
        self.append_trade()
        with self.assertRaises(ContractError):
            self.ledger.append(submission(), recorded_at=T0)
        self.assertEqual(self.ledger.state(ACCOUNT).cursor, 2)

    def test_equal_recording_times_preserve_sequence(self):
        self.seed()
        self.ledger.append(trade(), recorded_at=T0)
        self.assertEqual(self.ledger.state(ACCOUNT).cursor, 2)

    def test_prior_projection_immutable_and_supersedes(self):
        self.seed()
        old = self.ledger.state(ACCOUNT).projections[0]
        old_hash = hash_record(old)
        self.ledger.append(trade(), recorded_at=T1)
        new = self.ledger.state(ACCOUNT).projections[-1]
        self.assertEqual(new.supersedes_projection_id, old.projection_id)
        self.assertEqual(hash_record(self.ledger.state(ACCOUNT).projections[0]), old_hash)

    def test_supersedes_requires_same_account_existing_projection(self):
        self.seed()
        with self.assertRaises(ContractError):
            self.projection(supersedes_projection_id='projection:unknown')

    def test_no_baseline_means_only_accumulated_deltas(self):
        self.ledger.append(trade(), recorded_at=T1)
        p = self.projection()
        self.assertFalse(p.baseline_known)
        self.assertIn('baseline_missing', p.reason_codes)
        self.assertIsNone(p.available_cash)
        self.assertIsNone(p.reserved_cash)
        self.assertIsNone(p.broker_buy_capacity)

    def test_complete_zero_baseline(self):
        s = replace(baseline(), cash_legs=())
        self.assertEqual(self.ledger.append(s, recorded_at=T0).status, 'accepted')
        self.assertTrue(self.projection().complete)

    def test_late_baseline_quarantine(self):
        self.ledger.append(trade(), recorded_at=T1)
        self.assertEqual(self.ledger.append(baseline(), recorded_at=T2).reason, 'baseline_requires_first')

    def test_baseline_full_replacement_keeps_single_complete_baseline(self):
        first = self.ledger.append(baseline(), recorded_at=T0)
        revised = replace(baseline(), source_revision=2, predecessor_revision=1,
            correction_of=first.event_ids[-1], revision_mode='retroactive',
            cash_legs=cash_pair('settled_cash', '1200', 'opening_equity'))
        self.assertEqual(self.ledger.append(revised, recorded_at=T1).status, 'accepted')
        self.assertTrue(self.projection().baseline_known)
        self.assertTrue(self.projection().complete)
        self.assertEqual(self.balance(self.projection()), '1200')

    def test_incomplete_baseline_quarantine(self):
        s = replace(baseline(), baseline=LedgerBaseline(True, False, 'entire_account'))
        self.assertEqual(self.ledger.append(s, recorded_at=T0).reason, 'baseline_incomplete')

    def test_settlement_moves_cash_once_and_preserves_quantity(self):
        a = self.append_trade()
        settle = submission('settle', 'settlement', effective_at=T2, dependency_refs=a.event_ids,
            cash_legs=cash_pair('settled_cash', '-100', 'unsettled_payable'))
        result = self.ledger.append(settle, recorded_at=T2)
        self.assertEqual(result.status, 'accepted')
        self.assertEqual(self.balance(self.projection()), '900')
        self.assertEqual(self.balance(self.projection(), 'unsettled_payable'), '0')
        self.assertEqual(self.projection().holdings[0].amount, '10')
        self.assertEqual(self.ledger.append(settle, recorded_at=T3).status, 'duplicate')
        twice = replace(settle, source_event_key='settle-again')
        self.assertEqual(self.ledger.append(twice, recorded_at=T3).reason, 'already_settled')

    def test_sale_receivable_is_not_settled_cash(self):
        self.seed()
        sale = replace(trade(), position_deltas=(replace(trade().position_deltas[0], amount='-2'),),
                       cash_legs=cash_pair('unsettled_receivable', '25', 'trade_clearing', basis='trade'))
        a = self.ledger.append(sale, recorded_at=T1)
        self.assertEqual(self.balance(self.projection()), '1000')
        self.assertEqual(self.balance(self.projection(), 'unsettled_receivable'), '25')
        settle = submission('sale-settle', 'settlement', effective_at=T2, dependency_refs=a.event_ids,
            cash_legs=cash_pair('settled_cash', '25', 'unsettled_receivable'))
        self.assertEqual(self.ledger.append(settle, recorded_at=T2).status, 'accepted')
        self.assertEqual(self.balance(self.projection()), '1025')
        self.assertIn('economic_balance_invalid', self.projection().reason_codes)  # opening holding absent

    def test_settlement_rejects_quantity_and_wrong_amount(self):
        a = self.append_trade()
        settle = submission('settle', 'settlement', effective_at=T2, dependency_refs=a.event_ids,
            cash_legs=cash_pair('settled_cash', '-90', 'unsettled_payable'))
        self.assertEqual(self.ledger.append(settle, recorded_at=T2).reason, 'settlement_shape')
        settle = replace(settle, source_event_key='with-quantity', position_deltas=trade().position_deltas)
        self.assertEqual(self.ledger.append(settle, recorded_at=T2).reason, 'unexpected_position_delta')

    def test_settlement_revision_reverses_and_replaces_once(self):
        a = self.append_trade()
        settle = submission('settle', 'settlement', effective_at=T2, dependency_refs=a.event_ids,
            cash_legs=cash_pair('settled_cash', '-100', 'unsettled_payable'))
        b = self.ledger.append(settle, recorded_at=T2)
        revised = replace(settle, source_revision=2, predecessor_revision=1, correction_of=b.event_ids[-1], revision_mode='retroactive', evidence_refs=('synthetic-evidence:revised',))
        self.assertEqual(self.ledger.append(revised, recorded_at=T3).status, 'accepted')
        self.assertEqual(self.balance(self.projection()), '900')
        self.assertEqual(self.ledger.append(revised, recorded_at=T4).status, 'duplicate')

    def test_correction_marks_settlement_consequences_incomplete(self):
        a = self.append_trade()
        settle = submission('settle', 'settlement', effective_at=T2, dependency_refs=a.event_ids,
            cash_legs=cash_pair('settled_cash', '-100', 'unsettled_payable'))
        self.ledger.append(settle, recorded_at=T2)
        self.ledger.append(revision(trade(), a.event_ids[-1]), recorded_at=T3)
        p = self.projection()
        self.assertEqual(p.holdings[0].amount, '12')
        self.assertFalse(p.complete)
        self.assertIn('correction_consequences_unresolved', p.reason_codes)

    def test_linked_settlement_revision_can_resolve_consequences(self):
        a = self.append_trade()
        settle = submission('settle', 'settlement', effective_at=T2, dependency_refs=a.event_ids,
            cash_legs=cash_pair('settled_cash', '-100', 'unsettled_payable'))
        b = self.ledger.append(settle, recorded_at=T2)
        c = self.ledger.append(revision(trade(), a.event_ids[-1]), recorded_at=T3)
        revised = replace(settle, source_revision=2, predecessor_revision=1, correction_of=b.event_ids[-1],
            revision_mode='retroactive', dependency_refs=(c.event_ids[-1],),
            cash_legs=cash_pair('settled_cash', '-120', 'unsettled_payable'))
        self.assertEqual(self.ledger.append(revised, recorded_at=T4).status, 'accepted')
        self.assertTrue(self.projection().complete)
        self.assertEqual(self.balance(self.projection()), '880')

    def test_fee_tax_dividend_and_external_flow_accounts(self):
        self.seed()
        for kind, amount, contra in (('fee', '-1', 'fee_expense'), ('tax', '-2', 'tax_expense'),
            ('dividend', '3', 'dividend_income'), ('deposit', '4', 'external_flow'), ('withdrawal', '-5', 'external_flow')):
            s = submission(kind, kind, cash_legs=cash_pair('settled_cash', amount, contra))
            self.assertEqual(self.ledger.append(s, recorded_at=T1).status, 'accepted')
        self.assertEqual(self.balance(self.projection()), '999')
        self.assertEqual(self.balance(self.projection(), 'external_flow'), '1')

    def test_fx_balanced_per_currency(self):
        self.seed()
        s = submission('fx', 'fx', cash_legs=cash_pair('settled_cash', '-1300', 'fx_clearing', currency='KRW') +
            cash_pair('settled_cash', '1', 'fx_clearing'))
        self.assertEqual(self.ledger.append(s, recorded_at=T1).status, 'accepted')
        self.assertEqual(self.balance(self.projection()), '1001')
        self.assertIn('economic_balance_invalid', self.projection().reason_codes)

    def test_cross_currency_offsets_quarantine(self):
        s = submission(cash_legs=(CashLeg('settled_cash', 'USD', '100', 'settlement'),
                                 CashLeg('external_flow', 'KRW', '-100', 'settlement')))
        self.assertEqual(self.ledger.append(s, recorded_at=T1).reason, 'unbalanced_journal')

    def test_unknown_costs_quarantine_instead_of_zero(self):
        s = replace(trade(), completeness=LedgerCompleteness(True, False, True))
        self.assertEqual(self.ledger.append(s, recorded_at=T1).reason, 'incomplete_input')
        self.assertEqual(self.projection().holdings, ())

    def test_unsupported_semantics_evidence_and_zero(self):
        for s, reason in ((replace(submission(), event_type='unsupported'), 'unsupported_semantics'),
            (replace(submission(), evidence_refs=()), 'evidence_missing'),
            (submission(amount='0'), 'zero_leg')):
            with self.subTest(reason=reason):
                self.assertEqual(SyntheticLedger().append(s, recorded_at=T1).reason, reason)

    def test_split_ratio_with_exact_holdings(self):
        self.append_trade()
        split = submission('split', 'split', effective_at=T2, cash_legs=(),
            position_deltas=trade().position_deltas, split_ratio=SplitRatio(2, 1))
        self.assertEqual(self.ledger.append(split, recorded_at=T2).status, 'accepted')
        self.assertEqual(self.projection().holdings[0].amount, '20')

    def test_split_dependency_correction_marks_incomplete(self):
        a = self.append_trade()
        split = submission('split', 'split', effective_at=T2, cash_legs=(),
            position_deltas=trade().position_deltas, split_ratio=SplitRatio(2, 1))
        self.ledger.append(split, recorded_at=T2)
        self.ledger.append(revision(trade(), a.event_ids[-1]), recorded_at=T3)
        self.assertIn('correction_consequences_unresolved', self.projection().reason_codes)

    def test_split_revision_explicitly_quarantined(self):
        self.append_trade()
        split = submission('split', 'split', effective_at=T2, cash_legs=(),
            position_deltas=trade().position_deltas, split_ratio=SplitRatio(2, 1))
        first = self.ledger.append(split, recorded_at=T2)
        revised = replace(split, source_revision=2, predecessor_revision=1, revision_mode='retroactive',
                          correction_of=first.event_ids[-1])
        self.assertEqual(self.ledger.append(revised, recorded_at=T3).reason, 'split_revision_unsupported')

    def test_split_unknown_basis_or_ratio_quarantine(self):
        split = submission('split', 'split', effective_at=T2, cash_legs=(),
            position_deltas=trade().position_deltas, split_ratio=SplitRatio(2, 1))
        self.assertEqual(self.ledger.append(split, recorded_at=T2).reason, 'split_basis_unknown')
        self.ledger = SyntheticLedger()
        self.append_trade()
        self.assertEqual(self.ledger.append(replace(split, split_ratio=SplitRatio(3, 1)), recorded_at=T2).reason, 'split_ratio_mismatch')

    def test_rollback_each_append_boundary(self):
        for boundary in ('events', 'projection', 'outbox'):
            with self.subTest(boundary=boundary):
                ledger = SyntheticLedger()
                ledger.append(baseline(), recorded_at=T0)
                before = ledger.state(ACCOUNT)
                with self.assertRaises(ContractError):
                    ledger.append(trade(), recorded_at=T1, fail_at=boundary)
                self.assertEqual(ledger.state(ACCOUNT), before)
                self.assertEqual(len(ledger.outbox), 1)

    def test_consumer_rollback_ack_loss_collision(self):
        self.seed()
        m = self.ledger.outbox[0]
        with self.assertRaises(ContractError):
            self.ledger.consume('consumer', m.message_id, m.payload_hash, fail_before_commit=True)
        self.assertEqual(self.ledger.consumer_cursor('consumer', ACCOUNT), 0)
        self.assertEqual(self.ledger.consume('consumer', m.message_id, m.payload_hash), 'accepted')
        self.assertEqual(self.ledger.consume('consumer', m.message_id, m.payload_hash), 'duplicate')
        self.assertEqual(self.ledger.consume('consumer', m.message_id, '0'*64), 'collision')
        self.ledger.acknowledge(m.message_id)
        self.assertEqual(self.ledger.consumer_cursor('consumer', ACCOUNT), 1)

    def test_consumer_out_of_order_does_not_regress(self):
        self.append_trade()
        for m in reversed(self.ledger.outbox):
            self.ledger.consume('consumer', m.message_id, m.payload_hash)
        self.assertEqual(self.ledger.consumer_cursor('consumer', ACCOUNT), 2)

    def test_concurrent_identical_append(self):
        self.seed()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.ledger.append(trade(), recorded_at=T1), range(2)))
        self.assertEqual(sorted(x.status for x in results), ['accepted', 'duplicate'])
        self.assertEqual(self.projection().holdings[0].amount, '10')

    def test_exact_decimal_context_and_limits(self):
        value = '99999999999999999999.999999999999999999'
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(unscaled(scaled(value)), value)
            self.assertEqual(unscaled(scaled(value) - scaled('0.000000000000000001')), '99999999999999999999.999999999999999998')
            self.ledger.append(submission(amount=value), recorded_at=T0)
            self.assertEqual(self.balance(self.projection()), value)
        with self.assertRaises(ContractError):
            self.ledger.append(submission('extra', amount='0.000000000000000001'), recorded_at=T1)
        self.assertEqual(self.ledger.state(ACCOUNT).cursor, 1)

    def test_sequence_exhaustion_rollback(self):
        self.ledger._states[ACCOUNT] = LedgerState(ACCOUNT, cursor=MAX_SEQUENCE)
        with self.assertRaises(ContractError):
            self.ledger.append(submission(), recorded_at=T0)
        self.assertEqual(self.ledger.state(ACCOUNT).cursor, MAX_SEQUENCE)

    def test_wrong_environment_account_or_unknown_enum(self):
        for kwargs in ({'environment': 'paper'}, {'account_ref': 'real-account'}, {'event_type': 'mystery'},
                       {'source_revision': True}, {'source_revision': 0}, {'schema_version': 2}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ContractError):
                replace(submission(), **kwargs)

    def test_invalid_decimals_and_nested_types(self):
        for amount in ('1e2', '01', '+1', 'NaN', 'Infinity', '1.0000000000000000001', '100000000000000000000', 1.2, True):
            with self.subTest(amount=amount), self.assertRaises(ContractError):
                CashLeg('settled_cash', 'USD', amount, 'settlement')
        for kwargs in ({'cash_legs': []}, {'completeness': {'complete': True}},
                       {'evidence_refs': ('x',)*33}, {'cash_legs': cash_pair('settled_cash', '1', 'settled_cash')}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ContractError):
                replace(submission(), **kwargs)

    def test_invalid_times_and_mapping(self):
        for time in ('2026-10-01T00:00:00', '2026-10-01T00:00:00.0000001Z', '1999-01-01T00:00:00Z', '2101-01-01T00:00:00Z'):
            with self.subTest(time=time), self.assertRaises(ContractError):
                replace(submission(), effective_at=time)
        with self.assertRaises(ContractError):
            replace(trade(), mapping_version='different')

    def test_canonical_roundtrip_hash_normalization(self):
        s = submission(amount='1.000')
        normalized = replace(s, effective_at='2026-10-01T09:00:00+09:00')
        self.assertEqual(hash_record(normalized), hash_record(s))
        wrapper = CanonicalPayload('SyntheticLedgerSubmission', 1, 'synthetic', s)
        self.assertEqual(parse_payload(canonical_bytes(wrapper)), wrapper)
        self.seed()
        for p in (self.projection(), self.ledger.state(ACCOUNT).events[0].body):
            wire = canonical_bytes(CanonicalPayload(type(p).__name__, 1, 'synthetic', p))
            self.assertEqual(parse_payload(wire).payload, p)

    def test_wire_unknown_duplicate_missing_null_fields(self):
        wrapper = json.loads(canonical_bytes(CanonicalPayload('SyntheticLedgerSubmission', 1, 'synthetic', submission())))
        for mutate in (lambda x: x['payload'].update(extra=1), lambda x: x['payload'].pop('correction_of'),
                       lambda x: x['payload'].update(source_revision=None), lambda x: x['payload']['cash_legs'][0].update(amount=1)):
            altered = json.loads(json.dumps(wrapper))
            mutate(altered)
            with self.assertRaises(ContractError):
                parse_payload(json.dumps(altered))
        raw = json.dumps(wrapper).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1', 1)
        with self.assertRaises(ContractError):
            parse_payload(raw)

    def test_event_integrity_detects_hash_and_body_forgery(self):
        self.seed()
        e = self.ledger.state(ACCOUNT).events[0]
        with self.assertRaises(ContractError):
            replace(e, payload_hash='0'*64)
        with self.assertRaises(ContractError):
            replace(e.body, submission_hash='0'*64)
        forged = object.__new__(LedgerEvent)
        object.__setattr__(forged, 'body', e.body)
        object.__setattr__(forged, 'payload_hash', '0'*64)
        object.__setattr__(forged, 'canonicalization_version', 'qh-canonical-json-v1')
        state = self.ledger.state(ACCOUNT)
        state.events[0] = forged
        with self.assertRaises(ContractError):
            replay(state, as_of=T4, knowledge_cutoff=T4)

    def test_bounded_event_and_json_limits(self):
        # 32 evidence refs * 128 chars and 32 legs are accepted structurally; 33 is rejected.
        refs = tuple('r' + str(i).zfill(2) + 'x'*125 for i in range(32))
        self.assertEqual(len(replace(submission(), evidence_refs=refs).evidence_refs), 32)
        with self.assertRaises(ContractError):
            replace(submission(), evidence_refs=refs + ('extra',))

    def test_schema_validation_rejects_forged_nested_object(self):
        s = submission()
        object.__setattr__(s.completeness, 'complete', 1)
        with self.assertRaises(ContractError):
            self.ledger.append(s, recorded_at=T0)


if __name__ == '__main__':
    unittest.main()
