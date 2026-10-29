"""고정 EX fixture. 실제 Q24/Q26 원본과 별도 broker manifest를 구성한다."""
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from quantharbor.adapters.synthetic_approval import FixturePrincipal,SyntheticAuthority
from quantharbor.adapters.synthetic_execution_broker import (SyntheticExecutionBroker,BrokerSnapshot,BrokerFact)
from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
from quantharbor.application.approval import ApprovalApplication,validate_source
from quantharbor.domain import approval as a
from quantharbor.domain import execution as d
from quantharbor.domain.target import ref as target_ref
from quantharbor.ports.approval import ApprovalSource
from quantharbor.ports.execution import ExecutionInputs
from synthetic_approval import Clock,policy as approval_policy
from synthetic_target import fixture,build

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT/'docs/contracts/execution-fixture-v1.json'
MANIFEST = json.loads(FIXTURE_PATH.read_bytes())
assert sha256(FIXTURE_PATH.read_bytes()).hexdigest()==d.FIXTURE_SHA
assert len(MANIFEST['cases'])==40
AT = '2024-03-08T14:31:10.000000Z'


def _correction_fact(identity,execution='e1',quantity='1',price='100',*,revision=1,predecessor=None,sequence=1,semantics='delta',fee='0',tax='0'):
    return BrokerFact(identity,'fill',semantics,execution,revision,predecessor,sequence,quantity,price,fee,tax,AT)

# Independent declarations: quantity/principal/cash are never computed from reducer output.
DELTA = (_correction_fact('delta',price='90'),_correction_fact('delta',quantity='2',price='95',revision=2,predecessor=1))
CUMULATIVE = (_correction_fact('c1','stream',price='90',semantics='cumulative'),
    _correction_fact('c2','stream',quantity='3',sequence=2,semantics='cumulative'),
    _correction_fact('c2','stream',quantity='2',sequence=2,semantics='cumulative',revision=2,predecessor=1))
MULTI = (_correction_fact('m1',price='90'),_correction_fact('m2','e2'),_correction_fact('m1',quantity='2',price='95',revision=2,predecessor=1))
COST = (_correction_fact('cost',fee='0.5',tax='0.25'),
    _correction_fact('cost',revision=2,predecessor=1,fee='1',tax='0.5'))
CORRECTION_MANIFESTS = {
 'delta':dict(holdings=('2','0'),cash=(('settled_cash','1000'),('unsettled_payable','-190')),
              capacity='1000',sellable=('0','0'),cutoff=3),
 'cumulative':dict(holdings=('2','0'),cash=(('settled_cash','1000'),('unsettled_payable','-190')),
              capacity='1000',sellable=('0','0'),cutoff=4),
 'multi':dict(holdings=('3','0'),cash=(('settled_cash','1000'),('unsettled_payable','-290')),
              capacity='1000',sellable=('0','0'),cutoff=4),
 'cost':dict(holdings=('1','0'),cash=(('settled_cash','998.5'),('unsettled_payable','-100')),
              capacity='998.5',sellable=('0','0'),cutoff=3,included=('cost:used',)),
}

CORRECTION_FACTS = {'delta':DELTA,'cumulative':CUMULATIVE,'multi':MULTI,'cost':COST}


