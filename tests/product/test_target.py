from copy import copy, deepcopy
from dataclasses import replace
from functools import lru_cache
import unittest

from quantharbor.adapters.synthetic_target import SyntheticTargetRepository
from quantharbor.application.target import build_target, candidate_json, render_candidate
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.target import TargetScope, TargetValue, ref
from synthetic_target import build, changed, fixture


@lru_cache(maxsize=16)
def base(**kwargs):
    return fixture(**kwargs)


class TargetIntegrationTests(unittest.TestCase):
    def blocked(self, request, inputs, code):
        result = build(request, inputs)
        self.assertEqual((result.result.body.outcome, result.result.body.effect, result.candidates), ('blocked', 'none', ()))
        self.assertIn(code, {x.code for x in result.result.body.failures})
        return result

    def test_source_bound_704_and_804_golden(self):
        request, inputs = base(obligations=True)
        result = build(request, inputs)
        self.assertEqual(result.result.body.outcome, 'eligible')
        row = result.plan.body.cash_calculation[0]
        self.assertEqual((row.ledger_cash, row.outstanding, row.floor, row.broker_capacity,
            row.unreflected, row.available, row.planned_burden, row.remaining), ('1000','100','100','950','50','800','704','96'))
        self.assertEqual([(c.body.terms.maximum_burden,c.body.terms.cumulative_burden,c.body.terms.remaining_capacity)
            for c in result.candidates], [('302','302','498'),('402','704','96')])
        altered = replace(request, targets=(request.targets[0], replace(request.targets[1], value='5')))
        self.blocked(altered, inputs, 'cash_shortfall')
        self.assertEqual(inputs.current.snapshot.open_orders_status, 'unknown')
        self.assertTrue(all(x.available_cash is None and x.reserved_cash is None and x.broker_buy_capacity is None
            for x in inputs.current.snapshot.cash_by_currency))

    def test_kr_us_quantity_full_partial_and_scope_outside_preserved(self):
        for market in ('KR','US'):
            for mode, expected in (('partial', ['6','7']), ('full',['6','0'])):
                with self.subTest(market=market, mode=mode):
                    r,i=fixture(market=market, holdings=('10','7'), targets=('6',None), mode=mode)
                    result=build(r,i)
                    self.assertEqual(result.result.body.outcome,'eligible')
                    self.assertEqual([x.target_quantity for x in result.plan.body.positions],expected)
                    self.assertTrue(all(c.body.terms.side=='sell' for c in result.candidates))
            r,i=fixture(market=market,holdings=('10','7'),targets=('6',None),mode='full',scope_indices=(0,))
            result=build(r,i)
            self.assertEqual([x.target_quantity for x in result.plan.body.positions],['6','7'])
            self.blocked(replace(r,omission_rule='unspecified'),i,'ambiguous_omission')

    def test_weight_golden_both_markets(self):
        for market in ('KR','US'):
            r,i=fixture(market=market,prices=('60','60'),lot='2',basis='weight',targets=('0.25',None),fee='0')
            result=build(r,i)
            row=result.plan.body.positions[0]
            self.assertEqual((row.target_quantity,row.weight_residual,row.residual_numerator,row.residual_denominator),('4','0.01','1','100'))
            self.assertEqual(result.candidates[0].body.terms.maximum_burden,'240')

    def test_no_future_sale_cash(self):
        r,i=fixture(cash='200',holdings=('10','0'),targets=('0','3'),fee='0')
        self.blocked(r,i,'cash_shortfall')

    def test_valid_no_change_is_eligible_but_missing_semantics_is_blocked(self):
        r,i=fixture(holdings=('10','7'),targets=('10','7'))
        a=build(r,i)
        self.assertEqual((a.result.body.outcome,a.result.body.effect,a.candidates),('eligible','no_change',()))
        self.blocked(r,replace(i,facts=None),'source_incomplete')
        self.blocked(r,replace(i,policy=None),'policy_missing')
        self.blocked(*changed(r,i,facts=replace(i.facts,semantics_version='unknown')),'source_semantics_unknown')

    def test_paper_live_are_blocked_and_remain_canonical(self):
        r,i=base()
        for env in ('paper','live'):
            a=self.blocked(replace(r,environment=env),i,'environment_blocked')
            self.assertEqual(a.plan.body.environment,env)

    def test_no_q19_complete_to_known_conversion(self):
        r,i=base()
        # Q21 원래 unknown과 합성 facts 없는 입력은 가용금/미체결 사실을 만들지 않는다.
        self.assertEqual(i.current.snapshot.open_order_refs,())
        self.blocked(r,replace(i,facts=None),'source_incomplete')
        self.blocked(*changed(r,i,facts=replace(i.facts,open_orders_status='unknown')),'open_orders_unknown')

    def test_current_research_and_store_rights_revocation(self):
        r,i=base()
        for purposes in (('store','report'),('research','report')):
            data=replace(i.current.market_inputs[0],current_rights=replace(i.current.market_inputs[0].current_rights,purposes=purposes))
            point=replace(i.current,market_inputs=(data,))
            altered=replace(i,current=point,risk_points=(*i.risk_points[:-1],point))
            self.blocked(r,altered,'rights_denied')

    def test_refreshed_current_grant_preserves_historical_snapshot(self):
        r,i=base()
        data=replace(i.current.market_inputs[0],current_rights=replace(i.current.market_inputs[0].current_rights,valid_to='2026-01-01T00:00:00Z'))
        point=replace(i.current,market_inputs=(data,))
        altered=replace(i,current=point,risk_points=(*i.risk_points[:-1],point))
        a=build(r,altered)
        self.assertEqual(a.result.body.outcome,'eligible')
        self.assertEqual(altered.current.snapshot,i.current.snapshot)

    def test_source_refs_must_resolve_actual_objects(self):
        r,i=base(obligations=True)
        for facts in (replace(i.facts,projection_ref=replace(i.facts.projection_ref,sha256='a'*64)),
                      replace(i.facts,statement_ref=replace(i.facts.statement_ref,sha256='a'*64)),
                      replace(i.facts,loss_performance_ref=replace(i.facts.loss_performance_ref,sha256='a'*64))):
            with self.subTest(facts=facts.source_id),self.assertRaises(ContractError):
                build(r,replace(i,facts=facts))
        with self.assertRaises(ContractError):
            build(r,replace(i,obligation_sources=()))
        with self.assertRaises(ContractError):
            build(replace(r,snapshot_ref=replace(r.snapshot_ref,sha256='b'*64)),i)

    def test_forged_snapshot_projection_and_storage_evidence_rejected(self):
        r,i=base()
        for kind in ('snapshot','event','storage'):
            altered=copy(i)
            if kind=='snapshot':
                point=copy(i.current)
                object.__setattr__(point,'snapshot',deepcopy(i.current.snapshot))
                object.__setattr__(altered,'current',point)
                object.__setattr__(point.snapshot.valuation,'nav','9999')
            elif kind=='event':
                object.__setattr__(altered,'events',deepcopy(i.events))
                object.__setattr__(altered.events[0],'payload_hash','a'*64)
            else:
                point=copy(i.current)
                data=copy(i.current.market_inputs[0])
                bundle=copy(data.bundle)
                object.__setattr__(bundle,'summary',deepcopy(bundle.summary))
                object.__setattr__(bundle.summary,'quality',None)
                object.__setattr__(data,'bundle',bundle)
                object.__setattr__(point,'market_inputs',(data,))
                object.__setattr__(altered,'current',point)
            with self.subTest(kind=kind),self.assertRaises(ContractError):
                build(r,altered)

    def test_report_requires_current_report_rights_and_exact_candidate(self):
        r,i=base(targets=('3',None))
        repo=SyntheticTargetRepository()
        a=build_target(r,i,repo)
        c=a.candidates[0]
        rendered=render_candidate(c,repo,i.current.market_inputs,at=r.evaluated_at)
        self.assertIn('3주 매수',rendered)
        self.assertIn('최대 필요자금 302 USD',rendered)
        self.assertIn(c.body.display_terms.risks[0],rendered)
        self.assertIn('승인 전',rendered)
        self.assertEqual(candidate_json(c)['payload']['candidate_id'],c.candidate_id)
        data=i.current.market_inputs[0]
        revoked=replace(data,current_rights=replace(data.current_rights,purposes=('research','store')))
        with self.assertRaises(ContractError):
            render_candidate(c,repo,(revoked,),at=r.evaluated_at)
        with self.assertRaises(ContractError):
            render_candidate(c,repo,(),at=r.evaluated_at)

    def test_empty_or_wrong_period_risk_evidence_does_not_substitute(self):
        r,i=base()
        self.blocked(r,replace(i,risk_points=()),'loss_limit')
        policy=replace(i.policy,risk_window_start='2024-03-01T00:00:00Z')
        self.blocked(*changed(r,i,policy=policy),'loss_limit')
        self.blocked(r,replace(i,risk_points=tuple(reversed(i.risk_points))),'loss_limit')

    def test_generation_and_display_change_have_new_identity(self):
        r,i=base(targets=('3',None))
        first=build(r,i)
        second=build(replace(r,authority_generation='new-generation'),i)
        self.assertNotEqual(first.candidates[0].candidate_id,second.candidates[0].candidate_id)
        strategy=replace(i.strategy,risks=('새로운 합성 위험 문구입니다.',))
        third=build(*changed(r,i,strategy=strategy))
        self.assertNotEqual(first.candidates[0].candidate_id,third.candidates[0].candidate_id)


if __name__=='__main__':
    unittest.main()
