"""Q18 합성 문서 원문·계보·명시 연결. 본문은 비신뢰 데이터이며 실행하지 않는다."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
import re

from .catalog import Catalog, _contains, _no_overlap, _window
from .market_data import RightsGrant, count, digest, enum, header, record_hash, sequence, stamp
from .primitives import ContractError, identifier, utc_instant


MAX_CLAIMS = 16
MAX_BATCH_BYTES = 4194304
CANONICAL_VERSION = "qh-canonical-json-v1"
DOCUMENT_SCHEMAS = ("DocumentOriginal", "DocumentRevision", "DocumentObservation", "DocumentEntityContext")


def _text(value):
    if type(value) is not str or not 1 <= len(value) <= 8192:
        raise ContractError()
    try:
        raw = value.encode("utf-8")
    except UnicodeError:
        raise ContractError() from None
    if len(raw) > 8192:
        raise ContractError()
    return raw


def source_url(value):
    """Preserved HTTP(S) source metadata only; no DNS, URL access or normalization."""
    if (type(value) is not str or len(value) > 2048 or any(ord(x) < 32 or 127 <= ord(x) <= 159 or 0xD800 <= ord(x) <= 0xDFFF or x.isspace() for x in value)
            or "\\" in value):
        raise ContractError()
    match = re.fullmatch(r"https?://([^/?#]+)(?:[/?#].*)?", value, re.IGNORECASE | re.ASCII)
    if not match:
        raise ContractError()
    authority = match[1]
    host = re.fullmatch(r"(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)(?::([0-9]{1,5}))?", authority)
    if not host or (host[2] is not None and not 1 <= int(host[2]) <= 65535):
        raise ContractError()
    if not host[1].startswith("[") and any(not part or part.startswith("-") or part.endswith("-") for part in host[1].split(".")):
        raise ContractError()
    return value


@dataclass(frozen=True, slots=True)
class DocumentOriginal:
    schema_version: int
    environment: str
    media_type: str
    encoding: str
    text: str
    utf8_byte_length: int
    raw_sha256: str

    def __post_init__(self):
        header(self)
        enum(self.media_type, ("text/plain",))
        enum(self.encoding, ("utf-8",))
        raw = _text(self.text)
        count(self.utf8_byte_length, 8192)
        digest(self.raw_sha256)
        if self.utf8_byte_length != len(raw) or self.raw_sha256 != sha256(raw).hexdigest():
            raise ContractError()


def original(text):
    raw = _text(text)
    return DocumentOriginal(1, "synthetic", "text/plain", "utf-8", text, len(raw), sha256(raw).hexdigest())


@dataclass(frozen=True, slots=True)
class DocumentRevision:
    schema_version: int
    environment: str
    source_id: str
    dataset_id: str
    document_id: str
    revision_id: str
    predecessor_revision_id: str | None
    kind: str
    action: str
    source_url: str
    published_at: str | None
    publication_unknown_reason: str | None
    original_hash: str | None
    original_absent_reason: str | None
    evidence_ref: str

    def __post_init__(self):
        header(self)
        for x in (*self.key[1:], self.evidence_ref):
            identifier(x)
        enum(self.kind, ("disclosure", "financial_report", "news"))
        enum(self.action, ("publish", "replace", "retract"))
        source_url(self.source_url)
        if self.action == "publish":
            if self.predecessor_revision_id is not None:
                raise ContractError()
        else:
            identifier(self.predecessor_revision_id)
            if self.predecessor_revision_id == self.revision_id:
                raise ContractError()
        if self.published_at is None:
            identifier(self.publication_unknown_reason)
        else:
            stamp(self, "published_at")
            if self.publication_unknown_reason is not None:
                raise ContractError()
        if self.action == "retract":
            if self.original_hash is not None:
                raise ContractError()
            identifier(self.original_absent_reason)
        else:
            digest(self.original_hash)
            if self.original_absent_reason is not None:
                raise ContractError()

    @property
    def identity(self):
        return (self.environment, self.source_id, self.dataset_id, self.document_id)

    @property
    def key(self):
        return self.identity + (self.revision_id,)


@dataclass(frozen=True, slots=True)
class RevisionRef:
    source_id: str
    dataset_id: str
    document_id: str
    revision_id: str
    revision_hash: str

    def __post_init__(self):
        for x in self.key:
            identifier(x)
        digest(self.revision_hash)

    @property
    def key(self):
        return (self.source_id, self.dataset_id, self.document_id, self.revision_id)


def revision_ref(revision):
    if type(revision) is not DocumentRevision:
        raise ContractError()
    return RevisionRef(*revision.key[1:], record_hash(revision))


@dataclass(frozen=True, slots=True)
class DocumentObservation:
    schema_version: int
    environment: str
    observation_id: str
    revision_ref: RevisionRef
    observed_at: str
    ingested_at: str
    rights_ref: str
    dataset_version: str
    evidence_ref: str

    def __post_init__(self):
        header(self)
        for x in (self.observation_id, self.rights_ref, self.dataset_version, self.evidence_ref):
            identifier(x)
        if type(self.revision_ref) is not RevisionRef:
            raise ContractError()
        stamp(self, "observed_at", "ingested_at")
        if self.observed_at > self.ingested_at:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class DocumentClaim:
    revision: DocumentRevision
    observation: DocumentObservation

    def __post_init__(self):
        if (type(self.revision) is not DocumentRevision or type(self.observation) is not DocumentObservation
                or revision_ref(self.revision) != self.observation.revision_ref):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class ClaimRef:
    revision_hash: str
    observation_hash: str

    def __post_init__(self):
        digest(self.revision_hash)
        digest(self.observation_hash)

    @property
    def key(self):
        return (self.revision_hash, self.observation_hash)


def claim_ref(claim):
    if type(claim) is not DocumentClaim:
        raise ContractError()
    return ClaimRef(record_hash(claim.revision), record_hash(claim.observation))


@dataclass(frozen=True, slots=True)
class Entity:
    entity_id: str
    entity_version: str
    kind: str
    evidence_ref: str
    known_at: str

    def __post_init__(self):
        for x in (self.entity_id, self.entity_version, self.evidence_ref):
            identifier(x)
        enum(self.kind, ("company", "fund_issuer", "unknown"))
        stamp(self, "known_at")


@dataclass(frozen=True, slots=True)
class DocumentEntityLink:
    revision_ref: RevisionRef
    entity_id: str
    entity_version: str
    relation: str
    evidence_ref: str
    known_at: str

    def __post_init__(self):
        if type(self.revision_ref) is not RevisionRef:
            raise ContractError()
        for x in (self.entity_id, self.entity_version, self.evidence_ref):
            identifier(x)
        enum(self.relation, ("subject", "reporting_entity"))
        stamp(self, "known_at")


@dataclass(frozen=True, slots=True)
class EntityInstrumentLink:
    entity_id: str
    entity_version: str
    catalog_version: str
    instrument_id: str
    instrument_version: str
    listing_venue_id: str
    relation: str
    valid_from: str
    valid_to: str | None
    known_at: str
    evidence_ref: str

    def __post_init__(self):
        for x in (self.entity_id, self.entity_version, self.catalog_version, self.instrument_id,
                  self.instrument_version, self.listing_venue_id, self.evidence_ref):
            identifier(x)
        enum(self.relation, ("issuer",))
        start, end = _window(self.valid_from, self.valid_to)
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_to", end)
        stamp(self, "known_at")


@dataclass(frozen=True, slots=True)
class DocumentEntityContext:
    schema_version: int
    environment: str
    context_id: str
    context_version: str
    entities: tuple[Entity, ...]
    document_links: tuple[DocumentEntityLink, ...]
    instrument_links: tuple[EntityInstrumentLink, ...]

    def __post_init__(self):
        header(self)
        identifier(self.context_id)
        identifier(self.context_version)
        sequence(self.entities, Entity, maximum=16)
        sequence(self.document_links, DocumentEntityLink, maximum=32)
        sequence(self.instrument_links, EntityInstrumentLink, maximum=32)
        entities = {(x.entity_id, x.entity_version) for x in self.entities}
        if len(entities) != len(self.entities):
            raise ContractError()
        links = set()
        for x in self.document_links:
            key = (x.revision_ref, x.entity_id, x.entity_version)
            if (x.entity_id, x.entity_version) not in entities or key in links:
                raise ContractError()
            links.add(key)
        for x in self.instrument_links:
            if (x.entity_id, x.entity_version) not in entities:
                raise ContractError()
        _no_overlap(self.instrument_links, lambda x: (x.catalog_version, x.instrument_id, x.listing_venue_id),
                    lambda x: x.valid_from, lambda x: x.valid_to)


@dataclass(frozen=True, slots=True)
class DocumentRequest:
    request_id: str
    source_id: str
    dataset_id: str
    dataset_version: str
    scope_ref: str
    document_ids: tuple[str, ...]
    expected_document_ids: tuple[str, ...]
    started_at: str
    deadline: str

    def __post_init__(self):
        for x in (self.request_id, self.source_id, self.dataset_id, self.dataset_version, self.scope_ref):
            identifier(x)
        sequence(self.document_ids, maximum=16, unique=True)
        sequence(self.expected_document_ids, maximum=16, unique=True)
        if self.document_ids and not set(self.expected_document_ids) <= set(self.document_ids):
            raise ContractError()
        stamp(self, "started_at", "deadline")
        if self.started_at >= self.deadline:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class DocumentLimits:
    max_claims: int
    max_bytes: int
    max_age_seconds: int
    policy_ref: str

    def __post_init__(self):
        for value, maximum in ((self.max_claims, 16), (self.max_bytes, MAX_BATCH_BYTES), (self.max_age_seconds, 31536000)):
            count(value, maximum)
            if value == 0:
                raise ContractError()
        identifier(self.policy_ref)


@dataclass(frozen=True, slots=True)
class DocumentReceipt:
    request_id: str
    scope_ref: str
    status: str
    complete: bool
    received_at: str
    claim_refs: tuple[ClaimRef, ...]
    missing_document_ids: tuple[str, ...]
    error_reason: str | None
    terminal_ref: str | None

    def __post_init__(self):
        identifier(self.request_id)
        identifier(self.scope_ref)
        enum(self.status, ("success", "partial", "failed", "not_collected"))
        if type(self.complete) is not bool:
            raise ContractError()
        stamp(self, "received_at")
        sequence(self.claim_refs, ClaimRef, maximum=16)
        sequence(self.missing_document_ids, maximum=16, unique=True)
        for x in (self.error_reason, self.terminal_ref):
            if x is not None:
                identifier(x)
        if self.complete:
            if self.status != "success" or self.error_reason is not None or self.missing_document_ids or self.terminal_ref is None:
                raise ContractError()
        if self.status in ("partial", "failed", "not_collected") and self.complete:
            raise ContractError()
        if self.status == "failed" and self.error_reason is None:
            raise ContractError()
        if self.status == "not_collected" and self.claim_refs:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class DocumentFileRef:
    schema_name: str
    basename: str
    byte_length: int
    canonical_hash: str

    def __post_init__(self):
        enum(self.schema_name, DOCUMENT_SCHEMAS)
        patterns = {"DocumentOriginal": r"original-[0-9]{4}\.json", "DocumentRevision": r"revision-[0-9]{4}\.json",
                    "DocumentObservation": r"observation-[0-9]{4}\.json", "DocumentEntityContext": r"context\.json"}
        if type(self.basename) is not str or not re.fullmatch(patterns[self.schema_name], self.basename):
            raise ContractError()
        count(self.byte_length, 65536)
        if self.byte_length == 0:
            raise ContractError()
        digest(self.canonical_hash)


@dataclass(frozen=True, slots=True)
class DocumentBatchManifest:
    schema_version: int
    environment: str
    batch_id: str
    source_id: str
    dataset_id: str
    dataset_version: str
    created_at: str
    request: DocumentRequest
    limits: DocumentLimits
    receipt: DocumentReceipt
    claims: tuple[ClaimRef, ...]
    file_refs: tuple[DocumentFileRef, ...]
    context_hash: str
    catalog_hash: str
    canonical_version: str

    def __post_init__(self):
        header(self)
        for x in (self.batch_id, self.source_id, self.dataset_id, self.dataset_version):
            identifier(x)
        stamp(self, "created_at")
        if type(self.request) is not DocumentRequest or type(self.limits) is not DocumentLimits or type(self.receipt) is not DocumentReceipt:
            raise ContractError()
        if ((self.source_id, self.dataset_id, self.dataset_version) !=
                (self.request.source_id, self.request.dataset_id, self.request.dataset_version)
                or (self.receipt.request_id, self.receipt.scope_ref) != (self.request.request_id, self.request.scope_ref)
                or not self.request.started_at <= self.receipt.received_at <= self.request.deadline
                or self.receipt.received_at > self.created_at):
            raise ContractError()
        sequence(self.claims, ClaimRef, maximum=16, unique=True)
        if self.claims != tuple(sorted(self.claims, key=lambda x:x.key)) or set(self.receipt.claim_refs) != set(self.claims):
            raise ContractError()
        if len(self.receipt.claim_refs) > self.limits.max_claims:
            raise ContractError()
        sequence(self.file_refs, DocumentFileRef, maximum=64)
        if (len({x.basename for x in self.file_refs}) != len(self.file_refs)
                or len({x.canonical_hash for x in self.file_refs}) != len(self.file_refs)
                or sum(x.byte_length for x in self.file_refs) > min(self.limits.max_bytes, MAX_BATCH_BYTES)):
            raise ContractError()
        contexts = [x for x in self.file_refs if x.schema_name == "DocumentEntityContext"]
        digest(self.context_hash)
        digest(self.catalog_hash)
        if len(contexts) != 1 or contexts[0].canonical_hash != self.context_hash or self.canonical_version != CANONICAL_VERSION:
            raise ContractError()


def catalog_hash(catalog):
    if type(catalog) is not Catalog:
        raise ContractError()
    return sha256(b"qh-document-catalog-v1\n" + json.dumps(asdict(catalog), sort_keys=True, separators=(",", ":"),
                  ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def encoded(value):
    from .serialization import CanonicalPayload, canonical_bytes
    return canonical_bytes(CanonicalPayload(type(value).__name__, 1, "synthetic", value))


def document_files(originals, claims, context):
    """Closed deterministic file roles; never use source IDs or URLs as paths."""
    sequence(originals, DocumentOriginal, maximum=16, unique=True)
    sequence(claims, DocumentClaim, maximum=16)
    if type(context) is not DocumentEntityContext:
        raise ContractError()
    revisions = {record_hash(x.revision): x.revision for x in claims}
    observations = {record_hash(x.observation): x.observation for x in claims}
    objects = {"DocumentOriginal": {record_hash(x): x for x in originals}, "DocumentRevision": revisions,
               "DocumentObservation": observations, "DocumentEntityContext": {record_hash(context): context}}
    payloads = []
    roles = (("DocumentOriginal", "original"), ("DocumentRevision", "revision"), ("DocumentObservation", "observation"))
    for name, prefix in roles:
        for index, (hashed, value) in enumerate(sorted(objects[name].items())):
            raw = encoded(value)
            payloads.append((DocumentFileRef(name, f"{prefix}-{index:04d}.json", len(raw), hashed), value))
    raw = encoded(context)
    payloads.append((DocumentFileRef("DocumentEntityContext", "context.json", len(raw), record_hash(context)), context))
    return tuple(payloads)


@dataclass(frozen=True, slots=True)
class DocumentBundle:
    manifest: DocumentBatchManifest
    originals: tuple[DocumentOriginal, ...]
    claims: tuple[DocumentClaim, ...]
    context: DocumentEntityContext

    def __post_init__(self):
        if type(self.manifest) is not DocumentBatchManifest:
            raise ContractError()
        sequence(self.originals, DocumentOriginal, maximum=16, unique=True)
        sequence(self.claims, DocumentClaim, maximum=16, unique=True)
        if type(self.context) is not DocumentEntityContext:
            raise ContractError()
        manifest = self.manifest
        if (tuple(sorted((claim_ref(x) for x in self.claims), key=lambda x:x.key)) != manifest.claims
                or tuple(ref for ref, _ in document_files(self.originals, self.claims, self.context)) != manifest.file_refs):
            raise ContractError()
        originals = {record_hash(x):x for x in self.originals}
        used = {x.revision.original_hash for x in self.claims if x.revision.original_hash is not None}
        if used != set(originals):
            raise ContractError()
        found = set()
        for claim in self.claims:
            r, o = claim.revision, claim.observation
            if ((r.source_id, r.dataset_id, o.dataset_version) != (manifest.source_id, manifest.dataset_id, manifest.dataset_version)
                    or (manifest.request.document_ids and r.document_id not in manifest.request.document_ids)
                    or o.ingested_at > manifest.receipt.received_at):
                raise ContractError()
            found.add(r.document_id)
        missing = set(manifest.request.expected_document_ids) - found
        if set(manifest.receipt.missing_document_ids) != missing:
            raise ContractError()
        if sum(x.byte_length for x in manifest.file_refs) + len(encoded(manifest)) > min(manifest.limits.max_bytes, MAX_BATCH_BYTES):
            raise ContractError()


def required_purposes(purpose, use):
    """연구 용도는 호출 목적과 현재 research 권리를 함께 요구한다."""
    enum(purpose, ("store", "research", "ai", "report"))
    enum(use, ("preserve", "entity_research", "instrument_research"))
    return (purpose,) if use == "preserve" or purpose == "research" else (purpose, "research")


def check_rights(manifest, claims, rights, *, at, purpose):
    if type(manifest) is not DocumentBatchManifest or type(rights) is not RightsGrant:
        raise ContractError()
    if not rights.allows(at=at, purpose=purpose, source_id=manifest.source_id,
                         dataset_id=manifest.dataset_id, dataset_version=manifest.dataset_version):
        raise ContractError()
    if any(x.observation.rights_ref != rights.rights_ref for x in claims):
        raise ContractError()


@dataclass(frozen=True, slots=True)
class DocumentSelection:
    claim: DocumentClaim
    original: DocumentOriginal
    entities: tuple[Entity, ...]
    instrument_links: tuple[EntityInstrumentLink, ...]
    context_verified: bool

    def __post_init__(self):
        if (type(self.claim) is not DocumentClaim or type(self.original) is not DocumentOriginal
                or record_hash(self.original) != self.claim.revision.original_hash or type(self.context_verified) is not bool):
            raise ContractError()
        sequence(self.entities, Entity, maximum=16, unique=True)
        sequence(self.instrument_links, EntityInstrumentLink, maximum=32, unique=True)
        if self.context_verified and not self.entities:
            raise ContractError()

    @property
    def trust(self):
        return "untrusted_text"


@dataclass(frozen=True, slots=True)
class DocumentView:
    mode: str
    use: str
    knowledge_cutoff: str
    evaluated_at: str
    original_cutoff: str | None
    policy_ref: str
    status: str
    freshness: str
    scope_complete: bool
    selected: tuple[DocumentSelection, ...]
    held_reasons: tuple[str, ...]
    missing_document_ids: tuple[str, ...]

    def __post_init__(self):
        enum(self.mode, ("as_known", "restated"))
        enum(self.use, ("preserve", "entity_research", "instrument_research"))
        stamp(self, "knowledge_cutoff", "evaluated_at")
        identifier(self.policy_ref)
        if self.original_cutoff is not None:
            stamp(self, "original_cutoff")
        if ((self.mode == "restated" and (self.original_cutoff is None or self.original_cutoff >= self.knowledge_cutoff))
                or (self.mode == "as_known" and self.original_cutoff is not None)):
            raise ContractError()
        enum(self.status, ("complete", "partial", "unknown", "not_collected"))
        enum(self.freshness, ("fresh", "stale", "unknown"))
        if type(self.scope_complete) is not bool or self.knowledge_cutoff > self.evaluated_at:
            raise ContractError()
        sequence(self.selected, DocumentSelection, maximum=16)
        sequence(self.held_reasons, unique=True)
        sequence(self.missing_document_ids, maximum=16, unique=True)

    @property
    def usable_for_research(self):
        return (self.use != "preserve" and self.status == "complete" and self.freshness == "fresh"
                and bool(self.selected) and all(x.context_verified for x in self.selected))


def _claim_order(claim):
    o = claim.observation
    return (o.ingested_at, o.observed_at, o.observation_id, claim_ref(claim).key)


def _entity_links(claim, context, catalog, cutoff, *, entity_id, instrument_id, listing_venue_id):
    links = [x for x in context.document_links if x.revision_ref == revision_ref(claim.revision) and x.known_at <= cutoff]
    entities = [x for x in context.entities if x.kind != "unknown" and x.known_at <= cutoff
                and (entity_id is None or x.entity_id == entity_id)
                and any((x.entity_id, x.entity_version) == (y.entity_id, y.entity_version) for y in links)]
    instruments = []
    for link in context.instrument_links:
        if (link.known_at > cutoff or link.catalog_version != catalog.catalog_version
                or not _contains(link.valid_from, link.valid_to, cutoff)
                or not any((link.entity_id, link.entity_version) == (x.entity_id, x.entity_version) for x in entities)
                or (instrument_id is not None and (link.instrument_id, link.listing_venue_id) != (instrument_id, listing_venue_id))):
            continue
        matches = [x for x in catalog.instruments if (x.instrument_id, x.instrument_version, x.listing_venue_id) ==
                   (link.instrument_id, link.instrument_version, link.listing_venue_id)]
        if (len(matches) == 1 and matches[0].known_at <= cutoff and matches[0].eligible_for_initial_scope
                and _contains(matches[0].valid_from, matches[0].valid_to, cutoff)):
            instruments.append(link)
    if instrument_id is not None:
        entities = [x for x in entities if any((x.entity_id, x.entity_version) == (y.entity_id, y.entity_version) for y in instruments)]
    return tuple(entities), tuple(instruments)


def select_view(bundle, *, catalog, rights, evaluated_at, knowledge_cutoff, purpose="research", use="entity_research",
                mode="as_known", original_cutoff=None, entity_id=None, instrument_id=None, listing_venue_id=None,
                limits=None):
    """전체 근거로 cutoff chain/conflict와 명시 기업 연결을 재구성한다."""
    if type(bundle) is not DocumentBundle or type(catalog) is not Catalog:
        raise ContractError()
    if catalog_hash(catalog) != bundle.manifest.catalog_hash:
        raise ContractError()
    now, cutoff = utc_instant(evaluated_at), utc_instant(knowledge_cutoff)
    enum(mode, ("as_known", "restated"))
    enum(use, ("preserve", "entity_research", "instrument_research"))
    if cutoff > now or (mode == "restated" and (original_cutoff is None or utc_instant(original_cutoff) >= cutoff)):
        raise ContractError()
    if mode == "as_known" and original_cutoff is not None:
        raise ContractError()
    for value in (entity_id, instrument_id, listing_venue_id):
        if value is not None:
            identifier(value)
    if ((instrument_id is None) != (listing_venue_id is None)
            or (use == "instrument_research") != (instrument_id is not None and listing_venue_id is not None)):
        raise ContractError()
    for required in required_purposes(purpose, use):
        check_rights(bundle.manifest, bundle.claims, rights, at=now, purpose=required)
    policy = bundle.manifest.limits if limits is None else limits
    if type(policy) is not DocumentLimits:
        raise ContractError()
    manifest, held, selected = bundle.manifest, set(), []
    known = [x for x in bundle.claims if x.observation.observed_at <= cutoff and x.observation.ingested_at <= cutoff]
    blocked, facts, observations, groups = set(), {}, {}, {}
    for claim in known:
        r, o = claim.revision, claim.observation
        facts.setdefault(r.key, set()).add(record_hash(r))
        observations.setdefault(o.observation_id, []).append(claim)
        if r.published_at is None:
            held.add("publication_unknown")
            blocked.add(r.identity)
        elif r.published_at > o.observed_at:
            held.add("publication_observation_conflict")
            blocked.add(r.identity)
        elif r.published_at <= cutoff:
            bucket = groups.setdefault(r.identity, {})
            old = bucket.get(r.revision_id)
            if old is None or _claim_order(claim) < _claim_order(old):
                bucket[r.revision_id] = claim
    for key, values in facts.items():
        if len(values) > 1:
            blocked.add(key[:-1])
            held.add("revision_conflict")
    for values in observations.values():
        if len({record_hash(x.observation) for x in values}) > 1:
            blocked.update(x.revision.identity for x in values)
            held.add("observation_id_conflict")
    originals = {record_hash(x): x for x in bundle.originals}
    for identity, revisions in groups.items():
        if identity in blocked:
            continue
        roots = [x for x in revisions.values() if x.revision.action == "publish"]
        children = {}
        for claim in revisions.values():
            if claim.revision.predecessor_revision_id is not None:
                children.setdefault(claim.revision.predecessor_revision_id, []).append(claim)
        if len(roots) != 1 or any(k not in revisions or len(v) != 1 for k,v in children.items()):
            held.add("chain_missing_or_fork")
            continue
        node, seen, invalid = roots[0], set(), False
        while True:
            r = node.revision
            if r.revision_id in seen:
                invalid = True
                break
            seen.add(r.revision_id)
            next_nodes = children.get(r.revision_id, ())
            if not next_nodes:
                break
            child = next_nodes[0]
            if (r.action == "retract" or r.kind != child.revision.kind or child.revision.published_at < r.published_at):
                invalid = True
                break
            node = child
        if invalid or len(seen) != len(revisions):
            held.add("chain_invalid")
            continue
        if node.revision.action == "retract":
            held.add("retracted")
            continue
        entities, instruments = _entity_links(node, bundle.context, catalog, cutoff, entity_id=entity_id,
                                              instrument_id=instrument_id, listing_venue_id=listing_venue_id)
        verified = bool(entities) and (use != "instrument_research" or bool(instruments))
        if use != "preserve" and not verified:
            held.add("entity_or_instrument_unverified")
            continue
        selected.append(DocumentSelection(node, originals[node.revision.original_hash], entities, instruments, verified))
    receipt = manifest.receipt
    found = {x.revision.document_id for x in known}
    missing = tuple(sorted(set(manifest.request.expected_document_ids) - found))
    scope_complete = receipt.complete and receipt.received_at <= cutoff
    if receipt.received_at > cutoff:
        held.add("receipt_after_cutoff")
    if missing:
        held.add("missing_document")
    if receipt.status == "not_collected":
        status = "not_collected"
    elif receipt.status != "success" or not scope_complete or missing:
        status = "partial"
    elif held:
        status = "unknown"
    else:
        status = "complete"
    freshness = "unknown"
    if status == "complete" and selected:
        stale = any(datetime.fromisoformat(now) - datetime.fromisoformat(x.claim.revision.published_at) >
                    timedelta(seconds=policy.max_age_seconds) for x in selected)
        freshness = "stale" if stale else "fresh"
    return DocumentView(mode, use, cutoff, now, original_cutoff, policy.policy_ref, status, freshness, scope_complete,
                        tuple(sorted(selected, key=lambda x:x.claim.revision.key)), tuple(sorted(held)), missing)
