"""합성 원장 결정과 순수 재생. 영속 어댑터도 동일한 결과를 대조한다."""
from dataclasses import dataclass, field, replace
from hashlib import sha256

from quantharbor.domain.ledger import (
    AppendResult, CashBalance, CashLeg, ContractError, LedgerEvent, LedgerEventBody,
    LedgerProjection, MAX_EVENTS, MAX_SEQUENCE, PositionDelta, REDUCER_VERSION,
    SyntheticLedgerSubmission, exact, hash_record, identifier, instant, integer,
    scaled, unscaled, choice,
)


@dataclass(frozen=True, slots=True)
class Decision:
    submission: SyntheticLedgerSubmission
    submission_hash: str
    recorded_at: str
    result: AppendResult


@dataclass
class LedgerState:
    account_ref: str
    cursor: int = 0
    recorded_at: str | None = None
    events: list[LedgerEvent] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    projections: list[LedgerProjection] = field(default_factory=list)


def event_id(account_ref, sequence):
    return 'ledger:' + sha256(account_ref.encode('ascii')).hexdigest()[:16] + ':' + str(sequence)


def projection_id(account_ref, cursor, as_of, cutoff, mode, supersedes):
    return 'projection:' + sha256('|'.join((account_ref, str(cursor), as_of, cutoff, mode,
                                           REDUCER_VERSION, supersedes or '')).encode('ascii')).hexdigest()


def _latest(state, submission):
    matches = [e for e in state.events if e.body.kind == 'replacement' and
               e.body.submission.identity[:2] == submission.identity[:2]]
    return matches[-1] if matches else None


def _active(state):
    reversed_ids = {e.body.correction_of for e in state.events if e.body.kind == 'reversal'}
    return [e for e in state.events if e.body.kind == 'replacement' and e.body.event_id not in reversed_ids]


def _semantics(state, s, previous):
    if not s.completeness.complete or not s.completeness.costs_known or not s.completeness.semantics_known:
        return 'incomplete_input'
    if not s.evidence_refs:
        return 'evidence_missing'
    if s.event_type == 'unsupported' or s.revision_mode == 'unsupported':
        return 'unsupported_semantics'
    totals = {}
    for leg in s.cash_legs:
        totals[leg.currency] = totals.get(leg.currency, 0) + scaled(leg.amount)
    if any(totals.values()):
        return 'unbalanced_journal'
    if any(scaled(x.amount) == 0 for x in (*s.cash_legs, *s.position_deltas)):
        return 'zero_leg'
    cash = {(x.account, x.currency): scaled(x.amount) for x in s.cash_legs}
    accounts = {x.account for x in s.cash_legs}
    currencies = {x.currency for x in s.cash_legs}
    if s.event_type != 'baseline' and s.baseline is not None:
        return 'baseline_misuse'
    if s.event_type != 'split' and s.split_ratio is not None:
        return 'ratio_misuse'
    dependencies = []
    for ref in s.dependency_refs:
        dependency = next((e for e in _active(state) if e.body.event_id == ref), None)
        if dependency is None or dependency.body.effective_at > s.effective_at:
            return 'dependency_unresolved'
        dependencies.append(dependency)
    if s.event_type == 'baseline':
        if previous is None and state.events:
            return 'baseline_requires_first'
        if s.baseline is None or not s.baseline.cash_complete or not s.baseline.positions_complete:
            return 'baseline_incomplete'
        if s.dependency_refs or accounts - {'settled_cash', 'opening_equity'}:
            return 'baseline_shape'
        if any(x.basis != 'settlement' for x in s.cash_legs) or any(scaled(x.amount) < 0 for x in s.position_deltas):
            return 'baseline_shape'
        return None
    if s.event_type == 'split':
        if previous is not None:
            return 'split_revision_unsupported'
        if s.cash_legs or len(s.position_deltas) != 1 or s.split_ratio is None:
            return 'split_shape'
        p = replay(state, as_of=s.effective_at, knowledge_cutoff=state.recorded_at or s.effective_at)
        if not p.baseline_known or p.reason_codes:
            return 'split_basis_unknown'
        pos = s.position_deltas[0]
        old = next((scaled(x.amount) for x in p.holdings if x.key == pos.key), 0)
        if old <= 0 or (old + scaled(pos.amount)) * s.split_ratio.denominator != old * s.split_ratio.numerator:
            return 'split_ratio_mismatch'
        return None
    if s.event_type == 'trade':
        if len(s.position_deltas) != 1 or len(s.cash_legs) != 2 or len(currencies) != 1:
            return 'trade_shape'
        buying = scaled(s.position_deltas[0].amount) > 0
        target = 'unsettled_payable' if buying else 'unsettled_receivable'
        if accounts != {target, 'trade_clearing'} or any(x.basis != 'trade' for x in s.cash_legs):
            return 'trade_shape'
        amount = next(x for (a, c), x in cash.items() if a == target)
        return None if (amount < 0) == buying else 'trade_direction'
    if s.position_deltas:
        return 'unexpected_position_delta'
    if s.event_type == 'settlement':
        if len(dependencies) != 1 or dependencies[0].body.submission.event_type != 'trade':
            return 'settlement_dependency'
        trade = dependencies[0]
        for other in _active(state):
            if previous is not None and other.body.event_id == previous.body.event_id:
                continue
            if other.body.submission.event_type == 'settlement' and trade.body.event_id in other.body.submission.dependency_refs:
                return 'already_settled'
        outstanding = [x for x in trade.body.cash_legs if x.account.startswith('unsettled_')]
        expected = {(x.account, x.currency): -scaled(x.amount) for x in outstanding}
        for x in outstanding:
            expected['settled_cash', x.currency] = scaled(x.amount)
        if cash != expected or any(x.basis != 'settlement' for x in s.cash_legs):
            return 'settlement_shape'
        return None
    if s.event_type == 'fx':
        if len(s.cash_legs) != 4 or currencies != {'KRW', 'USD'} or accounts != {'settled_cash', 'fx_clearing'}:
            return 'fx_shape'
        if any(x.basis != 'settlement' for x in s.cash_legs) or cash['settled_cash', 'KRW'] * cash['settled_cash', 'USD'] >= 0:
            return 'fx_shape'
        return None
    counterparty, sign = {'fee': ('fee_expense', -1), 'tax': ('tax_expense', -1),
        'deposit': ('external_flow', 1), 'withdrawal': ('external_flow', -1),
        'dividend': ('dividend_income', 1)}[s.event_type]
    if len(s.cash_legs) != 2 or len(currencies) != 1 or accounts != {'settled_cash', counterparty}:
        return 'cash_event_shape'
    if any(x.basis != 'settlement' for x in s.cash_legs):
        return 'cash_event_shape'
    return None if next(x for (a, c), x in cash.items() if a == 'settled_cash') * sign > 0 else 'cash_event_direction'


