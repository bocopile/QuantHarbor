#!/usr/bin/env python3
"""root 전용 actual synthetic PostgreSQL 검사. unit discovery에서는 실행하지 않는다.

인자 없음, 기존 고정 image/자기 UUID project/local unix daemon만 사용한다.
raw daemon/SQL stderr는 출력하지 않는다. 미구현 EX를 통과로 집계하지 않는다.
"""
import sys
from pathlib import Path
from hashlib import sha256
import json
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'tests/product'))
from quantharbor.adapters.postgres_ledger import PostgresLedger,LedgerStorageError,_text
from quantharbor.adapters.postgres_execution import PostgresExecutionRepository
from quantharbor.adapters.execution_uow import ExecutionUnitOfWork,MAX_FRAME,MAX_CHUNK,MAX_CHUNK_FRAME
from quantharbor.domain import execution as d
from quantharbor.domain import approval as a
from synthetic_execution import DatabaseHarness,MANIFEST,AT
from synthetic_approval import policy as approval_policy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier,Event
from unittest.mock import patch
from dataclasses import replace
from synthetic_execution import BrokerFact
from quantharbor.application.approval import ApprovalApplication
from quantharbor.domain.valuation import number

MIGRATION=ROOT/'migrations/0003_synthetic_execution.sql'
# These are implementation gaps, not waived criteria or successful tests.
REMAINING=('control_actual_database_run_and_independent_reviews',
 'EX21_unsupported_earlier_cumulative_revision_successor_reinterpretation',
 'EX26_unsupported_zero_cost_and_settled_trade_dependency_corrections',
 'EX27_EX28_cancel_handoff_new_scenarios_authored_root_run_pending',
 'EX31_restart_rebind_manual_resume_new_scenarios_authored_root_run_pending',
 'EX32_EX37_exact_per_intent_row_index_byte_accounting_and_capacity_proof',
 'EX34_complete_SQL_auth_nonce_closed_schema_invariants_root_run_pending',
 'EX32_active3_terminal3_Q26_history_capacity_and_common_completion_reserve_proof')


class CheckFailure(Exception):
    def __init__(self,reason):
        self.reason=reason
        super().__init__(reason)


def require(condition,reason):
    if not condition: raise CheckFailure(reason)


def migration_script(db):
    checksum=sha256(MIGRATION.read_bytes()).hexdigest()
    return """BEGIN;
SELECT pg_advisory_xact_lock(5130001) IS NOT NULL;
DO $guard$ BEGIN
IF NOT EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version=2 AND checksum='%s') THEN RAISE EXCEPTION 'migration_order'; END IF;
IF EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version=3 AND checksum<>'%s') THEN RAISE EXCEPTION 'migration_checksum_mismatch'; END IF;
END $guard$;
SELECT NOT EXISTS(SELECT 1 FROM qh.schema_migrations WHERE version=3) AS apply_execution \\gset
\\if :apply_execution
%s
INSERT INTO qh.schema_migrations(version,checksum) VALUES(3,'%s');
\\endif
COMMIT;
"""%(db.migration_checksums[2],checksum,MIGRATION.read_text(),checksum)


def install(db):
    db._query(migration_script(db))
    db._query(migration_script(db))
    require(db._query('SELECT count(*) FROM qh.schema_migrations;')=='3','migration_count')


def rowcount(db,table):
    if table not in ('execution_intent','execution_claim','execution_outbox','execution_reservation','execution_broker_inbox','execution_attempt','ledger_event'):
        raise CheckFailure('runner_table')
    return int(db._query('SELECT count(*) FROM qh.'+table+';'))


def primary(db,checks,goldens):
    h=DatabaseHarness(db,available='900')
    approval=h.approved()
    require((approval.terms.quantity,approval.terms.limit_price,approval.terms.cost_bound,approval.terms.maximum_burden)==('3','100','2','302'),'EX01_candidate')
    challenge=h.admission_challenge(approval)
    for label in ('consumed','claim','intent','reservation','outbox','history','receipt','commit'):
        before=h.repo.fingerprint()
        try:
            with h.repo.inject_failure(label): h.app.execute(h.approver,challenge)
        except a.ApprovalDenied as failure:
            require(failure.reason=='commit_failed','EX04_fault_reason')
        else: raise CheckFailure('EX04_fault_not_raised')
        require(h.repo.fingerprint()==before,'EX04_fault_fingerprint_'+label)
    checks.append('EX04_actual_database_all_admission_faults_rollback')
    receipt=h.app.execute(h.approver,challenge)
    require(receipt.outcome=='applied','EX01_admission')
    before=h.repo.fingerprint()
    require(h.app.execute(h.approver,challenge)==receipt,'EX05_replay_receipt')
    require(h.repo.fingerprint()==before,'EX05_replay_no_write')
    require(tuple(rowcount(db,t) for t in ('execution_intent','execution_claim','execution_outbox','execution_reservation'))==(1,1,1,4),'EX01_atomic_rows')
    consumed=h.repo.head(h.approver,approval.approval_id)
    require(consumed.state=='consumed','EX01_consumed')
    goldens['candidate']={'quantity':'3','limit_price':'100','cost_bound':'2','maximum_burden':'302'}
    checks.extend(('EX01_actual_Q24_Q26_DB_admission','EX05_committed_command_lookup_no_second_intent'))
    other=PostgresExecutionRepository(db,h.authority,h.source,approval_policy(h.source),h.inputs,h.broker)
    require(other.fingerprint()==h.repo.fingerprint(),'EX35_shared_authority_second_connection')
    checks.append('EX35_two_facades_shared_registry_database_reload')
    broker_receipt=h.repo.dispatch(h.controller,consumed.consumed_intent_id)
    require(h.broker.received_count==1,'EX14_single_handoff')
    event=h.broker.issue_event(broker_receipt,0)
    for label in ('inbox','ledger','fill_reservation','fill_intent','fill_history','commit'):
        before=h.repo.fingerprint()
        try:
            with h.repo.inject_failure(label): h.repo.receive(event)
        except a.ApprovalDenied as failure:
            require(failure.reason=='commit_failed','EX24_fault_reason')
        else: raise CheckFailure('EX24_fault_not_raised')
        require(h.repo.fingerprint()==before,'EX24_fault_fingerprint_'+label)
    checks.append('EX24_actual_inbox_ledger_reservation_intent_faults_rollback')
    require(h.repo.receive(event)=='applied','EX06_fill')
    before=h.repo.fingerprint()
    require(h.repo.receive(event)=='duplicate' and h.repo.fingerprint()==before,'EX20_duplicate_fill')
    row=h.repo.account_cash(h.controller)[0]
    require((row.ledger,row.outstanding,row.floor,row.broker,row.unreflected,row.debits,row.available)==('1000','302','100','1000','202','100','598'),'EX06_cash_golden')
    p=db.replay(h.source.request.account_ref,as_of=AT,knowledge_cutoff=AT)
    require(p.holdings[0].amount=='1','EX06_Q20_quantity')
    require(next(x.amount for x in p.cash_balances if x.account=='unsettled_payable')=='-100','EX06_Q20_payable')
    goldens['partial_fill']={k:getattr(row,v) for k,v in [('L','ledger'),('H','outstanding'),('F','floor'),('B','broker'),('U','unreflected'),('D','debits'),('A','available')]}
    checks.extend(('EX06_actual_Q20_projection_DB_cash598','EX20_actual_duplicate_fill_once'))
    settlement=h.broker.issue_event(broker_receipt,1)
    require(h.repo.receive(settlement)=='applied','EX07_settlement')
    row=h.repo.account_cash(h.controller)[0]
    require((row.ledger,row.outstanding,row.broker,row.unreflected,row.debits,row.available)==('900','202','1000','202','100','598'),'EX07_cash_golden')
    goldens['settlement']={k:getattr(row,v) for k,v in [('L','ledger'),('H','outstanding'),('B','broker'),('U','unreflected'),('D','debits'),('A','available')]}
    checks.append('EX07_actual_Q20_settlement_no_reapply_cash598')
    outbox=json.loads(db._query('SELECT jsonb_agg(jsonb_build_array(message_id,payload_hash) ORDER BY cursor DESC) FROM qh.ledger_outbox;'))
    for mid,ph in outbox:
        h.repo.consume_ledger(mid,ph)
        h.repo.consume_ledger(mid,ph)
    require(db._query("SELECT count(*) FROM qh.ledger_inbox WHERE consumer='synthetic-execution';")==str(len(outbox)),'EX25_ledger_inbox')
    require(rowcount(db,'execution_broker_inbox')==2,'EX25_distinct_broker_inbox')
    checks.append('EX25_actual_reverse_duplicate_ledger_delivery_cursor_atomic')
    intent=h.repo.intent(h.controller,consumed.consumed_intent_id)
    cancel=h.repo.cancel(h.controller,intent.intent_id,command_id='cancel-1',expected_version=intent.state_version)
    require(cancel.maximum_remaining=='2' and cancel.state=='issued','EX27_cancel_bound')
    checks.append('EX27_DB_distinct_cancel_command_nonce_remaining_bound_only')

    fresh=h.broker.query(1)
    old_source=h.repo._source
    h.inputs=h.repo.refresh_current(h.controller,fresh)
    require(h.repo._source is old_source,'EX08_original_source_changed')
    bound=rows(db)
    require(bound['principal']['source_cutoff']==fresh.as_of and bound['principal']['broker_reflected']=='100','EX08_cutoff_reflection')
    row=h.repo.account_cash(h.controller)[0]
    require((row.ledger,row.outstanding,row.broker,row.unreflected,row.debits,row.available)==('900','202','900','202','0','598'),'EX08_cash_golden')
    # The second candidate reaches an actual new admission with the fresh cursor.
    next_approval=h.approved(1,label='next-approve')
    h.admit(next_approval,label='next-admit')
    require(h.repo.account_cash(h.controller)[0].available=='196','EX08_next_candidate')
    goldens['fresh_query']={'L':'900','H':'202','B':'900','U':'202','D':'0','A':'598','next_remaining':'196'}
    checks.append('EX08_EX33_actual_current_source_query_rebind_and_next_candidate_admission')

    db._query('SET ROLE qh_execution_product; UPDATE qh.execution_reservation SET body=body;',expected=3,error_marker=b'permission denied')
    db._query('SET ROLE qh_execution_product; DELETE FROM qh.execution_intent;',expected=3,error_marker=b'permission denied')
    checks.append('EX34_product_role_direct_financial_mutation_denied')


def crash(db,checks,goldens,*,before_handoff):
    h=DatabaseHarness(db)
    approval=h.admit(h.approved())
    try:
        with h.repo.inject_failure('before_handoff' if before_handoff else 'after_handoff'):
            h.repo.dispatch(h.controller,approval.consumed_intent_id)
    except a.ApprovalDenied: pass
    else: raise CheckFailure('EX16_crash_not_injected')
    require(h.broker.received_count==(0 if before_handoff else 1),'EX16_handoff_count')
    h.repo.recover()
    intent=h.repo.intent(h.controller,approval.consumed_intent_id)
    require(intent.state=='unknown','EX16_recovery_not_unknown')
    try: h.repo.dispatch(h.controller,intent.intent_id)
    except a.ApprovalDenied: pass
    else: raise CheckFailure('EX16_resent')
    require(h.broker.received_count==(0 if before_handoff else 1),'EX16_replayed_write')
    require(h.repo.account_cash(h.controller)[0].outstanding=='302','EX18_hold_released')
    rec=h.repo.reconcile(h.controller,h.broker.query())
    require(rec.result=='unresolved','EX18_empty_query_released_unknown')
    checks.append('EX16_EX18_actual_'+('before' if before_handoff else 'after')+'_handoff_crash_unknown_no_resend')


def withdrawal(db,checks,goldens):
    h=DatabaseHarness(db)
    approval=h.admit(h.approved())
    r=h.app.withdraw(h.controller,a.ref('approval',approval.approval_id,approval),command_id='protective-withdraw')
    require(r.outcome=='applied','EX15_protective_withdraw')
    intent=h.repo.intent(h.controller,approval.consumed_intent_id)
    require(intent.state=='aborted_unsent' and h.broker.received_count==0,'EX15_unsent')
    require(h.repo.account_cash(h.controller)[0].outstanding=='0','EX15_release')
    require(rowcount(db,'execution_claim')==1,'EX02_claim_removed')
    checks.append('EX02_EX15_EX29_DB_protective_withdraw_unsent_only_claim_preserved')


def contention(db,checks,goldens,*,winner=0):
    h=DatabaseHarness(db,available='600')
    approvals=(h.approved(0,label='approve-A'),h.approved(1,label='approve-B'))
    challenges=tuple(h.admission_challenge(x,label='admit-'+str(n)) for n,x in enumerate(approvals))
    other=PostgresExecutionRepository(db,h.authority,h.source,approval_policy(h.source),h.inputs,h.broker)
    facades=(h.repo,other)
    barrier,entered=Barrier(2),Event()
    started,finished={},{}
    def contender(n):
        started[n]=time.monotonic()
        barrier.wait(timeout=10)
        if n==winner:
            with facades[n]._lock:
                entered.set()
                result=facades[n].execute(h.approver,challenges[n])
        else:
            require(entered.wait(10),'EX03_gate_wait')
            result=facades[n].execute(h.approver,challenges[n])
        finished[n]=time.monotonic()
        return result
    # Two actual requests have started before either completes; the shared gate
    # orders them, and an independent SQL lock proves actual DB contention too.
    with ThreadPoolExecutor(max_workers=2) as pool:
        with ExecutionUnitOfWork(db,h.source.request.account_ref) as locked:
            futures=[pool.submit(contender,n) for n in (0,1)]
            for _ in range(300):
                waiting=db._query("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%execution_lock%');")
                if waiting=='t': break
                time.sleep(0.01)
            else: raise CheckFailure('EX03_actual_connection_not_blocked')
            require(len(started)==2 and not finished,'EX03_requests_not_concurrent')
            locked.commit()
        results=[f.result(timeout=45) for f in futures]
    require(results[winner].outcome=='applied' and results[1-winner].outcome=='rejected','EX03_winners')
    require(max(started.values())<min(finished.values()),'EX03_request_overlap')
    require(rowcount(db,'execution_intent')==1,'EX03_intent_count')
    remaining='298' if winner==0 else '198'
    require(h.repo.account_cash(h.controller)[0].available==remaining,'EX03_remaining')
    goldens['concurrency_winner_'+str(winner)]={'available':'600','burdens':['302','402'],'winners':1,'remaining':remaining}
    checks.append('EX03_EX35_concurrent_admission_requests_actual_DB_contention_winner_'+str(winner))


def commit_reply_loss(db,checks,goldens):
    h=DatabaseHarness(db)
    approval=h.approved()
    challenge=h.admission_challenge(approval)
    def lost_frame(uow):
        # The real connection executes COMMIT then exits before the response frame.
        # EOF is observed by the product; the durable result is queried separately.
        uow._exchange('COMMIT;\n\\quit',result=False)
    with patch.object(ExecutionUnitOfWork,'commit',lost_frame):
        try: h.app.execute(h.approver,challenge)
        except (d.ExecutionDenied,a.ApprovalDenied): pass
        else: raise CheckFailure('EX05_commit_reply_not_lost')
    require(rowcount(db,'execution_intent')==1,'EX05_commit_not_durable')
    before=h.repo.fingerprint()
    result=h.app.execute(h.approver,challenge)
    require(result.outcome=='applied' and h.repo.fingerprint()==before,'EX05_lookup_mutated')
    require(rowcount(db,'execution_intent')==1,'EX05_second_intent')
    checks.append('EX05_actual_connection_commit_response_frame_lost_lookup_once')


def duplicate_claims(db,checks,goldens):
    h=DatabaseHarness(db)
    first=h.approved(label='approval1')
    second=h.approved(label='approval2')
    h.admit(first,label='first')
    result=h.app.execute(h.approver,h.admission_challenge(second,label='second'))
    require(result.outcome=='rejected' and result.reason_code=='candidate_already_consumed','EX02_different_approval')
    require(h.repo.head(h.approver,second.approval_id).state=='approved','EX02_other_consumed')
    generation=h.repo.rotate(h.controller)
    require(db._query('SELECT generation FROM qh.execution_account;')==generation,'EX02_generation')
    db._query("INSERT INTO qh.execution_claim SELECT account_ref,environment,candidate_id,candidate_version,candidate_hash,'cross-generation-intent' FROM qh.execution_claim;",expected=3,error_marker=b'duplicate key')
    require(rowcount(db,'execution_claim')==1,'EX02_cross_generation_claim')
    checks.append('EX02_different_approval_rejected_cross_generation_SQL_claim_unique')


def financial_fact(identity,execution='e1',quantity='1',price='100',*,revision=1,predecessor=None,
                   sequence=1,semantics='delta',kind='fill',fee='0',tax='0'):
    return BrokerFact(identity,kind,semantics,execution,revision,predecessor,sequence,quantity,price,fee,tax,AT)


def rows(db):
    return json.loads(db._query("SELECT jsonb_object_agg(body->>'component',body) FROM qh.execution_reservation;"))


def conserved(db):
    # Multiple intents have the same component names; object_agg(component)
    # would silently discard one intent. Check every actual reservation row.
    actual=json.loads(db._query("SELECT coalesce(jsonb_agg(body ORDER BY intent_id,body->>'component'),'[]') FROM qh.execution_reservation;"))
    for r in actual:
        require(number(r['bound'])==number(r['held'])+number(r['used'])+number(r['released']),'EX39_reservation_conservation')


