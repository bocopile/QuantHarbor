"""Q26 AR1·AR2 재현과 종료 예약 회귀."""
import unittest
from dataclasses import replace
from unittest.mock import patch

from quantharbor.domain import approval as d
from quantharbor.domain.serialization import parse_payload
from synthetic_approval import Harness, rights_changed


class ApprovalReview(unittest.TestCase):
    def session(self, h, sid):
        s = h.repo.snapshot()
        return parse_payload(s['records'][s['heads'][('session', sid)]]).payload

    def assert_preserved(self, before, after, names):
        for name in names:
            self.assertEqual(after[name], before[name], name)
        self.assertTrue(before['records'].items() <= after['records'].items())

    def assert_capacity(self, h):
        s = h.repo._state
        n, b = h.repo._usage(s)
        self.assertLessEqual(n + sum(v[0] for v in s['holds'].values()), h.repo._capacity)
        self.assertLessEqual(b + sum(v[1] for v in s['holds'].values()), h.repo._byte_capacity)

    def test_AR1_repeated_stop_preserves_disconnect(self):
        h = Harness()
        sid = h.repo._state['handles'][h.controller]
        self.assertEqual(h.repo.snapshot()['holds'][sid][0], 6)
        # Control must work independently of source validation/reproduction.
        with patch.object(h.repo, '_source_check', side_effect=AssertionError('source used')) as source:
            for _ in range(5):
                h.app.control(h.controller, 'stop')
            try:
                h.app.control(h.controller, 'disconnect')
            except d.ApprovalDenied as error:
                self.fail('AR1 protected disconnect denied: ' + error.reason)
            source.assert_not_called()
        s = h.repo.snapshot()
        session = parse_payload(s['records'][s['heads'][('session', sid)]]).payload
        self.assertEqual(session.state, 'paused')
        self.assertEqual(s['mode'], 'stopped')

    def test_AR2_disconnect_releases_unusable_session_hold(self):
        h = Harness()
        sid = h.repo._state['handles'][h.approver]
        before = h.repo.snapshot()
        self.assertEqual(before['holds'][sid], (8, 8 * 65536))
        h.app.control(h.approver, 'disconnect')
        after = h.repo.snapshot()
        self.assertNotIn(sid, after['holds'], 'AR2 paused session retains unusable closure budget')
        self.assertTrue(before['records'].items() <= after['records'].items())
        session = parse_payload(after['records'][after['heads'][('session', sid)]]).payload
        self.assertEqual(session.state, 'paused')
        self.assertEqual(session.previous_ref, before['heads'][('session', sid)])

    def test_repeated_stop_same_and_changed_timestamp_is_exact_noop(self):
        h = Harness()
        with patch.object(h.repo, '_source_check', side_effect=AssertionError('source used')) as source:
            first = h.app.control(h.controller, 'stop')
            before = h.repo.snapshot()
            for at in ('2024-03-08T14:31:08Z', '2024-03-08T14:31:09Z', '2024-03-08T14:31:10Z'):
                h.clock.at = at
                self.assertEqual(h.app.control(h.controller, 'stop'), first)
                self.assertEqual(h.repo.snapshot(), before)
            source.assert_not_called()
        h.app.control(h.controller, 'disconnect')

    def test_explicit_resume_then_stop_creates_new_evidence_and_can_disconnect(self):
        h = Harness()
        with patch.object(h.repo, '_source_check', side_effect=AssertionError('source used')) as source:
            first = h.app.control(h.controller, 'stop')
            self.assertEqual(h.repo.snapshot()['mode'], 'stopped')
            h.app.control(h.controller, 'resume')
            self.assertEqual(h.repo.snapshot()['mode'], 'running')
            second = h.app.control(h.controller, 'stop')
            self.assertNotEqual(first, second)
            self.assertEqual(h.app.control(h.controller, 'stop'), second)
            h.app.control(h.controller, 'disconnect')
            self.assertEqual(h.repo.snapshot()['mode'], 'stopped')
            source.assert_not_called()

    def test_repeated_stop_still_requires_current_authority_and_valid_session(self):
        for loss, reason in (('permission', 'authority_denied'), ('liveness', 'session_inactive'),
                             ('expiry', 'session_expired'), ('disconnect', 'session_inactive')):
            with self.subTest(loss=loss):
                h = Harness()
                h.app.control(h.controller, 'stop')
                if loss == 'permission':
                    actions = tuple(a for a in h.repo._state['permissions']['fixture-controller'] if a != 'stop')
                    h.repo.change_permissions(h.controller, 'fixture-controller', actions)
                elif loss == 'liveness':
                    h.clock.at = '2024-03-08T14:31:38Z'
                elif loss == 'expiry':
                    h.clock.at = '2024-03-08T14:33:08Z'
                else:
                    h.app.control(h.controller, 'disconnect')
                before = h.repo.snapshot()
                with self.assertRaisesRegex(d.ApprovalDenied, '^' + reason + '$'):
                    h.app.control(h.controller, 'stop')
                self.assertEqual(h.repo.snapshot(), before)

    def test_full_store_runtime_heartbeat_and_resume_leave_stop_and_disconnect(self):
        for action in ('runtime', 'heartbeat', 'resume'):
            with self.subTest(action=action):
                h = Harness()
                # Exact current record/byte envelope: no unallocated room can hide
                # accidental use of the protected closure budget.
                s = h.repo._state
                n, b = h.repo._usage(s)
                h.repo._capacity = n + sum(v[0] for v in s['holds'].values())
                h.repo._byte_capacity = b + sum(v[1] for v in s['holds'].values())
                with patch.object(h.repo, '_source_check', side_effect=AssertionError('source used')) as source:
                    for _ in range(8):
                        before = h.repo.snapshot()
                        try:
                            if action == 'runtime':
                                h.repo.record_risk(h.controller, 'clear')
                            else:
                                h.app.control(h.controller, action)
                        except d.ApprovalDenied as error:
                            self.assertEqual(error.reason, 'capacity_exceeded')
                            self.assertEqual(h.repo.snapshot(), before)
                            break
                    else:
                        self.fail('unbounded control history')
                    before = h.repo.snapshot()
                    stop = h.app.control(h.controller, 'stop')
                    self.assertEqual(h.app.control(h.controller, 'stop'), stop)
                    h.app.control(h.controller, 'disconnect')
                    self.assert_preserved(before, h.repo.snapshot(),
                        ('risk_ref', 'intents', 'reservations', 'outbox', 'claims'))
                    self.assert_capacity(h)
                    source.assert_not_called()

    def test_disconnect_preserves_live_completion_and_withdraw_holds(self):
        h = Harness()
        a = h.consumed()
        h.app.challenge(h.controller, d.ref('approval', a.approval_id, a),
            action='dispatch', command_id='outstanding-before-disconnect')
        before = h.repo.snapshot()
        hold = before['holds'][a.approval_id]
        self.assertGreaterEqual(hold[0], 4 + 8)
        self.assertEqual(h.repo._pending_budget(h.repo._state, a.approval_id), (4, 4 * 65536))
        h.app.control(h.approver, 'disconnect')
        h.app.control(h.controller, 'stop')
        after = h.repo.snapshot()
        self.assertEqual(after['holds'][a.approval_id], hold)
        self.assert_preserved(before, after, ('commands', 'nonces', 'receipts', 'claims',
            'intents', 'outbox', 'reservations', 'risk_ref'))
        self.assertEqual(h.head(a).state, 'consumed')
        self.assertEqual(after['mode'], 'stopped')
        self.assert_capacity(h)

    def test_restore_releases_legacy_paused_and_expired_generation_holds(self):
        h = Harness()
        sid = h.repo._state['handles'][h.approver]
        h.app.control(h.approver, 'disconnect')
        # A current snapshot made by the previous implementation can legitimately
        # contain this unusable paused-session reservation.
        with h.repo._lock:
            s = h.repo._copy()
            s['holds'][sid] = (6, 6 * 65536)
            h.repo._room(s)
            h.repo._state = s
        h.clock.at = '2024-03-08T14:33:08Z'
        before = h.repo.snapshot()
        old_sessions = {identity for kind, identity in before['heads'] if kind == 'session'}
        controller_sid = h.repo._state['handles'][h.controller]
        self.assertEqual(self.session(h, controller_sid).expires_at, '2024-03-08T14:33:08.000000Z')
        generation = h.repo.restore(before)
        after = h.repo.snapshot()
        self.assertNotEqual(generation, before['generation'])
        self.assertTrue(old_sessions.isdisjoint(after['holds']))
        self.assertEqual(after['heads'][('session', sid)], before['heads'][('session', sid)])
        self.assertEqual(self.session(h, sid).state, 'paused')
        self.assertEqual(self.session(h, controller_sid).state, 'invalidated')
        self.assert_preserved(before, after, ('receipts', 'commands', 'nonces', 'intents',
            'reservations', 'claims', 'outbox'))
        for handle in (h.approver, h.controller):
            with self.assertRaisesRegex(d.ApprovalDenied, '^authority_denied$'):
                h.app.control(handle, 'heartbeat')
        self.assert_capacity(h)

    def test_restore_releases_other_terminal_session_holds_without_erasing_history(self):
        for terminal in ('faulted', 'invalidated'):
            with self.subTest(terminal=terminal):
                h = Harness()
                sid = h.repo._state['handles'][h.approver]
                old = self.session(h, sid)
                # Exercise all closed SessionRecord states in a legacy snapshot.
                with h.repo._lock:
                    s = h.repo._copy()
                    h.repo._put(s, 'session', replace(old, state=terminal, state_version=2,
                        previous_ref=d.ref('session', sid, old)))
                    h.repo._room(s)
                    h.repo._state = s
                before = h.repo.snapshot()
                h.repo.restore(before)
                after = h.repo.snapshot()
                self.assertNotIn(sid, after['holds'])
                self.assertEqual(after['heads'][('session', sid)], before['heads'][('session', sid)])
                self.assertTrue(before['records'].items() <= after['records'].items())

    def test_disconnect_and_restore_failure_roll_back_holds_and_state(self):
        for action in ('disconnect', 'restore'):
            for failure in ('commit', 'operation'):
                with self.subTest(action=action, failure=failure):
                    h = Harness()
                    before = h.repo.snapshot()
                    epoch, generation = h.authority._epoch, h.authority._generation
                    operation = (lambda: h.app.control(h.approver, 'disconnect')) if action == 'disconnect' else (
                        lambda: h.repo.restore(before))
                    context = h.repo.inject_failure('commit') if failure == 'commit' else patch.object(
                        h.repo, '_event', side_effect=RuntimeError('synthetic operation fault'))
                    with context:
                        with self.assertRaisesRegex(d.ApprovalDenied,
                                '^commit_failed$' if failure == 'commit' else '^invalid_contract$'):
                            operation()
                    self.assertEqual(h.repo.snapshot(), before)
                    self.assertEqual((h.authority._epoch, h.authority._generation), (epoch, generation))

    def test_disconnect_and_restore_clock_failure_preserve_holds_and_latch_fault(self):
        for action in ('disconnect', 'restore'):
            for at in (None, '2024-03-08T14:31:07Z'):
                with self.subTest(action=action, at=at):
                    h = Harness()
                    before = h.repo.snapshot()
                    epoch, generation = h.authority._epoch, h.authority._generation
                    h.clock.at = at
                    with self.assertRaisesRegex(d.ApprovalDenied, '^clock_invalid$'):
                        if action == 'disconnect':
                            h.app.control(h.approver, 'disconnect')
                        else:
                            h.repo.restore(before)
                    after = h.repo.snapshot()
                    self.assertEqual(after, before | {'clock_fault': True, 'mode': 'faulted'})
                    self.assertEqual((h.authority._epoch, h.authority._generation), (epoch, generation))

    def test_restore_preserves_unknown_reservations_and_new_controller_protective_withdraw(self):
        h = Harness()
        a = h.consumed()
        self.assertEqual(h.command(a, 'dispatch', 'before-unknown').outcome, 'applied')
        h.repo.record_unknown(h.controller, a.consumed_intent_id)
        h.app.control(h.approver, 'disconnect')
        h.app.control(h.controller, 'disconnect')
        before = h.repo.snapshot()
        h.repo.restore(before)
        after = h.repo.snapshot()
        self.assertEqual(after['holds'][a.approval_id], before['holds'][a.approval_id])
        self.assert_preserved(before, after, ('receipts', 'commands', 'nonces', 'claims',
            'intents', 'outbox', 'reservations'))
        fresh = h.authority.issue_session('fixture-controller')
        h.repo.replace_source(fresh, rights_changed(h.source))
        h.repo.record_risk(fresh, 'blocked')
        h.repo.change_permissions(fresh, 'fixture-approver', ())
        protected = h.repo.snapshot()
        receipt = h.app.withdraw(fresh, d.ref('approval', a.approval_id, a), command_id='protected-after-restore')
        self.assertEqual(receipt.outcome, 'applied')
        after = h.repo.snapshot()
        withdrawal = parse_payload(after['records'][receipt.result_ref]).payload
        self.assertEqual(withdrawal.state, 'requested')
        self.assert_preserved(protected, after, ('claims', 'intents', 'outbox', 'reservations'))
        self.assertTrue(all(v['state'] == 'held' for v in after['reservations'].values()))
        self.assertEqual(after['mode'], 'stopped')
        self.assertEqual(h.head(a).state, 'consumed')
        with self.assertRaisesRegex(d.ApprovalDenied, '^reconciliation_required$'):
            h.app.control(fresh, 'resume')
        self.assert_capacity(h)

    def test_closed_sessions_release_only_holds_until_finite_history_is_full(self):
        h = Harness()
        closed = set()
        for _ in range(128):
            before = h.repo.snapshot()
            try:
                handle = h.authority.issue_session('fixture-approver')
            except d.ApprovalDenied as error:
                self.assertEqual(error.reason, 'capacity_exceeded')
                self.assertEqual(h.repo.snapshot(), before)
                break
            sid = h.repo._state['handles'][handle]
            h.app.control(handle, 'disconnect')
            closed.add(sid)
            after = h.repo.snapshot()
            self.assertTrue(closed.isdisjoint(after['holds']))
            self.assertTrue(before['records'].items() <= after['records'].items())
            self.assert_capacity(h)
        else:
            self.fail('finite history unexpectedly allowed unlimited session starts')
        self.assertGreater(len(closed), 1)


if __name__ == '__main__':
    unittest.main()
