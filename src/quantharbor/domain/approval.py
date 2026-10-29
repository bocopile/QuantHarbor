"""Q26 닫힌 합성 증거. canonical 증거와 순수 전이 계획은 권한이 아니다."""
from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from types import MappingProxyType

from .ledger import digest, integer
from .primitives import ContractError, identifier, utc_instant
from .target import (TargetRef, OrderTerms, _checked, _nested, enum, optional,
                     sequence, positive_count, version)

CANONICAL = 'qh-canonical-json-v1'
FIXTURE_SHA = '84190ff349d81877bbfdace4ffd23d9e0c1de5d474c3a3c6568c870504c71300'
REASONS = ('invalid_contract', 'unsupported_environment', 'authority_denied', 'session_inactive',
    'session_expired', 'generation_mismatch', 'clock_invalid', 'nonce_unknown', 'replay_conflict',
    'version_conflict', 'candidate_mismatch', 'presentation_mismatch', 'source_unresolved',
    'rights_denied', 'policy_changed', 'expired', 'terminal_state', 'candidate_already_consumed',
    'capacity_exceeded', 'commit_failed', 'reconciliation_required', 'risk_blocked')
ACTIONS = ('approve', 'deny', 'revoke', 'withdraw', 'present', 'admit', 'dispatch', 'query',
           'stop', 'resume', 'heartbeat', 'disconnect', 'session', 'runtime', 'policy')
TRANSITIONS = {'pending': ('approved', 'denied', 'expired', 'invalidated'),
    'approved': ('revoked', 'expired', 'invalidated', 'consumed')}


class ApprovalDenied(ValueError):
    def __init__(self, reason='invalid_contract'):
        if type(reason) is not str or reason not in REASONS:
            reason = 'invalid_contract'
        self.reason = reason
        super().__init__(reason)


def text(value):
    if type(value) is not str or any(0xD800 <= ord(c) <= 0xDFFF for c in value) or not 1 <= len(value.encode('utf-8')) <= 2048:
        raise ContractError()
    return value


def rendered(value):
    if type(value) is not str or any(0xD800 <= ord(c) <= 0xDFFF for c in value) or not 1 <= len(value.encode('utf-8')) <= 16384:
        raise ContractError()
    return value


def plus(at, seconds):
    return utc_instant(datetime.fromisoformat(utc_instant(at)) + timedelta(seconds=seconds))


def hashed(value):
    digest(value)
    return value


class Checked:
    __slots__ = ()

    def __post_init__(self):
        for f in fields(self):
            object.__setattr__(self, f.name, _checked(SPECS[type(self)][f.name], getattr(self, f.name)))
        validate(self)


@dataclass(frozen=True, slots=True)
class ApprovalRef(Checked):
    kind: str
    id: str
    version: int
    canonicalization_version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ApprovalLimits(Checked):
    canonical_bytes: int = 65536
    resolved_bytes: int = 8388608
    refs: int = 128
    string_utf8_bytes: int = 2048
    rendered_utf8_bytes: int = 16384
    total_records: int = 128
    total_bytes: int = 8388608


@dataclass(frozen=True, slots=True)
class SyntheticApprovalPolicy(Checked):
    policy_id: str
    version: int
    environment: str
    account_ref: str
    valid_from: str
    valid_to: str
    approval_ttl_seconds: int
    challenge_ttl_seconds: int
    session_ttl_seconds: int
    liveness_timeout_seconds: int
    allowed_actions: tuple[str, ...]
    limits: ApprovalLimits
    fixture_manifest_ref: ApprovalRef


@dataclass(frozen=True, slots=True)
class PrincipalEvidence(Checked):
    principal_id: str
    issuer_id: str
    issuer_instance_id: str
    authority_generation: str
    environment: str
    account_ref: str
    role: str
    allowed_actions: tuple[str, ...]
    issued_at: str
    expires_at: str
    provenance: str
    fixture_manifest_ref: ApprovalRef


@dataclass(frozen=True, slots=True)
class SessionRecord(Checked):
    session_id: str
    principal_ref: ApprovalRef
    authority_generation: str
    environment: str
    account_ref: str
    policy_ref: ApprovalRef
    code_version: str
    state: str
    state_version: int
    started_at: str
    expires_at: str
    last_control_event_ref: ApprovalRef
    liveness_deadline: str
    clock_epoch: str
    previous_ref: ApprovalRef | None


