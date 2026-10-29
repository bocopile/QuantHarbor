"""구현 전 고정된 AP01~21 기대값과 실제 합성 aggregate의 행동 검증."""
from dataclasses import replace
import json
import pickle
from threading import Barrier, Event, Thread
import unittest

from quantharbor.adapters.synthetic_approval import SyntheticAuthority
from quantharbor.application.approval import ApprovalApplication
from quantharbor.domain import approval as d
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import parse_payload
from synthetic_approval import Harness, MANIFEST, policy, rights_changed


def ordered_race(first, second):
    """두 worker 모두 barrier 도착 후 지정 순서를 event로 확정한다. sleep 없음."""
    barrier, done = Barrier(2), Event()
    results = [None, None]
    def worker(index, operation):
        try:
            barrier.wait(timeout=15)
            if index:
                if not done.wait(timeout=30):
                    raise AssertionError('first operation did not finish')
            results[index] = operation()
        except Exception as error:
            results[index] = error
        finally:
            if not index:
                done.set()
    threads = (Thread(target=worker, args=(0, first)), Thread(target=worker, args=(1, second)))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=40)
        if t.is_alive():
            raise AssertionError('thread did not finish')
    for result in results:
        if isinstance(result, Exception):
            raise result
    return results


class ApprovalFixedCases(unittest.TestCase):
    def assertDenied(self, operation, reasons=None):
        with self.assertRaises(d.ApprovalDenied) as caught:
            operation()
        self.assertIn(caught.exception.reason, d.REASONS)
        self.assertEqual(str(caught.exception), caught.exception.reason)
        if reasons:
            self.assertIn(caught.exception.reason, reasons)

    def bundle(self, h, *, consumed=1):
        s = h.repo.snapshot()
        self.assertEqual(len(s['claims']), consumed)
        self.assertEqual(len(s['intents']), consumed)
        self.assertEqual(len(s['reservations']), 3 * consumed)
        self.assertEqual(len(s['outbox']), consumed)
        return s

    def test_AP01_exact_positive_presentation_explicit_approve_and_atomic_admission(self):
        h = Harness()
        p, a = h.present()
        self.assertEqual(a.state, 'pending')
        self.assertIsNone(a.issued_at)
        self.assertIsNone(a.decision_evidence_ref)
        self.assertEqual(a.terms, h.source.artifacts.candidates[0].body.terms)
        self.assertEqual((a.terms.quantity, a.terms.limit_price, a.terms.cost_bound,
                          a.terms.maximum_burden, a.terms.currency), ('3', '100', '2', '302', 'USD'))
        for literal in ('3주 매수', '지정가 100 USD', '비용 최대 2 USD', '최대 필요자금 302 USD',
                        '합성 승인 범위:', 'submit_candidate_once'):
            self.assertIn(literal, p.rendered_text)
        c = h.app.challenge(h.approver, d.ref('approval', a.approval_id, a), action='approve', command_id='AP01')
        self.assertEqual(c.expires_at, '2024-03-08T14:31:18.000000Z')
        h.clock.at = '2024-03-08T14:31:10Z'
        receipt = h.app.execute(h.approver, c)
        self.assertEqual(receipt.outcome, 'applied')
        a = h.head(a)
        self.assertEqual((a.state, a.state_version, a.issued_at, a.expires_at),
            ('approved', 2, '2024-03-08T14:31:10.000000Z', '2024-03-08T14:31:28.000000Z'))
        self.assertEqual(h.command(a, 'admit', 'AP01-admit').outcome, 'applied')
        s = self.bundle(h)
        self.assertEqual(h.head(a).state, 'consumed')
        self.assertEqual(next(iter(s['intents'].values()))['state'], 'prepared')
        self.assertEqual(next(iter(s['outbox'].values()))['state'], 'pending')
        self.assertEqual(s['reservations'][(h.head(a).consumed_intent_id, 'cash')]['amount'], '302')

    def test_AP02_exact_replay_only_receipt_and_current_permission(self):
        h = Harness()
        _, a = h.present()
        c = h.app.challenge(h.approver, d.ref('approval', a.approval_id, a), action='approve', command_id='same')
        receipt = h.app.execute(h.approver, c)
        before = h.repo.snapshot()
        self.assertEqual(h.app.execute(h.approver, c), receipt)
        self.assertEqual(h.repo.snapshot(), before)
        h.repo.change_permissions(h.controller, 'fixture-approver', ('present',))
        before = h.repo.snapshot()
        self.assertDenied(lambda: h.app.execute(h.approver, c), ('authority_denied',))
        self.assertEqual(h.repo.snapshot(), before)

    def test_AP03_nonce_command_action_candidate_display_session_substitutions(self):
        h = Harness()
        _, a = h.present()
        from quantharbor.domain.target import ref as target_ref
        b = h.source.artifacts.candidates[1]
        _, other = h.app.present(h.approver, target_ref('candidate', b.candidate_id, b))
        c = h.app.challenge(h.approver, d.ref('approval', a.approval_id, a), action='approve', command_id='nonce')
        substitutions = (dict(action='deny'), dict(command_id='different'), dict(nonce='nonce:foreign'),
            dict(session_id='session:foreign'), dict(target_ref=d.ref('approval', other.approval_id, other)),
            dict(presentation_ref=other.presentation_ref), dict(authority_generation='other-generation'))
        for changes in substitutions:
            with self.subTest(changes=tuple(changes)):
                before = h.repo.snapshot()
                self.assertDenied(lambda: h.app.execute(h.approver, replace(c, **changes)))
                self.assertEqual(h.repo.snapshot(), before)
        self.assertEqual(h.app.execute(h.approver, c).outcome, 'applied')

    def test_AP04_fake_principal_foreign_issuer_bool_AI_and_JSON_are_not_authority(self):
        h = Harness()
        foreign = Harness()
        state = h.repo.snapshot()
        principal = next(parse_payload(raw).payload for r, raw in state['records'].items() if r.kind == 'principal')
        for fake in (principal, parse_payload(d.encoded(principal)).payload, foreign.approver,
                     True, {'proof': True, 'authenticated': True}, '승인합니다', object()):
            self.assertDenied(lambda: h.app.present(fake, h.candidate_ref), ('authority_denied',))
        self.assertEqual(h.repo.snapshot(), state)
        self.assertDenied(lambda: pickle.dumps(h.approver), ('authority_denied',))

    def test_AP05_candidate_financial_text_account_generation_binding(self):
        for field in ('account', 'generation', 'price', 'text'):
            with self.subTest(field=field):
                h = Harness()
                _, a = h.present()
                source = h.source
                if field == 'account':
                    self.assertDenied(lambda: h.repo.replace_source(h.controller,
                        replace(source, request=replace(source.request, account_ref='synthetic-account:other'))))
                    continue
                if field == 'generation':
                    source = replace(source, request=replace(source.request, authority_generation='different'))
                elif field == 'price':
                    from synthetic_target import fixture, build
                    from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
                    from quantharbor.ports.approval import ApprovalSource
                    request, inputs = fixture(prices=('101', '100'))
                    repo = SyntheticTargetRepository()
                    source = ApprovalSource(request, inputs, build(request, inputs, repo), repo)
                else:
                    source = replace(source, inputs=replace(source.inputs,
                        strategy=replace(source.inputs.strategy, synthetic_notice='다른 표시')))
                h.repo.replace_source(h.controller, source)
                receipt = h.command(a, 'approve', 'changed')
                self.assertEqual(receipt.outcome, 'rejected')
                self.assertNotEqual(h.head(a).state, 'approved')

    def test_AP06_all_current_dependency_rights_and_policy_are_fresh(self):
        for scope in ('all', 'risk', 'daily', 'policy'):
            with self.subTest(scope=scope):
                h = Harness()
                _, a = h.approve()
                if scope == 'policy':
                    h.repo.replace_policy(h.controller, replace(policy(h.source), version=2))
                else:
                    h.repo.replace_source(h.controller, rights_changed(h.source, only=scope))
                receipt = h.command(a, 'admit', 'stale')
                self.assertEqual(receipt.outcome, 'rejected')
                self.assertIn(receipt.reason_code, ('rights_denied', 'policy_changed'))
                self.bundle(h, consumed=0)
                reporter = h.authority.issue_reader('fixture-reporting')
                if scope != 'policy':
                    self.assertDenied(lambda: h.app.query(reporter, account_ref=h.source.request.account_ref,
                        purpose='financial'), ('rights_denied',))

    def test_AP07_end_exclusive_presentation_expiry_heartbeat_no_extension_clock_fault(self):
        for at, outcome in (('2024-03-08T14:31:27.999999Z', 'applied'),
                            ('2024-03-08T14:31:28Z', 'rejected')):
            h = Harness()
            _, a = h.approve()
            h.clock.at = '2024-03-08T14:31:20Z'
            h.app.control(h.approver, 'heartbeat')
            self.assertEqual(h.head(a).expires_at, '2024-03-08T14:31:28.000000Z')
            h.clock.at = at
            receipt = h.command(a, 'admit', 'boundary')
            self.assertEqual(receipt.outcome, outcome)
            if outcome == 'rejected':
                self.assertEqual(receipt.reason_code, 'expired')
                self.assertEqual(h.head(a).state, 'expired')
        h.clock.at = '2024-03-08T14:31:09Z'
        self.assertDenied(lambda: h.present(), ('clock_invalid',))
        self.assertEqual(h.repo.snapshot()['mode'], 'faulted')

    def test_AP08_disconnect_liveness_expiry_never_auto_resume(self):
        for disconnect in (True, False):
            h = Harness()
            _, a = h.present()
            c = h.app.challenge(h.approver, d.ref('approval', a.approval_id, a), action='approve', command_id='offline')
            if disconnect:
                h.app.control(h.approver, 'disconnect')
            else:
                h.clock.at = '2024-03-08T14:31:38Z'
            before = h.repo.snapshot()
            self.assertDenied(lambda: h.app.execute(h.approver, c), ('session_inactive',))
            self.assertDenied(lambda: h.app.control(h.approver, 'heartbeat'), ('session_inactive',))
            self.assertEqual(h.repo.snapshot(), before)
            self.assertEqual(h.head(a).state, 'pending')

    def test_AP09_two_approvals_one_candidate_both_orders_shared_lock(self):
        for reverse in (False, True):
            h = Harness()
            _, a = h.approve(label='a')
            _, b = h.present()
            self.assertEqual(h.command(b, 'approve', 'b').outcome, 'applied')
            app2 = ApprovalApplication(h.repo)
            challenges = [h.app.challenge(h.approver, d.ref('approval', x.approval_id, h.head(x)),
                action='admit', command_id='admit-' + str(i)) for i, x in enumerate((a, b))]
            if reverse:
                challenges.reverse()
            results = ordered_race(lambda: h.app.execute(h.approver, challenges[0]),
                                   lambda: app2.execute(h.approver, challenges[1]))
            self.assertEqual([r.outcome for r in results], ['applied', 'rejected'])
            self.assertEqual(results[1].reason_code, 'candidate_already_consumed')
            self.assertEqual(sorted((h.head(a).state, h.head(b).state)), ['approved', 'consumed'])
            self.bundle(h)

    def test_AP10_revoke_admission_both_orders_no_partial_state(self):
        for first in ('revoke', 'admit'):
            h = Harness()
            _, a = h.approve()
            r = d.ref('approval', a.approval_id, a)
            cs = {action: h.app.challenge(h.approver, r, action=action, command_id=action)
                  for action in ('revoke', 'admit')}
            second = 'admit' if first == 'revoke' else 'revoke'
            results = ordered_race(lambda: h.app.execute(h.approver, cs[first]),
                lambda: ApprovalApplication(h.repo).execute(h.approver, cs[second]))
            self.assertEqual([r.outcome for r in results], ['applied', 'rejected'])
            self.assertEqual(h.head(a).state, 'revoked' if first == 'revoke' else 'consumed')
            self.bundle(h, consumed=0 if first == 'revoke' else 1)

    def test_AP11_prepared_withdraw_dispatch_both_orders(self):
        for first in ('withdraw', 'dispatch'):
            h = Harness()
            a = h.consumed()
            r = d.ref('approval', a.approval_id, a)
            cw = h.app.challenge(h.approver, r, action='withdraw', command_id='withdraw')
            cd = h.app.challenge(h.controller, r, action='dispatch', command_id='dispatch')
            ops = {'withdraw': lambda: h.app.execute(h.approver, cw),
                   'dispatch': lambda: ApprovalApplication(h.repo).execute(h.controller, cd)}
            results = ordered_race(ops[first], ops['dispatch' if first == 'withdraw' else 'withdraw'])
            s = self.bundle(h)
            intent = next(iter(s['intents'].values()))
            withdrawal = next(parse_payload(raw).payload for r, raw in s['records'].items() if r.kind == 'withdrawal')
            self.assertEqual(h.head(a).state, 'consumed')
            if first == 'withdraw':
                self.assertEqual(intent['state'], 'aborted_unsent')
                self.assertEqual(withdrawal.state, 'unsent_confirmed')
                self.assertEqual(results[1].outcome, 'rejected')
            else:
                self.assertEqual(intent['state'], 'dispatching')
                self.assertEqual(withdrawal.state, 'requested')
                self.assertTrue(all(r.outcome == 'applied' for r in results))
                self.assertTrue(all(v['state'] == 'held' for v in s['reservations'].values()))

    def test_AP12_each_staging_failure_leaves_entire_aggregate_unchanged(self):
        for label in ('consumed', 'claim', 'intent', 'reservation', 'outbox', 'history', 'receipt', 'commit'):
            with self.subTest(label=label):
                h = Harness()
                _, a = h.approve()
                c = h.app.challenge(h.approver, d.ref('approval', a.approval_id, a), action='admit', command_id='fault')
                before = h.repo.snapshot()
                with h.repo.inject_failure(label):
                    self.assertDenied(lambda: h.app.execute(h.approver, c), ('commit_failed',))
                self.assertEqual(h.repo.snapshot(), before)
                self.assertEqual(h.app.execute(h.approver, c).outcome, 'applied')
                self.bundle(h)

    def test_AP13_aborted_unsent_does_not_release_consumption_claim(self):
        h = Harness()
        a = h.consumed()
        self.assertEqual(h.command(a, 'withdraw', 'withdraw').outcome, 'applied')
        self.assertDenied(lambda: d.plan_admission_transition(h.head(a), intent_id='synthetic-intent:retry',
            aggregate_version=h.repo.snapshot()['version']), ('terminal_state',))
        self.assertDenied(lambda: h.command(a, 'admit', 'retry-old'), ('capacity_exceeded', 'terminal_state'))
        _, b = h.present()
        self.assertEqual(h.command(b, 'approve', 'approve-new').outcome, 'applied')
        receipt = h.command(b, 'admit', 'retry-new')
        self.assertEqual(receipt.reason_code, 'candidate_already_consumed')
        self.bundle(h)

    def test_AP14_restore_external_generation_preserves_unknown_and_pending_invalidation(self):
        h = Harness()
        a = h.consumed()
        self.assertEqual(h.command(a, 'dispatch', 'dispatch').outcome, 'applied')
        h.repo.record_unknown(h.controller, a.consumed_intent_id)
        _, pending = h.present()
        before = h.repo.snapshot()
        generation = h.repo.restore(before)
        after = h.repo.snapshot()
        self.assertNotEqual(generation, before['generation'])
        for key in ('intents', 'claims', 'reservations', 'outbox'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(h.head(a).state, 'consumed')
        self.assertEqual(h.head(pending).state, 'invalidated')
        self.assertEqual(after['mode'], 'stopped')
        self.assertDenied(lambda: h.present(), ('authority_denied',))
        fresh = h.authority.issue_session('fixture-controller')
        self.assertDenied(lambda: h.app.control(fresh, 'resume'), ('reconciliation_required',))
        self.assertDenied(lambda: h.app.control(fresh, True))

    def test_AP15_constructor_parser_reseal_predecessor_repository_bypass(self):
        h = Harness()
        _, a = h.present()
        with self.assertRaises(ContractError):
            replace(a, state='approved')
        with self.assertRaises(ContractError):
            replace(a, previous_ref=d.ref('approval', 'foreign', a))
        value = json.loads(d.encoded(a))
        value['payload']['unexpected'] = True
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(value))
        before = h.repo.snapshot()
        self.assertDenied(lambda: h.app.present(parse_payload(d.encoded(a)).payload, h.candidate_ref))
        self.assertFalse(hasattr(h.repo, 'append'))
        self.assertFalse(hasattr(h.repo, 'consume_approval'))
        self.assertEqual(h.repo.snapshot(), before)

    def test_AP16_capacity_failure_no_eviction_reserved_withdrawal_closes(self):
        h = Harness()
        a = h.consumed()
        while True:
            before = h.repo.snapshot()
            try:
                h.authority.issue_reader('fixture-reporting')
            except d.ApprovalDenied as error:
                self.assertEqual(error.reason, 'capacity_exceeded')
                self.assertEqual(h.repo.snapshot(), before)
                break
        records_before = set(before['records'])
        self.assertEqual(h.command(a, 'withdraw', 'closing').outcome, 'applied')
        after = h.repo.snapshot()
        self.assertTrue(records_before <= set(after['records']))
        self.assertEqual(next(iter(after['intents'].values()))['state'], 'aborted_unsent')

    def test_AP17_roles_protected_queries_fixed_errors_no_nonce_or_handles(self):
        h = Harness()
        _, a = h.approve()
        reporting = h.authority.issue_reader('fixture-reporting')
        research = h.authority.issue_reader('fixture-research')
        for permit in (reporting, research, h.controller):
            self.assertDenied(lambda: h.app.present(permit, h.candidate_ref), ('authority_denied',))
        self.assertDenied(lambda: h.app.control(h.approver, 'resume'), ('authority_denied',))
        self.assertDenied(lambda: h.app.query(research, account_ref=h.source.request.account_ref, purpose='financial'))
        self.assertDenied(lambda: h.app.query(reporting, account_ref='synthetic-account:foreign', purpose='status'))
        self.assertDenied(lambda: h.app.query(reporting, account_ref=h.source.request.account_ref, purpose='status', limit=21))
        result = h.app.query(reporting, account_ref=h.source.request.account_ref, purpose='financial', limit=1)
        raw = json.dumps(result)
        for forbidden in ('nonce', 'challenge', 'session:', 'principal', 'Traceback', 'password'):
            self.assertNotIn(forbidden, raw)
        self.assertIn('302', raw)
        self.assertEqual(len(result['rows']), 1)
        summary = h.app.query(research, account_ref=h.source.request.account_ref, purpose='research_summary')
        self.assertNotIn('maximum_burden', json.dumps(summary))

    def test_AP18_multiple_application_instances_exact_receipt_single_effect(self):
        h = Harness()
        _, a = h.present()
        app2 = ApprovalApplication(h.repo)
        c = app2.challenge(h.approver, d.ref('approval', a.approval_id, a), action='approve', command_id='shared')
        r1, r2 = ordered_race(lambda: h.app.execute(h.approver, c), lambda: app2.execute(h.approver, c))
        self.assertEqual(r1, r2)
        self.assertEqual(h.head(a).state_version, 2)
        self.assertEqual(len(h.repo.snapshot()['receipts']), 1)

    def test_AP19_protective_new_control_session_after_rights_risk_loss(self):
        h = Harness()
        a = h.consumed()
        h.repo.record_risk(h.controller, 'blocked')
        h.repo.replace_source(h.controller, rights_changed(h.source))
        h.clock.at = '2024-03-08T14:33:09Z'
        fresh = h.authority.issue_session('fixture-controller')
        receipt = h.command(a, 'withdraw', 'protective', handle=fresh)
        self.assertEqual(receipt.outcome, 'applied')
        self.assertEqual(h.head(a).state, 'consumed')
        reporter = h.authority.issue_reader('fixture-reporting')
        self.assertDenied(lambda: h.app.query(reporter, account_ref=h.source.request.account_ref, purpose='financial'))
        self.bundle(h)

    def test_AP20_expired_challenge_rejection_receipt_replay_not_substitution(self):
        h = Harness()
        _, a = h.present()
        c = h.app.challenge(h.approver, d.ref('approval', a.approval_id, a), action='approve', command_id='expired')
        h.clock.at = '2024-03-08T14:31:18Z'
        receipt = h.app.execute(h.approver, c)
        self.assertEqual((receipt.outcome, receipt.reason_code), ('rejected', 'expired'))
        before = h.repo.snapshot()
        self.assertEqual(h.app.execute(h.approver, c), receipt)
        self.assertDenied(lambda: h.app.execute(h.approver, replace(c, action='deny')), ('replay_conflict',))
        self.assertEqual(h.repo.snapshot(), before)
        self.assertNotEqual(h.head(a).state, 'denied')

    def test_AP21_pure_plan_no_authority_no_standalone_commit(self):
        h = Harness()
        _, a = h.approve()
        before = h.repo.snapshot()
        plan = d.plan_admission_transition(a, intent_id='synthetic-intent:pure', aggregate_version=before['version'])
        self.assertEqual(h.repo.snapshot(), before)
        self.assertDenied(lambda: h.app.execute(h.approver, plan))
        self.assertEqual(h.repo.snapshot(), before)
        self.assertEqual(h.command(a, 'admit', 'actual-simulation').outcome, 'applied')
        s = self.bundle(h)
        fact = parse_payload(s['records'][next(iter(s['intents'].values()))['runtime_ref']]).payload
        self.assertEqual(fact.provenance, 'synthetic_aggregate')
        self.assertEqual(fact.aggregate_version, s['version'])
        self.assertFalse(MANIFEST['actual_api_enabled'])


if __name__ == '__main__':
    unittest.main()
