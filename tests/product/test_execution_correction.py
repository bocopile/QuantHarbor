"""Q27 정정 연결 local tests. 실제 Q20 계산이며 DB 통과 증거는 아니다."""
from dataclasses import replace
from fractions import Fraction
import unittest
from unittest.mock import patch

from quantharbor.application.execution import build_current_inputs,current_risk
from quantharbor.application.execution_research import (replay_execution_events,
    execution_active_events,build_execution_performance)
from quantharbor.application.research import _replay_events,build_bound_performance,validate_trade_costs
from quantharbor.application.target import _Blocked
from quantharbor.domain import execution as d
from quantharbor.domain.ledger import LedgerEvent,hash_record
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.research import known
from quantharbor.domain.valuation import number
from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from synthetic_execution import composition,AT
from test_execution_financial import FinancialHarness,fact

from synthetic_execution import CORRECTION_MANIFESTS as MANIFESTS, CORRECTION_FACTS
DELTA=CORRECTION_FACTS['delta']
CUMULATIVE=CORRECTION_FACTS['cumulative']
MULTI=CORRECTION_FACTS['multi']
COST=CORRECTION_FACTS['cost']


def prepared(name,facts):
    source,inputs,broker=composition(available='900',facts=facts,current_manifest=MANIFESTS[name])
    h=FinancialHarness((),source=source,inputs=inputs,broker=broker)
    for n in range(len(facts)):
        if h.receive(n)!='applied': raise AssertionError('fixture not accepted')
    events=tuple(h.uow.ledger.state(h.intent.account_ref).events)
    q=broker.query(1)
    current=build_current_inputs(inputs,q,broker,h.projection(),events,at=AT)
    return h,current,events


def risk(h,current,**kw):
    return current_risk(h.source,current,h.broker,h.approval,at=AT,generation='synthetic-generation-1',
        fence=1,account_version=1,projection=current.current.current.snapshot.valuation.projection,
        intents=tuple(h.repo._state['intents'].values()),reservations=tuple(h.repo._state['reservations'].values()),**kw)


class ExecutionCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.delta=prepared('delta',DELTA)
        cls.cost=prepared('cost',COST)

    def test_delta_qty1_to2_not3_Q20_Q21_Q23_currentrisk(self):
        h,i,events=self.delta
        _,decision=risk(h,i)
        self.assertEqual(decision.outcome,'allow')
        self.assertEqual(i.current.events,events)
        self.assertEqual(sum((number(f.quantity) for f in i.current.costs),Fraction()),2)
        self.assertEqual(sum((f.notional for f in i.current.costs),Fraction()),190)
        self.assertEqual(i.current.performance.amount_pnl.value,'10')
        self.assertEqual(i.current.current.snapshot.valuation.nav,'1010')
        self.assertEqual((decision.cash[0].available,h.reserve('principal').held),('598','110'))
        self.assertEqual(tuple(x.amount for x in i.current.current.snapshot.valuation.projection.holdings),('2',))
        self.assertEqual(tuple(x.settled_quantity for x in i.current.facts.sellability_rows),('0','0'))

    def test_cumulative_latest_correction_literal190(self):
        h,i,events=prepared('cumulative',CUMULATIVE)
        self.assertEqual(risk(h,i)[1].outcome,'allow')
        self.assertEqual(sum((number(f.quantity) for f in i.current.costs),Fraction()),2)
        self.assertEqual(sum((f.notional for f in i.current.costs),Fraction()),190)
        self.assertEqual(i.current.events,events)

    def test_mult_price90_100_95_principal290(self):
        h,i,_=prepared('multi',MULTI)
        self.assertEqual(risk(h,i)[1].outcome,'allow')
        self.assertEqual(sum((f.notional for f in i.current.costs),Fraction()),290)
        self.assertEqual((i.current.current.snapshot.valuation.nav,h.reserve('principal').held),('1010','10'))

    def test_positive_cost_revision_latest_only_no_doublecharge(self):
        h,i,events=self.cost
        self.assertEqual(risk(h,i)[1].outcome,'allow')
        self.assertEqual(len(i.current.costs),1)
        self.assertEqual(tuple(a.amount for a in i.current.costs[0].allocations),('1','0.5'))
        self.assertEqual(i.current.performance.amount_pnl.value,'-1.5')
        self.assertEqual(len(events),10)
        self.assertEqual(i.current.current.snapshot.valuation.nav,'998.5')

    def test_bundle_replacement_appended_once_reversal_submission_never_appended(self):
        _,_,events=self.cost
        seen=[]
        original=SyntheticLedger.append
        def observe(store,submission,**kw):
            seen.append(submission)
            return original(store,submission,**kw)
        with patch.object(SyntheticLedger,'append',observe):
            store=replay_execution_events(events)
        self.assertEqual(len(seen),7)
        self.assertEqual(tuple(store.state(events[0].body.account_ref).events),events)
        self.assertEqual(seen, [e.body.submission for e in events if e.body.kind=='replacement'])

    def test_missing_reversal_replacement_and_bundle_reordering_denied(self):
        events=self.delta[2]
        for bad in (events[:2]+events[3:],events[:-1],events[:2]+tuple(reversed(events[2:])),events[:1]+events[2:]):
            with self.subTest(bad=tuple(e.body.sequence for e in bad)),self.assertRaises(ContractError):
                replay_execution_events(bad)

    def test_hash_bundle_account_cursor_predecessor_time_economics_forgery_denied(self):
        events=self.delta[2]
        changes=(dict(bundle_id='bundle:forged'),dict(account_ref='synthetic-account:foreign'),
            dict(sequence=99),dict(recorded_at='2024-03-08T14:31:09.000000Z'),
            dict(effective_at='2024-03-08T14:31:09.000000Z'),dict(submission_hash='0'*64),
            dict(correction_of=events[0].body.event_id))
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ContractError):
                b=replace(events[-1].body,**change)
                replay_execution_events((*events[:-1],LedgerEvent(b,hash_record(b))))
        with self.assertRaises(ContractError):
            replay_execution_events((*events[:-1],replace(events[-1],payload_hash='0'*64)))
        with self.assertRaises(ContractError):
            s=replace(events[-1].body.submission,predecessor_revision=2)
            b=replace(events[-1].body,submission=s,submission_hash=hash_record(s))
            replay_execution_events((*events[:-1],LedgerEvent(b,hash_record(b))))
        with self.assertRaises(ContractError):
            s=replace(events[-1].body.submission,dependency_refs=('missing-event',))
            b=replace(events[-1].body,submission=s,submission_hash=hash_record(s))
            replay_execution_events((*events[:-1],LedgerEvent(b,hash_record(b))))

    def test_quarantined_decision_cursor_gap_cannot_be_discarded(self):
        h,_,events=self.delta
        store=SyntheticLedger()
        store.append(events[0].body.submission,recorded_at=events[0].body.recorded_at)
        bad=replace(events[1].body.submission,source_event_key='quarantine',event_type='unsupported')
        self.assertEqual(store.append(bad,recorded_at=AT).status,'quarantined')
        store.append(events[1].body.submission,recorded_at=AT)
        with self.assertRaises(ContractError): replay_execution_events(tuple(store.state(h.intent.account_ref).events))

    def test_unresolved_settled_dependency_denied(self):
        h=FinancialHarness((fact('t'),fact('s',kind='settlement'),fact('t',price='99',revision=2,predecessor=1)))
        h.receive(0);h.receive(1);h.receive(2)
        events=tuple(h.uow.ledger.state(h.intent.account_ref).events)
        with self.assertRaises(ContractError): execution_active_events(events,h.projection())
        self.assertEqual(h.repo._state['intents'][h.intent.intent_id].accounting,'incomplete')

    def test_oldcost_doublecharge_missing_cost_and_forged_performance_denied(self):
        h,i,events=self.cost
        fact_=i.current.costs[0]
        old=next(e for e in events if e.body.submission.event_type=='fee')
        alloc=replace(fact_.allocations[0],event=replace(fact_.allocations[0].event,ref=old.body.event_id,sha256=hash_record(old.body)),
            revision=1,amount='0.5',rate='0.005')
        variants=((),(replace(fact_,allocations=(alloc,fact_.allocations[1])),),
                  (replace(fact_,allocations=fact_.allocations[:1]),),(fact_,fact_))
        for costs in variants:
            with self.subTest(costs=costs),self.assertRaises((ContractError,d.ExecutionDenied,_Blocked)):
                risk(h,replace(i,current=replace(i.current,costs=costs)))
        with self.assertRaises((ContractError,d.ExecutionDenied,_Blocked)):
            perf=replace(i.current.performance,amount_pnl=known(10,ratio=False))
            risk(h,replace(i,current=replace(i.current,performance=perf)))

    def test_current_rights_revoked_and_futurecutoff_and_completebool_denied(self):
        h,i,_=self.delta
        point=i.current.current
        data=point.market_inputs[0]
        revoked=replace(data,current_rights=replace(data.current_rights,revoked_at=AT))
        current=replace(i.current,current=replace(point,market_inputs=(revoked,)))
        with self.assertRaises((ContractError,d.ExecutionDenied,_Blocked)): risk(h,replace(i,current=current))
        with self.assertRaises((ContractError,d.ExecutionDenied,_Blocked)):
            risk(h,replace(i,query=replace(i.query,as_of='2024-03-08T14:31:11.000000Z')))
        with self.assertRaises(TypeError): build_execution_performance((),(),complete=True)
        with self.assertRaises(TypeError): build_current_inputs(i,i.query,h.broker,h.projection(),(),at=AT,complete=True)

    def test_original_Q23_v1_still_rejects_correction_history_and_costs(self):
        _,i,events=self.delta
        with self.assertRaises(ContractError): _replay_events(events)
        with self.assertRaises(ContractError): validate_trade_costs(events,i.current.costs)
        with self.assertRaises(ContractError):
            build_bound_performance(i.current.risk_points,events,costs=i.current.costs)

    def test_real_issuer_wrongscope_and_wrong_literal_balance_denied(self):
        from quantharbor.adapters.synthetic_execution_broker import SyntheticExecutionBroker
        h,i,events=self.delta
        snapshot=h.broker._snapshots[1]
        bad_scope=replace(snapshot.scope,positions=snapshot.scope.positions[:1])
        for bad in (replace(snapshot,scope=bad_scope,sellable=snapshot.sellable[:1],included_sequence=0),
                    replace(snapshot,statement=h.broker._snapshots[0].statement,included_sequence=0)):
            with self.subTest(scope=bad.scope):
                broker=SyntheticExecutionBroker(h.intent.account_ref,(bad,),())
                query=broker.query()
                with self.assertRaises((ContractError,d.ExecutionDenied)):
                    build_current_inputs(h.inputs,query,broker,h.projection(),events,at=AT)

    def test_all_current_risk_and_daily_rights_rechecked_after_correction(self):
        h,i,_=self.delta
        def revoked(point):
            return replace(point,market_inputs=tuple(replace(data,
                current_rights=replace(data.current_rights,revoked_at=AT)) for data in point.market_inputs))
        for current in (replace(i.current,risk_points=(revoked(i.current.risk_points[0]),i.current.risk_points[-1])),
                        replace(i.current,daily_usage_inputs=(revoked(i.current.risk_points[0]),))):
            with self.subTest(daily=bool(current.daily_usage_inputs)),self.assertRaises((ContractError,d.ExecutionDenied,_Blocked)):
                risk(h,replace(i,current=current))

    def test_EX19_local_receipt_transition_actual_finalreject_only_releases(self):
        from quantharbor.adapters.postgres_execution import PostgresExecutionRepository
        source,inputs,broker=composition(facts=(),response='final_reject')
        h=FinancialHarness((),source=source,inputs=inputs,broker=broker)
        real=h.receipt
        # Deliberately exercise the undecorated local transition only. The
        # root runner exercises this same path inside actual DB transactions.
        for fake in (replace(real,journal_id='forged-journal'),replace(real,issuer_instance='foreign-issuer'),True):
            with self.assertRaises((d.ExecutionDenied,AttributeError)):
                PostgresExecutionRepository._store_receipt.__wrapped__(h.repo,h.attempt,fake)
            self.assertEqual((h.reserve('principal').held,h.reserve('cost').held),('300','2'))
        PostgresExecutionRepository._store_receipt.__wrapped__(h.repo,h.attempt,real)
        self.assertEqual(h.repo._state['intents'][h.intent.intent_id].state,'rejected')
        self.assertEqual((h.reserve('principal').held,h.reserve('principal').released,h.reserve('cost').released),('0','300','2'))
        self.assertEqual(broker.received_count,1)
