"""Q24 닫힌 합성 목표 계약. 정확 유리수 계산, 불변 계획, 실행 권한 없음."""
from dataclasses import dataclass, fields
from fractions import Fraction
from types import MappingProxyType

from .ledger import choice, digest, exact, hash_record, integer
from .primitives import ContractError, currency, decimal_string, identifier, utc_instant
from .valuation import PositionKey, finite, number, quantize
from .research import Metric

MAX_INPUTS = 128
MAX_RESOLVED_BYTES = 8 * 1024 * 1024
CANONICAL = 'qh-canonical-json-v1'
FAILURES = ('environment_blocked', 'policy_missing', 'source_incomplete', 'source_semantics_unknown',
    'temporal_mismatch', 'reconciliation_incomplete', 'nav_unknown', 'mapping_unknown', 'rights_denied',
    'stale_input', 'calendar_ineligible', 'capability_unknown', 'cost_bound_unknown',
    'active_intent_conflict', 'open_orders_unknown', 'ambiguous_omission', 'lot_violation',
    'tick_violation', 'cash_shortfall', 'sellability_unknown', 'exposure_limit', 'daily_limit',
    'loss_limit', 'proposal_infeasible', 'expired', 'capacity_scope_unsupported')
KINDS = ('request', 'policy', 'facts', 'snapshot', 'projection', 'statement', 'event', 'performance',
    'strategy', 'plan', 'candidate', 'result', 'capability', 'cost', 'rights', 'catalog', 'calendar',
    'timezone', 'market', 'obligation_source')


def text(value):
    if type(value) is not str or not 1 <= len(value) <= 2048 or any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ContractError()
    return value


def enum(*values):
    def check(value):
        choice(value, values)
        return value
    return check


def count(value):
    integer(value, 0, 2147483647)
    return value


def positive_count(value):
    integer(value)
    return value


def version(value):
    integer(value, 1, 1)
    return value


def numeric(value):
    return decimal_string(value)


def nonnegative(value):
    value = numeric(value)
    if number(value) < 0:
        raise ContractError()
    return value


def positive(value):
    value = nonnegative(value)
    if number(value) <= 0:
        raise ContractError()
    return value


def ratio(value):
    value = nonnegative(value)
    if number(value) > 1:
        raise ContractError()
    return value


def hashed(value):
    digest(value)
    return value


def boolean(value):
    if type(value) is not bool:
        raise ContractError()
    return value


def optional(rule):
    return ('optional', rule)


def sequence(rule):
    return ('sequence', rule)


def _checked(rule, value):
    if type(rule) is tuple:
        if rule[0] == 'optional':
            return None if value is None else _checked(rule[1], value)
        if type(value) is not tuple or len(value) > MAX_INPUTS:
            raise ContractError()
        return tuple(_checked(rule[1], x) for x in value)
    if isinstance(rule, type):
        if type(value) is not rule:
            raise ContractError()
        return rule(**{f.name: getattr(value, f.name) for f in fields(rule)})
    return rule(value)


class Checked:
    __slots__ = ()

    def __post_init__(self):
        for f in fields(self):
            object.__setattr__(self, f.name, _checked(SPECS[type(self)][f.name], getattr(self, f.name)))
        validator = VALIDATORS.get(type(self))
        if validator:
            validator(self)


def ordered(values, key=lambda x: x):
    keys = tuple(key(x) for x in values)
    if keys != tuple(sorted(set(keys))):
        raise ContractError()


@dataclass(frozen=True, slots=True)
class TargetRef(Checked):
    kind: str
    id: str
    version: int
    canonicalization_version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class TargetScope(Checked):
    markets: tuple[str, ...]
    currencies: tuple[str, ...]
    positions: tuple[PositionKey, ...]


@dataclass(frozen=True, slots=True)
class TargetValue(Checked):
    position: PositionKey
    value: str
    limit_price: str | None


@dataclass(frozen=True, slots=True)
class CashTarget(Checked):
    currency: str
    minimum: str


@dataclass(frozen=True, slots=True)
class TargetRequest(Checked):
    schema_version: int
    environment: str
    account_ref: str
    request_id: str
    as_of: str
    knowledge_cutoff: str
    evaluated_at: str
    authority_generation: str
    expires_at: str
    mode: str
    scope: TargetScope
    omission_rule: str
    target_basis: str
    targets: tuple[TargetValue, ...]
    cash_targets: tuple[CashTarget, ...]
    snapshot_ref: TargetRef
    strategy_ref: TargetRef
    policy_ref: TargetRef | None
    research_refs: tuple[TargetRef, ...]
    predecessor_plan_ref: TargetRef | None


@dataclass(frozen=True, slots=True)
class CurrencyLimit(Checked):
    currency: str
    funding_limit: str
    cash_floor: str


@dataclass(frozen=True, slots=True)
class ExposureLimit(Checked):
    dimension: str
    key: str
    maximum_amount: str
    maximum_weight: str


