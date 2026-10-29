"""독립 합성 broker 발급 journal. URL/client/callback/credential 입력은 없다."""
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from uuid import uuid4

from quantharbor.domain import execution as d
from quantharbor.domain.ledger import exact, integer
from quantharbor.domain.primitives import utc_instant
from quantharbor.domain.target import TargetScope, ref as target_ref
from quantharbor.domain.valuation import SyntheticAccountStatement, number


@dataclass(frozen=True, slots=True)
class BrokerSnapshot:
    statement: SyntheticAccountStatement
    scope: TargetScope
    cash: tuple[d.BrokerCash, ...]
    sellable: tuple[d.BrokerQuantity, ...]
    as_of: str
    included_sequence: int = 0

    def __post_init__(self):
        exact(self.statement,SyntheticAccountStatement)
        exact(self.scope,TargetScope)
        utc_instant(self.as_of)
        integer(self.included_sequence,0)
        if type(self.cash) is not tuple or type(self.sellable) is not tuple:
            raise d.ExecutionDenied()
        for x in self.cash: exact(x,d.BrokerCash)
        for x in self.sellable: exact(x,d.BrokerQuantity)
        if len({x.currency for x in self.cash}) != len(self.cash) or len({x.position for x in self.sellable}) != len(self.sellable):
            raise d.ExecutionDenied()


@dataclass(frozen=True, slots=True)
class BrokerFact:
    event_id: str
    kind: str
    semantics: str
    execution_id: str
    revision: int
    predecessor_revision: int | None
    stream_sequence: int
    quantity: str
    price: str
    fee: str | None
    tax: str | None
    effective_at: str


