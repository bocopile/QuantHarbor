from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from itertools import permutations
import json
import unittest

from quantharbor.application.document_ingest import collect_documents, validate_bundle
from quantharbor.domain.documents import (
    DocumentBundle, DocumentClaim, DocumentEntityContext, DocumentFileRef, DocumentOriginal,
    claim_ref, encoded, original, revision_ref, select_view,
)
from quantharbor.domain.market_data import record_hash
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, parse_payload
from synthetic_documents import (
    INGESTED, KNOWN, LATER, NOW, OBSERVED, PUBLISHED, batch, catalog, document, entity_context, limits, request, rights,
)


def view(bundle, **changes):
    values = dict(catalog=catalog(), rights=rights(), evaluated_at=LATER, knowledge_cutoff=NOW)
    return select_view(bundle, **(values|changes))


class DocumentContractTests(unittest.TestCase):
    def test_exact_unicode_newline_raw_canonical_and_frozen_values(self):
        text = "합성é\nline\r\n\t\x00"
        value = original(text)
        self.assertEqual(value.text, text)
        self.assertEqual(value.utf8_byte_length, len(text.encode()))
        self.assertEqual(value.raw_sha256, sha256(text.encode()).hexdigest())
        self.assertNotEqual(value.raw_sha256, record_hash(value))
        self.assertNotEqual(record_hash(original("é")), record_hash(original("e\u0301")))
        self.assertNotEqual(record_hash(original("x\n")), record_hash(original("x\r\n")))
        self.assertEqual(record_hash(original("synthetic\n")), "1eb2f5421350516ba1f409995b04a4565c6133da66d69502d5c25d934058809f")
        self.assertEqual(parse_payload(encoded(value)).payload, value)
        with self.assertRaises(FrozenInstanceError): value.text = "changed"
        self.assertEqual(original("x"*8192).utf8_byte_length, 8192)
        for text in ("", "x"*8193, "한"*2731, "\ud800", None, b"text", True):
            with self.subTest(text_type=type(text).__name__), self.assertRaises(ContractError): original(text)
        for change in ({"utf8_byte_length":True}, {"raw_sha256":"0"*64}, {"media_type":"text/html"}, {"encoding":"latin-1"}):
            with self.assertRaises(ContractError): replace(value, **change)

    def test_url_metadata_and_exact_nullable_action_fields(self):
        for url in ("file:///private", "ftp://synthetic.invalid/x", "https:///no-host", "https://user:pass@synthetic.invalid/x",
                    "https://synthetic.invalid/\n", "https://synthetic.invalid/\x85", "https://synthetic.invalid/\ud800",
                    "https://synthetic.invalid:99999/x", "https://a..invalid/x", "https://synthetic.invalid/"+"x"*2048):
            with self.subTest(url_prefix=url[:8]), self.assertRaises(ContractError): document(revision_changes={"source_url":url})
        value = document()[1].revision
        for change in ({"action":"delta"}, {"predecessor_revision_id":"other"}, {"original_hash":None},
                       {"published_at":None}, {"environment":"live"}, {"schema_version":True}):
            with self.assertRaises(ContractError): replace(value, **change)
        retract = document(revision_changes={"action":"retract", "revision_id":"rev.t", "predecessor_revision_id":"rev.z"})
        self.assertIsNone(retract[0])
        with self.assertRaises(ContractError): replace(retract[1].revision, original_absent_reason=None)
        with self.assertRaises(ContractError): replace(document()[1].observation, observed_at=LATER)

    def test_five_closed_schemas_and_nested_decoder_boundaries(self):
        bundle = batch()
        values = (bundle.originals[0], bundle.claims[0].revision, bundle.claims[0].observation, bundle.context, bundle.manifest)
        for value in values:
            self.assertEqual(parse_payload(encoded(value)).payload, value)
            raw = json.loads(encoded(value))
            for operation in ("extra", "missing", "version", "environment"):
                changed = json.loads(json.dumps(raw))
                if operation == "extra": changed["payload"]["unknown"] = None
                elif operation == "missing": del changed["payload"][next(iter(changed["payload"]))]
                elif operation == "version": changed["schema_version"] = True
                else: changed["environment"] = "paper"
                with self.assertRaises(ContractError): parse_payload(json.dumps(changed))
        raw = encoded(bundle.manifest)
        with self.assertRaises(ContractError): parse_payload(raw.replace(b'"max_claims":16', b'"max_claims":16,"max_claims":16'))
        for x in (True, None, 1.0, float("nan")):
            changed = json.loads(encoded(bundle.originals[0])); changed["payload"]["utf8_byte_length"] = x
            with self.assertRaises(ContractError): parse_payload(json.dumps(changed))
        with self.assertRaises(ContractError): parse_payload(b" "*65537)
        forged = original("x"); object.__setattr__(forged, "text", "\ud800")
        with self.assertRaises(ContractError): record_hash(forged)

    def test_receipt_scope_clock_counts_missing_and_byte_limits(self):
        for change in ({"request_id":"wrong"}, {"scope_ref":"wrong"}, {"received_at":"2024-03-08T14:29:00Z"},
                       {"received_at":"2024-03-08T14:31:04Z"}, {"claim_refs":()}, {"missing_document_ids":("doc.2",), "complete":False},
                       {"complete":True, "terminal_ref":None}):
            with self.assertRaises(ContractError): batch(receipt_changes=change)
        for policy in (limits(max_claims=1), limits(max_bytes=1)):
            with self.assertRaises(ContractError): batch((document(), document()), policy=policy)
        for change in ({"max_claims":True}, {"max_age_seconds":0}, {"max_bytes":4194305}):
            with self.assertRaises(ContractError): limits(**change)
        duplicate = batch((document(), document()))
        self.assertEqual(len(duplicate.claims), 1)
        self.assertEqual(len(duplicate.manifest.receipt.claim_refs), 2)
        with self.assertRaises(ContractError): batch((document(),)*17)
        with self.assertRaises(ContractError): batch(req=request(document_ids=("other",), expected_document_ids=()))
        with self.assertRaises(ContractError): batch((document(observation_changes={"dataset_version":"other-version"}),))

    def test_partial_empty_failed_and_not_collected_are_distinct(self):
        partial = batch((document(),), req=request(expected_document_ids=("doc.1","doc.missing")))
        self.assertEqual(view(partial).status, "partial")
        self.assertEqual(view(partial).freshness, "unknown")
        self.assertEqual(view(partial).missing_document_ids, ("doc.missing",))
        empty = batch((), req=request(expected_document_ids=()))
        self.assertEqual(view(empty).status, "complete")
        self.assertEqual(view(empty).freshness, "unknown")
        not_collected = batch((), receipt_changes={"status":"not_collected", "complete":False, "error_reason":"not_attempted"})
        self.assertEqual(view(not_collected).status, "not_collected")
        failed = batch(receipt_changes={"status":"failed", "complete":False, "error_reason":"synthetic_failure"})
        self.assertEqual(len(failed.claims), 1)
        self.assertEqual(view(failed).status, "partial")
        with self.assertRaises(ContractError): batch(receipt_changes={"status":"not_collected", "complete":False})

    def test_unknown_and_contradictory_publication_do_not_become_pit(self):
        unknown = document(revision_changes={"published_at":None, "publication_unknown_reason":"not_provided"})
        result = view(batch((unknown,)), evaluated_at=NOW)
        self.assertFalse(result.selected)
        self.assertIn("publication_unknown", result.held_reasons)
        self.assertEqual(result.freshness, "unknown")
        contradictory = document(revision_changes={"published_at":NOW})
        self.assertIn("publication_observation_conflict", view(batch((contradictory,))).held_reasons)
        self.assertFalse(view(batch(), knowledge_cutoff=OBSERVED).selected)
        self.assertIn("receipt_after_cutoff", view(batch(), knowledge_cutoff=INGESTED).held_reasons)

    def test_explicit_entity_and_exact_catalog_link_time_and_etf_meaning(self):
        bundle = batch()
        result = view(bundle, evaluated_at=NOW, use="instrument_research", instrument_id="syn.instrument", listing_venue_id="syn.listing")
        self.assertTrue(result.usable_for_research)
        self.assertEqual(result.selected[0].instrument_links[0].relation, "issuer")
        unlinked = batch(context=entity_context((document()[1],), links=False))
        self.assertFalse(view(unlinked).selected)
        preserved = view(unlinked, use="preserve", evaluated_at=NOW)
        self.assertEqual(len(preserved.selected), 1)
        self.assertFalse(preserved.usable_for_research)
        late = batch(context=entity_context((document()[1],), known=LATER))
        self.assertFalse(view(late).selected)
        for change in ({"catalog_version":"wrong"}, {"instrument_version":"wrong"}, {"listing_venue_id":"wrong"},
                       {"known_at":LATER}, {"valid_to":PUBLISHED}):
            changed = replace(bundle.context, instrument_links=(replace(bundle.context.instrument_links[0], **change),))
            candidate = batch(context=changed)
            self.assertFalse(view(candidate, use="instrument_research", instrument_id="syn.instrument", listing_venue_id="syn.listing").selected)
        cat = catalog()
        etf = replace(cat, instruments=(replace(cat.instruments[0], product_kind="etf", etf_kind="general"),))
        etf_bundle = batch(cat=etf, context=entity_context((document()[1],), cat=etf, entity_kind="fund_issuer"))
        etf_view = view(etf_bundle, catalog=etf, use="instrument_research", instrument_id="syn.instrument", listing_venue_id="syn.listing")
        self.assertEqual(etf_view.selected[0].entities[0].kind, "fund_issuer")
        with self.assertRaises(ContractError): replace(bundle.context.instrument_links[0], relation="holding")
        with self.assertRaises(ContractError): view(bundle, catalog=etf)
        with self.assertRaises(ContractError): replace(bundle.context, entities=(bundle.context.entities[0],)*2)
        with self.assertRaises(ContractError): replace(bundle.context, instrument_links=bundle.context.instrument_links*2)
        with self.assertRaises(ContractError): replace(bundle.context, document_links=(replace(bundle.context.document_links[0], entity_version="missing"),))

    def test_research_use_requires_research_plus_requested_purpose(self):
        bundle = batch()
        for purpose in ("store", "report", "ai"):
            for use in ("entity_research", "instrument_research"):
                query = dict(use=use, purpose=purpose, evaluated_at=NOW)
                if use == "instrument_research":
                    query.update(instrument_id="syn.instrument", listing_venue_id="syn.listing")
                with self.subTest(purpose=purpose, use=use), self.assertRaises(ContractError):
                    view(bundle, rights=rights(purposes=(purpose,)), **query)
                allowed = view(bundle, rights=rights(purposes=(purpose,"research")), **query)
                self.assertTrue(allowed.usable_for_research)
                with self.assertRaises(ContractError):
                    view(bundle, rights=rights(purposes=("research",)), **query)
            preserved = view(bundle, rights=rights(purposes=(purpose,)), purpose=purpose, use="preserve", evaluated_at=NOW)
            self.assertTrue(preserved.selected)
            self.assertFalse(preserved.usable_for_research)

    def test_current_rights_scope_purpose_expiry_and_freshness(self):
        bundle = batch()
        self.assertEqual(view(bundle, evaluated_at=NOW).freshness, "fresh")
        self.assertEqual(view(bundle).freshness, "stale")
        for grant, at, purpose in ((rights(revoked_at=NOW), NOW, "research"), (rights(), "2025-01-01T00:00:00Z", "research"),
                                  (rights(purposes=("store",)), NOW, "ai"), (rights(dataset_version="other"), NOW, "research")):
            with self.assertRaises(ContractError): view(bundle, rights=grant, evaluated_at=at, purpose=purpose)
        with self.assertRaises(ContractError): batch((document(observation_changes={"rights_ref":"wrong"}),))
        with self.assertRaises(ContractError): batch(grant=rights(revoked_at=NOW))
        with self.assertRaises(ContractError): validate_bundle(bundle, catalog=catalog(), rights=rights(revoked_at=NOW), at=NOW)