@dataclass(frozen=True, slots=True)
class CandidateEvidence(Checked):
    candidate_ref: TargetRef
    plan_ref: TargetRef
    result_ref: TargetRef
    request_ref: TargetRef
    input_refs: tuple[TargetRef, ...]
    current_rights_refs: tuple[TargetRef, ...]
    source_revision_refs: tuple[TargetRef, ...]
    checked_at: str
    checker_version: str
    fixture_manifest_ref: ApprovalRef


@dataclass(frozen=True, slots=True)
class PresentationRecord(Checked):
    presentation_id: str
    candidate_ref: TargetRef
    candidate_render_version: str
    approval_render_version: str
    locale: str
    principal_ref: ApprovalRef
    session_ref: ApprovalRef
    authority_generation: str
    action: str
    approval_policy_ref: ApprovalRef
    valid_from: str
    expires_at: str
    rendered_text: str
    candidate_evidence_ref: ApprovalRef
    rendered_at: str


@dataclass(frozen=True, slots=True)
class ActionChallenge(Checked):
    challenge_id: str
    command_id: str
    nonce: str
    action: str
    principal_ref: ApprovalRef
    session_id: str
    authority_generation: str
    environment: str
    account_ref: str
    target_ref: ApprovalRef
    presentation_ref: ApprovalRef
    expected_state_version: int
    issued_at: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class ApprovalRecord(Checked):
    approval_id: str
    state: str
    state_version: int
    previous_ref: ApprovalRef | None
    principal_ref: ApprovalRef
    session_id: str
    authority_generation: str
    environment: str
    account_ref: str
    candidate_ref: TargetRef
    presentation_ref: ApprovalRef
    candidate_evidence_ref: ApprovalRef
    target_policy_ref: TargetRef
    approval_policy_ref: ApprovalRef
    authorized_action: str
    terms: OrderTerms
    created_at: str
    issued_at: str | None
    valid_from: str
    expires_at: str
    decision_evidence_ref: ApprovalRef | None
    consumed_intent_id: str | None
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class ActionReceipt(Checked):
    command_id: str
    challenge_ref: ApprovalRef
    command_payload_hash: str
    action: str
    target_ref: ApprovalRef
    actor_evidence_ref: ApprovalRef
    recorded_at: str
    outcome: str
    reason_code: str | None
    result_ref: ApprovalRef
    aggregate_version: int


@dataclass(frozen=True, slots=True)
class SyntheticRuntimeEvidence(Checked):
    event_id: str
    aggregate_id: str
    aggregate_version: int
    authority_generation: str
    environment: str
    account_ref: str
    kind: str
    target_id: str
    recorded_at: str
    provenance: str
    fixture_manifest_ref: ApprovalRef


@dataclass(frozen=True, slots=True)
class WithdrawalRequest(Checked):
    request_id: str
    principal_ref: ApprovalRef
    session_id: str
    authority_generation: str
    approval_ref: ApprovalRef
    intent_id: str
    requested_at: str
    state: str
    state_version: int
    previous_ref: ApprovalRef | None
    runtime_evidence_ref: ApprovalRef
    reason_code: str | None


@dataclass(frozen=True, slots=True)
class TransitionPlan:
    """실행 권한 없이 immutable snapshot에서 계산한 계획."""
    approval_ref: ApprovalRef
    intent_id: str
    expected_aggregate_version: int


def plan_admission_transition(approval, *, intent_id, aggregate_version):
    if type(approval) is not ApprovalRecord:
        raise ApprovalDenied()
    approval = checked(approval)
    identifier(intent_id)
    integer(aggregate_version, 0)
    if approval.state != 'approved':
        raise ApprovalDenied('terminal_state')
    return TransitionPlan(ref('approval', approval.approval_id, approval), intent_id, aggregate_version)


