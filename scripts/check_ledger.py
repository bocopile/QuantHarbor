#!/usr/bin/env python3
"""Q20 실제 합성 PostgreSQL 검사. 인자/기존 DB/SQL/credential 입력 없음.

root가 sandbox 승인 범위에서 별도로 실행한다. 원시 SQL/daemon 오류를 출력하지 않는다.
단위 시험 fixture와 application oracle을 그대로 사용하며 어댑터의 실제 append를 검사한다.
"""
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests/product'))
from quantharbor.adapters.postgres_ledger import PostgresLedger, LedgerStorageError, _append_sql, _text
from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.domain.ledger import CashLeg, LedgerCompleteness, PositionDelta, SplitRatio, hash_record
from synthetic_ledger import ACCOUNT, T0, T1, T2, T3, T4, baseline, cash_pair, revision, submission, trade


class CheckFailure(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise CheckFailure(reason)


def plain(value):
    return json.loads(json.dumps(value))


def fingerprint(db, database='qh_synthetic'):
    # Explicit immutable and mutable financial tables; sorted by complete row text.
    names = ('ledger_stream', 'ledger_event', 'ledger_journal', 'ledger_decision', 'ledger_projection',
             'ledger_outbox', 'ledger_delivery', 'ledger_inbox', 'ledger_workstate', 'ledger_inbox_collision')
    parts = ["'" + name + "',(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') FROM qh." + name + ' t)' for name in names]
    return sha256(db._query('SELECT qh.ledger_canonical(jsonb_build_object(' + ','.join(parts) + '));', database=database).encode()).hexdigest()


def wait_for(db, condition):
    for _ in range(150):
        if db._query('SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE ' + condition + ');') == 't':
            return
        time.sleep(0.01)
    raise CheckFailure('session_synchronization_timeout')


def launch(db, statement):
    process = subprocess.Popen(db._psql(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=db._env)
    process.stdin.write(statement.encode())
    process.stdin.close()
    process.stdin = None
    return process


def finish(process, *, must_succeed=True):
    try:
        stdout, _ = process.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise CheckFailure('session_timeout') from None
    require((process.returncode == 0) == must_succeed, 'session_exit_mismatch')
    return stdout.decode().strip()


def check_l1_l2(db, append, checks):
    """Known economics, independently asserted in addition to the parity oracle."""
    accounts = []
    stock = PositionDelta('synthetic-stock', 'XNAS', 'mapping-v1', 'share', '20')

    def expect(s, at, status='accepted', reason=None):
        result = append(s, at)
        require((result.status, result.reason) == (status, reason), 'l1_l2_expected_append_status')
        if status == 'quarantined':
            require(result.event_ids == (), 'l1_l2_quarantine_created_events')
        return result

    def opening(label):
        account = 'synthetic-account:ledger-' + label
        accounts.append(account)
        initial = replace(baseline(), account_ref=account)
        result = expect(initial, T0)
        buy = replace(trade(), account_ref=account)
        expect(buy, T1)
        return initial, result, buy

    def project(account, *, qty='20', settled='1000', payable='-100', clearing='100',
                other=(), reasons=(), at=T4, cutoff=T4, cursor=None):
        p = db.replay(account, as_of=at, knowledge_cutoff=cutoff, cursor=cursor)
        require({(x.account, x.currency): x.amount for x in p.cash_balances} == {
            ('settled_cash', 'USD'): settled, ('opening_equity', 'USD'): '-1000',
            ('unsettled_payable', 'USD'): payable, ('trade_clearing', 'USD'): clearing},
            'l1_l2_expected_cash')
        require(p.holdings == (*other, replace(stock, amount=qty)), 'l1_l2_expected_holdings')
        require(p.baseline_known is True and p.complete is (not reasons) and p.reason_codes == reasons,
                'l1_l2_expected_completeness')
        require((p.available_cash, p.reserved_cash, p.broker_buy_capacity) == (None, None, None),
                'l1_l2_availability_invented')
        return p

    # A paid trade cannot be released by scheduling a future migration to trade B.
    initial, _, buy = opening('l1-migration')
    account = initial.account_ref
    # The original trade has the known second sequence in this fresh account.
    from quantharbor.application.ledger import event_id
    b = expect(replace(buy, source_event_key='execution-b'), T1)
    settle = replace(submission('settle', 'settlement', effective_at=T2,
        dependency_refs=(event_id(account, 2),),
        cash_legs=cash_pair('settled_cash', '-100', 'unsettled_payable')), account_ref=account)
    a = expect(settle, T2)
    history = project(account, settled='900', clearing='200', at=T2, cutoff=T2)
    migration = replace(settle, source_revision=2, predecessor_revision=1, correction_of=a.event_ids[-1],
        revision_mode='prospective', effective_at=T4, dependency_refs=b.event_ids)
    expect(migration, T3, 'quarantined', 'prospective_dependency_change_unsupported')
    project(account, settled='900', clearing='200', at=T3, cutoff=T3)
    require(project(account, settled='900', clearing='200', at=T2, cutoff=T2,
        cursor=history.ledger_cursor) == history, 'l1_historical_projection_changed')
    expect(replace(settle, source_event_key='settle-again', effective_at=T3), T3, 'quarantined', 'already_settled')
    for at in (T3, T4):
        project(account, settled='900', clearing='200', at=at, reasons=('quarantined_observation',))
    checks.append('l1_dependency_migration_quarantined_duplicate_guard_known_cash_complete_history')

    # The restriction leaves a prospective revision of the same dependency supported.
    initial, _, buy = opening('l1-same-dependency')
    account = initial.account_ref
    settle = replace(settle, account_ref=account, dependency_refs=(event_id(account, 2),))
    a = expect(settle, T2)
    expect(replace(settle, source_revision=2, predecessor_revision=1, correction_of=a.event_ids[-1],
        revision_mode='prospective', effective_at=T4), T3)
    for at in (T3, T4):
        project(account, qty='10', settled='900', payable='0', at=at)
    checks.append('l1_same_dependency_prospective_revision_still_complete')

    for cause in ('baseline-adds-key', 'late-original', 'late-at-split', 'replacement-adds-key'):
        initial, opening_result, buy = opening('l2-' + cause)
        account = initial.account_ref
        other = ()
        payable, clearing = '-100', '100'
        if cause == 'replacement-adds-key':
            other = (PositionDelta('other-stock', 'XNAS', 'mapping-v1', 'share', '5'),)
            other_buy = replace(buy, source_event_key='other-trade', cash_legs=cash_pair(
                'unsettled_payable', '-50', 'trade_clearing', basis='trade'), position_deltas=other)
            prior = expect(other_buy, T1)
            payable, clearing = '-150', '150'
        split = replace(submission('split', 'split', effective_at=T2, cash_legs=(),
            position_deltas=(replace(stock, amount='10'),), split_ratio=SplitRatio(2, 1)), account_ref=account)
        expect(split, T2)
        history = project(account, payable=payable, clearing=clearing, other=other, at=T2, cutoff=T2)
        if cause == 'baseline-adds-key':
            late = replace(initial, source_revision=2, predecessor_revision=1, revision_mode='retroactive',
                correction_of=opening_result.event_ids[-1], position_deltas=(replace(stock, amount='5'),))
        elif cause == 'replacement-adds-key':
            late = revision(other_buy, prior.event_ids[-1], amount='5', cash='-50',
                position_deltas=(replace(stock, amount='5'),))
        else:
            late = replace(buy, source_event_key='late-original', effective_at=T2 if cause == 'late-at-split' else T1,
                cash_legs=cash_pair('unsettled_payable', '-50', 'trade_clearing', basis='trade'),
                position_deltas=(replace(stock, amount='5'),))
        expect(late, T3)
        project(account, qty='25', payable='-100' if cause == 'baseline-adds-key' else '-150',
            clearing='100' if cause == 'baseline-adds-key' else '150',
            other=(replace(other[0], amount='0'),) if other else (),
            reasons=('correction_consequences_unresolved',))
        # The missing split delta stays uncomputed; the original known result remains complete.
        project(account, payable=payable, clearing=clearing, other=other, at=T2, cutoff=T2)
        require(project(account, payable=payable, clearing=clearing, other=other, at=T2, cutoff=T2,
            cursor=history.ledger_cursor) == history, 'l2_historical_projection_changed')
    checks.append('l2_baseline_new_key_late_original_equal_time_replacement_known_incomplete_history')

    for cause in ('later-effective', 'other-identity'):
        initial, _, buy = opening('l2-unaffected-' + cause)
        account = initial.account_ref
        expect(replace(submission('split', 'split', effective_at=T2, cash_legs=(),
            position_deltas=(replace(stock, amount='10'),), split_ratio=SplitRatio(2, 1)), account_ref=account), T2)
        pos = replace(stock, amount='5', instrument_id='other-stock' if cause == 'other-identity' else 'synthetic-stock')
        expect(replace(buy, source_event_key='unaffected', effective_at=T1 if cause == 'other-identity' else T3,
            cash_legs=cash_pair('unsettled_payable', '-50', 'trade_clearing', basis='trade'), position_deltas=(pos,)), T3)
        project(account, qty='20' if cause == 'other-identity' else '25', payable='-150', clearing='150',
            other=(pos,) if cause == 'other-identity' else ())
    checks.append('l2_other_identity_and_later_effective_original_remain_complete')
    return accounts


def check_database(db, checks):
    oracle = SyntheticLedger()
    submissions = 0

    def parity(s, at, reprocess=False):
        nonlocal submissions
        actual = db.append(s, recorded_at=at, reprocess=reprocess)
        expected = oracle.append(s, recorded_at=at, reprocess=reprocess)
        require(actual == expected, 'append_semantics_mismatch')
        require(db.replay(s.account_ref, as_of=at, knowledge_cutoff=at) ==
                oracle.replay(s.account_ref, as_of=at, knowledge_cutoff=at), 'projection_semantics_mismatch')
        records = json.loads(db._query("SELECT coalesce(jsonb_agg(jsonb_build_object('body',body,'payload_hash',payload_hash,'canonicalization_version',canonicalization_version) ORDER BY sequence),'[]') FROM qh.ledger_event WHERE account_ref=" + _text(s.account_ref) + ';'))
        require(records == plain([asdict(e) for e in oracle.state(s.account_ref).events]), 'event_hash_semantics_mismatch')
        state = oracle.state(s.account_ref)
        hashes = json.loads(db._query("SELECT jsonb_agg(payload_hash ORDER BY cursor) FROM qh.ledger_projection WHERE account_ref=" + _text(s.account_ref) + ';'))
        require(hashes == [hash_record(p) for p in state.projections], 'stored_projection_hash_mismatch')
        submissions += 1
        return actual

    def new_account(label, s):
        return replace(s, account_ref='synthetic-account:ledger-' + label)

    for version in (1, 2):
        db._query(db._migration_script(version))
    db._query('CREATE DATABASE qh_ledger_restore;')
    db._query(db._migration_script(2), database='qh_ledger_restore', expected=3, error_marker=b'migration_order')
    before = fingerprint(db)
    db._query(db._migration_script(2, '0'*64), expected=3, error_marker=b'migration_checksum_mismatch')
    require(fingerprint(db) == before, 'migration_tamper_changed_state')
    checks.append('migration_order_checksum_idempotency')

    parity(baseline(), T0)
    a = parity(trade(), T1)
    parity(trade(), T1)  # repeated snapshot/submission
    s2 = revision(trade(), a.event_ids[-1])
    b = parity(s2, T2)
    parity(s2, T2)
    s3 = revision(s2, b.event_ids[-1], amount='14', cash='-140')
    c = parity(s3, T3)
    parity(trade(), T3)  # old revision must never restore old economics
    for kwargs in ({'as_of': T1, 'knowledge_cutoff': T1},
                   {'as_of': T1, 'knowledge_cutoff': T3, 'mode': 'restated'},
                   {'as_of': T3, 'knowledge_cutoff': T3, 'cursor': 2}):
        require(db.replay(ACCOUNT, **kwargs) == oracle.replay(ACCOUNT, **kwargs), 'knowledge_replay_mismatch')
    db._query('SELECT qh.ledger_replay(' + ','.join((_text(ACCOUNT), _text(T3), _text(T3), '3')) + ');', expected=3, error_marker=b'ledger_cursor')
    parity(trade(amount='11'), T3)
    checks.append('revisions_repeated_snapshots_balanced_reversal_knowledge_cursor_hash_parity')

    # Settlement must use the same full-replacement rules as trade, including repeat delivery.
    settle = submission('settle', 'settlement', effective_at=T3, dependency_refs=(c.event_ids[-1],),
        cash_legs=cash_pair('settled_cash', '-140', 'unsettled_payable'))
    d = parity(settle, T3)
    parity(settle, T3)
    parity(replace(settle, source_event_key='double-settlement'), T3)
    settled_revision = replace(settle, source_revision=2, predecessor_revision=1, correction_of=d.event_ids[-1],
        revision_mode='retroactive', evidence_refs=('synthetic-evidence:settlement-revised',))
    e = parity(settled_revision, T3)
    parity(settled_revision, T3)
    s4 = revision(s3, c.event_ids[-1], amount='15', cash='-150')
    f = parity(s4, T4)
    require('correction_consequences_unresolved' in db.replay(ACCOUNT, as_of=T4, knowledge_cutoff=T4).reason_codes, 'correction_consequence_missing')
    resolved = replace(settled_revision, source_revision=3, predecessor_revision=2, correction_of=e.event_ids[-1],
        dependency_refs=(f.event_ids[-1],), cash_legs=cash_pair('settled_cash', '-150', 'unsettled_payable'))
    parity(resolved, T4)
    checks.append('settlement_revisions_repeats_correction_consequences_parity')

    prospective_account = 'synthetic-account:ledger-prospective'
    p0 = replace(baseline(), account_ref=prospective_account)
    p1 = replace(trade(), account_ref=prospective_account)
    parity(p0, T0)
    pa = parity(p1, T1)
    p2 = revision(p1, pa.event_ids[-1], revision_mode='prospective', effective_at=T3)
    pb = parity(p2, T2)
    for at in (T2, T3):
        require(db.replay(prospective_account, as_of=at, knowledge_cutoff=T2) ==
                oracle.replay(prospective_account, as_of=at, knowledge_cutoff=T2), 'prospective_replay_mismatch')
    parity(revision(p2, pb.event_ids[-1], amount='13'), T2)  # uneffective revision quarantined
    checks.append('prospective_and_uneffective_revision_parity')

    missing = new_account('missing', trade())
    parity(missing, T1)
    parity(new_account('missing', baseline()), T2)
    bad = replace(missing, source_event_key='unknown-cost', completeness=LedgerCompleteness(True, False, True))
    parity(bad, T2)
    unbalanced = new_account('unbalanced', submission(cash_legs=(CashLeg('settled_cash', 'USD', '1', 'settlement'), CashLeg('external_flow', 'KRW', '-1', 'settlement'))))
    parity(unbalanced, T1)
    for kind, amount, contra in (('deposit', '4', 'external_flow'), ('withdrawal', '-5', 'external_flow'),
        ('fee', '-1', 'fee_expense'), ('tax', '-2', 'tax_expense'), ('dividend', '3', 'dividend_income')):
        parity(submission(kind, kind, effective_at=T4, cash_legs=cash_pair('settled_cash', amount, contra)), T4)
    fx = submission('fx', 'fx', effective_at=T4, cash_legs=cash_pair('settled_cash', '-1300', 'fx_clearing', currency='KRW') + cash_pair('settled_cash', '1', 'fx_clearing'))
    parity(fx, T4)
    zero = new_account('zero-baseline', replace(baseline(), cash_legs=()))
    zero_a = parity(zero, T0)
    parity(replace(zero, source_revision=2, predecessor_revision=1, correction_of=zero_a.event_ids[-1],
                   revision_mode='retroactive', cash_legs=cash_pair('settled_cash', '1', 'opening_equity')), T1)
    checks.append('baseline_completeness_costs_currency_cash_event_fx_parity')

    sp0, sp1 = new_account('split', baseline()), new_account('split', trade())
    parity(sp0, T0)
    sp_a = parity(sp1, T1)
    split = new_account('split', submission('split', 'split', effective_at=T2, cash_legs=(),
        position_deltas=trade().position_deltas, split_ratio=SplitRatio(2, 1)))
    parity(split, T2)
    parity(revision(sp1, sp_a.event_ids[-1]), T3)
    require('correction_consequences_unresolved' in db.replay(sp1.account_ref, as_of=T3, knowledge_cutoff=T3).reason_codes, 'split_correction_consequence_missing')
    checks.append('split_ratio_and_correction_consequences_parity')

    regression_accounts = check_l1_l2(db, parity, checks)

    # Explicit retry after an observation lacked its predecessor; no auto promotion.
    re1 = new_account('reprocess', trade())
    re0 = new_account('reprocess', baseline())
    from quantharbor.application.ledger import event_id
    parity(re0, T0)
    re2 = revision(re1, event_id(re1.account_ref, 3))
    parity(re2, T1)
    parity(re1, T2)
    parity(re2, T3)
    parity(re2, T3, reprocess=True)
    checks.append('quarantine_explicit_reprocess_parity')

    # Every injected failure goes through the actual economic append path, including correction.
    for s in (submission('rollback', effective_at=T4), revision(s4, f.event_ids[-1], amount='16', cash='-160')):
        for boundary in ('events', 'projection', 'outbox'):
            before = fingerprint(db)
            db._query('BEGIN;\n' + _append_sql(s, T4, fault=boundary) + '\nCOMMIT;', expected=3, error_marker=b'ledger_injected')
            require(fingerprint(db) == before, 'append_rollback_state_changed')
    checks.append('append_and_reversal_bundle_rollback_every_boundary')

    # SQL text boundary bypasses Python on purpose: unknown fields, duplicate keys, nulls, enums,
    # exact numeric limits, JSON number and source revision syntax all must be rejected by DB.
    wire = plain(asdict(new_account('direct', submission())))
    invalids = []
    for amount in ('NaN', 'Infinity', '-Infinity', '1e2', '01', '+1', '1.0000000000000000001', '100000000000000000000', 1, True, None):
        x = plain(wire); x['cash_legs'][0]['amount'] = amount; invalids.append(json.dumps(x))
    for field, value in (('environment', None), ('environment', 'live'), ('source_revision', True),
                         ('source_revision', None), ('source_revision', 2147483648), ('event_type', 'unknown'),
                         ('effective_at', '2026-10-01T00:00:00.0000001Z'), ('effective_at', '2026-02-30T00:00:00Z'),
                         ('effective_at', '2101-01-01T00:00:00Z'), ('extra', 'unknown')):
        x = plain(wire); x[field] = value; invalids.append(json.dumps(x))
    x = plain(wire); del x['correction_of']; invalids.append(json.dumps(x))
    invalids.append(json.dumps(wire).replace('"schema_version": 1', '"schema_version": 1,"schema_version": 1'))
    invalids.append(json.dumps(wire).replace('"source_revision": 1', '"source_revision": 1e0'))
    before = fingerprint(db)
    for raw in invalids:
        db._query('SELECT qh.ledger_append(' + _text(raw) + ',' + _text(T4) + ');', expected=3, error_marker=b'ledger_contract')
        require(fingerprint(db) == before, 'invalid_sql_input_changed_state')
    normalized = new_account('normalized', submission(amount='1'))
    raw_normalized = plain(asdict(normalized))
    raw_normalized['cash_legs'][0]['amount'] = '1.000'
    raw_normalized['cash_legs'][1]['amount'] = '-1.00'
    raw_normalized['effective_at'] = '2026-10-01T23:59:00+23:59'
    direct = json.loads(db._query('SELECT qh.ledger_append(' + _text(json.dumps(raw_normalized)) + ',' + _text(T4) + ');'))
    expected = oracle.append(normalized, recorded_at=T4)
    require(direct == plain(asdict(expected)), 'direct_normalization_hash_mismatch')
    parity(normalized, T4)
    exact = new_account('exact', submission(amount='99999999999999999999.999999999999999999'))
    parity(exact, T4)
    before = fingerprint(db)
    overflow = replace(exact, source_event_key='overflow', cash_legs=cash_pair('settled_cash', '0.000000000000000001', 'external_flow'))
    db._query(_append_sql(overflow, T4), expected=3, error_marker=b'ledger_contract')
    require(fingerprint(db) == before, 'numeric_overflow_partial_commit')
    # Direct table CHECK cannot silently round input to scale18.
    event = a.event_ids[-1]
    for number in ('NaN', 'Infinity', '-Infinity', '1.0000000000000000001', '100000000000000000000'):
        statement = 'INSERT INTO qh.ledger_journal VALUES(' + ','.join((_text(ACCOUNT), _text(event), '32', _text('settled_cash'), _text('USD'), _text(number) + '::numeric', _text('settlement'))) + ');'
        db._query(statement, expected=3, error_marker=b'ledger_journal_amount_check')
    before = fingerprint(db)
    db._query('BEGIN; UPDATE qh.ledger_stream SET cursor=2147483647 WHERE account_ref=' + _text(exact.account_ref) + ';' +
              _append_sql(replace(exact, source_event_key='exhausted'), T4) + 'COMMIT;', expected=3, error_marker=b'ledger_limit')
    require(fingerprint(db) == before, 'sequence_exhaustion_partial_commit')
    checks.append('direct_sql_closed_schema_duplicate_keys_exact_numeric_and_overflow_rollback')

    # Commit-time journal and correction guards, and immutable rows.
    db._query('BEGIN; INSERT INTO qh.ledger_journal VALUES(' + ','.join((_text(ACCOUNT), _text(event), '32', _text('settled_cash'), _text('USD'), '1', _text('settlement'))) + '); COMMIT;', expected=3, error_marker=b'ledger_commit_journal')
    for table in ('ledger_event', 'ledger_decision', 'ledger_journal', 'ledger_projection', 'ledger_outbox'):
        db._query('DELETE FROM qh.' + table + ';', expected=3, error_marker=b'ledger_immutable')
    checks.append('immutable_rows_and_deferred_journal_validation')

    # Genuine two-session contention on the account row, then retry the same economic input.
    concurrent = new_account('concurrent', submission())
    first = launch(db, "BEGIN; SET application_name='qh_ledger_first';\n" + _append_sql(concurrent, T4) + '\nSELECT pg_sleep(3); COMMIT;')
    second = None
    try:
        wait_for(db, "application_name='qh_ledger_first' AND wait_event='PgSleep'")
        second = launch(db, "BEGIN; SET application_name='qh_ledger_second';\n" + _append_sql(concurrent, T4) + '\nCOMMIT;')
        wait_for(db, "application_name='qh_ledger_second' AND wait_event_type='Lock'")
        first_result = json.loads(finish(first))
        second_result = json.loads(finish(second))
        require(first_result['status'] == 'accepted' and second_result['status'] == 'duplicate', 'concurrency_duplicate_effect')
    finally:
        for p in (first, second):
            if p is not None and p.poll() is None:
                p.kill(); p.communicate()
    oracle.append(concurrent, recorded_at=T4)
    parity(concurrent, T4)
    checks.append('two_session_account_lock_same_revision_exactly_one_economic_append')

    # Simulate connection termination after economic work but before commit.
    before = fingerprint(db)
    disconnected = new_account('disconnect', submission())
    process = launch(db, "BEGIN; SET application_name='qh_ledger_disconnect';\n" + _append_sql(disconnected, T4) + '\nSELECT pg_sleep(30); COMMIT;')
    try:
        wait_for(db, "application_name='qh_ledger_disconnect' AND wait_event='PgSleep'")
        require(db._query("SELECT bool_and(pg_terminate_backend(pid)) FROM pg_stat_activity WHERE application_name='qh_ledger_disconnect';") == 't', 'connection_termination_failed')
        finish(process, must_succeed=False)
    finally:
        if process.poll() is None:
            process.kill(); process.communicate()
    require(fingerprint(db) == before, 'connection_loss_partial_commit')
    parity(disconnected, T4)
    checks.append('connection_termination_rollback_and_replay')

    message = oracle.outbox[-1]
    before = fingerprint(db)
    db._query('SELECT qh.ledger_consume(' + ','.join(map(_text, ('consumer', message.message_id, message.payload_hash))) + ',true);', expected=3, error_marker=b'ledger_injected')
    require(fingerprint(db) == before, 'inbox_workstate_partial_commit')
    require(db.consume('consumer', message.message_id, message.payload_hash) == 'accepted', 'consumer_first_delivery')
    require(db.consume('consumer', message.message_id, message.payload_hash) == 'duplicate', 'consumer_ack_loss_duplicate')
    require(db.consume('consumer', message.message_id, '0'*64) == 'collision', 'consumer_collision')
    db.acknowledge(message.message_id)
    # Reverse delivery order of multiple cursors for the same account.
    for m in reversed([m for m in oracle.outbox if m.account_ref == ACCOUNT]):
        db.consume('ordered', m.message_id, m.payload_hash)
    require(db._query('SELECT cursor FROM qh.ledger_workstate WHERE consumer=\'ordered\' AND account_ref=' + _text(ACCOUNT) + ';') == str(oracle.state(ACCOUNT).cursor), 'consumer_cursor_regressed')
    checks.append('inbox_workstate_atomicity_collision_ack_loss_out_of_order_delivery')

    # pg_dump contains this same economic path, its projections and delivery/work state.
    before = fingerprint(db)
    dump = db._run(db._compose + ['exec', '-T', 'db', 'pg_dump', '-U', 'qh_synthetic', '-d', 'qh_synthetic', '--no-owner', '--no-privileges'])
    db._run(db._psql('qh_ledger_restore'), data=dump)
    require(fingerprint(db, 'qh_ledger_restore') == before, 'restore_economic_state_mismatch')
    require(db._query('SELECT version,checksum FROM qh.schema_migrations ORDER BY version;', database='qh_ledger_restore') ==
            db._query('SELECT version,checksum FROM qh.schema_migrations ORDER BY version;'), 'restore_migrations_mismatch')
    for account_ref in (ACCOUNT, prospective_account, sp1.account_ref, *regression_accounts):
        query = 'SELECT qh.ledger_replay(' + ','.join(map(_text, (account_ref, T4, T4))) + ');'
        require(db._query(query, database='qh_ledger_restore') == db._query(query), 'restored_replay_mismatch')
    # Repeated restored revision is still duplicate and cannot reapply a reversal.
    require(json.loads(db._query(_append_sql(s4, T4), database='qh_ledger_restore'))['status'] == 'duplicate', 'restored_revision_duplicate_mismatch')
    require(fingerprint(db, 'qh_ledger_restore') == before, 'restored_duplicate_changed_state')
    checks.append('same_economic_path_dump_restore_replay_and_duplicate_revision')
    return submissions


def main():
    if len(sys.argv) != 1:
        print(json.dumps({'scope': 'Q20_synthetic_ledger', 'result': 'fail', 'reason': 'arguments_not_accepted'}))
        return 2
    started = time.monotonic()
    checks = []
    db = PostgresLedger()
    report = {'scope': 'Q20_synthetic_ledger', 'result': 'fail'}
    try:
        with db:
            count = check_database(db, checks)
        report.update(result='pass', parity_submissions=count, migration_sha256=db.migration_checksums)
        exit_code = 0
    except (LedgerStorageError, CheckFailure) as exc:
        report['reason'] = exc.reason if isinstance(exc, LedgerStorageError) else str(exc)
        exit_code = 1
    except (ValueError, TypeError, KeyError, OSError, IndexError):
        report['reason'] = 'invalid_synthetic_result'
        exit_code = 1
    report.update(checks=checks, cleanup=db.cleanup, elapsed_seconds=round(time.monotonic()-started, 3))
    print(json.dumps(report))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
