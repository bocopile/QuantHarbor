"""P28-03/2b-1 private synthetic AI storage foundation.

Only fresh books and bounded database decoding are authoritative. No repository or
caller JSON import exists. Core execution, recovery and proof issuance are 2b-2;
processed transitions deliberately fail closed until that bridge is implemented.
Logical quotas are not RAM, WAL or disk reservations.
"""
import base64
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
import json
import os
import re
import selectors
import subprocess
from threading import RLock
import time
import uuid

from .postgres_ledger import PostgresLedger, LedgerStorageError, _text
from .product_database import ProductDatabase
from .product_schema import ensure_schema
from quantharbor.domain import investment_ai as d
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import canonical_bytes, parse_payload

_CHUNK = 32768
_RESPONSE = 262144
_ENCODED = 33554432
_AUX = 8388608
_GLOBAL = 1048576
_SLOT = 131072
_DEADLINE = 60.0
_TYPES = {'request': d.ResearchRequest, 'result': d.ResearchResult,
          'review': d.ResearchReview, 'hypothesis': d.Hypothesis,
          'budget_policy': d.AIBudgetPolicy, 'attempt': d.AIBudgetAttempt}
_IDS = dict(zip(_TYPES, ('request_id', 'result_id', 'review_id', 'hypothesis_id', 'policy_id', 'attempt_id')))
_HASH = re.compile('[0-9a-f]{64}')


class Opcode(Enum):
    APPEND = 'append'
    RESERVE = 'reserve'
    DISPATCH = 'dispatch'
    CANCEL = 'cancel'
    SETTLE = 'settle'
    QUERY_CHARGE = 'query_charge'
    QUERY_OUTCOME = 'query_outcome'
    FINISH_PROCESSED = 'finish_processed'
    REVIEW_PROCESSED = 'review_processed'
    RESTART_RECONCILE = 'restart_reconcile'


def _fail(reason='product_ai_corrupt'):
    raise LedgerStorageError(reason)


def _alive(deadline):
    if time.monotonic() >= deadline:
        _fail('product_ai_timeout')


@contextmanager
def _timed_lock(lock, deadline):
    remaining = deadline-time.monotonic()
    if remaining <= 0 or not lock.acquire(timeout=remaining):
        _fail('product_ai_timeout')
    try:
        _alive(deadline)
        yield
    finally:
        lock.release()


def _int(value, lo=0, hi=2**63-2):
    if type(value) is not int or not lo <= value <= hi:
        raise ContractError()
    return value


def _hash(value):
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise ContractError()
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ContractError()
        out[key] = value
    return out


def _bad_number(value):
    raise ContractError()


def _parse(raw, maximum=_RESPONSE):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise ContractError()
    return json.loads(raw, object_pairs_hook=_pairs, parse_float=_bad_number, parse_constant=_bad_number)


def _b64(raw):
    return base64.b64encode(raw).decode('ascii')


