from dataclasses import replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from quantharbor.application.market_ingest import replay_storage
from quantharbor.domain.market_data import IngestLimits, page_facts, reduce_page, reduce_page_facts, IngestState
from quantharbor.domain.market_storage import (
    CANONICAL_VERSION, REDUCER_VERSION, STORAGE_VERSION, FileRef, MarketEvidenceIndex, MarketStorageManifest,
    claim_ref, evidence_index, summary_for,
)
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from synthetic_market import LATER, NOW, context, item, page, request, rights
from synthetic_market_storage import collect, conflict_bundle, rich_bundle


class StorageContractTests(unittest.TestCase):
    def replay(self, bundle):
        state, envelope = replay_storage(bundle.descriptor, bundle.receipts, bundle.evidence, **context())
        self.assertEqual((state, envelope), (bundle.state, bundle.envelope))
        self.assertEqual(summary_for(state, envelope), bundle.summary)

    def test_actual_response_and_reference_facts_use_same_core(self):
        req, result = request(), page()
        facts = page_facts(result)
        self.assertEqual(facts.response_size_bytes, len(result.response_bytes))
        self.assertEqual(facts.response_sha256, sha256(result.response_bytes).hexdigest())
        self.assertEqual(reduce_page(IngestState(), req, result, IngestLimits(), evaluated_at=NOW),
                         reduce_page_facts(IngestState(), req, facts, IngestLimits(), evaluated_at=NOW))
        self.replay(collect().bundle)

    def test_complete_conflict_reobservations_and_exact_claim_index(self):
        for bundle in (rich_bundle(), conflict_bundle(), conflict_bundle(observation_collision=True)):
            self.replay(bundle)
            refs = evidence_index(bundle.evidence)
            self.assertEqual(len(refs.claims), len(bundle.evidence))
            self.assertEqual(refs.claims, tuple(sorted(refs.claims, key=lambda x:x.key)))
        bundle = conflict_bundle()
        self.assertEqual(len(bundle.evidence), 3)
        self.assertEqual(len(bundle.state.revisions.items), 2)
        self.assertEqual(bundle.state.revisions.conflicts[0].detected_at, "2024-03-08T14:40:00.000000Z")

    def test_partial_failed_rate_normalization_rejection_and_fetch_trace(self):
        def pages(req):
            return (page(req, terminal=False, cursor_out="c.1"),
                    page(req, cursor_in="c.1", status="failed", terminal=False, items=(), error_reason="synthetic_failure"))
        bundles = [collect(pages=pages).bundle, collect(limits=IngestLimits(max_bytes=1)).bundle,
                   collect(pages=lambda req: ()).bundle]
        for status in ("rate_limited", "normalization_failed"):
            bundles.append(collect(pages=lambda req, status=status: (page(req, status=status, terminal=False, items=(),
                error_reason="synthetic_failure", not_before="2024-03-08T15:00:00Z" if status=="rate_limited" else None),)).bundle)
        for bundle in bundles:
            self.replay(bundle)
            self.assertFalse(bundle.envelope.quality.eligible_for_new_risk)
        self.assertEqual(bundles[1].receipts[0].kind, "rejection")
        self.assertEqual(bundles[1].receipts[0].item_refs, ())
        self.assertEqual(bundles[2].receipts[0].kind, "fetch_failure")
        def bad_cursor(req):
            return (page(req, terminal=False, cursor_out="c.1"), page(req, cursor_in="wrong", items=()))
        self.replay(collect(pages=bad_cursor).bundle)

    def test_body_rejection_binds_preserved_request_scope_cursor_and_clock(self):
        def pages(req):
            return (page(req, items=(), response_bytes=b"", terminal=False, cursor_out="c.1",
                         received_at="2024-03-08T14:31:02Z"), page(req, cursor_in="c.1"))
        bundle = collect(limits=IngestLimits(max_bytes=1), pages=pages).bundle
        self.replay(bundle)
        receipt = bundle.receipts[-1]
        self.assertEqual(receipt.error_reason, "byte_limit")
        mutations = ({"request_id": "wrong"}, {"scope": replace(receipt.scope, coverage_ref="wrong.scope")},
                     {"cursor_in": "wrong.cursor"}, {"received_at": "2024-03-08T14:31:04Z"},
                     {"received_at": "2024-03-08T14:31:01Z"}, {"received_at": "2024-03-08T14:29:59Z"},
                     {"received_at": "2024-03-09T00:02:00Z"}, {"cursor_out": "c.1", "terminal": False})
        for mutation in mutations:
            with self.subTest(mutation=tuple(mutation)), self.assertRaises(ContractError):
                changed = bundle.receipts[:-1] + (replace(receipt, **mutation),)
                replay_storage(bundle.descriptor, changed, bundle.evidence, **context())

    def test_original_metadata_rejections_replay_with_their_actual_reason(self):
        mutations = ({"request_id": "wrong"}, {"scope": replace(request().scope, coverage_ref="wrong.scope")},
                     {"cursor_in": "wrong.cursor"}, {"received_at": "2024-03-08T14:31:04Z"},
                     {"received_at": "2024-03-08T14:31:01Z"}, {"received_at": "2024-03-08T14:29:59Z"},
                     {"received_at": "2024-03-09T00:02:00Z"}, {"cursor_out": "c.1", "terminal": False})
        for mutation in mutations:
            def pages(req):
                return (page(req, items=(), response_bytes=b"", terminal=False, cursor_out="c.1",
                             received_at="2024-03-08T14:31:02Z"),
                        replace(page(req, cursor_in="c.1"), **mutation))
            bundle = collect(limits=IngestLimits(max_bytes=1), pages=pages).bundle
            self.replay(bundle)
            self.assertIn(bundle.receipts[-1].error_reason,
                          ("scope_or_cursor_mismatch", "deadline_or_clock", "page_clock_invalid", "repeated_cursor"))
            with self.subTest(mutation=tuple(mutation)), self.assertRaises(ContractError):
                changed = bundle.receipts[:-1] + (replace(bundle.receipts[-1], error_reason="byte_limit"),)
                replay_storage(bundle.descriptor, changed, bundle.evidence, **context())

    def test_page_order_repeats_and_omitted_or_extra_evidence_rejected(self):
        bundle = collect(pages=lambda req: (page(req, items=(item(), item())),)).bundle
        self.assertEqual(len(bundle.receipts[0].item_refs), 2)
        self.assertEqual(bundle.state.records_received, 2)
        self.assertEqual(len(bundle.evidence), 1)
        self.replay(bundle)
        for receipts, evidence in (((), bundle.evidence), (bundle.receipts, ()),
                                  (bundle.receipts, bundle.evidence+(item(observation_id="extra"),))):
            with self.assertRaises(ContractError):
                replay_storage(bundle.descriptor, receipts, evidence, **context())
        with self.assertRaises(ContractError):
            replay_storage(replace(bundle.descriptor, request=replace(bundle.descriptor.request, request_id="wrong")),
                           bundle.receipts, bundle.evidence, **context())
        unfinished = collect(pages=lambda req: (page(req, terminal=False, cursor_out="c.1"),),
                             limits=IngestLimits(max_pages=1)).bundle
        with self.assertRaises(ContractError):
            replay_storage(replace(unfinished.descriptor, limits=IngestLimits(max_pages=2)),
                           unfinished.receipts, unfinished.evidence, **context())
        with self.assertRaises(ContractError):
            MarketEvidenceIndex(1, "synthetic", (claim_ref(item()), claim_ref(item())))

    def test_four_registered_schemas_roundtrip_and_nested_strictness(self):
        bundle = rich_bundle()
        file = FileRef("descriptor", "descriptor.json", 1, "0"*64, None)
        receipt = FileRef("receipt", "receipt-0001.json", 1, "0"*64, None)
        evidence = FileRef("evidence", "evidence-0000.parquet", 1, "0"*64, len(bundle.evidence))
        manifest = MarketStorageManifest(1, "synthetic", "syn.source", "syn.dataset", "dataset-v1", None, NOW,
            STORAGE_VERSION, REDUCER_VERSION, CANONICAL_VERSION, file, (receipt,), (evidence,), len(bundle.evidence),
            bundle.summary.evidence_index_hash, bundle.summary.accepted_record_set_hash, bundle.summary)
        values = (bundle.descriptor, bundle.receipts[0], evidence_index(bundle.evidence), manifest)
        for value in values:
            wrapper = CanonicalPayload(type(value).__name__, 1, "synthetic", value)
            raw = canonical_bytes(wrapper)
            self.assertEqual(parse_payload(raw), wrapper)
            bad = json.loads(raw)
            bad["payload"]["unknown"] = None
            with self.assertRaises(ContractError): parse_payload(json.dumps(bad))
            with self.assertRaises(ContractError): replace(value, schema_version=True)
        for name in ("../data.parquet", "dir/data.parquet", "/data.parquet", "bad.txt"):
            with self.assertRaises(ContractError): replace(evidence, name=name)
        bad = json.loads(canonical_bytes(CanonicalPayload("MarketIngestDescriptor", 1, "synthetic", bundle.descriptor)))
        bad["payload"]["limits"]["max_pages"] = True
        with self.assertRaises(ContractError): parse_payload(json.dumps(bad))
        with self.assertRaises(ContractError): replace(manifest, reducer_version="unknown")
        with self.assertRaises(ContractError): replace(manifest, evidence_count=0)

    def test_context_bytes_digest_cannot_be_rebound_by_same_version(self):
        bundle = collect().bundle
        ctx = context()
        cat = ctx["catalog"]
        changed = replace(cat, instruments=(replace(cat.instruments[0], classification_evidence_ref="changed"),))
        with self.assertRaises(ContractError):
            replay_storage(bundle.descriptor, bundle.receipts, bundle.evidence, **(ctx|{"catalog":changed}))
