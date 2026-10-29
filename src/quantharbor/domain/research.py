"""Q23 닫힌 합성 계약과 정확 산식. hash는 원천 진위의 보증이 아니다."""
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction

from .primitives import ContractError, currency, decimal_string, identifier
from .ledger import account, boolean, choice, digest, exact, hash_record, instant, integer, items
from .valuation import PositionKey, finite, number, quantize, reasons

RAW_SPEC_SHA256 = 'b24ec83a0cbbe1646fee64c2d433cf8d2c57831f58c8e2e746c0e9c371dc4bb4'
RATIO_QUANTUM = '0.000000000001'
STRATEGIES = ('cash', 'buy_hold', 'equal_weight_rebalance')
MAX_INPUTS = 128
MAX_RESOLVED_BYTES = 8388608


def header(obj):
    integer(obj.schema_version, 1, 1)
    choice(obj.environment, ('synthetic',))


def normalized(obj, *names):
    for name in names:
        object.__setattr__(obj, name, decimal_string(getattr(obj, name)))


def unique(values, cls, key=lambda x: x):
    items(values, cls, MAX_INPUTS)
    keys = tuple(key(x) for x in values)
    if len(set(keys)) != len(keys):
        raise ContractError()


@dataclass(frozen=True, slots=True)
class PointIndex:
    index: int

    def __post_init__(self):
        integer(self.index, 1, 12)


@dataclass(frozen=True, slots=True)
class FoldSpec:
    fold_id: str
    train: tuple[PointIndex, ...]
    validation: tuple[PointIndex, ...]
    oos: tuple[PointIndex, ...]

    def __post_init__(self):
        identifier(self.fold_id)
        previous = 0
        for group in (self.train, self.validation, self.oos):
            if type(group) is not tuple or not 1 <= len(group) <= 12:
                raise ContractError()
            for value in group:
                exact(value, PointIndex)
                integer(value.index, previous + 1, 12)
                previous = value.index


    @property
    def oos_indices(self):
        return tuple(x.index for x in self.oos)


@dataclass(frozen=True, slots=True)
class ResearchMarket:
    market_id: str
    currency: str
    timezone: str
    initial_cash: str
    tick: str
    money_quantum: str
    minimum_notional: str
    equity_price_multiplier: str
    etf_price_multiplier: str

    def __post_init__(self):
        choice(self.market_id, ('KR', 'US'))
        currency(self.currency)
        if (self.currency, self.timezone) != (('KRW', 'Asia/Seoul') if self.market_id == 'KR'
                                             else ('USD', 'America/New_York')):
            raise ContractError()
        for name in ('initial_cash', 'tick', 'money_quantum', 'minimum_notional',
                     'equity_price_multiplier', 'etf_price_multiplier'):
            normalized(self, name)
            if number(getattr(self, name)) <= 0:
                raise ContractError()


@dataclass(frozen=True, slots=True)
class PointTime:
    bar_start: str
    bar_end: str
    published_at: str
    observed_at: str
    ingested_at: str
    knowledge_cutoff: str

    def __post_init__(self):
        values = []
        for name in ('bar_start', 'bar_end', 'published_at', 'observed_at', 'ingested_at', 'knowledge_cutoff'):
            value = instant(getattr(self, name))
            object.__setattr__(self, name, value)
            values.append(value)
        if any(a >= b for a, b in zip(values, values[1:])):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class ResearchPoint:
    index: int
    KR: PointTime
    US: PointTime

    def __post_init__(self):
        integer(self.index, 1, 12)
        exact(self.KR, PointTime)
        exact(self.US, PointTime)


@dataclass(frozen=True, slots=True)
class CostScenario:
    scenario_id: str
    fee_rate_buy: str
    fee_rate_sell: str
    tax_rate_buy: str
    tax_rate_sell: str
    slippage_rate: str
    fx_spread_rate: str
    fx_explicit_fee: str

    def __post_init__(self):
        choice(self.scenario_id, ('explicit_costs', 'zero_cost_control'))
        for name in ('fee_rate_buy', 'fee_rate_sell', 'tax_rate_buy', 'tax_rate_sell',
                     'slippage_rate', 'fx_spread_rate', 'fx_explicit_fee'):
            normalized(self, name)
            if not 0 <= number(getattr(self, name)) < 1:
                raise ContractError()
        if self.fx_spread_rate != '0' or self.fx_explicit_fee != '0':
            raise ContractError()


