"""실행 위험: 원 후보 재현과 현재 typed 원천/DB 예약 계산을 별도로 수행한다."""
from dataclasses import dataclass, replace
from fractions import Fraction
from uuid import uuid4

from quantharbor.application.approval import validate_source
from quantharbor.application import target as t
from quantharbor.application.research import _revalidate_point
from quantharbor.application.execution_research import (replay_execution_events,
    execution_active_events, build_execution_performance)
from quantharbor.application.valuation import reconcile, value_projection
from quantharbor.domain import execution as d
from quantharbor.domain import approval as approval_domain
from quantharbor.domain.execution_math import cash_with_reservations, sellable, turnover, prospective_loss
from quantharbor.domain.ledger import exact, hash_record
from quantharbor.domain.primitives import utc_instant
from quantharbor.domain.target import cost_bounds, ref as target_ref
from quantharbor.domain.valuation import finite, number
from quantharbor.ports.execution import ExecutionInputs


def validate_current(original, inputs, broker, approval, *, at, generation, projection, intents):
    """호출자는 동일 DB transaction에서 projection/intents/reservations를 읽어야 한다."""
    exact(inputs, ExecutionInputs)
    at = utc_instant(at)
    if generation != (inputs.runtime_generation or original.request.authority_generation):
        raise d.ExecutionDenied('source_unresolved')
    candidate, evidence, _, end = validate_source(original, approval.candidate_ref, at=at, generation=original.request.authority_generation)
    if candidate.body.terms != approval.terms:
        raise d.ExecutionDenied('source_unresolved')
    if (inputs.policy.account_ref != approval.account_ref or
        inputs.policy.target_policy_ref != approval.target_policy_ref or
        not approval.valid_from <= at < approval.expires_at):
        raise d.ExecutionDenied('stale_source')
    _,dependency_end,valuation,performance,request,holdings,market = _validate_account_current(
        original,inputs,broker,at=at,generation=generation,projection=projection,intents=intents)
    dependency_end=min(dependency_end,original.request.expires_at)
    if at >= end:
        raise d.ExecutionDenied('stale_source')
    request=replace(original.request,as_of=request.as_of,knowledge_cutoff=request.knowledge_cutoff,
        evaluated_at=at,snapshot_ref=target_ref('snapshot',inputs.current.current.snapshot.snapshot_id,inputs.current.current.snapshot),
        policy_ref=inputs.policy.target_policy_ref)
    return candidate,evidence,end,dependency_end,valuation,performance,request,holdings,market


