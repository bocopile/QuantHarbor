"""Q27 실행 전용 Q20 bundle 재생과 Q21/Q23 성과. public Q23 v1은 보존한다."""
from fractions import Fraction

from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.application.research import (
    _resolved_bytes, _revalidate_point, _validate_flows, _validate_trade_cost_facts,
    nav_point,
)
from quantharbor.domain.ledger import LedgerEvent, exact
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.research import MAX_INPUTS, Metric, known, unique, unknown
from quantharbor.ports.research import ResearchPointInput
from quantharbor.research.metrics import calculate_performance


def replay_execution_events(events):
    """제공된 전체 이력을 replacement submission 당 한 번 실제 Q20으로 재생한다.

    decision 이력 없는 cursor gap은 복원하거나 건너뛰지 않는다. quarantine,
    누락 bundle, 미해결 dependency는 완전한 현재 성과의 근거가 될 수 없다.
    """
    _resolved_bytes((), events)
    if not events or len(events) > MAX_INPUTS:
        raise ContractError()
    store = SyntheticLedger()
    account = events[0].body.account_ref
    index = 0
    while index < len(events):
        first = events[index]
        exact(first, LedgerEvent)
        width = 2 if first.body.kind == 'reversal' else 1
        bundle = events[index:index + width]
        if len(bundle) != width:
            raise ContractError()
        replacement = bundle[-1]
        if (replacement.body.kind != 'replacement' or
                (replacement.body.submission.source_revision > 1) != (width == 2) or
                any(e.body.account_ref != account for e in bundle)):
            raise ContractError()
        state = store.state(account)
        before = len(state.events)
        result = store.append(replacement.body.submission, recorded_at=replacement.body.recorded_at)
        if result.status != 'accepted' or tuple(store.state(account).events[before:]) != bundle:
            raise ContractError()
        index += width
    if tuple(store.state(account).events) != events:
        raise ContractError()
    return store


def _active_at(store, projection):
    actual = store.replay(projection.account_ref, as_of=projection.as_of,
        knowledge_cutoff=projection.knowledge_cutoff, cursor=projection.ledger_cursor)
    if actual != projection or not actual.complete:
        raise ContractError()
    selected = tuple(e for e in store.state(projection.account_ref).events
        if e.body.sequence <= projection.ledger_cursor and
        e.body.recorded_at <= projection.knowledge_cutoff and e.body.effective_at <= projection.as_of)
    reversed_ids = {e.body.correction_of for e in selected if e.body.kind == 'reversal'}
    # External flow revisions keep Q23 v1's explicit unsupported boundary.
    if any(e.body.submission.event_type in ('deposit', 'withdrawal') and
           (e.body.kind != 'replacement' or e.body.submission.source_revision != 1) for e in selected):
        raise ContractError()
    return tuple(e for e in selected if e.body.kind == 'replacement' and e.body.event_id not in reversed_ids)


def execution_active_events(events, projection):
    """필터링 전에 전체 이력 및 요청한 Q20 projection을 검증한다."""
    return _active_at(replay_execution_events(events), projection)


def build_execution_performance(points, events, *, boundaries=(), boundary_inputs=(), costs=(),
                                benchmark_return=Metric(None, ('benchmark_missing',))):
    """실제 Q21 snapshot·flow·현재 trade/cost head에서 기존 Q23 산식을 계산한다."""
    _resolved_bytes((*points, *boundary_inputs), events)
    unique(points, ResearchPointInput, lambda p: p.snapshot.snapshot_id)
    unique(boundary_inputs, ResearchPointInput, lambda p: p.snapshot.snapshot_id)
    if len(points) < 2:
        raise ContractError()
    if any((p.snapshot.account_ref, p.snapshot.base_currency, p.snapshot.valuation.request.scope) !=
           (points[0].snapshot.account_ref, points[0].snapshot.base_currency, points[0].snapshot.valuation.request.scope)
           for p in (*points, *boundary_inputs)):
        raise ContractError()
    store = replay_execution_events(events)
    for point in (*points, *boundary_inputs):
        _revalidate_point(point, store)
        _active_at(store, point.snapshot.valuation.projection)
    _validate_flows(points, boundary_inputs, boundaries, events, store)
    active = _active_at(store, points[-1].snapshot.valuation.projection)
    _validate_trade_cost_facts(active, costs)
    measured = tuple(f for f in costs if points[0].snapshot.as_of < f.effective_at <= points[-1].snapshot.as_of)
    currency = points[0].snapshot.base_currency
    notional = (known(sum((f.notional for f in measured), Fraction()), ratio=False)
                if all(f.currency == currency for f in measured) else unknown('trade_base_fx_unknown'))
    return calculate_performance(tuple(nav_point(p.snapshot) for p in points), boundaries, notional, benchmark_return)
