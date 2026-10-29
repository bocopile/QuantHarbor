"""Q17B private immutable Parquet store. PyArrow is loaded only in storage runtime."""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import fcntl
from hashlib import sha256
from io import BytesIO
import os
import re
import stat

from quantharbor.application.market_ingest import replay_storage, select_view
from quantharbor.domain.market_data import (
    CorporateAction, FXObservation, IngestLimits, PriceBar, RightsGrant, assess_quality, fail_ingest, record_hash,
)
from quantharbor.domain.market_storage import (
    CANONICAL_VERSION, MAX_BUNDLE_BYTES, MAX_FILE_BYTES, REDUCER_VERSION, STORAGE_VERSION,
    FileRef, MarketIngestDescriptor, MarketPageReceipt, MarketStorageManifest, StorageBundle,
    claim_ref, evidence_index, summary_for,
)
from quantharbor.domain.primitives import ContractError, identifier, utc_instant
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload


_DECIMALS = ("open", "high", "low", "close", "volume", "fx_rate", "split_numerator", "split_denominator", "cash_per_unit")
_STRINGS = ("instrument_id", "listing_venue_id", "execution_venue_id", "currency", "quantity_unit",
            "base_currency", "quote_currency", "adjustment")
_TIMES = ("effective_at", "published_at", "observed_at", "ingested_at")


def _schema():
    import pyarrow as pa
    if pa.__version__ != "26.0.0":
        raise ContractError()
    return pa.schema([
        pa.field("revision_bytes", pa.binary(), nullable=False),
        pa.field("observation_bytes", pa.binary(), nullable=False),
        pa.field("revision_hash", pa.string(), nullable=False),
        pa.field("observation_hash", pa.string(), nullable=False),
        pa.field("payload_kind", pa.string(), nullable=False),
        *(pa.field(x, pa.timestamp("us", tz="UTC"), nullable=x == "published_at") for x in _TIMES),
        *(pa.field(x, pa.decimal128(38, 18), nullable=True) for x in _DECIMALS),
        *(pa.field(x, pa.string(), nullable=True) for x in _STRINGS),
    ], metadata={b"quantharbor.storage": STORAGE_VERSION.encode()})


def _row(item):
    r, o, p = item.revision, item.observation, item.revision.payload
    ref = claim_ref(item)
    row = {name: None for name in _DECIMALS + _STRINGS}
    row.update(revision_bytes=canonical_bytes(CanonicalPayload("MarketRevision", 1, "synthetic", r)),
               observation_bytes=canonical_bytes(CanonicalPayload("MarketObservation", 1, "synthetic", o)),
               revision_hash=ref.revision_hash, observation_hash=ref.observation_hash,
               payload_kind="none" if p is None else type(p).__name__)
    for name in _TIMES:
        value = getattr(r if name in ("effective_at", "published_at") else o, name)
        row[name] = None if value is None else datetime.fromisoformat(value)
    if type(p) is PriceBar:
        for name in ("open", "high", "low", "close"):
            row[name] = Decimal(getattr(p, name).amount)
        row.update(volume=None if p.volume is None else Decimal(p.volume.amount), instrument_id=p.instrument_id,
                   listing_venue_id=p.listing_venue_id, execution_venue_id=p.execution_venue_id,
                   currency=p.open.currency, quantity_unit=p.open.quantity_unit, adjustment=p.adjustment)
    elif type(p) is FXObservation:
        row.update(fx_rate=Decimal(p.fx.rate), base_currency=p.fx.base_currency, quote_currency=p.fx.quote_currency)
    elif type(p) is CorporateAction:
        row.update(instrument_id=p.instrument_id, listing_venue_id=p.listing_venue_id,
                   execution_venue_id=p.execution_venue_id, quantity_unit=p.quantity_unit,
                   split_numerator=None if p.numerator is None else Decimal(p.numerator),
                   split_denominator=None if p.denominator is None else Decimal(p.denominator),
                   cash_per_unit=None if p.cash_per_unit is None else Decimal(p.cash_per_unit.amount),
                   currency=None if p.cash_per_unit is None else p.cash_per_unit.currency)
    return row


