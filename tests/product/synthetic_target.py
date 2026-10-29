"""Q24 독립 합성 사실. 실제 Q16/Q17/Q20/Q21/Q23 경로를 연결한다."""
from dataclasses import replace
from datetime import datetime, timedelta
from hashlib import sha256

from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.adapters.synthetic_market import SyntheticPageAdapter
from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
from quantharbor.application.market_ingest import ingest
from quantharbor.application.research import build_bound_performance
from quantharbor.application.target import build_target, context_target_refs
from quantharbor.application.valuation import build_snapshot
from quantharbor.domain.catalog import Catalog, Instrument, SymbolMapping
from quantharbor.domain.ledger import CashBalance, PositionDelta, hash_record
from quantharbor.domain.market_data import (ExpectedEvent, FetchRequest, IngestLimits, MarketItem,
    MarketObservation, MarketRevision, PageResult, PriceBar, QueryScope, RightsGrant, record_hash)
from quantharbor.domain.primitives import Price, Quantity, utc_instant
from quantharbor.domain.target import (CashCapacity, CashObligation, CashTarget, Classification, CurrencyLimit,
    ExposureLimit, Sellability, SyntheticCostRule, SyntheticObligationSource, SyntheticOrderCapability,
    SyntheticStrategyProposal, SyntheticTargetFacts, SyntheticTargetPolicy, TargetRequest, TargetScope, TargetValue, ref)
from quantharbor.domain.valuation import (BalanceScope, CashTolerance, CurrencyQuantum, DOMAINS, PositionKey,
    PriceSelection, QuantityTolerance, ReconciliationPolicy, SeriesSelection, StatementSourceSnapshot,
    SyntheticAccountStatement, ValuationPolicy, ValuationRequest)
from quantharbor.ports.research import ResearchPointInput
from quantharbor.ports.target import TargetInputs
from quantharbor.ports.valuation import MarketDatasetInput
from synthetic_ledger import baseline, cash_pair
from synthetic_timezones import KNOWN, synthetic_timezone
from test_calendar import calendar, trading_day, session


