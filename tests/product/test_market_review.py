"""Q17A R1-R4 independent review regression, synthetic inputs only."""
from dataclasses import replace
from itertools import permutations
import unittest

import quantharbor.domain.market_data as market
from quantharbor.application import market_ingest
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from synthetic_market import END, LATER, NOW, bar, context, item, page, price, request, revision, rights, scope
from test_market_data import merged, selected
from test_market_ingest import run


def action(**changes):
    values = dict(instrument_id="syn.instrument", listing_venue_id="syn.listing", execution_venue_id="syn.venue",
                  source_code="SYN", action_kind="split", quantity_unit="share", effective_date="2024-03-08",
                  record_date=None, payment_date=None, dates_unknown_reason="not_provided", numerator="2",
                  denominator="1", cash_per_unit=None)
    return market.CorporateAction(**(values | changes))


def action_item(**changes):
    values = dict(series_id="syn.actions", event_id="syn.split", revision_id="split.1", payload=action())
    return item(revision(**(values | changes)), observation_id="obs.action")


def action_ref(value):
    return market.ActionRef(*value.revision.key, market.record_hash(value.revision))


def adjusted(value, *, knowledge_at=END, basis_at=END):
    details = market.Adjustment("split", "adjust-v1", basis_at, (action_ref(value),), knowledge_at, "syn.evidence")
    r = revision(series_id="syn.adjusted", payload=bar(adjustment="adjusted", adjustment_details=details),
                 published_at="2024-03-08T14:31:03Z")
    return item(r, observation_id="obs.adjusted", observed_at="2024-03-08T14:31:03Z", ingested_at="2024-03-08T14:31:03Z")


