"""Q17B synthetic bundles; no Arrow import or source data access."""
from dataclasses import replace

from quantharbor.adapters.synthetic_market import SyntheticPageAdapter
from quantharbor.application.market_ingest import ingest
from quantharbor.domain.market_data import ActionRef, Adjustment, CorporateAction, ExpectedEvent, FXObservation, IngestLimits, record_hash
from quantharbor.domain.primitives import FX, Money
from synthetic_market import END, LATER, NOW, START, bar, context, item, page, price, request, revision, rights, scope


def collect(items=None, *, version="dataset-v1", limits=None, pages=None, evaluated_at=NOW, **request_changes):
    items = (item(),) if items is None else items
    expected = tuple({(x.revision.series_id, x.revision.event_id):
                      ExpectedEvent(x.revision.series_id, x.revision.event_id, x.revision.effective_at) for x in items}.values())
    series = tuple(sorted({x.revision.series_id for x in items})) or ("syn.raw",)
    query = scope(series_ids=series, expected=expected, coverage_kind="expected_records" if expected else "confirmed_empty")
    req = request(dataset_version=version, scope=query, knowledge_cutoff=evaluated_at,
                  deadline="2024-03-09T00:01:00Z", **request_changes)
    grant = rights(dataset_version=version)
    pages = (page(req, items=items, received_at=evaluated_at),) if pages is None else pages(req)
    return ingest(req, SyntheticPageAdapter(pages), limits=IngestLimits(max_age_seconds=60) if limits is None else limits,
                  rights=grant, evaluated_at=evaluated_at, **context())


def rich_bundle():
    split = CorporateAction("syn.instrument", "syn.listing", "syn.venue", "SYN", "split", "share", "2024-03-08",
                            None, None, "not_provided", "3", "2", None)
    action = item(revision(series_id="syn.actions", event_id="syn.split", revision_id="split.1", payload=split),
                  observation_id="obs.action")
    dividend = item(revision(series_id="syn.dividends", event_id="syn.dividend", revision_id="dividend.1",
                    payload=replace(split, action_kind="cash_dividend", numerator=None, denominator=None,
                                    cash_per_unit=Money("0.123456789012345678", "USD"))), observation_id="obs.dividend")
    fx = item(revision(series_id="syn.fx", event_id="syn.fx.event", revision_id="fx.1",
                      payload=FXObservation(FX("USD", "KRW", "1300.123456789012345678", END, "syn.source"))),
              observation_id="obs.fx")
    details = Adjustment("split", "adjust-v1", END,
                         (ActionRef(*action.revision.key, record_hash(action.revision)),),
                         "2024-03-08T14:31:02Z", "syn.action.knowledge")
    adjusted = item(revision(series_id="syn.adjusted", event_id="syn.adjusted.bar", payload=bar(adjustment="adjusted",
                                adjustment_details=details), published_at=NOW), observation_id="obs.adjusted",
                    observed_at=NOW, ingested_at=NOW)
    raw = item(revision(payload=bar(open=price("10.000000000000000001"))),
               observed_at="2024-03-08T14:31:01.123456Z", ingested_at="2024-03-08T14:31:02.123456Z")
    return collect((raw, action, dividend, fx, adjusted)).bundle


def conflict_bundle(*, observation_collision=False):
    early = item(observation_id="obs.early")
    late = item(observation_id="obs.late", observed_at="2024-03-08T15:00:00Z", ingested_at="2024-03-08T15:00:00Z")
    opposite = item(revision(payload=bar(close=price("10"))), observation_id="obs.opposite",
                    observed_at="2024-03-08T14:40:00Z", ingested_at="2024-03-08T14:40:00Z")
    if observation_collision:
        early = item(observation_id="obs.shared")
        opposite = item(revision(event_id="syn.other.event"), observation_id="obs.shared",
                        observed_at="2024-03-08T14:40:00Z", ingested_at="2024-03-08T14:40:00Z")
    return collect((late, opposite, early), evaluated_at=LATER).bundle
