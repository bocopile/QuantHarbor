"""Q17 public synthetic facts only, no provider or market data files."""
from dataclasses import replace
from hashlib import sha256

from quantharbor.domain.catalog import Catalog, Instrument, SymbolMapping
from quantharbor.domain.market_data import (
    ExpectedEvent, FetchRequest, IngestLimits, MarketItem, MarketObservation, MarketRevision,
    PageResult, PriceBar, QueryScope, RightsGrant, record_hash,
)
from quantharbor.domain.primitives import Price, Quantity
from synthetic_timezones import KNOWN, synthetic_timezone
from test_calendar import calendar, trading_day


START = "2024-03-08T14:30:00Z"
END = "2024-03-08T14:31:00Z"
OBSERVED = "2024-03-08T14:31:01Z"
INGESTED = "2024-03-08T14:31:02Z"
NOW = "2024-03-08T14:31:03Z"
LATER = "2024-03-09T00:00:00Z"


def price(amount="10"):
    return Price(amount, "USD", "syn.instrument", "share")


def bar(**changes):
    values = dict(instrument_id="syn.instrument", listing_venue_id="syn.listing", execution_venue_id="syn.venue",
                  source_code="SYN", starts_at=START, ends_at=END, open=price(), high=price("12"), low=price("9"),
                  close=price("11"), volume=Quantity("100", "syn.instrument", "share"),
                  volume_unknown_reason=None, adjustment="raw", adjustment_details=None)
    return PriceBar(**(values | changes))


def revision(**changes):
    values = dict(schema_version=1, environment="synthetic", source_id="syn.source", dataset_id="syn.dataset",
                  series_id="syn.raw", event_id="syn.event", revision_id="rev.z", predecessor_revision_id=None,
                  revision_kind="original", effective_at=END, published_at=END, publication_unknown_reason=None,
                  normalization_version="normalize-v1", payload=bar())
    return MarketRevision(**(values | changes))


def item(r=None, **changes):
    r = revision() if r is None else r
    values = dict(schema_version=1, environment="synthetic", observation_id="obs.1", source_id=r.source_id,
                  dataset_id=r.dataset_id, series_id=r.series_id, event_id=r.event_id, revision_id=r.revision_id,
                  revision_hash=record_hash(r), observed_at=OBSERVED, ingested_at=INGESTED,
                  source_content_sha256=sha256(b"synthetic source bytes").hexdigest(), evidence_ref="syn.evidence",
                  rights_ref="syn.rights", catalog_version="catalog-v1", calendar_version="calendar-v1")
    return MarketItem(r, MarketObservation(**(values | changes)))


def rights(**changes):
    values = dict(rights_ref="syn.rights", environment="synthetic", source_id="syn.source", dataset_id="syn.dataset",
                  dataset_version="dataset-v1", purposes=("store", "research", "ai", "report"),
                  valid_from=KNOWN, valid_to="2025-01-01T00:00:00Z", revoked_at=None)
    return RightsGrant(**(values | changes))


def scope(**changes):
    values = dict(series_ids=("syn.raw",), starts_at=START, ends_at="2024-03-08T14:32:00Z",
                  expected=(ExpectedEvent("syn.raw", "syn.event", END),), coverage_kind="expected_records",
                  coverage_ref="syn.coverage")
    return QueryScope(**(values | changes))


def request(**changes):
    values = dict(request_id="syn.request", environment="synthetic", source_id="syn.source", dataset_id="syn.dataset",
                  dataset_version="dataset-v1", scope=scope(), started_at=START, deadline="2024-03-08T14:32:00Z",
                  knowledge_cutoff=NOW)
    return FetchRequest(**(values | changes))


def page(req=None, **changes):
    req = request() if req is None else req
    values = dict(request_id=req.request_id, scope=req.scope, cursor_in=None, cursor_out=None, terminal=True,
                  status="success", items=(item(),), response_bytes=b"synthetic response", source_snapshot="snapshot-v1",
                  received_at=NOW, error_reason=None, not_before=None)
    return PageResult(**(values | changes))


def context():
    zone = synthetic_timezone("US")
    cal = calendar(zone, trading_day(zone, "2024-03-08"))
    instrument = Instrument("syn.instrument", "instrument-v1", "syn.listing", "US", "USD", "equity", "not_applicable",
                            "classification-v1", "syn.classification", KNOWN, None, KNOWN)
    mapping = SymbolMapping("syn.mapping", "mapping-v1", "syn.source", "SYN", "syn.instrument", "syn.listing",
                            "syn.venue", KNOWN, None, KNOWN)
    cat = Catalog("catalog-v1", "syn.catalog", (instrument,), (mapping,))
    return dict(catalog=cat, calendar=cal, timezone=zone)
