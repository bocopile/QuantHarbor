"""Q23 고정 공개 파일만 읽는 fixture와 메모리 저장. 외부 서비스 없음."""
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import struct
import sys
from threading import RLock

from quantharbor.domain.ledger import (CashLeg, LedgerBaseline, LedgerCompleteness, PositionDelta,
    SyntheticLedgerSubmission, account, choice, exact, hash_record, integer)
from quantharbor.domain.primitives import ContractError, Price, Quantity, utc_instant
from quantharbor.domain.research import (ComparisonSpec, CostAllocation, CostScenario, ExecutionTrace,
    ExperimentRegistry, ExperimentResult, FileFingerprint, FoldSpec, ImplementationFingerprint,
    InputRef, OrderAttempt, PointIndex, PointTime, RAW_SPEC_SHA256, ResearchMarket, ResearchPoint, STRATEGIES,
    TradeCostFact, known)
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.valuation import (BalanceScope, CurrencyQuantum, DOMAINS, PositionKey,
    PriceSelection, ReconciliationPolicy, SeriesSelection, ValuationPolicy, ValuationRequest,
    finite, number)

_ROOT = Path(__file__).resolve().parents[3]
SPEC_PATH = 'docs/contracts/comparison-spec-v1.json'
# 검색이나 사용자 경로를 받지 않는다. 실제 소비하는 구현/lock의 닫힌 목록이다.
FINGERPRINT_PATHS = tuple(sorted((
    'pyproject.toml', 'config/runtime-lock.json', 'config/market-storage-lock.json',
    'src/quantharbor/__init__.py', 'src/quantharbor/domain/__init__.py',
    'src/quantharbor/application/__init__.py', 'src/quantharbor/adapters/__init__.py',
    'src/quantharbor/ports/__init__.py', 'src/quantharbor/market_data/__init__.py',
    'src/quantharbor/domain/documents.py', 'src/quantharbor/domain/broker_read.py',
    'src/quantharbor/domain/reporting.py',
    'src/quantharbor/domain/research.py', 'src/quantharbor/domain/serialization.py',
    'src/quantharbor/domain/primitives.py', 'src/quantharbor/domain/ledger.py',
    'src/quantharbor/domain/valuation.py', 'src/quantharbor/domain/market_data.py',
    'src/quantharbor/domain/market_storage.py', 'src/quantharbor/domain/catalog.py',
    'src/quantharbor/domain/calendar.py', 'src/quantharbor/application/research.py',
    'src/quantharbor/application/market_ingest.py', 'src/quantharbor/application/ledger.py',
    'src/quantharbor/application/valuation.py', 'src/quantharbor/ports/research.py',
    'src/quantharbor/ports/valuation.py', 'src/quantharbor/adapters/synthetic_research.py',
    'src/quantharbor/adapters/synthetic_market.py', 'src/quantharbor/adapters/synthetic_ledger.py',
    'src/quantharbor/adapters/synthetic_valuation.py', 'src/quantharbor/market_data/timezones.py',
    'src/quantharbor/research/__init__.py', 'src/quantharbor/research/metrics.py',
    'src/quantharbor/research/costing.py', 'src/quantharbor/research/strategies.py',
)))