@dataclass(frozen=True, slots=True)
class ComparisonSpec:
    schema_version: int
    environment: str
    spec_id: str
    source_sha256: str
    run_at: str
    markets: tuple[ResearchMarket, ...]
    folds: tuple[FoldSpec, ...]
    points: tuple[ResearchPoint, ...]
    costs: tuple[CostScenario, ...]
    equity_closes: tuple[str, ...]
    etf_closes: tuple[str, ...]
    fit: str = 'none'
    policy_version: str = 'comparison-spec-v1'

    def __post_init__(self):
        header(self)
        if (self.spec_id, self.source_sha256, self.fit, self.policy_version) != (
                'synthetic-comparison-v1', RAW_SPEC_SHA256, 'none', 'comparison-spec-v1'):
            raise ContractError()
        object.__setattr__(self, 'run_at', instant(self.run_at))
        for values, cls, key, length in ((self.markets, ResearchMarket, lambda x: x.market_id, 2),
                (self.folds, FoldSpec, lambda x: x.fold_id, 2),
                (self.points, ResearchPoint, lambda x: x.index, 12),
                (self.costs, CostScenario, lambda x: x.scenario_id, 2)):
            unique(values, cls, key)
            if len(values) != length:
                raise ContractError()
        for values in (self.equity_closes, self.etf_closes):
            if type(values) is not tuple or len(values) != 12 or any(number(x) <= 0 for x in values):
                raise ContractError()
        if tuple(p.index for p in self.points) != tuple(range(1, 13)):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class InputRef:
    kind: str
    ref: str
    sha256: str

    def __post_init__(self):
        choice(self.kind, ('spec', 'registry', 'fingerprint', 'snapshot', 'event', 'market', 'trace', 'cost', 'benchmark'))
        identifier(self.ref)
        digest(self.sha256)


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    path: str
    sha256: str

    def __post_init__(self):
        # 실제 허용 목록과 파일 읽기는 adapter에서만 수행한다.
        if type(self.path) is not str or len(self.path) > 160 or not self.path.startswith(('src/quantharbor/', 'config/', 'pyproject.')):
            raise ContractError()
        digest(self.sha256)


@dataclass(frozen=True, slots=True)
class ImplementationFingerprint:
    schema_version: int
    environment: str
    files: tuple[FileFingerprint, ...]
    python_version: str

    def __post_init__(self):
        header(self)
        if type(self.python_version) is not str or not self.python_version.startswith("3.13.") or not self.python_version[5:].isdigit():
            raise ContractError()
        unique(self.files, FileFingerprint, lambda x: x.path)
        if not self.files or tuple(x.path for x in self.files) != tuple(sorted(x.path for x in self.files)):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class ExperimentRegistry:
    schema_version: int
    environment: str
    spec_hash: str
    declared_at: str
    exploration_ref: str
    strategies: tuple[str, ...] = STRATEGIES
    fit: str = 'none'
    actions: str = 'explicit_none'

    def __post_init__(self):
        header(self)
        digest(self.spec_hash)
        object.__setattr__(self, 'declared_at', instant(self.declared_at))
        if (self.strategies, self.fit, self.exploration_ref) != (STRATEGIES, 'none', 'PG02:RESEARCH-DEC-001:fit-none'):
            raise ContractError()
        choice(self.actions, ('explicit_none', 'unknown'))


@dataclass(frozen=True, slots=True)
class Metric:
    value: str | None
    reason_codes: tuple[str, ...] = ()
    numerator: str | None = None
    denominator: str | None = None

    def __post_init__(self):
        reasons(self.reason_codes)
        if self.value is not None:
            normalized(self, 'value')
        if (self.value is None) != bool(self.reason_codes):
            raise ContractError()
        if (self.numerator is None) != (self.denominator is None):
            raise ContractError()
        if self.numerator is not None:
            for text in (self.numerator, self.denominator):
                if type(text) is not str or len(text) > 512:
                    raise ContractError()
                try:
                    if str(int(text)) != text:
                        raise ContractError()
                except ValueError:
                    raise ContractError() from None
            if self.value is None or int(self.denominator) <= 0:
                raise ContractError()
            v = Fraction(int(self.numerator), int(self.denominator))
            if self.value not in (quantize(v, RATIO_QUANTUM), quantize(v, '0.000000000000000001')):
                raise ContractError()

    @property
    def exact_value(self):
        return (number(self.value) if self.numerator is None else
                Fraction(int(self.numerator), int(self.denominator)))


