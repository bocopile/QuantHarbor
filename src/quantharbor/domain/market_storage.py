"""Q17B 고정 저장 사실·receipt·재생 계약. 파일/Arrow/current clock을 읽지 않는다."""
from dataclasses import dataclass
import re

from .market_data import (
    FetchRequest, IngestLimits, IngestState, MarketEnvelope, MarketItem, PageFacts, QualityResult,
    QueryScope, RecordRefSet, RightsGrant, count, digest, enum, fail_ingest, header, item_ref,
    record_hash, reduce_page_facts, sequence, stamp,
)
from .primitives import ContractError, identifier


STORAGE_VERSION = "market-evidence-v1"
REDUCER_VERSION = "market-reducer-v1"
CANONICAL_VERSION = "qh-canonical-json-v1"
MAX_BUNDLE_BYTES = 20971520
MAX_FILE_BYTES = 4194304
REJECTIONS = ("scope_or_cursor_mismatch", "deadline_or_clock", "page_clock_invalid", "repeated_cursor",
              "byte_limit", "record_limit", "record_scope_or_future", "normalization_rejected")


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


def claim_ref(item):
    if type(item) is not MarketItem:
        raise ContractError()
    return ClaimRef(record_hash(item.revision), record_hash(item.observation))


@dataclass(frozen=True, slots=True)
class MarketEvidenceIndex:
    schema_version: int
    environment: str
    claims: tuple[ClaimRef, ...]

    def __post_init__(self):
        header(self)
        sequence(self.claims, ClaimRef, unique=True)
        object.__setattr__(self, "claims", tuple(sorted(self.claims, key=lambda x: x.key)))


def evidence_index(evidence):
    sequence(evidence, MarketItem)
    return MarketEvidenceIndex(1, "synthetic", tuple(claim_ref(x) for x in evidence))


@dataclass(frozen=True, slots=True)
class ContextRef:
    kind: str
    context_id: str
    version: str
    sha256: str

    def __post_init__(self):
        enum(self.kind, ("catalog", "calendar", "timezone"))
        # timezone ID contains '/', unlike ordinary internal identifiers.
        if self.kind == "timezone":
            from .calendar import timezone_name
            timezone_name(self.context_id)
        else:
            identifier(self.context_id)
        identifier(self.version)
        digest(self.sha256)


