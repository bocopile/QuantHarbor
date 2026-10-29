"""Q18 bounded canonical JSON store. Standard library only; private synthetic files."""
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import os
import re
import stat

from quantharbor.application.document_ingest import validate_bundle
from quantharbor.domain.documents import (
    MAX_BATCH_BYTES, DocumentBatchManifest, DocumentBundle, DocumentClaim, DocumentEntityContext,
    DocumentLimits, DocumentObservation, DocumentOriginal, DocumentRevision, document_files,
    encoded, required_purposes, select_view,
)
from quantharbor.domain.market_data import RightsGrant, record_hash
from quantharbor.domain.primitives import ContractError, identifier, utc_instant
from quantharbor.domain.serialization import parse_payload


_TYPES = {x.__name__:x for x in (DocumentBatchManifest, DocumentEntityContext, DocumentObservation,
                               DocumentOriginal, DocumentRevision)}


def _private_directory(fd):
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ContractError()


def _regular(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1 or not 0 <= info.st_size <= 65536):
        raise ContractError()


def _file(fd, name):
    return os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)


def _metadata(fd, name, length):
    child = _file(fd, name)
    try:
        info = os.fstat(child)
        _regular(info)
        if info.st_size != length:
            raise ContractError()
    finally:
        os.close(child)


def _read(fd, name, length=None):
    child = _file(fd, name)
    try:
        before = os.fstat(child)
        _regular(before)
        if length is not None and before.st_size != length:
            raise ContractError()
        with os.fdopen(os.dup(child), "rb") as stream:
            raw = stream.read(65537)
        after = os.fstat(child)
        _regular(after)
        if (len(raw) != before.st_size or len(raw) > 65536 or
            (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
            (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ContractError()
        return raw
    finally:
        os.close(child)


def _write(fd, name, raw):
    if type(raw) is not bytes or len(raw) > 65536:
        raise ContractError()
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


def _parse(raw, schema_name, expected_hash=None):
    value = parse_payload(raw)
    if (value.schema_name != schema_name or type(value.payload) is not _TYPES[schema_name]
            or encoded(value.payload) != raw
            or (expected_hash is not None and record_hash(value.payload) != expected_hash)):
        raise ContractError()
    return value.payload


def _version(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ContractError()
    return value


@dataclass(frozen=True, slots=True)
class DocumentReadResult:
    bundle: DocumentBundle
    view: object


class DocumentFileStore:
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
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=fd)
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

    def _rights(self, rights, version, at, purpose):
        _private_directory(self._root_fd)
        if (type(rights) is not RightsGrant or not rights.allows(at=at, purpose=purpose, source_id=self.source_id,
                                                               dataset_id=self.dataset_id, dataset_version=version)):
            raise ContractError()

    @contextmanager
    def _writer_lock(self):
        fd = os.open("document-writer.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     0o600, dir_fd=self._root_fd)
        try:
            _regular(os.fstat(fd))
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)  # Persistent lock inode; never unlink it to recover a stale lock.

    def _directory(self, version):
        fd = os.open(_version(version), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                     dir_fd=self._root_fd)
        try:
            _private_directory(fd)
        except Exception:
            os.close(fd)
            raise
        return fd

    def _publish_manifest(self, fd, manifest):
        _write(fd, "manifest-pending.json", encoded(manifest))
        os.link("manifest-pending.json", "manifest.json", src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        os.unlink("manifest-pending.json", dir_fd=fd)
        os.fsync(fd)

    def write(self, bundle, *, rights, at, catalog):
        try:
            if type(bundle) is not DocumentBundle:
                raise ContractError()
            manifest, now = bundle.manifest, utc_instant(at)
            version = _version(manifest.dataset_version)
            self._rights(rights, version, now, "store")
            if ((manifest.source_id, manifest.dataset_id) != (self.source_id, self.dataset_id) or manifest.created_at > now):
                raise ContractError()
            checked = validate_bundle(bundle, catalog=catalog, rights=rights, at=now)
            payloads = tuple((ref, encoded(value)) for ref,value in document_files(checked.originals, checked.claims, checked.context))
            if sum(len(raw) for _,raw in payloads) + len(encoded(manifest)) > min(manifest.limits.max_bytes, MAX_BATCH_BYTES):
                raise ContractError()
            with self._writer_lock():
                os.mkdir(version, 0o700, dir_fd=self._root_fd)
                os.fsync(self._root_fd)
                fd = self._directory(version)
                try:
                    for ref, raw in payloads:
                        _write(fd, ref.basename, raw)
                    os.fsync(fd)
                    self._publish_manifest(fd, manifest)
                finally:
                    os.close(fd)
            return manifest
        except Exception:
            raise ContractError() from None

    def read(self, version, *, rights, at, catalog, knowledge_cutoff, purpose="research", use="entity_research",
             mode="as_known", original_cutoff=None, entity_id=None, instrument_id=None, listing_venue_id=None, limits=None):
        try:
            version, now = _version(version), utc_instant(at)
            # Both requested purpose and research-use authority precede every file open.
            for required in required_purposes(purpose, use):
                self._rights(rights, version, now, required)
            fd = self._directory(version)
            try:
                raw_manifest = _read(fd, "manifest.json")
                manifest = _parse(raw_manifest, "DocumentBatchManifest")
                if ((manifest.source_id, manifest.dataset_id, manifest.dataset_version) !=
                        (self.source_id, self.dataset_id, version) or manifest.created_at > now
                        or sum(x.byte_length for x in manifest.file_refs) + len(raw_manifest) > min(manifest.limits.max_bytes, MAX_BATCH_BYTES)):
                    raise ContractError()
                # All listed file types, sizes and ownership are checked before reading text bodies.
                for ref in manifest.file_refs:
                    _metadata(fd, ref.basename, ref.byte_length)
                decoded = {}
                order = {"DocumentObservation":0, "DocumentRevision":1, "DocumentEntityContext":2, "DocumentOriginal":3}
                for ref in sorted(manifest.file_refs, key=lambda x:order[x.schema_name]):
                    value = _parse(_read(fd, ref.basename, ref.byte_length), ref.schema_name, ref.canonical_hash)
                    if type(value) is DocumentObservation and value.rights_ref != rights.rights_ref:
                        raise ContractError()
                    decoded[ref.canonical_hash] = value
                claims = []
                for ref in manifest.claims:
                    r, o = decoded[ref.revision_hash], decoded[ref.observation_hash]
                    claims.append(DocumentClaim(r, o))
                originals = tuple(x for x in decoded.values() if type(x) is DocumentOriginal)
                context = decoded[manifest.context_hash]
                bundle = DocumentBundle(manifest, originals, tuple(claims), context)
                bundle = validate_bundle(bundle, catalog=catalog, rights=rights, at=now, purpose=purpose)
            finally:
                os.close(fd)
            view = select_view(bundle, catalog=catalog, rights=rights, evaluated_at=now, knowledge_cutoff=knowledge_cutoff,
                purpose=purpose, use=use, mode=mode, original_cutoff=original_cutoff, entity_id=entity_id,
                instrument_id=instrument_id, listing_venue_id=listing_venue_id, limits=limits)
            return DocumentReadResult(bundle, view)
        except Exception:
            raise ContractError() from None
