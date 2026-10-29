"""T1~T6 정상 golden과 누락/변조/경계 회귀. 상위 모듈 수정 없음."""
from dataclasses import replace
from functools import lru_cache
import unittest

from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.domain.ledger import CashBalance, CashLeg
from quantharbor.domain.market_data import ExpectedEvent, IngestLimits, MarketItem, PageResult, record_hash
from quantharbor.domain.primitives import ContractError, Price
from quantharbor.domain.research import known
from quantharbor.domain.target import CashObligation, CashTarget, SyntheticObligationSource, TargetValue, ref
from quantharbor.domain.valuation import FXSelection
from synthetic_target import build, changed, fixture
from test_target_review import (dataset, mixed_fixture, multibar_fixture, payable_fixture,
    plus, rebind, separate_fx_fixture, sold_fixture)


def identified_payable(r,i,amount='500'):
    e=next(e for e in i.events if e.body.submission.source_event_key=='buy')
    source=SyntheticObligationSource(1,'synthetic','identified-payable',r.account_ref,'buy-obligation','USD',amount,
        'buy_commitment',e.body.effective_at,'outstanding',ref('event',e.body.event_id,e.body))
    row=CashObligation(source.obligation_id,ref('obligation_source',source.source_id,source),'USD',amount,
        source.kind,source.effective_at,'outstanding',False,False)
    return replace(i,obligation_sources=(source,),facts=replace(i.facts,obligations=(row,)))


@lru_cache(maxsize=1)
def historical_fx_fixture():
    import synthetic_valuation as v
    r,i=sold_fixture()
    data=i.current.market_inputs[0]
    fx=v.fx_item(rate='3')
    data=dataset(data,(*data.bundle.evidence,fx))
    # Rebuild real Q21 inputs directly; no scalar conversion receipt is trusted.
    from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
    from quantharbor.application.valuation import build_snapshot
    from quantharbor.application.research import build_bound_performance
    from quantharbor.ports.research import ResearchPointInput
    vp=replace(i.current.snapshot.valuation.policy,fx=(FXSelection('USD',v.FX_SERIES),))
    points=[]
    for point in i.risk_points:
        s=point.snapshot
        datasets=(data,*point.market_inputs[1:])
        snapshot=build_snapshot(s.valuation.projection,replace(s.valuation.request,base_currency='KRW'),
            datasets,vp,s.reconciliation_policy,SyntheticSnapshotRepository(),statement=s.reconciliation_details.statement)
        assert snapshot.valuation.complete
        points.append(ResearchPointInput(snapshot,datasets))
    performance=build_bound_performance(tuple(points),i.events,costs=i.costs)
    s=points[-1].snapshot
    facts=replace(i.facts,projection_ref=ref('projection','current-projection',s.valuation.projection),
        loss_performance_ref=ref('performance','loss-performance',performance))
    r=replace(r,snapshot_ref=ref('snapshot',s.snapshot_id,s),research_refs=(ref('performance','loss-performance',performance),))
    return r,replace(i,current=points[-1],risk_points=tuple(points),performance=performance,facts=facts)


