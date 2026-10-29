"""Q25 닫힌 합성 소비 계약. 서술의 의미적 진실/실제 모델 품질 보증이 아니다."""
from dataclasses import dataclass, fields, asdict
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
import json

from .primitives import ContractError, currency, decimal_string, identifier, utc_instant
from .ledger import digest
from .valuation import PositionKey

CANONICAL = 'qh-canonical-json-v1'
MAX_INT = 2**63 - 1
ROLES = ('collector', 'study', 'strategy', 'portfolio', 'risk', 'report')
QUERIES = ('document_view', 'hypothesis_view', 'snapshot_view', 'research_view', 'candidate_view')
ROLE_QUERIES = MappingProxyType(dict(zip(ROLES, (
    ('document_view',), ('document_view', 'hypothesis_view'),
    ('document_view', 'hypothesis_view', 'research_view'),
    ('snapshot_view', 'research_view', 'candidate_view'), QUERIES, QUERIES))))
KINDS = ('document', 'original', 'revision', 'observation', 'context', 'snapshot', 'event',
    'performance', 'experiment', 'candidate', 'plan', 'rights', 'policy', 'strategy', 'timezone',
    'request', 'result', 'review', 'hypothesis', 'budget_policy', 'attempt', 'response')
SELECTORS = ('snapshot.nav', 'snapshot.economic_cash', 'snapshot.holding_quantity',
    'performance.twr', 'performance.amount_pnl', 'performance.observed_mdd',
    'performance.gross_turnover', 'performance.fees', 'performance.taxes', 'performance.slippage',
    'performance.benchmark_return', 'candidate.quantity', 'candidate.limit_price',
    'candidate.cost_bound', 'candidate.maximum_burden')
REASONS = ('schema', 'identity', 'citation', 'numeric', 'unit', 'missing_source', 'conflict',
    'unknown_metric', 'proof_incomplete', 'rights_denied', 'future_source', 'query_denied',
    'budget', 'capacity', 'unknown_charge', 'usage_overrun', 'deadline', 'client_failure',
    'truncated', 'expired', 'dependency_changed', 'retracted', 'superseded', 'self_review',
    'actual_disabled', 'retry_disabled', 'period_mismatch', 'intervention_unknown', 'inference_unverified')
STATUSES = ('complete', 'partial', 'invalid', 'blocked', 'failed')


def enum(*choices):
    def check(v):
        if type(v) is not str or v not in choices:
            raise ContractError()
        return v
    return check


def text(v):
    if type(v) is not str or not v or len(v.encode('utf-8', errors='surrogatepass')) > 2048 or any(0xD800 <= ord(c) <= 0xDFFF for c in v):
        raise ContractError()
    return v


def count(v):
    if type(v) is not int or not 0 <= v <= MAX_INT:
        raise ContractError()
    return v


def bounded(maximum):
    def check(v):
        if count(v) > maximum:
            raise ContractError()
        return v
    return check


def absent(v):
    if v is not None:
        raise ContractError()
    return None


def hashed(v):
    digest(v)
    return v


def opt(rule):
    return ('optional', rule)


def seq(rule, maximum=128):
    return ('sequence', rule, maximum)


def checked(rule, v):
    if type(rule) is tuple:
        if rule[0] == 'optional':
            return None if v is None else checked(rule[1], v)
        if type(v) is not tuple or len(v) > rule[2]:
            raise ContractError()
        return tuple(checked(rule[1], x) for x in v)
    if isinstance(rule, type):
        if type(v) is not rule:
            raise ContractError()
        return rule(**{f.name: getattr(v, f.name) for f in fields(rule)})
    return rule(v)


class Closed:
    __slots__ = ()

    def __post_init__(self):
        for f in fields(self):
            object.__setattr__(self, f.name, checked(SPECS[type(self)][f.name], getattr(self, f.name)))
        validate(self)


@dataclass(frozen=True, slots=True)
class AIRef(Closed):
    kind: str
    id: str
    version: int
    canonicalization_version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Usage(Closed):
    input_tokens: int
    output_tokens: int
    calls: int
    charge: int


@dataclass(frozen=True, slots=True)
class RetryPolicy(Closed):
    max_retries: int
    retryable_reasons: tuple[str, ...]
    backoff_ms: int
    max_escalations: int
    transitions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AIBudgetPolicy(Closed):
    schema_version: int
    environment: str
    policy_id: str
    version: int
    budget_scope: str
    window_start: str
    window_end: str
    charge_unit: str
    pricing_version: str
    input_rate: int
    output_rate: int
    fixed_call_cost: int
    window_caps: Usage
    role_caps: Usage
    request_caps: Usage
    attempt_caps: Usage
    concurrency_cap: int
    retry_policy: RetryPolicy


