"""Q22 합성 fixture. Q21 공개 API로 입력을 만들고 금액 기대는 별도 선언한다."""
from dataclasses import replace

from quantharbor.adapters.synthetic_reporting import SyntheticReportRepository
from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
from quantharbor.application.reporting import build_report
from quantharbor.application.valuation import build_snapshot
from quantharbor.domain.reporting import ReportPresentationRequest, ReportRequest
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes
from synthetic_valuation import (NOW, LATER, market, policy, projection, reconciliation_policy,
                                 request, rights, statement)


def snapshot(*, repository=None, **changes):
    values = dict(projection=projection(), request=request(), market_inputs=(market(),), policy=policy(),
        reconciliation_policy=reconciliation_policy(), repository=repository or SyntheticSnapshotRepository(),
        statement=statement())
    return build_snapshot(**(values | changes))


def report_request(**changes):
    return ReportRequest(**(dict(schema_version=1, environment='synthetic', created_at=NOW) | changes))


def report(*, value=None, repository=None, **changes):
    value = snapshot() if value is None else value
    return build_report(value, report_request(), (rights(),) if value.valuation.market_proofs else (),
                        repository or SyntheticReportRepository(), **changes)


def presentation(value, *, at=NOW, grants=None):
    if grants is None:
        grants = (rights(),) if value.snapshot.valuation.market_proofs else ()
    return ReportPresentationRequest(1, 'synthetic', value, at, grants)


def encoded(value):
    return canonical_bytes(CanonicalPayload(type(value).__name__, 1, 'synthetic', value))


def correction(snapshot_repository, predecessor, **changes):
    req = replace(predecessor.valuation.request, projection_mode='restated', knowledge_cutoff=LATER,
        evaluated_at=LATER, original_cutoff=NOW, supersedes_snapshot_id=predecessor.snapshot_id)
    p = replace(predecessor.valuation.projection, mode='restated', knowledge_cutoff=LATER)
    return snapshot(repository=snapshot_repository, **(dict(projection=p, request=req) | changes))