def known(value, *, ratio=True):
    value = Fraction(value)
    display = quantize(value, RATIO_QUANTUM if ratio else '0.000000000000000001')
    return Metric(display, (), str(value.numerator), str(value.denominator))


def unknown(reason):
    return Metric(None, (reason,))


@dataclass(frozen=True, slots=True)
class NavPoint:
    snapshot: InputRef
    as_of: str
    knowledge_cutoff: str
    ledger_cursor: int
    nav: str | None
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        exact(self.snapshot, InputRef)
        if self.snapshot.kind != 'snapshot':
            raise ContractError()
        for name in ('as_of', 'knowledge_cutoff'):
            object.__setattr__(self, name, instant(getattr(self, name)))
        if self.as_of > self.knowledge_cutoff:
            raise ContractError()
        integer(self.ledger_cursor, 0)
        reasons(self.reason_codes)
        if self.nav is not None:
            normalized(self, 'nav')
        if (self.nav is None) != bool(self.reason_codes):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class FlowBoundary:
    before: NavPoint
    after: NavPoint
    amount: str
    currency: str
    quantum: str
    events: tuple[InputRef, ...]

    def __post_init__(self):
        exact(self.before, NavPoint)
        exact(self.after, NavPoint)
        normalized(self, 'amount', 'quantum')
        currency(self.currency)
        unique(self.events, InputRef, lambda x: x.ref)
        a, b = self.before, self.after
        if (a.as_of, a.knowledge_cutoff) != (b.as_of, b.knowledge_cutoff) or not a.ledger_cursor < b.ledger_cursor:
            raise ContractError()
        if not self.events or any(x.kind != 'event' for x in self.events) or number(self.quantum) <= 0 or number(self.amount) % number(self.quantum):
            raise ContractError()
        if a.nav is not None and b.nav is not None and number(b.nav) != number(a.nav) + number(self.amount):
            raise ContractError()


def performance_math(points, flows, traded, benchmark):
    """정확값을 끝까지 보존. 관측된 부지수와 시간가중 NAV만 산출한다."""
    unique(points, NavPoint, lambda x: x.snapshot.ref)
    unique(flows, FlowBoundary, lambda x: x.before.as_of)
    exact(traded, Metric)
    exact(benchmark, Metric)
    if len(points) < 2 or any(a.as_of >= b.as_of for a, b in zip(points, points[1:])):
        raise ContractError()
    start, end = points[0].as_of, points[-1].as_of
    if any(not start < f.before.as_of <= end for f in flows):
        raise ContractError()
    flow_by_time = {f.before.as_of: f for f in flows}
    timeline = {p.as_of: p for p in points}
    for f in flows:
        if f.before.as_of in timeline and timeline[f.before.as_of] != f.after:
            raise ContractError()
        timeline[f.before.as_of] = f.after
    timeline = tuple(timeline[x] for x in sorted(timeline))
    all_points = (*timeline, *(f.before for f in flows))
    missing = any(p.nav is None for p in all_points)
    if missing:
        twr = pnl = mdd = average = unknown('nav_incomplete')
    else:
        pnl = known(number(points[-1].nav) - number(points[0].nav) - sum((number(f.amount) for f in flows), Fraction()), ratio=False)
        prior = number(timeline[0].nav)
        wealth = peak = Fraction(1)
        drawdown = Fraction()
        invalid = prior <= 0
        negative = prior < 0
        total = seconds = Fraction()
        for a, b in zip(timeline, timeline[1:]):
            delta = (datetime.fromisoformat(b.as_of) - datetime.fromisoformat(a.as_of))
            dt = Fraction(delta.days * 86400 + delta.seconds) + Fraction(delta.microseconds, 1000000)
            total += number(a.nav) * dt
            seconds += dt
            f = flow_by_time.get(b.as_of)
            value = number(f.before.nav if f else b.nav)
            if prior <= 0:
                invalid = True
            elif not invalid:
                wealth *= value / prior
                peak = max(peak, wealth)
                drawdown = max(drawdown, 1 - wealth / peak)
            negative |= value < 0 or number(b.nav) < 0
            prior = number(b.nav)
        twr = unknown('nonpositive_nav_denominator') if invalid else known(wealth - 1)
        mdd = (known(drawdown) if not negative and (not invalid or drawdown == 1) else
               unknown('negative_nav' if negative else 'nonpositive_nav_denominator'))
        average = known(total / seconds, ratio=False) if total / seconds > 0 else unknown('nonpositive_average_nav')
    if traded.value is None:
        gross = half = unknown('trade_base_fx_unknown')
    elif average.value is None:
        gross = half = unknown(average.reason_codes[0])
    else:
        gross = known(traded.exact_value / average.exact_value)
        half = known(traded.exact_value / (2 * average.exact_value))
    if twr.value is None or benchmark.value is None:
        excess = relative = unknown('benchmark_or_return_unknown')
    else:
        excess = known(twr.exact_value - benchmark.exact_value)
        relative = (known((1 + twr.exact_value) / (1 + benchmark.exact_value) - 1)
                    if 1 + benchmark.exact_value > 0 else unknown('nonpositive_benchmark_wealth'))
    return twr, pnl, mdd, average, gross, half, excess, relative


