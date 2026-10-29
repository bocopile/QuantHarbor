"""Q22 메모리 보고 append/get 포트. 외부 전송·원장 쓰기는 없다."""
from typing import Protocol

from quantharbor.domain.reporting import Report


class ReportRepository(Protocol):
    def append(self, report: Report) -> Report: ...

    def get(self, report_id: str, *, environment: str, account_ref: str) -> Report | None: ...