def multi_price(db,checks,goldens):
    facts=(financial_fact('price1',price='90'),financial_fact('price2','e2'),
        financial_fact('price1',quantity='2',price='95',revision=2,predecessor=1),financial_fact('late','e3'))
    h=DatabaseHarness(db,available='900',facts=facts)
    approval=h.admit(h.approved())
    # Fill can arrive after actual handoff but before receipt persistence.
    attempt,intent,deadline=h.repo._arm(h.controller,approval.consumed_intent_id)
    receipt=h.broker.handoff(attempt,intent)
    require(h.repo.receive(h.broker.issue_event(receipt,0))=='applied','EX20_before_ACK')
    h.repo._store_receipt(attempt,receipt)
    require(h.repo.intent(h.controller,intent.intent_id).state=='partially_filled','EX20_late_ACK_regressed')
    require(h.repo.receive(h.broker.issue_event(receipt,1))=='applied','EX39_second_price')
    require(rows(db)['principal']['used']=='190','EX39_two_price190')
    event=h.broker.issue_event(receipt,2)
    for stage in ('inbox','ledger','fill_reservation','fill_intent','fill_history','commit'):
        before=h.repo.fingerprint()
        try:
            with h.repo.inject_failure(stage): h.repo.receive(event)
        except a.ApprovalDenied as failure: require(failure.reason=='commit_failed','EX24_correction_fault')
        else: raise CheckFailure('EX24_correction_not_injected')
        require(h.repo.fingerprint()==before,'EX24_correction_fingerprint_'+stage)
    require(h.repo.receive(event)=='applied','EX39_correction')
    r=rows(db)
    require((r['principal']['held'],r['principal']['used'],r['cost']['held'])==('10','290','2'),'EX39_corrected_components')
    p=db.replay(h.source.request.account_ref,as_of=AT,knowledge_cutoff=AT)
    require(p.holdings[0].amount=='3' and next(x.amount for x in p.cash_balances if x.account=='unsettled_payable')=='-290','EX39_Q20_literal290')
    before=h.repo.fingerprint()
    require(h.repo.receive(event)=='duplicate' and h.repo.fingerprint()==before,'EX20_duplicate_economics')
    require(h.repo.receive(h.broker.issue_event(receipt,3))=='quarantined','EX23_late_fill')
    conserved(db)
    checks.extend(('EX20_actual_fill_before_ACK_late_ACK_no_regression','EX24_actual_correction_all_fault_fingerprints',
        'EX39_actual_multi_price190_revision290_Q20_conservation','EX23_actual_late_final_conflict_preserved'))
    goldens['multi_price']={'before_principal':'190','after_principal':'290','quantity':'3','principal_held':'10','cost_held':'2'}


def unknown_cost(db,checks,goldens):
    facts=(financial_fact('cost',fee=None,tax=None),financial_fact('cost',revision=2,predecessor=1,fee='1',tax='0.5'),
           financial_fact('settlement',kind='settlement'))
    h=DatabaseHarness(db,available='900',facts=facts)
    approval=h.admit(h.approved())
    receipt=h.repo.dispatch(h.controller,approval.consumed_intent_id)
    require(h.repo.receive(h.broker.issue_event(receipt,0))=='observed_incomplete','EX26_unknown')
    require(db._query("SELECT count(*) FROM qh.ledger_event WHERE source_kind='synthetic-execution';")=='0','EX26_false_known_cost')
    require(rows(db)['principal']['used']=='100' and rows(db)['cost']['held']=='2','EX26_conservative_hold')
    final=h.broker.issue_event(receipt,1)
    for stage in ('inbox','fill_trade','fill_fee','fill_tax','ledger','fill_reservation','fill_intent','fill_history','commit'):
        before=h.repo.fingerprint()
        try:
            with h.repo.inject_failure(stage): h.repo.receive(final)
        except a.ApprovalDenied as failure: require(failure.reason=='commit_failed','EX24_cost_fault')
        else: raise CheckFailure('EX24_cost_not_injected')
        require(h.repo.fingerprint()==before,'EX24_cost_fingerprint_'+stage)
    require(h.repo.receive(final)=='applied','EX26_finalization')
    require((rows(db)['cost']['held'],rows(db)['cost']['used'],rows(db)['cost']['settled'])==('0.5','1.5','1.5'),'EX26_cost_bound_once')
    require(h.repo.receive(h.broker.issue_event(receipt,2))=='applied','EX26_settlement')
    p=db.replay(h.source.request.account_ref,as_of=AT,knowledge_cutoff=AT)
    cash={x.account:x.amount for x in p.cash_balances}
    require((cash['settled_cash'],cash['fee_expense'],cash['tax_expense'],cash['unsettled_payable'])==('898.5','1','0.5','0'),'EX26_Q20_expense_literal')
    before=h.repo.fingerprint()
    require(h.repo.receive(final)=='duplicate' and h.repo.fingerprint()==before,'EX26_final_duplicate')
    conserved(db)
    checks.append('EX26_actual_unknown_complete_revision_fee1_tax0_5_settlement_once')


def cumulative(db,checks,goldens):
    facts=(financial_fact('c2','stream',quantity='3',sequence=2,semantics='cumulative'),
        financial_fact('c1','stream',price='90',semantics='cumulative'),
        financial_fact('c2','stream',quantity='2',sequence=2,semantics='cumulative',revision=2,predecessor=1))
    h=DatabaseHarness(db,available='900',facts=facts)
    approval=h.admit(h.approved())
    receipt=h.repo.dispatch(h.controller,approval.consumed_intent_id)
    out=h.broker.issue_event(receipt,0)
    require(h.repo.receive(out)=='quarantined','EX21_missing_predecessor')
    require(h.repo.receive(h.broker.issue_event(receipt,1))=='applied','EX21_predecessor')
    require(h.repo.reprocess(out)=='applied','EX21_explicit_reprocess')
    require(rows(db)['principal']['used']=='290','EX21_increment290')
    require(h.repo.receive(h.broker.issue_event(receipt,2))=='applied','EX21_cumulative_correction')
    require(rows(db)['principal']['used']=='190','EX21_correction190')
    conserved(db)
    checks.append('EX21_EX22_actual_cumulative_out_of_order_explicit_reprocess_prices_correction')


def sale(db,checks,goldens):
    facts=(financial_fact('sale'),financial_fact('settlement',kind='settlement'))
    h=DatabaseHarness(db,facts=facts,target_options={'holdings':('3','0'),'targets':('0',None)})
    approval=h.admit(h.approved())
    receipt=h.repo.dispatch(h.controller,approval.consumed_intent_id)
    require(h.repo.receive(h.broker.issue_event(receipt,0))=='applied','EX09_sale')
    require(h.repo.account_cash(h.controller)[0].available=='998','EX10_receivable_not_available')
    require(h.repo.receive(h.broker.issue_event(receipt,1))=='applied','EX10_sale_settlement')
    require(h.repo.account_cash(h.controller)[0].available=='998','EX10_stale_B_no_credit')
    require((rows(db)['quantity']['held'],rows(db)['quantity']['used'])==('2','1'),'EX09_quantity_reserve')
    conserved(db)
    checks.append('EX09_EX10_actual_sale_receivable_settlement_no_unproven_cash_capacity')


def negative_financial(db,checks,goldens):
    facts=(financial_fact('first'),financial_fact('first',price='99'),financial_fact('over','e2',quantity='4'),
        replace(financial_fact('revision',price='99',revision=2,predecessor=1),effective_at='2024-03-08T14:31:09.000000Z'))
    h=DatabaseHarness(db,facts=facts)
    first=h.approved(label='first-approval')
    second=h.approved(1,label='second-approval')
    first=h.admit(first,label='first-admission')
    challenge=h.admission_challenge(second,label='blocked-admission')
    receipt=h.repo.dispatch(h.controller,first.consumed_intent_id)
    require(h.repo.receive(h.broker.issue_event(receipt,0))=='applied','EX23_first')
    for n in (1,2,3):
        event=h.broker.issue_event(receipt,n)
        require(h.repo.receive(event)=='quarantined','EX23_negative_preserved')
        before=h.repo.fingerprint()
        require(h.repo.receive(event)=='duplicate' and h.repo.fingerprint()==before,'EX23_negative_duplicate')
    require(db._query("SELECT count(*) FROM qh.ledger_decision WHERE status='quarantined';")=='1','EX26_Q20_quarantine_not_preserved')
    require(rowcount(db,'execution_broker_inbox')==4,'EX23_missing_inbox')
    require(rows(db)['principal']['used']=='100','EX23_mutated_used')
    result=h.app.execute(h.approver,challenge)
    require(result.outcome=='rejected','EX23_new_order_not_blocked')
    p=db.replay(h.source.request.account_ref,as_of=AT,knowledge_cutoff=AT)
    require(not p.complete and 'quarantined_observation' in p.reason_codes,'EX26_Q20_incomplete')
    checks.append('EX23_EX26_actual_collision_overfill_Q20_quarantine_preserved_new_blocked')


def excessive_cost(db,checks,goldens):
    h=DatabaseHarness(db,facts=(financial_fact('excess',fee='2',tax='1'),))
    first=h.admit(h.approved())
    receipt=h.repo.dispatch(h.controller,first.consumed_intent_id)
    require(h.repo.receive(h.broker.issue_event(receipt,0))=='quarantined','EX26_excess_cost')
    p=db.replay(h.source.request.account_ref,as_of=AT,knowledge_cutoff=AT)
    cash={x.account:x.amount for x in p.cash_balances}
    require((cash['settled_cash'],cash['fee_expense'],cash['tax_expense'])==('997','2','1'),'EX26_excess_economics_dropped')
    require(h.repo.intent(h.controller,first.consumed_intent_id).accounting=='incomplete','EX26_excess_not_blocked')
    conserved(db)
    checks.append('EX26_actual_cost_over_bound_ledger_preserved_incomplete')


def obligations(db,checks,goldens):
    h=DatabaseHarness(db,obligations=True)
    approvals=(h.approved(0,label='a'),h.approved(1,label='b'))
    require(h.repo.account_cash(h.controller)[0].available=='800','EX38_initial800')
    h.admit(approvals[0],label='first')
    require(h.repo.account_cash(h.controller)[0].available=='498','EX38_first498')
    h.admit(approvals[1],label='second')
    require(h.repo.account_cash(h.controller)[0].available=='96','EX38_second96')
    checks.append('EX38_actual_obligations_two_admissions_800_498_96')



def corrected_current(db,checks,goldens,*,mode):
    # The same independent literal manifests drive local focused tests and this
    # actual DB composition. They contain no production-computed expectations.
    from synthetic_execution import CORRECTION_FACTS,CORRECTION_MANIFESTS
    facts=CORRECTION_FACTS[mode]
    h=DatabaseHarness(db,available='900',facts=facts,current_manifest=CORRECTION_MANIFESTS[mode])
    first=h.admit(h.approved())
    second=h.approved(1,label='correction-next-approve')
    other=PostgresExecutionRepository(db,h.authority,h.source,approval_policy(h.source),h.inputs,h.broker)
    receipt=h.repo.dispatch(h.controller,first.consumed_intent_id)
    for n in range(len(facts)):
        require(h.repo.receive(h.broker.issue_event(receipt,n))=='applied','correction_fill')
    original_source=h.repo._source
    query=h.broker.query(1)
    fresh=h.repo.refresh_current(h.controller,query)
    require(h.repo._source is original_source,'correction_original_source')
    require(other._registry['inputs'] is fresh,'correction_shared_current_binding')
    # Exact independent manifest consumption: actual Q20/Q21 reconciliation has
    # matched the independently issued statement, and cost/quantity use heads.
    p=fresh.current.current.snapshot.valuation.projection
    expected_qty='1' if mode=='cost' else '3' if mode=='multi' else '2'
    expected_notional='100' if mode=='cost' else '290' if mode=='multi' else '190'
    require(p.holdings[0].amount==expected_qty,'correction_literal_quantity')
    require(sum((x.notional for x in fresh.current.costs),number('0'))==number(expected_notional),'correction_literal_notional')
    require(fresh.current.current.snapshot.reconciliation_details.full_account_balances_matched,'correction_independent_reconcile')
    require(fresh.current.current.snapshot.reconciliation_details.statement==h.broker.statement(query),'correction_literal_statement')
    require(len(fresh.current.events)==int(db._query('SELECT count(*) FROM qh.ledger_event;')),'correction_history_lost')
    expected_pnl='-1.5' if mode=='cost' else '10'
    require(fresh.current.performance.amount_pnl.value==expected_pnl,'correction_Q23_pnl')
    expected_available='598'
    require(other.account_cash(h.controller)[0].available==expected_available,'correction_current_cash')
    # A second facade replays the source/current rights, Q20/Q21/Q23, risk and
    # actual DB admission; a prior allow decision cannot authorize this command.
    result=other.execute(h.approver,h.admission_challenge(second,label='correction-next-admit'))
    require(result.outcome=='applied','correction_next_admission')
    require(other.account_cash(h.controller)[0].available=='196','correction_next_cash')
    conserved(db)
    checks.append('EX08_EX21_EX22_EX26_EX33_EX35_actual_'+mode+'_Q20_Q21_Q23_currentrisk_next_admission')
    goldens['corrected_'+mode]={'quantity':expected_qty,'notional':expected_notional,'pnl':expected_pnl,
        'available':expected_available,'next_available':'196',
        'manifest_consumed':True,'all_history_preserved':True}


def finality(db,checks,goldens):
    h=DatabaseHarness(db,response='final_reject')
    first=h.admit(h.approved())
    attempt,intent,_=h.repo._arm(h.controller,first.consumed_intent_id)
    # A correctly typed, request-bound reseal is still not an issued receipt.
    fake=d.SyntheticBrokerReceipt('forged-final',h.broker._instance,intent.account_ref,intent.intent_id,
        attempt.attempt_id,intent.request_hash,None,1,AT,'final_reject','forged-journal')
    before=h.repo.fingerprint()
    for forged in (fake,replace(fake,issuer_instance='foreign-issuer'),True):
        try: h.repo._store_receipt(attempt,forged)
        except (a.ApprovalDenied,d.ExecutionDenied): pass
        else: raise CheckFailure('EX19_forged_finality_released')
        require(h.repo.fingerprint()==before,'EX19_forged_finality_mutated')
    require(rows(db)['principal']['held']=='300','EX19_held_before_real_finality')
    actual=h.broker.handoff(attempt,intent)
    require(actual.kind=='final_reject','EX19_actual_issuer_kind')
    h.repo._store_receipt(attempt,actual)
    require(h.repo.intent(h.controller,intent.intent_id).state=='rejected','EX19_actual_final_state')
    require((rows(db)['principal']['held'],rows(db)['principal']['released'],rows(db)['cost']['released'])==('0','300','2'),'EX19_actual_final_release')
    require(rowcount(db,'execution_claim')==1 and h.broker.received_count==1,'EX19_claim_and_one_handoff')
    checks.append('EX19_actual_issuer_finalreject_release_forged_hash_foreignissuer_bool_denied')


def sellable_bound(db,checks,goldens,*,quantity):
    # This DB check exercises the exact 7/8 boundary in current_risk. The full
    # fixed arithmetic decomposition (12-4,10-2-1) remains a separate unit golden.
    h=DatabaseHarness(db,broker_sellable=('7','0'),
        target_options={'holdings':('12','0'),'targets':('5' if quantity==7 else '4',None)})
    approval=h.approved()
    require(approval.terms.quantity==str(quantity),'EX09_original_candidate')
    result=h.app.execute(h.approver,h.admission_challenge(approval))
    require(result.outcome==('applied' if quantity==7 else 'rejected'),'EX09_DB_bound')
    require(rowcount(db,'execution_intent')==(1 if quantity==7 else 0),'EX09_DB_no_extra_intent')
    checks.append('EX09_actual_typed_DB_sellable7_quantity'+str(quantity)+'_'+result.outcome)


def append_external(db,source,*,key,index,quantity,price):
    from quantharbor.domain.ledger import SyntheticLedgerSubmission,CashLeg,PositionDelta,LedgerCompleteness
    buying=number(quantity)>0
    amount=number(quantity)*number(price)
    submission=SyntheticLedgerSubmission(1,'synthetic',source.request.account_ref,'synthetic-execution',key,
        1,None,'q24-mapping-v1','trade',AT,'original',None,
        (CashLeg('unsettled_payable' if buying else 'unsettled_receivable','USD',str(-amount),'trade'),
         CashLeg('trade_clearing','USD',str(amount),'trade')),
        (PositionDelta(*source.inputs.facts.covered_scope.positions[index].key,quantity),),
        ('independent-external-trade',),LedgerCompleteness(True,True,True),None,(),None)
    result=db.append(submission,recorded_at=AT)
    require(result.status=='accepted','external_trade_not_accepted')
    return result.event_ids[-1]



def settle_external(db,source,trade_id,amount):
    from quantharbor.domain.ledger import SyntheticLedgerSubmission,CashLeg,LedgerCompleteness
    submission=SyntheticLedgerSubmission(1,'synthetic',source.request.account_ref,'synthetic-execution','external-settlement',
        1,None,'q24-mapping-v1','settlement',AT,'original',None,
        (CashLeg('unsettled_payable','USD',amount,'settlement'),
         CashLeg('settled_cash','USD','-'+amount,'settlement')),(),
        ('independent-external-settlement',),LedgerCompleteness(True,True,True),None,(trade_id,),None)
    require(db.append(submission,recorded_at=AT).status=='accepted','external_settlement_not_accepted')


