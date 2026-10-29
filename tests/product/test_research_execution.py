"""Q23 실행 추가 경로와 실제 위험 계산의 local tests. DB authority 증거가 아니다."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.application.execution import current_risk,build_current_inputs
from quantharbor.domain import execution as d
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.valuation import number
from synthetic_execution import composition,approval_record,AT,CORRECTION_FACTS
from test_execution_broker import request
from test_execution_runner import runner


def local_current(options,external,*,active_index=None,next_index=0):
    source,inputs,broker=composition(facts=(),**options)
    approval=approval_record(source,next_index)
    store=SyntheticLedger()
    for e in source.inputs.events:
        store.append(e.body.submission,recorded_at=e.body.recorded_at)
    intents,reservations=(),()
    if active_index is not None:
        active=approval_record(source,active_index)
        _,intent=request(source,active,broker)
        intent=replace(intent,state='prepared')
        intents=(intent,)
        terms=intent.terms
        reservations=tuple(d.ReservationSlice(component,intent.intent_id,'obligation:'+intent.request_hash+':'+component,
            component,dimension,'share' if dimension=='quantity' else terms.currency,AT,'2024-03-09T00:00:00Z',
            amount,amount,'0','0','0','0',inputs.query.as_of,())
            for component,dimension,amount in (('principal','cash',terms.principal_bound),('cost','cash',terms.cost_bound),
                ('quantity','quantity',terms.quantity if terms.side=='sell' else '0')))
    trade_id=None
    for key,index,qty,price in external:
        if key=='settle-buy': runner.settle_external(store,source,trade_id,'200')
        else: trade_id=runner.append_external(store,source,key=key,index=index,quantity=qty,price=price)
    projection=store.replay(source.request.account_ref,as_of=AT,knowledge_cutoff=AT)
    events=tuple(store.state(source.request.account_ref).events)
    current=build_current_inputs(inputs,broker.query(1),broker,projection,events,at=AT)
    return source,current,broker,approval,intents,reservations


def compute(values):
    source,current,broker,approval,intents,reservations=values
    return current_risk(source,current,broker,approval,at=AT,generation='synthetic-generation-1',fence=1,
        account_version=0,projection=current.current.current.snapshot.valuation.projection,
        intents=intents,reservations=reservations)


class ExecutionResearchRiskTests(unittest.TestCase):
    def test_EX11_actual_typed_all_account_one_sided_opposing_sale_no_net(self):
        manifest=dict(holdings=('0','5'),cash=(('settled_cash','1000'),('unsettled_payable','-100')),
            capacity='1000',sellable=('0','4'),cutoff=0)
        values=local_current(dict(target_options={'holdings':('0','4'),'targets':('0.5','3'),'lot':'0.5','fee':'0'},
            exposure_ceiling='500',current_manifest=manifest), (('extra',1,'1','100'),),active_index=1)
        self.assertEqual(values[1].current.current.snapshot.valuation.nav,'1400')
        with self.assertRaises(d.ExecutionDenied): compute(values)
        # The source policy permits each original plan; extra current B exposure
        # is what makes 500+50 exceed500 even with the opposing sell100.
        import quantharbor.application.execution as execution
        with patch.object(execution,'prospective_loss',wraps=execution.prospective_loss) as actual:
            with self.assertRaises(d.ExecutionDenied): compute(values)
            self.assertEqual(actual.call_count,1)

    def test_EX12_daily_and_gross_turnover_used400_active350_new300_NAV1000(self):
        manifest=dict(holdings=('4','0'),cash=(('settled_cash','400'),('unsettled_receivable','200')),
            capacity='400',sellable=('4','0'),cutoff=0)
        import quantharbor.application.execution as execution
        for mode in ('daily','turnover'):
            with self.subTest(mode=mode):
                values=local_current(dict(target_options={'cash':'600','holdings':('4','0'),'targets':('0.5','3'),'lot':'0.5','fee':'0'},
                    policy_changes={'max_daily_amount':'1000' if mode=='daily' else '10000000'},current_manifest=manifest),
                    (('buy',1,'2','100'),('settle-buy',1,'2','100'),('sell',1,'-2','100')),active_index=0,next_index=1)
                self.assertEqual(sum((f.notional for f in values[1].current.costs),number('0')),400)
                self.assertEqual(values[1].current.performance.time_weighted_nav.value,'1000')
                with patch.object(execution,'turnover',wraps=execution.turnover) as actual:
                    with self.assertRaises(d.ExecutionDenied): compute(values)
                    self.assertEqual(actual.call_count,0 if mode=='daily' else 1)
                    if mode=='turnover': self.assertEqual(actual.call_args.args,('400','650','0','1000'))

    def test_EX13_observed40_plus_cost15_exceeds50_and_drawdown(self):
        manifest=dict(holdings=('1','0'),cash=(('settled_cash','1000'),('unsettled_payable','-140')),
            capacity='1000',sellable=('0','0'),cutoff=0)
        import quantharbor.application.execution as execution
        for mode in ('loss','drawdown'):
            with self.subTest(mode=mode):
                values=local_current(dict(target_options={'targets':(None,'1'),'fee':'15'},
                    policy_changes={'max_loss_amount':'50' if mode=='loss' else '1000000',
                        'max_drawdown':'0.5' if mode=='loss' else '0.05'},current_manifest=manifest),
                    (('loss',0,'1','140'),))
                self.assertEqual(values[1].current.performance.amount_pnl.value,'-40')
                with patch.object(execution,'prospective_loss',wraps=execution.prospective_loss) as actual:
                    with self.assertRaises(d.ExecutionDenied): compute(values)
                    self.assertEqual(actual.call_args.args[:3],('40','15','960'))

    def test_EX09_current_typed_broker7_accepts7_rejects8(self):
        for qty in ('7','8'):
            with self.subTest(qty=qty):
                source,i,broker=composition(broker_sellable=('7','0'),
                    target_options={'holdings':('12','0'),'targets':('5' if qty=='7' else '4',None)})
                approval=approval_record(source)
                args=dict(at=AT,generation='synthetic-generation-1',fence=1,account_version=0,
                    projection=i.current.current.snapshot.valuation.projection,intents=(),reservations=())
                if qty=='7': self.assertEqual(current_risk(source,i,broker,approval,**args)[1].outcome,'allow')
                else:
                    with self.assertRaises(d.ExecutionDenied): current_risk(source,i,broker,approval,**args)

    def test_future_revision_retained_but_cannot_enter_earlier_cutoff_costs(self):
        from test_execution_correction import prepared,DELTA
        h,_,events=prepared('delta',DELTA)
        store=SyntheticLedger()
        for e in events[:2]: store.append(e.body.submission,recorded_at=e.body.recorded_at)
        store.append(events[-1].body.submission,recorded_at='2024-03-08T14:31:11.000000Z')
        all_events=tuple(store.state(h.intent.account_ref).events)
        manifest=dict(holdings=('1','0'),cash=(('settled_cash','1000'),('unsettled_payable','-90')),
            capacity='1000',sellable=('0','0'),cutoff=0)
        source,i,broker=composition(available='900',facts=(),current_manifest=manifest)
        p=store.replay(h.intent.account_ref,as_of=AT,knowledge_cutoff=AT,cursor=2)
        current=build_current_inputs(i,broker.query(1),broker,p,all_events,at=AT)
        self.assertEqual(current.current.events,all_events)
        self.assertEqual(tuple((c.quantity,c.fill_price,c.revision) for c in current.current.costs),(('1','90',1),))
        self.assertEqual(current.current.performance.amount_pnl.value,'10')

    def test_additive_api_accepts_only_actual_points_and_no_untrusted_allow(self):
        from quantharbor.application.execution_research import build_execution_performance
        with self.assertRaises(ContractError): build_execution_performance(('1000','1010'),())
        with self.assertRaises(TypeError): build_execution_performance((),(),allow=True)
        with self.assertRaises(TypeError): build_execution_performance((),(),proof=True)