@dataclass(frozen=True, slots=True)
class PerformanceResult:
    schema_version: int
    environment: str
    points: tuple[NavPoint, ...]
    flows: tuple[FlowBoundary, ...]
    traded_notional: Metric
    benchmark_return: Metric
    twr: Metric
    amount_pnl: Metric
    observed_mdd: Metric
    time_weighted_nav: Metric
    gross_turnover: Metric
    half_turnover: Metric
    benchmark_excess: Metric
    benchmark_relative_wealth: Metric

    def __post_init__(self):
        header(self)
        calculated = performance_math(self.points, self.flows, self.traded_notional, self.benchmark_return)
        actual = (self.twr, self.amount_pnl, self.observed_mdd, self.time_weighted_nav, self.gross_turnover,
                  self.half_turnover, self.benchmark_excess, self.benchmark_relative_wealth)
        for x in actual:
            exact(x, Metric)
        if actual != calculated:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class CostAllocation:
    event: InputRef
    revision: int
    kind: str
    amount: str
    rate: str

    def __post_init__(self):
        exact(self.event, InputRef)
        if self.event.kind != 'event':
            raise ContractError()
        integer(self.revision)
        choice(self.kind, ('fee', 'tax'))
        normalized(self, 'amount', 'rate')
        if number(self.amount) <= 0 or not 0 < number(self.rate) < 1:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class TradeCostFact:
    schema_version: int
    environment: str
    account_ref: str
    trade: InputRef
    revision: int
    position: PositionKey
    currency: str
    effective_at: str
    side: str
    quantity: str
    reference_price: str
    fill_price: str
    quantum: str
    allocations: tuple[CostAllocation, ...]
    base_notional: Metric

    def __post_init__(self):
        header(self)
        account(self.account_ref)
        exact(self.trade, InputRef)
        if self.trade.kind != 'event':
            raise ContractError()
        integer(self.revision)
        exact(self.position, PositionKey)
        currency(self.currency)
        object.__setattr__(self, 'effective_at', instant(self.effective_at))
        choice(self.side, ('buy', 'sell'))
        normalized(self, 'quantity', 'reference_price', 'fill_price', 'quantum')
        if any(number(x) <= 0 for x in (self.quantity, self.reference_price, self.fill_price, self.quantum)):
            raise ContractError()
        unique(self.allocations, CostAllocation, lambda x: x.event.ref)
        if len({a.kind for a in self.allocations}) != len(self.allocations):
            raise ContractError()
        for a in self.allocations:
            if a.amount != quantize(self.notional * number(a.rate), self.quantum):
                raise ContractError()
        exact(self.base_notional, Metric)
        if self.base_notional.value is not None and number(self.base_notional.value) < 0:
            raise ContractError()

    @property
    def notional(self):
        return number(self.quantity) * number(self.fill_price)

    @property
    def cost(self):
        return sum((number(a.amount) for a in self.allocations), Fraction())

    @property
    def slippage(self):
        return number(self.quantity) * (number(self.fill_price) - number(self.reference_price)) * (1 if self.side == 'buy' else -1)


