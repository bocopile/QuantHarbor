from dataclasses import replace
from fractions import Fraction
import unittest

from quantharbor.application.research import validate_trade_costs
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.research import CostAllocation, InputRef, TradeCostFact, known, unknown
from quantharbor.domain.valuation import PositionKey
from quantharbor.research.costing import calculate_basis
from synthetic_research import ACCOUNT, TIMES, fixed_inputs

KEY = PositionKey('golden-stock', 'synthetic-venue', 'mapping-v1', 'share')


def fact(i, side, quantity, price, cost='0', reference=None, quantum='0.01'):
    # 독립 산식 fixture: event refs의 원천 연결은 별도 builder 시험에서 확인한다.
    notional = Fraction(quantity) * Fraction(price)
    allocations = ()
    if cost != '0':
        rate = {Fraction(1000): '0.01', Fraction(2000): '0.005', Fraction(900): '0.003333'}[notional]
        allocations = (CostAllocation(InputRef('event', 'cost-' + str(i), format(i + 100, '064x')),
            1, 'fee', cost, rate),)
    return TradeCostFact(1, 'synthetic', ACCOUNT, InputRef('event', 'trade-' + str(i), format(i, '064x')),
        1, KEY, 'USD', TIMES[min(i, 3) - 1], side, quantity, reference or price, price, quantum,
        allocations, known(notional, ratio=False))


class CostingTests(unittest.TestCase):
    def test_independent_moving_average_golden(self):
        facts = (fact(1, 'buy', '10', '100', '10'), fact(2, 'buy', '10', '200', '10'), fact(3, 'sell', '5', '180', '3'))
        result = calculate_basis(ACCOUNT, KEY, 'USD', '0.01', facts, known(2700, ratio=False))
        self.assertEqual((result.quantity.value, result.remaining_basis.value, result.realized_pnl.value,
                          result.unrealized_pnl.value), ('15', '2265', '142', '435'))
        with self.assertRaises(ContractError):
            replace(result, realized_pnl=known(999, ratio=False))

    def test_full_close_removes_all_basis_after_rounding(self):
        facts = (fact(1, 'buy', '3', '0.05', quantum='0.05'), fact(2, 'sell', '1', '0.1', quantum='0.05'), fact(3, 'sell', '2', '0.1', quantum='0.05'))
        result = calculate_basis(ACCOUNT, KEY, 'USD', '0.05', facts, known(0, ratio=False))
        self.assertEqual((result.quantity.value, result.remaining_basis.value, result.realized_pnl.value), ('0', '0', '0.15'))

    def test_unknown_basis_actions_and_valuation_are_not_false_zero(self):
        for kwargs in (dict(opening_quantity='1'), dict(supported=False)):
            result = calculate_basis(ACCOUNT, KEY, 'USD', '0.01', (), known(0, ratio=False), **kwargs)
            self.assertIsNone(result.remaining_basis.value)
            self.assertIsNone(result.realized_pnl.value)
        result = calculate_basis(ACCOUNT, KEY, 'USD', '0.01', (fact(1, 'buy', '1', '100'),), unknown('price_missing'))
        self.assertEqual(result.remaining_basis.value, '100')
        self.assertIsNone(result.unrealized_pnl.value)
        self.assertIsNone(result.attribution.value)

    def test_no_short_or_duplicate_trades(self):
        with self.assertRaises(ContractError):
            calculate_basis(ACCOUNT, KEY, 'USD', '0.01', (fact(1, 'sell', '1', '100'),), known(0, ratio=False))
        f = fact(1, 'buy', '1', '100')
        with self.assertRaises(ContractError):
            calculate_basis(ACCOUNT, KEY, 'USD', '0.01', (f, f), known(200, ratio=False))

    def test_slippage_is_in_fill_not_a_second_cash_charge(self):
        sell = fact(1, 'sell', '10', '99', reference='100')
        self.assertEqual(sell.slippage, 10)
        self.assertEqual(sell.notional, 990)

    def test_actual_event_cost_allocation_is_unique_complete_and_bound(self):
        run = fixed_inputs()[2]
        validate_trade_costs(run.events, run.costs)
        with self.assertRaises(ContractError):
            validate_trade_costs(run.events, run.costs[1:])
        with self.assertRaises(ContractError):
            validate_trade_costs(run.events, (*run.costs, run.costs[0]))
        f = run.costs[0]
        with self.assertRaises(ContractError):
            validate_trade_costs(run.events, (replace(f, allocations=()), *run.costs[1:]))
        with self.assertRaises(ContractError):
            validate_trade_costs(run.events, (replace(f, revision=2), *run.costs[1:]))
        with self.assertRaises(ContractError):
            validate_trade_costs(run.events, (replace(f, trade=replace(f.trade, sha256='0' * 64)), *run.costs[1:]))