def risk_negative(db,checks,goldens,*,mode):
    # Original Q24 plan is independently eligible. New actual ledger events
    # change the complete account before the attempted DB admission.
    if mode=='exposure':
        manifest=dict(holdings=('0','5'),cash=(('settled_cash','1000'),('unsettled_payable','-100')),
            capacity='1000',sellable=('0','4'),cutoff=0)
        h=DatabaseHarness(db,target_options={'holdings':('0','4'),'targets':('0.5','3'),'lot':'0.5','fee':'0'},
            exposure_ceiling='500',current_manifest=manifest)
        next_=h.approved(0,label='risk-next')
        h.admit(h.approved(1,label='opposing-sale'),label='opposing-sale-admit')
        append_external(db,h.source,key='exposure-external',index=1,quantity='1',price='100')
        expected={'current':'500','active_opposing_sale':'100','new_buy':'50','one_sided':'550','limit':'500'}
    elif mode in ('daily','turnover'):
        manifest=dict(holdings=('4','0'),cash=(('settled_cash','400'),('unsettled_receivable','200')),
            capacity='400',sellable=('4','0'),cutoff=0)
        h=DatabaseHarness(db,target_options={'cash':'600','holdings':('4','0'),'targets':('0.5','3'),'lot':'0.5','fee':'0'},
            policy_changes={'max_daily_amount':'1000' if mode=='daily' else '10000000'},current_manifest=manifest)
        h.admit(h.approved(0,label='active-sale'),label='active-sale-admit')
        next_=h.approved(1,label='risk-next')
        trade_id=append_external(db,h.source,key='roundtrip-buy',index=1,quantity='2',price='100')
        settle_external(db,h.source,trade_id,'200')
        append_external(db,h.source,key='roundtrip-sell',index=1,quantity='-2',price='100')
        expected={'used':'400','active':'350','new':'300','total':'1050','NAV':'1000','turnover':'1.05'}
    else:
        manifest=dict(holdings=('1','0'),cash=(('settled_cash','1000'),('unsettled_payable','-140')),
            capacity='1000',sellable=('0','0'),cutoff=0)
        h=DatabaseHarness(db,target_options={'targets':(None,'1'),'fee':'15'},
            policy_changes={'max_loss_amount':'50' if mode=='loss' else '1000000',
                            'max_drawdown':'0.5' if mode=='loss' else '0.05'},current_manifest=manifest)
        next_=h.approved(0,label='risk-next')
        append_external(db,h.source,key='adverse-price',index=0,quantity='1',price='140')
        expected={'observed_loss':'40','worst_cost':'15','prospective_loss':'55','NAV':'960','loss_limit':'50','drawdown_limit':'0.05'}
    query=h.broker.query(1)
    fresh=h.repo.refresh_current(h.controller,query)
    require(fresh.current.current.snapshot.reconciliation_details.full_account_balances_matched,'risk_negative_reconcile')
    if mode in ('daily','turnover'):
        require(sum((f.notional for f in fresh.current.costs),number('0'))==400,'risk_actual_daily_usage400')
        require(fresh.current.performance.time_weighted_nav.value=='1000','risk_actual_time_weighted_NAV1000')
    elif mode in ('loss','drawdown'):
        require(fresh.current.performance.amount_pnl.value=='-40','risk_actual_observed_loss40')
    challenge=h.admission_challenge(next_,label='risk-negative-admit')
    before=rowcount(db,'execution_intent')
    # Observe the real function, without substituting an allow or risk result.
    import quantharbor.adapters.postgres_execution as adapter
    import quantharbor.application.execution as application
    with patch.object(adapter,'current_risk',wraps=adapter.current_risk) as computed, \
         patch.object(application,'prospective_loss',wraps=application.prospective_loss) as loss, \
         patch.object(application,'turnover',wraps=application.turnover) as gross:
        result=h.app.execute(h.approver,challenge)
        require(computed.call_count==1,'risk_negative_cached_allow')
        require(loss.call_count==1,'risk_negative_actual_all_scope_not_reached')
        if mode in ('loss','drawdown'):
            require(loss.call_args.args[:3]==('40','15','960'),'risk_actual_prospective_loss55')
        if mode=='turnover':
            require(gross.call_count==1 and gross.call_args.args==('400','650','0','1000'),'risk_actual_gross_turnover105')
        if mode=='daily':
            require(gross.call_count==0,'risk_daily_did_not_reject_before_turnover')
    require(result.outcome=='rejected' and result.reason_code=='risk_blocked','risk_negative_admitted')
    require(rowcount(db,'execution_intent')==before,'risk_negative_new_intent')
    require(h.repo.head(h.approver,next_.approval_id).state=='approved','risk_negative_consumed')
    goldens['risk_'+mode]=expected
    checks.append(('EX11' if mode=='exposure' else 'EX12' if mode in ('daily','turnover') else 'EX13')+
        '_actual_all_account_DB_'+mode+'_negative_no_cached_allow')

def control_cancel(db,checks,goldens,*,mode='ack'):
    h=DatabaseHarness(db)
    approval=h.admit(h.approved()); iid=approval.consumed_intent_id
    receipt=h.repo.dispatch(h.controller,iid)
    intent=h.repo.intent(h.controller,iid)
    command=h.repo.cancel(h.controller,iid,command_id='control-cancel',expected_version=intent.state_version)
    require(command.maximum_remaining=='3','cancel_maximum')
    if mode=='unknown': h.broker._cancel_response='timeout'
    before=rows(db)
    ack=h.repo.dispatch_cancel(h.controller,command.command_id)
    require(rows(db)==before,'cancel_ACK_released')
    require(h.repo.cancel_receipt(h.controller,command.command_id,intent_id=iid,expected_version=command.expected_version)==ack,'cancel_replay_receipt')
    require(h.repo.intent(h.controller,iid).state=='acknowledged','cancel_ACK_terminal')
    require(h.repo.receive(h.broker.issue_event(receipt,0))=='applied','cancel_fill')
    if mode=='ack':
        confirmation=h.broker.issue_event(ack,2)
        require(h.repo.receive(confirmation)=='applied','cancel_confirmation')
        require(h.repo.intent(h.controller,iid).state=='cancelled_remaining','cancel_not_terminal')
        principal=rows(db)['principal']
        require((principal['used'],principal['released'])==('100','200'),'cancel_confirmed_remainder_only')
        before=h.repo.fingerprint()
        require(h.repo.receive(confirmation)=='duplicate' and h.repo.fingerprint()==before,'cancel_duplicate_changed')
        require(h.repo.cancel(h.controller,iid,command_id=command.command_id,expected_version=command.expected_version).state=='confirmed','cancel_replay_lookup')
    else:
        require(ack is None,'cancel_timeout_receipt')
        try: h.repo.dispatch_cancel(h.controller,command.command_id)
        except a.ApprovalDenied: pass
        else: raise CheckFailure('cancel_unknown_retried')
        require(rows(db)['principal']['released']=='0','cancel_unknown_released')
    require(h.broker.received_count==2,'cancel_send_count')
    checks.append('EX27_EX28_actual_DB_cancel_'+mode+'_attempt_commit_ACK_hold_fill_finality_no_retry')


def control_cancel_conflict(db,checks,goldens):
    h=DatabaseHarness(db)
    approval=h.admit(h.approved()); iid=approval.consumed_intent_id
    receipt=h.repo.dispatch(h.controller,iid); intent=h.repo.intent(h.controller,iid)
    command=h.repo.cancel(h.controller,iid,command_id='conflict-cancel',expected_version=intent.state_version)
    try: h.broker.issue_event(receipt,2)
    except d.ExecutionDenied: pass
    else: raise CheckFailure('submit_receipt_cancel_authority')
    ack=h.repo.dispatch_cancel(h.controller,command.command_id)
    confirmation=h.broker.issue_event(ack,2)
    require(h.repo.receive(confirmation)=='quarantined','cancel_conflicting_quantity_clamped')
    require(rows(db)['principal']['released']=='0','cancel_conflict_released')
    require(h.repo.receive(h.broker.issue_event(receipt,0))=='applied','cancel_reverse_fill_lost')
    require(h.repo.intent(h.controller,iid).accounting=='incomplete','cancel_conflict_auto_cleared')
    checks.append('EX28_actual_DB_confirmation_before_fill_conflict_preserved_incomplete_hold')


def control_race(db,checks,goldens,*,first='dispatch',action='stop'):
    h=DatabaseHarness(db)
    approval=h.admit(h.approved()); iid=approval.consumed_intent_id
    ready=Barrier(2); waiting=Event()
    def protect():
        ready.wait(60); waiting.set()
        if action=='stop': return h.repo.control(h.controller,'stop')
        return h.app.withdraw(h.controller,a.ref('approval',approval.approval_id,approval),command_id='raced-withdraw')
    if first=='dispatch':
        original=h.repo._handoff_ready
        def final(*args,**kwargs):
            result=original(*args,**kwargs)
            ready.wait(60); require(waiting.wait(60),'control_race_wait_timeout')
            return result
        with patch.object(h.repo,'_handoff_ready',side_effect=final),ThreadPoolExecutor(2) as pool:
            f=pool.submit(protect); h.repo.dispatch(h.controller,iid); f.result(60)
        require(h.broker.received_count==1,'control_dispatch_winner_missing')
        require(rows(db)['principal']['released']=='0','control_after_handoff_released')
    else:
        # Both requests are real concurrent threads. Protective operation owns the
        # same gate first; dispatch attempts it while protection is in flight.
        def dispatch():
            ready.wait(60); require(waiting.wait(60),'control_race_wait_timeout')
            return h.repo.dispatch(h.controller,iid)
        with ThreadPoolExecutor(2) as pool:
            with h.repo._lock:
                future=pool.submit(dispatch); ready.wait(60)
                if action=='stop': h.repo.control(h.controller,'stop')
                else: h.app.withdraw(h.controller,a.ref('approval',approval.approval_id,approval),command_id='raced-withdraw')
                waiting.set()
            try: future.result(60)
            except a.ApprovalDenied: pass
            else: raise CheckFailure('control_protection_winner_dispatched')
        require(h.broker.received_count==0,'control_protection_late')
    require(h.repo.head(h.approver,approval.approval_id).state=='consumed','control_consumed_rewritten')
    require(rowcount(db,'execution_claim')==1,'control_claim_deleted')
    checks.append('EX15_EX17_EX29_actual_DB_two_threads_shared_Python_gate_'+first+'_before_'+action+
                  '_not_multi_process_isolation_proof')


def control_protect_rights(db,checks,goldens):
    from synthetic_approval import rights_changed
    h=DatabaseHarness(db)
    approval=h.admit(h.approved()); iid=approval.consumed_intent_id
    second=h.authority.issue_session('execution-controller')
    h.repo.change_permissions(h.controller,'execution-approver',('query',))
    h.repo.replace_source(h.controller,rights_changed(h.source))
    require(h.app.withdraw(second,a.ref('approval',approval.approval_id,approval),command_id='rights-protect').outcome=='applied','protect_rights_denied')
    require(h.repo.intent(second,iid).state=='aborted_unsent' and h.broker.received_count==0,'protect_unsent')
    checks.append('EX29_actual_DB_new_controller_session_withdraw_after_approve_report_risk_rights_loss')


def control_restart(db,checks,goldens,*,mode='corrected'):
    from quantharbor.adapters.synthetic_approval import SyntheticAuthority
    from synthetic_execution import CORRECTION_FACTS,CORRECTION_MANIFESTS
    if mode=='corrected':
        h=DatabaseHarness(db,facts=CORRECTION_FACTS['delta'],current_manifest=CORRECTION_MANIFESTS['delta'])
    elif mode=='quarantine':
        h=DatabaseHarness(db,facts=(BrokerFact('restart-overfill','fill','delta','overfill',1,None,1,'4','100','0','0',AT),))
    else: h=DatabaseHarness(db,response='timeout' if mode=='unknown' else 'accepted')
    approval=h.admit(h.approved()); iid=approval.consumed_intent_id
    late_attempt=late_receipt=None
    if mode=='before_handoff':
        try:
            with h.repo.inject_failure('before_handoff'): h.repo.dispatch(h.controller,iid)
        except a.ApprovalDenied: pass
    elif mode=='late_completion':
        late_attempt,intent,_=h.repo._arm(h.controller,iid)
        late_receipt=h.broker.handoff(late_attempt,intent)
    else:
        receipt=h.repo.dispatch(h.controller,iid)
        if mode=='corrected':
            for n in range(2): require(h.repo.receive(h.broker.issue_event(receipt,n))=='applied','restart_correction')
            h.inputs=h.repo.refresh_current(h.controller,h.broker.query(1))
        elif mode=='quarantine': require(h.repo.receive(h.broker.issue_event(receipt,0))=='quarantined','restart_quarantine')
    before_reservations=rows(db)
    before_claims=rowcount(db,'execution_claim'); before_ledger=rowcount(db,'ledger_event')
    generation=h.authority._generation
    fresh=SyntheticAuthority(tuple(h.authority._principals.values()),clock=h.clock)
    new=PostgresExecutionRepository.restart(db,fresh,h.source,approval_policy(h.source),h.repo._registry['inputs'],h.broker,expected_generation=generation)
    require(fresh._generation!=generation,'restart_old_generation')
    require(rows(db)==before_reservations,'restart_lost_reservations')
    require(rowcount(db,'execution_claim')==before_claims and rowcount(db,'ledger_event')==before_ledger,'restart_history_lost')
    for repository in (h.repo,new):
        try: repository.intent(h.controller,iid)
        except a.ApprovalDenied: pass
        else: raise CheckFailure('restart_old_handle_authority')
    controller=fresh.issue_session('execution-controller')
    require(new.intent(controller,iid).state==('unknown' if mode in ('unknown','before_handoff','late_completion') else ('partially_filled' if mode=='corrected' else 'acknowledged')),'restart_state')
    if mode=='corrected':
        rec=new.rebind(controller,h.broker.query(1))
        require(rec.result=='matched','restart_corrected_not_matched')
        new.control(controller,'resume')
        approver=fresh.issue_session('execution-approver')
        app=ApprovalApplication(new)
        candidate=h.source.artifacts.candidates[1]
        from quantharbor.domain.target import ref as tr
        _,ap=app.present(approver,tr('candidate',candidate.candidate_id,candidate))
        challenge=app.challenge(approver,a.ref('approval',ap.approval_id,ap),action='approve',command_id='restart-new-approval')
        require(app.execute(approver,challenge).outcome=='applied','restart_new_candidate_cannot_approve')
    else:
        if late_receipt is not None:
            new._store_receipt(late_attempt,late_receipt)
            require(new.intent(controller,iid).broker_order_id==late_receipt.broker_order_id,'restart_late_financial_fact_lost')
        query=h.broker.query()
        require(new.reconcile(controller,query).result=='unresolved','restart_unknown_quarantine_cleared')
        try: new.control(controller,'resume')
        except a.ApprovalDenied: pass
        else: raise CheckFailure('restart_auto_resume')
    checks.append('EX17_EX18_EX30_EX31_actual_DB_restart_new_issuer_'+mode+'_preserves_claims_history_hold')


def control_restart_reply_loss(db,checks,goldens):
    from quantharbor.adapters.synthetic_approval import SyntheticAuthority
    h=DatabaseHarness(db)
    authority=SyntheticAuthority(tuple(h.authority._principals.values()),clock=h.clock)
    old=h.authority._generation
    def lost_frame(uow):
        uow._exchange('COMMIT;\n\\quit',result=False)
    with patch.object(ExecutionUnitOfWork,'commit',lost_frame):
        try:
            PostgresExecutionRepository.restart(db,authority,h.source,approval_policy(h.source),h.inputs,h.broker,expected_generation=old)
        except d.ExecutionDenied: pass
        else: raise CheckFailure('restart_commit_response_not_lost')
    require(authority._repository is None,'restart_uncommitted_live_issuer')
    observed=PostgresExecutionRepository.current_runtime(db,h.source.request.account_ref)
    require(observed['generation']!=old and observed['mode']=='stopped','restart_commit_not_durable')
    try: h.repo.control(h.controller,'resume')
    except a.ApprovalDenied: pass
    else: raise CheckFailure('restart_old_issuer_still_authoritative')
    new=PostgresExecutionRepository.restart(db,authority,h.source,approval_policy(h.source),h.inputs,h.broker,expected_generation=observed['generation'])
    require(authority._repository is new and h.broker.received_count==0,'restart_reply_loss_auto_order')
    checks.append('EX31_actual_DB_restart_COMMIT_response_loss_CAS_observation_no_live_split_authority')


def control_cancel_fault(db,checks,goldens,*,phase):
    h=DatabaseHarness(db)
    approval=h.admit(h.approved()); iid=approval.consumed_intent_id
    h.repo.dispatch(h.controller,iid); intent=h.repo.intent(h.controller,iid)
    command=h.repo.cancel(h.controller,iid,command_id='fault-cancel',expected_version=intent.state_version)
    before=h.repo.fingerprint()
    try:
        with h.repo.inject_failure(phase): h.repo.dispatch_cancel(h.controller,command.command_id)
    except a.ApprovalDenied: pass
    else: raise CheckFailure('cancel_fault_not_injected')
    require(h.repo.fingerprint()!=before,'cancel_attempt_not_durable')
    require(rowcount(db,'execution_attempt')==2,'cancel_attempt_missing')
    h.repo.recover()
    try: h.repo.dispatch_cancel(h.controller,command.command_id)
    except a.ApprovalDenied: pass
    else: raise CheckFailure('cancel_fault_resent')
    require(h.broker.received_count==(1 if phase=='before_cancel_handoff' else 2),'cancel_fault_handoff_count')
    require(rows(db)['principal']['released']=='0','cancel_fault_released')
    checks.append('EX27_actual_DB_'+phase+'_durable_attempt_unknown_hold_no_resend')


def control_proven_unsent(db,checks,goldens,*,sent=False):
    from quantharbor.adapters.synthetic_approval import SyntheticAuthority
    h=DatabaseHarness(db,response='timeout' if sent else 'accepted')
    approval=h.admit(h.approved()); iid=approval.consumed_intent_id
    if sent: h.repo.dispatch(h.controller,iid)
    else:
        try:
            with h.repo.inject_failure('before_handoff'): h.repo.dispatch(h.controller,iid)
        except a.ApprovalDenied: pass
        else: raise CheckFailure('manual_unsent_fault_missing')
    old=h.authority._generation
    authority=SyntheticAuthority(tuple(h.authority._principals.values()),clock=h.clock)
    new=PostgresExecutionRepository.restart(db,authority,h.source,approval_policy(h.source),h.inputs,h.broker,expected_generation=old)
    controller=authority.issue_session('execution-controller')
    before=rows(db)
    if sent:
        try: new.resolve_unsent(controller,iid)
        except d.ExecutionDenied: pass
        else: raise CheckFailure('manual_unsent_guessed_absence')
        require(rows(db)==before,'manual_sent_released')
        require(h.broker.received_count==1,'manual_sent_count')
    else:
        receipt=new.resolve_unsent(controller,iid)
        require(receipt.kind=='proven_unsent','manual_unsent_receipt')
        require(new.intent(controller,iid).state=='aborted_unsent','manual_unsent_state')
        require(all(row['held']=='0' for row in rows(db).values()),'manual_unsent_hold')
        require(rowcount(db,'execution_claim')==1,'manual_unsent_claim_removed')
        rec=new.rebind(controller,h.broker.query())
        require(rec.result=='matched','manual_unsent_rebind')
        new.control(controller,'resume')
        require(h.broker.received_count==0,'manual_unsent_order')
    checks.append('EX19_EX30_EX31_actual_DB_explicit_issuer_unsent_'+('already_sent_refused' if sent else 'revoked_attempt_only_release_rebind_resume'))


