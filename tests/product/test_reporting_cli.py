import io
import json
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

from quantharbor.__main__ import main
from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
from quantharbor.adapters.synthetic_reporting import SyntheticReportRepository
from quantharbor.application.reporting import build_report
from quantharbor.runtime.report_cli import MAX_INPUT_BYTES
from synthetic_reporting import (LATER, correction, encoded, presentation, report,
                                  report_request, snapshot)
from synthetic_valuation import (ACCOUNT, HOLDING, START, fx_item, ledger, market, policy,
    price_item, request, rights, statement)
from synthetic_ledger import baseline, cash_pair

ROOT = Path(__file__).resolve().parents[2]


class ReportingCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = report()
        cls.raw = encoded(presentation(cls.value))

    def invoke(self, raw, *args):
        return subprocess.run([sys.executable, '-B', '-m', 'quantharbor', 'report', *args],
            input=raw, cwd=ROOT, env={'PYTHONPATH': str(ROOT / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, timeout=15, check=False)

    def test_actual_api_canonical_to_subprocess_text_and_json(self):
        result = self.invoke(self.raw)
        self.assertEqual((result.returncode, result.stderr), (0, b''))
        text = result.stdout.decode()
        self.assertIn('SYNTHETIC', text)
        self.assertIn('NAV (완전 평가): "1022" "USD"', text)
        self.assertIn('가용금: unknown (미확인)', text)
        self.assertIn('원통화 평가액: "22"', text)
        self.assertIn('통화 "USD" | 결제 현금: "1000" | 미결제 수취: "0" | 미결제 지급: "0" | 경제적 현금: "1000"', text)
        self.assertIn('대사 비교 내역 (7행;', text)
        explicit = self.invoke(self.raw, '--format', 'text')
        self.assertEqual((explicit.returncode, explicit.stdout, explicit.stderr), (0, result.stdout, b''))
        result = self.invoke(self.raw, '--format', 'json')
        self.assertEqual((result.returncode, result.stderr), (0, b''))
        view = json.loads(result.stdout)
        self.assertTrue(view['synthetic'])
        self.assertEqual(view['valuation']['nav'], '1022')
        self.assertEqual(view['orders']['status'], 'unknown')
        self.assertEqual(view['snapshot_id'], self.value.snapshot.snapshot_id)
        self.assertEqual(view['report_id'], self.value.report_id)
        for key in ('account_ref', 'as_of', 'knowledge_cutoff', 'created_at', 'display_at'):
            self.assertIn(view[key], text)
        self.assertEqual(view['snapshot_hash'], self.value.input_manifest.snapshot_hash)
        self.assertEqual(view['build_rights'][0]['rights_ref'], 'syn.rights')
        self.assertEqual(view['display_rights'][0]['rights_ref'], 'syn.rights')
        self.assertTrue(view['data_refs'])
        self.assertNotIn(view['snapshot_hash'], text)
        self.assertNotIn('valuation.', text)
        self.assertIsNone(view['supersedes_report_id'])

    def test_actual_partial_and_explicit_unknown_json_text(self):
        r = report(value=snapshot(market_inputs=()))
        raw = encoded(presentation(r))
        text = self.invoke(raw, '--format', 'text')
        data = self.invoke(raw, '--format', 'json')
        self.assertEqual((text.returncode, data.returncode), (0, 0))
        view = json.loads(data.stdout)
        self.assertIsNone(view['valuation']['nav'])
        self.assertEqual(view['valuation']['known_subtotal'], '1000')
        rendered = text.stdout.decode()
        self.assertIn('NAV (완전 평가): unknown (미확인) "USD"', rendered)
        self.assertIn('확인된 부분 소계: "1000" "USD"', rendered)
        self.assertIn('가격: unknown (미확인) | 원통화: unknown (미확인) | 원통화 평가액: unknown (미확인)', rendered)
        self.assertIn(r'"market\u005fevidence\u005fmissing"', rendered)
        self.assertIn('전 계좌 잔고 일치: true', rendered)
        self.assertEqual((text.stderr, data.stderr), (b'', b''))

    def test_actual_multicurrency_text_and_full_json_provenance(self):
        store = ledger(seed=False)
        opening = replace(baseline(), account_ref=ACCOUNT, effective_at=START,
            cash_legs=cash_pair('settled_cash', '1000', 'opening_equity') +
                cash_pair('settled_cash', '1300', 'opening_equity', currency='KRW'), position_deltas=(HOLDING,))
        self.assertEqual(store.append(opening, recorded_at=START).status, 'accepted')
        p = store.replay(ACCOUNT, as_of=request().as_of, knowledge_cutoff=request().knowledge_cutoff)
        s = snapshot(projection=p, request=replace(request(), base_currency='KRW'), policy=policy(fx=True),
            market_inputs=(market(records=(price_item(), fx_item())),), statement=None)
        raw = encoded(presentation(report(value=s)))
        text, data = self.invoke(raw), self.invoke(raw, '--format', 'json')
        self.assertEqual((text.returncode, data.returncode, text.stderr, data.stderr), (0, 0, b'', b''))
        rendered = text.stdout.decode()
        for expected in ('NAV (완전 평가): "1329900" "KRW"', '통화별 현금 (2행)',
            '통화 "KRW" | 결제 현금: "1300" | 미결제 수취: "0" | 미결제 지급: "0" | 경제적 현금: "1300"',
            '통화 "USD" | 결제 현금: "1000" | 미결제 수취: "0" | 미결제 지급: "0" | 경제적 현금: "1000"',
            '통화 "KRW" | 원통화 확인 소계: "1300" | 기준통화 평가액: "1300" "KRW"',
            '통화 "USD" | 원통화 확인 소계: "1022" | 기준통화 평가액: "1328600" "KRW"',
            'FX: 1 "USD" = "1300" "KRW";', '환산 방향: "multiply"',
            '대사 원천: unknown (미확인)'):
            self.assertIn(expected, rendered)
        view = json.loads(data.stdout)
        self.assertEqual(view['valuation']['nav'], '1329900')
        self.assertEqual([(x['currency'], x['settled_cash']) for x in view['valuation']['cash_by_currency']],
                         [('KRW', '1300'), ('USD', '1000')])
        self.assertEqual(view['valuation']['native_totals'][1]['fx']['rate'], '1300')
        self.assertIsNone(view['reconciliation']['statement_ref'])
        self.assertTrue(view['data_refs'])
        self.assertTrue(view['display_rights'])

    def test_actual_mismatch_text_raw_differences_and_json_diagnostics(self):
        r = report(value=snapshot(statement=statement(holdings=(replace(HOLDING, amount='3'),))))
        raw = encoded(presentation(r))
        text, data = self.invoke(raw), self.invoke(raw, '--format', 'json')
        self.assertEqual((text.returncode, data.returncode, text.stderr, data.stderr), (0, 0, b'', b''))
        rendered = text.stdout.decode()
        self.assertIn('NAV (완전 평가): "1022" "USD"', rendered)
        self.assertIn('대사 상태: "mismatch" | 상세 상태: "mismatch"', rendered)
        self.assertIn('원장: "2" | 원천: "3" | 차이: "1" | 허용차: "0" | 단위: "share"; 사유: 없음', rendered)
        self.assertIn('대사 비교 내역 (7행;', rendered)
        view = json.loads(data.stdout)
        self.assertEqual((view['valuation']['status'], view['reconciliation']['status']), ('complete', 'mismatch'))
        self.assertEqual(len(view['reconciliation']['differences']), 7)
        self.assertEqual(view['reconciliation']['differences'][0]['difference'], '1')
        self.assertEqual(len(view['reconciliation']['statement_ref']['source_snapshot_hash']), 64)

    def test_actual_correction_snapshot_and_report_references(self):
        snapshots, reports = SyntheticSnapshotRepository(), SyntheticReportRepository()
        s = snapshot(repository=snapshots)
        first = report(value=s, repository=reports)
        corrected = build_report(correction(snapshots, s),
            report_request(created_at=LATER, supersedes_report_id=first.report_id), (rights(),), reports)
        result = self.invoke(encoded(presentation(corrected, at=LATER)), '--format', 'json')
        self.assertEqual((result.returncode, result.stderr), (0, b''))
        data = json.loads(result.stdout)
        self.assertEqual(data['version'], 2)
        self.assertEqual(data['supersedes_report_id'], first.report_id)
        self.assertEqual(data['supersedes_snapshot_id'], s.snapshot_id)
        self.assertEqual(data['projection_mode'], 'restated')
        result = self.invoke(encoded(presentation(corrected, at=LATER)))
        self.assertEqual((result.returncode, result.stderr), (0, b''))
        text = result.stdout.decode()
        for expected in (f'보고 ID: "{corrected.report_id}" | 버전: 2',
                         f'스냅샷 ID: "{corrected.snapshot.snapshot_id}"',
                         f'정정 전 보고 ID: "{first.report_id}"',
                         f'정정 전 스냅샷 ID: "{s.snapshot_id}"',
                         '조회 모드: "restated"',
                         f'최초 cutoff: "{s.knowledge_cutoff}"',
                         '보고 생성: "2024-03-09T00:00:00.000000Z" | 표시: "2024-03-09T00:00:00.000000Z"',
                         'NAV (완전 평가): "1022" "USD"'):
            self.assertIn(expected, text)

    def test_invalid_oversized_nonpresentation_and_noncanonical_input_are_fixed_errors(self):
        canary = b'SYNTHETIC_REPORT_CANARY'
        for raw in (b'', canary, b'\xff', b'{}', b'x' * (MAX_INPUT_BYTES + 1),
                    encoded(self.value), self.raw + b' ' * MAX_INPUT_BYTES,
                    self.raw.replace(b'"display_at":', b'"ai_text":"' + canary + b'","display_at":', 1)):
            with self.subTest(size=len(raw)):
                result = self.invoke(raw)
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                    (2, b'', b'QuantHarbor: invalid synthetic report input.\n'))

    def test_revoked_current_rights_and_tampered_snapshot_not_displayed(self):
        for path, replacement in ((('current_rights', 0, 'purposes'), ['store']),
                                  (('report', 'snapshot', 'valuation', 'nav'), '9999')):
            data = json.loads(self.raw)
            target = data['payload']
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = replacement
            result = self.invoke(json.dumps(data).encode())
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (2, b'', b'QuantHarbor: invalid synthetic report input.\n'))

    def test_no_path_shell_or_output_arguments_and_legacy_commands_preserved(self):
        for args in (('--input', 'SYNTHETIC_CANARY'), ('--output', 'SYNTHETIC_CANARY'),
                     ('--format', 'html'), ('SYNTHETIC_CANARY',)):
            result = self.invoke(self.raw, *args)
            self.assertEqual((result.returncode, result.stdout, result.stderr),
                             (2, b'', b'QuantHarbor: invalid command.\n'))
        for args in (['status'], ['--version'], ['--help'], ['validate-config', str(ROOT / 'config/runtime.synthetic.toml')]):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(args), 0)
            result = subprocess.run([sys.executable, '-B', '-m', 'quantharbor', *args], cwd=ROOT,
                env={'PYTHONPATH': str(ROOT / 'src'), 'PYTHONDONTWRITEBYTECODE': '1'},
                input=b'', capture_output=True, timeout=15, check=False)
            self.assertEqual((result.returncode, result.stdout.decode(), result.stderr), (0, out.getvalue(), b''))

    def test_stdin_read_is_bounded_and_unexpected_errors_not_reflected(self):
        class BoundedInput:
            def read(self, count):
                self.count = count
                raise RuntimeError('SYNTHETIC_REPORT_CANARY')
        buffer = BoundedInput()
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.stdin') as stdin, redirect_stdout(out), redirect_stderr(err):
            stdin.buffer = buffer
            code = main(['report'])
        self.assertEqual(buffer.count, MAX_INPUT_BYTES + 1)
        self.assertEqual((code, out.getvalue(), err.getvalue()),
                         (2, '', 'QuantHarbor: invalid synthetic report input.\n'))


if __name__ == '__main__':
    unittest.main()