@dataclass(frozen=True, slots=True)
class Period(Closed):
    cadence: str
    start: str
    end: str
    timezone: str
    timezone_ref: AIRef
    version: int


@dataclass(frozen=True, slots=True)
class ResearchRequest(Closed):
    schema_version: int
    environment: str
    request_id: str
    run_id: str
    idempotency_key: str
    role: str
    purpose: str
    account_ref: str | None
    scope: tuple[PositionKey, ...]
    as_of: str
    knowledge_cutoff: str
    evaluated_at: str
    deadline: str
    locale: str
    source_refs: tuple[AIRef, ...]
    required_outputs: tuple[str, ...]
    allowed_queries: tuple[str, ...]
    procedure_version: str
    instruction_version: str
    tool_schema_version: str
    client_profile: str
    budget_policy_ref: AIRef
    caps: Usage
    period: Period | None
    review_subject_ref: AIRef | None


@dataclass(frozen=True, slots=True)
class Citation(Closed):
    manifest_ref: AIRef
    revision_ref: AIRef
    observation_ref: AIRef
    original_ref: AIRef
    context_ref: AIRef
    start_utf8: int
    end_utf8: int
    exact_quote: str


@dataclass(frozen=True, slots=True)
class NumericClaim(Closed):
    claim_id: str
    source_ref: AIRef
    selector: str
    position: PositionKey | None
    period: Period | None
    value: str
    unit: str
    currency: str | None
    as_of: str


@dataclass(frozen=True, slots=True)
class NarrativeClaim(Closed):
    claim_id: str
    label: str
    text: str
    citation_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ClientIdentity(Closed):
    invocation_id: str
    evaluation_kind: str
    model_id: None


@dataclass(frozen=True, slots=True)
class Check(Closed):
    code: str
    subject_ref: AIRef | None
    expected: str | None
    observed: str | None
    outcome: str


@dataclass(frozen=True, slots=True)
class Query(Closed):
    name: str
    source_ref: AIRef


@dataclass(frozen=True, slots=True)
class QueryReceipt(Closed):
    query: Query
    resolved_refs: tuple[AIRef, ...]
    checked_at: str


@dataclass(frozen=True, slots=True)
class ModelResponse(Closed):
    identity: ClientIdentity
    finish_reason: str
    numeric_claims: tuple[NumericClaim, ...]
    narrative_claims: tuple[NarrativeClaim, ...]
    citations: tuple[Citation, ...]
    queries: tuple[Query, ...]
    assumptions: tuple[str, ...]
    counterevidence: tuple[str, ...]
    unknowns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PeriodReview(Closed):
    period: Period
    account_ref: str
    base_currency: str
    source_refs: tuple[AIRef, ...]
    performance_ref: AIRef | None
    benchmark_ref: AIRef | None
    metrics: tuple[Check, ...]
    research_changes: tuple[AIRef, ...]
    strategy_changes: tuple[AIRef, ...]
    intervention_unknowns: tuple[str, ...]
    supersedes_ref: AIRef | None
    event_boundary: str


@dataclass(frozen=True, slots=True)
class ResearchResult(Closed):
    schema_version: int
    environment: str
    result_id: str
    request_ref: AIRef
    input_manifest: tuple[AIRef, ...]
    client_identity: ClientIdentity
    procedure_version: str
    instruction_version: str
    tool_schema_version: str
    started_at: str
    finished_at: str
    response: ModelResponse | None
    query_receipts: tuple[QueryReceipt, ...]
    budget_attempt_refs: tuple[AIRef, ...]
    checks: tuple[Check, ...]
    status: str
    reasons: tuple[str, ...]
    period_review: PeriodReview | None


@dataclass(frozen=True, slots=True)
class ResearchReview(Closed):
    schema_version: int
    environment: str
    review_id: str
    review_request_ref: AIRef
    exact_result_ref: AIRef
    reviewer_identity: ClientIdentity
    reviewed_at: str
    dependency_refs: tuple[AIRef, ...]
    checks: tuple[Check, ...]
    findings: tuple[str, ...]
    verdict: str
    candidate_ref: AIRef | None


@dataclass(frozen=True, slots=True)
class Hypothesis(Closed):
    schema_version: int
    environment: str
    hypothesis_id: str
    origin_result_ref: AIRef
    proposition: str
    supporting_claim_refs: tuple[str, ...]
    opposing_claim_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    falsification_condition: str
    experiment_proposal: str | None
    dependencies: tuple[AIRef, ...]
    created_at: str
    expires_at: str
    assessment: str
    supersedes_ref: AIRef | None
    retracts_ref: AIRef | None


