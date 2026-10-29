"""Q23 명시 입력을 해소·재생하는 builder. 원천 진위 attestation은 아니다."""
from dataclasses import asdict, dataclass, replace
from fractions import Fraction
from hashlib import sha256
import json

from quantharbor.application.market_ingest import select_view
from quantharbor.application.valuation import build_snapshot
from quantharbor.domain.ledger import LedgerEvent, exact, hash_record, integer
from quantharbor.domain.market_data import PriceBar
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.research import (ExperimentManifest, ExperimentResult, InputRef, MAX_INPUTS,
    MAX_RESOLVED_BYTES, NavPoint, Metric, known, unique, unknown)
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.valuation import finite, number
from quantharbor.ports.research import ExperimentInputs, ResearchPointInput
from quantharbor.research.costing import calculate_basis
from quantharbor.research.metrics import calculate_performance
from quantharbor.research.strategies import fill_terms, plan_orders


def _encoded(obj):
    return canonical_bytes(CanonicalPayload(type(obj).__name__, 1, 'synthetic', obj))


def _ref(kind, name, obj):
    return InputRef(kind, name, hash_record(obj))


def nav_point(snapshot):
    v = snapshot.valuation
    return NavPoint(_ref('snapshot', snapshot.snapshot_id, snapshot), snapshot.as_of, snapshot.knowledge_cutoff,
        snapshot.ledger_cursor, v.nav, v.reason_codes if not v.complete else ())


def _preflight(inputs):
    """할당/재생 전에 각 객체64KiB와 해소 입력 전체8MiB를 확인한다."""
    if type(inputs) is not ExperimentInputs:
        raise ContractError()
    for values in (inputs.points, inputs.events, inputs.costs, inputs.boundaries, inputs.boundary_inputs):
        if type(values) is not tuple or len(values) > MAX_INPUTS:
            raise ContractError()
    total = 0
    for obj in (inputs.spec, inputs.registry, inputs.fingerprint, inputs.trace, *inputs.costs):
        total += len(_encoded(obj))
    total += _resolved_bytes((*inputs.points, *inputs.boundary_inputs), inputs.events)
    if total > MAX_RESOLVED_BYTES:
        raise ContractError()
    return total


