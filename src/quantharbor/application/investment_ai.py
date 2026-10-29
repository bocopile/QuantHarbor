"""Q25 읽기 전용 원천 검증/합성 호출. 금융 계산과 실행 권한을 만들지 않는다."""
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta
from fractions import Fraction
from hashlib import sha256
import json

from quantharbor.adapters.synthetic_investment_ai import AIDenied, SyntheticAIRepository
from quantharbor.application.document_ingest import validate_bundle
from quantharbor.application.research import (_replay_events, _revalidate_point, _resolved_bytes, build_bound_performance)
from quantharbor.domain import investment_ai as d
from quantharbor.domain.documents import select_view as document_view
from quantharbor.domain.ledger import hash_record
from quantharbor.domain.primitives import ContractError, utc_instant
from quantharbor.domain.research import known
from quantharbor.domain.serialization import parse_payload
from quantharbor.domain.valuation import finite, number
from quantharbor.market_data.timezones import ExplicitTimezone
from quantharbor.ports.investment_ai import DocumentSource, FinancialSource, CandidateSource, ClientReply
from quantharbor.runtime.boundary import authorize,synthetic_binding


class Incomplete(ValueError):
    def __init__(self,reason):
        self.reason=reason
        super().__init__(reason)


def performance_ref(source):
    return d.ref('performance','performance-'+hash_record(source.performance)[:24],source.performance)


def timezone_ref(zone):
    if type(zone) is not ExplicitTimezone:
        raise ContractError()
    raw=json.dumps({f.name:getattr(zone,f.name) for f in fields(zone) if f.name not in ('tzif_bytes','_zone')},sort_keys=True,separators=(',',':')).encode()
    return d.AIRef('timezone',zone.rules_version,1,d.CANONICAL,sha256(raw+zone.tzif_bytes).hexdigest())


