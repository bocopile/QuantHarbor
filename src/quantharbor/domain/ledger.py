"""Q20 닫힌 합성 원장. 숫자 연산은 10**18 고정소수 정수만 사용한다."""
from dataclasses import dataclass, fields
import re

from .primitives import ContractError, currency, decimal_string, identifier, utc_instant

MAX_EVENTS = 4096
MAX_LEGS = 32
MAX_POSITIONS = 32
MAX_REFS = 32
MAX_SEQUENCE = 2147483647
MAX_JSON_BYTES = 65536
REDUCER_VERSION = 'synthetic-ledger-v1'
ACCOUNTS = ('settled_cash', 'unsettled_receivable', 'unsettled_payable',
            'trade_clearing', 'opening_equity', 'external_flow', 'fee_expense',
            'tax_expense', 'dividend_income', 'fx_clearing')
EVENT_TYPES = ('baseline', 'trade', 'fee', 'tax', 'deposit', 'withdrawal',
               'dividend', 'fx', 'settlement', 'split', 'unsupported')


def choice(value, values):
    if type(value) is not str or value not in values:
        raise ContractError()


def integer(value, low=1, high=MAX_SEQUENCE):
    if type(value) is not int or not low <= value <= high:
        raise ContractError()


def boolean(value):
    if type(value) is not bool:
        raise ContractError()


def exact(value, cls):
    if type(value) is not cls:
        raise ContractError()
    cls(**{f.name: getattr(value, f.name) for f in fields(cls)})


def items(value, cls, maximum):
    if type(value) is not tuple or len(value) > maximum:
        raise ContractError()
    for item in value:
        identifier(item) if cls is str else exact(item, cls)


def digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ContractError()


def account(value):
    identifier(value)
    if not value.startswith('synthetic-account:') or value == 'synthetic-account:':
        raise ContractError()


def instant(value):
    result = utc_instant(value)
    if not '2000' <= result[:4] <= '2100':
        raise ContractError()
    return result


def scaled(value):
    value = decimal_string(value)
    whole, _, fraction = value.removeprefix('-').partition('.')
    result = int(whole) * 10**18 + int(fraction.ljust(18, '0'))
    return -result if value.startswith('-') else result


def unscaled(value):
    whole, fraction = divmod(abs(value), 10**18)
    return decimal_string(('-' if value < 0 else '') + str(whole) + '.' + str(fraction).zfill(18))


def negated(value):
    return unscaled(-scaled(value))


def hash_record(value):
    from .serialization import CanonicalPayload, canonical_hash
    return canonical_hash(CanonicalPayload(type(value).__name__, 1, 'synthetic', value))


@dataclass(frozen=True, slots=True)
class CashLeg:
    account: str
    currency: str
    amount: str
    basis: str

    def __post_init__(self):
        choice(self.account, ACCOUNTS)
        currency(self.currency)
        object.__setattr__(self, 'amount', decimal_string(self.amount))
        choice(self.basis, ('trade', 'settlement'))


@dataclass(frozen=True, slots=True)
class PositionDelta:
    instrument_id: str
    venue_id: str
    mapping_version: str
    unit: str
    amount: str

    def __post_init__(self):
        for value in (self.instrument_id, self.venue_id, self.mapping_version, self.unit):
            identifier(value)
        object.__setattr__(self, 'amount', decimal_string(self.amount))

    @property
    def key(self):
        return (self.instrument_id, self.venue_id, self.mapping_version, self.unit)


@dataclass(frozen=True, slots=True)
class LedgerCompleteness:
    complete: bool
    costs_known: bool
    semantics_known: bool

    def __post_init__(self):
        for value in (self.complete, self.costs_known, self.semantics_known):
            boolean(value)


@dataclass(frozen=True, slots=True)
class LedgerBaseline:
    cash_complete: bool
    positions_complete: bool
    scope: str

    def __post_init__(self):
        boolean(self.cash_complete)
        boolean(self.positions_complete)
        choice(self.scope, ('entire_account',))


@dataclass(frozen=True, slots=True)
class SplitRatio:
    numerator: int
    denominator: int

    def __post_init__(self):
        integer(self.numerator, 1, 1000000)
        integer(self.denominator, 1, 1000000)