@dataclass(frozen=True, slots=True)
class SyntheticTargetPolicy(Checked):
    schema_version: int
    environment: str
    policy_id: str
    account_ref: str
    valid_from: str
    valid_to: str
    synthetic_decision_ref: str
    allowed_positions: tuple[PositionKey, ...]
    allowed_markets: tuple[str, ...]
    allowed_currencies: tuple[str, ...]
    currency_limits: tuple[CurrencyLimit, ...]
    exposure_limits: tuple[ExposureLimit, ...]
    max_order_amount: str
    max_order_quantity: str
    max_daily_amount: str
    max_daily_quantity: str
    max_volume_participation: str
    max_loss_amount: str
    max_drawdown: str
    risk_window_start: str
    risk_window_end: str
    daily_window_start: str
    daily_window_end: str
    max_price_age_seconds: int
    max_fx_age_seconds: int
    max_account_age_seconds: int
    candidate_ttl_seconds: int
    max_price_deviation: str
    max_rounding_error: str


@dataclass(frozen=True, slots=True)
class SyntheticStrategyProposal(Checked):
    schema_version: int
    environment: str
    strategy_id: str
    account_ref: str
    rationale: str
    risks: tuple[str, ...]
    synthetic_notice: str


@dataclass(frozen=True, slots=True)
class CashCapacity(Checked):
    currency: str
    amount: str
    capacity_scope: str
    capacity_basis: str
    reflected_obligation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticObligationSource(Checked):
    schema_version: int
    environment: str
    source_id: str
    account_ref: str
    obligation_id: str
    currency: str
    amount: str
    kind: str
    effective_at: str
    status: str
    ledger_event_ref: TargetRef | None


@dataclass(frozen=True, slots=True)
class CashObligation(Checked):
    obligation_id: str
    source_ref: TargetRef
    currency: str
    amount: str
    kind: str
    effective_at: str
    outstanding_or_realized: str
    reflected_in_L: bool
    reflected_in_B: bool


@dataclass(frozen=True, slots=True)
class Sellability(Checked):
    position: PositionKey
    settled_quantity: str
    broker_sellable_quantity: str
    reserved_quantity: str
    unreflected_sell_quantity: str
    obligation_refs: tuple[TargetRef, ...]


@dataclass(frozen=True, slots=True)
class ActiveOrder(Checked):
    order_id: str
    position: PositionKey
    side: str
    quantity: str
    status: str
    source_snapshot_id: str


@dataclass(frozen=True, slots=True)
class Classification(Checked):
    position: PositionKey
    sector_id: str
    effective_from: str
    effective_to: str
    known_at: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class SyntheticOrderCapability(Checked):
    schema_version: int
    environment: str
    capability_id: str
    account_ref: str
    position: PositionKey
    market: str
    currency: str
    valid_from: str
    valid_to: str
    known_at: str
    catalog_ref: TargetRef
    calendar_ref: TargetRef
    order_kind: str
    time_in_force: str
    tick: str
    lot: str
    min_quantity: str
    max_quantity: str
    min_notional: str
    max_notional: str
    session_kind: str
    partial_fill_basis: str


@dataclass(frozen=True, slots=True)
class SyntheticCostRule(Checked):
    schema_version: int
    environment: str
    rule_id: str
    account_ref: str
    market: str
    currency: str
    side: str
    valid_from: str
    valid_to: str
    fee_fixed: str
    fee_per_share: str
    tax_fixed: str
    tax_per_share: str
    money_quantum: str
    rounding: str
    charging_basis: str


@dataclass(frozen=True, slots=True)
class SyntheticTargetFacts(Checked):
    schema_version: int
    environment: str
    account_ref: str
    source_id: str
    source_revision: str
    source_snapshot_id: str
    semantics_version: str
    mapping_version: str
    requested_scope: TargetScope
    covered_scope: TargetScope
    missing_scope: tuple[str, ...]
    status: str
    temporal_consistency: str
    source_as_of: str
    aligned_as_of: str
    observed_at: str
    ingested_at: str
    knowledge_cutoff: str
    ledger_cursor: int
    projection_ref: TargetRef
    statement_ref: TargetRef
    cash_capacity_rows: tuple[CashCapacity, ...]
    obligations: tuple[CashObligation, ...]
    post_source_cash_changes: tuple[TargetRef, ...]
    post_source_status: str
    sellability_rows: tuple[Sellability, ...]
    broker_open_orders: tuple[ActiveOrder, ...]
    open_orders_scope: TargetScope
    open_orders_status: str
    local_active_intents: tuple[ActiveOrder, ...]
    active_intents_scope: TargetScope
    active_intents_status: str
    classifications: tuple[Classification, ...]
    daily_usage_event_refs: tuple[TargetRef, ...]
    loss_performance_ref: TargetRef
    capabilities: tuple[SyntheticOrderCapability, ...]
    cost_rules: tuple[SyntheticCostRule, ...]