def _parquet_bytes(items):
    import pyarrow as pa
    import pyarrow.parquet as pq
    table = pa.Table.from_pylist([_row(x) for x in items], schema=_schema())
    table.validate(full=True)
    output = BytesIO()
    pq.write_table(table, output, compression="NONE", version="2.6", use_dictionary=False,
                   row_group_size=16, allow_truncated_timestamps=False, write_page_checksum=True)
    raw = output.getvalue()
    if len(raw) > MAX_FILE_BYTES:
        raise ContractError()
    return raw


def _decode_parquet(raw, expected_rows):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from quantharbor.domain.market_data import MarketItem
    if type(raw) is not bytes or len(raw) > MAX_FILE_BYTES or not 1 <= expected_rows <= 32:
        raise ContractError()
    with pq.ParquetFile(BytesIO(raw), pre_buffer=False, arrow_extensions_enabled=False,
            page_checksum_verification=True, thrift_string_size_limit=65536,
            thrift_container_size_limit=4096, schema_depth_limit=4) as file:
        metadata = file.metadata
        if (metadata.num_rows != expected_rows or not 1 <= metadata.num_row_groups <= 2
                or metadata.num_columns != len(_schema())
                or not file.schema_arrow.equals(_schema(), check_metadata=True)):
            raise ContractError()
        uncompressed = 0
        for index in range(metadata.num_row_groups):
            group = metadata.row_group(index)
            if group.num_rows > 16 or group.total_byte_size > MAX_FILE_BYTES:
                raise ContractError()
            for column_index in range(metadata.num_columns):
                column = group.column(column_index)
                if column.compression != "UNCOMPRESSED" or not 0 <= column.total_uncompressed_size <= MAX_FILE_BYTES:
                    raise ContractError()
                uncompressed += column.total_uncompressed_size
        if uncompressed > MAX_FILE_BYTES * 2:
            raise ContractError()
        props = metadata.metadata or {}
        if (set(props) != {b"ARROW:schema", b"quantharbor.storage"}
                or sum(len(k) + len(v) for k, v in props.items()) > 65536):
            raise ContractError()
        items = []
        for batch in file.iter_batches(batch_size=16, use_threads=False):
            batch.validate(full=True)
            for row in batch.to_pylist():
                rb, ob = row["revision_bytes"], row["observation_bytes"]
                if len(rb) > 65536 or len(ob) > 65536:
                    raise ContractError()
                revision, observation = parse_payload(rb), parse_payload(ob)
                if revision.schema_name != "MarketRevision" or observation.schema_name != "MarketObservation":
                    raise ContractError()
                item = MarketItem(revision.payload, observation.payload)
                if row != _row(item):
                    raise ContractError()
                if any(row[x] is not None and type(row[x]) is not Decimal for x in _DECIMALS):
                    raise ContractError()
                items.append(item)
                if len(items) > 32:
                    raise ContractError()
        if len(items) != expected_rows:
            raise ContractError()
        return tuple(items)


