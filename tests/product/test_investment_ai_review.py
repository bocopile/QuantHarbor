"""Q25 AR1~6 추가 회귀. 고정24 예상값과 별개이며 실제 typed 원천을 사용한다."""
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import json
import unittest

from quantharbor.domain import investment_ai as d
from quantharbor.domain.primitives import ContractError
from quantharbor.application.investment_ai import Sources, current_result, performance_ref, run_research
from quantharbor.adapters.synthetic_investment_ai import DeterministicSyntheticClient, SyntheticAIRepository
from quantharbor.ports.investment_ai import ClientReply, FinancialSource
from synthetic_investment_ai import (NOW, policy, request, response, run, document_source, citation,
    flow_source, candidate_source, full_period_source, full_period_request, synthetic_timezone)


class AIReviewTests(unittest.TestCase):
    def test_AR1_small_response_large_envelope_finalizes_known_charge(self):
        src = document_source(); c = citation(src)
        resp = response(citations=(c,), assumptions=('x' * 2048,) * 30 + ('x' * 1400,))
        self.assertLessEqual(len(d.encoded(resp)), 65536)
        sources = Sources(documents=(src,)); req = request((c.manifest_ref,))
        client = DeterministicSyntheticClient(resp)
        try:
            result = run(req, resp, sources=sources, client=client)
        except ContractError:
            self.fail('AR1: 허용 응답의 결과 포장 초과가 정산 후 저장 밖으로 탈출')
        self.assertEqual(result.status, 'invalid')
        self.assertIsNone(result.response)
        self.assertLessEqual(len(d.encoded(result)), 65536)
        a = sources.repository.attempt('a1')
        self.assertEqual((a.state, a.actual_usage.charge, client.calls), ('settled', 50, 1))
        self.assertEqual(sources.repository.result_for('a1'), result)
        self.assertEqual(sources.repository._holds, {})
        self.assertEqual(sources.repository.get(result.budget_attempt_refs[0]), a)
        denied = replace(src, current_rights=replace(src.current_rights, revoked_at=NOW))
        current = Sources(documents=(denied,), repository=sources.repository)
        self.assertIsNone(current_result(d.ref('result', result.result_id, result), current, at=NOW)[0])

    def test_AR2_predispatch_bad_clock_releases_only_owner_and_stores_failed(self):
        sources = Sources(); p = policy(); client = DeterministicSyntheticClient(response())
        for i in range(3):
            with self.subTest(i=i):
                ticks = iter((NOW, None, NOW))
                try:
                    result = run_research(request(request_id='r' + str(i)), p, sources, client,
                        attempt_id='a' + str(i), reserved=d.priced(69, 20), clock=lambda: next(ticks))
                except ContractError:
                    self.fail('AR2: dispatch 전 clock 실패가 예약/동시성 슬롯을 남김')
                a = sources.repository.attempt('a' + str(i))
                self.assertEqual((result.status, a.state, a.dispatch_at, a.actual_usage),
                    ('failed', 'cancelled_before_dispatch', None, None))
                self.assertEqual(sources.repository.result_for(a.attempt_id), result)
                self.assertEqual(sources.repository._holds, {})
        self.assertEqual(client.calls, 0)
        self.assertEqual(sources.repository.balance(p), p.window_caps.charge)
        self.assertEqual(run(request(request_id='next'), response(), sources=sources, attempt='next').status, 'complete')

    def test_AR2_nonowner_never_cancels_untransmitted_owner(self):
        sources = Sources(); repo = sources.repository; req = request(); p = policy()
        repo.reserve(req, p, 'a1', d.priced(69, 20), at=NOW)
        before = (dict(repo._records), dict(repo._holds), dict(repo._attempts), set(repo._blocked))
        ticks = iter((NOW, None))
        with self.assertRaises(ContractError):
            run_research(req, p, sources, DeterministicSyntheticClient(response()), attempt_id='a1',
                reserved=d.priced(69, 20), clock=lambda: next(ticks))
        self.assertEqual((repo._records, repo._holds, repo._attempts, repo._blocked), before)

    def test_AR3_actual_sale_fraction_slippage_ten(self):
        from synthetic_research import sale_fixture
        points, events, cost = sale_fixture()
        self.assertEqual((cost.side, cost.quantity, cost.reference_price, cost.fill_price, cost.slippage),
            ('sell', '10', '100', '99', Fraction(10)))
        points = tuple(replace(p, market_inputs=tuple(replace(m, current_rights=replace(m.current_rights,
            purposes=('ai', 'store', 'research', 'report'))) for m in p.market_inputs)) for p in points)
        from quantharbor.application.valuation import build_snapshot
        from quantharbor.adapters.synthetic_valuation import SyntheticSnapshotRepository
        points = tuple(replace(p, snapshot=build_snapshot(p.snapshot.valuation.projection, p.snapshot.valuation.request,
            p.market_inputs, p.snapshot.valuation.policy, p.snapshot.reconciliation_policy, SyntheticSnapshotRepository(),
            statement=p.snapshot.reconciliation_details.statement)) for p in points)
        from quantharbor.application.research import build_bound_performance
        src = FinancialSource(points, events, build_bound_performance(points, events, costs=(cost,)), costs=(cost,))
        claim = d.NumericClaim('slip', performance_ref(src), 'performance.slippage', None, None,
            '10', 'currency', 'USD', points[-1].snapshot.as_of)
        result = run(request((claim.source_ref,), account_ref=cost.account_ref), response(numeric=(claim,)), sources=Sources(financial=(src,)))
        self.assertEqual(result.status, 'complete')

    def test_AR4_aggregate_rejects_position_and_holding_requires_exact_position(self):
        from quantharbor.domain.valuation import PositionKey
        src = flow_source(); snap = src.points[0].snapshot
        sr = d.ref('snapshot', snap.snapshot_id, snap); pr = performance_ref(src)
        unrelated = PositionKey('unrelated', 'unrelated', 'unrelated', 'share')
        for ref, selector, value, unit, currency, at in (
            (pr, 'performance.twr', '0.21', 'ratio', None, src.points[-1].snapshot.as_of),
            (sr, 'snapshot.nav', '100', 'currency', 'USD', snap.as_of),
            (sr, 'snapshot.economic_cash', '100', 'currency', 'USD', snap.as_of)):
            with self.subTest(selector=selector):
                claim = d.NumericClaim('n', ref, selector, unrelated, None, value, unit, currency, at)
                result = run(request((ref,), account_ref=snap.account_ref), response(numeric=(claim,)), sources=Sources(financial=(src,)))
                self.assertEqual(result.status, 'invalid')
        # A real holding with no trade, same identity/venue/mapping/unit required.
        from synthetic_investment_ai import mdd_source
        src = mdd_source(); snap = src.points[0].snapshot; r = d.ref('snapshot', snap.snapshot_id, snap)
        key = snap.holdings[0].position
        from quantharbor.domain.valuation import PositionKey
        exact = PositionKey(*key.key)
        for position, expected in ((exact, 'complete'), (replace(exact, venue_id='wrong'), 'invalid'),
                                   (None, 'invalid')):
            claim = d.NumericClaim('h', r, 'snapshot.holding_quantity', position, None, '1', 'share', None, snap.as_of)
            result = run(request((r,), account_ref=snap.account_ref, scope=(exact,)), response(numeric=(claim,)), sources=Sources(financial=(src,)))
            self.assertEqual(result.status, expected)

    def test_AR4_candidate_exact_position(self):
        src = candidate_source(); c = src.artifacts.candidates[0]; r = d.ref('candidate', c.candidate_id, c)
        req = request((r,), account_ref=src.request.account_ref, scope=src.request.scope.positions,
            as_of=src.request.as_of, knowledge_cutoff=src.request.knowledge_cutoff,
            evaluated_at=src.request.evaluated_at, deadline=src.request.expires_at)
        for pos, status in ((c.body.terms.position, 'complete'),
                            (replace(c.body.terms.position, venue_id='wrong'), 'invalid'), (None, 'invalid')):
            claim = d.NumericClaim('qty', r, 'candidate.quantity', pos, None, '3', 'share', None, req.as_of)
            result = run(req, response(numeric=(claim,)), sources=Sources(candidates=(src,)), clock=lambda:req.evaluated_at)
            self.assertEqual(result.status, status)
        self.assertEqual(d.ref('candidate', c.candidate_id, c), r)

    def test_AR5_full_period_metrics_survive_malformed_and_exception(self):
        class Bad:
            def invoke(self, *args):
                return ClientReply(b'{', d.priced(49, 0))
        class Broken:
            def invoke(self, *args):
                raise RuntimeError('synthetic only')
        for cadence in ('weekly', 'monthly'):
            src = full_period_source(cadence); req = full_period_request(cadence, src)
            self.assertEqual([p.snapshot.valuation.nav for p in src.points], ['100', '110', '121'])
            for client, status, state in ((DeterministicSyntheticClient(response()), 'partial', 'settled'),
                                          (Bad(), 'invalid', 'settled'), (Broken(), 'failed', 'unknown_charge')):
                with self.subTest(cadence=cadence, status=status):
                    sources = Sources(financial=(src,), timezones=(synthetic_timezone('KR'),))
                    result = run(req, response(), sources=sources, client=client, clock=lambda:req.evaluated_at)
                    self.assertEqual(result.status, status)
                    self.assertIsNotNone(result.period_review)
                    review = result.period_review
                    self.assertEqual((review.period.start, review.period.end), (req.period.start, req.period.end))
                    self.assertEqual({m.expected:m.observed for m in review.metrics},
                        dict(twr='0.21', amount_pnl='21', observed_mdd='0', gross_turnover='0', benchmark_return='0.21'))
                    self.assertTrue(review.intervention_unknowns)
                    self.assertEqual(sources.repository.attempt('a1').state, state)

    def test_AR6_manifest_prepares_actual_variants_before_any_case(self):
        from test_investment_ai_evaluation import FixedEvaluation
        FixedEvaluation.setUpClass()
        manifest = json.loads(FixedEvaluation.manifest_path.read_text())
        self.assertTrue('cases' in manifest, 'AR6: 공통 refs만 기록하고 실제 사례별 변형 입력이 없음')
        self.assertEqual(set(manifest['cases']), {'E%02d' % i for i in range(1, 25)})
        self.assertFalse(FixedEvaluation.records)
        for case_id, case in manifest['cases'].items():
            self.assertTrue(case['variants'], case_id)
            self.assertEqual(case, FixedEvaluation.prepared[case_id].manifest())
        self.assertNotEqual(manifest['cases']['E03']['input_refs'], manifest['cases']['E04']['input_refs'])
        correction = FixedEvaluation.prepared['E03'].variants['main']
        missing = FixedEvaluation.prepared['E04'].variants['main']
        self.assertIn('rev.a', {c.revision.revision_id for c in correction.source_inputs['documents'][0].bundle.claims})
        self.assertIn('missing', missing.source_inputs['documents'][0].bundle.manifest.request.expected_document_ids)
        self.assertEqual(manifest['cases']['E04']['variants']['main']['source_omissions'], ['document:missing'])
        grants = manifest['cases']['E21']['variants']
        self.assertEqual(grants['0']['current_grants'][0]['rights_ref'], 'other')
        self.assertNotIn('ai', grants['1']['current_grants'][0]['purposes'])
        self.assertEqual(grants['6']['current_grants'][0]['dataset_version'], 'wrong')
        self.assertEqual(len(FixedEvaluation.prepared['E22'].variants['3'].payload), 65537)
        for case in FixedEvaluation.prepared.values():
            for v in case.variants.values():
                row = v.manifest()
                self.assertEqual(row['request']['source_refs'], [dict(kind=r.kind,id=r.id,version=r.version,
                    canonicalization_version=r.canonicalization_version,sha256=r.sha256) for r in v.request.source_refs])
                self.assertEqual(row['clock'], dict(mode='constant',value=v.at))

    def test_AR1_report_envelope_fallback_keeps_period_and_exact_charge(self):
        src = full_period_source('weekly'); req = full_period_request('weekly', src)
        resp = response(assumptions=('x' * 2048,) * 31 + ('x' * 1400,))
        self.assertLessEqual(len(d.encoded(resp)), 65536)
        sources = Sources(financial=(src,), timezones=(synthetic_timezone('KR'),))
        result = run(req, resp, sources=sources, clock=lambda:req.evaluated_at)
        self.assertEqual(result.status, 'invalid')
        self.assertIsNone(result.response)
        self.assertIsNotNone(result.period_review)
        self.assertEqual(result.period_review.metrics[0].observed, '0.21')
        self.assertEqual(sources.repository.attempt('a1').actual_usage.charge, 50)
        self.assertEqual(sources.repository._holds, {})

    def test_AR1_oversized_blocked_response_stays_blocked_and_current_rights_checked(self):
        src = document_source(); c = citation(src)
        denied = replace(src, current_rights=replace(src.current_rights, revoked_at=NOW))
        sources = Sources(documents=(denied,))
        resp = response(citations=(c,), assumptions=('x' * 2048,) * 30 + ('x' * 1400,))
        result = run(request((c.manifest_ref,)), resp, sources=sources)
        self.assertEqual(result.status, 'blocked')
        self.assertIn('rights_denied', result.reasons)
        self.assertEqual(sources.repository.attempt('a1').actual_usage.charge, 50)
        self.assertEqual(sources.repository._holds, {})

    def test_AR2_cancellation_keeps_storage_hold_through_failed_result(self):
        class Observed(SyntheticAIRepository):
            hold_at_finish = None
            def finish(self, attempt_id, result):
                self.hold_at_finish = self._holds.get(attempt_id)
                return super().finish(attempt_id, result)
        for bad in (None, RuntimeError('synthetic')):
            repo = Observed(); sources = Sources(repository=repo); ticks = iter((NOW, bad, None))
            def clock():
                tick = next(ticks)
                if isinstance(tick, Exception):
                    raise tick
                return tick
            result = run(request(), response(), sources=sources, clock=clock)
            self.assertEqual(result.status, 'failed')
            self.assertEqual(repo.hold_at_finish, (3, 3 * 65536))
            self.assertEqual(repo._holds, {})
            self.assertFalse(repo._blocked)

    def test_AR5_period_failure_does_not_bypass_current_rights_or_wrong_boundaries(self):
        # The existing short fold stays unknown for a monthly request, even on malformed AI.
        src = flow_source(); req = full_period_request('monthly')
        req = replace(req, source_refs=(performance_ref(src), req.period.timezone_ref), account_ref=src.points[0].snapshot.account_ref)
        class Bad:
            def invoke(self,*args):
                return ClientReply(b'{', d.priced(49,0))
        result = run(req, response(), sources=Sources(financial=(src,), timezones=(synthetic_timezone('KR'),)),
            client=Bad(), clock=lambda:req.evaluated_at)
        self.assertEqual(result.status, 'invalid')
        self.assertTrue(all(m.observed is None and m.code == 'period_mismatch' for m in result.period_review.metrics))
        # Report-purpose current document rights are checked even without a parsed response.
        src = full_period_source('monthly'); req = full_period_request('monthly', src)
        doc = document_source(); c = citation(doc)
        denied = replace(doc, current_rights=replace(doc.current_rights, purposes=('ai','store','research')))
        req = replace(req, source_refs=(*req.source_refs, c.manifest_ref))
        result = run(req, response(), sources=Sources(financial=(src,), documents=(denied,), timezones=(synthetic_timezone('KR'),)),
            client=Bad(), clock=lambda:req.evaluated_at)
        self.assertEqual(result.status, 'blocked')
        self.assertIn('rights_denied', result.reasons)
        self.assertIsNone(result.period_review)

    def test_AR1_receipts_leave_room_for_exact_bounded_failure(self):
        src = flow_source(); r = performance_ref(src)
        req = request((r,), account_ref=src.points[0].snapshot.account_ref)
        class Inline:
            denied = 0
            def invoke(self,request,attempt,dispatcher):
                from quantharbor.adapters.synthetic_investment_ai import AIDenied
                for _ in range(16):
                    try:
                        dispatcher.execute(d.Query('research_view',r))
                    except AIDenied as e:
                        self.denied += 1
                        if e.reason != 'capacity':
                            raise
                return ClientReply(d.encoded(response()), d.priced(49,0))
        sources = Sources(financial=(src,)); client = Inline()
        result = run(req, response(), sources=sources, client=client)
        self.assertGreater(client.denied, 0)
        self.assertEqual(result.status, 'blocked')
        self.assertIn('capacity', result.reasons)
        self.assertEqual(sources.repository.query_count(result.request_ref), 16)
        self.assertEqual(len(result.query_receipts), 16-client.denied)
        self.assertLessEqual(len(d.encoded(result)), 65536)
        self.assertEqual(sources.repository.result_for('a1'), result)
        self.assertEqual(sources.repository.attempt('a1').actual_usage.charge, 50)
        self.assertEqual(sources.repository._holds, {})
