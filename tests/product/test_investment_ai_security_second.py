"""Q25 2차 보안 회귀. 고정24 명세와 별도인 실제 공개 경로 재현."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from threading import Barrier, Event
import unittest

from quantharbor.domain import investment_ai as d
from quantharbor.domain.primitives import ContractError, utc_instant
from quantharbor.application.investment_ai import Sources, current_result, review_result
from quantharbor.adapters.synthetic_investment_ai import AIDenied, SyntheticAIRepository
from quantharbor.ports.investment_ai import ClientReply
from synthetic_investment_ai import NOW, policy, request, response, document_source, citation, run


class AISecondSecurityTests(unittest.TestCase):
    def test_AS1b_current_missing_or_changed_source_hides_historical_body(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,))
        old=run(request((c.manifest_ref,)),response(citations=(c,)),sources=sources)
        self.assertEqual(old.status,'complete')
        rr=d.ref('result',old.result_id,old)
        for documents in ((),(document_source(text='변경된 합성 원천'),)):
            with self.subTest(documents=bool(documents)):
                current=Sources(documents=documents,repository=sources.repository)
                body,status,reasons=current_result(rr,current,at=NOW)
                self.assertIn(status,('partial','invalid'))
                self.assertTrue(reasons)
                self.assertIsNone(body,'현재 확인 실패에 과거 인용 본문 노출')
                self.assertEqual(sources.repository.get(rr),old)

    def inline_fixture(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,))
        req=request((c.manifest_ref,))
        class Inline:
            def invoke(self,request,attempt,dispatcher):
                dispatcher.execute(d.Query('document_view',c.manifest_ref))
                return ClientReply(d.encoded(response()),d.priced(9,20))
        result=run(req,response(),sources=sources,client=Inline())
        self.assertEqual((result.status,len(result.query_receipts),result.response.queries),('complete',1,()))
        rr=d.ref('result',result.result_id,result)
        return sources,req,result,rr

    def test_AS3b_review_checks_omitted_inline_receipts(self):
        sources,req,result,rr=self.inline_fixture()
        reviewreq=replace(req,request_id='review',review_subject_ref=rr,allowed_queries=())
        review=review_result(reviewreq,rr,d.ClientIdentity('reviewer','synthetic',None),sources,at=NOW)
        self.assertEqual((review.verdict,review.findings),('blocked',('query_denied',)))
        self.assertEqual(sources.repository.query_count(result.request_ref),1)

    def test_AS4b_postdispatch_clock_regression_retains_unknown_and_blocks_scope(self):
        sources=Sources(); req=request(); ticks=iter((NOW,'2024-03-08T14:31:09Z',NOW,'2024-03-08T14:31:10Z'))
        try:
            result=run(req,response(),sources=sources,clock=lambda:next(ticks))
        except ContractError:
            self.fail('전송 후 시각 역행이 정산/결과 저장 밖으로 탈출')
        attempt=sources.repository.attempt('a1')
        self.assertEqual((attempt.state,attempt.actual_usage),('unknown_charge',None))
        self.assertGreaterEqual(attempt.settled_at,attempt.dispatch_at)
        self.assertIn('unknown_charge',result.reasons)
        newer=policy(policy_id='next',window_start='2025-01-01T00:00:00Z',window_end='2026-01-01T00:00:00Z')
        nxt=request(p=newer,request_id='next',as_of=newer.window_start,knowledge_cutoff=newer.window_start,
            evaluated_at=newer.window_start,deadline='2025-01-01T00:01:00Z')
        with self.assertRaises(AIDenied):
            sources.repository.reserve(nxt,newer,'next',d.priced(1,0),at=newer.window_start)

    def test_AS5b_duplicate_entering_before_reservation_cannot_dispatch_or_overwrite(self):
        entered=Event(); release=Event()
        class PausedRepository(SyntheticAIRepository):
            def reserve(self,*args,**kwargs):
                if not entered.is_set():
                    entered.set()
                    if not release.wait(timeout=5):
                        raise AssertionError('fixture reservation pause timeout')
                return super().reserve(*args,**kwargs)
        sources=Sources(repository=PausedRepository()); req=request()
        class Client:
            calls=0
            def invoke(self,*args):
                self.calls+=1
                return ClientReply(d.encoded(response()),d.priced(9,20))
        client=Client()
        with ThreadPoolExecutor(max_workers=2) as pool:
            owner=pool.submit(run,req,response(),sources=sources,client=client)
            self.assertTrue(entered.wait(timeout=5))
            try:
                duplicate=run(req,response(),sources=sources,client=client)
                before_release_calls=client.calls
                before_release_result=sources.repository.result_for('a1')
            finally:
                release.set()
            actual=owner.result(timeout=10)
        # 소유권을 예약과 동시에 정하면 B가 먼저 예약할 수도 있다.
        # 먼저 예약한 호출은 실제 결과를 반드시 저장하고, 뒤 호출은 덮어쓰지 않는다.
        if before_release_calls:
            self.assertEqual(before_release_result,duplicate,'실제 예약/호출의 결과가 유실')
        else:
            self.assertEqual(duplicate.status,'blocked')
        self.assertEqual((actual.status,client.calls),('complete',1))
        self.assertEqual(sources.repository.result_for('a1'),actual)

    def duplicate_final_clock_failure(self,fault):
        entered=Barrier(2,timeout=10); release=Barrier(2,timeout=10)
        reservations=[]; unknown_calls=[]
        class ObservedRepository(SyntheticAIRepository):
            def reserve(self,*args,**kwargs):
                attempt,new=super().reserve(*args,**kwargs)
                reservations.append((attempt.state,new))
                return attempt,new
            def settle_unknown(self,attempt_id):
                unknown_calls.append(attempt_id)
                return super().settle_unknown(attempt_id)
        sources=Sources(repository=ObservedRepository()); repo=sources.repository; req=request()
        class PausedClient:
            calls=0
            def invoke(self,*args):
                self.calls+=1
                entered.wait(); release.wait()
                return ClientReply(d.encoded(response()),d.priced(9,20))
        client=PausedClient(); ticks=iter((NOW,fault))
        def duplicate_clock():
            value=next(ticks)
            if isinstance(value,Exception):
                raise value
            return value
        def snapshot():
            return deepcopy(tuple(getattr(repo,name) for name in (
                '_records','_attempts','_holds','_blocked','_processed','_payloads',
                '_policies','_query_totals','_query_receipts','_query_denials')))
        error=None
        with ThreadPoolExecutor(max_workers=1) as pool:
            owner=pool.submit(run,req,response(),sources=sources,client=client)
            try:
                entered.wait()
                before=snapshot()
                try:
                    run(req,response(),sources=sources,client=client,clock=duplicate_clock)
                except (RuntimeError,ContractError) as exc:
                    error=exc
                after=snapshot()
                unknown_before_release=tuple(unknown_calls)
            finally:
                release.wait()
            actual=owner.result(timeout=10)
        self.assertEqual(reservations,[('reserved',True),('dispatched',False)])
        self.assertEqual(after,before,'비소유 호출이 소유자의 dispatch/정산 상태를 변경')
        self.assertEqual(unknown_before_release,(),'비소유 호출이 정산 fallback에 진입')
        self.assertIsInstance(error,RuntimeError if isinstance(fault,Exception) else ContractError)
        if isinstance(fault,Exception):
            self.assertIs(error,fault)
        self.assertEqual((actual.status,client.calls),('complete',1))
        settled=repo.attempt('a1')
        self.assertEqual((settled.state,settled.actual_usage),('settled',d.priced(9,20)))
        self.assertEqual(repo._blocked,set())
        self.assertEqual(repo._holds,{})
        self.assertEqual(repo.result_for('a1'),actual)
        self.assertEqual(actual.budget_attempt_refs,(d.ref('attempt','a1',settled),))
        followup=replace(req,request_id='next')
        self.assertTrue(repo.reserve(followup,policy(),'next',d.priced(1,0),at=NOW)[1])

    def test_AS45c_nonowner_final_clock_exception_preserves_active_owner(self):
        self.duplicate_final_clock_failure(RuntimeError('합성 중복 clock 오류'))

    def test_AS45c_nonowner_final_clock_none_preserves_active_owner(self):
        self.duplicate_final_clock_failure(None)

    def test_AS6_review_capacity_failure_does_not_leak_request_slot(self):
        sources=Sources(repository=SyntheticAIRepository(capacity=6)); req=request()
        result=run(req,response(),sources=sources); rr=d.ref('result',result.result_id,result)
        filler=replace(req,request_id='filler'); sources.repository.append('request',filler.request_id,filler)
        reviewreq=replace(req,request_id='review',review_subject_ref=rr)
        reviewref=d.ref('request',reviewreq.request_id,reviewreq)
        before=dict(sources.repository._records)
        with self.assertRaises(AIDenied) as cm:
            review_result(reviewreq,rr,d.ClientIdentity('reviewer','synthetic',None),sources,at=NOW)
        self.assertEqual(cm.exception.reason,'capacity')
        self.assertIsNone(sources.repository.get(reviewref),'실패한 검토 request가 마지막 슬롯을 소진')
        self.assertEqual(sources.repository._records,before)

    def test_current_safe_partial_and_cached_partial_remain_usable(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,)); req=request((c.manifest_ref,))
        old=run(req,response(citations=(c,),finish_reason='length'),sources=sources)
        rr=d.ref('result',old.result_id,old)
        self.assertEqual(current_result(rr,sources,at=NOW),(old,'partial',('truncated',)))
        self.assertEqual(run(req,response(),sources=sources),old)
        missing=d.AIRef('document','missing',1,d.CANONICAL,'0'*64)
        other=Sources(documents=(src,)); otherreq=request((c.manifest_ref,missing))
        partial=run(otherreq,response(citations=(c,)),sources=other)
        pr=d.ref('result',partial.result_id,partial)
        self.assertEqual(current_result(pr,other,at=NOW),(partial,'partial',('missing_source',)))

    def test_current_unverified_citation_never_becomes_safe_partial_body(self):
        src=document_source(); c=citation(src); sources=Sources()
        old=run(request((c.manifest_ref,)),response(citations=(c,)),sources=sources)
        self.assertEqual(old.status,'partial')
        body,status,reasons=current_result(d.ref('result',old.result_id,old),sources,at=NOW)
        self.assertEqual((body,status,reasons),(None,'partial',('missing_source',)))

    def test_current_payloadless_invalid_keeps_status_and_rechecks_source_rights(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,))
        class InvalidPayload:
            def invoke(self,*args):
                return ClientReply(b'{',d.priced(9,20))
        req=request((c.manifest_ref,),required_outputs=('document',))
        old=run(req,response(),sources=sources,client=InvalidPayload())
        self.assertEqual((old.status,old.reasons,old.response),('invalid',('schema',),None))
        rr=d.ref('result',old.result_id,old)
        self.assertEqual(current_result(rr,sources,at=NOW),(old,old.status,old.reasons))
        revoked=replace(src,current_rights=replace(src.current_rights,revoked_at=NOW))
        current=Sources(documents=(revoked,),repository=sources.repository)
        self.assertEqual(current_result(rr,current,at=NOW),(None,'blocked',('rights_denied','missing_source')))

    def test_current_report_revocation_hides_body_preserving_historical_review(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,))
        req=request((c.manifest_ref,),role='report',purpose='ai_report')
        old=run(req,response(citations=(c,)),sources=sources); rr=d.ref('result',old.result_id,old)
        reviewreq=replace(req,request_id='review',role='risk',purpose='ai_research',review_subject_ref=rr)
        reviewer=d.ClientIdentity('reviewer','synthetic',None)
        review=review_result(reviewreq,rr,reviewer,sources,at=NOW)
        self.assertEqual(review.verdict,'accepted')
        denied=replace(src,current_rights=replace(src.current_rights,purposes=('ai','research','store')))
        current=Sources(documents=(denied,),repository=sources.repository)
        self.assertEqual(current_result(rr,current,at=NOW),(None,'blocked',('rights_denied',)))
        self.assertEqual(sources.repository.get(d.ref('review',review.review_id,review)),review)
        later=review_result(reviewreq,rr,replace(reviewer,invocation_id='later'),current,at=NOW)
        self.assertEqual(later.verdict,'blocked')

    def test_current_hypothesis_source_disappearance_is_rejected(self):
        src=document_source(); c=citation(src); sources=Sources(documents=(src,)); req=request((c.manifest_ref,))
        old=run(req,response(citations=(c,),narrative=(d.NarrativeClaim('h','hypothesis','합성 가설',(0,)),)),sources=sources)
        rr=d.ref('result',old.result_id,old)
        h=d.Hypothesis(1,'synthetic','h',rr,'합성 가설',('h',),(),(),'반대 자료로 반증',None,
            sources.repository.hypothesis_dependencies(rr),NOW,'2024-03-08T14:31:30Z','proposed',None,None)
        sources.repository.append('hypothesis',h.hypothesis_id,h)
        current=Sources(repository=sources.repository)
        with self.assertRaises(AIDenied) as cm:
            current.hypothesis(d.ref('hypothesis',h.hypothesis_id,h),req,NOW)
        self.assertEqual(cm.exception.reason,'dependency_changed')
        self.assertIsNone(current_result(rr,current,at=NOW)[0])
        self.assertEqual(sources.repository.get(rr),old)

    def test_inline_review_valid_idempotent_and_missing_scope_blocked_without_queries(self):
        sources,req,result,rr=self.inline_fixture(); repo=sources.repository
        reviewreq=replace(req,request_id='review',review_subject_ref=rr)
        reviewer=d.ClientIdentity('reviewer','synthetic',None)
        review=review_result(reviewreq,rr,reviewer,sources,at=NOW)
        self.assertEqual(review.verdict,'accepted')
        self.assertEqual(review_result(reviewreq,rr,reviewer,sources,at=NOW),review)
        narrower=replace(reviewreq,request_id='narrow',source_refs=())
        blocked=review_result(narrower,rr,replace(reviewer,invocation_id='narrow'),sources,at=NOW)
        self.assertEqual((blocked.verdict,blocked.findings),('blocked',('query_denied',)))
        self.assertEqual(repo.query_count(result.request_ref),1)

    def test_review_revalidates_current_reviewer_account_scope(self):
        from synthetic_investment_ai import flow_source, performance_ref, numeric
        src=flow_source(); sources=Sources(financial=(src,))
        req=request((performance_ref(src),),account_ref=src.points[0].snapshot.account_ref)
        old=run(req,response(numeric=(numeric(src,'performance.twr','0.21'),)),sources=sources)
        self.assertEqual(old.status,'complete'); rr=d.ref('result',old.result_id,old)
        reviewreq=replace(req,request_id='review',review_subject_ref=rr,account_ref='synthetic-account:other')
        review=review_result(reviewreq,rr,d.ClientIdentity('reviewer','synthetic',None),sources,at=NOW)
        self.assertEqual(review.verdict,'blocked')
        self.assertIn('future_source',review.findings)

    def test_direct_malformed_settlement_times_and_usage_keep_reservation_and_scope(self):
        for at,usage in ((None,d.priced(1,0)),(True,d.priced(1,0)),('bad',d.priced(1,0)),
                         ('2024-03-08T14:31:07Z',d.priced(1,0)),(NOW,True),(NOW,object())):
            with self.subTest(at=at,usage_type=type(usage).__name__):
                repo=SyntheticAIRepository(); p=policy(); req=request(p=p)
                repo.reserve(req,p,'raw',d.priced(69,20),at=NOW); repo.dispatch('raw',at=NOW)
                holds=dict(repo._holds)
                unknown=repo.settle('raw',usage,at=at)
                self.assertEqual((unknown.state,unknown.actual_usage,unknown.settled_at),('unknown_charge',None,utc_instant(NOW)))
                self.assertEqual(repo._holds,holds)
                with self.assertRaises(AIDenied):
                    repo.reserve(replace(req,request_id='next'),p,'next',d.priced(1,0),at=NOW)

    def test_known_settlement_preserved_on_bad_time_usage_and_unknown_fallback(self):
        sources=Sources(); run(request(),response(),sources=sources); repo=sources.repository
        known=repo.attempt('a1'); before=dict(repo._records)
        for at,usage in ((True,d.priced(9,20)),('2024-03-08T14:31:07Z',d.priced(9,20)),(NOW,True)):
            with self.assertRaises(ContractError):
                repo.settle('a1',usage,at=at)
            self.assertEqual(repo.attempt('a1'),known)
        self.assertEqual(repo.settle_unknown('a1'),known)
        self.assertEqual(repo._records,before)
        self.assertEqual(repo._blocked,set())
        self.assertEqual(repo.settle('a1',known.actual_usage,at=NOW),known)

    def test_settlement_exception_after_commit_preserves_actual_known_usage(self):
        class RaisesAfterCommit(SyntheticAIRepository):
            def settle(self,*args,**kwargs):
                super().settle(*args,**kwargs)
                raise RuntimeError('합성 정산 후 오류')
        sources=Sources(repository=RaisesAfterCommit())
        result=run(request(),response(),sources=sources)
        known=sources.repository.attempt('a1')
        self.assertEqual((result.status,known.state,known.actual_usage.charge),('complete','settled',50))
        self.assertEqual(sources.repository._blocked,set())
        self.assertEqual(sources.repository.result_for('a1'),result)

    def test_clock_exception_and_malformed_value_after_dispatch_are_unknown(self):
        for fault in (RuntimeError('합성 clock 오류'),None,True):
            with self.subTest(fault_type=type(fault).__name__):
                ticks=iter((NOW,NOW,fault,NOW)); sources=Sources()
                def clock():
                    value=next(ticks)
                    if isinstance(value,Exception):
                        raise value
                    return value
                result=run(request(),response(),sources=sources,clock=clock)
                self.assertEqual((result.status,result.reasons),('partial',('unknown_charge',)))
                self.assertEqual(sources.repository.attempt('a1').state,'unknown_charge')
                self.assertEqual(sources.repository.result_for('a1'),result)

    def test_last_clock_failure_or_regression_preserves_already_settled_outcome(self):
        for last in (RuntimeError('합성 마지막 clock 오류'),None,'2024-03-08T14:31:07Z'):
            with self.subTest(last=last):
                ticks=iter((NOW,NOW,'2024-03-08T14:31:09Z',last)); sources=Sources()
                def clock():
                    value=next(ticks)
                    if isinstance(value,Exception):
                        raise value
                    return value
                result=run(request(),response(),sources=sources,clock=clock)
                known=sources.repository.attempt('a1')
                self.assertEqual((result.status,known.state,known.actual_usage.charge),('complete','settled',50))
                self.assertGreaterEqual(result.finished_at,known.settled_at)
                self.assertEqual(sources.repository._blocked,set())

    def test_owner_final_clock_failure_preserves_unknown_reservation(self):
        class UnknownUsage:
            def invoke(self,*args):
                return ClientReply(d.encoded(response()),None)
        for fault in (RuntimeError('합성 소유자 clock 오류'),None):
            with self.subTest(fault_type=type(fault).__name__):
                sources=Sources(); ticks=iter((NOW,NOW,NOW,fault))
                def clock():
                    value=next(ticks)
                    if isinstance(value,Exception):
                        raise value
                    return value
                result=run(request(),response(),sources=sources,client=UnknownUsage(),clock=clock)
                repo=sources.repository; attempt=repo.attempt('a1')
                self.assertEqual((result.status,result.reasons),('partial',('unknown_charge',)))
                self.assertEqual((attempt.state,attempt.actual_usage),('unknown_charge',None))
                self.assertEqual(attempt.reserved_usage,d.priced(69,20))
                self.assertEqual(repo._blocked,{policy().budget_scope})
                self.assertEqual(repo.result_for('a1'),result)
                with self.assertRaises(AIDenied) as cm:
                    repo.reserve(replace(request(),request_id='next'),policy(),'next',d.priced(1,0),at=NOW)
                self.assertEqual(cm.exception.reason,'unknown_charge')

    def test_client_failure_and_broken_settlement_clock_still_persist_unknown(self):
        class Broken:
            def invoke(self,*args):
                raise TimeoutError('합성 오류 원문 비노출')
        ticks=iter((NOW,NOW,None,None)); sources=Sources()
        result=run(request(),response(),sources=sources,client=Broken(),clock=lambda:next(ticks))
        self.assertEqual((result.status,result.reasons),('failed',('client_failure',)))
        self.assertIsNone(result.response)
        self.assertEqual(sources.repository.attempt('a1').state,'unknown_charge')
        self.assertEqual(sources.repository.result_for('a1'),result)

    def test_duplicate_during_settlement_never_persists_a_nonowner_failure(self):
        entered=Event(); release=Event()
        class PausedRepository(SyntheticAIRepository):
            def settle(self,*args,**kwargs):
                actual=super().settle(*args,**kwargs)
                entered.set()
                if not release.wait(timeout=5):
                    raise AssertionError('fixture settlement pause timeout')
                return actual
        sources=Sources(repository=PausedRepository()); req=request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            owner=pool.submit(run,req,response(),sources=sources)
            self.assertTrue(entered.wait(timeout=5))
            try:
                duplicate=run(req,response(),sources=sources)
                before_release=sources.repository.result_for('a1')
            finally:
                release.set()
            actual=owner.result(timeout=10)
        self.assertEqual((duplicate.status,before_release,actual.status),('blocked',None,'complete'))
        self.assertEqual(sources.repository.result_for('a1'),actual)

    def test_reentrant_duplicate_is_not_owner_of_outer_result(self):
        sources=Sources(); req=request(); duplicates=[]
        class Reentrant:
            calls=0
            def invoke(self,*args):
                self.calls+=1
                duplicates.append(run(req,response(),sources=sources,client=self))
                return ClientReply(d.encoded(response()),d.priced(9,20))
        client=Reentrant(); result=run(req,response(),sources=sources,client=client)
        self.assertEqual((result.status,duplicates[0].status,client.calls),('complete','blocked',1))
        self.assertEqual(sources.repository.result_for('a1'),result)

    def test_review_byte_capacity_failure_is_atomic_and_success_uses_exact_pair(self):
        sources=Sources(); req=request(); result=run(req,response(),sources=sources); repo=sources.repository
        rr=d.ref('result',result.result_id,result); reviewreq=replace(req,request_id='review',review_subject_ref=rr)
        reviewer=d.ClientIdentity('reviewer','synthetic',None)
        expected=d.ResearchReview(1,'synthetic','review:reviewer',d.ref('request',reviewreq.request_id,reviewreq),rr,
            reviewer,NOW,(),(),(),'accepted',None)
        # 처리 증거와 무관한 저장 여유 fixture. 기존 기록과 예약은 그대로 유지한다.
        exact=sum(map(len,repo._records.values()))+len(d.encoded(reviewreq))+len(d.encoded(expected))
        repo._byte_capacity=exact-1
        before=(dict(repo._records),dict(repo._processed),dict(repo._holds))
        with self.assertRaises(AIDenied):
            review_result(reviewreq,rr,reviewer,sources,at=NOW)
        self.assertEqual((repo._records,repo._processed,repo._holds),before)
        repo._byte_capacity=exact
        self.assertEqual(review_result(reviewreq,rr,reviewer,sources,at=NOW),expected)
        self.assertEqual(review_result(reviewreq,rr,reviewer,sources,at=NOW),expected)

    def test_review_malformed_and_conflicting_requests_never_leave_partial_records(self):
        sources=Sources(); req=request(); result=run(req,response(),sources=sources); repo=sources.repository
        rr=d.ref('result',result.result_id,result); reviewer=d.ClientIdentity('reviewer','synthetic',None)
        valid=replace(req,request_id='review',review_subject_ref=rr)
        for bad in (None,replace(valid,role='collector'),replace(valid,request_id=req.request_id)):
            before=(dict(repo._records),dict(repo._processed))
            with self.assertRaises(ContractError):
                review_result(bad,rr,reviewer,sources,at=NOW)
            self.assertEqual((repo._records,repo._processed),before)
        accepted=review_result(valid,rr,reviewer,sources,at=NOW)
        self.assertEqual(accepted.verdict,'accepted')

    def test_malformed_direct_execution_and_reservation_leave_repository_unchanged(self):
        sources=Sources(); repo=sources.repository; req=request(); p=policy()
        for r,b,u in ((None,p,d.priced(1,0)),(req,None,d.priced(1,0)),(req,p,True)):
            with self.assertRaises(ContractError):
                repo.reserve(r,b,'bad',u,at=NOW)
            self.assertEqual((repo._records,repo._holds,repo._attempts),({},{},{}))
        with self.assertRaises(ContractError):
            repo.execute(None,p,sources,None,attempt_id='bad',reserved=d.priced(1,0),clock=lambda:NOW)
        self.assertEqual((repo._records,repo._holds,repo._attempts),({},{},{}))

