"""Q25 독립 선언 합성 원천과 평가 fixture. 실제 API/계좌 자료 없음."""
from dataclasses import replace,asdict
from datetime import datetime,timedelta
from functools import lru_cache

from quantharbor.domain import investment_ai as d
from quantharbor.application.investment_ai import Sources,performance_ref,timezone_ref,run_research
from quantharbor.adapters.synthetic_investment_ai import SyntheticAIRepository,DeterministicSyntheticClient
from quantharbor.application.research import build_bound_performance,nav_point
from quantharbor.ports.investment_ai import DocumentSource,FinancialSource,CandidateSource
from quantharbor.domain.primitives import utc_instant
from quantharbor.domain.ledger import hash_record
import synthetic_documents as doc
from synthetic_research import flow_fixture
from synthetic_timezones import synthetic_timezone

NOW='2024-03-08T14:31:08Z'


def policy(*,golden=False,**changes):
    caps=d.Usage(131072,32768,16,100 if golden else 196624)
    values=dict(schema_version=1,environment='synthetic',policy_id='ai-budget-v1',version=1,budget_scope='synthetic-shared',
        window_start='2024-01-01T00:00:00Z',window_end='2025-01-01T00:00:00Z',charge_unit='synthetic_microcredit',
        pricing_version='synthetic-unit-v1',input_rate=1,output_rate=2,fixed_call_cost=1,window_caps=caps,
        role_caps=d.Usage(32768,8192,4,49156),request_caps=d.Usage(32768,8192,4,49156),
        attempt_caps=d.Usage(8192,2048,1,12289),concurrency_cap=2,retry_policy=d.RetryPolicy(0,(),0,0,()))
    return d.AIBudgetPolicy(**(values|changes))


def request(source_refs=(),*,p=None,**changes):
    p=p or policy()
    values=dict(schema_version=1,environment='synthetic',request_id='ai-request',run_id='ai-run',idempotency_key='ai-idem',
        role='risk',purpose='ai_research',account_ref=None,scope=(),as_of=NOW,knowledge_cutoff=NOW,evaluated_at=NOW,
        deadline='2024-03-08T14:32:08Z',locale='ko-KR',source_refs=tuple(source_refs),required_outputs=(),
        allowed_queries=d.QUERIES,procedure_version='ai-procedure-v1',instruction_version='ai-instruction-v1',tool_schema_version='ai-tools-v1',
        client_profile='synthetic',budget_policy_ref=d.ref('budget_policy',p.policy_id,p),caps=d.Usage(8192,2048,1,12289),period=None,review_subject_ref=None)
    return d.ResearchRequest(**(values|changes))


def response(*,numeric=(),narrative=(),citations=(),queries=(),**changes):
    values=dict(identity=d.ClientIdentity('synthetic-author-1','synthetic',None),finish_reason='stop',numeric_claims=numeric,
        narrative_claims=narrative,citations=citations,queries=queries,assumptions=(),counterevidence=(),unknowns=())
    return d.ModelResponse(**(values|changes))


def document_source(*,text='합성 문서\nSynthetic filing.',**changes):
    bundle=doc.batch((doc.document(text),),**changes)
    return DocumentSource(bundle,doc.catalog(),doc.rights())


def document_refs(src):
    b=src.bundle
    c=b.claims[0]
    return (d.ref('document',b.manifest.batch_id,b.manifest),d.ref('revision','revision:'+hash_record(c.revision),c.revision),
        d.ref('observation','observation:'+hash_record(c.observation),c.observation),d.ref('original',b.originals[0].raw_sha256,b.originals[0]),d.ref('context',b.context.context_id,b.context))


def citation(src,*,start=0,end=None):
    text=src.bundle.originals[0].text
    raw=text.encode()
    end=len(raw) if end is None else end
    return d.Citation(*document_refs(src),start,end,raw[start:end].decode())


@lru_cache(maxsize=1)
def flow_source():
    points,events,boundary_inputs,boundary=flow_fixture()
    perf=build_bound_performance(points,events,boundaries=(boundary,),boundary_inputs=boundary_inputs)
    return FinancialSource(points,events,perf,(boundary,),boundary_inputs)


