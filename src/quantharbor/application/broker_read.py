"""Q19 고정 합성 조회 조정. 실제 transport/키 주입/원장 변경은 제공하지 않는다."""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from quantharbor.adapters.kis_read import DecodeError, decode_page
from quantharbor.adapters.synthetic_broker import FixtureTransport
from quantharbor.domain.broker_read import (
    BrokerCursor, BrokerObservation, BrokerPageReceipt, BrokerQueryResult, BrokerReadBatch,
    BrokerReadBinding, BrokerReadCapability, BrokerReadRequest, SUPPORTED, exact,
)
from quantharbor.domain.market_data import sequence, record_hash
from quantharbor.domain.primitives import ContractError, identifier, utc_instant
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes


def _seconds(start, end):
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def _fact(item: BrokerObservation):
    # Compare source observations without arrival time; never subtract or sum quantities.
    return (item.kind, item.source_section, item.source_symbol, item.venue, item.currency,
            item.numbers, item.order_date, item.order_branch, item.order_number,
            item.original_order_number)


def _fact_key(item):
    if item.kind == 'order_cumulative':
        return (item.kind, item.order_date, item.order_branch, item.order_number)
    return (item.kind, item.source_section, item.source_symbol, item.venue, item.currency)


def _finish(request, request_hash, at, receipts, items, reasons, continuation=None,
            *, unsupported=False, force_error=False):
    reasons = tuple(dict.fromkeys(reasons))
    complete = not reasons
    accepted = any(r.validation == 'accepted' for r in receipts)
    status = ('unsupported' if unsupported else 'error' if force_error else 'success' if complete
              else 'unknown' if len(receipts) == 1 and accepted and any(code in reasons for code in
                  ('terminal_unverified', 'continuation_unverified', 'cursor_missing', 'cursor_repeated'))
              else 'partial' if accepted else 'error' if any(r.validation == 'rejected' for r in receipts)
              else 'unknown')
    result = BrokerQueryResult(request.query_id, request.environment, request.binding.account_ref,
        request.binding.capability_version, request.scope, tuple(items), status, complete, continuation,
        len(receipts), request.requested_at, at, None,
        'bounded_observation' if accepted else 'unknown', reasons[0] if reasons else None,
        'synthetic-evidence:' + request_hash)
    batch = BrokerReadBatch(1, 'synthetic', request, request_hash, result, tuple(receipts),
        () if complete else (request.scope.coverage,), reasons)
    try:
        canonical_bytes(CanonicalPayload('BrokerReadBatch', 1, 'synthetic', batch))
    except ContractError:
        if force_error:
            raise ContractError() from None
        # Explicit representation failure, never a truncated successful result.
        return _finish(request, request_hash, at, receipts, (), ('output_oversize',),
                       continuation, force_error=True)
    return batch