def validate(x):
    kinds = {'principal_ref': 'principal', 'session_ref': 'session', 'policy_ref': 'policy',
        'approval_policy_ref': 'policy', 'target_policy_ref': 'policy', 'candidate_ref': 'candidate',
        'plan_ref': 'plan', 'result_ref': 'result', 'request_ref': 'request',
        'presentation_ref': 'presentation', 'candidate_evidence_ref': 'evidence',
        'challenge_ref': 'challenge', 'actor_evidence_ref': 'principal',
        'approval_ref': 'approval', 'runtime_evidence_ref': 'runtime',
        'decision_evidence_ref': 'runtime', 'last_control_event_ref': 'runtime', 'fixture_manifest_ref': 'fixture'}
    for field, kind in kinds.items():
        r = getattr(x, field, None)
        if type(x) is ActionReceipt and field == 'result_ref':
            if r.kind not in ('approval', 'withdrawal', 'runtime'):
                raise ContractError()
            continue
        if r is not None and r.kind != kind:
            raise ContractError()
    for start, end in (('valid_from', 'valid_to'), ('issued_at', 'expires_at'),
                       ('valid_from', 'expires_at'), ('started_at', 'expires_at')):
        if hasattr(x, start) and hasattr(x, end):
            a, b = getattr(x, start), getattr(x, end)
            if (a is not None and b is not None and a >= b and
                    not (type(x) is ApprovalRecord and start == 'issued_at' and
                         x.state in ('expired', 'invalidated'))):
                raise ContractError()
    if isinstance(x, (ApprovalRecord, SessionRecord, WithdrawalRequest)):
        if (x.state_version == 1) != (x.previous_ref is None):
            raise ContractError()
        if x.previous_ref and x.previous_ref.version != x.state_version - 1:
            raise ContractError()
    if type(x) is ApprovalRecord:
        if (x.state_version == 1) != (x.state == 'pending'):
            raise ContractError()
        if x.previous_ref and (x.previous_ref.kind, x.previous_ref.id) != ('approval', x.approval_id):
            raise ContractError()
        if (x.state == 'pending') != (x.issued_at is None and x.decision_evidence_ref is None):
            raise ContractError()
        if (x.issued_at is None) != (x.decision_evidence_ref is None):
            raise ContractError()
        if (x.state == 'consumed') != (x.consumed_intent_id is not None):
            raise ContractError()
        if (x.terms.account_ref != x.account_ref or x.valid_from < x.terms.valid_from or
                x.expires_at > x.terms.valid_to or x.created_at > x.valid_from):
            raise ContractError()
    if type(x) is ApprovalLimits and tuple(getattr(x, f.name) for f in fields(x)) != object_limits():
        raise ContractError()
    if type(x) is SyntheticApprovalPolicy:
        if (x.approval_ttl_seconds, x.challenge_ttl_seconds, x.session_ttl_seconds,
                x.liveness_timeout_seconds) != (20, 10, 120, 30):
            raise ContractError()
    if type(x) is SessionRecord and x.previous_ref and (x.previous_ref.kind, x.previous_ref.id) != ('session', x.session_id):
        raise ContractError()
    if type(x) is WithdrawalRequest and x.previous_ref and (x.previous_ref.kind, x.previous_ref.id) != ('withdrawal', x.request_id):
        raise ContractError()
    if type(x) is ApprovalRef and x.kind == 'fixture' and (x.id, x.version, x.sha256) != (
            'qh-approval-synthetic-v1', 1, FIXTURE_SHA):
        raise ContractError()


def object_limits():
    return (65536, 8388608, 128, 2048, 16384, 128, 8388608)


# constructor와 parser가 공유하는 닫힌 구조 표. 등록 API는 공개하지 않는다.
SPECS = {}
def spec(cls, **rules):
    if {f.name for f in fields(cls)} != rules.keys():
        raise RuntimeError('Approval schema mismatch')
    SPECS[cls] = rules


S, O = sequence, optional
ID = identifier
E = enum('synthetic')
T = utc_instant
spec(ApprovalRef, kind=enum('fixture', 'policy', 'principal', 'session', 'evidence', 'presentation',
    'challenge', 'approval', 'receipt', 'withdrawal', 'runtime'), id=ID, version=positive_count,
    canonicalization_version=enum(CANONICAL), sha256=hashed)
spec(ApprovalLimits, **{name: positive_count for name in ApprovalLimits.__dataclass_fields__})
spec(SyntheticApprovalPolicy, policy_id=ID, version=positive_count, environment=E, account_ref=ID,
    valid_from=T, valid_to=T, approval_ttl_seconds=positive_count, challenge_ttl_seconds=positive_count,
    session_ttl_seconds=positive_count, liveness_timeout_seconds=positive_count,
    allowed_actions=S(enum(*ACTIONS)), limits=ApprovalLimits, fixture_manifest_ref=ApprovalRef)
spec(PrincipalEvidence, principal_id=ID, issuer_id=ID, issuer_instance_id=ID, authority_generation=ID,
    environment=E, account_ref=ID, role=enum('approver', 'controller', 'reporting', 'research'),
    allowed_actions=S(enum(*ACTIONS)), issued_at=T, expires_at=T,
    provenance=enum('synthetic_fixture'), fixture_manifest_ref=ApprovalRef)
