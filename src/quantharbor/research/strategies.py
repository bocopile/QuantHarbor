"""고정 수량 신호와 합성 all-or-none 체결 규칙. IO/주문 API 없음."""
from dataclasses import dataclass
from fractions import Fraction

from quantharbor.domain.primitives import ContractError, identifier
from quantharbor.domain.ledger import choice
from quantharbor.domain.research import STRATEGIES
from quantharbor.domain.valuation import finite, number, quantize


@dataclass(frozen=True, slots=True)
class SignalOrder:
    instrument_id: str
    side: str
    quantity: str
    decision_price: str

    def __post_init__(self):
        identifier(self.instrument_id)
        choice(self.side, ('buy', 'sell'))
        if number(self.quantity) <= 0 or number(self.quantity) % 1 or number(self.decision_price) <= 0:
            raise ContractError()


def plan_orders(strategy, nav, prices, holdings, *, first):
    """prices/holdings는 검증된 두 종목의 명시 (id, 정확값) tuple이다."""
    choice(strategy, STRATEGIES)
    if type(first) is not bool or type(prices) is not tuple or len(prices) != 2 or len(set(k for k, _ in prices)) != 2:
        raise ContractError()
    if strategy == 'cash' or (strategy == 'buy_hold' and not first):
        return ()
    if number(nav) <= 0:
        raise ContractError()
    positions = dict(holdings)
    orders = []
    for key, price in prices:
        p = number(price)
        if p <= 0:
            raise ContractError()
        target = (number(nav) * Fraction(45, 100) / p).__floor__()
        diff = Fraction(target) - number(positions.get(key, '0'))
        if diff:
            orders.append(SignalOrder(key, 'buy' if diff > 0 else 'sell', finite(abs(diff)), price))
    return tuple(sorted(orders, key=lambda o: (o.side != 'sell', o.instrument_id)))


def adverse_price(reference, side, slippage, tick):
    choice(side, ('buy', 'sell'))
    ref, rate, q = number(reference), number(slippage), number(tick)
    if ref <= 0 or q <= 0 or not 0 <= rate < 1:
        raise ContractError()
    units = ref * (1 + rate if side == 'buy' else 1 - rate) / q
    return finite((units.__ceil__() if side == 'buy' else units.__floor__()) * q)


def fill_terms(order, reference, volume, market, costs, cash, holding):
    """신호 수량을 변경하지 않는다. reference는 다음 적격 봉의 종가다."""
    fill = adverse_price(reference, order.side, costs.slippage_rate, market.tick)
    notional = number(order.quantity) * number(fill)
    fee_rate = getattr(costs, 'fee_rate_' + order.side)
    tax_rate = getattr(costs, 'tax_rate_' + order.side)
    fee = quantize(notional * number(fee_rate), market.money_quantum)
    tax = quantize(notional * number(tax_rate), market.money_quantum)
    reason = 'filled'
    if number(order.quantity) % 1:
        reason = 'lot'
    elif number(order.quantity) > number(volume) / 10:
        reason = 'volume'
    elif notional < number(market.minimum_notional):
        reason = 'minimum_notional'
    elif order.side == 'sell' and number(order.quantity) > number(holding):
        reason = 'position'
    elif order.side == 'buy' and notional + number(fee) + number(tax) > number(cash):
        reason = 'cash'
    return fill, fee, tax, reason
