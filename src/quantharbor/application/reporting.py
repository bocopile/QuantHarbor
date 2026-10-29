"""Q22 결정론적 생성·현재 권리 재검사·로컬 표현. 금융값은 snapshot 그대로다."""
from dataclasses import asdict
import json
import re

from quantharbor.application.valuation import validate_predecessor
from quantharbor.domain.ledger import hash_record
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.reporting import (Report, ReportInputManifest, ReportPresentationRequest,
    ReportRequest, check_rights)
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.domain.valuation import PortfolioSnapshot


def verified(value, kind):
    if type(value) is not kind:
        raise ContractError()
    return parse_payload(canonical_bytes(CanonicalPayload(kind.__name__, 1, 'synthetic', value))).payload


def validate_report_predecessor(predecessor, report):
    if predecessor is None:
        raise ContractError()
    prior = verified(predecessor, Report)
    snapshot = report.snapshot
    if (report.supersedes_report_id != prior.report_id or report.version != prior.version + 1
            or snapshot.snapshot_id == prior.snapshot.snapshot_id
            or snapshot.supersedes_snapshot_id != prior.snapshot.snapshot_id
            or report.created_at < prior.created_at):
        raise ContractError()
    validate_predecessor(prior.snapshot, snapshot.valuation.request)


def validate_report_lineage(report, repository):
    """모든 predecessor를 실제 조회한다. 누락·순환·역순·다른 계좌는 거부."""
    seen = {report.report_id}
    current = report
    for _ in range(128):
        if current.supersedes_report_id is None:
            if current.version != 1:
                raise ContractError()
            return
        prior = repository.get(current.supersedes_report_id, environment=report.environment,
                               account_ref=report.account_ref)
        validate_report_predecessor(prior, current)
        if prior.report_id in seen:
            raise ContractError()
        seen.add(prior.report_id)
        current = prior
    raise ContractError()


def build_report(snapshot, request, current_rights, repository):
    snapshot = verified(snapshot, PortfolioSnapshot)
    request = verified(request, ReportRequest)
    check_rights(snapshot, current_rights, request.created_at, store=True)
    version = 1
    if request.supersedes_report_id is not None:
        prior = repository.get(request.supersedes_report_id, environment=snapshot.environment,
                               account_ref=snapshot.account_ref)
        if prior is None:
            raise ContractError()
        version = verified(prior, Report).version + 1
    manifest = ReportInputManifest(1, 'synthetic', hash_record(snapshot), hash_record(request), version, current_rights)
    status = ('reconciled' if snapshot.valuation.complete and
              snapshot.reconciliation_details.full_account_balances_matched else 'provisional')
    report = verified(Report(1, 'synthetic', 'report:' + hash_record(manifest), snapshot, request, manifest, status), Report)
    validate_report_lineage(report, repository)
    return repository.append(report)


