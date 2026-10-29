"""Q21 합성 읽기 모델. 유리수 연산·닫힌 불변 계약; 원장 쓰기 권한은 없다."""
from dataclasses import dataclass
from fractions import Fraction

from .primitives import ContractError, Price, FX, currency, decimal_string, identifier
from .ledger import (CashBalance, LedgerProjection, PositionDelta, account, boolean,
                     choice, digest, exact, hash_record, instant, integer, items)
from .market_data import (MarketItem, PriceBar, FXObservation, RecordRef, RightsGrant,
                          QualityResult, QueryScope, header, item_ref)
from .market_storage import ContextRef
from .broker_read import BrokerReadScope

MAX_INPUTS = 128
ECONOMIC_CASH = ('settled_cash', 'unsettled_payable', 'unsettled_receivable')
DOMAINS = ('holdings',) + ECONOMIC_CASH
STAGES = ('holding_native', 'currency_sum', 'currency_base', 'base_sum')


def number(value):
    return Fraction(decimal_string(value))


def finite(value):
    """유한 정확값만 저장한다. 중간값의 크기/scale을 몰래 줄이지 않는다."""
    value = Fraction(value)
    scaled = value * 10**18
    if scaled.denominator != 1:
        raise ContractError()
    whole, fraction = divmod(abs(scaled.numerator), 10**18)
    return decimal_string(('-' if value < 0 else '') + str(whole) + '.' + str(fraction).zfill(18))


def quantize(value, quantum):
    """실제 quantum 배수로 half-even. 음수도 대칭이며 Decimal context 무관."""
    q = number(quantum)
    if q <= 0:
        raise ContractError()
    units = Fraction(value) / q
    whole, remainder = divmod(abs(units.numerator), units.denominator)
    if remainder * 2 > units.denominator or (remainder * 2 == units.denominator and whole % 2):
        whole += 1
    return finite((-whole if units < 0 else whole) * q)


def ordered(values, cls, key=lambda x: x):
    items(values, cls, MAX_INPUTS)
    keys = tuple(key(x) for x in values)
    if tuple(sorted(set(keys))) != keys:
        raise ContractError()


def reasons(values):
    ordered(values, str)


def nullable_number(obj, name):
    value = getattr(obj, name)
    if value is not None:
        object.__setattr__(obj, name, decimal_string(value))


@dataclass(frozen=True, slots=True)
class PositionKey:
    instrument_id: str
    venue_id: str
    mapping_version: str
    unit: str

    def __post_init__(self):
        for x in self.key:
            identifier(x)

    @property
    def key(self):
        return self.instrument_id, self.venue_id, self.mapping_version, self.unit


@dataclass(frozen=True, slots=True)
class BalanceScope:
    coverage: str
    positions: tuple[PositionKey, ...]
    currencies: tuple[str, ...]
    components: tuple[str, ...]

    def __post_init__(self):
        choice(self.coverage, ('entire_account', 'subset'))
        ordered(self.positions, PositionKey, lambda x: x.key)
        ordered(self.currencies, str)
        ordered(self.components, str)
        for x in self.currencies:
            currency(x)
        for x in self.components:
            choice(x, DOMAINS)
        if not self.components or ('holdings' not in self.components and self.positions):
            raise ContractError()
        if self.coverage == 'entire_account':
            if self.positions or self.currencies != ('KRW', 'USD') or self.components != tuple(sorted(DOMAINS)):
                raise ContractError()
        elif 'holdings' in self.components and not self.positions:
            raise ContractError()
        if any(x in self.components for x in ECONOMIC_CASH) and not self.currencies:
            raise ContractError()

    def contains_position(self, key):
        return 'holdings' in self.components and (self.coverage == 'entire_account' or key in {x.key for x in self.positions})

    @property
    def labels(self):
        return tuple(sorted((('holdings:entire_account',) if self.coverage == 'entire_account' else
                    tuple('holding:' + ':'.join(x.key) for x in self.positions)) +
                    tuple(a + ':' + c for a in self.components if a != 'holdings' for c in self.currencies)))


def scope_contains(outer, inner):
    return (set(inner.components) <= set(outer.components) and set(inner.currencies) <= set(outer.currencies)
            and (outer.coverage == 'entire_account' or (inner.coverage == 'subset' and
                 {x.key for x in inner.positions} <= {x.key for x in outer.positions})))


@dataclass(frozen=True, slots=True)
class ValuationRequest:
    schema_version: int
    environment: str
    account_ref: str
    request_id: str
    ledger_cursor: int
    as_of: str
    knowledge_cutoff: str
    evaluated_at: str
    projection_mode: str
    base_currency: str
    purpose: str
    valuation_policy_version: str
    reconciliation_policy_version: str
    scope: BalanceScope
    original_cutoff: str | None = None
    supersedes_snapshot_id: str | None = None

    def __post_init__(self):
        header(self)
        account(self.account_ref)
        for x in (self.request_id, self.valuation_policy_version, self.reconciliation_policy_version):
            identifier(x)
        integer(self.ledger_cursor, 0)
        for name in ('as_of', 'knowledge_cutoff', 'evaluated_at'):
            object.__setattr__(self, name, instant(getattr(self, name)))
        choice(self.projection_mode, ('as_known', 'restated'))
        choice(self.purpose, ('research', 'report'))
        currency(self.base_currency)
        exact(self.scope, BalanceScope)
        if self.knowledge_cutoff > self.evaluated_at or self.as_of > self.evaluated_at:
            raise ContractError()
        if self.supersedes_snapshot_id is not None:
            identifier(self.supersedes_snapshot_id)
        if self.projection_mode == 'restated':
            object.__setattr__(self, 'original_cutoff', instant(self.original_cutoff))
            if self.original_cutoff >= self.knowledge_cutoff or self.supersedes_snapshot_id is None:
                raise ContractError()
        elif self.original_cutoff is not None:
            raise ContractError()


