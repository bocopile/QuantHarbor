"""Q27 단일 DB 권위. 최초 session/presentation부터 DB 안에서 Q26 순수 전이를 재사용한다.

메모리 승인을 import하지 않는다. 상속한 Q26 메서드의 dict는 잠긴 transaction의
작업 사본이며 공개 진입점은 항상 DB에서 다시 읽는다. 외부 capability identity만
살아 있는 issuer registry에 남으며 권한/session/nonce/head는 DB에서 해소한다.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass, replace
from functools import wraps
from hashlib import sha256
import json
from uuid import uuid4

from quantharbor.adapters.execution_uow import ExecutionUnitOfWork
from quantharbor.adapters.execution_uow import ExecutionUnitOfWork as _TrustedUnitOfWork
from quantharbor.adapters.postgres_ledger import PostgresLedger
from quantharbor.adapters.synthetic_approval import (SyntheticApprovalRepository, SyntheticAuthority,
    _SessionHandle, _ReadPermit, _safe)
from quantharbor.adapters.synthetic_execution_broker import SyntheticExecutionBroker
from quantharbor.application.approval import source_bytes
from quantharbor.application.execution import current_risk,validate_current,_validate_account_current,build_current_inputs,execution_cash_base
from quantharbor.application.valuation import reconcile as reconcile_values
from quantharbor.domain import approval as a
from quantharbor.domain import execution as d
from quantharbor.domain.execution_budget import admit_manifest
from quantharbor.domain.ledger import (SyntheticLedgerSubmission, CashLeg, PositionDelta,
    LedgerCompleteness, hash_record, exact, integer)
from quantharbor.domain.primitives import identifier, utc_instant
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.target import ref as target_ref
from quantharbor.domain.valuation import finite, number
from quantharbor.ports.approval import ApprovalSource
from quantharbor.ports.execution import ExecutionInputs


@dataclass(frozen=True, slots=True)
class _HandoffWindow:
    """Only built from the locked DB read-set; never accepted by a public API."""
    attempt: d.DispatchAttempt
    intent: d.OrderIntent
    checked_at: str
    deadlines: tuple[str, ...]


def _pack(x):
    if x is None or type(x) in (str,int,bool): return x
    if type(x) is bytes: return {'bytes':x.decode()}
    if type(x) is tuple: return {'tuple':[_pack(v) for v in x]}
    if type(x) is dict: return {'map':[[_pack(k),_pack(v)] for k,v in x.items()]}
    if is_dataclass(x):
        return {'wire':json.loads(canonical_bytes(CanonicalPayload(type(x).__name__,1,'synthetic',x)))}
    raise d.ExecutionDenied()


def _unpack(x):
    if x is None or type(x) in (str,int,bool): return x
    if type(x) is not dict or len(x)!=1: raise d.ExecutionDenied()
    if 'bytes' in x: return x['bytes'].encode()
    if 'tuple' in x: return tuple(_unpack(v) for v in x['tuple'])
    if 'map' in x: return {_unpack(k):_unpack(v) for k,v in x['map']}
    if 'wire' in x: return parse_payload(json.dumps(x['wire'])).payload
    raise d.ExecutionDenied()


def _source_rights_restriction(previous,source):
    """Only attenuation of grants on the exact already-reproduced Q24 material.

    This can revoke authority while inputs are stale. It never makes a current
    binding, matched reconciliation, candidate or submission newly valid.
    """
    def point(old,new):
        if len(old.market_inputs)!=len(new.market_inputs): raise ValueError()
        restored=[]
        for left,right in zip(old.market_inputs,new.market_inputs):
            before,after=left.current_rights,right.current_rights
            if (replace(after,purposes=before.purposes,revoked_at=before.revoked_at)!=before or
                not set(after.purposes)<=set(before.purposes) or
                before.revoked_at is not None and (after.revoked_at is None or after.revoked_at>before.revoked_at)):
                raise ValueError()
            restored.append(replace(right,current_rights=before))
        return replace(new,market_inputs=tuple(restored))
    try:
        old,new=previous.inputs,source.inputs
        if any(len(getattr(old,k))!=len(getattr(new,k)) for k in ('risk_points','boundary_inputs','daily_usage_inputs')):
            return False
        restored=replace(new,current=point(old.current,new.current),
            **{k:tuple(point(x,y) for x,y in zip(getattr(old,k),getattr(new,k)))
               for k in ('risk_points','boundary_inputs','daily_usage_inputs')})
        return replace(source,inputs=restored)==previous
    except (ValueError,TypeError):return False


def _validate_source_replacement(previous,source,at):
    if previous is not None and _source_rights_restriction(previous,source):return
    from quantharbor.application.approval import validate_source
    if not source.artifacts.candidates:raise a.ApprovalDenied('source_unresolved')
    for candidate in source.artifacts.candidates:
        validate_source(source,target_ref('candidate',candidate.candidate_id,candidate),at=at,
            generation=source.request.authority_generation)


def _db_command(function):
    @wraps(function)
    def call(self,*args,**kwargs):
        with self._lock:
            if self._uow is not None:
                return function(self,*args,**kwargs)
            old_handles,old_readers = dict(self._registry['handles']),dict(self._registry['readers'])
            old_generation = self._authority._generation
            if self._registry.get('blocked'):
                raise d.ExecutionDenied('source_unresolved')
            old_history = self._registry.get('source_history',())
            self._source_history = old_history
            commit_started = False
            old_inputs = self._registry['inputs']
            old_source = self._registry['source']
            self._source = old_source
            self._inputs = old_inputs
            try:
                with ExecutionUnitOfWork(self._database,self._account) as uow:
                    self._uow = uow
                    self._bind_uow()
                    stored = uow.call('execution_load',self._account)
                    if stored is None:
                        raise d.ExecutionDenied('storage_failure')
                    self._db_version = stored['version']
                    self._state = _unpack(stored['state'])
                    if (self._state['generation'] != self._authority._generation or
                        self._registry.get('authority',self._authority) is not self._authority):
                        raise a.ApprovalDenied('generation_mismatch')
                    if (self._state.get('source_archive',())!=tuple(source_bytes(x) for x in self._source_history) or
                        stored['source_hash'] != self._source_hash()):
                        raise d.ExecutionDenied('source_unresolved')
                    self._state['handles'] = {h:sid for h,sid in self._registry['handles'].items()
                        if ('session',sid) in self._state['heads']}
                    self._state['readers'] = dict(self._registry['readers'])
                    self._dirty = False
                    self._final_authorities = []
                    self._refresh_check = None
                    self._validation_query = None
                    self._validated_current = None
                    self._source_replace_check = None
                    self._cancel_check = None
                    result = function(self,*args,**kwargs)
                    if self._dirty:
                        self._final_check()
                        self._persist()
                    commit_started = True
                    uow.commit()
                    self._registry['inputs'] = self._inputs
                    self._registry['source'] = self._source
                    self._registry['source_history'] = self._source_history
                    self._authority._generation = self._state['generation']
                    if self._state['generation']!=old_generation:
                        self._registry['handles'].clear()
                        self._registry['readers'].clear()
                    return result
            except (a.ApprovalDenied,d.ExecutionDenied):
                self._registry['handles'],self._registry['readers'] = old_handles,old_readers
                self._authority._generation = old_generation
                staged=(self._inputs,self._source,self._source_history,(self._state['generation'],self._state['fence']))
                self._inputs = old_inputs
                self._source = old_source
                self._source_history = old_history
                if commit_started:
                    self._observe_binding_commit(staged,stored)
                raise
            except Exception:
                self._registry['handles'],self._registry['readers'] = old_handles,old_readers
                self._authority._generation = old_generation
                staged=(self._inputs,self._source,self._source_history,(self._state['generation'],self._state['fence']))
                self._inputs = old_inputs
                self._source = old_source
                self._source_history = old_history
                if commit_started:
                    self._observe_binding_commit(staged,stored)
                raise d.ExecutionDenied('storage_failure') from None
            finally:
                self._uow = None
                self._state = None  # never serve authority from a cached aggregate
    return call


class PostgresExecutionRepository(SyntheticApprovalRepository):
    def __init__(self,database,authority,source,approval_policy,inputs,broker,*,cancel_principals=()):
        if (type(database) is not PostgresLedger or not database._ready or
            type(authority) is not SyntheticAuthority or type(source) is not ApprovalSource or
            type(inputs) is not ExecutionInputs or type(broker) is not SyntheticExecutionBroker):
            raise a.ApprovalDenied('authority_denied')
        if authority._repository is not None:
            # Multiple facades must share the very same composition, gate and opaque registry.
            prior = authority._repository
            if (type(prior) is not PostgresExecutionRepository or prior._database is not database or
                prior._registry['source'] is not source or prior._registry['inputs'] is not inputs or prior._broker is not broker):
                raise a.ApprovalDenied('authority_denied')
            self.__dict__.update(prior.__dict__)
            self._uow, self._state = None,None
            return
        policy = a.checked(approval_policy)
        if (type(policy) is not a.SyntheticApprovalPolicy or policy.account_ref != source.request.account_ref or
                inputs.policy.account_ref != policy.account_ref or broker._account != policy.account_ref):
            raise a.ApprovalDenied('authority_denied')
        broker.verify(inputs.query,'query',inputs.query.query_id)
        _validate_source_replacement(None,source,utc_instant(authority._clock()))
        self._database,self._authority,self._source,self._inputs,self._broker = database,authority,source,inputs,broker
        self._account = policy.account_ref
        self._lock = broker._gate
        self._source_history=()
        self._registry = {'handles':{},'readers':{},'inputs':inputs,'source':source,'source_history':(),'authority':authority}
        self._capacity,self._byte_capacity = 128,8388608
        self._failure,self._uow = None,None
        self._aggregate_id = 'execution-aggregate:'+uuid4().hex
        self._state = {'version':0,'records':{},'heads':{},'handles':{},'readers':{},'commands':{},
            'nonces':{},'receipts':{},'holds':{},'intents':{},'reservations':{},'outbox':{},'claims':{},
            'mode':'stopped','risk_ref':None,'last_at':None,'clock_fault':False,
            'generation':authority._generation,'restored':False,'source_bytes':len(source_bytes(source)),
            'policy':None,'permissions':{p.principal_id:p.allowed_actions for p in authority._principals.values()},
            'fence':1,'execution_records':{},'attempts':{},'events':{},'cancel_commands':{},
            'reconciliation':None,'withdrawals':{},'ledger_mapping':{},'unknown_costs':{},
            'current_policy_ref':d.ref('policy',inputs.policy.policy_id,inputs.policy),
            'target_policy_ref':inputs.policy.target_policy_ref,'pending_target_policy_ref':inputs.policy.target_policy_ref}
        if type(cancel_principals) is not tuple or any(x not in authority._principals or authority._principals[x].role!='controller' for x in cancel_principals):
            raise a.ApprovalDenied('authority_denied')
        self._state['execution_permissions'] = {x:('cancel',) for x in cancel_principals}
        self._state['policy'] = self._put(self._state,'policy',policy)
        with self._lock,ExecutionUnitOfWork(database,self._account) as uow:
            self._uow = uow
            self._bind_uow()
            existing = uow.call('execution_load',self._account)
            # Existing DB is intentionally not adopted by a new issuer. Restart uses rotate().
            if existing is not None:
                self._uow,self._state = None,None
                raise a.ApprovalDenied('authority_denied')
            self._db_version = -1
            self._persist()
            uow.commit()
        self._uow,self._state = None,None
        authority._repository = self

    def _bind_uow(self):
        if type(self._uow) is _TrustedUnitOfWork:
            self._uow.bind(self._authority,self._registry,self._broker)

    def _auth(self,s,handle,action,at,**kwargs):
        principal,session=super()._auth(s,handle,action,at,**kwargs)
        if type(self._uow) is _TrustedUnitOfWork:
            self._uow.actor(principal,session,action)
        return principal,session

    def _observe_binding_commit(self,staged,baseline):
        """No write retry. Only an exact committed DB identity can publish staging."""
        inputs,source,history,epoch=staged
        try:
            with ExecutionUnitOfWork(self._database,self._account) as observed:
                stored=observed.call('execution_load',self._account)
            self._inputs,self._source,self._source_history=inputs,source,history
            wanted=self._source_hash()
            observed_state=None if stored is None else _unpack(stored['state'])
            if (stored is not None and stored['source_hash']==wanted and
                stored['version']==self._db_version and
                (observed_state['generation'],observed_state['fence'])==epoch and
                observed_state.get('source_archive',())==tuple(source_bytes(x) for x in history) and
                epoch[0]==self._authority._generation):
                self._registry.update(inputs=inputs,source=source,source_history=history)
            elif stored is not None and (stored['version'],stored['source_hash'])==(baseline['version'],baseline['source_hash']):
                pass  # exact old DB binding: rollback observed, keep committed registry
            else:
                self._registry['blocked']=True
        except Exception:
            self._registry['blocked']=True
        finally:
            self._inputs=self._registry['inputs']
            self._source=self._registry['source']
            self._source_history=self._registry.get('source_history',())

    def _source_check(self,s,reference,at,*,require_live=True):
        from quantharbor.application.approval import validate_source
        sources=(self._source,) if require_live else (self._source,*self._source_history)
        for source in sources:
            if any(target_ref('candidate',c.candidate_id,c)==reference for c in source.artifacts.candidates):
                return validate_source(source,reference,at=at,
                    generation=source.request.authority_generation,require_live=require_live)
        raise a.ApprovalDenied('source_unresolved')

    def _source_hash(self):
        raw = source_bytes(self._source) + source_bytes(replace(self._source,inputs=self._inputs.current)) + d.encoded(self._inputs.query)+d.encoded(self._inputs.policy)+(self._inputs.runtime_generation or '').encode()
        raw += b''.join(source_bytes(x) for x in self._source_history)
        resolved=set()
        for source in (*self._source_history,self._source,replace(self._source,inputs=self._inputs.current)):
            resolved.update(source.artifacts.plan.body.input_refs)
            i=source.inputs
            resolved.update(('event',x.body.event_id) for x in i.events)
            resolved.update(('cost',x.trade.ref) for x in i.costs)
            resolved.update(('obligation',x.source_id) for x in i.obligation_sources)
            for point in (i.current,*i.risk_points,*i.boundary_inputs,*i.daily_usage_inputs):
                resolved.add(('snapshot',point.snapshot.snapshot_id))
                for data in point.market_inputs:
                    for item in data.bundle.evidence:
                        r=item.revision
                        resolved.add(('revision',r.source_id,r.dataset_id,r.event_id,r.revision_id))
                        resolved.add(('observation',item.observation.observation_id))
        if len(resolved)>128 or len(raw)>8388608:
            raise a.ApprovalDenied('capacity_exceeded')
        return sha256(raw).hexdigest()

    def _account_validation(self,s,at):
        approval_policy=self._policy(s)
        if not approval_policy.valid_from<=at<approval_policy.valid_to:
            raise a.ApprovalDenied('expired')
        projection=self._inputs.current.current.snapshot.valuation.projection
        value=_validate_account_current(self._source,self._inputs,self._broker,at=at,
            generation=s['generation'],projection=projection,intents=tuple(s['intents'].values()))
        from quantharbor.application import target
        for source in self._source_history:
            for point in (*source.inputs.risk_points,*source.inputs.boundary_inputs,
                          source.inputs.current,*source.inputs.daily_usage_inputs):
                target._current_rights(point,at,self._inputs.policy.target_policy_ref,('research','store','report'))
        execution_cash_base(self._inputs.current,value[4],self._inputs.policy.target_policy_ref,tuple(s['reservations'].values()))
        ends=[value[1]]
        for source in self._source_history:
            for point in (*source.inputs.risk_points,*source.inputs.boundary_inputs,source.inputs.current,*source.inputs.daily_usage_inputs):
                for data in point.market_inputs:
                    ends.extend((data.current_rights.valid_to,data.current_rights.revoked_at or data.current_rights.valid_to))
        value=(value[0],min(ends),*value[2:])
        self._validated_current={'source_hash':self._source_hash(),'current_identity':self._current_identity(),
            'validator_version':'q27-account-current-v1','valid_from':value[0],'valid_to':value[1],
            'query_ref':asdict(d.ref('query',(self._validation_query or self._inputs.query).query_id,self._validation_query or self._inputs.query)),
            'ledger_cursor':projection.ledger_cursor,'generation':s['generation'],'fence':s['fence']}
        return value

    def _current_identity(self):
        return sha256((self._source_hash()+':q27-account-current-v1').encode()).hexdigest()

    def _usage(self,s):
        # Q26 128/8MiB budget remains independent from execution's 1024/64MiB budget.
        q = {k:v for k,v in s.items() if k not in ('execution_records','attempts','events','cancel_commands','withdrawals','ledger_mapping','unknown_costs','event_heads','event_dispositions','financial_excess','current_binding','cancel_nonces','restart_binding')}
        q = q | {'intents':{},'reservations':{},'outbox':{},'claims':{}}
        return super()._usage(q)

    def _commit(self,s,*,owner=None,release=False):
        if self._uow is None: raise a.ApprovalDenied('authority_denied')
        if owner is not None and owner in s['holds'] and ('approval',owner) in s['heads']:
            approval=self._get(s,s['heads'][('approval',owner)])
            if approval.state=='consumed':
                # approve/deny/admit futures are now impossible. Preserve both
                # protective withdrawals and every already-issued command closure.
                count=2-s['withdrawals'].get(approval.consumed_intent_id,0)
                pending_n,pending_b=self._pending_budget(s,owner)
                before_n,before_b=self._usage(self._state)
                after_n,after_b=self._usage(s)
                s['holds'][owner]=(count*8+pending_n+max(0,after_n-before_n),
                    count*8*65536+pending_b+max(0,after_b-before_b))
        super()._commit(s,owner=owner,release=release)
        self._dirty = True

    def _final_check(self):
        """잠긴 전체 read-set은 그대로 두고 commit 직전 시각·현재 권한을 재확인한다."""
        if getattr(self,'_source_replace_check',None) is not None:
            handle,action,previous=self._source_replace_check
            at=self._now()
            self._auth(self._state,handle,action,at,protective=True)
            _validate_source_replacement(previous,self._source,at)
        if self._cancel_check is not None:
            handle,command_id = self._cancel_check
            self._check_cancel(self._state,handle,self._state['cancel_commands'][command_id],self._now())
        if self._refresh_check is not None:
            handle,action = self._refresh_check
            at = self._now()
            self._auth(self._state,handle,action,at,protective=True)
            self._account_validation(self._state,at)
        if not self._final_authorities:
            return
        s,at = self._state,self._now()
        for original,actor,action,approval,risk_ref,intent_id in self._final_authorities:
            self._auth(s,original,'approve',at)
            self._auth(s,actor,action,at)
            self._revalidate(s,approval,at)
            risk = s['execution_records'][risk_ref]
            intent = s['intents'][intent_id]
            if (s['mode']!='running' or at>=risk.valid_to or
                (intent.generation,intent.fence)!=(s['generation'],s['fence'])):
                raise a.ApprovalDenied('risk_blocked')

    def _persist(self):
        s = self._state
        self._room(s)
        persistent = {k:v for k,v in s.items() if k not in ('handles','readers')}
        evidence = [{'ref':asdict(r),'wire':json.loads(raw)} for r,raw in s['records'].items()]
        evidence += [{'ref':asdict(r),'wire':json.loads(d.encoded(obj))} for r,obj in s['execution_records'].items()]
        closed=[]
        for iid,intent in s['intents'].items():
            issued=[r for (owner,_),r in self._broker._event_count.items() if owner==iid]
            processed={d.ref('event',e.event_id,e) for e in s['events'].values() if e.intent_id==iid}
            if (intent.state in d.TERMINAL and intent.accounting=='complete' and
                (intent.state in ('rejected','aborted_unsent') or
                 len(issued)==len(self._broker._facts) and set(issued)<=processed)):
                closed.append(iid)
        obj = {'state':_pack(persistent),'generation':s['generation'],'mode':s['mode'],'fence':s['fence'],
            'source_hash':self._source_hash(),'evidence':evidence,'heads':[asdict(r) for r in s['heads'].values()],
            'intents':[asdict(x) for x in s['intents'].values()],
            'reservations':[asdict(x) for x in s['reservations'].values()],
            'attempts':[asdict(x) for x in s['attempts'].values()],'closed_owners':closed}
        if type(self._uow) is _TrustedUnitOfWork:
            self._uow.validity(getattr(self,'_validated_current',None))
        self._db_version = self._uow.call('execution_save',self._account,obj,str(self._db_version))

    def _remember(self,s,kind,identity,obj):
        obj = d.checked(obj)
        r = d.ref(kind,identity,obj)
        s['execution_records'][r] = obj
        return r

    @_db_command
    def _issue(self,issuer,principal_id,*,reader):
        token = super()._issue(issuer,principal_id,reader=reader)
        if reader: self._registry['readers'][token] = self._state['readers'][token]
        else: self._registry['handles'][token] = self._state['handles'][token]
        return token

    @_db_command
    def present(self,*args,**kwargs): return super().present(*args,**kwargs)
    def _past_command(self,s,command_id):
        challenge=receipt=None
        for reference in s['records']:
            if reference.kind not in ('challenge','receipt'): continue
            obj=self._get(s,reference)
            if obj.command_id!=command_id: continue
            if reference.kind=='challenge': challenge=obj
            else: receipt=obj
        return challenge,receipt

    def _command_refs(self,s,command_id):
        cr,rr=super()._command_refs(s,command_id)
        if cr is not None: return cr,rr
        challenge,receipt=self._past_command(s,command_id)
        if challenge is None or receipt is None: return None,None
        cr=a.ref('challenge',challenge.challenge_id,challenge)
        if (receipt.challenge_ref!=cr or receipt.command_payload_hash!=sha256(a.encoded(challenge)).hexdigest() or
            (receipt.command_id,receipt.action,receipt.target_ref,receipt.actor_evidence_ref)!=
            (challenge.command_id,challenge.action,challenge.target_ref,challenge.principal_ref)):
            raise a.ApprovalDenied('replay_conflict')
        return cr,a.ref('receipt',receipt.command_id,receipt)

    def _command_nonce(self,s,challenge,reference,receipt):
        # An absent lookup is valid only for an exact completed immutable pair.
        if super()._command_nonce(s,challenge,reference,receipt): return True
        return (receipt is not None and self._get(s,reference)==challenge and
            self._get(s,receipt).challenge_ref==reference)

    @_db_command
    def reclaim_completed(self,handle):
        """Separate atomic maintenance: never offsets a different owner's writes."""
        s,at=self._copy(),self._now()
        principal,_=self._auth(s,handle,'query',at,protective=True)
        if principal.role!='controller': raise a.ApprovalDenied('authority_denied')
        count=0;before=self._usage(s)
        for command_id,cr in tuple(s['commands'].items()):
            rr=s['receipts'].get(command_id)
            if rr is None: continue
            challenge=self._get(s,cr);receipt=self._get(s,rr)
            if (receipt.challenge_ref!=cr or receipt.command_payload_hash!=sha256(a.encoded(challenge)).hexdigest() or
                (receipt.command_id,receipt.action,receipt.target_ref,receipt.actor_evidence_ref)!=
                (challenge.command_id,challenge.action,challenge.target_ref,challenge.principal_ref) or
                s['nonces'].get(challenge.nonce)!=cr):
                raise a.ApprovalDenied('replay_conflict')
            del s['commands'][command_id];del s['nonces'][challenge.nonce];del s['receipts'][command_id]
            count+=1
        after=self._usage(s)
        if count: self._commit(s)
        return {'commands':count,'records':before[0]-after[0],'bytes':before[1]-after[1]}

    @_db_command
    def command_result(self,handle,command_id):
        identifier(command_id)
        s,at=self._state,self._now()
        principal,_=self._auth(s,handle,'query',at,protective=True)
        challenge,receipt=self._past_command(s,command_id)
        if challenge is None or receipt is None: return None
        original=self._get(s,challenge.principal_ref)
        if principal.role!='controller' and principal.principal_id!=original.principal_id:
            raise a.ApprovalDenied('authority_denied')
        if challenge.action not in ('withdraw','revoke'):
            approval=self._get(s,challenge.target_ref)
            self._source_check(s,approval.candidate_ref,at,require_live=False)
        return receipt

    @_db_command
    def challenge(self,*args,**kwargs): return super().challenge(*args,**kwargs)
    @_db_command
    def execute(self,*args,**kwargs):
        result=super().execute(*args,**kwargs)
        if type(self._uow) is _TrustedUnitOfWork:
            handle=args[0] if args else kwargs['handle']
            challenge=args[1] if len(args)>1 else kwargs['challenge']
            # Admission also checks the original approve right. A rejected
            # admission has no successful-intent final check to restore the
            # command actor/action, so bind it again through current auth.
            self._auth(self._state,handle,challenge.action,self._now(),
                protective=challenge.action in ('withdraw','revoke'))
            self._uow.command(challenge)
        return result
    @_db_command
    def withdraw(self,*args,**kwargs): return super().withdraw(*args,**kwargs)
    @_db_command
    def query(self,*args,**kwargs): return super().query(*args,**kwargs)
    @_db_command
    def change_permissions(self,*args,**kwargs): return super().change_permissions(*args,**kwargs)

    def record_risk(self,*args,**kwargs): raise a.ApprovalDenied('authority_denied')
    def record_unknown(self,*args,**kwargs): raise a.ApprovalDenied('authority_denied')
    def restore(self,*args,**kwargs): raise a.ApprovalDenied('authority_denied')
    def snapshot(self): raise a.ApprovalDenied('authority_denied')
    @_db_command
    def replace_source(self,handle,source):
        if type(source) is not ApprovalSource:
            raise a.ApprovalDenied('source_unresolved')
        s,at=self._copy(),self._now()
        _,session=self._auth(s,handle,'runtime',at,protective=True)
        if source==self._source: return
        if source.request.account_ref!=self._account:
            raise a.ApprovalDenied('authority_denied')
        # Policy changes require the existing policy authority, even in stopped mode.
        action='runtime'
        if source.inputs.policy!=self._inputs.current.policy:
            action='policy'
            self._auth(s,handle,'policy',at,protective=True)
        _validate_source_replacement(self._source,source,at)
        previous=self._source
        history=(*self._source_history,self._source)
        s['source_archive']=tuple(source_bytes(x) for x in history)
        s['source_bytes']=sum(len(x) for x in s['source_archive'])+len(source_bytes(source))
        if s['source_bytes']>8388608: raise a.ApprovalDenied('capacity_exceeded')
        self._session_room(s,session,1)
        event=self._event(s,'synthetic_source_update',source.request.request_id,at)
        for (kind,identity),r in tuple(s['heads'].items()):
            if kind=='approval':
                approval=self._get(s,r)
                if approval.state in ('pending','approved'):
                    self._change(s,approval,'invalidated',at,event,reason='policy_changed')
                    s['holds'].pop(identity,None)
        self._source_history=history
        self._source=source
        s['pending_target_policy_ref']=source.request.policy_ref
        self._source_replace_check=(handle,action,previous)
        s['reconciliation']=None
        self._commit(s,owner=session.session_id)
    @_db_command
    def replace_policy(self,*args,**kwargs):
        result=super().replace_policy(*args,**kwargs)
        self._state['reconciliation']=None
        return result

    def _projection(self,at,*,as_of=None):
        raw = self._uow.call('execution_ledger',self._account,'replay',as_of or '',at)
        return parse_payload(json.dumps(dict(schema_name='LedgerProjection',schema_version=1,environment='synthetic',payload=raw))).payload

    def _ledger_events(self,at):
        raw = self._uow.call('execution_ledger',self._account,'events','',at)
        return tuple(parse_payload(json.dumps(dict(schema_name='LedgerEvent',schema_version=1,
            environment='synthetic',payload=x))).payload for x in raw)

    def _validate_inclusions(self,s,query):
        self._broker.verify(query,'query',query.query_id)
        known = {}
        for r in s['reservations'].values():
            known[r.obligation_id+':held'] = (r,'held',number(r.held),None)
            known[r.obligation_id+':used'] = (r,'used',number(r.used),None)
            for key,head in s.get('event_heads',{}).items():
                if key[0]!=r.intent_id: continue
                identity = 'included-execution:'+sha256((r.obligation_id+':'+key[1]+':'+str(key[2])).encode()).hexdigest()
                amount = (number(head['principal']) if r.component=='principal' else
                    number(head['fee'])+number(head['tax']) if r.component=='cost' and head['known'] else
                    number(head['quantity']) if r.component=='quantity' else number('0'))
                known[identity] = (r,'part',amount,head)
        reflected = {}
        seen = set()
        for row in (*query.cash,*query.sellable):
            for component in row.included_components:
                if component in seen or component not in known: raise d.ExecutionDenied('source_unresolved')
                seen.add(component)
                r,part,amount,head = known[component]
                intent = s['intents'][r.intent_id]
                if (type(row) is d.BrokerCash and (r.dimension!='cash' or r.currency_or_unit!=row.currency) or
                    type(row) is d.BrokerQuantity and (r.dimension!='quantity' or intent.terms.position!=row.position)):
                    raise d.ExecutionDenied('source_unresolved')
                if part!='held':
                    if amount<=0 or head is None and type(row) is d.BrokerCash and number(r.used)!=number(r.settled):
                        raise d.ExecutionDenied('source_unresolved')
                    if head is not None and (not head['known'] or not head['ledger_event'] or
                        r.component=='principal' and number(head['settled'])!=number(head['principal'])):
                        raise d.ExecutionDenied('source_unresolved')
                    events = [e for e in s['events'].values() if e.intent_id==r.intent_id]
                    if not events or any(e.effective_at>query.as_of or d.ref('event',e.event_id,e) not in query.events or
                        self._broker._event_sequences[d.ref('event',e.event_id,e)]>query.cutoff_sequence for e in events):
                        raise d.ExecutionDenied('source_unresolved')
                    reflected[r.reservation_id] = reflected.get(r.reservation_id,number('0'))+amount
                    if reflected[r.reservation_id]>number(r.used):
                        raise d.ExecutionDenied('source_unresolved')
                elif amount<=0 or intent.broker_order_id is None or not any(self._broker.resolve(ref).intent_id==intent.intent_id
                    and self._broker.resolve(ref).kind=='accepted' for ref in query.receipts):
                    raise d.ExecutionDenied('source_unresolved')
        partial=set()
        for row in query.sellable:
            for part in row.hold_reflections:
                identity=part.obligation_id+':held'
                if identity in seen or identity in partial or identity not in known:
                    raise d.ExecutionDenied('source_unresolved')
                partial.add(identity)
                r,_,amount,_=known[identity]
                intent=s['intents'][r.intent_id]
                if (r.dimension!='quantity' or intent.terms.position!=row.position or
                    number(part.quantity)>amount or not any(
                        self._broker.resolve(ref).intent_id==intent.intent_id and
                        self._broker.resolve(ref).kind=='accepted' and
                        self._broker.resolve(ref).sequence<=query.cutoff_sequence for ref in query.receipts)):
                    raise d.ExecutionDenied('source_unresolved')
        return reflected

    @_db_command
    def refresh_current(self,handle,query,*,market_inputs=None,execution_policy=None):
        """Issue query first; derive current facts from the locked actual DB prefix.

        Original Q24 source stays immutable. No supplied current-ref, allow or
        caller-complete bit participates in the source-binding transition.
        """
        s,at = self._copy(),self._now()
        self._auth(s,handle,'runtime',at,protective=True)
        query = d.checked(query)
        self._broker.verify(query,'query',query.query_id)
        old = self._inputs.query
        if (query.account_ref!=self._account or query.status!='complete' or query.missing_scope or
            query.covered_scope!=old.covered_scope or query.requested_scope!=query.covered_scope or
            query.as_of<old.as_of or query.as_of>at or query.cutoff_sequence<old.cutoff_sequence or
            query.cutoff_sequence>self._broker._sequence):
            raise d.ExecutionDenied('source_unresolved')
        local = {d.ref('event',e.event_id,e) for e in s['events'].values()}
        if set(query.events)!=local or any(e.effective_at>query.as_of for e in s['events'].values()):
            raise d.ExecutionDenied('reconciliation_required')
        if any(i.accounting!='complete' for i in s['intents'].values()):
            raise d.ExecutionDenied('reconciliation_required')
        reflected = self._validate_inclusions(s,query)
        projection = self._projection(at,as_of=query.as_of)
        seed=self._inputs
        if execution_policy is not None:
            self._auth(s,handle,'policy',at,protective=True)
            execution_policy=d.checked(execution_policy)
            if (type(execution_policy) is not d.SyntheticExecutionPolicy or
                execution_policy.account_ref!=self._account or
                execution_policy.version!=self._inputs.policy.version+1 or
                execution_policy.target_policy_ref!=target_ref('policy',self._source.inputs.policy.policy_id,self._source.inputs.policy)):
                raise a.ApprovalDenied('policy_changed')
            seed=replace(seed,current=self._source.inputs,policy=execution_policy)
        elif self._source.inputs.policy!=self._inputs.current.policy:
            raise a.ApprovalDenied('policy_changed')
        inputs = build_current_inputs(seed,query,self._broker,projection,self._ledger_events(at),
            at=at,market_inputs=market_inputs)
        self._inputs = inputs
        s['current_policy_ref']=d.ref('policy',inputs.policy.policy_id,inputs.policy)
        s['target_policy_ref']=inputs.policy.target_policy_ref
        window=self._account_validation(s,at)
        s['reservations'] = {key:replace(r,source_cutoff=query.as_of,
            broker_reflected=finite(reflected.get(r.reservation_id,number('0'))))
            for key,r in s['reservations'].items()}
        self._remember(s,'query',query.query_id,query)
        s['current_binding'] = {'query':d.ref('query',query.query_id,query),'ledger_cursor':projection.ledger_cursor,
            'facts':target_ref('facts',inputs.current.facts.source_snapshot_id,inputs.current.facts),
            'version':s['version']+1,'identity':self._current_identity(),
            'validator_version':'q27-account-current-v1','valid_from':window[0],'valid_to':window[1]}
        # Validate the exact same source and current rights again immediately before save.
        s['reconciliation']=None
        self._refresh_check = (handle,'policy' if execution_policy is not None else 'runtime')
        self._commit(s)
        return inputs

    def _risk(self,s,approval,at,*,exclude=None):
        try:
            projection = self._projection(at)
            if self._ledger_events(at)!=self._inputs.current.events:
                raise d.ExecutionDenied('source_unresolved')
            self._validate_inclusions(s,self._inputs.query)
            # Q20 replay metadata as_of/cutoff is request-specific. The actual ledger prefix
            # must equal the independently supplied typed snapshot, not just its cursor.
            expected = self._inputs.current.current.snapshot.valuation.projection
            if (projection.ledger_cursor,projection.cash_balances,projection.holdings,projection.complete,
                projection.reason_codes) != (expected.ledger_cursor,expected.cash_balances,expected.holdings,
                expected.complete,expected.reason_codes):
                raise d.ExecutionDenied('source_unresolved')
            source,risk = current_risk(self._source,self._inputs,self._broker,approval,at=at,
                generation=s['generation'],fence=s['fence'],account_version=s['version'],projection=expected,
                intents=tuple(s['intents'].values()),reservations=tuple(s['reservations'].values()),exclude_intent=exclude)
            self._remember(s,'source',source.source_id,source)
            return self._remember(s,'risk',risk.risk_id,risk)
        except Exception as failure:
            if isinstance(failure,a.ApprovalDenied): raise
            raise a.ApprovalDenied('risk_blocked') from None

    def _admit(self,s,approval,at,event):
        key = ('synthetic',self._account,approval.candidate_ref.id,approval.candidate_ref.version)
        if key in s['claims']: raise a.ApprovalDenied('candidate_already_consumed')
        # All fixed issuer facts are checked before consumed/claim/intent mutation.
        try: admit_manifest(self._broker._facts)
        except d.ExecutionDenied: raise a.ApprovalDenied('capacity_exceeded') from None
        # Original approver's CURRENT registry+DB session/permission, separate from presenter evidence.
        handle = next((h for h,sid in s['handles'].items() if sid==approval.session_id),None)
        self._auth(s,handle,'approve',at)
        risk_ref = self._risk(s,approval,at)
        if sum(i.state not in d.TERMINAL for i in s['intents'].values())>=2:
            raise a.ApprovalDenied('capacity_exceeded')
        iid = 'execution-intent:'+uuid4().hex
        consumed = self._change(s,approval,'consumed',at,event,intent=iid)
        self._stage('consumed')
        s['claims'][key] = iid
        self._stage('claim')
        intent = d.OrderIntent(iid,self._account,'synthetic',approval.candidate_ref,consumed,approval.terms,
            hash_record(approval.terms),risk_ref,s['generation'],s['fence'],'prepared',1,None,'0','0',None,None,'complete')
        s['intents'][iid] = intent
        self._remember(s,'intent',iid,intent)
        self._stage('intent')
        terms = approval.terms
        for component,dimension,amount,unit in (
            ('principal','cash',terms.principal_bound,terms.currency),
            ('cost','cash',terms.cost_bound,terms.currency),
            ('quantity','quantity',terms.quantity if terms.side=='sell' else '0',terms.position.unit),
            ('risk','risk',finite(number(terms.quantity)*number(terms.limit_price)+number(terms.cost_bound)),terms.currency)):
            rid = 'reservation:'+uuid4().hex
            s['reservations'][rid] = d.ReservationSlice(rid,iid,'obligation:'+intent.request_hash+':'+component,component,dimension,unit,
                self._inputs.current.policy.daily_window_start,self._inputs.current.policy.daily_window_end,
                amount,amount,'0','0','0','0',self._inputs.query.as_of,())
        self._stage('reservation')
        s['outbox'][iid] = 'pending'
        self._stage('outbox')
        self._final_authorities.append((handle,handle,'admit',approval,risk_ref,iid))
        return consumed

    def _intent_change(self,s,intent,**changes):
        new = replace(intent,state_version=intent.state_version+1,previous_ref=d.ref('intent',intent.intent_id,intent),**changes)
        s['intents'][intent.intent_id] = new
        s['outbox'][intent.intent_id] = new.state
        self._remember(s,'intent',new.intent_id,new)
        return new

    def _release(self,s,intent):
        for key,r in tuple(s['reservations'].items()):
            if r.intent_id==intent.intent_id:
                s['reservations'][key] = replace(r,held='0',released=finite(number(r.released)+number(r.held)))

    def _release_remaining(self,s,intent,quantity):
        # Finality covers only the confirmed unfilled units. Order-level cost and
        # price-improvement cushions stay protected until their own financial facts.
        releases={}
        for key,r in s['reservations'].items():
            if r.intent_id!=intent.intent_id: continue
            amount=(quantity if r.component=='quantity' and intent.terms.side=='sell' else
                quantity*number(intent.terms.limit_price) if r.component=='risk' or
                (r.component=='principal' and intent.terms.side=='buy') else number('0'))
            if amount>number(r.held): raise d.ExecutionDenied('event_conflict')
            releases[key]=replace(r,held=finite(number(r.held)-amount),released=finite(number(r.released)+amount))
        s['reservations'].update(releases)

    def _withdraw(self,s,approval,principal,session,at,event):
        if approval.state=='approved': return self._change(s,approval,'revoked',at,event)
        if approval.state!='consumed': raise a.ApprovalDenied('terminal_state')
        iid = approval.consumed_intent_id
        if s['withdrawals'].get(iid,0)>=2: raise a.ApprovalDenied('capacity_exceeded')
        intent = s['intents'][iid]
        state = 'requested'
        if intent.state=='prepared' and intent.attempt_ref is None:
            attempt = d.DispatchAttempt('unsent-attempt:'+uuid4().hex,iid,'submit',intent.request_hash,
                s['generation'],s['fence'],self._broker._instance,'armed',at,None)
            receipt = self._broker.prove_unsent(attempt,intent)
            self._remember(s,'receipt',receipt.receipt_id,receipt)
            self._intent_change(s,intent,state='aborted_unsent')
            self._release(s,intent)
            state = 'unsent_confirmed'
        wr = a.WithdrawalRequest('withdrawal:'+uuid4().hex,session.principal_ref,session.session_id,
            s['generation'],a.ref('approval',approval.approval_id,approval),iid,at,state,1,None,event,None)
        s['withdrawals'][iid] = s['withdrawals'].get(iid,0)+1
        return self._put(s,'withdrawal',wr)

    def _dispatch(self,*args,**kwargs):
        # Q26 challenge('dispatch') is not an alternate Q27 handoff path.
        raise a.ApprovalDenied('authority_denied')

    @_db_command
    def _arm(self,handle,intent_id):
        at,s = self._now(),self._copy()
        self._auth(s,handle,'dispatch',at)
        intent = s['intents'].get(intent_id)
        if intent is None or intent.state!='prepared' or intent.attempt_ref is not None:
            raise a.ApprovalDenied('terminal_state')
        if s['mode']!='running' or s['restored'] or (intent.generation,intent.fence)!=(s['generation'],s['fence']):
            raise a.ApprovalDenied('generation_mismatch')
        approval = self._get(s,intent.approval_ref)
        self._revalidate(s,approval,at)
        original = next((h for h,sid in s['handles'].items() if sid==approval.session_id),None)
        self._auth(s,original,'approve',at)
        risk_ref = self._risk(s,approval,at,exclude=intent_id)
        attempt = d.DispatchAttempt('attempt:'+uuid4().hex,intent_id,'submit',intent.request_hash,
            s['generation'],s['fence'],self._broker._instance,'armed',at,None)
        ar = self._remember(s,'attempt',attempt.attempt_id,attempt)
        s['attempts'][attempt.attempt_id] = attempt
        intent = self._intent_change(s,intent,state='dispatching',attempt_ref=ar)
        self._final_authorities.append((original,handle,'dispatch',approval,risk_ref,intent_id))
        self._commit(s)
        return attempt,intent,s['execution_records'][risk_ref].valid_to

    def dispatch(self,handle,intent_id):
        identifier(intent_id)
        # Same issuer/account gate is held continuously from final DB auth to handoff.
        with self._lock:
            attempt,intent,deadline = self._arm(handle,intent_id)
            self._stage('before_handoff')
            if utc_instant(self._authority._clock())>=deadline:
                raise a.ApprovalDenied('expired')
            attempt,intent,window = self._handoff_ready(handle,attempt.attempt_id)
            self._check_handoff_time(window,attempt,intent)
            receipt = self._broker.handoff(attempt,intent)
            self._stage('after_handoff')
            # Persistence failure leaves a durable armed attempt. No resend API exists.
            return self._store_receipt(attempt,receipt)

    @_db_command
    def _handoff_ready(self,handle,attempt_id,command_id=None):
        s,at=self._copy(),self._now()
        attempt=s['attempts'][attempt_id]
        intent=s['intents'][attempt.intent_id]
        if attempt.state!='armed' or (attempt.generation,attempt.fence)!=(s['generation'],s['fence']):
            raise a.ApprovalDenied('generation_mismatch')
        if command_id is not None:
            command=s['cancel_commands'][command_id]
            self._check_cancel(s,handle,command,at)
            principal,session=self._auth(s,handle,'runtime',at,protective=True)
            # Cancellation has its own protective authority, independent of
            # expired submission approval/market data. Preserve that contract.
            deadlines=(principal.expires_at,session.expires_at,session.liveness_deadline,command.expires_at)
        else:
            actor,session=self._auth(s,handle,'dispatch',at)
            approval=self._get(s,intent.approval_ref)
            original=next((h for h,sid in s['handles'].items() if sid==approval.session_id),None)
            approver,approval_session=self._auth(s,original,'approve',at)
            if s['mode']!='running' or s['withdrawals'].get(intent.intent_id) or intent.state!='dispatching':
                raise a.ApprovalDenied('terminal_state')
            self._revalidate(s,approval,at)
            risk_ref=self._risk(s,approval,at,exclude=intent.intent_id)
            risk=s['execution_records'][risk_ref]
            # current_risk binds original source rights and the entire current
            # account/price/FX/mapping/rights dependency window in valid_to.
            # Add every separately checked authority/policy/order time bound.
            deadlines=(actor.expires_at,session.expires_at,session.liveness_deadline,
                approver.expires_at,approval_session.expires_at,approval_session.liveness_deadline,
                self._policy(s).valid_to,approval.expires_at,self._source.request.expires_at,
                risk.valid_to,self._inputs.policy.valid_to,self._inputs.current.policy.daily_window_end,
                approval.terms.valid_to,approval.terms.cost_rule.valid_to,approval.terms.capability.valid_to)
        return attempt,intent,_HandoffWindow(attempt,intent,at,deadlines)

    def _check_handoff_time(self,window,attempt,intent):
        """After transaction commit AND close, immediately before broker egress.

        The caller still owns the shared issuer/account gate, so all non-time
        checks remain valid. No DB I/O or caller bool/callback can extend the
        immutable deadlines obtained by the final full validation above.
        """
        if (type(window) is not _HandoffWindow or window.attempt!=attempt or window.intent!=intent or
            not window.deadlines):
            raise a.ApprovalDenied('authority_denied')
        try:
            now=utc_instant(self._authority._clock())
            if now<window.checked_at or (self._authority._last_observed is not None and now<self._authority._last_observed):
                raise ValueError()
        except Exception:
            raise a.ApprovalDenied('clock_invalid') from None
        self._authority._last_observed=now
        if now>=min(window.deadlines):
            raise a.ApprovalDenied('expired')

    @_db_command
    def _store_receipt(self,attempt,receipt):
        s = self._copy()
        intent = s['intents'][attempt.intent_id]
        if s['attempts'].get(attempt.attempt_id) not in (attempt,replace(attempt,state='unknown')):
            raise d.ExecutionDenied('event_conflict')
        if receipt is None:
            new = self._intent_change(s,intent,state='unknown') if intent.state in ('dispatching','unknown') else intent
            stored_attempt = replace(attempt,state='unknown')
        else:
            self._broker.verify(receipt,'receipt',receipt.receipt_id)
            if (receipt.attempt_id,receipt.request_hash,receipt.intent_id)!=(attempt.attempt_id,intent.request_hash,intent.intent_id):
                raise d.ExecutionDenied('source_unresolved')
            rr = self._remember(s,'receipt',receipt.receipt_id,receipt)
            stored_attempt = replace(attempt,state='result_stored',receipt_ref=rr)
            if receipt.kind=='proven_unsent':
                if (attempt.attempt_id not in self._broker._revoked or attempt.attempt_id in self._broker._requests or
                    intent.state not in ('dispatching','unknown') or intent.confirmed_quantity!='0' or intent.observed_quantity!='0'):
                    raise d.ExecutionDenied('event_conflict')
                stored_attempt=replace(attempt,state='proven_unsent',receipt_ref=rr)
                new=self._intent_change(s,intent,state='aborted_unsent')
                self._release(s,new)
            elif receipt.kind=='final_reject':
                new = self._intent_change(s,intent,state='rejected')
                self._release(s,new)
            else:
                new = self._intent_change(s,intent,state='acknowledged' if intent.state in ('dispatching','unknown') else intent.state,
                    broker_order_id=receipt.broker_order_id)
        s['attempts'][attempt.attempt_id] = stored_attempt
        if (attempt.generation,attempt.fence)!=(s['generation'],s['fence']):
            s['mode']='stopped'
            s['reconciliation']=None
        self._commit(s)
        return receipt

    @_db_command
    def resolve_unsent(self,handle,intent_id):
        """명시 수동 복구: 실제 동일 issuer가 handoff를 폐기한 증거만 사용한다."""
        s,at=self._state,self._now()
        _,session=self._auth(s,handle,'runtime',at,protective=True)
        intent=s['intents'].get(intent_id)
        if s['mode'] not in ('stopped','reconciling') or intent is None or intent.state not in ('dispatching','unknown') or intent.attempt_ref is None:
            raise a.ApprovalDenied('terminal_state')
        attempt=s['attempts'][intent.attempt_ref.id]
        if attempt.action!='submit' or attempt.egress_instance!=self._broker._instance:
            raise d.ExecutionDenied('source_unresolved')
        # This is an actual broker journal operation under the same gate. A mere
        # absent DB receipt, before_handoff fault, new day or generation is no proof.
        receipt=self._broker.prove_unsent(attempt,intent)
        self._store_receipt(attempt,receipt)
        s=self._copy()
        self._event(s,'explicit_synthetic_unsent_resolution',intent_id,at)
        self._commit(s,owner=session.session_id)
        return receipt

    @_db_command
    def recover(self):
        s = self._copy()
        for intent in tuple(s['intents'].values()):
            if intent.state=='dispatching':
                self._intent_change(s,intent,state='unknown')
        for cid,c in tuple(s['cancel_commands'].items()):
            if c.state=='armed':
                s['cancel_commands'][cid]=replace(c,state='unknown',state_version=c.state_version+1)
                self._remember(s,'cancel',cid,s['cancel_commands'][cid])
        s['mode'] = 'stopped'
        self._commit(s)

    @_db_command
    def control(self,handle,action):
        if action!='resume': return super().control(handle,action)
        s,at=self._copy(),self._now()
        _,session=self._auth(s,handle,'resume',at)
        rec=s['reconciliation']
        if (rec is None or rec.result!='matched' or rec.generation!=s['generation'] or
            rec.fence!=s['fence'] or rec.account_version!=s['version'] or
            rec.ledger_cursor!=self._projection(at).ledger_cursor or rec.session_id!=session.session_id or
            rec.source_hash!=self._source_hash() or rec.current_identity!=self._current_identity() or
            rec.validator_version!='q27-account-current-v1' or rec.valid_from is None or rec.valid_to is None or
            not rec.valid_from<=at<rec.valid_to or s['restored']):
            raise a.ApprovalDenied('reconciliation_required')
        self._validation_query=self._broker.resolve(rec.query_ref)
        self._validate_recovery(s, self._validation_query, at)
        self._refresh_check=(handle,'resume')
        self._session_room(s,session,1)
        s['mode']='running'
        event=self._event(s,'explicit_synthetic_resume',session.session_id,at)
        self._commit(s,owner=session.session_id)
        return event

    @_db_command
    def head(self,handle,approval_id):
        at,s = self._now(),self._state
        self._auth(s,handle,'present',at)
        r = s['heads'].get(('approval',approval_id))
        if r is None: raise a.ApprovalDenied('source_unresolved')
        approval = self._get(s,r)
        self._source_check(s,approval.candidate_ref,at,require_live=False)
        return approval

    @_db_command
    def intent(self,handle,intent_id):
        self._auth(self._state,handle,'runtime',self._now(),protective=True)
        result = self._state['intents'].get(intent_id)
        if result is None: raise d.ExecutionDenied('source_unresolved')
        return result

    @_db_command
    def fingerprint(self):
        return sha256(json.dumps(self._uow.call('execution_fingerprint',self._account),sort_keys=True,separators=(',',':')).encode()).hexdigest()

    @_db_command
    def reconcile(self,handle,query):
        s,at = self._copy(),self._now()
        _,session=self._auth(s,handle,'runtime',at,protective=True)
        query = d.checked(query)
        self._broker.verify(query,'query',query.query_id)
        projection = self._projection(at,as_of=query.as_of)
        statement = self._broker.statement(query)
        expected = self._inputs.current.current.snapshot
        request = replace(expected.valuation.request,evaluated_at=at,as_of=projection.as_of,
            knowledge_cutoff=projection.knowledge_cutoff,ledger_cursor=projection.ledger_cursor)
        compared = reconcile_values(projection,statement,request,expected.reconciliation_policy)
        unresolved = []
        window=None
        self._validation_query=query
        try:
            window=self._validate_recovery(s,query,at)
        except (d.ExecutionDenied,a.ApprovalDenied):
            unresolved.append('recovery_readset_unresolved')
        if (query.account_ref!=self._account or query.status!='complete' or query.missing_scope or
            query.covered_scope!=self._inputs.current.facts.covered_scope or not compared.full_account_balances_matched):
            unresolved.append('source_incomplete')
        local_receipts = {r for r in s['execution_records'] if r.kind=='receipt'}
        if any(r not in local_receipts for r in query.receipts) or any(r not in query.receipts for r in local_receipts
            if s['execution_records'][r].kind in ('accepted','final_reject','cancel_ack')):
            unresolved.append('unprocessed_receipt')
        local_events = {d.ref('event',event.event_id,event) for event in s['events'].values()}
        if any(r not in local_events for r in query.events) or any(r not in query.events for r in local_events):
            unresolved.append('unprocessed_event')
        if any(event.effective_at>query.as_of for event in s['events'].values()):
            unresolved.append('stale_query_cutoff')
        if any(i.state in ('unknown','dispatching') or i.accounting=='incomplete' for i in s['intents'].values()):
            unresolved.append('unknown_intent')
        prior=s.get('reconciliation')
        if (prior is not None and prior.query_ref==d.ref('query',query.query_id,query) and
            prior.ledger_cursor==projection.ledger_cursor and prior.generation==s['generation'] and
            prior.fence==s['fence'] and prior.session_id==session.session_id and
            prior.source_hash==self._source_hash() and prior.current_identity==self._current_identity() and
            prior.validator_version=='q27-account-current-v1' and prior.valid_to is not None and at<prior.valid_to and prior.unresolved==tuple(unresolved) and
            prior.account_version==s['version']):
            return prior
        rec = d.ExecutionReconciliation('reconcile:'+uuid4().hex,self._account,d.ref('query',query.query_id,query),
            projection.ledger_cursor,s['version']+1,s['generation'],s['fence'],at,
            'unresolved' if unresolved else 'matched',tuple(unresolved),session.session_id,self._source_hash(),
            self._current_identity(),'q27-account-current-v1',None if window is None else window[0],None if window is None else window[1])
        self._remember(s,'reconciliation',rec.reconciliation_id,rec)
        s['reconciliation'] = rec
        if window is not None and self._refresh_check is None: self._refresh_check=(handle,'runtime')
        self._commit(s)
        return rec

    def _validate_recovery(self,s,query,at):
        self._broker.verify(query,'query',query.query_id)
        if (query.status!='complete' or query.missing_scope or query.account_ref!=self._account or
            query.covered_scope!=query.requested_scope or query.covered_scope!=self._inputs.query.covered_scope or
            query.as_of>at or query.as_of<self._inputs.query.as_of or query.journal_sequence!=self._broker._sequence):
            raise d.ExecutionDenied('reconciliation_required')
        # A new query may describe different capacity/qty even without new fills.
        # Reconcile cannot silently replace the current typed source binding.
        bound=self._inputs.query
        if any(getattr(query,key)!=getattr(bound,key) for key in
            ('cash','sellable','statement_ref','as_of','cutoff_sequence','receipts','events','journal_sequence','request_attempts')):
            raise d.ExecutionDenied('reconciliation_required')
        manifest=self._broker.manifest(query)
        for attempt,remote in manifest:
            local=s['intents'].get(attempt.intent_id)
            recorded=s['attempts'].get(attempt.attempt_id)
            if (local is None or recorded is None or local.request_hash!=remote.request_hash or
                recorded.request_hash!=attempt.request_hash or recorded.action!=attempt.action):
                raise d.ExecutionDenied('reconciliation_required')
        for intent in s['intents'].values():
            components=[r for r in s['reservations'].values() if r.intent_id==intent.intent_id]
            if len(components)!=4 or {r.component for r in components}!={'principal','cost','quantity','risk'}:
                raise d.ExecutionDenied('reconciliation_required')
            claim=('synthetic',self._account,intent.candidate_ref.id,intent.candidate_ref.version)
            approval=self._get(s,intent.approval_ref)
            if (s['claims'].get(claim)!=intent.intent_id or approval.state!='consumed' or
                approval.consumed_intent_id!=intent.intent_id):
                raise d.ExecutionDenied('reconciliation_required')
            if intent.state!='aborted_unsent' and (intent.attempt_ref is None or intent.attempt_ref.id not in s['attempts']):
                raise d.ExecutionDenied('reconciliation_required')
        for attempt in s['attempts'].values():
            if attempt.state!='proven_unsent' and not any(a.attempt_id==attempt.attempt_id for a,_ in manifest):
                raise d.ExecutionDenied('reconciliation_required')
        if (s.get('unknown_costs') or s.get('financial_excess') or
            any(i.state in ('prepared','dispatching','unknown') or i.accounting!='complete' for i in s['intents'].values()) or
            any(c.state in ('armed','unknown') for c in s['cancel_commands'].values()) or
            any(v not in ('applied','resolved') for v in s.get('event_dispositions',{}).values())):
            raise d.ExecutionDenied('reconciliation_required')
        # Full Q20 history, Q21 independent balances and Q23 corrected performance/current rights.
        projection=self._projection(at,as_of=query.as_of)
        inputs=build_current_inputs(self._inputs,query,self._broker,projection,self._ledger_events(at),at=at)
        window=self._account_validation(s,at)
        expected=self._inputs.current.current.snapshot.valuation.projection
        if (projection.ledger_cursor,projection.cash_balances,projection.holdings,projection.complete,projection.reason_codes)!=(expected.ledger_cursor,expected.cash_balances,expected.holdings,expected.complete,expected.reason_codes):
            raise d.ExecutionDenied('reconciliation_required')
        self._validate_inclusions(s,query)
        local={d.ref('event',e.event_id,e) for e in s['events'].values()}
        receipts={r for r in s['execution_records'] if r.kind=='receipt'}
        if set(query.events)!=local or set(query.receipts)!=receipts:
            raise d.ExecutionDenied('reconciliation_required')
        return window

    @_db_command
    def consume_ledger(self,message_id,payload_hash):
        return self._uow.call('execution_consume',self._account,message_id,payload_hash)

    @contextmanager
    def inject_failure(self,label):
        if label not in ('consumed','claim','intent','reservation','outbox','history','receipt','commit',
                         'before_handoff','after_handoff','before_cancel_handoff','after_cancel_handoff','inbox','ledger','fill_trade','fill_fee','fill_tax','fill_reservation','fill_intent','fill_history'):
            raise d.ExecutionDenied()
        with self._lock:
            old,self._failure = self._failure,label
            try: yield
            finally: self._failure = old

    def _append_fill(self,event,intent,quantity,*,prior=None):
        """Q20 ledger_append SQL 참여. Python PostgresLedger.append를 호출하지 않는다."""
        terms = intent.terms
        if prior is not None:
            revision,correction,predecessor = prior['ledger_revision']+1,prior['ledger_event'],prior['ledger_revision']
        else:
            revision,correction,predecessor = 1,None,None
        source_key = 'execution:'+sha256((intent.intent_id+':'+event.execution_id+
            (':'+str(event.stream_sequence) if event.semantics=='cumulative' else '')).encode()).hexdigest()
        principal = number(quantity)*number(event.price)
        buying = terms.side=='buy'
        account_name = 'unsettled_payable' if buying else 'unsettled_receivable'
        amount = -principal if buying else principal
        submission = SyntheticLedgerSubmission(1,'synthetic',self._account,'synthetic-execution',source_key,
            revision,predecessor,terms.position.mapping_version,'trade',event.effective_at,
            'retroactive' if prior else 'original',correction,
            (CashLeg(account_name,terms.currency,finite(amount),'trade'),
             CashLeg('trade_clearing',terms.currency,finite(-amount),'trade')),
            (PositionDelta(*terms.position.key,finite(number(quantity) if buying else -number(quantity))),),
            (event.journal_id,),LedgerCompleteness(True,event.fee is not None and event.tax is not None,True),None,(),None)
        wire = json.loads(canonical_bytes(CanonicalPayload('SyntheticLedgerSubmission',1,'synthetic',submission)))['payload']
        result = self._uow.call('execution_ledger',self._account,'append',wire,self._now())
        return result,submission

    def _quarantine_event(self,s,event,reason):
        key = (event.event_id,event.revision,hash_record(event))
        if s.get('event_dispositions',{}).get(key)==reason and s['events'].get(key)==event:
            return 'quarantined'
        s['events'][key] = event
        s.setdefault('event_dispositions',{})[key] = reason
        self._remember(s,'event','quarantined:'+hash_record(event),event)
        self._uow.call('execution_event',self._account,{'body':asdict(event),'hash':hash_record(event),'disposition':reason})
        intent = s['intents'].get(event.intent_id)
        if intent is not None:
            self._intent_change(s,intent,accounting='incomplete',observed_quantity=finite(max(
                number(intent.observed_quantity),number(event.quantity) if event.kind=='fill' else 0)))
        s['mode'] = 'faulted'
        self._commit(s)
        return 'quarantined'

    @_db_command
    def receive(self,event):
        return self._receive(event)

    @_db_command
    def reprocess(self,event):
        key = (event.event_id,event.revision,hash_record(event))
        if self._state.get('event_dispositions',{}).get(key) != 'predecessor_missing':
            raise d.ExecutionDenied('event_conflict')
        return self._receive(event,reprocess=True)

    def _receive(self,event,*,reprocess=False):
        event = d.checked(event)
        exact(event,d.SyntheticOrderEvent)
        self._broker.verify(event,'event',event.event_id)
        if type(self._uow) is _TrustedUnitOfWork: self._uow.fact(event)
        receipt = self._broker.resolve(event.receipt_ref)
        self._broker.verify(receipt,'receipt',receipt.receipt_id)
        s,at = self._copy(),self._now()
        intent = s['intents'].get(event.intent_id)
        if (intent is None or event.account_ref!=self._account or
            (event.request_hash,event.broker_order_id)!=(intent.request_hash,receipt.broker_order_id) or
            receipt.intent_id!=intent.intent_id or
            receipt.kind!=('cancel_ack' if event.kind=='cancelled_remaining' else 'accepted') or
            receipt.attempt_id not in s['attempts']):
            raise d.ExecutionDenied('source_unresolved')
        key = (event.event_id,event.revision,hash_record(event))
        if key in s['events'] and not reprocess:
            return 'duplicate'
        if any(k[:2]==key[:2] and k!=key for k in s['events']):
            return self._quarantine_event(s,event,'payload_collision')
        if intent.broker_order_id is not None and intent.broker_order_id!=event.broker_order_id:
            return self._quarantine_event(s,event,'broker_id_conflict')
        if event.effective_at>at:
            return self._quarantine_event(s,event,'future_event')
        if event.kind in ('cancelled_remaining','expired_remaining'):
            remaining=number(intent.terms.quantity)-number(intent.confirmed_quantity)
            command=None
            if event.kind=='cancelled_remaining':
                command=next((c for c in s['cancel_commands'].values() if c.attempt_ref and
                    c.attempt_ref.id==receipt.attempt_id and c.broker_order_id==event.broker_order_id),None)
                remote=self._broker._requests.get(receipt.attempt_id)
                if command is None or remote is None or remote[0].action!='cancel':
                    return self._quarantine_event(s,event,'cancel_confirmation_authority_missing')
                if number(event.quantity)>number(command.maximum_remaining):
                    return self._quarantine_event(s,event,'cancel_quantity_conflict')
            if number(event.quantity)!=remaining or intent.state in d.TERMINAL:
                return self._quarantine_event(s,event,'terminal_conflict')
            try: self._release_remaining(s,intent,remaining)
            except d.ExecutionDenied: return self._quarantine_event(s,event,'cancel_reservation_conflict')
            s['events'][key]=event
            self._remember(s,'event',event.event_id,event)
            self._uow.call('execution_event',self._account,{'body':asdict(event),'hash':hash_record(event),'disposition':'applied'})
            self._intent_change(s,intent,state=event.kind)
            if command:
                s['cancel_commands'][command.command_id]=replace(command,state='confirmed',state_version=command.state_version+1)
                self._remember(s,'cancel',command.command_id,s['cancel_commands'][command.command_id])
            self._commit(s)
            return 'applied'
        if event.kind=='settlement':
            return self._settle_event(s,event,intent,key,at)
        if event.kind!='fill':
            return self._quarantine_event(s,event,'unsupported_event')
        if intent.state in d.TERMINAL and not (intent.state=='filled' and
            any(k[0]==intent.intent_id and k[1]==event.execution_id and event.revision>v['revision']
                for k,v in s.get('event_heads',{}).items())):
            return self._quarantine_event(s,event,'late_final_conflict')
        heads = s.setdefault('event_heads',{})
        accepted = [v for k,v in heads.items() if k[0]==intent.intent_id]
        if any(v['semantics']!=event.semantics for v in accepted):
            return self._quarantine_event(s,event,'mixed_semantics')
        stream_key = (intent.intent_id,event.execution_id,event.stream_sequence if event.semantics=='cumulative' else 0)
        prior = heads.get(stream_key)
        if event.semantics=='cumulative' and any(v['execution_id']!=event.execution_id for v in accepted):
            return self._quarantine_event(s,event,'mixed_stream')
        if prior and event.revision<=prior['revision']:
            return self._quarantine_event(s,event,'old_revision')
        expected = 1 if prior is None else prior['revision']+1
        if event.revision!=expected or event.predecessor_revision!=(None if prior is None else prior['revision']):
            return self._quarantine_event(s,event,'predecessor_missing')
        previous = None
        if event.semantics=='cumulative':
            previous = heads.get((intent.intent_id,event.execution_id,event.stream_sequence-1))
            if event.stream_sequence>1 and previous is None:
                return self._quarantine_event(s,event,'predecessor_missing')
            if any(v['stream_sequence']>event.stream_sequence for v in accepted):
                # Successor economics cannot be silently reinterpreted by a correction.
                return self._quarantine_event(s,event,'cumulative_successor_dependency')
        quantity = number(event.quantity)-(number(previous['issuer_quantity']) if previous else 0)
        total = sum((number(v['quantity']) for v in accepted),number('0')) + quantity-(number(prior['quantity']) if prior else 0)
        if quantity<=0 or total>number(intent.terms.quantity) or total<0:
            return self._quarantine_event(s,event,'overfill')
        if (number(event.price)>number(intent.terms.limit_price) and intent.terms.side=='buy' or
            number(event.price)<number(intent.terms.limit_price) and intent.terms.side=='sell'):
            return self._quarantine_event(s,event,'limit_violation')
        known = event.fee is not None and event.tax is not None
        fee = None if event.fee is None else number(event.fee)-(number(previous['issuer_fee']) if previous and previous['issuer_fee'] is not None else 0)
        tax = None if event.tax is None else number(event.tax)-(number(previous['issuer_tax']) if previous and previous['issuer_tax'] is not None else 0)
        if (fee is not None and fee<0) or (tax is not None and tax<0) or previous and not previous['known']:
            return self._quarantine_event(s,event,'cost_predecessor_unknown')
        head = {'quantity':finite(quantity),'issuer_quantity':event.quantity,'revision':event.revision,
            'stream_sequence':event.stream_sequence,'semantics':event.semantics,'execution_id':event.execution_id,
            'price':event.price,'principal':finite(quantity*number(event.price)),
            'issuer_fee':event.fee,'issuer_tax':event.tax,'fee':None if fee is None else finite(fee),
            'tax':None if tax is None else finite(tax),'known':known,'ledger_event':None,
            'ledger_revision':0,'charges':{},'settled':prior['settled'] if prior else '0','event':event}
        s['events'][key] = event
        s.setdefault('event_dispositions',{})[key] = 'applied' if known else 'observed_incomplete'
        self._remember(s,'event',event.event_id,event)
        self._uow.call('execution_event',self._account,{'body':asdict(event),'hash':hash_record(event),'disposition':'applied' if known else 'observed_incomplete'})
        self._stage('inbox')
        if not known:
            # No Q20 event with invented confirmed-zero costs. Keep the execution head
            # so its later complete revision replaces the same observed identity.
            if prior and prior['ledger_event']:
                return self._quarantine_event(s,event,'known_cost_revision_incomplete')
            heads[stream_key] = head
            s['unknown_costs'][stream_key] = event
            self._apply_usage(s,intent,ledger_refs=())
            self._intent_change(s,intent,observed_quantity=finite(total),broker_order_id=event.broker_order_id,
                accounting='incomplete',state='unknown')
            s['mode'] = 'faulted'
            self._commit(s)
            return 'observed_incomplete'
        ledger_prior = prior if prior and prior['ledger_event'] else None
        result,submission = self._append_fill(event,intent,finite(quantity),prior=ledger_prior)
        if result['status'] not in ('accepted','duplicate') or not result['event_ids']:
            return self._quarantine_event(s,event,'ledger_correction_unsupported')
        self._stage('fill_trade')
        head['ledger_event'] = result['event_ids'][-1]
        head['ledger_revision'] = submission.source_revision
        refs = list(result['event_ids'])
        # Expense components use Q20 fee/tax semantics, each with its own revision
        # identity and dependency on this exact trade replacement.
        for kind in ('fee','tax'):
            amount = number(head[kind])
            old = None if not ledger_prior else ledger_prior['charges'].get(kind)
            if amount==0:
                if old:
                    return self._quarantine_event(s,event,'zero_cost_correction_unsupported')
                continue
            charge,result = self._append_charge(event,intent,head,kind,amount,old)
            if result['status'] not in ('accepted','duplicate') or not result['event_ids']:
                return self._quarantine_event(s,event,'ledger_cost_correction_unsupported')
            head['charges'][kind] = {'event':result['event_ids'][-1],'revision':charge.source_revision}
            self._stage('fill_'+kind)
            refs.extend(result['event_ids'])
        self._stage('ledger')
        heads[stream_key] = head
        s['unknown_costs'].pop(stream_key,None)
        s['ledger_mapping'][(event.event_id,event.revision)] = head['ledger_event']
        projection = self._projection(at)
        if not projection.complete:
            # Q20 may accept a replacement while marking an already settled
            # dependency unresolved. Keep all rows and the former reservation.
            return self._quarantine_event(s,event,'ledger_dependency_unresolved')
        if not self._apply_usage(s,intent,ledger_refs=tuple(refs)):
            return self._quarantine_event(s,event,'approved_bound_exceeded')
        self._stage('fill_reservation')
        complete = all(v['known'] for k,v in heads.items() if k[0]==intent.intent_id) and not any(
            disposition not in ('applied','observed_incomplete','old_revision') and
            s['events'][event_key].intent_id==intent.intent_id
            for event_key,disposition in s.get('event_dispositions',{}).items())
        confirmed = sum((number(v['quantity']) for k,v in heads.items() if k[0]==intent.intent_id and v['ledger_event']),number('0'))
        self._intent_change(s,intent,confirmed_quantity=finite(confirmed),observed_quantity=finite(total),
            broker_order_id=event.broker_order_id,accounting='complete' if complete else 'incomplete',
            state='filled' if total==number(intent.terms.quantity) else 'partially_filled')
        self._stage('fill_intent')
        self._stage('fill_history')
        self._commit(s)
        return 'applied'

    def _append_charge(self,event,intent,head,kind,amount,prior):
        source = 'execution-cost:'+sha256((intent.intent_id+event.execution_id+':'+str(event.stream_sequence if event.semantics=='cumulative' else 0)+':'+kind).encode()).hexdigest()
        revision = 1 if prior is None else prior['revision']+1
        sub = SyntheticLedgerSubmission(1,'synthetic',self._account,'synthetic-execution',source,
            revision,None if prior is None else prior['revision'],intent.terms.position.mapping_version,
            kind,event.effective_at,'original' if prior is None else 'retroactive',None if prior is None else prior['event'],
            (CashLeg('settled_cash',intent.terms.currency,finite(-amount),'settlement'),
             CashLeg(kind+'_expense',intent.terms.currency,finite(amount),'settlement')),(),
            (event.journal_id,),LedgerCompleteness(True,True,True),None,(head['ledger_event'],),None)
        wire = json.loads(canonical_bytes(CanonicalPayload('SyntheticLedgerSubmission',1,'synthetic',sub)))['payload']
        return sub,self._uow.call('execution_ledger',self._account,'append',wire,self._now())

    def _apply_usage(self,s,intent,*,ledger_refs):
        heads = [v for k,v in s.get('event_heads',{}).items() if k[0]==intent.intent_id]
        quantity = sum((number(v['quantity']) for v in heads),number('0'))
        principal = sum((number(v['principal']) if v['known'] else number(v['quantity'])*number(intent.terms.limit_price) for v in heads),number('0'))
        # A known fee with unknown tax is an observed lower bound, not confirmed0.
        # Only actually posted complete costs are settled in Q20.
        cost = sum(((number(v['fee']) if v['fee'] is not None else 0)+
            (number(v['tax']) if v['tax'] is not None else 0) for v in heads),number('0'))
        posted_cost = sum((number(v['fee'])+number(v['tax']) for v in heads if v['known'] and v['ledger_event']),number('0'))
        pending = {}
        for key,r in s['reservations'].items():
            if r.intent_id!=intent.intent_id: continue
            used = {'principal':principal if intent.terms.side=='buy' else number('0'),
                    'quantity':quantity if intent.terms.side=='sell' else number('0'),
                    'cost':cost,'risk':principal+cost}[r.component]
            held = number(r.bound)-used-number(r.released)
            if held<0 or used<number(r.settled) or used<number(r.broker_reflected):
                s.setdefault('financial_excess',{})[intent.intent_id] = {'principal':finite(principal),'cost':finite(cost),'quantity':finite(quantity)}
                return False
            pending[key] = replace(r,held=finite(held),used=finite(used),
                settled=finite(posted_cost) if r.component=='cost' else r.settled,
                ledger_refs=tuple(dict.fromkeys((*r.ledger_refs,*ledger_refs))))
        s['reservations'].update(pending)
        return True

    def _settle_event(self,s,event,intent,key,at):
        matches = [(k,v) for k,v in s.get('event_heads',{}).items() if k[0]==intent.intent_id and
            k[1]==event.execution_id and (event.semantics!='cumulative' or k[2]==event.stream_sequence)]
        if len(matches)!=1:
            return self._quarantine_event(s,event,'settlement_dependency')
        head_key,prior = matches[0]
        if (not prior['known'] or not prior['ledger_event'] or number(event.quantity)!=number(prior['quantity']) or
            prior['settled']!='0' or event.price!=prior['price'] or event.fee is None or event.tax is None):
            return self._quarantine_event(s,event,'settlement_dependency')
        amount = number(prior['principal'])
        buying = intent.terms.side=='buy'
        sub = SyntheticLedgerSubmission(1,'synthetic',self._account,'synthetic-execution',
            'settlement:'+sha256((intent.intent_id+event.execution_id+str(head_key[2])).encode()).hexdigest(),1,None,
            intent.terms.position.mapping_version,'settlement',event.effective_at,'original',None,
            (CashLeg('settled_cash',intent.terms.currency,finite(-amount if buying else amount),'settlement'),
             CashLeg('unsettled_payable' if buying else 'unsettled_receivable',intent.terms.currency,finite(amount if buying else -amount),'settlement')),(),
            (event.journal_id,),LedgerCompleteness(True,True,True),None,(prior['ledger_event'],),None)
        wire = json.loads(canonical_bytes(CanonicalPayload('SyntheticLedgerSubmission',1,'synthetic',sub)))['payload']
        result = self._uow.call('execution_ledger',self._account,'append',wire,at)
        if result['status'] not in ('accepted','duplicate') or not result['event_ids']:
            return self._quarantine_event(s,event,'ledger_settlement_quarantined')
        s['event_heads'][head_key] = prior | {'settled':finite(amount)}
        if buying:
            for rid,r in tuple(s['reservations'].items()):
                if r.intent_id==intent.intent_id and r.component=='principal':
                    s['reservations'][rid] = replace(r,settled=finite(number(r.settled)+amount),ledger_refs=(*r.ledger_refs,*result['event_ids']))
        s['events'][key] = event
        self._remember(s,'event',event.event_id,event)
        self._uow.call('execution_event',self._account,{'body':asdict(event),'hash':hash_record(event),'disposition':'applied'})
        self._commit(s)
        return 'applied'

    @_db_command
    def cancel(self,handle,intent_id,*,command_id,expected_version):
        """별도 controller/runtime 권한과 DB nonce. Q26 approve는 취소 권한이 아니다."""
        identifier(command_id)
        integer(expected_version,1)
        s,at = self._copy(),self._now()
        principal,session = self._auth(s,handle,'runtime',at,protective=True)
        if principal.role!='controller' or 'cancel' not in s['execution_permissions'].get(principal.principal_id,()):
            raise a.ApprovalDenied('authority_denied')
        intent = s['intents'].get(intent_id)
        old = s['cancel_commands'].get(command_id)
        if old is not None:
            if (old.intent_ref.id,old.expected_version,old.session_id,old.generation)!=(intent_id,expected_version,session.session_id,s['generation']):
                raise a.ApprovalDenied('replay_conflict')
            return old
        if intent is None or intent.state in d.TERMINAL or intent.broker_order_id is None:
            raise a.ApprovalDenied('terminal_state')
        if any(c.intent_ref.id==intent_id and c.state in ('armed','unknown','acknowledged') for c in s['cancel_commands'].values()):
            raise a.ApprovalDenied('terminal_state')
        if intent.state_version!=expected_version: raise a.ApprovalDenied('version_conflict')
        if sum(c.intent_ref.id==intent_id for c in s['cancel_commands'].values())>=2:
            raise a.ApprovalDenied('capacity_exceeded')
        command = d.CancelCommand(command_id,'cancel-nonce:'+uuid4().hex,self._account,session.session_id,
            s['generation'],d.ref('intent',intent_id,intent),intent.broker_order_id,
            finite(number(intent.terms.quantity)-number(intent.confirmed_quantity)),expected_version,
            at,a.plus(at,10),'issued',None)
        s['cancel_commands'][command_id] = command
        s.setdefault('cancel_nonces',{})[command.nonce]=command_id
        self._cancel_check=(handle,command_id)
        self._remember(s,'cancel',command_id,command)
        self._commit(s)
        return command

    @_db_command
    def cancel_receipt(self,handle,command_id,*,intent_id,expected_version):
        """동일 조건의 명령 결과 조회. 새 handoff/권한 발급을 하지 않는다."""
        s,at=self._state,self._now()
        principal,session=self._auth(s,handle,'runtime',at,protective=True)
        if principal.role!='controller' or 'cancel' not in s['execution_permissions'].get(principal.principal_id,()):
            raise a.ApprovalDenied('authority_denied')
        command=s['cancel_commands'].get(command_id)
        if command is None or (command.intent_ref.id,command.expected_version,command.session_id,command.generation)!=(intent_id,expected_version,session.session_id,s['generation']):
            raise a.ApprovalDenied('replay_conflict')
        if command.attempt_ref is None: return None
        attempt=s['attempts'][command.attempt_ref.id]
        if attempt.receipt_ref is None: return None
        receipt=s['execution_records'][attempt.receipt_ref]
        self._broker.verify(receipt,'receipt',receipt.receipt_id)
        return receipt

    @_db_command
    def change_cancel_permissions(self,handle,principal_id,actions):
        s,at=self._copy(),self._now()
        _,session=self._auth(s,handle,'runtime',at,protective=True)
        principal=self._authority._principals.get(principal_id)
        if principal is None or principal.role!='controller' or type(actions) is not tuple or actions not in ((),('cancel',)):
            raise a.ApprovalDenied('authority_denied')
        s['execution_permissions'][principal_id]=actions
        event=self._event(s,'synthetic_cancel_permissions_update',principal_id,at)
        self._commit(s,owner=session.session_id)
        return event

    def _check_cancel(self,s,handle,command,at):
        principal,session=self._auth(s,handle,'runtime',at,protective=True)
        intent=s['intents'].get(command.intent_ref.id)
        if (principal.role!='controller' or 'cancel' not in s['execution_permissions'].get(principal.principal_id,()) or
            command.session_id!=session.session_id or command.generation!=s['generation'] or
            not command.issued_at<=at<command.expires_at or
            s.get('cancel_nonces',{}).get(command.nonce)!=command.command_id):
            raise a.ApprovalDenied('authority_denied')
        if (intent is None or intent.state in d.TERMINAL or intent.state_version!=command.expected_version or
            intent.broker_order_id!=command.broker_order_id or
            number(intent.terms.quantity)-number(intent.confirmed_quantity)!=number(command.maximum_remaining)):
            raise a.ApprovalDenied('version_conflict')
        return intent

    @_db_command
    def _arm_cancel(self,handle,command_id):
        s,at=self._copy(),self._now()
        command=s['cancel_commands'].get(command_id)
        if command is None: raise d.ExecutionDenied('source_unresolved')
        intent=self._check_cancel(s,handle,command,at)
        if any(c.command_id!=command_id and c.intent_ref.id==intent.intent_id and c.state in ('armed','unknown','acknowledged') for c in s['cancel_commands'].values()):
            raise a.ApprovalDenied('terminal_state')
        if command.state!='issued' or command.attempt_ref is not None:
            raise a.ApprovalDenied('terminal_state')
        attempt=d.DispatchAttempt('cancel-attempt:'+uuid4().hex,intent.intent_id,'cancel',intent.request_hash,
            s['generation'],s['fence'],self._broker._instance,'armed',at,None)
        ar=self._remember(s,'attempt',attempt.attempt_id,attempt)
        s['attempts'][attempt.attempt_id]=attempt
        s['cancel_commands'][command_id]=replace(command,state='armed',attempt_ref=ar,state_version=command.state_version+1)
        self._remember(s,'cancel',command_id,s['cancel_commands'][command_id])
        self._cancel_check=(handle,command_id)
        self._commit(s)
        return attempt

    def dispatch_cancel(self,handle,command_id):
        identifier(command_id)
        with self._lock:
            attempt=self._arm_cancel(handle,command_id)
            self._stage('before_cancel_handoff')
            attempt,intent,window=self._handoff_ready(handle,attempt.attempt_id,command_id)
            self._check_handoff_time(window,attempt,intent)
            receipt=self._broker.handoff(attempt,intent)
            self._stage('after_cancel_handoff')
            return self._store_cancel_receipt(command_id,attempt,receipt)

    @_db_command
    def _store_cancel_receipt(self,command_id,attempt,receipt):
        s=self._copy()
        command=s['cancel_commands'][command_id]
        if command.attempt_ref is None or command.attempt_ref.id!=attempt.attempt_id or attempt.action!='cancel':
            raise d.ExecutionDenied('event_conflict')
        recorded=s['attempts'].get(attempt.attempt_id)
        if recorded not in (attempt,replace(attempt,state='unknown')):
            raise d.ExecutionDenied('event_conflict')
        rr=None
        if receipt is not None:
            self._broker.verify(receipt,'receipt',receipt.receipt_id)
            if (receipt.kind,receipt.attempt_id,receipt.request_hash,receipt.broker_order_id)!=('cancel_ack',attempt.attempt_id,attempt.request_hash,command.broker_order_id):
                raise d.ExecutionDenied('source_unresolved')
            rr=self._remember(s,'receipt',receipt.receipt_id,receipt)
        s['attempts'][attempt.attempt_id]=replace(attempt,state='result_stored' if rr else 'unknown',receipt_ref=rr)
        next_state='confirmed' if command.state=='confirmed' else ('acknowledged' if rr else 'unknown')
        s['cancel_commands'][command_id]=replace(command,state=next_state,state_version=command.state_version+1)
        self._remember(s,'cancel',command_id,s['cancel_commands'][command_id])
        self._commit(s)
        return receipt

    def _invalidate_generation(self,s,generation,at):
        old=s['generation']
        s['generation'],s['mode'],s['restored']=generation,'stopped',True
        s['fence']+=1
        s['reconciliation']=None
        for intent in tuple(s['intents'].values()):
            if intent.state=='dispatching': self._intent_change(s,intent,state='unknown')
        for cid,c in tuple(s['cancel_commands'].items()):
            if c.state=='armed':
                s['cancel_commands'][cid]=replace(c,state='unknown',state_version=c.state_version+1)
                self._remember(s,'cancel',cid,s['cancel_commands'][cid])
        for (kind,identity),r in tuple(s['heads'].items()):
            obj=self._get(s,r)
            if kind=='approval' and obj.state in ('pending','approved'):
                event=self._event(s,'generation_invalidation',identity,at)
                self._change(s,obj,'invalidated',at,event,reason='generation_mismatch')
                s['holds'].pop(identity,None)
            if kind=='approval' and obj.state=='consumed':
                # Old-generation nonces cannot complete. Retain the exact two
                # remaining atomic withdrawal closures (3 issue + 5 completion),
                # while financial completion stays in the intent's protected budget.
                remaining=2-s['withdrawals'].get(obj.consumed_intent_id,0)
                s['holds'][identity]=(remaining*8,remaining*8*65536)
            if kind=='session':
                if obj.state=='running':
                    event=self._event(s,'generation_session_invalidation',identity,at)
                    self._put(s,'session',replace(obj,state='invalidated',state_version=obj.state_version+1,
                        previous_ref=r,last_control_event_ref=event))
                s['holds'].pop(identity,None)
        # Retire unusable generation-scoped indexes, never immutable evidence.
        # Past results are derived from original challenge/receipt records below.
        # No duplicate archive or hidden persistent lookup is kept.
        for key in ('commands','nonces','receipts','cancel_nonces'): s[key]={}
        s['restart_binding']={'previous_generation':old,'generation':generation,'at':at}
        return s

    @_db_command
    def rotate(self,handle):
        s,at=self._copy(),self._now()
        self._auth(s,handle,'runtime',at,protective=True)
        generation='generation:'+uuid4().hex
        self._invalidate_generation(s,generation,at)
        self._commit(s)
        return generation

    @classmethod
    def current_runtime(cls,database,account_ref):
        """Root composition의 읽기 전용 CAS 관측. 반환값은 handle/복원 권위가 아니다."""
        d.account(account_ref)
        if cls is not PostgresExecutionRepository or type(database) is not PostgresLedger or not database._ready:
            raise a.ApprovalDenied('authority_denied')
        with ExecutionUnitOfWork(database,account_ref) as uow:
            stored=uow.call('execution_load',account_ref)
            if stored is None: raise d.ExecutionDenied('source_unresolved')
            state=_unpack(stored['state'])
            return {'account_ref':account_ref,'version':stored['version'],'generation':state['generation'],
                    'fence':state['fence'],'mode':state['mode']}

    @classmethod
    def restart(cls,database,authority,source,approval_policy,inputs,broker,*,expected_generation,source_history=()):
        """현재 DB에만 재결속한다. JSON/backup/foreign broker journal은 권위 입력이 아니다.

        Root synthetic composition API: 새 issuer가 실제 DB+독립 live broker journal을
        확인하고 새 세대를 발급한다. 핸들 발급·rebind·resume는 각각 별도 명시 단계다.
        """
        identifier(expected_generation)
        if (cls is not PostgresExecutionRepository or type(database) is not PostgresLedger or not database._ready or
            type(authority) is not SyntheticAuthority or authority._repository is not None or
            type(source) is not ApprovalSource or type(inputs) is not ExecutionInputs or
            type(broker) is not SyntheticExecutionBroker or broker._account!=source.request.account_ref):
            raise a.ApprovalDenied('authority_denied')
        policy=a.checked(approval_policy)
        if type(policy) is not a.SyntheticApprovalPolicy or policy.account_ref!=broker._account:
            raise a.ApprovalDenied('authority_denied')
        self=object.__new__(cls)
        self._database,self._authority,self._source,self._inputs,self._broker=database,authority,source,inputs,broker
        self._account,self._lock=broker._account,broker._gate
        self._capacity,self._byte_capacity=128,8388608
        self._failure,self._uow,self._state=None,None,None
        self._aggregate_id='execution-aggregate:'+uuid4().hex
        if type(source_history) is not tuple or any(type(x) is not ApprovalSource for x in source_history):
            raise a.ApprovalDenied('source_unresolved')
        self._source_history=source_history
        self._registry={'handles':{},'readers':{},'inputs':inputs,'source':source,'source_history':source_history,'authority':authority}
        self._final_authorities,self._refresh_check,self._cancel_check=[],None,None
        generation='generation:'+uuid4().hex # outside stored snapshot, never caller's old generation
        with self._lock,ExecutionUnitOfWork(database,self._account) as uow:
            self._uow=uow
            self._bind_uow()
            try:
                stored=uow.call('execution_load',self._account)
                if stored is None: raise d.ExecutionDenied('source_unresolved')
                self._db_version=stored['version']
                self._state=_unpack(stored['state'])
                s=self._copy()
                if s.get('source_archive',())!=tuple(source_bytes(x) for x in source_history):
                    raise d.ExecutionDenied('source_unresolved')
                if s['generation']!=expected_generation: raise a.ApprovalDenied('generation_mismatch')
                if stored['source_hash']!=self._source_hash() or self._policy(s)!=policy:
                    raise d.ExecutionDenied('source_unresolved')
                # No financial fact is adopted from the new authority or an input JSON.
                # A lost journal leaves outstanding intents unknown for observation only.
                journal_ok=True
                for r,obj in s['execution_records'].items():
                    if r.kind in ('receipt','event'):
                        # Quarantine evidence has a local alias; issuer authority
                        # still belongs to the original typed object's identity.
                        if r.kind=='receipt' and type(obj) is d.SyntheticBrokerReceipt:
                            identity=obj.receipt_id
                        elif r.kind=='event' and type(obj) is d.SyntheticOrderEvent:
                            identity=obj.event_id
                        else:
                            journal_ok=False
                            continue
                        try: broker.verify(obj,r.kind,identity)
                        except d.ExecutionDenied: journal_ok=False
                try: broker.verify(inputs.query,'query',inputs.query.query_id)
                except d.ExecutionDenied: journal_ok=False
                at=self._now()
                self._invalidate_generation(s,generation,at)
                if not journal_ok:
                    for intent in tuple(s['intents'].values()):
                        if intent.state in ('acknowledged','partially_filled'):
                            self._intent_change(s,intent,state='unknown')
                s['handles'],s['readers']={},{}
                self._state=s
                self._commit(s)
                self._persist()
                uow.commit()
            finally:
                self._uow,self._state=None,None
            authority._generation=generation
            authority._repository=self
        return self

    @_db_command
    def rebind(self,handle,query,*,market_inputs=None,execution_policy=None):
        s,at=self._copy(),self._now()
        self._auth(s,handle,'runtime',at,protective=True)
        if s['mode'] not in ('stopped','reconciling'): raise a.ApprovalDenied('terminal_state')
        # refresh_current atomically rebuilds current Q20/Q21/Q23 and source rights;
        # unsupported correction/quarantine remains blocked, including preserved holds.
        self._inputs=replace(self._inputs,runtime_generation=s['generation'])
        self.refresh_current(handle,query,market_inputs=market_inputs,execution_policy=execution_policy)
        s=self._copy()
        self._validate_recovery(s,query,at)
        s['restored']=False
        s['mode']='reconciling'
        self._commit(s)
        return self.reconcile(handle,query)

    @_db_command
    def account_cash(self,handle,query=None):
        """실제 Q20 settled cash와 obligation component·독립 B로 재조회한다.

        이 API는 관측용이며 신규 admission의 current_risk를 대체하지 않는다.
        """
        from quantharbor.application.target import _cash_rows
        from quantharbor.domain.target import available_cash
        from quantharbor.domain.execution_math import cash_with_reservations
        s,at = self._state,self._now()
        self._auth(s,handle,'runtime',at,protective=True)
        query = self._inputs.query if query is None else d.checked(query)
        self._broker.verify(query,'query',query.query_id)
        if (query.account_ref!=self._account or query.status!='complete' or query.missing_scope or
            query.covered_scope!=self._inputs.current.facts.covered_scope or query.as_of>at):
            raise d.ExecutionDenied('source_unresolved')
        self._validate_inclusions(s,query)
        projection = self._projection(at)
        request = replace(self._source.request,as_of=self._inputs.current.current.snapshot.as_of,
            knowledge_cutoff=self._inputs.current.current.snapshot.knowledge_cutoff,evaluated_at=at)
        base = execution_cash_base(self._inputs.current,request,self._source.artifacts.plan.body.request.snapshot_ref,
            tuple(s['reservations'].values()))
        cash = {x.currency:x.amount for x in projection.cash_balances if x.account=='settled_cash'}
        capacities = {x.currency:x for x in query.cash}
        if set(capacities)!={x.currency for x in base}: raise d.ExecutionDenied('source_unresolved')
        result = []
        for row in base:
            settled = cash.get(row.currency,'0')
            available = available_cash(settled,row.outstanding,row.floor,row.broker_capacity,row.unreflected,row.post_source_debits)
            updated = replace(row,ledger_cash=settled,available=available,
                remaining=finite(number(available)-number(row.planned_burden)))
            result.append(cash_with_reservations(updated,tuple(s['reservations'].values()),
                broker_amount=capacities[row.currency].amount,included=capacities[row.currency].included_components,source_cutoff=query.as_of))
        return tuple(result)
