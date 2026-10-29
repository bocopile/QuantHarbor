"""AS1~5 실제 공개 경로 회귀. 고정24 평가와 별도이며 외부 호출 없음."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier, Event
import unittest

from quantharbor.domain import investment_ai as d
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import parse_payload
from quantharbor.application.investment_ai import Sources, ReadonlyDispatcher, review_result, timezone_ref, validate_response
from quantharbor.adapters.synthetic_investment_ai import AIDenied, DeterministicSyntheticClient
from quantharbor.ports.investment_ai import ClientReply
from synthetic_investment_ai import NOW, policy, request, response, document_source, citation, run, synthetic_timezone


class AISecurityTests(unittest.TestCase):
    def hypothesis_fixture(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,))
        req=request((c.manifest_ref,))
        result=run(req,response(citations=(c,),narrative=(d.NarrativeClaim('h','hypothesis','합성 가설',(0,)),)),sources=sources)
        origin=d.ref('result',result.result_id,result)
        h=d.Hypothesis(1,'synthetic','h',origin,'합성 가설',('h',),(),(),'반대 자료로 반증',None,
            sources.repository.hypothesis_dependencies(origin),NOW,'2024-03-08T14:31:30Z','proposed',None,None)
        return src,sources,req,result,h

    def test_AS1_cached_replay_requires_current_rights_without_old_body(self):
        src=document_source(); c=citation(src)
        req=request((c.manifest_ref,),role='report',purpose='ai_report')
        sources=Sources(documents=(src,)); client=DeterministicSyntheticClient(response(citations=(c,)))
        old=run(req,response(),sources=sources,client=client)
        self.assertEqual(old.status,'complete')
        self.assertEqual(run(req,response(),sources=sources,client=client),old)
        denied=replace(src,current_rights=replace(src.current_rights,purposes=('ai','research','store')))
        current=Sources(documents=(denied,),repository=sources.repository)
        replay=run(req,response(),sources=current,client=client)
        self.assertEqual(replay.status,'blocked')
        self.assertIsNone(replay.response)
        self.assertEqual((replay.input_manifest,replay.query_receipts,replay.checks), ((),(),()))
        self.assertEqual(client.calls,1)
        self.assertEqual(sources.repository.result_for('a1'),old)

    def test_AS2_hypothesis_dependencies_cannot_replace_origin(self):
        src=document_source(); c=citation(src); zone=synthetic_timezone('KR')
        sources=Sources(documents=(src,),timezones=(zone,)); req=request((c.manifest_ref,))
        result=run(req,response(citations=(c,),narrative=(d.NarrativeClaim('h','hypothesis','합성 가설',(0,)),)),sources=sources)
        self.assertEqual(result.status,'complete')
        h=d.Hypothesis(1,'synthetic','h',d.ref('result',result.result_id,result),'합성 가설',('h',),(),(),
            '반대 자료로 반증',None,(c.manifest_ref,),NOW,'2024-03-08T14:31:30Z','proposed',None,None)
        forged=parse_payload(d.encoded(replace(h,dependencies=(timezone_ref(zone),)))).payload
        with self.assertRaises(ContractError):
            sources.repository.append('hypothesis',forged.hypothesis_id,forged)

    def test_AS3_blocked_result_cannot_be_resealed_complete(self):
        from synthetic_investment_ai import candidate_source
        from quantharbor.ports.investment_ai import FinancialSource
        cs=candidate_source(); p=cs.inputs.current
        src=FinancialSource((p,),cs.inputs.events); sr=d.ref('snapshot',p.snapshot.snapshot_id,p.snapshot)
        sources=Sources(financial=(src,))
        req=request((sr,),role='collector',account_ref=p.snapshot.account_ref)
        result=run(req,response(queries=(d.Query('snapshot_view',sr),)),sources=sources)
        self.assertEqual((result.status,result.reasons),('blocked',('query_denied',)))
        self.assertEqual(sources.repository.attempt('a1').state,'settled')
        forged=parse_payload(d.encoded(replace(result,result_id='forged',status='complete',reasons=(),
            checks=tuple(c for c in result.checks if c.outcome=='pass'),
            query_receipts=(d.QueryReceipt(d.Query('snapshot_view',sr),(sr,),NOW),)))).payload
        with self.assertRaises(ContractError):
            sources.repository.append('result',forged.result_id,forged)

    def test_AS4_malformed_postdispatch_usage_blocks_next_window(self):
        class BadUsage:
            def invoke(self,*args):
                return ClientReply(d.encoded(response()),d.Usage(0,0,1,0))
        p=policy(window_end='2024-03-08T14:31:09Z'); req=request(p=p)
        sources=Sources(); result=run(req,response(),p=p,sources=sources,client=BadUsage())
        a=sources.repository.attempt('a1')
        self.assertEqual(a.state,'unknown_charge')
        self.assertIsNone(a.actual_usage)
        self.assertEqual(a.reserved_usage,d.priced(69,20))
        self.assertIn('unknown_charge',result.reasons)
        newer=policy(policy_id='next',window_start=p.window_end)
        newreq=request(p=newer,request_id='next',evaluated_at=p.window_end)
        client=DeterministicSyntheticClient(response())
        blocked=run(newreq,response(),p=newer,sources=sources,client=client,attempt='a2',clock=lambda:p.window_end)
        self.assertEqual((blocked.status,client.calls),('blocked',0))

    def test_AS5_shared_request_query_total_across_attempts(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,))
        req=request((c.manifest_ref,),role='collector',caps=d.Usage(32768,8192,4,49156))
        resp=response(queries=(d.Query('document_view',c.manifest_ref),)*16)
        results=[run(req,resp,sources=sources,attempt='a'+str(i)) for i in range(2)]
        self.assertEqual(results[0].status,'complete')
        self.assertEqual(sum(len(r.query_receipts) for r in results),16)
        self.assertEqual(results[1].status,'blocked')

    def test_cached_replay_missing_source_has_no_body(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,)); req=request((c.manifest_ref,))
        old=run(req,response(citations=(c,)),sources=sources)
        current=Sources(repository=sources.repository)
        result=run(req,response(),sources=current)
        self.assertEqual(result.status,'blocked')
        self.assertIsNone(result.response)
        self.assertEqual(sources.repository.result_for('a1'),old)

    def test_same_ref_current_grant_research_still_valid_and_idempotent(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,)); req=request((c.manifest_ref,))
        old=run(req,response(citations=(c,)),sources=sources)
        current=Sources(documents=(replace(src,current_rights=replace(src.current_rights,purposes=('ai','store','research'))),),repository=sources.repository)
        client=DeterministicSyntheticClient(response())
        self.assertEqual(run(req,response(),sources=current,client=client),old)
        self.assertEqual(client.calls,0)

    def test_hypothesis_derived_closure_every_dependency_is_mandatory(self):
        src,sources,req,result,h=self.hypothesis_fixture()
        self.assertTrue({'document','rights','revision','observation','original','context'}<=set(r.kind for r in h.dependencies))
        for dep in h.dependencies:
            omitted=replace(h,dependencies=tuple(r for r in h.dependencies if r!=dep))
            with self.assertRaises(ContractError):
                sources.repository.append('hypothesis',omitted.hypothesis_id,omitted)
        sources.repository.append('hypothesis',h.hypothesis_id,h)
        hr=d.ref('hypothesis',h.hypothesis_id,h)
        self.assertEqual(sources.hypothesis(hr,req,NOW),h)
        denied=Sources(documents=(replace(src,current_rights=replace(src.current_rights,revoked_at=NOW)),),repository=sources.repository)
        with self.assertRaises(AIDenied):
            denied.hypothesis(hr,req,NOW)
        with self.assertRaises(AIDenied):
            denied.repository.append('hypothesis','new',replace(h,hypothesis_id='new'),sources=denied)
        with self.assertRaises(AIDenied):
            denied.repository.append('hypothesis','implicit-current',replace(h,hypothesis_id='implicit-current'))
        self.assertEqual(sources.repository.get(hr),h)

    def test_hypothesis_candidate_policy_strategy_and_numeric_origin(self):
        from synthetic_investment_ai import candidate_source
        cs=candidate_source(); c=cs.artifacts.candidates[0]; cr=d.ref('candidate',c.candidate_id,c)
        sources=Sources(candidates=(cs,))
        req=request((cr,),account_ref=cs.request.account_ref,scope=cs.request.scope.positions,
            as_of=cs.request.as_of,knowledge_cutoff=cs.request.knowledge_cutoff,evaluated_at=cs.request.evaluated_at,deadline=cs.request.expires_at)
        claim=d.NumericClaim('quantity',cr,'candidate.quantity',c.body.terms.position,None,'3','share',None,req.as_of)
        result=run(req,response(numeric=(claim,)),sources=sources,clock=lambda:req.evaluated_at)
        self.assertEqual(result.status,'complete')
        deps=sources.repository.hypothesis_dependencies(d.ref('result',result.result_id,result))
        self.assertTrue({'candidate','plan','policy','strategy','snapshot','rights'}<=set(r.kind for r in deps))

    def test_result_and_review_caller_proofs_are_not_processing_evidence(self):
        sources=Sources(); req=request(); result=run(req,response(),sources=sources)
        self.assertEqual(result.status,'complete')
        for forged in (replace(result,result_id='copied'),replace(result,result_id='copy2',checks=())):
            canonical=parse_payload(d.encoded(forged)).payload
            with self.assertRaises(ContractError):
                sources.repository.append('result',canonical.result_id,canonical)
            with self.assertRaises(ContractError):
                sources.repository.finish('a1',canonical)
        rr=d.ref('result',result.result_id,result); rreq=replace(req,request_id='review',review_subject_ref=rr)
        sources.repository.append('request',rreq.request_id,rreq)
        fake=d.ResearchReview(1,'synthetic','fake',d.ref('request',rreq.request_id,rreq),rr,
            d.ClientIdentity('reviewer','synthetic',None),NOW,(),(),(),'accepted',None)
        with self.assertRaises(ContractError):
            sources.repository.append('review',fake.review_id,parse_payload(d.encoded(fake)).payload)

    def test_review_valid_duplicate_and_current_rights(self):
        src=document_source(); c=citation(src); req=request((c.manifest_ref,))
        sources=Sources(documents=(src,)); result=run(req,response(citations=(c,)),sources=sources)
        rr=d.ref('result',result.result_id,result); rreq=replace(req,request_id='review',review_subject_ref=rr)
        reviewer=d.ClientIdentity('reviewer','synthetic',None)
        review=review_result(rreq,rr,reviewer,sources,at=NOW)
        self.assertEqual(review.verdict,'accepted')
        self.assertEqual(review_result(rreq,rr,reviewer,sources,at=NOW),review)
        denied=Sources(documents=(replace(src,current_rights=replace(src.current_rights,revoked_at=NOW)),),repository=sources.repository)
        blocked=review_result(rreq,rr,replace(reviewer,invocation_id='later'),denied,at=NOW)
        self.assertEqual(blocked.verdict,'blocked')
        self.assertEqual(sources.repository.get(d.ref('review',review.review_id,review)),review)

    def test_review_request_query_intersection_and_no_quota_reexecution(self):
        src=document_source(); c=citation(src); req=request((c.manifest_ref,))
        sources=Sources(documents=(src,)); result=run(req,response(queries=(d.Query('document_view',c.manifest_ref),)),sources=sources)
        self.assertEqual(result.status,'complete')
        rr=d.ref('result',result.result_id,result); rreq=replace(req,request_id='review',review_subject_ref=rr,allowed_queries=())
        review=review_result(rreq,rr,d.ClientIdentity('reviewer','synthetic',None),sources,at=NOW)
        self.assertEqual((review.verdict,review.findings),('blocked',('query_denied',)))
        self.assertEqual(sources.repository.query_count(result.request_ref),1)

    def test_malformed_settlement_is_atomic_and_never_reverts_known_usage(self):
        sources=Sources(); repo=sources.repository; p=policy(); req=request(p=p)
        repo.reserve(req,p,'raw',d.priced(69,20),at=NOW); repo.dispatch('raw',at=NOW)
        unknown=repo.settle('raw',d.Usage(0,0,0,0),at=NOW)
        self.assertEqual((unknown.state,unknown.reasons),('unknown_charge',('unknown_charge',)))
        self.assertEqual(repo.settle('raw',None,at=NOW),unknown)
        with self.assertRaises(ContractError):
            repo.settle('raw',d.priced(1,0),at=NOW)
        clean=Sources(); run(request(),response(),sources=clean)
        a=clean.repository.attempt('a1')
        with self.assertRaises(ContractError):
            clean.repository.settle('a1',d.Usage(0,0,1,0),at=NOW)
        self.assertEqual(clean.repository.attempt('a1'),a)

    def test_concurrent_dispatchers_share_total_and_idempotent_replay_spends_zero_queries(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,))
        req=request((c.manifest_ref,),role='collector',caps=d.Usage(32768,8192,4,49156))
        barrier=Barrier(2)
        class Inline:
            def invoke(self,request,attempt,dispatcher):
                barrier.wait(timeout=10)
                for _ in range(12):
                    try:
                        dispatcher.execute(d.Query('document_view',c.manifest_ref))
                    except AIDenied:
                        break
                return ClientReply(d.encoded(response()),d.priced(9,20))
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run,req,response(),sources=sources,attempt='c'+str(i),client=Inline()) for i in range(2)]
            results=[f.result(timeout=30) for f in futures]
        self.assertEqual(sum(len(r.query_receipts) for r in results),16)
        self.assertEqual(sources.repository.query_count(results[0].request_ref),16)
        client=DeterministicSyntheticClient(response())
        self.assertEqual(run(req,response(),sources=sources,attempt='c0',client=client),results[0])
        self.assertEqual((client.calls,sources.repository.query_count(results[0].request_ref)),(0,16))
        dispatcher=ReadonlyDispatcher(req,sources,clock=lambda:NOW)
        with self.assertRaises(AIDenied):
            dispatcher.execute(d.Query('document_view',c.manifest_ref))

    def test_duplicate_attempt_in_flight_never_saves_a_fabricated_result(self):
        entered=Event(); release=Event(); sources=Sources(); req=request()
        class Slow:
            calls=0
            def invoke(self,*args):
                self.calls+=1; entered.set()
                if not release.wait(timeout=10):
                    raise TimeoutError()
                return ClientReply(d.encoded(response()),d.priced(9,20))
        client=Slow()
        with ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(run,req,response(),sources=sources,client=client)
            self.assertTrue(entered.wait(timeout=10))
            duplicate=run(req,response(),sources=sources,client=client)
            self.assertEqual(duplicate.status,'blocked')
            self.assertIsNone(sources.repository.result_for('a1'))
            release.set(); actual=future.result(timeout=30)
        self.assertEqual(actual.status,'complete')
        self.assertEqual(sources.repository.result_for('a1'),actual)
        self.assertEqual(client.calls,1)

    def test_client_cannot_hide_denied_inline_query_by_omitting_response_queries(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,))
        req=request((c.manifest_ref,),role='portfolio',allowed_queries=())
        class HidesDenial:
            def invoke(self,request,attempt,dispatcher):
                try:
                    dispatcher.execute(d.Query('document_view',c.manifest_ref))
                except AIDenied:
                    pass
                return ClientReply(d.encoded(response()),d.priced(9,20))
        result=run(req,response(),sources=sources,client=HidesDenial())
        self.assertEqual((result.status,result.reasons),('blocked',('query_denied',)))

