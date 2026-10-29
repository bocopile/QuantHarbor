"""qh-canonical-json-v1. 등록된 기본형만 검증·정규화 후 hash한다.

Q13 Money/Quantity/Price/FX와 Q17 고정 시장 자료 v1을 등록한다. 임의 payload나
OrderCandidate를 받아 주는 fallback/사용자 정의 제외 필드는 없다.
"""

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from types import MappingProxyType

from .primitives import ContractError, FX, Money, Price, Quantity
from . import market_data as market
from . import market_storage as storage
from . import documents as documents
from . import broker_read as broker
from . import ledger as ledger
from . import valuation as valuation
from . import reporting as reporting
from . import research as research
from . import target as target
from . import investment_ai as investment_ai
from . import approval as approval
from . import execution as execution


CANONICALIZATION_VERSION = "qh-canonical-json-v1"
_HASH_PREFIX = b"QuantHarbor/qh-canonical-json-v1\n"
_BASIC = {"Money": Money, "Quantity": Quantity, "Price": Price, "FX": FX}
_MARKET = {cls.__name__: cls for cls in (market.MarketRevision, market.MarketObservation,
           market.RecordRefSet, market.MarketEnvelope, market.DatasetManifest)}
_STORAGE = {cls.__name__: cls for cls in (storage.MarketStorageManifest, storage.MarketIngestDescriptor,
            storage.MarketPageReceipt, storage.MarketEvidenceIndex)}
_DOCUMENTS = {cls.__name__: cls for cls in (documents.DocumentOriginal, documents.DocumentRevision,
              documents.DocumentObservation, documents.DocumentEntityContext, documents.DocumentBatchManifest)}
_BROKER = {cls.__name__: cls for cls in (broker.BrokerReadCapability, broker.BrokerReadRequest,
           broker.BrokerReadBatch)}
_LEDGER = {cls.__name__: cls for cls in (ledger.SyntheticLedgerSubmission, ledger.LedgerEventBody,
           ledger.LedgerProjection, ledger.LedgerEvent)}
_VALUATION = {cls.__name__: cls for cls in (valuation.ValuationRequest, valuation.ValuationPolicy,
    valuation.MarketProof, valuation.ValuationResult, valuation.ReconciliationPolicy,
    valuation.StatementSourceSnapshot, valuation.SyntheticAccountStatement,
    valuation.ReconciliationResult, valuation.BrokerBatchInspection,
    valuation.SnapshotInputManifest, valuation.PortfolioSnapshot)}
_VALUATION_SUPPORT = {'ReplaySummary': storage.ReplaySummary}
_REPORTING = {cls.__name__: cls for cls in (reporting.ReportRequest, reporting.ReportInputManifest,
    reporting.Report, reporting.ReportPresentationRequest)}
_RESEARCH = {cls.__name__: cls for cls in (research.ComparisonSpec, research.ImplementationFingerprint,
    research.ExperimentRegistry, research.ExecutionTrace, research.TradeCostFact, research.PerformanceResult,
    research.CostBasisResult, research.ExperimentManifest, research.ExperimentResult)}
_TARGET = {cls.__name__: cls for cls in target.SPECS} | {'RightsGrant': market.RightsGrant}
_INVESTMENT_AI = {cls.__name__: cls for cls in investment_ai.SPECS}
_APPROVAL = {cls.__name__: cls for cls in approval.SPECS}
_EXECUTION = {cls.__name__: cls for cls in execution.SPECS}
_SCHEMAS = MappingProxyType({**_BASIC, **_MARKET, **_STORAGE, **_DOCUMENTS, **_BROKER, **_LEDGER,
                           **_VALUATION, **_VALUATION_SUPPORT, **_REPORTING, **_RESEARCH, **_TARGET, **_INVESTMENT_AI, **_APPROVAL, **_EXECUTION})
