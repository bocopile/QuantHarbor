from dataclasses import replace
import unittest
from unittest.mock import patch

from quantharbor.adapters.synthetic_market import SyntheticMemoryStore, SyntheticPageAdapter
from quantharbor.application.market_ingest import ingest
from quantharbor.domain.market_data import (
    ExpectedEvent, IngestLimits, IngestState, RecordRefSet, assess_quality, merge_revision,
    record_hash, reduce_page, select_raw_view,
)
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from synthetic_market import END, LATER, NOW, START, bar, context, item, page, request, revision, rights, scope
from synthetic_timezones import KNOWN
from test_calendar import calendar, trading_day


def run(pages=None, *, req=None, limits=None, grant=None, store=None, **ctxchanges):
    req = request() if req is None else req
    fetch = SyntheticPageAdapter((page(req),) if pages is None else pages)
    ctx = context() | ctxchanges
    return ingest(req, fetch, limits=IngestLimits(max_age_seconds=60) if limits is None else limits,
                  rights=rights() if grant is None else grant, evaluated_at=NOW, store=store, **ctx), fetch


class MarketIngestTests(unittest.TestCase):
    def test_complete_fresh_roundtrip_and_same_day_pit(self):
        result, fetch = run()
        self.assertEqual(fetch.calls, 1)
        envelope = result.envelope
        self.assertEqual(envelope.quality.status, "complete")
        self.assertTrue(envelope.quality.eligible_for_new_risk)
        self.assertEqual(result.state.snapshot_consistency, "consistent")
        raw = canonical_bytes(CanonicalPayload("MarketEnvelope", 1, "synthetic", envelope))
        self.assertEqual(parse_payload(raw).payload, envelope)
        view = select_raw_view(result.state.revisions, as_of=NOW, knowledge_cutoff=NOW, rights=rights(),
                           at=NOW, dataset_version="dataset-v1")
        self.assertEqual(len(view.selected), 1)
        with self.assertRaises(ContractError):
            replace(envelope, content_hash="0"*64)
        with self.assertRaises(ContractError):
            replace(envelope, environment="live")

    def test_pagination_duplicate_and_reobserved_facts(self):
        first = page(terminal=False, cursor_out="cursor.1")
        last = page(cursor_in="cursor.1", items=(item(observation_id="obs.2", source_content_sha256="0"*64),))
        result, fetch = run((first, last))
        self.assertEqual((fetch.calls, len(result.envelope.items)), (2, 2))
        self.assertEqual(result.envelope.quality.status, "complete")
        duplicate, _ = run((first, page(cursor_in="cursor.1")))
        self.assertEqual(len(duplicate.envelope.items), 1)
        self.assertEqual(duplicate.envelope.content_hash, run()[0].envelope.content_hash)

    def test_partial_failure_preserves_records_and_cannot_be_erased(self):
        req = request()
        first = page(terminal=False, cursor_out="cursor.1")
        failed = page(cursor_in="cursor.1", status="failed", terminal=False, items=(), error_reason="synthetic_failure")
        result, fetch = run((first, failed))
        self.assertEqual((fetch.calls, len(result.envelope.items)), (2, 1))
        self.assertEqual(result.envelope.quality.status, "partial")
        after = reduce_page(result.state, req, page(), IngestLimits(), evaluated_at=NOW)
        self.assertIn("failed", after.errors)
        self.assertIn("already_stopped", after.errors)
        self.assertFalse(result.envelope.quality.eligible_for_new_risk)

    def test_rate_limit_stops_without_sleep_or_retry(self):
        limited = page(status="rate_limited", terminal=False, items=(), error_reason="synthetic_limit",
                       not_before="2024-03-08T15:00:00Z")
        result, fetch = run((limited, page()))
        self.assertEqual(fetch.calls, 1)
        self.assertEqual(result.state.not_before, "2024-03-08T15:00:00.000000Z")
        self.assertEqual(result.envelope.quality.status, "unavailable")
        with self.assertRaises(ContractError):
            replace(limited, not_before=None)

    def test_cursor_scope_and_request_mismatch(self):
        first = page(terminal=False, cursor_out="cursor.1")
        for bad in (page(cursor_in="cursor.1", terminal=False, cursor_out="cursor.1"),
                    page(cursor_in="wrong"), page(request_id="wrong"),
                    page(scope=scope(ends_at="2024-03-08T14:33:00Z"))):
            pages = (first, bad) if bad.cursor_in is not None else (bad,)
            result, _ = run(pages)
            self.assertNotEqual(result.envelope.quality.status, "complete")
            self.assertTrue(result.state.errors)

    def test_page_byte_record_and_explicit_deadline_bounds(self):
        first = page(terminal=False, cursor_out="cursor.1")
        result, fetch = run((first, page(cursor_in="cursor.1")), limits=IngestLimits(max_pages=1))
        self.assertEqual(fetch.calls, 1)
        self.assertIn("page_limit", result.state.errors)
        for limits in (IngestLimits(max_bytes=1), IngestLimits(max_records=1)):
            result, _ = run((page(items=(item(), item(observation_id="obs.2"))),), limits=limits)
            self.assertTrue(set(result.state.errors) & {"byte_limit", "record_limit"})
        # A tiny raw response does not bypass accounting for typed normalized records.
        result, _ = run((page(response_bytes=b""),), limits=IngestLimits(max_bytes=100))
        self.assertIn("byte_limit", result.state.errors)
        for stamp in ("2024-03-08T14:29:59Z", "2024-03-08T14:32:01Z"):
            result, _ = run((page(received_at=stamp),))
            self.assertIn("deadline_or_clock", result.state.errors)

    def test_out_of_scope_and_future_observation_are_not_applied(self):
        foreign = item(revision(source_id="foreign.source"))
        future = item(observed_at="2024-03-08T14:31:04Z", ingested_at="2024-03-08T14:31:05Z")
        for record in (foreign, future):
            result, _ = run((page(items=(record,)),))
            self.assertIn("record_scope_or_future", result.state.errors)
            self.assertFalse(result.envelope.items)

    def test_missing_empty_unknown_closed_and_not_collected_are_distinct(self):
        missing, _ = run((page(items=()),))
        self.assertEqual(missing.envelope.quality.status, "unavailable")
        self.assertTrue(missing.envelope.quality.missing_scope)
        req = request(scope=scope(expected=(), coverage_kind="confirmed_empty"))
        empty, _ = run((page(req, items=()),), req=req)
        self.assertEqual(empty.envelope.quality.status, "complete")
        self.assertEqual(empty.envelope.quality.freshness, "unknown")
        unknownreq = request(scope=scope(expected=(), coverage_kind="unknown"))
        unknown, _ = run((page(unknownreq, items=()),), req=unknownreq)
        self.assertIn("coverage_unknown", unknown.state.errors if unknown.state.errors else unknown.envelope.quality.reasons)
        quality = assess_quality(IngestState(), req, IngestLimits(), evaluated_at=NOW, rights_allowed=True)
        self.assertIn("not_terminal", quality.reasons)
        ctx = context()
        closed_cal = calendar(ctx["timezone"], trading_day(ctx["timezone"], "2024-03-08", status="closed"))
        closedreq = request(scope=scope(expected=(), coverage_kind="explicit_closed"))
        closed, _ = run((page(closedreq, items=()),), req=closedreq, calendar=closed_cal)
        self.assertEqual(closed.envelope.quality.status, "complete")
        unverified, _ = run((page(closedreq, items=()),), req=closedreq)
        self.assertIn("closed_coverage_unverified", unverified.state.errors)

    def test_snapshot_unknown_mixed_and_completeness_are_independent(self):
        unknown, _ = run((page(source_snapshot=None),))
        self.assertEqual(unknown.state.snapshot_consistency, "unknown")
        self.assertEqual(unknown.envelope.quality.status, "complete")
        first = page(terminal=False, cursor_out="cursor.1")
        mixed, _ = run((first, page(cursor_in="cursor.1", source_snapshot="snapshot-v2")))
        self.assertEqual(mixed.state.snapshot_consistency, "mixed")
        self.assertEqual(mixed.envelope.quality.status, "complete")
        self.assertIn("snapshot.mixed", mixed.envelope.lineage_refs)

    def test_freshness_uses_each_series_not_global_latest(self):
        old_end = "2024-03-08T14:00:00Z"
        old = item(revision(series_id="syn.old", event_id="syn.old.event", effective_at=old_end,
                            published_at=old_end, payload=bar(starts_at="2024-03-08T13:59:00Z", ends_at=old_end)),
                   observation_id="obs.old")
        req = request(scope=scope(series_ids=("syn.raw", "syn.old"), starts_at="2024-03-08T13:00:00Z",
                    expected=(ExpectedEvent("syn.raw", "syn.event", END), ExpectedEvent("syn.old", "syn.old.event", old_end))))
        state = IngestState(revisions=merge_revision(merge_revision(IngestState().revisions, item())[0], old)[0], terminal=True)
        quality = assess_quality(state, req, IngestLimits(max_age_seconds=60), evaluated_at=NOW, rights_allowed=True)
        self.assertEqual(quality.freshness, "stale")
        self.assertFalse(quality.eligible_for_new_risk)
        result, _ = run(limits=IngestLimits())
        self.assertEqual(result.envelope.quality.freshness, "unknown")
        self.assertFalse(result.envelope.quality.eligible_for_new_risk)

    def test_raw_complete_but_chain_pit_or_publication_unusable_is_blocked(self):
        bad = (
            item(revision(published_at=None, publication_unknown_reason="unknown")),
            item(revision(revision_kind="replacement", predecessor_revision_id="missing")),
        )
        for record in bad:
            result, _ = run((page(items=(record,)),))
            self.assertFalse(result.envelope.quality.missing_scope)
            self.assertFalse(result.envelope.quality.eligible_for_new_risk)
            self.assertIn("pit_not_usable", result.state.errors)
        earlier = request(knowledge_cutoff=END)
        result, _ = run((page(earlier),), req=earlier)
        self.assertIn("pit_not_usable", result.state.errors)

    def test_rights_store_and_current_use_rechecked_no_overwrite(self):
        store = SyntheticMemoryStore()
        result, _ = run(store=store)
        self.assertEqual(store.read("syn.dataset", "dataset-v1", rights=rights(), at=NOW, purpose="research"), result.envelope)
        for grant, stamp, purpose in ((rights(revoked_at=NOW), NOW, "research"),
                                      (rights(), "2025-01-01T00:00:00Z", "research"),
                                      (rights(purposes=("store",)), NOW, "ai"),
                                      (rights(dataset_version="dataset-v2"), NOW, "report")):
            with self.assertRaises(ContractError):
                store.read("syn.dataset", "dataset-v1", rights=grant, at=stamp, purpose=purpose)
        with self.assertRaises(ContractError):
            run(store=store)
        newreq = request(dataset_version="dataset-v2", request_id="syn.request.2")
        newgrant = rights(dataset_version="dataset-v2")
        result2, _ = run((page(newreq),), req=newreq, grant=newgrant, store=store)
        self.assertNotEqual(result.envelope.dataset_version, result2.envelope.dataset_version)
        blocked, fetch = run(grant=rights(revoked_at=NOW), store=store)
        self.assertEqual(fetch.calls, 0)
        self.assertFalse(blocked.envelope.quality.rights_allowed)

    def test_context_failure_preserves_observation_but_denies_use(self):
        ctx = context()
        result, _ = run(calendar=replace(ctx["calendar"], days=()))
        self.assertEqual(len(result.envelope.items), 1)
        self.assertIn("calendar_unknown_or_nonregular", result.state.errors)
        self.assertFalse(result.envelope.quality.eligible_for_new_risk)

    def test_exception_errors_are_redacted_and_no_real_adapter_allowed(self):
        with patch.object(SyntheticPageAdapter, "fetch", side_effect=RuntimeError("synthetic-secret-marker")):
            result, fetch = run()
        self.assertNotIn("synthetic-secret-marker", repr(result))
        self.assertIn("fetch_or_normalization_failed", result.state.errors)
        with self.assertRaises(ContractError):
            ingest(request(), object(), limits=IngestLimits(), rights=rights(), evaluated_at=NOW, **context())
        with self.assertRaises(ContractError):
            run(store=object())
        for changes in ({"environment": "live"}, {"environment": "paper"}, {"knowledge_cutoff": LATER}):
            with self.assertRaises(ContractError):
                request(**changes)
        for changes in ({"max_pages": True}, {"max_records": 129}, {"max_bytes": 0}, {"max_age_seconds": True}):
            with self.assertRaises(ContractError):
                IngestLimits(**changes)
