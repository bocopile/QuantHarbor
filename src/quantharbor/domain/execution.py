"""Q27 닫힌 합성 실행 증거. 직렬화된 값은 실행 권한이 아니다."""
from dataclasses import dataclass, fields
from types import MappingProxyType

from .approval import ApprovalRef, text, plus
from .ledger import account as check_account
from .primitives import ContractError, identifier, utc_instant
from .target import (OrderTerms, TargetRef, TargetScope, _checked, _nested, enum,
    optional, sequence, positive_count, count, nonnegative, positive, hashed, numeric)
from .valuation import PositionKey

CANONICAL = 'qh-canonical-json-v1'
FIXTURE_SHA = '41756164ab565c611458d0d3dfeed236aaefa5d98973a76e04b04766c7ff46a1'
STATES = ('prepared', 'dispatching', 'unknown', 'acknowledged', 'partially_filled',
    'filled', 'rejected', 'aborted_unsent', 'cancelled_remaining', 'expired_remaining')
TERMINAL = ('filled', 'rejected', 'aborted_unsent', 'cancelled_remaining', 'expired_remaining')
REASONS = ('invalid_contract', 'authority_denied', 'storage_failure', 'source_unresolved',
    'stale_source', 'risk_blocked', 'capacity_exceeded', 'version_conflict', 'event_conflict',
    'reconciliation_required', 'commit_failed', 'handoff_unknown', 'unsupported_correction')


class ExecutionDenied(ValueError):
    def __init__(self, reason='invalid_contract'):
        self.reason = reason if type(reason) is str and reason in REASONS else 'invalid_contract'
        super().__init__(self.reason)


class Checked:
    __slots__ = ()

    def __post_init__(self):
        for f in fields(self):
            object.__setattr__(self, f.name, _checked(SPECS[type(self)][f.name], getattr(self, f.name)))
        if (getattr(self,'valid_to',None) is not None and
            (getattr(self,'valid_from',getattr(self,'checked_at',self.valid_to)) is None or
             getattr(self,'valid_from',getattr(self,'checked_at',self.valid_to)) >= self.valid_to)):
            raise ContractError()
        if type(self) is ExecutionReconciliation:
            values=(self.current_identity,self.validator_version,self.valid_from,self.valid_to)
            if ((self.current_identity is None)!=(self.validator_version is None) or
                self.validator_version not in (None,'q27-account-current-v1') or
                self.result=='matched' and self.current_identity is not None and self.valid_to is None):
                raise ContractError()
            if (self.valid_from is None)!=(self.valid_to is None):
                raise ContractError()
            if self.valid_to is not None and (any(x is None for x in values) or self.validator_version!='q27-account-current-v1'):
                raise ContractError()
        if type(self) is ReservationSlice:
            from .valuation import number
            if number(self.held) + number(self.used) + number(self.released) != number(self.bound):
                raise ContractError()
        if type(self) is OrderIntent:
            from .valuation import number
            if number(self.confirmed_quantity) > number(self.terms.quantity):
                raise ContractError()


@dataclass(frozen=True, slots=True)
class ExecutionRef(Checked):
    kind: str
    id: str
    version: int
    canonicalization_version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class SyntheticExecutionPolicy(Checked):
    policy_id: str
    version: int
    environment: str
    account_ref: str
    target_policy_ref: TargetRef
    valid_from: str
    valid_to: str
    max_gross_turnover: str
    fixture_ref: ExecutionRef


@dataclass(frozen=True, slots=True)
class ExecutionAccountState(Checked):
    account_ref: str
    environment: str
    mode: str
    state_version: int
    generation: str
    issuer_instance: str
    fence: int
    owner: str
    lease_deadline: str
    policy_ref: ExecutionRef
    source_ref: ExecutionRef | None
    ledger_cursor: int
    clock_epoch: int
    reconciliation_ref: ExecutionRef | None


@dataclass(frozen=True, slots=True)
class ExecutionSourceSet(Checked):
    source_id: str
    account_ref: str
    environment: str
    candidate_ref: TargetRef
    plan_ref: TargetRef
    result_ref: TargetRef
    request_ref: TargetRef
    input_refs: tuple[TargetRef, ...]
    scope: TargetScope
    query_ref: ExecutionRef
    ledger_cursor: int
    execution_version: int
    generation: str
    fence: int
    checked_at: str
    valid_to: str


