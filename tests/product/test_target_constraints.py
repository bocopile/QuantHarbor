from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import localcontext
from fractions import Fraction
import unittest

from quantharbor.domain.primitives import ContractError, utc_instant
from quantharbor.domain.ledger import LedgerEvent, hash_record
from quantharbor.domain.target import (ActiveOrder, CashTarget, TargetScope, available_cash, cost_bounds,
    weight_quantity)
from synthetic_target import build, changed, fixture, sale_target_fixture, fx_target_fixture
import test_target as integration
from test_target import base


class TargetConstraintTests(unittest.TestCase):
    blocked=integration.TargetIntegrationTests.blocked

    def test_source_bound_realized_cash_daily_usage_loss_and_drawdown(self):
        r,i=sale_target_fixture()
        a=build(r,i)
        self.assertEqual(a.result.body.outcome,'eligible')
        cash=a.plan.body.cash_calculation[0]
        self.assertEqual((cash.ledger_cash,cash.outstanding,cash.unreflected,cash.post_source_debits,cash.available),
                         ('1985','0','0','5','995'))
        risk=a.plan.body.account_calculation
        self.assertEqual((risk.daily_used_amount,risk.daily_used_quantity,risk.observed_loss,risk.observed_drawdown.value),
                         ('990','10','15','0.0075'))
        self.blocked(*changed(r,i,policy=replace(i.policy,max_daily_amount='1090')),'daily_limit')
        self.blocked(*changed(r,i,policy=replace(i.policy,max_loss_amount='14')),'loss_limit')
        self.blocked(*changed(r,i,policy=replace(i.policy,max_drawdown='0.0074')),'loss_limit')
        self.blocked(*changed(r,i,facts=replace(i.facts,post_source_cash_changes=())),'source_incomplete')
        with self.assertRaises(ContractError):
            build(r,replace(i,facts=replace(i.facts,daily_usage_event_refs=())))

    def test_source_bound_current_fx_both_directions_and_weight(self):
        for inverse in (False,True):
            r,i=fx_target_fixture(inverse=inverse)
            a=build(r,i)
            self.assertEqual(a.result.body.outcome,'eligible')
            self.assertEqual(a.plan.body.positions[0].target_quantity,'4')
            self.assertEqual(a.plan.body.positions[0].weight_residual,'0.00999759997599976' if inverse else '0.01')
            self.assertEqual((a.plan.body.positions[0].residual_numerator,a.plan.body.positions[0].residual_denominator),('1333','133332') if inverse else ('1','100'))
            self.assertEqual(a.candidates[0].body.terms.maximum_burden,'240')
            self.assertEqual(i.current.snapshot.valuation.nav,'333.33' if inverse else '300')

    def test_future_event_and_submission_window_intersection(self):
        r,i=base(targets=('3',None))
        body=replace(i.events[0].body,recorded_at='2024-03-09T00:00:00Z')
        event=LedgerEvent(body,hash_record(body))
        self.blocked(r,replace(i,events=(event,)),'temporal_mismatch')
        def plus(seconds):
            return utc_instant(datetime.fromisoformat(r.evaluated_at)+timedelta(seconds=seconds))
        data=i.current.market_inputs[0]
        data=replace(data,current_rights=replace(data.current_rights,valid_to=plus(7)))
        point=replace(i.current,market_inputs=(data,))
        inputs=replace(i,current=point,risk_points=(*i.risk_points[:-1],point))
        facts=replace(i.facts,capabilities=tuple(replace(c,valid_to=plus(11)) for c in i.facts.capabilities),
            cost_rules=tuple(replace(c,valid_to=plus(9)) for c in i.facts.cost_rules))
        a=build(*changed(r,inputs,facts=facts))
        self.assertEqual(a.candidates[0].body.terms.valid_to,plus(7))

    def test_nav_lower_bound_does_not_spend_upstream_rounding_gain(self):
        r,i=fixture(holdings=('1','0'),prices=('100.006','100'),targets=('1',None),fee='0')
        a=build(r,i)
        self.assertEqual(a.result.body.outcome,'eligible')
        calculation=a.plan.body.account_calculation
        self.assertEqual((calculation.nav,calculation.worst_cost_and_adverse,calculation.nav_lower_bound),
                         ('1100.01','0.01','1100'))

    def test_independent_math_cash_cost_and_weight_goldens(self):
        self.assertEqual(available_cash('1000','100','100','950','50','20'),'800')
        self.assertEqual(available_cash('10','20','0','100','0','0'),'-10')
        r,i=base()
        rule=replace(i.facts.cost_rules[0],fee_fixed='0.5',fee_per_share='0.125',tax_fixed='0',tax_per_share='0.075',money_quantum='0.05')
        self.assertEqual(cost_bounds(rule,'3'),('0.9','0.25'))
        self.assertEqual(weight_quantity('1000','0.25','60','2'),('4',Fraction(1,100)))
        with localcontext() as context:
            context.prec=2
            self.assertEqual(cost_bounds(rule,'3'),('0.9','0.25'))
            self.assertEqual(available_cash('1000','100','100','950','50','20'),'800')

    def test_source_bound_cost_quantum_and_conservative_nav(self):
        r,i=fixture(targets=('3',None))
        rules=tuple(replace(x,fee_fixed='0.5',fee_per_share='0.125',tax_per_share='0.075',money_quantum='0.05') for x in i.facts.cost_rules)
        a=build(*changed(r,i,facts=replace(i.facts,cost_rules=rules)))
        t=a.candidates[0].body.terms
        self.assertEqual((t.fee_bound,t.tax_bound,t.cost_bound,t.maximum_burden),('0.9','0.25','1.15','301.15'))
        self.assertEqual(a.plan.body.account_calculation.nav_lower_bound,'998.85')

    def test_buy_only_exposure_cannot_rely_on_sale(self):
        r,i=fixture(holdings=('4.5','1'),targets=('5.5','0'),lot='0.5',fee='0')
        limits=tuple(replace(x,maximum_amount='500') if x.dimension=='instrument' and x.key=='q24.A' else x for x in i.policy.exposure_limits)
        self.blocked(*changed(r,i,policy=replace(i.policy,exposure_limits=limits)),'exposure_limit')

    def test_scope_cannot_hide_existing_violation(self):
        r,i=fixture(holdings=('0','7'),targets=('1',None),scope_indices=(0,),fee='0')
        limits=tuple(replace(x,maximum_amount='600') if x.dimension=='instrument' and x.key=='q24.B' else x for x in i.policy.exposure_limits)
        self.blocked(*changed(r,i,policy=replace(i.policy,exposure_limits=limits)),'exposure_limit')

    def test_sector_market_currency_weight_funding_constraints(self):
        r,i=base()
        for dim in ('sector','market','currency','instrument'):
            limits=tuple(replace(x,maximum_weight='0.1') if x.dimension==dim else x for x in i.policy.exposure_limits)
            self.blocked(*changed(r,i,policy=replace(i.policy,exposure_limits=limits)),'exposure_limit')
        limits=(replace(i.policy.currency_limits[0],funding_limit='500'),)
        self.blocked(*changed(r,i,policy=replace(i.policy,currency_limits=limits)),'exposure_limit')
        self.blocked(*changed(r,i,policy=replace(i.policy,exposure_limits=())),'policy_missing')

    def test_order_daily_volume_and_rounding_limits(self):
        r,i=base()
        for field,value,code in (('max_order_amount','300','proposal_infeasible'),('max_order_quantity','2','proposal_infeasible'),
                ('max_daily_amount','703','daily_limit'),('max_daily_quantity','6','daily_limit'),
                ('max_volume_participation','0.0001','proposal_infeasible')):
            self.blocked(*changed(r,i,policy=replace(i.policy,**{field:value})),code)
        r,i=fixture(prices=('60','60'),lot='2',basis='weight',targets=('0.25',None),fee='0')
        self.blocked(*changed(r,i,policy=replace(i.policy,max_rounding_error='0.009')),'proposal_infeasible')

    def test_explicit_and_derived_tick_price_conditions(self):
        r,i=base(targets=('3',None))
        self.blocked(replace(r,targets=(replace(r.targets[0],limit_price='100.001'),)),i,'tick_violation')
        self.blocked(replace(r,targets=(replace(r.targets[0],limit_price='111'),)),i,'proposal_infeasible')
        r,i=fixture(prices=('100.005','100'),targets=('3',None),fee='0')
        a=build(r,i)
        self.assertEqual(a.candidates[0].body.terms.limit_price,'100')
        r,i=fixture(holdings=('3','0'),prices=('100.005','100'),targets=('0',None),fee='0')
        a=build(r,i)
        self.assertEqual(a.candidates[0].body.terms.limit_price,'100.01')

    def test_lot_and_sellability_independent_of_current_holdings(self):
        r,i=fixture(lot='2',targets=('3',None))
        self.blocked(r,i,'lot_violation')
        r,i=fixture(holdings=('10','0'),targets=('5',None))
        facts=replace(i.facts,sellability_rows=(replace(i.facts.sellability_rows[0],settled_quantity='4'),i.facts.sellability_rows[1]))
        self.blocked(*changed(r,i,facts=facts),'sellability_unknown')
        self.blocked(*changed(r,i,facts=replace(i.facts,sellability_rows=())),'sellability_unknown')

    def test_cash_floor_and_explicit_cash_target(self):
        r,i=base()
        r=replace(r,cash_targets=(CashTarget('USD','300'),))
        self.blocked(r,i,'cash_shortfall')
        r,i=base(obligations=True)
        facts=replace(i.facts,cash_capacity_rows=(replace(i.facts.cash_capacity_rows[0],capacity_scope='instrument'),))
        self.blocked(*changed(r,i,facts=facts),'capacity_scope_unsupported')

    def test_scope_and_temporal_completeness_are_not_proof_booleans(self):
        r,i=base()
        for facts,code in ((replace(i.facts,status='partial'),'source_incomplete'),
            (replace(i.facts,temporal_consistency='unknown'),'temporal_mismatch'),
            (replace(i.facts,active_intents_status='unknown'),'active_intent_conflict'),
            (replace(i.facts,post_source_status='unknown'),'source_incomplete'),
            (replace(i.facts,mapping_version='unknown-version'),'mapping_unknown'),
            (replace(i.facts,covered_scope=replace(i.facts.covered_scope,positions=())),'source_incomplete')):
            self.blocked(*changed(r,i,facts=facts),code)
        order=ActiveOrder('active-1',r.scope.positions[0],'buy','1','active',i.facts.source_snapshot_id)
        self.blocked(*changed(r,i,facts=replace(i.facts,broker_open_orders=(order,))),'active_intent_conflict')
        self.blocked(*changed(r,i,facts=replace(i.facts,local_active_intents=(order,))),'active_intent_conflict')

    def test_staleness_expiry_and_session_end_exclusion(self):
        r,i=base()
        self.blocked(replace(r,expires_at=r.evaluated_at),i,'expired')
        self.blocked(*changed(r,i,policy=replace(i.policy,max_account_age_seconds=1)),'stale_input')
        self.blocked(*changed(r,i,policy=replace(i.policy,max_price_age_seconds=1)),'stale_input')
        end=i.current.market_inputs[0].calendar.days[0].sessions[0].ends_at
        p=replace(i.policy,max_account_age_seconds=86400,max_price_age_seconds=86400)
        r,i=changed(r,i,policy=p)
        self.blocked(replace(r,evaluated_at=end,expires_at='2024-03-09T00:00:00Z'),i,'calendar_ineligible')

    def test_missing_capability_cost_classification_and_mapping_block(self):
        r,i=base()
        for facts,code in ((replace(i.facts,capabilities=()),'capability_unknown'),
                (replace(i.facts,cost_rules=()),'cost_bound_unknown'),
                (replace(i.facts,classifications=()),'source_incomplete')):
            self.blocked(*changed(r,i,facts=facts),code)

    def test_obligation_status_reflection_and_double_count_are_checked(self):
        r,i=base(obligations=True)
        for row in (replace(i.facts.obligations[0],reflected_in_L=True),
                    replace(i.facts.obligations[0],reflected_in_B=False)):
            facts=replace(i.facts,obligations=(row,i.facts.obligations[1]))
            with self.assertRaises(ContractError):
                build(r,replace(i,facts=facts))
        facts=replace(i.facts,obligations=(replace(i.facts.obligations[0],outstanding_or_realized='unknown'),i.facts.obligations[1]))
        with self.assertRaises(ContractError):
            build(r,replace(i,facts=facts))


if __name__=='__main__':
    unittest.main()
