"""Q17A explicit-time bounded orchestration; synthetic fetch only, zero retries."""
from dataclasses import dataclass

from quantharbor.domain.market_data import (
    FetchRequest, IngestLimits, IngestState, MarketEnvelope, RecordRefSet, RightsGrant,
    MarketItem, RawMarketView, adjustment_verified, assess_quality, fail_ingest, item_ref, record_hash,
    page_facts, reduce_page_facts, select_raw_view, sequence, validate_market_context,
)
from quantharbor.domain.primitives import ContractError, utc_instant
from quantharbor.adapters.synthetic_market import SyntheticMemoryStore, SyntheticPageAdapter
from quantharbor.market_data.timezones import ExplicitTimezone


@dataclass(frozen=True, slots=True)
class IngestResult:
    state: IngestState
    envelope: MarketEnvelope
    bundle: object


@dataclass(frozen=True, slots=True)
class ValidatedMarketView:
    raw_view: RawMarketView
    selected: tuple[MarketItem, ...]
    held_reasons: tuple[str, ...]

    def __post_init__(self):
        if type(self.raw_view) is not RawMarketView:
            raise ContractError()
        sequence(self.selected, MarketItem)
        sequence(self.held_reasons, unique=True)
        if any(x not in self.raw_view.selected for x in self.selected):
            raise ContractError()

    @property
    def context_validated(self):
        return True


def select_view(state, *, as_of, knowledge_cutoff, rights, at, dataset_version, catalog, calendar, timezone,
                mode="as_known", original_cutoff=None, purpose="research"):
    """사용 조회 진입점: raw PIT와 Q16 binding을 모두 검사한다. 금융 실행 권한은 아니다."""
    from quantharbor.domain.catalog import Catalog
    from quantharbor.domain.calendar import MarketCalendar
    if type(catalog) is not Catalog or type(calendar) is not MarketCalendar or type(timezone) is not ExplicitTimezone:
        raise ContractError()
    raw = select_raw_view(state, as_of=as_of, knowledge_cutoff=knowledge_cutoff, rights=rights, at=at,
                          dataset_version=dataset_version, mode=mode, original_cutoff=original_cutoff, purpose=purpose)
    held, context_items = set(raw.held_reasons), []
    try:
        timezone.validate_calendar(calendar)
    except ContractError:
        return ValidatedMarketView(raw, (), tuple(sorted(held | {"context_invalid"})))
    for item in raw.selected:
        try:
            reason = validate_market_context(item, catalog, calendar, timezone, knowledge_cutoff=knowledge_cutoff)
        except ContractError:
            reason = "context_invalid"
        if reason:
            held.add(reason)
        else:
            context_items.append(item)
    selected = []
    for item in context_items:
        if adjustment_verified(item, context_items, as_of=as_of, knowledge_cutoff=knowledge_cutoff):
            selected.append(item)
        else:
            held.add("adjustment_unverified")
    return ValidatedMarketView(raw, tuple(selected), tuple(sorted(held)))