class Sources:
    """호스트가 주입한 닫힌 원천 객체. ref는 검색 키이며 원천 승인 bool이 아니다."""
    def __init__(self,*,documents=(),financial=(),candidates=(),timezones=(),repository=None):
        self.repository=repository or SyntheticAIRepository()
        self._objects={}
        self._bindings={}
        self._zones={}
        self._all_financial=[]
        self._size=0
        for values,cls in ((documents,DocumentSource),(financial,FinancialSource),(candidates,CandidateSource),(timezones,ExplicitTimezone)):
            if type(values) is not tuple or len(values)>128 or any(type(x) is not cls for x in values):
                raise ContractError()
        for src in documents:
            b=src.bundle
            for kind,id,obj in (('document',b.manifest.batch_id,b.manifest),('context',b.context.context_id,b.context),
                                ('rights',src.current_rights.rights_ref,src.current_rights)):
                self._add(kind,id,obj,src)
            for claim in b.claims:
                self._add('revision','revision:'+hash_record(claim.revision),claim.revision,src)
                self._add('observation','observation:'+hash_record(claim.observation),claim.observation,src)
            for obj in b.originals:
                self._add('original',obj.raw_sha256,obj,src)
        for src in financial:
            self._financial(src)
        for src in candidates:
            a,i=src.artifacts,src.inputs
            self._financial(FinancialSource(i.risk_points,i.events,i.performance,i.boundaries,i.boundary_inputs,i.costs))
            self._financial(FinancialSource((i.current,*i.daily_usage_inputs),i.events,None,(),(),i.costs))
            self._add('plan',a.plan.plan_id,a.plan,src)
            for c in a.candidates:
                self._add('candidate',c.candidate_id,c,src)
            if i.policy:
                self._add('policy',i.policy.policy_id,i.policy,src)
            self._add('strategy',i.strategy.strategy_id,i.strategy,src)
        for zone in timezones:
            r=timezone_ref(zone)
            self._zones[r]=zone
            self._size+=len(zone.tzif_bytes)
        if self._size>8388608 or len(self._objects)+len(self._zones)>128:
            raise ContractError()
        self.repository.bind_sources(self)

    def _add(self,kind,id,obj,source):
        r=d.ref(kind,id,obj)
        raw=d.encoded(obj)
        prior=self._objects.get((kind,id))
        if prior and prior[0]!=r:
            raise ContractError()
        if not prior:
            self._size+=len(raw)
        self._objects[kind,id]=(r,parse_payload(raw).payload)
        self._bindings[r]=source
        if self._size>8388608:
            raise ContractError()
        return r

    def _financial(self,src):
        self._size+=_resolved_bytes((*src.points,*src.boundary_inputs),src.events)
        self._all_financial.append(src)
        if self._size>8388608:
            raise ContractError()
        for p in (*src.points,*src.boundary_inputs):
            self._add('snapshot',p.snapshot.snapshot_id,p.snapshot,src)
            for data in p.market_inputs:
                self._add('rights',data.current_rights.rights_ref,data.current_rights,src)
        for e in src.events:
            self._add('event',e.body.event_id,e.body,src)
        if src.performance:
            self._add('performance',performance_ref(src).id,src.performance,src)
        if src.benchmark:
            self._financial(src.benchmark)

    def refs(self):
        return tuple(v[0] for v in self._objects.values())+tuple(self._zones)

    def resolve(self,r):
        if type(r) is not d.AIRef:
            raise ContractError()
        if r.kind=='timezone':
            if r not in self._zones:
                raise Incomplete('missing_source')
            return self._zones[r]
        if r.kind in ('request','result','review','hypothesis','budget_policy','attempt'):
            obj=self.repository.get(r)
            if obj is None:
                raise Incomplete('missing_source')
            return obj
        row=self._objects.get((r.kind,r.id))
        if row is None:
            raise Incomplete('missing_source')
        if row[0]!=r:
            raise ContractError()
        return row[1]

    def _rights(self,grant,key,rights_ref,request,now,*,research=True):
        if grant.rights_ref!=rights_ref:
            raise AIDenied('rights_denied')
        required=('ai','store','research') if request.purpose=='ai_research' else (('ai','store','report','research') if research else ('ai','store','report'))
        if not all(grant.allows(at=now,purpose=p,source_id=key[0],dataset_id=key[1],dataset_version=key[2]) for p in required):
            raise AIDenied('rights_denied')

    def financial(self,src,request,now):
        # 모든 평가/흐름/후속일간/benchmark 입력을 검사한다. historical grant로 대체하지 않는다.
        all_points=(*src.points,*src.boundary_inputs)
        for p in all_points:
            s=p.snapshot
            if request.account_ref!=s.account_ref or s.knowledge_cutoff>request.knowledge_cutoff or s.as_of>request.as_of:
                raise AIDenied('future_source')
            for h in s.holdings:
                if request.scope and h.position.key not in {x.key for x in request.scope}:
                    raise AIDenied('query_denied')
            for data in p.market_inputs:
                desc=data.bundle.descriptor
                req=desc.request
                grant=data.current_rights
                self._rights(grant,(req.source_id,req.dataset_id,req.dataset_version),desc.historical_rights_snapshot.rights_ref,request,now)
                if any(x.observation.rights_ref!=grant.rights_ref for x in data.bundle.evidence):
                    raise AIDenied('rights_denied')
            for proof in s.valuation.market_proofs:
                matches=[x for x in p.market_inputs if (x.bundle.descriptor.request.source_id,x.bundle.descriptor.request.dataset_id,
                    x.bundle.descriptor.request.dataset_version)==proof.selection.dataset_key]
                if len(matches)!=1:
                    raise Incomplete('proof_incomplete')
                self._rights(matches[0].current_rights,proof.selection.dataset_key,proof.rights.rights_ref,request,now)
                if not proof.usable:
                    raise Incomplete('proof_incomplete')
            expected={(x.series.source_id,x.series.dataset_id,x.series.dataset_version,x.series.series_id) for x in s.valuation.policy.prices}
            expected|={(x.series.source_id,x.series.dataset_id,x.series.dataset_version,x.series.series_id) for x in s.valuation.policy.fx}
            actual={(x.selection.source_id,x.selection.dataset_id,x.selection.dataset_version,x.selection.series_id) for x in s.valuation.market_proofs}
            if expected-actual:
                raise Incomplete('proof_incomplete')
        store=_replay_events(src.events)
        for p in all_points:
            rebuilt=_revalidate_point(p,store)
            if not rebuilt.valuation.projection.complete:
                raise Incomplete('proof_incomplete')
        dependencies=[d.ref('snapshot',p.snapshot.snapshot_id,p.snapshot) for p in all_points]
        dependencies.extend(d.ref('event',e.body.event_id,e.body) for e in src.events)
        dependencies.extend(d.ref('rights',data.current_rights.rights_ref,data.current_rights) for p in all_points for data in p.market_inputs)
        if src.performance:
            dependencies.append(performance_ref(src))
            rebuilt=build_bound_performance(src.points,src.events,boundaries=src.boundaries,boundary_inputs=src.boundary_inputs,costs=src.costs)
            # scalar benchmark를 권위로 사용하지 않는다. 실제 counterpart를 다시 계산한다.
            if src.benchmark:
                dependencies.extend(self.financial(src.benchmark,request,now))
                bp=src.benchmark
                if (bp.points[0].snapshot.as_of,bp.points[-1].snapshot.as_of,bp.points[0].snapshot.base_currency)!=(src.points[0].snapshot.as_of,src.points[-1].snapshot.as_of,src.points[0].snapshot.base_currency):
                    raise ContractError()
                bperf=build_bound_performance(bp.points,bp.events,boundaries=bp.boundaries,boundary_inputs=bp.boundary_inputs,costs=bp.costs)
                rebuilt=build_bound_performance(src.points,src.events,boundaries=src.boundaries,boundary_inputs=src.boundary_inputs,costs=src.costs,benchmark_return=bperf.twr)
            elif src.performance.benchmark_return.value is not None:
                raise Incomplete('unknown_metric')
            if rebuilt!=src.performance:
                raise ContractError()
        return tuple(dict.fromkeys(dependencies))

    def validate(self,r,request,now):
        obj=self.resolve(r)
        src=self._bindings.get(r)
        if isinstance(src,DocumentSource):
            b=src.bundle
            self._rights(src.current_rights,(b.manifest.source_id,b.manifest.dataset_id,b.manifest.dataset_version),src.current_rights.rights_ref,request,now)
            try:
                validate_bundle(b,catalog=src.catalog,rights=src.current_rights,at=now)
                view=document_view(b,catalog=src.catalog,rights=src.current_rights,evaluated_at=now,
                    knowledge_cutoff=request.knowledge_cutoff,purpose='ai')
            except ContractError:
                raise AIDenied('rights_denied') from None
            if view.missing_document_ids:
                raise Incomplete('missing_source')
            if any('conflict' in x or 'fork' in x for x in view.held_reasons):
                raise Incomplete('conflict')
            if not view.usable_for_research:
                raise Incomplete('missing_source')
            if request.scope:
                allowed=[]
                for position in request.scope:
                    allowed.extend(m for m in src.catalog.mappings if
                        (m.instrument_id,m.execution_venue_id,m.mapping_version)==(position.instrument_id,position.venue_id,position.mapping_version)
                        and m.valid_from<=request.as_of and (m.valid_to is None or request.as_of<m.valid_to)
                        and m.known_at<=request.knowledge_cutoff)
                for selected in view.selected:
                    links=tuple(link for link in selected.instrument_links if any(
                        (link.instrument_id,link.listing_venue_id)==(m.instrument_id,m.listing_venue_id) for m in allowed))
                    if not links or any(not any((e.entity_id,e.entity_version)==(link.entity_id,link.entity_version) for link in links) for e in selected.entities):
                        raise AIDenied('query_denied')
            return obj,(d.ref('document',b.manifest.batch_id,b.manifest),d.ref('rights',src.current_rights.rights_ref,src.current_rights))
        if isinstance(src,FinancialSource):
            refs=self.financial(src,request,now)
            return obj,refs+tuple(d.ref('rights',data.current_rights.rights_ref,data.current_rights) for p in (*src.points,*src.boundary_inputs) for data in p.market_inputs)
        if isinstance(src,CandidateSource):
            from quantharbor.application.target import build_target
            from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
            i=src.inputs
            dependencies=list(self.financial(FinancialSource(i.risk_points,i.events,i.performance,i.boundaries,i.boundary_inputs,i.costs),request,now))
            dependencies.extend(self.financial(FinancialSource((i.current,*i.daily_usage_inputs),i.events,None,(),(),i.costs),request,now))
            if request.account_ref!=src.request.account_ref or request.scope and any(x.body.terms.position not in request.scope for x in src.artifacts.candidates):
                raise AIDenied('query_denied')
            if now>=src.request.expires_at:
                raise AIDenied('expired')
            if build_target(src.request,i,SyntheticTargetRepository())!=src.artifacts:
                raise ContractError()
            dependencies.extend(d.ref('candidate',c.candidate_id,c) for c in src.artifacts.candidates)
            dependencies.extend((d.ref('plan',src.artifacts.plan.plan_id,src.artifacts.plan),
                                 d.ref('strategy',i.strategy.strategy_id,i.strategy)))
            if i.policy:
                dependencies.append(d.ref('policy',i.policy.policy_id,i.policy))
            for p in (*i.risk_points,i.current,*i.daily_usage_inputs,*i.boundary_inputs):
                dependencies.append(d.ref('snapshot',p.snapshot.snapshot_id,p.snapshot))
                dependencies.extend(d.ref('rights',x.current_rights.rights_ref,x.current_rights) for x in p.market_inputs)
            return obj,tuple(dict.fromkeys(dependencies))
        if r.kind=='hypothesis':
            self.hypothesis(r,request,now)
        elif r.kind=='timezone':
            if obj.timezone_id!='Asia/Seoul':
                raise ContractError()
        return obj,(r,)

    def hypothesis(self,r,request,now):
        h=self.resolve(r)
        if type(h) is not d.Hypothesis:
            raise ContractError()
        if not h.created_at<=now<h.expires_at:
            raise AIDenied('expired')
        origin=self.resolve(h.origin_result_ref)
        origin_request=self.resolve(origin.request_ref)
        required=self.repository.hypothesis_dependencies(h.origin_result_ref)
        if not set(required)<=set(h.dependencies):
            raise AIDenied('dependency_changed')
        if origin.response is None:
            raise AIDenied('dependency_changed')
        status,reasons,_,_=validate_response(origin_request,origin.response,self,now)
        if status in ('blocked','invalid'):
            raise AIDenied('rights_denied' if 'rights_denied' in reasons else 'dependency_changed')
        for other in self.repository.hypotheses():
            if other.created_at>now:
                continue
            if other.retracts_ref==r:
                raise AIDenied('retracted')
            if other.supersedes_ref==r:
                raise AIDenied('superseded')
        for dep in h.dependencies:
            if dep.kind in ('hypothesis','result','request','review','attempt'):
                raise ContractError()
            try:
                self.validate(dep,request,now)
            except (Incomplete,ContractError):
                raise AIDenied('dependency_changed') from None
        return h

    def citation(self,c,request,now):
        if c.manifest_ref not in request.source_refs:
            raise ContractError()
        self.resolve(c.manifest_ref)
        src=self._bindings[c.manifest_ref]
        b=src.bundle
        # bindings must all belong to the very same Q18 bundle.
        for r in (c.revision_ref,c.observation_ref,c.original_ref,c.context_ref):
            self.resolve(r)
            if self._bindings[r] is not src:
                raise ContractError()
        revision=self.resolve(c.revision_ref)
        obs=self.resolve(c.observation_ref)
        original=self.resolve(c.original_ref)
        from quantharbor.domain.market_data import record_hash
        if revision.published_at is None or revision.published_at>request.knowledge_cutoff or obs.ingested_at>request.knowledge_cutoff or obs.observed_at>request.knowledge_cutoff:
            raise AIDenied('future_source')
        self.validate(c.manifest_ref,request,now)
        view=document_view(b,catalog=src.catalog,rights=src.current_rights,evaluated_at=now,knowledge_cutoff=request.knowledge_cutoff,purpose='ai')
        if not any(x.claim.revision==revision and x.claim.observation==obs and x.original==original for x in view.selected) or revision.original_hash!=record_hash(original) or b.context!=self.resolve(c.context_ref):
            raise ContractError()
        raw=original.text.encode()
        try:
            quote=raw[c.start_utf8:c.end_utf8].decode('utf-8')
        except UnicodeError:
            raise ContractError() from None
        if quote!=c.exact_quote or c.end_utf8>len(raw):
            raise ContractError()

    def numeric(self,c,request,now):
        if c.source_ref not in request.source_refs:
            raise ContractError()
        obj,refs=self.validate(c.source_ref,request,now)
        src=self._bindings[c.source_ref]
        selector=c.selector
        if selector.startswith('snapshot.') and c.source_ref.kind=='snapshot':
            at=obj.as_of
            unit='share' if selector.endswith('holding_quantity') else 'currency'
            cur=None if unit=='share' else obj.base_currency
            if c.period is not None:
                raise ContractError()
            if selector in ('snapshot.nav','snapshot.economic_cash') and c.position is not None:
                raise ContractError()
            if selector=='snapshot.nav':
                value=obj.valuation.nav
            elif selector=='snapshot.economic_cash':
                value=finite(sum((number(x.economic_cash) for x in obj.cash_by_currency),Fraction())) if all(x.currency==obj.base_currency for x in obj.cash_by_currency) else None
            else:
                if c.position is None or c.position not in request.scope:
                    raise ContractError()
                value=next((h.position.amount for h in obj.holdings if h.position.key==c.position.key),None)
        elif selector.startswith('performance.') and c.source_ref.kind=='performance':
            if c.position is not None:
                raise ContractError()
            name=selector.split('.')[1]
            at=src.points[-1].snapshot.as_of
            if c.period is not None and (c.period.start,c.period.end)!=(src.points[0].snapshot.as_of,at):
                raise Incomplete('period_mismatch')
            unit='currency' if name in ('amount_pnl','fees','taxes','slippage') else 'ratio'
            cur=src.points[0].snapshot.base_currency if unit=='currency' else None
            if name in ('fees','taxes','slippage'):
                if any(f.currency!=cur for f in src.costs):
                    raise Incomplete('unknown_metric')
                value=finite(sum((f.slippage if name=='slippage' else sum((number(a.amount) for a in f.allocations if a.kind==('fee' if name=='fees' else 'tax')),Fraction()) for f in src.costs if src.points[0].snapshot.as_of<f.effective_at<=at),Fraction()))
            else:
                value=getattr(obj,name).value
        elif selector.startswith('candidate.') and c.source_ref.kind=='candidate':
            terms=obj.body.terms
            name=selector.split('.')[1]
            at=src.request.as_of
            value=getattr(terms,name)
            unit='share' if name=='quantity' else 'currency'
            cur=None if unit=='share' else terms.currency
            if c.position!=terms.position or c.period is not None:
                raise ContractError()
        else:
            raise ContractError()
        if c.as_of!=at:
            raise ContractError()
        if c.unit!=unit or c.currency!=cur:
            raise ContractError()
        if value is None:
            raise Incomplete('unknown_metric')
        if c.value!=value:
            raise ContractError()
        return value,refs