def composition(*,obligations=False,available=None,response='accepted',facts=None,target_options=None,
                current_manifest=None,policy_changes=None,exposure_ceiling=None,broker_sellable=None):
    request,inputs = fixture(obligations=obligations,**(target_options or {}))
    if available=='900':
        inputs = replace(inputs,policy=replace(inputs.policy,currency_limits=tuple(
            replace(x,cash_floor='100') for x in inputs.policy.currency_limits)))
        request = replace(request,policy_ref=target_ref('policy',inputs.policy.policy_id,inputs.policy))
    if policy_changes is not None or exposure_ceiling is not None:
        policy = replace(inputs.policy,**(policy_changes or {}))
        if exposure_ceiling is not None:
            policy = replace(policy,exposure_limits=tuple(replace(x,maximum_amount=exposure_ceiling)
                for x in policy.exposure_limits))
        inputs = replace(inputs,policy=policy)
        request = replace(request,policy_ref=target_ref('policy',policy.policy_id,policy))
    target_repo = SyntheticTargetRepository()
    artifacts = build(request,inputs,target_repo)
    source = ApprovalSource(request,inputs,artifacts,target_repo)
    current = inputs
    statement = current.current.snapshot.reconciliation_details.statement
    snapshot = BrokerSnapshot(statement,current.facts.covered_scope,
        tuple(d.BrokerCash(x.currency,'600' if available=='600' else x.amount,()) for x in current.facts.cash_capacity_rows),
        tuple(d.BrokerQuantity(x.position,x.broker_sellable_quantity,()) for x in current.facts.sellability_rows),
        current.facts.source_as_of)
    if broker_sellable is not None:
        snapshot = replace(snapshot,sellable=tuple(d.BrokerQuantity(k,q,())
            for k,q in zip(snapshot.scope.positions,broker_sellable)))
    if facts is None:
        facts = (
            BrokerFact('fill-1','fill','delta','execution-1',1,None,1,'1','100','0','0',AT),
            BrokerFact('settlement-1','settlement','delta','execution-1',1,None,2,'1','100','0','0',AT),
            BrokerFact('cancel-remaining','cancelled_remaining','delta','cancel-1',1,None,3,'2','100','0','0',AT),
        )
    # Independent literal post EX06/07 statement; never copy a DB projection.
    from quantharbor.domain.ledger import CashBalance,PositionDelta,hash_record
    from quantharbor.domain.valuation import SyntheticAccountStatement
    ss = replace(statement.snapshot,statement_id='execution-fresh-statement',source_snapshot_id='execution-fresh-snapshot',
        source_as_of=AT,observed_at=AT,ingested_at=AT,
        holdings=(PositionDelta(*current.facts.covered_scope.positions[0].key,'1'),),cash=(CashBalance('settled_cash','USD','900'),))
    fresh_statement = replace(statement,snapshot=ss,source_snapshot_hash=hash_record(ss))
    component = 'obligation:'+hash_record(artifacts.candidates[0].body.terms)+':principal:used'
    fresh = BrokerSnapshot(fresh_statement,snapshot.scope,(d.BrokerCash('USD','900',(component,)),),
        tuple(d.BrokerQuantity(x.position,'1' if n==0 else '0',()) for n,x in enumerate(snapshot.sellable)),AT,3)
    if current_manifest is not None:
        fresh = literal_snapshot(snapshot, current_manifest,hash_record(artifacts.candidates[0].body.terms))
    broker = SyntheticExecutionBroker(source.request.account_ref,(snapshot,fresh),facts,response=response)
    query = broker.query()
    ep = d.SyntheticExecutionPolicy('q27-policy',1,'synthetic',request.account_ref,
        target_ref('policy',current.policy.policy_id,current.policy),request.evaluated_at,request.expires_at,'1',d.FIXTURE_REF)
    return source,ExecutionInputs(current,query,ep),broker


def literal_snapshot(initial, manifest,request_hash=None):
    """독립 수기 manifest만 소비한다. production 원장/예약 결과를 입력받지 않는다."""
    from quantharbor.domain.ledger import CashBalance, PositionDelta, hash_record
    ss = replace(initial.statement.snapshot,statement_id='literal-current-statement',
        source_snapshot_id='literal-current-snapshot',source_as_of=AT,observed_at=AT,ingested_at=AT,
        holdings=tuple(PositionDelta(*k.key,q) for k,q in zip(initial.scope.positions,manifest['holdings']) if q!='0'),
        cash=tuple(CashBalance(name,'USD',amount) for name,amount in manifest['cash']))
    statement = replace(initial.statement,snapshot=ss,source_snapshot_hash=hash_record(ss))
    return BrokerSnapshot(statement,initial.scope,
        (d.BrokerCash('USD',manifest['capacity'],tuple('obligation:'+request_hash+':'+x for x in manifest.get('included',()))),),
        tuple(d.BrokerQuantity(k,q,(),tuple(d.BrokerHoldReflection('obligation:'+request_hash+':quantity',amount)
            for amount in manifest.get('hold_reflections',())) if n==0 else ())
            for n,(k,q) in enumerate(zip(initial.scope.positions,manifest['sellable']))),
        AT,manifest['cutoff'])


def approval_record(source,index=0):
    """순수 위험 시험용 typed 승인. DB 승인의 대체물로 사용하지 않는다."""
    from synthetic_approval import Harness
    h=Harness()
    if source != h.source:
        # EX38 등은 별도 실제 source를 가진 simulation에서 생성한다.
        h.repo.replace_source(h.controller,source)
        h.source = source
    c=source.artifacts.candidates[index]
    h.candidate_ref=target_ref('candidate',c.candidate_id,c)
    return h.approve()[1]


