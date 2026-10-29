"""Q27 금융 경제 시험. 실제 Q20 reducer 사용, PostgreSQL/Docker 증명과 구분한다."""
from dataclasses import asdict,replace
from hashlib import sha256
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from quantharbor.adapters.execution_uow import ExecutionUnitOfWork,MAX_FRAME
from quantharbor.adapters.postgres_execution import PostgresExecutionRepository
from quantharbor.adapters.postgres_ledger import PostgresLedger
from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.adapters.synthetic_execution_broker import BrokerFact
from quantharbor.application.execution import build_current_inputs,current_risk,remaining_order
from quantharbor.domain import execution as d
from quantharbor.domain.ledger import hash_record
from quantharbor.domain.serialization import CanonicalPayload,parse_payload
from quantharbor.domain.valuation import number
from synthetic_execution import composition,approval_record,AT
from test_execution_broker import request


def fact(identity,execution='e1',quantity='1',price='100',*,revision=1,predecessor=None,sequence=1,
         semantics='delta',kind='fill',fee='0',tax='0'):
    return BrokerFact(identity,kind,semantics,execution,revision,predecessor,sequence,quantity,price,fee,tax,AT)


class LedgerParticipation:
    """Unit-only same reducer participant; deliberately has no SQL/process emulation."""
    def __init__(self,source):
        self.ledger=SyntheticLedger()
        self.inbox=[]
        for e in source.inputs.events:
            assert self.ledger.append(e.body.submission,recorded_at=e.body.recorded_at).status=='accepted'

    def call(self,function,*args):
        if function=='execution_event':
            self.inbox.append(args[1]);return True
        assert function=='execution_ledger'
        account,operation,payload,at=args
        if operation=='append':
            sub=parse_payload(json.dumps(dict(schema_name='SyntheticLedgerSubmission',schema_version=1,
                environment='synthetic',payload=payload))).payload
            return asdict(self.ledger.append(sub,recorded_at=at))
        if operation=='events': return [asdict(e) for e in self.ledger.state(account).events]
        assert operation=='replay'
        return asdict(self.ledger.replay(account,as_of=payload or at,knowledge_cutoff=at))


class FinancialHarness:
    def __init__(self,facts,*,source=None,inputs=None,broker=None,target_options=None):
        if source is None:
            source,inputs,broker=composition(facts=facts,target_options=target_options,available="900")
        self.source,self.inputs,self.broker=source,inputs,broker
        self.approval=approval_record(source)
        self.attempt,self.intent=request(source,self.approval,broker)
        self.receipt=broker.handoff(self.attempt,self.intent)
        self.uow=LedgerParticipation(source)
        repo=self.repo=object.__new__(PostgresExecutionRepository)
        repo._broker,repo._account,repo._inputs,repo._source=broker,self.intent.account_ref,inputs,source
        repo._uow=self.uow
        repo._now=lambda:AT
        repo._stage=lambda label:None
        repo._state={'version':0,'events':{},'execution_records':{},'intents':{self.intent.intent_id:self.intent},
            'outbox':{},'attempts':{self.attempt.attempt_id:self.attempt},'unknown_costs':{},'ledger_mapping':{},
            'reservations':{},'mode':'running','generation':self.intent.generation,'fence':self.intent.fence,'reconciliation':None}
        repo._commit=lambda state,**kw:setattr(repo,'_state',state)
        for component,dimension,amount in (('principal','cash',self.intent.terms.principal_bound),
            ('cost','cash',self.intent.terms.cost_bound),('quantity','quantity',self.intent.terms.quantity if self.intent.terms.side=='sell' else '0'),
            ('risk','risk',str(number(self.intent.terms.quantity)*number(self.intent.terms.limit_price)+number(self.intent.terms.cost_bound)))):
            repo._state['reservations'][component]=d.ReservationSlice(component,self.intent.intent_id,
                'obligation:'+self.intent.request_hash+':'+component,component,dimension,'share' if dimension=='quantity' else 'USD',
                AT,'2024-03-09T00:00:00Z',amount,amount,'0','0','0','0',inputs.query.as_of,())

    def event(self,index): return self.broker.issue_event(self.receipt,index)
    def receive(self,index): return self.repo._receive(self.event(index))
    def projection(self): return self.uow.ledger.replay(self.intent.account_ref,as_of=AT,knowledge_cutoff=AT)
    def cash(self,account): return next((x.amount for x in self.projection().cash_balances if x.account==account),'0')
    def reserve(self,component): return self.repo._state['reservations'][component]
    def conserved(self):
        return all(number(r.bound)==number(r.held)+number(r.used)+number(r.released) for r in self.repo._state['reservations'].values())