def fixture(*, market='US', cash='1000', holdings=('0', '0'), prices=('100', '100'), targets=('3', '4'),
            mode='partial', basis='quantity', lot='1', fee='2', obligations=False, scope_indices=(0, 1)):
    """기본 302+402=704, 합성 A800. 기대값은 테스트에서 독립 상수로 선언한다."""
    account = 'synthetic-account:q24:' + market
    code = 'USD' if market == 'US' else 'KRW'
    zone = synthetic_timezone(market)
    start = utc_instant('2024-03-08T14:30:00Z' if market == 'US' else '2024-03-08T00:30:00Z')
    end = utc_instant(datetime.fromisoformat(start) + timedelta(minutes=1))
    current_at = utc_instant(datetime.fromisoformat(end) + timedelta(seconds=1))
    now = utc_instant(datetime.fromisoformat(end) + timedelta(seconds=3))
    expires = utc_instant(datetime.fromisoformat(now) + timedelta(seconds=30))
    keys = tuple(PositionKey('q24.' + suffix, 'q24.venue', 'q24-mapping-v1', 'share') for suffix in ('A', 'B'))
    instruments = tuple(Instrument(k.instrument_id, 'v1', 'q24.listing', market, code,
        'equity' if i == 0 else 'etf', 'not_applicable' if i == 0 else 'general', 'v1',
        'q24:explicit-classification', KNOWN, None, KNOWN) for i, k in enumerate(keys))
    mappings = tuple(SymbolMapping('mapping-' + str(i), k.mapping_version, 'q24.source', 'SYN' + str(i),
        k.instrument_id, 'q24.listing', k.venue_id, KNOWN, None, KNOWN) for i, k in enumerate(keys))
    cat = Catalog('catalog-v1', 'q24.catalog', instruments, mappings)
    cal = calendar(zone, trading_day(zone, '2024-03-08', sessions=(session(zone, '2024-03-08',
        start='09:30:00', end='16:00:00'),)), venue_id='q24.venue')
    rights = RightsGrant('q24.rights', 'synthetic', 'q24.source', 'q24.dataset', 'v1',
        ('store', 'research', 'report'), KNOWN, '2025-01-01T00:00:00Z', None)
    records = []
    for i, key in enumerate(keys):
        p = Price(prices[i], code, key.instrument_id, 'share')
        bar = PriceBar(key.instrument_id, 'q24.listing', key.venue_id, 'SYN' + str(i), start, end,
            p, p, p, p, Quantity('10000', key.instrument_id, 'share'), None, 'raw', None)
        r = MarketRevision(1, 'synthetic', 'q24.source', 'q24.dataset', key.instrument_id, 'event-' + str(i),
            'revision-v1', None, 'original', end, end, None, 'normalize-v1', bar)
        o = MarketObservation(1, 'synthetic', 'observation-' + str(i), 'q24.source', 'q24.dataset', key.instrument_id,
            r.event_id, r.revision_id, record_hash(r), current_at, current_at, sha256(b'explicit synthetic facts').hexdigest(),
            'q24:evidence', rights.rights_ref, cat.catalog_version, cal.calendar_version)
        records.append(MarketItem(r, o))
    scope = QueryScope(tuple(k.instrument_id for k in keys), start, now,
        tuple(ExpectedEvent(x.revision.series_id, x.revision.event_id, end) for x in records), 'expected_records', 'q24.complete')
    req = FetchRequest('q24.market-request', 'synthetic', 'q24.source', 'q24.dataset', 'v1', scope, start, expires, now)
    page = PageResult(req.request_id, scope, None, None, True, 'success', tuple(records), b'synthetic-page',
        'q24-market-snapshot', current_at, None, None)
    data = MarketDatasetInput(ingest(req, SyntheticPageAdapter((page,)), limits=IngestLimits(max_age_seconds=3600),
        rights=rights, evaluated_at=now, catalog=cat, calendar=cal, timezone=zone).bundle, cat, cal, zone, rights)
    store = SyntheticLedger()
    position_rows = tuple(PositionDelta(*key.key, amount) for key, amount in zip(keys, holdings) if amount != '0')
    opening = replace(baseline(), account_ref=account, effective_at=start, mapping_version='q24-mapping-v1',
        cash_legs=cash_pair('settled_cash', cash, 'opening_equity', currency=code), position_deltas=position_rows)
    assert store.append(opening, recorded_at=start).status == 'accepted'
    events = tuple(store.state(account).events)
    whole = BalanceScope('entire_account', (), ('KRW', 'USD'), tuple(sorted(DOMAINS)))
    vp = ValuationPolicy(1, 'synthetic', 'q24-value-v1', tuple(PriceSelection(k,
        SeriesSelection('q24.source', 'q24.dataset', 'v1', k.instrument_id)) for k in keys), (),
        (CurrencyQuantum(code, '1' if code == 'KRW' else '0.01'),), 3600, 3600)
    rp = ReconciliationPolicy(1, 'synthetic', 'q24-reconcile-v1', (QuantityTolerance('share', '0'),),
        (CashTolerance('KRW', '0'), CashTolerance('USD', '0')))
    repo = SyntheticSnapshotRepository()
    points = []
    for i, at in enumerate((end, current_at)):
        p = store.replay(account, as_of=at, knowledge_cutoff=now)
        request = ValuationRequest(1, 'synthetic', account, 'q24-valuation-' + str(i), p.ledger_cursor, at, now,
            now, 'as_known', code, 'research', vp.version, rp.version, whole)
        source = StatementSourceSnapshot(1, 'synthetic', account, 'q24.statement', 'statement-' + str(i),
            'revision-1', 'statement-snapshot-' + str(i), 'q24-mapping-v1', 'economic-components-v1', whole,
            at, now, now, position_rows, (CashBalance('settled_cash', code, cash),), ('q24:independent-statement',))
        statement = SyntheticAccountStatement(1, 'synthetic', source, hash_record(source), whole, 'success',
            True, 'source_snapshot', 'verified', True, ())
        points.append(ResearchPointInput(build_snapshot(p, request, (data,), vp, rp, repo, statement=statement), (data,)))
    perf = build_bound_performance(tuple(points), events)
    target_scope = TargetScope((market,), (code,), tuple(keys[i] for i in scope_indices))
    full_scope = TargetScope((market,), (code,), keys)
    limits = tuple(sorted((ExposureLimit(dim, key, '100000000', '1') for dim, key in (
        ('instrument', keys[0].instrument_id), ('instrument', keys[1].instrument_id), ('sector', 'synthetic-sector'),
        ('market', market), ('currency', code))), key=lambda x: (x.dimension, x.key)))
    policy = SyntheticTargetPolicy(1, 'synthetic', 'q24-policy-v1', account, KNOWN, '2025-01-01T00:00:00Z',
        'TARGET-DEC-001:synthetic-only', keys, (market,), (code,), (CurrencyLimit(code, '100000000', '100' if obligations else '0'),),
        limits, '10000000', '10000', '10000000', '10000', '0.5', '1000000', '0.5', end, current_at,
        utc_instant(start[:10] + 'T00:00:00Z'), utc_instant(start[:10] + 'T23:59:59Z'), 3600, 3600, 3600, 60, '0.1', '0.1')
    ctx = context_target_refs(data)
    capabilities = tuple(SyntheticOrderCapability(1, 'synthetic', 'cap-' + str(i), account, key, market, code,
        KNOWN, '2025-01-01T00:00:00Z', KNOWN, ctx[0], ctx[1], 'limit', 'day', '1' if market == 'KR' else '0.01',
        lot, lot, '10000', '0', '10000000', 'regular', 'whole_order_aggregate') for i, key in enumerate(keys))
    costs = tuple(SyntheticCostRule(1, 'synthetic', 'cost-' + side, account, market, code,
        side, KNOWN, '2025-01-01T00:00:00Z', fee, '0', '0', '0', '1' if code == 'KRW' else '0.01',
        'ceiling', 'whole_order_aggregate') for side in ('buy', 'sell'))
    sources = tuple(SyntheticObligationSource(1, 'synthetic', 'obligation-source-' + str(i), account,
        'obligation-' + str(i), code, '50', 'buy_commitment', start, 'outstanding', None) for i in range(2)) if obligations else ()
    obs = tuple(CashObligation(x.obligation_id, ref('obligation_source', x.source_id, x), code, '50',
        x.kind, start, 'outstanding', False, i == 0) for i, x in enumerate(sources))
    facts = SyntheticTargetFacts(1, 'synthetic', account, 'q24.explicit-synthetic', 'v1', 'q24-facts-snapshot',
        'synthetic-cash-capacity-v1', 'q24-mapping-v1', full_scope, full_scope, (), 'complete', 'aligned',
        current_at, current_at, now, now, now, points[-1].snapshot.ledger_cursor,
        ref('projection', 'current-projection', points[-1].snapshot.valuation.projection),
        ref('statement', 'statement-1', points[-1].snapshot.reconciliation_details.statement),
        (CashCapacity(code, '950' if obligations else cash, 'account_currency', 'cash_only_no_auto_fx',
            ('obligation-0',) if obligations else ()),), obs, (), 'complete',
        tuple(Sellability(k, holdings[i], holdings[i], '0', '0', ()) for i, k in enumerate(keys)),
        (), full_scope, 'complete', (), full_scope, 'complete',
        tuple(Classification(k, 'synthetic-sector', KNOWN, '2025-01-01T00:00:00Z', KNOWN, 'q24:explicit-sector') for k in keys),
        (), ref('performance', 'loss-performance', perf), capabilities, costs)
    strategy = SyntheticStrategyProposal(1, 'synthetic', 'q24-explicit-proposal', account,
        '명시한 합성 목표와 현재 보유의 차이입니다.', ('가격 변화와 부분체결 위험이 있습니다.',), '합성 시험이며 실제 전략 채택이 아닙니다.')
    request = TargetRequest(1, 'synthetic', account, 'q24-request', current_at, now, now, 'synthetic-generation-1',
        expires, mode, target_scope, 'zero' if mode == 'full' else 'keep', basis,
        tuple(TargetValue(keys[i], value, None) for i, value in enumerate(targets) if value is not None), (),
        ref('snapshot', points[-1].snapshot.snapshot_id, points[-1].snapshot), ref('strategy', strategy.strategy_id, strategy),
        ref('policy', policy.policy_id, policy), (ref('performance', 'loss-performance', perf),), None)
    inputs = TargetInputs(points[-1], events, policy, facts, strategy, tuple(points), perf, sources)
    return request, inputs


