from dataclasses import FrozenInstanceError, asdict, replace
from decimal import localcontext
import json
import unittest

from quantharbor.domain.market_data import (
    ActionRef, Adjustment, CorporateAction, DatasetManifest, FXObservation, IngestLimits, ManifestFile, MarketItem,
    MarketObservation, MarketRevision, RecordRefSet, RevisionState, item_ref, merge_revision, record_hash, select_raw_view,
    validate_market_context,
)
from quantharbor.domain.primitives import ContractError, FX, Money, Price, Quantity
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from synthetic_market import END, INGESTED, LATER, NOW, OBSERVED, bar, context, item, price, revision, rights


def selected(state, cutoff=NOW, **changes):
    params = dict(as_of=NOW, knowledge_cutoff=cutoff, rights=rights(), at=LATER, dataset_version="dataset-v1")
    return select_raw_view(state, **(params | changes))


def merged(*items):
    state = RevisionState()
    for x in items:
        state, _ = merge_revision(state, x)
    return state


class MarketPayloadTests(unittest.TestCase):
    def test_prices_exact_units_ranges_and_unknown_volume(self):
        with localcontext() as ctx:
            ctx.prec = 1
            self.assertEqual(bar(open=price("10.000000000000000001")).open.amount, "10.000000000000000001")
        for changes in ({"low": price("0")}, {"high": price("8")}, {"close": price("13")},
                        {"open": Price("10", "KRW", "syn.instrument", "share")},
                        {"volume": Quantity("-1", "syn.instrument", "share")},
                        {"volume": Quantity("1", "other", "share")},
                        {"volume": None}, {"starts_at": END}, {"open": 10.0}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                bar(**changes)
        self.assertIsNone(bar(volume=None, volume_unknown_reason="source_unknown").volume)
        with self.assertRaises(FrozenInstanceError):
            bar().close = price()

    def test_adjustment_metadata_and_future_evidence(self):
        details = Adjustment("split", "adjust-v1", END,
            (ActionRef("synthetic", "syn.source", "syn.dataset", "syn.actions", "syn.split", "split.1", "0"*64),),
            END, "syn.action.evidence")
        with self.assertRaises(ContractError):
            bar(adjustment_details=details)
        with self.assertRaises(ContractError):
            bar(adjustment="adjusted")
        adjusted = revision(payload=bar(adjustment="adjusted", adjustment_details=details), series_id="syn.adjusted")
        view = selected(merged(item(adjusted)))
        self.assertFalse(view.selected)
        self.assertIn("adjustment_unverified", view.held_reasons)
        with self.assertRaises(ContractError):
            replace(adjusted, payload=bar(adjustment="adjusted", adjustment_details=replace(details, knowledge_at=LATER)))
        with self.assertRaises(ContractError):
            replace(details, action_refs=["split.1"])

    def test_fx_direction_and_split_dividend_dates_remain_distinct(self):
        fx = FXObservation(FX("USD", "KRW", "1300.25", END, "syn.source"))
        r = revision(payload=fx)
        self.assertEqual(r.payload.fx.rate, "1300.25")
        inverse = FXObservation(FX("KRW", "USD", "0.0007", END, "syn.source"))
        self.assertNotEqual(record_hash(r), record_hash(replace(r, payload=inverse)))
        with self.assertRaises(ContractError):
            FXObservation(FX("USD", "USD", "1", END, "syn.source"))
        with self.assertRaises(ContractError):
            replace(r, payload=FXObservation(FX("USD", "KRW", "1", END, "wrong.source")))
        split = CorporateAction("syn.instrument", "syn.listing", "syn.venue", "SYN", "split", "share",
                                "2024-03-08", None, None, "not_provided", "3", "2", None)
        dividend = replace(split, action_kind="cash_dividend", numerator=None, denominator=None,
                           cash_per_unit=Money("0.25", "USD"), record_date="2024-03-09", payment_date="2024-04-01",
                           dates_unknown_reason=None)
        self.assertNotEqual(dividend.effective_date, dividend.record_date)
        self.assertNotEqual(dividend.record_date, dividend.payment_date)
        for changes in ({"numerator": "0"}, {"denominator": "-1"}, {"numerator": True},
                        {"cash_per_unit": Money("1", "USD")}, {"dates_unknown_reason": None}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(split, **changes)
        self.assertIsNone(validate_market_context(item(revision(payload=split)), **context(), knowledge_cutoff=NOW))

    def test_identity_nullable_and_observation_order(self):
        for changes in ({"schema_version": True}, {"environment": "paper"}, {"predecessor_revision_id": "rev.x"},
                        {"revision_kind": "delta"}, {"published_at": None}, {"payload": {}},
                        {"effective_at": "2024-03-08T14:31:00"}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                revision(**changes)
        unknown = revision(published_at=None, publication_unknown_reason="source_unknown")
        self.assertIsNone(unknown.published_at)
        with self.assertRaises(ContractError):
            item(observed_at=LATER)
        with self.assertRaises(ContractError):
            item(revision(published_at=NOW))
        with self.assertRaises(ContractError):
            item(revision_hash="0" * 64)


class RevisionTests(unittest.TestCase):
    def test_duplicate_reobservation_and_conflict_are_separate(self):
        first = item()
        state, status = merge_revision(RevisionState(), first)
        self.assertEqual(status, "accepted")
        self.assertEqual(merge_revision(state, first), (state, "duplicate"))
        second = item(observation_id="obs.2", source_content_sha256="0" * 64)
        state, status = merge_revision(state, second)
        self.assertEqual((len(state.items), status), (2, "accepted"))
        self.assertEqual(len(selected(state).selected), 1)
        conflict = item(revision(payload=bar(close=price("10"))), observation_id="obs.3")
        conflicted, status = merge_revision(state, conflict)
        self.assertEqual(status, "conflict")
        self.assertEqual(len(conflicted.items), 2)
        self.assertIn("revision_conflict", selected(conflicted).held_reasons)
        self.assertFalse(selected(conflicted).selected)

    def test_chain_follows_predecessor_not_revision_sort_and_pit_restated(self):
        original = item()
        corrected = item(revision(revision_id="rev.a", predecessor_revision_id="rev.z", revision_kind="replacement",
                                  payload=bar(close=price("10")), published_at="2024-03-08T14:32:00Z"),
                         observation_id="obs.2", observed_at="2024-03-08T14:32:01Z", ingested_at="2024-03-08T14:32:02Z")
        state = merged(corrected, original)
        self.assertEqual(selected(state).selected[0].revision.revision_id, "rev.z")
        restated = selected(state, LATER, mode="restated", original_cutoff=NOW)
        self.assertEqual(restated.selected[0].revision.revision_id, "rev.a")
        self.assertEqual(selected(state).selected[0].revision.payload.close.amount, "11")
        with self.assertRaises(ContractError):
            selected(state, NOW, mode="restated", original_cutoff=NOW)

    def test_missing_fork_cycle_cross_identity_and_tombstone_are_held(self):
        a = revision(revision_id="a", predecessor_revision_id="b", revision_kind="replacement")
        b = revision(revision_id="b", predecessor_revision_id="a", revision_kind="replacement")
        child = revision(revision_id="child", predecessor_revision_id="rev.z", revision_kind="replacement")
        fork = replace(child, revision_id="fork")
        for records in ((item(child),), (item(a), item(b, observation_id="obs.b")),
                        (item(), item(child, observation_id="obs.c"), item(fork, observation_id="obs.f")),
                        (item(), item(replace(child, event_id="other.event"), observation_id="obs.c"))):
            with self.subTest(records=len(records)):
                view = selected(merged(*records))
                # A separate good identity may remain; no invalid child is selected.
                self.assertFalse(any(x.revision.revision_id in ("a", "b", "child", "fork") for x in view.selected))
                self.assertTrue(view.held_reasons)
        for kind in ("retraction", "unsupported"):
            tomb = replace(child, revision_kind=kind, payload=None)
            state = merged(item(), item(tomb, observation_id="obs.tomb"))
            self.assertFalse(selected(state).selected)
            self.assertIn(kind, selected(state).held_reasons)
            self.assertEqual(len(state.items), 2)

    def test_publication_ingestion_future_effective_and_rights_cutoffs(self):
        unknown = item(revision(published_at=None, publication_unknown_reason="unknown"))
        self.assertIn("publication_unknown", selected(merged(unknown)).held_reasons)
        self.assertFalse(selected(merged(item()), "2024-03-08T14:31:01Z").selected)
        future = item(revision(effective_at="2024-03-08T14:32:00Z", payload=bar(ends_at="2024-03-08T14:32:00Z")))
        self.assertFalse(selected(merged(future)).selected)
        self.assertIn("rights_blocked", selected(merged(item()), rights=rights(revoked_at=NOW)).held_reasons)
        self.assertFalse(selected(merged(item(rights_ref="other.rights"))).selected)
        with self.assertRaises(ContractError):
            selected(merged(item()), "2025-01-01T00:00:00Z")

    def test_late_conflict_does_not_rewrite_earlier_cutoff(self):
        original = item()
        conflict = item(revision(payload=bar(close=price("10"))), observation_id="obs.late",
                        observed_at="2024-03-08T15:00:00Z", ingested_at="2024-03-08T15:00:01Z")
        state = merged(original, conflict)
        self.assertEqual(selected(state).selected, (original,))
        self.assertIn("revision_conflict", selected(state, LATER).held_reasons)
        self.assertEqual(state.conflicts[0].incoming, conflict)

    def test_reobservation_selection_does_not_depend_on_page_order(self):
        old = item()
        new = item(observation_id="obs.new", observed_at="2024-03-08T14:31:02Z", ingested_at=NOW)
        self.assertEqual(selected(merged(old, new)), selected(merged(new, old)))

    def test_q16_catalog_calendar_bindings_fail_closed(self):
        ctx = context()
        self.assertIsNone(validate_market_context(item(), **ctx, knowledge_cutoff=NOW))
        for changes in ({"calendar_version": "unknown"}, {"catalog_version": "unknown"}):
            self.assertEqual(validate_market_context(item(**changes), **ctx, knowledge_cutoff=NOW), "context_version_mismatch")
        unknown = item(revision(payload=bar(source_code="MISSING")))
        self.assertEqual(validate_market_context(unknown, **ctx, knowledge_cutoff=NOW), "catalog_unknown_or_ineligible")
        wrong = dict(ctx, calendar=replace(ctx["calendar"], venue_id="other.venue"))
        self.assertEqual(validate_market_context(item(), **wrong, knowledge_cutoff=NOW), "calendar_venue_mismatch")
        missing = dict(ctx, calendar=replace(ctx["calendar"], days=()))
        self.assertEqual(validate_market_context(item(), **missing, knowledge_cutoff=NOW), "calendar_unknown_or_nonregular")
        with self.assertRaises(ContractError):
            validate_market_context(item(), **dict(ctx, calendar=replace(ctx["calendar"], rules_sha256="0"*64)), knowledge_cutoff=NOW)


class MarketCanonicalTests(unittest.TestCase):
    def test_nested_roundtrip_golden_and_source_hash_separation(self):
        r = revision()
        encoded = canonical_bytes(CanonicalPayload("MarketRevision", 1, "synthetic", r))
        self.assertEqual(parse_payload(encoded).payload, r)
        self.assertIn(b'"publication_unknown_reason":null', encoded)
        self.assertEqual(record_hash(r), "2b603e8e6afd98dc8ba07fb1e6e002949635864fb4e0e2a1494fd6f8ca6891d5")
        o = item().observation
        self.assertEqual(parse_payload(canonical_bytes(CanonicalPayload("MarketObservation", 1, "synthetic", o))).payload, o)
        self.assertNotEqual(o.source_content_sha256, o.revision_hash)
        refs = RecordRefSet(1, "synthetic", (item_ref(item(observation_id="obs.2")), item_ref(item())))
        reverse = replace(refs, records=tuple(reversed(refs.records)))
        self.assertEqual(record_hash(refs), record_hash(reverse))
        self.assertEqual(parse_payload(canonical_bytes(CanonicalPayload("RecordRefSet", 1, "synthetic", refs))).payload, refs)

    def test_nested_unknown_missing_duplicate_type_environment_and_size_rejected(self):
        base = json.loads(canonical_bytes(CanonicalPayload("MarketRevision", 1, "synthetic", revision())))
        for change in ("unknown", "missing", "float", "bool", "null", "surrogate", "environment", "payload"):
            value = json.loads(json.dumps(base))
            p = value["payload"]["payload"]
            if change == "unknown": p["extra"] = 1
            elif change == "missing": del p["volume_unknown_reason"]
            elif change in ("float", "bool", "null", "surrogate"): p["open"]["amount"] = {"float":1.0,"bool":True,"null":None,"surrogate":"\ud800"}[change]
            elif change == "environment": value["environment"] = "live"
            else: value["payload"]["payload"] = {"arbitrary": "dict"}
            with self.subTest(change=change), self.assertRaises(ContractError):
                parse_payload(json.dumps(value))
        raw = canonical_bytes(CanonicalPayload("MarketRevision", 1, "synthetic", revision()))
        with self.assertRaises(ContractError):
            parse_payload(raw.replace(b'"amount":"10"', b'"amount":"10","amount":"10"', 1))
        with self.assertRaises(ContractError):
            parse_payload(b" " * 65537)
        with self.assertRaises(ContractError):
            RecordRefSet(1, "synthetic", (item_ref(item()), item_ref(item())))
        with self.assertRaises(ContractError):
            RecordRefSet(1, "synthetic", (item_ref(item()),
                item_ref(item(revision(payload=bar(close=price("10"))), observation_id="obs.other"))))
        forged = revision()
        object.__setattr__(forged.payload.open, "amount", 1.0)
        with self.assertRaises(ContractError):
            record_hash(forged)

    def test_manifest_schema_hash_counts_paths_and_exact_nullable_fields(self):
        refs = RecordRefSet(1, "synthetic", (item_ref(item()),))
        file = ManifestFile("chunk-1.parquet", 100, "0"*64, 1, record_hash(refs))
        manifest = DatasetManifest(1, "synthetic", "syn.dataset", "dataset-v1", None, "normalize-v1",
                    "qh-canonical-json-v1", "syn.source", "2024-03-08T00:00:00Z", "2024-03-09T00:00:00Z",
                    (file,), refs, record_hash(refs), "syn.quality", "syn.rights", "as_known", NOW, NOW, NOW)
        self.assertEqual(parse_payload(canonical_bytes(CanonicalPayload("DatasetManifest", 1, "synthetic", manifest))).payload, manifest)
        for changes in ({"files": (file,file)}, {"previous_version": "dataset-v1"}, {"record_set_hash": "1"*64},
                        {"files": ()}, {"schema_version": True}, {"environment": "live"}):
            with self.subTest(changes=changes), self.assertRaises(ContractError):
                replace(manifest, **changes)
        for name in ("../chunk.parquet", "/chunk.parquet", "folder/chunk.parquet", "x.txt"):
            with self.assertRaises(ContractError):
                replace(file, name=name)
        with self.assertRaises(ContractError):
            replace(file, row_count=True)