def _reason(state, s, now):
    previous = _latest(state, s)
    if s.source_revision == 1:
        if previous is not None or s.predecessor_revision is not None or s.correction_of is not None or s.revision_mode != 'original':
            return 'revision_link_invalid'
    else:
        if previous is None or s.source_revision != previous.body.submission.source_revision + 1:
            return 'predecessor_missing'
        if (s.predecessor_revision != previous.body.submission.source_revision or
                s.correction_of != previous.body.event_id or s.event_type != previous.body.submission.event_type):
            return 'revision_link_invalid'
        if previous.body.effective_at > now:
            return 'uneffective_revision'
        if s.revision_mode == 'retroactive':
            if s.effective_at != previous.body.effective_at:
                return 'effective_move_unsupported'
        elif s.revision_mode == 'prospective':
            if not s.effective_at > max(previous.body.effective_at, now):
                return 'prospective_time_invalid'
            if s.event_type == 'settlement' and s.dependency_refs != previous.body.submission.dependency_refs:
                return 'prospective_dependency_change_unsupported'
        else:
            return 'revision_mode_unsupported'
    return _semantics(state, s, previous)


def append_to_state(state, submission, *, recorded_at, reprocess=False):
    """호출자는 transaction 복사본에서 실행 후 전체 상태를 commit한다."""
    exact(submission, SyntheticLedgerSubmission)
    if type(reprocess) is not bool or submission.account_ref != state.account_ref:
        raise ContractError()
    submission_hash = hash_record(submission)
    now = instant(recorded_at)
    same_key = [d for d in state.decisions if d.submission.identity == submission.identity]
    accepted = next((d for d in same_key if d.result.status == 'accepted'), None)
    same = next((d for d in reversed(same_key) if d.submission_hash == submission_hash), None)
    if same is not None and (same.result.status == 'accepted' or not reprocess):
        return replace(same.result, status='duplicate')
    if state.recorded_at is not None and now < state.recorded_at:
        raise ContractError()
    reason = 'source_collision' if accepted is not None else _reason(state, submission, now)
    n = 1 if reason or submission.source_revision == 1 else 2
    if state.cursor + n > MAX_SEQUENCE or len(state.events) + n > MAX_EVENTS or len(state.decisions) >= MAX_EVENTS:
        raise ContractError()
    end = state.cursor + n
    ids = []
    bundle = event_id(state.account_ref, end).replace('ledger:', 'bundle:')
    if reason is None:
        previous = _latest(state, submission)
        payloads = [(submission, 'replacement', submission.correction_of)]
        if previous is not None:
            payloads.insert(0, (previous.body.submission, 'reversal', previous.body.event_id))
        for source, kind, correction in payloads:
            seq = state.cursor + 1
            sign = -1 if kind == 'reversal' else 1
            body = LedgerEventBody(1, 'synthetic', state.account_ref, event_id(state.account_ref, seq),
                seq, now, submission.effective_at, bundle, kind,
                *(('internal-reversal', event_id(state.account_ref, seq), 1) if kind == 'reversal' else source.identity),
                correction, hash_record(source), source,
                tuple(CashLeg(x.account, x.currency, unscaled(sign * scaled(x.amount)), x.basis) for x in source.cash_legs),
                tuple(PositionDelta(*x.key, unscaled(sign * scaled(x.amount))) for x in source.position_deltas))
            state.events.append(LedgerEvent(body, hash_record(body)))
            ids.append(body.event_id)
            state.cursor = seq
    state.cursor = end
    state.recorded_at = now
    result = AppendResult('quarantined' if reason else 'accepted', reason, end, tuple(ids), submission_hash, None)
    state.decisions.append(Decision(submission, submission_hash, now, result))
    projection = replay(state, as_of=now, knowledge_cutoff=now,
                        supersedes_projection_id=state.projections[-1].projection_id if state.projections else None)
    hash_record(projection)  # Also checks canonical output size before commit.
    state.projections.append(projection)
    result = replace(result, projection_id=projection.projection_id)
    state.decisions[-1] = replace(state.decisions[-1], result=result)
    return result


