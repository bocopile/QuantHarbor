"""Q22 불변 합성 보고. 금융 계산·원문·자유 설명을 추가하지 않는다."""
from dataclasses import dataclass

from .ledger import digest, exact, hash_record, instant, integer
from .market_data import RightsGrant, header
from .primitives import ContractError, identifier
from .valuation import PortfolioSnapshot, ordered

REPORT_POLICY = 'synthetic-reporting-v1'
SCOPE_NOTICE = 'holdings_and_economic_cash_only_orders_fills_and_pnl_unverified'


def check_rights(snapshot, current_rights, at, *, store):
    """과거 proof 권리로 현재 소비를 허용하지 않는다. dataset당 정확히 하나."""
    ordered(current_rights, RightsGrant, lambda x: (x.source_id, x.dataset_id, x.dataset_version))
    required = {x.selection.dataset_key for x in snapshot.valuation.market_proofs}
    actual = {(x.source_id, x.dataset_id, x.dataset_version) for x in current_rights}
    if actual != required:
        raise ContractError()
    for grant in current_rights:
        for purpose in (('report', 'store') if store else ('report',)):
            if not grant.allows(at=at, purpose=purpose, source_id=grant.source_id,
                                dataset_id=grant.dataset_id, dataset_version=grant.dataset_version):
                raise ContractError()


@dataclass(frozen=True, slots=True)
class ReportRequest:
    schema_version: int
    environment: str
    created_at: str
    reporting_policy_version: str = REPORT_POLICY
    supersedes_report_id: str | None = None

    def __post_init__(self):
        header(self)
        object.__setattr__(self, 'created_at', instant(self.created_at))
        if type(self.reporting_policy_version) is not str or self.reporting_policy_version != REPORT_POLICY:
            raise ContractError()
        if self.supersedes_report_id is not None:
            identifier(self.supersedes_report_id)


@dataclass(frozen=True, slots=True)
class ReportInputManifest:
    schema_version: int
    environment: str
    snapshot_hash: str
    request_hash: str
    version: int
    rights: tuple[RightsGrant, ...]

    def __post_init__(self):
        header(self)
        digest(self.snapshot_hash)
        digest(self.request_hash)
        integer(self.version, 1, 128)
        ordered(self.rights, RightsGrant, lambda x: (x.source_id, x.dataset_id, x.dataset_version))


@dataclass(frozen=True, slots=True)
class Report:
    schema_version: int
    environment: str
    report_id: str
    snapshot: PortfolioSnapshot
    request: ReportRequest
    input_manifest: ReportInputManifest
    status: str
    trading_date: None = None
    trading_date_reason: str = 'trading_date_not_resolved'
    scope_notice: str = SCOPE_NOTICE

    def __post_init__(self):
        header(self)
        exact(self.snapshot, PortfolioSnapshot)
        exact(self.request, ReportRequest)
        exact(self.input_manifest, ReportInputManifest)
        manifest = self.input_manifest
        if (manifest.snapshot_hash, manifest.request_hash) != (hash_record(self.snapshot), hash_record(self.request)):
            raise ContractError()
        if self.report_id != 'report:' + hash_record(manifest):
            raise ContractError()
        if self.created_at < self.snapshot.created_at:
            raise ContractError()
        check_rights(self.snapshot, manifest.rights, self.created_at, store=True)
        expected = ('reconciled' if self.snapshot.valuation.complete and
                    self.snapshot.reconciliation_details.full_account_balances_matched else 'provisional')
        if (type(self.status) is not str or self.status != expected or self.trading_date is not None
                or type(self.trading_date_reason) is not str or self.trading_date_reason != 'trading_date_not_resolved'
                or type(self.scope_notice) is not str or self.scope_notice != SCOPE_NOTICE):
            raise ContractError()
        if (self.supersedes_report_id is None) != (manifest.version == 1):
            raise ContractError()
        if self.supersedes_report_id is not None and (
                self.snapshot.supersedes_snapshot_id is None or self.supersedes_report_id == self.report_id):
            raise ContractError()

    @property
    def version(self):
        return self.input_manifest.version

    @property
    def account_ref(self):
        return self.snapshot.account_ref

    @property
    def created_at(self):
        return self.request.created_at

    @property
    def supersedes_report_id(self):
        return self.request.supersedes_report_id


@dataclass(frozen=True, slots=True)
class ReportPresentationRequest:
    schema_version: int
    environment: str
    report: Report
    display_at: str
    current_rights: tuple[RightsGrant, ...]

    def __post_init__(self):
        header(self)
        exact(self.report, Report)
        object.__setattr__(self, 'display_at', instant(self.display_at))
        if self.display_at < self.report.created_at:
            raise ContractError()
        check_rights(self.report.snapshot, self.current_rights, self.display_at, store=False)