def basis_math(facts, opening_quantity, closing_value, quantum, supported):
    exact(closing_value, Metric)
    boolean(supported)
    if number(opening_quantity) != 0 or not supported:
        value = unknown('initial_basis_or_actions_or_corrections_unsupported')
        return value, value, value, value
    q = basis = realized = Fraction()
    for f in facts:
        qty = number(f.quantity)
        if f.side == 'buy':
            q += qty
            basis += f.notional + f.cost
        else:
            if qty > q:
                raise ContractError()
            removed = basis if qty == q else number(quantize(basis * qty / q, quantum))
            q -= qty
            basis -= removed
            realized += f.notional - f.cost - removed
    unrealized = unknown('native_valuation_unknown') if closing_value.value is None else known(number(closing_value.value) - basis, ratio=False)
    return known(q, ratio=False), known(basis, ratio=False), known(realized, ratio=False), unrealized


@dataclass(frozen=True, slots=True)
class CostBasisResult:
    schema_version: int
    environment: str
    account_ref: str
    position: PositionKey
    currency: str
    quantum: str
    facts: tuple[TradeCostFact, ...]
    opening_quantity: str
    closing_native_value: Metric
    supported: bool
    quantity: Metric
    remaining_basis: Metric
    realized_pnl: Metric
    unrealized_pnl: Metric
    attribution: Metric = Metric(None, ('price_fx_attribution_unsupported',))

    def __post_init__(self):
        header(self)
        account(self.account_ref)
        exact(self.position, PositionKey)
        currency(self.currency)
        normalized(self, 'quantum', 'opening_quantity')
        if number(self.quantum) <= 0:
            raise ContractError()
        unique(self.facts, TradeCostFact, lambda x: x.trade.ref)
        if any((x.account_ref, x.position, x.currency, x.quantum) != (self.account_ref, self.position, self.currency, self.quantum) for x in self.facts):
            raise ContractError()
        if tuple(x.effective_at for x in self.facts) != tuple(sorted(x.effective_at for x in self.facts)):
            raise ContractError()
        actual = (self.quantity, self.remaining_basis, self.realized_pnl, self.unrealized_pnl)
        for x in actual:
            exact(x, Metric)
        if actual != basis_math(self.facts, self.opening_quantity, self.closing_native_value, self.quantum, self.supported):
            raise ContractError()
        if self.attribution != unknown('price_fx_attribution_unsupported'):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class OrderAttempt:
    instrument_id: str
    decision_snapshot: InputRef
    decision_at: str
    fill_at: str
    side: str
    quantity: str
    decision_price: str
    reference_price: str
    fill_price: str
    status: str
    reason: str
    trade: InputRef | None

    def __post_init__(self):
        identifier(self.instrument_id)
        exact(self.decision_snapshot, InputRef)
        if self.decision_snapshot.kind != 'snapshot':
            raise ContractError()
        for name in ('decision_at', 'fill_at'):
            object.__setattr__(self, name, instant(getattr(self, name)))
        if self.decision_at >= self.fill_at:
            raise ContractError()
        choice(self.side, ('buy', 'sell'))
        normalized(self, 'quantity', 'decision_price', 'reference_price', 'fill_price')
        if any(number(getattr(self, x)) <= 0 for x in ('quantity', 'decision_price', 'reference_price', 'fill_price')):
            raise ContractError()
        choice(self.status, ('filled', 'unfilled'))
        choice(self.reason, ('filled', 'cash', 'volume', 'minimum_notional', 'lot', 'position'))
        if (self.status == 'filled') != (self.trade is not None) or (self.status == 'filled') != (self.reason == 'filled'):
            raise ContractError()
        if self.trade is not None:
            exact(self.trade, InputRef)
            if self.trade.kind != 'event':
                raise ContractError()


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    schema_version: int
    environment: str
    attempts: tuple[OrderAttempt, ...]

    def __post_init__(self):
        header(self)
        items(self.attempts, OrderAttempt, MAX_INPUTS)