@dataclass(frozen=True, slots=True)
class MarketIngestDescriptor:
    schema_version: int
    environment: str
    request: FetchRequest
    limits: IngestLimits
    evaluated_at: str
    view_mode: str
    original_cutoff: str | None
    catalog_ref: ContextRef
    calendar_ref: ContextRef
    timezone_ref: ContextRef
    rights_ref: str
    historical_rights_snapshot: RightsGrant

    def __post_init__(self):
        header(self)
        if type(self.request) is not FetchRequest or type(self.limits) is not IngestLimits:
            raise ContractError()
        stamp(self, "evaluated_at")
        enum(self.view_mode, ("as_known", "restated"))
        if self.view_mode == "restated":
            if self.original_cutoff is None:
                raise ContractError()
            stamp(self, "original_cutoff")
            if self.original_cutoff >= self.request.knowledge_cutoff:
                raise ContractError()
        elif self.original_cutoff is not None:
            raise ContractError()
        if self.evaluated_at < self.request.started_at or self.request.knowledge_cutoff > self.evaluated_at:
            raise ContractError()
        for value, kind in ((self.catalog_ref, "catalog"), (self.calendar_ref, "calendar"), (self.timezone_ref, "timezone")):
            if type(value) is not ContextRef or value.kind != kind:
                raise ContractError()
        grant = self.historical_rights_snapshot
        if (type(grant) is not RightsGrant or grant.rights_ref != self.rights_ref
                or (grant.source_id, grant.dataset_id, grant.dataset_version) !=
                   (self.request.source_id, self.request.dataset_id, self.request.dataset_version)):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class MarketPageReceipt:
    schema_version: int
    environment: str
    ordinal: int
    kind: str
    request_id: str
    scope: QueryScope
    cursor_in: str | None
    cursor_out: str | None
    terminal: bool
    status: str
    source_snapshot: str | None
    received_at: str
    error_reason: str | None
    not_before: str | None
    response_size_bytes: int
    response_sha256: str
    item_refs: tuple[ClaimRef, ...]

    def __post_init__(self):
        header(self)
        count(self.ordinal, 16)
        if self.ordinal == 0:
            raise ContractError()
        enum(self.kind, ("page", "rejection", "fetch_failure"))
        identifier(self.request_id)
        if type(self.scope) is not QueryScope or type(self.terminal) is not bool:
            raise ContractError()
        for x in (self.cursor_in, self.cursor_out, self.source_snapshot):
            if x is not None:
                identifier(x)
        stamp(self, "received_at")
        count(self.response_size_bytes)
        digest(self.response_sha256)
        sequence(self.item_refs, ClaimRef)  # Page order and repeats are meaningful.
        if self.kind == "page":
            self.facts(())  # shared field validator, not fake source bytes
        elif self.kind == "rejection":
            enum(self.error_reason, REJECTIONS)
            enum(self.status, ("success", "failed", "rate_limited", "normalization_failed"))
            if self.item_refs:
                raise ContractError()
            if self.not_before is not None:
                stamp(self, "not_before")
        else:
            if (self.status != "failed" or self.error_reason != "fetch_or_normalization_failed"
                    or self.item_refs or self.terminal or self.cursor_out is not None or self.source_snapshot is not None
                    or self.not_before is not None or self.response_size_bytes != 0):
                raise ContractError()
            from hashlib import sha256
            if self.response_sha256 != sha256(b"").hexdigest():
                raise ContractError()

    def facts(self, items):
        return PageFacts(self.request_id, self.scope, self.cursor_in, self.cursor_out, self.terminal,
                         self.status, items, self.response_size_bytes, self.response_sha256, self.source_snapshot,
                         self.received_at, self.error_reason, self.not_before)


def receipt_from_page(facts, before, after, ordinal):
    if type(facts) is not PageFacts:
        raise ContractError()
    accepted = after.pages == before.pages + 1
    reason = facts.error_reason
    if not accepted:
        reasons = set(after.errors) - set(before.errors)
        if len(reasons) != 1:
            raise ContractError()
        reason = reasons.pop()
    return MarketPageReceipt(1, "synthetic", ordinal, "page" if accepted else "rejection", facts.request_id,
        facts.scope, facts.cursor_in, facts.cursor_out, facts.terminal, facts.status, facts.source_snapshot,
        facts.received_at, reason, facts.not_before, facts.response_size_bytes, facts.response_sha256,
        tuple(claim_ref(x) for x in facts.items) if accepted else ())


def fetch_failure_receipt(request, state, evaluated_at, ordinal):
    from hashlib import sha256
    return MarketPageReceipt(1, "synthetic", ordinal, "fetch_failure", request.request_id, request.scope,
        state.next_cursor, None, False, "failed", None, evaluated_at, "fetch_or_normalization_failed", None,
        0, sha256(b"").hexdigest(), ())