def _public_bytes(path):
    if path not in (*FINGERPRINT_PATHS, SPEC_PATH):
        raise ContractError()
    fd = os.open(_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.split('/'):
            new = os.open(part, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            os.close(fd)
            fd = new
        before = os.fstat(fd)
        import stat
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 1048576:
            raise ContractError()
        data = bytearray()
        while len(data) <= 1048576:
            chunk = os.read(fd, min(65536, 1048577 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        if len(data) > 1048576 or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ContractError()
        return bytes(data)
    except OSError:
        raise ContractError() from None
    finally:
        os.close(fd)


def load_fixed_spec():
    raw = _public_bytes(SPEC_PATH)
    if sha256(raw).hexdigest() != RAW_SPEC_SHA256:
        raise ContractError()
    value = json.loads(raw)
    return ComparisonSpec(1, 'synthetic', value['spec_id'], RAW_SPEC_SHA256, value['run_at'],
        tuple(ResearchMarket(**(dict(market_id=x['id']) | {k: v for k, v in x.items() if k != 'id'})) for x in value['markets']),
        tuple(FoldSpec(x['id'], tuple(PointIndex(i) for i in x['train']), tuple(PointIndex(i) for i in x['validation']),
                       tuple(PointIndex(i) for i in x['oos'])) for x in value['folds']),
        tuple(ResearchPoint(x['index'], PointTime(**x['KR']), PointTime(**x['US'])) for x in value['points']),
        tuple(CostScenario(**(dict(scenario_id=x['id']) | {k: v for k, v in x.items() if k != 'id'})) for x in value['cost_scenarios']),
        tuple(value['base_equity_closes']), tuple(value['base_etf_closes']))


def implementation_fingerprint():
    return ImplementationFingerprint(1, 'synthetic', tuple(FileFingerprint(p, sha256(_public_bytes(p)).hexdigest())
                                                           for p in FINGERPRINT_PATHS),
                                     '.'.join(map(str, sys.version_info[:3])))


class SyntheticExperimentRepository:
    def __init__(self, *, capacity=128):
        integer(capacity, 1, 128)
        self._capacity = capacity
        self._results = {}
        self._lock = RLock()

    @classmethod
    def product_synthetic(cls, database, *, capacity=128):
        """명시 제품 연결. 같은 정확 repository 타입과 검증 경로를 유지한다."""
        from .product_artifacts import ProductArtifacts
        repository = SyntheticExperimentRepository(capacity=capacity)
        repository._results = ProductArtifacts.product_synthetic(database, 'experiment', capacity=capacity)
        repository._lock = database._product_gate
        return repository

    def list_records(self, *, environment, account_ref):
        from .product_artifacts import list_records
        with self._lock:
            return list_records(self._results, 'experiment', environment, account_ref)

    def get(self, result_id, *, environment, account_ref):
        from quantharbor.domain.primitives import identifier
        identifier(result_id)
        choice(environment, ('synthetic',))
        account(account_ref)
        with self._lock:
            stored = self._results.get(result_id)
            if stored is None:
                return None
            result = parse_payload(stored[1]).payload
            if hash_record(result) != stored[0] or result.result_id != result_id:
                raise ContractError()
            if (result.environment, result.manifest.account_ref) != (environment, account_ref):
                raise ContractError()
            return result

    def append(self, result):
        exact(result, ExperimentResult)
        encoded = canonical_bytes(CanonicalPayload('ExperimentResult', 1, 'synthetic', result))
        result = parse_payload(encoded).payload
        hashed = hash_record(result)
        with self._lock:
            existing = self._results.get(result.result_id)
            if existing is not None:
                if existing != (hashed, encoded):
                    raise ContractError()
                return parse_payload(existing[1]).payload
            if len(self._results) >= self._capacity:
                raise ContractError()
            prior_id = result.manifest.predecessor
            if prior_id is not None:
                prior = self.get(prior_id, environment=result.environment, account_ref=result.manifest.account_ref)
                if prior is None or prior.manifest.comparison_key != result.manifest.comparison_key or prior.manifest.created_at > result.manifest.created_at:
                    raise ContractError()
                # 한 predecessor에서 서로 다른 정정 분기를 암묵 선택하지 않는다.
                if any(parse_payload(row[1]).payload.manifest.predecessor == prior_id for row in self._results.values()):
                    raise ContractError()
            self._results[result.result_id] = hashed, encoded
            return result


KNOWN = '2023-12-01T00:00:00.000000Z'
WHOLE = BalanceScope('entire_account', (), ('KRW', 'USD'), tuple(sorted(DOMAINS)))


def _timezone(market):
    from quantharbor.market_data.timezones import ExplicitTimezone
    offsets = ((32400, 0, 0),) if market.market_id == 'KR' else ((-18000, 0, 0), (-14400, 1, 4))
    transitions = () if market.market_id == 'KR' else ((datetime(2024, 3, 10, 7, tzinfo=UTC), 1),
                                                     (datetime(2024, 11, 3, 6, tzinfo=UTC), 0))
    abbreviations = b'KST\0' if market.market_id == 'KR' else b'EST\0EDT\0'
    raw = b'TZif\0' + b'\0' * 15 + struct.pack('>6l', 0, 0, 0, len(transitions), len(offsets), len(abbreviations))
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    raw += b''.join(struct.pack('>l', (t - epoch) // timedelta(seconds=1)) for t, _ in transitions)
    raw += bytes(i for _, i in transitions)
    raw += b''.join(struct.pack('>lBB', *x) for x in offsets) + abbreviations
    return ExplicitTimezone(market.timezone, 'q23-synthetic-rules-v1', sha256(raw).hexdigest(),
                            '2024-01-01T00:00:00Z', '2025-01-01T00:00:00Z', KNOWN, raw)


def _context(spec, market):
    from quantharbor.domain.catalog import Catalog, Instrument, SymbolMapping
    from quantharbor.domain.calendar import MarketCalendar, TradingDay, TradingSession
    zone = _timezone(market)
    venue = 'q23.' + market.market_id
    instruments, mappings = [], []
    for suffix, kind, etf in (('equity', 'equity', 'not_applicable'), ('etf', 'etf', 'general')):
        key = venue + '.' + suffix
        instruments.append(Instrument(key, 'q23-instrument-v1', venue, market.market_id, market.currency,
            kind, etf, 'q23-classification-v1', 'q23:predeclared-universe-including-exit-status', KNOWN, None, KNOWN))
        mappings.append(SymbolMapping(key + '.mapping', 'q23-mapping-v1', 'q23.source', suffix.upper(),
                                     key, venue, venue, KNOWN, None, KNOWN))
    cat = Catalog('q23-catalog-v1', 'q23:synthetic-universe', tuple(instruments), tuple(mappings))
    days = []
    for point in spec.points:
        t = getattr(point, market.market_id)
        day = t.bar_start[:10]
        next_day = (datetime.fromisoformat(day) + timedelta(days=1)).date().isoformat()
        start = zone.resolve_local(day + 'T00:00:00', knowledge_cutoff=spec.run_at)
        end = zone.resolve_local(next_day + 'T00:00:00', knowledge_cutoff=spec.run_at)
        # 사전 선언한 합성 세션. 실제 거래소 달력의 재현이 아니다.
        session = TradingSession(venue + '.session.' + day, day, 'regular', t.bar_start,
            utc_instant(datetime.fromisoformat(t.bar_end) + timedelta(minutes=1)), KNOWN, 'q23:session')
        days.append(TradingDay(day, start, end, 'open', KNOWN, 'q23:day', (session,)))
    cal = MarketCalendar('q23-calendar-v1', venue, market.timezone, zone.rules_version,
        zone.content_sha256, '2024-01-01', '2025-01-01', KNOWN, 'q23:synthetic-calendar', tuple(days))
    return dict(catalog=cat, calendar=cal, timezone=zone)


def _market_point(spec, market, index, context):
    from quantharbor.adapters.synthetic_market import SyntheticPageAdapter
    from quantharbor.application.market_ingest import ingest
    from quantharbor.domain.market_data import (ExpectedEvent, FetchRequest, IngestLimits, MarketItem,
        MarketObservation, MarketRevision, PageResult, PriceBar, QueryScope, RightsGrant, record_hash)
    from quantharbor.ports.valuation import MarketDatasetInput
    t = getattr(spec.points[index - 1], market.market_id)
    rights = RightsGrant('q23.rights', 'synthetic', 'q23.source', 'q23.dataset', 'q23-dataset-v1',
        ('store', 'research', 'report'), KNOWN, '2025-01-01T00:00:00Z', None)
    records = []
    for suffix, closes, multiplier in (('equity', spec.equity_closes, market.equity_price_multiplier),
                                        ('etf', spec.etf_closes, market.etf_price_multiplier)):
        key = 'q23.' + market.market_id + '.' + suffix
        price = Price(finite(number(closes[index - 1]) * number(multiplier)), market.currency, key, 'share')
        payload = PriceBar(key, 'q23.' + market.market_id, 'q23.' + market.market_id, suffix.upper(),
            t.bar_start, t.bar_end, price, price, price, price, Quantity('100000', key, 'share'), None, 'raw', None)
        rev = MarketRevision(1, 'synthetic', 'q23.source', 'q23.dataset', key, key + '.' + str(index),
            'original-v1', None, 'original', t.bar_end, t.published_at, None, 'q23-normalize-v1', payload)
        obs = MarketObservation(1, 'synthetic', key + '.obs.' + str(index), 'q23.source', 'q23.dataset',
            key, rev.event_id, rev.revision_id, record_hash(rev), t.observed_at, t.ingested_at,
            sha256(('synthetic-fixed:' + key + ':' + str(index) + ':' + price.amount).encode()).hexdigest(),
            'q23:explicit-synthetic-source', rights.rights_ref, 'q23-catalog-v1', 'q23-calendar-v1')
        records.append(MarketItem(rev, obs))
    scope = QueryScope(tuple(x.revision.series_id for x in records), t.bar_start,
        utc_instant(datetime.fromisoformat(t.bar_end) + timedelta(microseconds=1)),
        tuple(ExpectedEvent(x.revision.series_id, x.revision.event_id, t.bar_end) for x in records),
        'expected_records', 'q23:complete-two-instrument-point:' + str(index))
    request = FetchRequest('q23-request-' + market.market_id + '-' + str(index), 'synthetic',
        'q23.source', 'q23.dataset', 'q23-dataset-v1', scope, t.bar_start,
        utc_instant(datetime.fromisoformat(t.knowledge_cutoff) + timedelta(seconds=1)), t.knowledge_cutoff)
    page = PageResult(request.request_id, scope, None, None, True, 'success', tuple(records),
        ('synthetic-fixed-page:' + market.market_id + ':' + str(index)).encode(), 'q23-source-snapshot-' + str(index),
        t.ingested_at, None, None)
    result = ingest(request, SyntheticPageAdapter((page,)), limits=IngestLimits(max_age_seconds=3600),
                    rights=rights, evaluated_at=t.knowledge_cutoff, **context)
    return MarketDatasetInput(result.bundle, **context, current_rights=rights)


def event_ref(event):
    return InputRef('event', event.body.event_id, event.payload_hash)


def snapshot_ref(snapshot):
    return InputRef('snapshot', snapshot.snapshot_id, hash_record(snapshot))


def _pair(target, amount, counter, currency, basis='settlement'):
    return (CashLeg(target, currency, finite(amount), basis), CashLeg(counter, currency, finite(-amount), basis))


def _submission(account_ref, key, kind, at, legs, *, positions=(), dependencies=(), baseline=None):
    return SyntheticLedgerSubmission(1, 'synthetic', account_ref, 'q23-synthetic', key, 1, None,
        'q23-mapping-v1', kind, at, 'original', None, legs, positions, ('q23:explicit-synthetic-facts',),
        LedgerCompleteness(True, True, True), baseline, dependencies, None)


def fixed_experiment_inputs(spec=None):
    """24개 계좌를 만들고 실제 Q17/Q20/Q21 경로로 검증 가능한 객체를 반환한다."""
    from quantharbor.adapters.synthetic_ledger import SyntheticLedger
    from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
    from quantharbor.application.valuation import build_snapshot
    from quantharbor.ports.research import ExperimentInputs, ResearchPointInput
    from quantharbor.research.strategies import plan_orders, fill_terms
    spec = load_fixed_spec() if spec is None else spec
    if spec != load_fixed_spec():
        raise ContractError()
    fingerprint = implementation_fingerprint()
    registry = ExperimentRegistry(1, 'synthetic', hash_record(spec), KNOWN, 'PG02:RESEARCH-DEC-001:fit-none')
    result = []
    for market in spec.markets:
        context = _context(spec, market)
        # 각 bundle은 그 시점의 두 봉만 포함한다. 최종 bundle의 과거 재사용 금지.
        datasets = {i: _market_point(spec, market, i, context) for i in range(1, 13)}
        positions = tuple(PositionKey(x.instrument_id, 'q23.' + market.market_id, 'q23-mapping-v1', 'share')
                          for x in context['catalog'].instruments)
        policy = ValuationPolicy(1, 'synthetic', 'q23-valuation-v1',
            tuple(PriceSelection(p, SeriesSelection('q23.source', 'q23.dataset', 'q23-dataset-v1', p.instrument_id))
                  for p in sorted(positions, key=lambda x: x.key)), (),
            (CurrencyQuantum(market.currency, market.money_quantum),), 3600, 3600)
        reconciliation = ReconciliationPolicy(1, 'synthetic', 'q23-reconciliation-v1', (), ())
        for costs in spec.costs:
            for fold in spec.folds:
                for strategy in STRATEGIES:
                    account_ref = 'synthetic-account:q23:' + ':'.join((market.market_id, costs.scenario_id, fold.fold_id, strategy))
                    ledger, snapshots = SyntheticLedger(), SyntheticSnapshotRepository()
                    points, facts, attempts = [], [], []
                    pending, previous = (), None
                    def append(submission, recorded_at):
                        appended = ledger.append(submission, recorded_at=recorded_at)
                        if appended.status != 'accepted':
                            raise ContractError()
                        return ledger.state(account_ref).events[-1]
                    first_time = getattr(spec.points[fold.oos_indices[0] - 1], market.market_id)
                    append(_submission(account_ref, 'opening', 'baseline', first_time.bar_end,
                        _pair('settled_cash', number(market.initial_cash), 'opening_equity', market.currency),
                        baseline=LedgerBaseline(True, True, 'entire_account')), first_time.knowledge_cutoff)
                    for j, index in enumerate(fold.oos_indices):
                        t = getattr(spec.points[index - 1], market.market_id)
                        dataset = datasets[index]
                        bars = {x.revision.payload.instrument_id: x.revision.payload for x in dataset.bundle.evidence}
                        for order in pending:
                            projection = ledger.replay(account_ref, as_of=t.bar_end, knowledge_cutoff=t.knowledge_cutoff)
                            cash = next(x.amount for x in projection.cash_balances if x.account == 'settled_cash')
                            holding = next((x.amount for x in projection.holdings if x.instrument_id == order.instrument_id), '0')
                            bar = bars[order.instrument_id]
                            fill, fee, tax, reason = fill_terms(order, bar.close.amount, bar.volume.amount, market, costs, cash, holding)
                            traded = None
                            if reason == 'filled':
                                qty, notional = number(order.quantity), number(order.quantity) * number(fill)
                                buying = order.side == 'buy'
                                target = 'unsettled_payable' if buying else 'unsettled_receivable'
                                signed = -notional if buying else notional
                                key = 'fill:' + str(index) + ':' + order.instrument_id
                                pos = next(p for p in positions if p.instrument_id == order.instrument_id)
                                traded = append(_submission(account_ref, key, 'trade', t.bar_end,
                                    _pair(target, signed, 'trade_clearing', market.currency, 'trade'),
                                    positions=(PositionDelta(*pos.key, finite(qty if buying else -qty)),)), t.knowledge_cutoff)
                                append(_submission(account_ref, key + ':settle', 'settlement', t.bar_end,
                                    (CashLeg(target, market.currency, finite(-signed), 'settlement'),
                                     CashLeg('settled_cash', market.currency, finite(signed), 'settlement')),
                                    dependencies=(traded.body.event_id,)), t.knowledge_cutoff)
                                allocations = []
                                for kind, amount in (('fee', fee), ('tax', tax)):
                                    if number(amount):
                                        ev = append(_submission(account_ref, key + ':' + kind, kind, t.bar_end,
                                            _pair('settled_cash', -number(amount), kind + '_expense', market.currency),
                                            dependencies=(traded.body.event_id,)), t.knowledge_cutoff)
                                        allocations.append(CostAllocation(event_ref(ev), 1, kind, amount, getattr(costs, kind + '_rate_' + order.side)))
                                facts.append(TradeCostFact(1, 'synthetic', account_ref, event_ref(traded), 1, pos,
                                    market.currency, t.bar_end, order.side, order.quantity, bar.close.amount, fill,
                                    market.money_quantum, tuple(allocations), known(notional, ratio=False)))
                            attempts.append(OrderAttempt(order.instrument_id, snapshot_ref(previous), previous.knowledge_cutoff,
                                t.bar_end, order.side, order.quantity, order.decision_price, bar.close.amount, fill,
                                'filled' if traded else 'unfilled', reason, event_ref(traded) if traded else None))
                        projection = ledger.replay(account_ref, as_of=t.bar_end, knowledge_cutoff=t.knowledge_cutoff)
                        request = ValuationRequest(1, 'synthetic', account_ref, 'q23-point-' + str(index),
                            projection.ledger_cursor, t.bar_end, t.knowledge_cutoff, t.knowledge_cutoff, 'as_known',
                            market.currency, 'research', policy.version, reconciliation.version, WHOLE)
                        snapshot = build_snapshot(projection, request, (dataset,), policy, reconciliation, snapshots)
                        points.append(ResearchPointInput(snapshot, (dataset,)))
                        if not snapshot.valuation.complete:
                            raise ContractError()
                        pending = plan_orders(strategy, snapshot.valuation.nav,
                            tuple(sorted((key, bar.close.amount) for key, bar in bars.items())),
                            tuple((p.instrument_id, p.amount) for p in projection.holdings), first=j == 0) if j < len(fold.oos) - 1 else ()
                        previous = snapshot
                    result.append(ExperimentInputs(spec, registry, fingerprint, market.market_id, costs.scenario_id,
                        fold.fold_id, strategy, tuple(points), tuple(ledger.state(account_ref).events), tuple(facts),
                        ExecutionTrace(1, 'synthetic', tuple(attempts))))
    return tuple(result)


def run_fixed_comparison():
    """반환: (24개 불변 ExperimentResult tuple, 24개 간결한 불변 RunSummary tuple)."""
    from quantharbor.application.research import build_comparison, summarize
    inputs = fixed_experiment_inputs()
    results = build_comparison(inputs, SyntheticExperimentRepository())
    return results, tuple(summarize(r) for r in results)
