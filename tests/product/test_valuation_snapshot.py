"""Canonical 복원·입력 결속·선행 snapshot·불변 저장·시점 재생 검증."""
from dataclasses import asdict, replace
import json
import unittest
from unittest.mock import patch

from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
from quantharbor.application.valuation import build_snapshot, reconcile, value_projection
from quantharbor.domain.ledger import CashBalance, hash_record
from quantharbor.domain.primitives import ContractError, utc_instant
from quantharbor.domain.market_data import item_ref
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.valuation import BalanceScope
from synthetic_ledger import cash_pair, submission
from synthetic_market import END, NOW, START, LATER, bar, item, price, revision, rights
from synthetic_valuation import (ACCOUNT, HOLDING, KEY, ledger, market, policy, projection,
                                reconciliation_policy, request, statement, price_item,
                                fx_item, unchecked_bytes, reseal_snapshot)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.p, self.req = projection(), request()
        self.inputs, self.pol, self.rpol = (market(),), policy(), reconciliation_policy()
        self.repo = SyntheticSnapshotRepository()

    def build(self, **changes):
        args = dict(projection=self.p, request=self.req, market_inputs=self.inputs,
                    policy=self.pol, reconciliation_policy=self.rpol, repository=self.repo, statement=statement())
        return build_snapshot(**(args | changes))

    def encoded(self, snapshot):
        return canonical_bytes(CanonicalPayload('PortfolioSnapshot', 1, 'synthetic', snapshot))

    def assert_snapshot_rejected(self, snapshot):
        for boundary in ('constructor', 'canonical', 'append'):
            with self.subTest(boundary=boundary), self.assertRaises(ContractError):
                if boundary == 'constructor':
                    replace(snapshot)
                elif boundary == 'canonical':
                    parse_payload(unchecked_bytes(snapshot))
                else:
                    repo = SyntheticSnapshotRepository()
                    try:
                        repo.append(snapshot)
                    finally:
                        self.assertFalse(repo._snapshots, 'rejected append must not retain snapshot bytes')

    def two_prices(self):
        old_end = '2024-03-08T14:30:30Z'
        old_price = price('10')
        old = item(revision(event_id='old.event', effective_at=old_end, published_at=old_end,
            payload=bar(ends_at=old_end, open=old_price, high=old_price, low=old_price, close=old_price)),
            observation_id='obs.old')
        return old, price_item()

    def test_v1_builder_refuses_raw_payload_without_store_at_consumption(self):
        repo = SyntheticSnapshotRepository()
        with self.assertRaises(ContractError):
            self.build(repository=repo, market_inputs=(market(current_rights=rights(purposes=('research',))),))
        self.assertFalse(repo._snapshots)

    def test_v1_blocked_inputs_with_no_selected_payload_remain_incomplete(self):
        for grant in (rights(revoked_at=NOW), rights(valid_to=NOW)):
            with self.subTest(grant=grant):
                s = self.build(market_inputs=(market(current_rights=grant),))
                self.assertIsNone(s.valuation.nav)
                self.assertFalse(s.valuation.market_proofs[0].selected)
                self.assertEqual(parse_payload(self.encoded(s)).payload, s)

    def test_v1_unknown_valuation_cannot_store_selected_raw_payload_directly(self):
        s = self.build()
        v = value_projection(self.p, self.req, (market(current_rights=rights(purposes=('research',))),), self.pol)
        self.assertIsNone(v.nav)
        self.assertTrue(v.market_proofs[0].selected)
        object.__setattr__(s, 'valuation', v)
        self.assert_snapshot_rejected(reseal_snapshot(s))

    def test_v1_storage_permission_is_checked_at_evaluated_at(self):
        req = replace(self.req, evaluated_at=LATER)
        s = self.build(request=req)
        v = value_projection(self.p, req, (market(current_rights=rights(purposes=('research',))),), self.pol)
        object.__setattr__(s, 'valuation', v)
        proof = v.market_proofs[0]
        object.__setattr__(proof, 'rights', rights(revoked_at=LATER))
        self.assert_snapshot_rejected(reseal_snapshot(s))

    def test_v2_old_price_recomputed_nav_and_manifest_rejected(self):
        old, new = self.two_prices()
        s = self.build(market_inputs=(market(records=(old, new)),))
        self.assertEqual(s.valuation.nav, '1022')
        self.assertEqual(parse_payload(self.encoded(s)).payload, s)
        v = s.valuation
        holding = replace(v.holdings[0], price=old.revision.payload.close, price_ref=item_ref(old), native_value='20')
        object.__setattr__(v, 'holdings', (holding,))
        object.__setattr__(v, 'native_totals', (replace(v.native_totals[0], known_subtotal='1020', base_value='1020'),))
        object.__setattr__(v, 'known_subtotal', '1020')
        object.__setattr__(v, 'nav', '1020')
        self.assert_snapshot_rejected(reseal_snapshot(s))

    def test_v2_ambiguous_latest_candidate_cannot_be_claimed_complete(self):
        s = self.build()
        proof = s.valuation.market_proofs[0]
        duplicate = price_item(event_id='other.event')
        object.__setattr__(proof, 'selected', tuple(sorted(proof.selected + (duplicate,), key=lambda x: x.revision.key)))
        object.__setattr__(proof, 'records', tuple(sorted(proof.records + (item_ref(duplicate),), key=lambda x: x.key)))
        self.assert_snapshot_rejected(reseal_snapshot(s))

    def test_v2_observation_rights_ref_mismatch_rejected(self):
        s = self.build()
        proof = s.valuation.market_proofs[0]
        object.__setattr__(proof, 'rights', rights(rights_ref='other.rights'))
        self.assertNotEqual(proof.selected[0].observation.rights_ref, proof.rights.rights_ref)
        self.assert_snapshot_rejected(reseal_snapshot(s))

    def test_v2_fx_latest_candidate_and_valid_raw_fx_roundtrip(self):
        old = fx_item(rate='1200')
        old_end = '2024-03-08T14:30:30Z'
        old = item(replace(old.revision, event_id='fx.old', effective_at=old_end, published_at=old_end,
            payload=replace(old.revision.payload, fx=replace(old.revision.payload.fx, as_of=old_end))),
            observation_id='obs.fx.old')
        s = self.build(request=replace(self.req, base_currency='KRW'), policy=policy(fx=True),
            market_inputs=(market(records=(price_item(), old, fx_item())),))
        self.assertEqual(s.valuation.nav, '1328600')
        self.assertEqual(parse_payload(self.encoded(s)).payload, s)
        v = s.valuation
        total = replace(v.native_totals[0], fx=old.revision.payload.fx, fx_ref=item_ref(old), base_value='1226400')
        object.__setattr__(v, 'native_totals', (total,))
        object.__setattr__(v, 'known_subtotal', '1226400')
        object.__setattr__(v, 'nav', '1226400')
        self.assert_snapshot_rejected(reseal_snapshot(s))

    def test_full_data_v1_and_roundtrip_and_deterministic_replay(self):
        snapshot = self.build()
        self.assertEqual(snapshot, parse_payload(self.encoded(snapshot)).payload)
        self.assertEqual(self.build(), snapshot)
        self.assertEqual(snapshot.snapshot_id, 'snapshot:' + hash_record(snapshot.input_manifest))
        self.assertNotEqual(hash_record(snapshot), hash_record(snapshot.input_manifest))
        self.assertEqual(snapshot.reconciliation, 'matched')
        self.assertEqual(snapshot.valuation_status, 'complete')
        self.assertEqual(snapshot.open_orders_status, 'unknown')
        self.assertEqual(snapshot.open_order_refs, ())
        self.assertIsNone(snapshot.supersedes_snapshot_id)
        self.assertEqual({x.kind for x in snapshot.data_refs},
                         {'ledger', 'request', 'valuation_policy', 'reconciliation_policy', 'market', 'statement'})
        self.assertEqual(snapshot.ledger_schema_version, 1)
        self.assertIn('synthetic-ledger-v1', self.encoded(snapshot).decode())
        self.assertIn('revision_hash', self.encoded(snapshot).decode())
        self.assertIn('evidence_index_hash', self.encoded(snapshot).decode())

    def test_canonical_tamper_rejects_nav_sum_cash_status_identity_and_hashes(self):
        snapshot = self.build()
        raw = json.loads(self.encoded(snapshot))
        def changed(*path, value):
            copied = json.loads(json.dumps(raw))
            target = copied['payload']
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            return json.dumps(copied)
        cases = ((('valuation', 'nav'), '1023'), (('valuation', 'known_subtotal'), '1023'),
            (('valuation', 'complete'), False),
            (('valuation', 'holdings', 0, 'native_value'), '23'),
            (('valuation', 'cash_by_currency', 0, 'economic_cash'), '999'),
            (('valuation', 'native_totals', 0, 'known_subtotal'), '1023'),
            (('valuation', 'projection_hash'), '0' * 64),
            (('valuation', 'policy_hash'), '0' * 64),
            (('valuation', 'request_hash'), '0' * 64),
            (('snapshot_id',), 'snapshot:' + '0' * 64),
            (('account_ref',), 'synthetic-account:other'),
            (('reconciliation',), 'incomplete'),
            (('open_orders_status',), 'complete'),
            (('ledger_cursor',), True), (('schema_version',), 2),
            (('valuation', 'holdings', 0, 'price', 'amount'), '12'),
            (('valuation', 'holdings', 0, 'price_ref', 'revision_hash'), '0' * 64),
            (('reconciliation_details', 'differences', 0, 'difference'), '1'),
            (('reconciliation_details', 'scope_matched'), False),
            (('input_manifest', 'valuation_hash'), '0' * 64))
        for path, value in cases:
            with self.subTest(path=path), self.assertRaises(ContractError):
                parse_payload(changed(*path, value=value))

    def test_canonical_unknown_fields_float_bool_and_duplicates_rejected(self):
        raw = json.loads(self.encoded(self.build()))
        for field, value in (('extra_field', 'x'), ('ledger_cursor', 1.5), ('schema_version', True)):
            modified = json.loads(json.dumps(raw))
            modified['payload'][field] = value
            with self.assertRaises(ContractError):
                parse_payload(json.dumps(modified))
        with self.assertRaises(ContractError):
            parse_payload(self.encoded(self.build()).decode().replace('"schema_version":1', '"schema_version":1,"schema_version":1', 1))

    def test_supplied_result_account_policy_request_projection_bindings(self):
        v = value_projection(self.p, self.req, self.inputs, self.pol)
        r = reconcile(self.p, statement(), self.req, self.rpol)
        self.assertEqual(self.build(valuation=v, reconciliation=r), self.build())
        other_req = replace(self.req, request_id='other-request')
        foreign = value_projection(self.p, other_req, self.inputs, self.pol)
        with self.assertRaises(ContractError):
            self.build(valuation=foreign)
        foreign_r = reconcile(self.p, statement(), other_req, self.rpol)
        with self.assertRaises(ContractError):
            self.build(reconciliation=foreign_r)
        with self.assertRaises(ContractError):
            self.build(broker_inspection=True)
        # Python internals cannot bypass reconstruction at the builder.
        forged = value_projection(self.p, self.req, self.inputs, self.pol)
        object.__setattr__(forged, 'nav', '9999')
        with self.assertRaises(ContractError):
            self.build(valuation=forged)

    def test_valuation_and_reconciliation_are_independent_axes(self):
        s = self.build(statement=statement(holdings=(replace(HOLDING, amount='3'),)))
        self.assertEqual((s.valuation_status, s.reconciliation), ('complete', 'mismatch'))
        s = self.build(market_inputs=())
        self.assertEqual((s.valuation_status, s.reconciliation), ('incomplete', 'matched'))
        self.assertIsNone(s.valuation.nav)

    def test_subset_not_promoted_to_snapshot_match(self):
        subset = BalanceScope('subset', (KEY,), (), ('holdings',))
        s = self.build(request=replace(self.req, scope=subset), statement=statement(cash=(),
            source_changes={'scope': subset}, requested_scope=subset))
        self.assertEqual(s.reconciliation_details.status, 'matched')
        self.assertEqual(s.reconciliation, 'incomplete')

    def test_append_get_bind_environment_account_and_immutable_bytes(self):
        s = self.build()
        fetched = self.repo.get(s.snapshot_id, environment='synthetic', account_ref=ACCOUNT)
        self.assertEqual(s, fetched)
        object.__setattr__(fetched, 'valuation_status', 'fake')
        self.assertEqual(self.repo.get(s.snapshot_id, environment='synthetic', account_ref=ACCOUNT).valuation_status, 'complete')
        for env, account in (('paper', ACCOUNT), ('synthetic', 'synthetic-account:other')):
            with self.assertRaises(ContractError):
                self.repo.get(s.snapshot_id, environment=env, account_ref=account)

    def test_repository_capacity_collision_and_idempotence(self):
        repo = SyntheticSnapshotRepository(capacity=1)
        s = self.build(repository=repo)
        self.assertEqual(repo.append(s), s)
        with self.assertRaises(ContractError):
            self.build(repository=repo, request=replace(self.req, request_id='different-request'))
        # Simulate storage corruption: even an ID hit must compare the canonical hash and bytes.
        repo._snapshots[s.snapshot_id] = ('0' * 64, self.encoded(s))
        with self.assertRaises(ContractError):
            repo.append(s)
        for value in (0, 129, True):
            with self.assertRaises(ContractError):
                SyntheticSnapshotRepository(capacity=value)

    def test_missing_actual_predecessor_rejected_at_builder_and_repository(self):
        prior = self.build()
        request2 = replace(self.req, request_id='new', supersedes_snapshot_id=prior.snapshot_id)
        next_snapshot = self.build(request=request2)
        self.assertEqual(next_snapshot.supersedes_snapshot_id, prior.snapshot_id)
        fresh = SyntheticSnapshotRepository()
        with self.assertRaises(ContractError):
            self.build(request=request2, repository=fresh)
        with self.assertRaises(ContractError):
            fresh.append(next_snapshot)
        with self.assertRaises(ContractError):
            self.build(request=replace(request2, supersedes_snapshot_id='missing-snapshot'))

    def test_predecessor_wrong_base_scope_account_and_asof_rejected(self):
        prior = self.build()
        req = replace(self.req, request_id='new', supersedes_snapshot_id=prior.snapshot_id)
        for altered in (replace(req, base_currency='KRW'),
                        replace(req, scope=BalanceScope('subset', (KEY,), (), ('holdings',)))):
            with self.assertRaises(ContractError):
                self.build(request=altered, statement=None)
        p = replace(self.p, as_of=START)
        with self.assertRaises(ContractError):
            self.build(projection=p, request=replace(req, as_of=START), statement=None)
        p = replace(self.p, account_ref='synthetic-account:other')
        with self.assertRaises(ContractError):
            self.build(projection=p, request=replace(req, account_ref=p.account_ref), statement=None)

    def test_restated_requires_later_cutoff_and_actual_predecessor(self):
        prior = self.build()
        req = replace(self.req, projection_mode='restated', knowledge_cutoff=LATER, evaluated_at=LATER,
            original_cutoff=NOW, supersedes_snapshot_id=prior.snapshot_id)
        p = replace(self.p, mode='restated', knowledge_cutoff=LATER)
        s = self.build(projection=p, request=req)
        self.assertEqual(s.projection_mode, 'restated')
        self.assertNotEqual(s.snapshot_id, prior.snapshot_id)
        self.assertEqual(self.repo.get(prior.snapshot_id, environment='synthetic', account_ref=ACCOUNT), prior)
        with self.assertRaises(ContractError):
            self.build(projection=p, request=replace(req, original_cutoff=START))
        with self.assertRaises(ContractError):
            replace(self.req, projection_mode='restated', original_cutoff=NOW)

    def test_actual_q20_late_revision_as_known_and_restated(self):
        store = ledger()
        old = store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW)
        old_snapshot = self.build(projection=old)
        opening = store.state(ACCOUNT).events[0]
        revised = replace(opening.body.submission, source_revision=2, predecessor_revision=1,
            correction_of=opening.body.event_id, revision_mode='retroactive',
            cash_legs=cash_pair('settled_cash', '1200', 'opening_equity'))
        self.assertEqual(store.append(revised, recorded_at=LATER).status, 'accepted')
        as_known = store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW, cursor=old.ledger_cursor)
        self.assertEqual(value_projection(as_known, self.req, self.inputs, self.pol).nav, '1022')
        restated = store.replay(ACCOUNT, as_of=END, knowledge_cutoff=LATER, mode='restated')
        req = replace(self.req, projection_mode='restated', knowledge_cutoff=LATER, evaluated_at=LATER,
            original_cutoff=NOW, supersedes_snapshot_id=old_snapshot.snapshot_id, ledger_cursor=restated.ledger_cursor)
        s = self.build(projection=restated, request=req, statement=statement(cash=(CashBalance('settled_cash', 'USD', '1200'),),
            source_changes={'observed_at': LATER, 'ingested_at': LATER}))
        self.assertEqual(s.valuation.nav, '1222')
        self.assertEqual(s.reconciliation, 'matched')
        self.assertEqual(old_snapshot.valuation.nav, '1022')

    def test_future_settlement_within_cursor_does_not_change_past_nav(self):
        store = ledger(holdings=())
        buy = replace(submission('buy', 'trade', effective_at=END), account_ref=ACCOUNT,
            cash_legs=cash_pair('unsettled_payable', '-22', 'trade_clearing', basis='trade'), position_deltas=(HOLDING,))
        accepted = store.append(buy, recorded_at=END)
        future = replace(submission('settle', 'settlement', effective_at=LATER), account_ref=ACCOUNT,
            cash_legs=cash_pair('settled_cash', '-22', 'unsettled_payable'), dependency_refs=accepted.event_ids)
        self.assertEqual(store.append(future, recorded_at=NOW).status, 'accepted')
        past = store.replay(ACCOUNT, as_of=END, knowledge_cutoff=NOW)
        s = self.build(projection=past, request=replace(self.req, ledger_cursor=past.ledger_cursor), statement=None)
        self.assertEqual(s.valuation.nav, '1000')
        self.assertEqual(s.cash_by_currency[0].settled_cash, '1000')
        self.assertEqual(s.cash_by_currency[0].unsettled_payable, '-22')
        self.assertEqual(s.ledger_cursor, 3)

    def test_canonical_size_limit_is_not_truncation(self):
        s = self.build()
        with self.assertRaises(ContractError):
            parse_payload(self.encoded(s) + b' ' * 65536)

    def test_complete_empty_kis_bridge_snapshot_stays_unresolved(self):
        import synthetic_broker as kis
        kreq = kis.request('us_balance')
        batch = kis.run((kis.page(kreq, data=kis.body('us_balance', empty=True)),), req=kreq)
        self.assertTrue(batch.result.complete)
        req = replace(self.req, account_ref=kreq.binding.account_ref, as_of=kis.START,
            knowledge_cutoff=kis.NOW, evaluated_at=kis.NOW)
        p = replace(self.p, account_ref=req.account_ref, as_of=req.as_of, knowledge_cutoff=req.knowledge_cutoff)
        s = self.build(projection=p, request=req, market_inputs=(), statement=None, broker_batch=batch)
        self.assertEqual(s.broker_details.status, 'incomplete')
        self.assertEqual(s.broker_details.source_scope, kreq.scope)
        self.assertNotEqual(s.reconciliation, 'matched')
        self.assertIn('broker', {x.kind for x in s.data_refs})
        self.assertEqual(parse_payload(self.encoded(s)).payload, s)


if __name__ == '__main__':
    unittest.main()