spec(SessionRecord, session_id=ID, principal_ref=ApprovalRef, authority_generation=ID, environment=E,
    account_ref=ID, policy_ref=ApprovalRef, code_version=ID,
    state=enum('running', 'paused', 'faulted', 'invalidated'), state_version=positive_count,
    started_at=T, expires_at=T, last_control_event_ref=ApprovalRef, liveness_deadline=T,
    clock_epoch=ID, previous_ref=O(ApprovalRef))
spec(CandidateEvidence, candidate_ref=TargetRef, plan_ref=TargetRef, result_ref=TargetRef,
    request_ref=TargetRef, input_refs=S(TargetRef), current_rights_refs=S(TargetRef),
    source_revision_refs=S(TargetRef), checked_at=T, checker_version=ID, fixture_manifest_ref=ApprovalRef)
spec(PresentationRecord, presentation_id=ID, candidate_ref=TargetRef, candidate_render_version=enum('target-ko-v1'),
    approval_render_version=enum('approval-ko-v1'), locale=enum('ko-KR'), principal_ref=ApprovalRef,
    session_ref=ApprovalRef, authority_generation=ID, action=enum('submit_candidate_once'),
    approval_policy_ref=ApprovalRef, valid_from=T, expires_at=T, rendered_text=rendered,
    candidate_evidence_ref=ApprovalRef, rendered_at=T)
spec(ActionChallenge, challenge_id=ID, command_id=ID, nonce=ID, action=enum(*ACTIONS),
    principal_ref=ApprovalRef, session_id=ID, authority_generation=ID, environment=E, account_ref=ID,
    target_ref=ApprovalRef, presentation_ref=ApprovalRef, expected_state_version=positive_count,
    issued_at=T, expires_at=T)
spec(ApprovalRecord, approval_id=ID, state=enum('pending', 'approved', 'denied', 'revoked', 'expired',
    'invalidated', 'consumed'), state_version=positive_count, previous_ref=O(ApprovalRef),
    principal_ref=ApprovalRef, session_id=ID, authority_generation=ID, environment=E, account_ref=ID,
    candidate_ref=TargetRef, presentation_ref=ApprovalRef, candidate_evidence_ref=ApprovalRef,
    target_policy_ref=TargetRef, approval_policy_ref=ApprovalRef, authorized_action=enum('submit_candidate_once'),
    terms=OrderTerms, created_at=T, issued_at=O(T), valid_from=T, expires_at=T,
    decision_evidence_ref=O(ApprovalRef), consumed_intent_id=O(ID), reason_code=O(enum(*REASONS)))
spec(ActionReceipt, command_id=ID, challenge_ref=ApprovalRef, command_payload_hash=hashed,
    action=enum(*ACTIONS), target_ref=ApprovalRef, actor_evidence_ref=ApprovalRef, recorded_at=T,
    outcome=enum('applied', 'rejected'), reason_code=O(enum(*REASONS)), result_ref=ApprovalRef,
    aggregate_version=positive_count)
spec(SyntheticRuntimeEvidence, event_id=ID, aggregate_id=ID, aggregate_version=positive_count,
    authority_generation=ID, environment=E, account_ref=ID, kind=ID, target_id=ID, recorded_at=T,
    provenance=enum('synthetic_aggregate'), fixture_manifest_ref=ApprovalRef)
spec(WithdrawalRequest, request_id=ID, principal_ref=ApprovalRef, session_id=ID, authority_generation=ID,
    approval_ref=ApprovalRef, intent_id=ID, requested_at=T, state=enum('requested', 'unsent_confirmed'),
    state_version=positive_count, previous_ref=O(ApprovalRef), runtime_evidence_ref=ApprovalRef,
    reason_code=O(enum(*REASONS)))
NESTED = MappingProxyType({cls: {n: _nested(r) for n, r in rules.items() if _nested(r) is not None}
                           for cls, rules in SPECS.items()})
SPECS = MappingProxyType({cls: MappingProxyType(rules) for cls, rules in SPECS.items()})


def encoded(obj):
    from .serialization import CanonicalPayload, canonical_bytes
    return canonical_bytes(CanonicalPayload(type(obj).__name__, 1, 'synthetic', obj))


def checked(obj):
    from .serialization import parse_payload
    return parse_payload(encoded(obj)).payload


def ref(kind, identity, obj):
    from .serialization import CanonicalPayload, canonical_hash
    return ApprovalRef(kind, identity, getattr(obj, 'state_version', getattr(obj, 'version', 1)),
        CANONICAL, canonical_hash(CanonicalPayload(type(obj).__name__, 1, 'synthetic', obj)))


FIXTURE_REF = ApprovalRef('fixture', 'qh-approval-synthetic-v1', 1, CANONICAL, FIXTURE_SHA)
