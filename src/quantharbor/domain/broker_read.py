"""Q19 합성 증권사 조회 사실. 원장·주문·실제 계좌 권한을 만들지 않는다."""
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from .primitives import ContractError, calendar_date, decimal_string, identifier, utc_instant
from .market_data import count, digest, enum, header, sequence, stamp, record_hash

OPERATIONS = ('kr_balance', 'kr_orders', 'kr_buy_capacity', 'us_balance', 'us_orders',
              'us_present_balance', 'kr_amendable_orders', 'us_open_orders',
              'us_settlement_balance', 'individual_executions')
SUPPORTED = OPERATIONS[:6]
REGISTRY_VERSION = 'kis-read-synthetic-v1'
REASONS = ('unsupported', 'schema_mismatch', 'source_error', 'missing_response', 'clock_invalid',
           'expired', 'page_limit', 'row_limit', 'byte_limit', 'time_limit', 'cursor_missing',
           'cursor_repeated', 'continuation_unverified', 'terminal_unverified', 'missing_fact',
           'duplicate_observation', 'conflicting_observation', 'account_mismatch',
           'account_unverified', 'output_oversize')


# One immutable numeric/identity contract shared by domain validation and wire decoding.
# Values: kind, required numeric fields, optional numeric fields, complete-row identity properties.
SOURCE_FIELDS = MappingProxyType({
    ('kr_balance', 'output1'): ('holding', ('hldg_qty', 'ord_psbl_qty'), (),
        ('source_symbol', 'venue', 'currency')),
    ('kr_balance', 'output2'): ('cash', ('dnca_tot_amt', 'nxdy_excc_amt', 'prvs_rcdl_excc_amt'), (),
        ('venue', 'currency')),
    ('kr_orders', 'output1'): ('order_cumulative', ('ord_qty', 'tot_ccld_qty', 'rmn_qty'), (),
        ('source_symbol', 'venue', 'currency', 'order_date', 'order_branch', 'order_number', 'original_order_number')),
    ('kr_orders', 'output2'): ('cash', ('tot_ord_qty', 'tot_ccld_qty', 'tot_ccld_amt', 'prsm_tlex_smtl', 'pchs_avg_pric'), (),
        ('venue', 'currency')),
    ('kr_buy_capacity', 'output'): ('buy_capacity',
        ('ord_psbl_cash', 'ord_psbl_sbst', 'ruse_psbl_amt', 'fund_rpch_chgs', 'psbl_qty_calc_unpr',
         'nrcvb_buy_amt', 'nrcvb_buy_qty', 'max_buy_amt', 'max_buy_qty', 'cma_evlu_amt',
         'ovrs_re_use_amt_wcrc', 'ord_psbl_frcr_amt_wcrc'), (), ('source_symbol', 'venue', 'currency')),
    ('us_balance', 'output1'): ('holding', ('ovrs_cblc_qty', 'ord_psbl_qty'), (),
        ('source_symbol', 'venue', 'currency')),
    ('us_balance', 'output2'): ('cash', ('ovrs_rlzt_pfls_amt', 'ovrs_tot_pfls', 'rlzt_erng_rt',
        'tot_evlu_pfls_amt', 'tot_pftrt', 'frcr_buy_amt_smtl1', 'ovrs_rlzt_pfls_amt2', 'frcr_buy_amt_smtl2'), (), ()),
    ('us_orders', 'output'): ('order_cumulative', ('ft_ord_qty', 'ft_ccld_qty', 'nccs_qty'), (),
        ('source_symbol', 'venue', 'currency', 'order_date', 'order_branch', 'order_number', 'original_order_number')),
    ('us_present_balance', 'output1'): ('holding', ('cblc_qty13', 'ord_psbl_qty1'), (),
        ('source_symbol', 'venue', 'currency')),
    ('us_present_balance', 'output2'): ('cash',
        ('frcr_dncl_amt_2', 'frcr_drwg_psbl_amt_1', 'nxdy_frcr_drwg_psbl_amt'), ('frcr_evlu_amt2',), ('currency',)),
    ('us_present_balance', 'output3'): ('cash', ('frcr_use_psbl_amt',), (), ()),
})


def numeric_fields(operation, section):
    profile = SOURCE_FIELDS.get((operation, section))
    if profile is None:
        raise ContractError()
    return profile[1] + profile[2]


def exact(value, cls):
    if type(value) is not cls:
        raise ContractError()
    # Constructors and canonical reconstruction both enforce nested invariants.
    from dataclasses import fields
    cls(**{f.name: getattr(value, f.name) for f in fields(cls)})


