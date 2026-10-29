"""실제 계좌/시세에서 유래하지 않은 Q20 fixture."""
from dataclasses import replace
from quantharbor.domain.ledger import (SyntheticLedgerSubmission, CashLeg, PositionDelta,
    LedgerCompleteness, LedgerBaseline)

ACCOUNT = 'synthetic-account:ledger'
T0 = '2026-10-01T00:00:00.000000Z'
T1 = '2026-10-02T00:00:00.000000Z'
T2 = '2026-10-03T00:00:00.000000Z'
T3 = '2026-10-04T00:00:00.000000Z'
T4 = '2026-10-05T00:00:00.000000Z'


def cash_pair(account, amount, counterparty, *, currency='USD', basis='settlement'):
    from quantharbor.domain.ledger import negated
    return (CashLeg(account, currency, amount, basis), CashLeg(counterparty, currency, negated(amount), basis))


def submission(key='deposit', event_type='deposit', amount='100', *, effective_at=T0, **kwargs):
    values = dict(schema_version=1, environment='synthetic', account_ref=ACCOUNT,
        source_kind='synthetic-fixture', source_event_key=key, source_revision=1,
        predecessor_revision=None, mapping_version='mapping-v1', event_type=event_type,
        effective_at=effective_at, revision_mode='original', correction_of=None,
        cash_legs=cash_pair('settled_cash', amount, 'external_flow'), position_deltas=(),
        evidence_refs=('synthetic-evidence:ledger',), completeness=LedgerCompleteness(True, True, True),
        baseline=None, dependency_refs=(), split_ratio=None)
    values.update(kwargs)
    return SyntheticLedgerSubmission(**values)


def baseline():
    return submission('opening', 'baseline', cash_legs=cash_pair('settled_cash', '1000', 'opening_equity'),
        baseline=LedgerBaseline(True, True, 'entire_account'))


def trade(amount='10', cash='-100', **kwargs):
    return submission('execution', 'trade', effective_at=T1,
        cash_legs=cash_pair('unsettled_payable', cash, 'trade_clearing', basis='trade'),
        position_deltas=(PositionDelta('synthetic-stock', 'XNAS', 'mapping-v1', 'share', amount),), **kwargs)


def revision(source, event_id, *, amount='12', cash='-120', **kwargs):
    values = dict(source_revision=source.source_revision + 1, predecessor_revision=source.source_revision,
        correction_of=event_id, revision_mode='retroactive',
        cash_legs=cash_pair('unsettled_payable', cash, 'trade_clearing', basis='trade'),
        position_deltas=(replace(source.position_deltas[0], amount=amount),))
    values.update(kwargs)
    return replace(source, **values)