def replay_receipts(descriptor, receipts, evidence):
    if type(descriptor) is not MarketIngestDescriptor:
        raise ContractError()
    sequence(receipts, MarketPageReceipt, maximum=16)
    index = evidence_index(evidence)
    by_claim = {claim_ref(x): x for x in evidence}
    request, limits = descriptor.request, descriptor.limits
    state, used = IngestState(), set()
    grant = descriptor.historical_rights_snapshot
    permitted = grant.allows(at=descriptor.evaluated_at, purpose="store", source_id=request.source_id,
                             dataset_id=request.dataset_id, dataset_version=request.dataset_version)
    if not permitted:
        state = fail_ingest(state, "rights_blocked")
    elif not receipts:
        raise ContractError()
    for number, receipt in enumerate(receipts, 1):
        if (receipt.ordinal != number or number > limits.max_pages or state.errors or state.terminal
                or state.pages >= limits.max_pages):
            raise ContractError()
        if receipt.kind == "fetch_failure":
            if (receipt.request_id != request.request_id or receipt.scope != request.scope
                    or receipt.cursor_in != state.next_cursor or receipt.received_at != descriptor.evaluated_at):
                raise ContractError()
            state = fail_ingest(state, "fetch_or_normalization_failed")
        elif receipt.kind == "rejection":
            # The omitted body cannot excuse preserved request/cursor/clock metadata.
            # Probe the same reducer with typed empty items, never fabricated raw bytes.
            from dataclasses import replace
            facts = replace(receipt, kind="page",
                            error_reason=None if receipt.status == "success" else "source_failed").facts(())
            probed = reduce_page_facts(state, request, facts, limits, evaluated_at=descriptor.evaluated_at)
            reasons = set(probed.errors) - set(state.errors)
            metadata_reasons = {"scope_or_cursor_mismatch", "deadline_or_clock", "page_clock_invalid", "repeated_cursor"}
            known_failure = reasons & (metadata_reasons | {"byte_limit"})
            if known_failure:
                if reasons != {receipt.error_reason}:
                    raise ContractError()
                state = probed
            elif receipt.error_reason in ("byte_limit", "record_limit", "record_scope_or_future", "normalization_rejected"):
                # Only the omitted body-based claim remains unverifiable. It stays a failure.
                state = fail_ingest(state, receipt.error_reason)
            else:
                raise ContractError()  # A declared metadata rejection must actually reproduce.

        else:
            try:
                items = tuple(by_claim[ref] for ref in receipt.item_refs)
            except KeyError:
                raise ContractError() from None
            used.update(receipt.item_refs)
            before = state
            state = reduce_page_facts(state, request, receipt.facts(items), limits, evaluated_at=descriptor.evaluated_at)
            if state.pages != before.pages + 1:
                raise ContractError()
    if not state.errors and not state.terminal and state.pages < limits.max_pages:
        raise ContractError()  # Truncated trace is not a page-limit stop.
    if used != set(index.claims) or set(claim_ref(x) for x in state.revisions.evidence) != used:
        raise ContractError()
    return state


@dataclass(frozen=True, slots=True)
class ConflictSummary:
    kind: str
    left: ClaimRef
    right: ClaimRef
    detected_at: str

    def __post_init__(self):
        enum(self.kind, ("revision", "observation_id"))
        if type(self.left) is not ClaimRef or type(self.right) is not ClaimRef:
            raise ContractError()
        stamp(self, "detected_at")


@dataclass(frozen=True, slots=True)
class ReplaySummary:
    pages: int
    bytes_received: int
    records_received: int
    next_cursor: str | None
    seen_cursors: tuple[str, ...]
    errors: tuple[str, ...]
    terminal: bool
    snapshots: tuple[str, ...]
    snapshot_missing: bool
    not_before: str | None
    last_received_at: str | None
    accepted_record_set_hash: str
    evidence_index_hash: str
    conflicts: tuple[ConflictSummary, ...]
    quality: QualityResult

    def __post_init__(self):
        count(self.pages, 16)
        count(self.bytes_received)
        count(self.records_received, 128)
        for value in (self.next_cursor,):
            if value is not None:
                identifier(value)
        sequence(self.seen_cursors, maximum=16, unique=True)
        sequence(self.errors, unique=True)
        sequence(self.snapshots, maximum=16, unique=True)
        sequence(self.conflicts, ConflictSummary)
        if type(self.terminal) is not bool or type(self.snapshot_missing) is not bool or type(self.quality) is not QualityResult:
            raise ContractError()
        for name in ("not_before", "last_received_at"):
            if getattr(self, name) is not None:
                stamp(self, name)
        digest(self.accepted_record_set_hash)
        digest(self.evidence_index_hash)