class ReviewRegressionTests(unittest.TestCase):
    def test_r1_action_local_effective_date_and_validated_entry(self):
        wrong = action_item(payload=action(effective_date="2099-01-01"))
        self.assertEqual(market.validate_market_context(wrong, **context(), knowledge_cutoff=NOW),
                         "action_effective_date_mismatch")
        self.assertFalse(hasattr(market, "select_view"))
        self.assertFalse(selected(merged(wrong)).context_validated)
        view = market_ingest.select_view(merged(wrong), as_of=NOW, knowledge_cutoff=NOW, rights=rights(),
                                        at=NOW, dataset_version="dataset-v1", **context())
        self.assertTrue(view.context_validated)
        self.assertFalse(view.selected)
        self.assertIn("action_effective_date_mismatch", view.held_reasons)
        req = request(scope=scope(
            series_ids=("syn.actions",), expected=(market.ExpectedEvent("syn.actions", "syn.split", END),)))
        result, _ = run((page(req, items=(wrong,)),), req=req)
        self.assertIn("action_effective_date_mismatch", result.state.errors)
        self.assertFalse(result.envelope.quality.eligible_for_new_risk)

    def test_r2_adjustment_uses_its_knowledge_and_basis_not_query_now(self):
        known_later = action_item()
        adjusted_bar = adjusted(known_later)
        view = selected(merged(known_later, adjusted_bar), LATER, as_of=LATER)
        self.assertFalse(any(x.revision.series_id == "syn.adjusted" for x in view.selected))
        self.assertIn("adjustment_unverified", view.held_reasons)
        knowledge = "2024-03-08T14:31:02Z"
        valid = adjusted(known_later, knowledge_at=knowledge)
        raw = selected(merged(known_later, valid), LATER, as_of=LATER)
        self.assertIn(valid, raw.selected)
        bound = market_ingest.select_view(merged(known_later, valid), as_of=LATER, knowledge_cutoff=LATER,
                    rights=rights(), at=LATER, dataset_version="dataset-v1", **context())
        self.assertIn(valid, bound.selected)
        self.assertEqual(parse_payload(canonical_bytes(CanonicalPayload("MarketRevision", 1, "synthetic", valid.revision))).payload,
                         valid.revision)
        for payload_changes in ({"instrument_id": "wrong"}, {"listing_venue_id": "wrong"},
                                {"execution_venue_id": "wrong"}, {"quantity_unit": "lot"}):
            other = action_item(payload=action(**payload_changes))
            value = adjusted(other, knowledge_at=knowledge)
            self.assertNotIn(value, selected(merged(other, value), LATER, as_of=LATER).selected)
        for ref_changes in ({"source_id": "wrong"}, {"dataset_id": "wrong"}, {"series_id": "wrong"},
                            {"event_id": "wrong"}, {"revision_id": "wrong"}, {"revision_hash": "0"*64}):
            details = valid.revision.payload.adjustment_details
            wrong_ref = replace(details.action_refs[0], **ref_changes)
            value = item(replace(valid.revision, payload=replace(valid.revision.payload,
                adjustment_details=replace(details, action_refs=(wrong_ref,)))), observation_id="obs.adjusted",
                observed_at=NOW, ingested_at=NOW)
            self.assertNotIn(value, selected(merged(known_later, value), LATER, as_of=LATER).selected)
        later_ingest = item(known_later.revision, observation_id="obs.action",
                           observed_at=knowledge, ingested_at="2024-03-08T14:31:03Z")
        later_publication = item(replace(known_later.revision, published_at="2024-03-08T14:31:03Z"),
                    observation_id="obs.action", observed_at="2024-03-08T14:31:04Z", ingested_at="2024-03-08T14:31:05Z")
        for evidence in (later_ingest, later_publication):
            value = adjusted(evidence, knowledge_at=knowledge)
            self.assertNotIn(value, selected(merged(evidence, value), LATER, as_of=LATER).selected)
        before_effect = adjusted(known_later, knowledge_at=knowledge, basis_at="2024-03-08T14:30:59Z")
        self.assertNotIn(before_effect, selected(merged(known_later, before_effect), LATER, as_of=LATER).selected)
        with self.assertRaises(ContractError):
            replace(valid.revision.payload.adjustment_details, action_refs=("split.1",))

    def test_r3_future_receipt_and_backward_page_clock(self):
        result, _ = run((page(items=(), received_at="2024-03-08T14:31:04Z"),))
        self.assertIn("page_clock_invalid", result.state.errors)
        first = page(items=(), terminal=False, cursor_out="cursor.1", received_at=NOW)
        last = page(items=(), cursor_in="cursor.1", received_at="2024-03-08T14:31:02Z")
        result, _ = run((first, last))
        self.assertIn("page_clock_invalid", result.state.errors)
        self.assertEqual(result.state.pages, 1)

    def test_r4_late_and_early_reobservations_conflict_order_invariant(self):
        late = item(observation_id="obs.late", observed_at="2024-03-08T15:00:00Z", ingested_at="2024-03-08T15:00:00Z")
        early = item(observation_id="obs.early")
        opposite = item(revision(payload=bar(close=price("10"))), observation_id="obs.opposite",
                        observed_at="2024-03-08T14:40:00Z", ingested_at="2024-03-08T14:40:00Z")
        for order in permutations((late, early, opposite)):
            with self.subTest(order=tuple(x.observation.observation_id for x in order)):
                state = merged(*order)
                self.assertEqual(min(x.detected_at for x in state.conflicts), "2024-03-08T14:40:00.000000Z")
                self.assertEqual(selected(state, "2024-03-08T14:35:00Z").selected, (early,))
                self.assertFalse(selected(state, "2024-03-08T14:45:00Z").selected)
                self.assertEqual(set(state.evidence), {late, early, opposite})
                self.assertEqual(state, merged(late, early, opposite))

    def test_r4_observation_id_collision_keeps_both_claims_order_independent(self):
        first = item(observation_id="obs.shared")
        second = item(revision(event_id="other.event"), observation_id="obs.shared",
                      observed_at="2024-03-08T14:40:00Z", ingested_at="2024-03-08T14:40:00Z")
        late = item(observation_id="obs.late", observed_at="2024-03-08T15:00:00Z", ingested_at="2024-03-08T15:00:00Z")
        for order in permutations((late, first, second)):
            state = merged(*order)
            self.assertEqual(set(state.evidence), {late, first, second})
            self.assertTrue(any(x.kind == "observation_id" for x in state.conflicts))
            self.assertEqual(min(x.detected_at for x in state.conflicts), "2024-03-08T14:40:00.000000Z")
            self.assertEqual(selected(state, "2024-03-08T14:35:00Z").selected, (first,))
            self.assertFalse(selected(state, "2024-03-08T14:45:00Z").selected)
            self.assertEqual(state, merged(first, second, late))