def changed(request, inputs, *, policy=None, facts=None, strategy=None):
    if policy is not None:
        inputs = replace(inputs, policy=policy)
        request = replace(request, policy_ref=ref('policy', policy.policy_id, policy))
    if facts is not None:
        inputs = replace(inputs, facts=facts)
    if strategy is not None:
        inputs = replace(inputs, strategy=strategy)
        request = replace(request, strategy_ref=ref('strategy', strategy.strategy_id, strategy))
    return request, inputs


def build(request, inputs, repository=None):
    return build_target(request, inputs, repository or SyntheticTargetRepository())


def sale_target_fixture():
    """Q23 독립 매도 golden의 실사건→일간 사용/손실/미반영 차감 연결."""
    from synthetic_research import sale_fixture
    import synthetic_valuation as v
    points, events, cost = sale_fixture()
    old = points[-1]
    # 독립 선언: 10주 매도, USD990 결제, fee2/tax3 뒤 0주/USD1985.
    statement = v.statement(holdings=(), cash=(CashBalance('settled_cash','USD','1985'),),
        source_changes=dict(source_as_of=old.snapshot.as_of,observed_at=old.snapshot.knowledge_cutoff,
                            ingested_at=old.snapshot.knowledge_cutoff))
    snap = build_snapshot(old.snapshot.valuation.projection, old.snapshot.valuation.request, old.market_inputs,
        old.snapshot.valuation.policy, old.snapshot.reconciliation_policy, SyntheticSnapshotRepository(),statement=statement)
    current = ResearchPointInput(snap,old.market_inputs)
    points = (points[0],current)
    performance = build_bound_performance(points,events,costs=(cost,))
    r,i=fixture(targets=('1',None),fee='1')
    key=v.KEY
    scope=TargetScope(('US',),('USD',),(key,))
    account=snap.account_ref
    contexts=context_target_refs(current.market_inputs[0])
    cap=replace(i.facts.capabilities[0],account_ref=account,position=key,catalog_ref=contexts[0],calendar_ref=contexts[1])
    rules=tuple(replace(x,account_ref=account) for x in i.facts.cost_rules)
    limits=tuple(sorted((ExposureLimit(dim,keyname,'10000000','1') for dim,keyname in
        (('instrument',key.instrument_id),('sector','synthetic-sector'),('market','US'),('currency','USD'))),key=lambda x:(x.dimension,x.key)))
    policy=replace(i.policy,account_ref=account,allowed_positions=(key,),exposure_limits=limits,
        risk_window_start=points[0].snapshot.as_of,risk_window_end=snap.as_of)
    strategy=replace(i.strategy,account_ref=account)
    sources=[]
    rows=[]
    for event,amount in ((events[-2],'2'),(events[-1],'3')):
        source=SyntheticObligationSource(1,'synthetic','source-'+amount,account,'obligation-'+amount,'USD',
            amount,'cash_debit',event.body.effective_at,'realized',ref('event',event.body.event_id,event.body))
        sources.append(source)
        rows.append(CashObligation(source.obligation_id,ref('obligation_source',source.source_id,source),
            'USD',amount,'cash_debit',source.effective_at,'realized',True,False))
    changes=tuple(sorted((ref('event',e.body.event_id,e.body) for e in events if
        points[0].snapshot.as_of < e.body.effective_at <= snap.as_of and any(x.account=='settled_cash' for x in e.body.cash_legs)),key=lambda x:x.id))
    facts=replace(i.facts,account_ref=account,mapping_version=key.mapping_version,
        requested_scope=scope,covered_scope=scope,source_as_of=points[0].snapshot.as_of,aligned_as_of=snap.as_of,
        observed_at=snap.knowledge_cutoff,ingested_at=snap.knowledge_cutoff,knowledge_cutoff=snap.knowledge_cutoff,
        ledger_cursor=snap.ledger_cursor,projection_ref=ref('projection','current-projection',snap.valuation.projection),
        statement_ref=ref('statement',statement.snapshot.statement_id,statement),cash_capacity_rows=(CashCapacity('USD','1000','account_currency','cash_only_no_auto_fx',()),),
        obligations=tuple(rows),post_source_cash_changes=changes,sellability_rows=(Sellability(key,'0','0','0','0',()),),
        open_orders_scope=scope,active_intents_scope=scope,classifications=(replace(i.facts.classifications[0],position=key),),
        daily_usage_event_refs=(ref('event',events[1].body.event_id,events[1].body),),
        loss_performance_ref=ref('performance','loss-performance',performance),capabilities=(cap,),cost_rules=rules)
    r=replace(r,account_ref=account,as_of=snap.as_of,knowledge_cutoff=snap.knowledge_cutoff,evaluated_at=snap.created_at,
        scope=scope,targets=(TargetValue(key,'1',None),),snapshot_ref=ref('snapshot',snap.snapshot_id,snap),
        strategy_ref=ref('strategy',strategy.strategy_id,strategy),policy_ref=ref('policy',policy.policy_id,policy),
        research_refs=(ref('performance','loss-performance',performance),))
    return r,TargetInputs(current,events,policy,facts,strategy,points,performance,tuple(sources),(cost,))