@dataclass(frozen=True, slots=True)
class ExecutionCash(Checked):
    currency: str
    ledger: str
    outstanding: str
    floor: str
    broker: str
    unreflected: str
    debits: str
    available: str


@dataclass(frozen=True, slots=True)
class ExecutionRiskDecision(Checked):
    risk_id: str
    account_ref: str
    candidate_ref: TargetRef
    approval_ref: ApprovalRef
    terms_hash: str
    source_ref: ExecutionRef
    policy_ref: ExecutionRef
    checked_at: str
    valid_to: str
    account_version: int
    ledger_cursor: int
    generation: str
    fence: int
    cash: tuple[ExecutionCash, ...]
    outcome: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OrderIntent(Checked):
    intent_id: str
    account_ref: str
    environment: str
    candidate_ref: TargetRef
    approval_ref: ApprovalRef
    terms: OrderTerms
    request_hash: str
    admission_risk_ref: ExecutionRef
    generation: str
    fence: int
    state: str
    state_version: int
    previous_ref: ExecutionRef | None
    confirmed_quantity: str
    observed_quantity: str
    attempt_ref: ExecutionRef | None
    broker_order_id: str | None
    accounting: str


@dataclass(frozen=True, slots=True)
class ReservationSlice(Checked):
    reservation_id: str
    intent_id: str
    obligation_id: str
    component: str
    dimension: str
    currency_or_unit: str
    window_start: str
    window_end: str
    bound: str
    held: str
    used: str
    released: str
    broker_reflected: str
    settled: str
    source_cutoff: str
    ledger_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DispatchAttempt(Checked):
    attempt_id: str
    intent_id: str
    action: str
    request_hash: str
    generation: str
    fence: int
    egress_instance: str
    state: str
    recorded_at: str
    receipt_ref: ExecutionRef | None


@dataclass(frozen=True, slots=True)
class SyntheticBrokerReceipt(Checked):
    receipt_id: str
    issuer_instance: str
    account_ref: str
    intent_id: str
    attempt_id: str
    request_hash: str
    broker_order_id: str | None
    sequence: int
    issued_at: str
    kind: str
    journal_id: str


@dataclass(frozen=True, slots=True)
class SyntheticOrderEvent(Checked):
    event_id: str
    issuer_instance: str
    account_ref: str
    intent_id: str
    request_hash: str
    broker_order_id: str
    revision: int
    predecessor_revision: int | None
    kind: str
    semantics: str
    execution_id: str
    stream_sequence: int
    quantity: str
    price: str
    fee: str | None
    tax: str | None
    effective_at: str
    issued_at: str
    receipt_ref: ExecutionRef
    journal_id: str


@dataclass(frozen=True, slots=True)
class SyntheticExecutionQuery(Checked):
    query_id: str
    issuer_instance: str
    account_ref: str
    environment: str
    requested_scope: TargetScope
    covered_scope: TargetScope
    missing_scope: tuple[str, ...]
    status: str
    as_of: str
    cutoff_sequence: int
    cash: tuple['BrokerCash', ...]
    sellable: tuple['BrokerQuantity', ...]
    receipts: tuple[ExecutionRef, ...]
    events: tuple[ExecutionRef, ...]
    statement_ref: TargetRef
    journal_id: str
    journal_sequence: int = 0
    request_attempts: tuple[DispatchAttempt, ...] = ()


@dataclass(frozen=True, slots=True)
class BrokerCash(Checked):
    currency: str
    amount: str
    included_components: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BrokerHoldReflection(Checked):
    obligation_id: str
    quantity: str


@dataclass(frozen=True, slots=True)
class BrokerQuantity(Checked):
    position: PositionKey
    quantity: str
    included_components: tuple[str, ...]
    hold_reflections: tuple[BrokerHoldReflection, ...] = ()