def _validate_account_current(original,inputs,broker,*,at,generation,projection,intents):
    """현재 전 계좌 검증. 주문 승인/요청 TTL과 실행 권한을 생성하지 않는다."""
    exact(inputs,ExecutionInputs)
    at=utc_instant(at)
    if generation != (inputs.runtime_generation or original.request.authority_generation):
        raise d.ExecutionDenied('source_unresolved')
    i, q, p = inputs.current, inputs.query, inputs.policy
    broker.verify(q,'query',q.query_id)
    s, facts, policy = i.current.snapshot, i.facts, i.policy
    if facts is None or policy is None:
        raise d.ExecutionDenied('source_unresolved')
    if (p.account_ref != original.request.account_ref or p.target_policy_ref != target_ref('policy',policy.policy_id,policy) or
        p.fixture_ref != d.FIXTURE_REF or number(p.max_gross_turnover) != 1 or
        not p.valid_from <= at < p.valid_to or not policy.valid_from <= at < policy.valid_to or
        q.account_ref != p.account_ref or q.status != 'complete' or q.missing_scope or
        q.requested_scope != q.covered_scope or q.covered_scope != facts.covered_scope or
        facts.requested_scope != facts.covered_scope or facts.missing_scope or facts.status != 'complete' or
        facts.open_orders_status != 'complete' or facts.active_intents_status != 'complete' or
        facts.post_source_status != 'complete' or facts.temporal_consistency != 'aligned' or
        facts.semantics_version != 'synthetic-cash-capacity-v1' or
        projection != s.valuation.projection or projection.ledger_cursor != facts.ledger_cursor or
        facts.projection_ref != target_ref('projection','current-projection',projection) or
        facts.statement_ref != q.statement_ref or facts.loss_performance_ref != target_ref('performance','loss-performance',i.performance) or
        facts.aligned_as_of != s.as_of or facts.knowledge_cutoff != s.knowledge_cutoff or
        facts.open_orders_scope != facts.covered_scope or facts.active_intents_scope != facts.covered_scope or
        not projection.complete or q.as_of != facts.source_as_of or
        q.as_of > at or facts.knowledge_cutoff > at or s.created_at > at):
        raise d.ExecutionDenied('source_unresolved')
    # Independent issuer statement and actual Q20 replay/Q21/Q23 calculations, no allow injection.
    store = replay_execution_events(i.events)
    _revalidate_point(t._historical_point(i.current),store)
    if store.replay(p.account_ref,as_of=projection.as_of,knowledge_cutoff=projection.knowledge_cutoff,
                    cursor=projection.ledger_cursor) != projection:
        raise d.ExecutionDenied('source_unresolved')
    vr = replace(s.valuation.request,evaluated_at=at)
    valuation = value_projection(projection,vr,i.current.market_inputs,s.valuation.policy)
    statement = broker.statement(q)
    reconciled = reconcile(projection,statement,vr,s.reconciliation_policy)
    if not valuation.complete or not reconciled.full_account_balances_matched:
        raise d.ExecutionDenied('reconciliation_required')
    performance = build_execution_performance(tuple(t._historical_point(x) for x in i.risk_points),i.events,
        boundaries=i.boundaries,boundary_inputs=tuple(t._historical_point(x) for x in i.boundary_inputs),
        costs=i.costs,benchmark_return=i.performance.benchmark_return)
    if performance != i.performance or i.risk_points[-1].snapshot != s:
        raise d.ExecutionDenied('source_unresolved')
    request = t._account_context(i,at)
    subject = target_ref('policy',policy.policy_id,policy)
    for point in (*i.risk_points,*i.boundary_inputs,i.current,*i.daily_usage_inputs):
        t._current_rights(point,at,subject,('research','store','report'))
    # Retained originals are still consumed for audit and historical obligations.
    original_grants=[]
    for point in (*original.inputs.risk_points,*original.inputs.boundary_inputs,
                  original.inputs.current,*original.inputs.daily_usage_inputs):
        t._current_rights(point,at,subject,('research','store','report'))
        original_grants.extend(data.current_rights for data in point.market_inputs)
    holdings, market, _ = t._market_rows(i,request,subject)
    dependency_start, dependency_end = t._account_dependency_window(i,request,market,subject)
    dependency_start=max(dependency_start,p.valid_from,policy.daily_window_start,*(g.valid_from for g in original_grants))
    dependency_end=min(dependency_end,p.valid_to,policy.daily_window_end,*(min(g.valid_to,g.revoked_at or g.valid_to) for g in original_grants))
    for info in market.values():
        cap=info['cap']
        if (cap is None or cap.account_ref!=p.account_ref or cap.known_at>request.knowledge_cutoff or
            not cap.valid_from<=at<cap.valid_to):
            raise d.ExecutionDenied('stale_source')
        t._bind(cap.catalog_ref,info['contexts'][0]);t._bind(cap.calendar_ref,info['contexts'][1])
        dependency_start=max(dependency_start,cap.valid_from)
        dependency_end=min(dependency_end,cap.valid_to)
    for rule in facts.cost_rules:
        if rule.account_ref!=p.account_ref or not rule.valid_from<=at<rule.valid_to:
            raise d.ExecutionDenied('stale_source')
        dependency_start=max(dependency_start,rule.valid_from)
        dependency_end=min(dependency_end,rule.valid_to)
    available_rules={(r.market,r.currency,r.side) for r in facts.cost_rules}
    if any((info['instrument'].market,info['instrument'].currency,side) not in available_rules
        for info in market.values() for side in ('buy','sell')):
        raise d.ExecutionDenied('source_unresolved')
    if any(x.terms.position not in market for x in intents):
        raise d.ExecutionDenied('source_unresolved')
    if not dependency_start <= at < dependency_end:
        raise d.ExecutionDenied('stale_source')
    # Account-wide broker open order set must have a request-bound local counterpart.
    known_broker = {x.broker_order_id for x in intents if x.broker_order_id}
    if facts.broker_open_orders or facts.local_active_intents:
        # These Q24 fields lack the required component semantics. Fail closed.
        raise d.ExecutionDenied('source_unresolved')
    for r in q.receipts:
        obj = broker.resolve(r)
        if obj.kind == 'accepted' and obj.broker_order_id not in known_broker:
            raise d.ExecutionDenied('reconciliation_required')
    return dependency_start,dependency_end,valuation,performance,request,holdings,market