@dataclass(frozen=True, slots=True)
class AIBudgetAttempt(Closed):
    schema_version: int
    environment: str
    attempt_id: str
    request_ref: AIRef
    role: str
    sequence: int
    client_profile: str
    policy_ref: AIRef
    reserved_usage: Usage
    state: str
    reserved_at: str
    dispatch_at: str | None
    settled_at: str | None
    actual_usage: Usage | None
    reasons: tuple[str, ...]


SPECS = {}
base = dict(schema_version=bounded(1), environment=enum('synthetic'))
SPECS[AIRef] = dict(kind=enum(*KINDS), id=identifier, version=bounded(1), canonicalization_version=enum(CANONICAL), sha256=hashed)
SPECS[Usage] = {n: count for n in ('input_tokens', 'output_tokens', 'calls', 'charge')}
SPECS[RetryPolicy] = dict(max_retries=count, retryable_reasons=seq(enum(*REASONS),64), backoff_ms=count, max_escalations=count, transitions=seq(text,64))
SPECS[AIBudgetPolicy] = base | dict(policy_id=identifier, version=count, budget_scope=identifier, window_start=utc_instant, window_end=utc_instant,
    charge_unit=enum('synthetic_microcredit'), pricing_version=enum('synthetic-unit-v1'), input_rate=count)
SPECS[AIBudgetPolicy].update(input_rate=count, output_rate=count, fixed_call_cost=count, window_caps=Usage, role_caps=Usage,
    request_caps=Usage, attempt_caps=Usage, concurrency_cap=bounded(2), retry_policy=RetryPolicy)
SPECS[Period] = dict(cadence=enum('weekly','monthly'), start=utc_instant, end=utc_instant, timezone=enum('Asia/Seoul'), timezone_ref=AIRef, version=bounded(1))
SPECS[ResearchRequest] = base | dict(request_id=identifier, run_id=identifier, idempotency_key=identifier, role=enum(*ROLES),
    purpose=enum('ai_research','ai_report'), account_ref=opt(identifier), scope=seq(PositionKey), as_of=utc_instant,
    knowledge_cutoff=utc_instant, evaluated_at=utc_instant, deadline=utc_instant, locale=enum('ko-KR','en-US'), source_refs=seq(AIRef),
    required_outputs=seq(enum('document','numeric','narrative','period'), 4), allowed_queries=seq(enum(*QUERIES),5),
    procedure_version=identifier, instruction_version=identifier, tool_schema_version=identifier, client_profile=enum('synthetic','actual'),
    budget_policy_ref=AIRef, caps=Usage, period=opt(Period), review_subject_ref=opt(AIRef))
SPECS[Citation] = {n: AIRef for n in ('manifest_ref','revision_ref','observation_ref','original_ref','context_ref')}
SPECS[Citation].update(start_utf8=bounded(8192),end_utf8=bounded(8192),exact_quote=text)
SPECS[NumericClaim] = dict(claim_id=identifier, source_ref=AIRef, selector=enum(*SELECTORS), position=opt(PositionKey), period=opt(Period),
    value=decimal_string, unit=enum('currency','ratio','share'), currency=opt(currency), as_of=utc_instant)
SPECS[NarrativeClaim] = dict(claim_id=identifier,label=enum('quote','inference','hypothesis'), text=text,citation_indices=seq(bounded(63),64))
SPECS[ClientIdentity] = dict(invocation_id=identifier,evaluation_kind=enum('synthetic'),model_id=absent)
SPECS[Check] = dict(code=enum(*REASONS),subject_ref=opt(AIRef),expected=opt(text),observed=opt(text),outcome=enum('pass','fail','unknown'))
SPECS[Query] = dict(name=enum(*QUERIES),source_ref=AIRef)
SPECS[QueryReceipt] = dict(query=Query,resolved_refs=seq(AIRef),checked_at=utc_instant)
SPECS[ModelResponse] = dict(identity=ClientIdentity,finish_reason=enum('stop','length'),numeric_claims=seq(NumericClaim,32),
    narrative_claims=seq(NarrativeClaim,32),citations=seq(Citation,64),queries=seq(Query,16),assumptions=seq(text,64),counterevidence=seq(text,64),unknowns=seq(text,64))