class ReadonlyDispatcher:
    def __init__(self,request,sources,*,clock,attempt_id=None):
        self.request=request
        self.sources=sources
        self.clock=clock
        self.receipts=[]
        self.attempt_id=attempt_id

    def execute(self,query):
        now=utc_instant(self.clock())
        obj,receipt=self.sources.repository.execute_query(self.request,query,self.sources,at=now,attempt_id=self.attempt_id)
        self.receipts.append(receipt)
        return obj


def validate_response(request,response,sources,now):
    response=parse_payload(d.encoded(response)).payload
    reasons=[]
    checks=[]
    manifest=[]
    status='complete'
    def mark(s,reason,subject=None):
        nonlocal status
        priority={'complete':0,'partial':1,'invalid':2,'blocked':3}
        if priority[s]>priority[status]:
            status=s
        if reason not in reasons:
            reasons.append(reason)
        checks.append(d.Check(reason,subject,None,None,'unknown' if s=='partial' else 'fail'))
    def perform(fn,reason,subject=None):
        try:
            fn()
            checks.append(d.Check(reason,subject,None,None,'pass'))
        except AIDenied as e:
            mark('blocked',e.reason,subject)
        except Incomplete as e:
            mark('partial',e.reason,subject)
        except ContractError:
            mark('invalid',reason,subject)
    for q in response.queries:
        kinds={'document_view':('document',),'snapshot_view':('snapshot',),'research_view':('performance','experiment'),
               'candidate_view':('candidate','plan'),'hypothesis_view':('hypothesis',)}
        if q.name not in d.ROLE_QUERIES[request.role] or q.name not in request.allowed_queries or q.source_ref not in request.source_refs or q.source_ref.kind not in kinds[q.name]:
            mark('blocked','query_denied',q.source_ref)
    for r in request.source_refs:
        def resolve(r=r):
            _,refs=sources.validate(r,request,now)
            manifest.extend((r,*refs))
        perform(resolve,'identity',r)
    for c in response.citations:
        perform(lambda c=c:sources.citation(c,request,now),'citation',c.manifest_ref)
    for c in response.numeric_claims:
        perform(lambda c=c:sources.numeric(c,request,now),'numeric',c.source_ref)
    if 'document' in request.required_outputs and not response.citations:
        mark('partial','missing_source')
    if 'numeric' in request.required_outputs and not response.numeric_claims:
        mark('partial','unknown_metric')
    if 'narrative' in request.required_outputs and not response.narrative_claims:
        mark('partial','missing_source')
    if response.finish_reason=='length':
        mark('partial','truncated')
    # explicit unknowns/counterevidence preserve uncertainty, never create consensus.
    if response.counterevidence:
        mark('partial','conflict')
    if response.unknowns:
        mark('partial','missing_source')
    if len(checks)>64:
        raise ContractError()
    return status,tuple(reasons),tuple(checks),tuple(dict.fromkeys(manifest))


