"""Q24 exact 계산을 확장하는 순수 실행 수학. 호출 결과는 권한이 아니다."""
from dataclasses import dataclass
from fractions import Fraction

from .execution import ExecutionCash, ReservationSlice, ExecutionDenied
from .ledger import exact
from .target import available_cash
from .valuation import finite, number


def cash_with_reservations(base, reservations, *, broker_amount=None, included=(), source_cutoff=None):
    """부분 이행을 H와 U/D에 각각 한 번 배치한다. 미청구 주문비용은 held다."""
    h, u, d = map(number, (base.outstanding, base.unreflected, base.post_source_debits))
    for r in reservations:
        exact(r, ReservationSlice)
        if r.dimension != 'cash' or r.currency_or_unit != base.currency:
            continue
        held, used, settled = map(number, (r.held, r.used, r.settled))
        if settled > used:
            raise ExecutionDenied('event_conflict')
        h += held + used - settled
        # 원금 사용량과 잔여분은 서로 다른 component identity다.
        held_included = r.obligation_id + ':held' in included
        used_included = r.obligation_id + ':used' in included
        if not held_included:
            u += held
        reflected = number(r.broker_reflected) if source_cutoff==r.source_cutoff else number('0')
        if reflected>used:
            raise ExecutionDenied('event_conflict')
        if not used_included:
            d += used-reflected
    b = base.broker_capacity if broker_amount is None else broker_amount
    a = available_cash(base.ledger_cash, finite(h), base.floor, b, finite(u), finite(d))
    return ExecutionCash(base.currency, base.ledger_cash, finite(h), base.floor, b, finite(u), finite(d), a)


def sellable(ledger, all_holds, broker, unreflected_holds, postquery_fills):
    values = tuple(number(x) for x in (ledger, all_holds, broker, unreflected_holds, postquery_fills))
    if any(v < 0 for v in values):
        raise ExecutionDenied()
    l,h,b,u,d = values
    return finite(min(l-h,b-u-d))


def one_sided(current, buys, sells):
    c,b,s = (number(x) for x in (current,buys,sells))
    if min(c,b,s) < 0 or s > c:
        raise ExecutionDenied('risk_blocked')
    return finite(c-s), finite(c+b)


def turnover(used, active, new, time_weighted_nav):
    if time_weighted_nav is None or number(time_weighted_nav) <= 0:
        raise ExecutionDenied('risk_blocked')
    return (number(used)+number(active)+number(new))/number(time_weighted_nav)


def prospective_loss(observed, extra, nav, observed_drawdown):
    if any(x is None for x in (observed,extra,nav,observed_drawdown)) or number(nav) <= 0:
        raise ExecutionDenied('risk_blocked')
    e = number(extra)
    return number(observed)+e, number(observed_drawdown)+e/number(nav)