@dataclass(frozen=True, slots=True)
class SyntheticLedgerSubmission:
    schema_version: int
    environment: str
    account_ref: str
    source_kind: str
    source_event_key: str
    source_revision: int
    predecessor_revision: int | None
    mapping_version: str
    event_type: str
    effective_at: str
    revision_mode: str
    correction_of: str | None
    cash_legs: tuple[CashLeg, ...]
    position_deltas: tuple[PositionDelta, ...]
    evidence_refs: tuple[str, ...]
    completeness: LedgerCompleteness
    baseline: LedgerBaseline | None
    dependency_refs: tuple[str, ...]
    split_ratio: SplitRatio | None

    def __post_init__(self):
        integer(self.schema_version, 1, 1)
        choice(self.environment, ('synthetic',))
        account(self.account_ref)
        for value in (self.source_kind, self.source_event_key, self.mapping_version):
            identifier(value)
        integer(self.source_revision)
        if self.predecessor_revision is not None:
            integer(self.predecessor_revision)
        if self.correction_of is not None:
            identifier(self.correction_of)
        choice(self.event_type, EVENT_TYPES)
        choice(self.revision_mode, ('original', 'retroactive', 'prospective', 'unsupported'))
        object.__setattr__(self, 'effective_at', instant(self.effective_at))
        items(self.cash_legs, CashLeg, MAX_LEGS)
        items(self.position_deltas, PositionDelta, MAX_POSITIONS)
        items(self.evidence_refs, str, MAX_REFS)
        items(self.dependency_refs, str, MAX_REFS)
        if len(set(self.evidence_refs)) != len(self.evidence_refs) or len(set(self.dependency_refs)) != len(self.dependency_refs):
            raise ContractError()
        if len({(x.account, x.currency) for x in self.cash_legs}) != len(self.cash_legs):
            raise ContractError()
        if len({x.key for x in self.position_deltas}) != len(self.position_deltas):
            raise ContractError()
        exact(self.completeness, LedgerCompleteness)
        if self.baseline is not None:
            exact(self.baseline, LedgerBaseline)
        if self.split_ratio is not None:
            exact(self.split_ratio, SplitRatio)
        if any(x.mapping_version != self.mapping_version for x in self.position_deltas):
            raise ContractError()

    @property
    def identity(self):
        return self.source_kind, self.source_event_key, self.source_revision


@dataclass(frozen=True, slots=True)
class LedgerEventBody:
    schema_version: int
    environment: str
    account_ref: str
    event_id: str
    sequence: int
    recorded_at: str
    effective_at: str
    bundle_id: str
    kind: str
    source_kind: str
    source_event_key: str
    source_revision: int
    correction_of: str | None
    submission_hash: str
    submission: SyntheticLedgerSubmission
    cash_legs: tuple[CashLeg, ...]
    position_deltas: tuple[PositionDelta, ...]

    def __post_init__(self):
        integer(self.schema_version, 1, 1)
        choice(self.environment, ('synthetic',))
        account(self.account_ref)
        for value in (self.event_id, self.bundle_id):
            identifier(value)
        integer(self.sequence)
        for name in ('recorded_at', 'effective_at'):
            object.__setattr__(self, name, instant(getattr(self, name)))
        choice(self.kind, ('replacement', 'reversal'))
        identifier(self.source_kind)
        identifier(self.source_event_key)
        integer(self.source_revision)
        exact(self.submission, SyntheticLedgerSubmission)
        expected_identity = (('internal-reversal', self.event_id, 1) if self.kind == 'reversal'
                             else self.submission.identity)
        if (self.source_kind, self.source_event_key, self.source_revision) != expected_identity:
            raise ContractError()
        if self.correction_of is not None:
            identifier(self.correction_of)
        digest(self.submission_hash)
        if self.submission.account_ref != self.account_ref:
            raise ContractError()
        items(self.cash_legs, CashLeg, MAX_LEGS)
        items(self.position_deltas, PositionDelta, MAX_POSITIONS)
        sign = -1 if self.kind == 'reversal' else 1
        expected_cash = tuple(CashLeg(x.account, x.currency, unscaled(sign * scaled(x.amount)), x.basis)
                              for x in self.submission.cash_legs)
        expected_positions = tuple(PositionDelta(*x.key, unscaled(sign * scaled(x.amount)))
                                   for x in self.submission.position_deltas)
        if self.cash_legs != expected_cash or self.position_deltas != expected_positions:
            raise ContractError()
        if self.kind == 'reversal' and self.correction_of is None:
            raise ContractError()
        if self.submission_hash != hash_record(self.submission):
            raise ContractError()
        if self.kind == 'replacement' and (self.correction_of != self.submission.correction_of or self.effective_at != self.submission.effective_at):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    body: LedgerEventBody
    payload_hash: str
    canonicalization_version: str = 'qh-canonical-json-v1'

    def __post_init__(self):
        choice(self.canonicalization_version, ('qh-canonical-json-v1',))
        exact(self.body, LedgerEventBody)
        digest(self.payload_hash)
        if self.payload_hash != hash_record(self.body) or self.body.submission_hash != hash_record(self.body.submission):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class CashBalance:
    account: str
    currency: str
    amount: str

    def __post_init__(self):
        choice(self.account, ACCOUNTS)
        currency(self.currency)
        object.__setattr__(self, 'amount', decimal_string(self.amount))


