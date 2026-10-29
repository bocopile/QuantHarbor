from dataclasses import replace
from datetime import datetime,timedelta
import unittest

from quantharbor.domain import investment_ai as d
from quantharbor.domain.primitives import ContractError,utc_instant
from quantharbor.application.investment_ai import Sources,performance_ref,ReadonlyDispatcher,review_result,current_result
from quantharbor.adapters.synthetic_investment_ai import SyntheticAIRepository,AIDenied,DeterministicSyntheticClient
from synthetic_investment_ai import *


class AIBoundsTests(unittest.TestCase):
    def test_direct_constructor_caps_and_int64_roundtrip(self):
        from quantharbor.domain.serialization import parse_payload
        self.assertEqual(parse_payload(d.encoded(d.Usage(2**63-1,0,1,1))).payload.input_tokens,2**63-1)
        with self.assertRaises(ContractError):
            response(assumptions=('가'*682,)*64)
        with self.assertRaises(ContractError):
            response(numeric=tuple(numeric(flow_source(),'performance.twr','0.21',id='n'+str(i)) for i in range(33)))

    def test_budget_capacity_before_client_and_concurrent_limit(self):
        repo=SyntheticAIRepository(capacity=4)
        client=DeterministicSyntheticClient(response())
        result=run(request(),response(),sources=Sources(repository=repo),client=client)
        self.assertEqual((result.status,result.reasons,client.calls),('blocked',('capacity',),0))
        repo=SyntheticAIRepository()
        p=policy();req=request(p=p)
        for n in ('one','two'):
            repo.reserve(replace(req,request_id=n),p,n,d.priced(1,0),at=NOW)
        with self.assertRaises(AIDenied):
            repo.reserve(replace(req,request_id='three'),p,'three',d.priced(1,0),at=NOW)
        repo.cancel('one',at=NOW)
        repo.reserve(replace(req,request_id='three'),p,'three',d.priced(1,0),at=NOW)

    def test_query_positive_fixed_scope_and_limit(self):
        src=document_source();c=citation(src);req=request((c.manifest_ref,),role='collector')
        dispatcher=ReadonlyDispatcher(req,Sources(documents=(src,)),clock=lambda:NOW)
        for _ in range(16):
            self.assertEqual(dispatcher.execute(d.Query('document_view',c.manifest_ref)),src.bundle.manifest)
        with self.assertRaises(AIDenied):
            dispatcher.execute(d.Query('document_view',c.manifest_ref))

    def test_known_usage_after_deadline_and_predispatch_cancellation(self):
        req=request(deadline='2024-03-08T14:31:10Z')
        values=iter((NOW,NOW,'2024-03-08T14:31:11Z','2024-03-08T14:31:11Z'))
        sources=Sources();client=DeterministicSyntheticClient(response())
        result=run(req,response(),sources=sources,client=client,clock=lambda:next(values))
        self.assertEqual(result.status,'failed')
        self.assertEqual(sources.repository.attempt('a1').actual_usage.charge,50)
        values=iter((NOW,'2024-03-08T14:31:11Z','2024-03-08T14:31:11Z'))
        sources=Sources();client=DeterministicSyntheticClient(response())
        result=run(req,response(),sources=sources,client=client,clock=lambda:next(values))
        self.assertEqual((result.status,client.calls),('blocked',0))
        self.assertEqual(sources.repository.attempt('a1').state,'cancelled_before_dispatch')

    def test_current_report_rights_at_presentation(self):
        src=document_source();c=citation(src)
        req=request((c.manifest_ref,),role='report',purpose='ai_report')
        sources=Sources(documents=(src,))
        result=run(req,response(citations=(c,)),sources=sources)
        self.assertEqual(result.status,'complete')
        denied=replace(src,current_rights=replace(src.current_rights,purposes=('ai','research','store')))
        current=Sources(documents=(denied,),repository=sources.repository)
        _,status,reasons=current_result(d.ref('result',result.result_id,result),current,at=NOW)
        self.assertEqual(status,'blocked')
        self.assertIn('rights_denied',reasons)

    def test_snapshot_and_cost_selectors_actual_bound_sources(self):
        src=candidate_source();point=src.inputs.current;snap=point.snapshot
        financial=FinancialSource((point,),src.inputs.events)
        sr=d.ref('snapshot',snap.snapshot_id,snap)
        req=request((sr,),account_ref=snap.account_ref,scope=src.request.scope.positions)
        claims=(d.NumericClaim('nav',sr,'snapshot.nav',None,None,'1000','currency','USD',snap.as_of),
            d.NumericClaim('cash',sr,'snapshot.economic_cash',None,None,'1000','currency','USD',snap.as_of))
        self.assertEqual(run(req,response(numeric=claims),sources=Sources(financial=(financial,))).status,'complete')
        for selector in ('performance.fees','performance.taxes','performance.slippage'):
            flow=flow_source()
            q=request((performance_ref(flow),),account_ref=flow.points[0].snapshot.account_ref)
            self.assertEqual(run(q,response(numeric=(numeric(flow,selector,'0'),)),sources=Sources(financial=(flow,))).status,'complete')

    def test_report_full_period_preserves_known_metrics_and_intervention_unknown(self):
        from quantharbor.adapters.synthetic_ledger import SyntheticLedger
        from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
        from quantharbor.application.valuation import build_snapshot
        from quantharbor.domain.ledger import SyntheticLedgerSubmission,CashLeg,LedgerCompleteness,LedgerBaseline
        from quantharbor.ports.research import ResearchPointInput
        base=flow_source().points[0].snapshot
        store=SyntheticLedger();points=[]
        times=('2024-03-03T15:00:00Z','2024-03-10T15:00:00Z')
        for i,amount in enumerate(('100','21')):
            s=SyntheticLedgerSubmission(1,'synthetic','synthetic-account:weekly','weekly','w'+str(i),1,None,'golden-mapping-v1',
                'baseline' if i==0 else 'dividend',times[i],'original',None,(CashLeg('settled_cash','USD',amount,'settlement'),
                CashLeg('opening_equity' if i==0 else 'dividend_income','USD','-'+amount,'settlement')),(),('synthetic:weekly',),
                LedgerCompleteness(True,True,True),LedgerBaseline(True,True,'entire_account') if i==0 else None,(),None)
            self.assertEqual(store.append(s,recorded_at=times[i]).status,'accepted')
            projection=store.replay(s.account_ref,as_of=times[i],knowledge_cutoff=times[i])
            req=replace(base.valuation.request,account_ref=s.account_ref,request_id='wv'+str(i),ledger_cursor=projection.ledger_cursor,
                as_of=times[i],knowledge_cutoff=times[i],evaluated_at=times[i])
            snap=build_snapshot(projection,req,(),base.valuation.policy,base.reconciliation_policy,SyntheticSnapshotRepository())
            points.append(ResearchPointInput(snap,()))
        events=tuple(store.state(s.account_ref).events);perf=build_bound_performance(tuple(points),events)
        src=FinancialSource(tuple(points),events,perf);z=synthetic_timezone('KR')
        from quantharbor.application.investment_ai import timezone_ref
        period=d.Period('weekly',*times,'Asia/Seoul',timezone_ref(z),1)
        at='2024-03-11T00:00:00Z'
        req=request((performance_ref(src),timezone_ref(z)),role='report',purpose='ai_report',period=period,required_outputs=('period',),
            account_ref=s.account_ref,as_of=at,knowledge_cutoff=at,evaluated_at=at,deadline='2024-03-11T00:01:00Z')
        result=run(req,response(),sources=Sources(financial=(src,),timezones=(z,)),clock=lambda:at)
        self.assertEqual(result.status,'partial')
        self.assertEqual([m.observed for m in result.period_review.metrics][:2],['0.21','21'])
        self.assertEqual(result.period_review.intervention_unknowns,('intervention_unknown',))