def current_risk(original, inputs, broker, approval, *, at, generation, fence,
                 account_version, projection, intents, reservations, exclude_intent=None):
    candidate,evidence,end,dependency_end,valuation,performance,request,holdings,market = validate_current(
        original,inputs,broker,approval,at=at,generation=generation,projection=projection,intents=intents)
    i,q,p = inputs.current,inputs.query,inputs.policy
    facts,policy,subject = i.facts,i.policy,approval.candidate_ref
    active = tuple(x for x in intents if x.state not in d.TERMINAL and x.intent_id != exclude_intent)
    if any(x.accounting!='complete' for x in intents) or any(x.state in ('unknown','dispatching') for x in active):
        raise d.ExecutionDenied('risk_blocked')
    # Exclude only the prospective self hold; already used economics remain bound.
    reserves = tuple(replace(x,held='0',released=finite(number(x.released)+number(x.held)))
        if x.intent_id==exclude_intent else x for x in reservations)
    base = execution_cash_base(i,request,subject,reservations)
    caps = {x.currency:x for x in q.cash}
    if set(caps) != {x.currency for x in base}:
        raise d.ExecutionDenied('source_unresolved')
    cash = tuple(cash_with_reservations(x,reserves,broker_amount=caps[x.currency].amount,
        included=caps[x.currency].included_components,source_cutoff=q.as_of) for x in base)
    terms = approval.terms
    info = market[terms.position]
    cap, session = t._order_context(info,request,subject)
    fee,tax = cost_bounds(terms.cost_rule,terms.quantity)
    if (cap != terms.capability or terms.cost_rule not in facts.cost_rules or
        (fee,tax) != (terms.fee_bound,terms.tax_bound) or not terms.cost_rule.valid_from <= at < terms.cost_rule.valid_to or
        not terms.valid_from <= at < terms.valid_to or
        abs(number(terms.limit_price)-number(info['bar'].close.amount)) > number(info['bar'].close.amount)*number(policy.max_price_deviation)):
        raise d.ExecutionDenied('stale_source')
    burden = number(terms.maximum_burden)
    if burden > number(next(x.available for x in cash if x.currency==terms.currency)):
        raise d.ExecutionDenied('risk_blocked')
    # Holdings already contain confirmed fills. Outstanding orders contain only
    # their remaining quantity and remaining cost, never the approved full quantity.
    orders = tuple(remaining_order(x,reservations) for x in active) + (terms,)
    for order in orders:
        row = market[order.position]
        if (number(order.quantity)>number(policy.max_order_quantity) or
            number(order.quantity)>number(row['bar'].volume.amount)*number(policy.max_volume_participation) or
            number(order.quantity)*number(order.limit_price)*row['fx']+number(order.cost_bound)*row['fx'] > number(policy.max_order_amount)):
            raise d.ExecutionDenied('risk_blocked')
    if terms.side == 'sell':
        sale = next(x for x in facts.sellability_rows if x.position==terms.position)
        broker_qty = next(x for x in q.sellable if x.position==terms.position)
        held = sum((number(r.held) for r in reserves if r.dimension=='quantity' and
            next(x for x in intents if x.intent_id==r.intent_id).terms.position==terms.position),Fraction())
        used = sum((number(r.used)-(number(r.broker_reflected) if r.source_cutoff==q.as_of else 0) for r in reserves if r.dimension=='quantity' and
            r.obligation_id+':used' not in broker_qty.included_components and
            next(x for x in intents if x.intent_id==r.intent_id).terms.position==terms.position),Fraction())
        partial_holds={x.obligation_id:number(x.quantity) for x in broker_qty.hold_reflections}
        unreflected = sum((number(r.held)-partial_holds.get(r.obligation_id,Fraction()) for r in reserves if r.dimension=='quantity' and
            r.obligation_id+':held' not in broker_qty.included_components and
            next(x for x in intents if x.intent_id==r.intent_id).terms.position==terms.position),Fraction())
        bound = sellable(sale.settled_quantity,finite(held),broker_qty.quantity,finite(unreflected),finite(used))
        if number(terms.quantity)>number(bound):
            raise d.ExecutionDenied('risk_blocked')
    nav = number(valuation.nav)
    extra = sum(((number(o.cost_bound)+number(o.quantity)*max(Fraction(),
        number(o.limit_price)-number(market[o.position]['bar'].close.amount) if o.side=='buy' else
        number(market[o.position]['bar'].close.amount)-number(o.limit_price)))*market[o.position]['fx'] for o in orders),Fraction())
    lower = nav-extra
    loss,drawdown = prospective_loss(finite(max(Fraction(),-performance.amount_pnl.exact_value)) if performance.amount_pnl.value is not None else None,
        finite(extra),valuation.nav,performance.observed_mdd.value)
    if lower <= 0 or loss>number(policy.max_loss_amount) or drawdown>number(policy.max_drawdown):
        raise d.ExecutionDenied('risk_blocked')
    groups = {}
    for key,info in market.items():
        price = number(info['bar'].close.amount)*info['fx']
        current = number(holdings.get(key,'0'))*price
        buys = sum((number(o.quantity)*price for o in orders if o.position==key and o.side=='buy'),Fraction())
        sells = sum((number(o.quantity)*price for o in orders if o.position==key and o.side=='sell'),Fraction())
        if sells>current:
            raise d.ExecutionDenied('risk_blocked')
        for dim,name in (('instrument',key.instrument_id),('sector',info['classification'].sector_id),('market',info['instrument'].market),('currency',info['instrument'].currency)):
            groups[(dim,name)] = groups.get((dim,name),Fraction())+current+buys
    limits = {(x.dimension,x.key):x for x in policy.exposure_limits}
    for key,amount in groups.items():
        limit = limits.get(key)
        if limit is None or amount>number(limit.maximum_amount) or amount>lower*number(limit.maximum_weight):
            raise d.ExecutionDenied('risk_blocked')
    for row in cash:
        limit = next(x for x in policy.currency_limits if x.currency==row.currency)
        invested = sum((number(holdings.get(k,'0'))*number(v['bar'].close.amount) for k,v in market.items() if v['instrument'].currency==row.currency),Fraction())
        proposed = number(terms.maximum_burden) if terms.currency==row.currency else Fraction()
        payable = -sum((number(x.amount) for x in projection.cash_balances if x.currency==row.currency and x.account=='unsettled_payable'),Fraction())
        if invested+number(row.outstanding)-payable+proposed>number(limit.funding_limit):
            raise d.ExecutionDenied('risk_blocked')
    if not policy.daily_window_start <= at < policy.daily_window_end:
        raise d.ExecutionDenied('stale_source')
    used = sum((x.notional*t._historical_usage_fx(i,request,x,subject) for x in i.costs if policy.daily_window_start<=x.effective_at<policy.daily_window_end),Fraction())
    used_qty = sum((number(x.quantity) for x in i.costs if policy.daily_window_start<=x.effective_at<policy.daily_window_end),Fraction())
    proposed = sum(((number(o.quantity)*number(o.limit_price)+number(o.cost_bound))*market[o.position]['fx'] for o in orders),Fraction())
    if (used+proposed>number(policy.max_daily_amount) or
        used_qty+sum((number(o.quantity) for o in orders),Fraction())>number(policy.max_daily_quantity) or
        turnover(finite(used),finite(proposed), '0',performance.time_weighted_nav.value)>number(p.max_gross_turnover)):
        raise d.ExecutionDenied('risk_blocked')
    source = d.ExecutionSourceSet('execution-source:'+uuid4().hex,p.account_ref,'synthetic',approval.candidate_ref,
        evidence.plan_ref,evidence.result_ref,evidence.request_ref,candidate.body.input_refs,facts.covered_scope,
        d.ref('query',q.query_id,q),projection.ledger_cursor,account_version,generation,fence,at,min(end,dependency_end))
    decision = d.ExecutionRiskDecision('execution-risk:'+uuid4().hex,p.account_ref,approval.candidate_ref,
        approval_domain.ref('approval',approval.approval_id,approval),hash_record(terms),
        d.ref('source',source.source_id,source),d.ref('policy',p.policy_id,p),at,source.valid_to,account_version,
        projection.ledger_cursor,generation,fence,cash,'allow',())
    return source,decision


