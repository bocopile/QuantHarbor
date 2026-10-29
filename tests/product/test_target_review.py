"""T1~T6: 실제 ingest/원장/snapshot 및 직접 canonical 복원 회귀."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from functools import lru_cache
from hashlib import sha256
import json
import unittest

from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.adapters.synthetic_market import SyntheticPageAdapter
from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
from quantharbor.application.market_ingest import ingest
from quantharbor.application.research import build_bound_performance
from quantharbor.application.target import context_target_refs
from quantharbor.application.valuation import build_snapshot
from quantharbor.domain.ledger import CashBalance, CashLeg, PositionDelta, hash_record
from quantharbor.domain.market_data import ExpectedEvent, IngestLimits, MarketItem, PageResult, record_hash
from quantharbor.domain.primitives import ContractError, Price, utc_instant
from quantharbor.domain.target import (CashCapacity, CashObligation, CashTarget, CurrencyLimit,
    ExposureLimit, SyntheticObligationSource, TargetPlan, TargetPlanBody, TargetScope, TargetValue, ref)
from quantharbor.domain.valuation import CurrencyQuantum, FXSelection, PositionKey, PriceSelection, SeriesSelection
from quantharbor.ports.research import ResearchPointInput
from synthetic_ledger import cash_pair
from synthetic_target import build, changed, fixture, fx_target_fixture, sale_target_fixture


def plus(at, seconds):
    return utc_instant(datetime.fromisoformat(at) + timedelta(seconds=seconds))


def dataset(data, records, *, request=None, rights=None, at=None):
    old = request or data.bundle.descriptor.request
    expected = tuple(sorted((ExpectedEvent(x.revision.series_id, x.revision.event_id,
        x.revision.effective_at) for x in records), key=lambda x:(x.series_id,x.event_id)))
    scope = replace(old.scope, series_ids=tuple(sorted({x.revision.series_id for x in records})), expected=expected)
    req = replace(old, scope=scope)
    page = PageResult(req.request_id, scope, None, None, True, 'success', tuple(records),
        b'Q24 review independent synthetic page', 'review-page', at or old.knowledge_cutoff, None, None)
    grant = rights or data.current_rights
    result = ingest(req, SyntheticPageAdapter((page,)), limits=IngestLimits(max_age_seconds=86400),
        rights=grant, evaluated_at=at or data.bundle.descriptor.evaluated_at,
        catalog=data.catalog, calendar=data.calendar, timezone=data.timezone)
    assert result.bundle.envelope.quality.status == 'complete', result.bundle.envelope.quality
    return replace(data, bundle=result.bundle, current_rights=grant)


def rebind(r, i, *, datasets=None, store=None, cash=None, positions=None, valuation_policy=None):
    """원본을 재구축하고 모든 참조를 결속한다. 검증기 mock 없음."""
    points = []
    repo = SyntheticSnapshotRepository()
    for point in i.risk_points:
        s = point.snapshot
        p = s.valuation.projection if store is None else store.replay(r.account_ref,
            as_of=s.as_of, knowledge_cutoff=s.knowledge_cutoff)
        req = replace(s.valuation.request, ledger_cursor=p.ledger_cursor)
        statement = s.reconciliation_details.statement
        if cash is not None or positions is not None:
            source = replace(statement.snapshot, cash=tuple(sorted(cash,key=lambda x:(x.account,x.currency))) if cash is not None else statement.snapshot.cash,
                holdings=positions if positions is not None else statement.snapshot.holdings)
            statement = replace(statement, snapshot=source, source_snapshot_hash=hash_record(source))
        data = datasets if datasets is not None else point.market_inputs
        snap = build_snapshot(p, req, data, valuation_policy or s.valuation.policy,
            s.reconciliation_policy, repo, statement=statement)
        assert snap.valuation.complete, snap.valuation.reason_codes
        if point is i.risk_points[-1]:
            assert snap.reconciliation == 'matched', snap.reconciliation
        points.append(ResearchPointInput(snap, data))
    events = i.events if store is None else tuple(store.state(r.account_ref).events)
    perf = build_bound_performance(tuple(points), events, costs=i.costs)
    s = points[-1].snapshot
    facts = replace(i.facts, ledger_cursor=s.ledger_cursor,
        projection_ref=ref('projection','current-projection',s.valuation.projection),
        statement_ref=ref('statement',s.reconciliation_details.statement.snapshot.statement_id,s.reconciliation_details.statement),
        loss_performance_ref=ref('performance','loss-performance',perf))
    r = replace(r, snapshot_ref=ref('snapshot',s.snapshot_id,s),research_refs=(ref('performance','loss-performance',perf),))
    return r, replace(i,current=points[-1],risk_points=tuple(points),events=events,performance=perf,facts=facts)


@lru_cache(maxsize=1)
def payable_fixture():
    from quantharbor.domain.research import TradeCostFact, InputRef, known
    r,i=fixture(holdings=('5','0'),targets=('11',None),fee='0')
    opening=i.events[0].body.submission
    store=SyntheticLedger()
    assert store.append(opening,recorded_at=opening.effective_at).status=='accepted'
    costs=[]
    for key,quantity,account,amount,side,price in (('buy','5','unsettled_payable','-500','buy','100'),
            ('sell','-5','unsettled_receivable','1000','sell','200')):
        at=plus(opening.effective_at,1 if side=='buy' else 2)
        trade=replace(opening,source_event_key=key,event_type='trade',effective_at=at,baseline=None,
            position_deltas=(replace(opening.position_deltas[0],amount=quantity),),
            cash_legs=cash_pair(account,amount,'trade_clearing',basis='trade'))
        result=store.append(trade,recorded_at=at)
        assert result.status=='accepted', result
        event=store.state(r.account_ref).events[-1]
        costs.append(TradeCostFact(1,'synthetic',r.account_ref,InputRef('event',event.body.event_id,event.payload_hash),
            1,r.targets[0].position,'USD',at,side,'5',price,price,'0.01',(),known(abs(int(amount)),ratio=False)))
    i=replace(i,costs=tuple(costs))
    cash=(CashBalance('settled_cash','USD','1000'),CashBalance('unsettled_receivable','USD','1000'),
        CashBalance('unsettled_payable','USD','-500'))
    r,i=rebind(r,i,store=store,cash=cash)
    daily=tuple(sorted((ref('event',e.body.event_id,e.body) for e in i.events[1:]),key=lambda x:x.id))
    return r,replace(i,facts=replace(i.facts,daily_usage_event_refs=daily))


@lru_cache(maxsize=1)
def multibar_fixture():
    r,i=fixture(holdings=('1','0'),targets=('3',None),fee='0')
    data=i.current.market_inputs[0]
    original=data.bundle.evidence[0]
    rev=original.revision
    p=Price('80','USD',rev.payload.instrument_id,'share')
    bar=replace(rev.payload,ends_at=plus(rev.payload.ends_at,-30),open=p,high=p,low=p,close=p)
    old=replace(rev,event_id='older-bar',effective_at=bar.ends_at,published_at=bar.ends_at,payload=bar)
    obs=replace(original.observation,observation_id='older-observation',event_id=old.event_id,
        revision_hash=record_hash(old))
    data=dataset(data,(*data.bundle.evidence,MarketItem(old,obs)))
    return rebind(r,i,datasets=(data,))


@lru_cache(maxsize=1)
def separate_fx_fixture():
    r,i=fx_target_fixture()
    data=i.current.market_inputs[0]
    bars=tuple(x for x in data.bundle.evidence if x.revision.series_id!='q24.fx')
    fx=next(x for x in data.bundle.evidence if x.revision.series_id=='q24.fx')
    rev=replace(fx.revision,dataset_id='q24.fx.dataset')
    obs=replace(fx.observation,dataset_id=rev.dataset_id,revision_hash=record_hash(rev),rights_ref='fx.rights')
    grant=replace(data.current_rights,rights_ref='fx.rights',dataset_id=rev.dataset_id,valid_to=plus(r.evaluated_at,5))
    req=replace(data.bundle.descriptor.request,request_id='fx-request',dataset_id=rev.dataset_id)
    fxdata=dataset(data,(MarketItem(rev,obs),),request=req,rights=grant)
    barsdata=dataset(data,bars)
    vp=replace(i.current.snapshot.valuation.policy,fx=(replace(i.current.snapshot.valuation.policy.fx[0],
        series=SeriesSelection('q24.source',rev.dataset_id,'v1','q24.fx')),))
    return rebind(r,i,datasets=(barsdata,fxdata),valuation_policy=vp)


@lru_cache(maxsize=1)
def sold_fixture():
    r,i=sale_target_fixture()
    other_r,other_i=fixture(targets=('1',None),fee='1')
    data=other_i.current.market_inputs[0]
    data=replace(data,catalog=replace(data.catalog,mappings=tuple(replace(m,mapping_version='mapping-v1') for m in data.catalog.mappings)))
    data=dataset(data,data.bundle.evidence)
    key=replace(other_r.targets[0].position,mapping_version='mapping-v1')
    scope=replace(i.facts.covered_scope,positions=tuple(sorted((*i.facts.covered_scope.positions,key),key=lambda x:x.key)))
    contexts=context_target_refs(data)
    cap=replace(other_i.facts.capabilities[0],account_ref=r.account_ref,position=key,catalog_ref=contexts[0],calendar_ref=contexts[1])
    facts=replace(i.facts,requested_scope=scope,covered_scope=scope,open_orders_scope=scope,active_intents_scope=scope,
        classifications=tuple(sorted((*i.facts.classifications,replace(other_i.facts.classifications[0],position=key)),key=lambda x:x.position.key)),
        capabilities=tuple(sorted((*i.facts.capabilities,cap),key=lambda x:x.position.key)))
    limits=tuple(sorted((*i.policy.exposure_limits,ExposureLimit('instrument',key.instrument_id,'10000000','1')),key=lambda x:(x.dimension,x.key)))
    policy=replace(i.policy,allowed_positions=scope.positions,exposure_limits=limits)
    r,i=changed(r,i,policy=policy,facts=facts)
    r=replace(r,scope=TargetScope(('US',),('USD',),(key,)),targets=(TargetValue(key,'1',None),))
    vp=replace(i.current.snapshot.valuation.policy,prices=tuple(sorted((*i.current.snapshot.valuation.policy.prices,
        PriceSelection(key,SeriesSelection('q24.source','q24.dataset','v1',key.instrument_id))),key=lambda x:x.position.key)))
    return rebind(r,i,datasets=(*i.current.market_inputs,data),valuation_policy=vp)


@lru_cache(maxsize=1)
def mixed_fixture():
    r,i=fixture(targets=('1',None),scope_indices=(0,),fee='0')
    kr,ki=fx_target_fixture()
    data=ki.current.market_inputs[0]
    key=PositionKey('q24.KR','q24.krvenue','q24-mapping-v1','share')
    instrument=replace(data.catalog.instruments[0],instrument_id=key.instrument_id,listing_venue_id='q24.krlisting')
    mapping=replace(data.catalog.mappings[0],instrument_id=key.instrument_id,source_id='q24.krsource',
        listing_venue_id='q24.krlisting',execution_venue_id=key.venue_id)
    cat=replace(data.catalog,source_ref='kr.catalog',instruments=(instrument,),mappings=(mapping,))
    cal=replace(data.calendar,venue_id=key.venue_id)
    grant=replace(data.current_rights,rights_ref='kr.rights',source_id='q24.krsource',dataset_id='kr.dataset')
    records=[]
    for old in data.bundle.evidence:
        if old.revision.series_id not in ('q24.A','q24.fx'):
            continue
        payload=old.revision.payload
        if old.revision.series_id=='q24.A':
            payload=replace(payload,instrument_id=key.instrument_id,listing_venue_id='q24.krlisting',execution_venue_id=key.venue_id,
                open=replace(payload.open,instrument_id=key.instrument_id),high=replace(payload.high,instrument_id=key.instrument_id),
                low=replace(payload.low,instrument_id=key.instrument_id),close=replace(payload.close,instrument_id=key.instrument_id),
                volume=replace(payload.volume,instrument_id=key.instrument_id))
        else:
            payload=replace(payload,fx=replace(payload.fx,source_id='q24.krsource'))
        rev=replace(old.revision,source_id='q24.krsource',dataset_id='kr.dataset',payload=payload)
        obs=replace(old.observation,source_id=rev.source_id,dataset_id=rev.dataset_id,rights_ref=grant.rights_ref,
            revision_hash=record_hash(rev))
        records.append(MarketItem(rev,obs))
    req=replace(data.bundle.descriptor.request,request_id='kr-market',source_id='q24.krsource',dataset_id='kr.dataset')
    data=dataset(replace(data,catalog=cat,calendar=cal,current_rights=grant),records,request=req,rights=grant)
    scope=TargetScope(('KR','US'),('KRW','USD'),tuple(sorted((*i.facts.covered_scope.positions,key),key=lambda x:x.key)))
    facts=replace(i.facts,requested_scope=scope,covered_scope=scope,open_orders_scope=scope,active_intents_scope=scope,
        classifications=tuple(sorted((*i.facts.classifications,replace(ki.facts.classifications[0],position=key)),key=lambda x:x.position.key)),
        cash_capacity_rows=(CashCapacity('KRW','0','account_currency','cash_only_no_auto_fx',()),*i.facts.cash_capacity_rows))
    limits=tuple(sorted((*i.policy.exposure_limits,ExposureLimit('instrument',key.instrument_id,'10000000','1'),
        ExposureLimit('market','KR','10000000','1'),ExposureLimit('currency','KRW','10000000','1')),key=lambda x:(x.dimension,x.key)))
    # Explicit synthetic stale-window policy permits the earlier KR close at US opening.
    policy=replace(i.policy,allowed_positions=scope.positions,allowed_markets=scope.markets,allowed_currencies=scope.currencies,
        currency_limits=(CurrencyLimit('KRW','10000000','0'),*i.policy.currency_limits),exposure_limits=limits,
        max_price_age_seconds=60000,max_fx_age_seconds=60000)
    r,i=changed(r,i,policy=policy,facts=facts)
    holding=PositionDelta(*key.key,'1')
    opening=replace(i.events[0].body.submission,position_deltas=(holding,))
    store=SyntheticLedger()
    assert store.append(opening,recorded_at=opening.effective_at).status=='accepted'
    vp=replace(i.current.snapshot.valuation.policy,prices=tuple(sorted((*i.current.snapshot.valuation.policy.prices,
        PriceSelection(key,SeriesSelection('q24.krsource','kr.dataset','v1','q24.A'))),key=lambda x:x.position.key)),
        fx=(FXSelection('KRW',SeriesSelection('q24.krsource','kr.dataset','v1','q24.fx')),),
        quantums=(CurrencyQuantum('KRW','1'),CurrencyQuantum('USD','0.01')),max_price_age_seconds=60000,max_fx_age_seconds=60000)
    return rebind(r,i,datasets=(*i.current.market_inputs,data),store=store,positions=(holding,),valuation_policy=vp)


def raw(obj):
    return json.dumps(dict(schema_name=type(obj).__name__,schema_version=1,environment='synthetic',payload=asdict(obj)),
        sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()


class ReviewRegressionTests(unittest.TestCase):
    def eligible(self,r,i):
        try:
            a=build(r,i)
        except ContractError as error:
            self.fail('valid source-bound input rejected: '+str(error))
        self.assertEqual(a.result.body.outcome,'eligible',a.result.body.failures)
        return a

    def test_T1_omitted_ledger_payable_blocks_600_despite_positive_receivable(self):
        r,i=payable_fixture()
        self.assertEqual(i.current.snapshot.valuation.nav,'2000')
        a=build(r,i)
        self.assertEqual((a.result.body.outcome,a.candidates),('blocked',()))

    def test_T2_direct_constructor_request_limit_and_cash_target(self):
        r,i=fixture(targets=('3',None))
        b=self.eligible(r,i).plan.body
        for req in (replace(r,targets=(replace(r.targets[0],limit_price='90'),)),
                    replace(r,cash_targets=(CashTarget('USD','900'),))):
            with self.subTest(request=req),self.assertRaises(ContractError):
                replace(b,request=req)

    def test_T2_canonical_parser_resealed_contradictory_body(self):
        from quantharbor.domain.serialization import parse_payload
        r,i=fixture(targets=('3',None))
        body=deepcopy(self.eligible(r,i).plan.body)
        object.__setattr__(body,'request',replace(r,cash_targets=(CashTarget('USD','900'),)))
        with self.assertRaises(ContractError):
            parse_payload(raw(body))

    def test_T2_repository_resealed_contradiction(self):
        from quantharbor.ports.target import TargetArtifacts
        r,i=fixture(targets=('3',None))
        a=self.eligible(r,i)
        # Serialize a freshly sealed plan body; repository must also reject before storing anything.
        body=deepcopy(a.plan.body)
        object.__setattr__(body,'request',replace(r,targets=(replace(r.targets[0],limit_price='90'),)))
        digest=sha256(b'QuantHarbor/qh-canonical-json-v1\n'+raw(body)).hexdigest()
        plan=deepcopy(a.plan)
        object.__setattr__(plan,'body',body)
        object.__setattr__(plan,'plan_id','target-plan:'+digest)
        def unchecked_ref(kind,id,obj):
            return replace(ref(kind,id,a.plan),sha256=sha256(b'QuantHarbor/qh-canonical-json-v1\n'+raw(obj)).hexdigest())
        pr=unchecked_ref('plan',plan.plan_id,plan)
        candidates=deepcopy(a.candidates)
        for c in candidates:
            object.__setattr__(c.body,'plan_ref',pr)
            object.__setattr__(c,'candidate_id','candidate:'+sha256(b'QuantHarbor/qh-canonical-json-v1\n'+raw(c.body)).hexdigest())
        result=deepcopy(a.result)
        object.__setattr__(result.body,'request_ref',unchecked_ref('request',r.request_id,body.request))
        object.__setattr__(result.body,'plan_ref',pr)
        object.__setattr__(result.body,'candidate_refs',tuple(unchecked_ref('candidate',c.candidate_id,c) for c in candidates))
        object.__setattr__(result,'result_id','target-result:'+sha256(b'QuantHarbor/qh-canonical-json-v1\n'+raw(result.body)).hexdigest())
        with self.assertRaises(ContractError):
            SyntheticTargetRepository().append(TargetArtifacts(plan,candidates,result))

    def test_T3_normal_series_uses_Q21_selected_latest_reference(self):
        r,i=multibar_fixture()
        a=self.eligible(r,i)
        self.assertEqual(a.candidates[0].body.terms.reference_price,'100')
        self.assertEqual(a.plan.body.positions[0].current_quantity,'1')

    def test_T5_all_account_fx_rights_intersect_candidate_expiry(self):
        r,i=separate_fx_fixture()
        a=self.eligible(r,i)
        self.assertEqual(a.candidates[0].body.terms.valid_to,plus(r.evaluated_at,5))

    def test_T4_untouched_KR_holding_at_US_open_needs_no_order_capability(self):
        r,i=mixed_fixture()
        krdata=i.current.market_inputs[1]
        self.assertFalse(krdata.timezone.lookup_calendar(krdata.calendar,r.evaluated_at,
            knowledge_cutoff=r.knowledge_cutoff).regular_session_eligible)
        a=self.eligible(r,i)
        self.assertEqual(len(a.candidates),1)
        self.assertEqual(a.candidates[0].body.terms.market,'US')
        self.assertEqual(next(p for p in a.plan.body.positions if p.position.instrument_id=='q24.KR').difference,'0')

    def test_T4_untouched_KR_with_capability_still_needs_no_open_session(self):
        r,i=mixed_fixture()
        key=next(k for k in i.policy.allowed_positions if k.instrument_id=='q24.KR')
        contexts=context_target_refs(i.current.market_inputs[1])
        cap=replace(i.facts.capabilities[0],position=key,market='KR',currency='KRW',
            catalog_ref=contexts[0],calendar_ref=contexts[1])
        caps=tuple(sorted((*i.facts.capabilities,cap),key=lambda x:x.position.key))
        self.eligible(r,replace(i,facts=replace(i.facts,capabilities=caps)))

    def test_T6_fully_sold_instrument_keeps_daily_usage_independent_of_scope(self):
        from quantharbor.application import target
        r,i=sold_fixture()
        self.assertNotIn(i.costs[0].position,r.scope.positions)
        self.assertTrue(all(x.position.amount=='0' for x in i.current.snapshot.holdings))
        subject=ref('request',r.request_id,r)
        # Q20 keeps zero tombstones. Isolate daily accounting with actual revalidated
        # sources and only economically held/requested positions, without any mocks.
        target._source(i,r,subject)
        cash=target._cash_rows(i,r,subject)
        holdings,market,_=target._market_rows(i,r,subject)
        holdings={k:q for k,q in holdings.items() if q!='0'}
        market={k:v for k,v in market.items() if k in holdings or k in r.scope.positions}
        positions=target._positions(r,holdings,market,i.current.snapshot.valuation.nav,i.policy,subject)
        orders,cash=target._orders(i,r,positions,market,cash,subject)
        try:
            _,c=target._constraints(i,r,market,positions,orders,cash,subject)
        except target._Blocked as error:
            self.fail(str(error.failure))
        self.assertEqual((c.daily_used_amount,c.daily_used_quantity),('990','10'))
        self.assertEqual(orders[0].quantity,'1')