def _unb64(value, maximum=65536):
    if type(value) is not str or len(value) > 4*((maximum+2)//3):
        raise ContractError()
    raw = base64.b64decode(value, validate=True)
    if len(raw) > maximum or _b64(raw) != value:
        raise ContractError()
    return raw


def _dto(raw, cls):
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise ContractError()
    wire = parse_payload(raw)
    if (type(wire.payload) is not cls or wire.schema_name != cls.__name__
            or type(wire.schema_version) is not int or wire.schema_version != 1
            or wire.environment != 'synthetic' or canonical_bytes(wire) != raw):
        raise ContractError()
    return wire.payload


@dataclass(frozen=True, slots=True)
class _Marker:
    record_hash: str
    kind: str
    transition: str
    revision: int


@dataclass(frozen=True, slots=True)
class _Book:
    records: tuple = ()             # (kind, id, canonical bytes)
    payloads: tuple = ()            # (attempt hash, request hash, policy hash, Usage)
    policies: tuple = ()            # exact policy record hashes
    blocked: tuple = ()             # one exact policy hash per blocked scope
    holds: tuple = ()               # exact attempt hashes; each owns 3/196608
    queries: tuple = ()             # (request hash, count)
    receipts: tuple = ()            # (attempt hash, tuple[QueryReceipt])
    denials: tuple = ()             # (attempt hash, tuple[reason])
    processed: tuple = ()           # (exact hash, creation transition, revision)


def _wire(book):
    if type(book) is not _Book:
        raise ContractError()
    return dict(version=1, records=[[k, i, _b64(raw)] for k, i, raw in book.records],
        payloads=[[a, r, p, list(d.usage_values(u))] for a, r, p, u in book.payloads],
        policies=list(book.policies), blocked=list(book.blocked), holds=list(book.holds),
        queries=[list(x) for x in book.queries],
        receipts=[[a, [_b64(d.encoded(r)) for r in rs]] for a, rs in book.receipts],
        denials=[[a, list(rs)] for a, rs in book.denials], processed=[list(x) for x in book.processed])


def _rows(value, width=None):
    if type(value) is not list or len(value) > 128:
        raise ContractError()
    if width is not None and any(type(x) is not list or len(x) != width for x in value):
        raise ContractError()
    return value


def _decode(raw, markers, revision, *, capacity=128, byte_capacity=8388608):
    """Private DB codec. This is intentionally not a public restoration entrypoint."""
    try:
        v = _parse(raw, _ENCODED)
        if (type(v) is not dict or set(v) != {'version', 'records', 'payloads', 'policies',
                'blocked', 'holds', 'queries', 'receipts', 'denials', 'processed'} or type(v['version']) is not int or v['version'] != 1):
            raise ContractError()
        records = []
        for k, i, b in _rows(v['records'], 3):
            if type(k) is not str or k not in _TYPES or type(i) is not str:
                raise ContractError()
            records.append((k, i, _unb64(b)))
        payloads = []
        for a, r, p, u in _rows(v['payloads'], 4):
            if type(u) is not list or len(u) != 4:
                raise ContractError()
            payloads.append((a, r, p, d.Usage(*u)))
        receipts = tuple((a, tuple(_dto(_unb64(x), d.QueryReceipt) for x in _rows(rs))) for a, rs in _rows(v['receipts'], 2))
        denials = tuple((a, tuple(_rows(rs))) for a, rs in _rows(v['denials'], 2))
        book = _Book(tuple(records), tuple(payloads), tuple(_rows(v['policies'])),
            tuple(_rows(v['blocked'])), tuple(_rows(v['holds'])),
            tuple(tuple(x) for x in _rows(v['queries'], 2)), receipts, denials,
            tuple(tuple(x) for x in _rows(v['processed'], 3)))
        _validate(book, markers, revision, capacity=capacity, byte_capacity=byte_capacity)
        if _json(_wire(book)) != raw:
            raise ContractError()
        return book
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError, ContractError):
        _fail()


