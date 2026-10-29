"""최대128개 합성 메모리 snapshot. 재시작 내구성·운영 DB 저장 증거는 아니다."""
from threading import RLock

from quantharbor.application.valuation import validate_predecessor
from quantharbor.domain.ledger import account, choice, hash_record, identifier, integer
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.valuation import PortfolioSnapshot


class SyntheticSnapshotRepository:
    def __init__(self, *, capacity=128):
        integer(capacity, 1, 128)
        self._capacity = capacity
        self._snapshots = {}
        self._lock = RLock()

    def get(self, snapshot_id, *, environment, account_ref):
        identifier(snapshot_id)
        choice(environment, ('synthetic',))
        account(account_ref)
        with self._lock:
            stored = self._snapshots.get(snapshot_id)
            if stored is None:
                return None
            snapshot = parse_payload(stored[1]).payload
            if hash_record(snapshot) != stored[0] or snapshot.snapshot_id != snapshot_id:
                raise ContractError()
            if snapshot.environment != environment or snapshot.account_ref != account_ref:
                raise ContractError()
            return snapshot

    def append(self, snapshot):
        if type(snapshot) is not PortfolioSnapshot:
            raise ContractError()
        encoded = canonical_bytes(CanonicalPayload('PortfolioSnapshot', 1, 'synthetic', snapshot))
        checked = parse_payload(encoded).payload
        digest = hash_record(checked)
        with self._lock:
            existing = self._snapshots.get(checked.snapshot_id)
            if existing is not None:
                if existing != (digest, encoded):
                    raise ContractError()
                return parse_payload(existing[1]).payload
            if len(self._snapshots) >= self._capacity:
                raise ContractError()
            if checked.supersedes_snapshot_id is not None:
                predecessor = self.get(checked.supersedes_snapshot_id, environment=checked.environment, account_ref=checked.account_ref)
                validate_predecessor(predecessor, checked.valuation.request)
                seen = {checked.snapshot_id}
                while predecessor is not None:
                    if predecessor.snapshot_id in seen:
                        raise ContractError()
                    seen.add(predecessor.snapshot_id)
                    predecessor = (self.get(predecessor.supersedes_snapshot_id, environment=checked.environment,
                        account_ref=checked.account_ref) if predecessor.supersedes_snapshot_id else None)
            self._snapshots[checked.snapshot_id] = digest, encoded
            return checked
