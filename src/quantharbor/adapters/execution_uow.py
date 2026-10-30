"""고정 합성 DB의 단일 psql connection/transaction. raw SQL은 제품 API가 아니다."""
import json
from decimal import Decimal
from functools import wraps
from hashlib import sha256
import os
import selectors
import subprocess
import time
from uuid import uuid4

from .postgres_ledger import PostgresLedger, _text
from quantharbor.domain.execution import ExecutionDenied
from quantharbor.domain.ledger import account

MAX_FRAME = 8388608
MAX_CHUNK = 65536
MAX_HEADER = 4096
MAX_CHUNK_FRAME = 135168
MAX_TRANSACTION_BYTES = 256 * 1048576
TRANSACTION_SECONDS = 120


def _json(raw, *, fingerprint=False):
    def pairs(values):
        obj={}
        for key,value in values:
            if key in obj: raise ValueError('duplicate_key')
            obj[key]=value
        return obj
    def invalid_number(value): raise ValueError('non_integer_json_number')
    return json.loads(raw,object_pairs_hook=pairs,
        parse_float=Decimal if fingerprint else invalid_number,parse_constant=invalid_number)



def _rollback_on_error(method):
    """A caught protocol error cannot turn a partial financial TX into COMMIT."""
    @wraps(method)
    def call(self,*args,**kwargs):
        if self._failed: raise ExecutionDenied('storage_failure')
        try: return method(self,*args,**kwargs)
        except Exception:
            self._failed=True
            self.close()  # stdin EOF, then bounded kill/wait if the peer is stuck
            raise
    return call


def state_delta(old,new):
    """Only changed entries cross the wire; immutable history is never resent."""
    if old is None: old={'map':[]}
    before={json.dumps(k,sort_keys=True,separators=(',',':')):(k,v) for k,v in old['map']}
    after={json.dumps(k,sort_keys=True,separators=(',',':')):(k,v) for k,v in new['map']}
    changes=[]
    for encoded,(key,value) in after.items():
        prior=before.get(encoded,(key,None))[1]
        if value==prior: continue
        if type(value) is dict and set(value)=={'map'} and (prior is None or type(prior) is dict and set(prior)=={'map'}):
            pm={} if prior is None else {json.dumps(k,sort_keys=True,separators=(',',':')):(k,v) for k,v in prior['map']}
            nm={json.dumps(k,sort_keys=True,separators=(',',':')):(k,v) for k,v in value['map']}
            change={'upsert':[[k,v] for ident,(k,v) in nm.items() if ident not in pm or pm[ident][1]!=v],
                'remove':[k for ident,(k,v) in pm.items() if ident not in nm]}
            changes.append({'key':key,'mode':'map','value':change})
        else: changes.append({'key':key,'mode':'value','value':value})
    for encoded,(key,_) in before.items():
        if encoded not in after: changes.append({'key':key,'mode':'remove','value':None})
    return changes