def summary_for(state, envelope):
    if type(state) is not IngestState or type(envelope) is not MarketEnvelope:
        raise ContractError()
    return ReplaySummary(state.pages, state.bytes_received, state.records_received, state.next_cursor,
        state.seen_cursors, state.errors, state.terminal, state.snapshots, state.snapshot_missing,
        state.not_before, state.last_received_at, envelope.content_hash, record_hash(evidence_index(state.revisions.evidence)),
        tuple(ConflictSummary(c.kind, claim_ref(c.counterpart), claim_ref(c.incoming), c.detected_at)
              for c in state.revisions.conflicts), envelope.quality)


@dataclass(frozen=True, slots=True)
class FileRef:
    role: str
    name: str
    size_bytes: int
    sha256: str
    row_count: int | None

    def __post_init__(self):
        enum(self.role, ("descriptor", "receipt", "evidence"))
        suffix = "parquet" if self.role == "evidence" else "json"
        if type(self.name) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\." + suffix, self.name):
            raise ContractError()
        count(self.size_bytes, MAX_FILE_BYTES if self.role == "evidence" else 65536)
        if not self.size_bytes:
            raise ContractError()
        digest(self.sha256)
        if self.role == "evidence":
            count(self.row_count, 32)
            if not self.row_count:
                raise ContractError()
        elif self.row_count is not None:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class MarketStorageManifest:
    schema_version: int
    environment: str
    source_id: str
    dataset_id: str
    dataset_version: str
    previous_version: str | None
    created_at: str
    storage_schema_version: str
    reducer_version: str
    canonical_version: str
    descriptor_file: FileRef
    receipt_files: tuple[FileRef, ...]
    evidence_files: tuple[FileRef, ...]
    evidence_count: int
    evidence_index_hash: str
    accepted_record_set_hash: str
    replay_summary: ReplaySummary

    def __post_init__(self):
        header(self)
        for x in (self.source_id, self.dataset_id, self.dataset_version):
            identifier(x)
        if self.previous_version is not None:
            identifier(self.previous_version)
            if self.previous_version == self.dataset_version:
                raise ContractError()
        stamp(self, "created_at")
        if (self.storage_schema_version, self.reducer_version, self.canonical_version) != (
                STORAGE_VERSION, REDUCER_VERSION, CANONICAL_VERSION):
            raise ContractError()
        if type(self.descriptor_file) is not FileRef or self.descriptor_file.role != "descriptor":
            raise ContractError()
        sequence(self.receipt_files, FileRef, maximum=16)
        sequence(self.evidence_files, FileRef, maximum=4)
        if any(x.role != "receipt" for x in self.receipt_files) or any(x.role != "evidence" for x in self.evidence_files):
            raise ContractError()
        files = (self.descriptor_file,) + self.receipt_files + self.evidence_files
        if len({x.name for x in files}) != len(files) or sum(x.size_bytes for x in files) > MAX_BUNDLE_BYTES:
            raise ContractError()
        count(self.evidence_count, 128)
        if sum(x.row_count for x in self.evidence_files) != self.evidence_count:
            raise ContractError()
        digest(self.evidence_index_hash)
        digest(self.accepted_record_set_hash)
        if (type(self.replay_summary) is not ReplaySummary
                or self.replay_summary.evidence_index_hash != self.evidence_index_hash
                or self.replay_summary.accepted_record_set_hash != self.accepted_record_set_hash):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class StorageBundle:
    descriptor: MarketIngestDescriptor
    receipts: tuple[MarketPageReceipt, ...]
    evidence: tuple[MarketItem, ...]
    state: IngestState
    envelope: MarketEnvelope
    summary: ReplaySummary

    def __post_init__(self):
        if (type(self.descriptor) is not MarketIngestDescriptor or type(self.state) is not IngestState
                or type(self.envelope) is not MarketEnvelope or type(self.summary) is not ReplaySummary):
            raise ContractError()
        sequence(self.receipts, MarketPageReceipt, maximum=16)
        evidence_index(self.evidence)
        if self.summary != summary_for(self.state, self.envelope) or set(self.evidence) != set(self.state.revisions.evidence):
            raise ContractError()
