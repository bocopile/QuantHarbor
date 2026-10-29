"""독립 Q23 기대값용 합성 객체. production이 이 모듈을 import하지 않는다."""
from dataclasses import replace
from functools import lru_cache

from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.adapters.synthetic_research import fixed_experiment_inputs
from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
from quantharbor.application.valuation import build_snapshot
from quantharbor.domain.ledger import CashLeg, LedgerBaseline, LedgerCompleteness, SyntheticLedgerSubmission
from quantharbor.domain.research import FlowBoundary, InputRef, NavPoint
from quantharbor.application.research import nav_point
from quantharbor.domain.valuation import (BalanceScope, CurrencyQuantum, DOMAINS, ReconciliationPolicy,
    ValuationPolicy, ValuationRequest)
from quantharbor.ports.research import ResearchPointInput

ACCOUNT = 'synthetic-account:research-golden'
TIMES = tuple('2024-01-0' + str(i) + 'T00:00:00.000000Z' for i in range(1, 5))


@lru_cache(maxsize=1)
def fixed_inputs():
    return fixed_experiment_inputs()


def nav(index, value, *, cursor=None, at=None, reason=()):
    return NavPoint(InputRef('snapshot', 'independent-snapshot-' + str(index), format(index, '064x')),
        at or TIMES[index - 1], at or TIMES[index - 1], index if cursor is None else cursor, value, reason)


def flow_fixture(*, withdrawal=False, intruder=False, with_market=False):
    """100→110→+50→160→176 또는100→-80→20→20. 전부 실제 원장/스냅샷."""
    store, repo = SyntheticLedger(), SyntheticSnapshotRepository()
    policy = ValuationPolicy(1, 'synthetic', 'golden-valuation-v1', (), (), (CurrencyQuantum('USD', '0.01'),), 3600, 3600)
    reconciliation = ReconciliationPolicy(1, 'synthetic', 'golden-reconciliation-v1', (), ())
    scope = BalanceScope('entire_account', (), ('KRW', 'USD'), tuple(sorted(DOMAINS)))
    times, market_inputs = TIMES, ()
    if with_market:
        import synthetic_valuation as v
        times = (v.NOW, '2024-03-08T14:31:04Z', '2024-03-08T14:31:05Z')
        policy, market_inputs = v.policy(), (v.market(),)
    def append(key, kind, amount, at):
        target = 'opening_equity' if kind == 'baseline' else ('external_flow' if kind in ('deposit', 'withdrawal') else 'dividend_income')
        sign = '-' + amount if kind == 'withdrawal' else amount
        opposite = amount if kind == 'withdrawal' else '-' + amount
        s = SyntheticLedgerSubmission(1, 'synthetic', ACCOUNT, 'golden-synthetic', key, 1, None,
            'golden-mapping-v1', kind, at, 'original', None,
            (CashLeg('settled_cash', 'USD', sign, 'settlement'), CashLeg(target, 'USD', opposite, 'settlement')),
            (), ('golden:independent-source',), LedgerCompleteness(True, True, True),
            LedgerBaseline(True, True, 'entire_account') if kind == 'baseline' else None, (), None)
        r = store.append(s, recorded_at=at)
        assert r.status == 'accepted', r.reason
        return store.state(ACCOUNT).events[-1]
    def snapshot(at):
        p = store.replay(ACCOUNT, as_of=at, knowledge_cutoff=at)
        req = ValuationRequest(1, 'synthetic', ACCOUNT, 'golden-request-' + str(p.ledger_cursor),
            p.ledger_cursor, at, at, at, 'as_known', 'USD', 'research', policy.version, reconciliation.version, scope)
        return ResearchPointInput(build_snapshot(p, req, market_inputs, policy, reconciliation, repo), market_inputs)
    append('opening', 'baseline', '100', times[0])
    first = snapshot(times[0])
    if not withdrawal:
        append('income1', 'dividend', '10', times[1])
    before = snapshot(times[1])
    flow_event = append('external', 'withdrawal' if withdrawal else 'deposit', '80' if withdrawal else '50', times[1])
    if intruder:
        append('interleaved-income', 'dividend', '1', times[1])
    after = snapshot(times[1])
    if not withdrawal:
        append('income2', 'dividend', '16', times[2])
    last = snapshot(times[2])
    boundary = FlowBoundary(nav_point(before.snapshot), nav_point(after.snapshot), '-80' if withdrawal else ('51' if intruder else '50'),
        'USD', '0.01', (InputRef('event', flow_event.body.event_id, flow_event.payload_hash),))
    return (first, last), tuple(store.state(ACCOUNT).events), (before, after), boundary


def sale_fixture():
    """독립 계약 예제: NAV2000,10주100→fill99,fee2,tax3→NAV1985."""
    import synthetic_valuation as v
    from synthetic_ledger import submission, cash_pair
    from quantharbor.domain.ledger import PositionDelta, hash_record
    from quantharbor.domain.research import CostAllocation, TradeCostFact, known
    store = v.ledger(holdings=(replace(v.HOLDING, amount='10'),), cash='1000')
    market = v.market(records=(v.price_item('100'),))
    policy, reconciliation, repo = v.policy(), v.reconciliation_policy(), SyntheticSnapshotRepository()
    def point(as_of, cutoff):
        p = store.replay(v.ACCOUNT, as_of=as_of, knowledge_cutoff=cutoff)
        req = v.request(ledger_cursor=p.ledger_cursor, as_of=as_of, knowledge_cutoff=cutoff, evaluated_at=cutoff)
        return ResearchPointInput(build_snapshot(p, req, (market,), policy, reconciliation, repo), (market,))
    first = point(v.END, v.NOW)
    at, cutoff = '2024-03-08T14:31:04Z', '2024-03-08T14:31:05Z'
    def append(key, kind, legs, *, positions=(), deps=()):
        s = submission(key, kind, account_ref=v.ACCOUNT, effective_at=at, cash_legs=legs,
                       position_deltas=positions, dependency_refs=deps)
        r = store.append(s, recorded_at=cutoff)
        assert r.status == 'accepted', r.reason
        return store.state(v.ACCOUNT).events[-1]
    trade = append('sale', 'trade', cash_pair('unsettled_receivable', '990', 'trade_clearing', basis='trade'),
        positions=(PositionDelta(*v.KEY.key, '-10'),))
    append('settlement', 'settlement', (CashLeg('unsettled_receivable', 'USD', '-990', 'settlement'),
        CashLeg('settled_cash', 'USD', '990', 'settlement')), deps=(trade.body.event_id,))
    fee = append('fee', 'fee', cash_pair('settled_cash', '-2', 'fee_expense'), deps=(trade.body.event_id,))
    tax = append('tax', 'tax', cash_pair('settled_cash', '-3', 'tax_expense'), deps=(trade.body.event_id,))
    fact = TradeCostFact(1, 'synthetic', v.ACCOUNT, InputRef('event', trade.body.event_id, trade.payload_hash),
        1, v.KEY, 'USD', at, 'sell', '10', '100', '99', '0.01',
        (CostAllocation(InputRef('event', fee.body.event_id, fee.payload_hash), 1, 'fee', '2', '0.00202'),
         CostAllocation(InputRef('event', tax.body.event_id, tax.payload_hash), 1, 'tax', '3', '0.00303')),
        known(990, ratio=False))
    return (first, point(at, cutoff)), tuple(store.state(v.ACCOUNT).events), fact