def period_review(request,sources,now):
    p=request.period
    zone=sources.resolve(p.timezone_ref)
    if zone.timezone_id!='Asia/Seoul':
        raise ContractError()
    # Q16 range/known_at + actual TZif offsets are consulted.
    for instant in (p.start,p.end):
        local=zone.to_local(instant,knowledge_cutoff=request.knowledge_cutoff)
        if (local.hour,local.minute,local.second,local.microsecond)!=(0,0,0,0):
            raise ContractError()
    metrics=[]
    perf_ref=None
    base=None
    for r in request.source_refs:
        obj,refs=sources.validate(r,request,now)
        src=sources._bindings.get(r)
        if isinstance(src,FinancialSource):
            base=src.points[0].snapshot.base_currency
        if r.kind=='performance':
            perf_ref=r
            matching=(src.points[0].snapshot.as_of,src.points[-1].snapshot.as_of)==(p.start,p.end)
            for selector in ('twr','amount_pnl','observed_mdd','gross_turnover','benchmark_return'):
                metric=getattr(obj,selector)
                metrics.append(d.Check('numeric' if matching and metric.value is not None else 'period_mismatch' if not matching else 'unknown_metric',r,
                    selector,metric.value if matching else None,'pass' if matching and metric.value is not None else 'unknown'))
    if not metrics:
        metrics=[d.Check('unknown_metric',None,'performance',None,'unknown')]
    if base is None or request.account_ref is None:
        raise Incomplete('missing_source')
    return d.PeriodReview(p,request.account_ref,base,request.source_refs,perf_ref,None,tuple(metrics),(),(),('intervention_unknown',),None,'display_[start,end);performance_(start,end]')


