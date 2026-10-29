"""Q26 공유 메모리 simulation. DB transaction/실제 인증/egress 구현이 아니다."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from threading import RLock
from uuid import uuid4

from quantharbor.application.approval import source_bytes, validate_source
from quantharbor.domain import approval as d
from quantharbor.domain.ledger import integer
from quantharbor.domain.primitives import identifier, utc_instant
from quantharbor.domain.serialization import parse_payload
from quantharbor.domain.target import ref as target_ref
from quantharbor.ports.approval import ApprovalSource
from quantharbor.runtime.boundary import authorize, synthetic_binding


_ROLE_ACTIONS = {
    'approver': ('present', 'approve', 'deny', 'revoke', 'withdraw', 'admit', 'query', 'heartbeat', 'disconnect'),
    'controller': ('session', 'stop', 'resume', 'dispatch', 'withdraw', 'query', 'runtime', 'policy', 'heartbeat', 'disconnect'),
    'reporting': ('query',), 'research': ('query',),
}
_VERSIONED = ('approval', 'session', 'withdrawal')
# Maximum completion records, including authenticated rejection/invalidation.
_COMPLETION = {'approve': 4, 'deny': 4, 'revoke': 4, 'admit': 10, 'dispatch': 4, 'withdraw': 5}
_ACTION_STATES = {'approve': ('pending',), 'deny': ('pending',), 'revoke': ('approved',),
    'admit': ('approved',), 'dispatch': ('consumed',), 'withdraw': ('approved', 'consumed')}
_IDS = {'approval': 'approval_id', 'session': 'session_id', 'withdrawal': 'request_id',
    'policy': 'policy_id', 'principal': 'principal_id', 'presentation': 'presentation_id',
    'challenge': 'challenge_id', 'receipt': 'command_id', 'runtime': 'event_id'}


def _safe(function):
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except d.ApprovalDenied:
            raise
        except Exception:
            raise d.ApprovalDenied('invalid_contract') from None
    return call


class _Opaque:
    __slots__ = ()

    def __reduce__(self):
        raise d.ApprovalDenied('authority_denied')

    def __repr__(self):
        return '<synthetic capability>'


class _SessionHandle(_Opaque):
    __slots__ = ()


class _ReadPermit(_Opaque):
    __slots__ = ()


@dataclass(frozen=True, slots=True)
class FixturePrincipal:
    principal_id: str
    account_ref: str
    role: str
    allowed_actions: tuple[str, ...]

    def __post_init__(self):
        identifier(self.principal_id)
        identifier(self.account_ref)
        if (self.role not in _ROLE_ACTIONS or type(self.allowed_actions) is not tuple or
                not set(self.allowed_actions) <= set(_ROLE_ACTIONS[self.role])):
            raise d.ApprovalDenied('authority_denied')


class SyntheticAuthority:
    """Trusted composition fixture issuer. 등록 ID는 실제 사람 인증이 아니다."""
    @_safe
    def __init__(self, principals, *, clock, generation='synthetic-generation-1'):
        if type(principals) is not tuple or not 1 <= len(principals) <= 8 or not callable(clock):
            raise d.ApprovalDenied()
        for p in principals:
            if type(p) is not FixturePrincipal:
                raise d.ApprovalDenied()
            FixturePrincipal(p.principal_id, p.account_ref, p.role, p.allowed_actions)
        if len({p.principal_id for p in principals}) != len(principals):
            raise d.ApprovalDenied()
        identifier(generation)
        self._principals = {p.principal_id: p for p in principals}
        self._clock = clock
        self._generation = generation
        self._instance = 'synthetic-issuer:' + uuid4().hex
        self._repository = None
        self._epoch = 0
        self._last_observed = None

    @_safe
    def issue_session(self, principal_id):
        if self._repository is None:
            raise d.ApprovalDenied('authority_denied')
        return self._repository._issue(self, principal_id, reader=False)

    @_safe
    def issue_reader(self, principal_id):
        if self._repository is None:
            raise d.ApprovalDenied('authority_denied')
        return self._repository._issue(self, principal_id, reader=True)


class SyntheticApprovalRepository:
    """모든 instance가 이 저장소 하나를 공유해야 한다. append/consume API 없음."""
    @_safe
    def __init__(self, authority, source, policy, *, capacity=128, byte_capacity=8388608):
        if type(authority) is not SyntheticAuthority or authority._repository is not None or type(source) is not ApprovalSource:
            raise d.ApprovalDenied()
        policy = d.checked(policy)
        if type(policy) is not d.SyntheticApprovalPolicy or policy.account_ref != source.request.account_ref:
            raise d.ApprovalDenied()
        integer(capacity, 1, 128)
        integer(byte_capacity, 1, 8388608)
        self._lock = RLock()
        self._authority = authority
        self._source = source
        self._capacity, self._byte_capacity = capacity, byte_capacity
        self._failure = None
        self._aggregate_id = 'synthetic-aggregate:' + uuid4().hex
        self._state = {'version': 0, 'records': {}, 'heads': {}, 'handles': {}, 'readers': {},
            'commands': {}, 'nonces': {}, 'receipts': {}, 'holds': {}, 'intents': {},
            'reservations': {}, 'outbox': {}, 'claims': {}, 'mode': 'stopped',
            'risk_ref': None, 'last_at': None, 'clock_fault': False,
            'generation': authority._generation, 'restored': False,
            'source_bytes': len(source_bytes(source)), 'policy': None}
        self._state['permissions'] = {p.principal_id: p.allowed_actions for p in authority._principals.values()}
        self._state['policy'] = self._put(self._state, 'policy', policy)
        self._room(self._state)
        authority._repository = self

    def _copy(self):
        # Handles retain identity; every mutable aggregate collection is separately staged.
        return {k: dict(v) if type(v) is dict else v for k, v in self._state.items()}

    def _usage(self, s):
        maps = ('records', 'heads', 'handles', 'readers', 'commands', 'nonces', 'receipts',
                'holds', 'intents', 'reservations', 'outbox', 'claims', 'permissions')
        records = sum(len(s[k]) for k in maps) + len(self._authority._principals) + 1
        size = s['source_bytes'] + sum(len(raw) for raw in s['records'].values())
        # Bounded indexes/registry/primitive runtime values are charged conservatively.
        size += 4096 * (records - len(s['records']))
        return records, size

    def _room(self, s):
        records, size = self._usage(s)
        if (records + sum(v[0] for v in s['holds'].values()) > self._capacity or
                size + sum(v[1] for v in s['holds'].values()) > self._byte_capacity):
            raise d.ApprovalDenied('capacity_exceeded')

    def _command_refs(self, s, command_id):
        """Lookup seam; execution may resolve completed immutable evidence."""
        return s['commands'].get(command_id), s['receipts'].get(command_id)

    def _command_nonce(self, s, challenge, reference, receipt):
        return s['nonces'].get(challenge.nonce) == reference

    def _pending_budget(self, s, approval_id):
        # Existing command/nonce indexes identify reservations; no uncharged side index.
        n = 0
        for command_id, r in s['commands'].items():
            if command_id not in s['receipts']:
                c = self._get(s, r)
                if c.target_ref.id == approval_id and c.authority_generation == s['generation']:
                    n += _COMPLETION[c.action]
        return n, n * 65536

    def _commit(self, s, *, owner=None, release=False):
        if owner is not None and owner in s['holds']:
            old_n, old_b = self._usage(self._state)
            new_n, new_b = self._usage(s)
            n, b = s['holds'][owner]
            s['holds'][owner] = (n - max(0, new_n - old_n), b - max(0, new_b - old_b))
            if min(s['holds'][owner]) < 0:
                raise d.ApprovalDenied('capacity_exceeded')
            if release:
                pending = self._pending_budget(s, owner)
                if pending[0]:
                    s['holds'][owner] = pending
                else:
                    del s['holds'][owner]
        self._room(s)
        self._stage('commit')
        s['version'] = self._state['version'] + 1
        self._state = s

    def _stage(self, label):
        if self._failure == label:
            raise d.ApprovalDenied('commit_failed')

    @contextmanager
    def inject_failure(self, label):
        """합성 시험 전용. 잠금 안에서만 활성화되며 production fault injector가 아니다."""
        if label not in ('consumed', 'claim', 'intent', 'reservation', 'outbox', 'history', 'receipt', 'commit'):
            raise d.ApprovalDenied()
        with self._lock:
            old, self._failure = self._failure, label
            try:
                yield
            finally:
                self._failure = old

    def _put(self, s, kind, obj, *, identity=None):
        obj = d.checked(obj)
        identity = identity or getattr(obj, _IDS.get(kind, ''), None)
        if identity is None:
            identity = 'evidence:' + sha256(d.encoded(obj)).hexdigest()
        r = d.ref(kind, identity, obj)
        raw = d.encoded(obj)
        if r in s['records']:
            if s['records'][r] != raw:
                raise d.ApprovalDenied('version_conflict')
            return r
        for old in s['records']:
            if (old.kind, old.id, old.version) == (r.kind, r.id, r.version) and old != r:
                raise d.ApprovalDenied('version_conflict')
        if kind in _VERSIONED:
            prior = s['heads'].get((kind, identity))
            if obj.previous_ref != prior or obj.state_version != (prior.version + 1 if prior else 1):
                raise d.ApprovalDenied('version_conflict')
            if prior:
                prev = self._get(s, prior)
                if kind == 'approval':
                    if obj.state not in d.TRANSITIONS.get(prev.state, ()):
                        raise d.ApprovalDenied('terminal_state')
                    fixed = ('approval_id', 'principal_ref', 'session_id', 'authority_generation', 'environment',
                        'account_ref', 'candidate_ref', 'presentation_ref', 'candidate_evidence_ref',
                        'target_policy_ref', 'approval_policy_ref', 'authorized_action', 'terms', 'created_at',
                        'valid_from', 'expires_at')
                    if any(getattr(prev, k) != getattr(obj, k) for k in fixed):
                        raise d.ApprovalDenied('invalid_contract')
                if kind == 'session' and (prev.session_id, prev.principal_ref, prev.account_ref,
                    prev.environment, prev.authority_generation, prev.expires_at) != (
                    obj.session_id, obj.principal_ref, obj.account_ref, obj.environment,
                    obj.authority_generation, obj.expires_at):
                    raise d.ApprovalDenied('invalid_contract')
            s['heads'][(kind, identity)] = r
        s['records'][r] = raw
        return r

    def _get(self, s, r):
        if type(r) is not d.ApprovalRef:
            raise d.ApprovalDenied()
        raw = s['records'].get(r)
        if raw is None:
            raise d.ApprovalDenied('source_unresolved')
        obj = parse_payload(raw).payload
        if d.ref(r.kind, r.id, obj) != r:
            raise d.ApprovalDenied('invalid_contract')
        return obj

    def _event(self, s, kind, target, at):
        obj = d.SyntheticRuntimeEvidence('event:' + uuid4().hex, self._aggregate_id,
            s['version'] + 1, s['generation'], 'synthetic', self._policy(s).account_ref, kind,
            target, at, 'synthetic_aggregate', d.FIXTURE_REF)
        return self._put(s, 'runtime', obj)

    def _policy(self, s):
        return self._get(s, s['policy'])

    def _now(self):
        try:
            now = utc_instant(self._authority._clock())
            if (self._authority._last_observed is not None and now < self._authority._last_observed):
                raise ValueError()
        except Exception:
            # Latch is a control fault, never a financial-state mutation or timestamp rewind.
            self._state = self._state | {'clock_fault': True, 'mode': 'faulted'}
            raise d.ApprovalDenied('clock_invalid') from None
        if self._state['clock_fault']:
            raise d.ApprovalDenied('clock_invalid')
        self._authority._last_observed = now
        return now

    def _auth(self, s, handle, action, at, *, protective=False, reader=False):
        if reader:
            if type(handle) is not _ReadPermit or handle not in s['readers']:
                raise d.ApprovalDenied('authority_denied')
            principal = self._get(s, s['readers'][handle])
            session = None
        else:
            if type(handle) is not _SessionHandle or handle not in s['handles']:
                raise d.ApprovalDenied('authority_denied')
            sid = s['handles'][handle]
            session = self._get(s, s['heads'][('session', sid)])
            principal = self._get(s, session.principal_ref)
            if session.state != 'running':
                raise d.ApprovalDenied('session_inactive')
            if at >= session.expires_at:
                raise d.ApprovalDenied('session_expired')
            if at >= session.liveness_deadline:
                raise d.ApprovalDenied('session_inactive')
        registered = self._authority._principals.get(principal.principal_id)
        if (registered is None or action not in registered.allowed_actions or
                action not in s['permissions'].get(principal.principal_id, ()) or action not in principal.allowed_actions or
                principal.issuer_instance_id != self._authority._instance or
                principal.authority_generation != self._authority._generation or
                principal.authority_generation != s['generation'] or
                principal.account_ref != self._policy(s).account_ref):
            raise d.ApprovalDenied('authority_denied')
        if at >= principal.expires_at:
            raise d.ApprovalDenied('session_expired')
        if not protective:
            p = self._policy(s)
            if action not in p.allowed_actions or not p.valid_from <= at < p.valid_to:
                raise d.ApprovalDenied('policy_changed')
        return principal, session

    @staticmethod
    def _session_room(s, session, needed, *, reserve=3):
        # 일반 사건은 stop 한 자리와 disconnect의 event+session history를 보존한다.
        n, b = s['holds'].get(session.session_id, (0, 0))
        if n < needed + reserve or b < (needed + reserve) * 65536:
            raise d.ApprovalDenied('capacity_exceeded')

    @_safe
    def _issue(self, issuer, principal_id, *, reader):
        with self._lock:
            if issuer is not self._authority or principal_id not in issuer._principals:
                raise d.ApprovalDenied('authority_denied')
            fixture = issuer._principals[principal_id]
            if reader != (fixture.role in ('reporting', 'research')):
                raise d.ApprovalDenied('authority_denied')
            at, s = self._now(), self._copy()
            policy = self._policy(s)
            if fixture.account_ref != policy.account_ref or not policy.valid_from <= at < policy.valid_to:
                raise d.ApprovalDenied('authority_denied')
            pid = fixture.principal_id + ':' + uuid4().hex
            p = d.PrincipalEvidence(pid, 'qh-synthetic-fixture', issuer._instance, s['generation'],
                'synthetic', fixture.account_ref, fixture.role, fixture.allowed_actions, at,
                min(d.plus(at, 120), policy.valid_to), 'synthetic_fixture', d.FIXTURE_REF)
            # registry lookup uses registered fixture ID independent of unique evidence identity.
            p = replace(p, principal_id=fixture.principal_id)
            pr = self._put(s, 'principal', p, identity=pid)
            if reader:
                token = _ReadPermit()
                s['readers'][token] = pr
                self._commit(s)
                return token
            sid, token = 'session:' + uuid4().hex, _SessionHandle()
            event = self._event(s, 'explicit_synthetic_session_start', sid, at)
            session = d.SessionRecord(sid, pr, s['generation'], 'synthetic', fixture.account_ref,
                s['policy'], 'q26-v1', 'running', 1, at, min(d.plus(at, 120), p.expires_at), event,
                d.plus(at, 30), 'clock:' + str(issuer._epoch), None)
            self._put(s, 'session', session)
            s['handles'][token] = sid
            # Eight future records include heartbeat/disconnect and terminal invalidation.
            s['holds'][sid] = (8, 8 * 65536)
            s['last_at'] = at
            self._commit(s)
            return token

    def _source_check(self, s, r, at, *, require_live=True):
        try:
            return validate_source(self._source, r, at=at, generation=s['generation'], require_live=require_live)
        except d.ApprovalDenied:
            raise
        except Exception:
            raise d.ApprovalDenied('source_unresolved') from None

    @staticmethod
    def _presentation_text(text, account, generation, policy_ref, expiry):
        return (text + f' · 합성 승인 범위: {account} · synthetic · {generation}'
                f' · submit_candidate_once · {policy_ref.sha256} · 승인 종료 {expiry} 미만')

    @_safe
    def present(self, handle, candidate_ref):
        with self._lock:
            at, s = self._now(), self._copy()
            principal, session = self._auth(s, handle, 'present', at)
            if s['mode'] != 'running':
                raise d.ApprovalDenied('session_inactive')
            candidate, evidence, text, end = self._source_check(s, candidate_ref, at)
            if candidate.body.account_ref != principal.account_ref:
                raise d.ApprovalDenied('authority_denied')
            expiry = min(candidate.body.terms.valid_to, end, self._policy(s).valid_to,
                d.plus(at, 20), principal.expires_at, session.expires_at)
            er = self._put(s, 'evidence', evidence)
            aid, pid = 'approval:' + uuid4().hex, 'presentation:' + uuid4().hex
            rendered = self._presentation_text(text, principal.account_ref, s['generation'], s['policy'], expiry)
            pres = d.PresentationRecord(pid, candidate_ref, 'target-ko-v1', 'approval-ko-v1', 'ko-KR',
                session.principal_ref, d.ref('session', session.session_id, session), s['generation'],
                'submit_candidate_once', s['policy'], at, expiry, rendered, er, at)
            pres_ref = self._put(s, 'presentation', pres)
            approval = d.ApprovalRecord(aid, 'pending', 1, None, session.principal_ref, session.session_id,
                s['generation'], 'synthetic', principal.account_ref, candidate_ref, pres_ref, er,
                candidate.body.policy_ref, s['policy'], 'submit_candidate_once', candidate.body.terms,
                at, None, at, expiry, None, None, None)
            self._put(s, 'approval', approval)
            s['holds'][aid] = (40, 40 * 65536)
            s['last_at'] = at
            self._commit(s)
            return pres, approval

    def _target(self, s, r):
        obj = self._get(s, r)
        if type(obj) is not d.ApprovalRecord:
            raise d.ApprovalDenied()
        current = s['heads'].get(('approval', obj.approval_id))
        if current != r:
            raise d.ApprovalDenied('version_conflict')
        return obj

    def _owner(self, a, principal, session, action):
        if a.account_ref != principal.account_ref:
            raise d.ApprovalDenied('authority_denied')
        if action not in ('withdraw',) and (a.principal_ref != session.principal_ref or a.session_id != session.session_id):
            # Dispatch is a separate controller operation on the aggregate, not user approval.
            if action != 'dispatch' or principal.role != 'controller':
                raise d.ApprovalDenied('authority_denied')

    @_safe
    def challenge(self, handle, approval_ref, *, action, command_id):
        return self._challenge(handle, approval_ref, action=action, command_id=command_id)

    def _challenge(self, handle, approval_ref, *, action, command_id, closing=False):
        if action not in ('approve', 'deny', 'revoke', 'withdraw', 'admit', 'dispatch'):
            raise d.ApprovalDenied()
        identifier(command_id)
        with self._lock:
            at, s = self._now(), self._copy()
            p, session = self._auth(s, handle, action, at, protective=action in ('withdraw', 'revoke'))
            a = self._get(s, approval_ref)
            if type(a) is not d.ApprovalRecord:
                raise d.ApprovalDenied()
            self._owner(a, p, session, action)
            cr, rr = self._command_refs(s, command_id)
            if cr is not None:
                c = self._get(s, cr)
                if c.authority_generation != s['generation']:
                    raise d.ApprovalDenied('generation_mismatch')
                if (c.action, c.target_ref, c.session_id) != (action, approval_ref, session.session_id):
                    raise d.ApprovalDenied('replay_conflict')
                if closing and rr is None:
                    # Independently issued commands must complete through execute.
                    raise d.ApprovalDenied('replay_conflict')
                if action not in ('withdraw', 'revoke'):
                    self._source_check(s, a.candidate_ref, at, require_live=False)
                return c
            a = self._target(s, approval_ref)
            if a.state not in _ACTION_STATES[action]:
                raise d.ApprovalDenied('terminal_state')
            # Every issued command owns its worst-case completion budget, even after
            # another command terminates the approval. Only atomic closure may use
            # the last eight records; an expired two-step closure cannot drain them.
            pending_n, pending_b = self._pending_budget(s, a.approval_id)
            required = 3 + _COMPLETION[action] + (0 if closing else 8)
            n, b = s['holds'][a.approval_id]
            s['holds'][a.approval_id] = (max(n, pending_n + required),
                max(b, pending_b + required * 65536))
            c = d.ActionChallenge('challenge:' + uuid4().hex, command_id, 'nonce:' + uuid4().hex, action,
                session.principal_ref, session.session_id, s['generation'], 'synthetic', p.account_ref,
                approval_ref, a.presentation_ref, a.state_version, at, min(d.plus(at, 10), session.expires_at))
            cr = self._put(s, 'challenge', c)
            s['commands'][command_id] = cr
            s['nonces'][c.nonce] = cr
            s['last_at'] = at
            self._commit(s, owner=a.approval_id)
            return c

    @_safe
    def withdraw(self, handle, approval_ref, *, command_id):
        """합성 보호 철회: challenge 발급과 실행을 같은 잠금에서 완료한다."""
        with self._lock:
            before = self._state
            try:
                c = self._challenge(handle, approval_ref, action='withdraw',
                    command_id=command_id, closing=True)
                receipt = self.execute(handle, c)
                if receipt.outcome != 'applied':
                    raise d.ApprovalDenied(receipt.reason_code)
                return receipt
            except Exception:
                # Internal swaps are invisible outside this lock. Failed issuance,
                # completion or injected commit leaves no command, charge or nonce.
                fault = self._state['clock_fault']
                self._state = before | {'clock_fault': True, 'mode': 'faulted'} if fault else before
                raise

    def _change(self, s, a, state, at, event, *, intent=None, reason=None):
        b = replace(a, state=state, state_version=a.state_version + 1,
            previous_ref=d.ref('approval', a.approval_id, a), issued_at=a.issued_at or at,
            decision_evidence_ref=a.decision_evidence_ref or event, consumed_intent_id=intent, reason_code=reason)
        return self._put(s, 'approval', b)

    def _revalidate(self, s, a, at):
        if a.authority_generation != s['generation']:
            raise d.ApprovalDenied('generation_mismatch')
        if a.approval_policy_ref != s['policy']:
            raise d.ApprovalDenied('policy_changed')
        if not a.valid_from <= at < a.expires_at:
            raise d.ApprovalDenied('expired')
        candidate, evidence, text, end = self._source_check(s, a.candidate_ref, at)
        pres = self._get(s, a.presentation_ref)
        original = self._get(s, a.candidate_evidence_ref)
        # checked_at is per-call; underlying immutable source identity must stay exact.
        if (candidate.body.terms != a.terms or pres.expires_at != a.expires_at or end < a.expires_at or
                replace(evidence, checked_at=original.checked_at) != original or
                pres.rendered_text != self._presentation_text(text, a.account_ref, a.authority_generation,
                                                              a.approval_policy_ref, a.expires_at) or
                pres.principal_ref != a.principal_ref or pres.candidate_ref != a.candidate_ref or
                pres.approval_policy_ref != a.approval_policy_ref):
            raise d.ApprovalDenied('presentation_mismatch')

    @_safe
    def execute(self, handle, challenge):
        if type(challenge) is not d.ActionChallenge:
            raise d.ApprovalDenied()
        challenge = d.checked(challenge)
        with self._lock:
            at, s = self._now(), self._copy()
            c = challenge
            p, session = self._auth(s, handle, c.action, at,
                protective=c.action in ('withdraw', 'revoke'))
            cr, prior_receipt = self._command_refs(s, c.command_id)
            if cr is None or not self._command_nonce(s, c, cr, prior_receipt):
                raise d.ApprovalDenied('nonce_unknown')
            if self._get(s, cr) != c:
                raise d.ApprovalDenied('replay_conflict')
            if (c.session_id, c.principal_ref, c.authority_generation) != (
                    session.session_id, session.principal_ref, s['generation']):
                raise d.ApprovalDenied('authority_denied')
            old = self._get(s, c.target_ref)
            self._owner(old, p, session, c.action)
            if prior_receipt is not None:
                # Replays cannot reveal stale financial context after current rights are lost.
                if c.action not in ('withdraw', 'revoke'):
                    self._source_check(s, old.candidate_ref, at, require_live=False)
                return self._get(s, prior_receipt)
            head = s['heads'][('approval', old.approval_id)]
            a = self._get(s, head)
            reason, result = None, head
            try:
                if at >= c.expires_at:
                    raise d.ApprovalDenied('expired')
                if head != c.target_ref or a.state_version != c.expected_state_version:
                    raise d.ApprovalDenied('version_conflict')
                if c.action in ('approve', 'admit'):
                    self._revalidate(s, a, at)
                    if s['mode'] != 'running':
                        raise d.ApprovalDenied('session_inactive')
                if c.action == 'deny' and at >= a.expires_at:
                    raise d.ApprovalDenied('expired')
                event = self._event(s, 'explicit_synthetic_' + c.action, a.approval_id, at)
                if c.action in ('approve', 'deny'):
                    if a.state != 'pending':
                        raise d.ApprovalDenied('terminal_state')
                    result = self._change(s, a, 'approved' if c.action == 'approve' else 'denied', at, event)
                elif c.action == 'revoke':
                    if a.state != 'approved':
                        raise d.ApprovalDenied('terminal_state')
                    result = self._change(s, a, 'revoked', at, event)
                elif c.action == 'admit':
                    result = self._admit(s, a, at, event)
                elif c.action == 'withdraw':
                    result = self._withdraw(s, a, p, session, at, event)
                elif c.action == 'dispatch':
                    self._dispatch(s, a, at, event)
                    result = event
            except d.ApprovalDenied as failure:
                reason = failure.reason
                # Roll back every staged effect before recording the authenticated rejection.
                s = self._copy()
                if reason == 'commit_failed':
                    raise
                if a.state in ('pending', 'approved') and head == c.target_ref and reason in (
                        'expired', 'rights_denied', 'policy_changed', 'candidate_mismatch',
                        'presentation_mismatch', 'generation_mismatch', 'source_unresolved') and (
                        reason != 'expired' or at >= a.expires_at):
                    event = self._event(s, 'synthetic_invalidation', a.approval_id, at)
                    result = self._change(s, a, 'expired' if reason == 'expired' else 'invalidated', at, event, reason=reason)
            self._stage('history')
            receipt = d.ActionReceipt(c.command_id, cr, sha256(d.encoded(c)).hexdigest(), c.action,
                c.target_ref, c.principal_ref, at, 'rejected' if reason else 'applied', reason, result, s['version'] + 1)
            rr = self._put(s, 'receipt', receipt)
            s['receipts'][c.command_id] = rr
            self._stage('receipt')
            s['last_at'] = at
            terminal = self._get(s, s['heads'][('approval', a.approval_id)]).state
            self._commit(s, owner=a.approval_id, release=terminal in ('denied', 'revoked', 'expired', 'invalidated'))
            return receipt

    def _admit(self, s, a, at, event):
        intent_id = 'synthetic-intent:' + a.candidate_ref.sha256
        plan = d.plan_admission_transition(a, intent_id=intent_id, aggregate_version=s['version'])
        # Stored facts only: no caller risk/prepared/unsent booleans.
        risk = self._get(s, s['risk_ref']) if s['risk_ref'] else None
        if risk is None or risk.kind != 'synthetic_risk_clear':
            raise d.ApprovalDenied('risk_blocked')
        key = (a.environment, a.account_ref, a.authority_generation, a.candidate_ref.id, a.candidate_ref.sha256)
        if key in s['claims']:
            raise d.ApprovalDenied('candidate_already_consumed')
        result = self._change(s, a, 'consumed', at, event, intent=plan.intent_id)
        self._stage('consumed')
        s['claims'][key] = plan.intent_id
        self._stage('claim')
        s['intents'][plan.intent_id] = {'state': 'prepared', 'approval_ref': result,
            'runtime_ref': event, 'generation': s['generation'], 'unsent_evidence_ref': event}
        self._stage('intent')
        for kind, amount in (('cash', a.terms.maximum_burden), ('quantity', a.terms.quantity), ('risk', a.terms.maximum_burden)):
            s['reservations'][(plan.intent_id, kind)] = {'amount': amount, 'runtime_ref': event, 'state': 'held'}
        self._stage('reservation')
        s['outbox'][plan.intent_id] = {'state': 'pending', 'runtime_ref': event}
        self._stage('outbox')
        return result

    def _withdraw(self, s, a, p, session, at, event):
        if a.state == 'approved':
            return self._change(s, a, 'revoked', at, event)
        if a.state != 'consumed':
            raise d.ApprovalDenied('terminal_state')
        intent = s['intents'].get(a.consumed_intent_id)
        if intent is None:
            raise d.ApprovalDenied('source_unresolved')
        state = 'requested'
        if intent['state'] == 'prepared':
            proof = self._get(s, intent['unsent_evidence_ref'])
            if (proof.provenance, proof.aggregate_id, proof.target_id, proof.kind) != (
                    'synthetic_aggregate', self._aggregate_id, a.approval_id, 'explicit_synthetic_admit'):
                raise d.ApprovalDenied('source_unresolved')
            state = 'unsent_confirmed'
            s['intents'][a.consumed_intent_id] = intent | {'state': 'aborted_unsent', 'runtime_ref': event}
            s['outbox'][a.consumed_intent_id] = {'state': 'aborted_unsent', 'runtime_ref': event}
            for key, reservation in tuple(s['reservations'].items()):
                if key[0] == a.consumed_intent_id:
                    s['reservations'][key] = reservation | {'state': 'released', 'runtime_ref': event}
        wr = d.WithdrawalRequest('withdrawal:' + uuid4().hex, session.principal_ref, session.session_id,
            s['generation'], d.ref('approval', a.approval_id, a), a.consumed_intent_id, at,
            state, 1, None, event, None)
        return self._put(s, 'withdrawal', wr)

    def _dispatch(self, s, a, at, event):
        if s['mode'] != 'running' or s['restored']:
            raise d.ApprovalDenied('session_inactive')
        self._revalidate(s, a, at)
        if a.state != 'consumed':
            raise d.ApprovalDenied('terminal_state')
        # Resolve the original issuer-bound capability, not the controller as an
        # approver. _auth rechecks registry, current permission, policy and liveness.
        handle = next((h for h, sid in s['handles'].items() if sid == a.session_id), None)
        _, original = self._auth(s, handle, 'approve', at)
        if (original.principal_ref, original.session_id, original.account_ref,
                original.environment, original.authority_generation) != (
                a.principal_ref, a.session_id, a.account_ref, a.environment, a.authority_generation):
            raise d.ApprovalDenied('authority_denied')
        risk = self._get(s, s['risk_ref']) if s['risk_ref'] else None
        if risk is None or risk.kind != 'synthetic_risk_clear':
            raise d.ApprovalDenied('risk_blocked')
        intent = s['intents'].get(a.consumed_intent_id)
        if intent is None or intent['state'] != 'prepared':
            raise d.ApprovalDenied('terminal_state')
        s['intents'][a.consumed_intent_id] = intent | {'state': 'dispatching', 'runtime_ref': event}
        s['outbox'][a.consumed_intent_id] = {'state': 'dispatching', 'runtime_ref': event}

    @_safe
    def control(self, handle, action):
        if action not in ('resume', 'stop', 'heartbeat', 'disconnect'):
            raise d.ApprovalDenied()
        with self._lock:
            at, s = self._now(), self._copy()
            p, session = self._auth(s, handle, action, at, protective=action in ('stop', 'disconnect'))
            authorize(synthetic_binding('controller'), 'synthetic.session')
            if action == 'resume':
                self._session_room(s, session, 1)
                if s['restored'] or any(v['state'] in ('prepared', 'dispatching', 'unknown') for v in s['intents'].values()):
                    raise d.ApprovalDenied('reconciliation_required')
                s['mode'] = 'running'
            elif action == 'stop':
                if s['mode'] == 'stopped':
                    # Account-wide stop is idempotent, after current authorization.
                    # Reuse durable evidence without an additional uncharged index.
                    for r in reversed(s['records']):
                        if r.kind == 'runtime':
                            prior = self._get(s, r)
                            if (prior.kind == 'explicit_synthetic_stop' and
                                    prior.authority_generation == s['generation']):
                                return r
                self._session_room(s, session, 1, reserve=2)
                s['mode'] = 'stopped'
            event = self._event(s, 'explicit_synthetic_' + action, session.session_id, at)
            if action in ('heartbeat', 'disconnect'):
                self._session_room(s, session, 2, reserve=0 if action == 'disconnect' else 3)
                updated = replace(session, state='paused' if action == 'disconnect' else 'running',
                    state_version=session.state_version + 1, previous_ref=d.ref('session', session.session_id, session),
                    last_control_event_ref=event,
                    liveness_deadline=session.liveness_deadline if action == 'disconnect' else min(session.expires_at, d.plus(at, 30)))
                self._put(s, 'session', updated)
            s['last_at'] = at
            self._commit(s, owner=session.session_id, release=action == 'disconnect')
            return event

    @_safe
    def record_risk(self, handle, state):
        if state not in ('clear', 'blocked'):
            raise d.ApprovalDenied()
        with self._lock:
            at, s = self._now(), self._copy()
            _, session = self._auth(s, handle, 'runtime', at)
            self._session_room(s, session, 1)
            event = self._event(s, 'synthetic_risk_' + state, self._aggregate_id, at)
            s['risk_ref'], s['last_at'] = event, at
            self._commit(s, owner=session.session_id)
            return event

    @_safe
    def change_permissions(self, handle, principal_id, allowed_actions):
        """명시 합성 controller 사건. 현재 권한은 모든 재전달에도 새로 해소한다."""
        with self._lock:
            at, s = self._now(), self._copy()
            _, session = self._auth(s, handle, 'runtime', at, protective=True)
            self._session_room(s, session, 1)
            fixture = self._authority._principals.get(principal_id)
            if fixture is None or type(allowed_actions) is not tuple or not set(allowed_actions) <= set(fixture.allowed_actions):
                raise d.ApprovalDenied('authority_denied')
            s['permissions'][principal_id] = allowed_actions
            event = self._event(s, 'synthetic_permissions_update', principal_id, at)
            self._commit(s, owner=session.session_id)
            return event

    @_safe
    def record_unknown(self, handle, intent_id):
        with self._lock:
            at, s = self._now(), self._copy()
            _, session = self._auth(s, handle, 'runtime', at, protective=True)
            self._session_room(s, session, 1)
            intent = s['intents'].get(intent_id)
            if intent is None or intent['state'] != 'dispatching':
                raise d.ApprovalDenied('terminal_state')
            event = self._event(s, 'synthetic_egress_unknown', intent_id, at)
            s['intents'][intent_id] = intent | {'state': 'unknown', 'runtime_ref': event}
            s['outbox'][intent_id] = {'state': 'unknown', 'runtime_ref': event}
            s['last_at'] = at
            self._commit(s, owner=session.session_id)
            return event

    @_safe
    def replace_source(self, handle, source):
        if type(source) is not ApprovalSource:
            raise d.ApprovalDenied()
        with self._lock:
            at, s = self._now(), self._copy()
            _, session = self._auth(s, handle, 'runtime', at, protective=True)
            self._session_room(s, session, 1)
            if source.request.account_ref != self._policy(s).account_ref:
                raise d.ApprovalDenied('authority_denied')
            s['source_bytes'] = len(source_bytes(source))
            self._event(s, 'synthetic_source_update', source.request.request_id, at)
            self._commit(s, owner=session.session_id)
            self._source = source

    @_safe
    def replace_policy(self, handle, policy):
        policy = d.checked(policy)
        with self._lock:
            at, s = self._now(), self._copy()
            _, session = self._auth(s, handle, 'policy', at, protective=True)
            self._session_room(s, session, 2)
            old = self._policy(s)
            if type(policy) is not d.SyntheticApprovalPolicy or policy.account_ref != old.account_ref or policy.version != old.version + 1:
                raise d.ApprovalDenied('policy_changed')
            s['policy'] = self._put(s, 'policy', policy)
            self._event(s, 'synthetic_policy_update', policy.policy_id, at)
            self._commit(s, owner=session.session_id)

    @_safe
    def snapshot(self):
        """Trusted composition용 snapshot. query API가 아니며 capability는 제외한다."""
        with self._lock:
            return deepcopy({k: v for k, v in self._state.items() if k not in ('handles', 'readers')})

    @_safe
    def restore(self, snapshot):
        """이미 발급된 합성 snapshot만 수락한다. 실제 backup 보안 경계가 아니다."""
        with self._lock:
            # Exact current snapshot prevents arbitrary canonical/repository resealing.
            if snapshot != self.snapshot():
                raise d.ApprovalDenied('invalid_contract')
            at, s = self._now(), self._copy()
            next_epoch = self._authority._epoch + 1
            generation = 'restored-generation:' + self._authority._instance + ':' + str(next_epoch)
            s['generation'], s['mode'], s['restored'] = generation, 'stopped', True
            s['handles'], s['readers'] = {}, {}
            for (kind, identity), r in tuple(s['heads'].items()):
                obj = self._get(s, r)
                if kind == 'approval' and obj.state in ('pending', 'approved'):
                    event = self._event(s, 'restore_invalidation', identity, at)
                    self._change(s, obj, 'invalidated', at, event, reason='generation_mismatch')
                    s['holds'].pop(identity, None)
                if kind == 'session' and obj.state == 'running':
                    event = self._event(s, 'restore_session_invalidation', identity, at)
                    self._put(s, 'session', replace(obj, state='invalidated', state_version=obj.state_version + 1,
                        previous_ref=r, last_control_event_ref=event))
                if kind == 'session':
                    # Every old-generation session is unusable, including paused
                    # or expired heads. Keep all history and financial holds.
                    s['holds'].pop(identity, None)
            s['last_at'] = at
            self._commit(s)
            self._authority._epoch, self._authority._generation = next_epoch, generation
            return generation

    @_safe
    def query(self, permit, *, account_ref, purpose, limit=10, cursor=0):
        integer(limit, 1, 20)
        integer(cursor, 0, 128)
        if purpose not in ('status', 'financial', 'research_summary'):
            raise d.ApprovalDenied()
        with self._lock:
            at, s = self._now(), self._state
            p, _ = self._auth(s, permit, 'query', at, reader=True, protective=True)
            if account_ref != p.account_ref:
                raise d.ApprovalDenied('authority_denied')
            if p.role == 'research' and purpose != 'research_summary':
                raise d.ApprovalDenied('authority_denied')
            rows = []
            for (kind, _), r in s['heads'].items():
                if kind != 'approval':
                    continue
                a = self._get(s, r)
                row = {'approval_id': a.approval_id, 'state': a.state, 'state_version': a.state_version,
                       'environment': 'synthetic', 'notice': '합성 상태이며 실제 인증·주문이 아닙니다.'}
                if purpose == 'financial':
                    candidate, _, text, _ = self._source_check(s, a.candidate_ref, at, require_live=False)
                    row['candidate_text'] = text
                    row['maximum_burden'] = candidate.body.terms.maximum_burden
                rows.append(row)
            return {'rows': tuple(rows[cursor:cursor + limit]),
                    'next_cursor': cursor + limit if cursor + limit < len(rows) else None}
