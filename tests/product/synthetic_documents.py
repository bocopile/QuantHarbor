"""Q18 bounded public synthetic text and issuer links; no source data or API."""
from quantharbor.application.document_ingest import collect_documents
from quantharbor.domain.documents import (
    DocumentClaim, DocumentEntityContext, DocumentEntityLink, DocumentLimits, DocumentObservation,
    DocumentReceipt, DocumentRequest, DocumentRevision, Entity, EntityInstrumentLink, claim_ref,
    original, revision_ref,
)
from quantharbor.domain.market_data import RightsGrant, record_hash
from synthetic_market import context as market_context


KNOWN = "2023-12-01T00:00:00Z"
PUBLISHED = "2024-03-08T14:31:00Z"
OBSERVED = "2024-03-08T14:31:01Z"
INGESTED = "2024-03-08T14:31:02Z"
NOW = "2024-03-08T14:31:03Z"
LATER = "2024-03-09T00:00:00Z"


def catalog():
    return market_context()["catalog"]


def rights(**changes):
    values = dict(rights_ref="doc.rights", environment="synthetic", source_id="doc.source", dataset_id="doc.dataset",
                  dataset_version="docs-v1", purposes=("store", "research", "ai", "report"), valid_from=KNOWN,
                  valid_to="2025-01-01T00:00:00Z", revoked_at=None)
    return RightsGrant(**(values|changes))


def document(text="합성 문서\nSynthetic filing.", *, revision_changes=None, observation_changes=None):
    changes = {} if revision_changes is None else revision_changes
    body = None if changes.get("action") == "retract" else original(text)
    values = dict(schema_version=1, environment="synthetic", source_id="doc.source", dataset_id="doc.dataset",
                  document_id="doc.1", revision_id="rev.z", predecessor_revision_id=None, kind="disclosure", action="publish",
                  source_url="https://synthetic.invalid/filing", published_at=PUBLISHED, publication_unknown_reason=None,
                  original_hash=None if body is None else record_hash(body), original_absent_reason=None if body is not None else "retracted",
                  evidence_ref="doc.revision.evidence")
    revision = DocumentRevision(**(values|changes))
    observed = dict(schema_version=1, environment="synthetic", observation_id="doc.obs.1", revision_ref=revision_ref(revision),
                    observed_at=OBSERVED, ingested_at=INGESTED, rights_ref="doc.rights", dataset_version="docs-v1",
                    evidence_ref="doc.observation.evidence")
    return body, DocumentClaim(revision, DocumentObservation(**(observed|({} if observation_changes is None else observation_changes))))


def entity_context(claims, *, cat=None, links=True, entity_kind="company", known=KNOWN, instrument=True):
    cat = catalog() if cat is None else cat
    entity = Entity("doc.company", "company-v1", entity_kind, "doc.entity.evidence", known)
    document_links = tuple(DocumentEntityLink(ref, entity.entity_id, entity.entity_version, "subject", "doc.link.evidence", known)
                           for ref in sorted({revision_ref(x.revision) for x in claims}, key=lambda x:(x.key,x.revision_hash))) if links else ()
    item = cat.instruments[0]
    instruments = (EntityInstrumentLink(entity.entity_id, entity.entity_version, cat.catalog_version, item.instrument_id,
        item.instrument_version, item.listing_venue_id, "issuer", KNOWN, None, known, "doc.issuer.evidence"),) if instrument else ()
    return DocumentEntityContext(1, "synthetic", "doc.context", "context-v1", (entity,), document_links, instruments)


def request(**changes):
    values = dict(request_id="doc.request", source_id="doc.source", dataset_id="doc.dataset", dataset_version="docs-v1",
                  scope_ref="doc.scope", document_ids=(), expected_document_ids=("doc.1",),
                  started_at="2024-03-08T14:30:00Z", deadline="2024-03-09T00:01:00Z")
    return DocumentRequest(**(values|changes))


def limits(**changes):
    return DocumentLimits(**(dict(max_claims=16, max_bytes=4194304, max_age_seconds=60, policy_ref="doc.freshness-v1")|changes))


def batch(items=None, *, at=NOW, cat=None, context=None, req=None, receipt_changes=None, grant=None, policy=None):
    items = (document(),) if items is None else items
    cat = catalog() if cat is None else cat
    req = request() if req is None else req
    claims = tuple(x[1] for x in items)
    originals = tuple(x[0] for x in items if x[0] is not None)
    if context is None:
        context = entity_context(claims, cat=cat)
    found = {x.revision.document_id for x in claims}
    missing = tuple(sorted(set(req.expected_document_ids)-found))
    values = dict(request_id=req.request_id, scope_ref=req.scope_ref, status="success" if not missing else "partial",
                  complete=not missing, received_at=at, claim_refs=tuple(claim_ref(x) for x in claims),
                  missing_document_ids=missing, error_reason=None, terminal_ref="doc.terminal" if not missing else None)
    receipt = DocumentReceipt(**(values|({} if receipt_changes is None else receipt_changes)))
    return collect_documents(batch_id="doc.batch", request=req, limits=limits() if policy is None else policy,
        receipt=receipt, claims=claims, originals=originals, context=context, catalog=cat,
        rights=rights() if grant is None else grant, evaluated_at=at)


def lineage_batch(kind):
    first = document("합성 첫 원문\nUnicode é / e\u0301\r\n")
    if kind == "correction":
        second = document("합성 정정 원문\n", revision_changes={"revision_id":"rev.a", "action":"replace",
            "predecessor_revision_id":"rev.z", "published_at":"2024-03-08T15:00:00Z"},
            observation_changes={"observation_id":"doc.obs.2", "observed_at":"2024-03-08T15:00:01Z", "ingested_at":"2024-03-08T15:00:02Z"})
        return batch((second,first), at=LATER)
    if kind == "conflict":
        late = document(first[0].text, observation_changes={"observation_id":"late.obs", "observed_at":"2024-03-08T15:00:00Z", "ingested_at":"2024-03-08T15:00:00Z"})
        opposite = document("상충한 합성 원문", observation_changes={"observation_id":"opposite.obs", "observed_at":"2024-03-08T14:40:00Z", "ingested_at":"2024-03-08T14:40:00Z"})
        return batch((late,opposite,first), at=LATER)
    if kind == "observation":
        other = document("다른 문서", revision_changes={"document_id":"doc.2"},
            observation_changes={"observed_at":"2024-03-08T14:40:00Z", "ingested_at":"2024-03-08T14:40:00Z"})
        return batch((other,first), at=LATER)
    raise ValueError("synthetic_document_fixture")