def read_broker(request: BrokerReadRequest, capability: BrokerReadCapability,
                transport: FixtureTransport, *, evaluated_at: str) -> BrokerReadBatch:
    """명시된 합성 시각과 고정 fixture만 소비한다. callback/port 대체 주입은 거부한다.

    모든 수신시각은 evaluated_at 이전이며 요청 이후여야 한다. 설정 한도에 도달하면
    종료 fixture가 있어도 complete로 승격하지 않는다. 오류 페이지 전의 관측은 보존한다.
    """
    exact(request, BrokerReadRequest)
    exact(capability, BrokerReadCapability)
    exact(transport, FixtureTransport)
    now = utc_instant(evaluated_at)
    if (capability.binding, capability.operation, capability.scope) != (request.binding, request.operation, request.scope):
        raise ContractError()
    if not capability.valid_from <= request.requested_at <= now < capability.expires_at or not now <= request.deadline_at:
        raise ContractError()
    request_hash = record_hash(request)
    if request.operation not in SUPPORTED or capability.support != 'synthetic_supported':
        return _finish(request, request_hash, now, (), (), ('unsupported',), unsupported=True)
    capability.authorize(request, now)
    if _seconds(request.requested_at, now) >= capability.max_seconds:
        return _finish(request, request_hash, now, (), (), ('time_limit',))
    receipts, items, reasons = [], [], []
    received_bytes = received_rows = 0
    cursor = BrokerCursor('', '')
    seen_cursors = {cursor}
    seen_facts = {}
    prior = request.requested_at
    maximum = min(capability.max_pages, capability.max_calls)
    continuation = None
    for index in range(maximum):
        page = transport.fetch(request, cursor, index)
        if page is None:
            reasons.append('missing_response')
            break
        reason = None
        if not prior <= page.received_at <= now or page.received_at > request.deadline_at:
            reason = 'clock_invalid'
        elif page.received_at >= capability.expires_at:
            reason = 'expired'
        elif _seconds(request.requested_at, page.received_at) >= capability.max_seconds:
            reason = 'time_limit'
        elif len(page.raw_body) >= 65536 or received_bytes + len(page.raw_body) > capability.max_bytes:
            reason = 'byte_limit'
        decoded = None
        rejected_rows = 0
        if reason is None:
            try:
                decoded = decode_page(page)
            except DecodeError as failure:
                reason = failure.reason
                rejected_rows = failure.received_rows
        if decoded is not None and received_rows + decoded.received_rows > capability.max_rows:
            reason = 'row_limit'
        accepted = reason is None
        receipt = BrokerPageReceipt(request_hash, index, cursor,
            decoded.response_cursor if decoded else None, page.received_at,
            sha256(page.raw_body).hexdigest(), len(page.raw_body),
            decoded.received_rows if decoded else rejected_rows,
            'accepted' if accepted else 'rejected', reason,
            decoded.account_evidence if decoded else 'unverified',
            page.tr_cont if page.tr_cont in ('', 'M', 'F') else 'unknown', page.terminal_evidence)
        receipts.append(receipt)
        received_bytes += len(page.raw_body)
        if not accepted:
            reasons.append(reason)
            break
        prior = page.received_at
        received_rows += decoded.received_rows
        reasons.extend(decoded.reasons)
        for item in decoded.items:
            key, fact = _fact_key(item), _fact(item)
            if key in seen_facts:
                reasons.append('duplicate_observation' if fact in seen_facts[key] else 'conflicting_observation')
            seen_facts.setdefault(key, []).append(fact)
            items.append(item)
        if received_rows >= capability.max_rows:
            reasons.append('row_limit')
        if received_bytes >= capability.max_bytes:
            reasons.append('byte_limit')
        if index + 1 >= maximum:
            reasons.append('page_limit')
        if page.tr_cont in ('M', 'F'):
            continuation = decoded.response_cursor
            if request.operation in ('us_present_balance', 'kr_buy_capacity'):
                reasons.append('continuation_unverified')
                break
            if continuation is None or not continuation.forward:
                reasons.append('cursor_missing')
                break
            if continuation in seen_cursors:
                reasons.append('cursor_repeated')
                break
            seen_cursors.add(continuation)
            cursor = continuation
            if any(code in reasons for code in ('row_limit', 'byte_limit', 'page_limit')):
                break
            continue
        continuation = None
        if page.tr_cont != '' or page.terminal_evidence != 'synthetic_terminal_v1':
            reasons.append('terminal_unverified')
        break
    return _finish(request, request_hash, now, receipts, items, reasons, continuation)


_READINESS_MISSING = ('PG01', 'SG01', 'SG02', 'AP05', 'private_injection',
                      'encryption_key_management', 'retention_restore')


@dataclass(frozen=True, slots=True)
class ConnectionReadiness:
    """Serializer 밖의 미연결 보고. 사용자 권한/자격 증명을 받지 않는다."""
    account_ref: str
    checked_at: str
    target_environment: str = 'paper'
    missing_requirements: tuple[str, ...] = _READINESS_MISSING
    evidence_refs: tuple[str, ...] = ('synthetic-local-only',)
    real_transport_available: bool = False
    connectable: bool = False

    def __post_init__(self):
        identifier(self.account_ref)
        if not self.account_ref.startswith('synthetic-account:') or self.account_ref == 'synthetic-account:':
            raise ContractError()
        object.__setattr__(self, 'checked_at', utc_instant(self.checked_at))
        if self.target_environment != 'paper' or self.missing_requirements != _READINESS_MISSING:
            raise ContractError()
        sequence(self.evidence_refs, str, 8, True)
        if (type(self.real_transport_available) is not bool or self.real_transport_available
                or type(self.connectable) is not bool or self.connectable):
            raise ContractError()


def connection_readiness(binding: BrokerReadBinding, *, checked_at: str) -> ConnectionReadiness:
    exact(binding, BrokerReadBinding)
    return ConnectionReadiness(binding.account_ref, checked_at)