# A closed structural table; no caller registration or arbitrary dict payload.
_NESTED = {
    research.FoldSpec: {'train': (research.PointIndex,), 'validation': (research.PointIndex,), 'oos': (research.PointIndex,)},
    research.ResearchPoint: {'KR': research.PointTime, 'US': research.PointTime},
    research.ComparisonSpec: {'markets': (research.ResearchMarket,), 'folds': (research.FoldSpec,),
        'points': (research.ResearchPoint,), 'costs': (research.CostScenario,),
        'equity_closes': (str,), 'etf_closes': (str,)},
    research.ImplementationFingerprint: {'files': (research.FileFingerprint,)},
    research.ExperimentRegistry: {'strategies': (str,)},
    research.Metric: {'reason_codes': (str,)},
    research.NavPoint: {'snapshot': research.InputRef, 'reason_codes': (str,)},
    research.FlowBoundary: {'before': research.NavPoint, 'after': research.NavPoint, 'events': (research.InputRef,)},
    research.PerformanceResult: {'points': (research.NavPoint,), 'flows': (research.FlowBoundary,),
        **{name: research.Metric for name in ('traded_notional', 'benchmark_return', 'twr', 'amount_pnl',
            'observed_mdd', 'time_weighted_nav', 'gross_turnover', 'half_turnover', 'benchmark_excess',
            'benchmark_relative_wealth')}},
    research.CostAllocation: {'event': research.InputRef},
    research.TradeCostFact: {'trade': research.InputRef, 'position': valuation.PositionKey,
        'allocations': (research.CostAllocation,), 'base_notional': research.Metric},
    research.CostBasisResult: {'position': valuation.PositionKey, 'facts': (research.TradeCostFact,),
        **{name: research.Metric for name in ('closing_native_value', 'quantity', 'remaining_basis',
            'realized_pnl', 'unrealized_pnl', 'attribution')}},
    research.OrderAttempt: {'decision_snapshot': research.InputRef, 'trade': (research.InputRef, None)},
    research.ExecutionTrace: {'attempts': (research.OrderAttempt,)},
    research.ExperimentManifest: {'refs': (research.InputRef,)},
    research.ExperimentResult: {'manifest': research.ExperimentManifest, 'performance': research.PerformanceResult,
        'cost_basis': (research.CostBasisResult,), 'reason_codes': (str,),
        **{name: research.Metric for name in ('fees', 'taxes', 'slippage', 'fx_transaction_cost', 'cash_benchmark_return')}},
    reporting.ReportInputManifest: {'rights': (market.RightsGrant,)},
    reporting.Report: {'snapshot': valuation.PortfolioSnapshot, 'request': reporting.ReportRequest,
        'input_manifest': reporting.ReportInputManifest},
    reporting.ReportPresentationRequest: {'report': reporting.Report, 'current_rights': (market.RightsGrant,)},
    valuation.BalanceScope: {'positions': (valuation.PositionKey,), 'currencies': (str,), 'components': (str,)},
    valuation.ValuationRequest: {'scope': valuation.BalanceScope},
    valuation.PriceSelection: {'position': valuation.PositionKey, 'series': valuation.SeriesSelection},
    valuation.FXSelection: {'series': valuation.SeriesSelection},
    valuation.ValuationPolicy: {'prices': (valuation.PriceSelection,), 'fx': (valuation.FXSelection,),
        'quantums': (valuation.CurrencyQuantum,), 'stages': (str,)},
    valuation.MarketProof: {'selection': valuation.SeriesSelection, 'receipt_hashes': (str,),
        'records': (market.RecordRef,), 'selected': (market.MarketItem,), 'contexts': (storage.ContextRef,), 'rights': market.RightsGrant,
        'quality': market.QualityResult, 'scope': market.QueryScope, 'held_reasons': (str,)},
    valuation.HoldingValuation: {'position': ledger.PositionDelta, 'price': (Price, None),
        'price_ref': (market.RecordRef, None), 'reason_codes': (str,)},
    valuation.CashValuation: {'reason_codes': (str,)},
    valuation.CurrencyValuation: {'fx': (FX, None), 'fx_ref': (market.RecordRef, None), 'reason_codes': (str,)},
    valuation.ValuationResult: {'projection': ledger.LedgerProjection, 'request': valuation.ValuationRequest,
        'policy': valuation.ValuationPolicy, 'market_proofs': (valuation.MarketProof,),
        'holdings': (valuation.HoldingValuation,), 'cash_by_currency': (valuation.CashValuation,),
        'native_totals': (valuation.CurrencyValuation,), 'reason_codes': (str,)},
    valuation.ReconciliationPolicy: {'quantities': (valuation.QuantityTolerance,), 'cash': (valuation.CashTolerance,)},
    valuation.StatementSourceSnapshot: {'scope': valuation.BalanceScope, 'holdings': (ledger.PositionDelta,),
        'cash': (ledger.CashBalance,), 'evidence_refs': (str,)},
    valuation.SyntheticAccountStatement: {'snapshot': valuation.StatementSourceSnapshot,
        'requested_scope': valuation.BalanceScope, 'reason_codes': (str,)},
    valuation.ReconciliationDifference: {'position': (valuation.PositionKey, None), 'reason_codes': (str,)},
    valuation.ReconciliationResult: {'statement': (valuation.SyntheticAccountStatement, None),
        'requested_scope': valuation.BalanceScope, 'covered_scope': (valuation.BalanceScope, None),
        'missing_scope': (str,), 'compared_domains': (str,),
        'differences': (valuation.ReconciliationDifference,), 'reason_codes': (str,)},
    valuation.BrokerBatchInspection: {'source_scope': broker.BrokerReadScope, 'source_missing_scope': (str,),
        'source_reason_codes': (str,), 'reason_codes': (str,)},
    valuation.PortfolioSnapshot: {'data_refs': (valuation.DataRef,), 'holdings': (valuation.HoldingValuation,),
        'cash_by_currency': (valuation.CashValuation,), 'open_order_refs': (str,),
        'valuation': valuation.ValuationResult, 'reconciliation_details': valuation.ReconciliationResult,
        'reconciliation_policy': valuation.ReconciliationPolicy, 'broker_details': (valuation.BrokerBatchInspection, None),
        'input_manifest': valuation.SnapshotInputManifest},
    ledger.SyntheticLedgerSubmission: {"cash_legs": (ledger.CashLeg,),
        "position_deltas": (ledger.PositionDelta,), "evidence_refs": (str,),
        "completeness": ledger.LedgerCompleteness, "baseline": (ledger.LedgerBaseline, None),
        "dependency_refs": (str,), "split_ratio": (ledger.SplitRatio, None)},
    ledger.LedgerEvent: {"body": ledger.LedgerEventBody},
    ledger.LedgerEventBody: {"submission": ledger.SyntheticLedgerSubmission,
        "cash_legs": (ledger.CashLeg,), "position_deltas": (ledger.PositionDelta,)},
    ledger.LedgerProjection: {"cash_balances": (ledger.CashBalance,),
        "holdings": (ledger.PositionDelta,), "reason_codes": (str,)},
    market.Adjustment: {"action_refs": (market.ActionRef,)},
    market.PriceBar: {"open": Price, "high": Price, "low": Price, "close": Price,
                      "volume": (Quantity, None), "adjustment_details": (market.Adjustment, None)},
    market.FXObservation: {"fx": FX},
    market.CorporateAction: {"cash_per_unit": (Money, None)},
    market.MarketRevision: {"payload": "market_payload"},
    market.MarketItem: {"revision": market.MarketRevision, "observation": market.MarketObservation},
    market.RecordRefSet: {"records": (market.RecordRef,)},
    market.QualityResult: {"missing_scope": (str,), "reasons": (str,)},
    market.MarketEnvelope: {"queried_scope": (str,), "items": (market.MarketItem,),
                            "quality": market.QualityResult, "lineage_refs": (str,)},
    market.DatasetManifest: {"files": (market.ManifestFile,), "record_set": market.RecordRefSet},
    market.QueryScope: {"series_ids": (str,), "expected": (market.ExpectedEvent,)},
    market.FetchRequest: {"scope": market.QueryScope},
    market.RightsGrant: {"purposes": (str,)},
    storage.MarketEvidenceIndex: {"claims": (storage.ClaimRef,)},
    storage.MarketIngestDescriptor: {"request": market.FetchRequest, "limits": market.IngestLimits,
        "catalog_ref": storage.ContextRef, "calendar_ref": storage.ContextRef, "timezone_ref": storage.ContextRef,
        "historical_rights_snapshot": market.RightsGrant},
    storage.MarketPageReceipt: {"scope": market.QueryScope, "item_refs": (storage.ClaimRef,)},
    storage.ConflictSummary: {"left": storage.ClaimRef, "right": storage.ClaimRef},
    storage.ReplaySummary: {"seen_cursors": (str,), "errors": (str,), "snapshots": (str,),
        "conflicts": (storage.ConflictSummary,), "quality": market.QualityResult},
    storage.MarketStorageManifest: {"descriptor_file": storage.FileRef, "receipt_files": (storage.FileRef,),
        "evidence_files": (storage.FileRef,), "replay_summary": storage.ReplaySummary},
    broker.BrokerReadCapability: {"binding": broker.BrokerReadBinding, "scope": broker.BrokerReadScope},
    broker.BrokerReadRequest: {"binding": broker.BrokerReadBinding, "scope": broker.BrokerReadScope},
    broker.BrokerObservation: {"binding": broker.BrokerReadBinding, "scope": broker.BrokerReadScope,
        "numbers": (broker.SourceNumber,)},
    broker.BrokerPageReceipt: {"request_cursor": broker.BrokerCursor,
        "response_cursor": (broker.BrokerCursor, None)},
    broker.BrokerQueryResult: {"queried_scope": broker.BrokerReadScope,
        "items": (broker.BrokerObservation,), "continuation": (broker.BrokerCursor, None)},
    broker.BrokerReadBatch: {"request": broker.BrokerReadRequest, "result": broker.BrokerQueryResult,
        "page_receipts": (broker.BrokerPageReceipt,), "missing_scope": (str,), "reason_codes": (str,)},
    documents.DocumentObservation: {"revision_ref": documents.RevisionRef},
    documents.DocumentEntityLink: {"revision_ref": documents.RevisionRef},
    documents.DocumentEntityContext: {"entities": (documents.Entity,), "document_links": (documents.DocumentEntityLink,),
        "instrument_links": (documents.EntityInstrumentLink,)},
    documents.DocumentRequest: {"document_ids": (str,), "expected_document_ids": (str,)},
    documents.DocumentReceipt: {"claim_refs": (documents.ClaimRef,), "missing_document_ids": (str,)},
    documents.DocumentBatchManifest: {"request": documents.DocumentRequest, "limits": documents.DocumentLimits,
        "receipt": documents.DocumentReceipt, "claims": (documents.ClaimRef,), "file_refs": (documents.DocumentFileRef,)},
}