def control_resume_binding(db,checks,goldens):
    manifest=dict(holdings=('0','0'),cash=(('settled_cash','1000'),),capacity='900',sellable=('0','0'),cutoff=0)
    h=DatabaseHarness(db,current_manifest=manifest)
    h.approved()
    second=h.authority.issue_session('execution-controller'); h.repo.control(h.controller,'stop')
    require(h.repo.reconcile(h.controller,h.broker.query()).result=='matched','resume_initial_match')
    try: h.repo.control(second,'resume')
    except a.ApprovalDenied: pass
    else: raise CheckFailure('resume_foreign_session_binding')
    changed=h.broker.query(1)
    require(h.repo.reconcile(h.controller,changed).result=='unresolved','resume_stale_current_capacity')
    h.repo.refresh_current(h.controller,changed)
    require(h.repo.reconcile(second,changed).result=='matched','resume_current_reconcile')
    h.repo.control(second,'resume')
    checks.append('EX30_actual_DB_resume_exact_session_source_hash_current_cash_qty_query_readset')



def literal_sell_holds(db,checks,goldens,*,quantity):
    from synthetic_execution import replacement_source
    manifest=dict(holdings=('12','0'),cash=(('settled_cash','1000'),('unsettled_receivable','100')),
        capacity='1000',sellable=('10','0'),cutoff=1,hold_reflections=('2',))
    h=DatabaseHarness(db,target_options={'holdings':('13','0'),'targets':('8',None)},
        facts=(financial_fact('sell-postquery'),),current_manifest=manifest)
    first=h.admit(h.approved())
    receipt=h.repo.dispatch(h.controller,first.consumed_intent_id)
    require(h.repo.receive(h.broker.issue_event(receipt,0))=='applied','EX09_postquery_fill')
    query=h.broker.query(1);fresh=h.repo.refresh_current(h.controller,query)
    require(fresh.current.current.snapshot.reconciliation_details.full_account_balances_matched,'EX09_independent_statement')
    qty=json.loads(db._query("SELECT body FROM qh.execution_reservation WHERE body->>'component'='quantity';"))
    require((fresh.current.facts.sellability_rows[0].settled_quantity,qty['held'],query.sellable[0].quantity,
        query.sellable[0].hold_reflections[0].quantity,qty['used'])==('12','4','10','2','1'),'EX09_literal_parts')
    h.source=replacement_source(h.source,('6' if quantity==7 else '5',),label='sell-next-'+str(quantity))
    h.repo.replace_source(h.controller,h.source)
    next_=h.approved(label='sell-next-approve')
    require(next_.terms.quantity==str(quantity),'EX09_next_terms')
    import quantharbor.application.execution as application
    with patch.object(application,'sellable',wraps=application.sellable) as calculated:
        result=h.app.execute(h.approver,h.admission_challenge(next_,label='sell-next-admit'))
    require(calculated.call_count==1 and calculated.call_args.args==('12','4','10','2','1'),'EX09_full_computation')
    require(result.outcome==('applied' if quantity==7 else 'rejected'),'EX09_literal_outcome')
    require(rowcount(db,'execution_intent')==(2 if quantity==7 else 1),'EX09_literal_atomicity')
    goldens['EX09_literal_'+str(quantity)]={'ledger':'12','holds':'4','broker':'10','unreflected':'2','postquery':'1','bound':'7','outcome':result.outcome}
    checks.append('EX09_full_DB_nonzero_partial_holds_postquery_fill_qty'+str(quantity))


def literal_exposure(db,checks,goldens):
    # This golden uses two approvals, within active2. Opposing-sale nonnetting
    # is separately exercised by risk_negative(mode='exposure') with real DB data.
    from synthetic_execution import replacement_source
    h=DatabaseHarness(db,target_options={'holdings':('0','4'),'targets':('1','3'),'lot':'0.5','fee':'0'},exposure_ceiling='500')
    buy=h.admit(h.approved(0,label='active-buy'),label='buy-admit')
    require(h.repo.intent(h.controller,buy.consumed_intent_id).terms.maximum_burden=='100','EX11_active_buy100')
    h.source=replacement_source(h.source,('0.5','3'),label='new-buy50-source')
    h.repo.replace_source(h.controller,h.source)
    next_=h.approved(0,label='new-buy50')
    require(next_.terms.maximum_burden=='50','EX11_new50')
    before=rowcount(db,'execution_intent')
    import quantharbor.adapters.postgres_execution as adapter
    with patch.object(adapter,'current_risk',wraps=adapter.current_risk) as computed:
        result=h.app.execute(h.approver,h.admission_challenge(next_,label='new-buy-admit'))
    require(computed.call_count==1,'EX11_financial_not_capacity_shortcut')
    require(result.outcome=='rejected' and result.reason_code=='risk_blocked','EX11_550_over500')
    require(rowcount(db,'execution_intent')==before==1,'EX11_no_second_intent')
    require(h.repo.head(h.approver,next_.approval_id).state=='approved','EX11_rejected_not_consumed')
    goldens['EX11_literal']={'current':'400','active_buy':'100','new_buy':'50','maximum':'550','limit':'500',
        'opposing_sale_nonnetting_case':'risk_negative_exposure'}
    checks.append('EX11_full_DB_400_plus_activebuy100_plus_new50_denied550_over500')


def storage_independent(db,checks,goldens):
    h=DatabaseHarness(db,facts=(financial_fact('cost',fee='1',tax='0.5'),))
    approval=h.admit(h.approved());receipt=h.repo.dispatch(h.controller,approval.consumed_intent_id)
    require(h.repo.receive(h.broker.issue_event(receipt,0))=='applied','storage_cost_fill')
    # Handwritten PK/UNIQUE keys for Q20; no call to production cost/manifest helper.
    definitions={
      'ledger_event':(('account_ref','sequence'),('event_id',),('account_ref','event_id'),('account_ref','source_kind','source_event_key','source_revision')),
      'ledger_journal':(('event_id','ordinal'),),
      'ledger_decision':(('account_ref','cursor'),),
      'ledger_projection':(('projection_id',),('account_ref','projection_id'),('account_ref','cursor','projection_id')),
      'ledger_outbox':(('message_id',),),'ledger_delivery':(('message_id',),),
      'ledger_inbox':(('consumer','message_id'),)}
    independent={}
    for table,keys in definitions.items():
        index_expr='+'.join('octet_length(qh.ledger_canonical(jsonb_build_array('+','.join(key)+')))' for key in keys)
        raw=db._query("SELECT jsonb_build_object('rows',count(*),'canonical_bytes',coalesce(sum(octet_length(qh.ledger_canonical(to_jsonb(t)))),0),'index_bytes',coalesce(sum("+index_expr+"),0)) FROM qh."+table+' t;')
        independent[table]=json.loads(raw)
        measured=json.loads(db._query("SELECT jsonb_build_object('rows',count(*),'canonical_bytes',coalesce(sum(octet_length(qh.ledger_canonical(row_data))),0),'index_bytes',coalesce(sum(index_bytes),0)) FROM qh.execution_storage_rows("+_text(h.source.request.account_ref)+") WHERE relation_name="+_text(table)+';'))
        require(independent[table]==measured,'independent_row_index_'+table)
    # Before consume: three first appends =21 real rows and3 protected future inboxes.
    require(db._query("SELECT count(*) FROM qh.ledger_decision WHERE submission->>'source_kind'='synthetic-execution';")=='3','storage_three_decisions')
    ledger_rows=int(db._query("SELECT count(*) FROM qh.execution_storage_rows("+_text(h.source.request.account_ref)+") WHERE owner="+_text(approval.consumed_intent_id)+" AND category='ledger';"))
    require(ledger_rows==21,'storage_real21_future3')
    all_rows=json.loads(db._query('SELECT jsonb_agg(jsonb_build_array(message_id,payload_hash)) FROM qh.ledger_outbox;'))
    for mid,ph in all_rows: h.repo.consume_ledger(mid,ph)
    require(int(db._query("SELECT count(*) FROM qh.execution_storage_rows("+_text(h.source.request.account_ref)+") WHERE owner="+_text(approval.consumed_intent_id)+" AND category='ledger';"))==24,'storage_consumed24')
    require(db._query("SELECT bool_and(reserved_records>=0 AND reserved_bytes>=0) FROM qh.execution_budget;")=='t','storage_reserve_nonnegative')
    goldens['storage_independent']=independent
    checks.append('EX32_independent_actual_rows_each_PK_UNIQUE_key_bytes_future_inbox')


def storage_manifest_deny(db,checks,goldens):
    h=DatabaseHarness(db)
    before=h.repo.fingerprint();received=h.broker.received_count
    from quantharbor.adapters.synthetic_execution_broker import SyntheticExecutionBroker
    facts=tuple(financial_fact('revision',revision=n+1,predecessor=n or None,fee='1',tax='0.5') for n in range(8))
    try: SyntheticExecutionBroker(h.source.request.account_ref,h.broker._snapshots,facts)
    except d.ExecutionDenied as denied: require(denied.reason=='capacity_exceeded','storage_255_reason')
    else: raise CheckFailure('storage_255_accepted')
    require(h.repo.fingerprint()==before and h.broker.received_count==received and rowcount(db,'execution_intent')==0,'storage_255_side_effects')
    checks.append('EX32_255_rows_fixed_manifest_preissue_deny_zero_DB_issuer_sideeffects')


def sql_auth_closed(db,checks,goldens):
    h=DatabaseHarness(db);first=h.admit(h.approved())
    before=h.repo.fingerprint();account=h.source.request.account_ref
    # AUTH negatives run as product, independent from structural owner negatives.
    for statement in ("SELECT qh.execution_save(NULL,NULL,NULL);", "SELECT qh.execution_event(NULL,NULL);",
        "SELECT qh.execution_ledger(NULL,'append',NULL,NULL);", "SELECT qh.ledger_append(NULL,NULL);",
        "SELECT qh.execution_issue_context(NULL,NULL,NULL,NULL,NULL);", "SELECT qh.execution_stage_chunk(NULL,NULL,NULL);"):
        db._query('BEGIN; SET LOCAL ROLE qh_execution_product; '+statement+' ROLLBACK;',expected=3,error_marker=b'permission denied')
        require(h.repo.fingerprint()==before,'SQLAUTH_generic_fingerprint')
    db._query("BEGIN; SET LOCAL ROLE qh_execution_product; SELECT qh.execution_apply('made-up','save'); COMMIT;",expected=3,error_marker=b'execution_auth')
    # Custom setting/self hash is never consulted by the authority path.
    db._query("BEGIN; SET LOCAL ROLE qh_execution_product; SET LOCAL qh.authorized='true'; SELECT qh.execution_apply('callerhash','append'); COMMIT;",expected=3,error_marker=b'execution_auth')
    checks.append('SQLAUTH_product_generic_context_issue_GUC_selfhash_denied')
    # Owner is deliberately able to issue contexts, but a different backend cannot use one.
    header={'version':int(db._query('SELECT version FROM qh.execution_account;')),'generation':h.authority._generation,'fence':1,
      'source_hash':h.repo._source_hash(),'actor':None,'session':None,'action':None,'nonce':None,'target':None,'target_version':None,
      'at':AT,'issuer':h.authority._instance,'fact':None,'operation':'consume','command':None,'current_validation':None}
    with ExecutionUnitOfWork(db,account) as uow:
        uow._exchange('RESET ROLE;',result=False)
        token='root-context'
        payload=json.dumps({'message_id':'missing','payload_hash':'0'*64},separators=(',',':')).encode()
        uow._select('execution_stage_chunk',token,0,payload.hex())
        uow._select('execution_issue_context',account,'consume',token,1,json.dumps(header,separators=(',',':')))
        db._query("BEGIN; SET LOCAL ROLE qh_execution_product; SELECT qh.execution_apply('root-context','consume'); COMMIT;",expected=3,error_marker=b'execution_auth')
        # Wrong action on the issuing backend is also rejected; close rolls back the context.
        try:uow._select('execution_apply',token,'save')
        except d.ExecutionDenied:pass
        else:raise CheckFailure('SQLAUTH_action_swap')
    require(h.repo.fingerprint()==before,'SQLAUTH_cross_context_fingerprint')
    checks.append('SQLAUTH_real_two_backend_action_bound_context_no_cross_connection')
    # Structural negatives use owner DML so permission denial cannot mask them.
    statements=(
      "UPDATE qh.execution_account SET common_plan=common_plan-'next';",
      "UPDATE qh.execution_account SET common_plan=common_plan||'{\"extra\":0}'::jsonb;",
      "UPDATE qh.execution_reservation SET body=body-'held';",
      "UPDATE qh.execution_reservation SET body=jsonb_set(body,'{held}','null'::jsonb);",
      "UPDATE qh.execution_reservation SET body=body||'{\"extra\":true}'::jsonb;",
      "UPDATE qh.execution_reservation SET body=jsonb_set(body,'{used}','\"1e2\"'::jsonb);",
      "UPDATE qh.execution_reservation SET body=jsonb_set(body,'{settled}','\"999\"'::jsonb);",
      "DELETE FROM qh.execution_outbox;",
      "DELETE FROM qh.execution_intent;",
      "DELETE FROM qh.execution_claim;",
      "SELECT qh.ledger_wire('{\"a\":1,\"a\":2}');")
    for statement in statements:
        db._query('BEGIN; '+statement+' COMMIT;',expected=3)
        require(h.repo.fingerprint()==before,'CLOSED_structural_fingerprint')
    require(db._query('SELECT (SELECT count(*) FROM qh.execution_stage)+(SELECT count(*) FROM qh.execution_context)+(SELECT count(*) FROM qh.execution_read_buffer);')=='0','SQLAUTH_staging_cleanup')
    checks.append('CLOSED_owner_missing_null_extra_decimal_reservation_atomicity_duplicate_key_separate')
    # Successfully reach COMMIT before each orphan is rejected by deferred coupling.
    template=json.loads(db._query('SELECT body FROM qh.execution_intent LIMIT 1;'))
    orphan=dict(template,intent_id='orphan-intent',approval_ref=dict(template['approval_ref'],id='orphan-approval'))
    approval_wire=json.loads(db._query("SELECT wire FROM qh.execution_evidence WHERE kind='approval' AND wire->'payload'->>'state'='consumed' LIMIT 1;"))
    approval_wire['payload'].update(approval_id='orphan-approval',consumed_intent_id='orphan-intent',state_version=1,previous_ref=None)
    wire=_text(json.dumps(approval_wire,separators=(',',':')))
    body=_text(json.dumps(orphan,separators=(',',':')))
    orphan_statements=(
      "INSERT INTO qh.execution_evidence VALUES("+_text(account)+",'approval','orphan-approval',1,qh.ledger_hash('ApprovalRecord',"+wire+"::jsonb->'payload'),"+wire+"::jsonb);",
      "INSERT INTO qh.execution_intent SELECT account_ref,'orphan-intent',candidate_id,candidate_version,'orphan-approval',state,version,"+body+"::jsonb,qh.ledger_hash('OrderIntent',"+body+"::jsonb) FROM qh.execution_intent LIMIT 1;",
      "INSERT INTO qh.execution_outbox VALUES("+_text(account)+",'orphan-intent','prepared');")
    for statement in orphan_statements:
        output=db._query("BEGIN; SET CONSTRAINTS ALL DEFERRED; "+statement+" SELECT 'q27_insert_reached_commit'; COMMIT;",expected=3)
        require('q27_insert_reached_commit' in output,'CLOSED_orphan_failed_before_COMMIT')
        require(h.repo.fingerprint()==before,'CLOSED_orphan_fingerprint')
    checks.append('CLOSED_standalone_consumed_intent_outbox_reach_COMMIT_fail_fingerprint_unchanged')
    sql_atomic_withdraw_binding(db,h,first,checks)




def stage_context(uow,account,header,payload,*,token='binding-probe'):
    header={'current_validation':None,**header}
    """Root owner diagnostic only; never a product context constructor."""
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    require(len(raw)<=64*1048576,'probe_payload_bound')
    uow._exchange('RESET ROLE;',result=False)
    parts=0
    for offset in range(0,len(raw),MAX_CHUNK):
        uow._select('execution_stage_chunk',token,parts,raw[offset:offset+MAX_CHUNK].hex())
        parts+=1
    uow._select('execution_issue_context',account,header['operation'],token,parts,
        json.dumps(header,separators=(',',':')))
    uow._exchange('SET LOCAL ROLE qh_execution_product;',result=False)
    return token


def expect_context_auth(uow,token,action):
    # Only execution_auth counts, never a syntax/shape/permission/storage error.
    sql=("DO $probe$ BEGIN BEGIN PERFORM qh.execution_apply("+_text(token)+","+_text(action)+
        "); RAISE EXCEPTION 'probe_expected_auth'; EXCEPTION WHEN OTHERS THEN "
        "IF SQLERRM IS DISTINCT FROM 'execution_auth' THEN RAISE; END IF; END; END $probe$; SELECT to_jsonb(true);")
    require(uow._exchange(sql) is True,'SQLAUTH_exact_error_code')