class ExecutionFinancialTests(unittest.TestCase):
    def test_EX39_multi_price_and_delta_revision_literal_principal290(self):
        h=FinancialHarness((fact('first',price='90'),fact('second','e2',price='100'),
            fact('first',quantity='2',price='95',revision=2,predecessor=1),fact('late','e3')))
        self.assertEqual((h.receive(0),h.receive(1)),('applied','applied'))
        self.assertEqual((h.cash('unsettled_payable'),h.reserve('principal').used,h.reserve('principal').held),('-190','190','110'))
        remaining=remaining_order(h.repo._state['intents']['intent-1'],tuple(h.repo._state['reservations'].values()))
        self.assertEqual((remaining.quantity,remaining.cost_bound,remaining.maximum_burden),('1','2','102'))
        self.assertEqual(h.receive(2),'applied')
        self.assertEqual((h.cash('unsettled_payable'),h.projection().holdings[0].amount,h.reserve('principal').used,h.reserve('principal').held),('-290','3','290','10'))
        self.assertTrue(h.conserved())
        before=h.projection()
        self.assertEqual(h.receive(2),'duplicate')
        self.assertEqual(h.projection(),before)
        self.assertEqual(h.receive(3),'quarantined')
        self.assertEqual(h.projection(),before)
        self.assertEqual(h.repo._state['mode'],'faulted')

    def test_EX22_predecessor_retained_then_explicit_reprocess_old_revision_no_regression(self):
        h=FinancialHarness((fact('revision',quantity='2',revision=2,predecessor=1),fact('revision'),
            fact('old-other-envelope',quantity='1')))
        self.assertEqual(h.receive(0),'quarantined')
        self.assertEqual(h.cash('unsettled_payable'),'0')
        self.assertEqual(h.receive(1),'applied')
        self.assertEqual(PostgresExecutionRepository.reprocess.__wrapped__(h.repo,h.event(0)),'applied')
        self.assertEqual((h.cash('unsettled_payable'),h.projection().holdings[0].amount),('-200','2'))
        before=h.projection()
        self.assertEqual(h.receive(2),'quarantined')
        self.assertEqual(h.projection(),before)
        self.assertEqual(len(h.repo._state['events']),3)

    def test_EX21_cumulative_increments_multiple_prices_and_latest_correction(self):
        h=FinancialHarness((fact('c1','stream',price='90',semantics='cumulative'),
            fact('c2','stream',quantity='3',sequence=2,semantics='cumulative'),
            fact('c2','stream',quantity='2',sequence=2,semantics='cumulative',revision=2,predecessor=1)))
        self.assertEqual((h.receive(0),h.receive(1)),('applied','applied'))
        self.assertEqual((h.cash('unsettled_payable'),h.projection().holdings[0].amount),('-290','3'))
        self.assertEqual(h.receive(2),'applied')
        self.assertEqual((h.cash('unsettled_payable'),h.projection().holdings[0].amount),('-190','2'))
        self.assertTrue(h.conserved())

    def test_EX21_out_of_order_cumulative_sequence_explicit_reprocess(self):
        h=FinancialHarness((fact('c2','stream',quantity='3',sequence=2,semantics='cumulative'),
            fact('c1','stream',semantics='cumulative')))
        self.assertEqual(h.receive(0),'quarantined')
        self.assertEqual(h.receive(1),'applied')
        self.assertEqual(PostgresExecutionRepository.reprocess.__wrapped__(h.repo,h.event(0)),'applied')
        self.assertEqual((h.cash('unsettled_payable'),h.projection().holdings[0].amount),('-300','3'))

    def test_EX26_unknown_cost_complete_revision_nonzero_fee_tax_settlement_once(self):
        h=FinancialHarness((fact('u',fee=None,tax=None),fact('u',revision=2,predecessor=1,fee='1',tax='0.5'),
            fact('settle',kind='settlement')))
        self.assertEqual(h.receive(0),'observed_incomplete')
        i=h.repo._state['intents']['intent-1']
        self.assertEqual((i.observed_quantity,i.confirmed_quantity,i.accounting),('1','0','incomplete'))
        self.assertEqual((h.cash('unsettled_payable'),h.reserve('principal').used,h.reserve('cost').held),('0','100','2'))
        self.assertEqual(len(h.uow.ledger.state(h.intent.account_ref).events),1)
        self.assertEqual(h.receive(1),'applied')
        self.assertEqual((h.cash('unsettled_payable'),h.cash('settled_cash'),h.cash('fee_expense'),h.cash('tax_expense')),('-100','998.5','1','0.5'))
        self.assertEqual((h.reserve('cost').held,h.reserve('cost').used,h.reserve('cost').settled),('0.5','1.5','1.5'))
        self.assertEqual(h.receive(2),'applied')
        self.assertEqual((h.cash('settled_cash'),h.reserve('principal').settled),('898.5','100'))
        before=h.projection()
        self.assertEqual(h.receive(1),'duplicate')
        self.assertEqual(h.receive(2),'duplicate')
        self.assertEqual(h.projection(),before)
        self.assertTrue(h.conserved())

    def test_EX26_excess_cost_preserved_with_actual_ledger_and_block(self):
        h=FinancialHarness((fact('expensive',fee='2',tax='1'),))
        self.assertEqual(h.receive(0),'quarantined')
        self.assertEqual((h.cash('fee_expense'),h.cash('tax_expense'),h.cash('settled_cash')),('2','1','997'))
        self.assertEqual(h.repo._state['financial_excess']['intent-1']['cost'],'3')
        self.assertEqual(h.repo._state['intents']['intent-1'].accounting,'incomplete')
        self.assertTrue(h.conserved())

    def test_EX23_overfill_collision_and_Q20_quarantine_preserve_evidence(self):
        h=FinancialHarness((fact('same'),fact('same',price='99'),fact('over','e2',quantity='4'),
            fact('bad-effective',revision=2,predecessor=1)))
        self.assertEqual(h.receive(0),'applied')
        before=h.projection()
        self.assertEqual(h.receive(1),'quarantined')
        self.assertEqual(h.receive(2),'quarantined')
        self.assertEqual(h.projection(),before)
        self.assertEqual(len(h.repo._state['events']),3)
        self.assertEqual(h.repo._state['intents']['intent-1'].observed_quantity,'4')

    def test_EX26_settled_trade_correction_retains_dependency_and_halts(self):
        h=FinancialHarness((fact('t'),fact('s',kind='settlement'),fact('t',price='99',revision=2,predecessor=1)))
        self.assertEqual((h.receive(0),h.receive(1)),('applied','applied'))
        self.assertEqual(h.receive(2),'quarantined')
        self.assertIn('correction_consequences_unresolved',h.projection().reason_codes)
        self.assertEqual(h.reserve('principal').settled,'100')
        self.assertEqual(h.repo._state['intents']['intent-1'].accounting,'incomplete')
        self.assertEqual(len(h.uow.ledger.state(h.intent.account_ref).events),5)

    def test_EX09_EX10_sell_settlement_receivable_does_not_raise_capacity(self):
        h=FinancialHarness((fact('sale'),fact('s',kind='settlement')),
            target_options={'holdings':('3','0'),'targets':('0',None)})
        self.assertEqual(h.intent.terms.side,'sell')
        self.assertEqual(h.receive(0),'applied')
        self.assertEqual((h.cash('settled_cash'),h.cash('unsettled_receivable'),h.reserve('quantity').held,h.reserve('quantity').used),('1000','100','2','1'))
        self.assertEqual(h.receive(1),'applied')
        self.assertEqual((h.cash('settled_cash'),h.cash('unsettled_receivable')),('1100','0'))
        self.assertEqual(h.inputs.query.cash[0].amount,'1000')
        self.assertTrue(h.conserved())

    def test_EX08_actual_event_inputs_fresh_query_A598_and_next_candidate_risk(self):
        h=FinancialHarness((fact('f','execution-1'),fact('s','execution-1',kind='settlement')),
            target_options=None)
        self.assertEqual((h.receive(0),h.receive(1)),('applied','applied'))
        q=h.broker.query(1)
        h.repo._validate_inclusions(h.repo._state,q)
        inputs=build_current_inputs(h.inputs,q,h.broker,h.projection(),tuple(h.uow.ledger.state(h.intent.account_ref).events),at=AT)
        # The next candidate uses the original Q24 terms, actual fresh typed source,
        # and the first intent's remaining reservations and realized usage.
        second=approval_record(h.source)
        # approval_record selects candidate 0; use its same source-bound terms here.
        _,risk=current_risk(h.source,inputs,h.broker,second,at=AT,generation='synthetic-generation-1',
            fence=1,account_version=1,projection=inputs.current.current.snapshot.valuation.projection,
            intents=tuple(h.repo._state['intents'].values()),reservations=tuple(h.repo._state['reservations'].values()))
        row=risk.cash[0]
        self.assertEqual((row.ledger,row.outstanding,row.broker,row.unreflected,row.debits,row.available),('900','202','900','202','0','598'))
        with self.assertRaises(d.ExecutionDenied):
            build_current_inputs(h.inputs,replace(q,cash=(replace(q.cash[0],amount='9999'),)),h.broker,
                h.projection(),tuple(h.uow.ledger.state(h.intent.account_ref).events),at=AT)

    def test_EX11_partial_fills_not_double_exposure_or_funding(self):
        from synthetic_target import build
        from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
        from quantharbor.ports.approval import ApprovalSource
        from quantharbor.domain.target import ref as target_ref
        source,inputs,broker=composition(available='900',target_options={'targets':('3',None)},
            facts=(fact('f','execution-1'),fact('s','execution-1',kind='settlement')))
        policy=replace(inputs.current.policy,currency_limits=tuple(replace(x,funding_limit='604') for x in inputs.current.policy.currency_limits),
            exposure_limits=tuple(replace(x,maximum_amount='600') for x in inputs.current.policy.exposure_limits))
        current=replace(inputs.current,policy=policy)
        request_=replace(source.request,policy_ref=target_ref('policy',policy.policy_id,policy))
        repository=SyntheticTargetRepository()
        artifacts=build(request_,current,repository)
        source=ApprovalSource(request_,current,artifacts,repository)
        inputs=replace(inputs,current=current,policy=replace(inputs.policy,target_policy_ref=request_.policy_ref))
        # The fresh query component is bound to the immutable order terms, which
        # contain their policy ref and therefore use a separately issued manifest.
        fresh=broker._snapshots[1]
        component='obligation:'+hash_record(artifacts.candidates[0].body.terms)+':principal:used'
        from quantharbor.adapters.synthetic_execution_broker import SyntheticExecutionBroker
        broker=SyntheticExecutionBroker(source.request.account_ref,(broker._snapshots[0],
            replace(fresh,cash=(replace(fresh.cash[0],included_components=(component,)),))),broker._facts)
        inputs=replace(inputs,query=broker.query())
        h=FinancialHarness((),source=source,inputs=inputs,broker=broker)
        self.assertEqual((h.receive(0),h.receive(1)),('applied','applied'))
        q=broker.query(1)
        current=build_current_inputs(inputs,q,broker,h.projection(),tuple(h.uow.ledger.state(h.intent.account_ref).events),at=AT)
        _,risk=current_risk(source,current,broker,h.approval,at=AT,generation='synthetic-generation-1',fence=1,
            account_version=1,projection=current.current.current.snapshot.valuation.projection,
            intents=tuple(h.repo._state['intents'].values()),reservations=tuple(h.repo._state['reservations'].values()))
        self.assertEqual((risk.outcome,risk.cash[0].available),('allow','598'))

    def test_EX33_fresh_query_missing_event_or_false_inclusion_fails_closed(self):
        h=FinancialHarness((fact('f','execution-1'),fact('s','execution-1',kind='settlement')))
        h.receive(0)
        # A stale snapshot cannot claim a debit before actual settlement or cutoff.
        q=h.broker.query()
        forged=replace(q,cash=(replace(q.cash[0],included_components=('arbitrary-component:used',)),))
        with self.assertRaises(d.ExecutionDenied): h.repo._validate_inclusions(h.repo._state,forged)
        with self.assertRaises(d.ExecutionDenied): h.broker.query(1)
        h.receive(1)
        q=h.broker.query(1)
        with self.assertRaises(d.ExecutionDenied):
            h.repo._validate_inclusions(h.repo._state,replace(q,events=()))


