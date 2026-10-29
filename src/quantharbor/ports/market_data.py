"""Q17 합성 수집/저장 포트. 실제 공급자 capability를 제공하지 않는다."""
from typing import Protocol

from quantharbor.domain.market_data import FetchRequest, MarketEnvelope, PageResult, RightsGrant


class MarketFetchPort(Protocol):
    def fetch(self, request: FetchRequest, cursor: str | None) -> PageResult: ...


class MarketStorePort(Protocol):
    def write(self, envelope: MarketEnvelope, *, rights: RightsGrant, at: str) -> None: ...
    def read(self, dataset_id: str, dataset_version: str, *, rights: RightsGrant, at: str,
             purpose: str) -> MarketEnvelope: ...