def sql_atomic_withdraw_binding(db,h,approval,checks):
    """Capture a real host-validated delta, then separately attack each SQL binding.

    Dry capture aborts the original transaction before apply; no finance/issuer
    calculator is replaced. Every negative uses the actual SQL parser and roles.
    """
    from copy import deepcopy
    captured={};chunks=[]
    original=ExecutionUnitOfWork._select
    def capture(uow,function,*values,**kw):
        if function=='execution_stage_chunk': chunks.append(bytes.fromhex(values[2]))
        if function=='execution_issue_context':
            captured['header']=json.loads(values[4]);captured['payload']=json.loads(b''.join(chunks));chunks.clear()
        if function=='execution_apply' and captured:
            raise d.ExecutionDenied('storage_failure')
        return original(uow,function,*values,**kw)
    before=h.repo.fingerprint();account=h.source.request.account_ref
    try:
        with patch.object(ExecutionUnitOfWork,'_select',capture):
            h.app.withdraw(h.controller,a.ref('approval',approval.approval_id,approval),command_id='atomic-withdraw-probe')
    except a.ApprovalDenied: pass
    else: raise CheckFailure('withdraw_capture_did_not_abort')
    require(bool(captured) and h.repo.fingerprint()==before,'withdraw_capture_rollback')
    original_header,original_payload=captured['header'],captured['payload']
    # AUTH negatives are not permission failures or owner structural DML failures.
    mutations=('actor','session','action','generation','nonce','issuer','target_version','missing_challenge','missing_receipt','receipt_actor','receipt_target','receipt_hash','nonce_map')
    for mutation in mutations:
        header,payload=deepcopy(original_header),deepcopy(original_payload)
        if mutation in ('actor','session','action','generation','nonce','issuer'):
            header[mutation]='wrong-binding'
        elif mutation=='target_version':
            header['command']['expected_state_version']+=1
        elif mutation in ('missing_challenge','missing_receipt'):
            schema='ActionChallenge' if mutation=='missing_challenge' else 'ActionReceipt'
            payload['evidence']=[x for x in payload['evidence'] if x['wire']['schema_name']!=schema]
        elif mutation.startswith('receipt_'):
            receipt=next(x['wire']['payload'] for x in payload['evidence'] if x['wire']['schema_name']=='ActionReceipt')
            if mutation=='receipt_actor': receipt['actor_evidence_ref']['sha256']='0'*64
            elif mutation=='receipt_target': receipt['target_ref']['sha256']='0'*64
            else: receipt['command_payload_hash']='0'*64
        else:
            change=next(x for x in payload['state_delta'] if x['key']=='nonces')
            change['value']['upsert']=[]
        with ExecutionUnitOfWork(db,account) as uow:
            token=stage_context(uow,account,header,payload)
            expect_context_auth(uow,token,'save')
        require(h.repo.fingerprint()==before,'SQLAUTH_withdraw_rollback_'+mutation)
    # The very same delta with all exact bindings is the positive SQL path.
    receipt=h.app.withdraw(h.controller,a.ref('approval',approval.approval_id,approval),command_id='atomic-withdraw-probe')
    require(receipt.outcome=='applied','SQLAUTH_atomic_withdraw_positive')
    after=h.repo.fingerprint()
    require(h.app.withdraw(h.controller,a.ref('approval',approval.approval_id,approval),command_id='atomic-withdraw-probe')==receipt,
        'SQLAUTH_withdraw_public_replay_result')
    require(h.repo.fingerprint()==after,'SQLAUTH_withdraw_public_replay_growth')
    # A new owner-issued context cannot authorize a consumed command again.
    header=deepcopy(original_header)
    header['version']=int(db._query('SELECT version FROM qh.execution_account;'))
    with ExecutionUnitOfWork(db,account) as uow:
        token=stage_context(uow,account,header,original_payload)
        expect_context_auth(uow,token,'save')
    require(h.repo.fingerprint()==after,'SQLAUTH_withdraw_reused_context_growth')
    checks.append('SQLAUTH_atomic_withdraw_exact_delta_current_session_target_nonce_receipt_negative_and_positive_replay_noop')


def common_budget_observation(db,account):
    future=json.loads(db._query('SELECT qh.execution_common_remaining('+_text(account)+');'))
    measured=json.loads(db._query("SELECT jsonb_build_object('records',coalesce(sum(n),0),'bytes',coalesce(sum(z),0)) FROM ("
      "SELECT 1 AS n,octet_length(qh.ledger_canonical(row_data))+index_bytes AS z FROM qh.execution_storage_rows("+_text(account)+") WHERE owner='@common' UNION ALL "
      "SELECT CASE WHEN owner='@common' THEN logical_records ELSE 0 END,CASE WHEN owner='@common' THEN 0 ELSE -canonical_bytes END FROM qh.execution_state_copies("+_text(account)+")) c;"))
    require(measured['records']+future['records']<=128,'common_actual_future_rows')
    require(measured['bytes']+future['bytes']<=8388608,'common_actual_future_bytes')
    return {'actual':measured,'remaining':future}


def storage_saturated_completion(db,checks,goldens):
    facts=(financial_fact('first'),financial_fact('first',quantity='2',price='95',revision=2,predecessor=1),
        financial_fact('cancel',execution='cancel',quantity='1',kind='cancelled_remaining'))
    h=DatabaseHarness(db,facts=facts)
    one=h.admit(h.approved(0,label='one'),label='admit-one')
    two=h.admit(h.approved(1,label='two'),label='admit-two')
    a_,b_=one.consumed_intent_id,two.consumed_intent_id
    def other_budget():return db._query('SELECT to_jsonb(b) FROM qh.execution_budget b WHERE owner='+_text(b_)+';')
    protected=other_budget()
    common_before=common_budget_observation(db,h.source.request.account_ref)
    require(common_before['remaining']['plan']=={'next':1,'sessions':0,'rebind':0,'resume':0},'common_before_recovery_plan')
    # Both24MiB owner charges + common8MiB + source8MiB exhaust the fixed64MiB.
    for owner in (a_,b_):
        require(db._query('SELECT closed FROM qh.execution_budget WHERE owner='+_text(owner)+';')=='f','saturation_owner_live')
    receipt=h.repo.dispatch(h.controller,a_)
    event=h.broker.issue_event(receipt,0)
    h.repo.control(h.controller,'stop')
    require(h.repo.receive(event)=='applied','saturation_issued_fill_after_stop')
    require(h.repo.receive(h.broker.issue_event(receipt,1))=='applied','saturation_correction')
    intent=h.repo.intent(h.controller,a_)
    cancel=h.repo.cancel(h.controller,a_,command_id='saturated-cancel',expected_version=intent.state_version)
    ack=h.repo.dispatch_cancel(h.controller,cancel.command_id)
    require(h.repo.receive(h.broker.issue_event(ack,2))=='applied','saturation_cancel_confirmation')
    require(other_budget()==protected,'saturation_other_owner_reserve_changed')
    current=two  # actual consumed approval returned by admit; controller has no present right
    require(h.app.withdraw(h.controller,a.ref('approval',current.approval_id,current),command_id='saturated-withdraw').outcome=='applied','saturation_withdraw')
    require(h.repo.intent(h.controller,b_).state=='aborted_unsent','saturation_unsent_preserved')
    old_records=db._query("SELECT jsonb_agg(jsonb_build_array(kind,id,version,hash) ORDER BY kind,id,version) FROM qh.execution_evidence;")
    from quantharbor.adapters.synthetic_approval import SyntheticAuthority
    fresh=SyntheticAuthority(tuple(h.authority._principals.values()),clock=h.clock)
    recovered=PostgresExecutionRepository.restart(db,fresh,h.source,approval_policy(h.source),h.repo._registry['inputs'],h.broker,
        expected_generation=h.authority._generation)
    common_rotated=common_budget_observation(db,h.source.request.account_ref)
    require(common_rotated['remaining']['plan']=={'next':0,'sessions':2,'rebind':1,'resume':1},'common_recovery_transfer')
    controller=fresh.issue_session('execution-controller')
    common_session=common_budget_observation(db,h.source.request.account_ref)
    require(common_session['remaining']['plan']['sessions']==1,'common_session_slot_consumed')
    goldens['common_completion']={'before':common_before,'rotated':common_rotated,'new_session':common_session}
    require(recovered.intent(controller,a_).state=='cancelled_remaining','saturation_recovery_fact')
    for kind,identity,version,digest in json.loads(old_records):
        require(db._query('SELECT hash FROM qh.execution_evidence WHERE kind='+_text(kind)+' AND id='+_text(identity)+' AND version='+str(version)+';')==digest,'saturation_immutable_history')
    require(rowcount(db,'execution_claim')==2,'saturation_claims')
    checks.append('EX32_saturated_two_owner_bytes_issued_fill_correction_cancel_withdraw_stop_restart_other_reserve')


def storage_terminal_third(db,checks,goldens):
    from synthetic_execution import replacement_source
    from quantharbor.adapters.synthetic_approval import SyntheticAuthority
    from quantharbor.adapters.postgres_execution import _unpack
    h=DatabaseHarness(db,facts=())
    one=h.admit(h.approved(0,label='first'),label='first-admit')
    two=h.admit(h.approved(1,label='second'),label='second-admit')
    # Do not label a blocked third presentation as proof of the active3 gate.
    before=h.repo.fingerprint()
    candidate=h.source.artifacts.candidates[0]
    from quantharbor.domain.target import ref as target_ref
    try: h.app.present(h.approver,target_ref('candidate',candidate.candidate_id,candidate))
    except a.ApprovalDenied as denied: require(denied.reason=='capacity_exceeded','active_three_precondition')
    else: raise CheckFailure('active_three_presentation_unexpectedly_fits_revisit_probe')
    require(h.repo.fingerprint()==before,'active_three_precondition_side_effect')
    history=json.loads(db._query("SELECT jsonb_agg(jsonb_build_array(kind,id,version,hash) ORDER BY kind,id,version) FROM qh.execution_evidence;"))
    # Use both bounded protective closures; retain their original history.
    for index,approval in enumerate((one,two)):
        for closure in range(2):
            require(h.app.withdraw(h.controller,a.ref('approval',approval.approval_id,approval),
                command_id='terminal-'+str(index)+'-'+str(closure)).outcome=='applied','terminal_protective_closure')
    require(db._query("SELECT count(*) FROM qh.execution_intent WHERE state NOT IN ('filled','rejected','aborted_unsent','cancelled_remaining','expired_remaining');")=='0','terminal_still_active')
    fresh=SyntheticAuthority(tuple(h.authority._principals.values()),clock=h.clock)
    h.repo=PostgresExecutionRepository.restart(db,fresh,h.source,approval_policy(h.source),h.repo._registry['inputs'],h.broker,
        expected_generation=h.authority._generation)
    h.authority=fresh;h.app=ApprovalApplication(h.repo)
    h.controller=fresh.issue_session('execution-controller');h.approver=fresh.issue_session('execution-approver')
    require(h.repo.rebind(h.controller,h.broker.query()).result=='matched','terminal_actual_rebind')
    h.repo.control(h.controller,'resume')
    h.source=replacement_source(h.source,('3','4'),label='third-source');h.repo.replace_source(h.controller,h.source)
    # Current controller becomes unusable only after the actual rebind/resume.
    h.repo.control(h.controller,'disconnect')
    observed=[];original=h.repo._room
    def measured(state):
        count,size=h.repo._usage(state)
        observed.append({'actual':count,'remaining':sum(v[0] for v in state['holds'].values()),'bytes':size})
        return original(state)
    before=h.repo.fingerprint()
    try:
        with patch.object(h.repo,'_room',measured): third=h.approved(0,label='third')
    except a.ApprovalDenied as denied:
        require(denied.reason=='capacity_exceeded' and bool(observed),'terminal_third_reason')
        require(observed[-1]['actual']+observed[-1]['remaining']>128,'terminal_third_actual_quota')
        require(h.repo.fingerprint()==before,'terminal_third_failed_issuance_side_effect')
        goldens['terminal_third_pending']={'blocked_at':'Q26_after_both_terminal_fresh_generation_rebind_resume',
          'actual':observed[-1]['actual'],'remaining_completion':observed[-1]['remaining'],'limit':128,
          'active3_proven':False,'terminal3_proven':False,'retained_claims':rowcount(db,'execution_claim')}
        checks.append('EX32_terminal_history_capacity_diagnostic_only_third_positive_UNRESOLVED')
    else:
        receipt=h.app.execute(h.approver,h.admission_challenge(third,label='third-admit'))
        require(receipt.outcome=='applied' and rowcount(db,'execution_intent')==3,'terminal_third_positive')
        goldens['terminal_third_positive']={'intents':3,'active3_proven':False}
        checks.append('EX32_both_terminal_actual_rebind_resume_third_positive')
    require(rowcount(db,'execution_claim') in (2,3),'terminal_claims_lost')
    for kind,identity,version,digest in history:
        require(db._query('SELECT hash FROM qh.execution_evidence WHERE kind='+_text(kind)+' AND id='+_text(identity)+' AND version='+str(version)+';')==digest,'terminal_immutable_history')


def frame_rollback(db,checks,goldens):
    h=DatabaseHarness(db);before=h.repo.fingerprint();account=h.source.request.account_ref
    header={'version':int(db._query('SELECT version FROM qh.execution_account;')),'generation':h.authority._generation,'fence':1,
      'source_hash':h.repo._source_hash(),'actor':None,'session':None,'action':None,'nonce':None,'target':None,'target_version':None,
      'at':AT,'issuer':h.authority._instance,'fact':None,'operation':'save','command':None}
    def clean(label):
        require(h.repo.fingerprint()==before,'EX37_rollback_'+label)
        require(db._query('SELECT (SELECT count(*) FROM qh.execution_stage)+(SELECT count(*) FROM qh.execution_context)+(SELECT count(*) FROM qh.execution_read_buffer);')=='0','EX37_cleanup_'+label)
    for label,raw,parts in (('UTF8',b'\xff',1),('JSON',b'{',1),('extra_output',b'{}extra',1),
                           ('missing',b'{}',2),('duplicate_key',b'{"a":1,"a":2}',1)):
        try:
            with ExecutionUnitOfWork(db,account) as uow:
                uow._exchange('RESET ROLE;',result=False)
                uow._select('execution_stage_chunk','incomplete',0,raw.hex())
                uow._select('execution_issue_context',account,'save','incomplete',parts,json.dumps(header,separators=(',',':')))
        except d.ExecutionDenied: pass
        else: raise CheckFailure('EX37_expected_rejection_'+label)
        clean(label)
    for label,parts in (('conflict',(0,0)),('order',(1,)),('gap',(0,2))):
        try:
            with ExecutionUnitOfWork(db,account) as uow:
                uow._exchange('RESET ROLE;',result=False)
                for part in parts: uow._select('execution_stage_chunk','bad-sequence',part,b'{}'.hex())
        except d.ExecutionDenied: pass
        else: raise CheckFailure('EX37_expected_rejection_'+label)
        clean(label)
    # Owner-scoped transport diagnostic: >8MiB valid UTF8 across real staging
    # and the normal paged load, then restore under SAVEPOINT before COMMIT.
    # This deliberately proves transport, not financial adoption of arbitrary JSON.
    blob='한'*3145729
    payload={'transport_probe':blob}
    raw_bytes=len(json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode())
    require(MAX_FRAME<raw_bytes<64*1048576,'EX37_large_probe_size')
    with ExecutionUnitOfWork(db,account) as uow:
        token=stage_context(uow,account,header,payload,token='large-transfer')
        uow._exchange('RESET ROLE; SAVEPOINT transport_probe; UPDATE qh.execution_account SET state=(SELECT payload FROM qh.execution_context WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND token=\'large-transfer\') WHERE account_ref='+_text(account)+';',result=False)
        uow._exchange('SET LOCAL ROLE qh_execution_product;',result=False)
        loaded=uow.call('execution_load',account)
        require(loaded['state']==payload,'EX37_large_real_paged_roundtrip')
        transferred=uow._transferred
        uow._exchange("RESET ROLE; ROLLBACK TO SAVEPOINT transport_probe; DELETE FROM qh.execution_context WHERE backend=pg_backend_pid() AND transaction_id=pg_current_xact_id() AND token='large-transfer';",result=False)
        uow.commit()
    clean('large_transfer_commit')
    goldens['frame_large_transfer']={'raw_bytes':raw_bytes,'transferred_bytes':transferred,'raw_chunk_limit':MAX_CHUNK,
        'hex_frame_limit':MAX_CHUNK_FRAME,'scope':'real_staging_and_paged_load_restore_then_COMMIT; not_domain_large_delta_authority'}
    # Exact64KiB followed by connection EOF; partial read followed by EOF.
    with ExecutionUnitOfWork(db,account) as uow:
        uow._exchange('RESET ROLE;',result=False)
        uow._select('execution_stage_chunk','boundary',0,(b'x'*MAX_CHUNK).hex())
    clean('EOF')
    with ExecutionUnitOfWork(db,account) as uow: uow._select('execution_read_page',account,'load','','',0)
    clean('read_EOF')
    try:
        with ExecutionUnitOfWork(db,account) as uow:
            uow._exchange('RESET ROLE;',result=False)
            uow._select('execution_stage_chunk','timeout',0,b'{}'.hex())
            uow._deadline=time.monotonic()+0.05
            uow._exchange('SELECT pg_sleep(0.2);',result=False)
    except d.ExecutionDenied: pass
    else: raise CheckFailure('EX37_expected_timeout')
    clean('timeout')
    # A poisoned frame cannot be caught and followed by an effective COMMIT.
    with ExecutionUnitOfWork(db,account) as uow:
        try: uow._exchange('SELECT true; SELECT true;')
        except d.ExecutionDenied: pass
        else: raise CheckFailure('EX37_extra_output_accepted')
        try: uow.commit()
        except d.ExecutionDenied: pass
        else: raise CheckFailure('EX37_poisoned_commit')
    clean('extra_output_poison')
    checks.append('EX37_EX40_real_gt8MiB_roundtrip_missing_conflict_order_UTF8_duplicate_EOF_timeout_poison_cleanup')
    # A real financial COMMIT then EOF: observe receipt, never automatic retry.
    approval=h.approved(label='frame-approval');challenge=h.admission_challenge(approval,label='frame-admit')
    def lost(uow): uow._exchange('COMMIT;\n\\quit',result=False)
    try:
        with patch.object(ExecutionUnitOfWork,'commit',lost): h.app.execute(h.approver,challenge)
    except (d.ExecutionDenied,a.ApprovalDenied): pass
    else: raise CheckFailure('EX40_expected_COMMIT_EOF')
    require(rowcount(db,'execution_intent')==1,'EX40_commit_not_durable')
    after=h.repo.fingerprint();receipt=h.repo.command_result(h.approver,challenge.command_id)
    require(receipt is not None and receipt.outcome=='applied','EX40_receipt_observation')
    require(h.app.execute(h.approver,challenge)==receipt and h.repo.fingerprint()==after,'EX40_no_retry_or_second_intent')
    require(db._query('SELECT (SELECT count(*) FROM qh.execution_stage)+(SELECT count(*) FROM qh.execution_context)+(SELECT count(*) FROM qh.execution_read_buffer);')=='0','EX40_COMMIT_EOF_cleanup')
    checks.append('EX40_actual_COMMIT_EOF_receipt_observation_no_financial_retry')