@dataclass(frozen=True)
class RemainingOrder:
    position: object
    currency: str
    side: str
    quantity: str
    limit_price: str
    cost_bound: str
    maximum_burden: str


def remaining_order(intent,reservations):
    q = number(intent.terms.quantity)-number(intent.observed_quantity)
    cost = next((r.held for r in reservations if r.intent_id==intent.intent_id and r.component=='cost'),intent.terms.cost_bound)
    burden = q*number(intent.terms.limit_price) if intent.terms.side=='buy' else Fraction()
    return RemainingOrder(intent.terms.position,intent.terms.currency,intent.terms.side,
        finite(q),intent.terms.limit_price,cost,finite(burden+number(cost)))


def build_current_inputs(previous,query,broker,projection,events,*,at,market_inputs=None):
    """Actual DB ledger prefix + issuer statement produce Q21/Q23 typed inputs.

    Q20 전체 bundle을 먼저 재생하고 현재 cutoff의 head만 집계한다.
    원본 events는 현재 입력에 전부 보존하며 Q23 public v1은 유지한다.
    """
    from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
    from quantharbor.application.valuation import build_snapshot
    from quantharbor.domain.research import TradeCostFact,CostAllocation,InputRef,known,unknown
    from quantharbor.domain.valuation import PositionKey,quantize
    from quantharbor.domain.target import SyntheticObligationSource,CashObligation,CashCapacity,Sellability
    from quantharbor.ports.research import ResearchPointInput
    broker.verify(query,'query',query.query_id)
    at = utc_instant(at)
    i = previous.current
    if (i.facts is None or query.account_ref != i.facts.account_ref or
        projection.account_ref != query.account_ref or query.status != 'complete' or query.missing_scope or
        query.requested_scope != query.covered_scope or query.covered_scope != i.facts.covered_scope or
        query.as_of != projection.as_of or query.as_of > at or projection.knowledge_cutoff != at or
        query.as_of < previous.query.as_of or query.cutoff_sequence < previous.query.cutoff_sequence or
        {x.currency for x in query.cash} != set(query.covered_scope.currencies) or
        {x.position for x in query.sellable} != set(query.covered_scope.positions)):
        raise d.ExecutionDenied('source_unresolved')
    for ref in query.events:
        event = broker.resolve(ref)
        if (event.account_ref != query.account_ref or event.effective_at > query.as_of or
            broker._event_sequences[ref] > query.journal_sequence):
            raise d.ExecutionDenied('stale_source')
    old = i.current.snapshot
    statement = broker.statement(query)
    market_inputs = i.current.market_inputs if market_inputs is None else market_inputs
    vr = replace(old.valuation.request,request_id='execution-current:'+uuid4().hex,as_of=projection.as_of,
        knowledge_cutoff=projection.knowledge_cutoff,evaluated_at=at,ledger_cursor=projection.ledger_cursor)
    active_events = execution_active_events(events,projection)
    snap = build_snapshot(projection,vr,market_inputs,old.valuation.policy,old.reconciliation_policy,
        SyntheticSnapshotRepository(),statement=statement)
    if not snap.valuation.complete or not snap.reconciliation_details.full_account_balances_matched:
        raise d.ExecutionDenied('reconciliation_required')
    point = ResearchPointInput(snap,market_inputs)
    first = i.risk_points[0]
    if first.snapshot.as_of>=snap.as_of:
        raise d.ExecutionDenied('stale_source')
    points = (first,point)
    costs = []
    for e in active_events:
        b,sub = e.body,e.body.submission
        if sub.event_type!='trade': continue
        quantity = abs(number(sub.position_deltas[0].amount))
        principal = abs(number(next(x.amount for x in sub.cash_legs if x.account.startswith('unsettled_'))))
        price = principal/quantity
        currency = sub.cash_legs[0].currency
        quantum = next(x.quantum for x in snap.valuation.policy.quantums if x.currency==currency)
        allocations = []
        for c in active_events:
            cb,cs = c.body,c.body.submission
            if cs.event_type in ('fee','tax') and cs.dependency_refs==(b.event_id,):
                amount = -number(next(x.amount for x in cb.cash_legs if x.account=='settled_cash'))
                rate = quantize(amount/principal,'0.000000000000000001')
                allocations.append(CostAllocation(InputRef('event',cb.event_id,hash_record(cb)),
                    cb.source_revision,cs.event_type,finite(amount),rate))
        costs.append(TradeCostFact(1,'synthetic',b.account_ref,InputRef('event',b.event_id,hash_record(b)),
            b.source_revision,PositionKey(*sub.position_deltas[0].key),currency,b.effective_at,
            'buy' if number(sub.position_deltas[0].amount)>0 else 'sell',finite(quantity),finite(price),finite(price),
            quantum,tuple(allocations),known(principal,ratio=False) if currency==snap.base_currency else unknown('trade_base_fx_unknown')))
    performance = build_execution_performance(points,events,costs=tuple(costs),benchmark_return=i.performance.benchmark_return)
    # Preserve external original obligations; derive every local payable from actual
    # Q20 trade/settlement dependencies. No invented all-account empty facts.
    local_ids = {e.body.event_id for e in events if e.body.source_kind=='synthetic-execution'}
    sources = [x for x in i.obligation_sources if x.ledger_event_ref is None or x.ledger_event_ref.id not in local_ids]
    obligations = [x for x in i.facts.obligations if x.source_ref in {target_ref('obligation_source',v.source_id,v) for v in sources}]
    for e in active_events:
        b = e.body
        if b.source_kind!='synthetic-execution' or b.kind!='replacement' or b.submission.event_type!='trade': continue
        for leg in b.cash_legs:
            if leg.account!='unsettled_payable': continue
            paid = sum((number(l.amount) for x in active_events if x.body.submission.event_type=='settlement' and
                x.body.submission.dependency_refs==(b.event_id,) for l in x.body.cash_legs if l.account=='unsettled_payable'),Fraction())
            amount = -number(leg.amount)-paid
            if amount<=0: continue
            identity = 'local-payable:'+b.event_id
            source = SyntheticObligationSource(1,'synthetic',identity,b.account_ref,identity,leg.currency,
                finite(amount),'buy_commitment',b.effective_at,'outstanding',target_ref('event',b.event_id,b))
            sources.append(source)
            obligations.append(CashObligation(identity,target_ref('obligation_source',identity,source),leg.currency,
                finite(amount),'buy_commitment',b.effective_at,'outstanding',False,False))
    holdings = {PositionKey(*x.key):number(x.amount) for x in projection.holdings}
    settled_trades = {ref for e in active_events if e.body.submission.event_type=='settlement' for ref in e.body.submission.dependency_refs}
    pending_buys = {}
    for e in active_events:
        if e.body.submission.event_type=='trade' and e.body.event_id not in settled_trades:
            for pos in e.body.position_deltas:
                if number(pos.amount)>0:
                    key = PositionKey(*pos.key)
                    pending_buys[key] = pending_buys.get(key,Fraction())+number(pos.amount)
    broker_qty = {x.position:x for x in query.sellable}
    sales = tuple(Sellability(k,finite(holdings.get(k,Fraction())-pending_buys.get(k,Fraction())),broker_qty[k].quantity,'0','0',())
        for k in query.covered_scope.positions)
    facts = replace(i.facts,source_snapshot_id='execution-facts:'+uuid4().hex,source_as_of=query.as_of,
        aligned_as_of=snap.as_of,observed_at=at,ingested_at=at,knowledge_cutoff=at,
        ledger_cursor=projection.ledger_cursor,projection_ref=target_ref('projection','current-projection',projection),
        statement_ref=query.statement_ref,cash_capacity_rows=tuple(CashCapacity(x.currency,x.amount,'account_currency',
            'cash_only_no_auto_fx',tuple(o.obligation_id for o in obligations if o.currency==x.currency and o.reflected_in_B)) for x in query.cash),
        obligations=tuple(obligations),sellability_rows=sales,post_source_cash_changes=(),
        daily_usage_event_refs=tuple(target_ref('event',x.body.event_id,x.body) for x in active_events if x.body.submission.event_type=='trade'),
        loss_performance_ref=target_ref('performance','loss-performance',performance))
    return ExecutionInputs(replace(i,current=point,events=events,facts=facts,risk_points=points,
        performance=performance,costs=tuple(costs),obligation_sources=tuple(sources)),query,previous.policy,previous.runtime_generation)


