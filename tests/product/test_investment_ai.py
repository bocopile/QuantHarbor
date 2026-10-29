from dataclasses import replace
import json
import unittest

from quantharbor.domain import investment_ai as d
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import parse_payload
from quantharbor.application.investment_ai import Sources,performance_ref,validate_response,ReadonlyDispatcher,review_result,timezone_ref
from quantharbor.adapters.synthetic_investment_ai import SyntheticAIRepository,AIDenied,DeterministicSyntheticClient
from synthetic_investment_ai import *


class InvestmentAITests(unittest.TestCase):
    def test_document_exact_positive_and_invalid_unicode_byte_offset(self):
        src=document_source()
        c=citation(src)
        sources=Sources(documents=(src,))
        req=request((c.manifest_ref,),required_outputs=('document','narrative'))
        resp=response(citations=(c,),narrative=(d.NarrativeClaim('q','quote',c.exact_quote,(0,)),))
        self.assertEqual(run(req,resp,sources=sources).status,'complete')
        bad=d.Citation(*document_refs(src),1,4,'합')
        self.assertEqual(run(req,response(citations=(bad,)),sources=Sources(documents=(src,))).status,'invalid')

    def test_sourcebound_flow_values_and_numeric_red(self):
        src=flow_source()
        req=request((performance_ref(src),),account_ref=src.points[0].snapshot.account_ref,required_outputs=('numeric',))
        resp=response(numeric=(numeric(src,'performance.twr','0.21'),numeric(src,'performance.amount_pnl','26',id='n2')))
        self.assertEqual(run(req,resp,sources=Sources(financial=(src,))).status,'complete')
        wrong=response(numeric=(numeric(src,'performance.twr','21'),))
        self.assertEqual(run(req,wrong,sources=Sources(financial=(src,))).status,'invalid')

    def test_mdd_sourcebound(self):
        src=mdd_source()
        self.assertEqual(src.performance.observed_mdd.value,'0.25')
        req=request((performance_ref(src),),account_ref=src.points[0].snapshot.account_ref)
        resp=response(numeric=(numeric(src,'performance.observed_mdd','0.10'),))
        self.assertEqual(run(req,resp,sources=Sources(financial=(src,))).status,'invalid')

    def test_candidate_actual_source_unchanged(self):
        src=candidate_source()
        self.assertTrue(src.artifacts.candidates)
        c=src.artifacts.candidates[0]
        r=d.ref('candidate',c.candidate_id,c)
        req=request((r,),account_ref=src.request.account_ref,scope=src.request.scope.positions,as_of=src.request.as_of,
            knowledge_cutoff=src.request.knowledge_cutoff,evaluated_at=src.request.evaluated_at,deadline=src.request.expires_at)
        now=src.request.evaluated_at
        claim=d.NumericClaim('quantity',r,'candidate.quantity',c.body.terms.position,None,'3','share',None,req.as_of)
        result=run(req,response(numeric=(claim,)),sources=Sources(candidates=(src,)),clock=lambda:now)
        self.assertEqual(result.status,'complete')
        self.assertEqual(d.ref('candidate',c.candidate_id,c),r)

    def test_current_rights_on_cash_only_unused_market(self):
        from synthetic_research import flow_fixture
        from quantharbor.ports.investment_ai import FinancialSource
        pts,events,bi,b=flow_fixture(with_market=True)
        def ai(point):
            return replace(point,market_inputs=tuple(replace(x,current_rights=replace(x.current_rights,purposes=('store','research','report','ai'))) for x in point.market_inputs))
        # only consumer current grant changes; historical proof remains unchanged intentionally.
        src=FinancialSource(tuple(ai(p) for p in pts),events,None,(),tuple(ai(p) for p in bi))
        r=d.ref('snapshot',src.points[0].snapshot.snapshot_id,src.points[0].snapshot)
        req=request((r,),account_ref=src.points[0].snapshot.account_ref)
        bad=replace(src,points=(replace(src.points[0],market_inputs=tuple(replace(x,current_rights=replace(x.current_rights,rights_ref='other')) for x in src.points[0].market_inputs)),*src.points[1:]))
        self.assertEqual(run(req,response(),sources=Sources(financial=(bad,))).status,'blocked')

    def test_direct_parser_and_repository_roundtrip(self):
        for obj in (policy(),request(),response(),d.priced(69,0)):
            self.assertEqual(parse_payload(d.encoded(obj)).payload,obj)
        repo=SyntheticAIRepository()
        r=request()
        repo.append('request',r.request_id,r)
        self.assertEqual(repo.get(d.ref('request',r.request_id,r)),r)
        with self.assertRaises(ContractError):
            replace(r,schema_version=True)
        with self.assertRaises(ContractError):
            d.Usage(True,0,1,2)
        with self.assertRaises(ContractError):
            parse_payload(d.encoded(r).replace(b'"schema_version":1',b'"schema_version":1,"schema_version":1',1))

    def test_budget_reservation_settle_and_unknown(self):
        p=policy(golden=True)
        repo=SyntheticAIRepository()
        req=request(p=p)
        a,_=repo.reserve(req,p,'one',d.priced(69,0),at=NOW)
        repo.dispatch('one',at=NOW)
        with self.assertRaises(AIDenied):
            repo.reserve(replace(req,request_id='two'),p,'two',d.priced(39,0),at=NOW)
        repo.settle('one',d.priced(49,0),at=NOW)
        self.assertEqual(repo.balance(p),50)
        self.assertEqual(repo.settle('one',d.priced(49,0),at=NOW).actual_usage.charge,50)
        with self.assertRaises(ContractError):
            repo.settle('one',d.priced(48,0),at=NOW)

    def test_bad_payload_known_usage_settled(self):
        from quantharbor.ports.investment_ai import ClientReply
        class Fault:
            def invoke(self,*args):
                return ClientReply(b'{',d.priced(49,0))
        sources=Sources()
        result=run(request(),response(),sources=sources,client=Fault())
        self.assertEqual(result.status,'invalid')
        self.assertEqual(sources.repository.attempt('a1').actual_usage.charge,50)

    def test_period_timezone_golden(self):
        z=synthetic_timezone('KR')
        p=d.Period('weekly','2024-03-03T15:00:00Z','2024-03-10T15:00:00Z','Asia/Seoul',timezone_ref(z),1)
        self.assertEqual(parse_payload(d.encoded(p)).payload,p)
        with self.assertRaises(ContractError):
            replace(p,start='2024-03-04T00:00:00Z')