def _validate(book, markers, revision, *, capacity=128, byte_capacity=8388608):
    _int(capacity, 1, 128)
    _int(byte_capacity, 1, 8388608)
    _int(revision)
    if type(book) is not _Book or any(type(getattr(book, f)) is not tuple for f in book.__dataclass_fields__):
        raise ContractError()
    if len(book.records) + 3*len(book.holds) > capacity or sum(len(x[2]) for x in book.records) + 196608*len(book.holds) > byte_capacity:
        raise ContractError()
    objects, keys = {}, set()
    for kind, identity, raw in book.records:
        if type(kind) is not str or kind not in _TYPES:
            raise ContractError()
        obj = _dto(raw, _TYPES[kind])
        if identity != getattr(obj, _IDS[kind]) or type(identity) is not str or (kind, identity) in keys:
            raise ContractError()
        keys.add((kind, identity))
        h = d.ref(kind, identity, obj).sha256
        if h in objects:
            raise ContractError()
        objects[h] = obj
    def resolve(h, cls):
        _hash(h)
        obj = objects.get(h)
        if type(obj) is not cls:
            raise ContractError()
        return obj
    def reference(r, cls):
        if type(r) is not d.AIRef:
            raise ContractError()
        obj = resolve(r.sha256, cls)
        kind = next(k for k, t in _TYPES.items() if t is cls)
        if d.ref(kind, getattr(obj, _IDS[kind]), obj) != r:
            raise ContractError()
        return obj
    def unique(rows):
        if len(rows) > 128 or len(set(rows)) != len(rows):
            raise ContractError()
    for rows in (book.policies, book.blocked, book.holds):
        unique(rows)
    for rows in (book.payloads, book.queries, book.receipts, book.denials):
        unique(tuple(x[0] for x in rows))
    attempts = {h: o for h, o in objects.items() if type(o) is d.AIBudgetAttempt}
    if set(x[0] for x in book.payloads) != set(attempts):
        raise ContractError()
    for ah, rh, ph, usage in book.payloads:
        a = resolve(ah, d.AIBudgetAttempt)
        r, p = resolve(rh, d.ResearchRequest), resolve(ph, d.AIBudgetPolicy)
        if (reference(a.request_ref, d.ResearchRequest) != r or reference(a.policy_ref, d.AIBudgetPolicy) != p
                or r.budget_policy_ref != a.policy_ref or a.role != r.role or a.reserved_usage != usage
                or type(usage) is not d.Usage or usage != d.priced(usage.input_tokens, usage.output_tokens)
                or usage.calls != 1 or not p.window_start <= a.reserved_at < p.window_end
                or a.reserved_at >= r.deadline or r.client_profile != 'synthetic'
                or p.retry_policy != d.RetryPolicy(0, (), 0, 0, ())):
            raise ContractError()
        for cap in (p.attempt_caps, r.caps):
            if any(x > y for x, y in zip(d.usage_values(usage), d.usage_values(cap))):
                raise ContractError()
        if a.actual_usage is not None and (a.actual_usage.calls != 1 or a.actual_usage != d.priced(a.actual_usage.input_tokens, a.actual_usage.output_tokens)):
            raise ContractError()
        over = a.actual_usage is not None and any(x > y for x, y in zip(d.usage_values(a.actual_usage), d.usage_values(usage)))
        expected_reasons = ('unknown_charge',) if a.state == 'unknown_charge' else ('usage_overrun',) if over else ()
        if a.reasons != expected_reasons:
            raise ContractError()
    by_request = {}
    for a in attempts.values():
        by_request.setdefault(a.request_ref.sha256, []).append(a.sequence)
    if any(sorted(sequences) != list(range(1, len(sequences)+1)) for sequences in by_request.values()):
        raise ContractError()
    policies = [resolve(h, d.AIBudgetPolicy) for h in book.policies]
    if set(book.policies) != {a.policy_ref.sha256 for a in attempts.values()}:
        raise ContractError()
    for n, p in enumerate(policies):
        for prior in policies[:n]:
            if p.budget_scope == prior.budget_scope and not (p.window_end <= prior.window_start or prior.window_end <= p.window_start):
                raise ContractError()
    blocked = [resolve(h, d.AIBudgetPolicy).budget_scope for h in book.blocked]
    unique(tuple(blocked))
    expected_blocked = {reference(a.policy_ref, d.AIBudgetPolicy).budget_scope for a in attempts.values() if a.reasons}
    if set(blocked) != expected_blocked:
        raise ContractError()
    marked = {}
    if type(markers) is not tuple or len(markers) > 128:
        raise ContractError()
    for m in markers:
        if type(m) is not _Marker or m.kind not in ('result', 'review') or m.transition != {'result': 'finish_processed', 'review': 'review_processed'}[m.kind]:
            raise ContractError()
        _int(m.revision, 1, revision)
        obj = resolve(m.record_hash, _TYPES[m.kind])
        if m.record_hash in marked:
            raise ContractError()
        marked[m.record_hash] = obj
    for entry in book.processed:
        if type(entry) is not tuple or len(entry) != 3:
            raise ContractError()
        _hash(entry[0])
        if type(entry[1]) is not str or entry[1] not in ('finish_processed', 'review_processed'):
            raise ContractError()
        _int(entry[2], 1, revision)
    if tuple(sorted(book.processed)) != tuple(sorted((m.record_hash, m.transition, m.revision) for m in markers)):
        raise ContractError()
    results = {h: o for h, o in objects.items() if type(o) in (d.ResearchResult, d.ResearchReview)}
    if set(marked) != set(results) or len(markers) > len(book.records):
        raise ContractError()
    finished = set()
    receipt_counts = {}
    for obj in results.values():
        if type(obj) is d.ResearchResult:
            r = reference(obj.request_ref, d.ResearchRequest)
            if (obj.procedure_version, obj.instruction_version, obj.tool_schema_version) != (r.procedure_version, r.instruction_version, r.tool_schema_version) or not obj.budget_attempt_refs:
                raise ContractError()
            for ar in obj.budget_attempt_refs:
                a = reference(ar, d.AIBudgetAttempt)
                if a.request_ref != obj.request_ref or a.state not in ('settled', 'unknown_charge', 'cancelled_before_dispatch'):
                    raise ContractError()
                if obj.status == 'complete' and (a.state != 'settled' or a.reasons):
                    raise ContractError()
                if a.state == 'cancelled_before_dispatch' and (obj.status not in ('failed', 'blocked') or obj.response is not None or obj.query_receipts):
                    raise ContractError()
                if ar.sha256 in finished:
                    raise ContractError()
                finished.add(ar.sha256)
            receipt_counts[obj.request_ref.sha256] = receipt_counts.get(obj.request_ref.sha256, 0) + len(obj.query_receipts)
            if any(q.query.name not in r.allowed_queries or q.query.name not in d.ROLE_QUERIES[r.role] or q.query.source_ref not in r.source_refs for q in obj.query_receipts):
                raise ContractError()
            earliest = min(reference(ar, d.AIBudgetAttempt).reserved_at for ar in obj.budget_attempt_refs)
            if any(q.checked_at < earliest or q.checked_at >= r.deadline or q.query.source_ref not in q.resolved_refs for q in obj.query_receipts):
                raise ContractError()
        else:
            r = reference(obj.review_request_ref, d.ResearchRequest)
            origin = reference(obj.exact_result_ref, d.ResearchResult)
            if r.role != 'risk' or r.review_subject_ref != obj.exact_result_ref or obj.reviewer_identity.invocation_id == origin.client_identity.invocation_id or obj.verdict == 'accepted' and origin.status != 'complete':
                raise ContractError()
    for h in book.holds:
        resolve(h, d.AIBudgetAttempt)
    for h, a in attempts.items():
        if (h in finished and h in book.holds) or (h not in finished and a.state != 'cancelled_before_dispatch' and h not in book.holds):
            raise ContractError()
    counts = {}
    for h, count in book.queries:
        resolve(h, d.ResearchRequest)
        counts[h] = _int(count, 0, 16)
    for ah, rs in book.receipts:
        a = resolve(ah, d.AIBudgetAttempt)
        r = reference(a.request_ref, d.ResearchRequest)
        if ah in finished or a.state not in ('dispatched', 'settled', 'unknown_charge') or len(rs) > counts.get(a.request_ref.sha256, 0):
            raise ContractError()
        receipt_counts[a.request_ref.sha256] = receipt_counts.get(a.request_ref.sha256, 0) + len(rs)
        # Match the memory repository's original receipt quota, then charge its
        # base64 transport expansion to the separate auxiliary slot.
        from dataclasses import asdict
        if len(json.dumps([asdict(x) for x in rs], ensure_ascii=False, separators=(',', ':')).encode()) > 32768:
            raise ContractError()
        for receipt in rs:
            _dto(d.encoded(receipt), d.QueryReceipt)
            if (receipt.query.name not in r.allowed_queries or receipt.query.name not in d.ROLE_QUERIES[r.role]
                    or receipt.query.source_ref not in r.source_refs or receipt.checked_at < a.reserved_at
                    or receipt.checked_at >= r.deadline or receipt.query.source_ref not in receipt.resolved_refs):
                raise ContractError()
    if any(count > counts.get(h, 0) for h, count in receipt_counts.items()):
        raise ContractError()
    for ah, reasons in book.denials:
        resolve(ah, d.AIBudgetAttempt)
        unique(reasons)
        if len(reasons) > 64 or any(type(x) is not str or x not in d.REASONS for x in reasons):
            raise ContractError()
    hypotheses = [o for o in objects.values() if type(o) is d.Hypothesis]
    if len(hypotheses) > 8:
        raise ContractError()
    for h in hypotheses:
        origin = reference(h.origin_result_ref, d.ResearchResult)
        r = reference(origin.request_ref, d.ResearchRequest)
        claims = {c.claim_id for c in (*origin.response.numeric_claims, *origin.response.narrative_claims)} if origin.response else set()
        dependencies = set((*r.source_refs, *origin.input_manifest))
        if origin.response:
            dependencies.update(c.source_ref for c in origin.response.numeric_claims)
            for c in origin.response.citations:
                dependencies.update((c.manifest_ref, c.revision_ref, c.observation_ref, c.original_ref, c.context_ref))
        if origin.status not in ('complete', 'partial') or not set((*h.supporting_claim_refs, *h.opposing_claim_refs)) <= claims or not dependencies <= set(h.dependencies):
            raise ContractError()
        for predecessor in (h.supersedes_ref, h.retracts_ref):
            if predecessor:
                prior = reference(predecessor, d.Hypothesis)
                if prior.created_at >= h.created_at or prior.hypothesis_id == h.hypothesis_id:
                    raise ContractError()
    _quota(book, markers)