def execution_cash_base(inputs,request,subject,reservations):
    """Q24 validates complete obligations; local Q20 portions move to reservations once."""
    # Q24 v1's payable walker understands original trades/settlements. Only the
    # internally derived, fully replayed current heads enter that economic check;
    # the authoritative input retains every original and reversal event.
    active = execution_active_events(inputs.events,inputs.current.snapshot.valuation.projection)
    base = t._cash_rows(replace(inputs,events=active),request,subject)
    represented = {ref for r in reservations for ref in r.ledger_refs}
    sources = {target_ref('obligation_source',x.source_id,x):x for x in inputs.obligation_sources}
    result = []
    for row in base:
        h,u,d = map(number,(row.outstanding,row.unreflected,row.post_source_debits))
        for obligation in inputs.facts.obligations:
            origin = sources[obligation.source_ref].ledger_event_ref
            if obligation.currency!=row.currency or origin is None or origin.id not in represented:
                continue
            amount = number(obligation.amount)
            if obligation.outstanding_or_realized=='outstanding':
                h -= amount
                if not obligation.reflected_in_B: u -= amount
            elif not obligation.reflected_in_B: d -= amount
        available = t.available_cash(row.ledger_cash,finite(h),row.floor,row.broker_capacity,finite(u),finite(d))
        result.append(replace(row,outstanding=finite(h),unreflected=finite(u),post_source_debits=finite(d),
            available=available,remaining=finite(number(available)-number(row.planned_burden))))
    return tuple(result)