def bind_projection(projection, request):
    exact(projection, LedgerProjection)
    exact(request, ValuationRequest)
    if (projection.environment, projection.account_ref, projection.ledger_cursor, projection.as_of, projection.knowledge_cutoff, projection.mode) != (
            request.environment, request.account_ref, request.ledger_cursor, request.as_of, request.knowledge_cutoff, request.projection_mode):
        raise ContractError()
    if len(projection.holdings) > MAX_INPUTS or len(projection.cash_balances) > MAX_INPUTS:
        raise ContractError()


def ledger_reasons(projection):
    result = set(projection.reason_codes)
    if any(number(x.amount) < 0 for x in projection.holdings) or any(
            (x.account == 'unsettled_payable' and number(x.amount) > 0) or
            (x.account in ('settled_cash', 'unsettled_receivable') and number(x.amount) < 0)
            for x in projection.cash_balances):
        result.add('economic_balance_invalid')
    return result


@dataclass(frozen=True, slots=True)
class CurrencyQuantum:
    currency: str
    quantum: str

    def __post_init__(self):
        currency(self.currency)
        object.__setattr__(self, 'quantum', decimal_string(self.quantum))
        if number(self.quantum) <= 0:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class SeriesSelection:
    source_id: str
    dataset_id: str
    dataset_version: str
    series_id: str

    def __post_init__(self):
        for x in (*self.dataset_key, self.series_id):
            identifier(x)

    @property
    def dataset_key(self):
        return self.source_id, self.dataset_id, self.dataset_version


@dataclass(frozen=True, slots=True)
class PriceSelection:
    position: PositionKey
    series: SeriesSelection

    def __post_init__(self):
        exact(self.position, PositionKey)
        exact(self.series, SeriesSelection)


@dataclass(frozen=True, slots=True)
class FXSelection:
    native_currency: str
    series: SeriesSelection

    def __post_init__(self):
        currency(self.native_currency)
        exact(self.series, SeriesSelection)


@dataclass(frozen=True, slots=True)
class ValuationPolicy:
    schema_version: int
    environment: str
    version: str
    prices: tuple[PriceSelection, ...]
    fx: tuple[FXSelection, ...]
    quantums: tuple[CurrencyQuantum, ...]
    max_price_age_seconds: int
    max_fx_age_seconds: int
    price_method: str = 'raw_close'
    rounding: str = 'half_even'
    stages: tuple[str, ...] = STAGES

    def __post_init__(self):
        header(self)
        identifier(self.version)
        ordered(self.prices, PriceSelection, lambda x: x.position.key)
        ordered(self.fx, FXSelection, lambda x: x.native_currency)
        ordered(self.quantums, CurrencyQuantum, lambda x: x.currency)
        if not self.quantums:
            raise ContractError()
        integer(self.max_price_age_seconds, 0, 31536000)
        integer(self.max_fx_age_seconds, 0, 31536000)
        choice(self.price_method, ('raw_close',))
        choice(self.rounding, ('half_even',))
        if type(self.stages) is not tuple or self.stages != STAGES:
            raise ContractError()

    def quantum(self, code):
        found = [x.quantum for x in self.quantums if x.currency == code]
        if len(found) != 1:
            raise ContractError()
        return found[0]


@dataclass(frozen=True, slots=True)
class MarketProof:
    selection: SeriesSelection
    descriptor_hash: str
    receipt_hashes: tuple[str, ...]
    evidence_index_hash: str
    envelope_hash: str
    summary_hash: str
    records: tuple[RecordRef, ...]
    selected: tuple[MarketItem, ...]
    contexts: tuple[ContextRef, ...]
    rights: RightsGrant
    quality: QualityResult
    scope: QueryScope
    held_reasons: tuple[str, ...]

    def __post_init__(self):
        exact(self.selection, SeriesSelection)
        for x in (self.descriptor_hash, self.evidence_index_hash, self.envelope_hash, self.summary_hash):
            digest(x)
        items(self.receipt_hashes, str, 16)
        for x in self.receipt_hashes:
            digest(x)
        ordered(self.records, RecordRef, lambda x: x.key)
        ordered(self.selected, MarketItem, lambda x: x.revision.key)
        if any(item_ref(x) not in self.records for x in self.selected):
            raise ContractError()
        items(self.contexts, ContextRef, 3)
        if tuple(x.kind for x in self.contexts) != ('catalog', 'calendar', 'timezone'):
            raise ContractError()
        exact(self.rights, RightsGrant)
        exact(self.quality, QualityResult)
        exact(self.scope, QueryScope)
        reasons(self.held_reasons)
        if self.selection.dataset_key != (self.rights.source_id, self.rights.dataset_id, self.rights.dataset_version):
            raise ContractError()
        if any(x.observation.rights_ref != self.rights.rights_ref for x in self.selected):
            raise ContractError()
        if self.selection.series_id not in self.scope.series_ids or any(
                (x.source_id, x.dataset_id) != self.selection.dataset_key[:2] for x in self.records):
            raise ContractError()

    @property
    def usable(self):
        return self.quality.status == 'complete' and self.quality.rights_allowed and not self.quality.reasons and not self.quality.missing_scope and not self.held_reasons


