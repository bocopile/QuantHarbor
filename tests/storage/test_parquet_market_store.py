from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

# Explicit public synthetic helpers; never load data, host tzdb or private configuration.
PRODUCT = Path(__file__).resolve().parents[1] / "product"
SOURCE = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(PRODUCT))

import pyarrow as pa
import pyarrow.parquet as pq
from quantharbor.adapters.parquet_market_store import ParquetMarketStore, _schema
from quantharbor.domain.market_data import IngestLimits, record_hash
from quantharbor.domain.market_storage import StorageBundle
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes
from synthetic_market import LATER, NOW, bar, context, item, page, price, revision, rights
from synthetic_market_storage import collect, conflict_bundle, rich_bundle


def encoded(value):
    return canonical_bytes(CanonicalPayload(type(value).__name__, 1, "synthetic", value))


class ParquetStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qh-store-test-")
        self.root = Path(self.temp.name)
        self.store = ParquetMarketStore(self.root, source_id="syn.source", dataset_id="syn.dataset")
        self.bundle = collect().bundle

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def write(self, bundle=None, **changes):
        bundle = self.bundle if bundle is None else bundle
        params = dict(rights=rights(dataset_version=bundle.descriptor.request.dataset_version),
                      at=bundle.descriptor.evaluated_at, **context())
        return self.store.write(bundle, **(params | changes))

    def read(self, version="dataset-v1", **changes):
        params = dict(rights=rights(dataset_version=version), at=NOW, limits=IngestLimits(max_age_seconds=60), **context())
        return self.store.read(version, **(params | changes))

    def rewrite_manifest(self, manifest):
        (self.root / manifest.dataset_version / "manifest.json").write_bytes(encoded(manifest))

    def replace_file(self, manifest, ref, raw):
        (self.root / manifest.dataset_version / ref.name).write_bytes(raw)
        new_ref = replace(ref, size_bytes=len(raw), sha256=sha256(raw).hexdigest())
        if ref.role == "evidence":
            updated = replace(manifest, evidence_files=tuple(new_ref if x==ref else x for x in manifest.evidence_files))
        else:
            updated = replace(manifest, receipt_files=tuple(new_ref if x==ref else x for x in manifest.receipt_files))
        self.rewrite_manifest(updated)
        return updated

    def test_exact_rich_financial_types_and_current_vs_historical(self):
        bundle = rich_bundle()
        manifest = self.write(bundle)
        result = self.read()
        self.assertEqual(result.historical.state, bundle.state)
        self.assertEqual(result.historical.envelope, bundle.envelope)
        self.assertEqual(result.historical.summary, bundle.summary)
        self.assertTrue(result.current_view.context_validated)
        self.assertTrue(result.current_quality.eligible_for_new_risk)
        ref = manifest.evidence_files[0]
        with pq.ParquetFile(self.root / "dataset-v1" / ref.name) as file:
            self.assertTrue(file.schema_arrow.equals(_schema(), check_metadata=True))
            rows = file.read().to_pylist()
        self.assertTrue(any(x["open"] == Decimal("10.000000000000000001") for x in rows))
        self.assertTrue(any(x["fx_rate"] == Decimal("1300.123456789012345678") for x in rows))
        self.assertTrue(any(x["cash_per_unit"] == Decimal("0.123456789012345678") for x in rows))
        self.assertTrue(any(x["observed_at"].microsecond == 123456 for x in rows))
        later = self.read(at=LATER)
        self.assertEqual(later.historical.envelope.quality.freshness, "fresh")
        self.assertEqual(later.current_quality.freshness, "stale")
        self.assertFalse(later.current_quality.eligible_for_new_risk)

    def test_writer_exit_then_new_reader_process_exact_reconstruction(self):
        program = '''import json,sys
sys.path[:0]=[sys.argv[2],sys.argv[3]]
from quantharbor.adapters.parquet_market_store import ParquetMarketStore
from quantharbor.domain.market_data import IngestLimits,record_hash
from synthetic_market import NOW,LATER,context,rights
from synthetic_market_storage import rich_bundle,conflict_bundle
bundle=rich_bundle() if sys.argv[5]=='rich' else conflict_bundle(observation_collision=sys.argv[5]=='observation')
at=NOW if sys.argv[5]=='rich' else LATER
with ParquetMarketStore(sys.argv[1],source_id='syn.source',dataset_id='syn.dataset') as store:
 if sys.argv[4]=='write':
  manifest=store.write(bundle,rights=rights(),at=at,**context())
 else:
  result=store.read('dataset-v1',rights=rights(),at=at,limits=IngestLimits(max_age_seconds=60),
      knowledge_cutoff=NOW if sys.argv[5]=='rich' else '2024-03-08T14:35:00Z',**context())
  assert result.historical.state==bundle.state and result.historical.envelope==bundle.envelope
  assert result.historical.summary==bundle.summary
  if sys.argv[5]=='rich': assert result.current_quality.eligible_for_new_risk
  else: assert len(result.current_view.selected)==1 and not result.current_quality.eligible_for_new_risk
  manifest=result.manifest
 print(json.dumps({'manifest_hash':record_hash(manifest),'evidence':len(bundle.evidence)}))
'''
        for fixture in ("rich", "revision", "observation"):
            target = self.root / fixture
            target.mkdir(mode=0o700)
            outputs = []
            for operation in ("write", "read"):
                process = subprocess.run([sys.executable, "-I", "-c", program, str(target), str(SOURCE), str(PRODUCT), operation, fixture],
                                         capture_output=True, timeout=25)
                self.assertEqual(process.returncode, 0, "synthetic_child_process_failed_"+fixture)
                outputs.append(json.loads(process.stdout))
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0]["evidence"], 5 if fixture=="rich" else 3)

    def test_full_revision_and_observation_collision_evidence_survives(self):
        for collision, version in ((False, "dataset-v1"), (True, "dataset-v2")):
            bundle = conflict_bundle(observation_collision=collision)
            if version != "dataset-v1":
                # Re-ingest the same synthetic evidence into an immutable new dataset version.
                bundle = collect(bundle.evidence, version=version, evaluated_at=LATER).bundle
            self.write(bundle)
            result = self.read(version, at=LATER, knowledge_cutoff="2024-03-08T14:35:00Z")
            self.assertEqual(result.historical.state, bundle.state)
            self.assertEqual(set(result.historical.evidence), set(bundle.evidence))
            self.assertEqual(len(result.historical.evidence), 3)
            self.assertEqual(len(result.current_view.selected), 1)
            self.assertFalse(result.current_quality.eligible_for_new_risk)
            self.assertEqual(result.manifest.evidence_count, 3)

    def test_partial_recollection_versions_failed_rejected_and_fetch_receipts(self):
        def partial(req):
            return (page(req, terminal=False, cursor_out="c.1"), page(req, cursor_in="c.1", items=(), status="failed",
                   terminal=False, error_reason="synthetic_failure"))
        bundles = [collect(pages=partial).bundle,
                   collect(version="dataset-v2", limits=IngestLimits(max_bytes=1)).bundle,
                   collect(version="dataset-v3", pages=lambda req: ()).bundle]
        for bundle in bundles:
            version = bundle.descriptor.request.dataset_version
            self.write(bundle)
            result = self.read(version)
            self.assertEqual(result.historical.state, bundle.state)
            self.assertEqual(result.historical.receipts, bundle.receipts)
            self.assertFalse(result.current_quality.eligible_for_new_risk)
        complete = collect(version="dataset-v4").bundle
        self.write(complete, previous_version="dataset-v1")
        self.assertEqual(self.read("dataset-v4").historical.envelope.quality.status, "complete")
        self.assertEqual(self.read().historical.envelope.quality.status, "partial")

    def test_pit_and_explicit_restated_are_views_not_rewrites(self):
        correction = item(revision(revision_id="rev.a", predecessor_revision_id="rev.z", revision_kind="replacement",
            payload=bar(close=price("10")), published_at="2024-03-08T15:00:00Z"), observation_id="obs.corrected",
            observed_at="2024-03-08T15:00:01Z", ingested_at="2024-03-08T15:00:02Z")
        bundle = collect((item(), correction), evaluated_at=LATER).bundle
        self.write(bundle)
        original_bytes = (self.root/"dataset-v1"/"manifest.json").read_bytes()
        old = self.read(at=LATER, as_of=LATER, knowledge_cutoff=NOW)
        restated = self.read(at=LATER, as_of=LATER, knowledge_cutoff=LATER, view_mode="restated", original_cutoff=NOW)
        self.assertEqual(old.current_view.selected[0].revision.revision_id, "rev.z")
        self.assertEqual(restated.current_view.selected[0].revision.revision_id, "rev.a")
        self.assertEqual((self.root/"dataset-v1"/"manifest.json").read_bytes(), original_bytes)

    def test_current_rights_before_any_files_and_scope_purpose_expiry(self):
        self.write()
        for grant, at, purpose in ((rights(revoked_at=NOW), NOW, "research"),
                                   (rights(), "2025-01-01T00:00:00Z", "research"),
                                   (rights(purposes=("store",)), NOW, "ai"),
                                   (rights(source_id="other.source"), NOW, "report")):
            with patch.object(self.store, "_directory", side_effect=AssertionError("must_not_read")) as opened:
                with self.assertRaises(ContractError): self.read(rights=grant, at=at, purpose=purpose)
                opened.assert_not_called()
        with self.assertRaises(ContractError): self.write(rights=rights(revoked_at=NOW))

    def test_hash_tamper_missing_file_and_no_glob(self):
        manifest = self.write()
        folder = self.root / "dataset-v1"
        (folder/"unlisted.parquet").write_bytes(b"not read")
        self.assertEqual(self.read().manifest, manifest)
        data = folder / manifest.evidence_files[0].name
        original = data.read_bytes()
        data.write_bytes(original + b"tamper")
        with self.assertRaises(ContractError): self.read()
        data.write_bytes(original)
        data.unlink()
        with self.assertRaises(ContractError): self.read()

    def test_parquet_typed_column_schema_and_row_bounds_despite_rehashed_file(self):
        manifest = self.write()
        ref = manifest.evidence_files[0]
        original = (self.root/"dataset-v1"/ref.name).read_bytes()
        for mode in ("typed", "schema", "rows"):
            rows = pq.read_table(BytesIO(original)).to_pylist()
            if mode == "typed": rows[0]["open"] = Decimal("99")
            elif mode == "rows": rows += rows
            table = pa.Table.from_pylist(rows, schema=_schema()) if mode != "schema" else pa.table({"wrong":[1]})
            output = BytesIO()
            pq.write_table(table, output, row_group_size=16, compression="NONE", use_dictionary=False, write_page_checksum=True)
            self.replace_file(manifest, ref, output.getvalue())
            with self.assertRaises(ContractError): self.read()
        (self.root/"dataset-v1"/ref.name).write_bytes(original)
        self.rewrite_manifest(manifest)
        altered_ref = replace(ref, row_count=2)
        self.rewrite_manifest(replace(manifest, evidence_files=(altered_ref,), evidence_count=2))
        with self.assertRaises(ContractError): self.read()

    def test_receipt_order_claim_and_summary_binding_tamper(self):
        manifest = self.write()
        ref, receipt = manifest.receipt_files[0], self.bundle.receipts[0]
        changes = (replace(receipt, ordinal=2), replace(receipt, response_size_bytes=10000),
                   replace(receipt, item_refs=(replace(receipt.item_refs[0], observation_hash="0"*64),)))
        for changed in changes:
            self.replace_file(manifest, ref, encoded(changed))
            with self.assertRaises(ContractError): self.read()
        self.replace_file(manifest, ref, encoded(receipt))
        self.rewrite_manifest(replace(manifest, receipt_files=()))
        with self.assertRaises(ContractError): self.read()

    def test_writer_rejects_recombined_state_context_and_unsupported_version(self):
        rejected = collect(limits=IngestLimits(max_bytes=1)).bundle
        for change in ({"request_id": "wrong"}, {"cursor_in": "wrong"},
                       {"scope": replace(rejected.receipts[0].scope, coverage_ref="wrong")},
                       {"received_at": "2024-03-08T14:31:04Z"}):
            forged_rejection = replace(rejected, receipts=(replace(rejected.receipts[0], **change),))
            with self.assertRaises(ContractError): self.write(forged_rejection)
        bundle = self.bundle
        other = collect(version="other-version").bundle
        forged = replace(bundle, descriptor=other.descriptor)
        with self.assertRaises(ContractError): self.write(forged)
        ctx = context()
        wrong = replace(ctx["catalog"], source_ref="other.source.ref")
        with self.assertRaises(ContractError): self.write(catalog=wrong)
        manifest = self.write()
        raw = json.loads(encoded(manifest))
        raw["payload"]["storage_schema_version"] = "unsupported"
        (self.root/"dataset-v1"/"manifest.json").write_text(json.dumps(raw))
        with self.assertRaises(ContractError): self.read()

    def test_immutable_version_flock_and_crash_orphan_not_public(self):
        with self.store._writer_lock():
            with ParquetMarketStore(self.root, source_id="syn.source", dataset_id="syn.dataset") as other:
                with self.assertRaises(ContractError):
                    other.write(self.bundle, rights=rights(), at=NOW, **context())
        with patch.object(self.store, "_publish_manifest", side_effect=SystemExit("synthetic_crash")):
            with self.assertRaises(SystemExit): self.write()
        self.assertFalse((self.root/"dataset-v1"/"manifest.json").exists())
        with self.assertRaises(ContractError): self.read()
        with self.assertRaises(ContractError): self.write()
        self.write(collect(version="dataset-v2").bundle)
        original = (self.root/"dataset-v2"/"manifest.json").read_bytes()
        with self.assertRaises(ContractError): self.write(collect(version="dataset-v2").bundle)
        self.assertEqual((self.root/"dataset-v2"/"manifest.json").read_bytes(), original)
        original_unlink = os.unlink
        def crash_after_link(name, *args, **kwargs):
            if name == "manifest-pending.json":
                raise SystemExit("synthetic_post_link_crash")
            return original_unlink(name, *args, **kwargs)
        with patch("quantharbor.adapters.parquet_market_store.os.unlink", side_effect=crash_after_link):
            with self.assertRaises(SystemExit): self.write(collect(version="dataset-v3").bundle)
        folder = self.root / "dataset-v3"
        self.assertTrue((folder/"manifest.json").exists())
        self.assertTrue((folder/"manifest-pending.json").exists())
        self.assertEqual((folder/"manifest.json").stat().st_nlink, 2)
        with self.assertRaises(ContractError): self.read("dataset-v3")
        with self.assertRaises(ContractError): self.write(collect(version="dataset-v3").bundle)

    def test_private_root_symlink_version_file_hardlink_and_permissions(self):
        link = self.root / "root-link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ContractError): ParquetMarketStore(link, source_id="syn.source", dataset_id="syn.dataset")
        with self.assertRaises(ContractError): ParquetMarketStore(str(self.root)+"/../", source_id="syn.source", dataset_id="syn.dataset")
        self.root.chmod(0o755)
        with self.assertRaises(ContractError): self.write()
        with self.assertRaises(ContractError): ParquetMarketStore(self.root, source_id="syn.source", dataset_id="syn.dataset")
        self.root.chmod(0o700)
        manifest = self.write()
        file = self.root/"dataset-v1"/manifest.evidence_files[0].name
        hardlink = self.root/"hardlink"
        os.link(file, hardlink)
        with self.assertRaises(ContractError): self.read()
        hardlink.unlink()
        file.chmod(0o644)
        with self.assertRaises(ContractError): self.read()
        file.chmod(0o600)
        original = file.read_bytes()
        file.unlink()
        file.symlink_to(self.root/"unrelated")
        with self.assertRaises(ContractError): self.read()
        file.unlink()
        file.write_bytes(original)
        file.chmod(0o600)
        versionlink = self.root/"dataset-v2"
        versionlink.symlink_to(self.root/"dataset-v1", target_is_directory=True)
        with self.assertRaises(ContractError): self.read("dataset-v2")
        with self.assertRaises(ContractError): self.read("../dataset-v1")
        self.assertEqual(self.read().manifest, manifest)
        lock = self.root/"writer.lock"
        lock.unlink()
        canary = self.root/"synthetic-canary"
        canary.write_bytes(b"synthetic canary unchanged")
        canary.chmod(0o600)
        lock.symlink_to(canary)
        with self.assertRaises(ContractError): self.write(collect(version="dataset-v3").bundle)
        self.assertEqual(canary.read_bytes(), b"synthetic canary unchanged")
