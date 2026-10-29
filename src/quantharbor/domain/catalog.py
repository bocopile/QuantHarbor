"""Q16 불변 합성 catalog. 공급자 연결·주문 권한·실제 상품 채택은 없다."""

from dataclasses import dataclass
import re

from .primitives import ContractError, currency, identifier, utc_instant


def _window(start, end):
    start = utc_instant(start)
    end = None if end is None else utc_instant(end)
    if end is not None and start >= end:
        raise ContractError()
    return start, end


def _contains(start, end, instant):
    return start <= instant and (end is None or instant < end)


def _tuple_of(value, expected):
    if type(value) is not tuple or any(type(item) is not expected for item in value):
        raise ContractError()


def _no_overlap(records, key, start, end):
    groups = {}
    for record in records:
        groups.setdefault(key(record), []).append(record)
    for group in groups.values():
        ordered = sorted(group, key=start)
        for previous, current in zip(ordered, ordered[1:]):
            if end(previous) is None or start(current) < end(previous):
                raise ContractError()


def source_code(value):
    """초기 합성 provider code: 대문자 ASCII/숫자 및 . _ -, 최대32자."""
    if type(value) is not str or not re.fullmatch(r"[A-Z0-9][A-Z0-9._-]{0,31}", value, re.ASCII):
        raise ContractError()
    return value


@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_id: str
    instrument_version: str
    listing_venue_id: str
    market: str
    currency: str
    product_kind: str
    etf_kind: str
    classification_version: str
    classification_evidence_ref: str
    valid_from: str
    valid_to: str | None
    known_at: str

    def __post_init__(self):
        for value in (self.instrument_id, self.instrument_version, self.listing_venue_id,
                      self.classification_version, self.classification_evidence_ref):
            identifier(value)
        currency(self.currency)
        if type(self.market) is not str or self.market not in ("KR", "US", "other", "unknown"):
            raise ContractError()
        allowed = {"equity": ("not_applicable",), "etf": ("general", "leveraged", "inverse", "unknown"),
                   "unknown": ("unknown",)}
        if (type(self.product_kind) is not str or self.product_kind not in allowed
                or type(self.etf_kind) is not str or self.etf_kind not in allowed[self.product_kind]):
            raise ContractError()
        start, end = _window(self.valid_from, self.valid_to)
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_to", end)
        object.__setattr__(self, "known_at", utc_instant(self.known_at))

    @property
    def eligible_for_initial_scope(self):
        return self.market in ("KR", "US") and (
            self.product_kind == "equity" or (self.product_kind == "etf" and self.etf_kind == "general"))


@dataclass(frozen=True, slots=True)
class SymbolMapping:
    mapping_id: str
    mapping_version: str
    source_id: str
    source_code: str
    instrument_id: str
    listing_venue_id: str
    execution_venue_id: str
    valid_from: str
    valid_to: str | None
    known_at: str

    def __post_init__(self):
        for value in (self.mapping_id, self.mapping_version, self.source_id, self.instrument_id,
                      self.listing_venue_id, self.execution_venue_id):
            identifier(value)
        source_code(self.source_code)
        start, end = _window(self.valid_from, self.valid_to)
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_to", end)
        object.__setattr__(self, "known_at", utc_instant(self.known_at))


@dataclass(frozen=True, slots=True)
class CatalogResolution:
    catalog_version: str
    instrument: Instrument
    mapping: SymbolMapping

    def __post_init__(self):
        identifier(self.catalog_version)
        if (type(self.instrument) is not Instrument or type(self.mapping) is not SymbolMapping
                or (self.instrument.instrument_id, self.instrument.listing_venue_id) !=
                (self.mapping.instrument_id, self.mapping.listing_venue_id)):
            raise ContractError()

    @property
    def eligible_for_initial_scope(self):
        return self.instrument.eligible_for_initial_scope


@dataclass(frozen=True, slots=True)
class Catalog:
    catalog_version: str
    source_ref: str
    instruments: tuple[Instrument, ...]
    mappings: tuple[SymbolMapping, ...]
    environment: str = "synthetic"
    schema_version: int = 1

    def __post_init__(self):
        identifier(self.catalog_version)
        identifier(self.source_ref)
        if (type(self.environment) is not str or self.environment != "synthetic"
                or type(self.schema_version) is not int or self.schema_version != 1):
            raise ContractError()
        _tuple_of(self.instruments, Instrument)
        _tuple_of(self.mappings, SymbolMapping)
        indexed = {(item.instrument_id, item.listing_venue_id): item for item in self.instruments}
        if len(indexed) != len(self.instruments) or len({item.mapping_id for item in self.mappings}) != len(self.mappings):
            raise ContractError()
        venue_markets = {}
        for instrument in self.instruments:
            existing = venue_markets.setdefault(instrument.listing_venue_id, instrument.market)
            if existing != instrument.market:
                raise ContractError()
        for mapping in self.mappings:
            instrument = indexed.get((mapping.instrument_id, mapping.listing_venue_id))
            if (instrument is None or mapping.valid_from < instrument.valid_from
                    or (instrument.valid_to is not None and
                        (mapping.valid_to is None or mapping.valid_to > instrument.valid_to))):
                raise ContractError()
        # alias/정정 중첩을 암묵 선택하지 않는다. 정정은 새 catalog version이다.
        for key in (lambda item: (item.source_id, item.source_code, item.listing_venue_id, item.execution_venue_id),
                    lambda item: (item.source_id, item.instrument_id, item.listing_venue_id, item.execution_venue_id)):
            _no_overlap(self.mappings, key, lambda item: item.valid_from, lambda item: item.valid_to)

    def resolve(self, source_id, code, listing_venue_id, execution_venue_id, *, as_of, knowledge_cutoff):
        for value in (source_id, listing_venue_id, execution_venue_id):
            identifier(value)
        source_code(code)
        instant, cutoff = utc_instant(as_of), utc_instant(knowledge_cutoff)
        matches = [item for item in self.mappings if
                   (item.source_id, item.source_code, item.listing_venue_id, item.execution_venue_id)
                   == (source_id, code, listing_venue_id, execution_venue_id)
                   and _contains(item.valid_from, item.valid_to, instant) and item.known_at <= cutoff]
        if not matches:
            return None
        if len(matches) != 1:
            raise ContractError()
        mapping = matches[0]
        instrument = next(item for item in self.instruments if
                          (item.instrument_id, item.listing_venue_id) == (mapping.instrument_id, listing_venue_id))
        if instrument.known_at > cutoff or not _contains(instrument.valid_from, instrument.valid_to, instant):
            return None
        return CatalogResolution(self.catalog_version, instrument, mapping)