def nullable_id(value):
    if value is not None:
        identifier(value)


@dataclass(frozen=True, slots=True)
class BrokerReadBinding:
    binding_version: str
    environment: str
    broker: str
    account_ref: str
    capability_version: str
    wire_profile: str
    endpoint_registry_version: str
    catalog_version: str

    def __post_init__(self):
        enum(self.binding_version, ('broker-read-binding-v1',))
        enum(self.environment, ('synthetic',))
        enum(self.broker, ('kis',))
        enum(self.wire_profile, ('paper',))
        enum(self.endpoint_registry_version, (REGISTRY_VERSION,))
        identifier(self.account_ref)
        if not self.account_ref.startswith('synthetic-account:') or self.account_ref == 'synthetic-account:':
            raise ContractError()
        identifier(self.capability_version)
        identifier(self.catalog_version)


@dataclass(frozen=True, slots=True)
class BrokerReadScope:
    coverage: str
    market: str
    currency: str
    exchange: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    period_class: str | None = None
    symbol: str | None = None
    price: str | None = None
    order_kind: str | None = None

    def __post_init__(self):
        enum(self.coverage, ('market_balance', 'cash_orders', 'broker_overseas_all', 'buy_capacity', 'unsupported'))
        enum(self.market, ('KR', 'US', 'overseas', 'unknown'))
        enum(self.currency, ('KRW', 'USD', 'source'))
        if self.exchange is not None:
            enum(self.exchange, ('KRX', 'NASD', 'NYSE', 'AMEX'))
        if (self.start_date is None) != (self.end_date is None):
            raise ContractError()
        for date in (self.start_date, self.end_date):
            if date is not None:
                calendar_date(date)
        if self.start_date is not None and self.start_date > self.end_date:
            raise ContractError()
        if self.period_class is not None:
            enum(self.period_class, ('inner', 'before'))
        nullable_id(self.symbol)
        if self.price is not None:
            object.__setattr__(self, 'price', decimal_string(self.price))
            if self.price.startswith('-'):
                raise ContractError()
        if self.order_kind is not None:
            enum(self.order_kind, ('01',))

    def for_operation(self, operation):
        enum(operation, OPERATIONS)
        expected = {
            'kr_balance': ('market_balance', 'KR', 'KRW', None),
            'kr_orders': ('cash_orders', 'KR', 'KRW', 'KRX'),
            'kr_buy_capacity': ('buy_capacity', 'KR', 'KRW', 'KRX'),
            'us_balance': ('market_balance', 'US', 'USD', self.exchange),
            'us_orders': ('broker_overseas_all', 'overseas', 'source', None),
            'us_present_balance': ('market_balance', 'US', 'USD', None),
        }
        if operation not in expected:
            if self != BrokerReadScope('unsupported', 'unknown', 'source'):
                raise ContractError()
            return
        if (self.coverage, self.market, self.currency, self.exchange) != expected[operation]:
            raise ContractError()
        if operation == 'us_balance' and self.exchange not in ('NASD', 'NYSE', 'AMEX'):
            raise ContractError()
        orders = operation in ('kr_orders', 'us_orders')
        if orders != (self.start_date is not None):
            raise ContractError()
        if (operation == 'kr_orders') != (self.period_class is not None):
            raise ContractError()
        buying = operation == 'kr_buy_capacity'
        if any((x is not None) != buying for x in (self.symbol, self.price, self.order_kind)):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class BrokerReadCapability:
    schema_version: int
    environment: str
    binding: BrokerReadBinding
    operation: str
    scope: BrokerReadScope
    support: str
    evidence_ref: str
    valid_from: str
    expires_at: str
    max_calls: int = 4
    max_pages: int = 4
    max_rows: int = 32
    max_bytes: int = 262144
    max_seconds: int = 30

    def __post_init__(self):
        header(self)
        exact(self.binding, BrokerReadBinding)
        exact(self.scope, BrokerReadScope)
        self.scope.for_operation(self.operation)
        enum(self.support, ('synthetic_supported', 'unconfirmed', 'unsupported'))
        if self.operation not in SUPPORTED and self.support == 'synthetic_supported':
            raise ContractError()
        identifier(self.evidence_ref)
        stamp(self, 'valid_from', 'expires_at')
        if self.valid_from >= self.expires_at:
            raise ContractError()
        for name, maximum in (('max_calls', 4), ('max_pages', 4), ('max_rows', 32),
                              ('max_bytes', 262144), ('max_seconds', 30)):
            count(getattr(self, name), maximum)
            if getattr(self, name) == 0:
                raise ContractError()

    def authorize(self, request, evaluated_at):
        exact(self, BrokerReadCapability)
        exact(request, BrokerReadRequest)
        now = utc_instant(evaluated_at)
        if (self.binding != request.binding or self.operation != request.operation or self.scope != request.scope
                or self.support != 'synthetic_supported' or not self.valid_from <= request.requested_at <= now < self.expires_at
                or not request.requested_at <= now <= request.deadline_at):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class BrokerReadRequest:
    schema_version: int
    environment: str
    query_id: str
    binding: BrokerReadBinding
    operation: str
    scope: BrokerReadScope
    requested_at: str
    deadline_at: str

    def __post_init__(self):
        header(self)
        identifier(self.query_id)
        exact(self.binding, BrokerReadBinding)
        exact(self.scope, BrokerReadScope)
        self.scope.for_operation(self.operation)
        stamp(self, 'requested_at', 'deadline_at')
        span = (datetime.fromisoformat(self.deadline_at) - datetime.fromisoformat(self.requested_at)).total_seconds()
        if not 0 < span <= 30:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class BrokerCursor:
    forward: str
    next: str

    def __post_init__(self):
        for value in (self.forward, self.next):
            if type(value) is not str or len(value) > 128 or (value and not all(32 <= ord(c) < 127 for c in value)):
                raise ContractError()
        if bool(self.forward) != bool(self.next):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class SourceNumber:
    source_field: str
    value: str | None
    missing_reason: str | None
    currency: str | None
    unit: str | None
    semantic_status: str = 'source_only'

    def __post_init__(self):
        identifier(self.source_field)
        enum(self.semantic_status, ('source_only', 'unknown'))
        if self.value is None:
            enum(self.missing_reason, ('absent', 'null', 'empty'))
        else:
            object.__setattr__(self, 'value', decimal_string(self.value))
            if self.missing_reason is not None:
                raise ContractError()
        if self.currency is not None:
            enum(self.currency, ('KRW', 'USD'))
        nullable_id(self.unit)