@dataclass(frozen=True, slots=True)
class TargetFailure(Checked):
    code: str
    subject_ref: TargetRef
    required_input: str
    observed_status: str


@dataclass(frozen=True, slots=True)
class TargetPosition(Checked):
    position: PositionKey
    current_quantity: str
    target_quantity: str
    difference: str
    weight_residual: str
    residual_numerator: str
    residual_denominator: str
    reference_base_price: Metric
    lot: str


@dataclass(frozen=True, slots=True)
class CashCalculation(Checked):
    currency: str
    ledger_cash: str
    outstanding: str
    floor: str
    broker_capacity: str
    unreflected: str
    post_source_debits: str
    available: str
    planned_burden: str
    remaining: str


@dataclass(frozen=True, slots=True)
class ExposureCalculation(Checked):
    dimension: str
    key: str
    current_amount: str
    minimum_amount: str
    maximum_amount: str
    nav_lower_bound: str
    maximum_limit: str
    maximum_weight: str


@dataclass(frozen=True, slots=True)
class OrderTerms(Checked):
    account_ref: str
    position: PositionKey
    mapping_ref: TargetRef
    market: str
    currency: str
    side: str
    quantity: str
    reference_price: str
    limit_price: str
    capability: SyntheticOrderCapability
    cost_rule: SyntheticCostRule
    fee_bound: str
    tax_bound: str
    cost_bound: str
    principal_bound: str
    minimum_sale_proceeds: str
    maximum_burden: str
    cumulative_burden: str
    remaining_capacity: str
    valid_from: str
    valid_to: str


@dataclass(frozen=True, slots=True)
class DisplayTerms(Checked):
    render_version: str
    locale: str
    account_label: str
    instrument_label: str
    rationale: str
    risks: tuple[str, ...]
    cost_explanation: str
    expiry_explanation: str
    synthetic_notice: str


@dataclass(frozen=True, slots=True)
class AccountCalculation(Checked):
    nav: str
    worst_cost_and_adverse: str
    nav_lower_bound: str
    daily_used_amount: str
    daily_used_quantity: str
    proposed_amount: str
    proposed_quantity: str
    daily_amount_limit: str
    daily_quantity_limit: str
    observed_loss: str
    observed_drawdown: Metric
    loss_limit: str
    drawdown_limit: str


@dataclass(frozen=True, slots=True)
class TargetPlanBody(Checked):
    schema_version: int
    environment: str
    account_ref: str
    request: TargetRequest
    input_refs: tuple[TargetRef, ...]
    positions: tuple[TargetPosition, ...]
    orders: tuple[OrderTerms, ...]
    cash_calculation: tuple[CashCalculation, ...]
    exposures: tuple[ExposureCalculation, ...]
    account_calculation: AccountCalculation | None
    status: str
    failures: tuple[TargetFailure, ...]
    policy: SyntheticTargetPolicy | None = None


@dataclass(frozen=True, slots=True)
class TargetPlan(Checked):
    plan_id: str
    body: TargetPlanBody


@dataclass(frozen=True, slots=True)
class CandidateBody(Checked):
    schema_version: int
    environment: str
    account_ref: str
    authority_generation: str
    plan_ref: TargetRef
    order_index: int
    policy_ref: TargetRef
    input_refs: tuple[TargetRef, ...]
    terms: OrderTerms
    display_terms: DisplayTerms


@dataclass(frozen=True, slots=True)
class OrderCandidate(Checked):
    candidate_id: str
    body: CandidateBody


@dataclass(frozen=True, slots=True)
class TargetResultBody(Checked):
    schema_version: int
    environment: str
    account_ref: str
    request_ref: TargetRef
    plan_ref: TargetRef
    candidate_refs: tuple[TargetRef, ...]
    outcome: str
    effect: str
    failures: tuple[TargetFailure, ...]


@dataclass(frozen=True, slots=True)
class TargetBuildResult(Checked):
    result_id: str
    body: TargetResultBody