@lru_cache(maxsize=1)
def mdd_source():
    import synthetic_valuation as v
    from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
    from quantharbor.application.valuation import build_snapshot
    from quantharbor.domain.market_data import MarketItem,record_hash
    from quantharbor.ports.research import ResearchPointInput
    store=v.ledger(holdings=(replace(v.HOLDING,amount='1'),),cash='1')
    records=[]
    for i,price in enumerate(('99','119','89','107')):
        item=v.price_item(price)
        end=utc_instant(datetime.fromisoformat(v.END)+timedelta(seconds=i))
        bar=replace(item.revision.payload,ends_at=end)
        revision=replace(item.revision,event_id='mdd-price-'+str(i),effective_at=end,published_at=end,payload=bar)
        observation=replace(item.observation,observation_id='mdd-obs-'+str(i),event_id=revision.event_id,observed_at=v.NOW,ingested_at=v.NOW,
            revision_hash=record_hash(revision))
        records.append(MarketItem(revision,observation))
    market=v.market(records=tuple(records),historical_rights=replace(v.rights(),purposes=('store','research','report','ai')))
    points=[]
    for i in range(4):
        at=utc_instant(datetime.fromisoformat(v.END)+timedelta(seconds=i))
        p=store.replay(v.ACCOUNT,as_of=at,knowledge_cutoff=v.NOW)
        req=v.request(request_id='mdd-'+str(i),as_of=at)
        snap=build_snapshot(p,req,(market,),v.policy(),v.reconciliation_policy(),SyntheticSnapshotRepository())
        points.append(ResearchPointInput(snap,(market,)))
    events=tuple(store.state(v.ACCOUNT).events)
    perf=build_bound_performance(tuple(points),events)
    return FinancialSource(tuple(points),events,perf)


@lru_cache(maxsize=1)
def candidate_source():
    import synthetic_target as t
    from quantharbor.application.valuation import build_snapshot
    from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
    from quantharbor.domain.target import ref
    r,i=t.fixture()
    points=[]
    for point in i.risk_points:
        data=tuple(replace(x,current_rights=replace(x.current_rights,purposes=('store','research','report','ai'))) for x in point.market_inputs)
        s=point.snapshot
        new=build_snapshot(s.valuation.projection,s.valuation.request,data,s.valuation.policy,s.reconciliation_policy,
            SyntheticSnapshotRepository(),statement=s.reconciliation_details.statement)
        points.append(replace(point,snapshot=new,market_inputs=data))
    perf=build_bound_performance(tuple(points),i.events)
    current=points[-1]
    facts=replace(i.facts,projection_ref=ref('projection','current-projection',current.snapshot.valuation.projection),
        loss_performance_ref=ref('performance','loss-performance',perf))
    i=replace(i,current=current,risk_points=tuple(points),performance=perf,facts=facts)
    r=replace(r,snapshot_ref=ref('snapshot',current.snapshot.snapshot_id,current.snapshot),research_refs=(ref('performance','loss-performance',perf),))
    return CandidateSource(r,i,t.build(r,i))


def numeric(src,selector,value,*,id='n1',unit=None,currency=None):
    ratio=selector.split('.')[-1] in ('twr','observed_mdd','gross_turnover','benchmark_return')
    return d.NumericClaim(id,performance_ref(src),selector,None,None,value,unit or ('ratio' if ratio else 'currency'),
        currency if currency else None if ratio else 'USD',src.points[-1].snapshot.as_of)


def run(req,resp,*,sources=None,p=None,client=None,attempt='a1',reserved=None,clock=None):
    sources=sources or Sources()
    p=p or policy()
    client=client or DeterministicSyntheticClient(resp)
    result=run_research(req,p,sources,client,attempt_id=attempt,reserved=reserved or d.priced(69,20),clock=clock or (lambda:NOW))
    rows=[]
    for ar in result.budget_attempt_refs:
        a=sources.repository.get(ar)
        rows.append(asdict(a))
    RUN_EVIDENCE[d.ref('result',result.result_id,result).sha256]=rows
    return result


def bilingual_source():
    from quantharbor.domain.documents import Entity,DocumentEntityContext,DocumentEntityLink,revision_ref
    first=doc.document('한빛 / Hanbit — 한국 문서',revision_changes={'document_id':'same-name.KR'},observation_changes={'observation_id':'same.KR'})
    second=doc.document('한빛 / Hanbit — English filing',revision_changes={'document_id':'same-name.US'},observation_changes={'observation_id':'same.US'})
    entities=(Entity('Hanbit.KR','KR-v1','company','synthetic:KR',doc.KNOWN),Entity('Hanbit.US','US-v2','company','synthetic:US',doc.KNOWN))
    links=tuple(sorted((DocumentEntityLink(revision_ref(x[1].revision),e.entity_id,e.entity_version,'subject','synthetic:link',doc.KNOWN) for x,e in zip((first,second),entities)),key=lambda x:x.revision_ref.key))
    ctx=DocumentEntityContext(1,'synthetic','bilingual.context','v1',entities,links,())
    b=doc.batch((first,second),context=ctx,req=doc.request(expected_document_ids=('same-name.KR','same-name.US')))
    return DocumentSource(b,doc.catalog(),doc.rights())


