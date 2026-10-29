"""Q20 내부 합성 원장 포트. 외부 주문/계좌 API를 노출하지 않는다."""
from typing import Protocol
from quantharbor.domain.ledger import AppendResult, LedgerProjection, SyntheticLedgerSubmission


class LedgerPort(Protocol):
    def append(self, submission: SyntheticLedgerSubmission, *, recorded_at: str,
               reprocess: bool = False) -> AppendResult: ...

    def replay(self, account_ref: str, *, as_of: str, knowledge_cutoff: str,
               cursor: int | None = None, mode: str = 'as_known') -> LedgerProjection: ...
