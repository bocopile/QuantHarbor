"""Q27 제어의 실제 공개 호출 경로. 메모리 저장 participant이며 PostgreSQL 증명이 아니다.

권한/위험/원장 계산은 제품 함수를 그대로 사용한다. Docker/외부 호출 없음.
"""
from copy import deepcopy
from dataclasses import asdict,replace
import json
from threading import Barrier,Event
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

import quantharbor.adapters.postgres_execution as adapter
from quantharbor.adapters.postgres_execution import PostgresExecutionRepository,_unpack
from quantharbor.adapters.postgres_ledger import PostgresLedger
from quantharbor.adapters.synthetic_approval import SyntheticAuthority,FixturePrincipal
from quantharbor.adapters.synthetic_ledger import SyntheticLedger
from quantharbor.adapters.synthetic_execution_broker import SyntheticExecutionBroker
from quantharbor.application.approval import ApprovalApplication
from quantharbor.domain import approval as a,execution as d
from quantharbor.domain.serialization import parse_payload
from synthetic_approval import Clock,policy
from synthetic_execution import composition,AT,CORRECTION_FACTS,CORRECTION_MANIFESTS
from quantharbor.domain.target import ref as target_ref
from test_execution_financial import fact


class LocalParticipant:
    """선형화된 transaction 사본. DB/SQL/다중 process 격리 주장은 하지 않는다."""
    def __init__(self,db,account):
        self.db,self.account=db,account
    def __enter__(self):
        self.stored=deepcopy(self.db.local_stored)
        self.ledger=SyntheticLedger()
        self.ledger._states=deepcopy(self.db.local_ledger._states)
        self.committed=False
        return self
    def __exit__(self,*args): pass
    def commit(self):
        if self.db.fail_commit: raise d.ExecutionDenied('storage_failure')
        self.db.local_stored=self.stored
        self.db.local_ledger=self.ledger
        self.committed=True
    def call(self,function,*args):
        if function=='execution_load': return deepcopy(self.stored)
        if function=='execution_save':
            account,obj,version=args
            if int(version)!=(-1 if self.stored is None else self.stored['version']): raise d.ExecutionDenied('version_conflict')
            self.stored={'version':int(version)+1,'state':deepcopy(obj['state']),'source_hash':obj['source_hash']}
            return self.stored['version']
        if function=='execution_event': return True
        if function=='execution_fingerprint': return self.stored
        if function=='execution_ledger':
            account,operation,payload,at=args
            if operation=='events': return [asdict(e) for e in self.ledger.state(account).events]
            if operation=='replay': return asdict(self.ledger.replay(account,as_of=payload or at,knowledge_cutoff=at))
            if operation=='append':
                obj=parse_payload(json.dumps(dict(schema_name='SyntheticLedgerSubmission',schema_version=1,environment='synthetic',payload=payload))).payload
                return asdict(self.ledger.append(obj,recorded_at=at))
        raise AssertionError(function)


class ControlHarness:
    def __init__(self,*,reporting=True,**options):
        self.source,self.inputs,self.broker=composition(**options)
        self.clock=Clock()
        self.db=PostgresLedger(); self.db._ready=True
        self.db.local_stored=None; self.db.local_ledger=SyntheticLedger(); self.db.fail_commit=False
        for e in self.source.inputs.events:
            self.db.local_ledger.append(e.body.submission,recorded_at=e.body.recorded_at)
        account=self.source.request.account_ref
        self.principals=(
            FixturePrincipal('approver',account,'approver',('present','approve','deny','revoke','withdraw','admit','query','heartbeat','disconnect')),
            FixturePrincipal('controller',account,'controller',('session','stop','resume','dispatch','withdraw','runtime','policy','heartbeat','disconnect','query')),
            *((FixturePrincipal('reader',account,'reporting',('query',)),) if reporting else ()))
        self.authority=SyntheticAuthority(self.principals,clock=self.clock)
        self.repo=PostgresExecutionRepository(self.db,self.authority,self.source,policy(self.source),self.inputs,self.broker,cancel_principals=('controller',))
        self.app=ApprovalApplication(self.repo)
        self.approver=self.authority.issue_session('approver'); self.controller=self.authority.issue_session('controller')
        self.reader=self.authority.issue_reader('reader') if reporting else None
        rec=self.repo.reconcile(self.controller,self.inputs.query)
        assert rec.result=='matched',rec.unresolved
        self.repo.control(self.controller,'resume')
        self.clock.at=AT
    def approved(self,index=0,label='approve'):
        candidate=self.source.artifacts.candidates[index]
        _,ap=self.app.present(self.approver,target_ref('candidate',candidate.candidate_id,candidate))
        c=self.app.challenge(self.approver,a.ref('approval',ap.approval_id,ap),action='approve',command_id=label)
        assert self.app.execute(self.approver,c).outcome=='applied'
        return self.repo.head(self.approver,ap.approval_id)
    def admit(self,approval=None):
        ap=self.approved() if approval is None else approval
        c=self.app.challenge(self.approver,a.ref('approval',ap.approval_id,ap),action='admit',command_id='admit')
        self.admission_command=c
        result=self.app.execute(self.approver,c); assert result.outcome=='applied',result.reason_code
        self.approval=self.repo.head(self.approver,ap.approval_id)
        self.iid=self.approval.consumed_intent_id
        return self.approval
    def send(self):
        self.admit(); self.receipt=self.repo.dispatch(self.controller,self.iid); return self.receipt
    def cancel(self,label='cancel'):
        i=self.repo.intent(self.controller,self.iid)
        return self.repo.cancel(self.controller,self.iid,command_id=label,expected_version=i.state_version)
    def state(self): return _unpack(self.db.local_stored['state'])
    def restart(self):
        self.new_authority=SyntheticAuthority(self.principals,clock=self.clock)
        return PostgresExecutionRepository.restart(self.db,self.new_authority,self.source,policy(self.source),
            self.repo._registry['inputs'],self.broker,expected_generation=self.authority._generation)