SPECS[PeriodReview] = dict(period=Period,account_ref=identifier,base_currency=currency,source_refs=seq(AIRef),performance_ref=opt(AIRef),
    benchmark_ref=opt(AIRef),metrics=seq(Check,64),research_changes=seq(AIRef),strategy_changes=seq(AIRef),intervention_unknowns=seq(text,64),
    supersedes_ref=opt(AIRef),event_boundary=enum('display_[start,end);performance_(start,end]'))
SPECS[ResearchResult] = base | dict(result_id=identifier,request_ref=AIRef,input_manifest=seq(AIRef),client_identity=ClientIdentity,
    procedure_version=identifier,instruction_version=identifier,tool_schema_version=identifier,started_at=utc_instant,finished_at=utc_instant,
    response=opt(ModelResponse),query_receipts=seq(QueryReceipt,16),budget_attempt_refs=seq(AIRef,4),checks=seq(Check,64),status=enum(*STATUSES),reasons=seq(enum(*REASONS),64),period_review=opt(PeriodReview))
SPECS[ResearchReview] = base | dict(review_id=identifier,review_request_ref=AIRef,exact_result_ref=AIRef,reviewer_identity=ClientIdentity,
    reviewed_at=utc_instant,dependency_refs=seq(AIRef),checks=seq(Check,64),findings=seq(enum(*REASONS),64),verdict=enum('accepted','changes_required','blocked'),candidate_ref=opt(AIRef))
SPECS[Hypothesis] = base | dict(hypothesis_id=identifier,origin_result_ref=AIRef,proposition=text,supporting_claim_refs=seq(identifier,32),
    opposing_claim_refs=seq(identifier,32),assumptions=seq(text,64),falsification_condition=text,experiment_proposal=opt(text),dependencies=seq(AIRef),
    created_at=utc_instant,expires_at=utc_instant,assessment=enum('proposed','supported','refuted','inconclusive'),supersedes_ref=opt(AIRef),retracts_ref=opt(AIRef))
SPECS[AIBudgetAttempt] = base | dict(attempt_id=identifier,request_ref=AIRef,role=enum(*ROLES),sequence=bounded(4),client_profile=enum('synthetic'),policy_ref=AIRef,
    reserved_usage=Usage,state=enum('reserved','dispatched','settled','unknown_charge','cancelled_before_dispatch'),reserved_at=utc_instant,
    dispatch_at=opt(utc_instant),settled_at=opt(utc_instant),actual_usage=opt(Usage),reasons=seq(enum(*REASONS),64))


