"""저장 산식·발급 경계 local 증거. 실제 PostgreSQL 증명은 root runner다."""
from copy import deepcopy
from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from quantharbor.domain.execution_budget import (Cost,canonical_size,row_cost,remaining,
    owner_charge,manifest_ledger_cost,admit_manifest,CATEGORY_RECORDS)
from quantharbor.domain import execution as d, approval as a
from quantharbor.adapters.execution_uow import state_delta
from quantharbor.adapters.postgres_execution import _pack,_unpack,PostgresExecutionRepository
from quantharbor.adapters.synthetic_execution_broker import SyntheticExecutionBroker
from test_execution_financial import fact,FinancialHarness


class ExecutionStorageTests(unittest.TestCase):
    def test_rows_and_each_index_are_independent_exact_utf8_bytes(self):
        body={'id':'synthetic:a','text':'한글','quantity':'1.25'}
        keys=(['synthetic:a'],['synthetic:a','1.25'])
        result=row_cost(body,keys)
        manual=lambda x:len(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())
        self.assertEqual(result,Cost(1,manual(body)+sum(manual(k) for k in keys)))
        self.assertGreater(result.bytes,canonical_size(body))
        self.assertEqual(row_cost(body,keys+keys).records,1)

    def test_255_manifest_before_issuer_construction_no_registry_sideeffects(self):
        facts=tuple(fact('r'+str(n),revision=n+1,predecessor=n or None,fee='1',tax='0.5') for n in range(8))
        self.assertEqual(manifest_ledger_cost(facts).records,24+7*33)
        with self.assertRaises(d.ExecutionDenied): admit_manifest(facts)
        # Cost gate runs before any journal/request/query/slot state is created.
        with patch.object(SyntheticExecutionBroker,'_put') as put:
            from synthetic_execution import composition
            with self.assertRaises(d.ExecutionDenied): composition(facts=facts)
        put.assert_not_called()

    def test_eight_slots_are_not_arbitrary_combinations(self):
        plain=tuple(fact('f'+str(n),execution='e'+str(n),fee='1',tax='0.5') for n in range(8))
        self.assertEqual(admit_manifest(plain).records,192)
        correction=(fact('r',fee='1',tax='0.5'),fact('r',revision=2,predecessor=1,fee='1',tax='0.5'))
        self.assertEqual(admit_manifest(correction).records,57)
        self.assertEqual(manifest_ledger_cost((fact('f',fee=None),fact('f',revision=2,predecessor=1))).records,8)
        self.assertEqual(manifest_ledger_cost((fact('s',kind='settlement'),)).records,8)

    def test_owner_remaining_reserve_cannot_be_borrowed_or_double_counted(self):
        actual={k:Cost() for k in CATEGORY_RECORDS}
        ceiling={k:Cost(v,v*4096) for k,v in CATEGORY_RECORDS.items()}
        first=owner_charge(actual,ceiling)
        actual['ledger']=Cost(8,1000)
        reserve={k:remaining(actual[k],ceiling[k]) for k in actual}
        self.assertEqual(owner_charge(actual,reserve),first)
        second=deepcopy(reserve)
        actual['ledger']=Cost(193,1000)
        with self.assertRaises(d.ExecutionDenied): owner_charge(actual,reserve)
        self.assertEqual(second,reserve)

    def test_delta_omits_unmodified_history_and_preserves_exact_map_keys(self):
        old={'records':{('original',1):b'untouched'},'holds':{'finished':(1,10)},'version':1}
        new=deepcopy(old);new['holds']={};new['version']=2
        delta=state_delta(_pack(old),_pack(new))
        self.assertEqual({x['key'] for x in delta},{'holds','version'})
        self.assertNotIn('untouched',json.dumps(delta))
        self.assertEqual(next(x for x in delta if x['key']=='holds')['value']['remove'],['finished'])
        self.assertEqual(state_delta(_pack(new),_pack(new)),[])

    def test_same_missing_dependency_reprocess_has_zero_history_growth(self):
        h=FinancialHarness((fact('r',quantity='2',revision=2,predecessor=1),fact('r')))
        self.assertEqual(h.receive(0),'quarantined')
        before=deepcopy(h.repo._state);inbox=len(h.uow.inbox)
        for _ in range(3):
            self.assertEqual(PostgresExecutionRepository.reprocess.__wrapped__(h.repo,h.event(0)),'quarantined')
        self.assertEqual(h.repo._state,before)
        self.assertEqual(len(h.uow.inbox),inbox)
        self.assertEqual(h.receive(1),'applied')
        self.assertEqual(PostgresExecutionRepository.reprocess.__wrapped__(h.repo,h.event(0)),'applied')

    def test_repeated_query_reconciliation_same_readset_no_new_uuid_or_commit(self):
        from test_execution_control import ControlHarness,LocalParticipant
        with patch('quantharbor.adapters.postgres_execution.ExecutionUnitOfWork',LocalParticipant):
            h=ControlHarness()
            # resume changes account mode/version, so establish one current result.
            first=h.repo.reconcile(h.controller,h.inputs.query)
            before=deepcopy(h.db.local_stored)
            second=h.repo.reconcile(h.controller,h.inputs.query)
            self.assertEqual(first,second)
            self.assertEqual(before,h.db.local_stored)

    def test_generation_preserves_original_indexes_no_duplicate_archive_or_reuse(self):
        from test_execution_control import ControlHarness,LocalParticipant
        from quantharbor.domain import approval as a
        with patch('quantharbor.adapters.postgres_execution.ExecutionUnitOfWork',LocalParticipant):
            h=ControlHarness();h.admit()
            prior=_unpack(h.db.local_stored['state'])
            command=h.admission_command
            h.repo.rotate(h.controller)
            after=_unpack(h.db.local_stored['state'])
            self.assertNotIn('retired_commands',after)
            for key in ('commands','nonces','receipts'):
                self.assertEqual(after[key],{})
            original_challenge,original_receipt=h.repo._past_command(after,command.command_id)
            self.assertEqual(original_challenge,command)
            self.assertIsNotNone(original_receipt)
            self.assertTrue(all(after['records'][r]==raw for r,raw in prior['records'].items()))
            with self.assertRaises(a.ApprovalDenied): h.app.execute(h.approver,command)

    def _sell_literal(self,quantity):
        from test_execution_control import ControlHarness,LocalParticipant
        from synthetic_execution import replacement_source
        manifest=dict(holdings=('12','0'),cash=(('settled_cash','1000'),('unsettled_receivable','100')),
            capacity='1000',sellable=('10','0'),cutoff=1,hold_reflections=('2',))
        with patch('quantharbor.adapters.postgres_execution.ExecutionUnitOfWork',LocalParticipant):
            h=ControlHarness(target_options={'holdings':('13','0'),'targets':('8',None)},
                facts=(fact('sell-postquery'),),current_manifest=manifest)
            h.send();self.assertEqual(h.repo.receive(h.broker.issue_event(h.receipt,0)),'applied')
            query=h.broker.query(1)
            fresh=h.repo.refresh_current(h.controller,query)
            self.assertEqual(fresh.current.facts.sellability_rows[0].settled_quantity,'12')
            state=h.state();reserve=next(r for r in state['reservations'].values() if r.component=='quantity')
            self.assertEqual((reserve.held,reserve.used,query.sellable[0].quantity,query.sellable[0].hold_reflections[0].quantity),('4','1','10','2'))
            h.source=replacement_source(h.source,('6' if quantity==7 else '5',),label='sell-next-'+str(quantity))
            h.repo.replace_source(h.controller,h.source)
            next_=h.approved(label='sell-next-approved')
            self.assertEqual(next_.terms.quantity,str(quantity))
            before=len(h.state()['intents'])
            result=h.app.execute(h.approver,h.app.challenge(h.approver,
                a.ref('approval',next_.approval_id,next_),action='admit',command_id='sell-seven'))
            self.assertEqual((result.outcome,len(h.state()['intents'])),('applied',before+1) if quantity==7 else ('rejected',before))

    def test_EX09_partial_broker_hold_and_postquery_fill_literal7(self):
        self._sell_literal(7)

    def test_EX09_partial_broker_hold_and_postquery_fill_literal8_denied(self):
        self._sell_literal(8)

    def test_EX11_two_approvals_reach_actual_exposure_400_100_50(self):
        from test_execution_control import ControlHarness,LocalParticipant
        from synthetic_execution import replacement_source
        import quantharbor.adapters.postgres_execution as adapter
        with patch('quantharbor.adapters.postgres_execution.ExecutionUnitOfWork',LocalParticipant):
            h=ControlHarness(target_options={'holdings':('0','4'),'targets':('1','3'),'lot':'0.5','fee':'0'},exposure_ceiling='500')
            first=h.approved(0,label='first-buy')
            got=h.app.execute(h.approver,h.app.challenge(h.approver,a.ref('approval',first.approval_id,first),action='admit',command_id='first-admit'))
            self.assertEqual(got.outcome,'applied')
            h.source=replacement_source(h.source,('0.5','3'),label='two-approval-buy50')
            h.repo.replace_source(h.controller,h.source)
            second=h.approved(0,label='second-buy')
            self.assertEqual((first.terms.maximum_burden,second.terms.maximum_burden),('100','50'))
            challenge=h.app.challenge(h.approver,a.ref('approval',second.approval_id,second),action='admit',command_id='second-admit')
            with patch.object(adapter,'current_risk',wraps=adapter.current_risk) as actual:
                result=h.app.execute(h.approver,challenge)
            self.assertEqual(actual.call_count,1)
            self.assertEqual((result.outcome,result.reason_code),('rejected','risk_blocked'))
            self.assertEqual(h.repo.head(h.approver,second.approval_id).state,'approved')

    def test_EX11_third_presentation_capacity_is_explicit_not_financial_pass(self):
        from test_execution_control import ControlHarness,LocalParticipant
        from synthetic_execution import replacement_source
        with patch('quantharbor.adapters.postgres_execution.ExecutionUnitOfWork',LocalParticipant):
            h=ControlHarness(target_options={'holdings':('0','4'),'targets':('1','3'),'lot':'0.5','fee':'0'},exposure_ceiling='500')
            one=h.approved(0,label='buy');two=h.approved(1,label='sell')
            for approval,label in ((one,'buy-admit'),(two,'sell-admit')):
                result=h.app.execute(h.approver,h.app.challenge(h.approver,a.ref('approval',approval.approval_id,approval),action='admit',command_id=label))
                self.assertEqual(result.outcome,'applied')
            h.source=replacement_source(h.source,('0.5','3'),label='buy50-source')
            h.repo.replace_source(h.controller,h.source)
            before=deepcopy(h.db.local_stored);observed=[]
            original=h.repo._room
            def measured(state):
                records,size=h.repo._usage(state)
                observed.append((records,sum(v[0] for v in state['holds'].values())))
                return original(state)
            with patch.object(h.repo,'_room',side_effect=measured),self.assertRaises(a.ApprovalDenied) as denied:
                h.approved(label='buy50')
            self.assertEqual(denied.exception.reason,'capacity_exceeded')
            self.assertEqual(h.db.local_stored,before)
            self.assertGreater(sum(observed[-1]),128)
            print('EX11_Q26_PRESENT records='+str(observed[-1][0])+' completion='+str(observed[-1][1])+' limit=128; full financial literal NOT reached')

    def test_issuer_slots_in_two_intents_do_not_collide_in_persisted_event_identity(self):
        h=FinancialHarness((fact('same-fixture-label'),))
        second=replace(h.intent,intent_id='independent-intent')
        attempt=replace(h.attempt,attempt_id='independent-attempt',intent_id=second.intent_id)
        receipt=h.broker.handoff(attempt,second)
        first=h.event(0);other=h.broker.issue_event(receipt,0)
        self.assertNotEqual((first.event_id,first.revision),(other.event_id,other.revision))
        self.assertEqual(h.broker.issue_event(receipt,0),other)
        self.assertEqual((first.quantity,other.quantity),('1','1'))

    def test_atomic_withdraw_real_transition_bridge_carries_exact_new_challenge_receipt(self):
        from dataclasses import asdict
        from test_execution_control import ControlHarness,LocalParticipant
        from quantharbor.adapters.execution_uow import ExecutionUnitOfWork,MAX_CHUNK
        from quantharbor.domain.serialization import parse_payload
        captured=[];original=LocalParticipant.call
        def record(participant,function,*values):
            if function=='execution_save':captured.append(deepcopy(values[1]))
            return original(participant,function,*values)
        with patch('quantharbor.adapters.postgres_execution.ExecutionUnitOfWork',LocalParticipant):
            h=ControlHarness(reporting=False);approval=h.admit()
            before=deepcopy(h.db.local_stored)
            with patch.object(LocalParticipant,'call',record):
                receipt=h.app.withdraw(h.controller,a.ref('approval',approval.approval_id,approval),command_id='bridge-protect')
            self.assertEqual(receipt.outcome,'applied')
            after=deepcopy(h.db.local_stored)
            self.assertEqual(h.app.withdraw(h.controller,a.ref('approval',approval.approval_id,approval),command_id='bridge-protect'),receipt)
            self.assertEqual(h.db.local_stored,after)
        state=_unpack(before['state']);new=_unpack(after['state'])
        challenge=parse_payload(new['records'][receipt.challenge_ref]).payload
        self.assertNotIn(receipt.challenge_ref,state['records'])
        sid=h.repo._registry['handles'][h.controller]
        session=parse_payload(state['records'][state['heads'][('session',sid)]]).payload
        principal=parse_payload(state['records'][session.principal_ref]).payload
        u=ExecutionUnitOfWork(h.db,h.source.request.account_ref);u._loaded=before
        u.bind(h.authority,h.repo._registry,h.broker);u.actor(principal,session,'withdraw');u.command(challenge)
        chunks=[];headers=[]
        def select(function,*values,**kwargs):
            if function=='execution_stage_chunk':
                chunk=bytes.fromhex(values[2]);self.assertLessEqual(len(chunk),MAX_CHUNK);chunks.append(chunk)
            elif function=='execution_issue_context':headers.append(json.loads(values[4]))
            return True
        with patch.object(u,'_exchange'),patch.object(u,'_select',side_effect=select):u._apply('save',captured[-1])
        header=headers[0];delta=json.loads(b''.join(chunks))
        self.assertEqual((header['actor'],header['session'],header['action'],header['nonce']),
            (principal.principal_id,session.session_id,'withdraw',challenge.nonce))
        self.assertEqual(header['command'],asdict(challenge))
        self.assertEqual(header['generation'],state['generation'])
        evidence={x['wire']['schema_name']:x['wire']['payload'] for x in delta['evidence']}
        self.assertEqual(evidence['ActionChallenge'],asdict(challenge))
        self.assertEqual(evidence['ActionReceipt'],asdict(receipt))
        self.assertTrue({'commands','nonces','receipts'}<={x['key'] for x in delta['state_delta']})
        self.assertNotIn('state',delta)

    def test_terminal_both_fresh_rebind_exact_Q26_history_barrier_is_not_active3_proof(self):
        from test_execution_control import ControlHarness,LocalParticipant
        from quantharbor.application.approval import ApprovalApplication
        from synthetic_execution import replacement_source
        with patch('quantharbor.adapters.postgres_execution.ExecutionUnitOfWork',LocalParticipant):
            h=ControlHarness(reporting=False,facts=());approvals=[]
            for ix in range(2):
                ap=h.approved(ix,label='before-'+str(ix))
                result=h.app.execute(h.approver,h.app.challenge(h.approver,a.ref('approval',ap.approval_id,ap),action='admit',command_id='admit-'+str(ix)))
                self.assertEqual(result.outcome,'applied');approvals.append(h.repo.head(h.approver,ap.approval_id))
            original=deepcopy(h.state())
            for ix,ap in enumerate(approvals):
                for closure in range(2):
                    self.assertEqual(h.app.withdraw(h.controller,a.ref('approval',ap.approval_id,ap),command_id='end-'+str(ix)+'-'+str(closure)).outcome,'applied')
            new=h.restart();h.repo=new;h.authority=h.new_authority;h.app=ApprovalApplication(new)
            h.controller=h.authority.issue_session('controller');h.approver=h.authority.issue_session('approver')
            self.assertEqual(new.rebind(h.controller,h.broker.query()).result,'matched');new.control(h.controller,'resume')
            h.source=replacement_source(h.source,('3','4'),label='new-third');new.replace_source(h.controller,h.source)
            new.control(h.controller,'disconnect')
            self.assertTrue(all(i.state=='aborted_unsent' for i in h.state()['intents'].values()))
            before=deepcopy(h.db.local_stored);observed=[];room=new._room
            def measure(state):
                observed.append((new._usage(state)[0],sum(v[0] for v in state['holds'].values())))
                return room(state)
            with patch.object(new,'_room',measure),self.assertRaises(a.ApprovalDenied) as denied:h.approved(label='third')
            self.assertEqual(denied.exception.reason,'capacity_exceeded')
            self.assertEqual(observed[-1],(85,48))
            self.assertEqual(h.db.local_stored,before)
            self.assertEqual(h.state()['claims'],original['claims'])
            self.assertTrue(all(h.state()['records'][r]==raw for r,raw in original['records'].items()))