@dataclass(frozen=True, slots=True)
class HoldingValuation:
    position: PositionDelta
    currency: str | None
    price: Price | None
    price_ref: RecordRef | None
    native_value: str | None
    reason_codes: tuple[str, ...]
    cost_basis: None = None
    unrealized_pnl: None = None
    price_pnl: None = None
    fx_pnl: None = None
    costing_reason: str = 'costing_spec_pending_q23'

    def __post_init__(self):
        exact(self.position, PositionDelta)
        if self.currency is not None:
            currency(self.currency)
        reasons(self.reason_codes)
        nullable_number(self, 'native_value')
        if any(x is not None for x in (self.cost_basis, self.unrealized_pnl, self.price_pnl, self.fx_pnl)):
            raise ContractError()
        choice(self.costing_reason, ('costing_spec_pending_q23',))
        if self.native_value is None:
            if not self.reason_codes or self.price is not None or self.price_ref is not None:
                raise ContractError()
        else:
            exact(self.price, Price)
            exact(self.price_ref, RecordRef)
            if self.reason_codes or (self.price.currency, self.price.instrument_id, self.price.quantity_unit) != (
                    self.currency, self.position.instrument_id, self.position.unit) or number(self.price.amount) <= 0:
                raise ContractError()


@dataclass(frozen=True, slots=True)
class CashValuation:
    currency: str
    settled_cash: str
    unsettled_receivable: str
    unsettled_payable: str
    economic_cash: str
    complete: bool
    reason_codes: tuple[str, ...]
    source_total: None = None
    reserved_cash: None = None
    available_cash: None = None
    broker_buy_capacity: None = None
    availability_reason: str = 'availability_semantics_unverified'

    def __post_init__(self):
        currency(self.currency)
        for name in (*ECONOMIC_CASH, 'economic_cash'):
            object.__setattr__(self, name, decimal_string(getattr(self, name)))
        boolean(self.complete)
        reasons(self.reason_codes)
        if self.complete != (not self.reason_codes) or number(self.economic_cash) != sum(number(getattr(self, a)) for a in ECONOMIC_CASH):
            raise ContractError()
        if any(x is not None for x in (self.source_total, self.reserved_cash, self.available_cash, self.broker_buy_capacity)):
            raise ContractError()
        choice(self.availability_reason, ('availability_semantics_unverified',))


@dataclass(frozen=True, slots=True)
class CurrencyValuation:
    currency: str
    known_subtotal: str
    complete: bool
    fx: FX | None
    fx_ref: RecordRef | None
    fx_direction: str
    base_value: str | None
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        currency(self.currency)
        object.__setattr__(self, 'known_subtotal', decimal_string(self.known_subtotal))
        nullable_number(self, 'base_value')
        boolean(self.complete)
        reasons(self.reason_codes)
        choice(self.fx_direction, ('identity', 'multiply', 'divide', 'unknown'))
        if self.fx_direction in ('multiply', 'divide'):
            exact(self.fx, FX)
            exact(self.fx_ref, RecordRef)
        elif self.fx is not None or self.fx_ref is not None:
            raise ContractError()
        if (self.base_value is None) != (self.fx_direction == 'unknown'):
            raise ContractError()
        if not self.complete and not self.reason_codes:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class ValuationResult:
    schema_version: int
    environment: str
    projection: LedgerProjection
    request: ValuationRequest
    policy: ValuationPolicy
    projection_hash: str
    request_hash: str
    policy_hash: str
    market_proofs: tuple[MarketProof, ...]
    holdings: tuple[HoldingValuation, ...]
    cash_by_currency: tuple[CashValuation, ...]
    native_totals: tuple[CurrencyValuation, ...]
    known_subtotal: str
    nav: str | None
    complete: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        header(self)
        bind_projection(self.projection, self.request)
        exact(self.policy, ValuationPolicy)
        if self.request.valuation_policy_version != self.policy.version:
            raise ContractError()
        for value, obj in ((self.projection_hash, self.projection), (self.request_hash, self.request), (self.policy_hash, self.policy)):
            if value != hash_record(obj):
                raise ContractError()
        ordered(self.market_proofs, MarketProof, lambda x: (*x.selection.dataset_key, x.selection.series_id))
        ordered(self.holdings, HoldingValuation, lambda x: x.position.key)
        ordered(self.cash_by_currency, CashValuation, lambda x: x.currency)
        ordered(self.native_totals, CurrencyValuation, lambda x: x.currency)
        reasons(self.reason_codes)
        boolean(self.complete)
        object.__setattr__(self, 'known_subtotal', decimal_string(self.known_subtotal))
        nullable_number(self, 'nav')
        validate_valuation(self)


