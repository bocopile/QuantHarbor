"""단위 시험용 in-memory transaction. PostgreSQL/내구성 증거가 아니다."""
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from quantharbor.application.ledger import LedgerState, append_to_state, replay
from quantharbor.domain.ledger import ContractError, SyntheticLedgerSubmission, account, digest, identifier, exact


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    message_id: str
    account_ref: str
    cursor: int
    projection_id: str
    payload_hash: str


class SyntheticLedger:
    def __init__(self):
        self._states = {}
        self._outbox = {}
        self._delivery = {}
        self._inbox = {}
        self._work = {}
        self._collisions = []
        self._lock = RLock()

    def state(self, account_ref):
        account(account_ref)
        with self._lock:
            return deepcopy(self._states.get(account_ref, LedgerState(account_ref)))

    @property
    def outbox(self):
        with self._lock:
            return tuple(self._outbox.values())

    def append(self, submission, *, recorded_at, reprocess=False, fail_at=None):
        exact(submission, SyntheticLedgerSubmission)
        if fail_at not in (None, 'events', 'projection', 'outbox'):
            raise ContractError()
        with self._lock:
            state = self.state(submission.account_ref)
            result = append_to_state(state, submission, recorded_at=recorded_at, reprocess=reprocess)
            if result.status == 'duplicate':
                return result
            if fail_at:
                raise ContractError()
            from quantharbor.domain.ledger import hash_record
            projection = state.projections[-1]
            message = OutboxMessage(projection.projection_id, state.account_ref, result.cursor,
                                    projection.projection_id, hash_record(projection))
            self._states[state.account_ref] = state
            self._outbox[message.message_id] = message
            self._delivery[message.message_id] = False
            return result

    def replay(self, account_ref, **kwargs):
        return replay(self.state(account_ref), **kwargs)

    def consume(self, consumer, message_id, payload_hash, *, fail_before_commit=False):
        identifier(consumer)
        identifier(message_id)
        digest(payload_hash)
        if type(fail_before_commit) is not bool:
            raise ContractError()
        with self._lock:
            message = self._outbox.get(message_id)
            if message is None:
                raise ContractError()
            key = consumer, message_id
            if payload_hash != message.payload_hash or (key in self._inbox and self._inbox[key] != payload_hash):
                self._collisions.append((consumer, message_id, payload_hash))
                return 'collision'
            if key in self._inbox:
                return 'duplicate'
            if fail_before_commit:
                raise ContractError()
            self._inbox[key] = payload_hash
            work_key = consumer, message.account_ref
            self._work[work_key] = max(message.cursor, self._work.get(work_key, 0))
            return 'accepted'

    def acknowledge(self, message_id):
        identifier(message_id)
        with self._lock:
            if message_id not in self._delivery:
                raise ContractError()
            self._delivery[message_id] = True

    def consumer_cursor(self, consumer, account_ref):
        identifier(consumer)
        account(account_ref)
        return self._work.get((consumer, account_ref), 0)