def presentation_data(request):
    request = verified(request, ReportPresentationRequest)
    report, snapshot = request.report, request.report.snapshot
    valuation, reconciliation = snapshot.valuation, snapshot.reconciliation_details
    statement = reconciliation.statement
    return dict(schema_version=1, environment='synthetic', synthetic=True,
        report_id=report.report_id, report_hash=hash_record(report), version=report.version,
        account_ref=report.account_ref, status=report.status, scope_notice=report.scope_notice,
        scope=asdict(valuation.request.scope), base_currency=snapshot.base_currency,
        as_of=snapshot.as_of, knowledge_cutoff=snapshot.knowledge_cutoff,
        projection_mode=snapshot.projection_mode, original_cutoff=valuation.request.original_cutoff,
        created_at=report.created_at, display_at=request.display_at,
        trading_date=report.trading_date, trading_date_reason=report.trading_date_reason,
        snapshot_id=snapshot.snapshot_id, snapshot_hash=report.input_manifest.snapshot_hash,
        snapshot_created_at=snapshot.created_at, supersedes_snapshot_id=snapshot.supersedes_snapshot_id,
        supersedes_report_id=report.supersedes_report_id, ledger_cursor=snapshot.ledger_cursor,
        ledger_schema_version=snapshot.ledger_schema_version, ledger_reducer_version=valuation.projection.reducer_version,
        reporting_policy_version=report.request.reporting_policy_version,
        valuation_policy_version=snapshot.valuation_policy_version,
        reconciliation_policy_version=snapshot.reconciliation_policy.version,
        data_refs=[asdict(x) for x in snapshot.data_refs],
        build_rights=[asdict(x) for x in report.input_manifest.rights],
        display_rights=[asdict(x) for x in request.current_rights],
        valuation=dict(status=snapshot.valuation_status, complete=valuation.complete, nav=valuation.nav,
            known_subtotal=valuation.known_subtotal, known_subtotal_meaning='confirmed_partial_subtotal_only',
            reason_codes=valuation.reason_codes, holdings=[asdict(x) for x in snapshot.holdings],
            cash_by_currency=[asdict(x) for x in snapshot.cash_by_currency],
            native_totals=[asdict(x) for x in valuation.native_totals]),
        orders=dict(status=snapshot.open_orders_status, open_order_refs=snapshot.open_order_refs,
                    reason='orders_not_queried'),
        reconciliation=dict(status=snapshot.reconciliation, detail_status=reconciliation.status,
            requested_scope=asdict(reconciliation.requested_scope),
            covered_scope=asdict(reconciliation.covered_scope) if reconciliation.covered_scope else None,
            missing_scope=reconciliation.missing_scope, compared_domains=reconciliation.compared_domains,
            scope_matched=reconciliation.scope_matched,
            full_account_balances_matched=reconciliation.full_account_balances_matched,
            differences=[asdict(x) for x in reconciliation.differences], reason_codes=reconciliation.reason_codes,
            statement_ref=(dict(statement_id=statement.snapshot.statement_id,
                source_id=statement.snapshot.source_id, source_revision=statement.snapshot.source_revision,
                source_snapshot_id=statement.snapshot.source_snapshot_id,
                source_snapshot_hash=statement.source_snapshot_hash, source_as_of=statement.snapshot.source_as_of,
                observed_at=statement.snapshot.observed_at, ingested_at=statement.snapshot.ingested_at,
                temporal_consistency=statement.temporal_consistency) if statement else None)),
        broker_details=asdict(snapshot.broker_details) if snapshot.broker_details else None)


def escaped_json(value, *, pretty=False):
    # JSON 문자열 quoting에 더해 Markdown/HTML 구분자도 실행 가능한 원문으로 내보내지 않는다.
    result = json.dumps(value, ensure_ascii=True, sort_keys=True,
                        indent=2 if pretty else None, allow_nan=False)
    def token(match):
        result = match.group()
        for char in '<>&`*_[]':
            result = result.replace(char, '\\u' + format(ord(char), '04x'))
        return result

    return re.sub(r'"(?:[^"\\]|\\.)*"', token, result)