def completion_observe(db,h):
    value=json.loads(db._query('SELECT qh.execution_common_charge('+_text(h.source.request.account_ref)+');'))
    require(value['records']<=128 and value['bytes']<=8388608,'DEC004_common_limit')
    return value


def completion_step(db,h,label,action,trace):
    before=completion_observe(db,h)
    result=action()
    after=completion_observe(db,h)
    require(after['records']<=before['records'],'DEC004_rows_'+label)
    require(after['bytes']<=before['bytes'],'DEC004_bytes_'+label)
    trace.append({'stage':label,'before':before,'after':after})
    return result


def completion_recovery_orders(db,checks,goldens,*,order='normal'):
    from quantharbor.adapters.synthetic_approval import SyntheticAuthority
    h=DatabaseHarness(db,facts=())
    aps=[h.admit(h.approved(ix,label='rec-ap-'+str(ix)),label='rec-admit-'+str(ix)) for ix in range(2)]
    for ix,ap in enumerate(aps):
        for j in range(2):h.app.withdraw(h.controller,a.ref('approval',ap.approval_id,ap),command_id=f'rec-end-{ix}-{j}')
    trace=[];fresh=SyntheticAuthority(tuple(h.authority._principals.values()),clock=h.clock)
    def restart():
        h.repo=PostgresExecutionRepository.restart(db,fresh,h.source,approval_policy(h.source),h.repo._registry['inputs'],h.broker,
            expected_generation=h.authority._generation)
        h.authority=fresh;h.app=ApprovalApplication(h.repo)
    completion_step(db,h,'restart',restart,trace)
    h.controller=completion_step(db,h,'controller',lambda:fresh.issue_session('execution-controller'),trace)
    if order=='invalidated':
        completion_step(db,h,'rebind-before-approver',lambda:h.repo.rebind(h.controller,h.broker.query()),trace)
        from synthetic_execution import replacement_source
        source=replacement_source(h.source,('3','4'),label='invalidated-source')
        before=completion_observe(db,h)
        h.repo.replace_source(h.controller,source)
        after=completion_observe(db,h)
        require(after['remaining']['plan']['rebind']==1,'DEC005_source_repair_not_reserved')
        require(h.source in h.repo._registry['source_history'],'DEC005_source_original_not_retained')
        trace.append({'stage':'elective-verified-source-invalidates','before':before,'after':after})
        h.source=source
        # Elective invalidation must acquire its new re-reconciliation before save.
        before=completion_observe(db,h);fingerprint=h.repo.fingerprint()
        try:h.approver=fresh.issue_session('execution-approver')
        except a.ApprovalDenied as denied:
            require(denied.reason=='capacity_exceeded' and h.repo.fingerprint()==fingerprint,'DEC004_invalidating_issue_rollback')
            goldens['completion_recovery_'+order]={'trace':trace,'elective_rejected_without_effect':True}
            checks.append('DEC004_invalidated_rebind_elective_issue_preflight_rejection');return
        after=completion_observe(db,h)
        require(after['remaining']['plan']['rebind']==1,'DEC004_invalidated_rebind_not_reserved')
        failed=h.repo.fingerprint()
        try:h.repo.control(h.controller,'resume')
        except a.ApprovalDenied as denied:require(denied.reason=='reconciliation_required','DEC004_invalidated_resume_reason')
        else:raise CheckFailure('DEC004_invalidated_resume_allowed')
        require(h.repo.fingerprint()==failed,'DEC004_invalidated_resume_sideeffects')
        trace.append({'stage':'elective-approver-invalidates','before':before,'after':after})
    else:
        principal='execution-controller' if order=='two_controllers' else 'execution-approver'
        h.approver=completion_step(db,h,'second-session',lambda:fresh.issue_session(principal),trace)
    rec=completion_step(db,h,'rebind',lambda:h.repo.rebind(h.controller,h.broker.query()),trace)
    require(rec.result=='matched','DEC004_rebind_matched')
    if order=='invalidated':
        completion_step(db,h,'protective-stop-before-resume',lambda:h.repo.control(h.controller,'stop'),trace)
        completion_step(db,h,'reconcile-after-protective-stop',lambda:h.repo.reconcile(h.controller,h.broker.query()),trace)
    protected=db._query('SELECT jsonb_agg(to_jsonb(b) ORDER BY owner) FROM qh.execution_budget b;')
    completion_step(db,h,'resume',lambda:h.repo.control(h.controller,'resume'),trace)
    require(db._query('SELECT jsonb_agg(to_jsonb(b) ORDER BY owner) FROM qh.execution_budget b;')==protected,'DEC004_recovery_borrowed_owner')
    completion_step(db,h,'stop',lambda:h.repo.control(h.controller if order!='two_controllers' else h.approver,'stop'),trace)
    goldens['completion_recovery_'+order]=trace
    checks.append('DEC004_actual_rows_bytes_recovery_'+order)


def completion_security_disconnect(db,checks,goldens):
    """SEC1 real DB red path, including every mandatory rows/bytes transition."""
    from quantharbor.adapters.synthetic_approval import SyntheticAuthority
    h=DatabaseHarness(db,facts=())
    for ix in range(2):
        ap=h.admit(h.approved(ix,label='sec1-ap-'+str(ix)),label='sec1-admit-'+str(ix))
        for j in range(2):
            h.app.withdraw(h.controller,a.ref('approval',ap.approval_id,ap),command_id=f'sec1-end-{ix}-{j}')
    trace=[]
    fresh=SyntheticAuthority(tuple(h.authority._principals.values()),clock=h.clock)
    # These closed owners have no remaining finance/withdraw commands. Their
    # budgets and immutable intent/reservation bodies must not fund recovery.
    protected=db._query("SELECT jsonb_build_object('budgets',(SELECT jsonb_agg(to_jsonb(b) ORDER BY owner) FROM qh.execution_budget b),"
        "'intents',(SELECT jsonb_agg(body ORDER BY intent_id) FROM qh.execution_intent),"
        "'reservations',(SELECT jsonb_agg(body ORDER BY id) FROM qh.execution_reservation));")
    def step(label,action):
        result=completion_step(db,h,label,action,trace)
        current=db._query("SELECT jsonb_build_object('budgets',(SELECT jsonb_agg(to_jsonb(b) ORDER BY owner) FROM qh.execution_budget b),"
            "'intents',(SELECT jsonb_agg(body ORDER BY intent_id) FROM qh.execution_intent),"
            "'reservations',(SELECT jsonb_agg(body ORDER BY id) FROM qh.execution_reservation));")
        require(current==protected,'SEC1_owner_borrow_'+label)
        return result
    def restart():
        h.repo=PostgresExecutionRepository.restart(db,fresh,h.source,approval_policy(h.source),h.repo._registry['inputs'],h.broker,
            expected_generation=h.authority._generation)
        h.authority=fresh;h.app=ApprovalApplication(h.repo)
    step('restart',restart)
    h.controller=step('controller',lambda:fresh.issue_session('execution-controller'))
    h.approver=step('approver',lambda:fresh.issue_session('execution-approver'))
    require(step('matched-before-disconnect',lambda:h.repo.rebind(h.controller,h.broker.query())).result=='matched','SEC1_matched')
    sid=h.repo._registry['handles'][h.approver]
    step('approver-disconnect',lambda:h.repo.control(h.approver,'disconnect'))
    require(db._query("SELECT e.wire->'payload'->>'state' FROM qh.execution_head h JOIN qh.execution_evidence e USING(account_ref,kind,id,version,hash) WHERE h.kind='session' AND h.id="+_text(sid)+';')=='paused','SEC1_disconnect_not_paused')
    require(completion_observe(db,h)['remaining']['plan']['rebind']==1,'SEC1_repair_not_reserved')
    failed=h.repo.fingerprint()
    try:h.repo.control(h.controller,'resume')
    except a.ApprovalDenied as denied:require(denied.reason=='reconciliation_required','SEC1_stale_resume_reason')
    else:raise CheckFailure('SEC1_stale_resume_allowed')
    require(h.repo.fingerprint()==failed,'SEC1_stale_resume_side_effect')
    require(step('fresh-rebind',lambda:h.repo.rebind(h.controller,h.broker.query())).result=='matched','SEC1_new_match')
    step('manual-resume',lambda:h.repo.control(h.controller,'resume'))
    require(db._query("SELECT mode FROM qh.execution_account;")=='running','SEC1_resume_not_running')
    step('controller-stop',lambda:h.repo.control(h.controller,'stop'))
    goldens['SEC1_disconnect_completion']={'trace':trace,'paused':True,'owner_budgets_unchanged':True,
        'slot':{'controller_records':13,'controller_bytes':1376256,'noncontroller_records':9,'noncontroller_bytes':851968},
        'capsule':{'records':29,'bytes':3211264}}
    checks.append('SEC1_actual_DB_disconnect_paused_fresh_rebind_manual_resume_every_rows_bytes_nonincrease_no_owner_borrow')


def completion_security_handoff(db,checks,goldens,*,cancel=False,command_boundary=False):
    """Only clock injection: real DB authority/risk/commit/close finish first."""
    h=DatabaseHarness(db,facts=());ap=h.admit(h.approved());iid=ap.consumed_intent_id
    if cancel:
        h.repo.dispatch(h.controller,iid)
        intent=h.repo.intent(h.controller,iid)
        command=h.repo.cancel(h.controller,iid,command_id='sec2-cancel',expected_version=intent.state_version)
    ready=h.repo._handoff_ready;before=h.broker.received_count;observed=[]
    def delayed(*args,**kwargs):
        value=ready(*args,**kwargs)
        require(h.repo._uow is None,'SEC2_DB_not_closed')
        window=value[2]
        observed.append({'checked_at':window.checked_at,'deadlines':window.deadlines})
        h.clock.at=command.expires_at if command_boundary else a.plus(h.clock.at,31)
        return value
    try:
        with patch.object(h.repo,'_handoff_ready',side_effect=delayed):
            if cancel:h.repo.dispatch_cancel(h.controller,command.command_id)
            else:h.repo.dispatch(h.controller,iid)
    except a.ApprovalDenied as denied:require(denied.reason=='expired','SEC2_final_expiry_reason')
    else:raise CheckFailure('SEC2_expired_handoff_allowed')
    require(len(observed)==1 and h.broker.received_count==before,'SEC2_received_expired_request')
    action='cancel' if cancel else 'submit'
    require(db._query("SELECT body->>'state' FROM qh.execution_attempt WHERE action="+_text(action)+';')=='armed','SEC2_arm_lost')
    require(db._query("SELECT bool_and((body->>'released')::numeric=0) FROM qh.execution_reservation;")=='t','SEC2_hold_released')
    # Resume of an attempt is not an API: fresh live authority still cannot
    # resend the persisted arm. Observe exact DB nonmutation on rejection.
    fresh=h.authority.issue_session('execution-controller');frozen=h.repo.fingerprint()
    try:
        if cancel:h.repo.dispatch_cancel(fresh,command.command_id)
        else:h.repo.dispatch(fresh,iid)
    except a.ApprovalDenied:pass
    else:raise CheckFailure('SEC2_armed_resend_allowed')
    require(h.repo.fingerprint()==frozen and h.broker.received_count==before,'SEC2_resend_mutation')
    label='SEC2_cancel_boundary' if command_boundary else 'SEC2_'+action
    goldens[label]={'received_delta':0,'reason':'expired','durable_attempt':'armed','holds_preserved':True,
        'noresend':True,'final_DB_committed_closed':True,'clock_after':h.clock.at,'window':observed[0]}
    checks.append(label+'_actual_DB_final_return_then_clock_advance_zero_receive_armed_hold_noresend')


def completion_security_handoff_positive(db,checks,goldens):
    h=DatabaseHarness(db,facts=());ap=h.admit(h.approved());iid=ap.consumed_intent_id
    ready=h.repo._handoff_ready;windows=[]
    def observed(*args,**kwargs):
        value=ready(*args,**kwargs)
        require(h.repo._uow is None,'SEC2_positive_DB_not_closed')
        windows.append(value[2].deadlines)
        h.clock.at=a.plus(h.clock.at,1)
        return value
    with patch.object(h.repo,'_handoff_ready',side_effect=observed):
        submitted=h.repo.dispatch(h.controller,iid)
        intent=h.repo.intent(h.controller,iid)
        command=h.repo.cancel(h.controller,iid,command_id='sec2-positive',expected_version=intent.state_version)
        cancelled=h.repo.dispatch_cancel(h.controller,command.command_id)
    require((submitted.kind,cancelled.kind,h.broker.received_count)==('accepted','cancel_ack',2),'SEC2_positive_handoff')
    goldens['SEC2_positive']={'received':2,'submit':submitted.kind,'cancel':cancelled.kind,'windows':windows}
    checks.append('SEC2_actual_DB_submit_cancel_positive_after_final_return_one_second_advance')


def completion_same_generation_third(db,checks,goldens,*,active=False):
    from synthetic_execution import replacement_source
    h=DatabaseHarness(db,facts=(),**({'target_options':{'holdings':('0','4'),'targets':('1','3'),'lot':'0.5','fee':'0'},'exposure_ceiling':'2000'} if active else {}));aps=[]
    for ix in range(2):
        ap=h.admit(h.approved(ix,label='new-ap-'+str(ix)),label='new-admit-'+str(ix));aps.append(ap)
        if active:require(h.repo.dispatch(h.controller,ap.consumed_intent_id).kind=='accepted','DEC004_active_dispatch')
        for j in range(2):require(h.app.withdraw(h.controller,a.ref('approval',ap.approval_id,ap),command_id=f'new-end-{ix}-{j}').outcome=='applied','DEC004_protective_closure')
        if active:h.repo.reclaim_completed(h.controller)
    original=db._query("SELECT jsonb_agg(to_jsonb(e) ORDER BY kind,id,version) FROM qh.execution_evidence e;")
    generation=db._query('SELECT generation FROM qh.execution_account;')
    def copies():
        return json.loads(db._query("SELECT jsonb_build_object('rows',sum(logical_records),'bytes',sum(canonical_bytes)) FROM qh.execution_state_copies("+_text(h.source.request.account_ref)+") WHERE category='control';"))
    before=copies();result=h.repo.reclaim_completed(h.controller);after=copies()
    if not active:
        require(result['records']==24 and result['commands']==8,'DEC004_reclaim24')
        require(before['rows']-after['rows']==24 and before['bytes']>after['bytes'],'DEC004_independent_copy_bytes24')
        require(db._query("SELECT jsonb_agg(to_jsonb(e) ORDER BY kind,id,version) FROM qh.execution_evidence e;")==original,'DEC004_reclaim_original_changed')
        require(db._query("SELECT count(*) FROM qh.execution_intent WHERE state='aborted_unsent';")=='2','DEC004_unsent_finality')
        h.repo.control(h.controller,'stop')
    if not active:
        require(h.repo.rebind(h.controller,h.broker.query()).result=='matched','DEC004_current_rebind')
        h.repo.control(h.controller,'resume')
    h.source=replacement_source(h.source,('0.5','3') if active else ('3','4'),label='new-third-source');h.repo.replace_source(h.controller,h.source)
    third=h.approved(0,label='third-actual-approve')
    approval_cleanup=None
    if active:
        # Finish bounded maintenance before issuing another command. Preserve
        # the completed approval evidence and both active financial holds.
        approval_cleanup=h.repo.reclaim_completed(h.controller)
        require(approval_cleanup['commands']==1 and approval_cleanup['records']==3,'DEC004_approve_lookup_reclaim3')
    challenge=h.admission_challenge(third,label='third-actual-admit')
    # Observe entry into the real calculation/gate; never replace its result.
    reached=[];admit=h.repo._admit
    def actual(state,approval,at,event):
        reached.append(sum(i.state not in d.TERMINAL for i in state['intents'].values()))
        return admit(state,approval,at,event)
    receipt=h.app.execute(h.approver,challenge) if not active else None
    if active:
        with patch.object(h.repo,'_admit',side_effect=actual):receipt=h.app.execute(h.approver,challenge)
        require(reached==[2] and (receipt.outcome,receipt.reason_code)==('rejected','capacity_exceeded'),'DEC004_active3_actual_admission_gate')
        require(rowcount(db,'execution_intent')==2 and rowcount(db,'execution_claim')==2,'DEC004_active3_mutation')
        require(db._query("SELECT count(*) FROM qh.execution_reservation WHERE (body->>'held')::numeric>0;")!='0','DEC004_active3_hold_released')
    else:
        require(receipt.outcome=='applied' and rowcount(db,'execution_intent')==3 and rowcount(db,'execution_claim')==3,'DEC004_terminal3_actual_admit')
        consumed=h.repo.head(h.approver,third.approval_id)
        require(h.repo.dispatch(h.controller,consumed.consumed_intent_id).kind=='accepted','DEC004_terminal3_real_dispatch')
    require(db._query('SELECT generation FROM qh.execution_account;')==generation,'DEC004_generation_changed')
    require(int(db._query("SELECT count(*) FROM qh.execution_intent WHERE state NOT IN ('filled','rejected','aborted_unsent','cancelled_remaining','expired_remaining');"))<=2,'DEC004_active2')
    goldens['completion_third_active' if active else 'completion_third_terminal']={'reclaim':result,'before':before,'after':after,'approval_lookup_reclaim':approval_cleanup,'admission_outcome':receipt.outcome,'active_gate_reached':reached}
    checks.append('DEC004_active3_actual_admission_gate' if active else 'DEC004_same_generation_terminal3_admission_and_dispatch')