def replay(state, *, as_of, knowledge_cutoff, cursor=None, mode='as_known',
           reducer_version=REDUCER_VERSION, supersedes_projection_id=None):
    as_of, cutoff = instant(as_of), instant(knowledge_cutoff)
    choice(mode, ('as_known', 'restated'))
    choice(reducer_version, (REDUCER_VERSION,))
    if cursor is None:
        cursor = state.cursor
    integer(cursor, 0)
    if cursor not in {0, *(d.result.cursor for d in state.decisions)}:
        raise ContractError()
    if supersedes_projection_id is not None:
        identifier(supersedes_projection_id)
        if not any(p.projection_id == supersedes_projection_id for p in state.projections):
            raise ContractError()
    selected = [e for e in state.events if e.body.sequence <= cursor and e.body.recorded_at <= cutoff and e.body.effective_at <= as_of]
    cash, positions, baselines = {}, {}, 0
    reasons = set()
    for e in selected:
        exact(e, LedgerEvent)
        b = e.body
        if b.submission.event_type == 'baseline':
            baselines += -1 if b.kind == 'reversal' else 1
        for x in b.cash_legs:
            key = (x.account, x.currency)
            cash[key] = cash.get(key, 0) + scaled(x.amount)
        for x in b.position_deltas:
            positions[x.key] = positions.get(x.key, 0) + scaled(x.amount)
    reversed_ids = {e.body.correction_of for e in selected if e.body.kind == 'reversal'}
    for e in selected:
        if e.body.kind == 'replacement' and e.body.event_id not in reversed_ids:
            if reversed_ids.intersection(e.body.submission.dependency_refs):
                reasons.add('correction_consequences_unresolved')
            if e.body.submission.event_type == 'split':
                keys = {x.key for x in e.body.position_deltas}
                # A late original/replacement can add a key absent from its reversal.
                # Preserve the existing reversal consequence rule for later corrections.
                if any(keys.intersection(x.key for x in r.body.position_deltas) and (
                       (r.body.kind == 'reversal' and
                        (r.body.sequence > e.body.sequence or r.body.effective_at > e.body.effective_at)) or
                       (r.body.kind == 'replacement' and r.body.sequence > e.body.sequence
                        and r.body.effective_at <= e.body.effective_at))
                       for r in selected):
                    reasons.add('correction_consequences_unresolved')
    decisions = [d for d in state.decisions if d.result.cursor <= cursor and d.recorded_at <= cutoff]
    for d in decisions:
        if d.result.status == 'quarantined' and d.submission.effective_at <= as_of:
            if not any(a.result.status == 'accepted' and a.submission_hash == d.submission_hash for a in decisions):
                reasons.add('quarantined_observation')
    baseline_known = baselines == 1
    if not baseline_known:
        reasons.add('baseline_missing')
    if any(v < 0 for v in positions.values()) or any(v < 0 for (a, c), v in cash.items() if a in ('settled_cash', 'unsettled_receivable')) or any(v > 0 for (a, c), v in cash.items() if a == 'unsettled_payable'):
        reasons.add('economic_balance_invalid')
    result = LedgerProjection(1, 'synthetic', state.account_ref,
        projection_id(state.account_ref, cursor, as_of, cutoff, mode, supersedes_projection_id),
        cursor, as_of, cutoff, mode, reducer_version, supersedes_projection_id,
        tuple(CashBalance(a, c, unscaled(v)) for (a, c), v in sorted(cash.items())),
        tuple(PositionDelta(*key, unscaled(v)) for key, v in sorted(positions.items())),
        baseline_known, not reasons, tuple(sorted(reasons)), None, None, None,
        'availability_semantics_unverified')
    hash_record(result)
    return result