def validate_valuation(result):
    p, req, policy = result.projection, result.request, result.policy
    if tuple(x.position for x in result.holdings) != p.holdings:
        raise ContractError()
    codes = {x.currency for x in p.cash_balances if x.account in ECONOMIC_CASH} | {x.currency for x in result.holdings if x.currency}
    if tuple(x.currency for x in result.native_totals) != tuple(sorted(codes)) or tuple(x.currency for x in result.cash_by_currency) != tuple(sorted(codes)):
        raise ContractError()
    cash = {(x.account, x.currency): x.amount for x in p.cash_balances}
    for row in result.cash_by_currency:
        expected = tuple(cash.get((a, row.currency), '0') for a in ECONOMIC_CASH)
        economic_invalid = number(expected[0]) < 0 or number(expected[1]) > 0 or number(expected[2]) < 0
        expected_reasons = tuple(sorted(ledger_reasons(p) | ({'economic_balance_invalid'} if economic_invalid else set())))
        if tuple(getattr(row, a) for a in ECONOMIC_CASH) != expected or row.reason_codes != expected_reasons or row.complete != (not expected_reasons):
            raise ContractError()
    for row in result.holdings:
        if row.native_value is not None:
            if row.native_value != quantize(number(row.position.amount) * number(row.price.amount), policy.quantum(row.currency)):
                raise ContractError()
            selection = next((x.series for x in policy.prices if x.position.key == row.position.key), None)
            source = validate_ref(result, row.price_ref, selection)
            if type(source.revision.payload) is not PriceBar or source.revision.payload.adjustment != 'raw' or source.revision.payload.close != row.price:
                raise ContractError()
            if source.revision.payload.execution_venue_id != row.position.venue_id:
                raise ContractError()
            validate_age(source, req, policy.max_price_age_seconds)
    all_reasons = ledger_reasons(p)
    for row in result.holdings:
        all_reasons.update(row.reason_codes)
    for row in result.cash_by_currency:
        all_reasons.update(row.reason_codes)
    for row in result.native_totals:
        c = next(x for x in result.cash_by_currency if x.currency == row.currency)
        holdings = [x for x in result.holdings if x.currency == row.currency]
        total = number(c.economic_cash) + sum((number(x.native_value) for x in holdings if x.native_value is not None), Fraction())
        native_complete = c.complete and all(x.native_value is not None for x in holdings)
        if row.known_subtotal != finite(total) or row.complete != native_complete:
            raise ContractError()
        expected_reasons = set(c.reason_codes) | {reason for x in holdings for reason in x.reason_codes}
        if row.currency == req.base_currency:
            if row.fx_direction != 'identity' or row.base_value != quantize(total, policy.quantum(req.base_currency)):
                raise ContractError()
        elif row.fx_direction != 'unknown':
            selection = next((x.series for x in policy.fx if x.native_currency == row.currency), None)
            source = validate_ref(result, row.fx_ref, selection)
            if type(source.revision.payload) is not FXObservation or source.revision.payload.fx != row.fx:
                raise ContractError()
            validate_age(source, req, policy.max_fx_age_seconds)
            pair = row.fx.base_currency, row.fx.quote_currency
            expected_pair = (row.currency, req.base_currency) if row.fx_direction == 'multiply' else (req.base_currency, row.currency)
            if pair != expected_pair or row.fx.as_of > req.as_of:
                raise ContractError()
            converted = total * number(row.fx.rate) if row.fx_direction == 'multiply' else total / number(row.fx.rate)
            if row.base_value != quantize(converted, policy.quantum(req.base_currency)):
                raise ContractError()
        elif not row.reason_codes:
            raise ContractError()
        if not expected_reasons <= set(row.reason_codes):
            raise ContractError()
        all_reasons.update(row.reason_codes)
    expected_subtotal = finite(sum((number(x.base_value) for x in result.native_totals if x.base_value is not None), Fraction()))
    complete = p.complete and not all_reasons and all(x.native_value is not None for x in result.holdings) and all(x.complete and x.base_value is not None for x in result.native_totals)
    if result.known_subtotal != expected_subtotal or result.complete != complete or result.reason_codes != tuple(sorted(all_reasons)) or result.nav != (expected_subtotal if complete else None):
        raise ContractError()


def validate_ref(result, ref, selection):
    if selection is None or (ref.source_id, ref.dataset_id, ref.series_id) != (selection.source_id, selection.dataset_id, selection.series_id):
        raise ContractError()
    proofs = [x for x in result.market_proofs if x.selection == selection]
    if len(proofs) != 1 or ref not in proofs[0].records or not proofs[0].usable:
        raise ContractError()
    proof = proofs[0]
    if not all(proof.rights.allows(at=result.request.evaluated_at, purpose=purpose, source_id=selection.source_id,
            dataset_id=selection.dataset_id, dataset_version=selection.dataset_version) for purpose in (result.request.purpose, 'store')):
        raise ContractError()
    candidates = [x for x in proof.selected if x.revision.series_id == selection.series_id]
    if not candidates:
        raise ContractError()
    latest = max(x.revision.effective_at for x in candidates)
    selected = [x for x in candidates if x.revision.effective_at == latest]
    if len(selected) != 1 or item_ref(selected[0]) != ref:
        raise ContractError()
    return selected[0]


def validate_snapshot_storage(valuation):
    """평가의 unknown 여부와 별개로 실제 저장할 원시 payload의 권리를 검사한다."""
    for proof in valuation.market_proofs:
        if proof.selected and not proof.rights.allows(at=valuation.request.evaluated_at, purpose='store',
                source_id=proof.selection.source_id, dataset_id=proof.selection.dataset_id,
                dataset_version=proof.selection.dataset_version):
            raise ContractError()