def fx_target_fixture(*, inverse=False):
    """KRW 보유/현금과 USD NAV, 검증된 Q17 FX로 절대 계좌 비중 계산."""
    import synthetic_valuation as v
    from quantharbor.domain.primitives import FX
    from quantharbor.domain.market_data import FXObservation
    from quantharbor.domain.valuation import FXSelection
    r,i=fixture(market='KR',cash='1000',holdings=('0','0'),prices=('60','60'),targets=('0.25',None),basis='weight',lot='2',fee='0')
    data=i.current.market_inputs[0]
    current_records=data.bundle.evidence
    at=current_records[0].revision.effective_at
    rate='3' if inverse else '0.3'
    fx=FX('USD' if inverse else 'KRW','KRW' if inverse else 'USD',rate,at,'q24.source')
    revision=MarketRevision(1,'synthetic','q24.source','q24.dataset','q24.fx','q24.fx.event','v1',None,
        'original',at,at,None,'normalize-v1',FXObservation(fx))
    observation=replace(current_records[0].observation,observation_id='q24.fx.obs',series_id='q24.fx',
        event_id=revision.event_id,revision_id=revision.revision_id,revision_hash=record_hash(revision))
    records=(*current_records,MarketItem(revision,observation))
    old=data.bundle.descriptor.request
    scope=replace(old.scope,series_ids=tuple(sorted((*old.scope.series_ids,'q24.fx'))),
        expected=tuple(sorted((*old.scope.expected,ExpectedEvent('q24.fx','q24.fx.event',at)),key=lambda x:(x.series_id,x.event_id))))
    req=replace(old,scope=scope)
    page=PageResult(req.request_id,scope,None,None,True,'success',records,b'synthetic-fx-page','q24-fx-source',r.knowledge_cutoff,None,None)
    bundle=ingest(req,SyntheticPageAdapter((page,)),limits=IngestLimits(max_age_seconds=3600),rights=data.current_rights,
        evaluated_at=r.evaluated_at,catalog=data.catalog,calendar=data.calendar,timezone=data.timezone).bundle
    data=replace(data,bundle=bundle)
    points=[]
    vp=replace(i.current.snapshot.valuation.policy,fx=(FXSelection('KRW',SeriesSelection('q24.source','q24.dataset','v1','q24.fx')),),
        quantums=(CurrencyQuantum('KRW','1'),CurrencyQuantum('USD','0.01')))
    repo=SyntheticSnapshotRepository()
    for point in i.risk_points:
        s=point.snapshot
        req=replace(s.valuation.request,base_currency='USD')
        rebuilt=build_snapshot(s.valuation.projection,req,(data,),vp,s.reconciliation_policy,repo,
            statement=s.reconciliation_details.statement)
        points.append(ResearchPointInput(rebuilt,(data,)))
    performance=build_bound_performance(tuple(points),i.events)
    s=points[-1].snapshot
    facts=replace(i.facts,projection_ref=ref('projection','current-projection',s.valuation.projection),
        loss_performance_ref=ref('performance','loss-performance',performance))
    r=replace(r,snapshot_ref=ref('snapshot',s.snapshot_id,s),research_refs=(ref('performance','loss-performance',performance),))
    return r,replace(i,current=points[-1],risk_points=tuple(points),performance=performance,facts=facts)
