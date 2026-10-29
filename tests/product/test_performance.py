from dataclasses import replace
from fractions import Fraction
import unittest

from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
from quantharbor.application.research import build_bound_performance, nav_point
from quantharbor.application.valuation import build_snapshot
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.research import FlowBoundary, InputRef, known, unknown
from quantharbor.domain.valuation import quantize
from quantharbor.research.metrics import calculate_performance
from synthetic_research import TIMES, fixed_inputs, flow_fixture, nav, sale_fixture


def rebuild_point(point, *, purpose=None, rights_changes=None):
    """목적/소비 권리를 바꾼 정상 Q21 snapshot을 생성한다. ID/hash 변조 없음."""
    s = point.snapshot
    request = s.valuation.request
    if purpose is not None:
        request = replace(request, purpose=purpose)
    market_inputs = point.market_inputs if rights_changes is None else tuple(
        replace(data, current_rights=replace(data.current_rights, **rights_changes))
        for data in point.market_inputs)
    snapshot = build_snapshot(s.valuation.projection, request, market_inputs, s.valuation.policy,
        s.reconciliation_policy, SyntheticSnapshotRepository(), statement=s.reconciliation_details.statement)
    return replace(point, snapshot=snapshot, market_inputs=market_inputs)


class PerformanceTests(unittest.TestCase):
    def calculate(self, points, *, traded=0, benchmark=Fraction(1, 10), flows=()):
        return calculate_performance(points, flows, known(traded, ratio=False), known(benchmark))

    def test_report_only_evaluation_points_rejected(self):
        run = next(x for x in fixed_inputs() if
            (x.market_id, x.scenario_id, x.fold_id, x.strategy) ==
            ('KR', 'explicit_costs', 'fold01', 'buy_hold'))
        legitimate = build_bound_performance(run.points, run.events, costs=run.costs)
        self.assertEqual(legitimate.twr.value, '-0.0047358')
        # 각 평가점 하나만 바꾸어 첫 점/중간 점/끝 점의 검사를 각각 입증한다.
        for index, point in enumerate(run.points):
            for purposes in (('store', 'report'), ('store', 'research', 'report')):
                with self.subTest(index=index, purposes=purposes):
                    report = rebuild_point(point, purpose='report', rights_changes=dict(purposes=purposes))
                    self.assertTrue(report.snapshot.valuation.complete)
                    self.assertEqual(report.snapshot.valuation.nav, point.snapshot.valuation.nav)
                    self.assertNotEqual(report.snapshot.snapshot_id, point.snapshot.snapshot_id)
                    changed = (*run.points[:index], report, *run.points[index + 1:])
                    with self.assertRaises(ContractError):
                        build_bound_performance(changed, run.events, costs=run.costs)

    def test_legitimate_research_inputs_without_report_rights_preserved(self):
        points, events, boundary_inputs, boundary = flow_fixture(with_market=True)
        changes = dict(purposes=('store', 'research'))
        points = tuple(rebuild_point(point, rights_changes=changes) for point in points)
        boundary_inputs = tuple(rebuild_point(point, rights_changes=changes) for point in boundary_inputs)
        boundary = replace(boundary, before=nav_point(boundary_inputs[0].snapshot),
                           after=nav_point(boundary_inputs[1].snapshot))
        r = build_bound_performance(points, events, boundaries=(boundary,), boundary_inputs=boundary_inputs)
        self.assertEqual((r.twr.value, r.amount_pnl.value), ('0.21', '26'))

    def test_research_rights_required_at_every_evaluation_point(self):
        points, events, boundary_inputs, boundary = flow_fixture(with_market=True)
        for index, point in enumerate(points):
            for changes in (dict(purposes=('store', 'report')),
                            dict(revoked_at=point.snapshot.created_at),
                            dict(valid_to=point.snapshot.created_at)):
                with self.subTest(index=index, changes=changes):
                    denied = rebuild_point(point, rights_changes=changes)
                    # Q21의 현금 NAV는 완전해도 제공한 시장 증빙의 연구 권리는 필수다.
                    self.assertTrue(denied.snapshot.valuation.complete)
                    self.assertTrue(denied.snapshot.valuation.market_proofs[0].held_reasons)
                    changed = (*points[:index], denied, *points[index + 1:])
                    with self.assertRaises(ContractError):
                        build_bound_performance(changed, events, boundaries=(boundary,), boundary_inputs=boundary_inputs)

    def test_report_only_flow_boundary_inputs_rejected(self):
        points, events, boundary_inputs, boundary = flow_fixture(with_market=True)
        legitimate = build_bound_performance(points, events, boundaries=(boundary,), boundary_inputs=boundary_inputs)
        self.assertEqual((legitimate.twr.value, legitimate.amount_pnl.value), ('0.21', '26'))
        report_only = tuple(rebuild_point(point, purpose='report', rights_changes=dict(purposes=('store', 'report')))
                            for point in boundary_inputs)
        flow = replace(boundary, before=nav_point(report_only[0].snapshot), after=nav_point(report_only[1].snapshot))
        self.assertTrue(all(point.snapshot.valuation.complete for point in report_only))
        with self.subTest(purposes=('store', 'report')), self.assertRaises(ContractError):
            build_bound_performance(points, events, boundaries=(flow,), boundary_inputs=report_only)
        # 권리를 유지한 채 직전/직후의 목적만 각각 바꾸어 두 경계의 검사를 입증한다.
        for index, point in enumerate(boundary_inputs):
            with self.subTest(index=index):
                report = rebuild_point(point, purpose='report')
                self.assertTrue(report.snapshot.valuation.complete)
                changed = (*boundary_inputs[:index], report, *boundary_inputs[index + 1:])
                flow = replace(boundary, before=nav_point(changed[0].snapshot), after=nav_point(changed[1].snapshot))
                with self.assertRaises(ContractError):
                    build_bound_performance(points, events, boundaries=(flow,), boundary_inputs=changed)

    def test_research_rights_required_at_every_flow_boundary_input(self):
        points, events, boundary_inputs, boundary = flow_fixture(with_market=True)
        at = boundary_inputs[0].snapshot.created_at
        for changes in (dict(purposes=('store', 'report')), dict(revoked_at=at), dict(valid_to=at)):
            with self.subTest(changes=changes):
                # 같은 시장/권리를 양쪽에 공급해 경계 증빙 불일치로 인한 거부를 배제한다.
                denied = tuple(rebuild_point(point, rights_changes=changes) for point in boundary_inputs)
                self.assertTrue(all(point.snapshot.valuation.complete for point in denied))
                self.assertTrue(all(point.snapshot.valuation.market_proofs[0].held_reasons for point in denied))
                flow = replace(boundary, before=nav_point(denied[0].snapshot), after=nav_point(denied[1].snapshot))
                with self.assertRaises(ContractError):
                    build_bound_performance(points, events, boundaries=(flow,), boundary_inputs=denied)

    def test_actual_flow_boundary_golden_21_percent_and_amount_26(self):
        points, events, boundary_inputs, boundary = flow_fixture()
        r = build_bound_performance(points, events, boundaries=(boundary,), boundary_inputs=boundary_inputs,
                                    benchmark_return=known(Fraction(1, 10)))
        self.assertEqual(r.twr.value, '0.21')
        self.assertEqual(r.amount_pnl.value, '26')
        self.assertEqual(r.benchmark_excess.value, '0.11')
        self.assertEqual(r.benchmark_relative_wealth.value, '0.1')
        self.assertEqual(r.time_weighted_nav.value, '130')

    def test_withdrawal_does_not_create_loss_or_drawdown(self):
        points, events, boundary_inputs, boundary = flow_fixture(withdrawal=True)
        r = build_bound_performance(points, events, boundaries=(boundary,), boundary_inputs=boundary_inputs)
        self.assertEqual((r.twr.value, r.amount_pnl.value, r.observed_mdd.value), ('0', '0', '0'))

    def test_missing_and_interleaved_flow_boundary_rejected(self):
        points, events, boundary_inputs, boundary = flow_fixture()
        with self.assertRaises(ContractError):
            build_bound_performance(points, events)
        with self.assertRaises(ContractError):
            build_bound_performance(points, events, boundaries=(boundary,), boundary_inputs=boundary_inputs[:1])
        points, events, boundary_inputs, boundary = flow_fixture(intruder=True)
        with self.assertRaises(ContractError):
            build_bound_performance(points, events, boundaries=(boundary,), boundary_inputs=boundary_inputs)

    def test_bad_flow_amount_time_currency_and_quantum(self):
        points, events, boundary_inputs, boundary = flow_fixture()
        with self.assertRaises(ContractError):
            replace(boundary, amount='49')
        with self.assertRaises(ContractError):
            replace(boundary, amount='50.001')
        with self.assertRaises(ContractError):
            replace(boundary, after=replace(boundary.after, knowledge_cutoff=TIMES[2]))
        with self.assertRaises(ContractError):
            build_bound_performance(points, events, boundaries=(replace(boundary, currency='KRW'),), boundary_inputs=boundary_inputs)

    def test_geometric_link_mdd_turnover_and_exact_ratios(self):
        r = self.calculate(tuple(nav(i, value) for i, value in enumerate(('100', '120', '90', '108'), 1)))
        self.assertEqual(r.twr.value, '0.08')
        self.assertEqual(r.observed_mdd.value, '0.25')
        r = self.calculate((nav(1, '100'), nav(2, '100')), traded=100)
        self.assertEqual((r.gross_turnover.value, r.half_turnover.value), ('1', '0.5'))
        # 시간가중 NAV는 (100*2+101)/3. 반올림된 평균을 회전율에 재사용하지 않는다.
        r = self.calculate((nav(1, '100'), nav(2, '101', at=TIMES[2]), nav(3, '102', at=TIMES[3])), traded=1)
        self.assertEqual(r.time_weighted_nav.exact_value, Fraction(301, 3))
        self.assertEqual(r.gross_turnover.exact_value, Fraction(3, 301))

    def test_loss_zero_negative_partial_and_bad_benchmark(self):
        loss = self.calculate((nav(1, '2000'), nav(2, '1985')))
        self.assertEqual(loss.twr.value, '-0.0075')
        self.assertEqual(loss.amount_pnl.value, '-15')
        zero = self.calculate((nav(1, '100'), nav(2, '0')))
        self.assertEqual((zero.twr.value, zero.observed_mdd.value), ('-1', '1'))
        after_zero = self.calculate((nav(1, '100'), nav(2, '0'), nav(3, '10')))
        self.assertIsNone(after_zero.twr.value)
        self.assertEqual(after_zero.observed_mdd.value, '1')
        for points in ((nav(1, '0'), nav(2, '10')), (nav(1, '-10'), nav(2, '-20'))):
            self.assertIsNone(self.calculate(points).twr.value)
        partial = self.calculate((nav(1, '100'), nav(2, None, reason=('price_missing',))))
        self.assertIsNone(partial.twr.value)
        self.assertIsNone(partial.amount_pnl.value)
        self.assertIsNone(partial.gross_turnover.value)
        self.assertIsNone(self.calculate((nav(1, '100'), nav(2, '100')), benchmark=-1).benchmark_relative_wealth.value)

    def test_fx_evaluation_gain_is_not_fx_transaction_cost(self):
        r = self.calculate((nav(1, '130000'), nav(2, '132000')))
        self.assertEqual(r.amount_pnl.value, '2000')
        self.assertEqual(r.gross_turnover.value, '0')
        self.assertEqual(quantize(Fraction('1.025'), '0.05'), '1')
        self.assertEqual(quantize(Fraction('1.075'), '0.05'), '1.1')
        self.assertEqual(quantize(Fraction('-1.025'), '0.05'), '-1')

    def test_actual_sale_fee_tax_and_slippage_no_double_count_golden(self):
        points, events, fact = sale_fixture()
        r = build_bound_performance(points, events, costs=(fact,))
        self.assertEqual((points[0].snapshot.valuation.nav, points[-1].snapshot.valuation.nav), ('2000', '1985'))
        self.assertEqual((r.twr.value, r.amount_pnl.value), ('-0.0075', '-15'))
        self.assertEqual(tuple(a.amount for a in fact.allocations), ('2', '3'))
        self.assertEqual(fact.slippage, 10)
        self.assertEqual(r.traded_notional.value, '990')
        self.assertTrue(all(h.cost_basis is None for h in points[0].snapshot.holdings))

    def test_summary_cannot_be_resealed_with_false_math(self):
        r = self.calculate((nav(1, '100'), nav(2, '110')))
        with self.assertRaises(ContractError):
            replace(r, twr=known(99))
        with self.assertRaises(ContractError):
            replace(r, gross_turnover=known(99))