def validate_age(item, request, max_age):
    from datetime import datetime, timedelta
    r, o = item.revision, item.observation
    if (r.effective_at > request.as_of or r.published_at is None or r.published_at > request.knowledge_cutoff
            or o.observed_at > request.knowledge_cutoff or o.ingested_at > request.knowledge_cutoff
            or datetime.fromisoformat(request.as_of) - datetime.fromisoformat(r.effective_at) > timedelta(seconds=max_age)):
        raise ContractError()


@dataclass(frozen=True, slots=True)
class QuantityTolerance:
    unit: str
    tolerance: str

    def __post_init__(self):
        identifier(self.unit)
        object.__setattr__(self, 'tolerance', decimal_string(self.tolerance))
        if number(self.tolerance) < 0:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class CashTolerance:
    currency: str
    tolerance: str

    def __post_init__(self):
        currency(self.currency)
        object.__setattr__(self, 'tolerance', decimal_string(self.tolerance))
        if number(self.tolerance) < 0:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class ReconciliationPolicy:
    schema_version: int
    environment: str
    version: str
    quantities: tuple[QuantityTolerance, ...]
    cash: tuple[CashTolerance, ...]

    def __post_init__(self):
        header(self)
        identifier(self.version)
        ordered(self.quantities, QuantityTolerance, lambda x: x.unit)
        ordered(self.cash, CashTolerance, lambda x: x.currency)

    def tolerance(self, domain, unit):
        found = [x.tolerance for x in (self.quantities if domain == 'holdings' else self.cash)
                 if (x.unit if domain == 'holdings' else x.currency) == unit]
        if len(found) != 1:
            raise ContractError()
        return found[0]


@dataclass(frozen=True, slots=True)
class StatementSourceSnapshot:
    schema_version: int
    environment: str
    account_ref: str
    source_id: str
    statement_id: str
    source_revision: str
    source_snapshot_id: str
    mapping_version: str
    semantics_version: str
    scope: BalanceScope
    source_as_of: str
    observed_at: str
    ingested_at: str
    holdings: tuple[PositionDelta, ...]
    cash: tuple[CashBalance, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self):
        header(self)
        account(self.account_ref)
        for x in (self.source_id, self.statement_id, self.source_revision, self.source_snapshot_id, self.mapping_version):
            identifier(x)
        choice(self.semantics_version, ('economic-components-v1', 'unknown'))
        exact(self.scope, BalanceScope)
        for name in ('source_as_of', 'observed_at', 'ingested_at'):
            object.__setattr__(self, name, instant(getattr(self, name)))
        if not self.source_as_of <= self.observed_at <= self.ingested_at:
            raise ContractError()
        ordered(self.holdings, PositionDelta, lambda x: x.key)
        ordered(self.cash, CashBalance, lambda x: (x.account, x.currency))
        ordered(self.evidence_refs, str)
        if not self.evidence_refs or any(not self.scope.contains_position(x.key) for x in self.holdings):
            raise ContractError()
        if any(x.account not in ECONOMIC_CASH or x.account not in self.scope.components or x.currency not in self.scope.currencies for x in self.cash):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class SyntheticAccountStatement:
    schema_version: int
    environment: str
    snapshot: StatementSourceSnapshot
    source_snapshot_hash: str
    requested_scope: BalanceScope
    status: str
    complete: bool
    temporal_consistency: str
    mapping_status: str
    omitted_means_zero: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        header(self)
        exact(self.snapshot, StatementSourceSnapshot)
        if self.source_snapshot_hash != hash_record(self.snapshot):
            raise ContractError()
        exact(self.requested_scope, BalanceScope)
        if not scope_contains(self.requested_scope, self.snapshot.scope):
            raise ContractError()
        choice(self.status, ('success', 'partial', 'error', 'unknown'))
        boolean(self.complete)
        boolean(self.omitted_means_zero)
        choice(self.temporal_consistency, ('source_snapshot', 'bounded_observation', 'unknown'))
        choice(self.mapping_status, ('verified', 'unknown'))
        reasons(self.reason_codes)
        if self.complete and (self.status != 'success' or self.reason_codes or self.snapshot.scope != self.requested_scope):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class ReconciliationDifference:
    domain: str
    position: PositionKey | None
    currency: str | None
    unit: str
    ledger_amount: str | None
    statement_amount: str | None
    difference: str | None
    tolerance: str
    status: str
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        choice(self.domain, DOMAINS)
        identifier(self.unit)
        if self.domain == 'holdings':
            exact(self.position, PositionKey)
            if self.currency is not None or self.unit != self.position.unit:
                raise ContractError()
        else:
            currency(self.currency)
            if self.position is not None or self.unit != self.currency:
                raise ContractError()
        for name in ('ledger_amount', 'statement_amount', 'difference', 'tolerance'):
            nullable_number(self, name)
        if self.tolerance is None or number(self.tolerance) < 0:
            raise ContractError()
        reasons(self.reason_codes)
        choice(self.status, ('matched', 'mismatch', 'unknown'))
        known = self.ledger_amount is not None and self.statement_amount is not None
        if known:
            delta = finite(number(self.statement_amount) - number(self.ledger_amount))
            status = 'matched' if abs(number(delta)) <= number(self.tolerance) else 'mismatch'
            if self.difference != delta or self.status != status:
                raise ContractError()
        elif self.status != 'unknown' or self.difference is not None or not self.reason_codes:
            raise ContractError()

    @property
    def key(self):
        return self.domain, self.position.key if self.position else (), self.currency or ''


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    schema_version: int
    environment: str
    projection_hash: str
    request_hash: str
    policy_hash: str
    statement: SyntheticAccountStatement | None
    status: str
    requested_scope: BalanceScope
    covered_scope: BalanceScope | None
    missing_scope: tuple[str, ...]
    compared_domains: tuple[str, ...]
    differences: tuple[ReconciliationDifference, ...]
    scope_matched: bool
    full_account_balances_matched: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        header(self)
        for x in (self.projection_hash, self.request_hash, self.policy_hash):
            digest(x)
        if self.statement is not None:
            exact(self.statement, SyntheticAccountStatement)
        exact(self.requested_scope, BalanceScope)
        if self.covered_scope is not None:
            exact(self.covered_scope, BalanceScope)
        reasons(self.missing_scope)
        ordered(self.compared_domains, str)
        for x in self.compared_domains:
            choice(x, DOMAINS)
        ordered(self.differences, ReconciliationDifference, lambda x: x.key)
        reasons(self.reason_codes)
        choice(self.status, ('unreconciled', 'matched', 'mismatch', 'incomplete'))
        boolean(self.scope_matched)
        boolean(self.full_account_balances_matched)
        if self.scope_matched != (self.status == 'matched') or self.full_account_balances_matched != (
                self.scope_matched and self.requested_scope.coverage == 'entire_account'):
            raise ContractError()
        if self.status == 'matched' and (self.reason_codes or self.missing_scope or any(x.status != 'matched' for x in self.differences)):
            raise ContractError()
        if self.status == 'matched':
            validate_matched_reconciliation(self)
        if self.status == 'incomplete' and not self.reason_codes:
            raise ContractError()
        if self.status == 'mismatch' and (self.reason_codes or not any(x.status == 'mismatch' for x in self.differences)):
            raise ContractError()