_NESTED.update(target.NESTED)
_NESTED.update(investment_ai.NESTED)
_NESTED.update(approval.NESTED)
_NESTED.update(execution.NESTED)


def _restore(expected, value):
    if type(value) is not dict or value.keys() != {field.name for field in fields(expected)}:
        raise ContractError()
    restored = dict(value)
    for name, kind in _NESTED.get(expected, {}).items():
        item = value[name]
        if kind == "market_payload":
            if item is None:
                restored[name] = None
            else:
                choices = [cls for cls in (market.PriceBar, market.FXObservation, market.CorporateAction)
                           if type(item) is dict and item.keys() == {f.name for f in fields(cls)}]
                if len(choices) != 1:
                    raise ContractError()
                restored[name] = _restore(choices[0], item)
        elif type(kind) is tuple and len(kind) == 2:
            restored[name] = None if item is None else _restore(kind[0], item)
        elif type(kind) is tuple:
            if type(item) not in (tuple, list) or len(item) > (ledger.MAX_EVENTS if expected is ledger.LedgerProjection else market.MAX_RECORDS):
                raise ContractError()
            restored[name] = tuple(item) if kind[0] is str else tuple(_restore(kind[0], x) for x in item)
        else:
            restored[name] = _restore(kind, item)
    return expected(**restored)
