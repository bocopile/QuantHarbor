"""Q22 최대128개 canonical 메모리 보고. 삭제·영속·외부 전달을 제공하지 않는다."""
from threading import RLock

from quantharbor.application.reporting import validate_report_lineage
from quantharbor.domain.ledger import account, choice, hash_record, identifier, integer
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.reporting import Report
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload


class SyntheticReportRepository:
    def __init__(self, *, capacity=128):
        integer(capacity, 1, 128)
        self._capacity = capacity
        self._reports = {}
        self._lock = RLock()

    def get(self, report_id, *, environment, account_ref):
        identifier(report_id)
        choice(environment, ('synthetic',))
        account(account_ref)
        with self._lock:
            stored = self._reports.get(report_id)
            if stored is None:
                return None
            report = parse_payload(stored[1]).payload
            if type(report) is not Report or hash_record(report) != stored[0] or report.report_id != report_id:
                raise ContractError()
            if report.environment != environment or report.account_ref != account_ref:
                raise ContractError()
            return report

    def append(self, report):
        if type(report) is not Report:
            raise ContractError()
        encoded = canonical_bytes(CanonicalPayload('Report', 1, 'synthetic', report))
        checked = parse_payload(encoded).payload
        digest = hash_record(checked)
        with self._lock:
            existing = self._reports.get(checked.report_id)
            if existing is not None and existing != (digest, encoded):
                raise ContractError()
            validate_report_lineage(checked, self)
            if existing is not None:
                return parse_payload(existing[1]).payload
            if len(self._reports) >= self._capacity:
                raise ContractError()
            self._reports[checked.report_id] = digest, encoded
            return checked