def validate_matched_reconciliation(result):
    """독립 결과에 포함된 statement/scope/원수량 근거만으로 확인 가능한 일치 조건."""
    statement = result.statement
    if statement is None:
        raise ContractError()
    source, scope = statement.snapshot, result.requested_scope
    if (result.covered_scope != scope or statement.requested_scope != scope or source.scope != scope
            or not statement.complete or statement.status != 'success' or statement.reason_codes
            or statement.temporal_consistency != 'source_snapshot' or statement.mapping_status != 'verified'
            or source.semantics_version != 'economic-components-v1'
            or any(x.mapping_version != source.mapping_version or number(x.amount) < 0 for x in source.holdings)
            or any(number(x.amount) > 0 if x.account == 'unsettled_payable' else number(x.amount) < 0 for x in source.cash)):
        raise ContractError()
    if result.compared_domains != tuple(sorted({x.domain for x in result.differences})):
        raise ContractError()
    holdings = {x.key: x.amount for x in source.holdings}
    cash = {(x.account, x.currency): x.amount for x in source.cash}
    required = {('holdings', key, '') for key in holdings} | {('holdings', x.key, '') for x in scope.positions}
    required |= {(a, (), c) for a in scope.components if a in ECONOMIC_CASH for c in scope.currencies}
    if not required <= {x.key for x in result.differences}:
        raise ContractError()
    for row in result.differences:
        if row.domain == 'holdings':
            if not scope.contains_position(row.position.key) or row.position.mapping_version != source.mapping_version:
                raise ContractError()
            amount = holdings.get(row.position.key)
        else:
            if row.domain not in scope.components or row.currency not in scope.currencies:
                raise ContractError()
            amount = cash.get((row.domain, row.currency))
        if amount is None and statement.omitted_means_zero:
            amount = '0'
        if amount is None or row.statement_amount != amount or row.reason_codes:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class BrokerBatchInspection:
    schema_version: int
    environment: str
    request_hash: str
    batch_hash: str
    query_hash: str
    query_id: str
    account_ref: str
    source_status: str
    source_complete: bool
    source_error: str | None
    source_scope: BrokerReadScope
    source_missing_scope: tuple[str, ...]
    source_reason_codes: tuple[str, ...]
    started_at: str
    finished_at: str
    status: str
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        header(self)
        for x in (self.request_hash, self.batch_hash, self.query_hash):
            digest(x)
        identifier(self.query_id)
        account(self.account_ref)
        choice(self.source_status, ('success', 'partial', 'error', 'unsupported', 'unknown'))
        boolean(self.source_complete)
        if self.source_error is not None:
            identifier(self.source_error)
        exact(self.source_scope, BrokerReadScope)
        items(self.source_missing_scope, str, MAX_INPUTS)
        items(self.source_reason_codes, str, MAX_INPUTS)
        for name in ('started_at', 'finished_at'):
            object.__setattr__(self, name, instant(getattr(self, name)))
        choice(self.status, ('incomplete',))
        reasons(self.reason_codes)
        required = {'mapping_unknown', 'source_number_semantics_unverified', 'settlement_inclusion_unknown',
                    'reservation_inclusion_unknown', 'source_as_of_unknown', 'temporal_consistency_insufficient',
                    'scope_not_entire_account'}
        if not required <= set(self.reason_codes) or not set(self.source_reason_codes) <= set(self.reason_codes):
            raise ContractError()
        if self.source_error != (self.source_reason_codes[0] if self.source_reason_codes else None) or self.source_complete != (self.source_status == 'success'):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class DataRef:
    kind: str
    ref: str
    sha256: str

    def __post_init__(self):
        choice(self.kind, ('ledger', 'request', 'valuation_policy', 'reconciliation_policy', 'market', 'statement', 'broker'))
        identifier(self.ref)
        digest(self.sha256)


