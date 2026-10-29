"""Q19 합성 조회 포트. 동일 프로세스 악성 코드에 대한 격리 경계는 아니다."""
from dataclasses import dataclass, field
from typing import Protocol

from quantharbor.domain.broker_read import BrokerCursor, BrokerReadRequest, exact
from quantharbor.domain.market_data import count, enum
from quantharbor.domain.primitives import ContractError, utc_instant


@dataclass(frozen=True, slots=True)
class FixtureAccountIdentity:
    """고정 영(零) 계좌 fixture의 식별 근거. 실제 계좌 입력을 받지 않는다."""
    version: str = 'synthetic-zero-account-v1'

    def __post_init__(self):
        enum(self.version, ('synthetic-zero-account-v1',))


@dataclass(frozen=True, slots=True)
class BrokerFixturePage:
    request: BrokerReadRequest
    page_index: int
    request_cursor: BrokerCursor
    received_at: str
    raw_body: bytes = field(repr=False)
    tr_cont: str = field(default='', repr=False)
    terminal_evidence: str | None = None
    expected_identity: FixtureAccountIdentity | None = None

    def __post_init__(self):
        exact(self.request, BrokerReadRequest)
        exact(self.request_cursor, BrokerCursor)
        count(self.page_index, 3)
        object.__setattr__(self, 'received_at', utc_instant(self.received_at))
        if type(self.raw_body) is not bytes or len(self.raw_body) > 1048576:
            raise ContractError()
        if type(self.tr_cont) is not str or len(self.tr_cont) > 32:
            raise ContractError()
        if self.terminal_evidence is not None:
            enum(self.terminal_evidence, ('synthetic_terminal_v1',))
        if self.expected_identity is not None:
            exact(self.expected_identity, FixtureAccountIdentity)


class BrokerReadPort(Protocol):
    def fetch(self, request: BrokerReadRequest, cursor: BrokerCursor,
              page_index: int) -> BrokerFixturePage | None: ...