class DocumentChainTests(unittest.TestCase):
    def corrected(self, action="replace", **changes):
        values = dict(revision_id="rev.a", predecessor_revision_id="rev.z", action=action, published_at="2024-03-08T15:00:00Z")
        return document("corrected synthetic", revision_changes=values|changes,
                        observation_changes={"observation_id":"doc.obs.2", "observed_at":"2024-03-08T15:00:01Z", "ingested_at":"2024-03-08T15:00:02Z"})

    def test_reverse_revision_order_restated_and_retraction_preserve_original(self):
        first, second = document(), self.corrected()
        value = batch((second, first), at=LATER)
        old = view(value, use="preserve")
        new = view(value, knowledge_cutoff=LATER, use="preserve", mode="restated", original_cutoff=NOW)
        self.assertEqual(old.selected[0].claim.revision.revision_id, "rev.z")
        self.assertEqual(new.selected[0].claim.revision.revision_id, "rev.a")
        self.assertEqual(new.original_cutoff, "2024-03-08T14:31:03.000000Z")
        self.assertEqual(len(value.originals), 2)
        tomb = batch((first, self.corrected(action="retract")), at=LATER)
        self.assertFalse(view(tomb, knowledge_cutoff=LATER).selected)
        self.assertIn("retracted", view(tomb, knowledge_cutoff=LATER).held_reasons)
        self.assertEqual(len(tomb.claims), 2)
        with self.assertRaises(ContractError): view(value, mode="restated", original_cutoff=NOW)

    def test_missing_fork_cycle_kind_change_and_retract_successor_are_held(self):
        first = document()
        second = self.corrected()
        fork = document("fork", revision_changes={"action":"replace", "revision_id":"fork", "predecessor_revision_id":"rev.z"},
                        observation_changes={"observation_id":"fork.obs"})
        cycle_a = document("cycle a", revision_changes={"action":"replace", "revision_id":"a", "predecessor_revision_id":"b"})
        cycle_b = document("cycle b", revision_changes={"action":"replace", "revision_id":"b", "predecessor_revision_id":"a"},
                           observation_changes={"observation_id":"cycle.obs"})
        after_tomb = self.corrected(revision_id="after", predecessor_revision_id="rev.a")
        after_tomb = (after_tomb[0], replace(after_tomb[1], observation=replace(after_tomb[1].observation, observation_id="after.obs")))
        for items in ((second,), (first,second,fork), (cycle_a,cycle_b),
                      (first,self.corrected(kind="news")), (first,self.corrected(action="retract"),after_tomb)):
            result = view(batch(items, at=LATER), knowledge_cutoff=LATER, use="preserve")
            self.assertFalse(result.selected)
            self.assertTrue(set(result.held_reasons)&{"chain_missing_or_fork","chain_invalid"})

    def test_conflict_cutoff_and_permutations_keep_both_facts_and_observation_ids(self):
        early = document()
        late = document(observation_changes={"observation_id":"late.obs", "observed_at":"2024-03-08T15:00:00Z", "ingested_at":"2024-03-08T15:00:00Z"})
        opposite = document("opposite", observation_changes={"observation_id":"opposite.obs", "observed_at":"2024-03-08T14:40:00Z", "ingested_at":"2024-03-08T14:40:00Z"})
        for items in permutations((early, late, opposite)):
            bundle = batch(items, at=LATER)
            before = view(bundle, knowledge_cutoff="2024-03-08T14:35:00Z", use="preserve")
            after = view(bundle, knowledge_cutoff="2024-03-08T14:45:00Z", use="preserve")
            self.assertEqual(before.selected[0].original.text, early[0].text)
            self.assertFalse(after.selected)
            self.assertIn("revision_conflict", after.held_reasons)
            self.assertEqual(len(bundle.claims), 3)
        collision = document("other document", revision_changes={"document_id":"doc.2"},
                             observation_changes={"observed_at":"2024-03-08T14:40:00Z", "ingested_at":"2024-03-08T14:40:00Z"})
        bundle = batch((early,collision), at=LATER)
        self.assertEqual(len(view(bundle, use="preserve").selected), 1)
        self.assertFalse(view(bundle, knowledge_cutoff=LATER, use="preserve").selected)
        self.assertIn("observation_id_conflict", view(bundle, knowledge_cutoff=LATER).held_reasons)