@dataclass(frozen=True, slots=True)
class SnapshotInputManifest:
    schema_version: int
    environment: str
    projection_hash: str
    request_hash: str
    valuation_policy_hash: str
    reconciliation_policy_hash: str
    valuation_hash: str
    reconciliation_hash: str
    broker_hash: str | None

    def __post_init__(self):
        header(self)
        for x in (self.projection_hash, self.request_hash, self.valuation_policy_hash, self.reconciliation_policy_hash,
                  self.valuation_hash, self.reconciliation_hash):
            digest(x)
        if self.broker_hash is not None:
            digest(self.broker_hash)


def snapshot_manifest(valuation, reconciliation, policy, broker=None):
    return SnapshotInputManifest(1, 'synthetic', valuation.projection_hash, valuation.request_hash,
        valuation.policy_hash, hash_record(policy), hash_record(valuation), hash_record(reconciliation),
        hash_record(broker) if broker else None)


def snapshot_refs(valuation, reconciliation, policy, broker=None):
    refs = [DataRef('ledger', valuation.projection.projection_id, valuation.projection_hash),
            DataRef('request', valuation.request.request_id, valuation.request_hash),
            DataRef('valuation_policy', valuation.policy.version, valuation.policy_hash),
            DataRef('reconciliation_policy', policy.version, hash_record(policy))]
    refs.extend(DataRef('market', 'market:' + str(i), hash_record(x)) for i, x in enumerate(valuation.market_proofs))
    if reconciliation.statement:
        refs.append(DataRef('statement', reconciliation.statement.snapshot.statement_id, hash_record(reconciliation.statement)))
    if broker:
        refs.append(DataRef('broker', broker.query_id, broker.batch_hash))
    return tuple(sorted(refs, key=lambda x: (x.kind, x.ref)))


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    schema_version: int
    environment: str
    snapshot_id: str
    account_ref: str
    ledger_cursor: int
    ledger_schema_version: int
    valuation_policy_version: str
    data_refs: tuple[DataRef, ...]
    as_of: str
    knowledge_cutoff: str
    projection_mode: str
    supersedes_snapshot_id: str | None
    holdings: tuple[HoldingValuation, ...]
    cash_by_currency: tuple[CashValuation, ...]
    open_order_refs: tuple[str, ...]
    reconciliation: str
    valuation_status: str
    created_at: str
    base_currency: str
    projection_hash: str
    valuation_policy_hash: str
    reconciliation_policy_hash: str
    valuation: ValuationResult
    reconciliation_details: ReconciliationResult
    reconciliation_policy: ReconciliationPolicy
    broker_details: BrokerBatchInspection | None
    input_manifest: SnapshotInputManifest
    open_orders_status: str = 'unknown'

    def __post_init__(self):
        header(self)
        exact(self.valuation, ValuationResult)
        exact(self.reconciliation_details, ReconciliationResult)
        exact(self.reconciliation_policy, ReconciliationPolicy)
        if self.broker_details is not None:
            exact(self.broker_details, BrokerBatchInspection)
        exact(self.input_manifest, SnapshotInputManifest)
        ordered(self.data_refs, DataRef, lambda x: (x.kind, x.ref))
        ordered(self.holdings, HoldingValuation, lambda x: x.position.key)
        ordered(self.cash_by_currency, CashValuation, lambda x: x.currency)
        if type(self.open_order_refs) is not tuple or self.open_order_refs:
            raise ContractError()
        choice(self.open_orders_status, ('unknown',))
        integer(self.ledger_cursor, 0)
        integer(self.ledger_schema_version, 1, 1)
        account(self.account_ref)
        for name in ('as_of', 'knowledge_cutoff', 'created_at'):
            object.__setattr__(self, name, instant(getattr(self, name)))
        v, r, req = self.valuation, self.reconciliation_details, self.valuation.request
        validate_snapshot_storage(v)
        expected = (req.account_ref, v.projection.ledger_cursor, v.policy.version, req.as_of, req.knowledge_cutoff,
                    req.projection_mode, req.supersedes_snapshot_id, v.holdings, v.cash_by_currency,
                    r.status if r.full_account_balances_matched or r.status != 'matched' else 'incomplete',
                    'complete' if v.complete else 'incomplete', req.evaluated_at, req.base_currency,
                    v.projection_hash, v.policy_hash, hash_record(self.reconciliation_policy))
        actual = (self.account_ref, self.ledger_cursor, self.valuation_policy_version, self.as_of, self.knowledge_cutoff,
                  self.projection_mode, self.supersedes_snapshot_id, self.holdings, self.cash_by_currency,
                  self.reconciliation, self.valuation_status, self.created_at, self.base_currency,
                  self.projection_hash, self.valuation_policy_hash, self.reconciliation_policy_hash)
        if actual != expected or (r.projection_hash, r.request_hash, r.policy_hash, r.requested_scope) != (
                v.projection_hash, v.request_hash, hash_record(self.reconciliation_policy), req.scope):
            raise ContractError()
        if req.reconciliation_policy_version != self.reconciliation_policy.version:
            raise ContractError()
        if self.broker_details and (self.broker_details.request_hash != v.request_hash or self.broker_details.account_ref != req.account_ref):
            raise ContractError()
        # 동일 순수 비교 함수를 복원에서도 호출해 차이·scope·완전성 위조를 거부한다.
        if r != compare_statement(v.projection, r.statement, req, self.reconciliation_policy):
            raise ContractError()
        if self.input_manifest != snapshot_manifest(v, r, self.reconciliation_policy, self.broker_details):
            raise ContractError()
        if self.snapshot_id != 'snapshot:' + hash_record(self.input_manifest):
            raise ContractError()
        if self.data_refs != snapshot_refs(v, r, self.reconciliation_policy, self.broker_details):
            raise ContractError()


