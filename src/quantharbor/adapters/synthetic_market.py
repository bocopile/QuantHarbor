"""In-memory synthetic adapters only. No disk/network/retry or source credentials."""
from quantharbor.domain.market_data import FetchRequest, MarketEnvelope, PageResult, RightsGrant
from quantharbor.domain.primitives import ContractError


class SyntheticPageAdapter:
    def __init__(self, pages):
        if type(pages) is not tuple or len(pages) > 16 or any(type(p) is not PageResult for p in pages):
            raise ContractError()
        self._pages = pages
        self.calls = 0

    def fetch(self, request, cursor):
        if type(request) is not FetchRequest or request.environment != "synthetic":
            raise ContractError()
        if self.calls >= len(self._pages):
            raise ContractError()
        page = self._pages[self.calls]
        self.calls += 1
        return page


class SyntheticMemoryStore:
    def __init__(self):
        self._versions = {}

    def write(self, envelope, *, rights, at):
        if (type(envelope) is not MarketEnvelope or type(rights) is not RightsGrant
                or envelope.rights_ref != rights.rights_ref
                or not rights.allows(at=at, purpose="store", source_id=envelope.source_id,
                    dataset_id=envelope.dataset_id, dataset_version=envelope.dataset_version)):
            raise ContractError()
        key = (envelope.dataset_id, envelope.dataset_version)
        if key in self._versions:
            raise ContractError()
        self._versions[key] = envelope

    def read(self, dataset_id, dataset_version, *, rights, at, purpose):
        value = self._versions.get((dataset_id, dataset_version))
        if (value is None or type(rights) is not RightsGrant or value.rights_ref != rights.rights_ref
                or not rights.allows(at=at, purpose=purpose, source_id=value.source_id,
                                    dataset_id=dataset_id, dataset_version=dataset_version)):
            raise ContractError()
        return value