def context_refs(catalog, calendar, timezone):
    """별도 고정 source-facts digest. 등록 canonical record hash와 혼용하지 않는다."""
    from dataclasses import asdict
    from hashlib import sha256
    import json
    from quantharbor.domain.catalog import Catalog
    from quantharbor.domain.calendar import MarketCalendar
    from quantharbor.domain.market_storage import ContextRef
    if type(catalog) is not Catalog or type(calendar) is not MarketCalendar or type(timezone) is not ExplicitTimezone:
        raise ContractError()
    facts = (("catalog", catalog.source_ref, catalog.catalog_version, asdict(catalog)),
             ("calendar", calendar.venue_id, calendar.calendar_version, asdict(calendar)),
             ("timezone", timezone.timezone_id, timezone.rules_version,
              {key: getattr(timezone, key) for key in ("timezone_id", "rules_version", "content_sha256",
                                                      "coverage_start", "coverage_end", "known_at")}))
    return tuple(ContextRef(kind, name, version, sha256(b"QuantHarbor/context-source-facts-v1\n" +
                 json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest())
                 for kind, name, version, value in facts)


def finalize_ingest(request, state, limits, rights, now, *, catalog, calendar, timezone,
                    view_mode="as_known", original_cutoff=None):
    permitted = rights.allows(at=now, purpose="store", source_id=request.source_id,
                             dataset_id=request.dataset_id, dataset_version=request.dataset_version)
    if not state.errors and not state.terminal:
        state = fail_ingest(state, "page_limit")
    if any(x.observation.rights_ref != rights.rights_ref for x in state.revisions.items):
        state = fail_ingest(state, "observation_rights_mismatch")
    view = select_view(state.revisions, as_of=now, knowledge_cutoff=request.knowledge_cutoff,
                       rights=rights, at=now, dataset_version=request.dataset_version, purpose="store", mode=view_mode, original_cutoff=original_cutoff,
                       catalog=catalog, calendar=calendar, timezone=timezone)
    for reason in view.held_reasons:
        state = fail_ingest(state, reason, not_before=state.not_before)
    selected_events = {x.revision.identity for x in view.selected}
    if any(x.revision.identity not in selected_events for x in state.revisions.items):
        state = fail_ingest(state, "pit_not_usable", not_before=state.not_before)
    if request.scope.coverage_kind == "explicit_closed":
        from datetime import datetime, timedelta
        try:
            first = timezone.lookup_calendar(calendar, request.scope.starts_at,
                                             knowledge_cutoff=request.knowledge_cutoff)
            last = timezone.lookup_calendar(calendar, datetime.fromisoformat(request.scope.ends_at) - timedelta(microseconds=1),
                                            knowledge_cutoff=request.knowledge_cutoff)
            if first.status != "closed" or last.status != "closed" or first.trading_date != last.trading_date:
                state = fail_ingest(state, "closed_coverage_unverified")
        except ContractError:
            state = fail_ingest(state, "closed_coverage_unverified")
    quality = assess_quality(state, request, limits, evaluated_at=now, rights_allowed=permitted)
    items = state.revisions.items
    # Upper envelope times summarize actual supplied observations, not wall clock invention.
    observed = max((x.observation.observed_at for x in items), default=request.started_at)
    ingested = max((x.observation.ingested_at for x in items), default=request.started_at)
    if observed > now or ingested > now:
        raise ContractError()
    refs = RecordRefSet(1, "synthetic", tuple(item_ref(x) for x in items))
    envelope = MarketEnvelope(request.request_id, 1, request.source_id, request.dataset_id,
                              request.dataset_version, "synthetic", request.scope.series_ids, items,
                              request.scope.ends_at, observed, ingested, quality, rights.rights_ref,
                              record_hash(refs), (request.scope.coverage_ref, "snapshot." + state.snapshot_consistency))
    return state, envelope


def replay_storage(descriptor, receipts, evidence, *, catalog, calendar, timezone):
    from quantharbor.domain.market_storage import MarketIngestDescriptor, replay_receipts
    if type(descriptor) is not MarketIngestDescriptor or context_refs(catalog, calendar, timezone) != (
            descriptor.catalog_ref, descriptor.calendar_ref, descriptor.timezone_ref):
        raise ContractError()
    state = replay_receipts(descriptor, receipts, evidence)
    return finalize_ingest(descriptor.request, state, descriptor.limits, descriptor.historical_rights_snapshot,
        descriptor.evaluated_at, catalog=catalog, calendar=calendar, timezone=timezone,
        view_mode=descriptor.view_mode, original_cutoff=descriptor.original_cutoff)


def ingest(request, fetch, *, limits, rights, evaluated_at, catalog, calendar, timezone, store=None,
           view_mode="as_known", original_cutoff=None):
    """Synthetic clock/deadline facts are supplied. No real I/O timeout or retry."""
    from quantharbor.domain.market_storage import (
        MarketIngestDescriptor, StorageBundle, fetch_failure_receipt, receipt_from_page, summary_for,
    )
    if (type(request) is not FetchRequest or type(fetch) is not SyntheticPageAdapter
            or type(limits) is not IngestLimits or type(rights) is not RightsGrant
            or type(timezone) is not ExplicitTimezone
            or (store is not None and type(store) is not SyntheticMemoryStore)):
        raise ContractError()
    now = utc_instant(evaluated_at)
    refs = context_refs(catalog, calendar, timezone)
    descriptor = MarketIngestDescriptor(1, "synthetic", request, limits, now, view_mode, original_cutoff,
                                       *refs, rights.rights_ref, rights)
    permitted = rights.allows(at=now, purpose="store", source_id=request.source_id,
                             dataset_id=request.dataset_id, dataset_version=request.dataset_version)
    state, receipts = IngestState(), []
    if not permitted:
        state = fail_ingest(state, "rights_blocked")
    while not state.errors and not state.terminal and state.pages < limits.max_pages:
        facts = None
        try:
            facts = page_facts(fetch.fetch(request, state.next_cursor))
            next_state = reduce_page_facts(state, request, facts, limits, evaluated_at=now)
            receipt = receipt_from_page(facts, state, next_state, len(receipts) + 1)
        except Exception:
            if facts is None:
                receipt = fetch_failure_receipt(request, state, now, len(receipts) + 1)
                next_state = fail_ingest(state, "fetch_or_normalization_failed")
            else:
                next_state = fail_ingest(state, "normalization_rejected")
                receipt = receipt_from_page(facts, state, next_state, len(receipts) + 1)
        receipts.append(receipt)
        state = next_state
    state, envelope = finalize_ingest(request, state, limits, rights, now, catalog=catalog, calendar=calendar,
                                     timezone=timezone, view_mode=view_mode, original_cutoff=original_cutoff)
    bundle = StorageBundle(descriptor, tuple(receipts), state.revisions.evidence, state, envelope, summary_for(state, envelope))
    if store is not None and permitted and "observation_rights_mismatch" not in state.errors:
        store.write(envelope, rights=rights, at=now)
    return IngestResult(state, envelope, bundle)