def render_report(request, *, output_format='text'):
    if type(output_format) is not str or output_format not in ('text', 'json'):
        raise ContractError()
    data = presentation_data(request)
    if output_format == 'json':
        result = escaped_json(data, pretty=True) + '\n'
        if len(result.encode('utf-8')) > 1048576:
            raise ContractError()
        return result
    # text는 금융 행만 명시적으로 배치한다. 전체 진단 근거는 위 JSON에 보존한다.
    def shown(value):
        return 'unknown (미확인)' if value is None else escaped_json(value)

    def listed(values):
        return ', '.join(shown(x) for x in values) if values else '없음'

    def position(row):
        return (f'종목 {shown(row["instrument_id"])} / 거래소 {shown(row["venue_id"])} / '
                f'매핑 {shown(row["mapping_version"])} / 단위 {shown(row["unit"])}')

    def scope(row):
        if row is None:
            return shown(None)
        positions = ('전 종목' if row['coverage'] == 'entire_account' else
                     '; '.join(position(x) for x in row['positions']) or '지정 없음')
        return (f'{shown(row["coverage"])}; {positions}; 통화 {listed(row["currencies"])}; '
                f'항목 {listed(row["components"])}')

    valuation, reconciliation = data['valuation'], data['reconciliation']
    base = shown(data['base_currency'])
    lines = ['QuantHarbor SYNTHETIC report (합성 자산·현금·대사 보고)',
        f'계좌: {shown(data["account_ref"])} | 기준통화: {base}',
        '평가 범위: ' + scope(data['scope']),
        f'평가 기준 (as_of): {shown(data["as_of"])} | 지식 마감 (cutoff): {shown(data["knowledge_cutoff"])}',
        f'보고 생성: {shown(data["created_at"])} | 표시: {shown(data["display_at"])}',
        f'스냅샷 생성: {shown(data["snapshot_created_at"])} | 조회 모드: {shown(data["projection_mode"])}',
        f'최초 cutoff: {shown(data["original_cutoff"])}',
        f'거래일: {shown(data["trading_date"])}; 사유: {shown(data["trading_date_reason"])}',
        '', '자산 요약',
        f'보고 상태: {shown(data["status"])} | 평가 상태: {shown(valuation["status"])}; 완전 평가: {shown(valuation["complete"])}',
        f'NAV (완전 평가): {shown(valuation["nav"])} {base}',
        f'확인된 부분 소계: {shown(valuation["known_subtotal"])} {base} (전체 자산·비중 분모로 사용하지 않음)',
        '평가 사유: ' + listed(valuation['reason_codes']),
        '', f'보유 자산 ({len(valuation["holdings"])}행)']
    empty = '없음 (평가 범위에서 확인됨)' if valuation['complete'] else 'unknown (미확인; 평가 불완전, 표시 행 없음)'
    if not valuation['holdings']:
        lines.append(empty)
    for row in valuation['holdings']:
        price = row['price']
        lines.extend((position(row['position']) + f' | 수량: {shown(row["position"]["amount"])}',
            '  가격: ' + (f'{shown(price["amount"])} {shown(price["currency"])} / {shown(price["quantity_unit"])}'
                         if price else shown(None)) +
            f' | 원통화: {shown(row["currency"])} | 원통화 평가액: {shown(row["native_value"])}',
            '  평가 사유: ' + listed(row['reason_codes']),
            f'  원가: {shown(row["cost_basis"])} | 미실현손익: {shown(row["unrealized_pnl"])} | '
            f'가격손익: {shown(row["price_pnl"])} | 환손익: {shown(row["fx_pnl"])}; 사유: {shown(row["costing_reason"])}'))
    lines.extend(('', f'통화별 현금 ({len(valuation["cash_by_currency"])}행)'))
    if not valuation['cash_by_currency']:
        lines.append(empty)
    for row in valuation['cash_by_currency']:
        lines.extend((f'통화 {shown(row["currency"])} | 결제 현금: {shown(row["settled_cash"])} | '
            f'미결제 수취: {shown(row["unsettled_receivable"])} | 미결제 지급: {shown(row["unsettled_payable"])} | '
            f'경제적 현금: {shown(row["economic_cash"])}',
            f'  완전 확인: {shown(row["complete"])}; 사유: {listed(row["reason_codes"])}',
            f'  원천 총액: {shown(row["source_total"])} | 예약금: {shown(row["reserved_cash"])} | '
            f'가용금: {shown(row["available_cash"])} | 매수가능액: {shown(row["broker_buy_capacity"])}; '
            f'사유: {shown(row["availability_reason"])}'))
    lines.extend(('', f'통화별 평가·환산 ({len(valuation["native_totals"])}행)'))
    if not valuation['native_totals']:
        lines.append(empty)
    for row in valuation['native_totals']:
        fx = row['fx']
        fx_text = (f'1 {shown(fx["base_currency"])} = {shown(fx["rate"])} {shown(fx["quote_currency"])}; '
                   f'기준 {shown(fx["as_of"])}; 출처 {shown(fx["source_id"])}' if fx else
                   '동일 통화 (환율 불필요)' if row['fx_direction'] == 'identity' else shown(None))
        lines.extend((f'통화 {shown(row["currency"])} | 원통화 확인 소계: {shown(row["known_subtotal"])} | '
            f'기준통화 평가액: {shown(row["base_value"])} {base}',
            f'  FX: {fx_text} | 환산 방향: {shown(row["fx_direction"])}',
            f'  완전 확인: {shown(row["complete"])}; 사유: {listed(row["reason_codes"])}'))
    lines.extend(('', '잔고 대사',
        '대사 범위: 보유 및 세 경제적 현금 component; 주문/체결/손익 미확인.',
        f'대사 상태: {shown(reconciliation["status"])} | 상세 상태: {shown(reconciliation["detail_status"])}',
        '요청 범위: ' + scope(reconciliation['requested_scope']),
        '확인 범위: ' + scope(reconciliation['covered_scope']),
        '누락 범위: ' + listed(reconciliation['missing_scope']),
        '비교 항목: ' + listed(reconciliation['compared_domains']),
        f'요청 범위 일치: {shown(reconciliation["scope_matched"])} | '
        f'전 계좌 잔고 일치: {shown(reconciliation["full_account_balances_matched"])}',
        '대사 사유: ' + listed(reconciliation['reason_codes'])))
    statement = reconciliation['statement_ref']
    if statement:
        lines.extend((f'대사 원천: {shown(statement["statement_id"])} | 출처: {shown(statement["source_id"])} | '
            f'개정: {shown(statement["source_revision"])} | 원천 스냅샷: {shown(statement["source_snapshot_id"])}',
            f'  원천 기준: {shown(statement["source_as_of"])} | 관측: {shown(statement["observed_at"])} | '
            f'수집: {shown(statement["ingested_at"])} | 시점 일관성: {shown(statement["temporal_consistency"])}'))
    else:
        lines.append('대사 원천: unknown (미확인)')
    lines.append(f'대사 비교 내역 ({len(reconciliation["differences"])}행; 차이 = 원천 - 원장)')
    if not reconciliation['differences']:
        lines.append('없음 (요청 범위에서 확인됨)' if reconciliation['scope_matched'] else
                     'unknown (미확인; 비교 내역 없음)')
    for row in reconciliation['differences']:
        identity = position(row['position']) if row['position'] else '통화 ' + shown(row['currency'])
        lines.extend((f'{shown(row["domain"])} | {identity} | 상태: {shown(row["status"])}',
            f'  원장: {shown(row["ledger_amount"])} | 원천: {shown(row["statement_amount"])} | '
            f'차이: {shown(row["difference"])} | 허용차: {shown(row["tolerance"])} | 단위: {shown(row["unit"])}; '
            f'사유: {listed(row["reason_codes"])}'))
    broker = data['broker_details']
    if broker:
        lines.extend((f'증권사 조회: {shown(broker["query_id"])} | 상태: {shown(broker["status"])} | '
            f'원천 상태: {shown(broker["source_status"])}; 원천 완전: {shown(broker["source_complete"])}',
            f'  오류: {shown(broker["source_error"])}; 누락 범위: {listed(broker["source_missing_scope"])}; '
            f'사유: {listed(broker["reason_codes"])}'))
    lines.extend(('', f'미체결 주문: {shown(data["orders"]["status"])} (미확인); 사유: {shown(data["orders"]["reason"])}',
        '주문 참조: ' + (listed(data['orders']['open_order_refs']) if data['orders']['open_order_refs'] else
                       '없음 (미조회; 주문 없음의 근거 아님)'),
        '', '보고 근거·정정',
        f'보고 ID: {shown(data["report_id"])} | 버전: {shown(data["version"])}',
        f'스냅샷 ID: {shown(data["snapshot_id"])}',
        '정정 전 보고 ID: ' + (shown(data['supersedes_report_id']) if data['supersedes_report_id'] else '없음 (최초 보고)'),
        '정정 전 스냅샷 ID: ' + (shown(data['supersedes_snapshot_id']) if data['supersedes_snapshot_id'] else '없음 (최초 스냅샷)'),
        f'정책: 보고 {shown(data["reporting_policy_version"])} / 평가 {shown(data["valuation_policy_version"])} / '
        f'대사 {shown(data["reconciliation_policy_version"])}',
        f'원장: cursor {shown(data["ledger_cursor"])} / schema {shown(data["ledger_schema_version"])} / '
        f'reducer {shown(data["ledger_reducer_version"])}',
        '전체 hash·자료 참조·현재 권리 근거: JSON 출력에서 확인.'))
    result = '\n'.join(lines) + '\n'
    if len(result.encode('utf-8')) > 1048576:
        raise ContractError()
    return result