@lru_cache(maxsize=4)
def extra_daily_fx_fixture(*, complete=False, seconds=1, rate='1'):
    """실제 ingest/replay/Q21 추가 증거. expected event 누락은 환율 숫자와 독립이다."""
    from quantharbor.adapters.synthetic_market import SyntheticPageAdapter
    from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
    from quantharbor.application.market_ingest import ingest, replay_storage
    from quantharbor.application.valuation import build_snapshot
    from quantharbor.ports.research import ResearchPointInput
    r,i=historical_fx_fixture()
    point=i.current
    data=point.market_inputs[0]
    fx=next(x for x in data.bundle.evidence if x.revision.series_id=='syn.fx')
    at=plus(fx.revision.effective_at,seconds)
    revision=replace(fx.revision,event_id='extra-daily-fx',effective_at=at,published_at=at,
        payload=replace(fx.revision.payload,fx=replace(fx.revision.payload.fx,rate=rate,as_of=at)))
    observation=replace(fx.observation,observation_id='extra-daily-observation',event_id=revision.event_id,
        revision_hash=record_hash(revision))
    records=(*tuple(x for x in data.bundle.evidence if x.revision.series_id!='syn.fx'),MarketItem(revision,observation))
    old=data.bundle.descriptor.request
    expected=tuple(ExpectedEvent(x.revision.series_id,x.revision.event_id,x.revision.effective_at) for x in records)
    if not complete:
        expected+= (ExpectedEvent('syn.fx','missing-daily-fx',at),)
    scope=replace(old.scope,expected=tuple(sorted(expected,key=lambda x:(x.series_id,x.event_id))))
    req=replace(old,request_id='extra-daily-request',scope=scope)
    page=PageResult(req.request_id,scope,None,None,True,'success',records,
        b'Q24 second review synthetic daily FX','extra-daily-page',old.knowledge_cutoff,None,None)
    result=ingest(req,SyntheticPageAdapter((page,)),limits=IngestLimits(max_age_seconds=86400),
        rights=data.current_rights,evaluated_at=data.bundle.descriptor.evaluated_at,
        catalog=data.catalog,calendar=data.calendar,timezone=data.timezone)
    data=replace(data,bundle=result.bundle)
    state,envelope=replay_storage(data.bundle.descriptor,data.bundle.receipts,data.bundle.evidence,
        catalog=data.catalog,calendar=data.calendar,timezone=data.timezone)
    assert (state,envelope)==(data.bundle.state,data.bundle.envelope)
    datasets=(data,*point.market_inputs[1:])
    s=point.snapshot
    snapshot=build_snapshot(s.valuation.projection,s.valuation.request,datasets,s.valuation.policy,
        s.reconciliation_policy,SyntheticSnapshotRepository(),statement=s.reconciliation_details.statement)
    proof=next(p for p in snapshot.valuation.market_proofs if p.selection.series_id=='syn.fx')
    assert proof.quality.status==('complete' if complete else 'partial')
    assert bool(proof.quality.missing_scope)==(not complete)
    assert proof.usable==complete and not proof.held_reasons
    daily=ResearchPointInput(snapshot,datasets)
    return r,replace(i,daily_usage_inputs=(daily,))