def _quota(book, markers):
    """Charge shared metadata once and every pending closing slot in full.

    This proves bounds of the *current closed codec*. Admitting new reserve/core
    transitions still requires their monotonic slot/record closure proof (2b-2).
    """
    wire = _wire(book)
    aux = {k: v for k, v in wire.items() if k != 'records'}
    # Attribution: receipts/denials live in their attempt slot. The other closed,
    # hash-normalized arrays plus server markers occupy the global reservation.
    global_part = {k: v for k, v in aux.items() if k not in ('receipts', 'denials')}
    global_part['markers'] = [[m.record_hash, m.kind, m.transition, m.revision] for m in markers]
    global_size = len(_json(global_part))
    if global_size > _GLOBAL:
        raise ContractError()
    per_attempt = {}
    for field in ('receipts', 'denials'):
        for h, value in aux[field]:
            per_attempt[h] = per_attempt.get(h, 0) + len(_json([h, value])) + 64
    if any(n > _SLOT for n in per_attempt.values()):
        raise ContractError()
    # A slot remains a fixed reservation while a closing hold exists. Terminal
    # auxiliary data is retained and charged as actual bytes, never evicted.
    reserved = _GLOBAL + _SLOT*len(book.holds) + sum(n for h, n in per_attempt.items() if h not in book.holds)
    if reserved > _AUX:
        raise ContractError()
    raw_size = sum(len(raw) for _, _, raw in book.records)
    # Each canonical record <=64KiB, total canonical+closing <=8MiB. Base64
    # expansion includes per-record rounding; ID strings may escape to 6 bytes
    # per codepoint (identifier is <=128 chars), covered by global headroom.
    closing = 196608*len(book.holds)
    worst = 4*((raw_size + closing + 2)//3) + 4*128 + reserved + _GLOBAL
    encoded = len(_json(wire))
    if encoded > _ENCODED or worst > _ENCODED:
        raise ContractError()
    return reserved, worst


class _Pipe:
    """Bounded nonblocking psql transport. No communicate/capture_output path."""
    def __init__(self, database):
        self._db = database

    def _exchange(self, fragments, deadline):
        if deadline <= time.monotonic():
            _fail('product_ai_timeout')
        process = None
        try:
            process = subprocess.Popen(self._db._psql(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=self._db._env)
            with selectors.DefaultSelector() as selector:
                for stream in (process.stdin, process.stdout, process.stderr):
                    os.set_blocking(stream.fileno(), False)
                selector.register(process.stdin, selectors.EVENT_WRITE, 'in')
                selector.register(process.stdout, selectors.EVENT_READ, 'out')
                selector.register(process.stderr, selectors.EVENT_READ, 'err')
                iterator, pending, done = iter(fragments), b'', False
                output = bytearray()
                errors = 0
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        _fail('product_ai_timeout')
                    for key, _ in selector.select(min(remaining, 0.1)):
                        if key.data == 'in':
                            if not pending and not done:
                                try:
                                    pending = next(iterator)
                                    if type(pending) is not bytes or len(pending) > 2*_CHUNK + 4096:
                                        _fail('product_ai_transport_input')
                                except StopIteration:
                                    done = True
                            if done and not pending:
                                selector.unregister(key.fileobj)
                                key.fileobj.close()
                            elif pending:
                                try:
                                    n = os.write(key.fd, pending[:_CHUNK])
                                    if n <= 0:
                                        _fail('product_ai_partial_write')
                                    pending = pending[n:]
                                except BlockingIOError:
                                    pass
                        else:
                            try:
                                data = os.read(key.fd, _CHUNK)
                            except BlockingIOError:
                                continue
                            if not data:
                                selector.unregister(key.fileobj)
                            elif key.data == 'out':
                                if len(output)+len(data) > _RESPONSE:
                                    _fail('product_ai_response_capacity')
                                output.extend(data)
                            else:
                                errors += len(data)
                                if errors > _RESPONSE:
                                    _fail('product_ai_response_capacity')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _fail('product_ai_timeout')
                code = process.wait(timeout=remaining)
                if code != 0:
                    _fail('product_ai_command_failed')
                return bytes(output).strip()
        except (OSError, subprocess.TimeoutExpired):
            _fail('product_ai_transport_unknown')
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                # kill + bounded reap; never retain raw stderr in errors/logs.
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()

    def metadata(self, deadline):
        return self._exchange((b'SELECT qh_product.ai_metadata();\n',), deadline)

    def chunk(self, revision, digest, index, deadline):
        _int(revision, 1)
        _hash(digest)
        _int(index, 0, 1023)
        sql = 'SELECT qh_product.ai_chunk(' + str(revision) + ',' + _text(digest) + ',' + str(index) + ');\n'
        return self._exchange((sql.encode(),), deadline)

    def publish(self, revision, opcode, operation_id, digest, raw, record_count, markers, deadline):
        if type(opcode) is not Opcode or opcode is not Opcode.APPEND:
            _fail('product_ai_bridge_required')
        _int(revision)
        _int(record_count, 0, 128)
        _hash(digest)
        if type(operation_id) is not str or re.fullmatch('[0-9a-f]{32}', operation_id) is None or type(raw) is not bytes or not 0 < len(raw) <= _ENCODED:
            raise ContractError()
        marker_wire = [[m.record_hash, m.kind, m.transition, m.revision] for m in markers]
        if type(markers) is not tuple or len(markers) > 128 or len(_json(marker_wire)) > 32768:
            raise ContractError()
        def fragments():
            yield b"BEGIN; SET LOCAL statement_timeout='15s'; SET LOCAL lock_timeout='10s';\nCREATE TEMP TABLE ai_stage (idx integer PRIMARY KEY CHECK(idx BETWEEN 0 AND 1023), payload bytea NOT NULL CHECK(octet_length(payload) BETWEEN 1 AND 32768)) ON COMMIT DROP;\n"
            for index, start in enumerate(range(0, len(raw), _CHUNK)):
                yield ("INSERT INTO ai_stage VALUES(" + str(index) + ",decode('" + raw[start:start+_CHUNK].hex() + "','hex'));\n").encode()
            yield ("SELECT qh_product.ai_publish(" + str(revision) + ',' + _text(opcode.value) + ',' + _text(operation_id) + ',' + _text(digest) + ",(SELECT string_agg(payload,''::bytea ORDER BY idx) FROM ai_stage)," + str(record_count) + ',' + _text(_json(marker_wire).decode()) + "::jsonb);\nCOMMIT;\nSELECT 'ai_ack:" + operation_id + ':' + str(revision+1) + ':' + sha256(raw).hexdigest() + "';\n").encode()
        return self._exchange(fragments(), deadline)


class _Shared:
    def __init__(self, generation):
        self.generation, self.lock, self.failed = generation, RLock(), False


@dataclass(frozen=True, slots=True)
class _Phase:
    store: object
    owner: object
    generation: object
    opcode: Opcode
    operation_id: str
    input_digest: str
    revision: int
    book: _Book
    markers: tuple


class ProductAIStore:
    """Internal DB-bound store. No AI core factory/execute bridge in 2b-1.

    append accepts only typed request/policy, never a book, memory repository,
    restore mapping, processed flag, arbitrary SQL, DSN or book identifier.
    """
    def __init__(self, database, *, capacity=128, byte_capacity=8388608):
        _int(capacity, 1, 128)
        _int(byte_capacity, 1, 8388608)
        if type(database) is not PostgresLedger:
            raise ContractError()
        self._db, self._generation = database, database._product_generation
        self._capacity, self._byte_capacity = capacity, byte_capacity
        self._owner = object()
        self._pipe = _Pipe(database)
        self._shared = None
        self._active_phase = None

    @classmethod
    def product_synthetic(cls, database, *, capacity=128, byte_capacity=8388608):
        deadline = time.monotonic()+_DEADLINE
        store = cls(database, capacity=capacity, byte_capacity=byte_capacity)
        with _timed_lock(database._product_gate, deadline):
            store._check()
            shared = getattr(database, '_product_ai_shared', None)
            if type(shared) is not _Shared or shared.generation is not store._generation:
                shared = _Shared(store._generation)
                database._product_ai_shared = shared
            store._shared = shared
            with _timed_lock(shared.lock, deadline):
                store._check()
                try:
                    ensure_schema(database, _execute=lambda sql: store._pipe._exchange((sql.encode(),), deadline))
                    _alive(deadline)
                    store._read(deadline)
                except BaseException:
                    shared.failed = True
                    raise
        return store

    def _check(self):
        p = self._db._product_database
        if (type(self._db) is not PostgresLedger or type(p) is not ProductDatabase or not self._db._ready
                or not p.active or p.lock is None or p.fd is None or self._db._compose is None
                or self._generation is None or self._generation is not self._db._product_generation):
            _fail('product_ai_database_unavailable')
        if self._shared is not None and (self._shared.generation is not self._generation or self._shared.failed):
            _fail('product_ai_failed_latch')

    def _read(self, deadline):
        _alive(deadline)
        self._check()
        try:
            meta = _parse(self._pipe.metadata(deadline))
            if type(meta) is not dict or set(meta) != {'codec', 'record_count', 'chunk_count', 'marker_count', 'revision', 'length', 'hash', 'operation_id', 'input_digest', 'opcode', 'markers'}:
                raise ContractError()
            revision, length = _int(meta['revision']), _int(meta['length'], 0, _ENCODED)
            _int(meta['codec'], 1, 1)
            record_count = _int(meta['record_count'], 0, 128)
            chunk_count = _int(meta['chunk_count'], 0, 1024)
            marker_count = _int(meta['marker_count'], 0, record_count)
            markers = tuple(_Marker(*x) for x in _rows(meta['markers'], 4))
            if marker_count != len(markers) or chunk_count != (length+_CHUNK-1)//_CHUNK:
                raise ContractError()
            if revision == 0:
                if length or record_count or markers or any(meta[k] is not None for k in ('hash', 'operation_id', 'input_digest', 'opcode')):
                    raise ContractError()
                _alive(deadline)
                return _Book(), (), meta
            _hash(meta['hash'])
            _hash(meta['input_digest'])
            if not length or type(meta['operation_id']) is not str or re.fullmatch('[0-9a-f]{32}', meta['operation_id']) is None or meta['opcode'] not in {o.value for o in Opcode}:
                raise ContractError()
            chunks = bytearray()
            for index in range((length+_CHUNK-1)//_CHUNK):
                part = _parse(self._pipe.chunk(revision, meta['hash'], index, deadline))
                if type(part) is not list or len(part) != 4 or type(part[0]) is not int or type(part[2]) is not int or part[:3] != [revision, meta['hash'], index] or type(part[3]) is not str:
                    raise ContractError()
                size = min(_CHUNK, length-len(chunks))
                if len(part[3]) != 2*size or re.fullmatch('[0-9a-f]+', part[3]) is None:
                    raise ContractError()
                chunks.extend(bytes.fromhex(part[3]))
            if len(chunks) != length or sha256(chunks).hexdigest() != meta['hash']:
                raise ContractError()
            book = _decode(bytes(chunks), markers, revision)
            if len(book.records) != record_count:
                raise ContractError()
            _alive(deadline)
            self._check()
            return book, markers, meta
        except (ContractError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            _fail()

    def read_records(self):
        deadline = time.monotonic()+_DEADLINE
        if self._shared is None:
            _fail('product_ai_factory_required')
        with _timed_lock(self._db._product_gate, deadline), _timed_lock(self._shared.lock, deadline):
            self._check()
            try:
                book, _, meta = self._read(deadline)
                _alive(deadline)
                return meta['revision'], tuple(book.records)
            except BaseException:
                self._shared.failed = True
                raise

    def append(self, kind, obj, *, expected_revision):
        deadline = time.monotonic()+_DEADLINE
        if self._shared is None:
            _fail('product_ai_factory_required')
        if type(kind) is not str or kind not in ('request', 'budget_policy') or type(obj) is not _TYPES[kind]:
            raise ContractError()
        _int(expected_revision)
        raw = d.encoded(obj)
        _dto(raw, _TYPES[kind])
        identity = getattr(obj, _IDS[kind])
        digest = sha256(_json([kind, identity, _b64(raw)])).hexdigest()
        with _timed_lock(self._db._product_gate, deadline), _timed_lock(self._shared.lock, deadline):
            self._check()
            try:
                book, markers, meta = self._read(deadline)
                if meta['revision'] != expected_revision:
                    _fail('product_ai_stale_revision')
                for k, i, prior in book.records:
                    if (k, i) == (kind, identity):
                        if prior != raw:
                            raise ContractError()
                        return expected_revision
                phase = _Phase(self, self._owner, self._generation, Opcode.APPEND, uuid.uuid4().hex,
                    digest, expected_revision, book, markers)
                proposed = replace(book, records=tuple(sorted((*book.records, (kind, identity, raw)))))
                self._active_phase = phase
                try:
                    return self._commit(phase, proposed, deadline)
                finally:
                    self._active_phase = None
            except ContractError:
                raise
            except LedgerStorageError as error:
                if error.reason != 'product_ai_stale_revision':
                    self._shared.failed = True
                raise
            except BaseException:
                self._shared.failed = True
                raise

    def _commit(self, phase, proposed, deadline):
        self._check()
        if (type(phase) is not _Phase or phase is not self._active_phase or phase.store is not self or phase.owner is not self._owner
                or phase.generation is not self._generation or phase.opcode is not Opcode.APPEND):
            _fail('product_ai_phase_invalid')
        # No generic candidate-book commit: ordinary append may add exactly one
        # request/policy and cannot alter any auxiliary state or create markers.
        old = {(k, i): raw for k, i, raw in phase.book.records}
        new = {(k, i): raw for k, i, raw in proposed.records}
        added = new.keys()-old.keys()
        if (len(added) != 1 or any(new.get(k) != v for k, v in old.items())
                or next(iter(added))[0] not in ('request', 'budget_policy')
                or replace(proposed, records=phase.book.records) != phase.book):
            _fail('product_ai_phase_invalid')
        _validate(proposed, phase.markers, phase.revision+1, capacity=self._capacity, byte_capacity=self._byte_capacity)
        raw = _json(_wire(proposed))
        _alive(deadline)
        expected_hash = sha256(raw).hexdigest()
        ack = ('ai_ack:' + phase.operation_id + ':' + str(phase.revision+1) + ':' + expected_hash).encode()
        acknowledged = False
        try:
            acknowledged = self._pipe.publish(phase.revision, phase.opcode, phase.operation_id, phase.input_digest, raw, len(proposed.records), phase.markers, deadline) == ack
        except LedgerStorageError:
            pass
        # A bounded readback is required even after an ack; never replay a write.
        # All commands and confirmation share the same operation deadline.
        try:
            confirmed, markers, meta = self._read(deadline)
            if (meta['revision'] == phase.revision+1 and meta['operation_id'] == phase.operation_id
                    and meta['input_digest'] == phase.input_digest and meta['opcode'] == phase.opcode.value
                    and meta['hash'] == expected_hash and confirmed == proposed and markers == phase.markers):
                self._check()
                _alive(deadline)
                return meta['revision']
        except LedgerStorageError:
            pass
        self._shared.failed = True
        _fail('product_ai_commit_unknown' if not acknowledged else 'product_ai_confirmation_failed')