class ExecutionUnitOfWork:
    def __init__(self, database, account_ref):
        if type(database) is not PostgresLedger or not database._ready:
            raise ExecutionDenied('storage_failure')
        account(account_ref)
        self._db, self.account_ref = database, account_ref
        self._process = None
        self._buffer = bytearray()
        self._deadline = None
        self._transferred = 0
        self._loaded = None
        self._trust = None
        self._actor = None
        self._fact = None
        self._command = None
        self._failed = False
        self._validity = None

    def __enter__(self):
        try:
            self._deadline = time.monotonic()+TRANSACTION_SECONDS
            self._process = subprocess.Popen(self._db._psql(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=self._db._env, bufsize=0)
            self._exchange("BEGIN; SET LOCAL statement_timeout='15s'; SET LOCAL lock_timeout='10s'; SET LOCAL ROLE qh_execution_product;", result=False)
            self.call('execution_lock', self.account_ref)
            return self
        except Exception:
            self.close()
            raise ExecutionDenied('storage_failure') from None

    @_rollback_on_error
    def _exchange(self, sql, *, result=True, frame_limit=MAX_FRAME):
        if self._process is None or type(sql) is not str:
            raise ExecutionDenied('storage_failure')
        marker = 'q27frame' + uuid4().hex
        frame = (sql + "\n\\echo " + marker + '\n').encode()
        if len(frame) > frame_limit or frame_limit>MAX_FRAME:
            raise ExecutionDenied('capacity_exceeded')
        try:
            # A raw pipe write may be partial. Bound both directions by one deadline;
            # drain stdout while writing so a full pipe cannot deadlock a large frame.
            deadline = min(time.monotonic() + 20,self._deadline or time.monotonic()+20)
            self._transferred += len(frame)
            if self._transferred>MAX_TRANSACTION_BYTES: raise ExecutionDenied("capacity_exceeded")
            output = bytearray()
            sent = 0
            os.set_blocking(self._process.stdin.fileno(), False)
            os.set_blocking(self._process.stdout.fileno(), False)
            with selectors.DefaultSelector() as selector:
                selector.register(self._process.stdin, selectors.EVENT_WRITE)
                selector.register(self._process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ExecutionDenied('storage_failure')
                    ready = selector.select(remaining)
                    if not ready:
                        raise ExecutionDenied('storage_failure')
                    for key, mask in ready:
                        if key.fileobj is self._process.stdin:
                            try:
                                written = os.write(key.fd, memoryview(frame)[sent:sent+65536])
                            except BlockingIOError:
                                continue
                            if written <= 0:
                                raise ExecutionDenied('storage_failure')
                            sent += written
                            if sent == len(frame):
                                selector.unregister(self._process.stdin)
                        else:
                            try:
                                chunk = os.read(key.fd, 65536)
                            except BlockingIOError:
                                continue
                            if not chunk:
                                raise ExecutionDenied('storage_failure')
                            self._transferred += len(chunk)
                            if self._transferred>MAX_TRANSACTION_BYTES: raise ExecutionDenied("capacity_exceeded")
                            output.extend(chunk)
                            if len(output) > MAX_FRAME:
                                raise ExecutionDenied('capacity_exceeded')
                    if sent == len(frame) and output.endswith((marker+'\n').encode()):
                        raw = output[:-(len(marker)+1)].decode().strip()
                        if result:
                            # json.loads rejects extra output; duplicate keys are checked before conversion.
                            return _json(raw)
                        if raw: raise ExecutionDenied('storage_failure')
                        return None
        except (OSError, ValueError, UnicodeError):
            raise ExecutionDenied('storage_failure') from None

    def bind(self, authority, registry, broker):
        from .synthetic_approval import SyntheticAuthority
        from .synthetic_execution_broker import SyntheticExecutionBroker
        if (type(authority) is not SyntheticAuthority or type(broker) is not SyntheticExecutionBroker or
            registry.get('authority') is not authority or registry.get('inputs') is None or
            broker._account!=self.account_ref):
            raise ExecutionDenied('authority_denied')
        self._trust=(authority,registry,broker)

    def validity(self,value):
        if self._trust is None: raise ExecutionDenied("authority_denied")
        self._validity=value

    def actor(self,principal,session,action):
        if self._trust is None: raise ExecutionDenied('authority_denied')
        self._actor=(principal,session,action)

    def command(self,challenge):
        if self._trust is None: raise ExecutionDenied("authority_denied")
        self._command=challenge

    def fact(self,event):
        if self._trust is None: raise ExecutionDenied('authority_denied')
        self._trust[2].verify(event,'event',event.event_id)
        self._fact=event

    def _select(self,function,*values,frame_limit=MAX_FRAME):
        if function=='execution_stage_chunk':
            token,part,raw=values
            if type(raw) is not str or len(raw)>MAX_CHUNK*2 or any(c not in '0123456789abcdef' for c in raw):
                raise ExecutionDenied('invalid_contract')
            return self._exchange('SELECT qh.execution_stage_chunk('+_text(token)+','+str(part)+",'"+raw+"');",frame_limit=MAX_CHUNK_FRAME)
        args=','.join('NULL' if v is None else str(v) if type(v) is int else
            _text(json.dumps(v,ensure_ascii=False,separators=(',',':')) if type(v) is not str else v) for v in values)
        return self._exchange('SELECT qh.'+function+'('+args+');',frame_limit=frame_limit)

    @_rollback_on_error
    def _read(self,operation,payload='',at=''):
        data=bytearray(); total=None
        for page in range(1024):
            response=self._select('execution_read_page',self.account_ref,operation,payload,at,page,frame_limit=MAX_CHUNK_FRAME)
            if (type(response) is not dict or set(response)!={'page','total','hex'} or type(response['page']) is not int or response['page']!=page or
                type(response['total']) is not int or not 0<=response['total']<=64*1048576 or
                total is not None and total!=response['total']): raise ExecutionDenied('storage_failure')
            total=response['total']
            if (type(response['hex']) is not str or len(response['hex'])>MAX_CHUNK*2 or
                any(c not in '0123456789abcdef' for c in response['hex'])): raise ExecutionDenied('storage_failure')
            chunk=bytes.fromhex(response['hex'])
            if len(chunk)!=min(MAX_CHUNK,total-page*MAX_CHUNK): raise ExecutionDenied('storage_failure')
            data.extend(chunk)
            if len(data)==total:
                if operation=='fingerprint':
                    # SQL freezes ordered rows as jsonb::text UTF-8 pages.
                    # Validate exact numbers without float conversion, then hash
                    # every original byte. The repository hashes this opaque
                    # digest through its existing JSON-result fingerprint path.
                    _json(data.decode('utf-8'),fingerprint=True)
                    return sha256(data).hexdigest()
                return _json(data.decode('utf-8'))
        raise ExecutionDenied('capacity_exceeded')

    @_rollback_on_error
    def _apply(self,action,payload):
        if self._trust is None: raise ExecutionDenied('authority_denied')
        authority,registry,broker=self._trust
        if registry.get('authority') is not authority: raise ExecutionDenied('authority_denied')
        from dataclasses import asdict
        stored=self._loaded
        from .postgres_execution import _unpack
        state={} if stored is None else _unpack(stored['state'])
        principal,session,actor_action=self._actor or (None,None,None)
        fact=self._fact
        header={'version':-1 if stored is None else stored['version'],
            'generation':state.get('generation'),'fence':state.get('fence'),
            'source_hash':None if stored is None else stored['source_hash'],
            'actor':None if principal is None else principal.principal_id,
            'session':None if session is None else session.session_id,'action':actor_action,'nonce':None,
            'target':None,'target_version':None,'at':authority._clock(),
            'issuer':broker._instance if fact else authority._instance,
            'fact':None if fact is None else asdict(fact),'operation':action,
            'command':None if self._command is None else asdict(self._command),
            'current_validation':self._validity}
        if self._command is not None: header['nonce']=self._command.nonce
        if action=='append':
            if fact is None: raise ExecutionDenied('authority_denied')
            broker.verify(fact,'event',fact.event_id)
            intent=state.get('intents',{}).get(fact.intent_id)
            if intent is None: raise ExecutionDenied('source_unresolved')
            header['target'],header['target_version']=intent.intent_id,intent.state_version
        if action=='save':
            # Normalized table rows also travel only when newly created/changed.
            previous={} if stored is None else _unpack(stored['state'])
            current=payload
            payload={k:v for k,v in current.items() if k!='state'}
            payload['state_delta']=state_delta(None if stored is None else stored['state'],current['state'])
            old_refs={}
            for reference in (*previous.get('records',{}),*previous.get('execution_records',{})):
                old_refs[(reference.kind,reference.id,reference.version,reference.sha256)]=True
            payload['evidence']=[v for v in current['evidence'] if (v['ref']['kind'],v['ref']['id'],v['ref']['version'],v['ref']['sha256']) not in old_refs]
            for name in ('intents','reservations','attempts'):
                key={'intents':'intent_id','reservations':'reservation_id','attempts':'attempt_id'}[name]
                payload[name]=[
                    v for v in current[name] if previous.get(name,{}).get(v[key]) is None or v!=asdict(previous[name][v[key]])]
            old_heads=previous.get('heads',{})
            payload['heads']=[v for v in current['heads'] if old_heads.get((v['kind'],v['id'])) is None or
                asdict(old_heads[(v['kind'],v['id'])])!=v]
        raw_header=json.dumps(header,ensure_ascii=False,separators=(',',':'))
        if len(raw_header.encode())>MAX_HEADER: raise ExecutionDenied('capacity_exceeded')
        # The host stages validated data under its owner role. Product cannot create
        # a context. This intentionally does not isolate a hostile DB owner/host.
        token='context:'+uuid4().hex
        encoder=json.JSONEncoder(ensure_ascii=False,separators=(',',':'),allow_nan=False)
        pending=bytearray(); count=0; size=0
        self._exchange('RESET ROLE;',result=False)
        for fragment in encoder.iterencode(payload):
            encoded=fragment.encode('utf-8'); size+=len(encoded)
            if size>64*1048576: raise ExecutionDenied('capacity_exceeded')
            pending.extend(encoded)
            while len(pending)>=MAX_CHUNK:
                self._select('execution_stage_chunk',token,count,bytes(pending[:MAX_CHUNK]).hex(),frame_limit=MAX_CHUNK_FRAME)
                del pending[:MAX_CHUNK]; count+=1
        if pending or count==0:
            self._select('execution_stage_chunk',token,count,bytes(pending).hex(),frame_limit=MAX_CHUNK_FRAME); count+=1
        self._select('execution_issue_context',self.account_ref,action,token,count,raw_header)
        self._exchange('SET LOCAL ROLE qh_execution_product;',result=False)
        return self._select('execution_apply',token,action)

    def call(self, function, *values):
        if not values or values[0]!=self.account_ref: raise ExecutionDenied('authority_denied')
        if function=='execution_lock': return self._select(function,*values)
        if function=='execution_load':
            self._loaded=self._read('load'); return self._loaded
        if function=='execution_fingerprint': return self._read('fingerprint')
        if function=='execution_ledger':
            _,operation,payload,at=values
            if operation in ('replay','events'): return self._read(operation,payload,at)
            if operation=='append': return self._apply('append',payload)
        if function=='execution_save':
            result=self._apply('save',values[1])
            self._loaded={'version':result,'state':values[1]['state'],'source_hash':values[1]['source_hash']}
            return result
        if function=='execution_event': return self._apply('event',values[1])
        if function=='execution_consume': return self._apply('consume',{'message_id':values[1],'payload_hash':values[2]})
        raise ExecutionDenied('authority_denied')

    def commit(self):
        self._exchange('COMMIT;', result=False)

    def close(self):
        p, self._process = self._process, None
        if p is not None:
            try:
                if p.stdin:
                    p.stdin.close()
                p.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                p.kill()
                p.wait(timeout=2)
            if p.stdout:
                p.stdout.close()

    def __exit__(self, exc_type, exc, tb):
        self.close()  # EOF without explicit commit rolls the transaction back.
