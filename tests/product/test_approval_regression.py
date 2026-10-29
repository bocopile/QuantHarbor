"""Q26 추가 회귀: 실제 source/serializer/역할/이력/시간/예약 경계."""
from dataclasses import replace
from hashlib import sha256
import json
from threading import Barrier, Thread
import unittest

from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
from quantharbor.application.approval import ApprovalApplication, validate_source
from quantharbor.domain import approval as d
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.target import ref as target_ref
from quantharbor.ports.approval import ApprovalSource
from synthetic_approval import Harness, actual_source, rights_changed
from synthetic_target import fixture, build


class ApprovalRegression(unittest.TestCase):
    def test_all_stored_contracts_roundtrip_and_real_previous_refs_resolve(self):
        h = Harness()
        a = h.consumed()
        h.command(a, 'withdraw', 'withdraw')
        s = h.repo.snapshot()
        for r, raw in s['records'].items():
            with self.subTest(kind=r.kind):
                obj = parse_payload(raw).payload
                self.assertEqual(d.encoded(obj), raw)
                self.assertEqual(d.ref(r.kind, r.id, obj), r)
                previous = getattr(obj, 'previous_ref', None)
                if previous:
                    self.assertIn(previous, s['records'])
                    old = parse_payload(s['records'][previous]).payload
                    self.assertEqual(old.state_version + 1, obj.state_version)
                    self.assertEqual(old.account_ref, obj.account_ref)
                    self.assertEqual(old.environment, obj.environment)
                    self.assertIn(obj.state, d.TRANSITIONS[old.state])
        self.assertEqual(a.expires_at, '2024-03-08T14:31:28.000000Z')

    def test_actual_changed_quantity_and_price_sources_reject_old_candidate(self):
        for kwargs in ({'targets': ('4', '4')}, {'prices': ('101', '100')}):
            with self.subTest(kwargs=kwargs):
                h = Harness()
                _, a = h.present()
                request, inputs = fixture(**kwargs)
                repo = SyntheticTargetRepository()
                artifacts = build(request, inputs, repo)
                self.assertEqual(artifacts.plan.body.status, 'eligible')
                altered = ApprovalSource(request, inputs, artifacts, repo)
                h.repo.replace_source(h.controller, altered)
                result = h.command(a, 'approve', 'changed-real-source')
                self.assertEqual(result.outcome, 'rejected')
                self.assertIn(result.reason_code, ('candidate_mismatch', 'source_unresolved'))
                self.assertNotEqual(h.head(a).state, 'approved')
                self.assertEqual(len(h.repo.snapshot()['intents']), 0)

    def test_no_report_display_alone_can_replace_missing_original_repository(self):
        h = Harness()
        _, a = h.present()
        missing = replace(h.source, repository=SyntheticTargetRepository())
        h.repo.replace_source(h.controller, missing)
        receipt = h.command(a, 'approve', 'missing')
        self.assertEqual((receipt.outcome, receipt.reason_code), ('rejected', 'source_unresolved'))
        self.assertEqual(h.head(a).state, 'invalidated')

    def test_current_rights_revoked_at_exact_instant_and_duplicate_finance_blocked(self):
        h = Harness()
        _, a = h.present()
        c = h.app.challenge(h.approver, d.ref('approval', a.approval_id, a), action='approve', command_id='first')
        h.app.execute(h.approver, c)
        source = rights_changed(h.source, purposes=('research', 'store', 'report'),
            revoked_at='2024-03-08T14:31:08Z')
        h.repo.replace_source(h.controller, source)
        before = h.repo.snapshot()
        with self.assertRaisesRegex(d.ApprovalDenied, '^rights_denied$'):
            h.app.execute(h.approver, c)
        self.assertEqual(h.repo.snapshot(), before)

    def test_deny_is_explicit_user_state_terminal_and_not_authority(self):
        h = Harness()
        _, a = h.present()
        result = h.command(a, 'deny', 'explicit-deny')
        self.assertEqual(result.outcome, 'applied')
        denied = h.head(a)
        self.assertEqual((denied.state, denied.state_version), ('denied', 2))
        self.assertIsNotNone(denied.decision_evidence_ref)
        with self.assertRaisesRegex(d.ApprovalDenied, '^terminal_state$'):
            d.plan_admission_transition(denied, intent_id='synthetic-intent:no', aggregate_version=1)

    def test_canonical_closed_nullable_environment_and_utf8_limits(self):
        h = Harness()
        p, a = h.present()
        for change in (dict(environment='live'), dict(state='consumed'), dict(state_version=True),
                       dict(authorized_action='cancel_order'), dict(expires_at='2024-03-08T14:32:00Z')):
            with self.subTest(change=tuple(change)), self.assertRaises(ContractError):
                replace(a, **change)
        with self.assertRaises(ContractError):
            canonical_bytes(CanonicalPayload('ApprovalRecord', 1, 'live', a))
        with self.assertRaises(ContractError):
            replace(p, rendered_text='가' * 5462)
        with self.assertRaises(ContractError):
            d.text('가' * 683)
        with self.assertRaises(ContractError):
            d.rendered('\ud800')
        self.assertEqual(len(d.rendered('가' * 5461).encode()), 16383)
        value = json.loads(d.encoded(p))
        value['payload']['fake_authentication'] = True
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(value))

    def test_rejected_command_does_not_erase_other_owners_success(self):
        h = Harness()
        _, a = h.approve()
        alien = h.authority.issue_session('fixture-approver')
        before = h.repo.snapshot()
        with self.assertRaisesRegex(d.ApprovalDenied, '^authority_denied$'):
            h.app.challenge(alien, d.ref('approval', a.approval_id, a), action='admit', command_id='alien')
        self.assertEqual(h.repo.snapshot(), before)
        self.assertEqual(h.head(a).state, 'approved')

    def test_history_missing_predecessor_cannot_be_staged(self):
        h = Harness()
        _, a = h.approve()
        before = h.repo.snapshot()
        bogus = replace(a, state='revoked', state_version=3,
            previous_ref=replace(d.ref('approval', a.approval_id, a), sha256='0' * 64))
        with self.assertRaisesRegex(d.ApprovalDenied, '^version_conflict$'):
            h.repo._put(h.repo._copy(), 'approval', bogus)
        self.assertEqual(h.repo.snapshot(), before)

    def test_unknown_withdrawal_preserves_all_reservations_and_no_cancel(self):
        h = Harness()
        a = h.consumed()
        h.command(a, 'dispatch', 'dispatch')
        h.repo.record_unknown(h.controller, a.consumed_intent_id)
        before = h.repo.snapshot()
        result = h.command(a, 'withdraw', 'unknown-withdraw')
        self.assertEqual(result.outcome, 'applied')
        after = h.repo.snapshot()
        withdrawal = parse_payload(after['records'][result.result_ref]).payload
        self.assertEqual(withdrawal.state, 'requested')
        self.assertEqual(after['reservations'], before['reservations'])
        self.assertEqual(after['intents'], before['intents'])
        self.assertEqual(next(iter(after['outbox'].values()))['state'], 'unknown')
        for action in ('cancel_order', 'liquidate'):
            with self.assertRaises(d.ApprovalDenied):
                h.app.control(h.controller, action)

    def test_restore_consumed_withdraw_with_new_generation_and_detail_stays_restricted(self):
        h = Harness()
        a = h.consumed()
        h.command(a, 'dispatch', 'dispatch')
        h.repo.record_unknown(h.controller, a.consumed_intent_id)
        saved = h.repo.snapshot()
        h.repo.restore(saved)
        controller = h.authority.issue_session('fixture-controller')
        self.assertEqual(h.command(a, 'withdraw', 'after-restore', handle=controller).outcome, 'applied')
        reporter = h.authority.issue_reader('fixture-reporting')
        with self.assertRaises(d.ApprovalDenied):
            h.app.query(reporter, account_ref=h.source.request.account_ref, purpose='financial')
        for name in ('claims', 'reservations', 'intents'):
            self.assertEqual(h.repo.snapshot()[name], saved[name])

    def test_raw_source_exception_is_fixed_code_without_input_echo(self):
        h = Harness()
        class FailedRepository:
            def get(self, *args, **kwargs):
                raise ValueError('SYNTHETIC_PRIVATE_PATH_DO_NOT_ECHO')
        h.repo.replace_source(h.controller, replace(h.source, repository=FailedRepository()))
        with self.assertRaisesRegex(d.ApprovalDenied, '^source_unresolved$'):
            h.present()

    def test_truly_simultaneous_two_instances_admit_one_candidate(self):
        h = Harness()
        _, a = h.approve(label='first')
        _, b = h.present()
        h.command(b, 'approve', 'second')
        approvals = (h.head(a), h.head(b))
        cs = tuple(h.app.challenge(h.approver, d.ref('approval', x.approval_id, x),
            action='admit', command_id='race-' + str(i)) for i, x in enumerate(approvals))
        barrier, results = Barrier(2), []
        def run(c):
            try:
                barrier.wait(timeout=15)
                results.append(ApprovalApplication(h.repo).execute(h.approver, c))
            except Exception as error:
                results.append(error)
        threads = [Thread(target=run, args=(c,)) for c in cs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            self.assertFalse(t.is_alive())
        self.assertEqual(sorted(r.outcome for r in results), ['applied', 'rejected'])
        self.assertEqual(len(h.repo.snapshot()['claims']), 1)

    def test_session_expiry_is_end_exclusive_even_with_recent_heartbeat(self):
        h = Harness()
        h.clock.at = '2024-03-08T14:33:08Z'
        with self.assertRaisesRegex(d.ApprovalDenied, '^session_expired$'):
            h.app.control(h.approver, 'heartbeat')

    def test_clock_missing_uncertain_and_monotonic_query_observation(self):
        for at in (None, float('nan'), 'uncertain-clock'):
            h = Harness()
            h.clock.at = at
            with self.assertRaisesRegex(d.ApprovalDenied, '^clock_invalid$'):
                h.present()
        h = Harness()
        reader = h.authority.issue_reader('fixture-reporting')
        h.clock.at = '2024-03-08T14:31:12Z'
        h.app.query(reader, account_ref=h.source.request.account_ref, purpose='status')
        h.clock.at = '2024-03-08T14:31:11Z'
        with self.assertRaisesRegex(d.ApprovalDenied, '^clock_invalid$'):
            h.present()

    def test_fixture_identity_and_exact_21_cases_are_frozen(self):
        from synthetic_approval import FIXTURE_PATH, MANIFEST
        self.assertEqual(sha256(FIXTURE_PATH.read_bytes()).hexdigest(),
            '84190ff349d81877bbfdace4ffd23d9e0c1de5d474c3a3c6568c870504c71300')
        self.assertEqual(len(MANIFEST['cases']), 21)
        self.assertEqual(MANIFEST['golden']['approval_expires_at'], '2024-03-08T14:31:28Z')

    def test_exact_command_replay_after_candidate_expiry_does_not_authorize_again(self):
        h = Harness()
        _, a = h.present()
        ar = d.ref('approval', a.approval_id, a)
        c = h.app.challenge(h.approver, ar, action='approve', command_id='past-expiry')
        first = h.app.execute(h.approver, c)
        h.clock.at = '2024-03-08T14:31:37Z'
        before = h.repo.snapshot()
        self.assertEqual(h.app.execute(h.approver, c), first)
        self.assertEqual(h.app.challenge(h.approver, ar, action='approve', command_id='past-expiry'), c)
        self.assertEqual(h.repo.snapshot(), before)
        self.assertEqual(h.head(a).state, 'approved')
        self.assertEqual(len(before['intents']), 0)

    def test_source_bytes_bound_is_checked_before_reproduction_without_mutation(self):
        h = Harness()
        source = h.source
        points = source.inputs.risk_points * 64
        oversized = replace(source, inputs=replace(source.inputs, risk_points=points,
            boundary_inputs=points, daily_usage_inputs=points))
        before = h.repo.snapshot()
        with self.assertRaisesRegex(d.ApprovalDenied, '^capacity_exceeded$'):
            h.repo.replace_source(h.controller, oversized)
        self.assertEqual(h.repo.snapshot(), before)

    def test_reserved_control_closure_survives_new_runtime_capacity_failure(self):
        h = Harness()
        while True:
            before = h.repo.snapshot()
            try:
                h.repo.record_risk(h.controller, 'blocked')
            except d.ApprovalDenied as error:
                self.assertEqual(error.reason, 'capacity_exceeded')
                self.assertEqual(h.repo.snapshot(), before)
                break
        h.app.control(h.controller, 'disconnect')
        after = h.repo.snapshot()
        session = next(parse_payload(after['records'][r]).payload for (kind, _), r in after['heads'].items()
            if kind == 'session' and parse_payload(after['records'][r]).payload.state == 'paused')
        self.assertEqual(session.state, 'paused')

    def test_lower_byte_capacity_and_altered_snapshot_fail_without_partial_state(self):
        h = Harness()
        before = h.repo.snapshot()
        changed = dict(before, generation='snapshot-selected-generation')
        with self.assertRaisesRegex(d.ApprovalDenied, '^invalid_contract$'):
            h.repo.restore(changed)
        self.assertEqual(h.repo.snapshot(), before)
        h.repo._byte_capacity = h.repo._usage(h.repo._state)[1] + sum(v[1] for v in before['holds'].values())
        with self.assertRaisesRegex(d.ApprovalDenied, '^capacity_exceeded$'):
            h.present()
        self.assertEqual(h.repo.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