_WRAPPER_FIELDS = frozenset(("schema_name", "schema_version", "environment", "payload"))
_MAX_JSON_BYTES = 65536


def _valid_string(value: str) -> None:
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ContractError()


def _encode(value: object) -> bytes:
    """검증 후 encoder. 공개 hash API의 스키마 검사를 대체하지 않는다."""
    # Python JSON의 고정 escape: \b\f\n\r\t, 나머지 control은 소문자 hex.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True, slots=True)
class CanonicalPayload:
    schema_name: str
    schema_version: int
    environment: str
    payload: object

    def __post_init__(self) -> None:
        if type(self.schema_name) is not str or self.schema_name not in _SCHEMAS:
            raise ContractError()
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ContractError()
        if type(self.environment) is not str or self.environment not in ("synthetic", "paper", "live"):
            raise ContractError()
        expected = _SCHEMAS[self.schema_name]
        if type(self.payload) is not expected:
            raise ContractError()
        # Reconstruct to reject objects forged with object.__new__/__setattr__.
        # A caller changing the instance through Python internals cannot bypass validation.
        object.__setattr__(self, "payload", _restore(expected, asdict(self.payload)))
        if self.schema_name in (_MARKET.keys() | _STORAGE.keys() | _DOCUMENTS.keys() | _BROKER.keys() | _LEDGER.keys()) and self.environment != (self.payload.body.environment if type(self.payload) is ledger.LedgerEvent else self.payload.environment):
            raise ContractError()
        if self.schema_name in (_VALUATION.keys() | _VALUATION_SUPPORT.keys()) and (
                self.environment != 'synthetic' or getattr(self.payload, 'environment', 'synthetic') != self.environment):
            raise ContractError()
        if self.schema_name in _REPORTING and (self.environment != 'synthetic' or self.payload.environment != self.environment):
            raise ContractError()
        if self.schema_name in _TARGET and self.environment != getattr(self.payload, 'environment',
                getattr(getattr(self.payload, 'body', None), 'environment', 'synthetic')):
            raise ContractError()
        if self.schema_name in _INVESTMENT_AI and self.environment != 'synthetic':
            raise ContractError()
        if self.schema_name in (_APPROVAL.keys() | _EXECUTION.keys()) and self.environment != 'synthetic':
            raise ContractError()
        if self.schema_name in _RESEARCH and (self.environment != 'synthetic' or self.payload.environment != self.environment):
            raise ContractError()