def citations_all(src):
    from quantharbor.domain.market_data import record_hash
    b=src.bundle
    result=[]
    for claim in b.claims:
        original=next(o for o in b.originals if record_hash(o)==claim.revision.original_hash)
        result.append(d.Citation(d.ref('document',b.manifest.batch_id,b.manifest),
            d.ref('revision','revision:'+hash_record(claim.revision),claim.revision),
            d.ref('observation','observation:'+hash_record(claim.observation),claim.observation),d.ref('original',original.raw_sha256,original),
            d.ref('context',b.context.context_id,b.context),0,len(original.text.encode()),original.text))
    return tuple(result)


RUN_EVIDENCE={}


@lru_cache(maxsize=2)
def full_period_source(cadence):
    """실제 현금 원장: 경계100→중간110→종료121, 외부흐름/거래 없음.

    독립 기대값은 TWR0.21/PnL21/MDD0/turnover0/benchmark0.21. 제품 결과로 기대값을 만들지 않는다.
    시장자료를 사용하지 않는 USD 전체 계좌이며 시장권리 검증을 주장하지 않는다.
    """
    from quantharbor.adapters.synthetic_ledger import SyntheticLedger
    from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
    from quantharbor.application.valuation import build_snapshot
    from quantharbor.domain.ledger import CashLeg, LedgerBaseline, LedgerCompleteness, SyntheticLedgerSubmission
    from quantharbor.ports.research import ResearchPointInput
    bounds = {
        'weekly': ('2024-03-03T15:00:00Z', '2024-03-06T15:00:00Z', '2024-03-10T15:00:00Z'),
        'monthly': ('2024-02-29T15:00:00Z', '2024-03-15T15:00:00Z', '2024-03-31T15:00:00Z'),
    }
    times = bounds[cadence]
    base = flow_source().points[0].snapshot
    account = 'synthetic-account:ai-period-' + cadence
    store, snapshots = SyntheticLedger(), SyntheticSnapshotRepository()
    points = []
    for i, (at, amount) in enumerate(zip(times, ('100', '10', '11'))):
        kind = 'baseline' if i == 0 else 'dividend'
        leg = 'opening_equity' if i == 0 else 'dividend_income'
        submission = SyntheticLedgerSubmission(1, 'synthetic', account, 'ai-period', str(i), 1, None,
            'ai-period-v1', kind, at, 'original', None,
            (CashLeg('settled_cash', 'USD', amount, 'settlement'),
             CashLeg(leg, 'USD', '-' + amount, 'settlement')), (), ('synthetic:ai-period',),
            LedgerCompleteness(True, True, True), LedgerBaseline(True, True, 'entire_account') if i == 0 else None, (), None)
        receipt = store.append(submission, recorded_at=at)
        if receipt.status != 'accepted':
            raise AssertionError(receipt.reason)
        projection = store.replay(account, as_of=at, knowledge_cutoff=at)
        req = replace(base.valuation.request, account_ref=account, request_id='period-' + str(i),
            ledger_cursor=projection.ledger_cursor, as_of=at, knowledge_cutoff=at, evaluated_at=at)
        snap = build_snapshot(projection, req, (), base.valuation.policy, base.reconciliation_policy, snapshots)
        points.append(ResearchPointInput(snap, ()))
    events = tuple(store.state(account).events)
    from quantharbor.domain.research import known
    benchmark = FinancialSource(tuple(points), events, build_bound_performance(tuple(points), events))
    # 동일 합성 현금 경로를 명시 counterpart로 사용한다. 실제 시장 benchmark가 아니다.
    performance = build_bound_performance(tuple(points), events, benchmark_return=known('0.21'))
    return FinancialSource(tuple(points), events, performance, benchmark=benchmark)


def full_period_request(cadence, src=None):
    src = src or full_period_source(cadence)
    zone = synthetic_timezone('KR')
    zr = timezone_ref(zone)
    period = d.Period(cadence, src.points[0].snapshot.as_of, src.points[-1].snapshot.as_of, 'Asia/Seoul', zr, 1)
    at = '2024-04-01T00:00:00Z'
    return request((performance_ref(src), zr), role='report', purpose='ai_report',
        account_ref=src.points[0].snapshot.account_ref, required_outputs=('period',), period=period,
        as_of=at, knowledge_cutoff=at, evaluated_at=at, deadline='2024-04-01T00:01:00Z')
