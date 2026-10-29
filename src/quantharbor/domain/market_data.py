"""Q17A 합성 시장 자료. 순수 사실·관측·시점·권리 규칙이며 금융 실행은 없다."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import re

from .primitives import ContractError, FX, Money, Price, Quantity, calendar_date, decimal_string, identifier, utc_instant


MAX_RECORDS = 128


def enum(value, choices):
    if type(value) is not str or value not in choices:
        raise ContractError()


def count(value, maximum=1048576):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ContractError()


def digest(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ContractError()


def sequence(value, expected=str, maximum=MAX_RECORDS, unique=False):
    if type(value) is not tuple or len(value) > maximum or any(type(x) is not expected for x in value):
        raise ContractError()
    if expected is str:
        for x in value:
            identifier(x)
    if unique and len(set(value)) != len(value):
        raise ContractError()


def stamp(obj, *names):
    for name in names:
        object.__setattr__(obj, name, utc_instant(getattr(obj, name)))


def header(obj):
    if type(obj.schema_version) is not int or obj.schema_version != 1:
        raise ContractError()
    enum(obj.environment, ("synthetic",))


def record_hash(record):
    # Local import avoids a schema registry/domain import cycle.
    from .serialization import CanonicalPayload, canonical_hash
    return canonical_hash(CanonicalPayload(type(record).__name__, 1, "synthetic", record))


@dataclass(frozen=True, slots=True)
class ActionRef:
    environment: str
    source_id: str
    dataset_id: str
    series_id: str
    event_id: str
    revision_id: str
    revision_hash: str

    def __post_init__(self):
        enum(self.environment, ("synthetic",))
        for value in self.key[1:]:
            identifier(value)
        digest(self.revision_hash)

    @property
    def key(self):
        return (self.environment, self.source_id, self.dataset_id, self.series_id, self.event_id, self.revision_id)


@dataclass(frozen=True, slots=True)
class Adjustment:
    method: str
    version: str
    basis_at: str
    action_refs: tuple[ActionRef, ...]
    knowledge_at: str
    evidence_ref: str

    def __post_init__(self):
        for x in (self.method, self.version, self.evidence_ref):
            identifier(x)
        sequence(self.action_refs, ActionRef, unique=True)
        if not self.action_refs:
            raise ContractError()
        stamp(self, "basis_at", "knowledge_at")


@dataclass(frozen=True, slots=True)
class PriceBar:
    instrument_id: str
    listing_venue_id: str
    execution_venue_id: str
    source_code: str
    starts_at: str
    ends_at: str
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Quantity | None
    volume_unknown_reason: str | None
    adjustment: str
    adjustment_details: Adjustment | None

    def __post_init__(self):
        from .catalog import source_code
        for x in (self.instrument_id, self.listing_venue_id, self.execution_venue_id):
            identifier(x)
        source_code(self.source_code)
        stamp(self, "starts_at", "ends_at")
        if self.starts_at >= self.ends_at:
            raise ContractError()
        prices = (self.open, self.high, self.low, self.close)
        if any(type(p) is not Price for p in prices):
            raise ContractError()
        units = {(p.currency, p.instrument_id, p.quantity_unit) for p in prices}
        if len(units) != 1 or self.open.instrument_id != self.instrument_id:
            raise ContractError()
        o, h, l, c = (Decimal(p.amount) for p in prices)
        if l <= 0 or not l <= o <= h or not l <= c <= h:
            raise ContractError()
        if self.volume is None:
            identifier(self.volume_unknown_reason)
        elif (type(self.volume) is not Quantity or self.volume_unknown_reason is not None
              or (self.volume.instrument_id, self.volume.unit) != (self.instrument_id, self.open.quantity_unit)
              or Decimal(self.volume.amount) < 0):
            raise ContractError()
        enum(self.adjustment, ("raw", "adjusted"))
        if ((self.adjustment == "raw" and self.adjustment_details is not None)
                or (self.adjustment == "adjusted" and type(self.adjustment_details) is not Adjustment)):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class FXObservation:
    fx: FX

    def __post_init__(self):
        if type(self.fx) is not FX or self.fx.base_currency == self.fx.quote_currency:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class CorporateAction:
    instrument_id: str
    listing_venue_id: str
    execution_venue_id: str
    source_code: str
    action_kind: str
    quantity_unit: str
    effective_date: str
    record_date: str | None
    payment_date: str | None
    dates_unknown_reason: str | None
    numerator: str | None
    denominator: str | None
    cash_per_unit: Money | None

    def __post_init__(self):
        from .catalog import source_code
        for x in (self.instrument_id, self.listing_venue_id, self.execution_venue_id, self.quantity_unit):
            identifier(x)
        source_code(self.source_code)
        calendar_date(self.effective_date)
        for value in (self.record_date, self.payment_date):
            if value is not None:
                calendar_date(value)
        if self.record_date is None or self.payment_date is None:
            identifier(self.dates_unknown_reason)
        elif self.dates_unknown_reason is not None:
            raise ContractError()
        enum(self.action_kind, ("split", "cash_dividend"))
        if self.action_kind == "split":
            for name in ("numerator", "denominator"):
                value = decimal_string(getattr(self, name))
                if Decimal(value) <= 0:
                    raise ContractError()
                object.__setattr__(self, name, value)
            if self.cash_per_unit is not None:
                raise ContractError()
        elif (self.numerator is not None or self.denominator is not None
              or type(self.cash_per_unit) is not Money or Decimal(self.cash_per_unit.amount) < 0):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class MarketRevision:
    schema_version: int
    environment: str
    source_id: str
    dataset_id: str
    series_id: str
    event_id: str
    revision_id: str
    predecessor_revision_id: str | None
    revision_kind: str
    effective_at: str
    published_at: str | None
    publication_unknown_reason: str | None
    normalization_version: str
    payload: PriceBar | FXObservation | CorporateAction | None

    def __post_init__(self):
        header(self)
        for x in (*self.identity[1:], self.revision_id, self.normalization_version):
            identifier(x)
        enum(self.revision_kind, ("original", "replacement", "retraction", "unsupported"))
        if self.revision_kind == "original":
            if self.predecessor_revision_id is not None:
                raise ContractError()
        else:
            identifier(self.predecessor_revision_id)
            if self.predecessor_revision_id == self.revision_id:
                raise ContractError()
        if self.revision_kind in ("retraction", "unsupported"):
            if self.payload is not None:
                raise ContractError()
        elif type(self.payload) not in (PriceBar, FXObservation, CorporateAction):
            raise ContractError()
        stamp(self, "effective_at")
        if self.published_at is None:
            identifier(self.publication_unknown_reason)
        else:
            stamp(self, "published_at")
            if self.publication_unknown_reason is not None:
                raise ContractError()
        if type(self.payload) is PriceBar:
            if self.effective_at != self.payload.ends_at:
                raise ContractError()
            details = self.payload.adjustment_details
            if details is not None and (self.published_at is None or details.knowledge_at > self.published_at):
                raise ContractError()
        if type(self.payload) is FXObservation:
            if self.payload.fx.source_id != self.source_id or self.payload.fx.as_of != self.effective_at:
                raise ContractError()

    @property
    def identity(self):
        return (self.environment, self.source_id, self.dataset_id, self.series_id, self.event_id)

    @property
    def key(self):
        return self.identity + (self.revision_id,)


@dataclass(frozen=True, slots=True)
class MarketObservation:
    schema_version: int
    environment: str
    observation_id: str
    source_id: str
    dataset_id: str
    series_id: str
    event_id: str
    revision_id: str
    revision_hash: str
    observed_at: str
    ingested_at: str
    source_content_sha256: str
    evidence_ref: str
    rights_ref: str
    catalog_version: str
    calendar_version: str

    def __post_init__(self):
        header(self)
        for x in (self.observation_id, *self.key[1:], self.evidence_ref, self.rights_ref,
                  self.catalog_version, self.calendar_version):
            identifier(x)
        digest(self.revision_hash)
        digest(self.source_content_sha256)
        stamp(self, "observed_at", "ingested_at")
        if self.observed_at > self.ingested_at:
            raise ContractError()

    @property
    def key(self):
        return (self.environment, self.source_id, self.dataset_id, self.series_id, self.event_id, self.revision_id)


@dataclass(frozen=True, slots=True)
class MarketItem:
    revision: MarketRevision
    observation: MarketObservation

    def __post_init__(self):
        if (type(self.revision) is not MarketRevision or type(self.observation) is not MarketObservation
                or self.revision.key != self.observation.key
                or record_hash(self.revision) != self.observation.revision_hash
                or (self.revision.published_at is not None
                    and self.revision.published_at > self.observation.observed_at)):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class RecordRef:
    environment: str
    source_id: str
    dataset_id: str
    series_id: str
    event_id: str
    revision_id: str
    revision_hash: str
    observation_id: str
    observation_hash: str

    def __post_init__(self):
        enum(self.environment, ("synthetic",))
        for x in (self.source_id, self.dataset_id, self.series_id, self.event_id, self.revision_id, self.observation_id):
            identifier(x)
        digest(self.revision_hash)
        digest(self.observation_hash)

    @property
    def key(self):
        return (self.environment, self.source_id, self.dataset_id, self.series_id, self.event_id,
                self.revision_id, self.observation_id)


def item_ref(item):
    r, o = item.revision, item.observation
    return RecordRef(*r.key, record_hash(r), o.observation_id, record_hash(o))


@dataclass(frozen=True, slots=True)
class RecordRefSet:
    schema_version: int
    environment: str
    records: tuple[RecordRef, ...]

    def __post_init__(self):
        header(self)
        sequence(self.records, RecordRef)
        if (len({x.key for x in self.records}) != len(self.records)
                or len({x.observation_id for x in self.records}) != len(self.records)):
            raise ContractError()
        facts = {}
        for ref in self.records:
            if facts.setdefault(ref.key[:6], ref.revision_hash) != ref.revision_hash:
                raise ContractError()
        object.__setattr__(self, "records", tuple(sorted(self.records, key=lambda x: x.key)))


@dataclass(frozen=True, slots=True)
class QualityResult:
    status: str
    missing_scope: tuple[str, ...]
    reasons: tuple[str, ...]
    freshness: str
    evaluated_at: str
    policy_ref: str
    rights_allowed: bool

    def __post_init__(self):
        enum(self.status, ("complete", "partial", "unavailable", "invalid"))
        enum(self.freshness, ("fresh", "stale", "unknown"))
        sequence(self.missing_scope, unique=True)
        sequence(self.reasons, unique=True)
        identifier(self.policy_ref)
        stamp(self, "evaluated_at")
        if type(self.rights_allowed) is not bool or (self.status == "complete" and self.missing_scope):
            raise ContractError()

    @property
    def eligible_for_new_risk(self):
        return self.status == "complete" and self.freshness == "fresh" and self.rights_allowed


@dataclass(frozen=True, slots=True)
class MarketEnvelope:
    envelope_id: str
    schema_version: int
    source_id: str
    dataset_id: str
    dataset_version: str
    environment: str
    queried_scope: tuple[str, ...]
    items: tuple[MarketItem, ...]
    as_of: str
    observed_at: str
    ingested_at: str
    quality: QualityResult
    rights_ref: str
    content_hash: str
    lineage_refs: tuple[str, ...]

    def __post_init__(self):
        header(self)
        for x in (self.envelope_id, self.source_id, self.dataset_id, self.dataset_version, self.rights_ref):
            identifier(x)
        sequence(self.queried_scope, unique=True)
        sequence(self.items, MarketItem)
        sequence(self.lineage_refs, unique=True)
        stamp(self, "as_of", "observed_at", "ingested_at")
        if type(self.quality) is not QualityResult or self.observed_at > self.ingested_at:
            raise ContractError()
        for item in self.items:
            r, o = item.revision, item.observation
            if ((r.source_id, r.dataset_id) != (self.source_id, self.dataset_id)
                    or r.series_id not in self.queried_scope or o.observed_at > self.observed_at
                    or o.ingested_at > self.ingested_at or o.rights_ref != self.rights_ref):
                raise ContractError()
        expected = record_hash(RecordRefSet(1, self.environment, tuple(item_ref(x) for x in self.items)))
        if self.content_hash != expected:
            raise ContractError()


@dataclass(frozen=True, slots=True)
class ManifestFile:
    name: str
    size_bytes: int
    sha256: str
    row_count: int
    record_set_hash: str

    def __post_init__(self):
        if type(self.name) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.parquet", self.name):
            raise ContractError()
        count(self.size_bytes, 1073741824)
        count(self.row_count, 1000000)
        digest(self.sha256)
        digest(self.record_set_hash)


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    schema_version: int
    environment: str
    dataset_id: str
    dataset_version: str
    previous_version: str | None
    normalization_version: str
    canonical_version: str
    source_id: str
    coverage_start: str
    coverage_end: str
    files: tuple[ManifestFile, ...]
    record_set: RecordRefSet
    record_set_hash: str
    quality_ref: str
    rights_ref: str
    view_mode: str
    as_of: str
    knowledge_cutoff: str
    created_at: str

    def __post_init__(self):
        header(self)
        for x in (self.dataset_id, self.dataset_version, self.normalization_version, self.source_id,
                  self.quality_ref, self.rights_ref):
            identifier(x)
        if self.previous_version is not None:
            identifier(self.previous_version)
            if self.previous_version == self.dataset_version:
                raise ContractError()
        if self.canonical_version != "qh-canonical-json-v1":
            raise ContractError()
        enum(self.view_mode, ("as_known", "restated"))
        stamp(self, "coverage_start", "coverage_end", "as_of", "knowledge_cutoff", "created_at")
        if self.coverage_start >= self.coverage_end or self.knowledge_cutoff > self.created_at:
            raise ContractError()
        sequence(self.files, ManifestFile)
        if len({x.name for x in self.files}) != len(self.files) or type(self.record_set) is not RecordRefSet:
            raise ContractError()
        if self.record_set_hash != record_hash(self.record_set):
            raise ContractError()
        if any((x.source_id, x.dataset_id) != (self.source_id, self.dataset_id) for x in self.record_set.records):
            raise ContractError()
        if sum(x.row_count for x in self.files) != len(self.record_set.records):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class RightsGrant:
    rights_ref: str
    environment: str
    source_id: str
    dataset_id: str
    dataset_version: str
    purposes: tuple[str, ...]
    valid_from: str
    valid_to: str
    revoked_at: str | None

    def __post_init__(self):
        enum(self.environment, ("synthetic",))
        for x in (self.rights_ref, self.source_id, self.dataset_id, self.dataset_version):
            identifier(x)
        sequence(self.purposes, unique=True)
        for x in self.purposes:
            enum(x, ("store", "research", "ai", "report"))
        stamp(self, "valid_from", "valid_to")
        if self.valid_from >= self.valid_to:
            raise ContractError()
        if self.revoked_at is not None:
            stamp(self, "revoked_at")

    def allows(self, *, at, purpose, source_id, dataset_id, dataset_version):
        enum(purpose, ("store", "research", "ai", "report"))
        moment = utc_instant(at)
        return ((source_id, dataset_id, dataset_version) == (self.source_id, self.dataset_id, self.dataset_version)
                and purpose in self.purposes and self.valid_from <= moment < self.valid_to
                and (self.revoked_at is None or moment < self.revoked_at))


@dataclass(frozen=True, slots=True)
class RevisionConflict:
    keys: tuple[tuple[str, ...], ...]
    incoming: MarketItem
    counterpart: MarketItem
    kind: str
    detected_at: str

    def __post_init__(self):
        if (type(self.keys) is not tuple or not 1 <= len(self.keys) <= 2
                or type(self.incoming) is not MarketItem or type(self.counterpart) is not MarketItem):
            raise ContractError()
        for key in self.keys:
            sequence(key, maximum=6)
            if len(key) != 6:
                raise ContractError()
        enum(self.kind, ("revision", "observation_id"))
        stamp(self, "detected_at")
        if self.detected_at != max(self.incoming.observation.ingested_at, self.counterpart.observation.ingested_at):
            raise ContractError()


def _evidence_order(item):
    o = item.observation
    return (o.ingested_at, o.observed_at, o.observation_id, item.revision.key, record_hash(item.revision), record_hash(o))


def _fact_key(item):
    return item.revision.key + (record_hash(item.revision),)


@dataclass(frozen=True, slots=True)
class RevisionState:
    items: tuple[MarketItem, ...] = ()
    conflicts: tuple[RevisionConflict, ...] = ()
    evidence: tuple[MarketItem, ...] = ()

    def __post_init__(self):
        sequence(self.items, MarketItem)
        sequence(self.conflicts, RevisionConflict)
        sequence(self.evidence, MarketItem)
        if not self.evidence:
            object.__setattr__(self, "evidence", self.items)
        if any(x not in self.evidence for x in self.items):
            raise ContractError()
        ids = [x.observation.observation_id for x in self.items]
        if len(set(ids)) != len(ids):
            raise ContractError()
        facts = {}
        for item in self.items:
            hashed = record_hash(item.revision)
            if facts.setdefault(item.revision.key, hashed) != hashed:
                raise ContractError()
        for conflict in self.conflicts:
            if conflict.incoming not in self.evidence or conflict.counterpart not in self.evidence:
                raise ContractError()


def _rebuild_revision_state(evidence):
    # Canonical ordering makes representatives and conflict instants independent of arrival order.
    ordered = tuple(sorted(set(evidence), key=_evidence_order))
    sequence(ordered, MarketItem)
    facts, observations, accepted, conflicts = {}, {}, [], []
    for item in ordered:
        facts.setdefault(_fact_key(item), item)  # earliest available observation for each normalized fact
    representatives = tuple(facts.values())
    for index, left in enumerate(representatives):
        for right in representatives[index + 1:]:
            if left.revision.key == right.revision.key:
                conflicts.append(RevisionConflict((left.revision.key,), right, left, "revision",
                    max(left.observation.ingested_at, right.observation.ingested_at)))
    for item in ordered:
        observations.setdefault(item.observation.observation_id, []).append(item)
    for group in observations.values():
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                conflicts.append(RevisionConflict(tuple(sorted({left.revision.key, right.revision.key})),
                    right, left, "observation_id", max(left.observation.ingested_at, right.observation.ingested_at)))
    accepted_facts, accepted_ids = {}, set()
    for item in ordered:
        hashed = record_hash(item.revision)
        if (accepted_facts.setdefault(item.revision.key, hashed) == hashed
                and item.observation.observation_id not in accepted_ids):
            accepted.append(item)
            accepted_ids.add(item.observation.observation_id)
    return RevisionState(tuple(accepted), tuple(conflicts), ordered)


def merge_revision(state, item):
    """모든 양쪽 근거를 보존하고, 더 이른 재관측 합류 시 충돌 시각도 재계산한다."""
    if type(state) is not RevisionState or type(item) is not MarketItem:
        raise ContractError()
    if item in state.evidence:
        return state, "duplicate"
    conflict = any((old.revision.key == item.revision.key and _fact_key(old) != _fact_key(item))
                   or old.observation.observation_id == item.observation.observation_id for old in state.evidence)
    rebuilt = _rebuild_revision_state(state.evidence + (item,))
    return rebuilt, "conflict" if conflict else "accepted"


@dataclass(frozen=True, slots=True)
class RawMarketView:
    mode: str
    as_of: str
    knowledge_cutoff: str
    selected: tuple[MarketItem, ...]
    held_reasons: tuple[str, ...]

    @property
    def context_validated(self):
        return False

    def __post_init__(self):
        enum(self.mode, ("as_known", "restated"))
        stamp(self, "as_of", "knowledge_cutoff")
        sequence(self.selected, MarketItem)
        sequence(self.held_reasons, unique=True)


def _payload_identity(payload):
    if type(payload) is PriceBar:
        return (type(payload), payload.instrument_id, payload.listing_venue_id, payload.execution_venue_id,
                payload.starts_at, payload.ends_at, payload.open.currency, payload.open.quantity_unit,
                payload.adjustment, payload.adjustment_details)
    if type(payload) is FXObservation:
        return (type(payload), payload.fx.base_currency, payload.fx.quote_currency)
    if type(payload) is CorporateAction:
        return (type(payload), payload.instrument_id, payload.listing_venue_id, payload.execution_venue_id,
                payload.quantity_unit, payload.action_kind, payload.effective_date)
    return (type(payload),)


def select_raw_view(state, *, as_of, knowledge_cutoff, rights, at, dataset_version,
                mode="as_known", original_cutoff=None, purpose="research"):
    """원시 PIT 선택만 한다. Q16 context 미검증이며 사용 view는 application 진입점이다."""
    if type(state) is not RevisionState or type(rights) is not RightsGrant:
        raise ContractError()
    enum(mode, ("as_known", "restated"))
    effective, cutoff, now = utc_instant(as_of), utc_instant(knowledge_cutoff), utc_instant(at)
    if cutoff > now or (mode == "restated" and
                       (original_cutoff is None or utc_instant(original_cutoff) >= cutoff)):
        raise ContractError()
    groups, held, selected = {}, set(), []
    for item in state.evidence:
        r, o = item.revision, item.observation
        if not rights.allows(at=now, purpose=purpose, source_id=r.source_id,
                             dataset_id=r.dataset_id, dataset_version=dataset_version) or o.rights_ref != rights.rights_ref:
            held.add("rights_blocked")
            continue
        if r.effective_at > effective or o.observed_at > cutoff or o.ingested_at > cutoff:
            continue
        if r.published_at is None:
            held.add("publication_unknown")
            continue
        if r.published_at > cutoff:
            continue
        bucket = groups.setdefault(r.identity, {})
        prior = bucket.get(r.revision_id)
        if prior is None or (o.ingested_at, o.observed_at, o.observation_id) < (
                prior.observation.ingested_at, prior.observation.observed_at, prior.observation.observation_id):
            bucket[r.revision_id] = item
    for identity, revisions in groups.items():
        if any(c.detected_at <= cutoff and any(key[:5] == identity for key in c.keys) for c in state.conflicts):
            held.add("revision_conflict")
            continue
        roots = [x for x in revisions.values() if x.revision.revision_kind == "original"]
        children = {}
        for item in revisions.values():
            predecessor = item.revision.predecessor_revision_id
            if predecessor is not None:
                children.setdefault(predecessor, []).append(item)
        if len(roots) != 1 or any(k not in revisions for k in children) or any(len(v) != 1 for v in children.values()):
            held.add("chain_missing_or_fork")
            continue
        node, seen, invalid = roots[0], set(), False
        while True:
            r = node.revision
            if r.revision_id in seen:
                invalid = True
                break
            seen.add(r.revision_id)
            successors = children.get(r.revision_id, ())
            if not successors:
                break
            child = successors[0]
            a, b = r.payload, child.revision.payload
            if (r.revision_kind in ("retraction", "unsupported") or child.revision.effective_at != r.effective_at
                    or child.revision.published_at < r.published_at
                    or (b is not None and _payload_identity(a) != _payload_identity(b))):
                invalid = True
                break
            node = child
        if invalid or len(seen) != len(revisions):
            held.add("chain_invalid")
        elif node.revision.revision_kind in ("retraction", "unsupported"):
            held.add(node.revision.revision_kind)
        else:
            selected.append(node)
    usable = []
    for node in selected:
        if not adjustment_verified(node, selected, as_of=effective, knowledge_cutoff=cutoff):
            held.add("adjustment_unverified")
        else:
            usable.append(node)
    return RawMarketView(mode, effective, cutoff, tuple(sorted(usable, key=lambda x: x.revision.key)), tuple(sorted(held)))


def adjustment_verified(node, candidates, *, as_of, knowledge_cutoff):
    """조정 시점의 정확 action identity/단위/venue/가용성에 결속한다."""
    payload = node.revision.payload
    if type(payload) is not PriceBar or payload.adjustment_details is None:
        return True
    details = payload.adjustment_details
    if details.basis_at > utc_instant(as_of) or details.knowledge_at > utc_instant(knowledge_cutoff):
        return False
    for ref in details.action_refs:
        matches = [x for x in candidates if x.revision.key == ref.key and record_hash(x.revision) == ref.revision_hash]
        if len(matches) != 1:
            return False
        action = matches[0]
        r, o, p = action.revision, action.observation, action.revision.payload
        if (type(p) is not CorporateAction
                or (r.environment, r.source_id, r.dataset_id, p.instrument_id, p.listing_venue_id,
                    p.execution_venue_id, p.quantity_unit) !=
                   (node.revision.environment, node.revision.source_id, node.revision.dataset_id,
                    payload.instrument_id, payload.listing_venue_id, payload.execution_venue_id, payload.open.quantity_unit)
                or r.published_at is None or r.published_at > details.knowledge_at
                or o.observed_at > details.knowledge_at or o.ingested_at > details.knowledge_at
                or r.effective_at > details.basis_at):
            return False
    return True


def validate_market_context(item, catalog, calendar, timezone, *, knowledge_cutoff):
    """Q16 timezone-bound calendar adapter를 전달받는다. 알 수 없으면 보류한다."""
    from .catalog import Catalog
    from .calendar import MarketCalendar
    if type(item) is not MarketItem or type(catalog) is not Catalog or type(calendar) is not MarketCalendar:
        raise ContractError()
    p, o = item.revision.payload, item.observation
    if (catalog.catalog_version != o.catalog_version or calendar.calendar_version != o.calendar_version):
        return "context_version_mismatch"
    if type(p) is FXObservation or p is None:
        return None
    resolution = catalog.resolve(item.revision.source_id, p.source_code, p.listing_venue_id,
                                 p.execution_venue_id, as_of=item.revision.effective_at,
                                 knowledge_cutoff=knowledge_cutoff)
    if (resolution is None or not resolution.eligible_for_initial_scope
            or resolution.instrument.instrument_id != p.instrument_id):
        return "catalog_unknown_or_ineligible"
    if calendar.venue_id != p.execution_venue_id:
        return "calendar_venue_mismatch"
    if type(p) is CorporateAction:
        if p.cash_per_unit is not None and p.cash_per_unit.currency != resolution.instrument.currency:
            return "currency_mismatch"
        timezone.validate_calendar(calendar)
        local = timezone.to_local(item.revision.effective_at, knowledge_cutoff=knowledge_cutoff)
        if local.date().isoformat() != p.effective_date:
            return "action_effective_date_mismatch"
        return None  # action date is not assumed to be a trading session.
    if p.open.currency != resolution.instrument.currency:
        return "currency_mismatch"
    first = timezone.lookup_calendar(calendar, p.starts_at, knowledge_cutoff=knowledge_cutoff)
    last = timezone.lookup_calendar(calendar, datetime.fromisoformat(p.ends_at) - timedelta(microseconds=1),
                                    knowledge_cutoff=knowledge_cutoff)
    if (not first.regular_session_eligible or not last.regular_session_eligible
            or first.session.session_id != last.session.session_id):
        return "calendar_unknown_or_nonregular"
    return None


@dataclass(frozen=True, slots=True)
class ExpectedEvent:
    series_id: str
    event_id: str
    effective_at: str

    def __post_init__(self):
        identifier(self.series_id)
        identifier(self.event_id)
        stamp(self, "effective_at")


@dataclass(frozen=True, slots=True)
class QueryScope:
    series_ids: tuple[str, ...]
    starts_at: str
    ends_at: str
    expected: tuple[ExpectedEvent, ...]
    coverage_kind: str
    coverage_ref: str

    def __post_init__(self):
        sequence(self.series_ids, unique=True)
        sequence(self.expected, ExpectedEvent)
        identifier(self.coverage_ref)
        stamp(self, "starts_at", "ends_at")
        enum(self.coverage_kind, ("expected_records", "explicit_closed", "confirmed_empty", "unknown"))
        if not self.series_ids or self.starts_at >= self.ends_at:
            raise ContractError()
        keys = [(x.series_id, x.event_id) for x in self.expected]
        if (len(set(keys)) != len(keys) or any(x.series_id not in self.series_ids or
                not self.starts_at <= x.effective_at < self.ends_at for x in self.expected)
                or (self.coverage_kind == "expected_records" and not self.expected)
                or (self.coverage_kind != "expected_records" and self.expected)):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class FetchRequest:
    request_id: str
    environment: str
    source_id: str
    dataset_id: str
    dataset_version: str
    scope: QueryScope
    started_at: str
    deadline: str
    knowledge_cutoff: str

    def __post_init__(self):
        enum(self.environment, ("synthetic",))
        for x in (self.request_id, self.source_id, self.dataset_id, self.dataset_version):
            identifier(x)
        stamp(self, "started_at", "deadline", "knowledge_cutoff")
        if (type(self.scope) is not QueryScope or self.started_at >= self.deadline
                or self.knowledge_cutoff > self.deadline):
            raise ContractError()


@dataclass(frozen=True, slots=True)
class IngestLimits:
    max_pages: int = 8
    max_bytes: int = 65536
    max_records: int = 64
    max_age_seconds: int | None = None
    policy_ref: str = "synthetic.unknown-freshness"

    def __post_init__(self):
        for value, maximum in ((self.max_pages, 16), (self.max_bytes, 1048576), (self.max_records, MAX_RECORDS)):
            count(value, maximum)
            if value == 0:
                raise ContractError()
        if self.max_age_seconds is not None:
            count(self.max_age_seconds, 31536000)
        identifier(self.policy_ref)


@dataclass(frozen=True, slots=True)
class PageResult:
    request_id: str
    scope: QueryScope
    cursor_in: str | None
    cursor_out: str | None
    terminal: bool
    status: str
    items: tuple[MarketItem, ...]
    response_bytes: bytes
    source_snapshot: str | None
    received_at: str
    error_reason: str | None
    not_before: str | None

    def __post_init__(self):
        page_facts(self)


@dataclass(frozen=True, slots=True)
class PageFacts:
    request_id: str
    scope: QueryScope
    cursor_in: str | None
    cursor_out: str | None
    terminal: bool
    status: str
    items: tuple[MarketItem, ...]
    response_size_bytes: int
    response_sha256: str
    source_snapshot: str | None
    received_at: str
    error_reason: str | None
    not_before: str | None

    def __post_init__(self):
        identifier(self.request_id)
        if type(self.scope) is not QueryScope or type(self.terminal) is not bool:
            raise ContractError()
        for x in (self.cursor_in, self.cursor_out, self.source_snapshot):
            if x is not None:
                identifier(x)
        enum(self.status, ("success", "failed", "rate_limited", "normalization_failed"))
        sequence(self.items, MarketItem)
        count(self.response_size_bytes)
        digest(self.response_sha256)
        stamp(self, "received_at")
        if self.status == "success":
            if self.error_reason is not None or self.not_before is not None or self.terminal != (self.cursor_out is None):
                raise ContractError()
        else:
            identifier(self.error_reason)
            if self.terminal or self.cursor_out is not None:
                raise ContractError()
        if self.status == "rate_limited":
            if self.not_before is None:
                raise ContractError()
            stamp(self, "not_before")
            if self.not_before < self.received_at:
                raise ContractError()
        elif self.not_before is not None:
            raise ContractError()


def page_facts(page):
    from hashlib import sha256
    if type(page) is not PageResult or type(page.response_bytes) is not bytes or len(page.response_bytes) > 1048576:
        raise ContractError()
    return PageFacts(page.request_id, page.scope, page.cursor_in, page.cursor_out, page.terminal, page.status,
                     page.items, len(page.response_bytes), sha256(page.response_bytes).hexdigest(), page.source_snapshot,
                     page.received_at, page.error_reason, page.not_before)


@dataclass(frozen=True, slots=True)
class IngestState:
    revisions: RevisionState = RevisionState()
    pages: int = 0
    bytes_received: int = 0
    records_received: int = 0
    next_cursor: str | None = None
    seen_cursors: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    terminal: bool = False
    snapshots: tuple[str, ...] = ()
    snapshot_missing: bool = False
    not_before: str | None = None
    last_received_at: str | None = None

    def __post_init__(self):
        if type(self.revisions) is not RevisionState:
            raise ContractError()
        count(self.pages, 16)
        count(self.bytes_received)
        count(self.records_received, MAX_RECORDS)
        sequence(self.seen_cursors, maximum=16, unique=True)
        sequence(self.errors, unique=True)
        sequence(self.snapshots, maximum=16, unique=True)
        if type(self.terminal) is not bool or type(self.snapshot_missing) is not bool:
            raise ContractError()
        if self.next_cursor is not None:
            identifier(self.next_cursor)
        if self.not_before is not None:
            stamp(self, "not_before")
        if self.last_received_at is not None:
            stamp(self, "last_received_at")

    @property
    def snapshot_consistency(self):
        if self.snapshot_missing or not self.snapshots:
            return "unknown"
        return "consistent" if len(self.snapshots) == 1 else "mixed"


def fail_ingest(state, reason, *, not_before=None):
    from dataclasses import replace
    identifier(reason)
    return replace(state, errors=tuple(sorted(set(state.errors + (reason,)))), not_before=not_before)


def reduce_page(state, request, page, limits, *, evaluated_at):
    """실제 bytes 경로도 저장 receipt 경로와 같은 사실 reducer를 사용한다."""
    return reduce_page_facts(state, request, page_facts(page), limits, evaluated_at=evaluated_at)


def reduce_page_facts(state, request, page, limits, *, evaluated_at):
    """길이/hash 사실 기반 bounded core. 재생에 가짜 response bytes를 만들지 않는다."""
    from dataclasses import replace
    from .serialization import CanonicalPayload, canonical_bytes
    if any(type(value) is not expected for value, expected in
           ((state, IngestState), (request, FetchRequest), (page, PageFacts), (limits, IngestLimits))):
        raise ContractError()
    if state.errors or state.terminal:
        return fail_ingest(state, "already_stopped")
    if state.pages >= limits.max_pages:
        return fail_ingest(state, "page_limit")
    if page.request_id != request.request_id or page.scope != request.scope or page.cursor_in != state.next_cursor:
        return fail_ingest(state, "scope_or_cursor_mismatch")
    if not request.started_at <= page.received_at <= request.deadline:
        return fail_ingest(state, "deadline_or_clock")
    if (page.received_at > utc_instant(evaluated_at)
            or (state.last_received_at is not None and page.received_at < state.last_received_at)):
        return fail_ingest(state, "page_clock_invalid")
    if page.cursor_out is not None and (page.cursor_out == page.cursor_in or page.cursor_out in state.seen_cursors):
        return fail_ingest(state, "repeated_cursor")
    # Account both source bytes and validated representation, never trust a claimed byte count.
    normalized_size = sum(len(canonical_bytes(CanonicalPayload("MarketRevision", 1, "synthetic", x.revision))) +
                          len(canonical_bytes(CanonicalPayload("MarketObservation", 1, "synthetic", x.observation)))
                          for x in page.items)
    size = max(page.response_size_bytes, normalized_size)
    if state.bytes_received + size > limits.max_bytes:
        return fail_ingest(state, "byte_limit")
    if state.records_received + len(page.items) > limits.max_records:
        return fail_ingest(state, "record_limit")
    revisions, errors = state.revisions, set(state.errors)
    for item in page.items:
        r, o = item.revision, item.observation
        if ((r.source_id, r.dataset_id) != (request.source_id, request.dataset_id)
                or r.series_id not in request.scope.series_ids
                or not request.scope.starts_at <= r.effective_at < request.scope.ends_at
                or o.ingested_at > page.received_at):
            return fail_ingest(state, "record_scope_or_future")
    for item in page.items:
        revisions, result = merge_revision(revisions, item)
        if result == "conflict":
            errors.add("revision_conflict")
    result = replace(state, revisions=revisions, pages=state.pages + 1,
                     bytes_received=state.bytes_received + size, records_received=state.records_received + len(page.items),
                     next_cursor=page.cursor_out, seen_cursors=state.seen_cursors +
                     (() if page.cursor_out is None else (page.cursor_out,)),
                     errors=tuple(sorted(errors)), terminal=page.terminal,
                     snapshots=tuple(sorted(set(state.snapshots + (() if page.source_snapshot is None else (page.source_snapshot,))))),
                     snapshot_missing=state.snapshot_missing or page.source_snapshot is None,
                     last_received_at=page.received_at)
    if page.status != "success":
        return fail_ingest(result, page.status, not_before=page.not_before)
    return result


def assess_quality(state, request, limits, *, evaluated_at, rights_allowed):
    now = utc_instant(evaluated_at)
    if now < request.started_at or type(rights_allowed) is not bool:
        raise ContractError()
    found = {(x.revision.series_id, x.revision.event_id, x.revision.effective_at) for x in state.revisions.items}
    missing = tuple(sorted(f"{x.series_id}:{x.event_id}" for x in request.scope.expected
                           if (x.series_id, x.event_id, x.effective_at) not in found))
    reasons = set(state.errors)
    if not state.terminal:
        reasons.add("not_terminal")
    if request.scope.coverage_kind == "unknown":
        reasons.add("coverage_unknown")
    if request.scope.coverage_kind in ("explicit_closed", "confirmed_empty") and state.revisions.items:
        reasons.add("empty_coverage_conflict")
    if missing:
        reasons.add("missing_expected")
    if not rights_allowed:
        reasons.add("rights_blocked")
    freshness = "unknown"
    if limits.max_age_seconds is not None:
        per_series = []
        for series in request.scope.series_ids:
            moments = [x.revision.effective_at for x in state.revisions.items if x.revision.series_id == series]
            if not moments:
                per_series.append("unknown")
                continue
            latest = max(moments)
            if latest > now:
                reasons.add("future_effective")
                per_series.append("unknown")
            else:
                age = datetime.fromisoformat(now) - datetime.fromisoformat(latest)
                per_series.append("fresh" if age <= timedelta(seconds=limits.max_age_seconds) else "stale")
        freshness = "stale" if "stale" in per_series else ("unknown" if "unknown" in per_series else "fresh")
    if not reasons:
        status = "complete"
    elif "revision_conflict" in reasons or "empty_coverage_conflict" in reasons:
        status = "invalid"
    else:
        status = "partial" if state.revisions.items else "unavailable"
    return QualityResult(status, missing, tuple(sorted(reasons)), freshness, now, limits.policy_ref, rights_allowed)
