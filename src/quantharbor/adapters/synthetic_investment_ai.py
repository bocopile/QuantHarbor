"""Q25 in-process 합성 client/공유 저장소. 실제 client는 항상 비활성이다."""
from dataclasses import asdict, replace
import json
from threading import RLock

from quantharbor.domain.investment_ai import (AIBudgetAttempt,AIBudgetPolicy,AIRef,Usage,ResearchRequest,
    ResearchResult,ResearchReview,Hypothesis,ModelResponse,encoded,ref,usage_values,priced)
from quantharbor.domain.primitives import ContractError,utc_instant
from quantharbor.domain.serialization import parse_payload
from quantharbor.ports.investment_ai import ClientReply


class AIDenied(ValueError):
    def __init__(self,reason):
        from quantharbor.domain.investment_ai import REASONS
        if reason not in REASONS:
            raise ContractError()
        self.reason=reason
        super().__init__(reason)


_TYPES={'request':ResearchRequest,'result':ResearchResult,'review':ResearchReview,'hypothesis':Hypothesis,
        'budget_policy':AIBudgetPolicy,'attempt':AIBudgetAttempt}


class SyntheticAIRepository:
    """한 repository를 모든 역할에서 공유한다. capacity는 예약된 최종 기록도 포함."""
    def __init__(self, *, capacity=128, byte_capacity=8388608):
        if type(capacity) is not int or not 1<=capacity<=128 or type(byte_capacity) is not int or not 1<=byte_capacity<=8388608:
            raise ContractError()
        self._lock=RLock()
        self._records={}
        self._holds={}
        self._attempts={}
        self._payloads={}
        self._blocked=set()
        self._policies={}
        self._processed={}
        self._current_sources=None
        self._query_totals={}
        self._query_receipts={}
        self._query_denials={}
        self._capacity=capacity
        self._byte_capacity=byte_capacity

    def _room(self, key,raw):
        records=len(self._records)+(key not in self._records)
        size=sum(map(len,self._records.values()))-len(self._records.get(key,b''))+len(raw)
        if records+sum(x[0] for x in self._holds.values())>self._capacity or size+sum(x[1] for x in self._holds.values())>self._byte_capacity:
            raise AIDenied('capacity')

    def append(self,kind,identity,obj,*,sources=None):
        if kind not in _TYPES or type(obj) is not _TYPES[kind]:
            raise ContractError()
        if kind=='attempt':
            raise ContractError()
        raw=encoded(obj)
        obj=parse_payload(raw).payload
        actual_id=getattr(obj,{'request':'request_id','result':'result_id','review':'review_id','hypothesis':'hypothesis_id','budget_policy':'policy_id','attempt':'attempt_id'}[kind])
        if identity!=actual_id:
            raise ContractError()
        key=(kind,identity)
        with self._lock:
            if key in self._records:
                if self._records[key]!=raw:
                    raise ContractError()
                return parse_payload(self._records[key]).payload
            if kind=='result':
                if self._processed.get(key)!=raw:
                    raise ContractError()
                request=self.get(obj.request_ref)
                if type(request) is not ResearchRequest or (obj.procedure_version,obj.instruction_version,obj.tool_schema_version)!=(request.procedure_version,request.instruction_version,request.tool_schema_version):
                    raise ContractError()
                if not obj.budget_attempt_refs:
                    raise ContractError()
                for ar in obj.budget_attempt_refs:
                    attempt=self.get(ar)
                    if type(attempt) is not AIBudgetAttempt or attempt.request_ref!=obj.request_ref or attempt.state not in ('settled','unknown_charge','cancelled_before_dispatch') or obj.status=='complete' and (attempt.state!='settled' or attempt.reasons):
                        raise ContractError()
                    if attempt.state=='cancelled_before_dispatch' and (obj.status not in ('failed','blocked') or obj.response is not None or obj.query_receipts):
                        raise ContractError()
                if any(q.query.name not in request.allowed_queries or q.query.source_ref not in request.source_refs for q in obj.query_receipts):
                    raise ContractError()
            if kind=='review':
                if self._processed.get(key)!=raw:
                    raise ContractError()
                request=self.get(obj.review_request_ref)
                result=self.get(obj.exact_result_ref)
                if type(request) is not ResearchRequest or type(result) is not ResearchResult or request.role!='risk' or request.review_subject_ref!=obj.exact_result_ref or obj.reviewer_identity.invocation_id==result.client_identity.invocation_id or obj.verdict=='accepted' and result.status!='complete':
                    raise ContractError()
            if kind=='hypothesis':
                if sum(k=='hypothesis' for k,_ in self._records)>=8:
                    raise AIDenied('capacity')
                origin=self.get(obj.origin_result_ref)
                if type(origin) is not ResearchResult or origin.status not in ('complete','partial'):
                    raise ContractError()
                claim_ids={c.claim_id for c in (*origin.response.numeric_claims,*origin.response.narrative_claims)} if origin.response else set()
                if not set((*obj.supporting_claim_refs,*obj.opposing_claim_refs))<=claim_ids:
                    raise ContractError()
                required=self.hypothesis_dependencies(obj.origin_result_ref)
                if not set(required)<=set(obj.dependencies):
                    raise ContractError()
                context=sources or self._current_sources
                if context is None or context.repository is not self:
                    raise ContractError()
                request=self.get(origin.request_ref)
                for dependency in obj.dependencies:
                    context.validate(dependency,request,obj.created_at)
                for predecessor in (obj.supersedes_ref,obj.retracts_ref):
                    if predecessor:
                        old=self.get(predecessor)
                        if type(old) is not Hypothesis or old.created_at>=obj.created_at or old.hypothesis_id==identity:
                            raise ContractError()
            self._room(key,raw)
            self._records[key]=raw
        return obj

    def bind_sources(self,sources):
        """호스트가 완성해 주입한 현재 원천을 사용한다. 과거 처리 원천으로 대체하지 않는다."""
        from quantharbor.application.investment_ai import Sources
        if type(sources) is not Sources or sources.repository is not self:
            raise ContractError()
        with self._lock:
            self._current_sources=sources

    def hypothesis_dependencies(self,origin_ref):
        """필수 집합은 처리된 origin/request/원천 manifest에서만 도출한다."""
        with self._lock:
            origin=self.get(origin_ref)
            if type(origin) is not ResearchResult or self._processed.get(('result',origin.result_id))!=encoded(origin):
                raise ContractError()
            request=self.get(origin.request_ref)
            dependencies=list((*request.source_refs,*origin.input_manifest))
            if origin.response:
                dependencies.extend(c.source_ref for c in origin.response.numeric_claims)
                for c in origin.response.citations:
                    dependencies.extend((c.manifest_ref,c.revision_ref,c.observation_ref,c.original_ref,c.context_ref))
            dependencies=tuple(dict.fromkeys(dependencies))
            if len(dependencies)>128:
                raise ContractError()
            return dependencies

    def execute_query(self,request,query,sources,*,at,attempt_id=None):
        with self._lock:
            if attempt_id is not None:
                a=self._attempts.get(attempt_id)
                if a is None or type(request) is not ResearchRequest or a.request_ref!=ref('request',request.request_id,request):
                    raise ContractError()
                if self.result_for(attempt_id) is not None:
                    raise AIDenied('query_denied')
            try:
                return self._execute_query(request,query,sources,at=at,attempt_id=attempt_id)
            except AIDenied as e:
                if attempt_id is not None:
                    self._query_denials[attempt_id]=tuple(dict.fromkeys((*self._query_denials.get(attempt_id,()),e.reason)))
                raise

    def _execute_query(self,request,query,sources,*,at,attempt_id):
        """실제 해소 전 요청 전체 quota를 잠금 안에서 소비한다. 실패도 환급하지 않는다."""
        from quantharbor.domain.investment_ai import ROLE_QUERIES, Query, QueryReceipt
        from quantharbor.runtime.boundary import authorize,synthetic_binding
        if type(request) is not ResearchRequest or sources.repository is not self:
            raise ContractError()
        if type(query) is not Query:
            raise AIDenied('query_denied')
        at=utc_instant(at)
        kinds={'document_view':('document',),'snapshot_view':('snapshot',),'research_view':('performance','experiment'),
               'candidate_view':('candidate','plan'),'hypothesis_view':('hypothesis',)}
        with self._lock:
            if at>=request.deadline:
                raise AIDenied('deadline')
            if query.name not in ROLE_QUERIES[request.role] or query.name not in request.allowed_queries or query.source_ref not in request.source_refs or query.source_ref.kind not in kinds[query.name]:
                raise AIDenied('query_denied')
            self.append('request',request.request_id,request)
            rr=ref('request',request.request_id,request)
            if attempt_id is not None:
                a=self._attempts.get(attempt_id)
                if a is None or a.request_ref!=rr or a.state not in ('dispatched','settled','unknown_charge'):
                    raise ContractError()
            count=self._query_totals.get(rr,0)
            if count>=16:
                raise AIDenied('query_denied')
            authorize(synthetic_binding('reporting' if request.role=='report' else 'research'),'synthetic.read')
            self._query_totals[rr]=count+1
            obj,refs=sources.validate(query.source_ref,request,at)
            receipt=QueryReceipt(query,tuple(dict.fromkeys((query.source_ref,*refs))),at)
            if attempt_id is not None:
                receipts=(*self._query_receipts.get(attempt_id,()),receipt)
                if len(json.dumps([asdict(r) for r in receipts],ensure_ascii=False,separators=(',',':')).encode())>32768:
                    raise AIDenied('capacity')
                self._query_receipts.setdefault(attempt_id,[]).append(receipt)
            return obj,receipt

    def query_count(self,request_ref):
        with self._lock:
            self.get(request_ref)
            return self._query_totals.get(request_ref,0)

    def query_denials(self,attempt_id):
        with self._lock:
            return self._query_denials.get(attempt_id,())

    def execute(self,request,policy,sources,client,**kwargs):
        """저장소가 실제 호출·정규화·검증을 실행하고 exact 처리 결과만 수락한다."""
        from quantharbor.application.investment_ai import _run_research
        if sources.repository is not self:
            raise ContractError()
        if type(request) is not ResearchRequest or type(policy) is not AIBudgetPolicy:
            raise ContractError()
        attempt_id=kwargs['attempt_id']
        # reserve의 단일 잠금에서 새 예약을 얻은 실제 호출만 결과를 확정한다.
        # 진입 순서와 별개인 owner 플래그를 먼저 획득하지 않는다.
        result,new=_run_research(request,policy,sources,client,**kwargs)
        with self._lock:
            if not new or self.result_for(attempt_id) is not None or not result.budget_attempt_refs:
                return result
            if tuple(self._query_receipts.get(attempt_id,()))!=result.query_receipts:
                raise ContractError()
            key=('result',result.result_id)
            self._processed[key]=encoded(result)
            try:
                result=self.finish(attempt_id,result)
                self._processed[key]=self._records[key]
                self._query_receipts.pop(attempt_id,None)
                return result
            except Exception:
                self._processed.pop(key,None)
                raise

    def execute_review(self,review_request,exact_result_ref,reviewer,sources,**kwargs):
        from quantharbor.application.investment_ai import _review_result
        if sources.repository is not self:
            raise ContractError()
        if type(review_request) is not ResearchRequest:
            raise ContractError()
        review_request=parse_payload(encoded(review_request)).payload
        with self._lock:
            result=self.get(exact_result_ref)
            if type(result) is not ResearchResult or self._processed.get(('result',result.result_id))!=encoded(result):
                raise ContractError()
            review=_review_result(review_request,exact_result_ref,reviewer,sources,**kwargs)
            key=('review',review.review_id)
            raw=encoded(review)
            prior=self._processed.get(key)
            if prior is not None and prior!=raw:
                raise ContractError()
            pending={('request',review_request.request_id):encoded(review_request),key:raw}
            for k,v in pending.items():
                if k in self._records and self._records[k]!=v:
                    raise ContractError()
            combined=self._records|pending
            if len(combined)+sum(x[0] for x in self._holds.values())>self._capacity or sum(map(len,combined.values()))+sum(x[1] for x in self._holds.values())>self._byte_capacity:
                raise AIDenied('capacity')
            old_records=dict(self._records)
            self._processed[key]=raw
            try:
                self.append('request',review_request.request_id,review_request)
                review=self.append('review',review.review_id,review)
                self._processed[key]=self._records[key]
                return review
            except Exception:
                self._records=old_records
                if prior is None:
                    self._processed.pop(key,None)
                else:
                    self._processed[key]=prior
                raise

    def get(self,reference):
        if type(reference) is not AIRef:
            raise ContractError()
        with self._lock:
            raw=self._records.get((reference.kind,reference.id))
            if raw is None:
                return None
            obj=parse_payload(raw).payload
            if ref(reference.kind,reference.id,obj)!=reference:
                raise ContractError()
            return obj

    def hypotheses(self):
        with self._lock:
            return tuple(parse_payload(v).payload for (k,_),v in self._records.items() if k=='hypothesis')

    def _save_attempt(self,a):
        self._records[('attempt',a.attempt_id)]=encoded(a)
        self._attempts[a.attempt_id]=a
        return a

    def reserve(self,request,policy,attempt_id,reserved,*,at):
        if type(request) is not ResearchRequest or type(policy) is not AIBudgetPolicy or type(reserved) is not Usage:
            raise ContractError()
        request=parse_payload(encoded(request)).payload
        policy=parse_payload(encoded(policy)).payload
        reserved=Usage(*usage_values(reserved))
        at=utc_instant(at)
        if ref('budget_policy',policy.policy_id,policy)!=request.budget_policy_ref or reserved.calls!=1 or reserved!=priced(reserved.input_tokens,reserved.output_tokens):
            raise ContractError()
        payload=(encoded(request),encoded(policy),encoded(reserved))
        with self._lock:
            if attempt_id in self._attempts:
                if self._payloads[attempt_id]!=payload:
                    raise ContractError()
                return self._attempts[attempt_id],False
            if policy.budget_scope in self._blocked:
                raise AIDenied('unknown_charge' if any(a.state=='unknown_charge' for a in self._attempts.values()) else 'usage_overrun')
            if not policy.window_start<=at<policy.window_end or at>=request.deadline:
                raise AIDenied('deadline')
            retry=policy.retry_policy
            if retry.max_retries or retry.retryable_reasons or retry.backoff_ms or retry.max_escalations or retry.transitions:
                raise AIDenied('retry_disabled')
            if request.client_profile!='synthetic':
                raise AIDenied('actual_disabled')
            # 동일 scope/window의 cap 변경으로 예약/정산을 우회하지 않는다.
            window=(policy.budget_scope,policy.window_start,policy.window_end)
            prior=self._policies.get(window)
            if prior is not None and prior!=policy:
                raise ContractError()
            if prior is None and any(s==policy.budget_scope and not (policy.window_end<=lo or hi<=policy.window_start) for s,lo,hi in self._policies):
                raise ContractError()
            active=sum(a.state in ('reserved','dispatched') for a in self._attempts.values())
            if active>=policy.concurrency_cap:
                raise AIDenied('budget')
            def over(v,cap):
                return any(x>y for x,y in zip(v,usage_values(cap)))
            if over(usage_values(reserved),policy.attempt_caps) or over(usage_values(reserved),request.caps):
                raise AIDenied('budget')
            scoped=[]
            for a in self._attempts.values():
                p=self.get(a.policy_ref)
                if p.budget_scope==policy.budget_scope and a.state!='cancelled_before_dispatch':
                    scoped.append((a,p,a.actual_usage or a.reserved_usage))
            for cap,rows in ((policy.window_caps,[u for a,p,u in scoped if (p.window_start,p.window_end)==(policy.window_start,policy.window_end)]),
                             (policy.role_caps,[u for a,p,u in scoped if a.role==request.role and (p.window_start,p.window_end)==(policy.window_start,policy.window_end)]),
                             (policy.request_caps,[u for a,p,u in scoped if a.request_ref.id==request.request_id])):
                total=tuple(x+sum(usage_values(u)[i] for u in rows) for i,x in enumerate(usage_values(reserved)))
                if over(total,cap):
                    raise AIDenied('budget')
            request_total=tuple(x+sum(usage_values(u)[i] for a,p,u in scoped if a.request_ref.id==request.request_id) for i,x in enumerate(usage_values(reserved)))
            if over(request_total,request.caps):
                raise AIDenied('budget')
            # request+policy+attemptを保存後、resultとsettlement/auditの最大領域を先取り。
            old_records=dict(self._records)
            try:
                self.append('request',request.request_id,request)
                self.append('budget_policy',policy.policy_id,policy)
                self._holds[attempt_id]=(3,3*65536)
                self._room(('attempt',attempt_id),b' ' * 4096)
                sequence=1+sum(a.request_ref.id==request.request_id for a in self._attempts.values())
                a=AIBudgetAttempt(1,'synthetic',attempt_id,ref('request',request.request_id,request),request.role,sequence,
                    'synthetic',request.budget_policy_ref,reserved,'reserved',at,None,None,None,())
                self._save_attempt(a)
            except Exception:
                self._records=old_records
                self._holds.pop(attempt_id,None)
                raise
            self._policies[window]=policy
            self._payloads[attempt_id]=payload
            return a,True

    def dispatch(self,attempt_id,*,at):
        at=utc_instant(at)
        with self._lock:
            a=self._attempts[attempt_id]
            if a.state!='reserved':
                raise ContractError()
            return self._save_attempt(replace(a,state='dispatched',dispatch_at=at))

    def cancel(self,attempt_id,*,at,retain_result=False):
        with self._lock:
            a=self._attempts[attempt_id]
            if a.state!='reserved':
                raise ContractError()
            a=self._save_attempt(replace(a,state='cancelled_before_dispatch',settled_at=utc_instant(at)))
            if not retain_result:
                self._holds.pop(attempt_id,None)
            return a

    def settle(self,attempt_id,usage,*,at):
        with self._lock:
            a=self._attempts[attempt_id]
            p=self.get(a.policy_ref)
            try:
                at=utc_instant(at)
                if at<(a.dispatch_at or a.reserved_at):
                    raise ContractError()
                if usage is not None:
                    if type(usage) is not Usage:
                        raise ContractError()
                    usage=Usage(*usage_values(usage))
                    if usage.calls!=1 or usage!=priced(usage.input_tokens,usage.output_tokens):
                        raise ContractError()
            except (ContractError,TypeError,ValueError,OverflowError):
                if a.state!='dispatched':
                    raise
                return self.settle_unknown(attempt_id)
            if a.state in ('settled','unknown_charge'):
                if a.actual_usage!=usage:
                    raise ContractError()
                return a
            if a.state!='dispatched':
                raise ContractError()
            reason=()
            if usage is None:
                reason=('unknown_charge',)
                self._blocked.add(p.budget_scope)
            elif any(x>y for x,y in zip(usage_values(usage),usage_values(a.reserved_usage))):
                reason=('usage_overrun',)
                self._blocked.add(p.budget_scope)
            return self._save_attempt(replace(a,state='settled' if usage else 'unknown_charge',actual_usage=usage,
                settled_at=at,reasons=reason))

    def settle_unknown(self,attempt_id):
        """전송 후 전제 실패의 확정. 마지막 확정 시각/정상 정산은 보존한다."""
        with self._lock:
            a=self._attempts[attempt_id]
            if a.state in ('settled','unknown_charge'):
                return a
            if a.state!='dispatched':
                raise ContractError()
            p=self.get(a.policy_ref)
            unknown=replace(a,state='unknown_charge',actual_usage=None,settled_at=a.dispatch_at,reasons=('unknown_charge',))
            self._blocked.add(p.budget_scope)
            return self._save_attempt(unknown)

    def finish(self,attempt_id,result):
        with self._lock:
            a=self._attempts[attempt_id]
            if result.request_ref!=a.request_ref or result.budget_attempt_refs!=(ref('attempt',attempt_id,a),):
                raise ContractError()
            hold=self._holds.pop(attempt_id,None)
            try:
                return self.append('result',result.result_id,result)
            except Exception:
                if hold:
                    self._holds[attempt_id]=hold
                raise

    def result_for(self,attempt_id):
        with self._lock:
            raw=self._records.get(('result','result:'+attempt_id))
            return parse_payload(raw).payload if raw else None

    def attempt(self,attempt_id):
        with self._lock:
            return parse_payload(encoded(self._attempts[attempt_id])).payload

    def balance(self,policy):
        with self._lock:
            values=[]
            for a in self._attempts.values():
                p=self.get(a.policy_ref)
                if p.budget_scope==policy.budget_scope and p.window_start==policy.window_start and a.state!='cancelled_before_dispatch':
                    values.append(a.actual_usage or a.reserved_usage)
            return policy.window_caps.charge-sum(u.charge for u in values)


class DeterministicSyntheticClient:
    def __init__(self,response,*,usage=priced(9,20)):
        if type(response) is not ModelResponse:
            raise ContractError()
        self._payload=encoded(response)
        self._usage=usage
        self.calls=0

    def invoke(self,request,attempt,dispatcher):
        self.calls+=1
        return ClientReply(self._payload,self._usage)


class DisabledActualClient:
    def invoke(self,request,attempt,dispatcher):
        raise AIDenied('actual_disabled')