class ExecutionApplication:
    def __init__(self,repository):
        from quantharbor.adapters.postgres_execution import PostgresExecutionRepository
        if type(repository) is not PostgresExecutionRepository:
            raise d.ExecutionDenied('authority_denied')
        self._repository = repository

    def dispatch(self,handle,intent_id):
        return self._repository.dispatch(handle,intent_id)

    def receive(self,event):
        return self._repository.receive(event)

    def cancel(self,handle,intent_id,*,command_id,expected_version):
        return self._repository.cancel(handle,intent_id,command_id=command_id,expected_version=expected_version)

    def reconcile(self,handle,query):
        return self._repository.reconcile(handle,query)

    def dispatch_cancel(self,handle,command_id):
        return self._repository.dispatch_cancel(handle,command_id)

    def rebind(self,handle,query,*,market_inputs=None,execution_policy=None):
        return self._repository.rebind(handle,query,market_inputs=market_inputs,execution_policy=execution_policy)

    def control(self,handle,action):
        return self._repository.control(handle,action)

    def cancel_receipt(self,handle,command_id,*,intent_id,expected_version):
        return self._repository.cancel_receipt(handle,command_id,intent_id=intent_id,expected_version=expected_version)

    def resolve_unsent(self,handle,intent_id):
        return self._repository.resolve_unsent(handle,intent_id)
