"""Q26 AS1·AS2 실제 보안 재현과 보호 종료 회귀."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from unittest.mock import patch

from quantharbor.application.approval import ApprovalApplication
from quantharbor.domain import approval as d
from quantharbor.domain.serialization import parse_payload
from synthetic_approval import Harness, rights_changed
from test_approval import ordered_race


class ApprovalSecurity(unittest.TestCase):
    def assert_capacity(self, h):
        s = h.repo._state
        n, b = h.repo._usage(s)
        self.assertLessEqual(n + sum(v[0] for v in s['holds'].values()), h.repo._capacity)
        self.assertLessEqual(b + sum(v[1] for v in s['holds'].values()), h.repo._byte_capacity)
        for (kind, aid), r in s['heads'].items():
            if kind == 'approval':
                pn, pb = h.repo._pending_budget(s, aid)
                hn, hb = s['holds'].get(aid, (0, 0))
                self.assertGreaterEqual(hn, pn)
                self.assertGreaterEqual(hb, pb)
                a = parse_payload(s['records'][r]).payload
                if a.state in ('pending', 'approved', 'consumed'):
                    self.assertGreaterEqual(hn - pn, 8)

    def flood(self, h, a, action='dispatch', handle=None):
        handle = handle or h.controller
        r = d.ref('approval', a.approval_id, a)
        challenges = []
        for i in range(128):
            before = h.repo.snapshot()
            try:
                c = h.app.challenge(handle, r, action=action, command_id='flood-' + str(i))
            except d.ApprovalDenied as error:
                self.assertEqual(error.reason, 'capacity_exceeded')
                self.assertEqual(h.repo.snapshot(), before)
                break
            challenges.append(c)
            self.assert_capacity(h)
        else:
            self.fail('unbounded challenge issuance')
        self.assertGreater(len(challenges), 0)
        return challenges

    def close(self, h, a, command_id='atomic-withdraw', handle=None):
        return h.app.withdraw(handle or h.controller, d.ref('approval', a.approval_id, a),
            command_id=command_id)

    def test_AS1_dispatch_rechecks_original_approver_current_permission(self):
        h = Harness()
        a = h.consumed()
        c = h.app.challenge(h.controller, d.ref('approval', a.approval_id, a),
            action='dispatch', command_id='AS1-dispatch')
        h.repo.change_permissions(h.controller, 'fixture-approver', ())
        before = h.repo.snapshot()
        result = h.app.execute(h.controller, c)
        self.assertEqual((result.outcome, result.reason_code), ('rejected', 'authority_denied'))
        after = h.repo.snapshot()
        for name in ('intents', 'outbox', 'reservations', 'claims', 'heads'):
            self.assertEqual(after[name], before[name], name)

    def test_AS2_outstanding_dispatch_completions_preserve_withdrawal(self):
        h = Harness()
        a = h.consumed()
        r = d.ref('approval', a.approval_id, a)
        challenges = []
        trace = [h.repo.snapshot()['holds'][a.approval_id][0]]
        for i in range(3):
            before = h.repo.snapshot()
            try:
                c = h.app.challenge(h.controller, r, action='dispatch', command_id='AS2-' + str(i))
            except d.ApprovalDenied as error:
                self.assertEqual(error.reason, 'capacity_exceeded')
                self.assertEqual(h.repo.snapshot(), before)
                break
            challenges.append(c)
            trace.append(h.repo.snapshot()['holds'][a.approval_id][0])
        self.assertGreaterEqual(len(challenges), 1, 'normal dispatch remains available')
        for i, c in enumerate(challenges):
            receipt = h.app.execute(h.controller, c)
            self.assertEqual(receipt.outcome, 'applied' if i == 0 else 'rejected')
            trace.append(h.repo.snapshot()['holds'][a.approval_id][0])
        try:
            result = h.command(a, 'withdraw', 'AS2-protected-withdrawal')
        except d.ApprovalDenied as error:
            self.fail('AS2 protective withdrawal denied: ' + error.reason + '; hold trace=' + str(trace))
        self.assertEqual(result.outcome, 'applied')

    def test_dispatch_positive_uses_controller_without_approval_permission(self):
        h = Harness()
        a = h.consumed()
        self.assertNotIn('approve', h.repo._state['permissions']['fixture-controller'])
        self.assertEqual(h.command(a, 'dispatch', 'positive-dispatch').outcome, 'applied')
        s = h.repo.snapshot()
        self.assertEqual(s['intents'][a.consumed_intent_id]['state'], 'dispatching')
        self.assertEqual(s['outbox'][a.consumed_intent_id]['state'], 'dispatching')
        self.assert_capacity(h)

    def test_dispatch_revocation_orders_and_explicit_regrant(self):
        for first in ('revoke', 'dispatch'):
            with self.subTest(first=first):
                h = Harness()
                a = h.consumed()
                c = h.app.challenge(h.controller, d.ref('approval', a.approval_id, a),
                    action='dispatch', command_id='ordered-dispatch')
                operations = {
                    'revoke': lambda: h.repo.change_permissions(h.controller, 'fixture-approver',
                        tuple(x for x in h.repo._state['permissions']['fixture-approver'] if x != 'approve')),
                    'dispatch': lambda: ApprovalApplication(h.repo).execute(h.controller, c),
                }
                second = 'dispatch' if first == 'revoke' else 'revoke'
                ordered_race(operations[first], operations[second])
                s = h.repo.snapshot()
                receipt = parse_payload(s['records'][s['receipts'][c.command_id]]).payload
                self.assertEqual(receipt.outcome, 'rejected' if first == 'revoke' else 'applied')
                self.assertEqual(s['intents'][a.consumed_intent_id]['state'],
                    'prepared' if first == 'revoke' else 'dispatching')
                self.assertTrue(all(x['state'] == 'held' for x in s['reservations'].values()))
                if first == 'revoke':
                    h.repo.change_permissions(h.controller, 'fixture-approver',
                        h.authority._principals['fixture-approver'].allowed_actions)
                    before = h.repo.snapshot()
                    self.assertEqual(h.app.execute(h.controller, c), receipt)
                    self.assertEqual(h.repo.snapshot(), before)
                    self.assertEqual(h.command(a, 'dispatch', 'explicit-new-command').outcome, 'applied')

    def test_dispatch_checks_original_session_binding_not_another_live_session(self):
        h = Harness()
        a = h.consumed()
        other = h.authority.issue_session('fixture-approver')
        other_sid = h.repo._state['handles'][other]
        # Deliberately corrupt only the session-head lookup to exercise the binding
        # check independently of ordinary repository history validation.
        with h.repo._lock:
            s = h.repo._copy()
            s['heads'][('session', a.session_id)] = s['heads'][('session', other_sid)]
            h.repo._state = s
        result = h.command(a, 'dispatch', 'wrong-live-session')
        self.assertEqual((result.outcome, result.reason_code), ('rejected', 'authority_denied'))
        self.assertEqual(h.repo.snapshot()['intents'][a.consumed_intent_id]['state'], 'prepared')

    def test_dispatch_original_disconnect_never_implicitly_cancels(self):
        h = Harness()
        a = h.consumed()
        h.app.control(h.approver, 'disconnect')
        before = h.repo.snapshot()
        result = h.command(a, 'dispatch', 'disconnected-original')
        self.assertEqual((result.outcome, result.reason_code), ('rejected', 'session_inactive'))
        after = h.repo.snapshot()
        for name in ('intents', 'reservations', 'outbox', 'claims'):
            self.assertEqual(after[name], before[name])
        self.assertEqual(self.close(h, a).outcome, 'applied')

    def test_protective_new_controller_survives_permission_report_and_risk_loss(self):
        h = Harness()
        a = h.consumed()
        fresh = h.authority.issue_session('fixture-controller')
        reader = h.authority.issue_reader('fixture-reporting')
        h.repo.change_permissions(h.controller, 'fixture-approver', ())
        h.repo.replace_source(h.controller, rights_changed(h.source))
        h.repo.record_risk(h.controller, 'blocked')
        result = self.close(h, a, handle=fresh)
        self.assertEqual(result.outcome, 'applied')
        s = h.repo.snapshot()
        wr = parse_payload(s['records'][result.result_ref]).payload
        self.assertEqual(wr.state, 'unsent_confirmed')
        self.assertEqual(s['intents'][a.consumed_intent_id]['state'], 'aborted_unsent')
        self.assertEqual(len(s['claims']), 1)
        with self.assertRaisesRegex(d.ApprovalDenied, '^rights_denied$'):
            h.app.query(reader, account_ref=a.account_ref, purpose='financial')
        before = h.repo.snapshot()
        self.assertEqual(self.close(h, a, handle=fresh), result)
        self.assertEqual(h.repo.snapshot(), before)

    def test_flood_completions_and_replays_cannot_spend_atomic_closure(self):
        h = Harness()
        a = h.consumed()
        cs = self.flood(h, a)
        original_commands = set(h.repo.snapshot()['commands'])
        self.assertGreaterEqual(len(cs), 2)
        for i, c in enumerate(cs):
            receipt = h.app.execute(h.controller, c)
            self.assertEqual(receipt.outcome, 'applied' if i == 0 else 'rejected')
            self.assert_capacity(h)
            before = h.repo.snapshot()
            self.assertEqual(h.app.challenge(h.controller, c.target_ref, action=c.action,
                command_id=c.command_id), c)
            self.assertEqual(h.app.execute(h.controller, c), receipt)
            self.assertEqual(h.repo.snapshot(), before)
        receipt = self.close(h, a)
        self.assertEqual(receipt.outcome, 'applied')
        s = h.repo.snapshot()
        self.assertTrue(original_commands <= set(s['commands']))
        self.assertEqual(parse_payload(s['records'][receipt.result_ref]).payload.state, 'requested')
        self.assertTrue(all(x['state'] == 'held' for x in s['reservations'].values()))

    def test_expired_and_permission_denied_completions_leave_protected_space(self):
        for failure in ('expired', 'authority_denied'):
            with self.subTest(failure=failure):
                h = Harness()
                a = h.consumed()
                cs = self.flood(h, a)
                if failure == 'expired':
                    h.clock.at = '2024-03-08T14:31:20Z'
                else:
                    h.repo.change_permissions(h.controller, 'fixture-approver', ())
                for c in cs:
                    result = h.app.execute(h.controller, c)
                    self.assertEqual((result.outcome, result.reason_code), ('rejected', failure))
                    self.assert_capacity(h)
                self.assertEqual(self.close(h, a).outcome, 'applied')
                self.assertEqual(h.repo.snapshot()['intents'][a.consumed_intent_id]['state'], 'aborted_unsent')

    def test_terminal_transition_retains_every_outstanding_completion_reservation(self):
        for terminal in ('denied', 'expired'):
            with self.subTest(terminal=terminal):
                h = Harness()
                _, a = h.present()
                r = d.ref('approval', a.approval_id, a)
                cs = [h.app.challenge(h.approver, r, action='approve', command_id='pending-' + str(i))
                    for i in range(3)]
                deny = h.app.challenge(h.approver, r, action='deny', command_id='deny')
                if terminal == 'expired':
                    h.clock.at = '2024-03-08T14:31:28Z'
                result = h.app.execute(h.approver, deny)
                self.assertEqual(h.head(a).state, terminal)
                self.assertEqual(result.outcome, 'applied' if terminal == 'denied' else 'rejected')
                self.assert_capacity(h)
                for c in cs:
                    self.assertEqual(h.app.execute(h.approver, c).outcome, 'rejected')
                    self.assert_capacity(h)
                self.assertNotIn(a.approval_id, h.repo.snapshot()['holds'])
                before = h.repo.snapshot()
                self.assertEqual(h.app.execute(h.approver, deny), result)
                self.assertEqual(h.repo.snapshot(), before)

    def test_simultaneous_issuance_then_withdraw_before_all_dispatch_completions(self):
        h = Harness()
        a = h.consumed()
        r = d.ref('approval', a.approval_id, a)
        barrier = Barrier(12)
        def issue(i):
            barrier.wait(timeout=20)
            try:
                return ApprovalApplication(h.repo).challenge(h.controller, r, action='dispatch',
                    command_id='simultaneous-' + str(i))
            except d.ApprovalDenied as error:
                return error.reason
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(issue, range(12)))
        cs = [x for x in results if type(x) is d.ActionChallenge]
        self.assertGreaterEqual(len(cs), 2)
        self.assertTrue(all(type(x) is d.ActionChallenge or x == 'capacity_exceeded' for x in results))
        self.assertIn('capacity_exceeded', results)
        self.assert_capacity(h)
        self.assertEqual(self.close(h, a).outcome, 'applied')
        for c in cs:
            result = h.app.execute(h.controller, c)
            self.assertEqual((result.outcome, result.reason_code), ('rejected', 'terminal_state'))
        self.assertEqual(h.repo.snapshot()['intents'][a.consumed_intent_id]['state'], 'aborted_unsent')

    def test_protective_pending_expired_commands_cannot_spend_final_closure(self):
        h = Harness()
        a = h.consumed()
        cs = self.flood(h, a, action='withdraw')
        h.clock.at = '2024-03-08T14:31:20Z'
        for c in cs:
            result = h.app.execute(h.controller, c)
            self.assertEqual((result.outcome, result.reason_code), ('rejected', 'expired'))
            self.assert_capacity(h)
        # No new free capacity is available: this succeeds using exactly the
        # protected hold, without needing another independently pending command.
        n, b = h.repo._usage(h.repo._state)
        h.repo._capacity = n + sum(v[0] for v in h.repo._state['holds'].values())
        h.repo._byte_capacity = b + sum(v[1] for v in h.repo._state['holds'].values())
        self.assertEqual(self.close(h, a).outcome, 'applied')

    def test_atomic_withdraw_staging_failure_rolls_back_issuance_and_all_charges(self):
        for label in ('history', 'receipt', 'completion_commit'):
            with self.subTest(label=label):
                h = Harness()
                a = h.consumed()
                before = h.repo.snapshot()
                original_stage, commits = h.repo._stage, []
                def stage(value):
                    if value == 'commit':
                        commits.append(value)
                    if value == label or label == 'completion_commit' and value == 'commit' and len(commits) == 2:
                        raise d.ApprovalDenied('commit_failed')
                    return original_stage(value)
                with patch.object(h.repo, '_stage', stage):
                    with self.assertRaisesRegex(d.ApprovalDenied, '^commit_failed$'):
                        self.close(h, a, command_id='rollback')
                self.assertEqual(h.repo.snapshot(), before)
                self.assertEqual(self.close(h, a, command_id='rollback').outcome, 'applied')

    def test_exact_eight_record_closure_at_record_and_byte_capacity(self):
        h = Harness()
        a = h.consumed()
        with h.repo._lock:
            s = h.repo._copy()
            s['holds'][a.approval_id] = (8, 8 * 65536)
            h.repo._state = s
            n, b = h.repo._usage(s)
            h.repo._capacity = n + sum(v[0] for v in s['holds'].values())
            h.repo._byte_capacity = b + sum(v[1] for v in s['holds'].values())
        before = h.repo.snapshot()
        with self.assertRaisesRegex(d.ApprovalDenied, '^capacity_exceeded$'):
            h.app.challenge(h.controller, d.ref('approval', a.approval_id, a),
                action='withdraw', command_id='cannot-leave-pending')
        self.assertEqual(h.repo.snapshot(), before)
        result = self.close(h, a)
        self.assertEqual(result.outcome, 'applied')
        s = h.repo.snapshot()
        self.assertEqual(s['holds'][a.approval_id][0], 0)
        self.assertEqual(s['intents'][a.consumed_intent_id]['state'], 'aborted_unsent')
        n, b = h.repo._usage(h.repo._state)
        self.assertLessEqual(n + sum(v[0] for v in s['holds'].values()), h.repo._capacity)
        self.assertLessEqual(b + sum(v[1] for v in s['holds'].values()), h.repo._byte_capacity)

    def test_atomic_withdraw_does_not_take_over_independently_issued_command(self):
        h = Harness()
        a = h.consumed()
        c = h.app.challenge(h.controller, d.ref('approval', a.approval_id, a),
            action='withdraw', command_id='two-step')
        h.clock.at = '2024-03-08T14:31:20Z'
        before = h.repo.snapshot()
        with self.assertRaisesRegex(d.ApprovalDenied, '^replay_conflict$'):
            self.close(h, a, command_id='two-step')
        self.assertEqual(h.repo.snapshot(), before)
        result = h.app.execute(h.controller, c)
        self.assertEqual((result.outcome, result.reason_code), ('rejected', 'expired'))
        self.assertEqual(self.close(h, a, command_id='fresh').outcome, 'applied')

    def test_invalid_new_actions_cannot_mint_commands_or_consume_protection(self):
        h = Harness()
        a = h.consumed()
        before = h.repo.snapshot()
        for i in range(12):
            for action in ('approve', 'deny', 'revoke', 'admit'):
                with self.assertRaisesRegex(d.ApprovalDenied, '^terminal_state$'):
                    h.app.challenge(h.approver, d.ref('approval', a.approval_id, a),
                        action=action, command_id='invalid-' + action + str(i))
        self.assertEqual(h.repo.snapshot(), before)
        self.assertEqual(self.close(h, a).outcome, 'applied')

    def test_atomic_withdraw_clock_fault_rolls_back_finance_but_keeps_fault_latch(self):
        h = Harness()
        a = h.consumed()
        before = h.repo.snapshot()
        ticks = iter(('2024-03-08T14:31:10Z', None))
        h.authority._clock = lambda: next(ticks)
        with self.assertRaisesRegex(d.ApprovalDenied, '^clock_invalid$'):
            self.close(h, a)
        after = h.repo.snapshot()
        self.assertTrue(after['clock_fault'])
        self.assertEqual(after['mode'], 'faulted')
        for name in before:
            if name not in ('clock_fault', 'mode'):
                self.assertEqual(after[name], before[name], name)


if __name__ == '__main__':
    unittest.main()