class CompletionLookupTests(unittest.TestCase):
    def setUp(self):
        from test_execution_control import LocalParticipant
        self.storage=patch('quantharbor.adapters.postgres_execution.ExecutionUnitOfWork',LocalParticipant)
        self.storage.start();self.addCleanup(self.storage.stop)

    def test_completed_reclaim_exact_three_rows_pending_preserved_and_replay_no_write(self):
        from test_execution_control import ControlHarness
        h=ControlHarness(reporting=False);h.admit()
        command=h.admission_command;receipt=h.app.execute(h.approver,command)
        ap=h.repo.head(h.approver,h.approval.approval_id)
        pending=h.app.challenge(h.controller,a.ref('approval',ap.approval_id,ap),action='withdraw',command_id='pending')
        before=h.state();result=h.repo.reclaim_completed(h.controller);after=h.state()
        self.assertEqual(result['commands'],2)
        self.assertEqual(result['records'],6)
        self.assertEqual(sum(len(before[k])-len(after[k]) for k in ('commands','nonces','receipts')),6)
        self.assertEqual(result['bytes'],6*4096)
        self.assertEqual(before['holds'],after['holds'])
        for key in ('records','heads','claims','intents','reservations','outbox'):
            self.assertEqual(before[key],after[key])
        self.assertEqual(set(after['commands']),{'pending'})
        self.assertIn(pending.nonce,after['nonces'])
        frozen=deepcopy(h.db.local_stored)
        self.assertEqual(h.app.execute(h.approver,command),receipt)
        self.assertEqual(h.app.challenge(h.approver,command.target_ref,action='admit',command_id=command.command_id),command)
        self.assertEqual(h.db.local_stored,frozen)
        for changed in (replace(command,nonce='tampered'),replace(command,action='withdraw')):
            with self.assertRaises(a.ApprovalDenied):h.app.execute(h.approver,changed)
        h.repo.change_permissions(h.controller,'approver',('query',))
        with self.assertRaises(a.ApprovalDenied):h.app.execute(h.approver,command)

    def test_reclaim_commit_failure_rolls_back_all_three_maps(self):
        from test_execution_control import ControlHarness
        h=ControlHarness(reporting=False);h.admit();before=deepcopy(h.db.local_stored)
        from test_execution_control import LocalParticipant
        original=LocalParticipant.call
        def save_failure(participant,function,*values):
            if function=='execution_save':raise d.ExecutionDenied('storage_failure')
            return original(participant,function,*values)
        with patch.object(LocalParticipant,'call',save_failure):
            with self.assertRaises(d.ExecutionDenied):h.repo.reclaim_completed(h.controller)
        self.assertEqual(h.db.local_stored,before)
        with h.repo.inject_failure('commit'):
            with self.assertRaises(a.ApprovalDenied):h.repo.reclaim_completed(h.controller)
        self.assertEqual(h.db.local_stored,before)
        h.db.fail_commit=True
        with self.assertRaises(d.ExecutionDenied):h.repo.reclaim_completed(h.controller)
        self.assertEqual(h.db.local_stored,before)

    def test_same_generation_two_terminal_then_real_third_dispatch(self):
        from test_execution_control import ControlHarness
        from synthetic_execution import replacement_source
        h=ControlHarness(reporting=False,facts=());aps=[]
        for ix in range(2):
            ap=h.approved(ix,label='approved-'+str(ix))
            c=h.app.challenge(h.approver,a.ref('approval',ap.approval_id,ap),action='admit',command_id='admitted-'+str(ix))
            self.assertEqual(h.app.execute(h.approver,c).outcome,'applied')
            aps.append(h.repo.head(h.approver,ap.approval_id))
        for ix,ap in enumerate(aps):
            for j in range(2):self.assertEqual(h.app.withdraw(h.controller,a.ref('approval',ap.approval_id,ap),command_id=f'end-{ix}-{j}').outcome,'applied')
        generation=h.state()['generation']
        self.assertTrue(all(i.state=='aborted_unsent' for i in h.state()['intents'].values()))
        self.assertEqual(h.repo.reclaim_completed(h.controller)['records'],24)
        h.repo.control(h.controller,'stop')
        self.assertEqual(h.repo.rebind(h.controller,h.broker.query()).result,'matched')
        h.repo.control(h.controller,'resume')
        h.source=replacement_source(h.source,('3','4'),label='third-real');h.repo.replace_source(h.controller,h.source)
        self.assertEqual(h.state()['mode'],'running')
        third=h.approved(label='third-approve')
        c=h.app.challenge(h.approver,a.ref('approval',third.approval_id,third),action='admit',command_id='third-admit')
        result=h.app.execute(h.approver,c)
        self.assertEqual((result.outcome,result.reason_code),('applied',None))
        consumed=h.repo.head(h.approver,third.approval_id)
        state=h.state();self.assertEqual(len(state['intents']),3);self.assertEqual(len(state['claims']),3)
        self.assertEqual(state['generation'],generation)
        self.assertLessEqual(sum(i.state not in d.TERMINAL for i in state['intents'].values()),2)
        self.assertEqual(h.repo.dispatch(h.controller,consumed.consumed_intent_id).kind,'accepted')


    def test_two_active_third_reaches_real_admission_gate(self):
        from test_execution_control import ControlHarness
        from synthetic_execution import replacement_source
        h=ControlHarness(reporting=False,facts=(),target_options={'holdings':('0','4'),'targets':('1','3'),'lot':'0.5','fee':'0'},exposure_ceiling='2000');aps=[]
        for ix in range(2):
            ap=h.approved(ix,label='active-approved-'+str(ix))
            c=h.app.challenge(h.approver,a.ref('approval',ap.approval_id,ap),action='admit',command_id='active-admitted-'+str(ix))
            self.assertEqual(h.app.execute(h.approver,c).outcome,'applied')
            ap=h.repo.head(h.approver,ap.approval_id);aps.append(ap)
            self.assertEqual(h.repo.dispatch(h.controller,ap.consumed_intent_id).kind,'accepted')
            # Requests on handed-off intents preserve their financial holds.
            for j in range(2):self.assertEqual(h.app.withdraw(h.controller,a.ref('approval',ap.approval_id,ap),command_id=f'active-withdraw-{ix}-{j}').outcome,'applied')
            h.repo.reclaim_completed(h.controller)
        before=h.state();self.assertEqual(sum(i.state not in d.TERMINAL for i in before['intents'].values()),2)
        self.assertTrue(any(r.held!='0' for r in before['reservations'].values()))
        h.source=replacement_source(h.source,('0.5','3'),label='active-third-real');h.repo.replace_source(h.controller,h.source)
        third=h.approved(label='active-third-approve')
        c=h.app.challenge(h.approver,a.ref('approval',third.approval_id,third),action='admit',command_id='active-third-admit')
        reached=[];original=h.repo._admit
        def actual(state,approval,at,event):
            reached.append(sum(i.state not in d.TERMINAL for i in state['intents'].values()))
            return original(state,approval,at,event)
        import quantharbor.adapters.postgres_execution as adapter
        with patch.object(h.repo,'_admit',side_effect=actual),patch.object(adapter,'current_risk',wraps=adapter.current_risk) as risk:
            result=h.app.execute(h.approver,c)
        self.assertEqual(reached,[2]);self.assertEqual(risk.call_count,1)
        self.assertEqual((result.outcome,result.reason_code),('rejected','capacity_exceeded'))
        self.assertEqual(len(h.state()['claims']),2);self.assertEqual(len(h.state()['intents']),2)
        self.assertEqual(before['reservations'],h.state()['reservations'])