def run_research(request,policy,sources,client,*,attempt_id,reserved,clock):
    return sources.repository.execute(request,policy,sources,client,attempt_id=attempt_id,reserved=reserved,clock=clock)


def _settle_dispatched(repo,attempt_id,usage,clock):
    try:
        return repo.settle(attempt_id,usage,at=clock())
    except Exception:
        # clock 자체의 예외/잘못된 값도 전송 후 불명 청구다.
        return repo.settle_unknown(attempt_id)


def _bounded_result(values):
    """응답 포장 초과도 exact attempt/실행 receipt를 보존한 실패 기록으로 확정한다."""
    def fits():
        wrapper=dict(schema_name='ResearchResult',schema_version=1,environment='synthetic',payload=values)
        return len(json.dumps(wrapper,default=asdict,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())<=65536
    if not fits():
        values.update(response=None,checks=(),status=values['status'] if values['status'] in ('blocked','failed') else 'invalid',reasons=tuple(dict.fromkeys((*values['reasons'],'schema'))))
        if not fits():
            # request_ref는 원래 source_refs를 결속한다. current_result는 항상 현재 권리를 재검사한다.
            values['input_manifest']=tuple(r for r in values['input_manifest'] if r.kind=='rights')
        if not fits():
            values['input_manifest']=()
        if not fits():
            values['period_review']=None
    return d.ResearchResult(**values)


def _run_research(request,policy,sources,client,*,attempt_id,reserved,clock):
    request=parse_payload(d.encoded(request)).payload
    policy=parse_payload(d.encoded(policy)).payload
    repo=sources.repository
    start=utc_instant(clock())
    identity=d.ClientIdentity('synthetic:'+attempt_id,'synthetic',None)
    attempt=None
    response=None
    manifest=()
    checks=()
    period=None
    status='blocked'
    reasons=()
    new=False
    dispatcher=ReadonlyDispatcher(request,sources,clock=clock,attempt_id=attempt_id)
    try:
        attempt,new=repo.reserve(request,policy,attempt_id,reserved,at=start)
        if not new:
            # dispatch/settlement/reservation replay never calls a second client.
            existing=repo.result_for(attempt_id)
            if existing is not None:
                current,status,current_reasons=current_result(d.ref('result',existing.result_id,existing),sources,at=start)
                if current is None or status!=existing.status or current_reasons!=existing.reasons:
                    return replace(existing,result_id='denied:'+attempt_id,response=None,input_manifest=(),query_receipts=(),checks=(),
                        period_review=None,status='blocked',reasons=current_reasons or ('dependency_changed',)),False
                return existing,False
            raise AIDenied('budget')
        try:
            dispatch_at=utc_instant(clock())
            if dispatch_at<start:
                raise ContractError()
        except Exception:
            attempt=repo.cancel(attempt_id,at=start,retain_result=True)
            status,reasons='failed',('client_failure',)
        else:
            if dispatch_at>=request.deadline:
                attempt=repo.cancel(attempt_id,at=dispatch_at,retain_result=True)
                raise AIDenied('deadline')
            attempt=repo.dispatch(attempt_id,at=dispatch_at)
            try:
                reply=client.invoke(request,attempt,dispatcher)
                if type(reply) is not ClientReply:
                    raise ContractError()
            except Exception:
                attempt=_settle_dispatched(repo,attempt_id,None,clock)
                status='failed'
                reasons=('client_failure',)
            else:
                attempt=_settle_dispatched(repo,attempt_id,reply.usage,clock)
                finish=attempt.settled_at
                try:
                    response=parse_payload(reply.payload).payload
                    if type(response) is not d.ModelResponse:
                        raise ContractError()
                    identity=response.identity
                    status,reasons,checks,manifest=validate_response(request,response,sources,finish)
                    for q in response.queries:
                        dispatcher.execute(q)
                except AIDenied as e:
                    status,reasons='blocked',(e.reason,)
                except Incomplete as e:
                    status,reasons='partial',(e.reason,)
                except (ContractError,ValueError,TypeError):
                    response=None
                    status,reasons='invalid',('schema',)
                if 'usage_overrun' in attempt.reasons:
                    status,reasons='blocked',('usage_overrun',)
                elif attempt.state=='unknown_charge' and status=='complete':
                    status,reasons='partial',('unknown_charge',)
                if repo.query_denials(attempt_id):
                    status,reasons='blocked',tuple(dict.fromkeys((*reasons,*repo.query_denials(attempt_id))))
                if finish>=request.deadline or datetime.fromisoformat(finish)-datetime.fromisoformat(attempt.dispatch_at)>=timedelta(seconds=10):
                    status,reasons='failed',('deadline',)
    except AIDenied as e:
        status,reasons='blocked',(e.reason,)
    except ContractError:
        status,reasons='invalid',('identity',)
    try:
        finish=utc_instant(clock())
    except Exception:
        if not new or attempt is None:
            raise
        if attempt.state!='cancelled_before_dispatch':
            attempt=repo.settle_unknown(attempt_id)
        finish=attempt.settled_at
    if attempt is not None:
        finish=max(finish,attempt.settled_at or attempt.dispatch_at or attempt.reserved_at)
    if new and attempt is not None and attempt.dispatch_at is not None and request.period:
        try:
            period=period_review(request,sources,finish)
            if period.intervention_unknowns or any(c.outcome=='unknown' for c in period.metrics):
                status='partial' if status=='complete' else status
                reasons=tuple(dict.fromkeys((*reasons,'intervention_unknown',*(('period_mismatch',) if any(c.code=='period_mismatch' for c in period.metrics) else ()))))
        except AIDenied as e:
            status,reasons='blocked',tuple(dict.fromkeys((*reasons,e.reason)))
        except Incomplete as e:
            status='partial' if status=='complete' else status
            reasons=tuple(dict.fromkeys((*reasons,e.reason)))
        except (ContractError,ValueError,TypeError):
            status,reasons='invalid',tuple(dict.fromkeys((*reasons,'identity')))
    result=_bounded_result(dict(schema_version=1,environment='synthetic',result_id='result:'+attempt_id,
        request_ref=d.ref('request',request.request_id,request),input_manifest=manifest,client_identity=identity,
        procedure_version=request.procedure_version,instruction_version=request.instruction_version,
        tool_schema_version=request.tool_schema_version,started_at=start,finished_at=finish,response=response,
        query_receipts=tuple(dispatcher.receipts),budget_attempt_refs=(d.ref('attempt',attempt_id,attempt),) if attempt else (),
        checks=checks,status=status,reasons=reasons,period_review=period))
    return result,new


def review_result(review_request,exact_result_ref,reviewer,sources,*,at,candidate_ref=None):
    return sources.repository.execute_review(review_request,exact_result_ref,reviewer,sources,at=at,candidate_ref=candidate_ref)


def _review_result(review_request,exact_result_ref,reviewer,sources,*,at,candidate_ref=None):
    now=utc_instant(at)
    if type(reviewer) is not d.ClientIdentity or review_request.role!='risk' or review_request.review_subject_ref!=exact_result_ref:
        raise ContractError()
    result=sources.resolve(exact_result_ref)
    if type(result) is not d.ResearchResult or result.client_identity.invocation_id==reviewer.invocation_id or now<result.finished_at:
        raise ContractError()
    request=sources.resolve(result.request_ref)
    # current time and rights; original financial scope/cutoff is kept.
    if result.response is None:
        raise ContractError()
    status,reasons,checks,manifest=validate_response(request,result.response,sources,now)
    queries=tuple(dict.fromkeys((*result.response.queries,*(r.query for r in result.query_receipts))))
    if any(q.name not in d.ROLE_QUERIES[context.role] or q.name not in context.allowed_queries or q.source_ref not in context.source_refs
           for context in (request,review_request) for q in queries):
        status,reasons='blocked',tuple(dict.fromkeys((*reasons,'query_denied')))
    review_status,review_reasons,review_checks,review_manifest=validate_response(review_request,result.response,sources,now)
    if {'complete':0,'partial':1,'invalid':2,'blocked':3}[review_status]>{'complete':0,'partial':1,'invalid':2,'blocked':3}[status]:
        status=review_status
    reasons=tuple(dict.fromkeys((*reasons,*review_reasons)))
    checks=tuple(dict.fromkeys((*checks,*review_checks)))
    manifest=tuple(dict.fromkeys((*manifest,*review_manifest)))
    if candidate_ref:
        if candidate_ref not in request.source_refs:
            raise ContractError()
        sources.validate(candidate_ref,request,now)
    verdict='accepted' if status=='complete' and result.status=='complete' else 'blocked' if status=='blocked' else 'changes_required'
    review=d.ResearchReview(1,'synthetic','review:'+reviewer.invocation_id,d.ref('request',review_request.request_id,review_request),
        exact_result_ref,reviewer,now,manifest,checks,reasons,verdict,candidate_ref)
    return review


def current_result(exact_result_ref,sources,*,at):
    """저장 결과를 표시할 때 현재 권리/의존성을 재검사한다. 과거 불변 기록은 보존."""
    result=sources.resolve(exact_result_ref)
    if type(result) is not d.ResearchResult:
        raise ContractError()
    request=sources.resolve(result.request_ref)
    now=utc_instant(at)
    if now<result.finished_at:
        raise ContractError()
    validation_response=result.response or d.ModelResponse(result.client_identity,'stop',(),(),(),(),(),(),())
    status,reasons,checks,manifest=validate_response(request,validation_response,sources,now)
    if status in ('blocked','invalid'):
        return None,status,reasons
    if result.response:
        body_refs=[c.source_ref for c in result.response.numeric_claims]
        for c in result.response.citations:
            body_refs.extend((c.manifest_ref,c.revision_ref,c.observation_ref,c.original_ref,c.context_ref))
        body_refs.extend(r.query.source_ref for r in result.query_receipts)
        for r in dict.fromkeys(body_refs):
            try:
                sources.resolve(r)
            except Incomplete as e:
                return None,'partial',(e.reason,)
            except ContractError:
                return None,'invalid',('identity',)
    # 원래부터 불완전한 안전한 부분은 유지하되, 현재 새로 실패한 원천은 숨긴다.
    prior_failures={(c.code,c.subject_ref) for c in result.checks if c.outcome!='pass'}
    unavailable=any(c.outcome!='pass' and c.subject_ref is not None and (c.code,c.subject_ref) not in prior_failures for c in checks)
    if unavailable:
        return None,status,reasons
    if result.response is None or status=='complete' and result.status!='complete':
        return result,result.status,result.reasons
    return result,status,reasons
