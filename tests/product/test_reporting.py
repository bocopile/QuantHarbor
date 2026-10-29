from dataclasses import FrozenInstanceError, replace
from decimal import localcontext
import json
import unittest

from quantharbor.adapters.synthetic_reporting import SyntheticReportRepository
from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
from quantharbor.application.reporting import build_report, presentation_data, render_report
from quantharbor.domain.ledger import CashBalance, hash_record
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import parse_payload
from quantharbor.domain.valuation import BalanceScope, CashTolerance, QuantityTolerance
from synthetic_reporting import (NOW, LATER, correction, encoded, presentation, report,
                                  report_request, snapshot)
from synthetic_valuation import (ACCOUNT, HOLDING, KEY, START, fx_item, ledger, market,
    policy, price_item, projection, reconciliation_policy, request, rights, statement, unchecked_bytes)
from synthetic_ledger import baseline, cash_pair, submission


class ReportContentTests(unittest.TestCase):
    def test_complete_exact_snapshot_identity_unknowns_and_determinism(self):
        s = snapshot()
        repo = SyntheticReportRepository()
        r = build_report(s, report_request(), (rights(),), repo)
        self.assertEqual(r, build_report(s, report_request(), (rights(),), repo))
        self.assertEqual(r.snapshot, s)
        self.assertEqual(r.status, 'reconciled')
        self.assertEqual(r.report_id, 'report:' + hash_record(r.input_manifest))
        self.assertNotEqual(hash_record(r), hash_record(r.input_manifest))
        self.assertEqual(parse_payload(encoded(r)).payload, r)
        with self.assertRaises(FrozenInstanceError):
            r.status = 'provisional'
        view = presentation_data(presentation(r))
        self.assertEqual(view['valuation']['nav'], '1022')
        self.assertEqual(view['valuation']['known_subtotal'], '1022')
        self.assertEqual(view['valuation']['holdings'][0]['native_value'], '22')
        self.assertEqual(view['valuation']['cash_by_currency'][0]['settled_cash'], '1000')
        self.assertEqual(view['orders'], dict(status='unknown', open_order_refs=(), reason='orders_not_queried'))
        self.assertIsNone(view['trading_date'])
        self.assertEqual(view['trading_date_reason'], 'trading_date_not_resolved')
        self.assertIn('orders_fills_and_pnl_unverified', view['scope_notice'])
        for key in ('cost_basis', 'unrealized_pnl', 'price_pnl', 'fx_pnl'):
            self.assertIsNone(view['valuation']['holdings'][0][key])
        for key in ('source_total', 'reserved_cash', 'available_cash', 'broker_buy_capacity'):
            self.assertIsNone(view['valuation']['cash_by_currency'][0][key])
        self.assertEqual(view['snapshot_hash'], hash_record(s))

    def test_partial_known_subtotal_is_not_nav_and_holding_retained(self):
        r = report(value=snapshot(market_inputs=()))
        v = presentation_data(presentation(r))['valuation']
        self.assertEqual(r.status, 'provisional')
        self.assertIsNone(v['nav'])
        self.assertEqual(v['known_subtotal'], '1000')
        self.assertEqual(v['known_subtotal_meaning'], 'confirmed_partial_subtotal_only')
        self.assertEqual(v['holdings'][0]['position']['amount'], '2')
        self.assertIsNone(v['holdings'][0]['price'])
        self.assertTrue(v['reason_codes'])

    def test_unknown_empty_source_is_not_zero(self):
        p = ledger(seed=False).replay(ACCOUNT, as_of=request().as_of, knowledge_cutoff=NOW)
        r = report(value=snapshot(projection=p, request=replace(request(), ledger_cursor=0),
                                  statement=None, market_inputs=()))
        view = presentation_data(presentation(r))
        self.assertIsNone(view['valuation']['nav'])
        self.assertEqual(view['valuation']['known_subtotal'], '0')
        self.assertTrue(view['valuation']['reason_codes'])
        self.assertEqual(view['reconciliation']['status'], 'unreconciled')

    def test_explicit_complete_zero_is_zero(self):
        store = ledger(seed=False)
        self.assertEqual(store.append(replace(baseline(), account_ref=ACCOUNT, effective_at=START,
            cash_legs=()), recorded_at=START).status, 'accepted')
        p = store.replay(ACCOUNT, as_of=request().as_of, knowledge_cutoff=NOW)
        r = report(value=snapshot(projection=p, market_inputs=(), statement=statement(holdings=(), cash=())))
        self.assertEqual(r.snapshot.valuation.nav, '0')
        self.assertEqual(r.status, 'reconciled')
        text = render_report(presentation(r, grants=()))
        self.assertIn('NAV (완전 평가): "0" "USD"', text)
        self.assertIn('보유 자산 (0행)\n없음 (평가 범위에서 확인됨)', text)
        self.assertIn('통화별 현금 (0행)\n없음 (평가 범위에서 확인됨)', text)

    def test_multicurrency_and_exact_decimal_context_independent(self):
        s = snapshot(request=replace(request(), base_currency='KRW'), policy=policy(fx=True),
            market_inputs=(market(records=(price_item(), fx_item())),))
        with localcontext() as ctx:
            ctx.prec = 2
            r = report(value=s)
            view = presentation_data(presentation(r))
        self.assertEqual(view['valuation']['nav'], '1328600')
        self.assertEqual(view['valuation']['native_totals'][0]['known_subtotal'], '1022')
        self.assertEqual(view['valuation']['native_totals'][0]['fx']['rate'], '1300')
        # USD cash fact retains all 18 stored fractional digits.
        p = ledger(holdings=(), cash='1.123456789012345678').replay(ACCOUNT, as_of=request().as_of, knowledge_cutoff=NOW)
        s = snapshot(projection=p, statement=None, market_inputs=())
        r = build_report(s, report_request(), (), SyntheticReportRepository())
        view = presentation_data(presentation(r, grants=()))
        self.assertEqual(view['valuation']['cash_by_currency'][0]['settled_cash'], '1.123456789012345678')
        self.assertEqual(view['valuation']['nav'], '1.12')
        text = render_report(presentation(r, grants=()))
        self.assertIn('결제 현금: "1.123456789012345678"', text)
        self.assertIn('NAV (완전 평가): "1.12" "USD"', text)

    def test_two_native_currencies_preserve_each_cash_component(self):
        store = ledger(seed=False)
        opening = replace(baseline(), account_ref=ACCOUNT, effective_at=START,
            cash_legs=cash_pair('settled_cash', '1000', 'opening_equity') +
                cash_pair('settled_cash', '1300', 'opening_equity', currency='KRW'), position_deltas=(HOLDING,))
        self.assertEqual(store.append(opening, recorded_at=START).status, 'accepted')
        p = store.replay(ACCOUNT, as_of=request().as_of, knowledge_cutoff=NOW)
        s = snapshot(projection=p, request=replace(request(), base_currency='KRW'), policy=policy(fx=True),
            market_inputs=(market(records=(price_item(), fx_item())),), statement=None)
        view = presentation_data(presentation(report(value=s)))
        self.assertEqual(view['valuation']['nav'], '1329900')
        rows = view['valuation']['cash_by_currency']
        self.assertEqual([(x['currency'], x['settled_cash']) for x in rows], [('KRW', '1300'), ('USD', '1000')])
        self.assertEqual([x['unsettled_payable'] for x in rows], ['0', '0'])

    def test_reconciliation_and_valuation_are_independent(self):
        s = snapshot(statement=statement(holdings=(replace(HOLDING, amount='3'),)))
        r = report(value=s)
        view = presentation_data(presentation(r))
        self.assertEqual((view['valuation']['status'], view['reconciliation']['status']), ('complete', 'mismatch'))
        self.assertEqual(r.status, 'provisional')
        delta = next(x for x in view['reconciliation']['differences'] if x['domain'] == 'holdings')
        self.assertEqual((delta['ledger_amount'], delta['statement_amount'], delta['difference']), ('2', '3', '1'))
        r = report(value=snapshot(market_inputs=()))
        self.assertEqual((r.snapshot.valuation_status, r.snapshot.reconciliation), ('incomplete', 'matched'))
        self.assertEqual(r.status, 'provisional')

    def test_subset_match_keeps_both_scopes_without_full_promotion(self):
        scope = BalanceScope('subset', (KEY,), (), ('holdings',))
        r = report(value=snapshot(request=replace(request(), scope=scope),
            statement=statement(cash=(), source_changes={'scope': scope}, requested_scope=scope)))
        view = presentation_data(presentation(r))
        self.assertEqual(r.status, 'provisional')
        self.assertEqual(view['reconciliation']['detail_status'], 'matched')
        self.assertEqual(view['reconciliation']['status'], 'incomplete')
        self.assertTrue(view['reconciliation']['scope_matched'])
        self.assertFalse(view['reconciliation']['full_account_balances_matched'])
        self.assertEqual(view['scope']['coverage'], 'subset')

    def test_rights_required_even_for_held_proof(self):
        s = snapshot(market_inputs=(market(current_rights=rights(revoked_at=NOW)),))
        self.assertFalse(s.valuation.market_proofs[0].selected)
        with self.assertRaises(ContractError):
            build_report(s, report_request(), (), SyntheticReportRepository())

    def test_text_and_json_consistent_no_raw_market_source(self):
        r = report()
        text = render_report(presentation(r))
        view = json.loads(render_report(presentation(r), output_format='json'))
        for field in ('report_id', 'snapshot_id', 'account_ref', 'as_of', 'knowledge_cutoff', 'created_at'):
            self.assertIn(view[field], text)
        self.assertIn('SYNTHETIC', text)
        self.assertIn('확인된 부분 소계', text)
        self.assertIn('NAV (완전 평가): "1022" "USD"', text)
        self.assertIn('원가: unknown (미확인)', text)
        self.assertIn('availability', view['valuation']['cash_by_currency'][0]['availability_reason'])
        self.assertNotIn('market_proofs', text)
        self.assertNotIn('selected', view)
        self.assertIn('scope_notice', view)


class ReportTextLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = report()

    def test_complete_human_layout_with_independent_financial_rows(self):
        text = render_report(presentation(self.value))
        for expected in (
            'QuantHarbor SYNTHETIC report (합성 자산·현금·대사 보고)',
            '계좌: "synthetic-account:valuation" | 기준통화: "USD"',
            r'평가 범위: "entire\u005faccount"; 전 종목; 통화 "KRW", "USD";',
            '보고 상태: "reconciled" | 평가 상태: "complete"; 완전 평가: true',
            'NAV (완전 평가): "1022" "USD"',
            '확인된 부분 소계: "1022" "USD" (전체 자산·비중 분모로 사용하지 않음)',
            '보유 자산 (1행)\n종목 "syn.instrument" / 거래소 "syn.venue" / 매핑 "mapping-v1" / 단위 "share" | 수량: "2"\n'
            '  가격: "11" "USD" / "share" | 원통화: "USD" | 원통화 평가액: "22"\n'
            '  평가 사유: 없음',
            '원가: unknown (미확인) | 미실현손익: unknown (미확인) | 가격손익: unknown (미확인) | 환손익: unknown (미확인); '
            r'사유: "costing\u005fspec\u005fpending\u005fq23"',
            '통화별 현금 (1행)\n통화 "USD" | 결제 현금: "1000" | 미결제 수취: "0" | 미결제 지급: "0" | 경제적 현금: "1000"',
            '원천 총액: unknown (미확인) | 예약금: unknown (미확인) | 가용금: unknown (미확인) | 매수가능액: unknown (미확인); '
            r'사유: "availability\u005fsemantics\u005funverified"',
            '통화별 평가·환산 (1행)\n통화 "USD" | 원통화 확인 소계: "1022" | 기준통화 평가액: "1022" "USD"\n'
            '  FX: 동일 통화 (환율 불필요) | 환산 방향: "identity"',
            '대사 상태: "matched" | 상세 상태: "matched"',
            '요청 범위 일치: true | 전 계좌 잔고 일치: true',
            '대사 비교 내역 (7행; 차이 = 원천 - 원장)',
            r'미체결 주문: "unknown" (미확인); 사유: "orders\u005fnot\u005fqueried"',
            '주문 참조: 없음 (미조회; 주문 없음의 근거 아님)',
            '정정 전 보고 ID: 없음 (최초 보고)',
            '정정 전 스냅샷 ID: 없음 (최초 스냅샷)',
            '정책: 보고 "synthetic-reporting-v1" / 평가 "synthetic-valuation-v1" / 대사 "synthetic-reconciliation-v1"',
            '원장: cursor 1 / schema 1 / reducer "synthetic-ledger-v1"',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        later_text = render_report(presentation(self.value, at=LATER))
        for label, value in (('평가 기준 (as_of)', self.value.snapshot.as_of),
                             ('지식 마감 (cutoff)', self.value.snapshot.knowledge_cutoff),
                             ('보고 생성', '2024-03-08T14:31:03.000000Z'),
                             ('표시', '2024-03-09T00:00:00.000000Z'),
                             ('스냅샷 생성', '2024-03-08T14:31:03.000000Z')):
            self.assertIn(f'{label}: "{value}"', later_text)
        for diagnostic in ('valuation.', 'data_refs', 'build_rights', 'display_rights',
                           hash_record(self.value), hash_record(self.value.snapshot)):
            self.assertNotIn(diagnostic, text)
        self.assertTrue(text.endswith('\n'))

    def test_partial_price_and_missing_fx_keep_unknowns_and_reasons(self):
        text = render_report(presentation(report(value=snapshot(market_inputs=()))))
        for expected in ('NAV (완전 평가): unknown (미확인) "USD"',
                         '확인된 부분 소계: "1000" "USD"',
                         '단위 "share" | 수량: "2"',
                         '가격: unknown (미확인) | 원통화: unknown (미확인) | 원통화 평가액: unknown (미확인)',
                         r'"market\u005fevidence\u005fmissing"',
                         '대사 상태: "matched" | 상세 상태: "matched"',
                         '보고 상태: "provisional" | 평가 상태: "incomplete"'):
            self.assertIn(expected, text)
        s = snapshot(request=replace(request(), base_currency='KRW'))
        text = render_report(presentation(report(value=s)))
        self.assertIn('NAV (완전 평가): unknown (미확인) "KRW"', text)
        self.assertIn('원통화 확인 소계: "1022" | 기준통화 평가액: unknown (미확인) "KRW"', text)
        self.assertIn('FX: unknown (미확인) | 환산 방향: "unknown"', text)

    def test_two_currencies_nonzero_components_and_fx_without_recomputation(self):
        store = ledger(seed=False)
        opening = replace(baseline(), account_ref=ACCOUNT, effective_at=START,
            cash_legs=cash_pair('settled_cash', '1000', 'opening_equity') +
                cash_pair('settled_cash', '1300', 'opening_equity', currency='KRW'), position_deltas=(HOLDING,))
        self.assertEqual(store.append(opening, recorded_at=START).status, 'accepted')
        for key, amount, component, cash in (('text-sale', '-1', 'unsettled_receivable', '25'),
                                              ('text-buy', '1', 'unsettled_payable', '-17')):
            trade = submission(key, 'trade', account_ref=ACCOUNT, effective_at=START,
                cash_legs=cash_pair(component, cash, 'trade_clearing', basis='trade'),
                position_deltas=(replace(HOLDING, amount=amount),))
            self.assertEqual(store.append(trade, recorded_at=START).status, 'accepted')
        p = store.replay(ACCOUNT, as_of=request().as_of, knowledge_cutoff=NOW)
        s = snapshot(projection=p, request=replace(request(), ledger_cursor=3, base_currency='KRW'), policy=policy(fx=True),
            market_inputs=(market(records=(price_item(), fx_item())),), statement=None)
        with localcontext() as ctx:
            ctx.prec = 2
            text = render_report(presentation(report(value=s)))
        for expected in ('NAV (완전 평가): "1340300" "KRW"', '통화별 현금 (2행)',
            '통화 "KRW" | 결제 현금: "1300" | 미결제 수취: "0" | 미결제 지급: "0" | 경제적 현금: "1300"',
            '통화 "USD" | 결제 현금: "1000" | 미결제 수취: "25" | 미결제 지급: "-17" | 경제적 현금: "1008"',
            '통화별 평가·환산 (2행)',
            '통화 "KRW" | 원통화 확인 소계: "1300" | 기준통화 평가액: "1300" "KRW"',
            '통화 "USD" | 원통화 확인 소계: "1030" | 기준통화 평가액: "1339000" "KRW"',
            'FX: 1 "USD" = "1300" "KRW";', '출처 "syn.source" | 환산 방향: "multiply"'):
            self.assertIn(expected, text)

    def test_inverse_fx_direction_and_exact_rate(self):
        s = snapshot(request=replace(request(), base_currency='KRW'), policy=policy(fx=True),
            market_inputs=(market(records=(price_item(), fx_item(inverse=True, rate='0.001'))),))
        text = render_report(presentation(report(value=s)))
        self.assertIn('NAV (완전 평가): "1022000" "KRW"', text)
        self.assertIn('FX: 1 "KRW" = "0.001" "USD";', text)
        self.assertIn('환산 방향: "divide"', text)

    def test_every_reconciliation_row_preserves_raw_values_and_thresholds(self):
        s = snapshot(statement=statement(holdings=(replace(HOLDING, amount='3'),), cash=(
            CashBalance('settled_cash', 'KRW', '1'), CashBalance('settled_cash', 'USD', '999'),
            CashBalance('unsettled_payable', 'USD', '-2'), CashBalance('unsettled_receivable', 'USD', '4'))),
            reconciliation_policy=reconciliation_policy(quantities=(QuantityTolerance('share', '0.1'),),
                cash=(CashTolerance('KRW', '1'), CashTolerance('USD', '0.25'))))
        text = render_report(presentation(report(value=s)))
        self.assertIn('보고 상태: "provisional" | 평가 상태: "complete"', text)
        self.assertIn('대사 상태: "mismatch" | 상세 상태: "mismatch"', text)
        rows = (
            ('"holdings" | 종목 "syn.instrument" / 거래소 "syn.venue" / 매핑 "mapping-v1" / 단위 "share" | 상태: "mismatch"',
             '"2" | 원천: "3" | 차이: "1" | 허용차: "0.1" | 단위: "share"'),
            ('"settled\\u005fcash" | 통화 "KRW" | 상태: "matched"',
             '"0" | 원천: "1" | 차이: "1" | 허용차: "1" | 단위: "KRW"'),
            ('"settled\\u005fcash" | 통화 "USD" | 상태: "mismatch"',
             '"1000" | 원천: "999" | 차이: "-1" | 허용차: "0.25" | 단위: "USD"'),
            ('"unsettled\\u005fpayable" | 통화 "KRW" | 상태: "matched"',
             '"0" | 원천: "0" | 차이: "0" | 허용차: "1" | 단위: "KRW"'),
            ('"unsettled\\u005fpayable" | 통화 "USD" | 상태: "mismatch"',
             '"0" | 원천: "-2" | 차이: "-2" | 허용차: "0.25" | 단위: "USD"'),
            ('"unsettled\\u005freceivable" | 통화 "KRW" | 상태: "matched"',
             '"0" | 원천: "0" | 차이: "0" | 허용차: "1" | 단위: "KRW"'),
            ('"unsettled\\u005freceivable" | 통화 "USD" | 상태: "mismatch"',
             '"0" | 원천: "4" | 차이: "4" | 허용차: "0.25" | 단위: "USD"'))
        for identity, values in rows:
            self.assertIn(identity + '\n  원장: ' + values + '; 사유: 없음', text)
        self.assertIn('대사 비교 내역 (7행;', text)

    def test_subset_keeps_identity_scopes_and_unknown_statement_quantities(self):
        subset = BalanceScope('subset', (KEY,), (), ('holdings',))
        r = report(value=snapshot(request=replace(request(), scope=subset),
            statement=statement(cash=(), source_changes={'scope': subset}, requested_scope=subset)))
        text = render_report(presentation(r))
        self.assertIn('평가 범위: "subset"; 종목 "syn.instrument" / 거래소 "syn.venue" / 매핑 "mapping-v1" / 단위 "share";', text)
        self.assertIn('대사 상태: "incomplete" | 상세 상태: "matched"', text)
        self.assertIn('요청 범위 일치: true | 전 계좌 잔고 일치: false', text)
        r = report(value=snapshot(statement=statement(holdings=(), cash=(), omitted_means_zero=False)))
        text = render_report(presentation(r))
        self.assertIn('원장: "2" | 원천: unknown (미확인) | 차이: unknown (미확인) | 허용차: "0"', text)
        self.assertIn(r'"statement\u005fvalue\u005funknown"', text)

    def test_empty_unqueried_collections_are_not_verified_empty(self):
        p = ledger(seed=False).replay(ACCOUNT, as_of=request().as_of, knowledge_cutoff=NOW)
        r = report(value=snapshot(projection=p, request=replace(request(), ledger_cursor=0),
                                  statement=None, market_inputs=()))
        text = render_report(presentation(r))
        for heading in ('보유 자산 (0행)', '통화별 현금 (0행)', '통화별 평가·환산 (0행)'):
            self.assertIn(heading + '\nunknown (미확인; 평가 불완전, 표시 행 없음)', text)
        self.assertIn('NAV (완전 평가): unknown (미확인)', text)
        self.assertIn('확인된 부분 소계: "0"', text)
        self.assertIn('대사 원천: unknown (미확인)', text)
        self.assertIn('unknown (미확인; 비교 내역 없음)', text)
        self.assertNotIn('없음 (평가 범위에서 확인됨)', text)

    def test_all_holdings_retained_with_readable_safe_ids(self):
        holdings = tuple(replace(HOLDING, instrument_id=f'syn.position:{i:02}', amount=str(i + 1)) for i in range(12))
        p = ledger(holdings=holdings).replay(ACCOUNT, as_of=request().as_of, knowledge_cutoff=NOW)
        text = render_report(presentation(report(value=snapshot(projection=p, statement=None, market_inputs=()))))
        self.assertIn('보유 자산 (12행)', text)
        for i in range(12):
            self.assertIn(f'종목 "syn.position:{i:02}" / 거래소 "syn.venue" / 매핑 "mapping-v1" / 단위 "share" | 수량: "{i + 1}"', text)
        self.assertEqual(text.count('원가: unknown (미확인)'), 12)
        for raw in ('\x1b', '\r', '<', '>', '&', '`', '*', '[', ']'):
            self.assertNotIn(raw, text)


class ReportRightsTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = snapshot()

    def test_build_requires_report_and_store_at_explicit_current_time(self):
        bad = ((), (rights(purposes=('store', 'research')),), (rights(purposes=('report',)),),
            (rights(revoked_at=NOW),), (rights(valid_to=NOW),), (rights(valid_from=LATER),),
            (rights(source_id='other'),), (rights(dataset_id='other'),), (rights(dataset_version='other'),),
            (rights(), rights()), (rights(), rights(dataset_id='zz.other')))
        for grants in bad:
            repo = SyntheticReportRepository()
            with self.subTest(grants=grants), self.assertRaises(ContractError):
                build_report(self.snapshot, report_request(), grants, repo)
            self.assertFalse(repo._reports)

    def test_display_checks_current_rights_again_without_store(self):
        r = report(value=self.snapshot)
        for grant in (rights(revoked_at=LATER), rights(valid_to=LATER), rights(purposes=('store',)),
                      rights(dataset_version='other')):
            with self.subTest(grant=grant), self.assertRaises(ContractError):
                presentation(r, at=LATER, grants=(grant,))
        view = presentation_data(presentation(r, at=LATER, grants=(rights(purposes=('report',)),)))
        self.assertEqual(view['display_rights'][0]['purposes'], ('report',))
        self.assertEqual(r.snapshot, self.snapshot)

    def test_generation_and_display_time_must_follow_snapshot_and_report(self):
        with self.assertRaises(ContractError):
            build_report(self.snapshot, report_request(created_at=START), (rights(),), SyntheticReportRepository())
        r = build_report(self.snapshot, report_request(created_at=LATER), (rights(),), SyntheticReportRepository())
        with self.assertRaises(ContractError):
            presentation(r, at=NOW)

    def test_missing_duplicate_unrelated_and_foreign_display_grants_rejected(self):
        r = report(value=self.snapshot)
        for grants in ((), (rights(), rights()), (rights(dataset_id='other'),),
                       (rights(), rights(dataset_id='zz.other'))):
            with self.subTest(grants=grants), self.assertRaises(ContractError):
                presentation(r, grants=grants)


class ReportRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.snapshots = SyntheticSnapshotRepository()
        self.first_snapshot = snapshot(repository=self.snapshots)
        self.repo = SyntheticReportRepository()
        self.first = report(value=self.first_snapshot, repository=self.repo)

    def corrected(self, *, repo=None, value=None, req=None):
        return build_report(value or correction(self.snapshots, self.first_snapshot), req or
            report_request(created_at=LATER, supersedes_report_id=self.first.report_id),
            (rights(),), self.repo if repo is None else repo)

    def test_actual_correction_version_snapshot_chain_and_original_preserved(self):
        r = self.corrected()
        self.assertEqual(r.version, 2)
        self.assertEqual(r.supersedes_report_id, self.first.report_id)
        self.assertEqual(r.snapshot.supersedes_snapshot_id, self.first_snapshot.snapshot_id)
        self.assertEqual(r.snapshot.projection_mode, 'restated')
        self.assertEqual(self.repo.get(self.first.report_id, environment='synthetic', account_ref=ACCOUNT), self.first)
        self.assertEqual(self.repo.append(r), r)
        self.assertEqual(parse_payload(encoded(presentation(r, at=LATER))).payload.report, r)

    def test_missing_actual_predecessor_at_build_and_direct_append(self):
        r = self.corrected()
        fresh = SyntheticReportRepository()
        with self.assertRaises(ContractError):
            self.corrected(repo=fresh, value=r.snapshot)
        with self.assertRaises(ContractError):
            fresh.append(r)
        self.assertFalse(fresh._reports)

    def test_same_snapshot_redisplay_is_not_correction(self):
        with self.assertRaises(ContractError):
            self.corrected(value=self.first_snapshot)
        self.assertEqual(presentation_data(presentation(self.first, at=LATER))['version'], 1)
        self.assertEqual(len(self.repo._reports), 1)

    def test_missing_snapshot_correction_link_rejected(self):
        independent = snapshot(request=replace(request(), request_id='independent'))
        with self.assertRaises(ContractError):
            self.corrected(value=independent)

    def test_account_asof_scope_base_and_cutoff_order_rejected(self):
        # Valid independent snapshots cannot be attached as corrections to another scope/account/time.
        for req, p, pol in (
            (replace(request(), account_ref='synthetic-account:other'),
             replace(projection(), account_ref='synthetic-account:other'), policy()),
            (replace(request(), as_of=START), replace(projection(), as_of=START), policy()),
            (replace(request(), scope=BalanceScope('subset', (KEY,), (), ('holdings',))), projection(), policy()),
            (replace(request(), base_currency='KRW'), projection(), policy())):
            s = snapshot(request=req, projection=p, policy=pol, statement=None)
            with self.subTest(req=req), self.assertRaises(ContractError):
                self.corrected(value=s)
        later = build_report(self.first_snapshot, report_request(created_at=LATER), (rights(),), self.repo)
        s = correction(self.snapshots, self.first_snapshot)
        with self.assertRaises(ContractError):
            self.corrected(value=s, req=report_request(created_at=NOW, supersedes_report_id=later.report_id))

    def test_repository_capacity_idempotence_collision_and_no_eviction(self):
        bounded = SyntheticReportRepository(capacity=1)
        bounded.append(self.first)
        self.assertEqual(bounded.append(self.first), self.first)
        with self.assertRaises(ContractError):
            build_report(self.first_snapshot, report_request(created_at=LATER), (rights(),), bounded)
        self.assertEqual(len(bounded._reports), 1)
        bounded._reports[self.first.report_id] = ('0' * 64, encoded(self.first))
        with self.assertRaises(ContractError):
            bounded.append(self.first)
        with self.assertRaises(ContractError):
            bounded.get(self.first.report_id, environment='synthetic', account_ref=ACCOUNT)
        for capacity in (0, 129, True):
            with self.assertRaises(ContractError):
                SyntheticReportRepository(capacity=capacity)

    def test_get_is_canonical_copy_and_checks_account_environment(self):
        fetched = self.repo.get(self.first.report_id, environment='synthetic', account_ref=ACCOUNT)
        object.__setattr__(fetched.snapshot.valuation, 'nav', '9')
        self.assertEqual(self.repo.get(self.first.report_id, environment='synthetic', account_ref=ACCOUNT).snapshot.valuation.nav, '1022')
        for environment, account in (('paper', ACCOUNT), ('synthetic', 'synthetic-account:other')):
            with self.assertRaises(ContractError):
                self.repo.get(self.first.report_id, environment=environment, account_ref=account)

    def test_corrupted_predecessor_chain_does_not_pass_on_idempotent_append(self):
        r = self.corrected()
        # Simulated corruption only; product exposes no deletion.
        self.repo._reports.pop(self.first.report_id)
        with self.assertRaises(ContractError):
            self.repo.append(r)

    def test_builder_does_not_accept_forged_snapshot(self):
        object.__setattr__(self.first_snapshot.valuation, 'nav', '9999')
        with self.assertRaises(ContractError):
            report(value=self.first_snapshot)


if __name__ == '__main__':
    unittest.main()
