from dataclasses import replace
import unittest

from quantharbor.domain import investment_ai as d
from quantharbor.domain.primitives import ContractError
from quantharbor.application.investment_ai import Sources,performance_ref,review_result
from quantharbor.adapters.synthetic_investment_ai import SyntheticAIRepository,AIDenied,DeterministicSyntheticClient
from synthetic_investment_ai import *


class AISourceTests(unittest.TestCase):
    def test_actual_incomplete_market_proof_stays_partial_even_cash_nav_known(self):
        import synthetic_valuation as v
        from quantharbor.domain.market_data import ExpectedEvent
        from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
        from quantharbor.application.valuation import build_snapshot
        from quantharbor.ports.research import ResearchPointInput
        grant=replace(v.rights(),purposes=('ai','store','research','report'))
        data=v.market(historical_rights=grant,scope_changes={'expected':(ExpectedEvent('syn.raw','syn.event',v.END),ExpectedEvent('syn.raw','missing-event',v.END))})
        store=v.ledger(holdings=(),cash='100')
        projection=store.replay(v.ACCOUNT,as_of=v.END,knowledge_cutoff=v.NOW)
        snap=build_snapshot(projection,v.request(),(data,),v.policy(),v.reconciliation_policy(),SyntheticSnapshotRepository())
        self.assertEqual(snap.valuation.nav,'100')
        self.assertTrue(any(not p.usable for p in snap.valuation.market_proofs))
        src=FinancialSource((ResearchPointInput(snap,(data,)),),tuple(store.state(v.ACCOUNT).events))
        r=d.ref('snapshot',snap.snapshot_id,snap)
        req=request((r,),account_ref=v.ACCOUNT)
        claim=d.NumericClaim('nav',r,'snapshot.nav',None,None,'100','currency','USD',snap.as_of)
        result=run(req,response(numeric=(claim,)),sources=Sources(financial=(src,)))
        self.assertEqual((result.status,result.reasons),('partial',('proof_incomplete',)))

    def test_current_ai_rights_on_all_actual_performance_points(self):
        src=mdd_source()
        r=performance_ref(src)
        req=request((r,),account_ref=src.points[0].snapshot.account_ref)
        for changed in (dict(purposes=('store','research','report')),dict(rights_ref='replacement-current'),dict(revoked_at=NOW)):
            points=tuple(replace(p,market_inputs=tuple(replace(x,current_rights=replace(x.current_rights,**changed)) for x in p.market_inputs)) for p in src.points)
            denied=replace(src,points=points)
            result=run(req,response(numeric=(numeric(src,'performance.twr','0.08'),)),sources=Sources(financial=(denied,)))
            self.assertEqual(result.status,'blocked')

    def test_scalar_benchmark_is_semantic_unknown(self):
        from quantharbor.domain.research import known
        src=flow_source()
        performance=build_bound_performance(src.points,src.events,boundaries=src.boundaries,boundary_inputs=src.boundary_inputs,benchmark_return=known('0.1'))
        scalar=replace(src,performance=performance)
        req=request((performance_ref(scalar),),account_ref=src.points[0].snapshot.account_ref)
        result=run(req,response(numeric=(numeric(scalar,'performance.benchmark_return','0.1'),)),sources=Sources(financial=(scalar,)))
        self.assertEqual((result.status,result.reasons),('partial',('unknown_metric',)))

    def test_sourcebound_benchmark_positive(self):
        from quantharbor.domain.research import known
        src=flow_source()
        performance=build_bound_performance(src.points,src.events,boundaries=src.boundaries,boundary_inputs=src.boundary_inputs,benchmark_return=known('0.21'))
        bound=replace(src,performance=performance,benchmark=src)
        req=request((performance_ref(bound),),account_ref=src.points[0].snapshot.account_ref)
        result=run(req,response(numeric=(numeric(bound,'performance.benchmark_return','0.21'),)),sources=Sources(financial=(bound,)))
        self.assertEqual(result.status,'complete')

    def test_result_cannot_be_stored_without_request_and_attempt_evidence(self):
        source=Sources();result=run(request(),response(),sources=source)
        with self.assertRaises(ContractError):
            SyntheticAIRepository().append('result',result.result_id,result)
        with self.assertRaises(ContractError):
            source.repository.append('attempt','forged',source.repository.attempt('a1'))

    def test_request_caps_accumulate_before_client(self):
        p=policy();repo=SyntheticAIRepository();req=request(caps=d.Usage(100,0,2,102))
        repo.reserve(req,p,'a1',d.priced(69,0),at=NOW);repo.dispatch('a1',at=NOW);repo.settle('a1',d.priced(69,0),at=NOW)
        with self.assertRaises(AIDenied):
            repo.reserve(req,p,'a2',d.priced(39,0),at=NOW)

    def test_hypothesis_rights_revocation_without_historical_mutation(self):
        src=document_source();c=citation(src);sources=Sources(documents=(src,));req=request((c.manifest_ref,))
        result=run(req,response(citations=(c,),narrative=(d.NarrativeClaim('h','hypothesis','미검증 가설',(0,)),)),sources=sources)
        h=d.Hypothesis(1,'synthetic','hyp-source',d.ref('result',result.result_id,result),'미검증 가설',('h',),(),(),'후속 자료로 반증',None,
            sources.repository.hypothesis_dependencies(d.ref('result',result.result_id,result)),NOW,'2024-03-08T14:31:30Z','proposed',None,None)
        sources.repository.append('hypothesis',h.hypothesis_id,h)
        href=d.ref('hypothesis',h.hypothesis_id,h)
        self.assertEqual(sources.hypothesis(href,req,NOW),h)
        denied=replace(src,current_rights=replace(src.current_rights,revoked_at=NOW))
        current=Sources(documents=(denied,),repository=sources.repository)
        with self.assertRaises(AIDenied):
            current.hypothesis(href,req,NOW)
        self.assertEqual(sources.repository.get(href),h)

    def test_role_global_policy_identity_and_capacity_bytes(self):
        p=policy();req=request();repo=SyntheticAIRepository(byte_capacity=1000)
        with self.assertRaises(AIDenied):
            repo.reserve(req,p,'first',d.priced(1,0),at=NOW)
        self.assertEqual(repo._records,{})
        repo=SyntheticAIRepository();repo.reserve(req,p,'first',d.priced(1,0),at=NOW)
        changed=replace(p,policy_id='other-policy',window_caps=replace(p.window_caps,charge=100))
        with self.assertRaises(ContractError):
            repo.reserve(request(p=changed,request_id='second',role='collector'),changed,'second',d.priced(1,0),at=NOW)

    def test_final_document_scope_binds_instrument_venue_and_mapping(self):
        from quantharbor.domain.valuation import PositionKey
        src=document_source();c=citation(src)
        mapping=src.catalog.mappings[0]
        good=PositionKey(mapping.instrument_id,mapping.execution_venue_id,mapping.mapping_version,'share')
        for scope,status in (((good,),'complete'),((replace(good,instrument_id='outside'),),'blocked'),
                             ((replace(good,venue_id='outside'),),'blocked'),((replace(good,mapping_version='outside'),),'blocked')):
            result=run(request((c.manifest_ref,),scope=scope),response(citations=(c,)),sources=Sources(documents=(src,)))
            self.assertEqual(result.status,status)

    def test_final_incomplete_ledger_cannot_complete_cash_claim(self):
        from quantharbor.adapters.synthetic_ledger import SyntheticLedger
        from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
        from quantharbor.application.valuation import build_snapshot
        from quantharbor.ports.research import ResearchPointInput
        from synthetic_ledger import baseline,submission,cash_pair
        base=flow_source().points[0].snapshot
        store=SyntheticLedger()
        opening=replace(baseline(),account_ref=base.account_ref,effective_at='2024-01-01T00:00:00Z',
            cash_legs=cash_pair('settled_cash','100','opening_equity'),position_deltas=())
        self.assertEqual(store.append(opening,recorded_at=opening.effective_at).status,'accepted')
        overfee=replace(submission('overfee','fee',cash_legs=cash_pair('settled_cash','-200','fee_expense')),
            account_ref=base.account_ref,effective_at='2024-01-02T00:00:00Z')
        self.assertEqual(store.append(overfee,recorded_at=overfee.effective_at).status,'accepted')
        projection=store.replay(base.account_ref,as_of=overfee.effective_at,knowledge_cutoff=overfee.effective_at)
        self.assertFalse(projection.complete)
        req=replace(base.valuation.request,request_id='incomplete-cash',ledger_cursor=projection.ledger_cursor,
            as_of=overfee.effective_at,knowledge_cutoff=overfee.effective_at,evaluated_at=overfee.effective_at)
        snap=build_snapshot(projection,req,(),base.valuation.policy,base.reconciliation_policy,SyntheticSnapshotRepository())
        fs=FinancialSource((ResearchPointInput(snap,()),),tuple(store.state(base.account_ref).events))
        sr=d.ref('snapshot',snap.snapshot_id,snap)
        claim=d.NumericClaim('cash',sr,'snapshot.economic_cash',None,None,'-100','currency','USD',snap.as_of)
        result=run(request((sr,),account_ref=base.account_ref),response(numeric=(claim,)),sources=Sources(financial=(fs,)))
        self.assertEqual((result.status,result.reasons),('partial',('proof_incomplete',)))