class DatabaseHarness:
    """root actual DB runner만 인스턴스화한다. unit suite는 Docker를 실행하지 않는다."""
    def __init__(self,db,*,available=None,obligations=False,response='accepted',facts=None,target_options=None,
                 current_manifest=None,policy_changes=None,exposure_ceiling=None,broker_sellable=None):
        from quantharbor.adapters.postgres_execution import PostgresExecutionRepository
        self.clock=Clock()
        self.source,self.inputs,self.broker=composition(available=available,obligations=obligations,response=response,facts=facts,
            target_options=target_options,current_manifest=current_manifest,policy_changes=policy_changes,
            exposure_ceiling=exposure_ceiling,broker_sellable=broker_sellable)
        for e in self.source.inputs.events:
            result=db.append(e.body.submission,recorded_at=e.body.recorded_at)
            assert result.status=='accepted'
        account=self.source.request.account_ref
        self.authority=SyntheticAuthority((
            FixturePrincipal('execution-approver',account,'approver',('present','approve','deny','revoke','withdraw','admit','query','heartbeat','disconnect')),
            FixturePrincipal('execution-controller',account,'controller',('session','stop','resume','dispatch','withdraw','runtime','policy','heartbeat','disconnect','query')),
        ),clock=self.clock)
        self.repo=PostgresExecutionRepository(db,self.authority,self.source,approval_policy(self.source),self.inputs,self.broker,cancel_principals=('execution-controller',))
        self.app=ApprovalApplication(self.repo)
        self.approver=self.authority.issue_session('execution-approver')
        self.controller=self.authority.issue_session('execution-controller')
        rec=self.repo.reconcile(self.controller,self.inputs.query)
        assert rec.result=='matched',rec.unresolved
        self.app.control(self.controller,'resume')
        self.clock.at=AT

    def approved(self,index=0,*,label='approve'):
        c=self.source.artifacts.candidates[index]
        _,approval=self.app.present(self.approver,target_ref('candidate',c.candidate_id,c))
        challenge=self.app.challenge(self.approver,a.ref('approval',approval.approval_id,approval),action='approve',command_id=label)
        receipt=self.app.execute(self.approver,challenge)
        assert receipt.outcome=='applied',receipt.reason_code
        return self.repo.head(self.approver,approval.approval_id)

    def admission_challenge(self,approval,*,label='admit'):
        return self.app.challenge(self.approver,a.ref('approval',approval.approval_id,approval),action='admit',command_id=label)

    def admit(self,approval,*,label='admit'):
        challenge=self.admission_challenge(approval,label=label)
        receipt=self.app.execute(self.approver,challenge)
        assert receipt.outcome=='applied',receipt.reason_code
        return self.repo.head(self.approver,approval.approval_id)


def replacement_source(source,values,*,label):
    """새 Q24 원본을 실제로 재계산한다. 이전 consumed/claim은 수정하지 않는다."""
    request=replace(source.request,request_id=label,
        targets=tuple(replace(row,value=value) for row,value in zip(source.request.targets,values)))
    repository=SyntheticTargetRepository()
    return ApprovalSource(request,source.inputs,build(request,source.inputs,repository),repository)


def fresh_target_source(source,*,at,label='q27-fresh-request',values=('1','2'),inputs=None):
    """실제 새 Q24 요청을 재현한다. 복구 검증에서 TTL 연장에 쓰지 않는다."""
    current=source.inputs if inputs is None else inputs
    snap=current.current.snapshot
    request=replace(source.request,request_id=label,evaluated_at=at,
        as_of=snap.as_of,knowledge_cutoff=snap.knowledge_cutoff,expires_at=a.plus(at,30),
        snapshot_ref=target_ref('snapshot',snap.snapshot_id,snap),
        policy_ref=target_ref('policy',current.policy.policy_id,current.policy),
        targets=tuple(replace(row,value=value) for row,value in zip(source.request.targets,values)))
    repository=SyntheticTargetRepository()
    artifacts=build(request,current,repository)
    assert artifacts.plan.body.status=='eligible',artifacts.result.body
    fresh=ApprovalSource(request,current,artifacts,repository)
    for candidate in artifacts.candidates:
        validate_source(fresh,target_ref('candidate',candidate.candidate_id,candidate),at=at,
            generation=request.authority_generation)
    return fresh