def canonical_bytes(value: CanonicalPayload) -> bytes:
    if type(value) is not CanonicalPayload:
        raise ContractError()
    checked = CanonicalPayload(value.schema_name, value.schema_version, value.environment, value.payload)
    encoded = _encode(asdict(checked))
    if len(encoded) > _MAX_JSON_BYTES:
        raise ContractError()
    return encoded


def canonical_hash(value: CanonicalPayload) -> str:
    return sha256(_HASH_PREFIX + canonical_bytes(value)).hexdigest()


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        _valid_string(key)
        if key in result:
            raise ContractError()
        result[key] = value
    return result


def _reject_number(value: str) -> object:
    raise ContractError()


def _integer(value: str) -> int:
    if len(value) > 19:
        raise ContractError()
    return int(value)


def _strings(value: object) -> None:
    if type(value) is str:
        _valid_string(value)
    elif type(value) is dict:
        for key, item in value.items():
            _valid_string(key)
            _strings(item)
    elif type(value) is list:
        for item in value:
            _strings(item)


def parse_payload(raw: str | bytes) -> CanonicalPayload:
    """JSON 입력의 중복 key·float·미등록 field/version을 거부한다."""
    try:
        if type(raw) not in (str, bytes):
            raise ContractError()
        if len(raw) > _MAX_JSON_BYTES:
            raise ContractError()
        if type(raw) is bytes:
            raw = raw.decode("utf-8")
        if len(raw.encode("utf-8")) > _MAX_JSON_BYTES:
            raise ContractError()
        value = json.loads(raw, object_pairs_hook=_pairs, parse_float=_reject_number,
                           parse_constant=_reject_number, parse_int=_integer)
        _strings(value)
        if type(value) is not dict or value.keys() != _WRAPPER_FIELDS:
            raise ContractError()
        name = value["schema_name"]
        if type(name) is not str or name not in _SCHEMAS:
            raise ContractError()
        payload = value["payload"]
        expected = _SCHEMAS[name]
        if type(payload) is not dict or payload.keys() != {field.name for field in fields(expected)}:
            raise ContractError()
        return CanonicalPayload(name, value["schema_version"], value["environment"], _restore(expected, payload))
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise ContractError() from None