def cost_bounds(rule, quantity):
    q = number(rule.money_quantum)
    def ceiling(value):
        units = value / q
        return finite(-(-units.numerator // units.denominator) * q)
    return (ceiling(number(rule.fee_fixed) + number(rule.fee_per_share) * number(quantity)),
            ceiling(number(rule.tax_fixed) + number(rule.tax_per_share) * number(quantity)))


def available_cash(ledger_cash, outstanding, floor, broker_capacity, unreflected, debits):
    return finite(min(number(ledger_cash) - number(outstanding) - number(floor),
                      number(broker_capacity) - number(unreflected) - number(debits)))


def weight_quantity(nav, weight, base_price, lot):
    n, w, p, l = map(number, (nav, weight, base_price, lot))
    if n <= 0 or p <= 0 or l <= 0 or not 0 <= w <= 1:
        raise ContractError()
    units = n * w / p / l
    quantity = (units.numerator // units.denominator) * l
    # 잔차 허용 비교는 반올림 전 정확한 유리수로 수행한다.
    return finite(quantity), w - quantity * p / n


def ref(kind, id, obj, *, environment=None):
    from .serialization import CanonicalPayload, canonical_hash
    env = environment or getattr(obj, 'environment', getattr(getattr(obj, 'body', None), 'environment', 'synthetic'))
    return TargetRef(kind, id, 1, CANONICAL, canonical_hash(CanonicalPayload(type(obj).__name__, 1, env, obj)))


def _ref_kind(value, kind):
    if value.kind != kind:
        raise ContractError()


def _scope(obj):
    ordered(obj.markets)
    ordered(obj.currencies)
    ordered(obj.positions, lambda x: x.key)


def _request(obj):
    _scope(obj.scope)
    ordered(obj.targets, lambda x: x.position.key)
    ordered(obj.cash_targets, lambda x: x.currency)
    ordered(obj.research_refs, lambda x: (x.kind, x.id))
    if any(x.position not in obj.scope.positions for x in obj.targets) or any(x.currency not in obj.scope.currencies for x in obj.cash_targets):
        raise ContractError()
    for value, kind in ((obj.snapshot_ref, 'snapshot'), (obj.strategy_ref, 'strategy')):
        _ref_kind(value, kind)
    if obj.policy_ref:
        _ref_kind(obj.policy_ref, 'policy')
    if obj.predecessor_plan_ref:
        _ref_kind(obj.predecessor_plan_ref, 'plan')
    if obj.as_of > obj.knowledge_cutoff or obj.knowledge_cutoff > obj.evaluated_at:
        raise ContractError()
    if obj.target_basis == 'weight' and sum((number(x.value) for x in obj.targets), Fraction()) > 1:
        raise ContractError()


def _policy(obj):
    _window(obj)
    if obj.risk_window_start >= obj.risk_window_end or obj.daily_window_start >= obj.daily_window_end:
        raise ContractError()
    for name in ('allowed_positions', 'allowed_markets', 'allowed_currencies', 'currency_limits', 'exposure_limits'):
        key = (lambda x: x.key) if name == 'allowed_positions' else ((lambda x: x.currency) if name == 'currency_limits' else
            ((lambda x: (x.dimension, x.key)) if name == 'exposure_limits' else (lambda x: x)))
        ordered(getattr(obj, name), key)
    if {x.currency for x in obj.currency_limits} != set(obj.allowed_currencies):
        raise ContractError()


def _window(obj):
    if obj.valid_from >= obj.valid_to:
        raise ContractError()


def _facts(obj):
    for name, key in (('missing_scope', lambda x: x), ('cash_capacity_rows', lambda x: x.currency),
        ('obligations', lambda x: x.obligation_id), ('sellability_rows', lambda x: x.position.key),
        ('broker_open_orders', lambda x: x.order_id), ('local_active_intents', lambda x: x.order_id),
        ('classifications', lambda x: x.position.key), ('capabilities', lambda x: x.position.key),
        ('cost_rules', lambda x: (x.market, x.currency, x.side))):
        ordered(getattr(obj, name), key)
    for refs in (obj.daily_usage_event_refs, obj.post_source_cash_changes):
        ordered(refs, lambda x: x.id)
        for r in refs:
            _ref_kind(r, 'event')
    _ref_kind(obj.projection_ref, 'projection')
    _ref_kind(obj.statement_ref, 'statement')
    _ref_kind(obj.loss_performance_ref, 'performance')
    if not obj.source_as_of <= obj.observed_at <= obj.ingested_at <= obj.knowledge_cutoff or obj.source_as_of > obj.aligned_as_of:
        raise ContractError()


def _terms(obj):
    c, r = obj.capability, obj.cost_rule
    if (c.account_ref, c.position, c.market, c.currency) != (obj.account_ref, obj.position, obj.market, obj.currency):
        raise ContractError()
    if (r.account_ref, r.market, r.currency, r.side) != (obj.account_ref, obj.market, obj.currency, obj.side):
        raise ContractError()
    q, price = number(obj.quantity), number(obj.limit_price)
    if (q % number(c.lot) or price % number(c.tick) or not number(c.min_quantity) <= q <= number(c.max_quantity)
            or not number(c.min_notional) <= q * price <= number(c.max_notional)):
        raise ContractError()
    fees, taxes = cost_bounds(r, obj.quantity)
    total = number(fees) + number(taxes)
    principal = q * price if obj.side == 'buy' else Fraction()
    proceeds = q * price if obj.side == 'sell' else Fraction()
    if (obj.fee_bound, obj.tax_bound, obj.cost_bound, obj.principal_bound, obj.minimum_sale_proceeds, obj.maximum_burden) != (
            fees, taxes, finite(total), finite(principal), finite(proceeds), finite(principal + total)):
        raise ContractError()
    _window(obj)
    if not max(c.valid_from, r.valid_from) <= obj.valid_from < obj.valid_to <= min(c.valid_to, r.valid_to):
        raise ContractError()
    _ref_kind(obj.mapping_ref, 'catalog')


def _cash(obj):
    if obj.available != available_cash(obj.ledger_cash, obj.outstanding, obj.floor, obj.broker_capacity,
            obj.unreflected, obj.post_source_debits) or obj.remaining != finite(number(obj.available) - number(obj.planned_burden)):
        raise ContractError()


def _position(obj):
    if obj.reference_base_price.value is None or obj.reference_base_price.exact_value <= 0:
        raise ContractError()
    try:
        n, d = int(obj.residual_numerator), int(obj.residual_denominator)
    except ValueError:
        raise ContractError() from None
    if n < 0 or d <= 0 or str(n) != obj.residual_numerator or str(d) != obj.residual_denominator or obj.weight_residual != quantize(Fraction(n, d), '0.000000000000000001'):
        raise ContractError()
    if obj.difference != finite(number(obj.target_quantity) - number(obj.current_quantity)):
        raise ContractError()


def _plan_body(obj):
    req = obj.request
    if (obj.account_ref, obj.environment) != (req.account_ref, req.environment):
        raise ContractError()
    ordered(obj.input_refs, lambda x: (x.kind, x.id))
    ordered(obj.positions, lambda x: x.position.key)
    ordered(obj.orders, lambda x: (x.position.instrument_id, x.position.venue_id, x.side))
    ordered(obj.cash_calculation, lambda x: x.currency)
    ordered(obj.exposures, lambda x: (x.dimension, x.key))
    if (obj.status == 'blocked') != bool(obj.failures) or (obj.status == 'blocked' and obj.orders):
        raise ContractError()
    if obj.status == 'eligible':
        if (obj.account_calculation is None or obj.environment != 'synthetic' or
                (req.mode, req.omission_rule) not in (('full', 'zero'), ('partial', 'keep')) or req.evaluated_at >= req.expires_at):
            raise ContractError()
        policy = obj.policy
        if (policy is None or req.policy_ref != ref('policy', policy.policy_id, policy)
                or policy.account_ref != req.account_ref or policy.environment != req.environment
                or not policy.valid_from <= req.evaluated_at < policy.valid_to):
            raise ContractError()
        explicit = {x.position: x for x in req.targets}
        if not set(req.scope.positions) <= {x.position for x in obj.positions}:
            raise ContractError()
        for position in obj.positions:
            target = explicit.get(position.position)
            residual = Fraction()
            if target is not None:
                if req.target_basis == 'quantity':
                    desired = number(target.value)
                    if desired % number(position.lot):
                        raise ContractError()
                else:
                    units = number(obj.account_calculation.nav) * number(target.value) / position.reference_base_price.exact_value / number(position.lot)
                    desired = (units.numerator // units.denominator) * number(position.lot)
                    residual = number(target.value) - desired * position.reference_base_price.exact_value / number(obj.account_calculation.nav)
            else:
                desired = Fraction() if req.mode == 'full' and position.position in req.scope.positions else number(position.current_quantity)
            if position.target_quantity != finite(desired) or residual != Fraction(int(position.residual_numerator), int(position.residual_denominator)):
                raise ContractError()
        cash = {x.currency: x for x in obj.cash_calculation}
        floors = {x.currency: number(x.cash_floor) for x in policy.currency_limits}
        if set(cash) != set(floors) or any(x.currency not in cash for x in req.cash_targets):
            raise ContractError()
        for target in req.cash_targets:
            floors[target.currency] = max(floors[target.currency], number(target.minimum))
        if any(number(row.floor) != floors[code] for code, row in cash.items()):
            raise ContractError()
        totals = {c: Fraction() for c in cash}
        positions = {x.position: x for x in obj.positions}
        for order in obj.orders:
            p = positions.get(order.position)
            if p is None or p.lot != order.capability.lot or abs(number(p.difference)) != number(order.quantity) or (number(p.difference) > 0) != (order.side == 'buy'):
                raise ContractError()
            if order.currency not in cash:
                raise ContractError()
            target = explicit.get(order.position)
            if target is not None and target.limit_price is not None:
                limit = number(target.limit_price)
                if ((order.side == 'buy' and number(order.limit_price) > limit)
                        or (order.side == 'sell' and number(order.limit_price) < limit)):
                    raise ContractError()
            totals[order.currency] += number(order.maximum_burden)
            if (order.cumulative_burden, order.remaining_capacity) != (finite(totals[order.currency]),
                    finite(number(cash[order.currency].available) - totals[order.currency])):
                raise ContractError()
        proposed = Fraction()
        adverse = Fraction()
        for order in obj.orders:
            position = positions[order.position]
            fx = position.reference_base_price.exact_value / number(order.reference_price)
            proposed += (number(order.quantity) * number(order.limit_price) + number(order.cost_bound)) * fx
            adverse += (number(order.cost_bound) + number(order.quantity) * max(Fraction(),
                number(order.limit_price) - number(order.reference_price) if order.side == 'buy' else
                number(order.reference_price) - number(order.limit_price))) * fx
            if not order.valid_from <= req.evaluated_at < order.valid_to <= req.expires_at:
                raise ContractError()
        calculation = obj.account_calculation
        if (calculation.proposed_quantity != finite(sum((number(o.quantity) for o in obj.orders), Fraction()))
                or number(calculation.proposed_amount) < proposed or number(calculation.worst_cost_and_adverse) < adverse
                or any(e.nav_lower_bound != calculation.nav_lower_bound for e in obj.exposures)):
            raise ContractError()
        if {x.position for x in obj.orders} != {x.position for x in obj.positions if number(x.difference)}:
            raise ContractError()
        if any(x.planned_burden != finite(totals[x.currency]) or number(x.remaining) < 0 for x in obj.cash_calculation):
            raise ContractError()
        if any(number(x.nav_lower_bound) <= 0 or number(x.maximum_amount) > number(x.maximum_limit)
               or number(x.maximum_amount) > number(x.maximum_weight) * number(x.nav_lower_bound) for x in obj.exposures):
            raise ContractError()


def _account_calculation(obj):
    if obj.nav_lower_bound != finite(number(obj.nav) - number(obj.worst_cost_and_adverse)) or number(obj.nav_lower_bound) <= 0:
        raise ContractError()
    if (number(obj.daily_used_amount) + number(obj.proposed_amount) > number(obj.daily_amount_limit)
            or number(obj.daily_used_quantity) + number(obj.proposed_quantity) > number(obj.daily_quantity_limit)
            or number(obj.observed_loss) > number(obj.loss_limit) or (obj.observed_drawdown.value is None or obj.observed_drawdown.exact_value > number(obj.drawdown_limit))):
        raise ContractError()


def _candidate(obj):
    _ref_kind(obj.plan_ref, 'plan')
    _ref_kind(obj.policy_ref, 'policy')
    ordered(obj.input_refs, lambda x: (x.kind, x.id))
    if obj.account_ref != obj.terms.account_ref or obj.environment != 'synthetic':
        raise ContractError()


def _result(obj):
    _ref_kind(obj.request_ref, 'request')
    _ref_kind(obj.plan_ref, 'plan')
    for r in obj.candidate_refs:
        _ref_kind(r, 'candidate')
    if len({x.id for x in obj.candidate_refs}) != len(obj.candidate_refs):
        raise ContractError()
    if obj.outcome == 'blocked':
        if obj.effect != 'none' or obj.candidate_refs or not obj.failures:
            raise ContractError()
    elif obj.failures or obj.effect != ('orders' if obj.candidate_refs else 'no_change'):
        raise ContractError()


def _identity(obj, name, prefix):
    if getattr(obj, name) != prefix + ref('plan', 'identity', obj.body).sha256:
        raise ContractError()


# 닫힌 필드 표: 직렬화 복원도 이 표의 중첩 타입만 소비한다.
SPECS = {}
def spec(cls, **rules):
    if {f.name for f in fields(cls)} != rules.keys():
        raise RuntimeError('Target schema mismatch')
    SPECS[cls] = rules


S = sequence
O = optional
H = dict(schema_version=version, environment=enum('synthetic'))
A = dict(account_ref=identifier)
W = dict(valid_from=utc_instant, valid_to=utc_instant)
spec(TargetRef, kind=enum(*KINDS), id=identifier, version=version, canonicalization_version=enum(CANONICAL, 'context-source-facts-v1'), sha256=hashed)
spec(TargetScope, markets=S(enum('KR', 'US')), currencies=S(currency), positions=S(PositionKey))
spec(TargetValue, position=PositionKey, value=nonnegative, limit_price=O(positive))
spec(CashTarget, currency=currency, minimum=nonnegative)
spec(TargetRequest, schema_version=version, environment=enum('synthetic', 'paper', 'live'), **A,
    request_id=identifier, as_of=utc_instant, knowledge_cutoff=utc_instant, evaluated_at=utc_instant,
    authority_generation=identifier, expires_at=utc_instant, mode=enum('full', 'partial'), scope=TargetScope,
    omission_rule=enum('zero', 'keep', 'unspecified'), target_basis=enum('quantity', 'weight'),
    targets=S(TargetValue), cash_targets=S(CashTarget), snapshot_ref=TargetRef, strategy_ref=TargetRef,
    policy_ref=O(TargetRef), research_refs=S(TargetRef), predecessor_plan_ref=O(TargetRef))
spec(CurrencyLimit, currency=currency, funding_limit=nonnegative, cash_floor=nonnegative)
spec(ExposureLimit, dimension=enum('instrument', 'sector', 'market', 'currency'), key=identifier,
    maximum_amount=nonnegative, maximum_weight=ratio)
spec(SyntheticTargetPolicy, **H, **A, **W, policy_id=identifier, synthetic_decision_ref=identifier,
    allowed_positions=S(PositionKey), allowed_markets=S(enum('KR', 'US')), allowed_currencies=S(currency),
    currency_limits=S(CurrencyLimit), exposure_limits=S(ExposureLimit), max_order_amount=nonnegative,
    max_order_quantity=nonnegative, max_daily_amount=nonnegative, max_daily_quantity=nonnegative,
    max_volume_participation=ratio, max_loss_amount=nonnegative, max_drawdown=ratio,
    risk_window_start=utc_instant, risk_window_end=utc_instant, daily_window_start=utc_instant,
    daily_window_end=utc_instant, max_price_age_seconds=positive_count, max_fx_age_seconds=positive_count,
    max_account_age_seconds=positive_count, candidate_ttl_seconds=positive_count,
    max_price_deviation=ratio, max_rounding_error=ratio)
spec(SyntheticStrategyProposal, **H, **A, strategy_id=identifier, rationale=text, risks=S(text), synthetic_notice=text)
spec(CashCapacity, currency=currency, amount=nonnegative,
    capacity_scope=enum('account_currency', 'instrument', 'unknown'), capacity_basis=enum('cash_only_no_auto_fx', 'unknown'),
    reflected_obligation_ids=S(identifier))
spec(SyntheticObligationSource, **H, **A, source_id=identifier, obligation_id=identifier,
    currency=currency, amount=positive, kind=enum('buy_commitment', 'cash_debit'), effective_at=utc_instant,
    status=enum('outstanding', 'realized', 'unknown'), ledger_event_ref=O(TargetRef))
spec(CashObligation, obligation_id=identifier, source_ref=TargetRef, currency=currency, amount=positive,
    kind=enum('buy_commitment', 'cash_debit'), effective_at=utc_instant,
    outstanding_or_realized=enum('outstanding', 'realized', 'unknown'), reflected_in_L=boolean, reflected_in_B=boolean)
spec(Sellability, position=PositionKey, settled_quantity=nonnegative, broker_sellable_quantity=nonnegative,
    reserved_quantity=nonnegative, unreflected_sell_quantity=nonnegative, obligation_refs=S(TargetRef))
spec(ActiveOrder, order_id=identifier, position=PositionKey, side=enum('buy', 'sell'), quantity=positive,
    status=enum('active', 'unknown'), source_snapshot_id=identifier)
spec(Classification, position=PositionKey, sector_id=identifier, effective_from=utc_instant,
    effective_to=utc_instant, known_at=utc_instant, source_ref=identifier)
spec(SyntheticOrderCapability, **H, **A, **W, capability_id=identifier, position=PositionKey,
    market=enum('KR', 'US'), currency=currency, known_at=utc_instant, catalog_ref=TargetRef,
    calendar_ref=TargetRef, order_kind=enum('limit'), time_in_force=enum('day'), tick=positive,
    lot=positive, min_quantity=positive, max_quantity=positive, min_notional=nonnegative,
    max_notional=positive, session_kind=enum('regular'), partial_fill_basis=enum('whole_order_aggregate'))
spec(SyntheticCostRule, **H, **A, **W, rule_id=identifier, market=enum('KR', 'US'), currency=currency,
    side=enum('buy', 'sell'), fee_fixed=nonnegative, fee_per_share=nonnegative, tax_fixed=nonnegative,
    tax_per_share=nonnegative, money_quantum=positive, rounding=enum('ceiling'), charging_basis=enum('whole_order_aggregate'))
spec(SyntheticTargetFacts, **H, **A, source_id=identifier, source_revision=identifier,
    source_snapshot_id=identifier, semantics_version=enum('synthetic-cash-capacity-v1', 'unknown'),
    mapping_version=identifier, requested_scope=TargetScope, covered_scope=TargetScope, missing_scope=S(identifier),
    status=enum('complete', 'partial', 'unknown'), temporal_consistency=enum('aligned', 'unknown'),
    source_as_of=utc_instant, aligned_as_of=utc_instant, observed_at=utc_instant, ingested_at=utc_instant,
    knowledge_cutoff=utc_instant, ledger_cursor=count, projection_ref=TargetRef, statement_ref=TargetRef,
    cash_capacity_rows=S(CashCapacity), obligations=S(CashObligation), post_source_cash_changes=S(TargetRef),
    post_source_status=enum('complete', 'unknown'), sellability_rows=S(Sellability), broker_open_orders=S(ActiveOrder),
    open_orders_scope=TargetScope, open_orders_status=enum('complete', 'partial', 'unknown'),
    local_active_intents=S(ActiveOrder), active_intents_scope=TargetScope,
    active_intents_status=enum('complete', 'partial', 'unknown'), classifications=S(Classification),
    daily_usage_event_refs=S(TargetRef), loss_performance_ref=TargetRef, capabilities=S(SyntheticOrderCapability), cost_rules=S(SyntheticCostRule))
spec(TargetFailure, code=enum(*FAILURES), subject_ref=TargetRef, required_input=identifier, observed_status=identifier)
spec(TargetPosition, position=PositionKey, current_quantity=nonnegative, target_quantity=nonnegative,
    difference=numeric, weight_residual=nonnegative, residual_numerator=text, residual_denominator=text, reference_base_price=Metric, lot=positive)
spec(CashCalculation, currency=currency, ledger_cash=numeric, outstanding=nonnegative, floor=nonnegative,
    broker_capacity=nonnegative, unreflected=nonnegative, post_source_debits=nonnegative,
    available=numeric, planned_burden=nonnegative, remaining=numeric)
spec(ExposureCalculation, dimension=enum('instrument', 'sector', 'market', 'currency'), key=identifier,
    current_amount=nonnegative, minimum_amount=nonnegative, maximum_amount=nonnegative,
    nav_lower_bound=numeric, maximum_limit=nonnegative, maximum_weight=ratio)
spec(OrderTerms, **A, **W, position=PositionKey, mapping_ref=TargetRef, market=enum('KR', 'US'), currency=currency,
    side=enum('buy', 'sell'), quantity=positive, reference_price=positive, limit_price=positive,
    capability=SyntheticOrderCapability, cost_rule=SyntheticCostRule, fee_bound=nonnegative, tax_bound=nonnegative,
    cost_bound=nonnegative, principal_bound=nonnegative, minimum_sale_proceeds=nonnegative,
    maximum_burden=nonnegative, cumulative_burden=nonnegative, remaining_capacity=numeric)
spec(DisplayTerms, render_version=enum('target-ko-v1'), locale=enum('ko-KR'), account_label=text,
    instrument_label=text, rationale=text, risks=S(text), cost_explanation=text, expiry_explanation=text, synthetic_notice=text)
spec(AccountCalculation, nav=positive, worst_cost_and_adverse=nonnegative, nav_lower_bound=positive,
    daily_used_amount=nonnegative, daily_used_quantity=nonnegative, proposed_amount=nonnegative,
    proposed_quantity=nonnegative, daily_amount_limit=nonnegative, daily_quantity_limit=nonnegative,
    observed_loss=nonnegative, observed_drawdown=Metric, loss_limit=nonnegative, drawdown_limit=ratio)
spec(TargetPlanBody, schema_version=version, environment=enum('synthetic', 'paper', 'live'), **A,
    request=TargetRequest, input_refs=S(TargetRef), positions=S(TargetPosition), orders=S(OrderTerms),
    cash_calculation=S(CashCalculation), exposures=S(ExposureCalculation), account_calculation=O(AccountCalculation), status=enum('eligible', 'blocked'), failures=S(TargetFailure), policy=O(SyntheticTargetPolicy))
spec(TargetPlan, plan_id=identifier, body=TargetPlanBody)
spec(CandidateBody, **H, **A, authority_generation=identifier, plan_ref=TargetRef, order_index=count,
    policy_ref=TargetRef, input_refs=S(TargetRef), terms=OrderTerms, display_terms=DisplayTerms)
spec(OrderCandidate, candidate_id=identifier, body=CandidateBody)
spec(TargetResultBody, schema_version=version, environment=enum('synthetic', 'paper', 'live'), **A,
    request_ref=TargetRef, plan_ref=TargetRef, candidate_refs=S(TargetRef), outcome=enum('eligible', 'blocked'),
    effect=enum('orders', 'no_change', 'none'), failures=S(TargetFailure))
spec(TargetBuildResult, result_id=identifier, body=TargetResultBody)
VALIDATORS = {TargetScope: _scope, TargetRequest: _request, SyntheticTargetPolicy: _policy,
    CashCapacity: lambda x: ordered(x.reflected_obligation_ids), SyntheticTargetFacts: _facts,
    SyntheticOrderCapability: _window, SyntheticCostRule: _window, TargetPosition: _position,
    CashCalculation: _cash, AccountCalculation: _account_calculation, OrderTerms: _terms, TargetPlanBody: _plan_body, CandidateBody: _candidate,
    TargetResultBody: _result, TargetPlan: lambda x: _identity(x, 'plan_id', 'target-plan:'),
    OrderCandidate: lambda x: _identity(x, 'candidate_id', 'candidate:'),
    TargetBuildResult: lambda x: _identity(x, 'result_id', 'target-result:')}


def _nested(rule):
    if type(rule) is tuple:
        inner = rule[1]
        if isinstance(inner, type):
            return (inner, None) if rule[0] == 'optional' else (inner,)
        if rule[0] == 'sequence':
            return (str,)
    elif isinstance(rule, type):
        return rule
    return None


NESTED = {cls: {name: _nested(rule) for name, rule in rules.items() if _nested(rule) is not None}
          for cls, rules in SPECS.items()}

SPECS = MappingProxyType({cls: MappingProxyType(rules) for cls, rules in SPECS.items()})
VALIDATORS = MappingProxyType(VALIDATORS)
NESTED = MappingProxyType({cls: MappingProxyType(rules) for cls, rules in NESTED.items()})