def validate(v):
    if type(v) in (ResearchRequest, ResearchResult, ResearchReview, Hypothesis, AIBudgetPolicy, AIBudgetAttempt, ModelResponse, PeriodReview):
        wrapper=dict(schema_name=type(v).__name__,schema_version=1,environment='synthetic',payload=asdict(v))
        if len(json.dumps(wrapper,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode())>65536:
            raise ContractError()
    if hasattr(v,'schema_version') and v.schema_version != 1 or type(v) in (AIRef,Period) and v.version != 1:
        raise ContractError()
    if type(v) is AIBudgetPolicy:
        if v.version<1 or v.window_start >= v.window_end or v.concurrency_cap < 1 or (v.input_rate,v.output_rate,v.fixed_call_cost) != (1,2,1):
            raise ContractError()
        hard = (8192,2048,1,12289)
        if any(x > y for x,y in zip(usage_values(v.attempt_caps), hard)) or any(x > y for x,y in zip(usage_values(v.request_caps),(32768,8192,4,49156))) or any(x > y for x,y in zip(usage_values(v.window_caps),(131072,32768,16,196624))):
            raise ContractError()
        if any(x > y for x,y in zip(usage_values(v.role_caps),usage_values(v.request_caps))):
            raise ContractError()
    if type(v) is ResearchRequest:
        if not v.as_of <= v.knowledge_cutoff <= v.evaluated_at < v.deadline or datetime.fromisoformat(v.deadline)-datetime.fromisoformat(v.evaluated_at)>timedelta(seconds=60):
            raise ContractError()
        if v.budget_policy_ref.kind != 'budget_policy' or len(set(v.source_refs)) != len(v.source_refs) or len(set(x.key for x in v.scope)) != len(v.scope):
            raise ContractError()
        if ('period' in v.required_outputs) != (v.period is not None) or (v.role=='report') != (v.purpose=='ai_report'):
            raise ContractError()
    if type(v) is Citation:
        if v.start_utf8 >= v.end_utf8 or v.end_utf8-v.start_utf8 != len(v.exact_quote.encode()):
            raise ContractError()
        if tuple(getattr(v,n).kind for n in ('manifest_ref','revision_ref','observation_ref','original_ref','context_ref')) != ('document','revision','observation','original','context'):
            raise ContractError()
    if type(v) is Period:
        if v.timezone_ref.kind != 'timezone':
            raise ContractError()
        # Q16 ref를 앱에서 해소한다. v1은 Seoul의 현대 UTC+09:00 경계만 지원.
        start=datetime.fromisoformat(v.start).astimezone(timezone(timedelta(hours=9)))
        end=datetime.fromisoformat(v.end).astimezone(timezone(timedelta(hours=9)))
        if start.year < 2000 or (start.hour,start.minute,start.second,start.microsecond)!=(0,0,0,0):
            raise ContractError()
        if v.cadence=='weekly':
            valid=start.weekday()==0 and end-start==timedelta(days=7)
        else:
            next_start=start.replace(year=start.year+1,month=1,day=1) if start.month==12 else start.replace(month=start.month+1,day=1)
            valid=start.day==1 and end==next_start
        if not valid:
            raise ContractError()
    if type(v) is ModelResponse:
        ids=tuple(x.claim_id for x in (*v.numeric_claims,*v.narrative_claims))
        if len(set(ids))!=len(ids) or len(ids)>32 or any(i>=len(v.citations) for c in v.narrative_claims for i in c.citation_indices):
            raise ContractError()
        if any(c.label=='quote' and (len(c.citation_indices)!=1 or c.text!=v.citations[c.citation_indices[0]].exact_quote) for c in v.narrative_claims):
            raise ContractError()
    if type(v) is ResearchResult:
        if v.request_ref.kind!='request' or v.started_at>v.finished_at or (v.response is not None and v.client_identity!=v.response.identity):
            raise ContractError()
        if (v.status=='complete' and (v.reasons or v.response is None or v.response.finish_reason!='stop' or any(c.outcome!='pass' for c in v.checks))) or (v.status!='complete' and not v.reasons):
            raise ContractError()
        if v.status=='complete' and v.response.queries and tuple(q.query for q in v.query_receipts[-len(v.response.queries):])!=v.response.queries:
            raise ContractError()
        if any(r.kind!='attempt' for r in v.budget_attempt_refs):
            raise ContractError()
    if type(v) is ResearchReview:
        if v.exact_result_ref.kind!='result' or v.review_request_ref.kind!='request' or (v.verdict=='accepted' and (v.findings or any(c.outcome!='pass' for c in v.checks))):
            raise ContractError()
    if type(v) is Hypothesis:
        if v.origin_result_ref.kind!='result' or v.created_at>=v.expires_at or not v.dependencies or (v.retracts_ref and v.supersedes_ref) or any(r.kind not in ('document','original','revision','observation','context','snapshot','event','performance','candidate','plan','rights','policy','strategy','timezone') for r in v.dependencies):
            raise ContractError()
    if type(v) is AIBudgetAttempt:
        if v.sequence<1 or v.request_ref.kind!='request' or v.policy_ref.kind!='budget_policy' or v.reserved_usage.calls!=1:
            raise ContractError()
        if (v.state in ('dispatched','settled','unknown_charge')) != (v.dispatch_at is not None) or (v.state=='settled') != (v.actual_usage is not None) or (v.state in ('settled','unknown_charge','cancelled_before_dispatch')) != (v.settled_at is not None):
            raise ContractError()
        if v.dispatch_at and v.dispatch_at<v.reserved_at or v.settled_at and v.settled_at<(v.dispatch_at or v.reserved_at):
            raise ContractError()


def usage_values(v):
    return (v.input_tokens,v.output_tokens,v.calls,v.charge)


def priced(input_tokens,output_tokens,calls=1):
    return Usage(input_tokens,output_tokens,calls,input_tokens+2*output_tokens+calls)


def encoded(obj):
    from .serialization import CanonicalPayload, canonical_bytes
    return canonical_bytes(CanonicalPayload(type(obj).__name__,1,'synthetic',obj))


def ref(kind,id,obj):
    from .serialization import CanonicalPayload, canonical_hash
    return AIRef(kind,id,1,CANONICAL,canonical_hash(CanonicalPayload(type(obj).__name__,1,'synthetic',obj)))


# serializer용 닫힌 중첩 표. 임의 dict/path 복원 없음.
NESTED = {}
for cls,spec in SPECS.items():
    nested={}
    for name,rule in spec.items():
        if isinstance(rule,type):
            nested[name]=rule
        elif type(rule) is tuple:
            if rule[0]=='optional' and isinstance(rule[1],type):
                nested[name]=(rule[1],None)
            elif rule[0]=='sequence':
                nested[name]=(rule[1] if isinstance(rule[1],type) else str,)
    NESTED[cls]=nested
