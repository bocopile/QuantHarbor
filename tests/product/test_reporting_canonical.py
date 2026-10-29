from dataclasses import replace
import json
import unittest

from quantharbor.adapters.synthetic_reporting import SyntheticReportRepository
from quantharbor.application.reporting import escaped_json, render_report
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from synthetic_reporting import encoded, presentation, report
from synthetic_valuation import unchecked_bytes


class ReportCanonicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = report()

    def test_report_presentation_request_and_manifest_roundtrip(self):
        for value in (self.report, self.report.request, self.report.input_manifest, presentation(self.report)):
            with self.subTest(kind=type(value).__name__):
                self.assertEqual(parse_payload(encoded(value)).payload, value)

    def test_tampered_financial_status_identity_manifest_and_unknowns_rejected(self):
        cases = ((('snapshot', 'valuation', 'nav'), '100'),
            (('snapshot', 'holdings', 0, 'cost_basis'), '0'),
            (('snapshot', 'cash_by_currency', 0, 'available_cash'), '0'),
            (('snapshot', 'open_orders_status'), 'complete'),
            (('snapshot', 'reconciliation_details', 'full_account_balances_matched'), False),
            (('report_id',), 'report:' + '0' * 64),
            (('status',), 'provisional'), (('trading_date',), '2024-03-08'),
            (('trading_date_reason',), 'user_date'), (('scope_notice',), 'fully_operational'),
            (('input_manifest', 'snapshot_hash'), '0' * 64), (('input_manifest', 'version'), True),
            (('schema_version',), True), (('environment',), 'live'),
            (('request', 'reporting_policy_version'), 'other'),
            (('request', 'created_at'), '2000-01-01T00:00:00Z'))
        for path, value in cases:
            raw = json.loads(encoded(self.report))
            target = raw['payload']
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ContractError):
                parse_payload(json.dumps(raw))

    def test_unknown_fields_duplicate_keys_float_overflow_unicode_and_limit(self):
        raw = encoded(self.report)
        bad = (raw + b' ' * 65536, raw.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1', 1),
            raw.replace(b'"schema_version":1', b'"schema_version":1.0', 1),
            raw.replace(b'"schema_version":1', b'"schema_version":99999999999', 1),
            raw.replace(b'"synthetic"', b'"\\ud800"', 1), b'\xff', b'{}', b'[' * 1000)
        for data in bad:
            with self.subTest(size=len(data)), self.assertRaises(ContractError):
                parse_payload(data)
        source = json.loads(raw)
        source['payload']['ai_text'] = 'SYNTHETIC_CANARY'
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(source))

    def test_forged_objects_rejected_by_constructor_canonical_append_and_display(self):
        r = parse_payload(encoded(self.report)).payload
        object.__setattr__(r.snapshot.valuation, 'nav', '999')
        for action in (lambda: replace(r), lambda: encoded(r),
                       lambda: SyntheticReportRepository().append(r), lambda: parse_payload(unchecked_bytes(r)),
                       lambda: render_report(presentation(r))):
            with self.assertRaises(ContractError):
                action()

    def test_foreign_wrapper_and_forged_current_display_rights_rejected(self):
        with self.assertRaises(ContractError):
            CanonicalPayload('Report', 1, 'paper', self.report)
        p = presentation(self.report)
        object.__setattr__(p.current_rights[0], 'purposes', ('store',))
        with self.assertRaises(ContractError):
            canonical_bytes(CanonicalPayload('ReportPresentationRequest', 1, 'synthetic', p))
        with self.assertRaises(ContractError):
            render_report(p)

    def test_identifier_injection_rejected_and_formatter_escapes_without_loss(self):
        for attempted in ('ref\x1b[31m', '<script>', '[label](url)', '`command`', 'ref\nother'):
            with self.subTest(attempted=attempted), self.assertRaises(ContractError):
                replace(self.report.request, supersedes_report_id=attempted)
        value = {'ref': '\x1b[31m<script>&`*_[x]\n'}
        rendered = escaped_json(value)
        self.assertEqual(json.loads(rendered), value)
        for raw in ('\x1b', '<', '>', '&', '`', '*', '[', ']'):
            self.assertNotIn(raw, rendered)

    def test_schema_is_closed_and_format_is_closed(self):
        raw = json.loads(encoded(self.report))
        for name in ('ReportV2', 'dict'):
            raw['schema_name'] = name
            with self.assertRaises(ContractError):
                parse_payload(json.dumps(raw))
        for output_format in ('html', 'markdown', True, None):
            with self.assertRaises(ContractError):
                render_report(presentation(self.report), output_format=output_format)


if __name__ == '__main__':
    unittest.main()