class ReviewGoldenAndNegativeTests(unittest.TestCase):
    def eligible(self,r,i):
        a=build(r,i)
        self.assertEqual(a.result.body.outcome,'eligible',a.result.body.failures)
        return a

    def blocked(self,r,i,code):
        a=build(r,i)
        self.assertEqual((a.result.body.outcome,a.candidates),('blocked',()))
        self.assertIn(code,{x.code for x in a.result.body.failures})
        return a

    def test_T1_identified_payable_H500_preserves_400_buy_without_receivable_netting(self):
        r,i=payable_fixture()
        i=identified_payable(r,i)
        r=replace(r,targets=(replace(r.targets[0],value='9'),))
        a=self.eligible(r,i)
        c=a.plan.body.cash_calculation[0]
        self.assertEqual((c.ledger_cash,c.outstanding,c.unreflected,c.available,c.planned_burden,c.remaining),
            ('1000','500','500','500','400','100'))
        self.blocked(replace(r,targets=(replace(r.targets[0],value='11'),)),i,'cash_shortfall')

    def test_T1_understatement_and_duplicate_same_ledger_origin_rejected(self):
        r,i=payable_fixture()
        with self.assertRaises(ContractError):
            build(r,identified_payable(r,i,'499'))
        i=identified_payable(r,i)
        source=replace(i.obligation_sources[0],source_id='identified-payable-2',obligation_id='buy-obligation-2')
        row=replace(i.facts.obligations[0],obligation_id=source.obligation_id,
            source_ref=ref('obligation_source',source.source_id,source))
        with self.assertRaises(ContractError):
            build(r,replace(i,obligation_sources=(*i.obligation_sources,source),
                facts=replace(i.facts,obligations=(*i.facts.obligations,row))))

    def test_T1_B_already_reflects_same_obligation_without_second_U_charge(self):
        r,i=payable_fixture()
        i=identified_payable(r,i)
        row=replace(i.facts.obligations[0],reflected_in_B=True)
        cap=replace(i.facts.cash_capacity_rows[0],amount='500',reflected_obligation_ids=(row.obligation_id,))
        i=replace(i,facts=replace(i.facts,obligations=(row,),cash_capacity_rows=(cap,)))
        r=replace(r,targets=(replace(r.targets[0],value='9'),))
        c=self.eligible(r,i).plan.body.cash_calculation[0]
        self.assertEqual((c.outstanding,c.unreflected,c.available,c.remaining),('500','0','500','100'))

    def test_T1_fully_settled_buy_is_not_charged_twice(self):
        r,i=payable_fixture()
        store=SyntheticLedger()
        for e in i.events:
            self.assertEqual(store.append(e.body.submission,recorded_at=e.body.recorded_at).status,'accepted')
        buy=i.events[1]
        s=replace(buy.body.submission,source_event_key='buy-settlement',event_type='settlement',
            effective_at=plus(buy.body.effective_at,3),position_deltas=(),dependency_refs=(buy.body.event_id,),
            cash_legs=(CashLeg('unsettled_payable','USD','500','settlement'),CashLeg('settled_cash','USD','-500','settlement')))
        self.assertEqual(store.append(s,recorded_at=s.effective_at).status,'accepted')
        cash=(CashBalance('settled_cash','USD','500'),CashBalance('unsettled_receivable','USD','1000'))
        r,i=rebind(r,i,store=store,cash=cash)
        caps=(replace(i.facts.cash_capacity_rows[0],amount='500'),)
        i=replace(i,facts=replace(i.facts,cash_capacity_rows=caps))
        r=replace(r,targets=(replace(r.targets[0],value='9'),))
        c=self.eligible(r,i).plan.body.cash_calculation[0]
        self.assertEqual((c.ledger_cash,c.outstanding,c.post_source_debits,c.available,c.remaining),('500','0','0','500','100'))

    def test_T1_mismatched_event_revision_and_unknown_status_rejected(self):
        r,i=payable_fixture()
        i=identified_payable(r,i)
        source=replace(i.obligation_sources[0],ledger_event_ref=replace(i.obligation_sources[0].ledger_event_ref,sha256='a'*64))
        row=replace(i.facts.obligations[0],source_ref=ref('obligation_source',source.source_id,source))
        with self.assertRaises(ContractError):
            build(r,replace(i,obligation_sources=(source,),facts=replace(i.facts,obligations=(row,))))
        source=replace(i.obligation_sources[0],status='unknown')
        row=replace(i.facts.obligations[0],outstanding_or_realized='unknown',source_ref=ref('obligation_source',source.source_id,source))
        self.blocked(r,replace(i,obligation_sources=(source,),facts=replace(i.facts,obligations=(row,))),'source_semantics_unknown')

    def test_T2_normal_explicit_limit_and_maximum_of_cash_floors(self):
        r,i=fixture(targets=('3',None),obligations=True)
        r=replace(r,targets=(replace(r.targets[0],limit_price='90'),),cash_targets=(CashTarget('USD','200'),))
        a=self.eligible(r,i)
        self.assertEqual(a.candidates[0].body.terms.limit_price,'90')
        self.assertEqual((a.plan.body.cash_calculation[0].floor,a.plan.body.cash_calculation[0].remaining),('200','428'))
        low=replace(r,cash_targets=(CashTarget('USD','50'),))
        self.assertEqual(self.eligible(low,i).plan.body.cash_calculation[0].floor,'100')
        self.blocked(replace(r,cash_targets=(CashTarget('USD','900'),)),i,'cash_shortfall')

    def test_T2_sell_floor_and_policy_floor_cannot_be_resealed(self):
        r,i=fixture(holdings=('5','0'),targets=('3',None),fee='0',obligations=True)
        a=self.eligible(r,i)
        with self.assertRaises(ContractError):
            replace(a.plan.body,request=replace(r,targets=(replace(r.targets[0],limit_price='110'),)))
        c=a.plan.body.cash_calculation[0]
        # Self-consistent cash math with floor0 must still conflict with the bound policy floor100.
        with self.assertRaises(ContractError):
            replace(a.plan.body,cash_calculation=(replace(c,floor='0',available='900',remaining='900'),))
        r=replace(r,targets=(replace(r.targets[0],limit_price='110'),))
        self.assertEqual(self.eligible(r,i).candidates[0].body.terms.limit_price,'110')

    def test_T3_future_bar_does_not_replace_selected_Q21_reference(self):
        r,i=multibar_fixture()
        data=i.current.market_inputs[0]
        old=next(x for x in data.bundle.evidence if x.revision.event_id=='event-0')
        p=replace(old.revision.payload.close,amount='130')
        bar=replace(old.revision.payload,ends_at=plus(old.revision.payload.ends_at,2),open=p,high=p,low=p,close=p)
        rev=replace(old.revision,event_id='future-bar',effective_at=bar.ends_at,published_at=bar.ends_at,payload=bar)
        obs=replace(old.observation,event_id=rev.event_id,observation_id='future-obs',revision_hash=record_hash(rev),
            observed_at=r.knowledge_cutoff,ingested_at=r.knowledge_cutoff)
        data=dataset(data,(*data.bundle.evidence,MarketItem(rev,obs)))
        r,i=rebind(r,i,datasets=(data,))
        self.assertEqual(self.eligible(r,i).candidates[0].body.terms.reference_price,'100')

    def test_T4_attempted_KR_order_at_US_open_is_still_blocked(self):
        r,i=mixed_fixture()
        key=next(k for k in i.policy.allowed_positions if k.instrument_id=='q24.KR')
        scope=replace(r.scope,markets=('KR','US'),currencies=('KRW','USD'),positions=tuple(sorted((*r.scope.positions,key),key=lambda x:x.key)))
        r=replace(r,scope=scope,targets=tuple(sorted((*r.targets,TargetValue(key,'2',None)),key=lambda x:x.position.key)))
        self.blocked(r,i,'capability_unknown')
        from quantharbor.application.target import context_target_refs
        ctx=context_target_refs(i.current.market_inputs[1])
        cap=replace(i.facts.capabilities[0],position=key,market='KR',currency='KRW',catalog_ref=ctx[0],calendar_ref=ctx[1])
        facts=replace(i.facts,capabilities=tuple(sorted((*i.facts.capabilities,cap),key=lambda x:x.position.key)))
        self.blocked(r,replace(i,facts=facts),'calendar_ineligible')

    def test_T4_untouched_holding_still_needs_fresh_price_and_classification(self):
        r,i=mixed_fixture()
        policy=replace(i.policy,max_price_age_seconds=3600)
        self.blocked(*changed(r,i,policy=policy),'stale_input')
        classes=tuple(c for c in i.facts.classifications if c.position.instrument_id!='q24.KR')
        self.blocked(r,replace(i,facts=replace(i.facts,classifications=classes)),'source_incomplete')

    def test_T5_untouched_other_market_price_freshness_caps_US_candidate(self):
        r,i=mixed_fixture()
        # KR bar ends00:31, US evaluation14:31:03; explicit bound leaves 5 seconds.
        r,i=changed(r,i,policy=replace(i.policy,max_price_age_seconds=50408))
        a=self.eligible(r,i)
        self.assertEqual(a.candidates[0].body.terms.valid_to,plus(r.evaluated_at,5))

    def test_T5_all_account_FX_freshness_and_expired_rights(self):
        r,i=separate_fx_fixture()
        r,i=changed(r,i,policy=replace(i.policy,max_fx_age_seconds=7))
        self.assertEqual(self.eligible(r,i).candidates[0].body.terms.valid_to,plus(r.evaluated_at,4))
        data=i.current.market_inputs[1]
        rights=replace(data.current_rights,valid_to=r.evaluated_at)
        current=replace(i.current,market_inputs=(i.current.market_inputs[0],replace(data,current_rights=rights)))
        self.blocked(r,replace(i,current=current,risk_points=(*i.risk_points[:-1],current)),'rights_denied')

    def test_T5_historical_risk_and_explicit_daily_source_rights_also_cap_expiry(self):
        r,i=sold_fixture()
        old=i.risk_points[0]
        data=old.market_inputs[0]
        grant=replace(data.current_rights,valid_to=plus(r.evaluated_at,2))
        historical=replace(old,market_inputs=(replace(data,current_rights=grant),*old.market_inputs[1:]))
        i=replace(i,daily_usage_inputs=(historical,))
        a=self.eligible(r,i)
        self.assertEqual(a.candidates[0].body.terms.valid_to,plus(r.evaluated_at,2))
        self.assertIn(ref('snapshot',historical.snapshot.snapshot_id,historical.snapshot),a.candidates[0].body.input_refs)

    def test_T6_fully_sold_end_to_end_and_daily_limit_rejects_next_buy(self):
        r,i=sold_fixture()
        # Sold instrument deliberately has no current order capability/classification.
        facts=replace(i.facts,classifications=tuple(x for x in i.facts.classifications if x.position in r.scope.positions),
            capabilities=tuple(x for x in i.facts.capabilities if x.position in r.scope.positions))
        i=replace(i,facts=facts)
        a=self.eligible(r,i)
        self.assertEqual((a.plan.body.account_calculation.daily_used_amount,a.plan.body.account_calculation.daily_used_quantity),('990','10'))
        self.assertNotIn(i.costs[0].position,{x.position for x in a.plan.body.positions})
        self.blocked(*changed(r,i,policy=replace(i.policy,max_daily_amount='1090')),'daily_limit')
        self.blocked(*changed(r,i,policy=replace(i.policy,max_daily_quantity='10')),'daily_limit')

    def test_T6_historical_currency_FX_bound_to_event_not_scalar_notional(self):
        r,i=historical_fx_fixture()
        a=self.eligible(r,i)
        self.assertEqual(a.plan.body.account_calculation.daily_used_amount,'2970')
        altered=replace(i,costs=(replace(i.costs[0],base_notional=known(1,ratio=False)),))
        self.assertEqual(self.eligible(r,altered).plan.body.account_calculation.daily_used_amount,'2970')
        self.blocked(*changed(r,i,policy=replace(i.policy,max_daily_amount='3200')),'daily_limit')

    def test_T6_missing_or_forged_trade_cost_evidence_is_rejected(self):
        r,i=sold_fixture()
        with self.assertRaises(ContractError):
            build(r,replace(i,costs=()))
        fact=replace(i.costs[0],trade=replace(i.costs[0].trade,sha256='b'*64))
        with self.assertRaises(ContractError):
            build(r,replace(i,costs=(fact,)))

    def test_T6_missing_historical_FX_payload_cannot_use_scalar_conversion(self):
        r,i=historical_fx_fixture()
        points=[]
        for point in i.risk_points:
            data=point.market_inputs[0]
            records=tuple(x for x in data.bundle.evidence if x.revision.series_id!='syn.fx')
            data=dataset(data,records)
            points.append(replace(point,market_inputs=(data,*point.market_inputs[1:])))
        with self.assertRaises(ContractError):
            build(r,replace(i,current=points[-1],risk_points=tuple(points),
                costs=(replace(i.costs[0],base_notional=known(2970,ratio=False)),)))
        fact=replace(i.costs[0],currency='KRW')
        with self.assertRaises(ContractError):
            build(r,replace(i,costs=(fact,)))

    def test_T6_historical_FX_history_selects_latest_eligible_event(self):
        from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
        from quantharbor.application.valuation import build_snapshot
        from quantharbor.application.research import build_bound_performance
        from quantharbor.ports.research import ResearchPointInput
        r,i=historical_fx_fixture()
        data=i.current.market_inputs[0]
        fx=next(x for x in data.bundle.evidence if x.revision.series_id=='syn.fx')
        at=plus(fx.revision.effective_at,-1)
        revision=replace(fx.revision,event_id='prior-fx',effective_at=at,published_at=at,
            payload=replace(fx.revision.payload,fx=replace(fx.revision.payload.fx,rate='2',as_of=at)))
        observation=replace(fx.observation,observation_id='prior-fx-observation',event_id=revision.event_id,
            revision_hash=record_hash(revision))
        prior=MarketItem(revision,observation)
        bars=tuple(x for x in data.bundle.evidence if x.revision.series_id!='syn.fx')
        early=dataset(data,(*bars,prior))
        late=dataset(data,(*bars,prior,fx))
        points=[]
        for point,supplied in zip(i.risk_points,(early,late)):
            s=point.snapshot
            datasets=(supplied,*point.market_inputs[1:])
            snapshot=build_snapshot(s.valuation.projection,s.valuation.request,datasets,s.valuation.policy,
                s.reconciliation_policy,SyntheticSnapshotRepository(),statement=s.reconciliation_details.statement)
            self.assertTrue(snapshot.valuation.complete)
            points.append(ResearchPointInput(snapshot,datasets))
        perf=build_bound_performance(tuple(points),i.events,costs=i.costs)
        s=points[-1].snapshot
        facts=replace(i.facts,projection_ref=ref('projection','current-projection',s.valuation.projection),
            loss_performance_ref=ref('performance','loss-performance',perf))
        r=replace(r,snapshot_ref=ref('snapshot',s.snapshot_id,s),research_refs=(ref('performance','loss-performance',perf),))
        i=replace(i,current=points[-1],risk_points=tuple(points),performance=perf,facts=facts)
        a=self.eligible(r,i)
        self.assertEqual(a.plan.body.account_calculation.daily_used_amount,'2970')

    def test_T5b_historical_risk_current_rights_ref_mismatch_rejected(self):
        r,i=sold_fixture()
        old=i.risk_points[0]
        data=old.market_inputs[0]
        grant=replace(data.current_rights,rights_ref='unrelated-valid-rights')
        self.assertTrue(all(grant.allows(at=r.evaluated_at,purpose=p,source_id=grant.source_id,
            dataset_id=grant.dataset_id,dataset_version=grant.dataset_version) for p in ('research','store')))
        historical=replace(old,market_inputs=(replace(data,current_rights=grant),*old.market_inputs[1:]))
        with self.assertRaises(ContractError):
            build(r,replace(i,risk_points=(historical,*i.risk_points[1:])))

    def test_T5b_historical_daily_current_rights_ref_mismatch_rejected(self):
        r,i=sold_fixture()
        old=i.risk_points[0]
        data=old.market_inputs[0]
        grant=replace(data.current_rights,rights_ref='unrelated-valid-rights')
        historical=replace(old,market_inputs=(replace(data,current_rights=grant),*old.market_inputs[1:]))
        with self.assertRaises(ContractError):
            build(r,replace(i,daily_usage_inputs=(historical,)))

    def test_T5b_same_reference_current_renewal_preserves_historical_grant(self):
        r,i=sold_fixture()
        old=i.risk_points[0]
        data=old.market_inputs[0]
        grant=replace(data.current_rights,valid_from=plus(r.evaluated_at,-1),valid_to=plus(r.evaluated_at,2))
        self.assertGreater(grant.valid_from,old.snapshot.created_at)
        historical=replace(old,market_inputs=(replace(data,current_rights=grant),*old.market_inputs[1:]))
        for scope in ('risk','daily'):
            with self.subTest(scope=scope):
                supplied=replace(i,risk_points=(historical,*i.risk_points[1:])) if scope=='risk' else replace(i,daily_usage_inputs=(historical,))
                a=self.eligible(r,supplied)
                self.assertEqual(a.candidates[0].body.terms.valid_to,grant.valid_to)
                self.assertEqual(historical.snapshot,old.snapshot)

    def test_T5b_historical_current_rights_still_require_identity_purposes_and_time(self):
        r,i=sold_fixture()
        old=i.risk_points[0]
        data=old.market_inputs[0]
        for change in (dict(source_id='other-source'),dict(dataset_id='other-dataset'),dict(dataset_version='other-version'),
                dict(purposes=('store',)),dict(purposes=('research',)),dict(valid_to=r.evaluated_at),
                dict(valid_from=plus(r.evaluated_at,1)),dict(revoked_at=r.evaluated_at)):
            for scope in ('risk','daily'):
                with self.subTest(change=change,scope=scope):
                    historical=replace(old,market_inputs=(replace(data,current_rights=replace(data.current_rights,**change)),*old.market_inputs[1:]))
                    supplied=replace(i,risk_points=(historical,*i.risk_points[1:])) if scope=='risk' else replace(i,daily_usage_inputs=(historical,))
                    self.blocked(r,supplied,'rights_denied')

    def test_T6b_partial_newer_FX1_cannot_undercount_USD990_sale_as_990(self):
        r,i=extra_daily_fx_fixture()
        r,i=changed(r,i,policy=replace(i.policy,max_daily_amount='3200'))
        a=build(r,i)
        # 완전 FX3이면2970+신규 매수는3200 초과. partial FX1이면990으로 낮아졌다.
        calculation=a.plan.body.account_calculation
        used=None if calculation is None else calculation.daily_used_amount
        self.assertEqual((a.result.body.outcome,a.candidates),('blocked',()),'daily_used_amount='+str(used))
        self.assertIn('source_incomplete',{x.code for x in a.result.body.failures})

    def test_T6b_partial_older_FX4_cannot_silently_fall_back_to_complete_FX3(self):
        r,i=extra_daily_fx_fixture(seconds=-1,rate='4')
        self.blocked(r,i,'source_incomplete')

    def test_T6b_complete_newer_daily_FX_proof_and_original_FX3_paths_pass(self):
        r,i=historical_fx_fixture()
        self.assertEqual(self.eligible(r,i).plan.body.account_calculation.daily_used_amount,'2970')
        self.blocked(*changed(r,i,policy=replace(i.policy,max_daily_amount='3200')),'daily_limit')
        r,i=extra_daily_fx_fixture(complete=True)
        r,i=changed(r,i,policy=replace(i.policy,max_daily_amount='3200'))
        self.assertEqual(self.eligible(r,i).plan.body.account_calculation.daily_used_amount,'990')