class ExecutionControlTests(unittest.TestCase):
    def setUp(self):
        self.storage=patch.object(adapter,'ExecutionUnitOfWork',LocalParticipant)
        self.storage.start(); self.addCleanup(self.storage.stop)

    def test_P2_source_invalidation_retains_exact_pending_completion_budget(self):
        from synthetic_execution import fresh_target_source
        for actions,expired in ((('revoke',),False),(('withdraw',),False),
                (('admit',),False),(('revoke','withdraw','admit'),True)):
            with self.subTest(actions=actions,expired=expired):
                h=ControlHarness(reporting=False,facts=());ap=h.approved()
                issued=[]
                for ix,action in enumerate(actions):
                    actor=h.controller if action=='withdraw' else h.approver
                    command=h.app.challenge(actor,a.ref('approval',ap.approval_id,ap),
                        action=action,command_id='p2-'+str(ix))
                    issued.append((actor,command))
                original=h.state()['records'].copy()
                required=sum({'revoke':4,'withdraw':5,'admit':10}[x] for x in actions)
                fresh=fresh_target_source(h.source,at=AT)
                h.repo.replace_source(h.controller,fresh)
                state=h.state()
                self.assertEqual(state['holds'][ap.approval_id],(required,required*65536))
                self.assertEqual(h.repo._pending_budget(state,ap.approval_id),state['holds'][ap.approval_id])
                self.assertEqual(h.repo.head(h.approver,ap.approval_id).state,'invalidated')
                # Legitimate optional work must preserve this other approval's reserve.
                candidate=fresh.artifacts.candidates[0]
                _,new=h.app.present(h.approver,target_ref('candidate',candidate.candidate_id,candidate))
                optional=h.app.challenge(h.approver,a.ref('approval',new.approval_id,new),
                    action='deny',command_id='p2-optional')
                self.assertEqual(h.state()['holds'][ap.approval_id],(required,required*65536))
                self.assertEqual(h.app.execute(h.approver,optional).outcome,'applied')
                if expired:h.clock.at=issued[0][1].expires_at
                for actor,command in issued:
                    before=deepcopy(h.db.local_stored)
                    h.db.fail_commit=True
                    with self.assertRaises(d.ExecutionDenied):h.app.execute(actor,command)
                    h.db.fail_commit=False
                    self.assertEqual(h.db.local_stored,before)
                    receipt=h.app.execute(actor,command)
                    self.assertEqual((receipt.outcome,receipt.reason_code),
                        ('rejected','expired' if expired else 'version_conflict'))
                    required-={'revoke':4,'withdraw':5,'admit':10}[command.action]
                    state=h.state()
                    self.assertEqual(state['holds'].get(ap.approval_id,(0,0)),(required,required*65536))
                    self.assertEqual(h.repo._pending_budget(state,ap.approval_id),(required,required*65536))
                    frozen=deepcopy(h.db.local_stored)
                    self.assertEqual(h.repo.resolve(h.approver,state['receipts'][command.command_id]),receipt)
                    self.assertEqual(h.app.execute(actor,command),receipt)
                    self.assertEqual(h.db.local_stored,frozen)
                    self.assertTrue(all(state['records'][key]==value for key,value in original.items()))
                    self.assertFalse(state['intents']);self.assertFalse(state['claims'])
                    self.assertEqual(h.broker.received_count,0)

    def test_P2_pending_approval_and_empty_budget_source_invalidation(self):
        from synthetic_execution import fresh_target_source
        for pending in (True,False):
            with self.subTest(pending=pending):
                h=ControlHarness(reporting=False,facts=())
                candidate=h.source.artifacts.candidates[0]
                _,ap=h.app.present(h.approver,target_ref('candidate',candidate.candidate_id,candidate))
                if pending:
                    command=h.app.challenge(h.approver,a.ref('approval',ap.approval_id,ap),
                        action='approve',command_id='p2-pending-approve')
                fresh=fresh_target_source(h.source,at=AT)
                before=deepcopy(h.db.local_stored);h.db.fail_commit=True
                with self.assertRaises(d.ExecutionDenied):h.repo.replace_source(h.controller,fresh)
                h.db.fail_commit=False
                self.assertEqual(h.db.local_stored,before)
                h.repo.replace_source(h.controller,fresh)
                if pending:
                    self.assertEqual(h.state()['holds'][ap.approval_id],(9,9*65536))
                    result=h.app.execute(h.approver,command)
                    self.assertEqual((result.outcome,result.reason_code),('rejected','version_conflict'))
                self.assertNotIn(ap.approval_id,h.state()['holds'])
                self.assertFalse(h.state()['intents']);self.assertEqual(h.broker.received_count,0)

    def test_DEC005_approval_expiry_recovers_without_new_order_authority(self):
        h=ControlHarness(reporting=False,facts=());ap=h.approved()
        command=h.app.challenge(h.approver,a.ref('approval',ap.approval_id,ap),action='admit',command_id='old-admit')
        h.repo.control(h.controller,'stop');h.clock.at=ap.expires_at
        result=h.app.execute(h.approver,command)
        self.assertEqual((result.outcome,result.reason_code),('rejected','expired'))
        original=h.state()['records'].copy()
        rec=h.repo.rebind(h.controller,h.broker.query())
        self.assertEqual(rec.result,'matched',rec.unresolved)
        self.assertEqual(rec.validator_version,'q27-account-current-v1')
        self.assertLess(rec.valid_from,rec.valid_to)
        h.repo.control(h.controller,'resume')
        self.assertEqual(h.app.execute(h.approver,command),result)
        old=h.repo.head(h.approver,ap.approval_id)
        with self.assertRaises(a.ApprovalDenied):
            h.app.challenge(h.approver,a.ref('approval',old.approval_id,old),action='admit',command_id='old-new-nonce')
        self.assertFalse(h.state()['intents']);self.assertEqual(h.broker.received_count,0)
        self.assertTrue(all(h.state()['records'][key]==value for key,value in original.items()))

    def test_DEC005_request_expiry_excluded_policy_expiry_not_excluded(self):
        h=ControlHarness(reporting=False,facts=())
        h.repo.control(h.controller,'stop')
        policy=replace(h.inputs.policy,version=2,valid_to=a.plus(AT,120))
        h.repo.rebind(h.controller,h.broker.query(),execution_policy=policy)
        h.clock.at=h.source.request.expires_at
        rec=h.repo.reconcile(h.controller,h.broker.query())
        self.assertEqual(rec.result,'matched',rec.unresolved)
        h.repo.control(h.controller,'resume')
        self.assertEqual(h.state()['mode'],'running')
        # The actual current policy remains an absolute deadline, never at+TTL.
        from quantharbor.application.execution import _validate_account_current
        inputs=h.repo._registry['inputs']
        with self.assertRaises(d.ExecutionDenied):
            _validate_account_current(h.source,inputs,h.broker,at=policy.valid_to,
                generation=h.authority._generation,projection=inputs.current.current.snapshot.valuation.projection,intents=())

    def test_DEC005_fresh_source_stopped_cycle_preserves_original_and_executes_new_candidate(self):
        from synthetic_execution import fresh_target_source
        from quantharbor.application.approval import source_bytes
        h=ControlHarness(reporting=False,facts=());old=h.approved()
        old_source=h.source;original=h.state()['records'].copy()
        h.repo.control(h.controller,'stop');h.clock.at=a.plus(AT,24)
        fresh=fresh_target_source(h.source,at=h.clock.at)
        h.repo.replace_source(h.controller,fresh)
        self.assertEqual(h.repo._registry['source_history'],(old_source,))
        self.assertEqual(h.state()['source_archive'],(source_bytes(old_source),))
        self.assertEqual(h.repo.head(h.approver,old.approval_id).state,'invalidated')
        with self.assertRaises(a.ApprovalDenied):h.repo.control(h.controller,'resume')
        ep=replace(h.inputs.policy,version=2,valid_to=a.plus(h.clock.at,30))
        rec=h.repo.rebind(h.controller,h.broker.query(),execution_policy=ep)
        self.assertEqual(rec.result,'matched',rec.unresolved)
        h.repo.control(h.controller,'resume');h.source=fresh
        ap=h.approved(label='fresh-approve');h.admit(ap)
        self.assertEqual(h.repo.dispatch(h.controller,h.iid).kind,'accepted')
        self.assertEqual(h.broker.received_count,1)
        self.assertTrue(all(h.state()['records'][key]==value for key,value in original.items()))
        self.assertNotEqual(ap.candidate_ref,old.candidate_ref)

    def test_DEC005_source_rollback_and_commit_loss_publish_only_observed_binding(self):
        from synthetic_execution import fresh_target_source
        h=ControlHarness(reporting=False,facts=());fresh=fresh_target_source(h.source,at=AT)
        old=h.repo._registry.copy();before=deepcopy(h.db.local_stored)
        h.db.fail_commit=True
        with self.assertRaises(d.ExecutionDenied):h.repo.replace_source(h.controller,fresh)
        h.db.fail_commit=False
        self.assertEqual(h.db.local_stored,before)
        self.assertIs(h.repo._registry['source'],old['source'])
        self.assertEqual(h.repo._registry['source_history'],())
        commit=LocalParticipant.commit
        def lost(participant):
            commit(participant)
            raise d.ExecutionDenied('storage_failure')
        with patch.object(LocalParticipant,'commit',lost):
            with self.assertRaises(d.ExecutionDenied):h.repo.replace_source(h.controller,fresh)
        self.assertIs(h.repo._registry['source'],fresh)
        self.assertEqual(h.repo._registry['source_history'],(old['source'],))
        self.assertFalse(h.repo._registry.get('blocked',False))
        self.assertEqual(h.broker.received_count,0)

    def test_DEC005_runtime_cannot_replace_policy_and_old_matched_cannot_resume(self):
        h=ControlHarness(reporting=False,facts=());h.repo.control(h.controller,'stop')
        h.repo.change_permissions(h.controller,'controller',('query','runtime','stop','resume'))
        before=deepcopy(h.db.local_stored)
        with self.assertRaises(a.ApprovalDenied):
            h.repo.rebind(h.controller,h.broker.query(),execution_policy=replace(h.inputs.policy,version=2))
        self.assertEqual(h.db.local_stored,before)
        h.repo.reconcile(h.controller,h.broker.query())
        state=h.state();state['reconciliation']=replace(state['reconciliation'],current_identity=None,validator_version=None,valid_from=None,valid_to=None)
        h.db.local_stored['state']=adapter._pack(state)
        with self.assertRaises(a.ApprovalDenied):h.repo.control(h.controller,'resume')

    def _final_DB_expiry(self,*,cancel=False):
        h=ControlHarness(reporting=False,facts=())
        if cancel:
            h.send(); command=h.cancel('final-db-cancel')
        else:
            h.admit()
        ready=h.repo._handoff_ready
        before=h.broker.received_count
        def delayed(*args,**kwargs):
            result=ready(*args,**kwargs)
            self.assertIsNone(h.repo._uow)  # transaction, commit and close finished
            h.clock.at=a.plus(h.clock.at,31)
            return result
        with patch.object(h.repo,'_handoff_ready',side_effect=delayed):
            with self.assertRaises(a.ApprovalDenied) as denied:
                if cancel:h.repo.dispatch_cancel(h.controller,command.command_id)
                else:h.repo.dispatch(h.controller,h.iid)
        self.assertEqual(denied.exception.reason,'expired')
        self.assertEqual(h.broker.received_count,before)
        state=h.state()
        attempt=next(x for x in state['attempts'].values() if x.action==('cancel' if cancel else 'submit'))
        self.assertEqual(attempt.state,'armed')
        self.assertTrue(all(r.released=='0' for r in state['reservations'].values()))
        # A fresh session does not turn the durable arm into a resend API.
        fresh=h.authority.issue_session('controller')
        with self.assertRaises(a.ApprovalDenied):
            if cancel:h.repo.dispatch_cancel(fresh,command.command_id)
            else:h.repo.dispatch(fresh,h.iid)
        self.assertEqual(h.broker.received_count,before)

    def test_SEC2_submit_clock_expires_after_final_DB_return(self):
        self._final_DB_expiry()

    def test_SEC2_cancel_clock_expires_after_final_DB_return(self):
        self._final_DB_expiry(cancel=True)

    def test_SEC2_window_binds_actual_authority_source_risk_and_clock_floor(self):
        h=ControlHarness(reporting=False,facts=());h.admit()
        attempt,_,_=h.repo._arm(h.controller,h.iid)
        observed=[];actual=adapter.current_risk
        def record(*args,**kwargs):
            value=actual(*args,**kwargs);observed.append(value);return value
        with patch.object(adapter,'current_risk',side_effect=record):
            attempt,intent,window=h.repo._handoff_ready(h.controller,attempt.attempt_id)
        self.assertIsNone(h.repo._uow)
        state=h.state()
        sessions=[h.repo._get(state,state['heads'][('session',h.repo._registry['handles'][handle])])
            for handle in (h.controller,h.approver)]
        expected=[h.approval.expires_at,h.source.request.expires_at,observed[-1][1].valid_to,
            h.inputs.policy.valid_to,h.inputs.current.policy.daily_window_end,
            h.approval.terms.valid_to,h.approval.terms.cost_rule.valid_to,h.approval.terms.capability.valid_to,
            h.repo._policy(state).valid_to]
        for session in sessions:
            expected.extend((session.expires_at,session.liveness_deadline,h.repo._get(state,session.principal_ref).expires_at))
        self.assertCountEqual(window.deadlines,expected)
        h.repo._check_handoff_time(window,attempt,intent)
        h.clock.at=min(window.deadlines)
        with self.assertRaises(a.ApprovalDenied) as denied:h.repo._check_handoff_time(window,attempt,intent)
        self.assertEqual(denied.exception.reason,'expired')
        h.clock.at=window.checked_at
        with self.assertRaises(a.ApprovalDenied) as denied:h.repo._check_handoff_time(window,attempt,intent)
        self.assertEqual(denied.exception.reason,'clock_invalid')
        self.assertEqual(h.broker.received_count,0)

    def test_SEC2_cancel_command_deadline_after_DB_without_session_expiry(self):
        h=ControlHarness(reporting=False,facts=());h.send();command=h.cancel()
        ready=h.repo._handoff_ready
        def delayed(*args,**kwargs):
            result=ready(*args,**kwargs)
            self.assertEqual(min(result[2].deadlines),command.expires_at)
            h.clock.at=command.expires_at  # session liveness still valid
            return result
        before=h.broker.received_count
        with patch.object(h.repo,'_handoff_ready',side_effect=delayed),self.assertRaises(a.ApprovalDenied) as denied:
            h.repo.dispatch_cancel(h.controller,command.command_id)
        self.assertEqual(denied.exception.reason,'expired')
        self.assertEqual(h.broker.received_count,before)

    def test_SEC1_disconnect_pauses_approver_then_remaining_controller_repairs(self):
        h=ControlHarness(reporting=False,facts=());h.admit()
        for n in range(2):
            h.app.withdraw(h.controller,a.ref('approval',h.approval.approval_id,h.approval),command_id='sec1-withdraw-'+str(n))
        repo=h.restart();controller=h.new_authority.issue_session('controller')
        approver=h.new_authority.issue_session('approver')
        self.assertEqual(repo.rebind(controller,h.broker.query()).result,'matched')
        repo.control(approver,'disconnect')
        state=h.state();sid=repo._registry['handles'][approver]
        self.assertEqual(repo._get(state,state['heads'][('session',sid)]).state,'paused')
        with self.assertRaises(a.ApprovalDenied) as denied:repo.control(controller,'resume')
        self.assertEqual(denied.exception.reason,'reconciliation_required')
        self.assertEqual(repo.rebind(controller,h.broker.query()).result,'matched')
        repo.control(controller,'resume')
        self.assertEqual(h.state()['mode'],'running')

    def test_cancel_ACK_does_not_release_fill_then_actual_confirmation(self):
        h=ControlHarness(); receipt=h.send(); c=h.cancel()
        ack=h.repo.dispatch_cancel(h.controller,c.command_id)
        self.assertEqual(ack.kind,'cancel_ack')
        self.assertEqual(h.repo.cancel_receipt(h.controller,c.command_id,intent_id=h.iid,expected_version=c.expected_version),ack)
        self.assertEqual(h.repo.intent(h.controller,h.iid).state,'acknowledged')
        self.assertTrue(all(r.released=='0' for r in h.state()['reservations'].values()))
        self.assertEqual(h.repo.receive(h.broker.issue_event(receipt,0)),'applied')
        confirmation=h.broker.issue_event(ack,2)
        self.assertEqual(h.repo.receive(confirmation),'applied')
        state=h.state(); self.assertEqual(state['intents'][h.iid].state,'cancelled_remaining')
        principal=next(r for r in state['reservations'].values() if r.component=='principal')
        self.assertEqual((principal.used,principal.released),('100','200'))
        cost=next(r for r in state['reservations'].values() if r.component=='cost')
        self.assertEqual((cost.held,cost.released),('2','0'))
        before=h.repo.fingerprint(); self.assertEqual(h.repo.receive(confirmation),'duplicate'); self.assertEqual(h.repo.fingerprint(),before)
        self.assertEqual(state['cancel_commands']['cancel'].state,'confirmed')
        self.assertEqual(h.repo.cancel(h.controller,h.iid,command_id='cancel',expected_version=c.expected_version),state['cancel_commands']['cancel'])

    def test_submit_receipt_cannot_issue_cancel_confirmation(self):
        h=ControlHarness(); receipt=h.send(); h.cancel()
        with self.assertRaises(d.ExecutionDenied): h.broker.issue_event(receipt,2)

    def test_cancel_timeout_holds_and_fills_continue_no_retry(self):
        h=ControlHarness(); receipt=h.send(); h.cancel(); h.broker._cancel_response='timeout'
        self.assertIsNone(h.repo.dispatch_cancel(h.controller,'cancel'))
        self.assertEqual(h.state()['cancel_commands']['cancel'].state,'unknown')
        self.assertEqual(h.repo.receive(h.broker.issue_event(receipt,0)),'applied')
        with self.assertRaises(a.ApprovalDenied): h.repo.dispatch_cancel(h.controller,'cancel')
        with self.assertRaises(a.ApprovalDenied): h.cancel('replacement')
        self.assertEqual(h.broker.received_count,2)

    def test_cancel_approve_is_not_cancel_and_replay_rechecks_permissions(self):
        h=ControlHarness(); h.send(); c=h.cancel()
        with self.assertRaises(a.ApprovalDenied): h.repo.cancel(h.approver,h.iid,command_id='forged',expected_version=c.expected_version)
        h.repo.change_permissions(h.controller,'controller',('stop','withdraw'))
        with self.assertRaises(a.ApprovalDenied): h.repo.cancel(h.controller,h.iid,command_id='cancel',expected_version=c.expected_version)
        self.assertEqual(h.broker.received_count,1)

    def test_cancel_TTL_and_target_version_fail_before_handoff(self):
        h=ControlHarness(); receipt=h.send(); h.cancel()
        h.repo.receive(h.broker.issue_event(receipt,0))
        with self.assertRaises(a.ApprovalDenied): h.repo.dispatch_cancel(h.controller,'cancel')
        c=h.cancel('fresh'); h.clock.at=a.plus(AT,11)
        with self.assertRaises(a.ApprovalDenied): h.repo.dispatch_cancel(h.controller,c.command_id)
        self.assertEqual(h.broker.received_count,1)

    def test_cancel_confirmation_conflict_preserves_evidence_and_hold(self):
        h=ControlHarness(); h.send(); h.cancel(); ack=h.repo.dispatch_cancel(h.controller,'cancel')
        event=h.broker.issue_event(ack,2) # broker confirms2 but local has filled0 => conflict, no clamp
        self.assertEqual(h.repo.receive(event),'quarantined')
        state=h.state(); self.assertEqual(state['mode'],'faulted')
        self.assertEqual(state['intents'][h.iid].accounting,'incomplete')
        self.assertTrue(all(r.released=='0' for r in state['reservations'].values()))

    def test_cancel_late_fill_preserves_observation_incomplete(self):
        h=ControlHarness(); receipt=h.send(); h.cancel(); ack=h.repo.dispatch_cancel(h.controller,'cancel')
        h.repo.receive(h.broker.issue_event(receipt,0)); h.repo.receive(h.broker.issue_event(ack,2))
        late=replace(h.broker._facts[0],event_id='late-fill',execution_id='late')
        h.broker._facts=(*h.broker._facts,late)
        self.assertEqual(h.repo.receive(h.broker.issue_event(receipt,3)),'quarantined')
        self.assertEqual(h.state()['intents'][h.iid].confirmed_quantity,'1')
        self.assertEqual(h.state()['intents'][h.iid].accounting,'incomplete')

    def test_cancel_handoff_crash_attempt_durable_no_resend(self):
        for phase in ('before_cancel_handoff','after_cancel_handoff'):
            with self.subTest(phase=phase):
                h=ControlHarness(); h.send(); h.cancel()
                with self.assertRaises(a.ApprovalDenied),h.repo.inject_failure(phase): h.repo.dispatch_cancel(h.controller,'cancel')
                h.repo.recover()
                with self.assertRaises(a.ApprovalDenied): h.repo.dispatch_cancel(h.controller,'cancel')
                self.assertEqual(h.broker.received_count,1 if phase.startswith('before') else 2)

    def test_withdraw_new_session_after_original_approver_revoked(self):
        h=ControlHarness(); ap=h.admit(); second=h.authority.issue_session('controller')
        h.repo.change_permissions(h.controller,'approver',('query',))
        result=h.app.withdraw(second,a.ref('approval',ap.approval_id,ap),command_id='protect')
        self.assertEqual(result.outcome,'applied')
        self.assertEqual(h.repo.intent(second,h.iid).state,'aborted_unsent')
        self.assertEqual(h.state()['claims'].__len__(),1)
        self.assertEqual(h.state()['heads'][('approval',ap.approval_id)].version,ap.state_version)

    def test_before_handoff_fault_then_withdraw_cannot_guess_unsent(self):
        h=ControlHarness(); ap=h.admit()
        with self.assertRaises(a.ApprovalDenied),h.repo.inject_failure('before_handoff'): h.repo.dispatch(h.controller,h.iid)
        h.app.withdraw(h.controller,a.ref('approval',ap.approval_id,ap),command_id='protect')
        self.assertTrue(all(r.released=='0' for r in h.state()['reservations'].values()))
        h.repo.recover(); self.assertEqual(h.repo.intent(h.controller,h.iid).state,'unknown')

    def test_gate_serializes_real_threads_both_stop_orders(self):
        self._gate_orders('stop')

    def test_gate_serializes_real_threads_both_withdraw_orders(self):
        self._gate_orders('withdraw')

    def _gate_orders(self,action):
        for dispatch_first in (False,True):
            with self.subTest(dispatch_first=dispatch_first):
                h=ControlHarness(); h.admit(); ready=Barrier(2); waiting=Event()
                def stop():
                    ready.wait(60); waiting.set()
                    return h.repo.control(h.controller,'stop') if action=='stop' else h.app.withdraw(h.controller,a.ref('approval',h.approval.approval_id,h.approval),command_id='raced-withdraw')
                if dispatch_first:
                    original=h.repo._handoff_ready
                    def checked(*args,**kwargs):
                        result=original(*args,**kwargs); ready.wait(60); self.assertTrue(waiting.wait(60)); return result
                    with patch.object(h.repo,'_handoff_ready',side_effect=checked),ThreadPoolExecutor(2) as pool:
                        f=pool.submit(stop); h.repo.dispatch(h.controller,h.iid); f.result(60)
                    self.assertEqual(h.broker.received_count,1)
                else:
                    def send():
                        ready.wait(60); self.assertTrue(waiting.wait(60))
                        return h.repo.dispatch(h.controller,h.iid)
                    with ThreadPoolExecutor(2) as pool:
                        with h.repo._lock:
                            f=pool.submit(send); ready.wait(60)
                            if action=='stop': h.repo.control(h.controller,'stop')
                            else: h.app.withdraw(h.controller,a.ref('approval',h.approval.approval_id,h.approval),command_id='raced-withdraw')
                            waiting.set()
                        with self.assertRaises(a.ApprovalDenied): f.result(60)
                    self.assertEqual(h.broker.received_count,0)
                if action=='stop': self.assertEqual(h.state()['mode'],'stopped')
                self.assertEqual(h.state()['heads'][('approval',h.approval.approval_id)].version,h.approval.state_version)

    def test_restart_opaque_handles_new_generation_claims_preserved(self):
        h=ControlHarness(); ap=h.admit()
        h.app.withdraw(h.controller,a.ref('approval',ap.approval_id,ap),command_id='protect')
        before=h.state(); new=h.restart(); generation=h.new_authority._generation
        self.assertNotEqual(generation,before['generation'])
        self.assertEqual(h.state()['claims'],before['claims'])
        self.assertEqual(h.state()['reservations'],before['reservations'])
        self.assertEqual(h.state()['mode'],'stopped')
        for handle in (h.controller,h.approver):
            with self.assertRaises(a.ApprovalDenied): new.intent(handle,h.iid)
        with self.assertRaises(a.ApprovalDenied): h.repo.intent(h.controller,h.iid)
        with self.assertRaises(a.ApprovalDenied): new.query(h.reader,account_ref=new._account,purpose='report')
        self.assertEqual(h.broker.received_count,0)

    def test_restart_unknown_empty_query_never_releases_or_resumes(self):
        h=ControlHarness(response='timeout'); h.send(); before=h.state()['reservations']; new=h.restart()
        controller=h.new_authority.issue_session('controller')
        rec=new.reconcile(controller,h.broker.query())
        self.assertEqual(rec.result,'unresolved')
        with self.assertRaises(a.ApprovalDenied): new.control(controller,'resume')
        self.assertEqual(h.state()['reservations'],before)

    def test_restart_CAS_and_failed_commit_dont_rotate_live_issuer(self):
        h=ControlHarness(); old=h.authority._generation
        authority=SyntheticAuthority(h.principals,clock=h.clock)
        with self.assertRaises(a.ApprovalDenied):
            PostgresExecutionRepository.restart(h.db,authority,h.source,policy(h.source),h.inputs,h.broker,expected_generation='wrong')
        h.db.fail_commit=True
        with self.assertRaises(d.ExecutionDenied): h.restart()
        h.db.fail_commit=False
        self.assertEqual(h.authority._generation,old)
        self.assertEqual(h.state()['generation'],old)
        self.assertEqual(h.repo.control(h.controller,'stop').kind,'runtime')

    def test_restart_corrected_history_rebind_resume_and_new_candidate(self):
        h=ControlHarness(facts=CORRECTION_FACTS['delta'],current_manifest=CORRECTION_MANIFESTS['delta'])
        receipt=h.send()
        for n in range(2): self.assertEqual(h.repo.receive(h.broker.issue_event(receipt,n)),'applied')
        h.inputs=h.repo.refresh_current(h.controller,h.broker.query(1))
        new=h.restart(); controller=h.new_authority.issue_session('controller')
        approver=h.new_authority.issue_session('approver')
        rec=new.rebind(controller,h.broker.query(1))
        self.assertEqual(rec.result,'matched',rec.unresolved)
        self.assertEqual(h.state()['mode'],'reconciling')
        new.control(controller,'resume')
        candidate=h.source.artifacts.candidates[1]
        app=ApprovalApplication(new)
        _,ap=app.present(approver,target_ref('candidate',candidate.candidate_id,candidate))
        c=app.challenge(approver,a.ref('approval',ap.approval_id,ap),action='approve',command_id='new-approve')
        self.assertEqual(app.execute(approver,c).outcome,'applied')
        before=h.state()
        self.assertEqual(before['claims'][('synthetic',new._account,h.approval.candidate_ref.id,h.approval.candidate_ref.version)],h.iid)
        with self.assertRaises(a.ApprovalDenied): app.execute(approver,h.admission_command)
        self.assertEqual(h.state()['claims'],before['claims'])
        self.assertEqual(h.state()['nonces'].get(h.admission_command.nonce),None)

    def test_quarantine_restart_cannot_clear_history_or_protection(self):
        h=ControlHarness(facts=(fact('bad',quantity='4'),)); receipt=h.send()
        self.assertEqual(h.repo.receive(h.broker.issue_event(receipt,0)),'quarantined')
        before=h.state(); new=h.restart(); controller=h.new_authority.issue_session('controller')
        # The local quarantine alias must not invalidate an intact issuer journal.
        self.assertEqual(new.intent(controller,h.iid).state,before['intents'][h.iid].state)
        with self.assertRaises(d.ExecutionDenied): new.rebind(controller,h.broker.query())
        self.assertEqual(new.reconcile(controller,h.broker.query()).result,'unresolved')
        with self.assertRaises(a.ApprovalDenied): new.control(controller,'resume')
        self.assertEqual(h.state()['events'],before['events']); self.assertEqual(h.state()['reservations'],before['reservations'])

    def test_shared_facade_refresh_and_generation_current_inputs(self):
        h=ControlHarness(facts=CORRECTION_FACTS['delta'],current_manifest=CORRECTION_MANIFESTS['delta'])
        other=PostgresExecutionRepository(h.db,h.authority,h.source,policy(h.source),h.inputs,h.broker)
        receipt=h.send()
        for n in range(2): h.repo.receive(h.broker.issue_event(receipt,n))
        current=h.repo.refresh_current(h.controller,h.broker.query(1))
        other.intent(h.controller,h.iid)
        self.assertIs(other._inputs,current)
        self.assertIsNone(other._state)
        new=h.restart()
        with self.assertRaises(a.ApprovalDenied): other.intent(h.controller,h.iid)
        controller=h.new_authority.issue_session('controller')
        new.rebind(controller,h.broker.query(1))
        facade=PostgresExecutionRepository(h.db,h.new_authority,h.source,policy(h.source),new._registry['inputs'],h.broker)
        self.assertIs(facade._registry,new._registry)

    def test_unprocessed_query_manifest_and_new_broker_cannot_auth_old_journal(self):
        h=ControlHarness(); receipt=h.send(); h.broker.issue_event(receipt,0); q=h.broker.query()
        foreign=SyntheticExecutionBroker(h.broker._account,h.broker._snapshots,h.broker._facts)
        with self.assertRaises(d.ExecutionDenied): foreign.manifest(q)
        self.assertEqual(h.repo.reconcile(h.controller,q).result,'unresolved') # actual issuer fill has not been processed locally
        self.assertEqual(h.broker.manifest(q)[0][0].action,'submit')
        h.broker.issue_event(receipt,1)
        with self.assertRaises(d.ExecutionDenied): h.broker.manifest(q)

    def test_cancel_separate_permission_withdraw_remains_authorized(self):
        h=ControlHarness(); h.send(); command=h.cancel()
        h.repo.change_cancel_permissions(h.controller,'controller',())
        with self.assertRaises(a.ApprovalDenied): h.repo.cancel_receipt(h.controller,command.command_id,intent_id=h.iid,expected_version=command.expected_version)
        with self.assertRaises(a.ApprovalDenied): h.repo.dispatch_cancel(h.controller,command.command_id)
        self.assertEqual(h.repo.control(h.controller,'stop').kind,'runtime')
        self.assertEqual(h.broker.received_count,1)

    def test_protective_withdraw_after_report_and_risk_source_rights_revoked(self):
        from synthetic_approval import rights_changed
        h=ControlHarness(); ap=h.admit(); second=h.authority.issue_session('controller')
        other=PostgresExecutionRepository(h.db,h.authority,h.source,policy(h.source),h.inputs,h.broker)
        changed=rights_changed(h.source)
        h.repo.replace_source(h.controller,changed)
        with self.assertRaises(a.ApprovalDenied): other.dispatch(h.controller,h.iid)
        self.assertIs(other._source,changed)
        self.assertEqual(ApprovalApplication(other).withdraw(second,a.ref('approval',ap.approval_id,ap),command_id='rights-protect').outcome,'applied')
        self.assertEqual(other.intent(second,h.iid).state,'aborted_unsent')
        self.assertEqual(h.broker.received_count,0)

    def test_late_completion_via_new_runtime_preserves_broker_financial_fact(self):
        h=ControlHarness(); h.admit()
        attempt,intent,_=h.repo._arm(h.controller,h.iid)
        receipt=h.broker.handoff(attempt,intent)
        new=h.restart(); controller=h.new_authority.issue_session('controller')
        self.assertEqual(new.intent(controller,h.iid).state,'unknown')
        with self.assertRaises(a.ApprovalDenied): h.repo._store_receipt(attempt,receipt)
        new._store_receipt(attempt,receipt)
        self.assertEqual(new.intent(controller,h.iid).broker_order_id,receipt.broker_order_id)
        self.assertEqual(h.state()['mode'],'stopped')
        self.assertEqual(new.receive(h.broker.issue_event(receipt,0)),'applied')
        self.assertEqual(h.state()['intents'][h.iid].confirmed_quantity,'1')
        self.assertEqual(h.broker.received_count,1)

    def test_restart_lost_broker_journal_is_observation_only_not_import(self):
        h=ControlHarness(); h.send(); before=h.state()['reservations']
        foreign=SyntheticExecutionBroker(h.broker._account,h.broker._snapshots,h.broker._facts)
        authority=SyntheticAuthority(h.principals,clock=h.clock)
        new=PostgresExecutionRepository.restart(h.db,authority,h.source,policy(h.source),h.inputs,foreign,expected_generation=h.authority._generation)
        controller=authority.issue_session('controller')
        self.assertEqual(new.intent(controller,h.iid).state,'unknown')
        with self.assertRaises((a.ApprovalDenied,d.ExecutionDenied)): new.rebind(controller,foreign.query())
        with self.assertRaises(a.ApprovalDenied): new.control(controller,'resume')
        self.assertEqual(h.state()['reservations'],before)
        self.assertEqual(foreign.received_count,0)

    def test_resume_fresh_controller_session_invalidates_old_reconciliation_version(self):
        h=ControlHarness(); h.repo.control(h.controller,'stop')
        rec=h.repo.reconcile(h.controller,h.broker.query())
        self.assertEqual(rec.result,'matched')
        second=h.authority.issue_session('controller')
        with self.assertRaises(a.ApprovalDenied): h.repo.control(second,'resume')
        rec=h.repo.reconcile(second,h.broker.query())
        self.assertEqual(rec.result,'matched')
        h.repo.control(second,'resume')
        self.assertEqual(h.state()['mode'],'running')

    def test_restart_commit_response_lost_old_issuer_fails_closed_current_CAS_observation(self):
        h=ControlHarness(); old=h.authority._generation
        original=LocalParticipant.commit
        def lost(participant):
            original(participant)
            raise d.ExecutionDenied('storage_failure')
        with patch.object(LocalParticipant,'commit',lost):
            with self.assertRaises(d.ExecutionDenied): h.restart()
        self.assertEqual(h.authority._generation,old)
        with self.assertRaises(a.ApprovalDenied): h.repo.control(h.controller,'resume')
        observed=PostgresExecutionRepository.current_runtime(h.db,h.source.request.account_ref)
        self.assertNotEqual(observed['generation'],old)
        self.assertEqual(observed['mode'],'stopped')
        self.assertIsNone(h.new_authority._repository)
        recovered=PostgresExecutionRepository.restart(h.db,h.new_authority,h.source,policy(h.source),h.inputs,h.broker,
            expected_generation=observed['generation'])
        self.assertIs(h.new_authority._repository,recovered)
        self.assertEqual(h.broker.received_count,0)

    def test_explicit_issuer_proven_unsent_after_restart_releases_only_actual_revoked_attempt(self):
        h=ControlHarness(); h.admit()
        with self.assertRaises(a.ApprovalDenied),h.repo.inject_failure('before_handoff'): h.repo.dispatch(h.controller,h.iid)
        before=h.state(); new=h.restart(); controller=h.new_authority.issue_session('controller')
        proof=new.resolve_unsent(controller,h.iid)
        self.assertEqual(proof.kind,'proven_unsent')
        state=h.state(); self.assertEqual(state['intents'][h.iid].state,'aborted_unsent')
        self.assertTrue(all(r.held=='0' for r in state['reservations'].values()))
        self.assertEqual(state['claims'],before['claims'])
        old_attempt=before['attempts'][before['intents'][h.iid].attempt_ref.id]
        with self.assertRaises(d.ExecutionDenied): h.broker.handoff(old_attempt,before['intents'][h.iid])
        self.assertEqual(new.rebind(controller,h.broker.query()).result,'matched')
        new.control(controller,'resume')
        self.assertEqual(h.broker.received_count,0)

    def test_manual_unsent_proof_cannot_release_already_handed_off_or_foreign_issuer(self):
        h=ControlHarness(response='timeout'); h.send(); h.repo.control(h.controller,'stop'); before=h.state()['reservations']
        # Actual broker received the request despite missing ACK. Absence is no proof.
        with self.assertRaises(d.ExecutionDenied): h.repo.resolve_unsent(h.controller,h.iid)
        self.assertEqual(h.state()['reservations'],before)
        new=h.restart(); controller=h.new_authority.issue_session('controller')
        with self.assertRaises(d.ExecutionDenied): new.resolve_unsent(controller,h.iid)
        foreign=SyntheticExecutionBroker(h.broker._account,h.broker._snapshots,h.broker._facts)
        authority=SyntheticAuthority(h.principals,clock=h.clock)
        observed=PostgresExecutionRepository.current_runtime(h.db,h.source.request.account_ref)
        readonly=PostgresExecutionRepository.restart(h.db,authority,h.source,policy(h.source),new._registry['inputs'],foreign,expected_generation=observed['generation'])
        fresh=authority.issue_session('controller')
        with self.assertRaises(d.ExecutionDenied): readonly.resolve_unsent(fresh,h.iid)
        self.assertEqual(h.state()['reservations'],before)
        self.assertEqual(h.broker.received_count,1)
        self.assertEqual(foreign.received_count,0)

    def test_resume_binds_exact_session_and_current_query_cash_qty_source_readset(self):
        manifest=dict(holdings=('0','0'),cash=(('settled_cash','1000'),),capacity='900',sellable=('0','0'),cutoff=0)
        h=ControlHarness(current_manifest=manifest); h.approved()
        second=h.authority.issue_session('controller'); h.repo.control(h.controller,'stop')
        initial=h.broker.query()
        rec=h.repo.reconcile(h.controller,initial)
        self.assertEqual(rec.result,'matched')
        self.assertEqual(rec.session_id,h.repo._registry['handles'][h.controller])
        self.assertEqual(rec.source_hash,h.repo._source_hash())
        with self.assertRaises(a.ApprovalDenied): h.repo.control(second,'resume')
        changed=h.broker.query(1)
        rec=h.repo.reconcile(h.controller,changed)
        self.assertEqual(rec.result,'unresolved')
        with self.assertRaises(a.ApprovalDenied): h.repo.control(h.controller,'resume')
        h.repo.refresh_current(h.controller,changed)
        self.assertEqual(h.repo.reconcile(second,changed).result,'matched')
        h.repo.control(second,'resume')
        self.assertEqual(h.state()['mode'],'running')


    def test_recovery_controller_rebind_then_approver_invalidates_and_reconciles_again(self):
        h=ControlHarness(reporting=False,facts=());h.admit()
        for n in range(2):h.app.withdraw(h.controller,a.ref('approval',h.approval.approval_id,h.approval),command_id='recover-end-'+str(n))
        new=h.restart();controller=h.new_authority.issue_session('controller')
        self.assertEqual(new.rebind(controller,h.broker.query()).result,'matched')
        from synthetic_execution import replacement_source
        changed=replacement_source(h.source,('3','4'),label='cannot-strand-recovery')
        original=h.repo._source
        new.replace_source(controller,changed)
        self.assertIs(new._registry['source'],changed)
        self.assertIn(original,new._registry['source_history'])
        self.assertIsNone(h.state()['reconciliation'])
        h.new_authority.issue_session('approver')
        before=deepcopy(h.db.local_stored)
        with self.assertRaises(a.ApprovalDenied) as denied:new.control(controller,'resume')
        self.assertEqual(denied.exception.reason,'reconciliation_required')
        self.assertEqual(h.db.local_stored,before)
        self.assertEqual(new.rebind(controller,h.broker.query()).result,'matched')
        new.control(controller,'resume')
        self.assertEqual(_unpack(h.db.local_stored['state'])['mode'],'running')

    def test_recovery_two_controllers_complete_rebind_resume_then_stop(self):
        h=ControlHarness(reporting=False,facts=());h.admit()
        for n in range(2):h.app.withdraw(h.controller,a.ref('approval',h.approval.approval_id,h.approval),command_id='recover-two-end-'+str(n))
        new=h.restart();one=h.new_authority.issue_session('controller');two=h.new_authority.issue_session('controller')
        self.assertEqual(new.rebind(one,h.broker.query()).result,'matched')
        new.control(one,'resume');new.control(two,'stop')
        self.assertEqual(_unpack(h.db.local_stored['state'])['mode'],'stopped')