class ExecutionPipeTests(unittest.TestCase):
    def unit_uow(self):
        db=PostgresLedger();db._ready=True
        return ExecutionUnitOfWork(db,'synthetic-account:pipe-unit')

    def test_EX37_partial_pipe_writes_send_entire_bounded_frame(self):
        uow=self.unit_uow()
        script="import sys,json; a=sys.stdin.buffer.readline(); marker=sys.stdin.buffer.readline().decode().split()[-1]; print(json.dumps(len(a)-1)); print(marker); sys.stdout.flush()"
        uow._process=subprocess.Popen([sys.executable,'-B','-c',script],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        write=os.write
        try:
            with patch('quantharbor.adapters.execution_uow.os.write',side_effect=lambda fd,data:write(fd,data[:7])):
                self.assertEqual(uow._exchange('x'*100000),100000)
        finally: uow.close()

    def test_EX37_write_timeout_and_oversized_frame_return_fixed_reason(self):
        uow=self.unit_uow()
        uow._process=object()
        with self.assertRaises(d.ExecutionDenied) as failure: uow._exchange('x'*MAX_FRAME)
        self.assertEqual(failure.exception.reason,'capacity_exceeded')
        uow._process=None
        uow._process=subprocess.Popen([sys.executable,'-B','-c','import sys; sys.stdin.buffer.read()'],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
        try:
            with patch('quantharbor.adapters.execution_uow.time.monotonic',side_effect=[0,21]):
                with self.assertRaises(d.ExecutionDenied) as failure: uow._exchange('SELECT 1;')
            self.assertEqual(failure.exception.reason,'storage_failure')
        finally: uow.close()


class ExecutionSourceRefreshTests(unittest.TestCase):
    def harness(self):
        return FinancialHarness((fact('f','execution-1'),fact('s','execution-1',kind='settlement')))

    def prepare_source_transition(self,h):
        from quantharbor.domain import approval as a
        approval_ref=a.ref('approval',h.approval.approval_id,h.approval)
        h.repo._state.update(heads={('approval',h.approval.approval_id):approval_ref},
            records={approval_ref:a.encoded(h.approval)},generation='synthetic-generation-1',fence=1)
        h.repo._auth=lambda *args,**kwargs:None

    def test_EX08_refresh_current_updates_reservation_cutoffs_and_reflection_atomically(self):
        h=self.harness()
        h.receive(0);h.receive(1)
        self.prepare_source_transition(h)
        original=h.repo._source
        q=h.broker.query(1)
        inputs=PostgresExecutionRepository.refresh_current.__wrapped__(h.repo,object(),q)
        self.assertIs(h.repo._source,original)
        self.assertEqual(inputs.query,q)
        self.assertEqual({r.source_cutoff for r in h.repo._state['reservations'].values()},{AT})
        self.assertEqual(h.reserve('principal').broker_reflected,'100')
        self.assertEqual(h.reserve('cost').broker_reflected,'0')
        self.assertEqual(h.repo._state['current_binding']['ledger_cursor'],3)
        self.assertEqual(h.repo._state['current_binding']['query'],d.ref('query',q.query_id,q))

    def test_EX33_refresh_rejects_real_but_stale_query_after_fill(self):
        h=self.harness();h.receive(0)
        self.prepare_source_transition(h)
        q=h.broker.query()
        before=h.repo._state.copy()
        with self.assertRaises(d.ExecutionDenied):
            PostgresExecutionRepository.refresh_current.__wrapped__(h.repo,object(),q)
        self.assertEqual(h.repo._state,before)

    def test_EX08_component_partial_reflection_cannot_double_deduct_or_double_include(self):
        from quantharbor.adapters.synthetic_execution_broker import SyntheticExecutionBroker,BrokerSnapshot
        from quantharbor.domain.execution_math import cash_with_reservations
        from quantharbor.domain.target import CashCalculation
        source,inputs,old_broker=composition(available='900',facts=(fact('a'),fact('b','e2'),fact('s',kind='settlement')))
        terms=source.artifacts.candidates[0].body.terms
        obligation='obligation:'+hash_record(terms)+':principal'
        part='included-execution:'+sha256((obligation+':e1:0').encode()).hexdigest()
        # The independently declared snapshot covers one100 settlement, while
        # another100 principal remains unsettled and the local held102 is absent.
        initial=old_broker._snapshots[0]
        fresh=replace(old_broker._snapshots[1],cash=(d.BrokerCash('USD','900',(part,)),),included_sequence=4)
        from quantharbor.domain.ledger import CashBalance,PositionDelta
        ss=replace(fresh.statement.snapshot,holdings=(PositionDelta(*terms.position.key,'2'),),
            cash=(CashBalance('settled_cash','USD','900'),CashBalance('unsettled_payable','USD','-100')))
        fresh=replace(fresh,statement=replace(fresh.statement,snapshot=ss,source_snapshot_hash=hash_record(ss)))
        duplicate=replace(fresh,cash=(d.BrokerCash('USD','900',(part,obligation+':used')),))
        broker=SyntheticExecutionBroker(source.request.account_ref,(initial,fresh,duplicate),old_broker._facts)
        inputs=replace(inputs,query=broker.query())
        h=FinancialHarness((),source=source,inputs=inputs,broker=broker)
        h.receive(0);h.receive(1);h.receive(2)
        query=broker.query(1)
        reflected=h.repo._validate_inclusions(h.repo._state,query)
        self.assertEqual(reflected['principal'],100)
        current=build_current_inputs(inputs,query,broker,h.projection(),tuple(h.uow.ledger.state(h.intent.account_ref).events),at=AT)
        self.assertTrue(current.current.current.snapshot.reconciliation_details.full_account_balances_matched)
        r=replace(h.reserve('principal'),source_cutoff=AT,broker_reflected='100')
        base=CashCalculation('USD','900','0','0','900','0','0','900','0','900')
        row=cash_with_reservations(base,(r,h.reserve('cost')),broker_amount='900',included=(part,),source_cutoff=AT)
        self.assertEqual((row.outstanding,row.unreflected,row.debits,row.available),('202','102','100','698'))
        with self.assertRaises(d.ExecutionDenied): h.repo._validate_inclusions(h.repo._state,broker.query(2))

    def test_EX33_reflection_cannot_reduce_old_query_used_or_spend_other_intent(self):
        from quantharbor.domain.execution_math import cash_with_reservations
        from quantharbor.domain.target import CashCalculation
        r=d.ReservationSlice('r','i','o','principal','cash','USD',AT,'2024-03-09T00:00:00Z',
            '300','100','200','0','100','100',AT,())
        other=replace(r,reservation_id='r2',intent_id='i2',obligation_id='o2',bound='20',held='20',used='0',settled='0',broker_reflected='0')
        base=CashCalculation('USD','900','0','0','900','0','0','900','0','900')
        row=cash_with_reservations(base,(r,other),source_cutoff=AT)
        self.assertEqual((row.outstanding,row.unreflected,row.debits,row.available),('220','120','100','680'))
        # A different query cutoff cannot inherit the prior source's inclusion.
        row=cash_with_reservations(base,(r,other),source_cutoff='2024-03-08T14:31:11.000000Z')
        self.assertEqual(row.debits,'200')


    def test_EX37_actual_LedgerEvent_codec_uses_body_environment_and_closed_schema(self):
        from quantharbor.adapters.postgres_execution import _pack,_unpack
        from quantharbor.domain.primitives import ContractError
        source,inputs,broker=composition()
        event=inputs.current.events[0]
        self.assertEqual(_unpack(_pack(event)),event)
        for environment in ('paper','live'):
            with self.assertRaises(ContractError): CanonicalPayload('LedgerEvent',1,environment,event)
        obj=asdict(event);obj['extra']='unknown'
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(dict(schema_name='LedgerEvent',schema_version=1,environment='synthetic',payload=obj)))

    def test_EX23_collision_remains_incomplete_after_a_later_valid_revision(self):
        h=FinancialHarness((fact('same'),fact('same',price='99'),fact('same',quantity='2',revision=2,predecessor=1)))
        self.assertEqual(h.receive(0),'applied')
        self.assertEqual(h.receive(1),'quarantined')
        self.assertEqual(h.receive(2),'applied')
        self.assertEqual(h.repo._state['intents']['intent-1'].accounting,'incomplete')
        self.assertEqual(h.repo._state['mode'],'faulted')
        self.assertEqual(len(h.repo._state['events']),3)


    def test_EX26_known_fee_unknown_tax_preserves_lower_bound_without_fake_zero(self):
        h=FinancialHarness((fact('partial-cost',fee='1',tax=None),
            fact('partial-cost',revision=2,predecessor=1,fee='1',tax='0.5')))
        self.assertEqual(h.receive(0),'observed_incomplete')
        self.assertEqual((h.reserve('cost').held,h.reserve('cost').used,h.reserve('cost').settled),('1','1','0'))
        head=next(iter(h.repo._state['event_heads'].values()))
        self.assertEqual(head['fee'],'1');self.assertIsNone(head['tax'])
        self.assertEqual(len(h.uow.ledger.state(h.intent.account_ref).events),1)
        self.assertEqual(h.receive(1),'applied')
        self.assertEqual((h.reserve('cost').held,h.reserve('cost').used,h.reserve('cost').settled),('0.5','1.5','1.5'))
        self.assertEqual((h.cash('fee_expense'),h.cash('tax_expense')),('1','0.5'))
        self.assertTrue(h.conserved())