def compare_statement(projection, statement, request, policy):
    """합성 statement의 원단위 비교. FX/평가 반올림/원장 변경이 없다."""
    bind_projection(projection, request)
    exact(policy, ReconciliationPolicy)
    if policy.version != request.reconciliation_policy_version:
        raise ContractError()
    hashes = hash_record(projection), hash_record(request), hash_record(policy)
    if statement is None:
        return ReconciliationResult(1, 'synthetic', *hashes, None, 'unreconciled', request.scope,
            None, request.scope.labels, (), (), False, False, ('statement_missing',))
    exact(statement, SyntheticAccountStatement)
    source = statement.snapshot
    if source.account_ref != request.account_ref or statement.requested_scope != request.scope:
        raise ContractError()
    covered = source.scope
    missing = tuple(sorted(set(request.scope.labels) - set(covered.labels)))
    why = ledger_reasons(projection) | set(statement.reason_codes)
    if not statement.complete or statement.status != 'success':
        why.add('statement_incomplete')
    if missing or covered != request.scope:
        why.add('scope_incomplete')
    if source.source_as_of != request.as_of:
        why.add('source_as_of_mismatch')
    if source.ingested_at > request.knowledge_cutoff or source.observed_at > request.knowledge_cutoff:
        why.add('source_after_cutoff')
    if statement.temporal_consistency != 'source_snapshot':
        why.add('temporal_consistency_insufficient')
    mapping_known = statement.mapping_status == 'verified' and all(x.mapping_version == source.mapping_version for x in source.holdings)
    if not mapping_known:
        why.add('mapping_unknown')
    semantics_known = source.semantics_version == 'economic-components-v1'
    if not semantics_known:
        why.add('cash_semantics_unknown')
    if any((x.account == 'unsettled_payable' and number(x.amount) > 0) or
           (x.account != 'unsettled_payable' and number(x.amount) < 0) for x in source.cash):
        why.add('economic_balance_invalid')
    if any(number(x.amount) < 0 for x in source.holdings):
        why.add('economic_balance_invalid')
    omitted_zero = statement.complete and statement.status == 'success' and not missing and covered == request.scope and statement.omitted_means_zero
    ledger_h = {x.key: x.amount for x in projection.holdings if request.scope.contains_position(x.key)}
    source_h = {x.key: x.amount for x in source.holdings}
    ledger_c = {(x.account, x.currency): x.amount for x in projection.cash_balances if
                x.account in request.scope.components and x.account in ECONOMIC_CASH and x.currency in request.scope.currencies}
    source_c = {(x.account, x.currency): x.amount for x in source.cash}
    diffs = []

    def difference(domain, position, code, left, right, source_known):
        unit = position.unit if position else code
        tolerance = policy.tolerance(domain, unit)
        notes = set()
        if left is None and projection.complete:
            left = '0'
        if right is None and omitted_zero and source_known:
            right = '0'
        if not source_known:
            right = None
            notes.add('mapping_unknown' if domain == 'holdings' else 'cash_semantics_unknown')
        if left is None:
            notes.add('ledger_value_unknown')
        if right is None:
            notes.add('statement_value_unknown')
        delta = finite(number(right) - number(left)) if left is not None and right is not None else None
        status = ('matched' if abs(number(delta)) <= number(tolerance) else 'mismatch') if delta is not None else 'unknown'
        if status == 'unknown':
            why.add('comparison_unknown')
        diffs.append(ReconciliationDifference(domain, position, code, unit, left, right, delta, tolerance, status, tuple(sorted(notes))))

    position_keys = set(ledger_h) | set(source_h) | {x.key for x in request.scope.positions}
    identities = {}
    for key in position_keys:
        identities.setdefault((key[0], key[1], key[3]), set()).add(key[2])
    for key in sorted(position_keys):
        same_mapping = len(identities[(key[0], key[1], key[3])]) == 1
        if not same_mapping:
            why.add('mapping_unknown')
        difference('holdings', PositionKey(*key), None, ledger_h.get(key), source_h.get(key),
                   mapping_known and same_mapping and covered.contains_position(key))
    cash_keys = set(ledger_c) | set(source_c) | {(a, c) for a in request.scope.components if a in ECONOMIC_CASH for c in request.scope.currencies}
    for a, c in sorted(cash_keys):
        difference(a, None, c, ledger_c.get((a, c)), source_c.get((a, c)), semantics_known and a in covered.components and c in covered.currencies)
    differences = tuple(sorted(diffs, key=lambda x: x.key))
    status = 'incomplete' if why else ('mismatch' if any(x.status == 'mismatch' for x in differences) else 'matched')
    return ReconciliationResult(1, 'synthetic', *hashes, statement, status, request.scope, covered,
        missing, tuple(sorted({x.domain for x in differences})), differences, status == 'matched',
        status == 'matched' and request.scope.coverage == 'entire_account', tuple(sorted(why)))
