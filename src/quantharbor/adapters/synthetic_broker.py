"""Q19 불변 합성 페이지 재생. callback·HTTP client·환경/파일 loader는 없다."""
from dataclasses import dataclass

from quantharbor.domain.broker_read import BrokerCursor, BrokerReadRequest, exact
from quantharbor.domain.market_data import count, sequence
from quantharbor.domain.primitives import ContractError
from quantharbor.ports.broker_read import BrokerFixturePage
from .kis_read import WirePlan


@dataclass(frozen=True, slots=True)
class FixtureTransport:
    """고정 fixture만 반환한다. 합성 신뢰 경계이며 실제 계좌 지원 근거가 아니다."""
    pages: tuple[BrokerFixturePage, ...]

    def __post_init__(self):
        sequence(self.pages, BrokerFixturePage, 4)
        keys = []
        for page in self.pages:
            exact(page, BrokerFixturePage)
            WirePlan(page.request, page.request_cursor)
            key = (page.request, page.page_index, page.request_cursor)
            if key in keys:
                raise ContractError()
            keys.append(key)

    def fetch(self, request: BrokerReadRequest, cursor: BrokerCursor,
              page_index: int) -> BrokerFixturePage | None:
        exact(self, FixtureTransport)
        exact(request, BrokerReadRequest)
        exact(cursor, BrokerCursor)
        count(page_index, 3)
        WirePlan(request, cursor)
        for page in self.pages:
            if page.request == request and page.page_index == page_index and page.request_cursor == cursor:
                return page
        return None