@dataclass(frozen=True, slots=True)
class CancelCommand(Checked):
    command_id: str
    nonce: str
    account_ref: str
    session_id: str
    generation: str
    intent_ref: ExecutionRef
    broker_order_id: str
    maximum_remaining: str
    expected_version: int
    issued_at: str
    expires_at: str
    state: str
    attempt_ref: ExecutionRef | None
    state_version: int = 1


@dataclass(frozen=True, slots=True)
class ExecutionReconciliation(Checked):
    reconciliation_id: str
    account_ref: str
    query_ref: ExecutionRef
    ledger_cursor: int
    account_version: int
    generation: str
    fence: int
    checked_at: str
    result: str
    unresolved: tuple[str, ...]
    session_id: str | None = None
    source_hash: str | None = None
    current_identity: str | None = None
    validator_version: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionCommandReceipt(Checked):
    command_id: str
    payload_hash: str
    session_id: str
    action: str
    target_id: str
    expected_version: int
    recorded_at: str
    account_version: int
    result_ref: ExecutionRef


SPECS = {}
def spec(cls, **rules):
    assert set(rules) == {f.name for f in fields(cls)}
    SPECS[cls] = rules

def account(value):
    check_account(value)
    return value


ID, T, N, O, S = identifier, utc_instant, nonnegative, optional, sequence
E = enum('synthetic')
spec(ExecutionRef, kind=enum('policy','source','risk','intent','reservation','attempt','event','query','cancel','reconciliation','runtime','receipt','fixture'), id=ID, version=positive_count, canonicalization_version=enum(CANONICAL), sha256=hashed)
spec(SyntheticExecutionPolicy, policy_id=ID, version=positive_count, environment=E, account_ref=account, target_policy_ref=TargetRef, valid_from=T, valid_to=T, max_gross_turnover=positive, fixture_ref=ExecutionRef)
spec(ExecutionAccountState, account_ref=account, environment=E, mode=enum('running','stopped','reconciling','faulted'), state_version=count, generation=ID, issuer_instance=ID, fence=positive_count, owner=ID, lease_deadline=T, policy_ref=ExecutionRef, source_ref=O(ExecutionRef), ledger_cursor=count, clock_epoch=count, reconciliation_ref=O(ExecutionRef))
spec(ExecutionSourceSet, source_id=ID, account_ref=account, environment=E, candidate_ref=TargetRef, plan_ref=TargetRef, result_ref=TargetRef, request_ref=TargetRef, input_refs=S(TargetRef), scope=TargetScope, query_ref=ExecutionRef, ledger_cursor=count, execution_version=count, generation=ID, fence=positive_count, checked_at=T, valid_to=T)
spec(ExecutionCash, currency=enum('USD','KRW'), ledger=N, outstanding=N, floor=N, broker=N, unreflected=N, debits=N, available=numeric)
spec(ExecutionRiskDecision, risk_id=ID, account_ref=account, candidate_ref=TargetRef, approval_ref=ApprovalRef, terms_hash=hashed, source_ref=ExecutionRef, policy_ref=ExecutionRef, checked_at=T, valid_to=T, account_version=count, ledger_cursor=count, generation=ID, fence=positive_count, cash=S(ExecutionCash), outcome=enum('allow','deny','unknown'), reasons=S(enum(*REASONS)))
spec(OrderIntent, intent_id=ID, account_ref=account, environment=E, candidate_ref=TargetRef, approval_ref=ApprovalRef, terms=OrderTerms, request_hash=hashed, admission_risk_ref=ExecutionRef, generation=ID, fence=positive_count, state=enum(*STATES), state_version=positive_count, previous_ref=O(ExecutionRef), confirmed_quantity=N, observed_quantity=N, attempt_ref=O(ExecutionRef), broker_order_id=O(ID), accounting=enum('complete','incomplete'))
spec(ReservationSlice, reservation_id=ID, intent_id=ID, obligation_id=ID, component=enum('principal','cost','quantity','risk'), dimension=enum('cash','quantity','risk'), currency_or_unit=ID, window_start=T, window_end=T, bound=N, held=N, used=N, released=N, broker_reflected=N, settled=N, source_cutoff=T, ledger_refs=S(ID))
spec(DispatchAttempt, attempt_id=ID, intent_id=ID, action=enum('submit','cancel'), request_hash=hashed, generation=ID, fence=positive_count, egress_instance=ID, state=enum('armed','handed_off','result_stored','unknown','proven_unsent'), recorded_at=T, receipt_ref=O(ExecutionRef))
spec(SyntheticBrokerReceipt, receipt_id=ID, issuer_instance=ID, account_ref=account, intent_id=ID, attempt_id=ID, request_hash=hashed, broker_order_id=O(ID), sequence=positive_count, issued_at=T, kind=enum('accepted','final_reject','proven_unsent','cancel_ack'), journal_id=ID)
spec(SyntheticOrderEvent, event_id=ID, issuer_instance=ID, account_ref=account, intent_id=ID, request_hash=hashed, broker_order_id=ID, revision=positive_count, predecessor_revision=O(positive_count), kind=enum('fill','cancelled_remaining','expired_remaining','settlement'), semantics=enum('delta','cumulative'), execution_id=ID, stream_sequence=positive_count, quantity=N, price=positive, fee=O(N), tax=O(N), effective_at=T, issued_at=T, receipt_ref=ExecutionRef, journal_id=ID)
spec(BrokerCash, currency=enum('USD','KRW'), amount=N, included_components=S(ID))
spec(BrokerHoldReflection, obligation_id=ID, quantity=positive)
spec(BrokerQuantity, position=PositionKey, quantity=N, included_components=S(ID), hold_reflections=S(BrokerHoldReflection))
spec(SyntheticExecutionQuery, query_id=ID, issuer_instance=ID, account_ref=account, environment=E, requested_scope=TargetScope, covered_scope=TargetScope, missing_scope=S(ID), status=enum('complete','partial','unknown'), as_of=T, cutoff_sequence=count, cash=S(BrokerCash), sellable=S(BrokerQuantity), receipts=S(ExecutionRef), events=S(ExecutionRef), statement_ref=TargetRef, journal_id=ID, journal_sequence=count, request_attempts=S(DispatchAttempt))
spec(CancelCommand, command_id=ID, nonce=ID, account_ref=account, session_id=ID, generation=ID, intent_ref=ExecutionRef, broker_order_id=ID, maximum_remaining=N, expected_version=positive_count, issued_at=T, expires_at=T, state=enum('issued','armed','acknowledged','unknown','confirmed'), attempt_ref=O(ExecutionRef), state_version=positive_count)
spec(ExecutionReconciliation, reconciliation_id=ID, account_ref=account, query_ref=ExecutionRef, ledger_cursor=count, account_version=count, generation=ID, fence=positive_count, checked_at=T, result=enum('matched','unresolved'), unresolved=S(ID), session_id=O(ID), source_hash=O(hashed), current_identity=O(hashed), validator_version=O(ID), valid_from=O(T), valid_to=O(T))
spec(ExecutionCommandReceipt, command_id=ID, payload_hash=hashed, session_id=ID, action=enum('cancel','resume','reconcile','withdraw'), target_id=ID, expected_version=count, recorded_at=T, account_version=count, result_ref=ExecutionRef)
NESTED = MappingProxyType({cls: {n: _nested(r) for n,r in rules.items() if _nested(r) is not None} for cls,rules in SPECS.items()})
SPECS = MappingProxyType({cls: MappingProxyType(rules) for cls,rules in SPECS.items()})


def encoded(obj):
    from .serialization import CanonicalPayload, canonical_bytes
    return canonical_bytes(CanonicalPayload(type(obj).__name__, 1, 'synthetic', obj))


def checked(obj):
    from .serialization import parse_payload
    return parse_payload(encoded(obj)).payload


def ref(kind, identity, obj):
    from .serialization import CanonicalPayload, canonical_hash
    return ExecutionRef(kind, identity, getattr(obj,'state_version',getattr(obj,'version',getattr(obj,'revision',1))), CANONICAL,
        canonical_hash(CanonicalPayload(type(obj).__name__,1,'synthetic',obj)))


FIXTURE_REF = ExecutionRef('fixture','qh-execution-synthetic-v1',1,CANONICAL,FIXTURE_SHA)
