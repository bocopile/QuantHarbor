from dataclasses import FrozenInstanceError, replace
from datetime import datetime
import unittest

from quantharbor.domain.catalog import Catalog, Instrument, SymbolMapping
from quantharbor.domain.primitives import ContractError


START = "2024-01-01T00:00:00Z"
CHANGE = "2024-06-01T00:00:00Z"
END = "2025-01-01T00:00:00Z"
KNOWN = "2023-12-01T00:00:00Z"


def instrument(**changes):
    values = dict(instrument_id="syn.instrument.001", instrument_version="instrument-v1",
                  listing_venue_id="syn.list.kr", market="KR", currency="KRW", product_kind="equity",
                  etf_kind="not_applicable", classification_version="classification-v1",
                  classification_evidence_ref="syn.evidence.001", valid_from=START, valid_to=END, known_at=KNOWN)
    return Instrument(**(values | changes))


def mapping(**changes):
    values = dict(mapping_id="syn.mapping.001", mapping_version="mapping-v1", source_id="syn.provider",
                  source_code="SAME", instrument_id="syn.instrument.001", listing_venue_id="syn.list.kr",
                  execution_venue_id="syn.exec.kr", valid_from=START, valid_to=END, known_at=KNOWN)
    return SymbolMapping(**(values | changes))


def lookup(catalog, code="SAME", listing="syn.list.kr", execution="syn.exec.kr", **changes):
    args = dict(as_of="2024-03-01T00:00:00Z", knowledge_cutoff="2024-12-01T00:00:00Z") | changes
    return catalog.resolve("syn.provider", code, listing, execution, **args)


class CatalogTests(unittest.TestCase):
    def test_same_ticker_other_markets_and_execution_venue_are_distinct(self):
        kr = instrument()
        us = instrument(instrument_id="syn.instrument.002", listing_venue_id="syn.list.us", market="US", currency="USD")
        us_mapping = mapping(mapping_id="syn.mapping.002", instrument_id=us.instrument_id,
                             listing_venue_id=us.listing_venue_id, execution_venue_id="syn.exec.us")
        catalog = Catalog("catalog-v1", "syn.source", (kr, us), (mapping(), us_mapping))
        first = lookup(catalog)
        second = lookup(catalog, listing="syn.list.us", execution="syn.exec.us")
        self.assertNotEqual(first.instrument.instrument_id, second.instrument.instrument_id)
        self.assertEqual(first.instrument.listing_venue_id, "syn.list.kr")
        self.assertEqual(first.mapping.execution_venue_id, "syn.exec.kr")
        self.assertIsNone(lookup(catalog, execution="syn.list.kr"))

    def test_code_changes_and_delisting_are_half_open(self):
        old = mapping(valid_to=CHANGE)
        new = mapping(mapping_id="syn.mapping.002", mapping_version="mapping-v2", source_code="NEW", valid_from=CHANGE)
        catalog = Catalog("catalog-v1", "syn.source", (instrument(),), (old, new))
        self.assertIsNotNone(lookup(catalog, as_of=START))
        self.assertIsNone(lookup(catalog, as_of=CHANGE))
        self.assertIsNotNone(lookup(catalog, code="NEW", as_of=CHANGE))
        self.assertIsNone(lookup(catalog, code="NEW", as_of=END))
        self.assertIsNone(lookup(catalog, as_of="2023-12-31T23:59:59.999999Z"))

    def test_mapping_and_classification_knowledge_cutoffs_prevent_future_facts(self):
        late_mapping = mapping(known_at="2024-07-01T00:00:00Z")
        catalog = Catalog("catalog-v1", "syn.source", (instrument(),), (late_mapping,))
        self.assertIsNone(lookup(catalog, knowledge_cutoff="2024-06-30T23:59:59.999999Z"))
        self.assertIsNotNone(lookup(catalog, knowledge_cutoff="2024-07-01T00:00:00Z"))
        late_instrument = instrument(known_at="2024-08-01T00:00:00Z")
        catalog = Catalog("catalog-v2", "syn.source", (late_instrument,), (mapping(),))
        self.assertIsNone(lookup(catalog, knowledge_cutoff="2024-07-01T00:00:00Z"))
        future = Catalog("catalog-v3", "syn.source", (instrument(),), (mapping(valid_from=CHANGE),))
        self.assertIsNone(lookup(future, as_of="2024-05-01T00:00:00Z"))

    def test_overlaps_duplicates_and_reverse_alias_ambiguity_are_rejected(self):
        first = mapping()
        variants = (first, mapping(mapping_id="syn.mapping.002"),
                    mapping(mapping_id="syn.mapping.002", source_code="ALIAS"),
                    mapping(mapping_id="syn.mapping.002", valid_from=CHANGE, known_at="2024-10-01T00:00:00Z"))
        for second in variants:
            with self.subTest(mapping_id=second.mapping_id), self.assertRaises(ContractError):
                Catalog("catalog-v1", "syn.source", (instrument(),), (first, second))

    def test_unknown_leveraged_inverse_and_other_markets_are_ineligible(self):
        for product, subtype, eligible in (("equity", "not_applicable", True), ("etf", "general", True),
                                            ("etf", "leveraged", False), ("etf", "inverse", False),
                                            ("etf", "unknown", False), ("unknown", "unknown", False)):
            item = instrument(product_kind=product, etf_kind=subtype)
            catalog = Catalog("catalog-v1", "syn.source", (item,), (mapping(),))
            self.assertEqual(lookup(catalog).eligible_for_initial_scope, eligible)
        for market in ("other", "unknown"):
            item = instrument(market=market, currency="USD")
            self.assertFalse(lookup(Catalog("catalog-v1", "syn.source", (item,), (mapping(),))).eligible_for_initial_scope)
        with self.assertRaises(ContractError):
            Catalog("catalog-v1", "syn.source", (instrument(), instrument(instrument_id="syn.other", market="US")), ())

    def test_mapping_references_lifecycle_and_record_identity_are_checked(self):
        invalid = (mapping(instrument_id="syn.missing"), mapping(listing_venue_id="syn.other"),
                   mapping(valid_from="2023-01-01T00:00:00Z"), mapping(valid_to=None))
        for item in invalid:
            with self.subTest(mapping_id=item.mapping_id), self.assertRaises(ContractError):
                Catalog("catalog-v1", "syn.source", (instrument(),), (item,))
        with self.assertRaises(ContractError):
            Catalog("catalog-v1", "syn.source", (instrument(), instrument()), ())

    def test_immutability_types_versions_formats_and_naive_instants(self):
        catalog = Catalog("catalog-v1", "syn.source", (instrument(),), (mapping(),))
        with self.assertRaises(FrozenInstanceError):
            catalog.catalog_version = "changed"
        for changes in (dict(instruments=[instrument()]), dict(schema_version=True), dict(environment="paper")):
            with self.subTest(changes=list(changes)), self.assertRaises(ContractError):
                replace(catalog, **changes)
        for code in ("same", "A B", "../A", "가", "A" * 33, True, None):
            with self.subTest(code=code), self.assertRaises(ContractError):
                mapping(source_code=code)
        for changes in (dict(valid_from=END), dict(product_kind=True), dict(market="CA"),
                        dict(etf_kind="general"), dict(classification_evidence_ref="")):
            with self.subTest(changes=list(changes)), self.assertRaises(ContractError):
                instrument(**changes)
        with self.assertRaises(ContractError):
            lookup(catalog, as_of=datetime(2024, 1, 1))


if __name__ == "__main__":
    unittest.main()