def completion_lookup_atomicity(db,checks,goldens):
    from copy import deepcopy
    from quantharbor.adapters.postgres_execution import _pack,_unpack
    h=DatabaseHarness(db,facts=());ap=h.admit(h.approved(),label='lookup-admit')
    with ExecutionUnitOfWork(db,h.source.request.account_ref) as u:
        stored=u.call('execution_load',u.account_ref);state=_unpack(stored['state'])
    command,receipt=h.repo._past_command(state,'lookup-admit')
    pending=h.app.challenge(h.controller,a.ref('approval',ap.approval_id,ap),action='withdraw',command_id='lookup-pending')
    before=h.repo.fingerprint();future=completion_observe(db,h)
    # Owner-DML negative: absent pending maps cannot erase the immutable reserve.
    delta=[{'key':k,'mode':'map','value':{'upsert':[],'remove':[v]}} for k,v in (('commands',pending.command_id),('nonces',pending.nonce))]
    sql="BEGIN; DO $probe$ BEGIN BEGIN UPDATE qh.execution_account SET state=qh.execution_patch(state,"+_text(json.dumps(delta))+"::jsonb); SET CONSTRAINTS ALL IMMEDIATE; RAISE EXCEPTION 'expected_pending_failure'; EXCEPTION WHEN OTHERS THEN IF SQLERRM IS DISTINCT FROM 'execution_atomicity' THEN RAISE; END IF; END; END $probe$; ROLLBACK;"
    db._query(sql)
    require(h.repo.fingerprint()==before and completion_observe(db,h)==future,'DEC004_pending_map_loss')
    # Real save failure, receipt/commit injection and response loss roll back or
    # leave one observed committed result; no financial retry is introduced.
    for label in ('receipt','commit'):
        try:
            with h.repo.inject_failure(label):h.app.execute(h.controller,pending)
        except (a.ApprovalDenied,d.ExecutionDenied):pass
        else:raise CheckFailure('DEC004_injected_failure_missing')
        require(h.repo.fingerprint()==before,'DEC004_receipt_rollback_'+label)
    select=ExecutionUnitOfWork._select
    def save_failure(u,function,*values,**kwargs):
        if function=='execution_apply':
            # Actual SQL AUTH failure after staging the real reclaim delta.
            return select(u,function,'missing-reclaim-context',*values[1:],**kwargs)
        return select(u,function,*values,**kwargs)
    try:
        with patch.object(ExecutionUnitOfWork,'_select',save_failure):h.repo.reclaim_completed(h.controller)
    except (a.ApprovalDenied,d.ExecutionDenied):pass
    else:raise CheckFailure('DEC004_reclaim_SQL_save_failure_missing')
    require(h.repo.fingerprint()==before,'DEC004_reclaim_SQL_save_rollback')
    original=ExecutionUnitOfWork.commit
    def fail_commit(u):raise d.ExecutionDenied('storage_failure')
    try:
        with patch.object(ExecutionUnitOfWork,'commit',fail_commit):h.repo.reclaim_completed(h.controller)
    except (a.ApprovalDenied,d.ExecutionDenied):pass
    else:raise CheckFailure('DEC004_reclaim_commit_failure_missing')
    require(h.repo.fingerprint()==before,'DEC004_reclaim_commit_rollback')
    def lost_reply(u):original(u);raise d.ExecutionDenied('storage_failure')
    try:
        with patch.object(ExecutionUnitOfWork,'commit',lost_reply):h.repo.reclaim_completed(h.controller)
    except (a.ApprovalDenied,d.ExecutionDenied):pass
    else:raise CheckFailure('DEC004_reclaim_response_loss_missing')
    require(h.repo.command_result(h.controller,command.command_id)==receipt,'DEC004_response_loss_observation')
    frozen=h.repo.fingerprint()
    require(h.app.execute(h.approver,command)==receipt,'DEC004_reclaimed_exact_replay')
    require(h.app.challenge(h.approver,command.target_ref,action='admit',command_id=command.command_id)==command,'DEC004_reclaimed_exact_challenge')
    for altered in (replace(command,nonce='bad-nonce'),replace(command,action='withdraw'),replace(command,expected_state_version=command.expected_state_version+1)):
        try:h.app.execute(h.approver,altered)
        except (a.ApprovalDenied,d.ExecutionDenied):pass
        else:raise CheckFailure('DEC004_mutated_replay_accepted')
    try:h.app.execute(h.controller,command)
    except (a.ApprovalDenied,d.ExecutionDenied):pass
    else:raise CheckFailure('DEC004_foreign_session_replay')
    require(h.repo.fingerprint()==frozen,'DEC004_replay_growth')
    h.repo.change_permissions(h.controller,'execution-approver',('query',))
    try:h.app.execute(h.approver,command)
    except (a.ApprovalDenied,d.ExecutionDenied):pass
    else:raise CheckFailure('DEC004_revoked_replay')
    h.repo.rotate(h.controller);h.controller=h.authority.issue_session('execution-controller');h.approver=h.authority.issue_session('execution-approver')
    try:h.app.execute(h.approver,command)
    except (a.ApprovalDenied,d.ExecutionDenied):pass
    else:raise CheckFailure('DEC004_oldgeneration_execute')
    require(h.repo.command_result(h.controller,command.command_id)==receipt,'DEC004_historical_authorized_query')
    checks.append('DEC004_pending_map_immutable_reserve_completed_reclaim_replay_auth_atomicity_commit_loss')


def completion_approval_terminal(db,checks,goldens,*,action='revoke',atomic=False,sibling=None,expiry=None):
    """Root actual DB: unconsumed approval closure, rejection and repair.

    Elective issuance/rebind may increase charge within the fixed caps. Issued
    completion, funded atomic withdrawal, fresh repair and resume may not.
    No heartbeat saturation is used: it would hit the separate session budget.
    """
    require(action in ('revoke','withdraw','admit') and sibling in (None,'withdraw','admit')
        and expiry in (None,'command','approval') and (not atomic or action=='withdraw'),
        'LIFECYCLE_scenario_arguments')
    h=DatabaseHarness(db,facts=());ap=h.approved();ar=a.ref('approval',ap.approval_id,ap)
    trace=[];issued=[]
    def issue(which,label):
        actor=h.controller if which=='withdraw' else h.approver
        before=completion_observe(db,h)
        challenge=h.app.challenge(actor,ar,action=which,command_id=label)
        after=completion_observe(db,h)
        trace.append({'stage':'elective-issue-'+which,'before':before,'after':after})
        issued.append((actor,challenge))
        return actor,challenge
    if sibling:other_actor,other=issue(sibling,'lifecycle-sibling')
    actor,command=(h.controller,None) if atomic else issue(action,'lifecycle-terminal')
    immutable=db._query("SELECT jsonb_agg(to_jsonb(e) ORDER BY kind,id,version) FROM qh.execution_evidence e;")
    if issued:
        # Prove the reserve is independent of mutable command/nonce lookup.
        # The attempted loss then reaches the actual deferred SQL coupling.
        pending=issued[0][1];before=h.repo.fingerprint();future=completion_observe(db,h)
        delta=[{'key':k,'mode':'map','value':{'upsert':[],'remove':[v]}}
            for k,v in (('commands',pending.command_id),('nonces',pending.nonce))]
        patch_sql='UPDATE qh.execution_account SET state=qh.execution_patch(state,'+_text(json.dumps(delta))+'::jsonb); '
        account=_text(h.source.request.account_ref)
        charge=json.loads(db._query('BEGIN; '+patch_sql+'SELECT qh.execution_common_remaining('+account+'); ROLLBACK;'))
        require(charge==future['remaining'],'LIFECYCLE_pending_reserve_depends_on_lookup')
        db._query("BEGIN; DO $probe$ BEGIN BEGIN "+patch_sql+
            "SET CONSTRAINTS ALL IMMEDIATE; RAISE EXCEPTION 'expected_pending_failure'; "
            "EXCEPTION WHEN OTHERS THEN IF SQLERRM IS DISTINCT FROM 'execution_atomicity' THEN RAISE; END IF; END; END $probe$; ROLLBACK;")
        require(h.repo.fingerprint()==before,'LIFECYCLE_pending_map_loss_rollback')
    completion_step(db,h,'stop',lambda:h.repo.control(h.controller,'stop'),trace)
    # Normal stopped has resume=0. This optional entry must buy every new live
    # session/approval/command repair obligation before its SQL commit.
    before=completion_observe(db,h)
    require(before['remaining']['plan']['resume']==0,'LIFECYCLE_normal_stop_resume_promise')
    rec=h.repo.rebind(h.controller,h.broker.query())
    after=completion_observe(db,h)
    require(rec.result=='matched' and after['remaining']['plan']['resume']==1
        and after['remaining']['plan']['rebind']==0,'LIFECYCLE_optional_rebind')
    trace.append({'stage':'elective-rebind-funds-new-obligations','before':before,'after':after})
    if command is not None:
        frozen=h.repo.fingerprint()
        for wrong_actor,wrong_command in ((h.approver if actor is h.controller else h.controller,command),
                (actor,replace(command,nonce='lifecycle-wrong-nonce'))):
            try:h.app.execute(wrong_actor,wrong_command)
            except (a.ApprovalDenied,d.ExecutionDenied) as denied:
                require(denied.reason in ('authority_denied','replay_conflict','nonce_unknown'),'LIFECYCLE_auth_denial')
            else:raise CheckFailure('LIFECYCLE_wrong_current_authority_accepted')
            require(h.repo.fingerprint()==frozen,'LIFECYCLE_auth_denial_mutated')
    # Every pre-existing immutable row survives, including pending challenges.
    original=json.loads(immutable)
    def retained():
        current=json.loads(db._query("SELECT jsonb_agg(to_jsonb(e) ORDER BY kind,id,version) FROM qh.execution_evidence e;"))
        require(all(row in current for row in original),'LIFECYCLE_immutable_evidence_lost')
        require(rowcount(db,'execution_intent')==0 and db._query('SELECT count(*) FROM qh.execution_budget;')=='0',
            'LIFECYCLE_owner_cost_borrow')
    if expiry:h.clock.at=command.expires_at if expiry=='command' else ap.expires_at
    receipt=completion_step(db,h,'terminal-'+action,
        (lambda:h.app.withdraw(actor,ar,command_id='lifecycle-atomic')) if atomic else
        (lambda:h.app.execute(actor,command)),trace)
    require((receipt.outcome,receipt.reason_code)==(('rejected','expired') if expiry else ('applied',None)),
        'LIFECYCLE_terminal_outcome')
    retained()
    if expiry=='approval':
        # The earlier unresolved/blocked observation remains in the immutable
        # lifecycle evidence JSON. DEC005 now requires positive current recovery.
        require(h.repo.head(h.approver,ap.approval_id).state=='expired','LIFECYCLE_target_not_expired')
        fresh=completion_step(db,h,'DEC005-expired-approval-current-reconcile',
            lambda:h.repo.reconcile(h.controller,h.broker.query()),trace)
        require(fresh.result=='matched','DEC005_expired_approval_current_recovery')
        completion_step(db,h,'DEC005-expired-approval-explicit-resume',lambda:h.repo.control(h.controller,'resume'),trace)
        before=h.broker.received_count;frozen=h.repo.fingerprint()
        replay=h.app.execute(actor,command)
        require(replay==receipt and h.broker.received_count==before and h.repo.fingerprint()==frozen,
            'DEC005_expired_approval_replay_effect')
        expired=h.repo.head(h.approver,ap.approval_id)
        try:h.app.challenge(actor,a.ref('approval',expired.approval_id,expired),action='admit',command_id='expired-new-nonce')
        except a.ApprovalDenied:pass
        else:raise CheckFailure('DEC005_expired_new_nonce')
        retained()
        goldens['approval_terminal_expired_target']={'trace':trace,'terminal_nonincrease':True,
            'fresh_reconcile':'matched','manual_resume':'running','broker_effects':0,
            'previous_diagnostic':'docs/evidence/execution-database-lifecycle-fixes-2026-10-27.json'}
        checks.append('DEC005_expired_approval_terminal_rows_bytes_matched_resume_no_replay_effect')
        return
    # Even a rejected receipt changes the aggregate read-set. Stale manual
    # resume must fail, then a genuinely new query+reconciliation must fit.
    def repair(label):
        require(completion_observe(db,h)['remaining']['plan']['rebind']==1,'LIFECYCLE_repair_not_reserved')
        frozen=h.repo.fingerprint()
        try:h.repo.control(h.controller,'resume')
        except a.ApprovalDenied as denied:require(denied.reason=='reconciliation_required','LIFECYCLE_stale_resume_reason')
        else:raise CheckFailure('LIFECYCLE_stale_resume_accepted')
        require(h.repo.fingerprint()==frozen,'LIFECYCLE_stale_resume_mutated')
        fresh=completion_step(db,h,label,lambda:h.repo.reconcile(h.controller,h.broker.query()),trace)
        require(fresh.result=='matched' and fresh.query_ref!=rec.query_ref,'LIFECYCLE_fresh_query_match')
    repair('fresh-reconcile')
    if sibling:
        rejected=completion_step(db,h,'issued-sibling-rejected',lambda:h.app.execute(other_actor,other),trace)
        require((rejected.outcome,rejected.reason_code)==('rejected','version_conflict'),'LIFECYCLE_sibling_rejection')
        repair('fresh-reconcile-after-sibling')
    if expiry=='command':
        require(h.repo.head(h.approver,ap.approval_id).state=='approved','LIFECYCLE_rejection_killed_live_approval')
        completion_step(db,h,'atomic-after-expired-command',
            lambda:h.app.withdraw(h.controller,ar,command_id='lifecycle-after-rejection'),trace)
        repair('fresh-reconcile-after-atomic')
    completion_step(db,h,'manual-resume',lambda:h.repo.control(h.controller,'resume'),trace)
    require(db._query('SELECT mode FROM qh.execution_account;')=='running','LIFECYCLE_manual_resume_mode')
    retained()
    # Replays must still use current permissions, even after durable completion.
    if command is not None:
        principal='execution-controller' if actor is h.controller else 'execution-approver'
        h.repo.change_permissions(h.controller,principal,('query',))
        frozen=h.repo.fingerprint()
        try:h.app.execute(actor,command)
        except a.ApprovalDenied as denied:require(denied.reason=='authority_denied','LIFECYCLE_revoked_replay_reason')
        else:raise CheckFailure('LIFECYCLE_revoked_replay_accepted')
        require(h.repo.fingerprint()==frozen,'LIFECYCLE_revoked_replay_mutated')
    label='approval_terminal_'+action+('_atomic' if atomic else '_issued')+('_sibling_'+sibling if sibling else '')+('_expired_'+expiry if expiry else '')
    goldens[label]={'trace':trace,'outcome':receipt.outcome,'reason':receipt.reason_code,
        'immutable_retained':True,'pending_lookup_negative':bool(issued),'actual_DB':True}
    checks.append('LIFECYCLE_'+label+'_rows_bytes_auth_immutable_fresh_reconcile_manual_resume')