@dataclass(frozen=True, slots=True)
class ExperimentManifest:
    schema_version: int
    environment: str
    account_ref: str
    spec_hash: str
    market_id: str
    scenario_id: str
    fold_id: str
    strategy: str
    starts_at: str
    ends_at: str
    base_currency: str
    scope_hash: str
    created_at: str
    refs: tuple[InputRef, ...]
    predecessor: str | None = None

    def __post_init__(self):
        header(self)
        account(self.account_ref)
        digest(self.spec_hash)
        digest(self.scope_hash)
        choice(self.market_id, ('KR', 'US'))
        choice(self.scenario_id, ('explicit_costs', 'zero_cost_control'))
        choice(self.fold_id, ('fold01', 'fold02'))
        choice(self.strategy, STRATEGIES)
        currency(self.base_currency)
        for name in ('starts_at', 'ends_at', 'created_at'):
            object.__setattr__(self, name, instant(getattr(self, name)))
        if not self.starts_at < self.ends_at <= self.created_at:
            raise ContractError()
        unique(self.refs, InputRef, lambda x: (x.kind, x.ref))
        if tuple((x.kind, x.ref) for x in self.refs) != tuple(sorted((x.kind, x.ref) for x in self.refs)):
            raise ContractError()
        if self.predecessor is not None:
            identifier(self.predecessor)

    @property
    def comparison_key(self):
        return (self.environment, self.account_ref, self.spec_hash, self.market_id, self.scenario_id,
                self.fold_id, self.strategy, self.starts_at, self.ends_at, self.base_currency, self.scope_hash)


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    schema_version: int
    environment: str
    result_id: str
    manifest: ExperimentManifest
    performance: PerformanceResult
    cost_basis: tuple[CostBasisResult, ...]
    fees: Metric
    taxes: Metric
    slippage: Metric
    fx_transaction_cost: Metric
    cash_benchmark_return: Metric
    status: str
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        header(self)
        exact(self.manifest, ExperimentManifest)
        exact(self.performance, PerformanceResult)
        unique(self.cost_basis, CostBasisResult, lambda x: x.position.key)
        for x in (self.fees, self.taxes, self.slippage, self.fx_transaction_cost, self.cash_benchmark_return):
            exact(x, Metric)
        if self.result_id != 'experiment:' + hash_record(self.manifest):
            raise ContractError()
        m, p = self.manifest, self.performance
        if (p.points[0].as_of, p.points[-1].as_of) != (m.starts_at, m.ends_at):
            raise ContractError()
        refs = set(m.refs)
        if any(x.snapshot not in refs for x in (*p.points, *(f.before for f in p.flows), *(f.after for f in p.flows))):
            raise ContractError()
        facts = tuple(f for c in self.cost_basis for f in c.facts)
        if any(c.account_ref != m.account_ref for c in self.cost_basis):
            raise ContractError()
        for f in facts:
            if f.trade not in refs or any(a.event not in refs for a in f.allocations):
                raise ContractError()
        for name, kind in (('fees', 'fee'), ('taxes', 'tax')):
            expected = known(sum((number(a.amount) for f in facts for a in f.allocations if a.kind == kind), Fraction()), ratio=False)
            # native totals of the fixed single-currency run only.
            if all(f.currency == m.base_currency for f in facts) and getattr(self, name) != expected:
                raise ContractError()
        if all(f.currency == m.base_currency for f in facts) and self.slippage != known(sum((f.slippage for f in facts), Fraction()), ratio=False):
            raise ContractError()
        if p.traded_notional != known(sum((f.base_notional.exact_value for f in facts), Fraction()), ratio=False):
            raise ContractError()
        if self.fx_transaction_cost != known(0, ratio=False):
            raise ContractError()
        reasons(self.reason_codes)
        expected_reasons = {r for metric in (p.twr, p.amount_pnl, p.observed_mdd, p.gross_turnover,
                            p.benchmark_excess, p.benchmark_relative_wealth, self.cash_benchmark_return,
                            self.fees, self.taxes, self.slippage, self.fx_transaction_cost) for r in metric.reason_codes}
        expected_reasons.update(r for c in self.cost_basis for metric in (c.remaining_basis, c.realized_pnl, c.unrealized_pnl) for r in metric.reason_codes)
        if self.reason_codes != tuple(sorted(expected_reasons)) or self.status != ('incomplete' if expected_reasons else 'complete'):
            raise ContractError()
