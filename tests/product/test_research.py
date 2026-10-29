from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from quantharbor.adapters.synthetic_research import (FINGERPRINT_PATHS, SyntheticExperimentRepository,
    implementation_fingerprint, load_fixed_spec)
from quantharbor.application.research import (_preflight, _resolve, build_comparison, build_experiment, summarize)
from quantharbor.domain.primitives import ContractError
from quantharbor.domain.research import (ExecutionTrace, FileFingerprint, InputRef, MAX_RESOLVED_BYTES,
    RAW_SPEC_SHA256, known)
from quantharbor.domain.ledger import hash_record
from quantharbor.domain.serialization import CanonicalPayload, canonical_bytes, parse_payload
from quantharbor.research.strategies import SignalOrder, adverse_price, fill_terms, plan_orders
from synthetic_research import fixed_inputs


@lru_cache(maxsize=1)
def results():
    return build_comparison(fixed_inputs(), SyntheticExperimentRepository())


def reseal(result, **changes):
    manifest = replace(result.manifest, **changes)
    return replace(result, manifest=manifest, result_id='experiment:' + hash_record(manifest))


class ResearchTests(unittest.TestCase):
    def test_01_all_24_runs_preserved_with_independent_fixed_expectations(self):
        all_results = results()
        self.assertEqual(len(all_results), 24)
        self.assertEqual(len({r.result_id for r in all_results}), 24)
        self.assertTrue(all(r.status == 'complete' for r in all_results))
        expected_hold = {('KR', 'explicit_costs', 'fold01'): '9952642',
                         ('KR', 'zero_cost_control', 'fold01'): '9966800',
                         ('US', 'explicit_costs', 'fold01'): '9954.81',
                         ('US', 'zero_cost_control', 'fold02'): '10085.6'}
        for r in all_results:
            m, p = r.manifest, r.performance
            if m.strategy == 'cash':
                self.assertEqual((p.twr.value, r.fees.value, r.slippage.value), ('0', '0', '0'))
            elif m.strategy == 'buy_hold' and (m.market_id, m.scenario_id, m.fold_id) in expected_hold:
                self.assertEqual(p.points[-1].nav, expected_hold[(m.market_id, m.scenario_id, m.fold_id)])
            self.assertEqual(r.fx_transaction_cost.value, '0')
            self.assertTrue(all(c.attribution.value is None for c in r.cost_basis))
            print('Q23', m.market_id, m.scenario_id, m.fold_id, m.strategy, r.status,
                  'TWR=' + p.twr.value, 'PnL=' + p.amount_pnl.value,
                  'MDD=' + p.observed_mdd.value, 'fees=' + r.fees.value, 'tax=' + r.taxes.value,
                  'slippage=' + r.slippage.value)

    def test_02_repeated_same_inputs_reproduce_all_manifest_and_result_hashes(self):
        from quantharbor.adapters.synthetic_research import run_fixed_comparison
        with patch('quantharbor.adapters.synthetic_research.fixed_experiment_inputs', return_value=fixed_inputs()):
            again, summaries = run_fixed_comparison()
        self.assertEqual(tuple(summarize(r) for r in again), summaries)
        self.assertEqual(tuple(hash_record(r) for r in results()), tuple(hash_record(r) for r in again))
        self.assertEqual(tuple(hash_record(r.manifest) for r in results()), tuple(hash_record(r.manifest) for r in again))

    def test_closed_immutable_canonical_contracts_and_no_future_q25_name(self):
        r = results()[2]
        encoded = canonical_bytes(CanonicalPayload('ExperimentResult', 1, 'synthetic', r))
        self.assertLessEqual(len(encoded), 65536)
        self.assertEqual(parse_payload(encoded).payload, r)
        with self.assertRaises(FrozenInstanceError):
            r.status = 'changed'
        for change in (dict(schema_name='ResearchResult'), dict(environment='live')):
            raw = json.loads(encoded) | change
            with self.assertRaises(ContractError):
                parse_payload(json.dumps(raw))
        raw = json.loads(encoded)
        raw['payload']['unexpected'] = 'field'
        with self.assertRaises(ContractError):
            parse_payload(json.dumps(raw))
        with self.assertRaises(ContractError):
            replace(r, fees=known(999, ratio=False))
        with self.assertRaises(ContractError):
            replace(r, performance=replace(r.performance, amount_pnl=known(999, ratio=False)))

    def test_fixed_raw_spec_and_allowlisted_actual_file_fingerprint(self):
        raw = Path('docs/contracts/comparison-spec-v1.json').read_bytes()
        self.assertEqual(sha256(raw).hexdigest(), RAW_SPEC_SHA256)
        spec = load_fixed_spec()
        self.assertEqual(spec.source_sha256, RAW_SPEC_SHA256)
        actual = implementation_fingerprint()
        self.assertEqual(tuple(x.path for x in actual.files), FINGERPRINT_PATHS)
        for f in actual.files:
            self.assertEqual(f.sha256, sha256(Path(f.path).read_bytes()).hexdigest())
        run = fixed_inputs()[0]
        with self.assertRaises(ContractError):
            _resolve(replace(run, fingerprint=replace(run.fingerprint,
                files=(replace(run.fingerprint.files[0], sha256='0' * 64), *run.fingerprint.files[1:]))))
        with self.assertRaises(ContractError):
            _resolve(replace(run, spec=replace(run.spec, equity_closes=('999', *run.spec.equity_closes[1:]))))
        from quantharbor.adapters.synthetic_research import _public_bytes
        with self.assertRaises(ContractError):
            _public_bytes('arbitrary-unapproved-path')

    def test_repo_idempotency_hash_account_collision_capacity_and_real_predecessor(self):
        r = results()[0]
        repo = SyntheticExperimentRepository(capacity=2)
        self.assertEqual(repo.append(r), r)
        self.assertEqual(repo.append(r), r)
        self.assertEqual(repo.get(r.result_id, environment='synthetic', account_ref=r.manifest.account_ref), r)
        with self.assertRaises(ContractError):
            repo.get(r.result_id, environment='synthetic', account_ref='synthetic-account:other')
        # 같은 manifest ID에 다른 산식 입력을 가진 결과를 덮어쓸 수 없다.
        conflicting = deepcopy(r)
        object.__setattr__(conflicting, 'cash_benchmark_return', known(1))
        with self.assertRaises(ContractError):
            repo.append(conflicting)
        revised = reseal(r, predecessor=r.result_id)
        self.assertEqual(repo.append(revised), revised)
        self.assertEqual(repo.get(r.result_id, environment='synthetic', account_ref=r.manifest.account_ref), r)
        with self.assertRaises(ContractError):
            SyntheticExperimentRepository().append(revised)
        with self.assertRaises(ContractError):
            repo.append(results()[1])
        wrong = reseal(results()[3], predecessor=r.result_id)
        with self.assertRaises(ContractError):
            SyntheticExperimentRepository().append(wrong)
        repo._results[r.result_id] = ('0' * 64, canonical_bytes(CanonicalPayload('ExperimentResult', 1, 'synthetic', r)))
        with self.assertRaises(ContractError):
            repo.get(r.result_id, environment='synthetic', account_ref=r.manifest.account_ref)

    def test_closed_input_selections_reject_unknown_and_untyped_values(self):
        run = fixed_inputs()[0]
        for values in (dict(market_id='EU'), dict(scenario_id='other'), dict(fold_id=True), dict(strategy=['cash'])):
            with self.assertRaises(ContractError):
                replace(run, **values)

    def test_registry_missing_actions_and_oos_changes_blocked(self):
        run = fixed_inputs()[0]
        with self.assertRaises(ContractError):
            _resolve(replace(run, registry=replace(run.registry, actions='unknown')))
        with self.assertRaises(ContractError):
            _resolve(replace(run, registry=replace(run.registry, declared_at=run.spec.run_at)))
        with self.assertRaises(ContractError):
            replace(run.registry, fit='trained')
        with self.assertRaises(ContractError):
            replace(run.registry, exploration_ref='OOS:selected-best')
        with self.assertRaises(ContractError):
            build_comparison(fixed_inputs()[:-1], SyntheticExperimentRepository())

    def test_pointwise_evidence_future_raw_rights_universe_and_missing_data(self):
        run = fixed_inputs()[1]
        first = run.points[0]
        def reject(point):
            with self.assertRaises(ContractError):
                _resolve(replace(run, points=(point, *run.points[1:])))
        reject(replace(first, market_inputs=()))
        # 최종 시점의 bundle을 과거 평가에 넘기지 않는다.
        reject(replace(first, market_inputs=run.points[-1].market_inputs))
        data = first.market_inputs[0]
        reject(replace(first, market_inputs=(replace(data, current_rights=replace(data.current_rights,
            revoked_at=first.snapshot.created_at)),)))
        future_cat = replace(data.catalog, instruments=tuple(replace(i, known_at=run.spec.run_at) for i in data.catalog.instruments))
        reject(replace(first, market_inputs=(replace(data, catalog=future_cat),)))
        forged = replace(first, market_inputs=(replace(data, bundle=deepcopy(data.bundle)),))
        object.__setattr__(forged.market_inputs[0].bundle.evidence[0].revision.payload, 'adjustment', 'adjusted')
        reject(forged)
        forged = replace(first, market_inputs=(replace(data, bundle=deepcopy(data.bundle)),))
        object.__setattr__(forged.market_inputs[0].bundle.evidence[0].revision, 'published_at', None)
        object.__setattr__(forged.market_inputs[0].bundle.evidence[0].revision, 'publication_unknown_reason', 'unknown')
        reject(forged)
        forged = replace(first, market_inputs=(replace(data, bundle=deepcopy(data.bundle)),))
        object.__setattr__(forged.market_inputs[0].bundle, 'evidence', forged.market_inputs[0].bundle.evidence[:1])
        reject(forged)

    def test_128_and_canonical_and_aggregate_limits(self):
        run = fixed_inputs()[0]
        with self.assertRaises(ContractError):
            replace(run, points=run.points * 43)
        with self.assertRaises(ContractError):
            replace(run, events=run.events * 129)
        r = results()[0]
        refs = tuple(InputRef('market', 'long-ref-' + str(i) + 'a' * 110, '0' * 64) for i in range(128))
        with self.assertRaises(ContractError):
            replace(r.manifest, refs=(*r.manifest.refs, *refs))
        # 유효한 TZif의 말미 padding으로 canonical 개별 상한과 별개인 총량 상한을 넘긴다.
        data = run.points[0].market_inputs[0]
        raw = data.timezone.tzif_bytes + b'\0' * 1000000
        zone = replace(data.timezone, tzif_bytes=raw, content_sha256=sha256(raw).hexdigest())
        large = replace(data, timezone=zone)
        point = replace(run.points[0], market_inputs=(large,) * 9)
        self.assertEqual(MAX_RESOLVED_BYTES, 8388608)
        with self.assertRaises(ContractError):
            _preflight(replace(run, points=(point, *run.points[1:])))
        with self.assertRaises(ContractError):
            parse_payload(b' ' * 65537)

    def test_no_real_broker_model_network_or_test_imports_in_production(self):
        import ast
        for path in ('src/quantharbor/application/research.py', 'src/quantharbor/adapters/synthetic_research.py',
                     'src/quantharbor/research/strategies.py'):
            tree = ast.parse(Path(path).read_text())
            names = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names.extend(x.name for x in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names.append(node.module or '')
            self.assertFalse(any(x.startswith(('tests', 'socket', 'requests', 'urllib', 'anthropic', 'openai'))
                                 or 'broker' in x for x in names))


class StrategyTests(unittest.TestCase):
    def test_next_bar_fixed_quantity_sell_first_and_explicit_t0_settlement(self):
        for run in fixed_inputs():
            events = {e.body.event_id: e for e in run.events}
            for a in run.trace.attempts:
                self.assertLess(a.decision_at, a.fill_at)
                if a.trade is not None:
                    trade = events[a.trade.ref]
                    self.assertEqual(a.fill_at, trade.body.effective_at)
                    self.assertEqual(abs(number(trade.body.position_deltas[0].amount)), number(a.quantity))
                    self.assertTrue(any(e.body.submission.event_type == 'settlement'
                        and e.body.submission.dependency_refs == (trade.body.event_id,)
                        and e.body.effective_at == trade.body.effective_at for e in run.events))
            for when in {a.fill_at for a in run.trace.attempts}:
                group = tuple(a for a in run.trace.attempts if a.fill_at == when)
                self.assertEqual(group, tuple(sorted(group, key=lambda a: (a.side != 'sell', a.instrument_id))))
        orders = plan_orders('buy_hold', '10000', (('equity', '108'), ('etf', '84')), (), first=True)
        self.assertEqual(tuple(o.quantity for o in orders), ('41', '53'))
        self.assertEqual(adverse_price('112', 'buy', '0.0005', '0.01'), '112.06')
        self.assertEqual(adverse_price('112', 'sell', '0.0005', '0.01'), '111.94')

    def test_all_or_none_cash_volume_minimum_and_lot(self):
        spec = load_fixed_spec()
        market, costs = spec.markets[1], spec.costs[0]
        order = SignalOrder('equity', 'buy', '41', '108')
        self.assertEqual(fill_terms(order, '1000', '100000', market, costs, '10000', '0')[-1], 'cash')
        self.assertEqual(order.quantity, '41')
        self.assertEqual(fill_terms(order, '112', '10', market, costs, '10000', '0')[-1], 'volume')
        self.assertEqual(fill_terms(SignalOrder('equity', 'buy', '1', '0.1'), '0.1', '100000', market, costs, '10000', '0')[-1], 'minimum_notional')
        self.assertEqual(fill_terms(SignalOrder('equity', 'sell', '2', '100'), '100', '100000', market, costs, '10000', '1')[-1], 'position')
        with self.assertRaises(ContractError):
            SignalOrder('equity', 'buy', '1.1', '100')


from quantharbor.domain.valuation import number