def recovery_validity(db,checks,goldens,*,mode='request'):
    """DEC005 actual DB acceptance; authored here, only root executes this."""
    from synthetic_execution import fresh_target_source
    from quantharbor.application.approval import source_bytes
    require(mode in ('empty','request','policy','fresh','runtime','unknown','cost','rights'),'DEC005_mode')
    options={'facts':()} if mode not in ('unknown','cost') else ({'response':'timeout','facts':()} if mode=='unknown' else {'facts':(financial_fact('recovery-unknown-cost',fee=None),)})
    h=DatabaseHarness(db,**options);trace=[]
    original_source=h.source;old=None
    if mode in ('unknown','cost'):
        old=h.admit(h.approved());iid=old.consumed_intent_id
        receipt=h.repo.dispatch(h.controller,iid)
        if mode=='cost':require(h.repo.receive(h.broker.issue_event(receipt,0))=='observed_incomplete','DEC005_cost_setup')
    elif mode=='fresh':old=h.approved()
    original=json.loads(db._query("SELECT jsonb_agg(to_jsonb(e) ORDER BY kind,id,version) FROM qh.execution_evidence e;"))
    completion_step(db,h,'stop',lambda:h.repo.control(h.controller,'stop'),trace)
    if mode=='runtime':
        h.repo.change_permissions(h.controller,'execution-controller',('runtime','query','resume','stop'))
        frozen=h.repo.fingerprint();inputs=h.repo._registry['inputs']
        try:h.repo.rebind(h.controller,h.broker.query(),execution_policy=replace(h.inputs.policy,version=2))
        except a.ApprovalDenied as denied:require(denied.reason=='authority_denied','DEC005_runtime_policy_reason')
        else:raise CheckFailure('DEC005_runtime_policy_escalation')
        require(h.repo.fingerprint()==frozen and h.repo._registry['inputs'] is inputs,'DEC005_runtime_policy_mutated')
    elif mode=='rights':
        market=tuple(replace(x,current_rights=replace(x.current_rights,purposes=('store','research'))) for x in h.inputs.current.current.market_inputs)
        frozen=h.repo.fingerprint();inputs=h.repo._registry['inputs']
        try:h.repo.rebind(h.controller,h.broker.query(),market_inputs=market)
        except (d.ExecutionDenied,a.ApprovalDenied):pass
        else:raise CheckFailure('DEC005_report_rights_ignored')
        require(h.repo.fingerprint()==frozen and h.repo._registry['inputs'] is inputs,'DEC005_rights_mutated')
        short=tuple(replace(x,current_rights=replace(x.current_rights,valid_to=a.plus(h.clock.at,2)))
            for x in h.inputs.current.current.market_inputs)
        rec=h.repo.rebind(h.controller,h.broker.query(),market_inputs=short)
        require(rec.result=='matched' and rec.valid_to==a.plus(h.clock.at,2),'DEC005_rights_absolute_deadline')
        h.clock.at=rec.valid_to;frozen=h.repo.fingerprint()
        try:h.repo.control(h.controller,'resume')
        except a.ApprovalDenied:pass
        else:raise CheckFailure('DEC005_rights_at_valid_to_resumed')
        require(h.repo.fingerprint()==frozen,'DEC005_rights_boundary_mutated')
    elif mode in ('unknown','cost'):
        before=db._query('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM qh.execution_reservation r;')
        fresh=fresh_target_source(h.source,at=h.clock.at)
        h.repo.replace_source(h.controller,fresh)
        frozen=h.repo.fingerprint()
        try:h.repo.rebind(h.controller,h.broker.query(1 if mode=='cost' else 0))
        except (d.ExecutionDenied,a.ApprovalDenied):pass
        else:raise CheckFailure('DEC005_financial_hold_released')
        require(h.repo.fingerprint()==frozen,'DEC005_failed_rebind_mutated')
        require(db._query('SELECT jsonb_agg(to_jsonb(r) ORDER BY id) FROM qh.execution_reservation r;')==before,'DEC005_reservation_changed')
        try:h.repo.control(h.controller,'resume')
        except a.ApprovalDenied:pass
        else:raise CheckFailure('DEC005_unknown_resumed')
    else:
        if mode=='request':
            h.repo.rebind(h.controller,h.broker.query(),execution_policy=replace(h.inputs.policy,version=2,valid_to=a.plus(AT,120)))
            h.clock.at=h.source.request.expires_at
        elif mode in ('policy','fresh'):
            h.clock.at=h.inputs.policy.valid_to if mode=='policy' else a.plus(h.source.request.expires_at,1)
            frozen=h.repo.fingerprint()
            rec=h.repo.reconcile(h.controller,h.broker.query())
            require(rec.result=='unresolved','DEC005_expired_policy_not_blocked')
            blocked=h.repo.fingerprint()
            try:h.repo.control(h.controller,'resume')
            except a.ApprovalDenied:pass
            else:raise CheckFailure('DEC005_expired_policy_resumed')
            require(h.repo.fingerprint()==blocked,'DEC005_expired_resume_mutated')
            if mode=='fresh':
                fresh=fresh_target_source(h.source,at=h.clock.at)
                require(all(c.candidate_id!=original_source.artifacts.candidates[0].candidate_id for c in fresh.artifacts.candidates),'DEC005_old_candidate_present')
                h.repo.replace_source(h.controller,fresh);h.source=fresh
                require(h.repo._registry['source_history']==(original_source,),'DEC005_original_not_retained')
                require(h.repo.head(h.approver,old.approval_id).state=='invalidated','DEC005_old_approval_live')
        if mode in ('policy','fresh'):
            ep=replace(h.inputs.policy,version=2,valid_to=a.plus(h.clock.at,30))
            rec=h.repo.rebind(h.controller,h.broker.query(),execution_policy=ep)
        elif mode=='empty':
            # No prior resume obligation exists after an ordinary stop. This
            # elective initial rebind must fund the new recovery promises;
            # only the following explicit resume is mandatory completion.
            before=completion_observe(db,h)
            rec=h.repo.rebind(h.controller,h.broker.query())
            after=completion_observe(db,h)
            require(before['remaining']['plan']['resume']==0 and after['remaining']['plan']['resume']==1,'DEC005_empty_rebind_obligations')
            require(after['records']<=128 and after['bytes']<=8388608,'DEC005_empty_rebind_capacity')
            trace.append({'stage':'elective-empty-rebind','before':before,'after':after})
        else:
            # Request TTL elapsed while the account's matched validity remains
            # current. A new reconciliation is elective, not funded repair.
            before=completion_observe(db,h)
            rec=h.repo.reconcile(h.controller,h.broker.query())
            after=completion_observe(db,h)
            require(before['remaining']['plan']['rebind']==0 and before['remaining']['plan']['resume']==1,'DEC005_request_current_rebind_not_due')
            require(after['remaining']['plan']['resume']==1,'DEC005_request_resume_obligation_lost')
            require(after['records']<=128 and after['bytes']<=8388608,'DEC005_request_reconcile_capacity')
            trace.append({'stage':'elective-request-expiry-current-reconcile','before':before,'after':after})
        require(rec.result=='matched' and rec.validator_version=='q27-account-current-v1' and rec.valid_from<=h.clock.at<rec.valid_to,'DEC005_current_match')
        completion_step(db,h,'explicit-resume',lambda:h.repo.control(h.controller,'resume'),trace)
        if mode=='fresh':
            ap=h.approved(label='recovery-new-approval');ap=h.admit(ap,label='recovery-new-admit')
            require(h.repo.dispatch(h.controller,ap.consumed_intent_id).kind=='accepted','DEC005_new_candidate_dispatch')
            require(h.broker.received_count==1,'DEC005_new_effect_count')
            archived=json.loads(db._query("SELECT qh.execution_map_get(state,'\"source_archive\"') FROM qh.execution_account;"))
            require(archived['tuple'][0]['bytes'].encode()==source_bytes(original_source),'DEC005_DB_original_archive')
        else:require(h.broker.received_count==0 and rowcount(db,'execution_intent')==0,'DEC005_recovery_created_order')
    retained=json.loads(db._query("SELECT jsonb_agg(to_jsonb(e) ORDER BY kind,id,version) FROM qh.execution_evidence e;"))
    require(all(row in retained for row in original),'DEC005_original_history_lost')
    goldens['DEC005_'+mode]={'trace':trace,'received':h.broker.received_count,'original_retained':True,
        'storage':json.loads(db._query('SELECT qh.execution_common_charge('+_text(original_source.request.account_ref)+');'))}
    checks.append('DEC005_'+mode+'_actual_boundary_original_rows_bytes')


def recovery_binding_transaction(db,checks,goldens,*,mode='rollback'):
    """Real SQL read-set attacks, rollback, and actual COMMIT EOF observation."""
    from copy import deepcopy
    from synthetic_execution import fresh_target_source
    require(mode in ('rollback','commit_loss','sql'),'DEC005_transaction_mode')
    h=DatabaseHarness(db,facts=());h.repo.control(h.controller,'stop')
    before=h.repo.fingerprint();source=h.repo._registry['source'];inputs=h.repo._registry['inputs']
    fresh=fresh_target_source(source,at=h.clock.at)
    if mode=='commit_loss':
        def lost(uow):uow._exchange('COMMIT;\n\\quit',result=False)
        try:
            with patch.object(ExecutionUnitOfWork,'commit',lost):h.repo.replace_source(h.controller,fresh)
        except (d.ExecutionDenied,a.ApprovalDenied):pass
        else:raise CheckFailure('DEC005_COMMIT_EOF_not_observed')
        require(h.repo._registry['source'] is fresh and not h.repo._registry.get('blocked'), 'DEC005_COMMIT_binding_not_observed')
        require(h.repo.fingerprint()!=before and h.broker.received_count==0,'DEC005_COMMIT_effects')
        rec=h.repo.rebind(h.controller,h.broker.query())
        require(rec.result=='matched','DEC005_COMMIT_rebind')
        # A second actual commit whose binding observation fails must block
        # every facade. The root observes the DB without reviving old handles.
        another=fresh_target_source(fresh,at=h.clock.at,label='ambiguous-source',values=('2','1'))
        after_commit={'value':False};read=ExecutionUnitOfWork._read
        def ambiguous_commit(uow):
            try:uow._exchange('COMMIT;\n\\quit',result=False)
            finally:after_commit['value']=True
        def unavailable(uow,*args,**kwargs):
            if after_commit['value']:raise d.ExecutionDenied('storage_failure')
            return read(uow,*args,**kwargs)
        try:
            with patch.object(ExecutionUnitOfWork,'commit',ambiguous_commit),patch.object(ExecutionUnitOfWork,'_read',unavailable):
                h.repo.replace_source(h.controller,another)
        except (d.ExecutionDenied,a.ApprovalDenied):pass
        else:raise CheckFailure('DEC005_ambiguous_COMMIT_not_lost')
        require(h.repo._registry.get('blocked') is True,'DEC005_ambiguous_binding_not_blocked')
        try:h.repo.fingerprint()
        except d.ExecutionDenied:pass
        else:raise CheckFailure('DEC005_ambiguous_facade_not_blocked')
        observed=PostgresExecutionRepository.current_runtime(db,h.source.request.account_ref)
        require(observed['mode'] in ('stopped','reconciling'),'DEC005_ambiguous_resume')
    else:
        captured={};chunks=[];select=ExecutionUnitOfWork._select
        def capture(uow,function,*values,**kw):
            if function=='execution_stage_chunk':chunks.append(bytes.fromhex(values[2]))
            if function=='execution_issue_context':
                captured.update(header=json.loads(values[4]),payload=json.loads(b''.join(chunks)));chunks.clear()
            if function=='execution_apply' and captured:raise d.ExecutionDenied('storage_failure')
            return select(uow,function,*values,**kw)
        try:
            with patch.object(ExecutionUnitOfWork,'_select',capture):
                if mode=='sql':h.repo.rebind(h.controller,h.broker.query())
                else:h.repo.replace_source(h.controller,fresh)
        except (d.ExecutionDenied,a.ApprovalDenied):pass
        else:raise CheckFailure('DEC005_capture_not_aborted')
        require(captured and h.repo.fingerprint()==before and h.repo._registry['source'] is source and h.repo._registry['inputs'] is inputs,'DEC005_staged_rollback')
        if mode=='sql':
            mutations=('version','generation','fence','source_hash','current_identity','validator_version','valid_to','query_ref','ledger_cursor')
            for name in mutations:
                header,payload=deepcopy(captured['header']),deepcopy(captured['payload'])
                if name in ('version','fence'):header[name]+=1
                elif name in ('generation','source_hash'):header[name]='0'*64
                elif name=='valid_to':header['current_validation'][name]=AT
                elif name=='query_ref':header['current_validation'][name]['sha256']='0'*64
                elif name=='ledger_cursor':header['current_validation'][name]+=1
                else:header['current_validation'][name]='0'*64
                with ExecutionUnitOfWork(db,h.source.request.account_ref) as uow:
                    token=stage_context(uow,h.source.request.account_ref,header,payload,token='recovery-binding-probe')
                    expect_context_auth(uow,token,'save')
                require(h.repo.fingerprint()==before,'DEC005_SQL_rollback_'+name)
            rec=h.repo.rebind(h.controller,h.broker.query())
            require(rec.result=='matched','DEC005_SQL_positive')
    require(h.broker.received_count==0,'DEC005_binding_economic_effect')
    goldens['DEC005_transaction_'+mode]={'received':0,
        'binding_publication':'exact_observation_then_ambiguity_blocks' if mode=='commit_loss' else 'unchanged_on_rollback_or_exact_SQL_binding'}
    checks.append('DEC005_transaction_'+mode+'_actual_DB_registry_CAS_readset')


def main():
    if len(sys.argv)!=1:
        print(json.dumps({'status':'fail','reason':'arguments_not_accepted','checks':[],'cleanup':[]}))
        return 2
    started=time.monotonic()
    result={'scope':'Q27_synthetic_actual_database_only','status':'partial','q27_complete':False,
            'checks':[],'goldens':{},'remaining':REMAINING,'cleanup':[],'phase':'preflight',
            'fixture_sha256':d.FIXTURE_SHA,'migration_sha256':sha256(MIGRATION.read_bytes()).hexdigest()}
    exit_code=0
    try:
        require(sha256((ROOT/'docs/contracts/execution-fixture-v1.json').read_bytes()).hexdigest()==d.FIXTURE_SHA,'fixture_hash')
        for scenario_number,scenario in enumerate((primary,lambda db,c,g:crash(db,c,g,before_handoff=True),
                         lambda db,c,g:crash(db,c,g,before_handoff=False),withdrawal,contention,lambda db,c,g:contention(db,c,g,winner=1),
                         commit_reply_loss,duplicate_claims,multi_price,unknown_cost,cumulative,sale,negative_financial,excessive_cost,obligations,
                         lambda db,c,g:corrected_current(db,c,g,mode='delta'),
                         lambda db,c,g:corrected_current(db,c,g,mode='cumulative'),
                         lambda db,c,g:corrected_current(db,c,g,mode='multi'),
                         lambda db,c,g:corrected_current(db,c,g,mode='cost'),finality,
                         lambda db,c,g:sellable_bound(db,c,g,quantity=7),
                         lambda db,c,g:sellable_bound(db,c,g,quantity=8),
                         lambda db,c,g:risk_negative(db,c,g,mode='exposure'),
                         lambda db,c,g:risk_negative(db,c,g,mode='daily'),
                         lambda db,c,g:risk_negative(db,c,g,mode='turnover'),
                         lambda db,c,g:risk_negative(db,c,g,mode='loss'),
                         lambda db,c,g:risk_negative(db,c,g,mode='drawdown'),
                         control_cancel,lambda db,c,g:control_cancel(db,c,g,mode='unknown'),control_cancel_conflict,
                         lambda db,c,g:control_race(db,c,g,first='dispatch',action='stop'),
                         lambda db,c,g:control_race(db,c,g,first='protect',action='stop'),
                         lambda db,c,g:control_race(db,c,g,first='dispatch',action='withdraw'),
                         lambda db,c,g:control_race(db,c,g,first='protect',action='withdraw'),control_protect_rights,
                         lambda db,c,g:control_restart(db,c,g,mode='corrected'),
                         lambda db,c,g:control_restart(db,c,g,mode='quarantine'),
                         lambda db,c,g:control_restart(db,c,g,mode='unknown'),
                         lambda db,c,g:control_restart(db,c,g,mode='before_handoff'),
                         lambda db,c,g:control_restart(db,c,g,mode='late_completion'),control_restart_reply_loss,
                         lambda db,c,g:control_cancel_fault(db,c,g,phase='before_cancel_handoff'),
                         lambda db,c,g:control_cancel_fault(db,c,g,phase='after_cancel_handoff'),
                         control_proven_unsent,lambda db,c,g:control_proven_unsent(db,c,g,sent=True),control_resume_binding,
                         lambda db,c,g:literal_sell_holds(db,c,g,quantity=7),
                         lambda db,c,g:literal_sell_holds(db,c,g,quantity=8),literal_exposure,
                         storage_independent,storage_manifest_deny,storage_saturated_completion,storage_terminal_third,sql_auth_closed,frame_rollback,
                         completion_recovery_orders,
                         lambda db,c,g:completion_recovery_orders(db,c,g,order='two_controllers'),
                         lambda db,c,g:completion_recovery_orders(db,c,g,order='invalidated'),
                         completion_same_generation_third,
                         lambda db,c,g:completion_same_generation_third(db,c,g,active=True),completion_lookup_atomicity,
                         completion_security_disconnect,completion_security_handoff,
                         lambda db,c,g:completion_security_handoff(db,c,g,cancel=True),
                         lambda db,c,g:completion_security_handoff(db,c,g,cancel=True,command_boundary=True),
                         completion_security_handoff_positive,
                         completion_approval_terminal,
                         lambda db,c,g:completion_approval_terminal(db,c,g,action='withdraw'),
                         lambda db,c,g:completion_approval_terminal(db,c,g,action='withdraw',atomic=True),
                         lambda db,c,g:completion_approval_terminal(db,c,g,sibling='withdraw'),
                         lambda db,c,g:completion_approval_terminal(db,c,g,action='withdraw',atomic=True,sibling='admit'),
                         lambda db,c,g:completion_approval_terminal(db,c,g,expiry='command'),
                         lambda db,c,g:completion_approval_terminal(db,c,g,action='admit',expiry='approval'),
                         lambda db,c,g:recovery_validity(db,c,g,mode='empty'),
                         lambda db,c,g:recovery_validity(db,c,g,mode='request'),
                         lambda db,c,g:recovery_validity(db,c,g,mode='policy'),
                         lambda db,c,g:recovery_validity(db,c,g,mode='fresh'),
                         lambda db,c,g:recovery_validity(db,c,g,mode='runtime'),
                         lambda db,c,g:recovery_validity(db,c,g,mode='unknown'),
                         lambda db,c,g:recovery_validity(db,c,g,mode='cost'),
                         lambda db,c,g:recovery_validity(db,c,g,mode='rights'),
                         lambda db,c,g:recovery_binding_transaction(db,c,g,mode='rollback'),
                         lambda db,c,g:recovery_binding_transaction(db,c,g,mode='commit_loss'),
                         lambda db,c,g:recovery_binding_transaction(db,c,g,mode='sql')),start=1):
            print('scenario:'+str(scenario_number)+':start',file=sys.stderr,flush=True)
            result['phase']=getattr(scenario,'__name__','bounded_scenario')
            db=PostgresLedger()
            try:
                with db:
                    result['phase'] += ':migration'
                    install(db)
                    result['phase'] = result['phase'].removesuffix(':migration')+':scenario'
                    scenario(db,result['checks'],result['goldens'])
            except Exception:
                print('scenario:'+str(scenario_number)+':fail:CHECK',file=sys.stderr,flush=True)
                raise
            finally:
                result['cleanup'].append({'project':db._project,'result':db.cleanup})
            print('scenario:'+str(scenario_number)+':end',file=sys.stderr,flush=True)
        result['checks'].append('EX40_own_UUID_projects_fixed_image_migrations_idempotent_cleanup')
        result['reason']='implemented_checks_pass_remaining_contract_work'
    except (CheckFailure,LedgerStorageError,d.ExecutionDenied,a.ApprovalDenied) as failure:
        result['status']='fail'
        result['reason']=getattr(failure,'reason','synthetic_database_failure')
        exit_code=1
    except Exception:
        result['status']='fail'
        result['reason']='runner_contract_failure'
        exit_code=1
    result['elapsed_seconds']=round(time.monotonic()-started,3)
    print(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    return exit_code


if __name__=='__main__':
    raise SystemExit(main())
