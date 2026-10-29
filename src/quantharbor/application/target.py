"""Q24 원천 결속 목표 builder. 적격은 승인/예약/제출 권한이 아니다."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from fractions import Fraction
import json

from quantharbor.application.market_ingest import context_refs, select_view
from quantharbor.application.research import (_encoded, _replay_events, _resolved_bytes,
    _revalidate_point, build_bound_performance)
from quantharbor.application.valuation import reconcile, value_projection
from quantharbor.domain.ledger import exact, hash_record
from quantharbor.domain.market_data import FXObservation, PriceBar, item_ref
from quantharbor.domain.primitives import ContractError, utc_instant
from quantharbor.domain.research import known
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.target import (CANONICAL, MAX_INPUTS, MAX_RESOLVED_BYTES, CandidateBody,
    AccountCalculation, CashCalculation, DisplayTerms, ExposureCalculation, OrderCandidate, OrderTerms, TargetBuildResult,
    TargetFailure, TargetPlan, TargetPlanBody, TargetPosition, TargetRef, TargetRequest, TargetResultBody,
    TargetScope, available_cash, cost_bounds, ref, weight_quantity)
from quantharbor.domain.valuation import PositionKey, finite, number, quantize
from quantharbor.ports.research import ResearchPointInput
from quantharbor.ports.target import TargetArtifacts, TargetInputs
from quantharbor.ports.valuation import MarketDatasetInput


class _Blocked(Exception):
    def __init__(self, code, subject, required, status):
        self.failure = TargetFailure(code, subject, required, status)


def _require(condition, code, subject, required, status='unknown'):
    if not condition:
        raise _Blocked(code, subject, required, status)


def context_target_refs(data):
    """Q16 별도 source-facts digest를 canonical hash로 잘못 표시하지 않는다."""
    return tuple(TargetRef(x.kind, x.kind + ':' + x.sha256, 1, 'context-source-facts-v1', x.sha256)
                 for x in context_refs(data.catalog, data.calendar, data.timezone))


def _preflight(inputs, request):
    if type(inputs) is not TargetInputs:
        raise ContractError()
    # 사건·자료를 해소하기 전에 집합과 각 canonical 객체의 크기를 제한한다.
    points = (*inputs.risk_points, *inputs.boundary_inputs, *inputs.daily_usage_inputs)
    if inputs.current not in points:
        points += (inputs.current,)
    total = _resolved_bytes(points, inputs.events)
    for obj in (request, inputs.strategy, inputs.performance, inputs.policy, inputs.facts,
                *inputs.obligation_sources, *inputs.costs, *inputs.boundaries):
        if obj is not None:
            env = getattr(obj, 'environment', 'synthetic')
            total += len(canonical_bytes(CanonicalPayload(type(obj).__name__, 1, env, obj)))
    if total > MAX_RESOLVED_BYTES:
        raise ContractError()
    return total


def _bind(given, expected):
    if given != expected:
        raise ContractError()


def _historical_point(point):
    """현재 권리와 과거 snapshot의 권리 증빙을 분리해 모두 검증한다."""
    proofs = point.snapshot.valuation.market_proofs
    data = []
    for supplied in point.market_inputs:
        req = supplied.bundle.descriptor.request
        grants = {p.rights for p in proofs if p.selection.dataset_key == (req.source_id, req.dataset_id, req.dataset_version)}
        if len(grants) != 1:
            raise ContractError()
        historical = next(iter(grants))
        # 같은 참조의 현재 갱신만 허용한다. 과거 grant 치환으로 불일치를 지우지 않는다.
        _bind(supplied.current_rights.rights_ref, historical.rights_ref)
        data.append(replace(supplied, current_rights=historical))
    return ResearchPointInput(point.snapshot, tuple(data))


def _current_rights(point, at, subject, purposes=('research', 'store')):
    for data in point.market_inputs:
        req = data.bundle.descriptor.request
        for purpose in purposes:
            _require(data.current_rights.allows(at=at, purpose=purpose, source_id=req.source_id,
                dataset_id=req.dataset_id, dataset_version=req.dataset_version),
                'rights_denied', subject, purpose, 'denied')


def _source(inputs, request, subject):
    s, policy, facts = inputs.current.snapshot, inputs.policy, inputs.facts
    _bind(request.snapshot_ref, ref('snapshot', s.snapshot_id, s))
    _bind(request.strategy_ref, ref('strategy', inputs.strategy.strategy_id, inputs.strategy))
    _bind(request.policy_ref, ref('policy', policy.policy_id, policy))
    _bind(request.research_refs, (ref('performance', 'loss-performance', inputs.performance),))
    _require(all(x.account_ref == request.account_ref for x in (s, policy, facts, inputs.strategy)),
        'source_incomplete', subject, 'account_binding', 'mismatch')
    _require((s.as_of, s.knowledge_cutoff) == (request.as_of, request.knowledge_cutoff) and s.created_at <= request.evaluated_at,
        'temporal_mismatch', subject, 'snapshot_time', 'mismatch')
    _require(s.projection_mode == 'as_known' and s.supersedes_snapshot_id is None and
        all(e.body.source_revision == 1 and e.body.kind == 'replacement' and e.body.submission.revision_mode == 'original' for e in inputs.events),
        'source_semantics_unknown', subject, 'original_as_known_inputs', 'unsupported_correction')
    _require(s.reconciliation_details.full_account_balances_matched and s.reconciliation == 'matched',
        'reconciliation_incomplete', subject, 'entire_account_statement')
    _require(s.valuation.complete and s.valuation.nav is not None and number(s.valuation.nav) > 0,
        'nav_unknown', subject, 'positive_complete_nav')
    _require(len(inputs.risk_points) >= 2 and inputs.risk_points[-1].snapshot == s,
        'loss_limit', subject, 'current_bound_performance', 'missing')
    _require((inputs.risk_points[0].snapshot.as_of, inputs.risk_points[-1].snapshot.as_of) ==
        (policy.risk_window_start, policy.risk_window_end) and policy.risk_window_end == request.as_of,
        'loss_limit', subject, 'risk_window', 'mismatch')
    points = (*inputs.risk_points, *inputs.boundary_inputs, inputs.current, *inputs.daily_usage_inputs)
    for point in points:
        _current_rights(point, request.evaluated_at, subject)
        _require(point.snapshot.projection_mode == 'as_known' and point.snapshot.supersedes_snapshot_id is None,
                 'source_semantics_unknown', subject, 'as_known', 'unsupported_correction')
    _require(all(e.body.recorded_at <= request.knowledge_cutoff and e.body.effective_at <= request.as_of for e in inputs.events),
        'temporal_mismatch', subject, 'current_ledger_event_prefix', 'future_event')
    _require(all(p.snapshot.as_of <= request.as_of and p.snapshot.knowledge_cutoff <= request.knowledge_cutoff and
        p.snapshot.created_at <= request.evaluated_at for p in points),
        'temporal_mismatch', subject, 'current_risk_knowledge_prefix', 'future_point')
    store = _replay_events(inputs.events)
    _revalidate_point(_historical_point(inputs.current), store)
    for point in inputs.daily_usage_inputs:
        _require(point.snapshot.account_ref == request.account_ref and point.snapshot.base_currency == s.base_currency,
            'source_incomplete', subject, 'historical_daily_account_currency', 'mismatch')
        _revalidate_point(_historical_point(point), store)
    performance = build_bound_performance(tuple(_historical_point(p) for p in inputs.risk_points), inputs.events,
        boundaries=inputs.boundaries, boundary_inputs=tuple(_historical_point(p) for p in inputs.boundary_inputs),
        costs=inputs.costs, benchmark_return=inputs.performance.benchmark_return)
    _bind(inputs.performance, performance)
    _require(performance.amount_pnl.value is not None and performance.observed_mdd.value is not None,
        'loss_limit', subject, 'complete_loss_performance')
    _require(max(Fraction(), -performance.amount_pnl.exact_value) <= number(policy.max_loss_amount) and
        performance.observed_mdd.exact_value <= number(policy.max_drawdown), 'loss_limit', subject, 'loss_drawdown', 'exceeded')
    current_request = replace(s.valuation.request, evaluated_at=request.evaluated_at)
    valuation = value_projection(s.valuation.projection, current_request, inputs.current.market_inputs, s.valuation.policy)
    _require(valuation.complete and valuation.nav == s.valuation.nav,
        'source_incomplete', subject, 'current_market_valuation', 'incomplete')
    statement = s.reconciliation_details.statement
    compared = reconcile(s.valuation.projection, statement, current_request, s.reconciliation_policy)
    _require(compared.full_account_balances_matched, 'reconciliation_incomplete', subject, 'current_reconciliation')
    _bind(facts.projection_ref, ref('projection', 'current-projection', s.valuation.projection))
    _bind(facts.statement_ref, ref('statement', statement.snapshot.statement_id, statement))
    _bind(facts.loss_performance_ref, request.research_refs[0])
    _require(facts.status == 'complete' and not facts.missing_scope and
        facts.requested_scope == facts.covered_scope, 'source_incomplete', subject, 'complete_scope', facts.status)
    _require(facts.semantics_version == 'synthetic-cash-capacity-v1',
        'source_semantics_unknown', subject, 'cash_capacity_semantics')
    _require(facts.temporal_consistency == 'aligned' and facts.aligned_as_of == request.as_of and
        facts.knowledge_cutoff == request.knowledge_cutoff and facts.ledger_cursor == s.ledger_cursor and
        facts.knowledge_cutoff <= request.evaluated_at,
        'temporal_mismatch', subject, 'aligned_complete_facts', facts.temporal_consistency)
    age = datetime.fromisoformat(request.evaluated_at) - datetime.fromisoformat(facts.source_as_of)
    _require(age < timedelta(seconds=policy.max_account_age_seconds), 'stale_input', subject, 'account_freshness', 'stale')
    _require(facts.open_orders_status == 'complete' and facts.open_orders_scope == facts.covered_scope,
        'open_orders_unknown', subject, 'complete_account_open_orders', facts.open_orders_status)
    _require(facts.active_intents_status == 'complete' and facts.active_intents_scope == facts.covered_scope,
        'active_intent_conflict', subject, 'complete_account_active_intents', facts.active_intents_status)
    _require(not facts.broker_open_orders and not facts.local_active_intents,
        'active_intent_conflict', subject, 'empty_active_orders', 'unsupported_active_orders')
    _require(facts.post_source_status == 'complete', 'source_incomplete', subject, 'post_source_cash_changes')
    complete_cursor = max((e.body.sequence for e in inputs.events if e.body.recorded_at <= request.knowledge_cutoff), default=0)
    _require(s.ledger_cursor == complete_cursor, 'source_incomplete', subject, 'complete_ledger_cursor', 'incomplete')
    expected_changes = tuple(sorted((ref('event', e.body.event_id, e.body) for e in inputs.events
        if facts.source_as_of < e.body.effective_at <= request.as_of and e.body.sequence <= s.ledger_cursor
        and any(x.account == 'settled_cash' for x in e.body.cash_legs)), key=lambda r: r.id))
    _require(facts.post_source_cash_changes == expected_changes, 'source_incomplete', subject, 'complete_cash_changes', 'incomplete')
    return valuation


def _ledger_payables(inputs, request, subject):
    """원본 매수 사건별 잔여채무. 채권이나 다른 매수채무와 상계하지 않는다."""
    payables = {}
    for event in inputs.events:
        b = event.body
        for leg in b.cash_legs:
            if leg.account == 'unsettled_payable' and number(leg.amount) < 0:
                _require(b.submission.event_type == 'trade', 'source_semantics_unknown', subject,
                    'identified_payable_trade', 'unsupported')
                payables[(b.event_id, leg.currency)] = [ref('event', b.event_id, b), -number(leg.amount)]
            elif leg.account == 'unsettled_payable' and number(leg.amount) > 0:
                deps = b.submission.dependency_refs
                _require(b.submission.event_type == 'settlement' and len(deps) == 1 and
                    (deps[0], leg.currency) in payables, 'source_semantics_unknown', subject,
                    'identified_payable_settlement', 'unsupported')
                row = payables[(deps[0], leg.currency)]
                row[1] -= number(leg.amount)
                _require(row[1] >= 0, 'source_incomplete', subject, 'payable_remaining', 'mismatch')
    remaining = {r: (code, amount) for (_, code), (r, amount) in payables.items() if amount}
    for cash in inputs.current.snapshot.cash_by_currency:
        amount = sum((amount for code, amount in remaining.values() if code == cash.currency), Fraction())
        _require(amount == -number(cash.unsettled_payable), 'source_incomplete', subject,
            'ledger_payable_projection', 'mismatch')
    return remaining


def _cash_rows(inputs, request, subject):
    facts, policy, s = inputs.facts, inputs.policy, inputs.current.snapshot
    sources = {ref('obligation_source', x.source_id, x): x for x in inputs.obligation_sources}
    events = {ref('event', e.body.event_id, e.body): e for e in inputs.events}
    used_sources, realized_events = set(), set()
    payables, linked_payables = _ledger_payables(inputs, request, subject), set()
    balances = {x.currency: number(x.settled_cash) for x in s.cash_by_currency}
    caps = {x.currency: x for x in facts.cash_capacity_rows}
    limits = {x.currency: x for x in policy.currency_limits}
    codes = set(balances) | set(caps) | set(limits)
    _require(set(caps) == codes and set(limits) == codes, 'policy_missing', subject, 'all_currency_limits_and_capacity', 'missing')
    h = {c: Fraction() for c in codes}
    u, d = h.copy(), h.copy()
    reflected = {c: set() for c in codes}
    for row in facts.obligations:
        source = sources.get(row.source_ref)
        if source is None:
            raise ContractError()
        used_sources.add(row.source_ref)
        if (source.account_ref, source.obligation_id, source.currency, source.amount, source.kind,
                source.effective_at, source.status) != (request.account_ref, row.obligation_id, row.currency,
                row.amount, row.kind, row.effective_at, row.outstanding_or_realized):
            raise ContractError()
        _require(row.currency in codes and row.effective_at <= request.as_of,
            'source_incomplete', subject, 'obligation_currency_time', 'mismatch')
        _require(row.outstanding_or_realized != 'unknown', 'source_semantics_unknown', subject, 'obligation_status')
        cap = caps[row.currency]
        in_b = row.obligation_id in cap.reflected_obligation_ids
        if row.reflected_in_B != in_b:
            raise ContractError()
        if in_b:
            reflected[row.currency].add(row.obligation_id)
        if row.outstanding_or_realized == 'outstanding':
            if row.reflected_in_L:
                raise ContractError()
            if source.ledger_event_ref is not None:
                origin = events.get(source.ledger_event_ref)
                if (source.ledger_event_ref in linked_payables or origin is None or
                        payables.get(source.ledger_event_ref) != (row.currency, number(row.amount)) or
                        row.effective_at != origin.body.effective_at or row.kind != 'buy_commitment'):
                    raise ContractError()
                linked_payables.add(source.ledger_event_ref)
            h[row.currency] += number(row.amount)
            if not in_b:
                u[row.currency] += number(row.amount)
        else:
            event = events.get(source.ledger_event_ref)
            if event is None or source.ledger_event_ref in realized_events or not row.reflected_in_L:
                raise ContractError()
            legs = [x for x in event.body.cash_legs if x.account == 'settled_cash' and x.currency == row.currency]
            if (event.body.effective_at != row.effective_at or len(legs) != 1 or number(legs[0].amount) != -number(row.amount)):
                raise ContractError()
            realized_events.add(source.ledger_event_ref)
            if not in_b:
                _require(facts.source_as_of < row.effective_at <= request.as_of,
                    'source_semantics_unknown', subject, 'unreflected_debit_time', 'unsupported')
                d[row.currency] += number(row.amount)
    if used_sources != set(sources) or any(set(caps[c].reflected_obligation_ids) != reflected[c] for c in codes):
        raise ContractError()
    _require(linked_payables == set(payables), 'source_incomplete', subject,
        'complete_ledger_payable_obligations', 'missing')
    # 반영 안 된 모든 원장 차감은 한 의무의 realized 부분으로 정확히 한 번 설명해야 한다.
    for r in facts.post_source_cash_changes:
        event = events[r]
        if any(x.account == 'settled_cash' and number(x.amount) < 0 for x in event.body.cash_legs):
            _require(r in realized_events, 'source_incomplete', subject, 'cash_debit_obligation', 'missing')
    result = []
    for code in sorted(codes):
        cap, limit = caps[code], limits[code]
        _require(cap.capacity_scope == 'account_currency', 'capacity_scope_unsupported', subject, 'account_currency_capacity', cap.capacity_scope)
        _require(cap.capacity_basis == 'cash_only_no_auto_fx', 'source_semantics_unknown', subject, 'cash_only_capacity')
        floor = max(number(limit.cash_floor), *(number(x.minimum) for x in request.cash_targets if x.currency == code), Fraction())
        l = balances.get(code, Fraction())
        a = available_cash(finite(l), finite(h[code]), finite(floor), cap.amount, finite(u[code]), finite(d[code]))
        result.append(CashCalculation(code, finite(l), finite(h[code]), finite(floor), cap.amount,
            finite(u[code]), finite(d[code]), a, '0', a))
    return tuple(result)


@dataclass(frozen=True)
class _AccountContext:
    account_ref: str
    as_of: str
    knowledge_cutoff: str
    evaluated_at: str
    scope: object
    expires_at: str
    cash_targets: tuple = ()


def _account_context(inputs,at):
    """주문 요청을 만들지 않는다. horizon은 실제 현재 정책 만료다."""
    s=inputs.current.snapshot
    return _AccountContext(s.account_ref,s.as_of,s.knowledge_cutoff,at,
        inputs.facts.covered_scope,inputs.policy.valid_to)


def _market_rows(inputs, request, subject):
    """계좌 전체 보유와 요청 scope의 가격·분류·매핑·세션을 해소한다."""
    s, policy, facts = inputs.current.snapshot, inputs.policy, inputs.facts
    _require(all(k.mapping_version == facts.mapping_version for k in facts.covered_scope.positions),
        'mapping_unknown', subject, 'facts_mapping_version', 'mismatch')
    holdings = {PositionKey(*x.position.key): x.position.amount for x in s.holdings if number(x.position.amount)}
    keys = set(holdings) | set(request.scope.positions)
    _require(set(request.scope.markets) <= set(policy.allowed_markets) and
        set(request.scope.currencies) <= set(policy.allowed_currencies),
        'proposal_infeasible', subject, 'request_scope_policy', 'excluded')
    classes = {x.position: x for x in facts.classifications}
    capabilities = {x.position: x for x in facts.capabilities}
    available = {}
    all_contexts = []
    selections = {x.position: x.series for x in s.valuation.policy.prices}
    held_refs = {PositionKey(*x.position.key): x.price_ref for x in s.holdings if number(x.position.amount)}
    for data in inputs.current.market_inputs:
        req = data.bundle.descriptor.request
        contexts = context_target_refs(data)
        all_contexts.extend(contexts)
        view = select_view(data.bundle.state.revisions, as_of=request.as_of, knowledge_cutoff=request.knowledge_cutoff,
            rights=data.current_rights, at=request.evaluated_at, dataset_version=req.dataset_version,
            catalog=data.catalog, calendar=data.calendar, timezone=data.timezone, purpose='research')
        _require(not view.held_reasons and data.bundle.envelope.quality.status == 'complete',
            'source_incomplete', subject, 'complete_current_market', 'incomplete')
        for item in view.selected:
            bar = item.revision.payload
            if type(bar) is not PriceBar:
                continue
            resolution = data.catalog.resolve(req.source_id, bar.source_code, bar.listing_venue_id,
                bar.execution_venue_id, as_of=request.as_of, knowledge_cutoff=request.knowledge_cutoff)
            current_resolution = data.catalog.resolve(req.source_id, bar.source_code, bar.listing_venue_id,
                bar.execution_venue_id, as_of=request.evaluated_at, knowledge_cutoff=request.knowledge_cutoff)
            _require(resolution is not None and resolution == current_resolution and resolution.eligible_for_initial_scope,
                'mapping_unknown', subject, 'eligible_catalog_mapping')
            key = PositionKey(bar.instrument_id, bar.execution_venue_id, resolution.mapping.mapping_version, bar.close.quantity_unit)
            if key not in keys:
                continue
            selection = selections.get(key)
            _require(selection is not None, 'mapping_unknown', subject, 'explicit_Q21_price_selection', 'missing')
            if (selection.dataset_key, selection.series_id) != ((req.source_id, req.dataset_id, req.dataset_version), item.revision.series_id):
                continue
            series = [x for x in view.selected if x.revision.series_id == selection.series_id]
            latest = max(x.revision.effective_at for x in series)
            matches = [x for x in series if x.revision.effective_at == latest]
            _require(len(matches) == 1, 'source_incomplete', subject, 'unambiguous_latest_Q21_price', 'ambiguous')
            if item != matches[0]:
                continue
            if key in held_refs:
                _bind(held_refs[key], item_ref(item))
            _require(bar.adjustment == 'raw' and item.revision.revision_kind == 'original' and
                item.revision.predecessor_revision_id is None, 'source_semantics_unknown', subject, 'original_raw_price', 'unsupported_correction')
            if key in available:
                raise ContractError()
            instrument = resolution.instrument
            _require(key not in request.scope.positions or (instrument.market in request.scope.markets and instrument.currency in request.scope.currencies),
                'mapping_unknown', subject, 'scope_market_currency', 'mismatch')
            _require(key in policy.allowed_positions and instrument.market in policy.allowed_markets and
                instrument.currency in policy.allowed_currencies, 'proposal_infeasible', subject, 'allowed_universe', 'excluded')
            _require(instrument.market in facts.covered_scope.markets and key in facts.covered_scope.positions,
                'source_incomplete', subject, 'entire_account_positions', 'incomplete')
            classification = classes.get(key)
            _require(classification is not None and classification.effective_from <= request.as_of < classification.effective_to
                and classification.effective_from <= request.evaluated_at < classification.effective_to
                and classification.known_at <= request.knowledge_cutoff,
                'source_incomplete', subject, 'explicit_sector_classification')
            cap = capabilities.get(key)
            ingest_age = data.bundle.descriptor.limits.max_age_seconds
            price_age = min(policy.max_price_age_seconds, s.valuation.policy.max_price_age_seconds,
                ingest_age if ingest_age is not None else policy.max_price_age_seconds)
            price_end = _plus(item.revision.effective_at, price_age)
            _require(number(bar.close.amount) > 0 and bar.volume is not None and number(bar.volume.amount) > 0,
                'source_incomplete', subject, 'positive_price_volume')
            if instrument.currency == s.base_currency:
                fx = Fraction(1)
                fx_end = request.expires_at
            else:
                native = next((x for x in s.valuation.native_totals if x.currency == instrument.currency), None)
                _require(native is not None and native.fx is not None, 'nav_unknown', subject, 'current_fx')
                fx = number(native.fx.rate) if native.fx_direction == 'multiply' else 1 / number(native.fx.rate)
                fx_end = _plus(native.fx.as_of, policy.max_fx_age_seconds)
            available[key] = dict(bar=bar, instrument=instrument, classification=classification, cap=cap,
                data=data, fx=fx, fx_end=fx_end, price_end=price_end, contexts=contexts,
                mapping_end=resolution.mapping.valid_to or request.expires_at,
                instrument_end=instrument.valid_to or request.expires_at)
    _require(set(available) == keys, 'mapping_unknown', subject, 'all_position_prices', 'missing')
    _require(set(facts.covered_scope.currencies) >= {x.currency for x in s.cash_by_currency},
        'source_incomplete', subject, 'all_account_currencies', 'missing')
    return holdings, available, tuple(all_contexts)


def _plus(at, seconds):
    try:
        return utc_instant(datetime.fromisoformat(at) + timedelta(seconds=seconds))
    except (ValueError, OverflowError):
        raise ContractError() from None


def _account_dependency_window(inputs, request, market, subject):
    """전체계좌 평가/위험 근거의 현재 소비권리와 신선도 교집합."""
    s, policy = inputs.current.snapshot, inputs.policy
    starts = [policy.valid_from, inputs.facts.observed_at, inputs.facts.ingested_at,
        s.created_at, s.knowledge_cutoff]
    ends = [request.expires_at, policy.valid_to,
        _plus(inputs.facts.source_as_of, policy.max_account_age_seconds),
        _plus(s.as_of, policy.max_account_age_seconds)]
    statement = s.reconciliation_details.statement
    if statement is not None:
        ends.append(_plus(statement.snapshot.source_as_of, policy.max_account_age_seconds))
    for point in (*inputs.risk_points, *inputs.boundary_inputs, inputs.current, *inputs.daily_usage_inputs):
        for data in point.market_inputs:
            grant = data.current_rights
            starts.append(grant.valid_from)
            ends.extend((grant.valid_to, grant.revoked_at or grant.valid_to))
    for info in market.values():
        ends.extend((info['price_end'], info['fx_end'], info['mapping_end'], info['instrument_end'],
            info['classification'].effective_to))
        starts.append(info['classification'].effective_from)
    for total in s.valuation.native_totals:
        if total.currency == s.base_currency:
            continue
        _require(total.fx is not None, 'nav_unknown', subject, 'all_account_fx')
        selection = next((x.series for x in s.valuation.policy.fx if x.native_currency == total.currency), None)
        _require(selection is not None, 'nav_unknown', subject, 'all_account_fx_selection')
        from quantharbor.domain.valuation import validate_ref
        item = validate_ref(s.valuation, total.fx_ref, selection)
        data = next(x for x in inputs.current.market_inputs if
            (x.bundle.descriptor.request.source_id, x.bundle.descriptor.request.dataset_id,
             x.bundle.descriptor.request.dataset_version) == selection.dataset_key)
        ages = [policy.max_fx_age_seconds, s.valuation.policy.max_fx_age_seconds]
        if data.bundle.descriptor.limits.max_age_seconds is not None:
            ages.append(data.bundle.descriptor.limits.max_age_seconds)
        ends.append(_plus(item.revision.effective_at, min(ages)))
    start, end = max(starts), min(ends)
    _require(start <= request.evaluated_at < end, 'stale_input', subject, 'all_account_dependency_window', 'expired')
    return start, end


def _dependency_window(inputs,request,market,subject):
    start,end=_account_dependency_window(inputs,request,market,subject)
    return max(start,request.evaluated_at),end


def _historical_usage_fx(inputs, request, fact, subject):
    """TradeCostFact의 원장결속 후 독립 과거 종목/통화/FX 원본을 해소한다."""
    events = {e.body.event_id: e for e in inputs.events}
    event = events.get(fact.trade.ref)
    if event is None:
        raise ContractError()
    cutoff = min(event.body.recorded_at, request.knowledge_cutoff)
    conversions = set()
    for point in (*inputs.risk_points, *inputs.boundary_inputs, *inputs.daily_usage_inputs):
        policy = point.snapshot.valuation.policy
        selection = next((x.series for x in policy.prices if x.position == fact.position), None)
        if selection is None:
            continue
        data = next((d for d in point.market_inputs if (d.bundle.descriptor.request.source_id,
            d.bundle.descriptor.request.dataset_id, d.bundle.descriptor.request.dataset_version) == selection.dataset_key), None)
        if data is None:
            continue
        mappings = [m for m in data.catalog.mappings if (m.instrument_id, m.execution_venue_id,
            m.mapping_version, m.source_id) == (*fact.position.key[:3], selection.source_id)]
        resolutions = [data.catalog.resolve(m.source_id, m.source_code, m.listing_venue_id, m.execution_venue_id,
            as_of=fact.effective_at, knowledge_cutoff=cutoff) for m in mappings]
        resolutions = [x for x in resolutions if x is not None and x.eligible_for_initial_scope]
        if len(resolutions) != 1 or resolutions[0].instrument.currency != fact.currency:
            continue
        if fact.currency == inputs.current.snapshot.base_currency:
            conversions.add((fact.effective_at, Fraction(1)))
            continue
        fx_selection = next((x.series for x in policy.fx if x.native_currency == fact.currency), None)
        if fx_selection is None:
            continue
        fxdata = next((d for d in point.market_inputs if (d.bundle.descriptor.request.source_id,
            d.bundle.descriptor.request.dataset_id, d.bundle.descriptor.request.dataset_version) == fx_selection.dataset_key), None)
        if fxdata is None:
            continue
        # _source가 실제 Q17 재생/Q21 재구축으로 결속한 해당 series 증거를 검사한다.
        # 부분 입력을 건너뛰면 더 낮은 다른 환율로 되돌아갈 수 있으므로 명시 차단한다.
        proofs = [p for p in point.snapshot.valuation.market_proofs if p.selection == fx_selection]
        _require(len(proofs) == 1 and proofs[0].usable, 'source_incomplete', subject,
            'complete_historical_daily_fx_proof', 'incomplete')
        view = select_view(fxdata.bundle.state.revisions, as_of=fact.effective_at, knowledge_cutoff=cutoff,
            rights=fxdata.current_rights, at=request.evaluated_at, dataset_version=fx_selection.dataset_version,
            catalog=fxdata.catalog, calendar=fxdata.calendar, timezone=fxdata.timezone, purpose='research')
        items = [x for x in view.selected if x.revision.series_id == fx_selection.series_id]
        if view.held_reasons or not items:
            continue
        latest = max(x.revision.effective_at for x in items)
        chosen = [x for x in items if x.revision.effective_at == latest]
        if len(chosen) != 1 or type(chosen[0].revision.payload) is not FXObservation:
            continue
        item = chosen[0]
        if item.revision.revision_kind != 'original' or item.revision.predecessor_revision_id is not None:
            continue
        age = datetime.fromisoformat(fact.effective_at) - datetime.fromisoformat(latest)
        if age > timedelta(seconds=min(policy.max_fx_age_seconds, inputs.policy.max_fx_age_seconds)):
            continue
        fx = item.revision.payload.fx
        base = inputs.current.snapshot.base_currency
        if (fx.base_currency, fx.quote_currency) == (fact.currency, base):
            conversions.add((latest, number(fx.rate)))
        elif (fx.base_currency, fx.quote_currency) == (base, fact.currency):
            conversions.add((latest, 1 / number(fx.rate)))
    # 과거 snapshot에 포함된 이전 FX는 중복/상충이 아니다. 사건시점까지
    # 알려진 검증된 원본 중 최신 시각을 고른 뒤 동시각 상충만 차단한다.
    latest = max((at for at, _ in conversions), default=None)
    rates = {rate for at, rate in conversions if at == latest}
    _require(len(rates) == 1, 'mapping_unknown', subject, 'historical_daily_instrument_currency_fx', 'missing_or_ambiguous')
    return next(iter(rates))


def _positions(request, holdings, market, nav, policy, subject):
    target = {x.position: x for x in request.targets}
    _require((request.mode, request.omission_rule) in (('full', 'zero'), ('partial', 'keep')),
        'ambiguous_omission', subject, 'explicit_omission_rule', request.omission_rule)
    result = []
    for key in sorted(set(holdings) | set(request.scope.positions), key=lambda x: x.key):
        current, residual = number(holdings.get(key, '0')), Fraction()
        row, info = target.get(key), market[key]
        lot_text = info['cap'].lot if info['cap'] is not None else '1'
        lot = number(lot_text)
        if row is not None:
            if request.target_basis == 'quantity':
                desired = number(row.value)
                _require(desired % lot == 0, 'lot_violation', subject, 'target_lot', 'not_multiple')
            else:
                _require(info['cap'] is not None, 'capability_unknown', subject, 'weight_target_lot')
                _require(number(row.value) <= 1, 'proposal_infeasible', subject, 'absolute_account_weight', 'exceeded')
                units = number(nav) * number(row.value) / (number(info['bar'].close.amount) * info['fx']) / lot
                desired = (units.numerator // units.denominator) * lot
                residual = number(row.value) - desired * number(info['bar'].close.amount) * info['fx'] / number(nav)
                _require(residual <= number(policy.max_rounding_error), 'proposal_infeasible', subject, 'weight_rounding_error', 'exceeded')
        else:
            desired = Fraction() if request.mode == 'full' and key in request.scope.positions else current
        delta = desired - current
        _require(delta % lot == 0, 'lot_violation', subject, 'difference_lot', 'not_multiple')
        result.append(TargetPosition(key, finite(current), finite(desired), finite(delta),
            quantize(residual, '0.000000000000000001'), str(residual.numerator), str(residual.denominator),
            known(number(info['bar'].close.amount) * info['fx'], ratio=False), lot_text))
    return tuple(result)


def _order_context(info, request, subject):
    cap = info['cap']
    _require(cap is not None, 'capability_unknown', subject, 'instrument_capability')
    _bind(cap.catalog_ref, info['contexts'][0])
    _bind(cap.calendar_ref, info['contexts'][1])
    _require((cap.market, cap.currency, cap.account_ref) == (info['instrument'].market,
        info['instrument'].currency, request.account_ref) and cap.known_at <= request.knowledge_cutoff and
        cap.valid_from <= request.evaluated_at < cap.valid_to,
        'capability_unknown', subject, 'current_account_capability', 'expired_or_mismatch')
    data = info['data']
    session = data.timezone.lookup_calendar(data.calendar, request.evaluated_at, knowledge_cutoff=request.knowledge_cutoff)
    _require(session.regular_session_eligible, 'calendar_ineligible', subject, 'regular_session', session.status)
    return cap, session.session


def _orders(inputs, request, positions, market, cash, subject):
    policy, facts = inputs.policy, inputs.facts
    cash_map = {x.currency: x for x in cash}
    cumulative = {x.currency: Fraction() for x in cash}
    sells = {x.position: x for x in facts.sellability_rows}
    target = {x.position: x for x in request.targets}
    result = []
    contexts = {row.position: _order_context(market[row.position], request, subject)
        for row in positions if number(row.difference)}
    dependency_start, dependency_end = _dependency_window(inputs, request, market, subject)
    for row in positions:
        if not number(row.difference):
            continue
        info, q = market[row.position], abs(number(row.difference))
        bar = info['bar']
        cap, session = contexts[row.position]
        side = 'buy' if number(row.difference) > 0 else 'sell'
        rules = [x for x in facts.cost_rules if (x.account_ref, x.market, x.currency, x.side) ==
            (request.account_ref, info['instrument'].market, bar.close.currency, side)]
        _require(len(rules) == 1, 'cost_bound_unknown', subject, 'whole_order_cost_rule')
        rule = rules[0]
        _require(rule.valid_from <= request.evaluated_at < rule.valid_to, 'cost_bound_unknown', subject, 'current_cost_rule', 'expired')
        specified = target.get(row.position)
        reference = number(bar.close.amount)
        tick = number(cap.tick)
        if specified is not None and specified.limit_price is not None:
            price = number(specified.limit_price)
            _require(price % tick == 0, 'tick_violation', subject, 'limit_price_tick', 'not_multiple')
        else:
            units = reference / tick
            price = ((units.numerator // units.denominator) if side == 'buy' else -(-units.numerator // units.denominator)) * tick
        _require(price > 0 and abs(price - reference) <= reference * number(policy.max_price_deviation),
            'proposal_infeasible', subject, 'price_deviation', 'exceeded')
        _require(number(cap.min_quantity) <= q <= number(cap.max_quantity) and
            number(cap.min_notional) <= q * price <= number(cap.max_notional),
            'proposal_infeasible', subject, 'capability_quantity_notional', 'exceeded')
        _require(q <= number(policy.max_order_quantity) and q <= number(bar.volume.amount) * number(policy.max_volume_participation),
            'proposal_infeasible', subject, 'order_quantity_participation', 'exceeded')
        fee, tax = cost_bounds(rule, finite(q))
        cost = number(fee) + number(tax)
        _require((q * price + cost) * info['fx'] <= number(policy.max_order_amount),
            'proposal_infeasible', subject, 'order_amount', 'exceeded')
        if side == 'sell':
            sale = sells.get(row.position)
            _require(sale is not None and not sale.obligation_refs and not number(sale.reserved_quantity) and not number(sale.unreflected_sell_quantity),
                'sellability_unknown', subject, 'independent_sellability', 'missing_or_unsupported_obligation')
            sellable = min(number(row.current_quantity), number(sale.settled_quantity) - number(sale.reserved_quantity),
                number(sale.broker_sellable_quantity) - number(sale.unreflected_sell_quantity))
            _require(q <= sellable, 'sellability_unknown', subject, 'settled_broker_sellability', 'insufficient')
        principal = q * price if side == 'buy' else Fraction()
        burden = principal + cost
        code = bar.close.currency
        _require(code in cash_map, 'source_incomplete', subject, 'order_currency_cash', 'missing')
        cumulative[code] += burden
        remaining = number(cash_map[code].available) - cumulative[code]
        _require(remaining >= 0, 'cash_shortfall', subject, 'aggregate_planned_burden', 'exceeded')
        grant = info['data'].current_rights
        valid_from = max(request.evaluated_at, policy.valid_from, cap.valid_from, rule.valid_from,
            grant.valid_from, session.starts_at, dependency_start)
        valid_to = min(request.expires_at, policy.valid_to, _plus(request.evaluated_at, policy.candidate_ttl_seconds),
            cap.valid_to, rule.valid_to, grant.valid_to, grant.revoked_at or grant.valid_to,
            _plus(bar.ends_at, policy.max_price_age_seconds), info['fx_end'],
            _plus(facts.source_as_of, policy.max_account_age_seconds), session.ends_at,
            info['mapping_end'], info['instrument_end'], info['classification'].effective_to, dependency_end)
        _require(valid_from < valid_to, 'expired', subject, 'nonempty_submission_window', 'empty')
        result.append(OrderTerms(request.account_ref, row.position, info['contexts'][0], info['instrument'].market,
            code, side, finite(q), bar.close.amount, finite(price), cap, rule, fee, tax, finite(cost),
            finite(principal), finite(q * price if side == 'sell' else Fraction()), finite(burden),
            finite(cumulative[code]), finite(remaining), valid_from, valid_to))
    # 정확한 candidate 순서가 누적 부담의 순서다.
    result = tuple(sorted(result, key=lambda x: (x.position.instrument_id, x.position.venue_id, x.side)))
    running, adjusted = {c: Fraction() for c in cash_map}, []
    for order in result:
        running[order.currency] += number(order.maximum_burden)
        adjusted.append(replace(order, cumulative_burden=finite(running[order.currency]),
            remaining_capacity=finite(number(cash_map[order.currency].available) - running[order.currency])))
    cash = tuple(replace(x, planned_burden=finite(running[x.currency]),
        remaining=finite(number(x.available) - running[x.currency])) for x in cash)
    return tuple(adjusted), cash


def _ceiling(value, quantum):
    q = number(quantum)
    units = value / q
    return -(-units.numerator // units.denominator) * q


def _floor(value, quantum):
    q = number(quantum)
    units = value / q
    return (units.numerator // units.denominator) * q


def _constraints(inputs, request, market, positions, orders, cash, subject):
    policy, s = inputs.policy, inputs.current.snapshot
    nav = number(s.valuation.nav)
    loss = sum(((number(o.cost_bound) + number(o.quantity) * max(Fraction(),
        number(o.limit_price) - number(o.reference_price) if o.side == 'buy' else
        number(o.reference_price) - number(o.limit_price))) * market[o.position]['fx'] for o in orders), Fraction())
    quantum = s.valuation.policy.quantum(s.base_currency)
    # Q21 표시/평가 quantum의 half-even 증액을 NAV 하한으로 재사용하지 않는다.
    native = {x.currency: x for x in s.valuation.native_totals}
    cash_value = Fraction()
    for row in s.cash_by_currency:
        total = native[row.currency]
        fx = (Fraction(1) if row.currency == s.base_currency else
            (number(total.fx.rate) if total.fx_direction == 'multiply' else 1 / number(total.fx.rate)))
        cash_value += number(row.economic_cash) * fx
    exact_nav = cash_value + sum((number(p.current_quantity) * number(market[p.position]['bar'].close.amount) *
        market[p.position]['fx'] for p in positions), Fraction())
    loss = _ceiling(loss + max(Fraction(), nav - exact_nav), quantum)
    lower = nav - loss
    _require(lower > 0, 'nav_unknown', subject, 'conservative_nav_lower_bound', 'nonpositive')
    order_map = {x.position: x for x in orders}
    groups = {}
    for row in positions:
        info, order = market[row.position], order_map.get(row.position)
        price = number(info['bar'].close.amount) * info['fx']
        current = number(row.current_quantity) * price
        low = current - (number(order.quantity) * price if order and order.side == 'sell' else Fraction())
        high = current + (number(order.quantity) * price if order and order.side == 'buy' else Fraction())
        for dim, key in (('instrument', row.position.instrument_id), ('sector', info['classification'].sector_id),
                         ('market', info['instrument'].market), ('currency', info['instrument'].currency)):
            values = groups.setdefault((dim, key), [Fraction(), Fraction(), Fraction()])
            for i, amount in enumerate((current, low, high)):
                values[i] += amount
    limits = {(x.dimension, x.key): x for x in policy.exposure_limits}
    _require(set(groups) <= set(limits), 'policy_missing', subject, 'all_account_exposure_limits', 'missing')
    exposures = []
    for (dim, key), (current, low, high) in sorted(groups.items()):
        limit = limits[(dim, key)]
        current, low, high = _ceiling(current, quantum), _floor(low, quantum), _ceiling(high, quantum)
        _require(high <= number(limit.maximum_amount) and high <= lower * number(limit.maximum_weight),
            'exposure_limit', subject, 'one_sided_fill_exposure', 'exceeded')
        exposures.append(ExposureCalculation(dim, key, finite(current), finite(low), finite(high),
            finite(lower), limit.maximum_amount, limit.maximum_weight))
    for row in cash:
        invested = sum((number(p.current_quantity) * number(market[p.position]['bar'].close.amount)
            for p in positions if market[p.position]['instrument'].currency == row.currency), Fraction())
        limit = next(x for x in policy.currency_limits if x.currency == row.currency)
        _require(invested + number(row.outstanding) + number(row.planned_burden) <= number(limit.funding_limit),
            'exposure_limit', subject, 'currency_funding_limit', 'exceeded')
        _require(number(row.remaining) >= 0, 'cash_shortfall', subject, 'cash_floor', 'exceeded')
    _require(policy.daily_window_start <= request.as_of < policy.daily_window_end,
        'daily_limit', subject, 'current_daily_window', 'mismatch')
    daily = tuple(sorted((ref('event', e.body.event_id, e.body) for e in inputs.events if
        policy.daily_window_start <= e.body.effective_at < policy.daily_window_end and
        e.body.effective_at <= request.as_of and e.body.submission.event_type == 'trade'), key=lambda r: r.id))
    _bind(inputs.facts.daily_usage_event_refs, daily)
    used_amount, used_quantity = Fraction(), Fraction()
    daily_ids = {r.id for r in daily}
    for fact in inputs.costs:
        if fact.trade.ref in daily_ids:
            used_amount += fact.notional * _historical_usage_fx(inputs, request, fact, subject)
            used_quantity += number(fact.quantity)
    proposed_amount = sum(((number(o.quantity) * number(o.limit_price) + number(o.cost_bound)) * market[o.position]['fx'] for o in orders), Fraction())
    proposed_quantity = sum((number(o.quantity) for o in orders), Fraction())
    used_amount, proposed_amount = _ceiling(used_amount, quantum), _ceiling(proposed_amount, quantum)
    _require(used_amount + proposed_amount <= number(policy.max_daily_amount) and
        used_quantity + proposed_quantity <= number(policy.max_daily_quantity), 'daily_limit', subject, 'aggregate_daily_usage', 'exceeded')
    calculation = AccountCalculation(finite(nav), finite(loss), finite(lower), finite(used_amount),
        finite(used_quantity), finite(proposed_amount), finite(proposed_quantity), policy.max_daily_amount,
        policy.max_daily_quantity, finite(max(Fraction(), -inputs.performance.amount_pnl.exact_value)),
        inputs.performance.observed_mdd, policy.max_loss_amount, policy.max_drawdown)
    return tuple(exposures), calculation


def validate_predecessor(prior, request):
    if type(prior) is not TargetPlan:
        raise ContractError()
    previous = prior.body.request
    if (previous.environment, previous.account_ref, previous.scope, previous.mode, previous.target_basis) != (
            request.environment, request.account_ref, request.scope, request.mode, request.target_basis):
        raise ContractError()
    if request.as_of < previous.as_of or request.knowledge_cutoff < previous.knowledge_cutoff or request.evaluated_at < previous.evaluated_at:
        raise ContractError()
    _bind(request.predecessor_plan_ref, ref('plan', prior.plan_id, prior))


def _finish(request, inputs, repository, refs, positions=(), orders=(), cash=(), exposures=(), calculation=None, failures=()):
    env = request.environment
    body = TargetPlanBody(1, env, request.account_ref, request, refs, positions, orders, cash, exposures, calculation,
        'blocked' if failures else 'eligible', failures, inputs.policy)
    plan = TargetPlan('target-plan:' + ref('plan', 'identity', body).sha256, body)
    plan_ref = ref('plan', plan.plan_id, plan)
    candidates = []
    for index, order in enumerate(orders):
        strategy = inputs.strategy
        display = DisplayTerms('target-ko-v1', 'ko-KR', request.account_ref, order.position.instrument_id,
            strategy.rationale, strategy.risks, '합성 전체 주문 비용 상한이며 부분체결 횟수와 무관합니다.',
            '표시한 종료시각은 제외하며 이후 최신 근거를 다시 검사해야 합니다.', strategy.synthetic_notice)
        cb = CandidateBody(1, env, request.account_ref, request.authority_generation, plan_ref, index,
            request.policy_ref, refs, order, display)
        candidates.append(OrderCandidate('candidate:' + hash_record(cb), cb))
    rb = TargetResultBody(1, env, request.account_ref, ref('request', request.request_id, request), plan_ref,
        tuple(ref('candidate', c.candidate_id, c) for c in candidates), 'blocked' if failures else 'eligible',
        'none' if failures else ('orders' if orders else 'no_change'), failures)
    result = TargetBuildResult('target-result:' + ref('result', 'identity', rb).sha256, rb)
    return repository.append(TargetArtifacts(plan, tuple(candidates), result))


def build_target(request, inputs, repository):
    """source-bound 공개 API. 명시 합성 객체 없이는 후보를 만들지 않는다."""
    if type(request) is not TargetRequest:
        raise ContractError()
    request = parse_payload(canonical_bytes(CanonicalPayload('TargetRequest', 1, request.environment, request))).payload
    _preflight(inputs, request)
    def normalize(point):
        return replace(point, market_inputs=tuple(replace(data) for data in point.market_inputs))
    inputs = replace(inputs, current=normalize(inputs.current),
        risk_points=tuple(normalize(p) for p in inputs.risk_points),
        boundary_inputs=tuple(normalize(p) for p in inputs.boundary_inputs),
        daily_usage_inputs=tuple(normalize(p) for p in inputs.daily_usage_inputs))
    subject = ref('request', request.request_id, request)
    s = inputs.current.snapshot
    all_refs = [subject, ref('snapshot', s.snapshot_id, s), ref('strategy', inputs.strategy.strategy_id, inputs.strategy),
        ref('performance', 'loss-performance', inputs.performance), ref('projection', 'current-projection', s.valuation.projection)]
    if inputs.policy is not None:
        all_refs.append(ref('policy', inputs.policy.policy_id, inputs.policy))
    if inputs.facts is not None:
        all_refs.append(ref('facts', inputs.facts.source_snapshot_id, inputs.facts))
    statement = s.reconciliation_details.statement
    if statement is not None:
        all_refs.append(ref('statement', statement.snapshot.statement_id, statement))
    for data in inputs.current.market_inputs:
        all_refs.extend(context_target_refs(data))
        all_refs.extend((ref('rights', data.current_rights.rights_ref, data.current_rights),
            ref('market', data.bundle.descriptor.request.request_id, data.bundle.descriptor)))
    for point in (*inputs.risk_points, *inputs.boundary_inputs, *inputs.daily_usage_inputs):
        all_refs.append(ref('snapshot', point.snapshot.snapshot_id, point.snapshot))
        for data in point.market_inputs:
            grant_ref = ref('rights', 'rights-evidence', data.current_rights)
            all_refs.append(replace(grant_ref, id='rights:' + grant_ref.sha256))
    all_refs.extend(ref('cost', 'trade-cost:' + fact.trade.ref, fact) for fact in inputs.costs)
    refs = tuple(sorted(set(all_refs), key=lambda x: (x.kind, x.id)))
    if len({(x.kind, x.id) for x in refs}) != len(refs):
        raise ContractError()
    if request.predecessor_plan_ref is not None:
        validate_predecessor(repository.get(request.predecessor_plan_ref, environment=request.environment,
            account_ref=request.account_ref), request)
    try:
        _require(request.environment == 'synthetic', 'environment_blocked', subject, 'synthetic_environment', request.environment)
        _require(inputs.policy is not None and request.policy_ref is not None, 'policy_missing', subject, 'explicit_synthetic_policy', 'missing')
        _require(inputs.facts is not None, 'source_incomplete', subject, 'explicit_synthetic_facts', 'missing')
        policy = inputs.policy
        _require(policy.valid_from <= request.evaluated_at < policy.valid_to and request.evaluated_at < request.expires_at,
            'expired', subject, 'current_policy_request', 'expired')
        _source(inputs, request, subject)
        cash = _cash_rows(inputs, request, subject)
        holdings, market, contexts = _market_rows(inputs, request, subject)
        positions = _positions(request, holdings, market, inputs.current.snapshot.valuation.nav, policy, subject)
        orders, cash = _orders(inputs, request, positions, market, cash, subject)
        exposures, calculation = _constraints(inputs, request, market, positions, orders, cash, subject)
        return _finish(request, inputs, repository, refs, positions, orders, cash, exposures, calculation)
    except _Blocked as error:
        return _finish(request, inputs, repository, refs, failures=(error.failure,))


def render_candidate(candidate, repository, market_inputs, *, at):
    """현재 report 권리를 해소한 뒤 exact hash의 금융조건·문구만 표시한다."""
    if type(candidate) is not OrderCandidate or type(market_inputs) is not tuple or len(market_inputs) > MAX_INPUTS:
        raise ContractError()
    candidate = parse_payload(_encoded(candidate)).payload
    at = utc_instant(at)
    b = candidate.body
    stored = repository.get(ref('candidate', candidate.candidate_id, candidate), environment=b.environment, account_ref=b.account_ref)
    if stored != candidate:
        raise ContractError()
    expected = {r.id: r for r in b.input_refs if r.kind == 'market'}
    if len(market_inputs) != len(expected):
        raise ContractError()
    seen = set()
    for data in market_inputs:
        exact(data, MarketDatasetInput)
        data = replace(data)
        descriptor = data.bundle.descriptor
        _bind(expected.get(descriptor.request.request_id), ref('market', descriptor.request.request_id, descriptor))
        if descriptor.request.request_id in seen:
            raise ContractError()
        seen.add(descriptor.request.request_id)
        req, rights = descriptor.request, data.current_rights
        if not rights.allows(at=at, purpose='report', source_id=req.source_id, dataset_id=req.dataset_id, dataset_version=req.dataset_version):
            raise ContractError()
    t, d = b.terms, b.display_terms
    action = '매수' if t.side == 'buy' else '매도'
    return (f'합성 주문 후보 · {d.account_label} · {d.instrument_label} {t.quantity}주 {action} · '
        f'지정가 {t.limit_price} {t.currency} · 비용 최대 {t.cost_bound} {t.currency} · '
        f'최대 필요자금 {t.maximum_burden} {t.currency} · 매도 최저 총대금 {t.minimum_sale_proceeds} {t.currency} · '
        f'{t.capability.time_in_force} · {t.valid_from}부터 {t.valid_to} 미만 · '
        f'{d.rationale} · 위험: {" / ".join(d.risks)} · {d.cost_explanation} · {d.expiry_explanation} · '
        f'{d.synthetic_notice} · 승인 전이며 주문은 전송되지 않았습니다.')


def candidate_json(candidate):
    return json.loads(_encoded(candidate))