@dataclass(frozen=True, slots=True)
class BrokerObservation:
    query_id: str
    binding: BrokerReadBinding
    operation: str
    scope: BrokerReadScope
    kind: str
    source_section: str
    row_key: str
    source_symbol: str | None
    venue: str | None
    currency: str | None
    observed_at: str
    numbers: tuple[SourceNumber, ...]
    order_date: str | None = None
    order_branch: str | None = None
    order_number: str | None = None
    original_order_number: str | None = None
    mapping_status: str = 'mapping_unknown'
    instrument_id: None = None
    execution_granularity: str = 'not_applicable'
    individual_execution_id: None = None
    settlement_inclusion: str = 'unknown'
    reservation_inclusion: str = 'unknown'
    usable_for_internal_available_cash: bool = False

    def __post_init__(self):
        identifier(self.query_id)
        exact(self.binding, BrokerReadBinding)
        exact(self.scope, BrokerReadScope)
        self.scope.for_operation(self.operation)
        enum(self.kind, ('holding', 'cash', 'order_cumulative', 'buy_capacity'))
        enum(self.source_section, ('output', 'output1', 'output2', 'output3'))
        profile = SOURCE_FIELDS.get((self.operation, self.source_section))
        if profile is None or self.kind != profile[0]:
            raise ContractError()
        identifier(self.row_key)
        for value in (self.source_symbol, self.venue, self.order_branch, self.order_number, self.original_order_number):
            nullable_id(value)
        if self.currency is not None:
            enum(self.currency, ('KRW', 'USD'))
        if self.order_date is not None:
            calendar_date(self.order_date)
        expected_currency = expected_venues = None
        if self.operation.startswith('kr_'):
            expected_currency, expected_venues = 'KRW', ('KRX',)
        elif self.operation == 'us_balance':
            expected_currency, expected_venues = 'USD', (self.scope.exchange,)
        elif self.operation == 'us_present_balance':
            expected_currency, expected_venues = 'USD', ('NASD', 'NYSE', 'AMEX')
        if self.currency is not None and expected_currency is not None and self.currency != expected_currency:
            raise ContractError()
        if self.venue is not None and expected_venues is not None and self.venue not in expected_venues:
            raise ContractError()
        if self.operation == 'kr_buy_capacity' and self.source_symbol is not None and self.source_symbol != self.scope.symbol:
            raise ContractError()
        stamp(self, 'observed_at')
        sequence(self.numbers, SourceNumber, 64)
        for value in self.numbers:
            exact(value, SourceNumber)
        present_fields = {x.source_field for x in self.numbers}
        if len(present_fields) != len(self.numbers) or present_fields - set(profile[1] + profile[2]):
            raise ContractError()
        enum(self.mapping_status, ('mapping_unknown',))
        if self.instrument_id is not None or self.individual_execution_id is not None:
            raise ContractError()
        enum(self.execution_granularity, ('order_cumulative',) if self.kind == 'order_cumulative' else ('not_applicable',))
        enum(self.settlement_inclusion, ('unknown',))
        enum(self.reservation_inclusion, ('unknown',))
        if type(self.usable_for_internal_available_cash) is not bool or self.usable_for_internal_available_cash:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class BrokerPageReceipt:
    request_hash: str
    page_index: int
    request_cursor: BrokerCursor
    response_cursor: BrokerCursor | None
    received_at: str
    body_sha256: str
    received_bytes: int
    received_rows: int
    validation: str
    reason: str | None
    account_evidence: str
    wire_marker: str
    terminal_evidence: str | None

    def __post_init__(self):
        digest(self.request_hash)
        count(self.page_index, 3)
        exact(self.request_cursor, BrokerCursor)
        if self.response_cursor is not None:
            exact(self.response_cursor, BrokerCursor)
        stamp(self, 'received_at')
        digest(self.body_sha256)
        count(self.received_bytes)
        count(self.received_rows, 100000)
        enum(self.validation, ('accepted', 'rejected'))
        if self.reason is not None:
            enum(self.reason, REASONS)
        if (self.validation == 'rejected') != (self.reason is not None):
            raise ContractError()
        enum(self.account_evidence, ('request_bound_only', 'synthetic_echo_verified', 'unverified'))
        enum(self.wire_marker, ('', 'M', 'F', 'unknown'))
        if self.terminal_evidence is not None:
            enum(self.terminal_evidence, ('synthetic_terminal_v1',))