def _resolved_bytes(points, events):
    if type(points) is not tuple or len(points) > MAX_INPUTS or type(events) is not tuple or len(events) > MAX_INPUTS:
        raise ContractError()
    total = 0
    for event in events:
        exact(event, LedgerEvent)
        total += len(_encoded(event.body))
    for point in points:
        if type(point) is not ResearchPointInput or type(point.market_inputs) is not tuple or len(point.market_inputs) > MAX_INPUTS:
            raise ContractError()
        total += len(_encoded(point.snapshot))
        for supplied in point.market_inputs:
            bundle = supplied.bundle
            for values in (bundle.receipts, bundle.evidence):
                if type(values) is not tuple or len(values) > MAX_INPUTS:
                    raise ContractError()
            from quantharbor.domain.market_storage import evidence_index
            total += sum(len(_encoded(obj)) for obj in (bundle.descriptor, bundle.envelope, bundle.summary,
                                                         evidence_index(bundle.evidence)))
            for obj in (*bundle.receipts, *(x.revision for x in bundle.evidence), *(x.observation for x in bundle.evidence)):
                total += len(_encoded(obj))
            # Q16 source facts have their existing separate digest contract, not a new codec.
            for context in (supplied.catalog, supplied.calendar):
                size = len(json.dumps(asdict(context), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())
                if size > 65536:
                    raise ContractError()
                total += size
            total += len(supplied.timezone.tzif_bytes)
            if total > MAX_RESOLVED_BYTES:
                raise ContractError()
    if total > MAX_RESOLVED_BYTES:
        raise ContractError()
    return total


def _replay_events(events):
    from quantharbor.adapters.synthetic_ledger import SyntheticLedger
    if type(events) is not tuple or not 1 <= len(events) <= MAX_INPUTS:
        raise ContractError()
    store = SyntheticLedger()
    account_ref = events[0].body.account_ref
    for event in events:
        exact(event, LedgerEvent)
        if event.body.account_ref != account_ref:
            raise ContractError()
        accepted = store.append(event.body.submission, recorded_at=event.body.recorded_at)
        if accepted.status != 'accepted' or store.state(account_ref).events[-1] != event:
            raise ContractError()
    if tuple(store.state(account_ref).events) != events:
        raise ContractError()
    return store


def _revalidate_point(point, store):
    from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
    exact(point, ResearchPointInput)
    s = parse_payload(_encoded(point.snapshot)).payload
    request = s.valuation.request
    # Q23 v1 supports as-known snapshots; historical v1 placeholders are preserved.
    if request.purpose != 'research' or request.projection_mode != 'as_known' or s.supersedes_snapshot_id is not None:
        raise ContractError()
    p = store.replay(s.account_ref, as_of=s.as_of, knowledge_cutoff=s.knowledge_cutoff, cursor=s.ledger_cursor)
    if p != s.valuation.projection:
        raise ContractError()
    rebuilt = build_snapshot(p, request, point.market_inputs, s.valuation.policy,
        s.reconciliation_policy, SyntheticSnapshotRepository(), statement=s.reconciliation_details.statement)
    # Q21은 권리 보류 증빙을 포함한 unknown/현금 NAV도 저장할 수 있다.
    # 연구 소비는 모든 원천 증빙에 대해 소비 시각의 research/store 권리를 요구한다.
    for proof in rebuilt.valuation.market_proofs:
        for purpose in ('research', 'store'):
            if not proof.rights.allows(at=request.evaluated_at, purpose=purpose,
                    source_id=proof.selection.source_id, dataset_id=proof.selection.dataset_id,
                    dataset_version=proof.selection.dataset_version):
                raise ContractError()
    if rebuilt != s or hash_record(rebuilt) != hash_record(s):
        raise ContractError()
    return s


def _validate_flows(points, boundary_inputs, boundaries, events, store):
    snapshots = {p.snapshot.snapshot_id: p.snapshot for p in (*points, *boundary_inputs)}
    if len(snapshots) != len(points) + len(boundary_inputs):
        raise ContractError()
    flow_events = {e.body.event_id: e for e in events if points[0].snapshot.as_of < e.body.effective_at <= points[-1].snapshot.as_of
                   and e.body.submission.event_type in ('deposit', 'withdrawal')}
    allocated = set()
    used_boundaries = set()
    for boundary in boundaries:
        before = snapshots.get(boundary.before.snapshot.ref)
        after = snapshots.get(boundary.after.snapshot.ref)
        if before is None or after is None or nav_point(before) != boundary.before or nav_point(after) != boundary.after:
            raise ContractError()
        a, b = before.valuation, after.valuation
        if (a.policy, a.market_proofs, before.as_of, before.knowledge_cutoff, before.base_currency,
                a.request.scope, before.account_ref) != (b.policy, b.market_proofs, after.as_of,
                after.knowledge_cutoff, after.base_currency, b.request.scope, after.account_ref):
            raise ContractError()
        between = tuple(e for e in events if before.ledger_cursor < e.body.sequence <= after.ledger_cursor)
        refs = tuple(_ref('event', e.body.event_id, e.body) for e in between)
        if refs != boundary.events or len(between) != after.ledger_cursor - before.ledger_cursor:
            raise ContractError()
        amount = Fraction()
        for e in between:
            if e.body.event_id in allocated or e.body.event_id not in flow_events or e.body.effective_at != before.as_of or e.body.recorded_at > before.knowledge_cutoff:
                raise ContractError()
            s = e.body.submission
            if s.source_revision != 1 or s.position_deltas or e.body.kind != 'replacement':
                raise ContractError()
            legs = [x for x in s.cash_legs if x.account == 'settled_cash']
            if len(legs) != 1 or legs[0].currency != before.base_currency or boundary.currency != before.base_currency:
                raise ContractError()
            amount += number(legs[0].amount)
            allocated.add(e.body.event_id)
        if number(boundary.amount) != amount or boundary.quantum != a.policy.quantum(before.base_currency):
            raise ContractError()
        used_boundaries.update((before.snapshot_id, after.snapshot_id))
    if allocated != set(flow_events) or {p.snapshot.snapshot_id for p in boundary_inputs} - used_boundaries:
        raise ContractError()
    # 모든 평가점은 cutoff까지 기록된 완결 cursor여야 한다. 직전 경계만 예외다.
    before_ids = {f.before.snapshot.ref for f in boundaries}
    for s in snapshots.values():
        complete_cursor = max((e.body.sequence for e in events if e.body.recorded_at <= s.knowledge_cutoff), default=0)
        if s.snapshot_id not in before_ids and s.ledger_cursor != complete_cursor:
            raise ContractError()
    return snapshots


def build_bound_performance(points, events, *, boundaries=(), boundary_inputs=(), costs=(),
                            benchmark_return=Metric(None, ('benchmark_missing',))):
    """Q20/Q21 실입력의 흐름 경계를 검증하는 별도 성과 API. 임의 NAV 배열 금지."""
    _resolved_bytes((*points, *boundary_inputs), events)
    unique(points, ResearchPointInput, lambda p: p.snapshot.snapshot_id)
    unique(boundary_inputs, ResearchPointInput, lambda p: p.snapshot.snapshot_id)
    if len(points) < 2:
        raise ContractError()
    if any((p.snapshot.account_ref, p.snapshot.base_currency, p.snapshot.valuation.request.scope) !=
           (points[0].snapshot.account_ref, points[0].snapshot.base_currency, points[0].snapshot.valuation.request.scope)
           for p in (*points, *boundary_inputs)):
        raise ContractError()
    store = _replay_events(events)
    for p in (*points, *boundary_inputs):
        _revalidate_point(p, store)
    _validate_flows(points, boundary_inputs, boundaries, events, store)
    validate_trade_costs(events, costs)
    base_currency = points[0].snapshot.base_currency
    measured = tuple(f for f in costs if points[0].snapshot.as_of < f.effective_at <= points[-1].snapshot.as_of)
    traded_notional = (known(sum((f.notional for f in measured), Fraction()), ratio=False)
                       if all(f.currency == base_currency for f in measured) else unknown('trade_base_fx_unknown'))
    return calculate_performance(tuple(nav_point(p.snapshot) for p in points), boundaries,
                                 traded_notional, benchmark_return)


def validate_trade_costs(event_inputs, cost_inputs):
    # Public Q23 v1 keeps its original-only contract. Execution validates the
    # complete correction stream before using the shared economic checks.
    if any(e.body.submission.event_type == 'trade' and
           e.body.submission.revision_mode != 'original' for e in event_inputs):
        raise ContractError()
    _validate_trade_cost_facts(event_inputs, cost_inputs)


def _validate_trade_cost_facts(event_inputs, cost_inputs):
    events = {e.body.event_id: e for e in event_inputs}
    trades = {e.body.event_id for e in event_inputs if e.body.submission.event_type == 'trade'}
    charges = {e.body.event_id for e in event_inputs if e.body.submission.event_type in ('fee', 'tax')}
    used_trades, used_costs = set(), set()
    from quantharbor.domain.research import TradeCostFact
    unique(cost_inputs, TradeCostFact, lambda f: f.trade.ref)
    for fact in cost_inputs:
        e = events.get(fact.trade.ref)
        if e is None or fact.trade != _ref('event', e.body.event_id, e.body) or e.body.event_id in used_trades:
            raise ContractError()
        b, s = e.body, e.body.submission
        if s.event_type != 'trade' or b.kind != 'replacement' or b.source_revision != fact.revision:
            raise ContractError()
        if (b.account_ref, b.effective_at, s.position_deltas[0].key) != (fact.account_ref, fact.effective_at, fact.position.key):
            raise ContractError()
        buying = number(s.position_deltas[0].amount) > 0
        if fact.side != ('buy' if buying else 'sell') or number(fact.quantity) != abs(number(s.position_deltas[0].amount)):
            raise ContractError()
        legs = [x for x in s.cash_legs if x.account.startswith('unsettled_')]
        if len(legs) != 1 or legs[0].currency != fact.currency or abs(number(legs[0].amount)) != fact.notional:
            raise ContractError()
        for alloc in fact.allocations:
            cost = events.get(alloc.event.ref)
            if cost is None or alloc.event != _ref('event', cost.body.event_id, cost.body) or alloc.event.ref in used_costs:
                raise ContractError()
            cb, cs = cost.body, cost.body.submission
            if (cs.event_type, cb.source_revision, cb.account_ref, cb.effective_at, cs.dependency_refs) != (
                    alloc.kind, alloc.revision, fact.account_ref, fact.effective_at, (b.event_id,)):
                raise ContractError()
            cash = [x for x in cb.cash_legs if x.account == 'settled_cash']
            if len(cash) != 1 or cash[0].currency != fact.currency or number(cash[0].amount) != -number(alloc.amount):
                raise ContractError()
            used_costs.add(alloc.event.ref)
        used_trades.add(b.event_id)
    if used_trades != trades or used_costs != charges:
        raise ContractError()


def _point_prices(point, spec, market, index):
    s = point.snapshot
    t = getattr(spec.points[index - 1], market.market_id)
    if (s.as_of, s.knowledge_cutoff, s.created_at) != (t.bar_end, t.knowledge_cutoff, t.knowledge_cutoff):
        raise ContractError()
    if len(point.market_inputs) != 1:
        raise ContractError()
    data = point.market_inputs[0]
    bundle = data.bundle
    req = bundle.descriptor.request
    if req.knowledge_cutoff != t.knowledge_cutoff or bundle.descriptor.evaluated_at != t.knowledge_cutoff or bundle.envelope.quality.status != 'complete':
        raise ContractError()
    first_cutoff = getattr(spec.points[0], market.market_id).knowledge_cutoff
    expected_ids = {'q23.' + market.market_id + '.equity', 'q23.' + market.market_id + '.etf'}
    if {x.instrument_id for x in data.catalog.instruments} != expected_ids:
        raise ContractError()
    for inst in data.catalog.instruments:
        if (not inst.eligible_for_initial_scope or inst.currency != market.currency or inst.market != market.market_id
                or inst.known_at >= first_cutoff or inst.valid_from >= first_cutoff or inst.valid_to is not None):
            raise ContractError()
        if (inst.product_kind, inst.etf_kind) != (('equity', 'not_applicable') if inst.instrument_id.endswith('.equity') else ('etf', 'general')):
            raise ContractError()
    grant = data.current_rights
    for at in (t.knowledge_cutoff, spec.run_at):
        for purpose in ('store', 'research', 'report'):
            if not grant.allows(at=at, purpose=purpose, source_id=req.source_id,
                                dataset_id=req.dataset_id, dataset_version=req.dataset_version):
                raise ContractError()
    view = select_view(bundle.state.revisions, as_of=s.as_of, knowledge_cutoff=s.knowledge_cutoff,
        rights=grant, at=s.created_at, dataset_version=req.dataset_version, catalog=data.catalog,
        calendar=data.calendar, timezone=data.timezone, purpose='research')
    if view.held_reasons or len(view.selected) != 2 or len(bundle.evidence) != 2:
        raise ContractError()
    bars = {}
    for item in view.selected:
        r, o = item.revision, item.observation
        bar = r.payload
        if type(bar) is not PriceBar or bar.instrument_id not in expected_ids or bar.instrument_id in bars:
            raise ContractError()
        if (bar.starts_at, bar.ends_at, r.effective_at, r.published_at, o.observed_at, o.ingested_at) != (
                t.bar_start, t.bar_end, t.bar_end, t.published_at, t.observed_at, t.ingested_at):
            raise ContractError()
        closes = spec.equity_closes if bar.instrument_id.endswith('.equity') else spec.etf_closes
        multiplier = market.equity_price_multiplier if bar.instrument_id.endswith('.equity') else market.etf_price_multiplier
        expected = finite(number(closes[index - 1]) * number(multiplier))
        if bar.adjustment != 'raw' or bar.volume is None or bar.volume.amount != '100000' or any(p.amount != expected for p in (bar.open, bar.high, bar.low, bar.close)):
            raise ContractError()
        if r.revision_kind != 'original' or r.predecessor_revision_id is not None or r.publication_unknown_reason is not None:
            raise ContractError()
        bars[bar.instrument_id] = bar
    if set(bars) != expected_ids or {x.series_id for x in req.scope.expected} != expected_ids or len(req.scope.expected) != 2:
        raise ContractError()
    return bars


def _validate_execution(inputs, store, market, costs, bars):
    facts = {f.trade.ref: f for f in inputs.costs}
    attempts, used = iter(inputs.trace.attempts), set()
    for j, (previous, current) in enumerate(zip(inputs.points, inputs.points[1:])):
        ps, cs = previous.snapshot, current.snapshot
        p = ps.valuation.projection
        orders = plan_orders(inputs.strategy, ps.valuation.nav,
            tuple(sorted((k, b.close.amount) for k, b in bars[j].items())),
            tuple((h.instrument_id, h.amount) for h in p.holdings), first=j == 0)
        running = store.replay(ps.account_ref, as_of=cs.as_of, knowledge_cutoff=cs.knowledge_cutoff, cursor=ps.ledger_cursor)
        cash = next(x.amount for x in running.cash_balances if x.account == 'settled_cash' and x.currency == market.currency)
        positions = {h.instrument_id: h.amount for h in running.holdings}
        last_sequence = ps.ledger_cursor
        event_map = {e.body.event_id: e for e in inputs.events}
        for order in orders:
            a = next(attempts, None)
            if a is None:
                raise ContractError()
            bar = bars[j + 1][order.instrument_id]
            fill, fee, tax, reason = fill_terms(order, bar.close.amount, bar.volume.amount, market, costs,
                                               cash, positions.get(order.instrument_id, '0'))
            if (a.instrument_id, a.side, a.quantity, a.decision_price, a.decision_snapshot, a.decision_at,
                    a.fill_at, a.reference_price, a.fill_price, a.reason) != (
                    order.instrument_id, order.side, order.quantity, order.decision_price,
                    nav_point(ps).snapshot, ps.knowledge_cutoff, cs.as_of, bar.close.amount, fill, reason):
                raise ContractError()
            if reason == 'filled':
                fact = facts.get(a.trade.ref)
                if fact is None or fact.trade in used or (fact.quantity, fact.side, fact.reference_price, fact.fill_price,
                        fact.currency, fact.effective_at, fact.quantum, fact.position.instrument_id) != (a.quantity, a.side, a.reference_price,
                        a.fill_price, market.currency, a.fill_at, market.money_quantum, order.instrument_id):
                    raise ContractError()
                source_events = [event_map[fact.trade.ref], *(event_map[x.event.ref] for x in fact.allocations)]
                if event_map[fact.trade.ref].body.sequence <= last_sequence or any(
                        e.body.recorded_at > cs.knowledge_cutoff or e.body.sequence > cs.ledger_cursor for e in source_events):
                    raise ContractError()
                last_sequence = max(e.body.sequence for e in source_events)
                charges = {x.kind: (x.amount, x.rate) for x in fact.allocations}
                expected = {kind: (amount, getattr(costs, kind + '_rate_' + order.side))
                            for kind, amount in (('fee', fee), ('tax', tax)) if number(amount)}
                if charges != expected or fact.base_notional != known(fact.notional, ratio=False):
                    raise ContractError()
                settlement = [e for e in inputs.events if e.body.submission.event_type == 'settlement'
                              and e.body.submission.dependency_refs == (fact.trade.ref,)]
                if len(settlement) != 1 or settlement[0].body.effective_at != fact.effective_at or settlement[0].body.sequence > cs.ledger_cursor:
                    raise ContractError()
                signed = number(order.quantity) * (1 if order.side == 'buy' else -1)
                positions[order.instrument_id] = finite(number(positions.get(order.instrument_id, '0')) + signed)
                cash = finite(number(cash) + (-fact.notional if order.side == 'buy' else fact.notional) - number(fee) - number(tax))
                last_sequence = max(last_sequence, settlement[0].body.sequence)
                used.add(fact.trade)
        actual_cash = next(x.amount for x in cs.valuation.projection.cash_balances
                           if x.account == 'settled_cash' and x.currency == market.currency)
        actual_positions = {h.instrument_id: h.amount for h in cs.valuation.projection.holdings}
        if number(actual_cash) != number(cash) or {k: number(v) for k, v in positions.items() if number(v)} != {
                k: number(v) for k, v in actual_positions.items() if number(v)}:
            raise ContractError()
    if next(attempts, None) is not None or used != {f.trade for f in inputs.costs}:
        raise ContractError()


def _resolve(inputs):
    from quantharbor.adapters.synthetic_research import load_fixed_spec, implementation_fingerprint
    exact(inputs, ExperimentInputs)
    spec = inputs.spec
    if spec != load_fixed_spec() or inputs.fingerprint != implementation_fingerprint():
        raise ContractError()
    registry = inputs.registry
    if registry.spec_hash != hash_record(spec) or registry.actions != 'explicit_none':
        raise ContractError()
    market = next((m for m in spec.markets if m.market_id == inputs.market_id), None)
    fold = next((f for f in spec.folds if f.fold_id == inputs.fold_id), None)
    costs = next((c for c in spec.costs if c.scenario_id == inputs.scenario_id), None)
    if market is None or fold is None or costs is None or len(inputs.points) != len(fold.oos):
        raise ContractError()
    if registry.declared_at >= min(getattr(p, market.market_id).knowledge_cutoff for p in spec.points):
        raise ContractError()
    store = _replay_events(inputs.events)
    first, last = inputs.points[0].snapshot, inputs.points[-1].snapshot
    base = inputs.events[0].body.submission
    # 고정 primary 시나리오는 외부흐름/행동/정정 없음. 일반 흐름 API는 별도로 제공한다.
    if (base.event_type != 'baseline' or base.position_deltas or base.source_revision != 1 or
            any(e.body.submission.event_type not in ('baseline', 'trade', 'fee', 'tax', 'settlement') or
                e.body.kind != 'replacement' or e.body.source_revision != 1 for e in inputs.events)):
        raise ContractError()
    opening_cash = [x for x in base.cash_legs if x.account == 'settled_cash']
    if len(opening_cash) != 1 or (opening_cash[0].amount, opening_cash[0].currency) != (market.initial_cash, market.currency):
        raise ContractError()
    policy = first.valuation.policy
    expected_ids = {'q23.' + market.market_id + '.equity', 'q23.' + market.market_id + '.etf'}
    if ({p.position.instrument_id for p in policy.prices} != expected_ids or policy.fx or
            policy.quantum(market.currency) != market.money_quantum):
        raise ContractError()
    bars = []
    for point, index in zip(inputs.points, fold.oos_indices):
        s = _revalidate_point(point, store)
        if (s.account_ref, s.base_currency, s.valuation.request.scope) != (first.account_ref, market.currency, first.valuation.request.scope):
            raise ContractError()
        if s.valuation.policy != first.valuation.policy or s.valuation.request.scope.coverage != 'entire_account' or s.valuation.request.purpose != 'research':
            raise ContractError()
        bars.append(_point_prices(point, spec, market, index))
    _validate_flows(inputs.points, inputs.boundary_inputs, inputs.boundaries, inputs.events, store)
    if (base.effective_at, inputs.events[0].body.recorded_at) != (first.as_of, first.knowledge_cutoff) or any(
            e.body.recorded_at > last.knowledge_cutoff or e.body.effective_at > last.as_of for e in inputs.events):
        raise ContractError()
    if first.valuation.nav != market.initial_cash or first.ledger_cursor != 1:
        raise ContractError()
    validate_trade_costs(inputs.events, inputs.costs)
    _validate_execution(inputs, store, market, costs, bars)
    refs = [_ref('spec', spec.spec_id, spec), _ref('registry', 'PG02:fixed-registry', registry),
            _ref('fingerprint', 'Q23:implementation-and-lock', inputs.fingerprint), _ref('trace', 'Q23:execution', inputs.trace)]
    refs.extend(_ref('event', e.body.event_id, e.body) for e in inputs.events)
    refs.extend(_ref('cost', f.trade.ref, f) for f in inputs.costs)
    for point in (*inputs.points, *inputs.boundary_inputs):
        refs.append(nav_point(point.snapshot).snapshot)
        refs.extend(_ref('market', d.bundle.descriptor.request.request_id, d.bundle.descriptor) for d in point.market_inputs)
    # 참조는 명시 해소했다. 동일 ID에 다른 hash가 있으면 거부한다.
    indexed = {}
    for ref in refs:
        key = ref.kind, ref.ref
        if key in indexed and indexed[key] != ref:
            raise ContractError()
        indexed[key] = ref
    scope_hash = sha256(b'QuantHarbor/Q23/scope-v1\n' + json.dumps(asdict(first.valuation.request.scope),
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    manifest = ExperimentManifest(1, 'synthetic', first.account_ref, hash_record(spec), market.market_id,
        costs.scenario_id, fold.fold_id, inputs.strategy, first.as_of, last.as_of, market.currency,
        scope_hash, spec.run_at, tuple(indexed[k] for k in sorted(indexed)))
    traded = known(sum((f.base_notional.exact_value for f in inputs.costs), Fraction()), ratio=False)
    performance = calculate_performance(tuple(nav_point(p.snapshot) for p in inputs.points), inputs.boundaries,
                                        traded, unknown('benchmark_missing'))
    rows = []
    for position in first.valuation.policy.prices:
        key = position.position
        fs = tuple(f for f in inputs.costs if f.position == key)
        holding = next((h for h in last.valuation.holdings if h.position.key == key.key), None)
        closing = known(0, ratio=False) if holding is None else (known(number(holding.native_value), ratio=False)
                   if holding.native_value is not None else unknown('native_valuation_unknown'))
        rows.append(calculate_basis(first.account_ref, key, market.currency, market.money_quantum, fs, closing))
    return manifest, performance, tuple(rows)


def build_experiment(inputs, repository, *, benchmark, cash_benchmark, predecessor=None):
    """세 명시 입력군을 재검증해 24가지 중 한 실행을 append하는 안정 API."""
    size = sum(_preflight(x) for x in (inputs, benchmark, cash_benchmark))
    if size > MAX_RESOLVED_BYTES:
        raise ContractError()
    return _build_resolved(_resolve(inputs), repository, _resolve(benchmark), _resolve(cash_benchmark), predecessor)


def _build_resolved(resolved, repository, resolved_benchmark, resolved_cash, predecessor=None):
    manifest, raw, rows = resolved
    benchmark_m, benchmark_p, _ = resolved_benchmark
    cash_m, cash_p, _ = resolved_cash
    def comparable(m):
        return (m.environment, m.spec_hash, m.market_id, m.scenario_id, m.fold_id, m.starts_at,
                m.ends_at, m.base_currency, m.scope_hash, m.created_at)
    for m, p, strategy in ((benchmark_m, benchmark_p, 'buy_hold'), (cash_m, cash_p, 'cash')):
        if m.strategy != strategy or comparable(m) != comparable(manifest) or tuple(x.as_of for x in raw.points) != tuple(x.as_of for x in p.points):
            raise ContractError()
    refs = (*manifest.refs, _ref('benchmark', 'buy_hold:resolved-inputs', benchmark_m),
            _ref('benchmark', 'cash:resolved-inputs', cash_m))
    manifest = replace(manifest, refs=tuple(sorted(refs, key=lambda r: (r.kind, r.ref))), predecessor=predecessor)
    p = calculate_performance(raw.points, raw.flows, raw.traded_notional, benchmark_p.twr)
    facts = tuple(f for row in rows for f in row.facts)
    fees, taxes = (known(sum((number(a.amount) for f in facts for a in f.allocations if a.kind == kind), Fraction()), ratio=False)
                   for kind in ('fee', 'tax'))
    slippage = known(sum((f.slippage for f in facts), Fraction()), ratio=False)
    fx_cost = known(0, ratio=False)  # primary 명시 no-FX. 평가 FX 변화와 구분한다.
    reason_codes = tuple(sorted({r for m in (p.twr, p.amount_pnl, p.observed_mdd, p.gross_turnover,
        p.benchmark_excess, p.benchmark_relative_wealth, cash_p.twr, fees, taxes, slippage, fx_cost,
        *(m for row in rows for m in (row.remaining_basis, row.realized_pnl, row.unrealized_pnl))) for r in m.reason_codes}))
    result = ExperimentResult(1, 'synthetic', 'experiment:' + hash_record(manifest), manifest, p, rows,
        fees, taxes, slippage, fx_cost, cash_p.twr, 'incomplete' if reason_codes else 'complete', reason_codes)
    from quantharbor.adapters.synthetic_research import implementation_fingerprint
    actual_fingerprint = _ref('fingerprint', 'Q23:implementation-and-lock', implementation_fingerprint())
    if actual_fingerprint not in manifest.refs:
        raise ContractError()
    return repository.append(result)


def build_comparison(inputs, repository):
    """고정 24개 입력을 모두 검증하고 빠짐없이 반환한다. 정렬/승자 선택 없음."""
    if type(inputs) is not tuple or len(inputs) != 24:
        raise ContractError()
    expected = {(m, c, f, s) for m in ('KR', 'US') for c in ('explicit_costs', 'zero_cost_control')
                for f in ('fold01', 'fold02') for s in ('cash', 'buy_hold', 'equal_weight_rebalance')}
    by_key = {(x.market_id, x.scenario_id, x.fold_id, x.strategy): x for x in inputs}
    if set(by_key) != expected or len(by_key) != len(inputs):
        raise ContractError()
    sizes = {k: _preflight(v) for k, v in by_key.items()}
    for key in by_key:
        if sizes[key] + sizes[(*key[:3], 'buy_hold')] + sizes[(*key[:3], 'cash')] > MAX_RESOLVED_BYTES:
            raise ContractError()
    # 재사용은 이 호출의 검증된 객체에 한정된다. 전역 hash/객체 cache는 없다.
    resolved = {key: _resolve(value) for key, value in by_key.items()}
    return tuple(_build_resolved(resolved[(x.market_id, x.scenario_id, x.fold_id, x.strategy)], repository,
        resolved[(x.market_id, x.scenario_id, x.fold_id, 'buy_hold')],
        resolved[(x.market_id, x.scenario_id, x.fold_id, 'cash')]) for x in inputs)


@dataclass(frozen=True, slots=True)
class RunSummary:
    market: str
    cost_scenario: str
    fold: str
    strategy: str
    status: str
    twr: str | None
    amount_pnl: str | None
    observed_mdd: str | None
    gross_turnover: str | None
    fees: str | None
    taxes: str | None
    slippage: str | None
    reason_codes: tuple[str, ...]
    result_id: str
    manifest_hash: str
    result_hash: str


def summarize(result):
    exact(result, ExperimentResult)
    m, p = result.manifest, result.performance
    return RunSummary(m.market_id, m.scenario_id, m.fold_id, m.strategy, result.status, p.twr.value,
        p.amount_pnl.value, p.observed_mdd.value, p.gross_turnover.value, result.fees.value, result.taxes.value,
        result.slippage.value, result.reason_codes, result.result_id, hash_record(m), hash_record(result))
