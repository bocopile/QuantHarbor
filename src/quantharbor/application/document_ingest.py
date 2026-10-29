"""Q18 explicit synthetic inputs only. No fetch, text execution, AI, retry or clock."""
from quantharbor.domain.catalog import Catalog
from quantharbor.domain.documents import (
    CANONICAL_VERSION, MAX_BATCH_BYTES, DocumentBatchManifest, DocumentBundle, DocumentClaim,
    DocumentEntityContext, DocumentLimits, DocumentOriginal, DocumentReceipt, DocumentRequest,
    catalog_hash, check_rights, claim_ref, document_files, encoded,
)
from quantharbor.domain.market_data import RightsGrant, record_hash, sequence
from quantharbor.domain.primitives import ContractError, utc_instant
from quantharbor.domain.serialization import parse_payload


def collect_documents(*, batch_id, request, limits, receipt, claims, originals, context, catalog,
                      rights, evaluated_at, rights_at=None):
    """Receipt is a supplied synthetic fact; complete applies only to the explicit scope."""
    if (type(request) is not DocumentRequest or type(limits) is not DocumentLimits or type(receipt) is not DocumentReceipt
            or type(context) is not DocumentEntityContext or type(catalog) is not Catalog or type(rights) is not RightsGrant):
        raise ContractError()
    sequence(claims, DocumentClaim, maximum=16)
    sequence(originals, DocumentOriginal, maximum=16)
    now = utc_instant(evaluated_at)
    authority_time = now if rights_at is None else utc_instant(rights_at)
    if authority_time < now or not rights.allows(at=authority_time, purpose="store", source_id=request.source_id,
                                                dataset_id=request.dataset_id, dataset_version=request.dataset_version):
        raise ContractError()
    if any(x.observation.rights_ref != rights.rights_ref for x in claims):
        raise ContractError()
    if len(claims) > limits.max_claims or tuple(claim_ref(x) for x in claims) != receipt.claim_refs:
        raise ContractError()
    # Reconstruction validates immutable objects even if the caller used Python internals to alter them.
    checked_originals = tuple(parse_payload(encoded(x)).payload for x in originals)
    checked_context = parse_payload(encoded(context)).payload
    checked_claims = tuple(DocumentClaim(parse_payload(encoded(x.revision)).payload,
                                        parse_payload(encoded(x.observation)).payload) for x in claims)
    unique_claims = tuple(sorted(set(checked_claims), key=lambda x:claim_ref(x).key))
    unique_originals = tuple(sorted(set(checked_originals), key=record_hash))
    refs = tuple(ref for ref, _ in document_files(unique_originals, unique_claims, checked_context))
    manifest = DocumentBatchManifest(1, "synthetic", batch_id, request.source_id, request.dataset_id,
        request.dataset_version, now, request, limits, receipt, tuple(claim_ref(x) for x in unique_claims), refs,
        record_hash(checked_context), catalog_hash(catalog), CANONICAL_VERSION)
    bundle = DocumentBundle(manifest, unique_originals, unique_claims, checked_context)
    check_rights(manifest, bundle.claims, rights, at=authority_time, purpose="store")
    return bundle


def validate_bundle(bundle, *, catalog, rights, at, purpose="store"):
    """Reconstruct all relationships. Historical metadata never grants current rights."""
    if type(bundle) is not DocumentBundle or type(catalog) is not Catalog:
        raise ContractError()
    manifest = parse_payload(encoded(bundle.manifest)).payload
    check_rights(manifest, bundle.claims, rights, at=at, purpose=purpose)
    if catalog_hash(catalog) != manifest.catalog_hash:
        raise ContractError()
    by_claim = {claim_ref(x):x for x in bundle.claims}
    try:
        received = tuple(by_claim[x] for x in manifest.receipt.claim_refs)
    except KeyError:
        raise ContractError() from None
    # Read purposes may exclude store. Validation does not manufacture a temporary grant:
    # use the same pure bundle validation, without claiming current write authorization.
    sequence(bundle.originals, DocumentOriginal, maximum=16, unique=True)
    originals = tuple(parse_payload(encoded(x)).payload for x in bundle.originals)
    context = parse_payload(encoded(bundle.context)).payload
    claims = tuple(DocumentClaim(parse_payload(encoded(x.revision)).payload,
                                 parse_payload(encoded(x.observation)).payload) for x in received)
    unique_claims = tuple(sorted(set(claims), key=lambda x:claim_ref(x).key))
    refs = tuple(ref for ref, _ in document_files(originals, unique_claims, context))
    reconstructed = DocumentBatchManifest(1, "synthetic", manifest.batch_id, manifest.source_id, manifest.dataset_id,
        manifest.dataset_version, manifest.created_at, manifest.request, manifest.limits, manifest.receipt,
        tuple(claim_ref(x) for x in unique_claims), refs, record_hash(context), catalog_hash(catalog), CANONICAL_VERSION)
    if encoded(reconstructed) != encoded(manifest):
        raise ContractError()
    return DocumentBundle(reconstructed, tuple(sorted(originals, key=record_hash)), unique_claims, context)