@dataclass(frozen=True, slots=True)
class BrokerQueryResult:
    query_id: str
    environment: str
    account_ref: str
    capability_version: str
    queried_scope: BrokerReadScope
    items: tuple[BrokerObservation, ...]
    status: str
    complete: bool
    continuation: BrokerCursor | None
    pages_fetched: int
    started_at: str
    finished_at: str
    source_as_of: None
    temporal_consistency: str
    source_error: str | None
    raw_reference: str

    def __post_init__(self):
        identifier(self.query_id)
        enum(self.environment, ('synthetic',))
        for value in (self.account_ref, self.capability_version, self.raw_reference):
            identifier(value)
        exact(self.queried_scope, BrokerReadScope)
        sequence(self.items, BrokerObservation, 32)
        for item in self.items:
            exact(item, BrokerObservation)
        enum(self.status, ('success', 'partial', 'error', 'unsupported', 'unknown'))
        if type(self.complete) is not bool or (self.status == 'success') != self.complete:
            raise ContractError()
        if self.continuation is not None:
            exact(self.continuation, BrokerCursor)
        count(self.pages_fetched, 4)
        stamp(self, 'started_at', 'finished_at')
        if self.finished_at < self.started_at or self.source_as_of is not None:
            raise ContractError()
        enum(self.temporal_consistency, ('bounded_observation', 'unknown'))
        if self.source_error is not None:
            enum(self.source_error, REASONS)