@dataclass(frozen=True, slots=True)
class LedgerProjection:
    schema_version: int
    environment: str
    account_ref: str
    projection_id: str
    ledger_cursor: int
    as_of: str
    knowledge_cutoff: str
    mode: str
    reducer_version: str
    supersedes_projection_id: str | None
    cash_balances: tuple[CashBalance, ...]
    holdings: tuple[PositionDelta, ...]
    baseline_known: bool
    complete: bool
    reason_codes: tuple[str, ...]
    available_cash: None
    reserved_cash: None
    broker_buy_capacity: None
    availability_reason: str

    def __post_init__(self):
        integer(self.schema_version, 1, 1)
        choice(self.environment, ('synthetic',))
        account(self.account_ref)
        identifier(self.projection_id)
        integer(self.ledger_cursor, 0)
        for name in ('as_of', 'knowledge_cutoff'):
            object.__setattr__(self, name, instant(getattr(self, name)))
        choice(self.mode, ('as_known', 'restated'))
        choice(self.reducer_version, (REDUCER_VERSION,))
        if self.supersedes_projection_id is not None:
            identifier(self.supersedes_projection_id)
        items(self.cash_balances, CashBalance, MAX_EVENTS)
        items(self.holdings, PositionDelta, MAX_EVENTS)
        items(self.reason_codes, str, MAX_EVENTS)
        if tuple(sorted(set(self.reason_codes))) != self.reason_codes:
            raise ContractError()
        for reason in self.reason_codes:
            choice(reason, ('baseline_missing', 'economic_balance_invalid',
                            'correction_consequences_unresolved', 'quarantined_observation'))
        cash_keys = tuple((x.account, x.currency) for x in self.cash_balances)
        position_keys = tuple(x.key for x in self.holdings)
        if tuple(sorted(set(cash_keys))) != cash_keys or tuple(sorted(set(position_keys))) != position_keys:
            raise ContractError()
        boolean(self.baseline_known)
        boolean(self.complete)
        if self.complete != (not self.reason_codes) or self.baseline_known == ('baseline_missing' in self.reason_codes):
            raise ContractError()
        if any(x is not None for x in (self.available_cash, self.reserved_cash, self.broker_buy_capacity)):
            raise ContractError()
        choice(self.availability_reason, ('availability_semantics_unverified',))


@dataclass(frozen=True, slots=True)
class AppendResult:
    status: str
    reason: str | None
    cursor: int
    event_ids: tuple[str, ...]
    submission_hash: str
    projection_id: str | None

    def __post_init__(self):
        choice(self.status, ('accepted', 'duplicate', 'quarantined'))
        if self.reason is not None:
            identifier(self.reason)
        integer(self.cursor)
        items(self.event_ids, str, 2)
        digest(self.submission_hash)
        if self.projection_id is not None:
            identifier(self.projection_id)