class SyntheticExecutionBroker:
    def __init__(self, account_ref, snapshots, facts=(), *, response='accepted', cancel_response='cancel_ack'):
        from quantharbor.domain.ledger import account
        account(account_ref)
        if (type(snapshots) is not tuple or not 1 <= len(snapshots) <= 8 or
            type(facts) is not tuple or len(facts)>8 or response not in ('accepted','final_reject','timeout')):
            raise d.ExecutionDenied()
        for s in snapshots:
            exact(s,BrokerSnapshot)
            if s.statement.snapshot.account_ref != account_ref:
                raise d.ExecutionDenied()
        for f in facts: exact(f,BrokerFact)
        from quantharbor.domain.execution_budget import admit_manifest
        self._completion_cost = admit_manifest(facts)
        self._account, self._snapshots, self._facts = account_ref, snapshots, facts
        if cancel_response not in ('cancel_ack','timeout'):
            raise d.ExecutionDenied()
        self._response, self._cancel_response = response, cancel_response
        self._instance = 'synthetic-broker:' + uuid4().hex
        self._gate = RLock()
        self._journal = {}
        self._requests = {}
        self._sequence = 0
        self._event_count = {}
        self._revoked = set()
        self._query_count = 0
        self._event_sequences = {}

    def _put(self, kind, identity, obj):
        r = d.ref(kind,identity,obj)
        prior = self._journal.get(r)
        if prior is not None and prior != obj:
            raise d.ExecutionDenied('event_conflict')
        self._journal[r] = obj
        return obj

    def resolve(self, reference):
        with self._gate:
            if type(reference) is not d.ExecutionRef or reference not in self._journal:
                raise d.ExecutionDenied('source_unresolved')
            return self._journal[reference]

    def verify(self, obj, kind, identity):
        # Hash equivalence alone is insufficient: exact object must be in this journal.
        if self.resolve(d.ref(kind,identity,obj)) != obj or obj.issuer_instance != self._instance:
            raise d.ExecutionDenied('source_unresolved')
        return obj

    def handoff(self, attempt, intent):
        exact(attempt,d.DispatchAttempt)
        exact(intent,d.OrderIntent)
        with self._gate:
            if (intent.account_ref != self._account or attempt.intent_id != intent.intent_id or
                attempt.request_hash != intent.request_hash or attempt.state != 'armed' or
                attempt.attempt_id in self._revoked):
                raise d.ExecutionDenied('authority_denied')
            prior = self._requests.get(attempt.attempt_id)
            if prior is not None:
                raise d.ExecutionDenied('event_conflict')  # issuer never retries a write
            self._requests[attempt.attempt_id] = (attempt,intent)
            self._sequence += 1
            if (self._cancel_response if attempt.action=='cancel' else self._response) == 'timeout':
                return None
            kind = 'cancel_ack' if attempt.action == 'cancel' else self._response
            broker_id = None if kind == 'final_reject' else intent.broker_order_id or 'synthetic-order:' + uuid4().hex
            receipt = d.SyntheticBrokerReceipt('broker-receipt:'+uuid4().hex,self._instance,
                self._account,intent.intent_id,attempt.attempt_id,attempt.request_hash,broker_id,
                self._sequence,attempt.recorded_at,kind,'broker-journal:'+uuid4().hex)
            return self._put('receipt',receipt.receipt_id,receipt)

    def prove_unsent(self, attempt, intent):
        with self._gate:
            if (attempt.attempt_id in self._requests or attempt.intent_id != intent.intent_id or
                attempt.egress_instance!=self._instance or attempt.request_hash!=intent.request_hash or intent.account_ref!=self._account):
                raise d.ExecutionDenied('handoff_unknown')
            for obj in self._journal.values():
                if type(obj) is d.SyntheticBrokerReceipt and obj.kind=='proven_unsent' and obj.attempt_id==attempt.attempt_id:
                    return obj
            self._revoked.add(attempt.attempt_id)
            self._sequence += 1
            receipt = d.SyntheticBrokerReceipt('unsent:'+uuid4().hex,self._instance,self._account,
                intent.intent_id,attempt.attempt_id,intent.request_hash,None,self._sequence,
                attempt.recorded_at,'proven_unsent','broker-journal:'+uuid4().hex)
            return self._put('receipt',receipt.receipt_id,receipt)

    def issue_event(self, receipt, index):
        integer(index,0,len(self._facts)-1)
        with self._gate:
            self.verify(receipt,'receipt',receipt.receipt_id)
            if receipt.kind not in ('accepted','cancel_ack') or receipt.attempt_id not in self._requests:
                raise d.ExecutionDenied('source_unresolved')
            key = (receipt.intent_id,index)
            old = self._event_count.get(key)
            if old is not None:
                return self.resolve(old)
            if sum(k[0]==receipt.intent_id for k in self._event_count) >= 8:
                raise d.ExecutionDenied('capacity_exceeded')
            f = self._facts[index]
            if (f.kind=='cancelled_remaining') != (receipt.kind=='cancel_ack'):
                raise d.ExecutionDenied('source_unresolved')
            event_id='broker-event:'+sha256((receipt.intent_id+':'+f.event_id).encode()).hexdigest()
            obj = d.SyntheticOrderEvent(event_id,self._instance,self._account,receipt.intent_id,
                receipt.request_hash,receipt.broker_order_id,f.revision,f.predecessor_revision,
                f.kind,f.semantics,f.execution_id,f.stream_sequence,f.quantity,f.price,f.fee,f.tax,
                f.effective_at,receipt.issued_at,d.ref('receipt',receipt.receipt_id,receipt),
                'broker-event-journal:'+uuid4().hex)
            self._sequence += 1
            self._event_sequences[d.ref('event',obj.event_id,obj)] = self._sequence
            self._put('event',obj.event_id,obj)
            self._event_count[key] = d.ref('event',obj.event_id,obj)
            return obj

    def query(self, index=0):
        integer(index,0,len(self._snapshots)-1)
        with self._gate:
            if self._query_count >= 20:
                raise d.ExecutionDenied('capacity_exceeded')
            s = self._snapshots[index]
            if s.included_sequence>self._sequence:
                raise d.ExecutionDenied('source_unresolved')
            complete = s.statement.status == 'success' and s.statement.complete
            obj = d.SyntheticExecutionQuery('query:'+uuid4().hex,self._instance,self._account,'synthetic',
                s.scope,s.scope,(), 'complete' if complete else 'partial',s.as_of,s.included_sequence,
                s.cash,s.sellable,tuple(r for r in self._journal if r.kind=='receipt'),
                tuple(r for r in self._journal if r.kind=='event'),
                target_ref('statement',s.statement.snapshot.statement_id,s.statement),'broker-query-journal:'+uuid4().hex,self._sequence,tuple(a for a,_ in self._requests.values()))
            self._query_count += 1
            return self._put('query',obj.query_id,obj)

    def manifest(self, query):
        with self._gate:
            self.verify(query,'query',query.query_id)
            if (query.journal_sequence!=self._sequence or query.request_attempts!=tuple(a for a,_ in self._requests.values())):
                raise d.ExecutionDenied('stale_source')
            if query.receipts != tuple(r for r in self._journal if r.kind=='receipt') or query.events != tuple(r for r in self._journal if r.kind=='event'):
                raise d.ExecutionDenied('stale_source')
            return tuple((attempt,intent) for attempt,intent in self._requests.values())

    def statement(self, query):
        self.verify(query,'query',query.query_id)
        matches = [s.statement for s in self._snapshots if target_ref('statement',s.statement.snapshot.statement_id,s.statement)==query.statement_ref]
        if not matches:
            raise d.ExecutionDenied('source_unresolved')
        return matches[0]

    @property
    def received_count(self):
        return len(self._requests)