@dataclass(frozen=True, slots=True)
class BrokerReadBatch:
    schema_version: int
    environment: str
    request: BrokerReadRequest
    request_hash: str
    result: BrokerQueryResult
    page_receipts: tuple[BrokerPageReceipt, ...]
    missing_scope: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        header(self)
        exact(self.request, BrokerReadRequest)
        digest(self.request_hash)
        if self.request_hash != record_hash(self.request):
            raise ContractError()
        exact(self.result, BrokerQueryResult)
        sequence(self.page_receipts, BrokerPageReceipt, 4)
        sequence(self.missing_scope, str, 1, True)
        sequence(self.reason_codes, str, len(REASONS), True)
        for reason in self.reason_codes:
            enum(reason, REASONS)
        req, result = self.request, self.result
        if (result.query_id, result.environment, result.account_ref, result.capability_version, result.queried_scope) != (
                req.query_id, req.environment, req.binding.account_ref, req.binding.capability_version, req.scope):
            raise ContractError()
        if result.source_error != (self.reason_codes[0] if self.reason_codes else None):
            raise ContractError()
        if result.finished_at > req.deadline_at:
            raise ContractError()
        if result.started_at != req.requested_at or result.pages_fetched != len(self.page_receipts):
            raise ContractError()
        prior = req.requested_at
        accepted_times = []
        for i, receipt in enumerate(self.page_receipts):
            exact(receipt, BrokerPageReceipt)
            if receipt.request_hash != self.request_hash or receipt.page_index != i:
                raise ContractError()
            if i == 0:
                if receipt.request_cursor != BrokerCursor('', ''):
                    raise ContractError()
            else:
                previous = self.page_receipts[i - 1]
                if (previous.validation != 'accepted' or previous.wire_marker not in ('M', 'F')
                        or receipt.request_cursor != previous.response_cursor):
                    raise ContractError()
            if receipt.validation == 'accepted':
                if not prior <= receipt.received_at <= result.finished_at <= req.deadline_at:
                    raise ContractError()
                prior = receipt.received_at
                accepted_times.append(receipt.received_at)
        for item in result.items:
            if (item.query_id, item.binding, item.operation, item.scope) != (req.query_id, req.binding, req.operation, req.scope):
                raise ContractError()
            if item.observed_at not in accepted_times:
                raise ContractError()
        if result.complete:
            if req.operation not in SUPPORTED:
                raise ContractError()
            if req.operation in ('kr_buy_capacity', 'us_present_balance') and len(self.page_receipts) != 1:
                raise ContractError()
            if self.reason_codes or self.missing_scope or not self.page_receipts or result.continuation is not None:
                raise ContractError()
            if (len(self.page_receipts) >= 4 or sum(r.received_rows for r in self.page_receipts) >= 32
                    or sum(r.received_rows for r in self.page_receipts) != len(result.items)
                    or any(r.received_bytes >= 65536 or r.account_evidence == 'unverified' for r in self.page_receipts)
                    or (datetime.fromisoformat(result.finished_at) - datetime.fromisoformat(result.started_at)).total_seconds() >= 30):
                raise ContractError()
            # The schema has timestamps, not an item page ID. Bind exact timestamp groups;
            # equal-time pages are legitimate and contribute their summed row/section counts.
            receipt_rows, receipt_pages, observed_rows = {}, {}, {}
            for receipt in self.page_receipts:
                if receipt.validation == 'accepted':
                    at = receipt.received_at
                    receipt_rows[at] = receipt_rows.get(at, 0) + receipt.received_rows
                    receipt_pages[at] = receipt_pages.get(at, 0) + 1
            for item in result.items:
                observed_rows[item.observed_at] = observed_rows.get(item.observed_at, 0) + 1
            if {at: n for at, n in receipt_rows.items() if n} != observed_rows:
                raise ContractError()
            mandatory_section = {'kr_buy_capacity': 'output', 'kr_orders': 'output2'}.get(req.operation)
            if mandatory_section is not None:
                for at, page_count in receipt_pages.items():
                    if sum(item.observed_at == at and item.source_section == mandatory_section
                           for item in result.items) != page_count:
                        raise ContractError()
            seen_cursors = {BrokerCursor('', '')}
            for receipt in self.page_receipts[:-1]:
                if (receipt.response_cursor is None or not receipt.response_cursor.forward
                        or receipt.response_cursor in seen_cursors):
                    raise ContractError()
                seen_cursors.add(receipt.response_cursor)
            seen_facts = set()
            for item in result.items:
                profile = SOURCE_FIELDS[(item.operation, item.source_section)]
                if (not set(profile[1]) <= {n.source_field for n in item.numbers}
                        or any(n.value is None for n in item.numbers)
                        or any(getattr(item, name) is None for name in profile[3])):
                    raise ContractError()
                if item.kind == 'order_cumulative':
                    if None in (item.order_date, item.order_branch, item.order_number, item.original_order_number):
                        raise ContractError()
                    if not req.scope.start_date <= item.order_date <= req.scope.end_date:
                        raise ContractError()
                    key = (item.kind, item.order_date, item.order_branch, item.order_number)
                else:
                    if item.kind == 'holding' and item.source_symbol is None:
                        raise ContractError()
                    key = (item.kind, item.source_section, item.source_symbol, item.venue, item.currency)
                if key in seen_facts:
                    raise ContractError()
                seen_facts.add(key)
            last = self.page_receipts[-1]
            if any(x.validation != 'accepted' for x in self.page_receipts) or last.wire_marker != '' or last.terminal_evidence != 'synthetic_terminal_v1':
                raise ContractError()
        elif self.missing_scope != (req.scope.coverage,) or not self.reason_codes:
            raise ContractError()