def _version(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ContractError()
    return value


def _private_directory(fd):
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ContractError()


def _regular(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1):
        raise ContractError()


def _read(fd, name, limit):
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = os.fstat(child)
        _regular(before)
        if before.st_size > limit:
            raise ContractError()
        with os.fdopen(os.dup(child), "rb") as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(child)
        _regular(after)
        if (len(raw) > limit or len(raw) != before.st_size or
            (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ContractError()
        return raw
    finally:
        os.close(child)


def _write(fd, name, raw):
    child = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd)
    try:
        _regular(os.fstat(child))
        with os.fdopen(os.dup(child), "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(child)
    if _read(fd, name, len(raw)) != raw:
        raise ContractError()


def _encoded(value):
    return canonical_bytes(CanonicalPayload(type(value).__name__, 1, "synthetic", value))


def _parsed(raw, expected):
    value = parse_payload(raw)
    if value.schema_name != expected.__name__ or type(value.payload) is not expected:
        raise ContractError()
    if _encoded(value.payload) != raw:
        raise ContractError()
    return value.payload


@dataclass(frozen=True, slots=True)
class StorageReadResult:
    manifest: MarketStorageManifest
    historical: StorageBundle
    current_view: object
    current_quality: object


class ParquetMarketStore:
    def __init__(self, root, *, source_id, dataset_id):
        self._root_fd = None
        try:
            identifier(source_id)
            identifier(dataset_id)
            path = os.fspath(root)
            if type(path) is not str or not path.startswith("/") or any(x in (".", "..") for x in path.split("/")):
                raise ContractError()
            fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            try:
                for part in (x for x in path.split("/") if x):
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                    os.close(fd)
                    fd = child
                _private_directory(fd)
                self._root_fd = fd
                fd = None
            finally:
                if fd is not None:
                    os.close(fd)
            self.source_id, self.dataset_id = source_id, dataset_id
        except Exception:
            self.close()
            raise ContractError() from None

    def close(self):
        if self._root_fd is not None:
            os.close(self._root_fd)
            self._root_fd = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def _writer_lock(self):
        fd = os.open("writer.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     0o600, dir_fd=self._root_fd)
        try:
            _regular(os.fstat(fd))
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)  # Persistent inode; never unlink a live/stale flock path.

    def _directory(self, version):
        _version(version)
        fd = os.open(version, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self._root_fd)
        try:
            _private_directory(fd)
        except Exception:
            os.close(fd)
            raise
        return fd

    def _rights(self, grant, version, at, purpose):
        _private_directory(self._root_fd)
        if (type(grant) is not RightsGrant or not grant.allows(at=at, purpose=purpose,
                source_id=self.source_id, dataset_id=self.dataset_id, dataset_version=version)):
            raise ContractError()

    def _publish_manifest(self, fd, manifest):
        raw = _encoded(manifest)
        _write(fd, "manifest-pending.json", raw)
        # link is an atomic no-overwrite publication; reader may fail closed during unlink.
        os.link("manifest-pending.json", "manifest.json", src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.unlink("manifest-pending.json", dir_fd=fd)
        os.fsync(fd)

    def write(self, bundle, *, rights, at, catalog, calendar, timezone, previous_version=None):
        try:
            return self._write_bundle(bundle, rights=rights, at=at, catalog=catalog, calendar=calendar,
                                      timezone=timezone, previous_version=previous_version)
        except Exception:
            raise ContractError() from None

    def _write_bundle(self, bundle, *, rights, at, catalog, calendar, timezone, previous_version):
        if type(bundle) is not StorageBundle:
            raise ContractError()
        descriptor, request = bundle.descriptor, bundle.descriptor.request
        version, now = _version(request.dataset_version), utc_instant(at)
        self._rights(rights, version, now, "store")
        if (request.source_id, request.dataset_id) != (self.source_id, self.dataset_id) or now < descriptor.evaluated_at:
            raise ContractError()
        if previous_version is not None:
            _version(previous_version)
            if previous_version == version:
                raise ContractError()
        state, envelope = replay_storage(descriptor, bundle.receipts, bundle.evidence,
                                          catalog=catalog, calendar=calendar, timezone=timezone)
        if (state != bundle.state or envelope != bundle.envelope or summary_for(state, envelope) != bundle.summary):
            raise ContractError()
        evidence = tuple(sorted(bundle.evidence, key=lambda x: claim_ref(x).key))
        payloads = [("descriptor", "descriptor.json", _encoded(descriptor), None)]
        payloads += [("receipt", f"receipt-{index:04d}.json", _encoded(receipt), None)
                     for index, receipt in enumerate(bundle.receipts, 1)]
        for index in range(0, len(evidence), 32):
            chunk = evidence[index:index + 32]
            raw = _parquet_bytes(chunk)
            if _decode_parquet(raw, len(chunk)) != chunk:
                raise ContractError()
            payloads.append(("evidence", f"evidence-{index // 32:04d}.parquet", raw, len(chunk)))
        if sum(len(x[2]) for x in payloads) > MAX_BUNDLE_BYTES:
            raise ContractError()
        refs = tuple(FileRef(role, name, len(raw), sha256(raw).hexdigest(), rows) for role, name, raw, rows in payloads)
        manifest = MarketStorageManifest(1, "synthetic", self.source_id, self.dataset_id, version, previous_version,
            now, STORAGE_VERSION, REDUCER_VERSION, CANONICAL_VERSION, refs[0], tuple(x for x in refs if x.role == "receipt"),
            tuple(x for x in refs if x.role == "evidence"), len(evidence), record_hash(evidence_index(evidence)),
            envelope.content_hash, bundle.summary)
        _encoded(manifest)  # Bound before any filesystem mutation.
        with self._writer_lock():
            if previous_version is not None:
                previous_fd = self._directory(previous_version)
                try:
                    prior = _parsed(_read(previous_fd, "manifest.json", 65536), MarketStorageManifest)
                    if ((prior.source_id, prior.dataset_id, prior.dataset_version) !=
                            (self.source_id, self.dataset_id, previous_version) or prior.created_at > now):
                        raise ContractError()
                finally:
                    os.close(previous_fd)
            os.mkdir(version, 0o700, dir_fd=self._root_fd)
            os.fsync(self._root_fd)
            fd = self._directory(version)
            try:
                for _, name, raw, _ in payloads:
                    _write(fd, name, raw)
                os.fsync(fd)
                self._publish_manifest(fd, manifest)
            finally:
                os.close(fd)
        return manifest

    def read(self, version, *, rights, at, limits, catalog, calendar, timezone, purpose="research",
             as_of=None, knowledge_cutoff=None, view_mode=None, original_cutoff=None):
        try:
            return self._read_bundle(version, rights=rights, at=at, limits=limits, catalog=catalog, calendar=calendar,
                timezone=timezone, purpose=purpose, as_of=as_of, knowledge_cutoff=knowledge_cutoff,
                view_mode=view_mode, original_cutoff=original_cutoff)
        except Exception:
            raise ContractError() from None

    def _read_bundle(self, version, *, rights, at, limits, catalog, calendar, timezone, purpose,
                     as_of, knowledge_cutoff, view_mode, original_cutoff):
        version, now = _version(version), utc_instant(at)
        self._rights(rights, version, now, purpose)  # Current authority before opening manifest/data.
        if type(limits) is not IngestLimits:
            raise ContractError()
        fd = self._directory(version)
        try:
            manifest = _parsed(_read(fd, "manifest.json", 65536), MarketStorageManifest)
            if ((manifest.source_id, manifest.dataset_id, manifest.dataset_version) !=
                    (self.source_id, self.dataset_id, version) or manifest.created_at > now):
                raise ContractError()
            refs = (manifest.descriptor_file,) + manifest.receipt_files + manifest.evidence_files
            raw_files = {}
            for ref in refs:
                raw = _read(fd, ref.name, min(ref.size_bytes, MAX_FILE_BYTES))
                if len(raw) != ref.size_bytes or sha256(raw).hexdigest() != ref.sha256:
                    raise ContractError()
                raw_files[ref.name] = raw
            descriptor = _parsed(raw_files[manifest.descriptor_file.name], MarketIngestDescriptor)
            request = descriptor.request
            if ((request.source_id, request.dataset_id, request.dataset_version) !=
                    (manifest.source_id, manifest.dataset_id, manifest.dataset_version)
                    or descriptor.evaluated_at > manifest.created_at):
                raise ContractError()
            receipts = tuple(_parsed(raw_files[x.name], MarketPageReceipt) for x in manifest.receipt_files)
            evidence = tuple(item for ref in manifest.evidence_files for item in _decode_parquet(raw_files[ref.name], ref.row_count))
            if len(evidence) != manifest.evidence_count or record_hash(evidence_index(evidence)) != manifest.evidence_index_hash:
                raise ContractError()
            state, envelope = replay_storage(descriptor, receipts, evidence, catalog=catalog, calendar=calendar, timezone=timezone)
            summary = summary_for(state, envelope)
            if summary != manifest.replay_summary or envelope.content_hash != manifest.accepted_record_set_hash:
                raise ContractError()
            bundle = StorageBundle(descriptor, receipts, evidence, state, envelope, summary)
        finally:
            os.close(fd)
        mode = descriptor.view_mode if view_mode is None else view_mode
        cutoff = request.knowledge_cutoff if knowledge_cutoff is None else knowledge_cutoff
        original = descriptor.original_cutoff if original_cutoff is None else original_cutoff
        view = select_view(state.revisions, as_of=descriptor.evaluated_at if as_of is None else as_of,
            knowledge_cutoff=cutoff, rights=rights, at=now, dataset_version=version, catalog=catalog,
            calendar=calendar, timezone=timezone, mode=mode, original_cutoff=original, purpose=purpose)
        current_state = state
        for reason in view.held_reasons:
            current_state = fail_ingest(current_state, reason, not_before=current_state.not_before)
        selected_events = {x.revision.identity for x in view.selected}
        if any(x.revision.identity not in selected_events for x in state.revisions.items):
            current_state = fail_ingest(current_state, "pit_not_usable", not_before=current_state.not_before)
        quality = assess_quality(current_state, request, limits, evaluated_at=now, rights_allowed=True)
        return StorageReadResult(manifest, bundle, view, quality)
